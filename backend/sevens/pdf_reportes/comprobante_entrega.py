"""
Comprobante de entrega de un utensilio o dotación a un empleado (franelas, delantales...): una
hoja corta, con el articulo, la cantidad, quien recibe y las lineas de firma de quien entrega y de
quien recibe. Lo imprime la administradora al registrar la entrega (ver activos_views).

Recibe los datos ya armados por la vista (ver DATOS_EJEMPLO) y no toca la base de datos.
"""
import os
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .base import (
    GRIS_FILA, GRIS_LINEA, GRIS_SUAVE, GRIS_TEXTO, MARGEN_LATERAL, NOMBRE_NEGOCIO, ROJO_MARCA, RUTA_LOGO,
    _fabrica_lienzo,
)

DATOS_EJEMPLO = {
    'codigo': 'ENT-000001',
    'fecha': None,              # datetime de la entrega
    'receptor': 'Nombre de quien recibe',
    'articulo': 'Franela M',
    'categoria': 'Uniformes',
    'cantidad': 2,
    'motivo': 'Dotación inicial',
    'entregado_por': 'Nombre de quien entrega',
}


def generar_pdf_comprobante_entrega(datos, generado_en=None):
    generado_en = generado_en or datetime.now()
    fecha = datos.get('fecha') or generado_en

    estilo_titulo = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=GRIS_TEXTO)
    estilo_sub = ParagraphStyle('s', fontName='Helvetica', fontSize=9.5, leading=13, textColor=GRIS_SUAVE)
    estilo_etiqueta = ParagraphStyle('e', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=GRIS_SUAVE)
    estilo_valor = ParagraphStyle('v', fontName='Helvetica', fontSize=11, leading=14, textColor=GRIS_TEXTO)
    estilo_firma = ParagraphStyle('f', fontName='Helvetica', fontSize=9, leading=12, textColor=GRIS_SUAVE, alignment=1)

    ancho_util = A4[0] - 2 * MARGEN_LATERAL
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGEN_LATERAL, rightMargin=MARGEN_LATERAL, topMargin=14 * mm,
        bottomMargin=16 * mm, title=f'Comprobante de entrega {datos["codigo"]}', author=NOMBRE_NEGOCIO,
    )
    elementos = []

    texto_cab = [
        Paragraph('Comprobante de entrega', estilo_titulo),
        Paragraph(
            f'{escape(NOMBRE_NEGOCIO)} · Nº {escape(datos["codigo"])} · {fecha:%d/%m/%Y %H:%M}', estilo_sub,
        ),
    ]
    if os.path.exists(RUTA_LOGO):
        cab = Table([[Image(RUTA_LOGO, width=16 * mm, height=16 * mm), texto_cab]], colWidths=[20 * mm, None])
        cab.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elementos.append(cab)
    else:
        elementos.extend(texto_cab)
    elementos.append(Spacer(1, 8 * mm))

    def fila(etiqueta, valor):
        return [Paragraph(escape(etiqueta.upper()), estilo_etiqueta), Paragraph(escape(str(valor or '—')), estilo_valor)]

    filas = [
        fila('Recibe', datos['receptor']),
        fila('Artículo', datos['articulo']),
        fila('Categoría', datos.get('categoria')),
        fila('Cantidad', datos['cantidad']),
        fila('Motivo / nota', datos.get('motivo')),
        fila('Entregado por', datos.get('entregado_por')),
    ]
    tabla = Table(filas, colWidths=[ancho_util * 0.25, ancho_util * 0.75])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), GRIS_FILA),
        ('LINEBEFORE', (0, 0), (0, -1), 3, ROJO_MARCA),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, GRIS_LINEA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 6 * mm))
    elementos.append(Paragraph(
        'Declaro haber recibido el artículo indicado, en la cantidad señalada, para mi uso en el trabajo.',
        estilo_valor,
    ))
    elementos.append(Spacer(1, 26 * mm))

    firmas = Table(
        [[Paragraph('Entregó', estilo_firma), '', Paragraph('Recibí conforme', estilo_firma)]],
        colWidths=[ancho_util * 0.4, ancho_util * 0.2, ancho_util * 0.4],
    )
    firmas.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 0.8, GRIS_TEXTO), ('LINEABOVE', (2, 0), (2, 0), 0.8, GRIS_TEXTO),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(firmas)

    documento.build(elementos, canvasmaker=_fabrica_lienzo(f'{NOMBRE_NEGOCIO} · Comprobante {datos["codigo"]}'))
    return buffer.getvalue()
