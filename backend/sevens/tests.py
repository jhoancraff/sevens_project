import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from sevens.models import (
    VGAjusteInventario,
    VGCategoriaGasto,
    VGCategoriaProducto,
    VGCierreInventario,
    VGCliente,
    VGCompra,
    VGCompraBorrador,
    VGDetalleAjusteInventario,
    VGDetalleCompra,
    VGDetalleCompraBorrador,
    VGDetallePedido,
    VGDetallePedidoAdicional,
    VGDetallePedidoOpcion,
    VGFactura,
    VGGasto,
    VGGrupoOpcionProducto,
    VGGrupoOpcionRacionPorTamano,
    VGIngrediente,
    VGIngresoExtra,
    VGMetodoPago,
    VGMovimientoInventario,
    VGNotaEntrega,
    VGPedido,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
    VGRecetaProducto,
    VGRol,
    VGTasaCambio,
    VGTransferenciaCuenta,
    VGUsuario,
)
from sevens.api_views import _importar_ingredientes, _load_preparation_cost_map, _preview_ingrediente_row
from sevens.unit_rescale import rescale_legacy_units


class LoginViewTests(TestCase):
    def test_login_creates_session_for_valid_user(self):
        mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        VGUsuario.objects.create_user(
            username='chef',
            password='restaurante123',
            cedula='12345678',
            email='chef@sevens.test',
            id_role=mesero_role,
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'chef',
            'password': 'restaurante123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'chef')
        self.assertEqual(response.json()['user']['role'], 'Mesero')
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_accepts_email_identifier(self):
        VGUsuario.objects.create_user(
            username='meseroemail',
            password='claveSegura789',
            cedula='12345670',
            email='mesero.email@sevens.test',
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'mesero.email@sevens.test',
            'password': 'claveSegura789',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'meseroemail')

    def test_login_accepts_case_insensitive_username(self):
        VGUsuario.objects.create_user(
            username='Jhoan',
            password='claveJhoan789',
            cedula='12345671',
            email='jhoan@sevens.test',
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'jhoan',
            'password': 'claveJhoan789',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'Jhoan')

    def test_session_status_returns_authenticated_user_after_login(self):
        VGUsuario.objects.create_user(
            username='mesero',
            password='claveSegura123',
            cedula='12345679',
            email='mesero@sevens.test',
        )

        self.client.post('/api/auth/login/', {
            'username': 'mesero',
            'password': 'claveSegura123',
        })

        response = self.client.get('/api/auth/status/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'mesero')

    def test_logout_clears_session_and_status(self):
        VGUsuario.objects.create_user(
            username='admincocina',
            password='claveAdmin456',
            cedula='12345680',
            email='admin@sevens.test',
        )

        self.client.post('/api/auth/login/', {
            'username': 'admincocina',
            'password': 'claveAdmin456',
        })

        logout_response = self.client.post('/api/auth/logout/')
        status_response = self.client.get('/api/auth/status/')

        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(logout_response.json()['authenticated'])
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.json()['authenticated'])
        self.assertNotIn('_auth_user_id', self.client.session)


class AdminCatalogApiTests(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='admincatalogo',
            password='claveAdmin123',
            cedula='99999999',
            email='admincatalogo@sevens.test',
            id_role=self.admin_role,
        )
        self.client.force_login(self.admin)

    def test_admin_catalog_endpoint_persists_inventory_recipes_and_beverages(self):
        inventory_payload = {
            'tipo': 'inventario',
            'nombre': 'Tomate',
            'ingrediente_id': '',
            'cantidad': '5.5',
            'unidad': 'g',
            'proveedor': 'Proveedor Uno',
            'stock_minimo': '1.0',
            # El endpoint deriva costo_unitario de precio_total/cantidad (nunca
            # lee un costo_unitario recibido) -- 12.375 / 5.5 = 2.25.
            'precio_total': '12.375',
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(inventory_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        ingredient = VGIngrediente.objects.get(nombre='Tomate')
        self.assertEqual(ingredient.stock_actual, 5.5)
        self.assertEqual(ingredient.unidad_medida, 'g')
        self.assertEqual(ingredient.ultimo_proveedor, 'Proveedor Uno')
        self.assertEqual(ingredient.stock_minimo, Decimal('1.0'))
        self.assertEqual(ingredient.costo_unitario, Decimal('2.25'))
        compra = VGCompra.objects.get(proveedor_nombre='Proveedor Uno')
        detalle = VGDetalleCompra.objects.get(compra=compra, ingrediente=ingredient)
        movimiento = VGMovimientoInventario.objects.get(ingrediente=ingredient, id_referencia=compra.id)
        self.assertEqual(compra.estado, 'recibido')
        self.assertEqual(detalle.cantidad, Decimal('5.5'))
        self.assertEqual(movimiento.tipo_movimiento, 'entrada')

        recipe_payload = {
            'tipo': 'recetas',
            'nombre': 'Salsa roja',
            'rendimiento_cantidad': '1.0',
            'rendimiento_unidad': 'l',
            'componentes': [
                {'tipo': 'ingrediente', 'nombre': 'Tomate', 'cantidad': '0.800'},
                {'tipo': 'sub_preparacion', 'nombre': 'Base de tomate', 'cantidad': '0.200'},
            ],
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(recipe_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        preparation = VGPreparacion.objects.get(nombre='Salsa roja')
        self.assertEqual(preparation.rendimiento_cantidad, 1.0)
        self.assertEqual(preparation.componentes.count(), 2)
        self.assertTrue(VGRecetaPreparacion.objects.filter(preparacion=preparation, ingrediente=ingredient).exists())
        sub_preparation = VGPreparacion.objects.get(nombre='Base de tomate')
        self.assertTrue(VGRecetaPreparacion.objects.filter(preparacion=preparation, sub_preparacion=sub_preparation).exists())

        beverage_payload = {
            'tipo': 'bebidas',
            'nombre': 'Jugo de naranja',
            'categoria': 'Jugos',
            'precio': '3.80',
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(beverage_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        category = VGCategoriaProducto.objects.get(nombre='Jugos')
        beverage = VGProducto.objects.get(nombre='Jugo de naranja')
        self.assertEqual(beverage.categoria, category)
        self.assertEqual(beverage.precio_venta, Decimal('3.80'))

        response = self.client.get('/api/admin/catalogo/')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['nombre'] == 'Tomate' for item in payload['inventory']))
        self.assertTrue(any(item['nombre'] == 'Salsa roja' for item in payload['recipes']))
        self.assertTrue(any(item['nombre'] == 'Jugo de naranja' for item in payload['beverages']))

    def test_subrecipe_cost_uses_price_fields_when_ingredient_cost_is_stale_zero(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Queso con costo desincronizado', unidad_medida='g', costo_unitario='0',
            contenido_envase='1000', peso_real='800', precio_compra='400',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa con queso desincronizado', rendimiento_cantidad='1000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(
            preparacion=preparation, ingrediente=ingredient, cantidad_requerida='200',
        )

        costs = _load_preparation_cost_map()[preparation.id]

        self.assertEqual(costs['costo_total'], Decimal('100.000000'))
        self.assertEqual(costs['costo_unitario'], Decimal('0.100000'))

        response = self.client.get('/api/admin/catalogo/')
        self.assertEqual(response.status_code, 200)
        inventory_item = next(item for item in response.json()['inventory'] if item['id'] == ingredient.id)
        self.assertEqual(Decimal(inventory_item['costo_unitario']), Decimal('0.500000'))

    def test_admin_catalog_endpoint_updates_existing_records(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Cebolla',
            unidad_medida='g',
            stock_actual='2.00',
            stock_minimo='1.00',
            costo_unitario='0.50',
            ultimo_proveedor='Inicial',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa base',
            rendimiento_cantidad='1.000',
            rendimiento_unidad='ml',
        )
        category = VGCategoriaProducto.objects.create(nombre='Jugos')
        beverage = VGProducto.objects.create(
            nombre='Jugo de piña',
            categoria=category,
            precio_venta='2.50',
            disponible=True,
        )

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'inventario',
                'id': ingredient.id,
                'ingrediente_id': ingredient.id,
                'nombre': 'Cebolla',
                'cantidad': '7.25',
                'unidad': 'g',
                'proveedor': 'Proveedor Editado',
                'stock_minimo': '1.50',
                # 6.525 / 7.25 = 0.90 (el endpoint deriva costo_unitario de precio_total/cantidad).
                'precio_total': '6.525',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('9.25'))
        self.assertEqual(ingredient.ultimo_proveedor, 'Proveedor Editado')
        self.assertEqual(ingredient.stock_minimo, Decimal('1.50'))
        self.assertEqual(ingredient.costo_unitario, Decimal('0.90'))
        self.assertTrue(VGCompra.objects.filter(proveedor_nombre='Proveedor Editado').exists())
        self.assertTrue(VGMovimientoInventario.objects.filter(ingrediente=ingredient, tipo_movimiento='entrada').exists())

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'recetas',
                'id': preparation.id,
                'nombre': 'Salsa base',
                'rendimiento_cantidad': '2.500',
                'rendimiento_unidad': 'l',
                'componentes': [],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        preparation.refresh_from_db()
        self.assertEqual(preparation.rendimiento_cantidad, Decimal('2.500'))

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'bebidas',
                'id': beverage.id,
                'nombre': 'Jugo de piña',
                'categoria': 'Jugos',
                'precio': '4.20',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        beverage.refresh_from_db()
        self.assertEqual(beverage.precio_venta, Decimal('4.20'))

    def test_admin_catalog_endpoint_deletes_existing_records(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Pimenton',
            unidad_medida='g',
            stock_actual='1.00',
            stock_minimo='1.00',
            costo_unitario='1.00',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa temporal',
            rendimiento_cantidad='1.000',
            rendimiento_unidad='ml',
        )
        category = VGCategoriaProducto.objects.create(nombre='Jugos')
        beverage = VGProducto.objects.create(
            nombre='Jugo de mango',
            categoria=category,
            precio_venta='2.50',
            disponible=True,
        )

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({'tipo': 'eliminar_inventario', 'id': ingredient.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VGIngrediente.objects.filter(pk=ingredient.id).exists())

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({'tipo': 'eliminar_receta', 'id': preparation.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VGPreparacion.objects.filter(pk=preparation.id).exists())

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({'tipo': 'eliminar_bebida', 'id': beverage.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VGProducto.objects.filter(pk=beverage.id).exists())

    def test_crear_ingrediente_requiere_precio_compra(self):
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'crear_ingrediente',
                'nombre': 'Aji dulce',
                'unidad': 'g',
                'contenido_envase': '500',
                'peso_real': '450',
                # precio_compra ausente a propósito.
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VGIngrediente.objects.filter(nombre='Aji dulce').exists())

    def test_crear_ingrediente_deriva_costo_unitario_de_precio_compra(self):
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'crear_ingrediente',
                'nombre': 'Costillas',
                'unidad': 'g',
                'contenido_envase': '1000',
                'peso_real': '850',
                'precio_compra': '4250',
                # Un costo_unitario mandado por el cliente se debe ignorar por completo.
                'costo_unitario': '999',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        ingredient = VGIngrediente.objects.get(nombre='Costillas')
        self.assertEqual(ingredient.precio_compra, Decimal('4250.00'))
        self.assertEqual(ingredient.costo_unitario, Decimal('5.000000'))

    def test_actualizar_ingrediente_recalcula_al_completar_triple(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Queso amarillo',
            unidad_medida='g',
            stock_actual='0',
            costo_unitario='0.30',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'actualizar_ingrediente',
                'id': ingredient.id,
                'nombre': 'Queso amarillo',
                'unidad': 'g',
                'contenido_envase': '2000',
                'peso_real': '2000',
                'precio_compra': '900',
                # También se ignora al completar el trío.
                'costo_unitario': '0.10',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.costo_unitario, Decimal('0.450000'))

    def test_actualizar_ingrediente_legacy_sin_precio_compra_respeta_costo_manual(self):
        """
        Regresión: el frontend real siempre manda contenido_envase/peso_real (con su
        valor guardado) pero puede mandar precio_compra vacío si el ingrediente es de
        antes de este campo. Editar otro dato (ej. proveedor) sin tocar precio de compra
        NO debe bloquear el guardado ni recalcular el costo.
        """
        ingredient = VGIngrediente.objects.create(
            nombre='Yuca',
            unidad_medida='g',
            stock_actual='0',
            costo_unitario='0.02',
            contenido_envase='1000',
            peso_real='1000',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'actualizar_ingrediente',
                'id': ingredient.id,
                'nombre': 'Yuca',
                'unidad': 'g',
                'proveedor': 'Agromercado Andino',
                'contenido_envase': '1000',
                'peso_real': '1000',
                'precio_compra': None,
                'costo_unitario': '0.02',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.ultimo_proveedor, 'Agromercado Andino')
        self.assertEqual(ingredient.costo_unitario, Decimal('0.02'))
        self.assertIsNone(ingredient.precio_compra)

    def test_actualizar_ingrediente_envase_peso_parcial_rechazada(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Pimienta blanca', unidad_medida='g', stock_actual='0', costo_unitario='0.05',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'actualizar_ingrediente',
                'id': ingredient.id,
                'nombre': 'Pimienta blanca',
                'unidad': 'g',
                'contenido_envase': '500',
                # peso_real ausente: sigue siendo un par obligatorio, sin cambios.
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        ingredient.refresh_from_db()
        self.assertIsNone(ingredient.contenido_envase)

    def test_ingreso_administrativo_no_desincroniza_costo_unitario_existente(self):
        """
        Ver _costo_unitario_por_compra vs. la división simple: reponer stock desde
        "Ingreso administrativo" (tipo='inventario') sobre un ingrediente que ya tiene su
        trío completo debe respetar la merma, no pisarlo con precio_total/cantidad.
        """
        ingredient = VGIngrediente.objects.create(
            nombre='Punta trasera QA',
            unidad_medida='g',
            stock_actual='0',
            costo_unitario='5.00',
            contenido_envase='1000',
            peso_real='850',
            precio_compra='4250',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'inventario',
                'ingrediente_id': ingredient.id,
                'nombre': 'Punta trasera QA',
                'cantidad': '2000',
                'unidad': 'g',
                'precio_total': '8500',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        # Naive: 8500/2000 = 4.25. Ajustado por merma (850/1000): 8500/(2000*0.85) = 5.00.
        self.assertEqual(ingredient.costo_unitario, Decimal('5.000000'))


class ImportarIngredientesExcelTests(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='adminimportexcel',
            password='claveAdmin123',
            cedula='99999998',
            email='adminimportexcel@sevens.test',
            id_role=self.admin_role,
        )

    def test_preview_ingrediente_nuevo_sin_trio_es_error(self):
        row = {
            'fila': 2, 'nombre': 'Chorizo', 'unidad': 'g', 'cantidad': '5000',
            'precio_total': '', 'contenido_envase': '', 'peso_real': '', 'precio_compra': '',
        }
        resultado = _preview_ingrediente_row(row)
        self.assertEqual(resultado['accion'], 'error')

    def test_importar_ingrediente_nuevo_sin_trio_no_crea_nada(self):
        resumen = _importar_ingredientes(
            [{'nombre': 'Chorizo', 'unidad': 'g', 'cantidad': '5000'}],
            self.admin,
        )
        self.assertEqual(resumen['creados'], 0)
        self.assertEqual(len(resumen['errores']), 1)
        self.assertFalse(VGIngrediente.objects.filter(nombre='Chorizo').exists())

    def test_importar_ingrediente_nuevo_con_trio_crea_y_deriva_costo(self):
        resumen = _importar_ingredientes(
            [{
                'nombre': 'Chorizo', 'unidad': 'g', 'cantidad': '5000',
                'contenido_envase': '1000', 'peso_real': '1000', 'precio_compra': '4500',
            }],
            self.admin,
        )
        self.assertEqual(resumen['creados'], 1)
        self.assertEqual(resumen['errores'], [])
        ingredient = VGIngrediente.objects.get(nombre='Chorizo')
        self.assertEqual(ingredient.stock_actual, Decimal('5000'))
        self.assertEqual(ingredient.precio_compra, Decimal('4500.00'))
        self.assertEqual(ingredient.costo_unitario, Decimal('4.500000'))

    def test_importar_ingrediente_existente_actualiza_precio_sin_tocar_stock(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Papeleta', unidad_medida='g', stock_actual='5000', costo_unitario='0.01',
        )
        movimientos_antes = VGMovimientoInventario.objects.filter(ingrediente=ingredient).count()

        resumen = _importar_ingredientes(
            [{
                'nombre': 'Papeleta', 'unidad': 'g', 'cantidad': '',
                'contenido_envase': '1000', 'peso_real': '950', 'precio_compra': '950',
            }],
            self.admin,
        )
        self.assertEqual(resumen['errores'], [])
        self.assertEqual(resumen['actualizados'], 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('5000'))
        self.assertEqual(ingredient.contenido_envase, Decimal('1000'))
        self.assertEqual(ingredient.peso_real, Decimal('950'))
        self.assertEqual(ingredient.precio_compra, Decimal('950.00'))
        self.assertEqual(ingredient.costo_unitario, Decimal('1.000000'))
        self.assertEqual(
            VGMovimientoInventario.objects.filter(ingrediente=ingredient).count(),
            movimientos_antes,
        )

    def test_importar_ingrediente_existente_trio_parcial_da_error(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Cilantro', unidad_medida='g', stock_actual='500', costo_unitario='0.02',
        )
        resumen = _importar_ingredientes(
            [{'nombre': 'Cilantro', 'unidad': 'g', 'cantidad': '', 'peso_real': '900'}],
            self.admin,
        )
        self.assertEqual(resumen['actualizados'], 0)
        self.assertEqual(len(resumen['errores']), 1)
        ingredient.refresh_from_db()
        self.assertIsNone(ingredient.peso_real)
        self.assertEqual(ingredient.stock_actual, Decimal('500'))

    def test_importar_ingrediente_existente_suma_cantidad_al_stock(self):
        # -5 + 10 = 5, no 10: "cantidad" es lo que la carga suma, nunca el valor final.
        ingredient = VGIngrediente.objects.create(
            nombre='Cerveza', unidad_medida='unidad', stock_actual='-5', costo_unitario='1.00',
        )
        resumen = _importar_ingredientes(
            [{'nombre': 'Cerveza', 'unidad': 'unidad', 'cantidad': '10'}],
            self.admin,
        )
        self.assertEqual(resumen['errores'], [])
        self.assertEqual(resumen['actualizados'], 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('5'))
        movimiento = VGMovimientoInventario.objects.filter(ingrediente=ingredient).latest('fecha_movimiento')
        self.assertEqual(movimiento.cantidad, Decimal('10'))
        self.assertEqual(movimiento.tipo_movimiento, 'entrada')

    def test_importar_ingrediente_existente_cantidad_negativa_resta_del_stock(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Ron', unidad_medida='unidad', stock_actual='10', costo_unitario='1.00',
        )
        resumen = _importar_ingredientes(
            [{'nombre': 'Ron', 'unidad': 'unidad', 'cantidad': '-3'}],
            self.admin,
        )
        self.assertEqual(resumen['errores'], [])
        self.assertEqual(resumen['actualizados'], 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('7'))
        movimiento = VGMovimientoInventario.objects.filter(ingrediente=ingredient).latest('fecha_movimiento')
        self.assertEqual(movimiento.cantidad, Decimal('-3'))
        self.assertEqual(movimiento.tipo_movimiento, 'ajuste')


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.analista_role, _ = VGRol.objects.get_or_create(nombre_role='Analista')
        self.admin_user = VGUsuario.objects.create_user(
            username='adminusuarios',
            password='claveAdmin999',
            cedula='90000001',
            email='adminusuarios@sevens.test',
            id_role=self.admin_role,
            is_staff=True,
        )
        self.target_user = VGUsuario.objects.create_user(
            username='meseroexistente',
            password='claveMesero111',
            cedula='90000002',
            email='mesero@sevens.test',
            id_role=self.mesero_role,
        )

    def test_admin_users_endpoint_requires_admin_role(self):
        outsider = VGUsuario.objects.create_user(
            username='sinpermiso',
            password='claveSinPermiso1',
            cedula='90000003',
            email='sinpermiso@sevens.test',
            id_role=self.mesero_role,
        )
        self.client.force_login(outsider)

        response = self.client.get('/api/admin/usuarios/')

        self.assertEqual(response.status_code, 401)

    def test_admin_users_endpoint_lists_roles_and_users(self):
        self.client.force_login(self.admin_user)

        response = self.client.get('/api/admin/usuarios/')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(role['nombre_role'] == 'Administrador' for role in payload['roles']))
        self.assertTrue(any(user['username'] == 'meseroexistente' for user in payload['users']))

    def test_admin_users_endpoint_creates_updates_and_deletes_user(self):
        self.client.force_login(self.admin_user)

        create_response = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({
                'action': 'create',
                'username': 'nuevoanalista',
                'password': 'ClaveNueva123',
                'first_name': 'Ana',
                'last_name': 'Lista',
                'email': 'ana@sevens.test',
                'cedula': '90000004',
                'telefono': '04120000000',
                'fecha_nacimiento': '1995-01-10',
                'role_id': self.analista_role.id,
                'is_active': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 201)
        created_user = VGUsuario.objects.get(username='nuevoanalista')
        self.assertTrue(created_user.check_password('ClaveNueva123'))
        self.assertEqual(created_user.id_role, self.analista_role)

        update_response = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({
                'action': 'update',
                'id': created_user.id,
                'username': 'nuevoanalista',
                'password': 'ClaveActualizada456',
                'first_name': 'Ana Maria',
                'last_name': 'Lista',
                'email': 'anamaria@sevens.test',
                'cedula': '90000004',
                'telefono': '04125555555',
                'fecha_nacimiento': '1995-01-12',
                'role_id': self.admin_role.id,
                'is_active': False,
            }),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        created_user.refresh_from_db()
        self.assertEqual(created_user.first_name, 'Ana Maria')
        self.assertEqual(created_user.email, 'anamaria@sevens.test')
        self.assertEqual(created_user.id_role, self.admin_role)
        self.assertTrue(created_user.is_staff)
        self.assertFalse(created_user.is_active)
        self.assertTrue(created_user.check_password('ClaveActualizada456'))

        delete_response = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({'action': 'delete', 'id': created_user.id}),
            content_type='application/json',
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(VGUsuario.objects.filter(pk=created_user.id).exists())


class KitchenOrdersApiTests(TestCase):
    def setUp(self):
        self.mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.user = VGUsuario.objects.create_user(
            username='cocinero',
            password='claveCocina123',
            cedula='22345680',
            email='cocina@sevens.test',
            id_role=self.mesero_role,
        )
        self.client.force_login(self.user)

        self.category = VGCategoriaProducto.objects.create(nombre='Platos')
        self.product = VGProducto.objects.create(
            nombre='Pabellon criollo',
            categoria=self.category,
            precio_venta='11.50',
            disponible=True,
        )

    def _create_order(self, estado='pendiente'):
        pedido = VGPedido.objects.create(
            usuario=self.user,
            tipo_pedido='local',
            estado=estado,
            subtotal='11.50',
            total='11.50',
        )
        VGDetallePedido.objects.create(
            pedido=pedido,
            producto=self.product,
            cantidad=1,
            precio_unitario='11.50',
            estado='pendiente',
            notas='Sin cebolla',
        )
        return pedido

    def test_kitchen_orders_endpoint_returns_active_orders(self):
        pedido = self._create_order(estado='pendiente')

        response = self.client.get('/api/pedidos/cocina/?estado=activos')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['orders']), 1)
        self.assertEqual(payload['orders'][0]['id'], pedido.id)
        self.assertEqual(payload['orders'][0]['items'][0]['producto'], 'Pabellon criollo')

    def test_kitchen_orders_counts_use_full_queryset_not_limit(self):
        self._create_order(estado='pendiente')
        self._create_order(estado='pendiente')
        self._create_order(estado='en_preparacion')

        response = self.client.get('/api/pedidos/cocina/?estado=activos&limit=1')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['orders']), 1)
        self.assertEqual(payload['counts']['pendiente'], 2)
        self.assertEqual(payload['counts']['en_preparacion'], 1)

    def test_kitchen_order_status_update_changes_order_and_items(self):
        pedido = self._create_order(estado='pendiente')

        response = self.client.post(
            f'/api/pedidos/{pedido.id}/estado/',
            data='{"estado": "en_preparacion"}',
            content_type='application/json',
        )

        pedido.refresh_from_db()
        detalle = pedido.detalles.first()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pedido.estado, 'en_preparacion')
        self.assertEqual(detalle.estado, 'en_preparacion')

    def test_kitchen_order_status_rejects_invalid_transition(self):
        pedido = self._create_order(estado='pendiente')

        response = self.client.post(
            f'/api/pedidos/{pedido.id}/estado/',
            data='{"estado": "entregado"}',
            content_type='application/json',
        )

        pedido.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(pedido.estado, 'pendiente')

    @patch('sevens.api_views._notify_cocina_event')
    def test_create_order_triggers_notification_regardless_of_role(self, notify_mock):
        # pedido_create_view llama a _notify_cocina_event('NUEVA_COMANDAS', ...)
        # sin chequeo de rol -- cocina necesita enterarse de CUALQUIER pedido
        # nuevo, sin importar quién lo registró.
        payload = {
            'tipo_pedido': 'local',
            'cliente_nombre': 'Cliente de prueba',
            'items': [
                {
                    'product_id': self.product.id,
                    'cantidad': 1,
                    'notas': '',
                },
            ],
        }

        response = self.client.post(
            '/api/pedidos/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(notify_mock.called)

        notify_mock.reset_mock()
        self.user.id_role = self.admin_role
        self.user.save(update_fields=['id_role'])

        response = self.client.post(
            '/api/pedidos/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(notify_mock.called)


class PedidoCobroInventoryDeductionTests(TestCase):
    """
    Al cobrar un pedido, el inventario debe descontarse según la receta de cada producto:
    ingredientes directos, subrecetas prorrateadas por rendimiento (incluyendo subrecetas
    anidadas), productos vinculados a una receta/subreceta, y adicionales.
    """

    def setUp(self):
        self.cajero_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.user = VGUsuario.objects.create_user(
            username='cajera',
            password='claveCajera123',
            cedula='33345680',
            email='cajera@sevens.test',
            id_role=self.cajero_role,
        )
        self.client.force_login(self.user)
        self.category = VGCategoriaProducto.objects.create(nombre='Platos')
        self.metodo_pago, _ = VGMetodoPago.objects.get_or_create(
            nombre='Efectivo', defaults={'es_efectivo': True},
        )

    def _cobrar(self, pedido_ids):
        return self.client.post(
            '/api/pedidos/cobro/',
            data=json.dumps({'pedido_ids': pedido_ids, 'metodo_pago_id': self.metodo_pago.id}),
            content_type='application/json',
        )

    def test_cobro_deducts_direct_ingredient_from_stock(self):
        arroz = VGIngrediente.objects.create(
            nombre='Arroz', unidad_medida='g', stock_actual='5000', costo_unitario='0.01',
        )
        plato = VGProducto.objects.create(
            nombre='Arroz blanco', categoria=self.category, precio_venta='3.00', disponible=True,
        )
        VGRecetaProducto.objects.create(producto=plato, ingrediente=arroz, cantidad_requerida='150.000')

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='6.00', total='6.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=2, precio_unitario='3.00', estado='entregado',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        arroz.refresh_from_db()
        # 150g x 2 platos = 300g descontados de 5000g
        self.assertEqual(arroz.stock_actual, Decimal('4700.00'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'pagado')
        movimiento = VGMovimientoInventario.objects.get(ingrediente=arroz, id_referencia=pedido.id)
        self.assertEqual(movimiento.tipo_movimiento, 'salida')
        self.assertEqual(movimiento.cantidad, Decimal('300.00'))

    def test_cobro_prorates_subreceta_by_rendimiento_including_nested(self):
        tomate = VGIngrediente.objects.create(
            nombre='Tomate', unidad_medida='g', stock_actual='10000', costo_unitario='0.01',
        )
        base = VGPreparacion.objects.create(
            nombre='Base de tomate', rendimiento_cantidad='500.000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(preparacion=base, ingrediente=tomate, cantidad_requerida='500.000')

        salsa = VGPreparacion.objects.create(
            nombre='Salsa de la casa', rendimiento_cantidad='1000.000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(preparacion=salsa, sub_preparacion=base, cantidad_requerida='400.000')

        plato = VGProducto.objects.create(
            nombre='Pasta con salsa', categoria=self.category, precio_venta='8.00', disponible=True,
        )
        # El plato lleva 200g de una salsa cuyo lote rinde 1000g (usa 1/5 del lote).
        VGRecetaProducto.objects.create(producto=plato, preparacion=salsa, cantidad_requerida='200.000')

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='8.00', total='8.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='8.00', estado='entregado',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        tomate.refresh_from_db()
        # 200g de salsa -> 1/5 del lote de 1000g -> 1/5 de 400g de base -> 80g de base
        # 80g de base -> 80/500 del lote de base -> 16% de 500g de tomate -> 80g de tomate
        self.assertEqual(tomate.stock_actual, Decimal('9920.00'))

    def test_cobro_deducts_ingredients_for_producto_vinculado_a_receta(self):
        pollo = VGIngrediente.objects.create(
            nombre='Pollo', unidad_medida='g', stock_actual='3000', costo_unitario='0.02',
        )
        recetas_category = VGCategoriaProducto.objects.get_or_create(nombre='Recetas')[0]
        receta_maestra = VGProducto.objects.create(
            nombre='Pollo a la plancha (receta)', categoria=recetas_category, precio_venta='0', disponible=False,
        )
        VGRecetaProducto.objects.create(producto=receta_maestra, ingrediente=pollo, cantidad_requerida='250.000')

        plato_vendible = VGProducto.objects.create(
            nombre='Pollo a la plancha', categoria=self.category, precio_venta='9.50', disponible=True,
            receta_vinculada=receta_maestra,
        )

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='9.50', total='9.50',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato_vendible, cantidad=1, precio_unitario='9.50', estado='entregado',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        pollo.refresh_from_db()
        self.assertEqual(pollo.stock_actual, Decimal('2750.00'))

    def test_cobro_deducts_ingredients_for_adicional(self):
        queso = VGIngrediente.objects.create(
            nombre='Queso', unidad_medida='g', stock_actual='2000', costo_unitario='0.03',
        )
        extra_queso = VGPreparacion.objects.create(
            nombre='Queso extra', rendimiento_cantidad='1000.000', rendimiento_unidad='g', es_adicional=True,
        )
        VGRecetaPreparacion.objects.create(preparacion=extra_queso, ingrediente=queso, cantidad_requerida='1000.000')

        plato = VGProducto.objects.create(
            nombre='Hamburguesa', categoria=self.category, precio_venta='6.00', disponible=True,
        )

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='6.00', total='6.00',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='6.00', estado='entregado',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=extra_queso, cantidad=100, precio_unitario='0.30',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        queso.refresh_from_db()
        # 100g de "queso extra" a partir de un lote 1:1 -> 100g de queso descontados.
        self.assertEqual(queso.stock_actual, Decimal('1900.00'))

    def test_cobro_deducts_chistorra_chorizo_adicionales_por_unidad_and_salsa(self):
        chistorra = VGIngrediente.objects.create(
            nombre='Chistorra', unidad_medida='unidad', stock_actual='10', costo_unitario='0.70',
        )
        chorizo = VGIngrediente.objects.create(
            nombre='Chorizo', unidad_medida='unidad', stock_actual='12', costo_unitario='0.90',
        )
        tomate = VGIngrediente.objects.create(
            nombre='Tomate', unidad_medida='g', stock_actual='4000', costo_unitario='0.02',
        )

        adicional_chistorra = VGPreparacion.objects.create(
            nombre='Chistorra extra', rendimiento_cantidad='1.000', rendimiento_unidad='unidad', es_adicional=True,
        )
        VGRecetaPreparacion.objects.create(
            preparacion=adicional_chistorra, ingrediente=chistorra, cantidad_requerida='1.000',
        )

        adicional_chorizo = VGPreparacion.objects.create(
            nombre='Chorizo extra', rendimiento_cantidad='1.000', rendimiento_unidad='unidad', es_adicional=True,
        )
        VGRecetaPreparacion.objects.create(
            preparacion=adicional_chorizo, ingrediente=chorizo, cantidad_requerida='1.000',
        )

        salsa = VGPreparacion.objects.create(
            nombre='Salsa de la casa', rendimiento_cantidad='1000.000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(
            preparacion=salsa, ingrediente=tomate, cantidad_requerida='300.000',
        )

        plato = VGProducto.objects.create(
            nombre='Plato con salsa', categoria=self.category, precio_venta='12.00', disponible=True,
        )
        VGRecetaProducto.objects.create(producto=plato, preparacion=salsa, cantidad_requerida='200.000')

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='12.00', total='12.00',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='12.00', estado='entregado',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=adicional_chistorra, cantidad=2, precio_unitario='1.40',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=adicional_chorizo, cantidad=3, precio_unitario='2.40',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)

        chistorra.refresh_from_db()
        chorizo.refresh_from_db()
        tomate.refresh_from_db()

        # 2 chistorra extra => 2 unidades; 3 chorizo extra => 3 unidades; la salsa usa 20% del lote de tomate.
        self.assertEqual(chistorra.stock_actual, Decimal('8.00'))
        self.assertEqual(chorizo.stock_actual, Decimal('9.00'))
        self.assertEqual(tomate.stock_actual, Decimal('3940.00'))


class TablaRacionesPorTamanoTests(TestCase):
    """
    Reproduce la tabla física completa acordada con el usuario para un plato de
    proteína a peso variable con 4 acompañantes dinámicos (3 vendidos por peso,
    1 por unidad), verificando el descuento de inventario real vía
    /api/pedidos/cobro/ (no solo la función de lookup por separado):

        Proteína   Papas fritas  Ensalada  Yuca    Patacón
        250g       120g          120g      150g    3 UND
        500g       120g          200g      200g    4 UND
        750g       180g          250g      300g    6 UND
        1000g      360g          350g      400g    8 UND
    """

    TABLA = {
        250: {'papas': Decimal('120'), 'ensalada': Decimal('120'), 'yuca': Decimal('150'), 'patacon': Decimal('3')},
        500: {'papas': Decimal('120'), 'ensalada': Decimal('200'), 'yuca': Decimal('200'), 'patacon': Decimal('4')},
        750: {'papas': Decimal('180'), 'ensalada': Decimal('250'), 'yuca': Decimal('300'), 'patacon': Decimal('6')},
        1000: {'papas': Decimal('360'), 'ensalada': Decimal('350'), 'yuca': Decimal('400'), 'patacon': Decimal('8')},
    }

    def setUp(self):
        self.cajero_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.user = VGUsuario.objects.create_user(
            username='cajera_raciones',
            password='claveCajera123',
            cedula='33345681',
            email='cajera_raciones@sevens.test',
            id_role=self.cajero_role,
        )
        self.client.force_login(self.user)
        self.metodo_pago, _ = VGMetodoPago.objects.get_or_create(
            nombre='Efectivo', defaults={'es_efectivo': True},
        )
        self.category_platos = VGCategoriaProducto.objects.create(nombre='Platos raciones')
        self.category_guarniciones = VGCategoriaProducto.objects.create(nombre='Guarniciones')

        # Un ingrediente crudo por acompañante, para poder aislar cada descuento.
        self.papa_ing = VGIngrediente.objects.create(
            nombre='Papa cruda', unidad_medida='g', stock_actual='1000000', costo_unitario='0.01',
        )
        self.lechuga_ing = VGIngrediente.objects.create(
            nombre='Lechuga y tomate', unidad_medida='g', stock_actual='1000000', costo_unitario='0.01',
        )
        self.yuca_ing = VGIngrediente.objects.create(
            nombre='Yuca cruda', unidad_medida='g', stock_actual='1000000', costo_unitario='0.01',
        )
        self.platano_ing = VGIngrediente.objects.create(
            nombre='Plátano verde', unidad_medida='unidad', stock_actual='1000', costo_unitario='0.20',
        )

        # Acompañantes con receta 1:1 (1000g de ingrediente por "1 unidad" del
        # producto vendido por peso == 1kg; 1 unidad de ingrediente por unidad
        # del producto vendido por unidad), para que la cantidad descontada sea
        # EXACTAMENTE la celda de la tabla, sin factores que compliquen la aserción.
        self.papas_fritas = VGProducto.objects.create(
            nombre='Papas fritas', categoria=self.category_guarniciones, precio_venta='0',
            disponible=True, venta_por_peso=True,
        )
        VGRecetaProducto.objects.create(
            producto=self.papas_fritas, ingrediente=self.papa_ing, cantidad_requerida='1000.000',
        )
        self.ensalada = VGProducto.objects.create(
            nombre='Ensalada', categoria=self.category_guarniciones, precio_venta='0',
            disponible=True, venta_por_peso=True,
        )
        VGRecetaProducto.objects.create(
            producto=self.ensalada, ingrediente=self.lechuga_ing, cantidad_requerida='1000.000',
        )
        self.yuca = VGProducto.objects.create(
            nombre='Yuca', categoria=self.category_guarniciones, precio_venta='0',
            disponible=True, venta_por_peso=True,
        )
        VGRecetaProducto.objects.create(
            producto=self.yuca, ingrediente=self.yuca_ing, cantidad_requerida='1000.000',
        )
        self.patacon = VGProducto.objects.create(
            nombre='Patacón', categoria=self.category_guarniciones, precio_venta='0',
            disponible=True, venta_por_peso=False,
        )
        VGRecetaProducto.objects.create(
            producto=self.patacon, ingrediente=self.platano_ing, cantidad_requerida='1.000',
        )

        # Plato principal a peso variable, SIN receta propia — así la única
        # deducción de inventario del pedido es la del acompañante elegido y
        # la aserción queda limpia.
        self.proteina = VGProducto.objects.create(
            nombre='Proteína', categoria=self.category_platos, precio_venta='0.02',
            disponible=True, venta_por_peso=True,
        )
        self.grupo = VGGrupoOpcionProducto.objects.create(
            producto=self.proteina, nombre='Acompañante',
            categoria_opciones=self.category_guarniciones,
        )

        for tramo, fila in self.TABLA.items():
            VGGrupoOpcionRacionPorTamano.objects.create(
                grupo=self.grupo, producto=self.papas_fritas, tramo_peso_gramos=tramo, cantidad=fila['papas'],
            )
            VGGrupoOpcionRacionPorTamano.objects.create(
                grupo=self.grupo, producto=self.ensalada, tramo_peso_gramos=tramo, cantidad=fila['ensalada'],
            )
            VGGrupoOpcionRacionPorTamano.objects.create(
                grupo=self.grupo, producto=self.yuca, tramo_peso_gramos=tramo, cantidad=fila['yuca'],
            )
            VGGrupoOpcionRacionPorTamano.objects.create(
                grupo=self.grupo, producto=self.patacon, tramo_peso_gramos=tramo, cantidad=fila['patacon'],
            )

    def _pedir_y_cobrar(self, peso_gramos, producto_acompanante, grupo=None):
        """Crea un pedido de 1 Proteína a `peso_gramos` con `producto_acompanante`
        de acompañante, lo cobra vía el endpoint real, y devuelve la respuesta."""
        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='0.02', total='0.02',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=self.proteina, cantidad=1, precio_unitario='0.02',
            estado='entregado', peso_gramos=str(peso_gramos),
        )
        VGDetallePedidoOpcion.objects.create(
            detalle_pedido=detalle, grupo_nombre='Acompañante', grupo=grupo or self.grupo,
            producto=producto_acompanante, precio_unitario='0',
        )
        response = self.client.post(
            '/api/pedidos/cobro/',
            data=json.dumps({'pedido_ids': [pedido.id], 'metodo_pago_id': self.metodo_pago.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_cada_tramo_exacto_descuenta_la_celda_exacta_de_la_tabla(self):
        casos = [
            (250, self.papas_fritas, self.papa_ing, Decimal('120')),
            (500, self.ensalada, self.lechuga_ing, Decimal('200')),
            (750, self.yuca, self.yuca_ing, Decimal('300')),
            (1000, self.patacon, self.platano_ing, Decimal('8')),
        ]
        for peso_gramos, producto, ingrediente, esperado in casos:
            with self.subTest(peso=peso_gramos, producto=producto.nombre):
                ingrediente.refresh_from_db()
                antes = ingrediente.stock_actual
                self._pedir_y_cobrar(peso_gramos, producto)
                ingrediente.refresh_from_db()
                self.assertEqual(antes - ingrediente.stock_actual, esperado)

    def test_peso_intermedio_usa_el_tramo_mas_cercano(self):
        # 600g está a 100g de 500 y a 150g de 750 -> el tramo más cercano es 500.
        self.papa_ing.refresh_from_db()
        antes = self.papa_ing.stock_actual
        self._pedir_y_cobrar(600, self.papas_fritas)
        self.papa_ing.refresh_from_db()
        self.assertEqual(antes - self.papa_ing.stock_actual, self.TABLA[500]['papas'])

    def test_peso_fuera_de_rango_por_debajo_usa_el_tramo_limite_mas_chico(self):
        self.yuca_ing.refresh_from_db()
        antes = self.yuca_ing.stock_actual
        self._pedir_y_cobrar(100, self.yuca)
        self.yuca_ing.refresh_from_db()
        self.assertEqual(antes - self.yuca_ing.stock_actual, self.TABLA[250]['yuca'])

    def test_peso_fuera_de_rango_por_encima_usa_el_tramo_limite_mas_grande(self):
        self.platano_ing.refresh_from_db()
        antes = self.platano_ing.stock_actual
        self._pedir_y_cobrar(5000, self.patacon)
        self.platano_ing.refresh_from_db()
        self.assertEqual(antes - self.platano_ing.stock_actual, self.TABLA[1000]['patacon'])

    def test_grupo_sin_tabla_configurada_sigue_el_comportamiento_de_siempre(self):
        """
        Retrocompatibilidad: un grupo/producto SIN ninguna fila en
        VGGrupoOpcionRacionPorTamano debe seguir funcionando exactamente igual
        que antes de este cambio — acá, escalando a la par del peso del plato
        principal (sin gramos_base_racion configurado tampoco).
        """
        arepa_ing = VGIngrediente.objects.create(
            nombre='Harina de maíz', unidad_medida='g', stock_actual='100000', costo_unitario='0.01',
        )
        arepa = VGProducto.objects.create(
            nombre='Arepa', categoria=self.category_guarniciones, precio_venta='0',
            disponible=True, venta_por_peso=True,
        )
        VGRecetaProducto.objects.create(producto=arepa, ingrediente=arepa_ing, cantidad_requerida='1000.000')

        # Grupo hermano, sin ninguna fila en VGGrupoOpcionRacionPorTamano.
        grupo_sin_tabla = VGGrupoOpcionProducto.objects.create(
            producto=self.proteina, nombre='Acompañante sin tabla',
            categoria_opciones=self.category_guarniciones,
        )

        arepa_ing.refresh_from_db()
        antes = arepa_ing.stock_actual
        self._pedir_y_cobrar(500, arepa, grupo=grupo_sin_tabla)
        arepa_ing.refresh_from_db()
        # Sin tabla ni gramos_base_racion: cantidad_platos = 1 x (500/1000) = 0.5 ->
        # 1000g de receta x 0.5 = 500g descontados (mismo cálculo que antes de este cambio).
        self.assertEqual(antes - arepa_ing.stock_actual, Decimal('500.00'))


class UnidadesMedidaTests(TestCase):
    """
    El negocio ya no maneja kg/l: el catálogo de unidades solo admite
    gramos/mililitros/unidad, los formularios que crean ingredientes lo
    validan, y los datos que ya existían en kg/l se reescalan correctamente
    (misma cantidad física, mismo dinero total) al pasar a g/ml — ver
    sevens/unit_rescale.py y la migración 0025_solo_gramos_ml_unidad.
    """

    def test_unidades_de_ingrediente_son_solo_gramos_mililitros_unidad(self):
        self.assertEqual(
            VGIngrediente.UNIDADES,
            [('g', 'Gramos'), ('ml', 'Mililitros'), ('unidad', 'Unidad')],
        )

    def test_crear_ingrediente_con_unidad_kg_es_rechazado(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        admin = VGUsuario.objects.create_superuser(
            username='adminunidades',
            password='claveAdmin123',
            cedula='88888888',
            email='adminunidades@sevens.test',
            id_role=admin_role,
        )
        self.client.force_login(admin)

        response = self.client.post(
            '/api/admin/compras/borrador/agregar/',
            data=json.dumps({
                'nombre': 'Ingrediente en kilos',
                'unidad': 'kg',
                'cantidad': '10',
                'precio_total': '20',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertIn('g, ml o unidad', payload['message'])
        self.assertFalse(VGIngrediente.objects.filter(nombre='Ingrediente en kilos').exists())

    def test_rescale_legacy_units_convierte_kg_y_litros_manteniendo_el_dinero(self):
        # Ingrediente en kg, con stock/costo, una compra histórica y una receta que lo usa.
        carne = VGIngrediente.objects.create(
            nombre='Carne (legacy kg)', unidad_medida='kg',
            stock_actual='100.00', stock_minimo='10.00', costo_unitario='5.0000',
        )
        compra = VGCompra.objects.create(proveedor_nombre='Frigorifico X')
        detalle_compra = VGDetalleCompra.objects.create(
            compra=compra, ingrediente=carne, cantidad='50.00', costo_unitario='4.0000',
        )
        borrador = VGCompraBorrador.objects.create()
        detalle_borrador = VGDetalleCompraBorrador.objects.create(
            borrador=borrador, ingrediente=carne, cantidad='20.00', precio_total='80.00',
        )
        category = VGCategoriaProducto.objects.create(nombre='Platos legacy')
        plato = VGProducto.objects.create(
            nombre='Bistec (legacy)', categoria=category, precio_venta='10.00', disponible=True,
        )
        receta_directa = VGRecetaProducto.objects.create(
            producto=plato, ingrediente=carne, cantidad_requerida='0.200',
        )

        # Subreceta en litros que también usa el ingrediente en kg, y un plato
        # que a su vez usa esa subreceta -- para probar la cascada de las dos
        # direcciones (por ingrediente Y por preparación) en un solo test.
        salsa = VGPreparacion.objects.create(
            nombre='Salsa (legacy l)', rendimiento_cantidad='2.000', rendimiento_unidad='l',
        )
        receta_salsa = VGRecetaPreparacion.objects.create(
            preparacion=salsa, ingrediente=carne, cantidad_requerida='0.500',
        )
        receta_plato_salsa = VGRecetaProducto.objects.create(
            producto=plato, preparacion=salsa, cantidad_requerida='0.300',
        )

        # Ingrediente que YA estaba en gramos no debe tocarse.
        sal = VGIngrediente.objects.create(
            nombre='Sal (ya en g)', unidad_medida='g', stock_actual='500.00', costo_unitario='0.01',
        )

        counts = rescale_legacy_units(
            VGIngrediente=VGIngrediente,
            VGPreparacion=VGPreparacion,
            VGDetalleCompra=VGDetalleCompra,
            VGDetalleCompraBorrador=VGDetalleCompraBorrador,
            VGRecetaProducto=VGRecetaProducto,
            VGRecetaPreparacion=VGRecetaPreparacion,
        )

        self.assertEqual(counts, {
            'ingredientes': 1,
            'preparaciones': 1,
            'detalle_compra': 1,
            'detalle_compra_borrador': 1,
            'receta_producto': 2,
            'receta_preparacion': 1,
        })

        carne.refresh_from_db()
        self.assertEqual(carne.unidad_medida, 'g')
        self.assertEqual(carne.stock_actual, Decimal('100000.00'))
        self.assertEqual(carne.stock_minimo, Decimal('10000.00'))
        self.assertEqual(carne.costo_unitario, Decimal('0.005000'))
        # El valor total del inventario (cantidad x costo) no cambia.
        self.assertEqual(Decimal('100.00') * Decimal('5.0000'), Decimal('100000.00') * Decimal('0.005000'))

        detalle_compra.refresh_from_db()
        self.assertEqual(detalle_compra.cantidad, Decimal('50000.00'))
        self.assertEqual(detalle_compra.costo_unitario, Decimal('0.004000'))
        self.assertEqual(detalle_compra.subtotal, Decimal('50.00') * Decimal('4.0000'))  # $200, invariante

        detalle_borrador.refresh_from_db()
        self.assertEqual(detalle_borrador.cantidad, Decimal('20000.00'))
        self.assertEqual(detalle_borrador.precio_total, Decimal('80.00'))  # dinero total, no se toca
        self.assertEqual(detalle_borrador.costo_unitario, Decimal('80.00') / Decimal('20000.00'))

        receta_directa.refresh_from_db()
        self.assertEqual(receta_directa.cantidad_requerida, Decimal('200.000'))

        salsa.refresh_from_db()
        self.assertEqual(salsa.rendimiento_unidad, 'ml')
        self.assertEqual(salsa.rendimiento_cantidad, Decimal('2000.000'))

        receta_salsa.refresh_from_db()
        self.assertEqual(receta_salsa.cantidad_requerida, Decimal('500.000'))

        receta_plato_salsa.refresh_from_db()
        self.assertEqual(receta_plato_salsa.cantidad_requerida, Decimal('300.000'))

        sal.refresh_from_db()
        self.assertEqual(sal.unidad_medida, 'g')
        self.assertEqual(sal.stock_actual, Decimal('500.00'))
        self.assertEqual(sal.costo_unitario, Decimal('0.010000'))

        # Correr la función una segunda vez es un no-op: ya no queda nada en kg/l.
        second_pass_counts = rescale_legacy_units(
            VGIngrediente=VGIngrediente,
            VGPreparacion=VGPreparacion,
            VGDetalleCompra=VGDetalleCompra,
            VGDetalleCompraBorrador=VGDetalleCompraBorrador,
            VGRecetaProducto=VGRecetaProducto,
            VGRecetaPreparacion=VGRecetaPreparacion,
        )
        self.assertEqual(second_pass_counts, {
            'ingredientes': 0,
            'preparaciones': 0,
            'detalle_compra': 0,
            'detalle_compra_borrador': 0,
            'receta_producto': 0,
            'receta_preparacion': 0,
        })


def _set_tasa_actual(tasa):
    """
    Simula "la tasa BCV actual del sistema" para un test: obtener_tasa_actual()
    devuelve la VGTasaCambio con el fecha_actualizacion (auto_now) mas reciente,
    y no la refresca contra la fuente externa mientras no este vencida (6h) — así
    que crear/actualizar directamente la fila de hoy es suficiente para que la
    vea como "la tasa actual" sin tener que mockear la llamada de red.
    """
    fila, _created = VGTasaCambio.objects.update_or_create(
        fecha=timezone.localdate(), defaults={'tasa': Decimal(str(tasa)), 'fuente': 'BCV'},
    )
    return fila


class TasaCambioAutoAssignTests(TestCase):
    """
    Persistencia automática de tasa: crear un VGGasto, VGCompra o VGPago sin
    mandar tasa_cambio_referencia debe dejarlo con la tasa BCV actual del
    sistema en ese momento (ver tasa_cambio_para_registro/obtener_tasa_actual),
    nunca en NULL.
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='tasa_admin', password='claveAdmin123', cedula='90000001',
            email='tasa_admin@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.metodo_pago = VGMetodoPago.objects.create(nombre='Efectivo test', moneda='USD', es_efectivo=True)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Servicios test')
        self.tasa_actual = _set_tasa_actual('780.5000')

    def test_gasto_creation_auto_assigns_current_rate(self):
        response = self.client.post(
            '/api/admin/gastos/',
            data=json.dumps({
                'categoria_id': self.categoria_gasto.id,
                'descripcion': 'Factura de luz',
                'monto': '50.00',
                'fecha_gasto': timezone.localdate().isoformat(),
                # tasa_cambio_referencia deliberadamente omitida.
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        gasto = VGGasto.objects.get(descripcion='Factura de luz')
        self.assertEqual(gasto.tasa_cambio_referencia, self.tasa_actual.tasa)
        self.assertEqual(response.json()['gasto']['tasa_cambio_referencia'], str(self.tasa_actual.tasa))

    def test_compra_creation_auto_assigns_current_rate(self):
        # El alta de un ingrediente NUEVO por /api/admin/catalogo/ crea de una vez
        # un VGCompra (ver AdminCatalogApiTests) — no hace falta un flujo aparte.
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'inventario',
                'nombre': 'Cebolla test',
                'ingrediente_id': '',
                'cantidad': '10',
                'unidad': 'kg',
                'proveedor': 'Proveedor tasa test',
                'stock_minimo': '1.0',
                'precio_total': '20.00',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        compra = VGCompra.objects.get(proveedor_nombre='Proveedor tasa test')
        self.assertEqual(compra.tasa_cambio_referencia, self.tasa_actual.tasa)

    def test_pago_creation_auto_assigns_current_rate(self):
        cliente = VGCliente.objects.create(nombre='Cliente tasa test')
        factura = VGFactura.objects.create(
            numero_factura=900001, numero_control=900001, cliente=cliente,
            total=Decimal('100.00'), saldo_pendiente=Decimal('100.00'),
        )

        response = self.client.post(
            f'/api/facturas/{factura.id}/abonos/',
            data=json.dumps({'monto': '100.00', 'metodo_pago_id': self.metodo_pago.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        pago = factura.pagos.get()
        self.assertEqual(pago.tasa_cambio_referencia, self.tasa_actual.tasa)


class TasaCambioInmutabilidadFinancieraTests(TestCase):
    """
    Un registro ya creado no debe cambiar de valor en bolívares cuando la tasa
    BCV vigente cambia después — tasa_cambio_referencia queda congelada a la
    tasa que estaba activa al momento de crearlo. La única excepción
    deliberada es el bolívar EQUIVALENTE de un gasto en dólares mientras sigue
    pendiente (ver moneda_origen y _serialize_gasto en gastos_views.py): como
    esa deuda aun no se pagó, su equivalente en bs debe reflejar lo que
    costaría saldarla HOY, no lo que costaba el día que se registró — a
    diferencia de un gasto registrado directamente en bolívares, que sí queda
    fijo en ese monto (reportado 2026-09).
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='inmutable_admin', password='claveAdmin123', cedula='90000002',
            email='inmutable_admin@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Alquiler test')

    def test_gasto_en_usd_recalcula_su_bs_a_la_tasa_actual_mientras_este_pendiente(self):
        tasa_x = _set_tasa_actual('750.0000')

        response = self.client.post(
            '/api/admin/gastos/',
            data=json.dumps({
                'categoria_id': self.categoria_gasto.id,
                'descripcion': 'Alquiler de septiembre',
                'monto': '200.00',
                'fecha_gasto': timezone.localdate().isoformat(),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        gasto_id = response.json()['gasto']['id']

        # La tasa "actual" del sistema sube después de crear el gasto.
        tasa_y = _set_tasa_actual('900.0000')
        self.assertNotEqual(tasa_x.tasa, tasa_y.tasa)

        detail_response = self.client.get(f'/api/admin/gastos/{gasto_id}/')
        self.assertEqual(detail_response.status_code, 200)
        gasto_payload = detail_response.json()['gasto']

        # tasa_cambio_referencia (la que se congeló al registrar el gasto) no
        # cambia nunca — eso sigue siendo inmutable.
        self.assertEqual(gasto_payload['tasa_cambio_referencia'], str(tasa_x.tasa))

        # Pero total_bs/saldo_pendiente_bs de un gasto en USD SI se recalculan
        # con la tasa vigente mientras siga pendiente.
        bs_con_tasa_nueva = (Decimal('200.00') * tasa_y.tasa).quantize(Decimal('0.01'))
        self.assertEqual(gasto_payload['total_bs'], str(bs_con_tasa_nueva))
        self.assertEqual(gasto_payload['saldo_pendiente_bs'], str(bs_con_tasa_nueva))

    def test_gasto_en_bs_mantiene_su_monto_en_bolivares_fijo(self):
        tasa_x = _set_tasa_actual('750.0000')

        response = self.client.post(
            '/api/admin/gastos/',
            data=json.dumps({
                'categoria_id': self.categoria_gasto.id,
                'descripcion': 'Jabón',
                'monto_bs': '2000.00',
                'fecha_gasto': timezone.localdate().isoformat(),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        gasto_id = response.json()['gasto']['id']

        _set_tasa_actual('900.0000')

        detail_response = self.client.get(f'/api/admin/gastos/{gasto_id}/')
        self.assertEqual(detail_response.status_code, 200)
        gasto_payload = detail_response.json()['gasto']

        self.assertEqual(gasto_payload['moneda_origen'], 'VES')
        self.assertEqual(gasto_payload['tasa_cambio_referencia'], str(tasa_x.tasa))
        self.assertEqual(gasto_payload['total_bs'], '2000.00')
        self.assertEqual(gasto_payload['saldo_pendiente_bs'], '2000.00')


class EstadoResultadosHistoricoAcumuladoTests(TestCase):
    """
    El total en bolívares de un reporte que abarca varios registros con tasas
    congeladas distintas debe ser la suma de cada uno convertido con SU PROPIA
    tasa (registro por registro) — no la suma en USD del período multiplicada
    por la tasa vigente al momento de pedir el reporte (ver
    reporte_estado_resultados_view / _calcular_margen_periodo en
    api_views.py/contabilidad_views.py).
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='reporte_admin', password='claveAdmin123', cedula='90000003',
            email='reporte_admin@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Nomina test')

    def test_gastos_total_bs_es_la_suma_registro_por_registro_no_usd_por_tasa_actual(self):
        hoy = timezone.localdate()

        tasa_x = _set_tasa_actual('700.0000')
        gasto_1 = VGGasto.objects.create(
            categoria=self.categoria_gasto, descripcion='Nomina quincena 1',
            monto=Decimal('300.00'), saldo_pendiente=Decimal('300.00'),
            fecha_gasto=hoy, tasa_cambio_referencia=tasa_x.tasa,
        )

        tasa_y = _set_tasa_actual('950.0000')
        gasto_2 = VGGasto.objects.create(
            categoria=self.categoria_gasto, descripcion='Nomina quincena 2',
            monto=Decimal('300.00'), saldo_pendiente=Decimal('300.00'),
            fecha_gasto=hoy, tasa_cambio_referencia=tasa_y.tasa,
        )

        response = self.client.get(
            f'/api/admin/reportes/estado-resultados/?desde={hoy.isoformat()}&hasta={hoy.isoformat()}',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        esperado_bs = (
            gasto_1.monto * tasa_x.tasa + gasto_2.monto * tasa_y.tasa
        ).quantize(Decimal('0.01'))
        self.assertEqual(payload['gastos_total_bs'], str(esperado_bs))

        # El bug que se corrigió: sumar el USD del período y multiplicarlo por
        # la tasa vigente AL CONSULTAR dá un número distinto — probamos que el
        # endpoint ya NO devuelve ese valor.
        usd_total = gasto_1.monto + gasto_2.monto
        bs_con_tasa_actual_al_consultar = (usd_total * tasa_y.tasa).quantize(Decimal('0.01'))
        self.assertNotEqual(payload['gastos_total_bs'], str(bs_con_tasa_actual_al_consultar))


class AjusteInventarioTests(TestCase):
    """
    Cubre las reglas de negocio mas delicadas del modulo de ajuste de
    inventario (ver ajustes_inventario_views.py): guardar solo procesa lineas
    nuevas/modificadas sin retocar lo ya aplicado, editar/quitar una linea ya
    aplicada mueve solo el delta (o el reverso exacto) en vez de recalcular
    todo desde cero, y el cierre mensual bloquea el mes completo.
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='ajusteinventario', password='claveAdmin123', cedula='90000004',
            email='ajusteinventario@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.harina = VGIngrediente.objects.create(
            nombre='Harina', unidad_medida='g', stock_actual=Decimal('100.00'),
        )
        self.queso = VGIngrediente.objects.create(
            nombre='Queso', unidad_medida='g', stock_actual=Decimal('50.00'),
        )

    def _agregar(self, ingrediente, tipo, cantidad, motivo=''):
        return self.client.post(
            '/api/admin/inventario/ajuste/agregar/',
            data=json.dumps({
                'ingrediente_id': ingrediente.id, 'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo,
            }),
            content_type='application/json',
        )

    def test_guardar_aplica_deltas_y_crea_movimientos_trazables(self):
        self._agregar(self.harina, 'suma', '30.00')
        self._agregar(self.queso, 'resta', '10.00')

        response = self.client.post('/api/admin/inventario/ajuste/guardar/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['ok'])
        ajuste_id = payload['ajuste']['id']

        self.harina.refresh_from_db()
        self.queso.refresh_from_db()
        self.assertEqual(self.harina.stock_actual, Decimal('130.00'))
        self.assertEqual(self.queso.stock_actual, Decimal('40.00'))

        movimientos = VGMovimientoInventario.objects.filter(tipo_movimiento='ajuste', id_referencia=ajuste_id)
        self.assertEqual(movimientos.count(), 2)
        self.assertEqual(
            set(movimientos.values_list('ingrediente_id', 'cantidad')),
            {(self.harina.id, Decimal('30.00')), (self.queso.id, Decimal('-10.00'))},
        )

        for detalle in payload['ajuste']['detalles']:
            self.assertTrue(detalle['aplicado'])
            self.assertEqual(detalle['cantidad'], detalle['cantidad_aplicada'])

    def test_guardar_de_nuevo_solo_procesa_la_linea_nueva(self):
        self._agregar(self.harina, 'suma', '30.00')
        self.client.post('/api/admin/inventario/ajuste/guardar/')

        self._agregar(self.queso, 'resta', '5.00')
        response = self.client.post('/api/admin/inventario/ajuste/guardar/')
        self.assertEqual(response.status_code, 200, response.content)

        self.harina.refresh_from_db()
        self.queso.refresh_from_db()
        # La linea de harina YA aplicada no se vuelve a tocar/duplicar.
        self.assertEqual(self.harina.stock_actual, Decimal('130.00'))
        self.assertEqual(self.queso.stock_actual, Decimal('45.00'))

        self.assertEqual(
            VGMovimientoInventario.objects.filter(tipo_movimiento='ajuste', ingrediente=self.harina).count(), 1,
        )
        self.assertEqual(
            VGMovimientoInventario.objects.filter(tipo_movimiento='ajuste', ingrediente=self.queso).count(), 1,
        )

    def test_editar_linea_aplicada_mueve_solo_el_delta(self):
        self._agregar(self.harina, 'suma', '30.00')
        self.client.post('/api/admin/inventario/ajuste/guardar/')

        detalle_id = VGDetalleAjusteInventario.objects.get(ingrediente=self.harina).id
        response = self.client.post(
            '/api/admin/inventario/ajuste/editar/',
            data=json.dumps({'detalle_id': detalle_id, 'cantidad': '50.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.harina.refresh_from_db()
        # 100 base + 30 (primer guardado) + 20 de delta (50 - 30) = 150, NUNCA
        # se revierte el aplicado original para re-sumar 50 desde cero.
        self.assertEqual(self.harina.stock_actual, Decimal('150.00'))

        movimientos = VGMovimientoInventario.objects.filter(tipo_movimiento='ajuste', ingrediente=self.harina).order_by('id')
        self.assertEqual(list(movimientos.values_list('cantidad', flat=True)), [Decimal('30.00'), Decimal('20.00')])

    def test_quitar_linea_aplicada_revierte_exactamente_lo_aplicado(self):
        self._agregar(self.queso, 'resta', '10.00')
        self.client.post('/api/admin/inventario/ajuste/guardar/')
        self.queso.refresh_from_db()
        self.assertEqual(self.queso.stock_actual, Decimal('40.00'))

        detalle_id = VGDetalleAjusteInventario.objects.get(ingrediente=self.queso).id
        response = self.client.post(
            '/api/admin/inventario/ajuste/quitar/',
            data=json.dumps({'detalle_id': detalle_id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.queso.refresh_from_db()
        self.assertEqual(self.queso.stock_actual, Decimal('50.00'))
        self.assertFalse(VGDetalleAjusteInventario.objects.filter(pk=detalle_id).exists())

        reversos = VGMovimientoInventario.objects.filter(tipo_movimiento='ajuste', ingrediente=self.queso).order_by('id')
        self.assertEqual(list(reversos.values_list('cantidad', flat=True)), [Decimal('-10.00'), Decimal('10.00')])

    def test_quitar_linea_no_aplicada_no_genera_movimiento(self):
        self._agregar(self.harina, 'suma', '30.00')
        detalle_id = VGDetalleAjusteInventario.objects.get(ingrediente=self.harina).id

        response = self.client.post(
            '/api/admin/inventario/ajuste/quitar/',
            data=json.dumps({'detalle_id': detalle_id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.harina.refresh_from_db()
        self.assertEqual(self.harina.stock_actual, Decimal('100.00'))
        self.assertFalse(VGMovimientoInventario.objects.filter(tipo_movimiento='ajuste', ingrediente=self.harina).exists())

    def test_cierre_mensual_bloquea_agregar_y_exige_lineas_guardadas(self):
        self._agregar(self.harina, 'suma', '30.00')

        # No se puede cerrar con una linea sin guardar todavia.
        rechazo = self.client.post('/api/admin/inventario/cierre/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(rechazo.status_code, 400)

        self.client.post('/api/admin/inventario/ajuste/guardar/')
        cierre = self.client.post('/api/admin/inventario/cierre/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(cierre.status_code, 201, cierre.content)

        anio = timezone.localtime(timezone.now()).year
        mes = timezone.localtime(timezone.now()).month
        self.assertTrue(VGCierreInventario.objects.filter(anio=anio, mes=mes).exists())

        bloqueado = self._agregar(self.queso, 'resta', '5.00')
        self.assertEqual(bloqueado.status_code, 400)
        self.assertFalse(VGDetalleAjusteInventario.objects.filter(ingrediente=self.queso).exists())

    def test_descartar_ajuste_sin_lineas_aplicadas(self):
        self._agregar(self.harina, 'suma', '30.00')
        response = self.client.post('/api/admin/inventario/ajuste/descartar/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()['ajuste'])
        self.assertFalse(VGAjusteInventario.objects.exists())

    def test_descartar_rechazado_si_ya_tiene_lineas_aplicadas(self):
        self._agregar(self.harina, 'suma', '30.00')
        self.client.post('/api/admin/inventario/ajuste/guardar/')

        response = self.client.post('/api/admin/inventario/ajuste/descartar/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VGAjusteInventario.objects.exists())


class TransferenciaCuentasTests(TestCase):
    """
    Cubre la transferencia manual de dinero entre cuentas propias
    (VGTransferenciaCuenta) y su integracion en disponibilidad_por_cuenta
    (reportes.py) via contabilidad_views.transferencias_cuentas_view. Los
    saldos de apertura se siembran con VGIngresoExtra (mismo mecanismo que
    usa disponibilidad_por_cuenta para sumar dinero real entrado por cada
    cuenta).
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='transferencias_admin', password='claveAdmin123', cedula='90000005',
            email='transferencias_admin@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)

        self.zelle = VGMetodoPago.objects.create(nombre='Zelle Test', moneda='USD')
        self.binance = VGMetodoPago.objects.create(nombre='Binance Test', moneda='USD')
        self.banesco = VGMetodoPago.objects.create(nombre='Banesco Test', moneda='VES')

        self.hoy = timezone.localdate()

        # Saldo de apertura: 1000 USD en Zelle.
        VGIngresoExtra.objects.create(
            tipo='pago_extra', monto=Decimal('1000.00'), metodo_pago=self.zelle,
        )
        # Saldo de apertura en Banesco: 100 USD equivalentes, congelados a una
        # tasa de 40 Bs/USD -> 4000 Bs reales en esa cuenta.
        VGIngresoExtra.objects.create(
            tipo='pago_extra', monto=Decimal('100.00'), metodo_pago=self.banesco,
            tasa_cambio_referencia=Decimal('40.0000'),
        )

    def _disponibilidad(self):
        response = self.client.get(f'/api/admin/reportes/disponibilidad-cuentas/?fecha={self.hoy.isoformat()}')
        self.assertEqual(response.status_code, 200, response.content)
        return {cuenta['id']: cuenta for cuenta in response.json()['cuentas']}

    def _transferir(self, **overrides):
        body = {
            'fecha': self.hoy.isoformat(),
            'cuenta_origen_id': self.zelle.id,
            'cuenta_destino_id': self.binance.id,
            'monto_origen': '200.00',
            'concepto': 'Reorganizando fondos',
        }
        body.update(overrides)
        return self.client.post(
            '/api/admin/transferencias-cuentas/', data=json.dumps(body), content_type='application/json',
        )

    def test_transferencia_misma_moneda_mueve_el_saldo_exacto(self):
        response = self._transferir()
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertEqual(payload['transferencia']['monto_usd'], '200.00')

        saldos = self._disponibilidad()
        self.assertEqual(Decimal(saldos[self.zelle.id]['saldo_disponible']), Decimal('800.00'))
        self.assertEqual(Decimal(saldos[self.binance.id]['saldo_disponible']), Decimal('200.00'))
        self.assertEqual(Decimal(saldos[self.zelle.id]['transferencias_salientes_acumuladas']), Decimal('200.00'))
        self.assertEqual(Decimal(saldos[self.binance.id]['transferencias_entrantes_acumuladas']), Decimal('200.00'))

    def test_transferencia_misma_moneda_rechaza_montos_distintos(self):
        response = self._transferir(monto_destino='150.00')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VGTransferenciaCuenta.objects.exists())

    def test_transferencia_cruzada_usa_tasa_manual_no_bcv(self):
        # 800 Bs de Banesco -> Zelle, a una tasa ACORDADA de 40 (coincide con
        # la tasa congelada del saldo inicial a proposito, para que el
        # resultado en Bs sea facil de verificar), nunca la BCV automatica.
        response = self._transferir(
            cuenta_origen_id=self.banesco.id,
            cuenta_destino_id=self.zelle.id,
            monto_origen='800.00',
            monto_destino='20.00',
            tasa_cambio='40.0000',
        )
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()['transferencia']
        self.assertEqual(payload['monto_usd'], '20.00')
        self.assertEqual(payload['tasa_cambio'], '40.0000')

        saldos = self._disponibilidad()
        # Banesco: baja 800 Bs reales Y 20 USD del saldo normalizado general.
        self.assertEqual(Decimal(saldos[self.banesco.id]['saldo_disponible_bs']), Decimal('3200.00'))
        self.assertEqual(Decimal(saldos[self.banesco.id]['saldo_disponible']), Decimal('80.00'))
        # Zelle: sube 20 USD (el lado ya en dolares no tiene saldo en Bs).
        self.assertEqual(Decimal(saldos[self.zelle.id]['saldo_disponible']), Decimal('1020.00'))

    def test_transferencia_cruzada_sin_tasa_se_rechaza(self):
        response = self._transferir(
            cuenta_origen_id=self.banesco.id,
            cuenta_destino_id=self.zelle.id,
            monto_origen='800.00',
            monto_destino='20.00',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VGTransferenciaCuenta.objects.exists())

    def test_no_permite_transferir_a_la_misma_cuenta(self):
        response = self._transferir(cuenta_destino_id=self.zelle.id)
        self.assertEqual(response.status_code, 400)

    def test_rechaza_si_no_hay_saldo_suficiente(self):
        response = self._transferir(monto_origen='5000.00')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VGTransferenciaCuenta.objects.exists())

    def test_concepto_es_obligatorio(self):
        response = self._transferir(concepto='')
        self.assertEqual(response.status_code, 400)

    def test_get_sin_filtros_devuelve_el_mes_en_curso(self):
        self._transferir()
        response = self.client.get('/api/admin/transferencias-cuentas/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload['transferencias']), 1)
        self.assertEqual(payload['transferencias'][0]['cuenta_origen_nombre'], 'Zelle Test')
        self.assertEqual(payload['transferencias'][0]['cuenta_destino_nombre'], 'Binance Test')
        self.assertEqual(payload['total_usd'], '200.00')

    def test_get_filtra_por_rango_de_fechas(self):
        self._transferir()
        ayer = (self.hoy - timedelta(days=1)).isoformat()
        anteayer = (self.hoy - timedelta(days=2)).isoformat()
        response = self.client.get(f'/api/admin/transferencias-cuentas/?desde={anteayer}&hasta={ayer}')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['transferencias'], [])

    def test_get_filtra_por_id(self):
        self._transferir()
        primera_id = VGTransferenciaCuenta.objects.get().id
        self._transferir(concepto='Otra transferencia')

        response = self.client.get(f'/api/admin/transferencias-cuentas/?id={primera_id}')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload['transferencias']), 1)
        self.assertEqual(payload['transferencias'][0]['id'], primera_id)

    def test_get_filtra_por_cuenta_como_origen_o_destino(self):
        self._transferir()  # Zelle Test -> Binance Test
        self._transferir(
            cuenta_origen_id=self.banesco.id, cuenta_destino_id=self.zelle.id,
            monto_origen='400.00', monto_destino='10.00', tasa_cambio='40.0000',
        )  # Banesco Test -> Zelle Test

        response = self.client.get(f'/api/admin/transferencias-cuentas/?cuenta_id={self.binance.id}')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload['transferencias']), 1)
        self.assertEqual(payload['transferencias'][0]['cuenta_destino_nombre'], 'Binance Test')

        # Zelle Test participa como origen en una y como destino en la otra —
        # el filtro por cuenta debe encontrar las dos.
        response_zelle = self.client.get(f'/api/admin/transferencias-cuentas/?cuenta_id={self.zelle.id}')
        self.assertEqual(len(response_zelle.json()['transferencias']), 2)


class ReporteMovimientoProductosTests(TestCase):
    """
    El reporte de movimiento de productos NO agrega ventas — cada linea de
    pedido pagada es su propia fila en la seccion de su producto. Cobra los
    pedidos a traves del endpoint real /api/pedidos/cobro/ (igual criterio
    que PedidoCobroInventoryDeductionTests) para probar contra datos reales,
    no solo contra un lookup aislado.
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='movimiento_admin', password='claveAdmin123', cedula='90000006',
            email='movimiento_admin@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria_entradas = VGCategoriaProducto.objects.create(nombre='Entradas')
        self.categoria_fuertes = VGCategoriaProducto.objects.create(nombre='Platos fuertes')
        self.metodo_pago, _ = VGMetodoPago.objects.get_or_create(
            nombre='Efectivo', defaults={'es_efectivo': True},
        )
        self.tequenos = VGProducto.objects.create(
            nombre='Tequeños', categoria=self.categoria_entradas, precio_venta='4.00', disponible=True,
        )
        self.carne = VGProducto.objects.create(
            nombre='Carne a la parrilla', categoria=self.categoria_fuertes, precio_venta='10.00',
            disponible=True, venta_por_peso=True,
        )
        self.hoy = timezone.localdate()

    def _crear_pedido_pagado(self, lineas, estado_inicial='entregado'):
        """lineas: [(producto, cantidad, peso_gramos|None)] — cobra via el endpoint real de cobro."""
        pedido = VGPedido.objects.create(
            usuario=self.admin, tipo_pedido='local', estado=estado_inicial, subtotal='0', total='0',
        )
        for producto, cantidad, peso in lineas:
            VGDetallePedido.objects.create(
                pedido=pedido, producto=producto, cantidad=cantidad, precio_unitario='1.00',
                peso_gramos=peso, estado='entregado',
            )
        response = self.client.post(
            '/api/pedidos/cobro/',
            data=json.dumps({'pedido_ids': [pedido.id], 'metodo_pago_id': self.metodo_pago.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return pedido

    def _reporte(self, desde=None, hasta=None):
        query = {}
        if desde:
            query['desde'] = desde
        if hasta:
            query['hasta'] = hasta
        response = self.client.get('/api/admin/reportes/movimiento-productos/', data=query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_producto_por_unidad_muestra_cada_venta_como_fila_separada(self):
        for _ in range(5):
            self._crear_pedido_pagado([(self.tequenos, 1, None)])

        payload = self._reporte(self.hoy.isoformat(), self.hoy.isoformat())
        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.tequenos.id)
        self.assertEqual(len(grupo['filas']), 5)
        self.assertEqual(grupo['total_cantidad'], '5.00')
        self.assertEqual(grupo['unidad'], 'unidad')
        # Las filas van en orden cronologico (la mas vieja primero).
        fechas = [fila['fecha_hora'] for fila in grupo['filas']]
        self.assertEqual(fechas, sorted(fechas))

    def test_producto_por_peso_muestra_el_peso_exacto_de_cada_venta_y_suma_correcto(self):
        self._crear_pedido_pagado([(self.carne, 1, Decimal('250.00'))])
        self._crear_pedido_pagado([(self.carne, 1, Decimal('500.00'))])

        payload = self._reporte(self.hoy.isoformat(), self.hoy.isoformat())
        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.carne.id)
        self.assertEqual(len(grupo['filas']), 2)
        # Cada fila trae SU PROPIO peso exacto — nunca un promedio.
        self.assertEqual({fila['peso_gramos'] for fila in grupo['filas']}, {'250.00', '500.00'})
        self.assertEqual(grupo['unidad'], 'kg')
        self.assertEqual(grupo['total_cantidad'], '0.75')

    def test_fila_muestra_el_codigo_de_nota_de_entrega_o_guion_si_no_tiene(self):
        pedido_con_nota = self._crear_pedido_pagado([(self.tequenos, 1, None)])
        nota = VGNotaEntrega.objects.get(pedidos=pedido_con_nota)

        # Un pedido pagado sin nota de entrega (dato historico/de borde) no
        # debe romper el reporte — la fila debe traer None, no un error.
        pedido_sin_nota = VGPedido.objects.create(
            usuario=self.admin, tipo_pedido='local', estado='pagado', subtotal='4.00', total='4.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido_sin_nota, producto=self.tequenos, cantidad=1, precio_unitario='4.00', estado='entregado',
        )

        payload = self._reporte(self.hoy.isoformat(), self.hoy.isoformat())
        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.tequenos.id)
        codigos_por_pedido = {fila['pedido_id']: fila['nota_entrega_codigo'] for fila in grupo['filas']}
        self.assertEqual(codigos_por_pedido[pedido_con_nota.id], nota.codigo)
        self.assertIsNone(codigos_por_pedido[pedido_sin_nota.id])

    def test_rango_por_defecto_es_solo_hoy(self):
        self._crear_pedido_pagado([(self.tequenos, 1, None)])

        pedido_ayer = VGPedido.objects.create(
            usuario=self.admin, tipo_pedido='local', estado='pagado', subtotal='4.00', total='4.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido_ayer, producto=self.tequenos, cantidad=1, precio_unitario='4.00', estado='entregado',
        )
        VGPedido.objects.filter(pk=pedido_ayer.pk).update(fecha_creacion=timezone.now() - timedelta(days=1))

        response = self.client.get('/api/admin/reportes/movimiento-productos/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['desde'], self.hoy.isoformat())
        self.assertEqual(payload['hasta'], self.hoy.isoformat())
        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.tequenos.id)
        self.assertEqual(len(grupo['filas']), 1)

    def test_secciones_ordenadas_de_mayor_a_menor_movimiento(self):
        for _ in range(3):
            self._crear_pedido_pagado([(self.tequenos, 1, None)])
        self._crear_pedido_pagado([(self.carne, 1, Decimal('100.00'))])

        payload = self._reporte(self.hoy.isoformat(), self.hoy.isoformat())
        nombres = [producto['nombre'] for producto in payload['productos']]
        self.assertEqual(nombres[0], 'Tequeños')


class ReporteMargenGananciaDetalleTests(TestCase):
    """
    El reporte de margen de ganancia detallado debe mostrar el ingreso y el
    costo CONGELADOS de cada venta, nunca recalculados con los precios o
    costos de HOY — ver reporte_margen_ganancia_detalle_view (api_views.py).
    Cobra a traves del endpoint real /api/pedidos/cobro/ (que es quien
    congela VGDetallePedido.costo_unitario_venta al cobrar, ver
    _snapshot_costo_venta_detalles) para probar contra el mecanismo real,
    no contra un valor puesto a mano.
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='margen_admin', password='claveAdmin123', cedula='90000007',
            email='margen_admin@sevens.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria = VGCategoriaProducto.objects.create(nombre='Platos fuertes')
        self.metodo_pago, _ = VGMetodoPago.objects.get_or_create(
            nombre='Efectivo', defaults={'es_efectivo': True},
        )
        self.carne = VGIngrediente.objects.create(
            nombre='Carne', unidad_medida='g', stock_actual='100000', costo_unitario='0.02',
        )
        self.bistec = VGProducto.objects.create(
            nombre='Bistec', categoria=self.categoria, precio_venta='10.00', disponible=True,
        )
        VGRecetaProducto.objects.create(producto=self.bistec, ingrediente=self.carne, cantidad_requerida='150.000')
        self.hoy = timezone.localdate()

    def _crear_pedido_pagado(self, producto, precio_unitario):
        pedido = VGPedido.objects.create(
            usuario=self.admin, tipo_pedido='local', estado='entregado', subtotal='0', total='0',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=producto, cantidad=1, precio_unitario=precio_unitario, estado='entregado',
        )
        response = self.client.post(
            '/api/pedidos/cobro/',
            data=json.dumps({'pedido_ids': [pedido.id], 'metodo_pago_id': self.metodo_pago.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return pedido

    def _reporte(self):
        response = self.client.get(
            '/api/admin/reportes/margen-ganancia-detalle/',
            data={'desde': self.hoy.isoformat(), 'hasta': self.hoy.isoformat()},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _fila(self, payload, pedido_id):
        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.bistec.id)
        return next(f for f in grupo['filas'] if f['pedido_id'] == pedido_id)

    def test_ingreso_y_costo_quedan_congelados_aunque_cambien_despues(self):
        pedido = self._crear_pedido_pagado(self.bistec, '10.00')

        detalle = VGDetallePedido.objects.get(pedido=pedido)
        self.assertEqual(detalle.costo_unitario_venta, Decimal('3.00'))  # 150g x $0.02/g

        # Cambia el precio de venta actual del producto Y el costo actual del
        # ingrediente — si el reporte recalculara con cualquiera de los dos,
        # esta prueba lo detecta.
        self.bistec.precio_venta = Decimal('999.00')
        self.bistec.save(update_fields=['precio_venta'])
        self.carne.costo_unitario = Decimal('5.00')
        self.carne.save(update_fields=['costo_unitario'])

        payload = self._reporte()
        fila = self._fila(payload, pedido.id)
        self.assertEqual(fila['ingreso'], '10.00')
        self.assertEqual(fila['costo'], '3.00')
        self.assertEqual(fila['ganancia_monto'], '7.00')
        self.assertFalse(fila['costo_estimado'])

    def test_venta_sin_costo_congelado_cae_a_costo_estimado(self):
        pedido = self._crear_pedido_pagado(self.bistec, '10.00')
        # Simula una venta vieja de antes de que existiera el snapshot de costo.
        VGDetallePedido.objects.filter(pedido=pedido).update(costo_unitario_venta=None)

        # El costo ACTUAL de la receta en este momento: 150g x $0.02/g = $3.00.
        payload = self._reporte()
        fila = self._fila(payload, pedido.id)
        self.assertTrue(fila['costo_estimado'])
        self.assertEqual(fila['costo'], '3.00')

        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.bistec.id)
        self.assertTrue(grupo['tiene_estimado'])

    def test_seccion_marca_estimado_solo_en_la_fila_que_corresponde(self):
        pedido_real = self._crear_pedido_pagado(self.bistec, '10.00')
        pedido_estimado = self._crear_pedido_pagado(self.bistec, '10.00')
        VGDetallePedido.objects.filter(pedido=pedido_estimado).update(costo_unitario_venta=None)

        payload = self._reporte()
        fila_real = self._fila(payload, pedido_real.id)
        fila_estimada = self._fila(payload, pedido_estimado.id)
        self.assertFalse(fila_real['costo_estimado'])
        self.assertTrue(fila_estimada['costo_estimado'])

        grupo = next(p for p in payload['productos'] if p['producto_id'] == self.bistec.id)
        self.assertTrue(grupo['tiene_estimado'])
        self.assertEqual(len(grupo['filas']), 2)
        # Los totales de la seccion siguen sumando bien aunque mezcle fuentes.
        self.assertEqual(grupo['ingreso_total'], '20.00')
        self.assertEqual(grupo['costo_total'], '6.00')

    def test_rango_por_defecto_es_solo_hoy(self):
        pedido = self._crear_pedido_pagado(self.bistec, '10.00')
        VGPedido.objects.filter(pk=pedido.pk).update(fecha_creacion=timezone.now() - timedelta(days=1))

        response = self.client.get('/api/admin/reportes/margen-ganancia-detalle/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['desde'], self.hoy.isoformat())
        self.assertEqual(payload['hasta'], self.hoy.isoformat())
        self.assertEqual(payload['productos'], [])
