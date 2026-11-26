"""
Subrecetas bloqueadas (recetas secretas): que nada de su composicion salga de la aplicacion sin el codigo, que
abrirla con el codigo funcione y se frene a quien adivina, y que la operacion (inventario) no cambie.
"""
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib import admin as django_admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.utils import timezone

from sevens.admin import VGPreparacionFormulario, VGPreparacionPanel
from sevens.alertas_costos_views import _recetas_afectadas
from sevens.api_views import (
    _compute_pedido_ingredient_needs, _ingredientes_sin_costo_de_producto, _load_preparation_structure,
)
from sevens.merma_ingredientes_views import _usos
from sevens.models import (
    VGAccesoSubreceta, VGCategoriaProducto, VGDetallePedido, VGIngrediente, VGMovimientoInventario, VGPedido,
    VGPreparacion, VGProducto, VGRecetaPreparacion, VGRecetaProducto, VGRol, VGUsuario,
)
from sevens.subrecetas_bloqueadas import usa_bloqueada

SECRETO = 'Chile ahumado secreto'


class SecretaBase(TestCase):
    def setUp(self):
        for nombre in ('Administrador', 'Contador', 'Mesero', 'Cajera'):
            VGRol.objects.get_or_create(nombre_role=nombre)
        self.admin = self.usuario('sec_admin', 'Administrador', '94000001')
        self.mesero = self.usuario('sec_mesero', 'Mesero', '94000002')
        self.tomate = VGIngrediente.objects.create(nombre='Tomate SB', unidad_medida='g', stock_actual='100000', costo_unitario='0.01')
        self.chile = VGIngrediente.objects.create(nombre=SECRETO, unidad_medida='g', stock_actual='100000', costo_unitario='0')
        self.salsa = VGPreparacion.objects.create(nombre='Salsa Sevens', rendimiento_cantidad='1000', rendimiento_unidad='g', bloqueada=True)
        self.salsa.poner_codigo('Ahumado#7')
        self.salsa.save()
        VGRecetaPreparacion.objects.create(preparacion=self.salsa, ingrediente=self.chile, cantidad_requerida='137')
        VGRecetaPreparacion.objects.create(preparacion=self.salsa, ingrediente=self.tomate, cantidad_requerida='863')
        self.normal = VGPreparacion.objects.create(nombre='Pico de gallo SB', rendimiento_cantidad='500', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=self.normal, ingrediente=self.tomate, cantidad_requerida='500')
        categoria = VGCategoriaProducto.objects.create(nombre='Platos SB')
        self.alitas = VGProducto.objects.create(
            nombre='Alitas SB', categoria=categoria, precio_venta='8', disponible=True, subreceta_vinculada=self.salsa,
        )
        self.nachos = VGProducto.objects.create(nombre='Nachos SB', categoria=categoria, precio_venta='6', disponible=True)
        VGRecetaProducto.objects.create(producto=self.nachos, preparacion=self.salsa, cantidad_requerida='50')

    def usuario(self, username, rol, cedula, **extra):
        return VGUsuario.objects.create_user(
            username=username, password='claveSecreta123', cedula=cedula, email=f'{username}@test.test',
            id_role=VGRol.objects.get(nombre_role=rol), **extra,
        )

    def post(self, url, cuerpo, usuario=None):
        self.client.force_login(usuario or self.admin)
        return self.client.post(url, json.dumps(cuerpo), content_type='application/json')

    def get(self, url, usuario=None):
        self.client.force_login(usuario or self.admin)
        return self.client.get(url)

    def abrir(self, codigo, usuario=None, preparacion=None):
        return self.post('/api/admin/subrecetas/desbloquear/', {'id': (preparacion or self.salsa).id, 'codigo': codigo}, usuario)


