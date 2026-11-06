import json
from unittest.mock import patch

from sevens import cierre_turno as ct
from sevens.impresion_lpd import _build_acta_cierre_turno_bytes, imprimir_acta_cierre_turno
from sevens.models import VGImpresoraCaja, VGPago
from sevens.pdf_reportes import generar_pdf_acta_cierre_turno
from sevens.test_cierre_turno import CierreTurnoBase


class Fase4Base(CierreTurnoBase):
    def get(self, usuario, ruta, **params):
        self.client.force_login(usuario)
        return self.client.get(f'/api/{ruta}/', params)

    def post(self, usuario, ruta, cuerpo):
        self.client.force_login(usuario)
        return self.client.post(f'/api/{ruta}/', json.dumps(cuerpo), content_type='application/json')

    def cierre_con_de_todo(self):
        """Un cierre por otra persona con un pago movil, una propina, y un cobro que no llego."""
        movil = self.pago(self.ana, self.pago_movil, referencia='4471')
        efectivo = self.pago(self.ana)
        propina = self.propina(self.ana, '3')
        return ct.cerrar_turno(
            self.ana, self.admin,
            [
                {'origen': 'pago', 'id': movil.id, 'estado': 'no_llego', 'nota': 'no aparece en el banco'},
                {'origen': 'pago', 'id': efectivo.id, 'estado': 'confirmada'},
                {'origen': 'ingreso_extra', 'id': propina.id, 'estado': 'confirmada'},
            ],
            'Ana salió de emergencia',
        ), movil


class TicketTermicoTests(Fase4Base):
    def test_el_ticket_trae_el_acta_completa(self):
        cierre, _ = self.cierre_con_de_todo()
        ticket = _build_acta_cierre_turno_bytes(ct.datos_del_acta(cierre))

        for texto in (cierre.codigo, 'ACTA DE CIERRE DE TURNO', 'Turno de: ana', 'Cerro: admin', 'CT Pago M', 'Ref:4471',
                      '*** NO LLEGO ***', 'Nota: no aparece en el banco', 'NOVEDAD', 'Ana sali', 'No llegaron'):
            self.assertIn(texto.encode('cp1252'), ticket, texto)
        # Pago movil en bolivares (10 USD a 100 Bs), no en dolares.
        self.assertIn(b'Bs.1.000,00', ticket)
        self.assertNotIn(b'REIMPRESION', ticket)

    def test_la_reimpresion_lo_dice_y_lo_modificado_se_advierte(self):
        cierre, movil = self.cierre_con_de_todo()
        VGPago.objects.filter(pk=movil.pk).update(estado='anulado')
        ticket = _build_acta_cierre_turno_bytes(ct.datos_del_acta(cierre), es_reimpresion=True)
        self.assertIn(b'(REIMPRESION)', ticket)
        self.assertIn(b'MODIFICADO DESPUES DEL CIERRE', ticket)

    def test_un_cierre_normal_sin_novedad_dice_sin_novedad(self):
        self.pago(self.ana)
        ticket = _build_acta_cierre_turno_bytes(ct.datos_del_acta(self.cerrar(self.ana)))
        self.assertIn(b'Sin novedad.', ticket)
        self.assertNotIn(b'Cerro:', ticket)

    def test_sin_impresora_configurada_devuelve_el_motivo_sin_lanzar(self):
        self.pago(self.ana)
        exito, motivo = imprimir_acta_cierre_turno(self.cerrar(self.ana))
        self.assertFalse(exito)
        self.assertIn('impresora de caja', motivo)

    def test_con_impresora_configurada_envia_el_trabajo(self):
        VGImpresoraCaja.objects.create(ip='127.0.0.1', puerto=515, cola='caja', activo=True)
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        with patch('sevens.impresion_lpd.enviar_trabajo_lpd') as enviar:
            exito, motivo = imprimir_acta_cierre_turno(cierre)
        self.assertTrue(exito, motivo)
        self.assertIn(cierre.codigo.encode(), enviar.call_args.args[3])
        self.assertEqual(enviar.call_args.kwargs['nombre_trabajo'], f'Acta de turno {cierre.codigo}')


