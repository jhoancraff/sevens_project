"""
Estado de cuenta en PDF del BNC (banco_pdf_bnc.py). Los PDF de prueba se arman aqui imitando la estructura
de Microsoft Reporting Services (el que exporta el BNC), con datos inventados: nunca un estado de cuenta real.
"""
import zlib
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from sevens.banco_excel import ExtractoInvalido, parsear_extracto
from sevens.banco_pdf_bnc import es_cuenta_bnc
from sevens.models import VGMetodoPago, VGMovimientoBancario, VGRol, VGUsuario

CUENTA_BNC = '0191 - 0000 - 00 - 0000000001'
FECHA_X, DESC_X, REF_X, DEB_X, CRE_X, SAL_X = 59.0, 116.0, 300.0, 377.0, 453.0, 512.0


def _escapar(texto):
    return texto.encode('cp1252').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


def _pdf(paginas, cid_textos=()):
    """
    paginas: [[(x, y, texto), ...], ...]. Los textos que esten en `cid_textos` se escriben con una fuente Type0
    (codigos de 2 bytes + /ToUnicode), como hace Reporting Services con las tildes y otras letras.
    """
    objetos = {}
    alfabeto = {}
    for texto in cid_textos:
        for letra in texto:
            alfabeto.setdefault(letra, len(alfabeto) + 3)

    def flujo(numero, datos):
        comprimido = zlib.compress(datos)
        objetos[numero] = b'<< /Filter /FlateDecode /Length %d >>\nstream\n%s\nendstream' % (len(comprimido), comprimido)

    objetos[5] = b'<< /Type /Font /Subtype /TrueType /BaseFont /Tahoma /FirstChar 0 /LastChar 255 >>'
    objetos[6] = b'<< /Type /Font /Subtype /Type0 /BaseFont /ABCDEE+Tahoma /Encoding /Identity-H /ToUnicode 7 0 R >>'
    pares = b''.join(b'<%04X> <%04X>\n' % (codigo, ord(letra)) for letra, codigo in alfabeto.items())
    flujo(7, b'/CIDInit /ProcSet findresource begin\n%d beginbfchar\n%sendbfchar\nend' % (len(alfabeto), pares))

    hijos, numero = [], 20
    for pagina in paginas:
        contenido = b''
        for x, y, texto in pagina:
            if texto in cid_textos:
                cadena = b'<%s>' % b''.join(b'%04X' % alfabeto[letra] for letra in texto)
                fuente = b'/F4'
            else:
                cadena = b'(%s)' % _escapar(texto)
                fuente = b'/F3'
            contenido += b'q 1 0 0 1 0 0 cm BT %s 7.999 Tf 0 0 0 rg 380.167 TL %.3f %.3f Td %s Tj T* ET Q\n' % (fuente, x, y, cadena)
        flujo(numero + 1, contenido)
        objetos[numero] = (
            b'<< /Type /Page /Parent 2 0 R /Resources << /Font << /F3 5 0 R /F4 6 0 R >> >> /Contents %d 0 R >>' % (numero + 1)
        )
        hijos.append(b'%d 0 R' % numero)
        numero += 2
    objetos[1] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objetos[2] = b'<< /Type /Pages /Count %d /Kids [%s] >>' % (len(hijos), b' '.join(hijos))
    return b'%PDF-1.3\r\n' + b''.join(b'%d 0 obj\n%s\nendobj\n' % (n, objetos[n]) for n in sorted(objetos)) + b'%%EOF'


def _fila(y, fecha, descripcion, referencia, monto, saldo, debito=True, x_monto=None):
    celdas = [(FECHA_X, y, fecha), (DESC_X, y, descripcion)]
    if referencia is not None:
        celdas.append((REF_X, y, referencia))
    celdas += [(x_monto or (DEB_X if debito else CRE_X), y, monto), (SAL_X, y, saldo)]
    return celdas


