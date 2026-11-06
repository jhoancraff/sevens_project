"""
API del cierre de turno (ver cierre_turno.py para las reglas).

  GET  cierre-turno/estado/        -> aviso y badge: mis pendientes + quien mas tiene sin cerrar
  GET  cierre-turno/pendientes/    -> lo que hay que revisar para cerrar (propio o de otra persona)
  POST cierre-turno/cerrar/        -> cierra el turno (e imprime el acta; un fallo de impresora no lo deshace)
  POST cierre-turno/imprimir/      -> reimprime el acta en la impresora de caja
  GET  cierre-turno/acta-pdf/      -> acta A4 en PDF (?cierre_id=)
  GET  cierre-turno/cierres/       -> historial de cierres (con ?cierre_id= el detalle con lineas)
  GET/POST admin/cierre-turno/config/ -> activacion y umbral (administrador/contador/dueño)

Los tres roles que cobran (cajera, administrador, contador; el dueño entra por
_is_admin_user) usan los mismos endpoints con la misma logica. La diferencia de
alcance es solo de lectura: el historial completo es de administrador/contador/
dueño; una cajera ve unicamente los cierres donde ella es titular o quien cerro.
"""
import json
from collections import Counter
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from . import cierre_turno as servicio
from .auth_helpers import _auth_response, _get_role_name, _is_admin_user
from .cierre_turno import CierreTurnoError
from .impresion_lpd import imprimir_acta_cierre_turno
from .pdf_reportes import generar_pdf_acta_cierre_turno
from .reportes_pdf_views import responder_pdf
from .models import VGCierreTurno, VGCierreTurnoLinea, VGConfiguracionCierreTurno, VGUsuario

MAX_CIERRES_LISTADO = 300


# ---------------------------------------------------------------------------
# Serializacion (montos como string decimal, fechas ISO)
# ---------------------------------------------------------------------------
def _iso(valor):
    return valor.isoformat() if valor else None


def _txt(valor):
    return str(valor) if valor is not None else None


def _linea_json(dato):
    """Campos comunes de una linea, sea pendiente (dict) o ya cerrada (VGCierreTurnoLinea)."""
    return {
        'origen': dato['origen'],
        'origen_id': dato['origen_id'],
        'fecha_transaccion': _iso(dato['fecha_transaccion']),
        'concepto': dato['concepto'],
        'documento': dato['documento'],
        'cliente': dato['cliente'],
        'numero_cobro': dato['numero_cobro'],
        'saldo_posterior': _txt(dato['saldo_posterior']),
        'referencia': dato['referencia'],
        'metodo_pago_id': dato['metodo_pago'].pk if dato.get('metodo_pago') else dato.get('metodo_pago_id'),
        'metodo_pago_nombre': dato['metodo_pago_nombre'],
        'moneda': dato['moneda'],
        'es_efectivo': dato['es_efectivo'],
        'monto_usd': _txt(dato['monto_usd']),
        'monto_bs': _txt(dato['monto_bs']),
        'tasa_cambio_referencia': _txt(dato['tasa_cambio_referencia']),
    }


def _linea_cierre_json(linea, modificaciones=()):
    dato = {campo: getattr(linea, campo) for campo in (
        'origen', 'origen_id', 'fecha_transaccion', 'concepto', 'documento', 'cliente', 'numero_cobro',
        'saldo_posterior', 'referencia', 'metodo_pago_id', 'metodo_pago_nombre', 'moneda', 'es_efectivo',
        'monto_usd', 'monto_bs', 'tasa_cambio_referencia',
    )}
    return {
        **_linea_json(dato),
        'id': linea.id,
        'estado': linea.estado,
        'estado_label': linea.get_estado_display(),
        'nota': linea.nota,
        'modificaciones': list(modificaciones),
    }


