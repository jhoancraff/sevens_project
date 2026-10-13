"""
PDF de lo que Cashea nos debe: los cobros con la cuenta Cashea que Cashea todavia no ha pagado
(ver cashea_views.cashea_pendientes_view), con las mismas columnas que la pantalla de Cashea.

La deuda esta fija en dolares; en bolivares cambia con la tasa, por eso cada orden trae la tasa en
que se registro, su monto en Bs a esa tasa, la tasa actual del sistema y cuanto deberia pagar
Cashea en Bs a la tasa actual. Al final va el total de cada columna de dinero.

Recibe las filas ya normalizadas por la vista (ver FILA_EJEMPLO) y no toca la base de datos.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, formatear_numero, generar_pdf_tabla

# Una orden, tal como la entrega la vista. Los montos pueden venir como Decimal o texto.
FILA_EJEMPLO = {
    'orden_cashea': '209485647',
    'fecha': '2026-10-12',      # ISO del dia del cobro
    'nota_codigo': '00000012',
    'cliente': 'Nombre del cliente o vacio',
    'monto_usd': '12.00',
    'tasa_registro': '876.7976',     # None si no hubo tasa
    'monto_bs_registro': '10521.57',  # None si no hubo tasa
    'tasa_actual': '900.0000',        # None si el sistema no tiene tasa
    'monto_bs_actual': '10800.00',    # None si el sistema no tiene tasa
}

COLUMNAS = [
    Columna('Orden Cashea', 0.115),
    Columna('Fecha', 0.08, 'centro'),
    Columna('Nota', 0.08, 'centro'),
    Columna('Cliente', 0.17),
    Columna('Monto ($)', 0.085, 'derecha'),
    Columna('Tasa de registro', 0.085, 'derecha'),
    Columna('Bs a esa tasa', 0.13, 'derecha'),
    Columna('Tasa actual', 0.075, 'derecha'),
    Columna('Debería pagar en Bs (tasa actual)', 0.18, 'derecha'),
]


def _decimal(valor):
    if valor in (None, ''):
        return None
    return Decimal(str(valor))


def _dia(iso):
    if not iso:
        return '—'
    anio, mes, dia = str(iso)[:10].split('-')
    return f'{dia}/{mes}/{anio}'


def _numero(valor, decimales=2):
    return formatear_numero(valor, decimales, decimales) if valor is not None else '—'


def _dos_decimales(valor):
    return valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if valor is not None else None


def armar_filas_cashea(filas):
    """
    Ordena por fecha y numero de orden y suma las columnas de dinero (con cada monto ya
    redondeado a 2 decimales, para que lo impreso cuadre). Devuelve (filas_texto, totales).
    """
    totales = {'usd': Decimal('0'), 'bs_registro': Decimal('0'), 'bs_actual': Decimal('0'), 'sin_tasa': 0}
    textos = []
    for fila in sorted(filas, key=lambda f: (str(f['fecha']), str(f['orden_cashea']))):
        usd = _dos_decimales(_decimal(fila['monto_usd'])) or Decimal('0')
        bs_registro = _dos_decimales(_decimal(fila.get('monto_bs_registro')))
        bs_actual = _dos_decimales(_decimal(fila.get('monto_bs_actual')))
        tasa_registro = _decimal(fila.get('tasa_registro'))
        tasa_actual = _decimal(fila.get('tasa_actual'))
        totales['usd'] += usd
        if bs_registro is not None:
            totales['bs_registro'] += bs_registro
        if bs_actual is not None:
            totales['bs_actual'] += bs_actual
        if bs_registro is None or bs_actual is None:
            totales['sin_tasa'] += 1
        textos.append([
            str(fila['orden_cashea']),
            _dia(fila['fecha']),
            str(fila.get('nota_codigo') or '—'),
            str(fila.get('cliente') or '—'),
            _numero(usd),
            _numero(tasa_registro, 4),
            _numero(bs_registro),
            _numero(tasa_actual, 4),
            _numero(bs_actual),
        ])
    return textos, totales


def generar_pdf_cashea_por_cobrar(filas, desde=None, hasta=None, tasa_actual=None, generado_en=None):
    textos, totales = armar_filas_cashea(filas)
    if desde and hasta:
        subtitulo = f'Cobros del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}'
    elif desde:
        subtitulo = f'Cobros desde el {desde:%d/%m/%Y}'
    elif hasta:
        subtitulo = f'Cobros hasta el {hasta:%d/%m/%Y}'
    else:
        subtitulo = 'Todos los cobros sin liquidar'

    cantidad = len(textos)
    izquierda = (
        f'<b>{cantidad}</b> {"orden" if cantidad == 1 else "órdenes"} por cobrar · '
        f'Deuda: <b>$ {formatear_numero(totales["usd"])}</b>'
    )
    if tasa_actual:
        derecha = (
            f'A la tasa actual (Bs {formatear_numero(tasa_actual, 2, 4)}): '
            f'<b>Bs {formatear_numero(totales["bs_actual"])}</b>'
        )
    else:
        derecha = 'No hay tasa actual disponible'

    return generar_pdf_tabla(
        titulo='Lo que nos debe Cashea',
        subtitulo=subtitulo,
        columnas=COLUMNAS,
        filas=textos,
        resumen=(izquierda, derecha),
        fila_total=[
            'Total', '', '', '',
            f'$ {formatear_numero(totales["usd"])}',
            '',
            f'Bs {formatear_numero(totales["bs_registro"])}',
            '',
            f'Bs {formatear_numero(totales["bs_actual"])}',
        ],
        orientacion='horizontal',
        generado_en=generado_en or datetime.now(),
        mensaje_vacio='Cashea no nos debe nada: no hay cobros sin liquidar en este rango.',
    )
