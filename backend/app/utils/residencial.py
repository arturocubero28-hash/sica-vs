"""
Helper compartido para la herencia de residencial_id (Día 37, bases
multi-residencial).

Cuando un admin o supervisor crea algo (un guardia, un cajero, una unidad,
un dispositivo), ese algo debe quedar bajo la misma Residencial que su
creador — así es como, el día que exista un segundo cliente, cada uno ve
solo lo suyo sin que nadie tenga que acordarse de pasar el dato a mano en
cada endpoint.

Hoy, con un solo admin en Villas del Sol, esta función siempre devuelve el
mismo valor (o None, si nunca se corrió el bootstrap) — no cambia ningún
comportamiento existente.
"""


def residencial_id_heredado(usuario_actual):
    """
    Determina qué residencial_id debe heredar algo creado por usuario_actual.

    - admin / supervisor: su propio residencial_id (el admin lo tiene
      seteado a su propia Residencial desde que esta se crea; el
      supervisor hereda el mismo valor al ser creado por ese admin).
    - super_admin / desarrollador: None — son roles de plataforma, no
      pertenecen a ninguna Residencial de cliente. Si alguno de estos
      roles crea algo directamente (posible hoy porque varios endpoints
      también aceptan "super_admin"), ese registro queda sin residencial
      asignada — coherente con que son operaciones de administración
      general, no de un cliente específico.
    - cualquier otro rol: None (no debería llegar a crear nada de esto,
      pero por seguridad se devuelve None en vez de fallar).
    """
    if usuario_actual.rol in ("admin", "supervisor"):
        return usuario_actual.residencial_id
    return None


def residencial_id_filtro(usuario_actual):
    """
    Determina por qué residencial_id se deben FILTRAR las lecturas (listados,
    métricas, historial) que hace usuario_actual. Es la contraparte de lectura
    de residencial_id_heredado (que es para escritura).

    - admin / supervisor: su propio residencial_id → solo ve lo de SU cliente.
    - super_admin / desarrollador: None → son roles de plataforma, ven TODO
      (no se aplica filtro). Coherente con que administran el SaaS completo.

    Uso típico en un endpoint de listado:

        rid = residencial_id_filtro(usuario_actual)
        q = Cuenta.query
        if rid is not None:
            q = q.join(Unidad).filter(Unidad.residencial_id == rid)

    Con una sola residencial (hoy), admin devuelve su id y el filtro no cambia
    nada visible (todo pertenece a esa misma residencial). El día que haya un
    segundo cliente, cada admin queda automáticamente aislado sin tocar más
    código.
    """
    if usuario_actual is None:
        return None
    if usuario_actual.rol in ("admin", "supervisor"):
        return usuario_actual.residencial_id
    return None


def scope_visitas(query, usuario_actual):
    """Filtra una query de Visita por la residencial del admin (vía
    Cuenta→Unidad). super_admin/desarrollador: sin filtro. Uso:
        q = scope_visitas(Visita.query, usuario_actual)
    """
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.cuenta import Cuenta, Unidad
    from app.models.visita import Visita
    return (query.join(Cuenta, Visita.cuenta_id == Cuenta.id)
                 .join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == rid))


def scope_eventos(query, usuario_actual):
    """Filtra una query de EventoAcceso por la residencial del admin (vía
    AccesoFisico). super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.visita import EventoAcceso, AccesoFisico
    return (query.join(AccesoFisico, EventoAcceso.acceso_id == AccesoFisico.id)
                 .filter(AccesoFisico.residencial_id == rid))


def scope_cuotas(query, usuario_actual):
    """Filtra una query de Cuota por la residencial del admin (vía
    Cuenta→Unidad). super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.cuenta import Cuota, Cuenta, Unidad
    return (query.join(Cuenta, Cuota.cuenta_id == Cuenta.id)
                 .join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == rid))


def scope_pagos(query, usuario_actual):
    """Filtra una query de Pago por la residencial del admin (vía
    Cuenta→Unidad). super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.cuenta import Pago, Cuenta, Unidad
    return (query.join(Cuenta, Pago.cuenta_id == Cuenta.id)
                 .join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == rid))


def scope_cuentas(query, usuario_actual):
    """Filtra una query de Cuenta por la residencial del admin (vía Unidad).
    super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.cuenta import Cuenta, Unidad
    return (query.join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == rid))


def scope_ventas_tarjeta(query, usuario_actual):
    """Filtra una query de VentaTarjeta por la residencial del admin (vía
    Cuenta→Unidad). super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.cuenta import VentaTarjeta, Cuenta, Unidad
    return (query.join(Cuenta, VentaTarjeta.cuenta_id == Cuenta.id)
                 .join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == rid))


def scope_sesiones_caja(query, usuario_actual):
    """Filtra una query de SesionCaja por la residencial del admin (vía el
    cajero → Usuario.residencial_id). super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.caja import SesionCaja
    from app.models.usuario import Usuario
    return (query.join(Usuario, SesionCaja.cajero_id == Usuario.id)
                 .filter(Usuario.residencial_id == rid))


def scope_por_sesion_caja(query, modelo, campo_sesion, usuario_actual):
    """Filtra por residencial un modelo ligado a una sesión de caja
    (AjusteCaja.sesion_caja_id, SalidaCaja.sesion_id) uniendo
    SesionCaja→cajero→residencial. super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.caja import SesionCaja
    from app.models.usuario import Usuario
    return (query.join(SesionCaja, campo_sesion == SesionCaja.id)
                 .join(Usuario, SesionCaja.cajero_id == Usuario.id)
                 .filter(Usuario.residencial_id == rid))


def scope_usuarios(query, usuario_actual):
    """Filtra una query de Usuario por la residencial del admin (directo, ya
    que Usuario tiene residencial_id). super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.usuario import Usuario
    return query.filter(Usuario.residencial_id == rid)


def scope_por_cuenta(query, modelo, usuario_actual):
    """Filtra por residencial cualquier modelo que tenga cuenta_id (ArregloPago,
    SolicitudBaja, etc.) uniendo Cuenta→Unidad→residencial.
    super_admin/desarrollador: sin filtro."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    from app.models.cuenta import Cuenta, Unidad
    return (query.join(Cuenta, modelo.cuenta_id == Cuenta.id)
                 .join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == rid))