def _cierre_json(cierre, incluir_lineas=False, con_modificaciones=None):
    """
    `con_modificaciones`: cuantas lineas cambiaron despues del cierre (el listado lo
    calcula en bloque). Con `incluir_lineas` se calcula aca y cada linea trae sus cambios.
    """
    lineas = list(cierre.lineas.select_related('cierre')) if incluir_lineas else None
    cambios = servicio.modificaciones_de_lineas(lineas) if incluir_lineas else {}
    if incluir_lineas:
        con_modificaciones = len(cambios)
    datos = {
        'id': cierre.id,
        'numero': cierre.numero,
        'codigo': f'CT-{cierre.numero:06d}',
        'tipo': cierre.tipo,
        'tipo_label': cierre.get_tipo_display(),
        'titular_id': cierre.titular_id,
        'titular_nombre': cierre.titular_nombre,
        'titular_rol': cierre.titular_rol,
        'cerrado_por_id': cierre.cerrado_por_id,
        'cerrado_por_nombre': cierre.cerrado_por_nombre,
        'cerrado_por_rol': cierre.cerrado_por_rol,
        'fecha_cierre': _iso(cierre.fecha_cierre),
        'desde': _iso(cierre.desde),
        'hasta': _iso(cierre.hasta),
        'novedad': cierre.novedad,
        'total_lineas': cierre.total_lineas,
        'total_confirmadas': cierre.total_confirmadas,
        'total_no_llegaron': cierre.total_no_llegaron,
        'con_modificaciones': con_modificaciones or 0,
    }
    if incluir_lineas:
        datos['lineas'] = [_linea_cierre_json(linea, cambios.get(linea.id, ())) for linea in lineas]
    return datos


def _config_json(config):
    return {
        'activo': config.activo,
        'fecha_activacion': _iso(config.fecha_activacion),
        'umbral_tardio_horas': config.umbral_tardio_horas,
    }


def _resumen_json(usuario):
    filas = []
    for fila in servicio.resumen_pendientes():
        filas.append({
            **fila,
            'mas_antigua': _iso(fila['mas_antigua']),
            'es_mio': fila['titular_id'] == usuario.id,
        })
    return filas


# ---------------------------------------------------------------------------
# Utilidades de las vistas
# ---------------------------------------------------------------------------
def _sin_permiso():
    return _auth_response({'ok': False, 'message': 'No tienes permiso para el cierre de turno.'}, status=401)


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}, None
    except json.JSONDecodeError:
        return None, _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)


def _titular_de(request, valor):
    """El titular pedido (por defecto, el propio usuario). None si no existe o esta inactivo."""
    if valor in (None, ''):
        return request.user
    try:
        return VGUsuario.objects.select_related('id_role').get(pk=int(valor), is_active=True)
    except (TypeError, ValueError, VGUsuario.DoesNotExist):
        return None


def _cierres_visibles(usuario):
    """Administrador/contador/dueño ven todos los cierres; una cajera solo donde es titular o quien cerro."""
    consulta = VGCierreTurno.objects.all()
    if not _is_admin_user(usuario):
        consulta = consulta.filter(Q(titular=usuario) | Q(cerrado_por=usuario))
    return consulta


def _fecha(valor, por_defecto):
    if not valor:
        return por_defecto
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
@csrf_exempt
def cierre_turno_estado_view(request):
    """Lo minimo para el aviso fijo y el badge: se consulta con frecuencia, asi que es liviano."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not servicio.usuario_puede_cobrar(request.user):
        return _sin_permiso()

    config = VGConfiguracionCierreTurno.obtener_config()
    resumen = _resumen_json(request.user) if config.activo else []
    mios = next((fila['cantidad'] for fila in resumen if fila['es_mio']), 0)
    return _auth_response({
        'ok': True,
        **_config_json(config),
        'mis_pendientes': mios,
        'pendientes': resumen,
        'pendientes_ajenos': [fila for fila in resumen if not fila['es_mio']],
    })


@csrf_exempt
def cierre_turno_pendientes_view(request):
    """Detalle de lo pendiente de un titular (`titular_id`, por defecto el propio usuario) para armar el cierre."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not servicio.usuario_puede_cobrar(request.user):
        return _sin_permiso()

    titular = _titular_de(request, request.GET.get('titular_id'))
    if titular is None:
        return _auth_response({'ok': False, 'message': 'La persona indicada no existe o está inactiva.'}, status=404)

    detalle = servicio.detalle_pendientes(titular, request.user)
    return _auth_response({
        'ok': True,
        'titular': {'id': titular.id, 'nombre': servicio._nombre_usuario(titular), 'rol': _get_role_name(titular)},
        'es_propio': titular.id == request.user.id,
        'activo': detalle['activo'],
        'corte': _iso(detalle['corte']),
        'tipo': detalle['tipo'],
        'umbral_tardio_horas': detalle['umbral_tardio_horas'],
        'lineas': [_linea_json(linea) for linea in detalle['lineas']],
        'lotes_pos_abiertos': [
            {'id': lote.id, 'numero': lote.numero, 'metodo_pago_nombre': lote.metodo_pago.nombre}
            for lote in detalle['lotes_pos_abiertos']
        ],
    })


