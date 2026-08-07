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


def visita_en_residencial_de(visita, usuario_actual):
    """
    True si la visita pertenece a la residencial del usuario (guardia/admin).

    CRÍTICO (aislación de acceso físico): un guardia solo puede validar y
    registrar accesos de visitas de SU residencial. Sin esto, un guardia de la
    Residencial B puede escanear y autorizar el QR de una visita de la
    Residencial A.

    - super_admin/desarrollador: siempre True (roles de plataforma).
    - Si el usuario no tiene residencial asignada (None): True, para no romper
      el modo de una sola residencial sin residencial_id (comportamiento
      histórico previo al multi-tenant).
    - En otro caso: compara la residencial de la visita (vía
      cuenta→unidad→residencial_id) con la del usuario.
    """
    if usuario_actual is None:
        return True
    if usuario_actual.rol in ("super_admin", "desarrollador"):
        return True
    rid_usuario = usuario_actual.residencial_id
    if rid_usuario is None:
        return True
    cuenta = getattr(visita, "cuenta", None)
    if cuenta is None:
        return True  # sin cuenta no se puede determinar; no bloquear datos legacy
    unidad = getattr(cuenta, "unidad", None)
    rid_visita = getattr(unidad, "residencial_id", None) if unidad else None
    if rid_visita is None:
        return True  # datos sin residencial asignada: no bloquear
    return rid_visita == rid_usuario


def pertenece_a_mi_residencial(recurso, usuario_actual):
    """
    True si `recurso` (cualquier modelo con residencial_id DIRECTO —
    Camara, AjusteCaja, etc.) pertenece a la residencial del usuario.
    Mismo criterio que visita_en_residencial_de, generalizado para no
    repetir la lógica en cada modelo nuevo que la necesite.

    - super_admin/desarrollador: siempre True (roles de plataforma).
    - Si el usuario no tiene residencial asignada (None): True, para no
      romper el modo de una sola residencial sin residencial_id.
    - Si el recurso no tiene residencial asignada (None, datos legacy sin
      backfill): True, no bloquear datos viejos.
    - En otro caso: compara directamente.
    """
    if usuario_actual is None:
        return True
    if usuario_actual.rol in ("super_admin", "desarrollador"):
        return True
    rid_usuario = usuario_actual.residencial_id
    if rid_usuario is None:
        return True
    rid_recurso = getattr(recurso, "residencial_id", None)
    if rid_recurso is None:
        return True
    return rid_recurso == rid_usuario


def residencial_id_de_usuario(usuario_actual):
    """
    A diferencia de residencial_id_filtro (que solo filtra para admin/
    supervisor, pensado para el panel administrativo), esta devuelve la
    residencial_id de CUALQUIER usuario autenticado — residente, guardia,
    cajero, admin — excepto los roles de plataforma (super_admin,
    desarrollador), que ven todo.

    Se usa para contenido que TODOS los roles consumen y que debe aislarse
    igual para todos, como los comunicados: un residente o guardia de una
    residencial no debe ver los anuncios de otra.
    """
    if usuario_actual is None:
        return None
    if usuario_actual.rol in ("super_admin", "desarrollador"):
        return None
    return usuario_actual.residencial_id


def scope_directo(query, modelo, usuario_actual):
    """Filtra por residencial cualquier modelo que tenga residencial_id
    DIRECTO (TipoTarjeta, Tarifa, Comunicado, etc.). super_admin/desarrollador:
    sin filtro. Filas con residencial_id NULL (legacy) se excluyen para un
    admin normal — deben migrarse, no mostrarse a todos."""
    rid = residencial_id_filtro(usuario_actual)
    if rid is None:
        return query
    return query.filter(modelo.residencial_id == rid)


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


def resolver_residencial_caja(usuario_actual, request):
    """
    Día 47: cada residencial opera su caja de forma INDEPENDIENTE (decisión
    del usuario) — no existe una vista combinada de "todas juntas", porque
    sumar el efectivo de negocios distintos no tiene sentido operativo. Todo
    endpoint de caja necesita saber a qué residencial aplica.

    - cajero / admin / supervisor: su propia residencial_id (usan
      residencial_id_de_usuario, que a diferencia de residencial_id_filtro
      cubre TODOS los roles de cliente, no solo admin — un cajero también
      tiene la suya).
    - super_admin / desarrollador: no pertenecen a ninguna, así que deben
      indicarla explícitamente con ?residencial_id=<uuid> (o en el body del
      POST). Si no la mandan, se devuelve un error pidiendo que elijan una
      — nunca se asume ni se combinan residenciales.

    Devuelve (residencial_id_interno, respuesta_de_error). Uso típico:

        rid, err = resolver_residencial_caja(usuario_actual, request)
        if err:
            return err

    Día 51 — niveles de plan: este resolver ahora también valida
    permite_cuotas sobre la residencial REALMENTE resuelta (la del
    usuario, o la elegida explícitamente por un rol de plataforma) — no
    alcanza con el decorador @requiere_funcion_plan en cada endpoint,
    porque ese decorador solo mira usuario_actual.residencial_id, que
    para desarrollador/super_admin siempre es None (nunca bloquea,
    sin importar qué residencial estén mirando en realidad). Bug real
    encontrado por el usuario probando con su propia cuenta de
    desarrollador contra una residencial en plan Básico.
    """
    def _validar_plan(rid):
        from app.utils.residencial import plan_permite
        if not plan_permite(rid, "cuotas"):
            from flask import jsonify
            return None, (jsonify({"error": {"code": "funcion_no_incluida",
                          "message": "Tu plan actual no incluye esta función — "
                                     "hablá con tu proveedor para subir de plan."}}), 402)
        return rid, None

    rid = residencial_id_de_usuario(usuario_actual)
    if rid is not None:
        return _validar_plan(rid)

    # Rol de plataforma sin residencial propia: exigir que la indique.
    uuid_pedido = request.args.get("residencial_id")
    if not uuid_pedido and request.method in ("POST", "PUT"):
        body = request.get_json(silent=True) or {}
        uuid_pedido = body.get("residencial_id")

    if not uuid_pedido:
        from flask import jsonify
        return None, (jsonify({"error": {
            "code": "elegi_residencial",
            "message": "Como desarrollador/super_admin, indicá con qué residencial "
                       "querés trabajar (?residencial_id=<uuid>) — no hay una vista "
                       "combinada de todas juntas."}}), 400)

    from app.models.residencial import Residencial
    r = Residencial.query.filter_by(uuid_publico=uuid_pedido).first()
    if not r:
        from flask import jsonify
        return None, (jsonify({"error": {"code": "residencial_no_encontrada",
                                         "message": "No se encontró esa residencial"}}), 404)
    return _validar_plan(r.id)


