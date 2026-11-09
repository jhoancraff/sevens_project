"""
La cuenta del cliente (pre-factura) es una foto: guarda sus lineas y su total al momento de generarla. La
nota de entrega y la factura, en cambio, se arman con lo que suman los pedidos AL COBRAR. Si el pedido
cambio entre una cosa y la otra (se quito o movio un item, se agrego un servicio, cambio el delivery), el
cliente recibe una nota por un monto distinto al de la cuenta que ya tiene en la mano.

Este modulo detecta ese caso para avisarle a la cajera ANTES de emitir el documento. La tasa se protege
aparte (ver tasa_cuenta.py); aqui se protege el monto.
"""
from decimal import Decimal

from .models import VGPreFactura

CENTAVO = Decimal('0.01')


def total_de_cuenta_de_pedidos(pedidos):
    """
    Lo que sumaria hoy la cuenta de estos pedidos. La cuenta lleva productos, adicionales, opciones, delivery
    y servicios; no lleva impuesto/propina/descuento a nivel de pedido (la pantalla no los usa), asi que se
    sacan para comparar peras con peras.
    """
    return sum(
        ((pedido.total - pedido.impuesto - pedido.propina + pedido.descuento) for pedido in pedidos),
        Decimal('0'),
    ).quantize(CENTAVO)


def cuenta_desactualizada(pedido_ids, pedidos):
    """
    Si el cliente tiene una cuenta vigente de EXACTAMENTE estos pedidos y su total ya no coincide con lo que
    suman ahora, devuelve los datos para avisar; si coincide (o no hay cuenta, o la cuenta es de otro
    conjunto de pedidos) devuelve None. Con la cuenta mas reciente basta: es la que el cliente tiene.
    """
    ids = set(int(pedido_id) for pedido_id in pedido_ids)
    if not ids:
        return None
    for cuenta in VGPreFactura.objects.filter(estado='vigente', pedidos__id__in=ids).distinct().order_by('-fecha_emision', '-id'):
        if set(cuenta.pedidos.values_list('id', flat=True)) != ids:
            continue
        total_cuenta = Decimal(cuenta.total).quantize(CENTAVO)
        total_actual = total_de_cuenta_de_pedidos(pedidos)
        if total_cuenta == total_actual:
            return None
        return {
            'codigo': f'PF-{cuenta.numero:06d}',
            'total_cuenta': total_cuenta,
            'total_actual': total_actual,
            'diferencia': (total_actual - total_cuenta).quantize(CENTAVO),
        }
    return None


def mensaje_cuenta_desactualizada(aviso, documento='la nota de entrega'):
    return (
        f"La cuenta {aviso['codigo']} que se le entregó al cliente es de ${aviso['total_cuenta']}, "
        f"pero ahora el pedido suma ${aviso['total_actual']} (diferencia ${aviso['diferencia']}). "
        f"Genera la cuenta de nuevo (conserva la tasa) o confirma emitir {documento} por el monto actual."
    )


def respuesta_cuenta_desactualizada(aviso, documento='la nota de entrega'):
    """Cuerpo JSON del 409 que pide confirmacion: la pantalla lo reconoce por `cuenta_desactualizada`."""
    return {
        'ok': False,
        'cuenta_desactualizada': True,
        'message': mensaje_cuenta_desactualizada(aviso, documento),
        'cuenta': {
            'codigo': aviso['codigo'],
            'total_cuenta': str(aviso['total_cuenta']),
            'total_actual': str(aviso['total_actual']),
            'diferencia': str(aviso['diferencia']),
        },
    }