@csrf_exempt
def cierre_turno_cerrar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not servicio.usuario_puede_cobrar(request.user):
        return _sin_permiso()

    data, error = _json_body(request)
    if error:
        return error

    titular = _titular_de(request, data.get('titular_id'))
    if titular is None:
        return _auth_response({'ok': False, 'message': 'La persona indicada no existe o está inactiva.'}, status=404)

    corte = None
    if data.get('corte'):
        corte = parse_datetime(str(data['corte']))
        if corte is None:
            return _auth_response({'ok': False, 'message': 'La hora de corte no es valida.'}, status=400)
        if timezone.is_naive(corte):
            corte = timezone.make_aware(corte)

    lineas = data.get('lineas')
    if not isinstance(lineas, list):
        return _auth_response({'ok': False, 'message': 'Falta la lista de transacciones a cerrar.'}, status=400)

    try:
        cierre = servicio.cerrar_turno(
            titular, request.user, lineas, str(data.get('novedad', '') or ''), corte=corte,
        )
    except CierreTurnoError as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)

    # El turno ya quedo cerrado: nada de lo que pase al imprimir lo deshace. El acta se puede
    # reimprimir cuando se arregle la impresora.
    impresion = _imprimir_acta(cierre)
    mensaje = f'Turno cerrado: {cierre.total_confirmadas} confirmada(s), {cierre.total_no_llegaron} que no llegó/llegaron.'
    mensaje += ' Acta enviada a la impresora.' if impresion['ok'] else f' No se pudo imprimir el acta: {impresion["message"]}'
    return _auth_response({
        'ok': True,
        'message': mensaje,
        'impresion': impresion,
        'cierre': _cierre_json(cierre, incluir_lineas=True),
    }, status=201)


def _imprimir_acta(cierre, es_reimpresion=False):
    try:
        exito, motivo = imprimir_acta_cierre_turno(cierre, es_reimpresion=es_reimpresion)
    except Exception as exc:  # una impresora caida no puede tumbar ni el cierre ni su respuesta
        exito, motivo = False, f'Error al imprimir: {exc}'
    return {'ok': exito, 'message': motivo or 'Impreso.'}


def _cierre_visible_o_error(request, cierre_id):
    """El cierre pedido si este usuario puede verlo (una cajera, solo los suyos); si no, la respuesta de error."""
    try:
        return _cierres_visibles(request.user).get(pk=int(cierre_id)), None
    except (TypeError, ValueError, VGCierreTurno.DoesNotExist):
        return None, _auth_response({'ok': False, 'message': 'El cierre no existe.'}, status=404)


@csrf_exempt
def cierre_turno_imprimir_view(request):
    """Reimprime el acta (ticket de la impresora de caja) de un cierre. POST {cierre_id}."""
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not servicio.usuario_puede_cobrar(request.user):
        return _sin_permiso()
    data, error = _json_body(request)
    if error:
        return error
    cierre, error = _cierre_visible_o_error(request, data.get('cierre_id'))
    if error:
        return error
    impresion = _imprimir_acta(cierre, es_reimpresion=True)
    if not impresion['ok']:
        return _auth_response({'ok': False, 'message': impresion['message']}, status=502)
    return _auth_response({'ok': True, 'message': f'Acta {cierre.codigo} enviada a la impresora.'})