class NoSaleSinCodigoTests(SecretaBase):
    def test_el_catalogo_no_trae_componentes_ni_costo_de_la_tanda_de_la_bloqueada(self):
        recetas = {r['nombre']: r for r in self.get('/api/admin/catalogo/').json()['recipes']}
        secreta = recetas['Salsa Sevens']
        self.assertTrue(secreta['bloqueada'])
        self.assertEqual(secreta['componentes'], [])
        for campo in ('componentes_total', 'costo_total', 'margen_ganancia'):
            self.assertIsNone(secreta[campo], campo)
        self.assertNotIn(SECRETO, json.dumps(secreta, ensure_ascii=False))
        self.assertNotIn('codigo_acceso', secreta)
        self.assertEqual(len(recetas['Pico de gallo SB']['componentes']), 1)

    def test_al_usarla_en_otra_receta_o_producto_llega_su_costo_por_unidad(self):
        # Tanda de 1000 g: 863 g de tomate a $0.01 (el chile no tiene precio) = $8.63 -> $0.008630 por gramo.
        for url, clave in (
            ('/api/admin/catalogo/', 'recipes'),            # selector al armar subrecetas
            ('/api/admin/productos/', 'subrecetas'),        # selector al armar productos
            ('/api/admin/recetas/', 'preparations'),        # selector al armar recetas
        ):
            filas = {f['nombre']: f for f in self.get(url).json()[clave]}
            self.assertEqual(Decimal(filas['Salsa Sevens']['costo_unitario_calculado']), Decimal('0.008630'), url)
            self.assertNotIn(SECRETO, json.dumps(filas['Salsa Sevens'], ensure_ascii=False), url)

    def test_una_subreceta_que_usa_la_bloqueada_suma_su_costo_segun_la_cantidad(self):
        marinado = VGPreparacion.objects.create(nombre='Marinado SB', rendimiento_cantidad='200', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=marinado, sub_preparacion=self.salsa, cantidad_requerida='100')
        filas = {f['nombre']: f for f in self.get('/api/admin/catalogo/').json()['recipes']}
        self.assertEqual(filas['Marinado SB']['costo_total'], '0.86')  # 100 g x $0.00863
        self.assertEqual([c['nombre'] for c in filas['Marinado SB']['componentes']], ['Salsa Sevens'])

    def test_los_productos_no_nombran_ingredientes_sin_precio_de_la_secreta(self):
        for producto in self.get('/api/admin/productos/').json()['products']:
            self.assertNotIn(SECRETO, producto.get('ingredientes_sin_costo', []), producto['nombre'])

    def test_el_aviso_de_ingredientes_sin_costo_no_nombra_los_de_la_secreta(self):
        componentes, _ = _load_preparation_structure()
        costos = {self.tomate.id: Decimal('0.01'), self.chile.id: Decimal('0')}
        nombres = {self.chile.id: SECRETO, self.tomate.id: 'Tomate SB'}
        for producto in (self.alitas, self.nachos):
            self.assertEqual(_ingredientes_sin_costo_de_producto(producto, costos, componentes, nombres), [], producto.nombre)

    def test_el_mesero_no_ve_la_composicion_de_un_plato_hecho_con_la_secreta(self):
        # La pantalla de Nuevo pedido muestra la composicion de cada plato (serializers.py).
        self.assertEqual(VGProducto.objects.get(pk=self.alitas.pk).nombres_composicion(), [])
        self.client.force_login(self.mesero)
        VGPreparacion.objects.filter(pk=self.salsa.pk).update(bloqueada=False)
        self.assertIn(SECRETO, VGProducto.objects.get(pk=self.alitas.pk).nombres_composicion())

    def test_la_pantalla_de_merma_no_dice_que_ingredientes_lleva(self):
        usos = _usos([self.chile.id, self.tomate.id])
        self.assertNotIn(self.chile.id, usos)
        self.assertEqual([u['nombre'] for u in usos[self.tomate.id]], ['Pico de gallo SB'])

    def test_una_alerta_de_costo_no_delata_que_un_producto_lleva_el_ingrediente_secreto(self):
        fila = SimpleNamespace(id=1, ingrediente_id=self.chile.id, costo_anterior=Decimal('0.01'), costo_nuevo=Decimal('0.05'))
        self.assertEqual(_recetas_afectadas([fila])[1]['recetas'], [])
        # Sin candado, el mismo cambio si lista los productos: la prueba anterior no esta vacia.
        VGPreparacion.objects.filter(pk=self.salsa.pk).update(bloqueada=False)
        self.assertEqual({r['nombre'] for r in _recetas_afectadas([fila])[1]['recetas']}, {'Alitas SB', 'Nachos SB'})

    def test_usa_bloqueada_ve_a_traves_de_subrecetas_anidadas_y_productos(self):
        envoltura = VGPreparacion.objects.create(nombre='Marinado SB', rendimiento_cantidad='1', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=envoltura, sub_preparacion=self.salsa, cantidad_requerida='1')
        for tipo, objeto, esperado in (
            ('subreceta', self.salsa, True), ('subreceta', envoltura, True), ('subreceta', self.normal, False),
            ('receta', self.alitas, True), ('receta', self.nachos, True), ('ingrediente', self.chile, False),
        ):
            self.assertEqual(usa_bloqueada(tipo, objeto), esperado, (tipo, objeto.nombre))


