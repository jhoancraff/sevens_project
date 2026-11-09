import json
from decimal import Decimal

from django.test import TestCase

from sevens.models import (
    VGCategoriaProducto, VGDetallePedido, VGMetodoPago, VGNotaEntrega, VGPedido, VGPreFactura, VGProducto, VGRol, VGUsuario,
)
from sevens.tests import _set_tasa_actual


class CuentaMontoBase(TestCase):
    def setUp(self):
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.user = VGUsuario.objects.create_user(
            username='cm_cajera', password='claveCajera123', cedula='96100001', email='cm_cajera@sevens.test', id_role=cajera_role,
        )
        self.client.force_login(self.user)
        categoria = VGCategoriaProducto.objects.create(nombre='Platos CM')
        self.plato = VGProducto.objects.create(nombre='Plato CM', categoria=categoria, precio_venta='20.85', disponible=True)
        self.punta = VGProducto.objects.create(
            nombre='Punta cruda', categoria=categoria, precio_venta='6.50', disponible=True, venta_por_peso=True,
        )
        VGMetodoPago.objects.create(nombre='Efectivo CM', moneda='USD', es_efectivo=True)
        _set_tasa_actual('100.0000')

    def post(self, ruta, cuerpo=None):
        return self.client.post(ruta, data=json.dumps(cuerpo or {}), content_type='application/json')

    def crear_pedido(self, items):
        respuesta = self.post('/api/pedidos/', {'tipo_pedido': 'local', 'cliente_nombre': 'Cliente CM', 'items': items})
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        pedido = VGPedido.objects.get(pk=respuesta.json()['pedido']['id'])
        VGPedido.objects.filter(pk=pedido.pk).update(estado='entregado')
        pedido.detalles.update(estado='entregado')
        pedido.refresh_from_db()
        return pedido

    def cuenta(self, pedidos):
        respuesta = self.post('/api/prefacturas/', {'pedido_ids': [p.id for p in pedidos]})
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return respuesta.json()['prefactura']

    def cobrar(self, pedidos, **extra):
        return self.post('/api/pedidos/cobro/', {
            'pedido_ids': [p.id for p in pedidos], 'cliente_cedula': '96100111', 'cliente_nombre': 'Cliente CM', **extra,
        })


class RedondeoPorLineaTests(CuentaMontoBase):
    def test_un_producto_por_peso_suma_en_el_pedido_lo_mismo_que_en_la_cuenta_y_en_la_nota(self):
        # 350 g a $6.50/kg = 2.275 -> 2.28 por linea; antes el pedido sumaba 23.125 y daba 23.12.
        pedido = self.crear_pedido([
            {'product_id': self.plato.id, 'cantidad': 1, 'notas': ''},
            {'product_id': self.punta.id, 'cantidad': 1, 'peso_gramos': '350', 'notas': ''},
        ])
        self.assertEqual(pedido.total, Decimal('23.13'))
        cuenta = self.cuenta([pedido])
        self.assertEqual(Decimal(cuenta['total']), Decimal('23.13'))

        respuesta = self.cobrar([pedido])
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertEqual(Decimal(respuesta.json()['nota_entrega']['total']), Decimal('23.13'))

    def test_el_subtotal_de_cada_linea_ya_viene_redondeado_a_centavos(self):
        pedido = self.crear_pedido([{'product_id': self.punta.id, 'cantidad': 1, 'peso_gramos': '350', 'notas': ''}])
        self.assertEqual(pedido.detalles.get().subtotal, Decimal('2.28'))

    def test_la_cuenta_y_el_pedido_coinciden_con_varios_pesos_raros(self):
        for gramos in ('125', '175', '225', '333', '350', '475', '675', '777'):
            pedido = self.crear_pedido([
                {'product_id': self.plato.id, 'cantidad': 3, 'notas': ''},
                {'product_id': self.punta.id, 'cantidad': 1, 'peso_gramos': gramos, 'notas': ''},
            ])
            self.assertEqual(Decimal(self.cuenta([pedido])['total']), pedido.total, gramos)