def _encabezado_tabla(y):
    return [(68, y, 'FECHA'), (170, y, 'DESCRIPCIÓN'), (282, y, 'REFERENCIA'), (352, y, 'DÉBITOS'), (421, y, 'CRÉDITOS'), (498, y, 'SALDO')]


def _cabecera_banco(cuenta=CUENTA_BNC):
    return [
        (416, 944, 'ESTADO DE CUENTA'), (258, 879, 'NOMBRE DEL CLIENTE'), (50, 862, 'NEGOCIO DE PRUEBA, C.A.'),
        (85, 718, 'NÚMERO DE LA CUENTA'), (73, 701, cuenta), (99, 667, 'OCTUBRE - 2026'),
    ]


def _resumen(saldo_inicial, saldo_final, filas):
    celdas = [(276, 633, 'RESUMEN'), (51, 616, 'CANTIDAD'), (189, 616, 'DESCRIPCIÓN'), (352, 616, 'DÉBITOS'),
              (421, 616, 'CRÉDITOS'), (498, 616, 'SALDO'), (96, 600, 'Saldo Inicial'), (SAL_X, 600, saldo_inicial)]
    y = 585
    for cantidad, descripcion, monto in filas:
        celdas += [(67, y, str(cantidad)), (96, y, descripcion), (DEB_X, y, monto)]
        y -= 15
    return celdas + [(96, y, 'Saldo Final'), (SAL_X, y, saldo_final)]


def estado_simple(cuenta=CUENTA_BNC, saldo_final='4.590,55', movimientos=None, resumen_cantidades=3, cid=()):
    movimientos = movimientos if movimientos is not None else (
        _fila(465, '31/10/2026', 'Comisión Uso Canal Electronico', '0', '684,00', '4.547,93')
        + _fila(451, '31/10/2026', 'Ints. mensual de su cuenta', '0', '44,86', '4.592,79', debito=False)
        + _fila(437, '31/10/2026', 'Cargo por I.S.L.R. Cuenta', '0', '2,24', '4.590,55')
    )
    pagina = (
        _cabecera_banco(cuenta)
        + _resumen('5.231,93', saldo_final, [(1, 'Comisión', '684,00'), (resumen_cantidades - 1, 'Otros', '47,10')])
        + [(266, 510, 'MOVIMIENTOS')] + _encabezado_tabla(493) + [(116, 479, 'Saldo Inicial'), (SAL_X, 479, '5.231,93')]
        + movimientos + [(37, 43, 'Página: 1 de 1'), (497, 43, 'www.bnc.com.ve')]
    )
    return _pdf([pagina], cid_textos=cid)


