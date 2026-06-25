"""
Lógica central de permisos de acceso — fuente única de verdad.

Tanto la validación en vivo (endpoint validar-tarjeta) como la copia que
descargan las Raspberry Pi (endpoint sincronizar) usan estas funciones, para
que la regla de "quién tiene permiso" exista en un solo lugar y no se
desincronicen el servidor y las Pis.

Pensado para multi-tenancy futuro: cuando exista residencial_id, el filtrado
por residencial se agrega aquí, en un único punto.
"""
from app.models.cuenta import Tarjeta, Cuenta


def motivo_denegacion(tarjeta, acceso=None):
    """
    Devuelve None si la tarjeta tiene permiso, o un string con el motivo si NO.
    Si se pasa 'acceso' (un AccesoFisico), también valida la compatibilidad de
    tipo (peatonal/vehicular). Si no se pasa, valida solo el permiso general.

    Esta es la fuente única de verdad de los permisos.
    """
    # 1. La tarjeta debe estar activa
    if tarjeta.estado != "activa":
        return "Tarjeta dada de baja o inactiva"

    # 2. La cuenta debe existir, estar activa y no bloqueada por mora
    cuenta = Cuenta.query.get(tarjeta.cuenta_id)
    if not cuenta or not cuenta.activa:
        return "La cuenta no está activa"
    if cuenta.bloqueada:
        return "Cuenta bloqueada por mora"

    # 3. Si se especifica el acceso, validar compatibilidad de tipo.
    #    Regla: peatonal solo abre accesos peatonales; vehicular abre ambos.
    if acceso is not None:
        if tarjeta.tipo_acceso == "peatonal" and acceso.tipo == "vehicular":
            return "Tarjeta peatonal: no habilitada para acceso vehicular"

    return None


def tiene_permiso(tarjeta, acceso=None):
    """True si la tarjeta tiene permiso (azúcar sobre motivo_denegacion)."""
    return motivo_denegacion(tarjeta, acceso) is None


def tarjetas_con_permiso():
    """
    Devuelve las tarjetas que actualmente tienen permiso de acceso (activas,
    cuenta activa y sin mora). Es lo que se incluye en la copia que baja la Pi.

    Filtra en la base de datos lo más posible y termina de afinar en Python
    con la misma función motivo_denegacion, para no duplicar la regla.

    SaaS futuro: aquí se agregaría el filtro por residencial.
    """
    candidatas = (Tarjeta.query
                  .filter(Tarjeta.estado == "activa")
                  .all())
    # Afinar con la lógica central (cuenta activa / sin mora)
    return [t for t in candidatas if motivo_denegacion(t) is None]
