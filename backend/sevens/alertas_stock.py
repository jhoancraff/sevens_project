"""
Alerta diaria de stock minimo por Telegram.

Cada dia se manda UN resumen con los ingredientes que tienen el stock minimo definido (mayor que 0) y cuyo stock
actual esta en ese minimo o por debajo. Los que no tienen minimo definido no entran.

El comando alertas_stock_minimo se ejecuta cada hora (ver sevens-alerta-stock.timer) y llama a
ejecutar(), que decide solo si hay algo que hacer:
  - antes de la hora de inicio (TELEGRAM_ALERTA_STOCK_HORA, por defecto 8) no hace nada;
  - si hoy ya quedo 'enviado' o 'sin_alertas' tampoco, asi sale una sola vez al dia;
  - si hoy no se ha enviado todavia (primera corrida del dia, servidor que estuvo apagado) o la ultima vez fallo,
    lo intenta ahora. Un fallo se reintenta en la hora siguiente.
Cada dia queda un registro (VGEjecucionAlertaStock) con el resultado. El aviso sale por Telegram (chats de
TELEGRAM_CHAT_IDS) y/o por WhatsApp (numeros de WHATSAPP_TO_PHONES), segun lo que este configurado. Si varios
destinos lo reciben y alguno falla, al reintentar solo se manda a los que faltan.
"""
import logging
import os
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .api_views import HIDDEN_INGREDIENT_IDS
from .models import VGEjecucionAlertaStock, VGIngrediente
from .telegram_alertas import configuracion, enviar_texto, limpiar_error
from .whatsapp_alertas import configuracion as configuracion_whatsapp, enviar_plantilla, una_linea

logger = logging.getLogger(__name__)

HORA_INICIO_POR_DEFECTO = 8


def hora_inicio():
    """Hora (0-23, hora de Venezuela) a partir de la cual se puede enviar el aviso del dia."""
    try:
        hora = int(os.getenv('TELEGRAM_ALERTA_STOCK_HORA', HORA_INICIO_POR_DEFECTO))
    except ValueError:
        return HORA_INICIO_POR_DEFECTO
    return min(max(hora, 0), 23)


def ingredientes_en_minimo():
    """Ingredientes con stock minimo definido (> 0) cuyo stock actual esta en ese minimo o por debajo."""
    return list(
        VGIngrediente.objects.exclude(id__in=HIDDEN_INGREDIENT_IDS)
        .filter(stock_minimo__gt=0, stock_actual__lte=F('stock_minimo'))
        .order_by('nombre')
        .values('id', 'nombre', 'unidad_medida', 'stock_actual', 'stock_minimo', 'categoria__nombre')
    )


def _cantidad(valor, unidad):
    """1250.5 -> '1.250,5 g' (miles con punto, decimales con coma, sin ceros sobrantes)."""
    numero = Decimal(valor).quantize(Decimal('0.01'))
    texto = f'{numero:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    if texto.endswith(',00'):
        texto = texto[:-3]
    elif texto.endswith('0'):
        texto = texto[:-1]
    return f'{texto} {unidad}'.strip()


def armar_mensaje(ingredientes, fecha, aviso_ayer=False):
    lineas = [
        f'⚠️ Stock mínimo — {fecha:%d/%m/%Y}',
        f'{len(ingredientes)} ingrediente{"s" if len(ingredientes) != 1 else ""} en su mínimo o por debajo:',
        '',
    ]
    for item in ingredientes:
        unidad = item['unidad_medida']
        lineas.append(
            f"• {item['nombre'].strip()}: {_cantidad(item['stock_actual'], unidad)} "
            f"(mínimo {_cantidad(item['stock_minimo'], unidad)})"
        )
    if aviso_ayer:
        lineas += ['', 'ℹ️ No hay registro del aviso de ayer (el servidor pudo estar apagado).']
    return '\n'.join(lineas)


LIMITE_RESUMEN_WHATSAPP = 700  # la plantilla admite 1024 caracteres en total; el resto es texto fijo


def armar_resumen_whatsapp(ingredientes, limite=LIMITE_RESUMEN_WHATSAPP):
    """
    La lista en UNA linea para la variable {{ingredientes}} de la plantilla (Meta no admite saltos de linea):
    'Pollo: 800 g (mín. 2.000 g) | Sal: 500 g (mín. 500 g)'. Si no caben todos, termina con 'y N más'.
    """
    items = [
        una_linea(f"{item['nombre']}: {_cantidad(item['stock_actual'], item['unidad_medida'])} "
                  f"(mín. {_cantidad(item['stock_minimo'], item['unidad_medida'])})")
        for item in ingredientes
    ]
    partes = []
    largo = 0
    for indice, item in enumerate(items):
        suma = len(item) + (3 if partes else 0)
        despues = len(items) - indice - 1
        cola = len(f' | y {despues} más') if despues else 0
        if partes and largo + suma + cola > limite:
            return ' | '.join(partes) + f' | y {len(items) - indice} más'
        largo += suma
        partes.append(item)
    return ' | '.join(partes)


