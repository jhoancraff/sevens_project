from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sevens import cierre_turno as ct
from sevens.cierre_turno import CierreTurnoError
from sevens.lotes_pos import asignar_pago_a_lote
from sevens.models import (
    VGCierreTurno,
    VGCliente,
    VGConfiguracionCierreTurno,
    VGIngresoExtra,
    VGMetodoPago,
    VGNotaEntrega,
    VGPago,
    VGRol,
    VGTasaCambio,
    VGUsuario,
)


class CierreTurnoBase(TestCase):
    def setUp(self):
        roles = {
            nombre: VGRol.objects.get_or_create(nombre_role=nombre)[0]
            for nombre in ('Cajera', 'Administrador', 'Contador', 'Mesero')
        }
        self.ana = self._usuario('ana', roles['Cajera'])
        self.berta = self._usuario('berta', roles['Cajera'])
        self.admin = self._usuario('admin', roles['Administrador'])
        self.contador = self._usuario('conta', roles['Contador'])
        self.mesero = self._usuario('mesero', roles['Mesero'])

        self.efectivo = VGMetodoPago.objects.create(nombre='CT Efectivo USD', moneda='USD', es_efectivo=True)
        self.pago_movil = VGMetodoPago.objects.create(nombre='CT Pago Móvil', moneda='VES', cuenta_bancaria='Banesco')
        self.zelle = VGMetodoPago.objects.create(nombre='CT Zelle', moneda='USD')
        self.pos = VGMetodoPago.objects.create(
            nombre='CT Punto Banesco', moneda='VES', cuenta_bancaria='Banesco', es_punto_venta=True,
        )
        self.cliente = VGCliente.objects.create(nombre='Pedro', apellido='Pérez')
        VGTasaCambio.objects.create(fecha=timezone.localdate(), tasa=Decimal('100.0000'))

        self.hoy = timezone.localdate()
        self.ahora = timezone.now()
        # Activado desde hace 2 dias para poder simular transacciones "viejas".
        ct.activar_cierre_turno(self.admin, self.hoy - timedelta(days=2))

    def _usuario(self, username, rol):
        return VGUsuario.objects.create_user(
            username=username, password=None, cedula=f'V{abs(hash(username)) % 10**7}',
            email=f'{username}@sevens.test', id_role=rol,
        )

    def nota(self):
        return VGNotaEntrega.objects.create(
            cliente=self.cliente, metodo_pago=self.efectivo, total=Decimal('40'), saldo_pendiente=Decimal('40'),
            estado='pendiente_pago', tasa_cambio_referencia=Decimal('100.0000'),
        )

    def pago(self, usuario, metodo=None, monto='10', referencia='', hace_horas=0, tasa='100.0000'):
        metodo = metodo or self.efectivo
        pago = VGPago.objects.create(
            nota_entrega=self.nota(), monto=Decimal(monto), metodo_pago=metodo, estado='completado',
            tasa_cambio_referencia=Decimal(tasa), referencia=referencia, creado_por=usuario,
        )
        if metodo.es_punto_venta:
            asignar_pago_a_lote(pago, usuario)
        if hace_horas:
            VGPago.objects.filter(pk=pago.pk).update(fecha_pago=timezone.now() - timedelta(hours=hace_horas))
            pago.refresh_from_db()
        return pago

    def propina(self, usuario, monto='2', metodo=None, tipo='propina', hace_horas=0):
        extra = VGIngresoExtra.objects.create(
            tipo=tipo, monto=Decimal(monto), metodo_pago=metodo or self.efectivo, creado_por=usuario,
            descripcion='nota' if tipo == 'ingreso_no_facturado' else '',
        )
        if hace_horas:
            VGIngresoExtra.objects.filter(pk=extra.pk).update(fecha_creacion=timezone.now() - timedelta(hours=hace_horas))
        return extra

    def lineas(self, titular, estado='confirmada', cambios=None):
        """Todas las pendientes del titular con `estado`; `cambios` = {(origen, id): (estado, nota)}."""
        cambios = cambios or {}
        resultado = []
        for linea in ct.listar_pendientes(titular):
            clave = (linea['origen'], linea['origen_id'])
            est, nota = cambios.get(clave, (estado, ''))
            resultado.append({'origen': clave[0], 'id': clave[1], 'estado': est, 'nota': nota})
        return resultado

    def cerrar(self, titular, cerrador=None, novedad='', **kwargs):
        return ct.cerrar_turno(titular, cerrador or titular, self.lineas(titular), novedad, **kwargs)


