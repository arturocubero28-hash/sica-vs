"""
Módulo de Guardias — /api/v1/guardias/

El admin crea y administra los usuarios guardia.
Cada guardia se crea con una contraseña genérica y debe cambiarla
obligatoriamente en su primer inicio de sesión.
"""
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.usuario import Usuario
from app.auth.security import roles_required

guardias_bp = Blueprint("guardias", __name__)

PASSWORD_GENERICA = "VillasDelSol2026"


# ── Listar guardias ───────────────────────────────────────────────────────────
@guardias_bp.get("")
@roles_required("admin", "super_admin")
def listar_guardias(usuario_actual):
    guardias = (Usuario.query
                .filter_by(rol="guardia")
                .order_by(Usuario.created_at.desc())
                .all())
    data = []
    for g in guardias:
        d = g.to_dict()
        d["debe_cambiar_password"] = g.debe_cambiar_password
        data.append(d)
    return jsonify({"data": data})


# ── Crear guardia ─────────────────────────────────────────────────────────────
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

    guardia = Usuario(
        nombre=nombre, apellido=apellido, email=email,
        rol="guardia", activo=True,
        debe_cambiar_password=True,   # obligado a cambiar en el primer login
    )
    guardia.set_password(PASSWORD_GENERICA)
    db.session.add(guardia)
    db.session.commit()

    d = guardia.to_dict()
    d["password_generica"] = PASSWORD_GENERICA  # mostrar al admin para entregársela
    return jsonify({"data": d}), 201


# ── Activar / desactivar guardia ──────────────────────────────────────────────
@guardias_bp.put("/<uuid_guardia>")
@roles_required("admin", "super_admin")
def editar_guardia(usuario_actual, uuid_guardia):
    g = Usuario.query.filter_by(uuid_publico=uuid_guardia, rol="guardia").first()
    if not g:
        return jsonify({"error": {"code": "no_encontrado", "message": "Guardia no encontrado"}}), 404

    data = request.get_json(silent=True) or {}
    if "nombre" in data and data["nombre"].strip():
        g.nombre = data["nombre"].strip()
    if "apellido" in data and data["apellido"].strip():
        g.apellido = data["apellido"].strip()
    if "activo" in data:
        g.activo = bool(data["activo"])
    db.session.commit()
    return jsonify({"data": g.to_dict()})


# ── Resetear contraseña del guardia a la genérica ─────────────────────────────
@guardias_bp.post("/<uuid_guardia>/reset-password")
@roles_required("admin", "super_admin")
def reset_password_guardia(usuario_actual, uuid_guardia):
    g = Usuario.query.filter_by(uuid_publico=uuid_guardia, rol="guardia").first()
    if not g:
        return jsonify({"error": {"code": "no_encontrado", "message": "Guardia no encontrado"}}), 404

    g.set_password(PASSWORD_GENERICA)
    g.debe_cambiar_password = True
    db.session.commit()
    return jsonify({"data": {"message": "Contraseña restablecida",
                             "password_generica": PASSWORD_GENERICA}})