@csrf_exempt
def cierre_turno_acta_pdf_view(request):
    """Acta A4 en PDF de un cierre (`cierre_id`). Siempre se arma con el estado de hoy: avisa lo modificado despues del cierre."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not servicio.usuario_puede_cobrar(request.user):
        return _sin_permiso()
    cierre, error = _cierre_visible_o_error(request, request.GET.get('cierre_id'))
    if error:
        return error
    pdf = generar_pdf_acta_cierre_turno(servicio.datos_del_acta(cierre), generado_en=timezone.localtime())
    return responder_pdf(pdf, f'acta-cierre-turno-{cierre.codigo}', con_fecha=False)


@csrf_exempt
def cierre_turno_cierres_view(request):
    """
    Historial de cierres. Administrador/contador/dueño ven todos; una cajera, solo
    los suyos (titular o quien cerro). Con `cierre_id` devuelve el acta con sus lineas.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not servicio.usuario_puede_cobrar(request.user):
        return _sin_permiso()

    consulta = _cierres_visibles(request.user)

    cierre_id = request.GET.get('cierre_id')
    if cierre_id:
        try:
            cierre = consulta.prefetch_related('lineas').get(pk=int(cierre_id))
        except (TypeError, ValueError, VGCierreTurno.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El cierre no existe.'}, status=404)
        return _auth_response({'ok': True, 'cierre': _cierre_json(cierre, incluir_lineas=True)})

    hoy = timezone.localdate()
    desde = _fecha(request.GET.get('desde'), hoy - timedelta(days=30))
    hasta = _fecha(request.GET.get('hasta'), hoy)
    if desde is None or hasta is None or desde > hasta:
        return _auth_response({'ok': False, 'message': 'Rango de fechas invalido.'}, status=400)
    inicio = timezone.make_aware(datetime.combine(desde, time.min))
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min))
    consulta = consulta.filter(fecha_cierre__gte=inicio, fecha_cierre__lt=fin)

    tipo = request.GET.get('tipo')
    if tipo:
        if tipo not in {clave for clave, _ in VGCierreTurno.TIPOS}:
            return _auth_response({'ok': False, 'message': 'Tipo invalido.'}, status=400)
        consulta = consulta.filter(tipo=tipo)
    if request.GET.get('titular_id'):
        try:
            consulta = consulta.filter(titular_id=int(request.GET['titular_id']))
        except ValueError:
            return _auth_response({'ok': False, 'message': 'Titular invalido.'}, status=400)
    if request.GET.get('con_no_llegaron') in ('1', 'true'):
        consulta = consulta.filter(total_no_llegaron__gt=0)

    cierres = list(consulta.order_by('-fecha_cierre', '-numero')[:MAX_CIERRES_LISTADO])
    # "Modificado despues del cierre" para todo el listado de una vez (no cierre por cierre).
    lineas = list(VGCierreTurnoLinea.objects.filter(cierre__in=cierres).select_related('cierre'))
    cambios = servicio.modificaciones_de_lineas(lineas)
    modificadas = Counter(linea.cierre_id for linea in lineas if linea.id in cambios)
    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'cierres': [_cierre_json(cierre, con_modificaciones=modificadas[cierre.id]) for cierre in cierres],
        'titulares': [
            {'id': usuario.id, 'nombre': servicio._nombre_usuario(usuario)}
            for usuario in VGUsuario.objects.filter(cierres_turno_titular__isnull=False).distinct()
        ] if _is_admin_user(request.user) else [],
    })


@csrf_exempt
def admin_cierre_turno_config_view(request):
    """GET: configuracion. POST (`action`): activar | umbral. Solo administrador/contador/dueño."""
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para esta configuración.'}, status=401)

    if request.method == 'GET':
        return _auth_response({'ok': True, **_config_json(VGConfiguracionCierreTurno.obtener_config())})

    data, error = _json_body(request)
    if error:
        return error
    accion = str(data.get('action', '')).strip().lower()
    try:
        if accion == 'activar':
            config = servicio.activar_cierre_turno(request.user)
            mensaje = f'Cierre de turno activado desde el {config.fecha_activacion:%d/%m/%Y}.'
        elif accion == 'umbral':
            config = servicio.actualizar_umbral_tardio(request.user, data.get('horas'))
            mensaje = f'Umbral de cierre tardío: {config.umbral_tardio_horas} horas.'
        else:
            return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)
    except CierreTurnoError as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)
    return _auth_response({'ok': True, 'message': mensaje, **_config_json(config)})