class ConfiguracionTests(CierreTurnoBase):
    def test_nace_inactivo_y_sin_pendientes(self):
        VGConfiguracionCierreTurno.objects.all().delete()
        pago = self.pago(self.ana)
        self.assertFalse(VGConfiguracionCierreTurno.obtener_config().activo)
        self.assertEqual(ct.listar_pendientes(self.ana), [])
        self.assertEqual(ct.resumen_pendientes(), [])
        with self.assertRaisesMessage(CierreTurnoError, 'todavía no está activado'):
            ct.cerrar_turno(self.ana, self.ana, [{'origen': 'pago', 'id': pago.id, 'estado': 'confirmada'}])

    def test_solo_admin_o_contador_activan_y_una_sola_vez(self):
        VGConfiguracionCierreTurno.objects.all().delete()
        with self.assertRaises(CierreTurnoError):
            ct.activar_cierre_turno(self.ana)
        ct.activar_cierre_turno(self.contador)
        with self.assertRaisesMessage(CierreTurnoError, 'ya está activo'):
            ct.activar_cierre_turno(self.admin)

    def test_umbral_por_defecto_20_horas_y_se_puede_cambiar(self):
        self.assertEqual(VGConfiguracionCierreTurno.obtener_config().umbral_tardio_horas, 20)
        with self.assertRaises(CierreTurnoError):
            ct.actualizar_umbral_tardio(self.ana, 8)
        with self.assertRaises(CierreTurnoError):
            ct.actualizar_umbral_tardio(self.admin, 0)
        ct.actualizar_umbral_tardio(self.admin, 8)
        self.assertEqual(VGConfiguracionCierreTurno.obtener_config().umbral_tardio_horas, 8)

    def test_lo_anterior_a_la_fecha_de_activacion_no_cuenta(self):
        self.pago(self.ana, hace_horas=24 * 5)
        self.assertEqual(ct.listar_pendientes(self.ana), [])


class PendientesTests(CierreTurnoBase):
    def test_solo_lo_propio_completado_y_que_no_es_pos(self):
        propio = self.pago(self.ana, self.zelle)
        self.pago(self.berta, self.zelle)
        anulado = self.pago(self.ana)
        VGPago.objects.filter(pk=anulado.pk).update(estado='anulado')
        self.pago(self.ana, self.pos)  # POS: lo cubre el lote
        extra = self.propina(self.ana)
        self.propina(self.ana, tipo='ingreso_no_facturado')  # administrativo: no entra

        claves = {(l['origen'], l['origen_id']) for l in ct.listar_pendientes(self.ana)}
        self.assertEqual(claves, {('pago', propio.id), ('ingreso_extra', extra.id)})

    def test_resumen_dice_quien_tiene_pendientes_y_desde_cuando(self):
        self.pago(self.ana, hace_horas=5)
        self.pago(self.ana)
        self.propina(self.berta)
        resumen = {fila['titular_nombre']: fila for fila in ct.resumen_pendientes()}
        self.assertEqual(resumen['ana']['cantidad'], 2)
        self.assertEqual(resumen['berta']['cantidad'], 1)
        self.assertGreaterEqual(resumen['ana']['horas_pendiente'], 5)
        self.assertEqual(ct.resumen_pendientes()[0]['titular_nombre'], 'ana')  # la mas vieja primero

    def test_la_linea_pago_movil_trae_los_bs_con_su_tasa_congelada(self):
        pago = self.pago(self.ana, self.pago_movil, monto='12', referencia='4471', tasa='105.0000')
        linea = ct.listar_pendientes(self.ana)[0]
        self.assertEqual(linea['monto_bs'], Decimal('1260.00'))
        self.assertEqual(linea['referencia'], '4471')
        self.assertEqual(linea['cliente'], 'Pedro Pérez')
        self.assertTrue(linea['documento'].startswith('Nota '))
        self.assertEqual(linea['origen_id'], pago.id)


