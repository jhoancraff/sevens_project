import json
from datetime import timedelta
from decimal import Decimal

from sevens import cierre_turno as ct
from sevens.models import VGCierreCaja, VGConfiguracionCierreTurno, VGCorreccionMetodoPago, VGPago
from sevens.test_cierre_turno import CierreTurnoBase


class Fase3Base(CierreTurnoBase):
    def get(self, usuario, ruta, **params):
        self.client.force_login(usuario)
        return self.client.get(f'/api/{ruta}/', params)

    def post(self, usuario, ruta, cuerpo):
        self.client.force_login(usuario)
        return self.client.post(f'/api/{ruta}/', json.dumps(cuerpo), content_type='application/json')

    def cerrar_caja(self, usuario, fecha=None):
        return self.post(usuario, 'admin/reportes/cuadre-caja', {
            'action': 'cerrar_caja', 'fecha': (fecha or self.hoy).isoformat(),
        })

    def cambiar_cuenta(self, usuario, tipo, registro, metodo):
        return self.post(usuario, 'admin/reportes/cuadre-caja', {
            'action': 'cambiar_metodo_pago', 'fecha': self.hoy.isoformat(), 'tipo': tipo,
            'id': registro.id, 'metodo_pago_id': metodo.id, 'motivo': 'me equivoqué de cuenta',
        })


class CierreDeCajaRequiereTurnosCerradosTests(Fase3Base):
    def test_no_se_cierra_la_caja_si_queda_algo_sin_cerrar_por_turno(self):
        self.pago(self.ana)
        self.pago(self.ana)
        self.propina(self.berta)

        respuesta = self.cerrar_caja(self.admin)
        self.assertEqual(respuesta.status_code, 400)
        datos = respuesta.json()
        self.assertIn('hay 3 transacción(es) sin cierre de turno', datos['message'])
        self.assertIn('ana: 2', datos['message'])
        self.assertIn('berta: 1', datos['message'])
        self.assertEqual(datos['cierre_turno_pendiente']['total'], 3)
        self.assertFalse(VGCierreCaja.objects.exists())

    def test_con_todos_los_turnos_cerrados_la_caja_se_cierra(self):
        self.pago(self.ana)
        self.propina(self.berta)
        self.cerrar(self.ana)
        self.cerrar(self.berta)

        respuesta = self.cerrar_caja(self.admin)
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertTrue(VGCierreCaja.objects.filter(fecha=self.hoy).exists())

    def test_un_administrador_puede_cerrar_el_turno_de_otra_y_asi_destrabar_la_caja(self):
        self.pago(self.ana)
        self.assertEqual(self.cerrar_caja(self.admin).status_code, 400)
        self.cerrar(self.ana, cerrador=self.admin, novedad='Ana se fue de emergencia')
        self.assertEqual(self.cerrar_caja(self.admin).status_code, 201)

    def test_cierre_de_turno_sin_activar_no_bloquea_nada(self):
        VGConfiguracionCierreTurno.objects.all().delete()
        self.pago(self.ana)
        self.assertEqual(self.cerrar_caja(self.admin).status_code, 201)

    def test_los_cobros_por_punto_de_venta_no_cuentan_como_pendientes_de_turno(self):
        self.pago(self.ana, self.pos)
        self.assertEqual(ct.pendientes_para_cierre_de_caja(self.hoy)['total'], 0)

    def test_lo_de_dias_posteriores_no_bloquea_la_caja_de_un_dia_anterior(self):
        ayer = self.hoy - timedelta(days=1)
        self.pago(self.ana, hace_horas=30)  # de ayer
        self.pago(self.berta)  # de hoy
        para_ayer = ct.pendientes_para_cierre_de_caja(ayer)
        self.assertEqual([fila['titular_nombre'] for fila in para_ayer['por_titular']], ['ana'])
        para_hoy = ct.pendientes_para_cierre_de_caja(self.hoy)
        self.assertEqual(para_hoy['total'], 2)

    def test_el_cuadre_avisa_cuantos_turnos_faltan_para_poder_cerrar(self):
        self.pago(self.ana)
        datos = self.get(self.admin, 'admin/reportes/cuadre-caja', fecha=self.hoy.isoformat()).json()
        self.assertTrue(datos['cierre_turno_pendiente']['activo'])
        self.assertEqual(datos['cierre_turno_pendiente']['total'], 1)
        self.assertEqual(datos['cierre_turno_pendiente']['por_titular'][0]['titular_id'], self.ana.id)