class AbrirConCodigoTests(SecretaBase):
    def test_con_el_codigo_correcto_se_ve_la_receta_y_queda_registrado(self):
        r = self.abrir('Ahumado#7')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r['Cache-Control'], 'no-store')
        receta = r.json()['subreceta']
        self.assertEqual([(c['nombre'], Decimal(c['cantidad'])) for c in receta['componentes']], [(SECRETO, 137), ('Tomate SB', 863)])
        self.assertIsNotNone(receta['costo_total'])
        acceso = VGAccesoSubreceta.objects.get()
        self.assertEqual((acceso.usuario, acceso.preparacion, acceso.exitoso), (self.admin, self.salsa, True))

    def test_el_codigo_se_guarda_cifrado(self):
        self.salsa.refresh_from_db()
        self.assertNotIn('Ahumado#7', self.salsa.codigo_acceso)
        self.assertTrue(self.salsa.codigo_correcto('Ahumado#7'))
        self.assertFalse(self.salsa.codigo_correcto('ahumado#7'))

    def test_un_codigo_errado_no_muestra_nada(self):
        r = self.abrir('1234')
        self.assertEqual(r.status_code, 403)
        self.assertNotIn(SECRETO, r.content.decode())
        self.assertIn('Quedan 4', r.json()['message'])
        self.assertFalse(VGAccesoSubreceta.objects.get().exitoso)

    def test_cinco_errores_frenan_incluso_el_codigo_correcto_por_unos_minutos(self):
        for _ in range(5):
            self.assertEqual(self.abrir('mal').status_code, 403)
        self.assertEqual(self.abrir('Ahumado#7').status_code, 429)
        VGAccesoSubreceta.objects.update(fecha=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.abrir('Ahumado#7').status_code, 200)

    def test_un_acierto_reinicia_la_cuenta_de_errores(self):
        for _ in range(4):
            self.abrir('mal')
        self.assertEqual(self.abrir('Ahumado#7').status_code, 200)
        for _ in range(4):
            self.assertEqual(self.abrir('mal').status_code, 403)
        self.assertEqual(self.abrir('Ahumado#7').status_code, 200)

    def test_solo_administrador_o_contador_y_solo_subrecetas_bloqueadas(self):
        self.assertEqual(self.abrir('Ahumado#7', usuario=self.mesero).status_code, 401)
        self.assertEqual(self.abrir('x', preparacion=self.normal).status_code, 404)
        self.assertEqual(VGAccesoSubreceta.objects.count(), 0)


class NoSeModificaDesdeLaAppTests(SecretaBase):
    def assert_intacta(self):
        self.salsa.refresh_from_db()
        self.assertEqual(self.salsa.nombre, 'Salsa Sevens')
        self.assertEqual(self.salsa.componentes.count(), 2)

    def test_editar_eliminar_o_guardar_con_su_nombre_se_rechaza(self):
        componentes = [{'tipo': 'ingrediente', 'referencia_id': self.tomate.id, 'cantidad': '1', 'nombre': 'Tomate SB'}]
        intentos = (
            {'tipo': 'actualizar_preparacion', 'id': self.salsa.id, 'nombre': 'Otra', 'componentes': componentes},
            {'tipo': 'eliminar_receta', 'id': self.salsa.id},
            {'tipo': 'recetas', 'id': self.salsa.id, 'nombre': 'Salsa Sevens', 'componentes': componentes},
            {'tipo': 'recetas', 'nombre': 'salsa sevens', 'componentes': componentes},
        )
        for cuerpo in intentos:
            r = self.post('/api/admin/catalogo/', cuerpo)
            self.assertEqual(r.status_code, 403, (cuerpo['tipo'], r.content))
            self.assert_intacta()


class ComidaDeEmpleadosTests(SecretaBase):
    def previsualizar(self, preparacion):
        return self.post('/api/admin/comida-empleados/previsualizar/', {'tipo': 'subreceta', 'origen_id': preparacion.id, 'cantidad': '100'})

    def test_la_vista_previa_y_el_detalle_no_muestran_los_ingredientes_de_la_secreta(self):
        datos = self.previsualizar(self.salsa).json()
        self.assertTrue(datos['oculta'])
        self.assertEqual((datos['lineas'], datos['sin_stock'], datos['costo_total']), ([], [], None))
        self.assertNotIn(SECRETO, json.dumps(datos, ensure_ascii=False))

        r = self.post('/api/admin/comida-empleados/', {'tipo': 'subreceta', 'origen_id': self.salsa.id, 'cantidad': '100'})
        self.assertEqual(r.status_code, 201, r.content)
        comida = r.json()['comida']
        self.assertEqual(comida['lineas'], [])
        self.assertTrue(comida['oculta'])
        detalle = self.get(f'/api/admin/comida-empleados/{comida["id"]}/').json()['comida']
        self.assertEqual(detalle['lineas'], [])
        # El inventario si se desconto, y el motivo del movimiento no nombra la receta.
        self.chile.refresh_from_db()
        self.assertLess(self.chile.stock_actual, Decimal('100000'))
        for movimiento in VGMovimientoInventario.objects.all():
            self.assertNotIn('Salsa', movimiento.motivo)

    def test_sin_stock_de_la_secreta_pide_confirmar_sin_nombrar_el_ingrediente(self):
        VGIngrediente.objects.filter(pk=self.chile.pk).update(stock_actual=1)
        datos = self.previsualizar(self.salsa).json()
        self.assertTrue(datos['hay_faltantes'])
        r = self.post('/api/admin/comida-empleados/', {'tipo': 'subreceta', 'origen_id': self.salsa.id, 'cantidad': '100'})
        self.assertEqual(r.status_code, 409)
        self.assertNotIn(SECRETO, json.dumps(r.json(), ensure_ascii=False))

    def test_una_subreceta_normal_sigue_mostrando_el_desglose(self):
        datos = self.previsualizar(self.normal).json()
        self.assertFalse(datos['oculta'])
        self.assertEqual([l['nombre'] for l in datos['lineas']], ['Tomate SB'])


