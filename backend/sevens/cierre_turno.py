"""
Cierre de turno por cajera: al terminar su turno, quien cobró revisa cada
transaccion que registro (cobros que no son de punto de venta + propinas / pagos
extra), marca cuales "llegaron" y cuales "no llegaron", escribe una novedad y
cierra. El acta queda guardada (VGCierreTurno + VGCierreTurnoLinea) y es la
constancia con la que se va a su casa.

Modelo de "pendiente" (no hay apertura de turno ni se cierra "por fecha"):
una transaccion esta pendiente mientras su `cierre_turno` sea NULL, sea de
`fecha_activacion` en adelante, y la haya registrado ese usuario (creado_por).
Un turno que cruza la medianoche, un doble turno o un cierre olvidado funcionan
igual: se cierra lo que haya pendiente.

Los cobros por punto de venta NO entran: ya tienen su propio cierre (el lote POS,
ver lotes_pos.py). Un lote POS abierto con cobros del titular bloquea el cierre
para que primero se cierre el lote.

Mismos tres roles para todo: cualquiera que pueda cobrar (cajera,
administrador, contador, dueño) puede ser titular de un cierre o cerrar el de
otro. Los tipos de cierre salen del servidor, nunca de lo que mande el cliente:

  normal       el titular cierra lo suyo
  tardio       el titular cierra lo suyo y su pendiente mas viejo supera el
               umbral de horas configurado (VGConfiguracionCierreTurno)
  por_tercero  cierra otra persona (el titular se fue sin cerrar)

Un cierre que no es 'normal', o que tiene alguna transaccion "no llego", exige
novedad. Marcar "no llego" no toca el pago ni la contabilidad: solo queda
visible. Todo corre en transaction.atomic con select_for_update, asi un doble
clic o dos personas cerrando a la vez nunca duplican un cierre: el segundo no
encuentra nada pendiente y se rechaza.
"""
from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Min, Q
from django.utils import timezone

from .auth_helpers import _get_role_name, _is_admin_user, _is_cajera_user
from .lotes_pos import _tasa_de_pago
from .models import (
    VGCierreTurno,
    VGCierreTurnoLinea,
    VGConfiguracionCierreTurno,
    VGCorreccionMetodoPago,
    VGCorrelativoFiscal,
    VGIngresoExtra,
    VGLotePOS,
    VGPago,
    VGUsuario,
)

SERIE_CIERRE_TURNO = 'CIERRE_TURNO'
CENTIMOS = Decimal('0.01')

ORIGEN_PAGO = 'pago'
ORIGEN_EXTRA = 'ingreso_extra'
ORIGENES = (ORIGEN_PAGO, ORIGEN_EXTRA)
ESTADO_CONFIRMADA = 'confirmada'
ESTADO_NO_LLEGO = 'no_llego'
ESTADOS_LINEA = (ESTADO_CONFIRMADA, ESTADO_NO_LLEGO)

TIPO_NORMAL = 'normal'
TIPO_TARDIO = 'tardio'
TIPO_POR_TERCERO = 'por_tercero'


class CierreTurnoError(Exception):
    """Regla de negocio incumplida al cerrar un turno; el mensaje es apto para mostrar al usuario."""


# ---------------------------------------------------------------------------
# Permisos y configuracion
# ---------------------------------------------------------------------------
def usuario_puede_cobrar(usuario):
    """La misma condicion con la que las vistas de cobro dejan pasar: cajera, administrador, contador o dueño."""
    return bool(usuario) and bool(_is_admin_user(usuario) or _is_cajera_user(usuario))


def _exigir_admin(usuario):
    if not (usuario and _is_admin_user(usuario)):
        raise CierreTurnoError('Solo un administrador, contador o el dueño puede cambiar esta configuración.')


def activar_cierre_turno(usuario, fecha=None):
    """
    Activa el cierre de turno: desde el inicio de `fecha` (hoy por defecto) las
    transacciones cuentan como pendientes. No se reactiva: mover la fecha de un
    sistema ya activo haria aparecer o desaparecer pendientes sin querer.
    """
    _exigir_admin(usuario)
    with transaction.atomic():
        config = VGConfiguracionCierreTurno.objects.select_for_update().filter().first()
        if config is None:
            config = VGConfiguracionCierreTurno.objects.create()
        if config.activo:
            raise CierreTurnoError(f'El cierre de turno ya está activo desde {config.fecha_activacion:%d/%m/%Y}.')
        config.fecha_activacion = fecha or timezone.localdate()
        config.actualizado_por = usuario
        config.save(update_fields=['fecha_activacion', 'actualizado_por', 'fecha_actualizacion'])
        return config


