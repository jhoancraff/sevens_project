"""
Ningun ingrediente se oculta por su numero. Habia una lista fija de ids (heredada del sistema anterior) que
escondia ingredientes reales: en produccion, "QUESO MOZARELLA" (id 285) y el siguiente que se creara (288).
"""
import json

from django.test import TestCase

from sevens.models import VGIngrediente, VGMovimientoInventario, VGRol, VGUsuario

IDS_ANTES_OCULTOS = (285, 288, 312, 337, 366, 371, 372, 381, 487, 488)


class SinIngredientesOcultosTests(TestCase):
    def setUp(self):
        rol, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_user(
            username='oc_admin', password='claveOculta123', cedula='94200001', email='oc_admin@test.test', id_role=rol,
        )
        self.client.force_login(self.admin)
        self.ingredientes = [
            VGIngrediente.objects.create(id=pk, nombre=f'Insumo {pk}', unidad_medida='g', stock_actual='1000', costo_unitario='0.01')
            for pk in IDS_ANTES_OCULTOS
        ]
        self.nombres = {i.nombre for i in self.ingredientes}

    def nombres_de(self, url, clave):
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200, url)
        return {fila['nombre'] for fila in respuesta.json()[clave]}

    def test_salen_en_inventario_productos_recetas_y_comida_de_empleados(self):
        for url, clave in (
            ('/api/admin/catalogo/', 'inventory'),
            ('/api/admin/productos/', 'ingredients'),
            ('/api/admin/recetas/', 'ingredients'),
            ('/api/admin/comida-empleados/opciones/', 'ingredientes'),
        ):
            self.assertLessEqual(self.nombres, self.nombres_de(url, clave), url)

    def test_se_pueden_usar_en_una_comida_de_empleados_y_quedan_en_los_movimientos(self):
        queso = self.ingredientes[0]
        r = self.client.post('/api/admin/comida-empleados/', json.dumps({
            'tipo': 'ingrediente', 'origen_id': queso.id, 'cantidad': '100',
        }), content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(VGMovimientoInventario.objects.filter(ingrediente=queso).count(), 1)
        queso.refresh_from_db()
        self.assertEqual(queso.stock_actual, 900)
