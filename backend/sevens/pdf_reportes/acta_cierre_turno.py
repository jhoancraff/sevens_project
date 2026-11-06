"""
Acta del cierre de turno de una cajera (o de quien cobre): quien cerro, de quien era el turno, cada
transaccion agrupada por cuenta con su estado ("llego" / "no llego") y su nota, la novedad y las
lineas de firma. Es el documento que se guarda para una auditoria (ver cierre_turno.py).

Recibe los datos ya armados por cierre_turno.datos_del_acta y no toca la
base de datos. Si algo cambio despues del cierre, la reimpresion lo advierte en la columna de
observaciones y en la franja del resumen.
"""
import os
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .base import (
    GRIS_FILA, GRIS_SUAVE, GRIS_TEXTO, MARGEN_LATERAL, NOMBRE_NEGOCIO, ROJO_MARCA, RUTA_LOGO, Columna, Seccion,
    _construir_tabla, _estilos, _fabrica_lienzo, formatear_numero,
)

COLUMNAS = [
    Columna('Fecha y hora', 0.12, 'centro'),
    Columna('Transacción', 0.30),
    Columna('Ref.', 0.11),
    Columna('Monto', 0.17, 'derecha'),
    Columna('Estado', 0.09, 'centro'),
    Columna('Observaciones', 0.21),
]


def _monto_principal(linea):
    """En la moneda de la cuenta: lo que se compara contra el banco (Bs en pago movil, $ en el resto)."""
    if linea['moneda'] == 'VES' and linea['monto_bs'] is not None:
        return f'Bs {formatear_numero(linea["monto_bs"])}'
    return f'$ {formatear_numero(linea["monto_usd"])}'


def _total_del_grupo(grupo):
    if grupo['moneda'] == 'VES' and grupo['total_bs']:
        return f'Bs {formatear_numero(grupo["total_bs"])}'
    return f'$ {formatear_numero(grupo["total_usd"])}'


def _observaciones(linea):
    partes = []
    if linea['nota']:
        partes.append(linea['nota'])
    for cambio in linea['modificaciones']:
        partes.append(f'MODIFICADO DESPUÉS DEL CIERRE: {cambio["detalle"]}')
    return ' · '.join(partes)


def _secciones(datos):
    secciones = []
    for grupo in datos['grupos']:
        filas = []
        for linea in grupo['lineas']:
            concepto = linea['concepto'] + (f' · {linea["cliente"]}' if linea['cliente'] else '')
            filas.append([
                linea['fecha'].strftime('%d/%m %H:%M'),
                concepto,
                linea['referencia'] or '—',
                _monto_principal(linea),
                'Llegó' if linea['llego'] else 'NO LLEGÓ',
                _observaciones(linea),
            ])
        cantidad = len(grupo['lineas'])
        secciones.append(Seccion(
            columnas=COLUMNAS,
            filas=filas,
            titulo=grupo['nombre'],
            detalle=f'{cantidad} transacción(es)',
            fila_total=['Total', '', '', _total_del_grupo(grupo), '', ''],
        ))
    return secciones