def actualizar_umbral_tardio(usuario, horas):
    """Cambia las horas a partir de las cuales un cierre propio se marca como tardio."""
    _exigir_admin(usuario)
    try:
        horas = int(horas)
    except (TypeError, ValueError):
        raise CierreTurnoError('El umbral debe ser un número entero de horas.')
    if horas < 1:
        raise CierreTurnoError('El umbral debe ser de al menos 1 hora.')
    with transaction.atomic():
        config = VGConfiguracionCierreTurno.objects.select_for_update().filter().first()
        if config is None:
            config = VGConfiguracionCierreTurno.objects.create()
        config.umbral_tardio_horas = horas
        config.actualizado_por = usuario
        config.save(update_fields=['umbral_tardio_horas', 'actualizado_por', 'fecha_actualizacion'])
        return config


def inicio_conteo(config=None):
    """Instante (00:00 locales del dia de activacion) desde el que cuentan los pendientes; None si esta inactivo."""
    config = config or VGConfiguracionCierreTurno.obtener_config()
    if not config.activo:
        return None
    return timezone.make_aware(datetime.combine(config.fecha_activacion, time.min))


# ---------------------------------------------------------------------------
# Transacciones pendientes
# ---------------------------------------------------------------------------
def pagos_pendientes(titular=None, config=None):
    inicio = inicio_conteo(config)
    if inicio is None:
        return VGPago.objects.none()
    consulta = VGPago.objects.filter(
        estado='completado', cierre_turno__isnull=True, metodo_pago__es_punto_venta=False,
        fecha_pago__gte=inicio, creado_por__isnull=False,
    )
    if titular is not None:
        consulta = consulta.filter(creado_por=titular)
    return consulta


def extras_pendientes(titular=None, config=None):
    """Propinas y pagos extra. El ingreso no facturado es administrativo (no lo registra una cajera al cobrar): no entra."""
    inicio = inicio_conteo(config)
    if inicio is None:
        return VGIngresoExtra.objects.none()
    consulta = (
        VGIngresoExtra.objects
        .filter(cierre_turno__isnull=True, fecha_creacion__gte=inicio, creado_por__isnull=False)
        .exclude(tipo='ingreso_no_facturado')
    )
    if titular is not None:
        consulta = consulta.filter(creado_por=titular)
    return consulta


def _consulta_pagos(consulta):
    return consulta.select_related(
        'metodo_pago', 'nota_entrega__cliente', 'factura__cliente', 'pedido__cliente',
    )


def _nombre_persona(persona):
    if persona is None:
        return ''
    return f'{persona.nombre} {persona.apellido}'.strip()


def _nombre_usuario(usuario):
    if usuario is None:
        return ''
    return usuario.get_full_name() or usuario.username


def _linea_pago(pago):
    """Datos congelados de un cobro: lo que la cajera compara contra su banco."""
    metodo = pago.metodo_pago
    documento = ''
    cliente = ''
    concepto = 'Cobro'
    if pago.nota_entrega_id:
        nota = pago.nota_entrega
        documento = f'Nota {nota.codigo}'
        concepto = f'Cobro de nota {nota.codigo}'
        cliente = _nombre_persona(nota.cliente)
    elif pago.factura_id:
        factura = pago.factura
        documento = f'Factura Nº {factura.numero_factura}' if factura.numero_factura else f'Factura #{factura.id}'
        concepto = f'Cobro de {documento.lower()}'
        cliente = _nombre_persona(factura.cliente)
    elif pago.pedido_id:
        documento = f'Pedido #{pago.pedido_id}'
        concepto = f'Cobro de pedido #{pago.pedido_id}'
        cliente = _nombre_persona(pago.pedido.cliente)
    if metodo.es_cashea:
        concepto = f'Financiado por Cashea — {documento}' if documento else 'Financiado por Cashea'

    monto_bs = None
    if metodo.moneda == 'VES':
        tasa = _tasa_de_pago(pago)
        if tasa:
            monto_bs = (pago.monto * tasa).quantize(CENTIMOS)

    return {
        'origen': ORIGEN_PAGO,
        'origen_id': pago.id,
        'fecha_transaccion': pago.fecha_pago,
        'concepto': concepto,
        'documento': documento,
        'cliente': cliente,
        'numero_cobro': pago.numero_cobro,
        'saldo_posterior': pago.saldo_posterior,
        'referencia': pago.referencia,
        'metodo_pago': metodo,
        'metodo_pago_nombre': metodo.nombre,
        'moneda': metodo.moneda,
        'es_efectivo': metodo.es_efectivo,
        'monto_usd': pago.monto,
        'monto_bs': monto_bs,
        'tasa_cambio_referencia': pago.tasa_cambio_referencia,
    }


