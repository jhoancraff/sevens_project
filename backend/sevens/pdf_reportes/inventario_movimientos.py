"""
PDF de los movimientos del inventario (ingredientes y utensilios): primero el resumen por articulo
—existencia al inicio, entradas, salidas, bajas, ajustes, existencia al final y stock actual— y despues
el detalle de cada movimiento. Es el mismo contenido de la pantalla «Movimientos del inventario»
(ver inventario_movimientos_views).

Recibe filas ya armadas por la vista y no toca la base de datos. El detalle se limita a
MAX_FILAS_DETALLE (un rango largo de ventas de ingredientes puede traer miles de filas); el resumen
siempre sale completo y avisa cuando el detalle esta recortado.
"""
from datetime import datetime
from decimal import Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

MAX_FILAS_DETALLE = 1500

COLUMNAS_RESUMEN = [
    Columna('Artículo', 0.25),
    Columna('Tipo', 0.09, 'centro'),
    Columna('Inicial', 0.09, 'derecha'),
    Columna('Entradas', 0.09, 'derecha'),
    Columna('Salidas / entregas', 0.11, 'derecha'),
    Columna('Bajas', 0.08, 'derecha'),
    Columna('Ajustes', 0.09, 'derecha'),
    Columna('Final', 0.10, 'derecha'),
    Columna('Stock actual', 0.10, 'derecha'),
]

COLUMNAS_DETALLE = [
    Columna('Fecha', 0.10, 'centro'),
    Columna('Artículo', 0.20),
    Columna('Movimiento', 0.12),
    Columna('Cantidad', 0.09, 'derecha'),
    Columna('Motivo', 0.23),
    Columna('Recibió', 0.10),
    Columna('Registró', 0.09),
    Columna('Comprobante', 0.07, 'centro'),
]

ETIQUETAS_TIPO = {
    'entrada': 'Entrada', 'salida': 'Salida', 'entrega': 'Entrega a empleado', 'baja': 'Baja', 'ajuste': 'Ajuste',
}
ETIQUETA_ORIGEN = {'ingrediente': 'Ingrediente', 'utensilio': 'Utensilio'}


def _cantidad(valor):
    return formatear_numero(Decimal(valor or 0), 0, 2)


def _con_signo(valor):
    valor = Decimal(valor or 0)
    return f'+{_cantidad(valor)}' if valor > 0 else _cantidad(valor)


def generar_pdf_inventario_movimientos(resumen, detalle, total_detalle, desde, hasta, filtros='', generado_en=None):
    """
    resumen: dicts de inventario_movimientos_views.resumen_por_articulo.
    detalle: dicts de detalle_movimientos (ya ordenados); total_detalle: cuantos hay en total.
    """
    filas_resumen = [
        [
            fila['nombre'], ETIQUETA_ORIGEN.get(fila['origen'], fila['origen']),
            _cantidad(fila['inicial']), _cantidad(fila['entradas']), _cantidad(fila['salidas']),
            _cantidad(fila['bajas']), _con_signo(fila['ajustes']) if fila['ajustes'] else '0',
            _cantidad(fila['final']), _cantidad(fila['actual']),
        ]
        for fila in resumen
    ]

    recortado = total_detalle > MAX_FILAS_DETALLE
    detalle = detalle[:MAX_FILAS_DETALLE]
    filas_detalle = [
        [
            f"{fila['fecha']:%d/%m/%Y %H:%M}", fila['articulo'], ETIQUETAS_TIPO.get(fila['tipo'], fila['tipo']),
            _con_signo(fila['delta']), fila['motivo'] or '—', fila['receptor'] or '—',
            fila['registrado_por'] or '—', fila['comprobante'] or '—',
        ]
        for fila in detalle
    ]

    secciones = [
        Seccion(
            titulo='Resumen por artículo',
            detalle=f'{len(filas_resumen)} artículo{"s" if len(filas_resumen) != 1 else ""} con movimientos',
            columnas=COLUMNAS_RESUMEN,
            filas=filas_resumen,
            mensaje_vacio='No hubo movimientos en este rango.',
        ),
        Seccion(
            titulo='Detalle de movimientos',
            detalle=(
                f'se muestran los {MAX_FILAS_DETALLE} más recientes de {total_detalle}: acota el rango para ver el resto'
                if recortado else f'{total_detalle} movimiento{"s" if total_detalle != 1 else ""}'
            ),
            columnas=COLUMNAS_DETALLE,
            filas=filas_detalle,
            mensaje_vacio='No hubo movimientos en este rango.',
        ),
    ]
    partes = [f'Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}']
    if filtros:
        partes.append(filtros)
    return generar_pdf_reporte(
        titulo='Movimientos del inventario',
        subtitulo=' · '.join(partes),
        secciones=secciones,
        resumen=(
            'Existencia al inicio + entradas − salidas − bajas ± ajustes = existencia al final.',
            'La existencia se calcula hacia atrás desde el stock actual.',
        ),
        orientacion='horizontal',
        generado_en=generado_en or datetime.now(),
    )
