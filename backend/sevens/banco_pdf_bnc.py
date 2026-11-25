"""
Lectura del estado de cuenta en PDF del BNC (Banco Nacional de Credito) para la conciliacion bancaria.

Solo el BNC: su banca en linea exporta un PDF generado con Microsoft Reporting Services, con TEXTO real (no
es una foto), asi que se lee con la libreria estandar (zlib + expresiones regulares), igual que
banco_excel.py lee el .xlsx sin dependencias. Cualquier otro PDF se rechaza; para los demas bancos se sigue
usando .xlsx / .csv.

El PDF trae, ademas del encabezado con el numero de cuenta (0191-...), un RESUMEN (saldo inicial, una fila
por tipo de movimiento con su cantidad, saldo final) y la tabla MOVIMIENTOS: Fecha, Descripcion,
Referencia, Debitos, Creditos y Saldo. Debitos y creditos van en columnas distintas pero alineadas a la
derecha, asi que un monto grande puede "invadir" la columna vecina: el tipo NO se decide por la posicion
sino por como encadena el saldo (saldo anterior + monto = credito; saldo anterior - monto = debito). De paso
eso verifica el archivo: si una linea no encadena, o el total no llega al saldo final del resumen, o faltan
lineas respecto a las cantidades del resumen, NO se importa nada.

Devuelve la misma estructura que banco_excel.parsear_extracto, asi la importacion, la deteccion de
duplicados y la conciliacion no cambian.
"""
import hashlib
import re
import unicodedata
import zlib
from datetime import datetime

from .banco_excel import ExtractoInvalido, clasificar, huella_movimiento, parsear_monto, verificar_saldos

BANCO = 'BNC'
MENSAJE_NO_ES_BNC = (
    'Solo se admite en PDF el estado de cuenta del BNC. Para otros bancos sube el archivo en Excel (.xlsx) o CSV.'
)
MAX_BYTES_DESCOMPRIMIDOS = 20 * 1024 * 1024
TOLERANCIA_FILA = 2.5  # puntos: celdas cuya altura difiere menos que esto son de la misma fila

_MONTO = re.compile(r'^-?\d{1,3}(\.\d{3})*,\d{2}$|^-?\d+,\d{2}$')
_FECHA = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_CUENTA_BNC = re.compile(r'0191\s*-?\s*\d{4}\s*-?\s*\d{2}\s*-?\s*\d{10}')


# ---------------------------------------------------------------------------
# PDF -> filas de texto con posicion
# ---------------------------------------------------------------------------
def _objetos(datos):
    return {int(numero): cuerpo for numero, cuerpo in re.findall(rb'(\d+)\s+0\s+obj(.*?)endobj', datos, re.S)}


def _stream(objeto):
    encontrado = re.search(rb'stream\r?\n(.*?)\r?\n?endstream', objeto, re.S)
    if not encontrado:
        return b''
    crudo = encontrado.group(1)
    if b'/FlateDecode' not in objeto:
        return crudo
    try:
        return zlib.decompressobj().decompress(crudo, MAX_BYTES_DESCOMPRIMIDOS)
    except zlib.error:
        raise ExtractoInvalido('El PDF está dañado: no se pudo descomprimir.')


def _cmap(texto):
    """Tabla CID -> texto de un /ToUnicode (bfchar y bfrange)."""
    mapa = {}
    for bloque in re.findall(rb'beginbfchar(.*?)endbfchar', texto, re.S):
        for origen, destino in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', bloque):
            mapa[int(origen, 16)] = bytes.fromhex(destino.decode()).decode('utf-16-be', 'replace')
    for bloque in re.findall(rb'beginbfrange(.*?)endbfrange', texto, re.S):
        for desde, hasta, destino in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', bloque):
            inicio, fin, base = int(desde, 16), int(hasta, 16), int(destino, 16)
            for codigo in range(inicio, min(fin, inicio + 65535) + 1):
                mapa[codigo] = chr(base + codigo - inicio)
    return mapa


def _fuentes(objetos):
    """{'F3': (es_cid, mapa)} a partir de las referencias /Fn de los recursos."""
    fuentes = {}
    for cuerpo in objetos.values():
        for nombre, referencia in re.findall(rb'/(F\d+)\s+(\d+)\s+0\s+R', cuerpo):
            fuente = objetos.get(int(referencia), b'')
            a_unicode = re.search(rb'/ToUnicode\s+(\d+)\s+0\s+R', fuente)
            mapa = _cmap(_stream(objetos.get(int(a_unicode.group(1)), b''))) if a_unicode else {}
            fuentes[nombre.decode()] = (b'/Type0' in fuente, mapa)
    return fuentes