def _linea_extra(extra):
    metodo = extra.metodo_pago
    concepto = extra.get_tipo_display()
    if extra.descripcion:
        concepto = f'{concepto} — {extra.descripcion}'
    monto_bs = None
    if metodo.moneda == 'VES' and extra.tasa_cambio_referencia:
        monto_bs = (extra.monto * extra.tasa_cambio_referencia).quantize(CENTIMOS)
    return {
        'origen': ORIGEN_EXTRA,
        'origen_id': extra.id,
        'fecha_transaccion': extra.fecha_creacion,
        'concepto': concepto,
        'documento': '',
        'cliente': '',
        'numero_cobro': None,
        'saldo_posterior': None,
        'referencia': '',
        'metodo_pago': metodo,
        'metodo_pago_nombre': metodo.nombre,
        'moneda': metodo.moneda,
        'es_efectivo': metodo.es_efectivo,
        'monto_usd': extra.monto,
        'monto_bs': monto_bs,
        'tasa_cambio_referencia': extra.tasa_cambio_referencia,
    }


def listar_pendientes(titular, config=None):
    """Lineas pendientes del titular (pagos + propinas/extra), en orden cronologico."""
    lineas = [_linea_pago(pago) for pago in _consulta_pagos(pagos_pendientes(titular, config))]
    lineas += [_linea_extra(extra) for extra in extras_pendientes(titular, config).select_related('metodo_pago')]
    lineas.sort(key=lambda linea: (linea['fecha_transaccion'], linea['origen'], linea['origen_id']))
    return lineas


def resumen_pendientes(config=None, hasta_fecha=None):
    """
    Quien tiene transacciones sin cerrar: por titular, cuantas y desde cuando. Es
    lo que alimenta el aviso "Ana tiene 11 sin cerrar" y el tablero del
    administrador. Ordenado del pendiente mas viejo al mas nuevo.

    `hasta_fecha` limita a lo registrado ese dia o antes (lo que cuenta para cerrar
    la caja de ese dia: lo de dias posteriores no le corresponde).
    """
    acumulado = {}
    for consulta in (pagos_pendientes(config=config), extras_pendientes(config=config)):
        campo_fecha = 'fecha_pago' if consulta.model is VGPago else 'fecha_creacion'
        if hasta_fecha is not None:
            consulta = consulta.filter(**{f'{campo_fecha}__date__lte': hasta_fecha})
        for fila in consulta.values('creado_por').annotate(cantidad=Count('id'), mas_antigua=Min(campo_fecha)):
            item = acumulado.setdefault(fila['creado_por'], {'cantidad': 0, 'mas_antigua': fila['mas_antigua']})
            item['cantidad'] += fila['cantidad']
            item['mas_antigua'] = min(item['mas_antigua'], fila['mas_antigua'])

    usuarios = VGUsuario.objects.select_related('id_role').in_bulk(list(acumulado))
    ahora = timezone.now()
    resumen = []
    for usuario_id, item in acumulado.items():
        usuario = usuarios.get(usuario_id)
        resumen.append({
            'titular_id': usuario_id,
            'titular_nombre': _nombre_usuario(usuario),
            'titular_rol': _get_role_name(usuario) if usuario else '',
            'cantidad': item['cantidad'],
            'mas_antigua': item['mas_antigua'],
            'horas_pendiente': round((ahora - item['mas_antigua']).total_seconds() / 3600, 1),
        })
    resumen.sort(key=lambda fila: fila['mas_antigua'])
    return resumen


