"""Abrir una subreceta bloqueada con su código (ver subrecetas_bloqueadas.py)."""
import json
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api_views import _auth_response, _is_admin_user, _load_preparation_cost_map
from .models import VGAccesoSubreceta, VGPreparacion
from .subrecetas_bloqueadas import MAX_INTENTOS_FALLIDOS, MINUTOS_DE_BLOQUEO


def _sin_guardar(respuesta):
    # La receta secreta no debe quedarse en la caché del navegador ni de un intermediario.
    respuesta['Cache-Control'] = 'no-store'
    return respuesta


def _composicion(preparacion):
    componentes = []
    for componente in preparacion.componentes.select_related('ingrediente', 'sub_preparacion').order_by('id'):
        if componente.ingrediente_id:
            nombre, unidad = componente.ingrediente.nombre, componente.ingrediente.unidad_medida
        else:
            nombre, unidad = componente.sub_preparacion.nombre, componente.sub_preparacion.rendimiento_unidad
        componentes.append({
            'nombre': nombre, 'unidad': unidad, 'cantidad': str(componente.cantidad_requerida),
            'tipo': 'ingrediente' if componente.ingrediente_id else 'sub_preparacion',
            # Una subreceta bloqueada dentro de otra: se ve su nombre, pero su contenido pide su propio código.
            'bloqueada': bool(componente.sub_preparacion_id and componente.sub_preparacion.bloqueada),
        })
    costos = _load_preparation_cost_map().get(preparacion.id, {'costo_total': Decimal('0'), 'costo_unitario': Decimal('0')})
    return {
        'id': preparacion.id,
        'nombre': preparacion.nombre,
        'rendimiento_cantidad': str(preparacion.rendimiento_cantidad),
        'rendimiento_unidad': preparacion.rendimiento_unidad,
        'componentes': componentes,
        'costo_total': str(costos['costo_total'].quantize(Decimal('0.01'))),
        'costo_unitario': str(costos['costo_unitario'].quantize(Decimal('0.000001'))),
    }


@csrf_exempt
def desbloquear_subreceta_view(request):
    """POST {id, codigo}: devuelve la receta si el código es correcto. No deja nada abierto: cada vez se pide."""
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        preparacion = VGPreparacion.objects.get(pk=int(data.get('id')), bloqueada=True)
    except (ValueError, TypeError, UnicodeDecodeError, AttributeError, VGPreparacion.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Esa subreceta bloqueada no existe.'}, status=404)

    desde = timezone.now() - timedelta(minutes=MINUTOS_DE_BLOQUEO)
    recientes = VGAccesoSubreceta.objects.filter(usuario=request.user, preparacion=preparacion, fecha__gte=desde)
    # Solo cuentan los fallos posteriores a la ultima vez que acerto.
    ultimo_acierto = recientes.filter(exitoso=True).order_by('-fecha').values_list('fecha', flat=True).first()
    fallos = recientes.filter(exitoso=False)
    if ultimo_acierto:
        fallos = fallos.filter(fecha__gt=ultimo_acierto)
    if fallos.count() >= MAX_INTENTOS_FALLIDOS:
        return _auth_response({
            'ok': False,
            'message': f'Demasiados códigos errados. Espera {MINUTOS_DE_BLOQUEO} minutos para volver a intentar.',
        }, status=429)

    correcto = preparacion.codigo_correcto(str(data.get('codigo') or ''))
    VGAccesoSubreceta.objects.create(
        preparacion=preparacion, usuario=request.user, exitoso=correcto, ip=request.META.get('REMOTE_ADDR') or None,
    )
    if not correcto:
        quedan = max(MAX_INTENTOS_FALLIDOS - fallos.count(), 0)
        return _auth_response({
            'ok': False,
            'message': 'Código incorrecto.' + (f' Quedan {quedan} intento(s).' if quedan else ' Se bloqueó el acceso por unos minutos.'),
        }, status=403)
    return _sin_guardar(_auth_response({'ok': True, 'subreceta': _composicion(preparacion)}))
