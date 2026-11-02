"""
Categorias de productos del menu (Platos, Bebidas, Pizzas...): crear, renombrar, desactivar y eliminar.

Una categoria DESACTIVADA deja de ofrecerse a los meseros al tomar un pedido (la lista de
productos trae `categoria_activa` y la pantalla de pedido la oculta, ver ProductoSerializer);
sus productos siguen existiendo y se pueden volver a mostrar activandola. Eliminar solo se
permite si no tiene productos.

La impresora de cada categoria sigue configurandose en Impresoras (admin_categorias_view).
"""
import json

from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user
from .models import VGCategoriaProducto

LARGO_MAXIMO_NOMBRE = 100
LARGO_MAXIMO_DESCRIPCION = 255

# «Recetas» es de uso interno (no se lista). Las otras dos las busca el sistema por su nombre
# («Otros» se crea sola al abrir Productos; «Guarniciones» no se ofrece sueltas en el menu, solo como
# acompanante), asi que no se pueden renombrar ni eliminar.
CATEGORIA_INTERNA = 'recetas'
CATEGORIAS_PROTEGIDAS = ('otros', 'guarniciones')


def _es_protegida(categoria):
    return categoria.nombre.strip().lower() in CATEGORIAS_PROTEGIDAS


def _serialize_categoria(categoria):
    return {
        'id': categoria.id,
        'nombre': categoria.nombre,
        'descripcion': categoria.descripcion,
        'activa': categoria.activa,
        'productos': categoria.total_productos,
        'productos_disponibles': categoria.total_disponibles,
        'protegida': _es_protegida(categoria),
    }


def _listado():
    categorias = (
        VGCategoriaProducto.objects.exclude(nombre__iexact=CATEGORIA_INTERNA)
        .annotate(total_productos=Count('productos'), total_disponibles=Count('productos', filter=Q(productos__disponible=True)))
        .order_by('nombre')
    )
    return [_serialize_categoria(categoria) for categoria in categorias]


def _nombre_valido(data, excluir_id=None):
    """Devuelve (nombre, mensaje_de_error)."""
    nombre = ' '.join(str(data.get('nombre', '') or '').split())
    if not nombre:
        return None, 'El nombre de la categoría es obligatorio.'
    if len(nombre) > LARGO_MAXIMO_NOMBRE:
        return None, f'El nombre no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres.'
    if nombre.lower() == CATEGORIA_INTERNA:
        return None, 'Ese nombre lo usa el sistema; elige otro.'
    repetida = VGCategoriaProducto.objects.filter(nombre__iexact=nombre)
    if excluir_id is not None:
        repetida = repetida.exclude(pk=excluir_id)
    if repetida.exists():
        return None, 'Ya existe una categoría con ese nombre.'
    return nombre, None


def _descripcion_valida(data):
    descripcion = ' '.join(str(data.get('descripcion', '') or '').split())
    if len(descripcion) > LARGO_MAXIMO_DESCRIPCION:
        return None, f'La descripción no puede pasar de {LARGO_MAXIMO_DESCRIPCION} caracteres.'
    return descripcion, None


@csrf_exempt
def admin_categorias_productos_view(request):
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        return _auth_response({'ok': True, 'categorias': _listado()})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'create':
        nombre, error = _nombre_valido(data)
        if error:
            return _auth_response({'ok': False, 'message': error}, status=400)
        descripcion, error = _descripcion_valida(data)
        if error:
            return _auth_response({'ok': False, 'message': error}, status=400)
        categoria = VGCategoriaProducto.objects.create(
            nombre=nombre, descripcion=descripcion, creado_por=request.user, actualizado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': f'Categoría «{categoria.nombre}» creada.',
            'categorias': _listado(),
        }, status=201)

    try:
        categoria = VGCategoriaProducto.objects.exclude(nombre__iexact=CATEGORIA_INTERNA).get(pk=int(data.get('id')))
    except (TypeError, ValueError, VGCategoriaProducto.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'La categoría no existe.'}, status=400)

    if action == 'update':
        campos = ['actualizado_por', 'fecha_actualizacion']
        if 'nombre' in data:
            nombre, error = _nombre_valido(data, excluir_id=categoria.pk)
            if error:
                return _auth_response({'ok': False, 'message': error}, status=400)
            if nombre != categoria.nombre:
                if _es_protegida(categoria):
                    return _auth_response({
                        'ok': False,
                        'message': f'«{categoria.nombre}» la usa el sistema por su nombre y no se puede renombrar.',
                    }, status=400)
                categoria.nombre = nombre
                campos.append('nombre')
        if 'descripcion' in data:
            descripcion, error = _descripcion_valida(data)
            if error:
                return _auth_response({'ok': False, 'message': error}, status=400)
            categoria.descripcion = descripcion
            campos.append('descripcion')
        if 'activa' in data:
            categoria.activa = bool(data.get('activa'))
            campos.append('activa')
        categoria.actualizado_por = request.user
        categoria.save(update_fields=campos)
        if 'activa' in data:
            accion = 'activada' if categoria.activa else 'desactivada: los meseros ya no la ven'
            mensaje = f'Categoría «{categoria.nombre}» {accion}.'
        else:
            mensaje = f'Categoría «{categoria.nombre}» actualizada.'
        return _auth_response({'ok': True, 'message': mensaje, 'categorias': _listado()})

    if action == 'delete':
        if _es_protegida(categoria):
            return _auth_response({
                'ok': False,
                'message': f'«{categoria.nombre}» la usa el sistema por su nombre y no se puede eliminar. Puedes desactivarla.',
            }, status=400)
        cantidad = categoria.productos.count()
        if cantidad:
            return _auth_response({
                'ok': False,
                'message': (
                    f'«{categoria.nombre}» tiene {cantidad} producto(s). Muévelos a otra categoría para eliminarla, '
                    'o desactívala para que los meseros no la vean.'
                ),
            }, status=400)
        nombre = categoria.nombre
        try:
            categoria.delete()
        except ProtectedError:
            return _auth_response({
                'ok': False,
                'message': f'«{nombre}» está en uso (por ejemplo como opciones de un plato) y no se puede eliminar. Puedes desactivarla.',
            }, status=400)
        return _auth_response({'ok': True, 'message': f'Categoría «{nombre}» eliminada.', 'categorias': _listado()})

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)