def lotes_pos_abiertos_con_cobros_de(titular):
    """Lotes POS todavia abiertos que contienen cobros vigentes del titular: hay que cerrarlos antes del cierre de turno."""
    return VGLotePOS.objects.filter(
        estado='abierto', pagos__creado_por=titular, pagos__estado='completado',
    ).select_related('metodo_pago').distinct()


# ---------------------------------------------------------------------------
# Cierre de caja del dia y cambios posteriores al cierre
# ---------------------------------------------------------------------------
def pendientes_para_cierre_de_caja(fecha):
    """
    Lo que impide cerrar la caja de `fecha`: transacciones de ese dia (o anteriores)
    que todavia no estan en ningun cierre de turno. Sin cierre de turno activado
    no bloquea nada. `por_titular` ya viene listo para serializar.
    """
    config = VGConfiguracionCierreTurno.obtener_config()
    if not config.activo:
        return {'activo': False, 'total': 0, 'por_titular': []}
    por_titular = [
        {**fila, 'mas_antigua': fila['mas_antigua'].isoformat()}
        for fila in resumen_pendientes(config, hasta_fecha=fecha)
    ]
    return {
        'activo': True,
        'total': sum(fila['cantidad'] for fila in por_titular),
        'por_titular': por_titular,
    }


def mensaje_pendientes_cierre_de_caja(pendientes):
    """Texto para el rechazo del cierre de caja: cuantas hay y de quien."""
    detalle = ', '.join(f'{fila["titular_nombre"]}: {fila["cantidad"]}' for fila in pendientes['por_titular'])
    return (
        f'No se puede cerrar la caja: hay {pendientes["total"]} transacción(es) sin cierre de turno ({detalle}). '
        'Cada quien debe cerrar su turno primero (un administrador puede cerrar el de otra persona).'
    )


def _mismo_monto(a, b):
    micro = Decimal('0.000001')
    return a.quantize(micro) == b.quantize(micro)


def modificaciones_de_lineas(lineas):
    """
    Que cambio DESPUES del cierre en las transacciones de estas lineas: {linea.id: [cambio, ...]}.
    Las lineas del acta son una foto congelada (nunca se reescriben): aqui se compara
    esa foto contra el estado actual del cobro / la propina, para que una auditoria
    vea de un vistazo lo que se movio despues de que la cajera se fue tranquila.

    Cada cambio: {'tipo': anulado|cuenta_cambiada|monto_distinto|eliminado, 'detalle': str}
    y, en cuenta_cambiada, quien y cuando lo corrigio / por que, si quedo registro.
    Se resuelve con 3 consultas sin importar cuantas lineas lleguen (lineas debe traer
    `cierre` con select_related).
    """
    lineas = list(lineas)
    ids_pago = [linea.origen_id for linea in lineas if linea.origen == ORIGEN_PAGO]
    ids_extra = [linea.origen_id for linea in lineas if linea.origen == ORIGEN_EXTRA]
    pagos = VGPago.objects.select_related('metodo_pago').in_bulk(ids_pago)
    extras = VGIngresoExtra.objects.select_related('metodo_pago').in_bulk(ids_extra)

    correcciones = defaultdict(list)
    for correccion in (
        VGCorreccionMetodoPago.objects
        .filter(Q(tipo=ORIGEN_PAGO, registro_id__in=ids_pago) | Q(tipo=ORIGEN_EXTRA, registro_id__in=ids_extra))
        .select_related('metodo_anterior', 'metodo_nuevo', 'creado_por')
        .order_by('fecha_creacion')
    ):
        correcciones[(correccion.tipo, correccion.registro_id)].append(correccion)

    resultado = {}
    for linea in lineas:
        actual = (pagos if linea.origen == ORIGEN_PAGO else extras).get(linea.origen_id)
        cambios = []
        if actual is None:
            cambios.append({'tipo': 'eliminado', 'detalle': 'El registro ya no existe.'})
        else:
            if linea.origen == ORIGEN_PAGO and actual.estado != 'completado':
                cambios.append({'tipo': 'anulado', 'detalle': 'El cobro fue anulado después del cierre.'})
            if actual.metodo_pago_id != linea.metodo_pago_id:
                cambio = {
                    'tipo': 'cuenta_cambiada',
                    'detalle': f'La cuenta pasó de {linea.metodo_pago_nombre} a {actual.metodo_pago.nombre}.',
                }
                posteriores = [
                    c for c in correcciones.get((linea.origen, linea.origen_id), [])
                    if c.fecha_creacion >= linea.cierre.fecha_cierre
                ]
                if posteriores:
                    ultima = posteriores[-1]
                    cambio.update({
                        'por': _nombre_usuario(ultima.creado_por),
                        'fecha': ultima.fecha_creacion.isoformat(),
                        'motivo': ultima.motivo,
                    })
                cambios.append(cambio)
            if not _mismo_monto(actual.monto, linea.monto_usd):
                cambios.append({
                    'tipo': 'monto_distinto',
                    'detalle': f'El monto era ${linea.monto_usd:.2f} y ahora es ${actual.monto:.2f}.',
                })
        if cambios:
            resultado[linea.id] = cambios
    return resultado


