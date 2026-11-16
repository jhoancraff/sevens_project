from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from sevens.api_views import racion_acompanante_para_comanda
from sevens.impresion_termica import (
    _bloques_comanda,
    _build_ticket_bytes,
    _collect_print_items,
    imprimir_comandas_pedido,
)
from sevens.models import (
    VGCategoriaProducto, VGDetallePedido, VGDetallePedidoOpcion, VGGrupoOpcionProducto, VGGrupoOpcionRacionPorTamano,
    VGPedido, VGProducto, VGRol, VGUsuario,
)


class PorcionesBase(TestCase):
    TABLA = {  # tramo -> (papas g, ensalada g, patacones u)
        250: ('120', '100', '2'),
        500: ('200', '200', '4'),
        1000: ('360', '350', '8'),
    }

    def setUp(self):
        rol, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.mesero = VGUsuario.objects.create_user(
            username='mario', password='claveMesero123', cedula='97100001', email='mario@sevens.test', id_role=rol,
        )
        self.carnes = VGCategoriaProducto.objects.create(nombre='Carnes PR', ip_impresora='10.1.0.1', puerto_impresora=9100)
        self.guarniciones = VGCategoriaProducto.objects.create(nombre='Guarniciones PR', ip_impresora='10.1.0.2', puerto_impresora=9100)
        self.papas = VGProducto.objects.create(nombre='Papas fritas', categoria=self.guarniciones, precio_venta='0', disponible=True, venta_por_peso=True)
        self.ensalada = VGProducto.objects.create(nombre='Ensalada', categoria=self.guarniciones, precio_venta='0', disponible=True, venta_por_peso=True)
        self.patacon = VGProducto.objects.create(nombre='Patacón', categoria=self.guarniciones, precio_venta='0', disponible=True, venta_por_peso=False)
        self.punta = VGProducto.objects.create(nombre='Punta trasera', categoria=self.carnes, precio_venta='6.50', disponible=True, venta_por_peso=True)
        self.grupo = VGGrupoOpcionProducto.objects.create(producto=self.punta, nombre='Guarnición', categoria_opciones=self.guarniciones)
        for tramo, (papas, ensalada, patacones) in self.TABLA.items():
            VGGrupoOpcionRacionPorTamano.objects.create(grupo=self.grupo, producto=self.papas, tramo_peso_gramos=tramo, cantidad=papas)
            VGGrupoOpcionRacionPorTamano.objects.create(grupo=self.grupo, producto=self.ensalada, tramo_peso_gramos=tramo, cantidad=ensalada)
            VGGrupoOpcionRacionPorTamano.objects.create(grupo=self.grupo, producto=self.patacon, tramo_peso_gramos=tramo, cantidad=patacones)

    def plato(self, peso, guarniciones, cantidad=1, pedido=None, grupo=None):
        pedido = pedido or VGPedido.objects.create(
            usuario=self.mesero, tipo_pedido='llevar', estado='pendiente', subtotal='10', total='10',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=self.punta, cantidad=cantidad, precio_unitario='6.50', peso_gramos=peso, estado='pendiente',
        )
        for guarnicion in guarniciones:
            VGDetallePedidoOpcion.objects.create(
                detalle_pedido=detalle, grupo_nombre='Guarnición', grupo=grupo or self.grupo, producto=guarnicion, precio_unitario=0,
            )
        return pedido, detalle

    def items(self, pedido):
        detalles = list(
            pedido.detalles.select_related('producto__categoria').order_by('id')
            .prefetch_related('adicionales__preparacion', 'opciones__preparacion', 'opciones__producto__categoria', 'opciones__grupo')
        )
        return _collect_print_items(detalles)

    def lineas_de_guarniciones(self, pedido):
        """Lo que llega a la impresora de guarniciones: [(plato con sus gramos, [(cantidad, guarnición), ...]), ...]."""
        solo = [item for item in self.items(pedido) if item['tipo'] == 'acompanante']
        return [
            (linea['nombre'], [(hija['cantidad'], hija['nombre']) for hija in linea['hijas']])
            for bloque in _bloques_comanda(solo) for linea in bloque['lineas']
        ]