class LaOperacionNoCambiaTests(SecretaBase):
    def test_vender_un_plato_sigue_descontando_los_ingredientes_de_la_secreta(self):
        pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='local', estado='entregado', subtotal='8', total='8')
        VGDetallePedido.objects.create(pedido=pedido, producto=self.nachos, cantidad=2, precio_unitario='6', estado='entregado')
        componentes, rendimientos = _load_preparation_structure()
        necesidades = _compute_pedido_ingredient_needs(pedido, componentes, rendimientos)
        # 100 g de salsa (2 x 50) de una tanda de 1000 g
        self.assertEqual(necesidades[self.chile.id], Decimal('13.7'))


class DjangoAdminTests(SecretaBase):
    def formulario(self, instancia=None, **datos):
        base = {'nombre': 'Nueva SB', 'rendimiento_cantidad': '1', 'rendimiento_unidad': 'g'}
        base.update(datos)
        return VGPreparacionFormulario(data=base, instance=instancia)

    def test_para_bloquear_hay_que_poner_un_codigo_y_se_guarda_cifrado(self):
        self.assertIn('nuevo_codigo', self.formulario(bloqueada=True).errors)
        self.assertIn('nuevo_codigo', self.formulario(bloqueada=True, nuevo_codigo='12').errors)
        formulario = self.formulario(bloqueada=True, nuevo_codigo='clave-9')
        self.assertTrue(formulario.is_valid(), formulario.errors)
        preparacion = formulario.save()
        self.assertTrue(preparacion.codigo_correcto('clave-9'))

    def test_dejar_el_codigo_vacio_conserva_el_actual_y_desbloquear_lo_borra(self):
        conservar = self.formulario(instancia=VGPreparacion.objects.get(pk=self.salsa.pk), nombre='Salsa Sevens', bloqueada=True)
        self.assertTrue(conservar.is_valid(), conservar.errors)
        self.assertTrue(conservar.save().codigo_correcto('Ahumado#7'))
        abrir = self.formulario(instancia=VGPreparacion.objects.get(pk=self.salsa.pk), nombre='Salsa Sevens')
        self.assertTrue(abrir.is_valid(), abrir.errors)
        self.assertEqual(abrir.save().codigo_acceso, '')

    def peticion(self, **extra):
        peticion = RequestFactory().get('/admin/')
        peticion.user = self.usuario(extra.pop('username'), 'Administrador', extra.pop('cedula'), **extra)
        return peticion

    def test_solo_el_superusuario_ve_los_componentes_y_puede_cambiarla(self):
        panel = VGPreparacionPanel(VGPreparacion, django_admin.site)
        jefe = self.peticion(username='sb_jefe', cedula='94000010', is_staff=True, is_superuser=True)
        staff = self.peticion(username='sb_staff', cedula='94000011', is_staff=True)

        self.assertTrue(panel.get_inlines(jefe, self.salsa))
        self.assertIn('bloqueada', panel.get_fields(jefe, self.salsa))
        self.assertTrue(panel.has_change_permission(jefe, self.salsa))

        self.assertEqual(panel.get_inlines(staff, self.salsa), [])
        self.assertNotIn('bloqueada', panel.get_fields(staff, self.salsa))
        self.assertFalse(panel.has_change_permission(staff, self.salsa))
        self.assertFalse(panel.has_delete_permission(staff, self.salsa))
        with self.assertRaises(PermissionDenied):
            panel.history_view(staff, str(self.salsa.pk))

        panel.delete_queryset(staff, VGPreparacion.objects.filter(pk=self.salsa.pk))
        self.assertTrue(VGPreparacion.objects.filter(pk=self.salsa.pk).exists())

    def test_la_pantalla_de_edicion_del_superusuario_carga_y_guarda(self):
        jefe = self.usuario('sb_jefe2', 'Administrador', '94000012', is_staff=True, is_superuser=True)
        self.client.force_login(jefe)
        r = self.client.get(f'/admin/sevens/vgpreparacion/{self.salsa.pk}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'nuevo_codigo')
        self.assertNotContains(r, self.salsa.codigo_acceso)