# ---------------------------------------------------------------------------
# Acta imprimible
# ---------------------------------------------------------------------------
def datos_del_acta(cierre):
    """
    Todo lo que necesitan el ticket termico y el PDF del acta, ya agrupado por
    cuenta (en el orden en que aparece cada una) y con las horas en hora local. Las
    lineas son la foto congelada del cierre; `modificaciones` trae lo que cambio
    despues (ver modificaciones_de_lineas) para que una reimpresion lo advierta.
    """
    lineas = list(cierre.lineas.select_related('cierre').order_by('fecha_transaccion', 'origen', 'origen_id'))
    cambios = modificaciones_de_lineas(lineas)
    grupos = {}
    usd_no_llegaron = Decimal('0')
    for linea in lineas:
        grupo = grupos.setdefault(linea.metodo_pago_nombre, {
            'nombre': linea.metodo_pago_nombre,
            'moneda': linea.moneda,
            'es_efectivo': linea.es_efectivo,
            'total_usd': Decimal('0'),
            'total_bs': Decimal('0'),
            'lineas': [],
        })
        grupo['total_usd'] += linea.monto_usd
        if linea.monto_bs is not None:
            grupo['total_bs'] += linea.monto_bs
        if linea.estado == ESTADO_NO_LLEGO:
            usd_no_llegaron += linea.monto_usd
        grupo['lineas'].append({
            'fecha': timezone.localtime(linea.fecha_transaccion),
            'concepto': linea.concepto,
            'documento': linea.documento,
            'cliente': linea.cliente,
            'referencia': '' if linea.referencia.startswith('ABONO-') else linea.referencia,
            'moneda': linea.moneda,
            'monto_usd': linea.monto_usd,
            'monto_bs': linea.monto_bs,
            'llego': linea.estado == ESTADO_CONFIRMADA,
            'nota': linea.nota,
            'modificaciones': cambios.get(linea.id, []),
        })
    return {
        'codigo': cierre.codigo,
        'tipo': cierre.tipo,
        'tipo_label': cierre.get_tipo_display(),
        'titular_nombre': cierre.titular_nombre,
        'titular_rol': cierre.titular_rol,
        'cerrado_por_nombre': cierre.cerrado_por_nombre,
        'cerrado_por_rol': cierre.cerrado_por_rol,
        'fecha_cierre': timezone.localtime(cierre.fecha_cierre),
        'desde': timezone.localtime(cierre.desde) if cierre.desde else None,
        'hasta': timezone.localtime(cierre.hasta) if cierre.hasta else None,
        'novedad': cierre.novedad,
        'total_lineas': cierre.total_lineas,
        'total_confirmadas': cierre.total_confirmadas,
        'total_no_llegaron': cierre.total_no_llegaron,
        'usd_no_llegaron': usd_no_llegaron,
        'con_modificaciones': len(cambios),
        'grupos': list(grupos.values()),
    }