class PorcionSegunLaTablaTests(PorcionesBase):
    def test_cada_tramo_exacto_escribe_la_celda_de_la_tabla(self):
        for peso, (papas, ensalada, patacones) in self.TABLA.items():
            pedido, _ = self.plato(peso, [self.papas, self.ensalada, self.patacon])
            self.assertEqual(
                self.lineas_de_guarniciones(pedido),
                [(f'Punta trasera {peso} g', [(f'{papas} g', 'Papas fritas'), (f'{ensalada} g', 'Ensalada'), (f'{patacones}x', 'Patacón')])],
                peso,
            )

    def test_un_peso_intermedio_usa_el_tramo_mas_cercano(self):
        # 600 g está a 100 de 500 y a 400 de 1000: gana 500.
        pedido, _ = self.plato(600, [self.papas])
        self.assertEqual(self.lineas_de_guarniciones(pedido)[0][1][0][0], '200 g')

    def test_un_peso_fuera_de_rango_usa_el_tramo_limite(self):
        pequeno, _ = self.plato(100, [self.papas])
        grande, _ = self.plato(2000, [self.papas])
        self.assertEqual(self.lineas_de_guarniciones(pequeno)[0][1][0][0], '120 g')
        self.assertEqual(self.lineas_de_guarniciones(grande)[0][1][0][0], '360 g')

    def test_dos_platos_en_una_misma_linea_duplican_la_porcion(self):
        pedido, _ = self.plato(500, [self.papas], cantidad=2)
        self.assertEqual(self.lineas_de_guarniciones(pedido), [('2x Punta trasera 500 g', [('400 g', 'Papas fritas')])])

    def test_platos_iguales_se_suman_y_platos_distintos_quedan_separados(self):
        pedido, _ = self.plato(500, [self.papas])
        self.plato(500, [self.papas], pedido=pedido)
        self.plato(1000, [self.papas], pedido=pedido)
        self.assertEqual(
            self.lineas_de_guarniciones(pedido),
            [('2x Punta trasera 500 g', [('400 g', 'Papas fritas')]), ('Punta trasera 1000 g', [('360 g', 'Papas fritas')])],
        )

    def test_lo_que_escribe_la_comanda_es_lo_que_descuenta_el_cobro(self):
        # La misma celda: el multiplicador del cobro es gramos / 1000 (la receta de una guarnición de peso es por kg).
        from sevens.api_views import _resolver_cantidad_tabla_racion_por_tamano
        _, detalle = self.plato(500, [self.papas])
        porcion = racion_acompanante_para_comanda(detalle.opciones.get(), detalle)
        multiplicador = _resolver_cantidad_tabla_racion_por_tamano(self.grupo.id, self.papas, detalle.peso_gramos)
        self.assertEqual(porcion['valor'] / Decimal('1000'), multiplicador)


class PorcionSinTablaTests(PorcionesBase):
    def test_sin_tabla_con_gramos_base_se_escriben_raciones(self):
        sin_tabla = VGGrupoOpcionProducto.objects.create(
            producto=self.punta, nombre='Otro', categoria_opciones=self.guarniciones, gramos_base_racion=250,
        )
        _, detalle = self.plato(490, [self.papas], grupo=sin_tabla)  # 490/250 = 1.96 -> 2 raciones
        porcion = racion_acompanante_para_comanda(detalle.opciones.get(), detalle)
        self.assertEqual((porcion['valor'], porcion['unidad']), (Decimal('2'), 'rac'))

    def test_sin_nada_la_guarnicion_de_peso_va_a_la_par_del_plato(self):
        vacio = VGGrupoOpcionProducto.objects.create(producto=self.punta, nombre='Vacío', categoria_opciones=self.guarniciones)
        _, detalle = self.plato(300, [self.papas], grupo=vacio)
        porcion = racion_acompanante_para_comanda(detalle.opciones.get(), detalle)
        self.assertEqual((porcion['valor'], porcion['unidad']), (Decimal('300'), 'g'))

    def test_sin_nada_una_guarnicion_por_unidad_es_una_por_plato(self):
        vacio = VGGrupoOpcionProducto.objects.create(producto=self.punta, nombre='Vacío', categoria_opciones=self.guarniciones)
        _, detalle = self.plato(300, [self.patacon], cantidad=2, grupo=vacio)
        porcion = racion_acompanante_para_comanda(detalle.opciones.get(), detalle)
        self.assertEqual((porcion['valor'], porcion['unidad']), (Decimal('2'), 'u'))

    def test_si_falla_el_calculo_la_guarnicion_sale_solo_con_su_nombre_y_no_se_pierde_la_comanda(self):
        pedido, _ = self.plato(500, [self.papas])
        with patch('sevens.api_views.racion_acompanante_para_comanda', side_effect=RuntimeError('boom')):
            items = self.items(pedido)
        guarnicion = [item for item in items if item['tipo'] == 'acompanante'][0]
        self.assertIsNone(guarnicion['porcion'])
        linea = _bloques_comanda([guarnicion])[0]['lineas'][0]
        self.assertEqual([hija['nombre'] for hija in linea['hijas']], ['Papas fritas'])