class CerrarTurnoTests(CierreTurnoBase):
    def test_cierre_normal_guarda_acta_marca_las_transacciones_y_no_toca_las_de_otra(self):
        p1 = self.pago(self.ana, self.efectivo)
        p2 = self.pago(self.ana, self.pago_movil, monto='12', referencia='4471')
        p3 = self.pago(self.ana, self.zelle)
        extra = self.propina(self.ana)
        de_berta = self.pago(self.berta)

        cierre = ct.cerrar_turno(
            self.ana, self.ana,
            [
                {'origen': 'pago', 'id': p1.id, 'estado': 'confirmada'},
                {'origen': 'pago', 'id': p2.id, 'estado': 'no_llego', 'nota': 'ref 4471 no aparece'},
                {'origen': 'pago', 'id': p3.id, 'estado': 'confirmada'},
                {'origen': 'ingreso_extra', 'id': extra.id, 'estado': 'confirmada'},
            ],
            'Un pago móvil sin acreditar',
        )

        self.assertEqual(cierre.tipo, 'normal')
        self.assertEqual(cierre.numero, 1)
        self.assertEqual((cierre.total_lineas, cierre.total_confirmadas, cierre.total_no_llegaron), (4, 3, 1))
        self.assertEqual((cierre.titular, cierre.cerrado_por), (self.ana, self.ana))
        self.assertEqual(cierre.titular_rol, 'Cajera')
        self.assertEqual(cierre.novedad, 'Un pago móvil sin acreditar')

        linea = cierre.lineas.get(origen_id=p2.id, origen='pago')
        self.assertEqual(linea.estado, 'no_llego')
        self.assertEqual(linea.nota, 'ref 4471 no aparece')
        self.assertEqual(linea.monto_bs, Decimal('1200.00'))
        self.assertEqual(linea.metodo_pago_nombre, 'CT Pago Móvil')

        for pago in (p1, p2, p3):
            pago.refresh_from_db()
            self.assertEqual(pago.cierre_turno_id, cierre.id)
        extra.refresh_from_db()
        self.assertEqual(extra.cierre_turno_id, cierre.id)
        de_berta.refresh_from_db()
        self.assertIsNone(de_berta.cierre_turno_id)
        self.assertEqual(ct.listar_pendientes(self.ana), [])
        self.assertEqual(len(ct.listar_pendientes(self.berta)), 1)

    def test_el_siguiente_cierre_arranca_vacio_y_con_el_numero_que_sigue(self):
        self.pago(self.ana)
        primero = self.cerrar(self.ana)
        self.assertEqual(ct.listar_pendientes(self.ana), [])
        self.pago(self.ana)
        segundo = self.cerrar(self.ana)
        self.assertEqual((primero.numero, segundo.numero), (1, 2))
        self.assertEqual(segundo.total_lineas, 1)

    def test_sin_novedad_se_puede_cerrar_si_todo_llego_y_es_normal(self):
        self.pago(self.ana)
        cierre = self.cerrar(self.ana)
        self.assertEqual(cierre.novedad, '')

    def test_no_llego_exige_nota_y_novedad(self):
        pago = self.pago(self.ana, self.pago_movil)
        with self.assertRaisesMessage(CierreTurnoError, 'Explica en una nota'):
            ct.cerrar_turno(self.ana, self.ana, [{'origen': 'pago', 'id': pago.id, 'estado': 'no_llego'}], 'x')
        with self.assertRaisesMessage(CierreTurnoError, 'novedad es obligatoria'):
            ct.cerrar_turno(
                self.ana, self.ana, [{'origen': 'pago', 'id': pago.id, 'estado': 'no_llego', 'nota': 'no aparece'}],
            )
        self.assertEqual(VGCierreTurno.objects.count(), 0)
        pago.refresh_from_db()
        self.assertIsNone(pago.cierre_turno_id)

    def test_marcar_no_llego_no_altera_el_pago(self):
        pago = self.pago(self.ana, self.pago_movil)
        ct.cerrar_turno(
            self.ana, self.ana, [{'origen': 'pago', 'id': pago.id, 'estado': 'no_llego', 'nota': 'n'}], 'novedad',
        )
        pago.refresh_from_db()
        self.assertEqual(pago.estado, 'completado')
        self.assertEqual(pago.metodo_pago_id, self.pago_movil.id)

    def test_no_se_puede_dejar_afuera_una_transaccion_pendiente(self):
        p1 = self.pago(self.ana)
        self.pago(self.ana)
        with self.assertRaisesMessage(CierreTurnoError, 'Faltan 1'):
            ct.cerrar_turno(self.ana, self.ana, [{'origen': 'pago', 'id': p1.id, 'estado': 'confirmada'}])
        self.assertEqual(VGCierreTurno.objects.count(), 0)

    def test_lo_registrado_despues_del_corte_queda_pendiente(self):
        self.pago(self.ana)
        detalle = ct.detalle_pendientes(self.ana, self.ana)
        nueva = self.pago(self.ana)  # llega mientras ella revisaba
        lineas = [
            {'origen': l['origen'], 'id': l['origen_id'], 'estado': 'confirmada'} for l in detalle['lineas']
        ]
        cierre = ct.cerrar_turno(self.ana, self.ana, lineas, corte=detalle['corte'])
        self.assertEqual(cierre.total_lineas, 1)
        nueva.refresh_from_db()
        self.assertIsNone(nueva.cierre_turno_id)
        self.assertEqual(len(ct.listar_pendientes(self.ana)), 1)

    def test_doble_clic_no_duplica_el_cierre(self):
        self.pago(self.ana)
        lineas = self.lineas(self.ana)
        ct.cerrar_turno(self.ana, self.ana, lineas)
        with self.assertRaisesMessage(CierreTurnoError, 'ya no están pendientes'):
            ct.cerrar_turno(self.ana, self.ana, lineas)
        self.assertEqual(VGCierreTurno.objects.count(), 1)

    def test_no_se_puede_cerrar_con_transacciones_de_otra_persona_como_si_fueran_del_titular(self):
        ajena = self.pago(self.berta)
        propia = self.pago(self.ana)
        with self.assertRaisesMessage(CierreTurnoError, 'no son de ana'):
            ct.cerrar_turno(self.ana, self.ana, [
                {'origen': 'pago', 'id': propia.id, 'estado': 'confirmada'},
                {'origen': 'pago', 'id': ajena.id, 'estado': 'confirmada'},
            ])

    def test_entradas_mal_formadas_se_rechazan(self):
        pago = self.pago(self.ana)
        base = {'origen': 'pago', 'id': pago.id, 'estado': 'confirmada'}
        for malas in (
            [], [{**base, 'estado': 'quizas'}], [{**base, 'origen': 'factura'}], [{**base, 'id': 'abc'}], [base, base],
        ):
            with self.assertRaises(CierreTurnoError):
                ct.cerrar_turno(self.ana, self.ana, malas, 'x')

    def test_lote_pos_abierto_con_cobros_del_titular_bloquea_el_cierre(self):
        self.pago(self.ana, self.zelle)
        pago_pos = self.pago(self.ana, self.pos)
        with self.assertRaisesMessage(CierreTurnoError, 'cerrar el lote POS'):
            self.cerrar(self.ana)
        from sevens.lotes_pos import cerrar_lote
        cerrar_lote(pago_pos.lote_pos, self.ana)
        self.assertEqual(self.cerrar(self.ana).total_lineas, 1)

    def test_un_lote_pos_con_cobros_solo_de_otra_no_bloquea(self):
        self.pago(self.berta, self.pos)
        self.pago(self.ana, self.zelle)
        self.assertEqual(self.cerrar(self.ana).total_lineas, 1)

    def test_quien_no_cobra_no_cierra(self):
        pago = self.pago(self.ana)
        with self.assertRaisesMessage(CierreTurnoError, 'No tienes permiso'):
            ct.cerrar_turno(self.ana, self.mesero, [{'origen': 'pago', 'id': pago.id, 'estado': 'confirmada'}], 'x')

    def test_lo_confirmado_no_cambia_si_despues_se_anula_el_pago(self):
        pago = self.pago(self.ana, self.zelle, monto='25')
        cierre = self.cerrar(self.ana)
        VGPago.objects.filter(pk=pago.pk).update(estado='anulado', metodo_pago=self.efectivo)
        linea = cierre.lineas.get()
        self.assertEqual(linea.estado, 'confirmada')
        self.assertEqual(linea.monto_usd, Decimal('25'))
        self.assertEqual(linea.metodo_pago_nombre, 'CT Zelle')