# ---------------------------------------------------------------------------
# Cierre
# ---------------------------------------------------------------------------
def determinar_tipo(titular, cerrador, mas_antigua, ahora, config):
    """El tipo lo decide el servidor: nunca viene del cliente."""
    if titular.pk != cerrador.pk:
        return TIPO_POR_TERCERO
    horas = (ahora - mas_antigua).total_seconds() / 3600
    return TIPO_TARDIO if horas > config.umbral_tardio_horas else TIPO_NORMAL


def detalle_pendientes(titular, cerrador, ahora=None):
    """
    Todo lo que la pantalla de cierre necesita de una vez: las lineas pendientes,
    los lotes POS que bloquean, y que tipo de cierre resultaria si se cerrara ahora.
    `corte` es el instante de la consulta: se manda de vuelta al cerrar para que
    lo que llegue despues no obligue a recargar.
    """
    ahora = ahora or timezone.now()
    config = VGConfiguracionCierreTurno.obtener_config()
    lineas = listar_pendientes(titular, config)
    tipo = None
    if lineas:
        tipo = determinar_tipo(titular, cerrador, min(linea['fecha_transaccion'] for linea in lineas), ahora, config)
    return {
        'activo': config.activo,
        'corte': ahora,
        'tipo': tipo,
        'umbral_tardio_horas': config.umbral_tardio_horas,
        'lineas': lineas,
        'lotes_pos_abiertos': list(lotes_pos_abiertos_con_cobros_de(titular)),
    }


def _normalizar_lineas(lineas):
    """[{'origen','id','estado','nota'}] -> {(origen, id): (estado, nota)}, rechazando lo mal formado o repetido."""
    pedidas = {}
    for item in lineas or []:
        try:
            origen = str(item.get('origen', '')).strip()
            origen_id = int(item.get('id'))
        except (AttributeError, TypeError, ValueError):
            raise CierreTurnoError('Hay una transacción mal formada en la lista a cerrar.')
        if origen not in ORIGENES:
            raise CierreTurnoError('Hay una transacción de un tipo desconocido en la lista a cerrar.')
        estado = str(item.get('estado', '')).strip()
        if estado not in ESTADOS_LINEA:
            raise CierreTurnoError('Cada transacción debe marcarse como "llegó" o "no llegó".')
        if (origen, origen_id) in pedidas:
            raise CierreTurnoError('Hay una transacción repetida en la lista a cerrar.')
        pedidas[(origen, origen_id)] = (estado, str(item.get('nota', '') or '').strip())
    return pedidas


def _etiqueta(linea_o_clave):
    origen, origen_id = linea_o_clave
    return f'{"propina/extra" if origen == ORIGEN_EXTRA else "cobro"} #{origen_id}'


