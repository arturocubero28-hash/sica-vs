"""
Módulo de Guardias — /api/v1/guardias/

Solo conserva la creación de guardias (usada desde el módulo Usuarios del
frontend). Listar, editar y resetear contraseña de guardias se hace por los
endpoints genéricos de /api/v1/usuarios — los duplicados se eliminaron en la
limpieza de la auditoría del Día 11.
"""
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.usuario import Usuario
from app.auth.security import roles_required
from app.utils.passwords import generar_password_temporal

guardias_bp = Blueprint("guardias", __name__)


@guardias_bp.post("")
@roles_required("admin", "super_admin")
def crear_guardia(usuario_actual):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not nombre or not apellido or not email:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Nombre, apellido y correo son obligatorios"}}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": {"code": "email_duplicado",
                                  "message": "Ya existe un usuario con ese correo"}}), 400

    # SEC-01: contraseña aleatoria por usuario — antes era una fija
    # compartida ('VillasDelSol2026') para todos los guardias nuevos.
    password_temporal = generar_password_temporal()

    guardia = Usuario(
        nombre=nombre, apellido=apellido, email=email,
        rol="guardia", activo=True,
        debe_cambiar_password=True,   # obligado a cambiar en el primer login
    )
    guardia.set_password(password_temporal)
    db.session.add(guardia)
    db.session.commit()

    d = guardia.to_dict()
    d["password_generica"] = password_temporal  # mostrar al admin para entregársela
    return jsonify({"data": d}), 201


@guardias_bp.post("/mi-punto-acceso")
@roles_required("guardia")
def fijar_mi_punto_acceso(usuario_actual):
    """
    El guardia elige en qué punto de acceso está trabajando este turno.
    Queda guardado en su usuario — normalmente se elige una sola vez, ya
    que cada guardia usa siempre el mismo teléfono asignado a un punto
    específico (ACCESS-04, Auditoría Día 35).
    """
    from app.models.visita import AccesoFisico

    data = request.get_json(silent=True) or {}
    nombre_punto = (data.get("punto_acceso") or "").strip()
    if not nombre_punto:
        return jsonify({"error": {"code": "punto_requerido",
                                  "message": "Indicá el punto de acceso"}}), 400

    existe = AccesoFisico.query.filter_by(punto_acceso=nombre_punto, activo=True).first()
    if not existe:
        return jsonify({"error": {"code": "punto_invalido",
                                  "message": "Ese punto de acceso no existe o está inactivo"}}), 400

    usuario_actual.punto_acceso_actual = nombre_punto
    db.session.commit()
    return jsonify({"data": {"punto_acceso": nombre_punto}})


@guardias_bp.get("/mis-trancas")
@roles_required("guardia")
def mis_trancas_disponibles(usuario_actual):
    """
    Devuelve las trancas del punto de acceso donde está el guardia — para
    llenar el menú del botón 'Abrir' en la app (ACCESS-04, Auditoría Día 35).
    """
    from app.models.visita import AccesoFisico

    if not usuario_actual.punto_acceso_actual:
        return jsonify({"error": {"code": "sin_punto_asignado",
                                  "message": "No tenés un punto de acceso asignado"}}), 400

    trancas = AccesoFisico.query.filter_by(
        punto_acceso=usuario_actual.punto_acceso_actual, activo=True
    ).order_by(AccesoFisico.tipo, AccesoFisico.direccion).all()

    return jsonify({"data": {
        "punto_acceso": usuario_actual.punto_acceso_actual,
        "trancas": [t.to_dict() for t in trancas],
    }})


@guardias_bp.post("/abrir-manual")
@roles_required("guardia")
def abrir_tranca_manual(usuario_actual):
    """
    Registra la apertura manual de una tranca SIN visita asociada — ej. el
    guardia deja salir a alguien que vio, o una emergencia. Exige que la
    app haya pedido confirmación explícita antes de llamar este endpoint;
    el registro queda auditado con quién, cuándo y cuál tranca exacta
    (ACCESS-04, Auditoría Día 35).

    Hoy esto solo REGISTRA la acción — no dispara nada físico todavía,
    porque el agente de la Raspberry Pi que acciona el relay real no está
    construido. Cuando exista, este mismo endpoint es el punto donde se
    le manda la orden a la Pi del punto correspondiente.
    """
    from app.models.visita import AccesoFisico, AperturaManual

    data = request.get_json(silent=True) or {}
    acceso_uuid = (data.get("acceso_id") or "").strip()
    if not acceso_uuid:
        return jsonify({"error": {"code": "tranca_requerida",
                                  "message": "Indicá qué tranca abrir"}}), 400

    acceso = AccesoFisico.query.filter_by(id=acceso_uuid, activo=True).first() \
        if acceso_uuid.isdigit() else None
    if not acceso:
        return jsonify({"error": {"code": "tranca_invalida",
                                  "message": "Esa tranca no existe o está inactiva"}}), 400

    # El guardia solo puede abrir trancas de SU punto asignado — no las de otro.
    if acceso.punto_acceso != usuario_actual.punto_acceso_actual:
        return jsonify({"error": {"code": "tranca_fuera_de_tu_punto",
                                  "message": "Esa tranca no pertenece a tu punto de acceso"}}), 403

    apertura = AperturaManual(
        acceso_id=acceso.id,
        guardia_id=usuario_actual.id,
        motivo=(data.get("motivo") or "").strip()[:255] or None,
    )
    db.session.add(apertura)
    db.session.commit()

    return jsonify({"data": apertura.to_dict()}), 201