class LecturaPdfBncTests(SimpleTestCase):
    def leer(self, contenido):
        return parsear_extracto(contenido, 'Rpt20261125.pdf')

    def test_lee_los_movimientos_con_su_tipo_saldo_y_clase(self):
        resultado = self.leer(estado_simple())
        self.assertEqual(resultado['banco'], 'BNC')
        self.assertEqual(resultado['numero_cuenta'], '01910000000000000001')
        self.assertEqual(
            [(m['fecha'].day, m['tipo'], m['monto'], m['saldo'], m['clase']) for m in resultado['movimientos']],
            [(31, 'debito', Decimal('684.00'), Decimal('4547.93'), 'comision'),
             (31, 'credito', Decimal('44.86'), Decimal('4592.79'), 'otro_credito'),
             (31, 'debito', Decimal('2.24'), Decimal('4590.55'), 'otro_debito')],
        )
        self.assertEqual({m['referencia'] for m in resultado['movimientos']}, {''})  # "0" no es una referencia
        self.assertEqual(resultado['saltos_saldo'], 0)
        self.assertEqual(len({m['huella'] for m in resultado['movimientos']}), 3)

    def test_el_tipo_sale_del_saldo_aunque_un_monto_grande_invada_la_columna_vecina(self):
        movimientos = (
            _fila(465, '02/10/2026', 'TRANSFERENCIA RECIBIDA', '000123456789', '1.234.567,89', '1.239.799,82', debito=False, x_monto=340)
            + _fila(451, '02/10/2026', 'PAGO', '987654', '9.000,00', '1.230.799,82', x_monto=453)
        )
        contenido = estado_simple(movimientos=movimientos, saldo_final='1.230.799,82', resumen_cantidades=2)
        movs = self.leer(contenido)['movimientos']
        self.assertEqual([(m['tipo'], m['referencia']) for m in movs], [('credito', '000123456789'), ('debito', '987654')])

    def test_las_letras_de_una_fuente_con_codigos_propios_se_leen(self):
        contenido = estado_simple(cid=('Comisión Uso Canal Electronico',))
        self.assertEqual(self.leer(contenido)['movimientos'][0]['descripcion'], 'Comisión Uso Canal Electronico')

    def test_una_descripcion_en_dos_renglones_se_une(self):
        movimientos = (
            _fila(465, '31/10/2026', 'Comisión Uso Canal Electronico', '0', '684,00', '4.547,93')
            + [(DESC_X, 456, 'por transferencias')]
            + _fila(441, '31/10/2026', 'Ints. mensual', '0', '44,86', '4.592,79', debito=False)
            + _fila(427, '31/10/2026', 'Cargo por I.S.L.R.', '0', '2,24', '4.590,55')
        )
        movs = self.leer(estado_simple(movimientos=movimientos))['movimientos']
        self.assertEqual(movs[0]['descripcion'], 'Comisión Uso Canal Electronico por transferencias')

    def test_varias_paginas_con_el_encabezado_repetido(self):
        pagina_1 = (
            _cabecera_banco() + _resumen('1.000,00', '1.150,00', [(2, 'Varios', '150,00')]) + [(266, 510, 'MOVIMIENTOS')]
            + _encabezado_tabla(493) + [(116, 479, 'Saldo Inicial'), (SAL_X, 479, '1.000,00')]
            + _fila(465, '01/10/2026', 'PRIMERO', '111', '200,00', '1.200,00', debito=False)
            + [(37, 43, 'Página: 1 de 2'), (497, 43, 'www.bnc.com.ve')]
        )
        pagina_2 = (
            _encabezado_tabla(900) + _fila(880, '02/10/2026', 'SEGUNDO', '222', '50,00', '1.150,00')
            + [(37, 43, 'Página: 2 de 2'), (497, 43, 'www.bnc.com.ve')]
        )
        resultado = self.leer(_pdf([pagina_1, pagina_2]))
        self.assertEqual([(m['descripcion'], m['hoja']) for m in resultado['movimientos']], [('PRIMERO', 'Página 1'), ('SEGUNDO', 'Página 2')])

    def test_otro_banco_en_pdf_se_rechaza(self):
        for contenido in (
            estado_simple(cuenta='0134 - 0000 - 00 - 0000000001'),
            _pdf([[(50, 800, 'FACTURA'), (50, 780, 'Total 100,00')]]),
        ):
            with self.assertRaisesMessage(ExtractoInvalido, 'estado de cuenta del BNC'):
                self.leer(contenido)

    def test_un_pdf_sin_texto_o_con_clave_se_explica(self):
        with self.assertRaisesMessage(ExtractoInvalido, 'no tiene texto'):
            self.leer(_pdf([[]]))
        with self.assertRaisesMessage(ExtractoInvalido, 'contraseña'):
            self.leer(estado_simple() + b'\n/Encrypt 9 0 R')

    def test_un_saldo_que_no_encadena_no_importa_nada(self):
        movimientos = (
            _fila(465, '31/10/2026', 'Comisión', '0', '684,00', '4.547,93')
            + _fila(451, '31/10/2026', 'Intereses', '0', '44,86', '4.600,00', debito=False)
            + _fila(437, '31/10/2026', 'ISLR', '0', '2,24', '4.590,55')
        )
        with self.assertRaisesMessage(ExtractoInvalido, 'El saldo no cuadra'):
            self.leer(estado_simple(movimientos=movimientos))

    def test_si_falta_una_linea_respecto_del_resumen_no_importa_nada(self):
        with self.assertRaisesMessage(ExtractoInvalido, 'indica 4 movimiento(s) y se leyeron 3'):
            self.leer(estado_simple(resumen_cantidades=4))

    def test_si_no_se_llega_al_saldo_final_no_importa_nada(self):
        with self.assertRaisesMessage(ExtractoInvalido, 'saldo final'):
            self.leer(estado_simple(saldo_final='9.999,99'))

    def test_excel_y_csv_siguen_leyendose_como_antes(self):
        csv = 'Fecha;Referencia;Descripcion;Tipo;Monto;Saldo\n01/10/2026;123;PAGO;Credito;10,00;10,00\n'.encode()
        resultado = parsear_extracto(csv, 'plaza.csv')
        self.assertEqual(len(resultado['movimientos']), 1)
        self.assertNotIn('banco', resultado)

    def test_solo_una_cuenta_del_bnc_puede_recibir_el_pdf(self):
        for nombre in ('BNC', 'Bnc Empresa', 'Cuenta BNC 6431', 'Banco Nacional de Crédito'):
            self.assertTrue(es_cuenta_bnc(nombre), nombre)
        for nombre in ('Banco Plaza', 'Banesco', 'Abnco', ''):
            self.assertFalse(es_cuenta_bnc(nombre), nombre)