class CuentaDesactualizadaTests(CuentaMontoBase):
    def pedido_de_dos_items(self):
        pedido = self.crear_pedido([
            {'product_id': self.plato.id, 'cantidad': 1, 'notas': ''},
            {'product_id': self.plato.id, 'cantidad': 1, 'notas': ''},
        ])
        return pedido

    def quitar_un_item(self, pedido):
        detalle = pedido.detalles.order_by('-id').first()
        respuesta = self.post(f'/api/pedidos/{pedido.id}/items/{detalle.id}/eliminar/', {'motivo': 'el cliente lo devolvio'})
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        pedido.refresh_from_db()

    def test_si_la_cuenta_coincide_el_cobro_sigue_normal(self):
        pedido = self.pedido_de_dos_items()
        self.cuenta([pedido])
        respuesta = self.cobrar([pedido])
        self.assertEqual(respuesta.status_code, 201, respuesta.content)

    def test_si_el_pedido_cambio_despues_de_la_cuenta_se_frena_sin_tocar_nada(self):
        pedido = self.pedido_de_dos_items()
        cuenta = self.cuenta([pedido])
        self.quitar_un_item(pedido)

        respuesta = self.cobrar([pedido])
        self.assertEqual(respuesta.status_code, 409)
        cuerpo = respuesta.json()
        self.assertTrue(cuerpo['cuenta_desactualizada'])
        self.assertEqual(cuerpo['cuenta']['codigo'], cuenta['codigo'])
        self.assertEqual(cuerpo['cuenta']['total_cuenta'], '41.70')
        self.assertEqual(cuerpo['cuenta']['total_actual'], '20.85')
        self.assertEqual(cuerpo['cuenta']['diferencia'], '-20.85')
        self.assertIn(cuenta['codigo'], cuerpo['message'])

        # Nada cambio: el pedido sigue cobrable y no nacio ninguna nota.
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'entregado')
        self.assertEqual(VGNotaEntrega.objects.count(), 0)

    def test_confirmando_el_monto_actual_se_emite_la_nota_por_lo_que_suma_hoy(self):
        pedido = self.pedido_de_dos_items()
        self.cuenta([pedido])
        self.quitar_un_item(pedido)
        respuesta = self.cobrar([pedido], confirmar_monto_cuenta=True)
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertEqual(Decimal(respuesta.json()['nota_entrega']['total']), Decimal('20.85'))

    def test_regenerar_la_cuenta_lo_resuelve_y_conserva_la_tasa(self):
        pedido = self.pedido_de_dos_items()
        self.cuenta([pedido])
        self.quitar_un_item(pedido)
        _set_tasa_actual('120.0000')
        nueva = self.post('/api/prefacturas/', {'pedido_ids': [pedido.id]}).json()
        self.assertTrue(nueva['tasa_reutilizada'])
        self.assertEqual(nueva['prefactura']['total'], '20.85')

        respuesta = self.cobrar([pedido])
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertEqual(respuesta.json()['nota_entrega']['tasa_cambio_referencia'], '100.0000')

    def test_una_cuenta_de_otro_conjunto_de_pedidos_no_dispara_el_aviso(self):
        a, b = self.pedido_de_dos_items(), self.pedido_de_dos_items()
        self.cuenta([a, b])
        self.quitar_un_item(a)
        # Se cobra solo `a`: la cuenta era de a+b, no es comparable.
        self.assertEqual(self.cobrar([a]).status_code, 201)

    def test_sin_cuenta_no_hay_aviso(self):
        pedido = self.pedido_de_dos_items()
        self.assertEqual(self.cobrar([pedido]).status_code, 201)

    def test_una_cuenta_anulada_no_cuenta(self):
        pedido = self.pedido_de_dos_items()
        cuenta = self.cuenta([pedido])
        self.assertEqual(self.post(f'/api/prefacturas/{cuenta["id"]}/anular/').status_code, 200)
        self.quitar_un_item(pedido)
        self.assertEqual(self.cobrar([pedido]).status_code, 201)

    def test_la_factura_desde_la_cuenta_tambien_pide_confirmacion(self):
        pedido = self.pedido_de_dos_items()
        cuenta = self.cuenta([pedido])
        self.quitar_un_item(pedido)
        respuesta = self.post(f'/api/prefacturas/{cuenta["id"]}/convertir/')
        self.assertEqual(respuesta.status_code, 409, respuesta.content)
        self.assertTrue(respuesta.json()['cuenta_desactualizada'])
        self.assertEqual(VGPreFactura.objects.get(pk=cuenta['id']).estado, 'vigente')

        confirmada = self.post(f'/api/prefacturas/{cuenta["id"]}/convertir/', {'confirmar_monto_cuenta': True})
        self.assertEqual(confirmada.status_code, 201, confirmada.content)

    def test_la_pantalla_de_cobro_recibe_el_total_de_la_cuenta_vigente(self):
        pedido = self.pedido_de_dos_items()
        self.cuenta([pedido])
        from sevens.tasa_cuenta import prefacturas_con_tasa_vigente
        self.assertEqual(prefacturas_con_tasa_vigente()[0]['total'], '41.70')
