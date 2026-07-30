"""
Módulo de Usuarios — /api/v1/usuarios/

Gestión de todos los usuarios del sistema por el admin:
listar, buscar, crear cajeros, resetear contraseña, activar/desactivar.
"""
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.usuario import Usuario
from app.auth.security import roles_required
from app.utils.passwords import generar_password_temporal, puede_gestionar_rol, ROLES_CREDENCIAL_LOCAL
from app.utils.residencial import residencial_id_heredado

usuarios_bp = Blueprint("usuarios", __name__)


# ── Listar / buscar usuarios ──────────────────────────────────────────────────
@usuarios_bp.get("")
@roles_required("admin", "super_admin")
def listar_usuarios(usuario_actual):
    rol = request.args.get("rol")          # filtro opcional por rol
    buscar = (request.args.get("buscar") or "").strip().lower()

    from app.utils.residencial import scope_usuarios
    q = scope_usuarios(Usuario.query, usuario_actual)
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
        d["ultimo_acceso"] = u.ultimo_acceso.isoformat() if u.ultimo_acceso else None
        data.append(d)
    return jsonify({"data": data})


# ── Crear cajero ──────────────────────────────────────────────────────────────
@usuarios_bp.post("/cajeros")
@roles_required("admin", "super_admin")
def crear_cajero(usuario_actual):
    return _crear_usuario_rol(request, "cajero", usuario_actual)


# ── Crear supervisor (bases multi-residencial, Día 37) ─────────────────────────
# Solo admin/super_admin — ver puede_gestionar_rol(): ni siquiera otro
# supervisor puede crear uno nuevo, así el admin dueño mantiene el control
# de quién tiene su mismo nivel de acceso.
@usuarios_bp.post("/supervisores")
@roles_required("admin", "super_admin")
def crear_supervisor(usuario_actual):
    return _crear_usuario_rol(request, "supervisor", usuario_actual)


# ── Crear desarrollador (solo super_admin o desarrollador) ────────────────────
@usuarios_bp.post("/desarrolladores")
@roles_required("super_admin", "desarrollador")
def crear_desarrollador(usuario_actual):
    return _crear_usuario_rol(request, "desarrollador", usuario_actual)


def _crear_usuario_rol(req, rol, usuario_actual):
    # SEC-01: jerarquía de roles — un admin no puede crear un super_admin
    # ni un desarrollador. Solo super_admin/desarrollador pueden hacerlo.
    # También cubre la regla especial de 'supervisor' (Día 37): solo
    # admin/super_admin puede crear uno, ni siquiera otro supervisor.
    if not puede_gestionar_rol(usuario_actual.rol, rol):
        return jsonify({"error": {"code": "rol_insuficiente",
                                  "message": f"Tu rol no tiene permiso para crear usuarios "
                                             f"con rol '{rol}'"}}), 403

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

    # Día 50 — sistema de suscripciones.
    from app.utils.residencial import limite_usuarios_alcanzado
    if limite_usuarios_alcanzado(usuario_actual.residencial_id):
        return jsonify({"error": {"code": "limite_usuarios",
                                  "message": "Tu plan actual no permite más usuarios. "
                                             "Pedile a tu desarrollador que te suba de plan."}}), 402

    # SEC-01: contraseña aleatoria por usuario, no una fija compartida.
    # Se muestra una sola vez en la respuesta para que el admin la anote
    # y se la entregue en papel; el usuario debe cambiarla en su primer login.
    password_temporal = generar_password_temporal()

    u = Usuario(
        nombre=nombre, apellido=apellido, email=email,
        rol=rol, activo=True, debe_cambiar_password=True,
        # Bases multi-residencial (Día 37): cajero y supervisor heredan la
        # residencial de quien los crea. desarrollador queda sin residencial
        # (rol de plataforma) — residencial_id_heredado() ya lo maneja.
        residencial_id=residencial_id_heredado(usuario_actual),
    )
    u.set_password(password_temporal)
    db.session.add(u)
    db.session.commit()

    d = u.to_dict()
    d["password_generica"] = password_temporal
    return jsonify({"data": d}), 201


# ── Resetear contraseña de guardias/cajeros (solo desde el panel admin) ───────
@usuarios_bp.post("/<uuid_usuario>/reset-password")
@roles_required("admin", "super_admin")
def reset_password(usuario_actual, uuid_usuario):
    from app.utils.residencial import pertenece_a_mi_residencial
    u = Usuario.query.filter_by(uuid_publico=uuid_usuario).first()
    # Día 48 — hallazgo de auditoría, el más grave del día: sin este
    # chequeo, un admin de otra residencial podía resetear la contraseña
    # de un guardia/cajero ajeno y ver la clave nueva generada — un
    # secuestro de cuenta completo, con solo conocer el UUID del usuario.
    if not u or not pertenece_a_mi_residencial(u, usuario_actual):
        return jsonify({"error": {"code": "no_encontrado", "message": "Usuario no encontrado"}}), 404

    # SEC-01: un usuario no puede resetearse su propia contraseña por esta vía
    if u.id == usuario_actual.id:
        return jsonify({"error": {"code": "auto_reset",
                                  "message": "No podés resetear tu propia contraseña por acá. "
                                             "Usá 'Cambiar contraseña' en tu perfil."}}), 400

    # SEC-01: jerarquía de roles — un admin no puede resetear a un
    # super_admin ni a un desarrollador. Solo super_admin puede hacerlo.
    if not puede_gestionar_rol(usuario_actual.rol, u.rol):
        return jsonify({"error": {"code": "rol_insuficiente",
                                  "message": "Tu rol no tiene permiso para resetear "
                                             "la contraseña de este usuario"}}), 403

    # SEC-01: este endpoint es SOLO para credenciales locales de papel
    # (guardia, cajero). Residentes, admins y super_admins usan el flujo
    # de recuperación por correo electrónico — no se les genera ni
    # muestra una contraseña en pantalla.
    if u.rol not in ROLES_CREDENCIAL_LOCAL:
        return jsonify({"error": {"code": "usa_recuperacion_email",
                                  "message": "Este usuario debe recuperar su contraseña por "
                                             "correo electrónico, no desde este panel."}}), 400

    password_temporal = generar_password_temporal()
    u.set_password(password_temporal)
    u.debe_cambiar_password = True
    db.session.commit()
    return jsonify({"data": {"message": "Contraseña restablecida",
                             "password_generica": password_temporal}})


# ── Activar / desactivar usuario ──────────────────────────────────────────────
@usuarios_bp.put("/<uuid_usuario>")
@roles_required("admin", "super_admin")
def editar_usuario(usuario_actual, uuid_usuario):
    from app.utils.residencial import pertenece_a_mi_residencial
    u = Usuario.query.filter_by(uuid_publico=uuid_usuario).first()
    # Día 48 — hallazgo de auditoría: sin este chequeo, un admin de otra
    # residencial podía editar o desactivar un usuario ajeno con solo
    # conocer su UUID.
    if not u or not pertenece_a_mi_residencial(u, usuario_actual):
        return jsonify({"error": {"code": "no_encontrado", "message": "Usuario no encontrado"}}), 404

    # SEC-01: jerarquía de roles — un admin no puede editar/desactivar a un
    # super_admin ni desarrollador. Se exceptúa el propio usuario editando
    # sus propios datos de contacto (nombre, teléfono, etc. — no rol).
    if u.id != usuario_actual.id and not puede_gestionar_rol(usuario_actual.rol, u.rol):
        return jsonify({"error": {"code": "rol_insuficiente",
                                  "message": "Tu rol no tiene permiso para editar este usuario"}}), 403

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
