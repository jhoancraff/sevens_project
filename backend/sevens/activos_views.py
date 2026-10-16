"""
Utensilios y equipos del restaurante (neveras, platos, tenedores, impresoras, franelas para los
empleados...): una tabla aparte de los ingredientes (ver models.VGActivo) para que el inventario
de ingredientes, las recetas, los costos y el estado de resultados no se enteren de que existen.

La cantidad de un artículo SOLO cambia con un movimiento (VGMovimientoActivo): entrada (compra),
entrega a un empleado, baja o ajuste de conteo. Cada uno queda con su motivo; las entregas llevan
quien recibió y un comprobante imprimible (ver reportes_pdf_views.comprobante_entrega_activo_pdf_view).

Endpoints: admin_activos_view (artículos y sus movimientos), admin_categorias_activos_view y
admin_inventario_general_view (ingredientes y utensilios juntos o separados). Solo administradores.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q
from django.views.decorators.csrf import csrf_exempt

from .api_views import HIDDEN_INGREDIENT_IDS, _costo_unitario_efectivo
from .auth_helpers import _auth_response, _is_admin_user
from .models import (
    VGActivo,
    VGCategoriaActivo,
    VGCategoriaIngrediente,
    VGCorrelativoFiscal,
    VGIngrediente,
    VGMovimientoActivo,
)

SERIE_ENTREGA = 'ENTREGA_ACTIVO'
LARGO_NOMBRE = 150
CENTIMOS = Decimal('0.01')


def _json(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return None


def _solo_admin(request, metodos):
    if request.method not in metodos:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    return None


def _entero(valor, nombre, minimo=0):
    """Entero >= minimo o (None, mensaje)."""
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return None, f'{nombre} debe ser un número entero.'
    if numero < minimo:
        return None, f'{nombre} no puede ser menor a {minimo}.'
    return numero, None


def _nombre_persona(usuario):
    return (usuario.get_full_name() or usuario.username) if usuario else ''


def serialize_activo(activo):
    return {
        'id': activo.id,
        'nombre': activo.nombre,
        'tipo': activo.tipo,
        'tipo_label': activo.get_tipo_display(),
        'categoria': activo.categoria_id,
        'categoria_nombre': activo.categoria.nombre if activo.categoria_id else '',
        'cantidad': activo.cantidad,
        'cantidad_minima': activo.cantidad_minima,
        'bajo_minimo': activo.cantidad_minima > 0 and activo.cantidad <= activo.cantidad_minima,
        'estado': activo.estado,
        'estado_label': activo.get_estado_display(),
        'ubicacion': activo.ubicacion,
        'valor_unitario': str(activo.valor_unitario) if activo.valor_unitario is not None else None,
        'valor_total': str((activo.valor_total or Decimal('0')).quantize(CENTIMOS)),
        'fecha_adquisicion': activo.fecha_adquisicion.isoformat() if activo.fecha_adquisicion else None,
        'proveedor': activo.proveedor,
        'serial': activo.serial,
        'notas': activo.notas,
        'activo': activo.activo,
    }


def serialize_movimiento(mov):
    return {
        'id': mov.id,
        'tipo': mov.tipo,
        'tipo_label': mov.get_tipo_display(),
        'delta': mov.delta,
        'cantidad_resultante': mov.cantidad_resultante,
        'motivo': mov.motivo,
        'receptor': mov.receptor,
        'comprobante': mov.codigo_comprobante,
        'registrado_por': _nombre_persona(mov.creado_por),
        'fecha': mov.fecha_creacion.isoformat(),
    }


def _validar_campos(data, activo=None):
    """
    Campos editables de un articulo (no incluye la cantidad: esa cambia solo con movimientos).
    Devuelve (campos, mensaje_de_error).
    """
    nombre = ' '.join(str(data.get('nombre', '') or '').split())
    if not nombre:
        return None, 'El nombre del artículo es obligatorio.'
    if len(nombre) > LARGO_NOMBRE:
        return None, f'El nombre no puede pasar de {LARGO_NOMBRE} caracteres.'
    repetido = VGActivo.objects.filter(nombre__iexact=nombre)
    if activo is not None:
        repetido = repetido.exclude(pk=activo.pk)
    if repetido.exists():
        return None, 'Ya existe un artículo con ese nombre.'

    tipo = str(data.get('tipo', 'equipo') or 'equipo').strip().lower()
    if tipo not in {clave for clave, _ in VGActivo.TIPOS}:
        return None, 'El tipo debe ser equipo o dotación.'
    estado = str(data.get('estado', 'bueno') or 'bueno').strip().lower()
    if estado not in {clave for clave, _ in VGActivo.ESTADOS}:
        return None, 'El estado no es válido.'

    categoria = None
    categoria_raw = data.get('categoria_id')
    if categoria_raw not in (None, '', 0, '0'):
        try:
            categoria = VGCategoriaActivo.objects.get(pk=int(categoria_raw))
        except (TypeError, ValueError, VGCategoriaActivo.DoesNotExist):
            return None, 'La categoría no existe.'

    minima, error = _entero(data.get('cantidad_minima') or 0, 'La cantidad mínima')
    if error:
        return None, error

    valor = None
    valor_raw = data.get('valor_unitario')
    if valor_raw not in (None, ''):
        try:
            valor = Decimal(str(valor_raw)).quantize(CENTIMOS)
        except InvalidOperation:
            return None, 'El valor unitario no es válido.'
        if valor < 0:
            return None, 'El valor unitario no puede ser negativo.'

    fecha = None
    fecha_raw = data.get('fecha_adquisicion')
    if fecha_raw not in (None, ''):
        try:
            fecha = date.fromisoformat(str(fecha_raw))
        except ValueError:
            return None, 'La fecha de adquisición no es válida.'

    return {
        'nombre': nombre,
        'tipo': tipo,
        'estado': estado,
        'categoria': categoria,
        'cantidad_minima': minima,
        'ubicacion': ' '.join(str(data.get('ubicacion', '') or '').split())[:80],
        'valor_unitario': valor,
        'fecha_adquisicion': fecha,
        'proveedor': str(data.get('proveedor', '') or '').strip()[:150],
        'serial': str(data.get('serial', '') or '').strip()[:100],
        'notas': str(data.get('notas', '') or '').strip(),
        'activo': bool(data.get('activo', True)),
    }, None


def _registrar_movimiento(activo, tipo, delta, motivo, usuario, receptor=''):
    """Aplica el cambio de cantidad y deja el movimiento. El caller ya tiene el articulo bloqueado."""
    activo.cantidad = activo.cantidad + delta
    activo.actualizado_por = usuario
    activo.save(update_fields=['cantidad', 'actualizado_por', 'fecha_actualizacion'])
    numero = VGCorrelativoFiscal.siguiente(SERIE_ENTREGA) if tipo == 'entrega' else None
    return VGMovimientoActivo.objects.create(
        activo_ref=activo, tipo=tipo, delta=delta, cantidad_resultante=activo.cantidad,
        motivo=motivo, receptor=receptor, numero_comprobante=numero,
        creado_por=usuario, actualizado_por=usuario,
    )


def _filtrar_activos(params):
    consulta = VGActivo.objects.select_related('categoria')
    if params.get('incluir_inactivos') not in ('1', 'true', 'True'):
        consulta = consulta.filter(activo=True)
    tipo = (params.get('tipo') or '').strip().lower()
    if tipo in ('equipo', 'dotacion'):
        consulta = consulta.filter(tipo=tipo)
    categoria = (params.get('categoria_id') or '').strip().lower()
    if categoria == 'sin':
        consulta = consulta.filter(categoria__isnull=True)
    elif categoria:
        try:
            consulta = consulta.filter(categoria_id=int(categoria))
        except ValueError:
            pass
    estado = (params.get('estado') or '').strip().lower()
    if estado:
        consulta = consulta.filter(estado=estado)
    ubicacion = (params.get('ubicacion') or '').strip()
    if ubicacion:
        consulta = consulta.filter(ubicacion__iexact=ubicacion)
    texto = ' '.join((params.get('q') or '').split())
    for palabra in texto.split():
        consulta = consulta.filter(
            Q(nombre__icontains=palabra) | Q(categoria__nombre__icontains=palabra)
            | Q(ubicacion__icontains=palabra) | Q(serial__icontains=palabra) | Q(proveedor__icontains=palabra)
        )
    return consulta.order_by('nombre')


@csrf_exempt
def admin_activos_view(request):
    error = _solo_admin(request, ('GET', 'POST'))
    if error:
        return error

    if request.method == 'GET':
        activo_id = request.GET.get('movimientos_de')
        if activo_id:
            try:
                activo = VGActivo.objects.get(pk=int(activo_id))
            except (TypeError, ValueError, VGActivo.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El artículo no existe.'}, status=404)
            movimientos = activo.movimientos.select_related('creado_por')[:200]
            return _auth_response({
                'ok': True,
                'activo': serialize_activo(activo),
                'movimientos': [serialize_movimiento(m) for m in movimientos],
            })

        activos = list(_filtrar_activos(request.GET))
        return _auth_response({
            'ok': True,
            'activos': [serialize_activo(a) for a in activos],
            'resumen': {
                'articulos': len(activos),
                'unidades': sum(a.cantidad for a in activos),
                'valor_total': str(sum((a.valor_total or Decimal('0') for a in activos), Decimal('0')).quantize(CENTIMOS)),
                'bajo_minimo': sum(1 for a in activos if a.cantidad_minima > 0 and a.cantidad <= a.cantidad_minima),
            },
            'categorias': [
                {'id': c.id, 'nombre': c.nombre, 'activo': c.activo} for c in VGCategoriaActivo.objects.order_by('nombre')
            ],
            'ubicaciones': sorted(
                {u for u in VGActivo.objects.exclude(ubicacion='').values_list('ubicacion', flat=True)},
                key=str.lower,
            ),
        })

    data = _json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    action = str(data.get('action', '')).strip().lower()

    if action == 'create':
        campos, mensaje = _validar_campos(data)
        if mensaje:
            return _auth_response({'ok': False, 'message': mensaje}, status=400)
        cantidad, mensaje = _entero(data.get('cantidad') or 0, 'La cantidad')
        if mensaje:
            return _auth_response({'ok': False, 'message': mensaje}, status=400)
        with transaction.atomic():
            activo = VGActivo.objects.create(**campos, cantidad=0, creado_por=request.user, actualizado_por=request.user)
            if cantidad > 0:
                _registrar_movimiento(activo, 'entrada', cantidad, 'Existencia inicial', request.user)
        activo.refresh_from_db()
        return _auth_response({
            'ok': True, 'message': f'Artículo «{activo.nombre}» creado.', 'activo': serialize_activo(activo),
        }, status=201)

    try:
        activo_id = int(data.get('id'))
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'El artículo no existe.'}, status=400)

    with transaction.atomic():
        try:
            activo = VGActivo.objects.select_for_update().get(pk=activo_id)
        except VGActivo.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El artículo no existe.'}, status=400)

        if action == 'update':
            campos, mensaje = _validar_campos(data, activo=activo)
            if mensaje:
                return _auth_response({'ok': False, 'message': mensaje}, status=400)
            for nombre, valor in campos.items():
                setattr(activo, nombre, valor)
            activo.actualizado_por = request.user
            activo.save()
            return _auth_response({
                'ok': True, 'message': f'Artículo «{activo.nombre}» actualizado.', 'activo': serialize_activo(activo),
            })

        if action == 'delete':
            nombre = activo.nombre
            activo.delete()
            return _auth_response({'ok': True, 'message': f'Artículo «{nombre}» eliminado.'})

        if action == 'movimiento':
            tipo = str(data.get('tipo', '')).strip().lower()
            if tipo not in ('entrada', 'entrega', 'baja', 'ajuste'):
                return _auth_response({'ok': False, 'message': 'El tipo de movimiento no es válido.'}, status=400)
            cantidad, mensaje = _entero(data.get('cantidad'), 'La cantidad', minimo=0 if tipo == 'ajuste' else 1)
            if mensaje:
                return _auth_response({'ok': False, 'message': mensaje}, status=400)
            motivo = str(data.get('motivo', '') or '').strip()[:255]
            receptor = ' '.join(str(data.get('receptor', '') or '').split())[:150]

            if tipo == 'entrega':
                if not receptor:
                    return _auth_response({'ok': False, 'message': 'Indica quién recibe la entrega.'}, status=400)
                delta = -cantidad
            elif tipo == 'baja':
                if not motivo:
                    return _auth_response({'ok': False, 'message': 'Indica el motivo de la baja (rota, perdida...).'}, status=400)
                delta = -cantidad
            elif tipo == 'entrada':
                delta = cantidad
            else:  # ajuste: `cantidad` es la existencia real contada
                if not motivo:
                    return _auth_response({'ok': False, 'message': 'Indica el motivo del ajuste de conteo.'}, status=400)
                delta = cantidad - activo.cantidad
                if delta == 0:
                    return _auth_response({'ok': False, 'message': 'La cantidad contada es la misma que ya hay.'}, status=400)
            if activo.cantidad + delta < 0:
                return _auth_response({
                    'ok': False,
                    'message': f'No hay suficiente existencia: quedan {activo.cantidad} de «{activo.nombre}».',
                }, status=400)

            movimiento = _registrar_movimiento(activo, tipo, delta, motivo, request.user, receptor)
            return _auth_response({
                'ok': True,
                'message': {
                    'entrada': f'Entrada registrada: +{cantidad}.',
                    'entrega': f'Entrega registrada a {receptor}: {cantidad} (comprobante {movimiento.codigo_comprobante}).',
                    'baja': f'Baja registrada: {cantidad}.',
                    'ajuste': f'Conteo ajustado a {activo.cantidad}.',
                }[tipo],
                'activo': serialize_activo(activo),
                'movimiento': serialize_movimiento(movimiento),
            }, status=201)

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


@csrf_exempt
def admin_categorias_activos_view(request):
    error = _solo_admin(request, ('GET', 'POST'))
    if error:
        return error

    def listado():
        return [
            {'id': c.id, 'nombre': c.nombre, 'activo': c.activo, 'articulos': c.cantidad}
            for c in VGCategoriaActivo.objects.annotate(cantidad=Count('activos')).order_by('nombre')
        ]

    if request.method == 'GET':
        return _auth_response({
            'ok': True,
            'categorias': listado(),
            'sin_categoria': VGActivo.objects.filter(categoria__isnull=True).count(),
        })

    data = _json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    action = str(data.get('action', '')).strip().lower()

    def nombre_valido(excluir_id=None):
        nombre = ' '.join(str(data.get('nombre', '') or '').split())
        if not nombre:
            return None, 'El nombre de la categoría es obligatorio.'
        if len(nombre) > 80:
            return None, 'El nombre no puede pasar de 80 caracteres.'
        repetida = VGCategoriaActivo.objects.filter(nombre__iexact=nombre)
        if excluir_id is not None:
            repetida = repetida.exclude(pk=excluir_id)
        if repetida.exists():
            return None, 'Ya existe una categoría con ese nombre.'
        return nombre, None

    if action == 'create':
        nombre, mensaje = nombre_valido()
        if mensaje:
            return _auth_response({'ok': False, 'message': mensaje}, status=400)
        categoria = VGCategoriaActivo.objects.create(nombre=nombre, creado_por=request.user, actualizado_por=request.user)
        return _auth_response({
            'ok': True, 'message': f'Categoría «{categoria.nombre}» creada.', 'categorias': listado(),
        }, status=201)

    try:
        categoria = VGCategoriaActivo.objects.get(pk=int(data.get('id')))
    except (TypeError, ValueError, VGCategoriaActivo.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'La categoría no existe.'}, status=400)

    if action == 'update':
        campos = ['actualizado_por', 'fecha_actualizacion']
        if 'nombre' in data:
            nombre, mensaje = nombre_valido(excluir_id=categoria.pk)
            if mensaje:
                return _auth_response({'ok': False, 'message': mensaje}, status=400)
            categoria.nombre = nombre
            campos.append('nombre')
        if 'activo' in data:
            categoria.activo = bool(data.get('activo'))
            campos.append('activo')
        categoria.actualizado_por = request.user
        categoria.save(update_fields=campos)
        return _auth_response({
            'ok': True, 'message': f'Categoría «{categoria.nombre}» actualizada.', 'categorias': listado(),
        })

    if action == 'delete':
        if categoria.activos.exists():
            return _auth_response({
                'ok': False,
                'message': 'La categoría tiene artículos: pásalos a otra categoría o desactívala en vez de eliminarla.',
            }, status=400)
        nombre = categoria.nombre
        categoria.delete()
        return _auth_response({'ok': True, 'message': f'Categoría «{nombre}» eliminada.', 'categorias': listado()})

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def filas_inventario_general(params):
    """
    Ingredientes y utensilios en un mismo formato, segun el filtro. Lo usan la pantalla
    «Todo el inventario» y su PDF para que ambos muestren exactamente lo mismo.

      tipo       todo (por defecto) | ingredientes | utensilios
      categoria  'sin' (sin categoria, en ambos), 'i:<id>' (categoria de ingredientes) o
                 'a:<id>' (categoria de utensilios); una categoria de un tipo deja fuera al otro
      q          texto: nombre o categoria

    Devuelve (ingredientes, utensilios), listas de dicts ya ordenadas por nombre.
    """
    tipo = (params.get('tipo') or 'todo').strip().lower()
    categoria = (params.get('categoria') or '').strip().lower()
    texto = ' '.join((params.get('q') or '').split()).lower()

    incluir_ing = tipo in ('todo', 'ingredientes') and not categoria.startswith('a:')
    incluir_act = tipo in ('todo', 'utensilios') and not categoria.startswith('i:')

    ingredientes = []
    if incluir_ing:
        consulta = VGIngrediente.objects.exclude(id__in=HIDDEN_INGREDIENT_IDS).select_related('categoria')
        if categoria == 'sin':
            consulta = consulta.filter(categoria__isnull=True)
        elif categoria.startswith('i:'):
            try:
                consulta = consulta.filter(categoria_id=int(categoria[2:]))
            except ValueError:
                pass
        for ing in consulta.order_by('nombre'):
            costo = _costo_unitario_efectivo(ing.costo_unitario, ing.precio_compra, ing.peso_real)
            ingredientes.append({
                'origen': 'ingrediente', 'id': ing.id, 'nombre': ing.nombre,
                'categoria': ing.categoria.nombre if ing.categoria_id else '',
                'cantidad': ing.stock_actual, 'unidad': ing.unidad_medida,
                'valor_total': (Decimal(ing.stock_actual or 0) * Decimal(costo or 0)).quantize(CENTIMOS),
            })

    utensilios = []
    if incluir_act:
        consulta = VGActivo.objects.filter(activo=True).select_related('categoria')
        if categoria == 'sin':
            consulta = consulta.filter(categoria__isnull=True)
        elif categoria.startswith('a:'):
            try:
                consulta = consulta.filter(categoria_id=int(categoria[2:]))
            except ValueError:
                pass
        for art in consulta.order_by('nombre'):
            utensilios.append({
                'origen': 'utensilio', 'id': art.id, 'nombre': art.nombre,
                'categoria': art.categoria.nombre if art.categoria_id else '',
                'cantidad': art.cantidad, 'unidad': 'unidad', 'tipo': art.get_tipo_display(),
                'ubicacion': art.ubicacion, 'estado': art.get_estado_display(),
                'valor_unitario': art.valor_unitario,
                'valor_total': (art.valor_total or Decimal('0')).quantize(CENTIMOS),
            })

    if texto:
        def coincide(fila):
            return texto in f"{fila['nombre']} {fila['categoria']} {fila.get('ubicacion', '')}".lower()
        ingredientes = [fila for fila in ingredientes if coincide(fila)]
        utensilios = [fila for fila in utensilios if coincide(fila)]
    return ingredientes, utensilios


def admin_inventario_general_view(request):
    error = _solo_admin(request, ('GET',))
    if error:
        return error
    ingredientes, utensilios = filas_inventario_general(request.GET)

    def serializar(fila):
        return {
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in fila.items()},
            'cantidad': str(fila['cantidad']),
        }

    total_ing = sum((f['valor_total'] for f in ingredientes), Decimal('0'))
    total_art = sum((f['valor_total'] for f in utensilios), Decimal('0'))
    return _auth_response({
        'ok': True,
        'ingredientes': [serializar(f) for f in ingredientes],
        'utensilios': [serializar(f) for f in utensilios],
        'resumen': {
            'ingredientes': len(ingredientes),
            'utensilios': len(utensilios),
            'valor_ingredientes': str(total_ing.quantize(CENTIMOS)),
            'valor_utensilios': str(total_art.quantize(CENTIMOS)),
        },
        'categorias_ingredientes': [
            {'id': c.id, 'nombre': c.nombre, 'activo': c.activo} for c in VGCategoriaIngrediente.objects.order_by('nombre')
        ],
        'categorias_utensilios': [
            {'id': c.id, 'nombre': c.nombre, 'activo': c.activo} for c in VGCategoriaActivo.objects.order_by('nombre')
        ],
    })