def cerrar_turno(titular, cerrador, lineas, novedad='', corte=None, ahora=None):
    """
    Cierra el turno de `titular` con `lineas` (cada una confirmada o "no llego").
    `cerrador` es quien confirma: el propio titular u otra persona que pueda cobrar.

    Reglas (cada una rechaza con CierreTurnoError, sin dejar nada a medias):
      - cierre de turno activo y `cerrador` autorizado;
      - cada linea debe seguir pendiente y ser del titular (un doble clic o dos
        personas a la vez: el segundo ya no encuentra nada);
      - hay que incluir TODO lo pendiente anterior a `corte` (si no se manda,
        todo lo pendiente): no se puede dejar afuera la transaccion incomoda;
        lo registrado despues de `corte` queda pendiente para el siguiente cierre;
      - "no llego" exige nota;
      - ningun lote POS abierto con cobros del titular;
      - novedad obligatoria si el cierre no es 'normal' o hay "no llego".
    """
    if not usuario_puede_cobrar(cerrador):
        raise CierreTurnoError('No tienes permiso para cerrar turnos.')
    if titular is None:
        raise CierreTurnoError('Falta indicar de quién es el turno.')
    config = VGConfiguracionCierreTurno.obtener_config()
    if not config.activo:
        raise CierreTurnoError('El cierre de turno todavía no está activado.')

    ahora = ahora or timezone.now()
    novedad = (novedad or '').strip()
    pedidas = _normalizar_lineas(lineas)
    if not pedidas:
        raise CierreTurnoError('No hay transacciones para cerrar.')

    with transaction.atomic():
        pagos = {
            pago.id: pago
            for pago in _consulta_pagos(pagos_pendientes(titular, config)).select_for_update(of=('self',))
        }
        extras = {
            extra.id: extra
            for extra in extras_pendientes(titular, config).select_related('metodo_pago').select_for_update(of=('self',))
        }
        pendientes = {(ORIGEN_PAGO, pid): pago for pid, pago in pagos.items()}
        pendientes.update({(ORIGEN_EXTRA, eid): extra for eid, extra in extras.items()})

        ajenas = [clave for clave in pedidas if clave not in pendientes]
        if ajenas:
            raise CierreTurnoError(
                f'{len(ajenas)} transacción(es) ya no están pendientes o no son de {_nombre_usuario(titular)} '
                f'({", ".join(_etiqueta(clave) for clave in ajenas[:5])}). Recarga la lista.'
            )

        def momento(clave):
            transaccion = pendientes[clave]
            return transaccion.fecha_pago if clave[0] == ORIGEN_PAGO else transaccion.fecha_creacion

        obligatorias = [clave for clave in pendientes if corte is None or momento(clave) <= corte]
        faltan = [clave for clave in obligatorias if clave not in pedidas]
        if faltan:
            raise CierreTurnoError(
                f'Faltan {len(faltan)} transacción(es) por confirmar. Hay que revisar todas antes de cerrar el turno.'
            )

        for clave, (estado, nota) in pedidas.items():
            if estado == ESTADO_NO_LLEGO and not nota:
                raise CierreTurnoError(f'Explica en una nota por qué no llegó el {_etiqueta(clave)}.')

        lotes = list(lotes_pos_abiertos_con_cobros_de(titular))
        if lotes:
            numeros = ', '.join(f'#{lote.numero} ({lote.metodo_pago.nombre})' for lote in lotes)
            raise CierreTurnoError(f'Antes de cerrar el turno hay que cerrar el lote POS {numeros}.')

        datos = []
        for clave, (estado, nota) in pedidas.items():
            transaccion = pendientes[clave]
            dato = _linea_pago(transaccion) if clave[0] == ORIGEN_PAGO else _linea_extra(transaccion)
            dato['estado'] = estado
            dato['nota'] = nota
            datos.append(dato)
        datos.sort(key=lambda dato: (dato['fecha_transaccion'], dato['origen'], dato['origen_id']))

        desde = datos[0]['fecha_transaccion']
        hasta = datos[-1]['fecha_transaccion']
        tipo = determinar_tipo(titular, cerrador, desde, ahora, config)
        no_llegaron = sum(1 for dato in datos if dato['estado'] == ESTADO_NO_LLEGO)
        if (tipo != TIPO_NORMAL or no_llegaron) and not novedad:
            motivo = 'se cierra por otra persona' if tipo == TIPO_POR_TERCERO else (
                'el cierre es tardío' if tipo == TIPO_TARDIO else 'hay transacciones que no llegaron'
            )
            raise CierreTurnoError(f'La novedad es obligatoria: {motivo}.')

        cierre = VGCierreTurno.objects.create(
            numero=VGCorrelativoFiscal.siguiente(SERIE_CIERRE_TURNO),
            tipo=tipo,
            titular=titular,
            titular_nombre=_nombre_usuario(titular),
            titular_rol=_get_role_name(titular),
            cerrado_por=cerrador,
            cerrado_por_nombre=_nombre_usuario(cerrador),
            cerrado_por_rol=_get_role_name(cerrador),
            fecha_cierre=ahora,
            desde=desde,
            hasta=hasta,
            novedad=novedad,
            total_lineas=len(datos),
            total_confirmadas=len(datos) - no_llegaron,
            total_no_llegaron=no_llegaron,
            creado_por=cerrador,
            actualizado_por=cerrador,
        )
        VGCierreTurnoLinea.objects.bulk_create([VGCierreTurnoLinea(cierre=cierre, **dato) for dato in datos])
        VGPago.objects.filter(pk__in=[oid for (origen, oid) in pedidas if origen == ORIGEN_PAGO]).update(cierre_turno=cierre)
        VGIngresoExtra.objects.filter(pk__in=[oid for (origen, oid) in pedidas if origen == ORIGEN_EXTRA]).update(cierre_turno=cierre)
        return cierre
