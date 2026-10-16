"""
Movimientos del inventario: todo lo que entro, salio o se ajusto, de ingredientes y de utensilios y
equipos, en un rango de fechas — para responder «por que tengo este stock».

  - Ingredientes: VGMovimientoInventario (compras y cargas = entrada; ventas y reposiciones = salida;
    ajustes de inventario = ajuste con signo).
  - Utensilios: VGMovimientoActivo (entrada, entrega a empleado, baja, ajuste de conteo).

Dos bloques: un RESUMEN por articulo (existencia al inicio del rango + entradas - salidas -/+ ajustes =
existencia al final, y el stock actual) y el DETALLE de cada movimiento. Las existencias se calculan
hacia atras desde el stock actual del articulo (stock actual menos los movimientos posteriores), asi
siempre cuadran con lo que muestra el inventario hoy; un cambio de stock hecho a mano sin movimiento
(por ejemplo editando el ingrediente) no aparece, porque no dejo rastro.

Solo administradores. La misma consulta alimenta la pantalla (paginada) y el PDF
(reportes_pdf_views.reporte_inventario_movimientos_pdf_view).
"""
from datetime import date
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, When
from django.utils import timezone

from .api_views import HIDDEN_INGREDIENT_IDS
from .auth_helpers import _auth_response, _is_admin_user
from .models import VGActivo, VGIngrediente, VGMovimientoActivo, VGMovimientoInventario

TAMANO_PAGINA = 100
ORIGENES = ('todo', 'utensilios', 'ingredientes')
TIPOS = ('entrada', 'salida', 'entrega', 'baja', 'ajuste')
CERO = Decimal('0')
ETIQUETAS_TIPO = {
    'entrada': 'Entrada', 'salida': 'Salida', 'entrega': 'Entrega a empleado', 'baja': 'Baja', 'ajuste': 'Ajuste',
}


class ParametrosInvalidos(Exception):
    pass


def leer_parametros(params):
    """Devuelve un dict ya validado; lanza ParametrosInvalidos con un mensaje para el usuario."""
    hoy = timezone.localdate()
    try:
        desde = date.fromisoformat(params['desde']) if params.get('desde') else hoy.replace(day=1)
        hasta = date.fromisoformat(params['hasta']) if params.get('hasta') else hoy
    except ValueError:
        raise ParametrosInvalidos('Las fechas no son validas.')
    if desde > hasta:
        raise ParametrosInvalidos('"Desde" no puede ser posterior a "Hasta".')
    origen = (params.get('origen') or 'todo').strip().lower()
    if origen not in ORIGENES:
        raise ParametrosInvalidos('El origen debe ser todo, utensilios o ingredientes.')
    tipo = (params.get('tipo') or '').strip().lower()
    if tipo and tipo not in TIPOS:
        raise ParametrosInvalidos('El tipo de movimiento no es valido.')
    try:
        pagina = max(1, int(params.get('pagina') or 1))
    except ValueError:
        pagina = 1
    return {
        'desde': desde, 'hasta': hasta, 'origen': origen, 'tipo': tipo,
        'q': ' '.join((params.get('q') or '').split()),
        'receptor': ' '.join((params.get('receptor') or '').split()),
        'pagina': pagina,
    }


def _numero(valor):
    """Decimal sin ceros sobrantes: 3.00 -> '3', 1250.50 -> '1250.5' (los utensilios son enteros)."""
    valor = Decimal(valor or 0)
    texto = f'{valor:f}'
    if '.' in texto:
        texto = texto.rstrip('0').rstrip('.')
    return texto or '0'


def _movimientos_ingredientes(p):
    consulta = VGMovimientoInventario.objects.exclude(ingrediente_id__in=HIDDEN_INGREDIENT_IDS)
    for palabra in p['q'].split():
        consulta = consulta.filter(ingrediente__nombre__icontains=palabra)
    return consulta


def _movimientos_activos(p):
    consulta = VGMovimientoActivo.objects.all()
    for palabra in p['q'].split():
        consulta = consulta.filter(activo_ref__nombre__icontains=palabra)
    if p['receptor']:
        consulta = consulta.filter(receptor__icontains=p['receptor'])
    return consulta


def _en_rango(campo, p):
    return Q(**{f'{campo}__date__gte': p['desde'], f'{campo}__date__lte': p['hasta']})


def _incluye_ingredientes(p):
    # Un filtro de receptor o un tipo exclusivo de utensilios deja fuera a los ingredientes.
    return p['origen'] in ('todo', 'ingredientes') and not p['receptor'] and p['tipo'] not in ('entrega', 'baja')


