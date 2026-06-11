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

guardias_bp = Blueprint("guardias", __name__)

PASSWORD_GENERICA = "VillasDelSol2026"


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
