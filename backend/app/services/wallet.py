"""
Utilidades compartidas de Google Wallet.

ROTATION-07 (Auditoría Día 35): el object_id de un pase de Wallet se
construía en DOS lugares distintos con formatos DIFERENTES:
  - tarjeta_virtual.py (cuando el residente toca "Agregar a Wallet"):
    f"{issuer_id}.tv{uuid_sin_guiones}"
  - tasks/mora.py (la tarea nocturna automática de actualización):
    f"{issuer_id}.tv_{uuid_CON_guiones}"

Como el formato no coincidía, la tarea nocturna intentaba actualizar un
object_id que Google nunca había visto — la actualización automática del
QR diario en los pases de Wallet fallaba en silencio todas las noches
desde que existe esta función (Día 32), y el 404 resultante se contaba
como "éxito" en el log. En la práctica, el pase de Wallet de un residente
solo se actualizaba si él mismo volvía a tocar "Agregar a Wallet" a mano.

Ahora existe un solo lugar que genera el object_id — cualquier código que
necesite construirlo (crear el pase, actualizarlo a mano, o la rotación
automática nocturna) usa esta misma función, eliminando la posibilidad de
que vuelvan a desincronizarse.
"""


def wallet_object_id(issuer_id: str, uuid_tarjeta) -> str:
    """
    Construye el object_id de Wallet para una TarjetaVirtual dada.
    Google no acepta guiones en el object id, así que se quitan del UUID.
    """
    uuid_limpio = str(uuid_tarjeta).replace("-", "")
    return f"{issuer_id}.tv{uuid_limpio}"