class ImpresionAlCerrarTests(Fase4Base):
    def cerrar_por_api(self, usuario):
        detalle = self.get(usuario, 'cierre-turno/pendientes').json()
        return self.post(usuario, 'cierre-turno/cerrar', {
            'corte': detalle['corte'],
            'lineas': [{'origen': l['origen'], 'id': l['origen_id'], 'estado': 'confirmada'} for l in detalle['lineas']],
        })

    def test_al_cerrar_se_imprime_el_acta(self):
        self.pago(self.ana)
        with patch('sevens.cierre_turno_views.imprimir_acta_cierre_turno', return_value=(True, None)) as impresora:
            respuesta = self.cerrar_por_api(self.ana)
        self.assertEqual(respuesta.status_code, 201)
        impresora.assert_called_once()
        self.assertTrue(respuesta.json()['impresion']['ok'])
        self.assertIn('Acta enviada a la impresora', respuesta.json()['message'])

    def test_un_fallo_de_impresora_no_deshace_el_cierre(self):
        pago = self.pago(self.ana)
        with patch('sevens.cierre_turno_views.imprimir_acta_cierre_turno', return_value=(False, 'sin impresora')):
            respuesta = self.cerrar_por_api(self.ana)
        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(respuesta.json()['impresion']['ok'])
        self.assertIn('No se pudo imprimir el acta: sin impresora', respuesta.json()['message'])
        pago.refresh_from_db()
        self.assertIsNotNone(pago.cierre_turno_id)

    def test_una_excepcion_al_imprimir_tampoco_tumba_el_cierre(self):
        pago = self.pago(self.ana)
        with patch('sevens.cierre_turno_views.imprimir_acta_cierre_turno', side_effect=RuntimeError('boom')):
            respuesta = self.cerrar_por_api(self.ana)
        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(respuesta.json()['impresion']['ok'])
        pago.refresh_from_db()
        self.assertIsNotNone(pago.cierre_turno_id)

    def test_reimprimir_marca_el_ticket_como_reimpresion(self):
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        with patch('sevens.cierre_turno_views.imprimir_acta_cierre_turno', return_value=(True, None)) as impresora:
            respuesta = self.post(self.ana, 'cierre-turno/imprimir', {'cierre_id': cierre.id})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(impresora.call_args.kwargs['es_reimpresion'])

    def test_reimprimir_con_la_impresora_caida_da_502_con_el_motivo(self):
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        with patch('sevens.cierre_turno_views.imprimir_acta_cierre_turno', return_value=(False, 'sin impresora')):
            respuesta = self.post(self.ana, 'cierre-turno/imprimir', {'cierre_id': cierre.id})
        self.assertEqual(respuesta.status_code, 502)
        self.assertEqual(respuesta.json()['message'], 'sin impresora')

    def test_una_cajera_no_reimprime_el_acta_de_otra(self):
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        self.assertEqual(self.post(self.berta, 'cierre-turno/imprimir', {'cierre_id': cierre.id}).status_code, 404)
        self.assertEqual(self.post(self.mesero, 'cierre-turno/imprimir', {'cierre_id': cierre.id}).status_code, 401)


class ActaPdfTests(Fase4Base):
    def test_el_pdf_se_descarga_con_su_nombre(self):
        cierre, _ = self.cierre_con_de_todo()
        respuesta = self.get(self.admin, 'cierre-turno/acta-pdf', cierre_id=cierre.id)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertIn(f'acta-cierre-turno-{cierre.codigo}.pdf', respuesta['Content-Disposition'])
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_el_titular_baja_su_acta_pero_otra_cajera_no(self):
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        self.assertEqual(self.get(self.ana, 'cierre-turno/acta-pdf', cierre_id=cierre.id).status_code, 200)
        self.assertEqual(self.get(self.berta, 'cierre-turno/acta-pdf', cierre_id=cierre.id).status_code, 404)
        self.assertEqual(self.get(self.mesero, 'cierre-turno/acta-pdf', cierre_id=cierre.id).status_code, 401)
        self.assertEqual(self.get(self.ana, 'cierre-turno/acta-pdf', cierre_id=99999).status_code, 404)

    def test_el_pdf_sirve_con_muchas_transacciones_y_con_cambios_posteriores(self):
        for _ in range(45):
            self.pago(self.ana, self.pago_movil, referencia='123')
        cierre = self.cerrar(self.ana)
        VGPago.objects.filter(cierre_turno=cierre).update(estado='anulado')
        pdf = generar_pdf_acta_cierre_turno(ct.datos_del_acta(cierre))
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 3000)

    def test_el_pdf_de_un_cierre_con_texto_de_usuario_raro_no_falla(self):
        pago = self.pago(self.ana)
        cierre = ct.cerrar_turno(
            self.ana, self.ana,
            [{'origen': 'pago', 'id': pago.id, 'estado': 'no_llego', 'nota': '<b>tag</b> & "comillas"'}],
            'novedad <i>sin cerrar & más',
        )
        self.assertTrue(generar_pdf_acta_cierre_turno(ct.datos_del_acta(cierre)).startswith(b'%PDF'))
