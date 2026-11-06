import json

from sevens import cierre_turno as ct
from sevens.models import VGConfiguracionCierreTurno
from sevens.test_cierre_turno import CierreTurnoBase


class CierreTurnoApiTests(CierreTurnoBase):
    """Los endpoints usan el servicio y los mismos tres roles; aqui se prueba permisos, forma de la respuesta y alcance."""

    def get(self, usuario, nombre, **params):
        self.client.force_login(usuario)
        return self.client.get(f'/api/{nombre}/', params)

    def post(self, usuario, nombre, cuerpo):
        self.client.force_login(usuario)
        return self.client.post(f'/api/{nombre}/', json.dumps(cuerpo), content_type='application/json')

    def test_quien_no_cobra_no_entra_a_ningun_endpoint(self):
        for nombre in ('cierre-turno/estado', 'cierre-turno/pendientes', 'cierre-turno/cierres'):
            self.assertEqual(self.get(self.mesero, nombre).status_code, 401)
        self.assertEqual(self.post(self.mesero, 'cierre-turno/cerrar', {'lineas': []}).status_code, 401)

    def test_estado_muestra_mis_pendientes_y_los_ajenos(self):
        self.pago(self.ana)
        self.pago(self.ana)
        self.pago(self.berta, hace_horas=3)
        datos = self.get(self.ana, 'cierre-turno/estado').json()
        self.assertTrue(datos['activo'])
        self.assertEqual(datos['mis_pendientes'], 2)
        self.assertEqual([fila['titular_nombre'] for fila in datos['pendientes_ajenos']], ['berta'])
        self.assertEqual(datos['pendientes_ajenos'][0]['cantidad'], 1)

    def test_pendientes_de_otra_persona_anticipa_el_tipo_por_tercero(self):
        self.pago(self.ana, self.pago_movil, referencia='4471')
        datos = self.get(self.berta, 'cierre-turno/pendientes', titular_id=self.ana.id).json()
        self.assertEqual(datos['tipo'], 'por_tercero')
        self.assertFalse(datos['es_propio'])
        self.assertEqual(datos['titular']['nombre'], 'ana')
        self.assertEqual(datos['lineas'][0]['referencia'], '4471')
        self.assertEqual(datos['lineas'][0]['monto_bs'], '1000.00')
        propio = self.get(self.ana, 'cierre-turno/pendientes').json()
        self.assertTrue(propio['es_propio'])
        self.assertEqual(propio['tipo'], 'normal')

    def test_pendientes_avisa_los_lotes_pos_que_bloquean(self):
        self.pago(self.ana, self.pos)
        datos = self.get(self.ana, 'cierre-turno/pendientes').json()
        self.assertEqual(datos['lotes_pos_abiertos'][0]['metodo_pago_nombre'], 'CT Punto Banesco')

    def test_titular_inexistente_da_404(self):
        self.assertEqual(self.get(self.ana, 'cierre-turno/pendientes', titular_id=99999).status_code, 404)

    def test_cerrar_devuelve_el_acta_y_un_error_claro_si_falta_algo(self):
        pago = self.pago(self.ana, self.pago_movil)
        detalle = self.get(self.ana, 'cierre-turno/pendientes').json()
        fallo = self.post(self.ana, 'cierre-turno/cerrar', {'lineas': [], 'corte': detalle['corte']})
        self.assertEqual(fallo.status_code, 400)
        self.assertIn('No hay transacciones', fallo.json()['message'])

        ok = self.post(self.ana, 'cierre-turno/cerrar', {
            'corte': detalle['corte'],
            'novedad': 'no apareció',
            'lineas': [{'origen': 'pago', 'id': pago.id, 'estado': 'no_llego', 'nota': 'ref no aparece'}],
        })
        self.assertEqual(ok.status_code, 201)
        cierre = ok.json()['cierre']
        self.assertEqual(cierre['codigo'], 'CT-000001')
        self.assertEqual(cierre['total_no_llegaron'], 1)
        self.assertEqual(cierre['lineas'][0]['estado'], 'no_llego')
        self.assertEqual(cierre['lineas'][0]['nota'], 'ref no aparece')

    def test_cerrar_por_otra_persona_por_api(self):
        pago = self.pago(self.ana)
        respuesta = self.post(self.admin, 'cierre-turno/cerrar', {
            'titular_id': self.ana.id, 'novedad': 'Ana se fue',
            'lineas': [{'origen': 'pago', 'id': pago.id, 'estado': 'confirmada'}],
        })
        self.assertEqual(respuesta.status_code, 201)
        cierre = respuesta.json()['cierre']
        self.assertEqual(
            (cierre['tipo'], cierre['titular_nombre'], cierre['cerrado_por_nombre']), ('por_tercero', 'ana', 'admin'),
        )

    def test_historial_una_cajera_solo_ve_los_suyos_y_el_admin_todos(self):
        self.pago(self.ana)
        self.cerrar(self.ana)
        self.pago(self.berta)
        cierre_berta = self.cerrar(self.berta)

        de_ana = self.get(self.ana, 'cierre-turno/cierres').json()['cierres']
        self.assertEqual([c['titular_nombre'] for c in de_ana], ['ana'])
        self.assertEqual(self.get(self.ana, 'cierre-turno/cierres', cierre_id=cierre_berta.id).status_code, 404)

        todos = self.get(self.admin, 'cierre-turno/cierres').json()
        self.assertEqual({c['titular_nombre'] for c in todos['cierres']}, {'ana', 'berta'})
        detalle = self.get(self.contador, 'cierre-turno/cierres', cierre_id=cierre_berta.id).json()['cierre']
        self.assertEqual(len(detalle['lineas']), 1)

    def test_historial_filtra_por_tipo_y_por_no_llegaron(self):
        a = self.pago(self.ana, self.pago_movil)
        ct.cerrar_turno(self.ana, self.ana, [{'origen': 'pago', 'id': a.id, 'estado': 'no_llego', 'nota': 'n'}], 'nov')
        self.pago(self.berta)
        self.cerrar(self.berta)
        solo = self.get(self.admin, 'cierre-turno/cierres', con_no_llegaron='1').json()['cierres']
        self.assertEqual([c['titular_nombre'] for c in solo], ['ana'])
        self.assertEqual(self.get(self.admin, 'cierre-turno/cierres', tipo='por_tercero').json()['cierres'], [])
        self.assertEqual(self.get(self.admin, 'cierre-turno/cierres', tipo='raro').status_code, 400)

    def test_configuracion_solo_para_admin_contador_o_dueno(self):
        VGConfiguracionCierreTurno.objects.all().delete()
        self.assertEqual(self.get(self.ana, 'admin/cierre-turno/config').status_code, 401)
        self.assertEqual(self.post(self.ana, 'admin/cierre-turno/config', {'action': 'activar'}).status_code, 401)
        self.assertEqual(self.post(self.contador, 'admin/cierre-turno/config', {'action': 'activar'}).status_code, 200)
        self.assertEqual(self.post(self.admin, 'admin/cierre-turno/config', {'action': 'activar'}).status_code, 400)
        cambio = self.post(self.admin, 'admin/cierre-turno/config', {'action': 'umbral', 'horas': 12}).json()
        self.assertEqual(cambio['umbral_tardio_horas'], 12)
        self.assertEqual(
            self.post(self.admin, 'admin/cierre-turno/config', {'action': 'umbral', 'horas': 0}).status_code, 400,
        )
