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


def motivo_denegacion(tarjeta, acceso=None, residencial_id=None):
    """
    Devuelve None si la tarjeta tiene permiso, o un string con el motivo si NO.
    Si se pasa 'acceso' (un AccesoFisico), también valida la compatibilidad de
    tipo (peatonal/vehicular). Si no se pasa, valida solo el permiso general.

    Esta es la fuente única de verdad de los permisos.

    Bases multi-residencial (Día 37): si se pasa residencial_id, la tarjeta
    debe pertenecer a esa residencial (vía Cuenta→Unidad) o se deniega —
    una Pi asignada a una residencial no debe poder validar tarjetas de
    otra. Si no se pasa (None), no se aplica esta verificación — igual que
    siempre.
    """
    # 1. La tarjeta debe estar activa
    if tarjeta.estado != "activa":
        return "Tarjeta dada de baja o inactiva"

    # 2. La cuenta debe existir, estar activa y no bloqueada por mora
    cuenta = Cuenta.query.get(tarjeta.cuenta_id)
    if not cuenta or not cuenta.activa:
        return "La cuenta no está activa"
    if cuenta.bloqueada:
        return "Servicio suspendido por falta de pago"

    # 3. Bases multi-residencial: la tarjeta debe ser de la misma
    #    residencial que la Pi que está preguntando (si la Pi tiene una
    #    asignada). Se trata igual que "no encontrada" desde afuera, no se
    #    distingue el motivo exacto para no filtrar información de otros
    #    clientes.
    if residencial_id is not None:
        from app.models.cuenta import Unidad
        unidad = Unidad.query.get(cuenta.unidad_id) if cuenta.unidad_id else None
        if not unidad or unidad.residencial_id != residencial_id:
            return "Tarjeta no encontrada"

    # 4. Si se especifica el acceso, validar compatibilidad de tipo.
    #    Regla: peatonal solo abre accesos peatonales; vehicular abre ambos.
    if acceso is not None:
        if tarjeta.tipo_acceso == "peatonal" and acceso.tipo == "vehicular":
            return "Tarjeta peatonal: no habilitada para acceso vehicular"

    return None


def tiene_permiso(tarjeta, acceso=None):
    """True si la tarjeta tiene permiso (azúcar sobre motivo_denegacion)."""
    return motivo_denegacion(tarjeta, acceso) is None


def tarjetas_con_permiso(residencial_id=None):
    """
    Devuelve las tarjetas que actualmente tienen permiso de acceso (activas,
    cuenta activa y sin mora). Es lo que se incluye en la copia que baja la Pi.

    Filtra en la base de datos lo más posible y termina de afinar en Python
    con la misma función motivo_denegacion, para no duplicar la regla.

    Bases multi-residencial (Día 37): si se pasa residencial_id, se filtra
    a las tarjetas cuya Cuenta→Unidad pertenezca a esa residencial (una Pi
    solo debe descargar tarjetas de SU cliente). Si no se pasa (None, el
    valor por defecto), no se filtra — se devuelven todas, exactamente el
    comportamiento de siempre. Esto mantiene 100% compatible el caso de
    Villas del Sol hoy, y solo separa datos cuando una Pi ya está asignada
    a una residencial específica.
    """
    from app.models.cuenta import Unidad

    q = Tarjeta.query.filter(Tarjeta.estado == "activa")
    if residencial_id is not None:
        q = (q.join(Cuenta, Tarjeta.cuenta_id == Cuenta.id)
              .join(Unidad, Cuenta.unidad_id == Unidad.id)
              .filter(Unidad.residencial_id == residencial_id))
    candidatas = q.all()
    # Afinar con la lógica central (cuenta activa / sin mora)
    return [t for t in candidatas if motivo_denegacion(t) is None]