def _incluye_utensilios(p):
    return p['origen'] in ('todo', 'utensilios') and p['tipo'] != 'salida'


def _firmado_ingrediente():
    return Case(
        When(tipo_movimiento='salida', then=-F('cantidad')),
        default=F('cantidad'),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _filtro_tipo_ingrediente(p):
    return Q(tipo_movimiento=p['tipo']) if p['tipo'] else Q()


def _filtro_tipo_activo(p):
    return Q(tipo=p['tipo']) if p['tipo'] else Q()


def resumen_por_articulo(p):
    """Una fila por articulo con movimientos (que cumplan los filtros) en el rango."""
    filas = []

    if _incluye_ingredientes(p):
        base = _movimientos_ingredientes(p)
        ids = set(
            base.filter(_en_rango('fecha_movimiento', p)).filter(_filtro_tipo_ingrediente(p))
            .values_list('ingrediente_id', flat=True)
        )
        rango = _en_rango('fecha_movimiento', p)
        firmado = _firmado_ingrediente()
        agregados = {
            fila['ingrediente_id']: fila
            for fila in base.filter(ingrediente_id__in=ids).values('ingrediente_id').annotate(
                entradas=Sum('cantidad', filter=rango & Q(tipo_movimiento='entrada')),
                salidas=Sum('cantidad', filter=rango & Q(tipo_movimiento='salida')),
                ajustes=Sum('cantidad', filter=rango & Q(tipo_movimiento='ajuste')),
                neto=Sum(firmado, filter=rango),
                posterior=Sum(firmado, filter=Q(fecha_movimiento__date__gt=p['hasta'])),
                cantidad=Count('id', filter=rango),
            )
        }
        for ing in VGIngrediente.objects.filter(pk__in=ids).select_related('categoria'):
            ag = agregados[ing.id]
            actual = Decimal(ing.stock_actual or 0)
            final = actual - (ag['posterior'] or CERO)
            inicial = final - (ag['neto'] or CERO)
            filas.append({
                'origen': 'ingrediente', 'id': ing.id, 'nombre': ing.nombre,
                'categoria': ing.categoria.nombre if ing.categoria_id else '', 'unidad': ing.unidad_medida,
                'inicial': inicial, 'entradas': ag['entradas'] or CERO, 'salidas': ag['salidas'] or CERO,
                'bajas': CERO, 'ajustes': ag['ajustes'] or CERO, 'final': final, 'actual': actual,
                'movimientos': ag['cantidad'],
            })

    if _incluye_utensilios(p):
        base = _movimientos_activos(p)
        ids = set(
            base.filter(_en_rango('fecha_creacion', p)).filter(_filtro_tipo_activo(p))
            .values_list('activo_ref_id', flat=True)
        )
        rango = _en_rango('fecha_creacion', p)
        agregados = {
            fila['activo_ref_id']: fila
            for fila in base.filter(activo_ref_id__in=ids).values('activo_ref_id').annotate(
                entradas=Sum('delta', filter=rango & Q(tipo='entrada')),
                entregas=Sum('delta', filter=rango & Q(tipo='entrega')),
                bajas=Sum('delta', filter=rango & Q(tipo='baja')),
                ajustes=Sum('delta', filter=rango & Q(tipo='ajuste')),
                neto=Sum('delta', filter=rango),
                posterior=Sum('delta', filter=Q(fecha_creacion__date__gt=p['hasta'])),
                cantidad=Count('id', filter=rango),
            )
        }
        for art in VGActivo.objects.filter(pk__in=ids).select_related('categoria'):
            ag = agregados[art.id]
            actual = Decimal(art.cantidad)
            final = actual - Decimal(ag['posterior'] or 0)
            inicial = final - Decimal(ag['neto'] or 0)
            filas.append({
                'origen': 'utensilio', 'id': art.id, 'nombre': art.nombre,
                'categoria': art.categoria.nombre if art.categoria_id else '', 'unidad': 'unidad',
                'inicial': inicial, 'entradas': Decimal(ag['entradas'] or 0),
                'salidas': -Decimal(ag['entregas'] or 0), 'bajas': -Decimal(ag['bajas'] or 0),
                'ajustes': Decimal(ag['ajustes'] or 0), 'final': final, 'actual': actual,
                'movimientos': ag['cantidad'],
            })

    filas.sort(key=lambda f: (f['origen'], f['nombre'].lower()))
    return filas


def detalle_movimientos(p, limite=None, desplazamiento=0):
    """
    Movimientos del rango, del mas nuevo al mas viejo (ingredientes y utensilios mezclados por fecha).
    Devuelve (filas, total). `limite` None = todos.
    """
    filas = []
    total = 0
    tope = None if limite is None else desplazamiento + limite

    if _incluye_ingredientes(p):
        consulta = (
            _movimientos_ingredientes(p).filter(_en_rango('fecha_movimiento', p)).filter(_filtro_tipo_ingrediente(p))
            .select_related('ingrediente', 'creado_por').order_by('-fecha_movimiento', '-id')
        )
        total += consulta.count()
        for mov in (consulta if tope is None else consulta[:tope]):
            cantidad = Decimal(mov.cantidad or 0)
            delta = -abs(cantidad) if mov.tipo_movimiento == 'salida' else cantidad
            filas.append({
                'origen': 'ingrediente', 'movimiento_id': mov.id, 'fecha': mov.fecha_movimiento,
                'articulo': mov.ingrediente.nombre, 'unidad': mov.ingrediente.unidad_medida,
                'tipo': mov.tipo_movimiento, 'delta': delta, 'motivo': mov.motivo, 'receptor': '', 'comprobante': '',
                'registrado_por': (mov.creado_por.get_full_name() or mov.creado_por.username) if mov.creado_por else '',
            })

    if _incluye_utensilios(p):
        consulta = (
            _movimientos_activos(p).filter(_en_rango('fecha_creacion', p)).filter(_filtro_tipo_activo(p))
            .select_related('activo_ref', 'creado_por').order_by('-fecha_creacion', '-id')
        )
        total += consulta.count()
        for mov in (consulta if tope is None else consulta[:tope]):
            filas.append({
                'origen': 'utensilio', 'movimiento_id': mov.id, 'fecha': mov.fecha_creacion,
                'articulo': mov.activo_ref.nombre, 'unidad': 'unidad',
                'tipo': mov.tipo, 'delta': Decimal(mov.delta), 'motivo': mov.motivo, 'receptor': mov.receptor,
                'comprobante': mov.codigo_comprobante,
                'registrado_por': (mov.creado_por.get_full_name() or mov.creado_por.username) if mov.creado_por else '',
            })

    filas.sort(key=lambda f: f['fecha'], reverse=True)
    if limite is not None:
        filas = filas[desplazamiento:desplazamiento + limite]
    return filas, total


def totales_generales(resumen):
    """Suma de las columnas de movimiento, por origen (no se mezclan gramos con unidades)."""
    totales = {}
    for fila in resumen:
        t = totales.setdefault(fila['origen'], {'articulos': 0, 'movimientos': 0})
        t['articulos'] += 1
        t['movimientos'] += fila['movimientos']
    return totales


def serializar_resumen(fila):
    return {
        **{k: fila[k] for k in ('origen', 'id', 'nombre', 'categoria', 'unidad', 'movimientos')},
        **{k: _numero(fila[k]) for k in ('inicial', 'entradas', 'salidas', 'bajas', 'ajustes', 'final', 'actual')},
    }


def serializar_detalle(fila):
    fecha = timezone.localtime(fila['fecha'])
    return {
        'origen': fila['origen'], 'movimiento_id': fila['movimiento_id'], 'fecha': fecha.isoformat(),
        'articulo': fila['articulo'], 'unidad': fila['unidad'], 'tipo': fila['tipo'],
        'tipo_label': ETIQUETAS_TIPO.get(fila['tipo'], fila['tipo']), 'delta': _numero(fila['delta']),
        'motivo': fila['motivo'], 'receptor': fila['receptor'], 'comprobante': fila['comprobante'],
        'registrado_por': fila['registrado_por'],
    }


def admin_inventario_movimientos_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    try:
        p = leer_parametros(request.GET)
    except ParametrosInvalidos as error:
        return _auth_response({'ok': False, 'message': str(error)}, status=400)

    resumen = resumen_por_articulo(p)
    filas, total = detalle_movimientos(p, limite=TAMANO_PAGINA, desplazamiento=(p['pagina'] - 1) * TAMANO_PAGINA)
    return _auth_response({
        'ok': True,
        'desde': p['desde'].isoformat(),
        'hasta': p['hasta'].isoformat(),
        'resumen': [serializar_resumen(f) for f in resumen],
        'totales': totales_generales(resumen),
        'movimientos': [serializar_detalle(f) for f in filas],
        'total_movimientos': total,
        'pagina': p['pagina'],
        'paginas': max(1, -(-total // TAMANO_PAGINA)),
        'tamano_pagina': TAMANO_PAGINA,
    })