def _falta_el_de_ayer(hoy):
    """True si el sistema ya habia corrido antes pero no dejo registro de ayer (servidor apagado ese dia)."""
    ayer = hoy - timedelta(days=1)
    return (
        VGEjecucionAlertaStock.objects.filter(fecha__lt=hoy).exists()
        and not VGEjecucionAlertaStock.objects.filter(fecha=ayer).exists()
    )


def destinos_configurados(texto, fecha, resumen, enviar, enviar_whatsapp):
    """
    Lista de (clave, secreto, accion) con todos los destinos del aviso. La clave identifica al destino en el
    registro del dia: el chat de Telegram tal cual, o 'wa:<numero>' para WhatsApp.
    """
    destinos = []
    token, chats = configuracion()
    if token and chats:
        for chat in chats:
            destinos.append((chat, token, lambda chat=chat, token=token: enviar(token, chat, texto)))
    whatsapp = configuracion_whatsapp()
    if whatsapp.completa:
        for numero in whatsapp.numeros:
            destinos.append((
                f'wa:{numero}', whatsapp.token,
                lambda numero=numero, whatsapp=whatsapp: enviar_whatsapp(whatsapp, numero, fecha, resumen),
            ))
    return destinos


def ejecutar(ahora=None, enviar=enviar_texto, enviar_whatsapp=enviar_plantilla):
    """
    Corre la revision de hoy. Devuelve un dict con 'resultado':
      'fuera_de_horario' | 'ya_enviado' | 'sin_alertas' | 'enviado' | 'fallido'
    (y 'error' en el caso de 'fallido'). `enviar(token, chat_id, texto)` y
    `enviar_whatsapp(config, numero, fecha, ingredientes)` se pueden cambiar en las pruebas.
    """
    ahora = timezone.localtime(ahora or timezone.now())
    hoy = ahora.date()
    if ahora.hour < hora_inicio():
        return {'resultado': 'fuera_de_horario'}

    # El registro del dia se bloquea mientras se envia: si dos corridas coinciden, la segunda espera y ve que
    # ya salio, en vez de mandar el aviso doble.
    with transaction.atomic():
        registro, _ = VGEjecucionAlertaStock.objects.select_for_update().get_or_create(fecha=hoy)
        if registro.estado in (VGEjecucionAlertaStock.ENVIADO, VGEjecucionAlertaStock.SIN_ALERTAS):
            return {'resultado': 'ya_enviado'}

        registro.intentos += 1
        ingredientes = ingredientes_en_minimo()
        registro.cantidad_ingredientes = len(ingredientes)

        if not ingredientes:
            registro.estado = VGEjecucionAlertaStock.SIN_ALERTAS
            registro.ultimo_error = ''
            registro.completado_en = ahora
            registro.save()
            return {'resultado': 'sin_alertas'}

        texto = armar_mensaje(ingredientes, hoy, aviso_ayer=_falta_el_de_ayer(hoy))
        destinos = destinos_configurados(
            texto, f'{hoy:%d/%m/%Y}', armar_resumen_whatsapp(ingredientes), enviar, enviar_whatsapp,
        )
        if not destinos:
            error = (
                'El aviso no está configurado: faltan TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_IDS, o '
                'WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN y WHATSAPP_TO_PHONES.'
            )
            registro.estado = VGEjecucionAlertaStock.FALLIDO
            registro.ultimo_error = error
            registro.save()
            return {'resultado': 'fallido', 'error': error}

        ya_enviados = [clave for clave in registro.chats_enviados.split(',') if clave]
        errores = []
        for clave, secreto, accion in destinos:
            if clave in ya_enviados:
                continue
            try:
                accion()
                ya_enviados.append(clave)
            except Exception as error:  # noqa: BLE001 - cualquier fallo de red/Telegram/WhatsApp se registra y se reintenta
                errores.append(f'{clave}: {limpiar_error(error, secreto)}')
        registro.chats_enviados = ','.join(ya_enviados)

        if errores:
            registro.estado = VGEjecucionAlertaStock.FALLIDO
            registro.ultimo_error = '; '.join(errores)
            registro.save()
            logger.warning('Alerta de stock minimo fallida: %s', registro.ultimo_error)
            return {'resultado': 'fallido', 'error': registro.ultimo_error}

        registro.estado = VGEjecucionAlertaStock.ENVIADO
        registro.ultimo_error = ''
        registro.completado_en = ahora
        registro.save()
        return {'resultado': 'enviado', 'ingredientes': len(ingredientes)}