class TiposDeCierreTests(CierreTurnoBase):
    def test_cierre_propio_pasado_el_umbral_es_tardio_y_pide_novedad(self):
        self.pago(self.ana, hace_horas=21)
        with self.assertRaisesMessage(CierreTurnoError, 'tardío'):
            self.cerrar(self.ana)
        cierre = self.cerrar(self.ana, novedad='Volví al día siguiente')
        self.assertEqual(cierre.tipo, 'tardio')

    def test_justo_dentro_del_umbral_sigue_siendo_normal(self):
        self.pago(self.ana, hace_horas=16)  # doble turno de 7am a 11pm
        self.assertEqual(self.cerrar(self.ana).tipo, 'normal')

    def test_el_umbral_cambiado_se_respeta(self):
        ct.actualizar_umbral_tardio(self.admin, 8)
        self.pago(self.ana, hace_horas=9)
        self.assertEqual(self.cerrar(self.ana, novedad='tarde').tipo, 'tardio')

    def test_cierra_otra_persona_es_por_tercero_con_ambos_nombres(self):
        self.pago(self.ana)
        self.pago(self.ana, self.pago_movil)
        with self.assertRaisesMessage(CierreTurnoError, 'otra persona'):
            self.cerrar(self.ana, self.berta)
        cierre = self.cerrar(self.ana, self.berta, novedad='Ana salió de emergencia a las 12:30')
        self.assertEqual(cierre.tipo, 'por_tercero')
        self.assertEqual((cierre.titular, cierre.cerrado_por), (self.ana, self.berta))
        self.assertEqual((cierre.titular_nombre, cierre.cerrado_por_nombre), ('ana', 'berta'))
        self.assertEqual(VGPago.objects.filter(cierre_turno=cierre, creado_por=self.ana).count(), 2)

    def test_los_tres_roles_son_titulares_y_pueden_cerrar_por_otro(self):
        for titular in (self.admin, self.contador, self.ana):
            self.pago(titular, self.zelle)
            self.assertEqual(self.cerrar(titular).tipo, 'normal')

        casos = ((self.ana, self.admin), (self.admin, self.contador), (self.contador, self.ana))
        for titular, cerrador in casos:
            self.pago(titular, self.zelle)
            cierre = self.cerrar(titular, cerrador, novedad='se fue')
            self.assertEqual(cierre.tipo, 'por_tercero')
            self.assertEqual(cierre.cerrado_por, cerrador)

    def test_despues_de_que_otro_cerro_por_ella_su_siguiente_cierre_es_normal(self):
        # Ana cobra a las 12:30, no cierra; Berta cierra por ella; luego Ana cobra y cierra normal.
        self.pago(self.ana, hace_horas=3)
        self.cerrar(self.ana, self.berta, novedad='emergencia')
        self.pago(self.ana)
        self.assertEqual(self.cerrar(self.ana).tipo, 'normal')

    def test_detalle_anticipa_el_tipo_sin_cerrar_nada(self):
        self.pago(self.ana, hace_horas=25)
        self.assertEqual(ct.detalle_pendientes(self.ana, self.ana)['tipo'], 'tardio')
        self.assertEqual(ct.detalle_pendientes(self.ana, self.berta)['tipo'], 'por_tercero')
        self.assertEqual(VGCierreTurno.objects.count(), 0)