def limite_casas_alcanzado(residencial_id):
    """
    Día 50 — sistema de suscripciones. True si la residencial ya está en
    (o por encima de) el tope de casas de su plan. Sin residencial_id o
    sin plan asignado, nunca bloquea (no hay límite contra el cual medir).
    """
    if not residencial_id:
        return False
    from app.models.residencial import Residencial
    from app.models.cuenta import Cuenta, Unidad
    residencial = Residencial.query.get(residencial_id)
    if not residencial or not residencial.plan_id:
        return False
    actuales = (
        Cuenta.query.join(Unidad, Cuenta.unidad_id == Unidad.id)
        .filter(Unidad.residencial_id == residencial_id)
        .count()
    )
    return actuales >= residencial.plan.max_casas


def limite_usuarios_alcanzado(residencial_id):
    """
    Mismo criterio que limite_casas_alcanzado(), pero para usuarios.
    Cuenta TODOS los roles bajo la residencial (admin incluido) contra
    Plan.max_usuarios — es el tope total de cuentas de acceso al
    sistema, no solo residentes.
    """
    if not residencial_id:
        return False
    from app.models.residencial import Residencial
    from app.models.usuario import Usuario
    residencial = Residencial.query.get(residencial_id)
    if not residencial or not residencial.plan_id:
        return False
    actuales = Usuario.query.filter_by(residencial_id=residencial_id).count()
    return actuales >= residencial.plan.max_usuarios


def plan_permite(residencial_id, funcion):
    """
    Día 51 — niveles de plan (Básico/Premium) por flags de función.
    Devuelve True si la residencial puede usar esa función según su plan.

    Mismo criterio que el resto del sistema de suscripciones: sin
    residencial_id o sin plan asignado, SIEMPRE permite — no hay
    restricción de nivel contra la cual medir (Villas del Sol, sin plan
    todavía, sigue con acceso completo a todo).

    funcion: 'cuotas' o 'notificaciones' — el nombre del flag en el
    modelo Plan, sin el prefijo 'permite_'.
    """
    if not residencial_id:
        return True
    from app.models.residencial import Residencial
    residencial = Residencial.query.get(residencial_id)
    if not residencial or not residencial.plan_id or not residencial.plan:
        return True
    return getattr(residencial.plan, f"permite_{funcion}", True)


def marcar_config_cuotas_si_corresponde(residencial, anterior_tenia_cuotas):
    """
    Día 55 — Sprint 2a. Se llama JUSTO DESPUÉS de cambiarle el plan a una
    residencial (en ambos caminos: admin auto-upgrade en suscripcion.py,
    y dev en desarrollador.py). Enciende cuotas_config_pendiente si el
    plan NUEVO incluye cuotas y el ANTERIOR no las incluía — es decir,
    solo en la transición "sin cuotas -> con cuotas", que es cuando el
    admin necesita el wizard de configuración.

    No se enciende si:
    - el plan nuevo no tiene cuotas (Básico -> Básico, o bajar a Básico);
    - ya venía con cuotas (Intermedio -> Premium, por ejemplo — ya está
      todo configurado, no hay nada que pedirle al admin).

    IMPORTANTE — recibe anterior_tenia_cuotas como un BOOLEAN ya resuelto,
    NO como el objeto Plan. Motivo (bug real encontrado al probar): si se
    captura `plan_anterior = residencial.plan` y luego se hace flush()
    tras cambiar plan_id, SQLAlchemy RECARGA esa relación y la variable
    termina apuntando al plan NUEVO, no al viejo. Por eso el llamador
    debe leer `residencial.plan.permite_cuotas` (o el criterio que sea)
    ANTES de tocar plan_id y pasar ya el bool -- un primitivo no muta
    cuando la relación se recarga.
    """
    # IMPORTANTE: residencial.plan puede estar cacheado con el plan VIEJO.
    # Cambiar residencial.plan_id + flush() NO recarga automáticamente la
    # relación .plan si ya estaba cargada en memoria (SQLAlchemy conserva
    # el objeto viejo). Por eso se expira el atributo antes de leerlo -- el
    # próximo acceso a .plan dispara una recarga lazy con el plan_id nuevo.
    # Este fue el bug real que hizo que la marca nunca se encendiera al
    # probar: el helper leía el plan anterior y salía temprano.
    from app.extensions import db
    db.session.expire(residencial, ["plan"])
    plan_nuevo = residencial.plan
    if not plan_nuevo or not plan_nuevo.permite_cuotas:
        return
    if not anterior_tenia_cuotas:
        residencial.cuotas_config_pendiente = True
