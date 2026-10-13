"""
Cashea: cuenta "Por cobrar a Cashea" y liquidaciones semanales.

Una venta con Cashea se cobra en dos partes sobre la MISMA nota de entrega:
la inicial en caja con la cuenta real (efectivo, pago movil...) y el financiado
con el metodo es_cashea (referencia = numero de orden de Cashea). La nota queda
pagada, pero el financiado no es dinero disponible: su saldo vive en la cuenta
Cashea hasta que Cashea liquida la semana, EN BOLIVARES a la tasa del dia, a una
cuenta registrada en el sistema.

Registrar esa liquidacion (liquidaciones_cashea_view) mueve el dinero asi, todo
en una transaccion:
  - VGTransferenciaCuenta Cashea (USD) -> cuenta destino (VES) por el neto:
    baja "Por cobrar a Cashea" y sube el banco con los Bs reales depositados,
  - VGGasto "Comision Cashea" pagado con la cuenta Cashea por la diferencia
    (servicios tecnologicos + IVA - retencion + descuento por adelanto - lo que
    Cashea devuelve por cancelaciones): la comision es un gasto aparte, nunca
    una venta menor.
La cuenta Cashea queda en cero para lo liquidado. Ver reportes.disponibilidad_por_cuenta
(excluida de los totales de disponibilidad) y models.VGLiquidacionCashea.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user
from .gastos_views import _registrar_abono_gasto
from .models import (
    VGCategoriaGasto,
    VGCorrelativoFiscal,
    VGGasto,
    VGLiquidacionCashea,
    VGMetodoPago,
    VGPago,
    VGTransferenciaCuenta,
)
from .reportes import tasa_para_fecha
from .tasa_cambio import obtener_tasa_actual

SERIE_LIQUIDACION = 'CASHEA_LIQ'
CATEGORIA_COMISION = 'Comisión Cashea'
CENTIMOS = Decimal('0.01')
SEIS_DECIMALES = Decimal('0.000001')


def _cuenta_cashea():
    return VGMetodoPago.objects.filter(es_cashea=True).first()


def _nombre_persona(usuario):
    return (usuario.get_full_name() or usuario.username) if usuario else ''


def _tasa_de_registro(pago, fecha):
    """Tasa con la que quedo registrado el cobro de Cashea (la del dia del cobro)."""
    nota = pago.nota_entrega
    return (
        pago.tasa_cambio_referencia
        or (nota.tasa_cambio_referencia if nota is not None else None)
        or tasa_para_fecha(fecha)
    )


def _serialize_pendiente(pago, hoy, tasa_actual=None):
    nota = pago.nota_entrega
    cliente = nota.cliente if nota is not None else None
    fecha = timezone.localtime(pago.fecha_pago).date()
    tasa_registro = _tasa_de_registro(pago, fecha)
    return {
        # Lo que nos debe Cashea esta fijo en dolares; en bolivares cambia con la
        # tasa: a la que se registro el cobro y a la tasa actual del sistema.
        'tasa_registro': str(tasa_registro) if tasa_registro else None,
        'monto_bs_registro': str((pago.monto * tasa_registro).quantize(CENTIMOS)) if tasa_registro else None,
        'tasa_actual': str(tasa_actual) if tasa_actual else None,
        'monto_bs_actual': str((pago.monto * tasa_actual).quantize(CENTIMOS)) if tasa_actual else None,
        'pago_id': pago.id,
        'orden_cashea': pago.referencia,
        'fecha': fecha.isoformat(),
        'dias': (hoy - fecha).days,
        'monto_usd': str(pago.monto.quantize(CENTIMOS)),
        'nota_id': nota.id if nota is not None else None,
        'nota_codigo': nota.codigo if nota is not None else '',
        'nota_estado': nota.estado if nota is not None else '',
        'cliente': cliente.nombre_completo if cliente is not None else '',
        'cobrado_por': _nombre_persona(pago.creado_por),
    }


def _serialize_liquidacion(liquidacion):
    return {
        'id': liquidacion.id,
        'codigo': liquidacion.codigo,
        'estado': liquidacion.estado,
        'fecha_deposito': liquidacion.fecha_deposito.isoformat(),
        'periodo_desde': liquidacion.periodo_desde.isoformat() if liquidacion.periodo_desde else None,
        'periodo_hasta': liquidacion.periodo_hasta.isoformat() if liquidacion.periodo_hasta else None,
        'cuenta_destino': liquidacion.cuenta_destino.nombre,
        'tasa_cambio': str(liquidacion.tasa_cambio),
        'deposito_bs': str(liquidacion.deposito_bs),
        'monto_financiado_usd': str(liquidacion.monto_financiado_usd.quantize(CENTIMOS)),
        'ajuste_cancelaciones_usd': str(liquidacion.ajuste_cancelaciones_usd.quantize(CENTIMOS)),
        'neto_usd': str(liquidacion.neto_usd.quantize(CENTIMOS)),
        'comision_usd': str(liquidacion.comision_usd.quantize(CENTIMOS)),
        'comision_pct_financiado': (
            str((liquidacion.comision_usd / liquidacion.monto_financiado_usd * 100).quantize(CENTIMOS))
            if liquidacion.monto_financiado_usd else None
        ),
        'referencia': liquidacion.referencia,
        'notas': liquidacion.notas,
        'registrado_por': _nombre_persona(liquidacion.creado_por),
        'fecha_creacion': liquidacion.fecha_creacion.isoformat(),
    }


def _decimal(valor, defecto=None):
    if valor in (None, ''):
        return defecto
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def _fecha(valor, defecto=None):
    if valor in (None, ''):
        return defecto
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        return None


def cashea_pendientes_view(request):
    """Cobros con Cashea que Cashea aun no ha pagado, mas la cuenta y lo que nos debe."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    cuenta = _cuenta_cashea()
    pagos = []
    if cuenta is not None:
        pagos = list(
            VGPago.objects.filter(metodo_pago=cuenta, estado='completado', liquidacion_cashea__isnull=True)
            .select_related('nota_entrega__cliente', 'creado_por')
            .order_by('fecha_pago', 'id')
        )
    hoy = timezone.localdate()
    total = sum((pago.monto for pago in pagos), Decimal('0'))
    tasa_obj = obtener_tasa_actual()
    tasa_actual = tasa_obj.tasa if tasa_obj else None
    pendientes = [_serialize_pendiente(pago, hoy, tasa_actual) for pago in pagos]
    return _auth_response({
        'ok': True,
        'cuenta_cashea': {'id': cuenta.id, 'nombre': cuenta.nombre, 'activo': cuenta.activo} if cuenta else None,
        'por_cobrar_usd': str(total.quantize(CENTIMOS)),
        'tasa_actual': str(tasa_actual) if tasa_actual else None,
        'por_cobrar_bs_registro': str(sum(
            (Decimal(item['monto_bs_registro']) for item in pendientes if item['monto_bs_registro']), Decimal('0'),
        ).quantize(CENTIMOS)),
        'por_cobrar_bs_actual': (
            str((total * tasa_actual).quantize(CENTIMOS)) if tasa_actual else None
        ),
        'cantidad': len(pagos),
        'pendientes': pendientes,
    })


