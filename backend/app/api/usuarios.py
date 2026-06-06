"""
Módulo de Usuarios — /api/v1/usuarios/

Gestión de todos los usuarios del sistema por el admin:
listar, buscar, crear cajeros, resetear contraseña, activar/desactivar.
"""
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.usuario import Usuario
from app.auth.security import roles_required

usuarios_bp = Blueprint("usuarios", __name__)

PASSWORD_GENERICA = "VillasDelSol2026"


# ── Listar / buscar usuarios ──────────────────────────────────────────────────
@usuarios_bp.get("")
@roles_required("admin", "super_admin")
def listar_usuarios(usuario_actual):
    rol = request.args.get("rol")          # filtro opcional por rol
    buscar = (request.args.get("buscar") or "").strip().lower()

    q = Usuario.query
    if rol:
        q = q.filter_by(rol=rol)
    usuarios = q.order_by(Usuario.created_at.desc()).all()

    data = []
    for u in usuarios:
        if buscar:
            blob = f"{u.nombre} {u.apellido} {u.email}".lower()
            if buscar not in blob:
                continue
        d = u.to_dict()
        d["debe_cambiar_password"] = u.debe_cambiar_password
        data.append(d)
    return jsonify({"data": data})


# ── Crear cajero ──────────────────────────────────────────────────────────────
@usuarios_bp.post("/cajeros")
@roles_required("admin", "super_admin")
def crear_cajero(usuario_actual):
    return _crear_usuario_rol(request, "cajero")


# ── Crear desarrollador (solo super_admin o desarrollador) ────────────────────
@usuarios_bp.post("/desarrolladores")
@roles_required("super_admin", "desarrollador")
def crear_desarrollador(usuario_actual):
    return _crear_usuario_rol(request, "desarrollador")


def _crear_usuario_rol(req, rol):
    data = req.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not nombre or not apellido or not email:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Nombre, apellido y correo son obligatorios"}}), 400
    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": {"code": "email_duplicado",
                                  "message": "Ya existe un usuario con ese correo"}}), 400

    u = Usuario(
        nombre=nombre, apellido=apellido, email=email,
        rol=rol, activo=True, debe_cambiar_password=True,
    )
    u.set_password(PASSWORD_GENERICA)
    db.session.add(u)
    db.session.commit()

    d = u.to_dict()
    d["password_generica"] = PASSWORD_GENERICA
    return jsonify({"data": d}), 201


# ── Resetear contraseña de cualquier usuario ──────────────────────────────────
@usuarios_bp.post("/<uuid_usuario>/reset-password")
@roles_required("admin", "super_admin")
def reset_password(usuario_actual, uuid_usuario):
    u = Usuario.query.filter_by(uuid_publico=uuid_usuario).first()
    if not u:
        return jsonify({"error": {"code": "no_encontrado", "message": "Usuario no encontrado"}}), 404

    u.set_password(PASSWORD_GENERICA)
    u.debe_cambiar_password = True
    db.session.commit()
    return jsonify({"data": {"message": "Contraseña restablecida",
                             "password_generica": PASSWORD_GENERICA}})


# ── Activar / desactivar usuario ──────────────────────────────────────────────
@usuarios_bp.put("/<uuid_usuario>")
@roles_required("admin", "super_admin")
def editar_usuario(usuario_actual, uuid_usuario):
    u = Usuario.query.filter_by(uuid_publico=uuid_usuario).first()
    if not u:
        return jsonify({"error": {"code": "no_encontrado", "message": "Usuario no encontrado"}}), 404

    data = request.get_json(silent=True) or {}

    # Datos de información extendida (la administración los gestiona)
    campos_texto = ["nombre", "apellido", "telefono", "dni", "rtn",
                    "direccion_exacta", "profesion",
                    "contacto_emergencia_nombre", "contacto_emergencia_telefono"]
    for campo in campos_texto:
        if campo in data:
            valor = (data[campo] or "").strip() or None
            setattr(u, campo, valor)

    if "activo" in data:
        # No permitir desactivarse a sí mismo
        if u.id == usuario_actual.id and not data["activo"]:
            return jsonify({"error": {"code": "auto_desactivacion",
                                      "message": "No podés desactivar tu propia cuenta"}}), 400
        u.activo = bool(data["activo"])
    db.session.commit()
    return jsonify({"data": u.to_dict()})
