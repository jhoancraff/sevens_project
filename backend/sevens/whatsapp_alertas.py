"""
Envio de avisos por WhatsApp (Cloud API de Meta) con una plantilla aprobada.

Los avisos automaticos los inicia el sistema, no el cliente, y WhatsApp solo permite eso con plantillas aprobadas
por Meta (el texto libre solo vale dentro de las 24 h siguientes a que la persona escriba). Por eso aqui se envia la
plantilla de stock minimo, con dos variables con nombre: {{fecha}} e {{ingredientes}}.

Configuracion (en backend/.env):
    WHATSAPP_PHONE_NUMBER_ID   id del numero de telefono de la API de Meta (el mismo de las alertas de comandas).
    WHATSAPP_ACCESS_TOKEN      token del usuario del sistema (permanente; el de la pantalla de pruebas vence en 24 h).
    WHATSAPP_TO_PHONES         numeros que reciben el aviso, separados por coma, con codigo de pais y sin 0 inicial
                               (ej. 584121234567). Con el numero de pruebas de Meta, cada uno debe estar en su
                               lista de destinatarios (maximo 5).
    WHATSAPP_TEMPLATE_STOCK    nombre de la plantilla aprobada (por defecto alerta_stock_minimo).
    WHATSAPP_TEMPLATE_LANG     idioma de la plantilla (por defecto es).
    WHATSAPP_API_VERSION       version de la API de Graph (por defecto v23.0).
"""
import os
import re
from dataclasses import dataclass, field

import requests

from .telegram_alertas import limpiar_error

PLANTILLA_POR_DEFECTO = 'alerta_stock_minimo'
IDIOMA_POR_DEFECTO = 'es'
VERSION_POR_DEFECTO = 'v23.0'

# Errores de Meta que se explican solos con una frase.
PISTAS = {
    190: 'el token venció o no es válido (genere uno permanente con un usuario del sistema)',
    131030: 'el número no está en la lista de destinatarios permitidos del número de pruebas',
    131026: 'el número no tiene WhatsApp o no se le puede entregar el mensaje',
    132000: 'la cantidad de variables no coincide con la plantilla',
    132001: 'la plantilla no existe o no está aprobada en ese idioma',
    132012: 'el formato de una variable no coincide con la plantilla',
    132015: 'la plantilla está pausada o deshabilitada por Meta',
}


@dataclass
class ConfiguracionWhatsApp:
    phone_number_id: str = ''
    token: str = ''
    numeros: list = field(default_factory=list)
    plantilla: str = PLANTILLA_POR_DEFECTO
    idioma: str = IDIOMA_POR_DEFECTO
    version: str = VERSION_POR_DEFECTO

    @property
    def completa(self):
        return bool(self.phone_number_id and self.token and self.numeros)


def normalizar_numero(numero):
    """'+58 (412) 123-4567' -> '584121234567' (la API solo quiere digitos, con codigo de pais)."""
    return re.sub(r'\D', '', numero or '')


def configuracion():
    numeros = []
    for numero in os.getenv('WHATSAPP_TO_PHONES', '').split(','):
        numero = normalizar_numero(numero)
        if numero and numero not in numeros:
            numeros.append(numero)
    return ConfiguracionWhatsApp(
        phone_number_id=os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip(),
        token=os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip(),
        numeros=numeros,
        plantilla=os.getenv('WHATSAPP_TEMPLATE_STOCK', '').strip() or PLANTILLA_POR_DEFECTO,
        idioma=os.getenv('WHATSAPP_TEMPLATE_LANG', '').strip() or IDIOMA_POR_DEFECTO,
        version=os.getenv('WHATSAPP_API_VERSION', '').strip() or VERSION_POR_DEFECTO,
    )


def una_linea(texto):
    """Meta no acepta saltos de linea, tabuladores ni mas de 4 espacios seguidos dentro de una variable."""
    return re.sub(r'\s+', ' ', str(texto)).strip()


def _detalle_error(respuesta):
    try:
        error = respuesta.json().get('error') or {}
    except ValueError:
        error = {}
    mensaje = error.get('error_data', {}).get('details') or error.get('message') or respuesta.text
    codigo = error.get('code')
    pista = PISTAS.get(codigo)
    return f'{mensaje} [código {codigo}]' + (f' — {pista}' if pista else '') if codigo else str(mensaje)


def enviar_plantilla(config, numero, fecha, ingredientes):
    """
    Manda la plantilla de stock minimo a `numero`. Si no se pudo (sin internet, token vencido, plantilla sin
    aprobar, numero no permitido...) lanza una excepcion con la razon, para que quien llama decida si reintenta.
    """
    carga = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': numero,
        'type': 'template',
        'template': {
            'name': config.plantilla,
            'language': {'code': config.idioma},
            'components': [{
                'type': 'body',
                'parameters': [
                    {'type': 'text', 'parameter_name': 'fecha', 'text': una_linea(fecha)},
                    {'type': 'text', 'parameter_name': 'ingredientes', 'text': una_linea(ingredientes)},
                ],
            }],
        },
    }
    try:
        respuesta = requests.post(
            f'https://graph.facebook.com/{config.version}/{config.phone_number_id}/messages',
            headers={'Authorization': f'Bearer {config.token}', 'Content-Type': 'application/json'},
            json=carga,
            timeout=10,
        )
    except requests.RequestException as error:
        raise RuntimeError(limpiar_error(error, config.token)) from None
    if not respuesta.ok:
        raise RuntimeError(f'WhatsApp respondió {respuesta.status_code}: {limpiar_error(_detalle_error(respuesta), config.token)}')