@csrf_exempt
def liquidaciones_cashea_view(request):
    """
    GET: historial de liquidaciones. POST (action 'registrar' o 'anular'): ver
    el docstring del modulo.
    """
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        liquidaciones = (
            VGLiquidacionCashea.objects.select_related('cuenta_destino', 'creado_por').order_by('-fecha_deposito', '-numero')
        )
        vigentes = [item for item in liquidaciones if item.estado == 'registrada']
        return _auth_response({
            'ok': True,
            'liquidaciones': [_serialize_liquidacion(item) for item in liquidaciones],
            'totales': {
                'financiado_usd': str(sum((item.monto_financiado_usd for item in vigentes), Decimal('0')).quantize(CENTIMOS)),
                'comision_usd': str(sum((item.comision_usd for item in vigentes), Decimal('0')).quantize(CENTIMOS)),
                'neto_usd': str(sum((item.neto_usd for item in vigentes), Decimal('0')).quantize(CENTIMOS)),
                'deposito_bs': str(sum((item.deposito_bs for item in vigentes), Decimal('0')).quantize(CENTIMOS)),
            },
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', 'registrar')).strip().lower()
    if action == 'anular':
        return _anular_liquidacion(request, data)
    if action != 'registrar':
        return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)
    return _registrar_liquidacion(request, data)


def _registrar_liquidacion(request, data):
    cuenta_cashea = _cuenta_cashea()
    if cuenta_cashea is None:
        return _auth_response({
            'ok': False,
            'message': 'No hay una cuenta de Cashea configurada. Márcala en Métodos de pago.',
        }, status=400)

    # La liquidacion cubre UNA semana de ventas (el reporte de Cashea es
    # semanal, de lunes a domingo): se paga cualquier dia de la semana siguiente,
    # por eso el periodo y la fecha del deposito son datos distintos.
    desde = _fecha(data.get('periodo_desde'))
    hasta = _fecha(data.get('periodo_hasta'))
    if desde is None or hasta is None:
        return _auth_response({
            'ok': False,
            'message': 'Indica la semana (desde y hasta) que cubre el reporte de Cashea.',
        }, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    pago_ids = None
    if data.get('pago_ids'):
        try:
            pago_ids = {int(valor) for valor in data.get('pago_ids')}
        except (TypeError, ValueError):
            return _auth_response({'ok': False, 'message': 'La lista de cobros no es valida.'}, status=400)

    try:
        cuenta_destino = VGMetodoPago.objects.get(pk=int(data.get('cuenta_destino_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'La cuenta donde cayó el depósito no es valida.'}, status=400)
    if cuenta_destino.moneda != 'VES' or cuenta_destino.es_cashea:
        return _auth_response({
            'ok': False,
            'message': 'Cashea deposita en bolívares: elige una cuenta en Bs que no sea la de Cashea.',
        }, status=400)

    deposito_bs = _decimal(data.get('deposito_bs'))
    if deposito_bs is None or deposito_bs <= 0:
        return _auth_response({'ok': False, 'message': 'Indica los bolívares que depositó Cashea.'}, status=400)
    deposito_bs = deposito_bs.quantize(CENTIMOS)

    # Los dos totales del reporte de Cashea: lo que financio en la semana y lo
    # que paga (ya sin comisiones). Con ellos la comision sale del reporte, no
    # de una tasa, y la tasa que uso Cashea queda implicita: Bs / total en USD.
    financiado_reporte = _decimal(data.get('monto_financiado_reporte'))
    if financiado_reporte is None or financiado_reporte <= 0:
        return _auth_response({
            'ok': False,
            'message': 'Indica el «Monto financiado» que dice el reporte de Cashea.',
        }, status=400)
    financiado_reporte = financiado_reporte.quantize(CENTIMOS)
    total_pagar = _decimal(data.get('total_pagar_usd'))
    if total_pagar is None or total_pagar <= 0:
        return _auth_response({
            'ok': False,
            'message': 'Indica el «Total a pagar» en dólares que dice el reporte de Cashea.',
        }, status=400)
    total_pagar = total_pagar.quantize(CENTIMOS)
    tasa = (deposito_bs / total_pagar).quantize(Decimal('0.0001'))

    ajuste = _decimal(data.get('ajuste_cancelaciones_usd'), Decimal('0'))
    if ajuste is None or ajuste < 0:
        return _auth_response({'ok': False, 'message': 'El ajuste por cancelaciones no es valido.'}, status=400)
    ajuste = ajuste.quantize(SEIS_DECIMALES)

    hoy = timezone.localdate()
    fecha_deposito = _fecha(data.get('fecha_deposito'), hoy)
    if fecha_deposito is None:
        return _auth_response({'ok': False, 'message': 'La fecha del depósito no es valida.'}, status=400)

    referencia = str(data.get('referencia', '') or '').strip()[:100]
    notas = str(data.get('notas', '') or '').strip()

    with transaction.atomic():
        candidatos = (
            VGPago.objects.select_for_update()
            .filter(metodo_pago=cuenta_cashea, estado='completado', liquidacion_cashea__isnull=True,
                    fecha_pago__date__range=(desde, hasta))
        )
        if pago_ids is not None:
            pagos = list(candidatos.filter(pk__in=pago_ids))
            if len(pagos) != len(pago_ids):
                return _auth_response({
                    'ok': False,
                    'message': (
                        'Alguno de los cobros ya fue liquidado, fue anulado, no es de Cashea '
                        'o no cae dentro de la semana indicada. Recarga la lista.'
                    ),
                }, status=409)
        else:
            pagos = list(candidatos)
        if not pagos:
            return _auth_response({
                'ok': False,
                'message': f'No hay cobros de Cashea pendientes entre {desde:%d/%m/%Y} y {hasta:%d/%m/%Y}.',
            }, status=400)

        financiado = sum((pago.monto for pago in pagos), Decimal('0')).quantize(SEIS_DECIMALES)
        # El total de Sevens debe coincidir con el del reporte de Cashea: si no,
        # falta o sobra una orden y hay que revisarla ANTES de mover dinero.
        diferencia = (financiado_reporte - financiado.quantize(CENTIMOS)).quantize(CENTIMOS)
        if abs(diferencia) > CENTIMOS:
            return _auth_response({
                'ok': False,
                'message': (
                    f'No cuadra con el reporte de Cashea: Sevens suma ${financiado.quantize(CENTIMOS)} en '
                    f'{len(pagos)} cobro(s) de la semana y el reporte indica ${financiado_reporte} '
                    f'(diferencia ${diferencia}). Revisa las órdenes antes de registrar el pago.'
                ),
                'diferencia_usd': str(diferencia),
            }, status=400)
        # El neto es el «Total a pagar» del reporte; VGTransferenciaCuenta.monto_usd
        # va en 2 decimales y la comision absorbe cualquier resto para que la
        # cuenta Cashea quede exactamente en cero.
        neto_usd = total_pagar
        comision = (financiado - ajuste - neto_usd).quantize(SEIS_DECIMALES)
        if comision < 0:
            return _auth_response({
                'ok': False,
                'message': (
                    f'El depósito (${neto_usd}) es mayor a lo que se financió (${financiado.quantize(CENTIMOS)}). '
                    'Revisa el «Total a pagar» del reporte y los cobros incluidos.'
                ),
            }, status=400)
        if neto_usd < CENTIMOS:
            return _auth_response({'ok': False, 'message': 'El depósito es demasiado pequeño.'}, status=400)

        numero = VGCorrelativoFiscal.siguiente(SERIE_LIQUIDACION)
        codigo = f'CAS-{numero:06d}'
        concepto = f'Liquidación Cashea {codigo}'

        transferencia = VGTransferenciaCuenta.objects.create(
            fecha=fecha_deposito,
            cuenta_origen=cuenta_cashea,
            cuenta_destino=cuenta_destino,
            moneda_origen='USD',
            moneda_destino='VES',
            monto_origen=neto_usd,
            monto_destino=deposito_bs,
            tasa_cambio=tasa,
            monto_usd=neto_usd,
            referencia=referencia,
            concepto=concepto,
            creado_por=request.user,
            actualizado_por=request.user,
        )

        gasto = None
        if comision > 0:
            categoria, _ = VGCategoriaGasto.objects.get_or_create(
                nombre=CATEGORIA_COMISION, defaults={'creado_por': request.user, 'actualizado_por': request.user},
            )
            gasto = VGGasto.objects.create(
                categoria=categoria,
                descripcion=concepto,
                proveedor_nombre='Cashea',
                numero_comprobante=referencia,
                monto=comision,
                saldo_pendiente=comision,
                estado_pago='pendiente',
                fecha_gasto=fecha_deposito,
                notas=notas,
                tasa_cambio_referencia=tasa,
                moneda_origen='USD',
                creado_por=request.user,
                actualizado_por=request.user,
            )
            _registrar_abono_gasto(
                gasto, comision, cuenta_cashea, referencia or codigo, request.user, tasa_cambio_referencia=tasa,
            )

        liquidacion = VGLiquidacionCashea.objects.create(
            numero=numero,
            fecha_deposito=fecha_deposito,
            periodo_desde=desde,
            periodo_hasta=hasta,
            cuenta_cashea=cuenta_cashea,
            cuenta_destino=cuenta_destino,
            tasa_cambio=tasa,
            deposito_bs=deposito_bs,
            monto_financiado_usd=financiado,
            ajuste_cancelaciones_usd=ajuste,
            neto_usd=neto_usd,
            comision_usd=comision,
            referencia=referencia,
            notas=notas,
            transferencia=transferencia,
            gasto=gasto,
            creado_por=request.user,
            actualizado_por=request.user,
        )
        VGPago.objects.filter(pk__in=[pago.id for pago in pagos]).update(liquidacion_cashea=liquidacion)

    liquidacion = VGLiquidacionCashea.objects.select_related('cuenta_destino', 'creado_por').get(pk=liquidacion.pk)
    return _auth_response({
        'ok': True,
        'message': f'Liquidación {liquidacion.codigo} registrada: {len(pagos)} cobros.',
        'liquidacion': _serialize_liquidacion(liquidacion),
    }, status=201)


def _anular_liquidacion(request, data):
    motivo = str(data.get('motivo', '') or '').strip()
    if not motivo:
        return _auth_response({'ok': False, 'message': 'Indica el motivo de la anulación.'}, status=400)

    with transaction.atomic():
        try:
            liquidacion = VGLiquidacionCashea.objects.select_for_update().get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGLiquidacionCashea.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La liquidación no existe.'}, status=404)
        if liquidacion.estado == 'anulada':
            return _auth_response({'ok': False, 'message': 'La liquidación ya está anulada.'}, status=409)

        transferencia = liquidacion.transferencia
        gasto = liquidacion.gasto
        VGPago.objects.filter(liquidacion_cashea=liquidacion).update(liquidacion_cashea=None)
        liquidacion.estado = 'anulada'
        liquidacion.notas = f'{liquidacion.notas}\nANULADA: {motivo}'.strip()
        liquidacion.transferencia = None
        liquidacion.gasto = None
        liquidacion.actualizado_por = request.user
        liquidacion.save(update_fields=['estado', 'notas', 'transferencia', 'gasto', 'actualizado_por', 'fecha_actualizacion'])
        # Estos dos registros existen solo por esta liquidacion: al anularla se
        # retiran para que la cuenta Cashea y el banco vuelvan a su saldo previo.
        if transferencia is not None:
            transferencia.delete()
        if gasto is not None:
            gasto.abonos.all().delete()
            gasto.delete()

    return _auth_response({
        'ok': True,
        'message': f'Liquidación {liquidacion.codigo} anulada: sus cobros vuelven a estar por cobrar.',
    })