def _tokens(contenido):
    """Tokens de un content stream. Las cadenas (...) admiten parentesis anidados y escapes."""
    i, largo = 0, len(contenido)
    while i < largo:
        caracter = contenido[i:i + 1]
        if caracter.isspace():
            i += 1
        elif caracter == b'(':
            profundidad, j = 1, i + 1
            while j < largo and profundidad:
                if contenido[j:j + 1] == b'\\':
                    j += 2
                    continue
                profundidad += {b'(': 1, b')': -1}.get(contenido[j:j + 1], 0)
                j += 1
            yield contenido[i:j]
            i = j
        elif contenido[i:i + 2] in (b'<<', b'>>'):
            yield contenido[i:i + 2]
            i += 2
        elif caracter == b'<':
            j = contenido.find(b'>', i)
            j = largo if j == -1 else j + 1
            yield contenido[i:j]
            i = j
        elif caracter in (b'[', b']'):
            yield caracter
            i += 1
        else:
            encontrado = re.compile(rb'/?[^\s\[\]()<>/]*').match(contenido, i)
            fin = max(encontrado.end(), i + 1)
            yield contenido[i:fin]
            i = fin


def _literal(crudo):
    def reemplazo(m):
        valor = m.group(1)
        if valor[:1] in b'01234567':
            return bytes([int(valor, 8) & 0xFF])
        return {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f'}.get(valor, valor)
    return re.sub(rb'\\([0-7]{1,3}|.)', reemplazo, crudo, flags=re.S)


def _texto_de(token, fuente):
    es_cid, mapa = fuente
    if token[:1] == b'<':
        hexa = re.sub(rb'[^0-9A-Fa-f]', b'', token)
        crudo = bytes.fromhex((hexa + b'0' * (len(hexa) % 2)).decode())
    else:
        crudo = _literal(token[1:-1])
    if es_cid:
        return ''.join(mapa.get(int.from_bytes(crudo[i:i + 2], 'big'), '?') for i in range(0, len(crudo), 2))
    return crudo.decode('cp1252', 'replace')


def _fragmentos(contenido, fuentes):
    """[(x, y, texto)] de un content stream (Tm/Td/TD/T*/TL/Tf/Tj/TJ, que es lo que usa Reporting Services)."""
    pila, salida = [], []
    x = y = inicio_x = inicio_y = interlineado = 0.0
    fuente = (False, {})

    def numeros():
        return float(pila[-2]), float(pila[-1])

    for token in _tokens(contenido):
        try:
            if token == b'BT':
                x = y = inicio_x = inicio_y = 0.0
            elif token == b'Tf':
                fuente = fuentes.get(pila[-2][1:].decode(), (False, {}))
            elif token in (b'Td', b'TD'):
                dx, dy = numeros()
                inicio_x, inicio_y = inicio_x + dx, inicio_y + dy
                x, y = inicio_x, inicio_y
                if token == b'TD':
                    interlineado = -dy
            elif token == b'Tm':
                inicio_x, inicio_y = numeros()
                x, y = inicio_x, inicio_y
            elif token == b'TL':
                interlineado = float(pila[-1])
            elif token == b'T*':
                inicio_y -= interlineado
                x, y = inicio_x, inicio_y
            elif token in (b'Tj', b'TJ'):
                texto = ''.join(_texto_de(p, fuente) for p in pila if p[:1] in (b'(', b'<'))
                if texto.strip():
                    salida.append((x, y, texto.strip()))
            elif token[:1] in (b'(', b'<', b'[', b']', b'/') or re.fullmatch(rb'[-+]?\d*\.?\d+', token):
                pila.append(token)
                continue
        except (IndexError, ValueError, UnicodeDecodeError):
            pass  # un operador mal formado no debe tumbar la lectura: el control de saldos detecta lo que falte
        pila = []
    return salida


def _paginas(objetos):
    """Los objetos /Page en el orden del documento (arbol /Pages -> /Kids)."""
    def es_pagina(cuerpo):
        return re.search(rb'/Type\s*/Page(?![s\w])', cuerpo) is not None

    ordenadas, vistas = [], set()

    def recorrer(numero):
        cuerpo = objetos.get(numero)
        if cuerpo is None or numero in vistas:
            return
        vistas.add(numero)
        hijos = re.search(rb'/Kids\s*\[([^\]]*)\]', cuerpo)
        if hijos:
            for hijo in re.findall(rb'(\d+)\s+0\s+R', hijos.group(1)):
                recorrer(int(hijo))
        elif es_pagina(cuerpo):
            ordenadas.append(cuerpo)

    for numero, cuerpo in objetos.items():
        if re.search(rb'/Type\s*/Pages(?![\w])', cuerpo) and b'/Parent' not in cuerpo:
            recorrer(numero)
    return ordenadas or [cuerpo for cuerpo in objetos.values() if es_pagina(cuerpo)]


def leer_filas(datos):
    """Por pagina, sus filas de arriba hacia abajo: [[(y, [(x, texto), ...]), ...], ...]."""
    if b'/Encrypt' in datos:
        raise ExtractoInvalido('El PDF está protegido con contraseña. Descárgalo del banco sin protección.')
    objetos = _objetos(datos)
    fuentes = _fuentes(objetos)
    paginas = []
    for pagina in _paginas(objetos):
        contenidos = re.search(rb'/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)', pagina)
        if not contenidos:
            continue
        flujo = b'\n'.join(_stream(objetos.get(int(n), b'')) for n in re.findall(rb'(\d+)\s+0\s+R', contenidos.group(1)))
        filas = []
        for x, y, texto in sorted(_fragmentos(flujo, fuentes), key=lambda f: (-f[1], f[0])):
            if filas and abs(filas[-1][0] - y) <= TOLERANCIA_FILA:
                filas[-1][1].append((x, texto))
            else:
                filas.append((y, [(x, texto)]))
        paginas.append([(y, sorted(celdas)) for y, celdas in filas])
    return paginas


# ---------------------------------------------------------------------------
# Filas -> movimientos
# ---------------------------------------------------------------------------
def _normal(texto):
    sin_tildes = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode()
    return ' '.join(sin_tildes.upper().split())


def _es_encabezado_movimientos(textos):
    normalizados = {_normal(t) for t in textos}
    return {'FECHA', 'REFERENCIA', 'SALDO'} <= normalizados


def _saldo_en(textos, etiqueta):
    """El monto de la fila 'Saldo Inicial' / 'Saldo Final', o None si no es esa fila."""
    if any(_normal(t) == etiqueta for t in textos) and _MONTO.match(textos[-1]):
        return parsear_monto(textos[-1])
    return None


def parsear_estado_bnc(contenido):
    """Igual que banco_excel.parsear_extracto, a partir del PDF del BNC. Lanza ExtractoInvalido."""
    paginas = leer_filas(contenido)
    todo = ' '.join(texto for pagina in paginas for _, celdas in pagina for _, texto in celdas)
    if not todo.strip():
        raise ExtractoInvalido('El PDF no tiene texto que leer (¿es una foto o un escaneo?). ' + MENSAJE_NO_ES_BNC)
    cuenta = _CUENTA_BNC.search(todo)
    if 'ESTADO DE CUENTA' not in _normal(todo) or cuenta is None:
        raise ExtractoInvalido(MENSAJE_NO_ES_BNC)

    saldo_inicial = saldo_final = None
    cantidad_resumen = 0
    en_movimientos = False
    movimientos = []

    for numero_pagina, pagina in enumerate(paginas, start=1):
        anterior = None  # (indice del movimiento, x de su descripcion, y): para descripciones en dos renglones
        for numero_fila, (y, celdas) in enumerate(pagina, start=1):
            textos = [texto for _, texto in celdas]
            if _es_encabezado_movimientos(textos):
                if any(_normal(t) == 'CANTIDAD' for t in textos):
                    continue
                en_movimientos = True
                continue

            inicial = _saldo_en(textos, 'SALDO INICIAL')
            if inicial is not None:
                saldo_inicial = inicial if saldo_inicial is None else saldo_inicial
                continue
            final = _saldo_en(textos, 'SALDO FINAL')
            if final is not None:
                saldo_final = final
                continue

            if not en_movimientos:
                # Fila del resumen: CANTIDAD | DESCRIPCION | monto
                if len(textos) >= 3 and textos[0].isdigit() and _MONTO.match(textos[-1]):
                    cantidad_resumen += int(textos[0])
                continue

            if _FECHA.match(textos[0]):
                if len(textos) < 4 or not (_MONTO.match(textos[-1]) and _MONTO.match(textos[-2])):
                    raise ExtractoInvalido(f'No se pudo leer el movimiento del {textos[0]}. No se importó nada.')
                referencia = textos[-3] if len(textos) >= 5 and textos[-3].isdigit() else ''
                descripcion = ' '.join(textos[1:-3] if referencia else textos[1:-2])
                try:
                    fecha = datetime.strptime(textos[0], '%d/%m/%Y')
                except ValueError:
                    raise ExtractoInvalido(f'La fecha "{textos[0]}" no es válida. No se importó nada.')
                movimientos.append({
                    'hoja': f'Página {numero_pagina}', 'fila': numero_fila, 'fecha': fecha,
                    # "0" = el banco no puso referencia (comisiones e intereses): no debe cruzar por referencia
                    'referencia': '' if not referencia.strip('0') else referencia[:40],
                    'descripcion': descripcion, 'monto': parsear_monto(textos[-2]), 'saldo': parsear_monto(textos[-1]),
                })
                anterior = (len(movimientos) - 1, celdas[1][0], y)
                continue

            # Segundo renglon de una descripcion larga: una sola celda, alineada con la descripcion de arriba
            if anterior and len(celdas) == 1 and abs(celdas[0][0] - anterior[1]) < 6 and 0 < anterior[2] - y < 20:
                movimientos[anterior[0]]['descripcion'] += f' {textos[0]}'
                anterior = (anterior[0], anterior[1], y)
            else:
                anterior = None

    if not movimientos:
        raise ExtractoInvalido('El estado de cuenta no tiene movimientos.')
    if saldo_inicial is None or saldo_final is None:
        raise ExtractoInvalido('No se encontraron el saldo inicial y el saldo final en el PDF. No se importó nada.')
    if cantidad_resumen and cantidad_resumen != len(movimientos):
        raise ExtractoInvalido(
            f'El resumen del banco indica {cantidad_resumen} movimiento(s) y se leyeron {len(movimientos)}. No se importó nada.'
        )

    saldo = saldo_inicial
    for movimiento in movimientos:
        monto = abs(movimiento['monto'])
        if movimiento['saldo'] - saldo == monto:
            tipo = 'credito'
        elif saldo - movimiento['saldo'] == monto:
            tipo = 'debito'
        else:
            raise ExtractoInvalido(
                f"El saldo no cuadra en el movimiento del {movimiento['fecha']:%d/%m/%Y} "
                f"({movimiento['descripcion'][:60]}). No se importó nada."
            )
        saldo = movimiento['saldo']
        movimiento['monto'] = monto
        movimiento['tipo'] = tipo
        movimiento['descripcion'] = movimiento['descripcion'][:255]
        movimiento['observacion'] = ''
        # El BNC escribe con tildes ("Comisión ..."): las reglas de clasificar() comparan sin ellas.
        movimiento['clase'] = clasificar(_normal(movimiento['descripcion']), tipo)
        movimiento['huella'] = huella_movimiento(
            movimiento['fecha'], movimiento['referencia'], movimiento['descripcion'], tipo, monto, movimiento['saldo'],
        )
    if saldo != saldo_final:
        raise ExtractoInvalido('Los movimientos no llegan al saldo final del resumen: falta alguna línea. No se importó nada.')

    return {
        'movimientos': movimientos, 'errores': [],
        'hojas': [{'nombre': 'Estado de cuenta BNC', 'movimientos': len(movimientos)}], 'hojas_omitidas': [],
        'repetidas_en_archivo': 0, 'saltos_saldo': verificar_saldos(movimientos),
        'huella_archivo': hashlib.sha256(contenido).hexdigest(),
        'banco': BANCO, 'numero_cuenta': re.sub(r'\D', '', cuenta.group(0)),
    }


def es_cuenta_bnc(nombre_cuenta):
    """La cuenta bancaria del sistema (VGMetodoPago.cuenta_bancaria) a la que se puede subir un PDF del BNC."""
    nombre = _normal(nombre_cuenta)
    return re.search(r'\bBNC\b', nombre) is not None or 'NACIONAL DE CREDITO' in nombre