class PorcionEnLaComandaTests(PorcionesBase):
    def impresas(self, pedido):
        enviados = {}

        def conectar(direccion, timeout=None):
            conexion = MagicMock()
            conexion.__enter__.return_value = conexion
            conexion.sendall.side_effect = lambda datos, host=direccion[0]: enviados.__setitem__(host, datos)
            return conexion

        with patch('sevens.impresion_termica.socket.create_connection', side_effect=conectar), \
                patch('sevens.impresion_termica.time.sleep'):
            imprimir_comandas_pedido(pedido)
        return enviados

    @override_settings(COMANDA_GRAFICA=False)
    def test_la_comanda_de_texto_de_guarniciones_trae_gramos_y_el_plato(self):
        pedido, _ = self.plato(500, [self.papas, self.ensalada, self.patacon])
        texto = self.impresas(pedido)['10.1.0.2']
        for esperado in ('200 g Papas fritas', '200 g Ensalada', '4x Patac', 'para Punta trasera 500 g'):
            self.assertIn(esperado.encode('cp1252'), texto, esperado)

    def test_la_comanda_grafica_de_guarniciones_se_dibuja(self):
        pedido, _ = self.plato(500, [self.papas, self.patacon])
        datos = self.impresas(pedido)['10.1.0.2']
        self.assertIn(b'\x1dv0', datos)

    def test_la_comanda_de_la_carne_no_lleva_las_guarniciones_ni_cambia(self):
        pedido, _ = self.plato(500, [self.papas])
        with override_settings(COMANDA_GRAFICA=False):
            texto = self.impresas(pedido)['10.1.0.1']
        self.assertIn(b'500 g Punta trasera', texto)
        self.assertNotIn(b'Papas', texto)

    def test_en_una_misma_impresora_la_guarnicion_sale_dentro_de_su_plato_con_la_cantidad(self):
        # Carnes y guarniciones comparten impresora: el plato armado conserva su bloque "PLATO N".
        VGCategoriaProducto.objects.filter(pk=self.guarniciones.pk).update(ip_impresora='10.1.0.1')
        pedido = VGPedido.objects.create(usuario=self.mesero, tipo_pedido='llevar', estado='pendiente', subtotal='10', total='10')
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=self.punta, cantidad=1, precio_unitario='6.50', peso_gramos=500, estado='pendiente', grupo_armado=1,
        )
        VGDetallePedidoOpcion.objects.create(detalle_pedido=detalle, grupo_nombre='Guarnición', grupo=self.grupo, producto=self.papas, precio_unitario=0)
        items = [item for item in self.items(pedido) if item['destino'] == ('10.1.0.1', 9100)]
        bloque = _bloques_comanda(items)[0]
        self.assertTrue(bloque['plato'].startswith('PLATO 1'))
        self.assertEqual(len(bloque['lineas']), 1)
        plato = bloque['lineas'][0]
        self.assertEqual((plato['cantidad'], plato['nombre']), ('500 g', 'Punta trasera'))
        self.assertEqual([(h['cantidad'], h['nombre']) for h in plato['hijas']], [('200 g', 'Papas fritas')])
        with override_settings(COMANDA_GRAFICA=False):
            ticket = _build_ticket_bytes(pedido, [self.carnes, self.guarniciones], items)
        self.assertIn(b'200 g Papas fritas', ticket)


