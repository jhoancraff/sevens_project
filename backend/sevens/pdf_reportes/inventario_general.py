"""
PDF del inventario general: ingredientes y/o utensilios y equipos, segun el filtro de la pantalla
«Todo el inventario» (ver activos_views.filas_inventario_general).

Cada tipo va en su propio bloque con su subtotal: el valor de los ingredientes (costo de receta) y
el de los utensilios (valor de compra, informativo) NO se mezclan en un solo «total del
inventario». Cuando salen los dos, el resumen los muestra por separado y da el patrimonio total
aparte, con ese nombre.

Recibe las filas ya calculadas por la vista y no toca la base de datos.
"""
from datetime import datetime
from decimal import Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

COLUMNAS_INGREDIENTES = [
    Columna('Ingrediente', 0.36),
    Columna('Categoría', 0.24),
    Columna('Unidad', 0.12, 'centro'),
    Columna('Stock', 0.13, 'derecha'),
    Columna('Valor ($)', 0.15, 'derecha'),
]

COLUMNAS_UTENSILIOS = [
    Columna('Utensilio / equipo', 0.25),
    Columna('Categoría', 0.15),
    Columna('Ubicación', 0.13),
    Columna('Estado', 0.10, 'centro'),
    Columna('Cantidad', 0.08, 'derecha'),
    Columna('Valor unit. ($)', 0.14, 'derecha'),
    Columna('Valor total ($)', 0.15, 'derecha'),
]

UNIDADES = {'g': 'Gramos', 'ml': 'Mililitros', 'unidad': 'Unidad'}


def _dinero(valor):
    return f'$ {formatear_numero(valor)}'


def _filas_ingredientes(ingredientes):
    return [
        [
            fila['nombre'], fila['categoria'] or '—', UNIDADES.get(fila['unidad'], fila['unidad']),
            formatear_numero(fila['cantidad'], 0, 2), formatear_numero(fila['valor_total']),
        ]
        for fila in ingredientes
    ]


def _filas_utensilios(utensilios):
    return [
        [
            fila['nombre'], fila['categoria'] or '—', fila.get('ubicacion') or '—', fila.get('estado') or '—',
            str(fila['cantidad']),
            formatear_numero(fila['valor_unitario']) if fila.get('valor_unitario') is not None else '—',
            formatear_numero(fila['valor_total']),
        ]
        for fila in utensilios
    ]


def generar_pdf_inventario_general(ingredientes, utensilios, tipo='todo', subtitulo=None, generado_en=None):
    """
    ingredientes / utensilios: listas de dicts (ver activos_views.filas_inventario_general).
    tipo: 'todo' | 'ingredientes' | 'utensilios' (que bloques se imprimen).
    """
    total_ing = sum((fila['valor_total'] for fila in ingredientes), Decimal('0'))
    total_art = sum((fila['valor_total'] for fila in utensilios), Decimal('0'))
    ver_ing = tipo in ('todo', 'ingredientes')
    ver_art = tipo in ('todo', 'utensilios')

    secciones = []
    if ver_ing:
        secciones.append(Seccion(
            titulo='Ingredientes',
            detalle=f'{len(ingredientes)} ingrediente{"s" if len(ingredientes) != 1 else ""}',
            columnas=COLUMNAS_INGREDIENTES,
            filas=_filas_ingredientes(ingredientes),
            fila_total=['Subtotal ingredientes', '', '', '', _dinero(total_ing)],
            mensaje_vacio='No hay ingredientes con ese filtro.',
        ))
    if ver_art:
        unidades = sum(fila['cantidad'] for fila in utensilios)
        secciones.append(Seccion(
            titulo='Utensilios y equipos',
            detalle=f'{len(utensilios)} artículo{"s" if len(utensilios) != 1 else ""} · {unidades} unidades',
            columnas=COLUMNAS_UTENSILIOS,
            filas=_filas_utensilios(utensilios),
            fila_total=['Subtotal utensilios (valor de compra)', '', '', '', '', '', _dinero(total_art)],
            mensaje_vacio='No hay utensilios con ese filtro.',
        ))

    if ver_ing and ver_art:
        resumen = (
            f'Ingredientes: <b>{_dinero(total_ing)}</b> · Utensilios: <b>{_dinero(total_art)}</b>',
            f'Patrimonio total: <b>{_dinero(total_ing + total_art)}</b>',
        )
        titulo = 'Inventario general'
    elif ver_ing:
        resumen = (f'<b>{len(ingredientes)}</b> ingredientes', f'Valor de los ingredientes: <b>{_dinero(total_ing)}</b>')
        titulo = 'Inventario de ingredientes'
    else:
        resumen = (
            f'<b>{len(utensilios)}</b> artículos',
            f'Valor de compra de los utensilios: <b>{_dinero(total_art)}</b>',
        )
        titulo = 'Utensilios y equipos'

    return generar_pdf_reporte(
        titulo=titulo,
        subtitulo=subtitulo,
        secciones=secciones,
        resumen=resumen,
        orientacion='horizontal' if ver_art else 'vertical',
        generado_en=generado_en or datetime.now(),
    )