def generar_pdf_acta_cierre_turno(datos, generado_en=None):
    generado_en = generado_en or datetime.now()
    estilos = _estilos()
    estilo_texto = ParagraphStyle('texto', fontName='Helvetica', fontSize=10, leading=14, textColor=GRIS_TEXTO)
    estilo_alerta = ParagraphStyle('alerta', parent=estilo_texto, textColor=ROJO_MARCA, fontName='Helvetica-Bold')
    estilo_firma = ParagraphStyle('firma', fontName='Helvetica', fontSize=9, leading=12, textColor=GRIS_SUAVE, alignment=1)
    ancho_util = A4[0] - 2 * MARGEN_LATERAL
    titulo = f'Acta de cierre de turno {datos["codigo"]}'

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGEN_LATERAL, rightMargin=MARGEN_LATERAL, topMargin=14 * mm,
        bottomMargin=16 * mm, title=titulo, author=NOMBRE_NEGOCIO,
    )
    elementos = []

    texto_cabecera = [
        Paragraph(escape(titulo), estilos['titulo']),
        Paragraph(
            f'{escape(NOMBRE_NEGOCIO)} · {escape(datos["tipo_label"])} · Generado el {generado_en:%d/%m/%Y %H:%M}',
            estilos['subtitulo'],
        ),
    ]
    if os.path.exists(RUTA_LOGO):
        cabecera = Table([[Image(RUTA_LOGO, width=16 * mm, height=16 * mm), texto_cabecera]], colWidths=[20 * mm, None])
        cabecera.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elementos.append(cabecera)
    else:
        elementos.extend(texto_cabecera)
    elementos.append(Spacer(1, 5 * mm))

    def rol(nombre, cargo):
        return f'{nombre} ({cargo})' if cargo else nombre

    periodo = '—'
    if datos['desde'] and datos['hasta']:
        periodo = f'{datos["desde"]:%d/%m/%Y %H:%M} a {datos["hasta"]:%d/%m/%Y %H:%M}'
    etiqueta = estilos['subtitulo']
    filas_info = [
        [Paragraph('TURNO DE', etiqueta), Paragraph(escape(rol(datos['titular_nombre'], datos['titular_rol'])), estilo_texto)],
        [Paragraph('CERRADO POR', etiqueta), Paragraph(escape(rol(datos['cerrado_por_nombre'], datos['cerrado_por_rol'])), estilo_texto)],
        [Paragraph('FECHA DEL CIERRE', etiqueta), Paragraph(f'{datos["fecha_cierre"]:%d/%m/%Y %H:%M}', estilo_texto)],
        [Paragraph('TRANSACCIONES', etiqueta), Paragraph(escape(periodo), estilo_texto)],
        [Paragraph('RESULTADO', etiqueta), Paragraph(
            f'{datos["total_lineas"]} transacción(es): <b>{datos["total_confirmadas"]}</b> llegaron · '
            f'<b>{datos["total_no_llegaron"]}</b> no llegaron'
            + (f' (${formatear_numero(datos["usd_no_llegaron"])})' if datos['total_no_llegaron'] else ''),
            estilo_texto,
        )],
    ]
    info = Table(filas_info, colWidths=[ancho_util * 0.22, ancho_util * 0.78])
    info.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), GRIS_FILA), ('LINEBEFORE', (0, 0), (0, -1), 3, ROJO_MARCA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
    ]))
    elementos.append(info)
    if datos['con_modificaciones']:
        elementos.append(Spacer(1, 3 * mm))
        elementos.append(Paragraph(
            f'Atención: {datos["con_modificaciones"]} transacción(es) cambiaron después del cierre '
            '(ver la columna Observaciones). El acta conserva lo que se firmó.',
            estilo_alerta,
        ))
    elementos.append(Spacer(1, 5 * mm))

    for indice, seccion in enumerate(_secciones(datos)):
        if indice:
            elementos.append(Spacer(1, 5 * mm))
        elementos.append(CondPageBreak(35 * mm))
        texto = escape(seccion.titulo) + f'  <font name="Helvetica" size="9" color="#6f6464">{escape(seccion.detalle)}</font>'
        titulo_seccion = Paragraph(texto, estilos['seccion'])
        tabla = _construir_tabla(seccion, ancho_util, estilos)
        if len(seccion.filas) <= 20:
            elementos.append(KeepTogether([titulo_seccion, tabla]))
        else:
            elementos.extend([titulo_seccion, tabla])

    bloque_final = [Spacer(1, 6 * mm), Paragraph('Novedad', estilos['seccion'])]
    bloque_final.append(Paragraph(escape(datos['novedad']) if datos['novedad'] else 'Sin novedad.', estilo_texto))
    bloque_final.append(Spacer(1, 22 * mm))
    firmas = Table(
        [[
            Paragraph(f'Titular del turno<br/>{escape(datos["titular_nombre"])}', estilo_firma), '',
            Paragraph(f'Quien cierra<br/>{escape(datos["cerrado_por_nombre"])}', estilo_firma),
        ]],
        colWidths=[ancho_util * 0.4, ancho_util * 0.2, ancho_util * 0.4],
    )
    firmas.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 0.8, GRIS_TEXTO), ('LINEABOVE', (2, 0), (2, 0), 0.8, GRIS_TEXTO),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    bloque_final.append(firmas)
    elementos.append(KeepTogether(bloque_final))

    documento.build(elementos, canvasmaker=_fabrica_lienzo(f'{NOMBRE_NEGOCIO} · {titulo}'))
    return buffer.getvalue()
