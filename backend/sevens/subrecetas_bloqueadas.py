"""
Subrecetas bloqueadas (recetas secretas): sus ingredientes, cantidades y costo no salen en la aplicación sin
el código. Un superusuario las bloquea y pone el código desde el Django Admin; allí mismo se modifican.

Este módulo es la regla central; cada vista que podría mostrar la composición la consulta. La operación NO
cambia: las ventas siguen descontando inventario y calculando costos con la receta completa (el candado es
sobre lo que se muestra, no sobre lo que se calcula). Importa solo modelos para que cualquier vista pueda
usarlo sin ciclos.
"""
from .models import VGPreparacion, VGRecetaPreparacion

MAX_INTENTOS_FALLIDOS = 5
MINUTOS_DE_BLOQUEO = 10
LARGO_MINIMO_CODIGO = 4
MENSAJE_SOLO_ADMIN = 'Esta subreceta está bloqueada: solo se modifica desde el Django Admin.'


def ids_bloqueadas():
    return set(VGPreparacion.objects.filter(bloqueada=True).values_list('id', flat=True))


def _subrecetas_dentro_de():
    """{preparacion_id: [ids de las subrecetas que usa directamente]}."""
    dentro = {}
    for padre, hija in VGRecetaPreparacion.objects.filter(sub_preparacion__isnull=False).values_list('preparacion_id', 'sub_preparacion_id'):
        dentro.setdefault(padre, []).append(hija)
    return dentro


def _alcanza_bloqueada(ids_iniciales, bloqueadas, dentro):
    pendientes, vistas = list(ids_iniciales), set()
    while pendientes:
        actual = pendientes.pop()
        if actual in vistas:
            continue
        if actual in bloqueadas:
            return True
        vistas.add(actual)
        pendientes.extend(dentro.get(actual, []))
    return False


def usa_bloqueada(tipo, objeto):
    """
    True si desglosar `objeto` (tipo 'subreceta' o 'receta'/producto) en ingredientes mostraría los de una
    subreceta bloqueada: ella misma, o cualquiera que use directa o indirectamente. Un 'ingrediente' nunca.
    """
    if tipo == 'ingrediente' or objeto is None:
        return False
    bloqueadas = ids_bloqueadas()
    if not bloqueadas:
        return False
    if tipo == 'subreceta':
        iniciales = [objeto.id]
    else:
        # Producto/receta: su subreceta vinculada, las de su receta vinculada, o las de su propia tabla.
        if getattr(objeto, 'subreceta_vinculada_id', None):
            iniciales = [objeto.subreceta_vinculada_id]
        else:
            origen = objeto.receta_vinculada if getattr(objeto, 'receta_vinculada_id', None) else objeto
            iniciales = [pk for pk in origen.receta.values_list('preparacion_id', flat=True) if pk]
    return _alcanza_bloqueada(iniciales, bloqueadas, _subrecetas_dentro_de())