class CambioDeCuentaTrasElCierreTests(Fase3Base):
    def test_una_cajera_cambia_la_cuenta_mientras_el_turno_sigue_abierto(self):
        pago = self.pago(self.ana, self.zelle)
        respuesta = self.cambiar_cuenta(self.ana, 'pago', pago, self.pago_movil)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        pago.refresh_from_db()
        self.assertEqual(pago.metodo_pago_id, self.pago_movil.id)

    def test_una_cajera_ya_no_puede_cambiar_la_cuenta_de_algo_que_quedo_en_un_acta(self):
        pago = self.pago(self.ana, self.zelle)
        extra = self.propina(self.ana, metodo=self.zelle)
        cierre = self.cerrar(self.ana)

        for tipo, registro in (('pago', pago), ('ingreso_extra', extra)):
            respuesta = self.cambiar_cuenta(self.ana, tipo, registro, self.pago_movil)
            self.assertEqual(respuesta.status_code, 400)
            self.assertIn(f'CT-{cierre.numero:06d}', respuesta.json()['message'])
            registro.refresh_from_db()
            self.assertEqual(registro.metodo_pago_id, self.zelle.id)
        self.assertFalse(VGCorreccionMetodoPago.objects.exists())

    def test_el_administrador_si_puede_y_queda_marcado_como_modificado(self):
        pago = self.pago(self.ana, self.zelle)
        cierre = self.cerrar(self.ana)

        self.assertEqual(self.cambiar_cuenta(self.admin, 'pago', pago, self.pago_movil).status_code, 200)

        detalle = self.get(self.admin, 'cierre-turno/cierres', cierre_id=cierre.id).json()['cierre']
        self.assertEqual(detalle['con_modificaciones'], 1)
        (cambio,) = detalle['lineas'][0]['modificaciones']
        self.assertEqual(cambio['tipo'], 'cuenta_cambiada')
        self.assertEqual(cambio['detalle'], 'La cuenta pasó de CT Zelle a CT Pago Móvil.')
        self.assertEqual(cambio['por'], 'admin')
        self.assertEqual(cambio['motivo'], 'me equivoqué de cuenta')
        # La foto del acta no se reescribe: sigue diciendo Zelle.
        self.assertEqual(detalle['lineas'][0]['metodo_pago_nombre'], 'CT Zelle')


class ModificadoDespuesDelCierreTests(Fase3Base):
    def test_un_acta_sin_cambios_no_trae_marcas(self):
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        detalle = self.get(self.ana, 'cierre-turno/cierres', cierre_id=cierre.id).json()['cierre']
        self.assertEqual(detalle['con_modificaciones'], 0)
        self.assertEqual(detalle['lineas'][0]['modificaciones'], [])

    def test_un_cobro_anulado_despues_del_cierre_se_marca(self):
        pago = self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        VGPago.objects.filter(pk=pago.pk).update(estado='anulado')

        (cambio,) = self.get(self.ana, 'cierre-turno/cierres', cierre_id=cierre.id).json()['cierre']['lineas'][0]['modificaciones']
        self.assertEqual(cambio['tipo'], 'anulado')

    def test_un_monto_distinto_se_marca(self):
        pago = self.pago(self.ana, monto='10')
        cierre = self.cerrar(self.ana)
        VGPago.objects.filter(pk=pago.pk).update(monto=Decimal('12'))

        (cambio,) = self.get(self.admin, 'cierre-turno/cierres', cierre_id=cierre.id).json()['cierre']['lineas'][0]['modificaciones']
        self.assertEqual(cambio['tipo'], 'monto_distinto')
        self.assertEqual(cambio['detalle'], 'El monto era $10.00 y ahora es $12.00.')

    def test_una_propina_eliminada_se_marca(self):
        extra = self.propina(self.ana)
        cierre = self.cerrar(self.ana)
        extra.delete()

        (cambio,) = self.get(self.admin, 'cierre-turno/cierres', cierre_id=cierre.id).json()['cierre']['lineas'][0]['modificaciones']
        self.assertEqual(cambio['tipo'], 'eliminado')

    def test_el_listado_cuenta_las_lineas_modificadas_de_cada_cierre(self):
        modificado = self.pago(self.ana)
        self.pago(self.ana)
        self.cerrar(self.ana)
        self.pago(self.berta)
        self.cerrar(self.berta)
        VGPago.objects.filter(pk=modificado.pk).update(estado='anulado')

        cierres = self.get(self.admin, 'cierre-turno/cierres').json()['cierres']
        por_titular = {cierre['titular_nombre']: cierre['con_modificaciones'] for cierre in cierres}
        self.assertEqual(por_titular, {'ana': 1, 'berta': 0})