class SubirPdfBncTests(TestCase):
    BASE = '/api/admin/conciliacion-bancaria/'

    def setUp(self):
        rol, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_user(
            username='bnc_admin', password='claveBnc123', cedula='93100001', email='bnc_admin@test.test', id_role=rol,
        )
        VGMetodoPago.objects.create(nombre='PM BNC', moneda='VES', cuenta_bancaria='BNC Empresa')
        VGMetodoPago.objects.create(nombre='PM Plaza', moneda='VES', cuenta_bancaria='Banco Plaza')
        self.client.force_login(self.admin)

    def subir(self, accion, cuenta='BNC Empresa', contenido=None):
        return self.client.post(self.BASE + 'importar/', {
            'action': accion, 'cuenta': cuenta,
            'archivo': SimpleUploadedFile('Rpt.pdf', contenido or estado_simple(), content_type='application/pdf'),
        })

    def test_vista_previa_e_importacion_del_pdf_y_sin_duplicar(self):
        r = self.subir('preview')
        self.assertEqual(r.status_code, 200, r.content)
        resumen = r.json()['resumen']
        self.assertEqual((resumen['leidos'], resumen['nuevos']), (3, 3))
        self.assertEqual((resumen['debitos'], resumen['creditos']), ('686.24', '44.86'))
        self.assertEqual(VGMovimientoBancario.objects.count(), 0)

        r = self.subir('confirm')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(VGMovimientoBancario.objects.filter(cuenta_bancaria='BNC Empresa').count(), 3)
        self.subir('confirm')
        self.assertEqual(VGMovimientoBancario.objects.count(), 3)

    def test_el_pdf_del_bnc_no_entra_en_la_cuenta_de_otro_banco(self):
        r = self.subir('confirm', cuenta='Banco Plaza')
        self.assertEqual(r.status_code, 400)
        self.assertIn('cuenta del BNC', r.json()['message'])
        self.assertEqual(VGMovimientoBancario.objects.count(), 0)

    def test_un_pdf_de_otro_banco_responde_400_con_la_explicacion(self):
        r = self.subir('preview', contenido=estado_simple(cuenta='0134 - 0000 - 00 - 0000000001'))
        self.assertEqual(r.status_code, 400)
        self.assertIn('estado de cuenta del BNC', r.json()['message'])
