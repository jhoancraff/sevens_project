from django.test import TestCase, override_settings

from sevens.impresion_termica import (
    _build_ticket_bytes,
    _build_ticket_secundario_bytes,
    _collect_print_items,
    _datos_comanda,
    _bloques_comanda,
    _titulo_estacion,
)
from sevens.models import (
    VGCategoriaProducto, VGDetallePedido, VGDetallePedidoOpcion, VGGrupoOpcionProducto, VGPedido, VGProducto, VGRol, VGUsuario,
)

IP = '10.2.0.1'


class CategoriasOcultasBase(TestCase):
    def setUp(self):
        rol, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.mesero = VGUsuario.objects.create_user(
            username='oscar', password='claveMesero123', cedula='97200001', email='oscar@sevens.test', id_role=rol,
        )
        self.entradas = VGCategoriaProducto.objects.create(nombre='Entradas OC', ip_impresora=IP, puerto_impresora=9100)
        self.guarniciones = VGCategoriaProducto.objects.create(nombre='Guarniciones OC', ip_impresora=IP, puerto_impresora=9100)
        self.oculta = VGCategoriaProducto.objects.create(
            nombre='Acompañantes Tradicionales OC', ip_impresora=IP, puerto_impresora=9100, activa=False,
        )

    def pedido(self):
        return VGPedido.objects.create(usuario=self.mesero, tipo_pedido='llevar', estado='pendiente', subtotal='5', total='5')

    def producto(self, nombre, categoria, **extra):
        return VGProducto.objects.create(nombre=nombre, categoria=categoria, precio_venta='5', disponible=True, **extra)

    def items(self, pedido):
        detalles = list(
            pedido.detalles.select_related('producto__categoria').order_by('id')
            .prefetch_related('adicionales__preparacion', 'opciones__preparacion', 'opciones__producto__categoria', 'opciones__grupo')
        )
        return _collect_print_items(detalles), detalles


class TituloDeLaComandaTests(CategoriasOcultasBase):
    def test_las_categorias_ocultas_no_salen_en_el_titulo(self):
        self.assertEqual(_titulo_estacion([self.oculta, self.entradas, self.guarniciones]), 'ENTRADAS OC / GUARNICIONES OC')

    def test_sin_ocultas_el_titulo_es_el_de_siempre(self):
        self.assertEqual(_titulo_estacion([self.guarniciones, self.entradas]), 'ENTRADAS OC / GUARNICIONES OC')

    def test_si_solo_hay_una_oculta_se_usan_las_visibles_de_esa_impresora(self):
        self.assertEqual(_titulo_estacion([self.oculta]), 'ENTRADAS OC / GUARNICIONES OC')

    def test_si_no_hay_ninguna_visible_el_titulo_es_comanda(self):
        VGCategoriaProducto.objects.filter(pk__in=[self.entradas.pk, self.guarniciones.pk]).update(activa=False)
        self.assertEqual(_titulo_estacion([self.oculta]), 'COMANDA')

    def test_el_titulo_va_en_los_datos_de_la_comanda_dibujada(self):
        pedido = self.pedido()
        datos = _datos_comanda(pedido, _titulo_estacion([self.entradas, self.oculta]), [])
        self.assertEqual(datos['estacion'], 'ENTRADAS OC')


class ComandaImpresaTests(CategoriasOcultasBase):
    def armar(self):
        pedido = self.pedido()
        entrante = self.producto('Tequeños OC', self.entradas)
        arepa = self.producto('Arepa OC', self.oculta)
        VGDetallePedido.objects.create(pedido=pedido, producto=entrante, cantidad=1, precio_unitario='5', estado='pendiente')
        VGDetallePedido.objects.create(pedido=pedido, producto=arepa, cantidad=1, precio_unitario='5', estado='pendiente')
        items, detalles = self.items(pedido)
        return pedido, items, detalles

    @override_settings(COMANDA_GRAFICA=False)
    def test_la_comanda_de_texto_no_imprime_la_categoria_oculta(self):
        pedido, items, _ = self.armar()
        ticket = _build_ticket_bytes(pedido, [self.entradas, self.oculta], items)
        self.assertIn(b'ENTRADAS OC', ticket)
        self.assertNotIn('ACOMPAÑANTES'.encode('cp1252'), ticket)

    def test_la_comanda_dibujada_usa_el_titulo_sin_la_oculta(self):
        pedido, items, _ = self.armar()
        with self.settings(COMANDA_GRAFICA=True):
            from unittest.mock import patch
            with patch('sevens.impresion_termica._comanda_a_bytes', return_value=b'x') as dibujar:
                _build_ticket_bytes(pedido, [self.entradas, self.oculta], items)
        self.assertEqual(dibujar.call_args.args[0]['estacion'], 'ENTRADAS OC')

    def test_el_plato_armado_no_escribe_la_categoria_oculta(self):
        pedido = self.pedido()
        corte = self.producto('Corte OC', self.entradas)
        arepa = self.producto('Arepa OC', self.oculta)
        VGDetallePedido.objects.create(pedido=pedido, producto=corte, cantidad=1, precio_unitario='5', estado='pendiente', grupo_armado=1)
        VGDetallePedido.objects.create(pedido=pedido, producto=arepa, cantidad=1, precio_unitario='5', estado='pendiente', grupo_armado=1)
        items, _ = self.items(pedido)
        (bloque,) = _bloques_comanda(items)
        self.assertEqual(bloque['plato'], 'PLATO 1 - ENTRADAS OC')

    def test_un_plato_armado_solo_con_categoria_oculta_queda_como_plato_n(self):
        pedido = self.pedido()
        arepa = self.producto('Arepa OC', self.oculta)
        casabe = self.producto('Casabe OC', self.oculta)
        VGDetallePedido.objects.create(pedido=pedido, producto=arepa, cantidad=1, precio_unitario='5', estado='pendiente', grupo_armado=3)
        VGDetallePedido.objects.create(pedido=pedido, producto=casabe, cantidad=1, precio_unitario='5', estado='pendiente', grupo_armado=3)
        items, _ = self.items(pedido)
        (bloque,) = _bloques_comanda(items)
        self.assertEqual(bloque['plato'], 'PLATO 3')

    @override_settings(COMANDA_GRAFICA=False)
    def test_la_copia_secundaria_de_una_oculta_tampoco_la_nombra(self):
        pedido = self.pedido()
        arepa = self.producto('Arepa OC', self.oculta)
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=arepa, cantidad=1, precio_unitario='5', estado='pendiente', grupo_armado=2,
        )
        ticket = _build_ticket_secundario_bytes(pedido, self.oculta, [detalle])
        self.assertNotIn('ACOMPAÑANTES'.encode('cp1252'), ticket)
        self.assertNotIn(b'Acompa', ticket)
        self.assertIn(b'Plato 2', ticket)