class DisenoDeLaComandaTests(PorcionesBase):
    """La carne con sus gramos y, debajo con sangría, sus guarniciones."""

    def lineas(self, pedido, categoria=None):
        items = [i for i in self.items(pedido) if categoria is None or i['categoria'].id == categoria.id]
        return [linea for bloque in _bloques_comanda(items) for linea in bloque['lineas']]

    def test_en_la_misma_impresora_cada_carne_lleva_sus_guarniciones_debajo(self):
        VGCategoriaProducto.objects.filter(pk=self.guarniciones.pk).update(ip_impresora='10.1.0.1')
        pedido, _ = self.plato(500, [self.papas, self.ensalada])
        self.plato(1000, [self.papas], pedido=pedido)
        lineas = self.lineas(pedido)
        self.assertEqual(
            [(l['cantidad'], l['nombre'], [(h['cantidad'], h['nombre']) for h in l['hijas']]) for l in lineas],
            [('500 g', 'Punta trasera', [('200 g', 'Papas fritas'), ('200 g', 'Ensalada')]),
             ('1000 g', 'Punta trasera', [('360 g', 'Papas fritas')])],
        )

    def test_las_guarniciones_en_su_propia_impresora_llevan_el_plato_como_encabezado(self):
        pedido, _ = self.plato(500, [self.papas])
        (linea,) = self.lineas(pedido, self.guarniciones)
        self.assertTrue(linea['encabezado'])
        self.assertEqual(linea['nombre'], 'Punta trasera 500 g')
        self.assertEqual([(h['cantidad'], h['nombre']) for h in linea['hijas']], [('200 g', 'Papas fritas')])

    def test_dos_cortes_de_distinto_peso_no_se_juntan_y_conservan_sus_gramos(self):
        pedido, _ = self.plato(350, [])
        self.plato(500, [], pedido=pedido)
        self.assertEqual([(l['cantidad'], l['nombre']) for l in self.lineas(pedido, self.carnes)],
                         [('350 g', 'Punta trasera'), ('500 g', 'Punta trasera')])

    def test_dos_cortes_iguales_tampoco_se_juntan(self):
        pedido, _ = self.plato(500, [self.papas])
        self.plato(500, [self.ensalada], pedido=pedido)
        lineas = self.lineas(pedido, self.carnes)
        self.assertEqual([l['cantidad'] for l in lineas], ['500 g', '500 g'])

    def test_un_corte_de_dos_platos_en_una_linea_lo_dice(self):
        pedido, _ = self.plato(500, [], cantidad=2)
        self.assertEqual(self.lineas(pedido, self.carnes)[0]['cantidad'], '2x 500 g')

    def test_lo_que_no_es_por_peso_ni_tiene_guarniciones_sigue_consolidandose(self):
        yuca = VGProducto.objects.create(nombre='Yuca frita', categoria=self.guarniciones, precio_venta='3', disponible=True)
        pedido = VGPedido.objects.create(usuario=self.mesero, tipo_pedido='llevar', estado='pendiente', subtotal='9', total='9')
        for _ in range(3):
            VGDetallePedido.objects.create(pedido=pedido, producto=yuca, cantidad=1, precio_unitario='3', estado='pendiente')
        lineas = self.lineas(pedido, self.guarniciones)
        self.assertEqual([(l['cantidad'], l['nombre']) for l in lineas], [('3x', 'Yuca frita')])

    def test_el_dibujo_con_guarniciones_debajo_funciona(self):
        from sevens.comanda_grafica import dibujar_comanda
        pedido, _ = self.plato(500, [self.papas, self.ensalada, self.patacon])
        datos = {
            'estacion': 'COCINA', 'titulo': 'MESA 7', 'pedido': pedido.id, 'hora': '16/11 18:13', 'cliente': 'Ana', 'mesero': 'mario',
            'bloques': [{'plato': None, 'lineas': self.lineas(pedido)}],
        }
        self.assertEqual(dibujar_comanda(datos).width, 576)
