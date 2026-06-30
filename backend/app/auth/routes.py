"""
Endpoints de autenticación.

  POST /api/v1/auth/login        { email, password }      -> { token, usuario }
  GET  /api/v1/auth/me           (con token)              -> { usuario }
  POST /api/v1/auth/activar      { token, password }      -> activa cuenta y define contraseña
  POST /api/v1/auth/recuperar    { email }                -> envía token de recuperación
  POST /api/v1/auth/reset        { token, password }      -> define nueva contraseña
"""
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.config import Config
from app.models.usuario import Usuario
from app.auth.security import generar_token, token_required, revocar_token

auth_bp = Blueprint("auth", __name__)


def validar_password(password):
    """
    Valida la política mínima de contraseñas:
    - Al menos 8 caracteres
    - Al menos una letra mayúscula
    - Al menos un signo (carácter no alfanumérico)
    Devuelve None si es válida, o un mensaje de error si no.
    """
    import re
    if not password or len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres"
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe incluir al menos una letra mayúscula"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "La contraseña debe incluir al menos un signo (ej: ! @ # $ % & *)"
    return None


def _generar_token_temporal(email, proposito, horas=48):
    """Genera un JWT de corta vida para activación o recuperación."""
    payload = {
        "sub": email,
        "proposito": proposito,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=horas),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _verificar_token_temporal(token_str, proposito_esperado):
    """Decodifica un token temporal y devuelve el email o None."""
    try:
        p = jwt.decode(token_str, current_app.config["JWT_SECRET"], algorithms=["HS256"])
        if p.get("proposito") != proposito_esperado:
            return None
        return p.get("sub")
    except jwt.PyJWTError:
        return None


# ── Login ──────────────────────────────────────────────────────
@auth_bp.post("/login")
@limiter.limit(lambda: Config.LOGIN_RATE_LIMIT)
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Email y contraseña son obligatorios"}}), 400

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario or not usuario.check_password(password):
        from flask import g
        g.email_intento = email[:120] if email else None
        return jsonify({"error": {"code": "credenciales_invalidas",
                                  "message": "Email o contraseña incorrectos"}}), 401

    if not usuario.activo:
        return jsonify({"error": {"code": "usuario_inactivo",
                                  "message": "Tu usuario está inactivo. Revisá tu correo para activar tu cuenta."}}), 403

    usuario.ultimo_acceso = dt.datetime.utcnow()

    # Generar token y registrar la sesión activa (dispositivo)
    token, jti, expira = generar_token(usuario, devolver_jti=True)
    from app.models.sesion_activa import SesionActiva, describir_dispositivo
    ua = (request.user_agent.string or "")[:300]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if ip:
        ip = ip.split(",")[0].strip()[:45]
    db.session.add(SesionActiva(
        usuario_id=usuario.id, jti=jti,
        dispositivo=describir_dispositivo(ua), user_agent=ua, ip=ip,
        expira_en=expira,
    ))
    db.session.commit()

    return jsonify({"data": {"token": token, "usuario": usuario.to_dict()}})


# ── Me ─────────────────────────────────────────────────────────
@auth_bp.get("/me")
@token_required
def me(usuario_actual):
    return jsonify({"data": {"usuario": usuario_actual.to_dict()}})


# ── Cambiar contraseña (usuario autenticado) ───────────────────
@auth_bp.post("/cambiar-password")
@token_required
def cambiar_password(usuario_actual):
    data = request.get_json(silent=True) or {}
    actual = data.get("password_actual") or ""
    nueva = data.get("password_nueva") or ""

    # Si el usuario está obligado a cambiar (primer login), no exigimos la actual
    if not usuario_actual.debe_cambiar_password:
        if not usuario_actual.check_password(actual):
            return jsonify({"error": {"code": "password_incorrecta",
                                      "message": "La contraseña actual es incorrecta"}}), 400

    error = validar_password(nueva)
    if error:
        return jsonify({"error": {"code": "password_debil", "message": error}}), 400

    usuario_actual.set_password(nueva)
    usuario_actual.debe_cambiar_password = False
    db.session.commit()

    return jsonify({"data": {"message": "Contraseña actualizada correctamente",
                             "usuario": usuario_actual.to_dict()}})


# ── Actualizar perfil (nombre, teléfono) ───────────────────────
@auth_bp.put("/perfil")
@token_required
def actualizar_perfil(usuario_actual):
    data = request.get_json(silent=True) or {}
    if "nombre" in data and data["nombre"].strip():
        usuario_actual.nombre = data["nombre"].strip()
    if "apellido" in data and data["apellido"].strip():
        usuario_actual.apellido = data["apellido"].strip()
    if "telefono" in data:
        usuario_actual.telefono = data["telefono"].strip()
    db.session.commit()
    return jsonify({"data": {"usuario": usuario_actual.to_dict()}})


# ── Activación de cuenta ───────────────────────────────────────
@auth_bp.post("/activar")
@limiter.limit("10 per hour")
def activar_cuenta():
    """El residente recibe un link con un token. Aquí define su contraseña."""
    data = request.get_json(silent=True) or {}
    token_str = data.get("token") or ""
    password = data.get("password") or ""

    if not token_str or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Token y contraseña son obligatorios"}}), 400
    error = validar_password(password)
    if error:
        return jsonify({"error": {"code": "password_debil", "message": error}}), 400

    email = _verificar_token_temporal(token_str, "activacion")
    if not email:
        return jsonify({"error": {"code": "token_invalido",
                                  "message": "El enlace de activación es inválido o expiró"}}), 400

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return jsonify({"error": {"code": "usuario_no_encontrado",
                                  "message": "No se encontró el usuario"}}), 404

    usuario.set_password(password)
    usuario.activo = True
    db.session.commit()

    token = generar_token(usuario)
    return jsonify({"data": {
        "message": "Cuenta activada correctamente",
        "token": token,
        "usuario": usuario.to_dict(),
    }})


# ── Solicitar recuperación de contraseña ───────────────────────
@auth_bp.post("/recuperar")
@limiter.limit("3 per hour")
def solicitar_recuperacion():
    """Genera un token de recuperación. En producción se envía por correo con Resend."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "El correo es obligatorio"}}), 400

    usuario = Usuario.query.filter_by(email=email).first()

    # Siempre respondemos OK para no revelar si el email existe
    if not usuario:
        return jsonify({"data": {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}})

    token_reset = _generar_token_temporal(email, "reset", horas=2)

    # TODO: Integrar Resend para enviar el correo con el link
    # resend.Emails.send({
    #     "from": "SICA-VS <noreply@villasdelsol.hn>",
    #     "to": email,
    #     "subject": "Restablecer contraseña - SICA-VS",
    #     "html": f"<a href='https://sitio/reset?token={token_reset}'>Restablecer</a>"
    # })

    respuesta = {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}
    # El token se devuelve en pantalla SOLO en desarrollo (no hay correos aún).
    # En producción esto sería una fuga crítica: cualquiera con un email válido
    # tomaría la cuenta sin acceder al correo. Por eso se condiciona al entorno.
    if current_app.config.get("ENV") != "production":
        respuesta["dev_token"] = token_reset

    return jsonify({"data": respuesta})


# ── Restablecer contraseña ─────────────────────────────────────
@auth_bp.post("/reset")
@limiter.limit("10 per hour")
def restablecer_password():
    data = request.get_json(silent=True) or {}
    token_str = data.get("token") or ""
    password = data.get("password") or ""

    if not token_str or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Token y nueva contraseña son obligatorios"}}), 400
    error = validar_password(password)
    if error:
        return jsonify({"error": {"code": "password_debil", "message": error}}), 400

    email = _verificar_token_temporal(token_str, "reset")
    if not email:
        return jsonify({"error": {"code": "token_invalido",
                                  "message": "El enlace de recuperación es inválido o expiró"}}), 400

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return jsonify({"error": {"code": "usuario_no_encontrado",
                                  "message": "No se encontró el usuario"}}), 404

    usuario.set_password(password)
    if not usuario.activo:
        usuario.activo = True
    db.session.commit()

    return jsonify({"data": {"message": "Contraseña restablecida correctamente. Ya puedes iniciar sesión."}})


# ── Cerrar sesión (revoca el token actual) ─────────────────────
@auth_bp.post("/logout")
@token_required
def logout(usuario_actual):
    """
    Revoca el token con el que se hizo la petición, añadiéndolo a la
    blacklist. A partir de aquí ese token deja de ser válido aunque
    no haya expirado.
    """
    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else ""
    if token:
        revocar_token(token, usuario_id=usuario_actual.id)
        # Eliminar el registro de sesión activa de este token
        from flask import g
        from app.models.sesion_activa import SesionActiva
        jti = getattr(g, "jti_actual", None)
        if jti:
            SesionActiva.query.filter_by(jti=jti).delete()
            db.session.commit()
    return jsonify({"data": {"message": "Sesión cerrada"}})


# ── Listar mis sesiones activas (dispositivos conectados) ──────
@auth_bp.get("/sesiones")
@token_required
def listar_sesiones(usuario_actual):
    from flask import g
    from app.models.sesion_activa import SesionActiva
    jti_actual = getattr(g, "jti_actual", None)
    sesiones = (SesionActiva.query
                .filter_by(usuario_id=usuario_actual.id)
                .order_by(SesionActiva.ultimo_uso.desc())
                .all())
    return jsonify({"data": [s.to_dict(jti_actual) for s in sesiones]})


# ── Cerrar una sesión específica ───────────────────────────────
@auth_bp.post("/sesiones/<int:sesion_id>/cerrar")
@token_required
def cerrar_sesion(usuario_actual, sesion_id):
    from app.models.sesion_activa import SesionActiva
    from app.models.token_revocado import TokenRevocado
    sesion = SesionActiva.query.filter_by(id=sesion_id, usuario_id=usuario_actual.id).first()
    if not sesion:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Sesión no encontrada"}}), 404
    # Revocar el token de esa sesión (blacklist) y borrar el registro
    if not TokenRevocado.esta_revocado(sesion.jti):
        db.session.add(TokenRevocado(jti=sesion.jti, usuario_id=usuario_actual.id,
                                     expira_en=sesion.expira_en))
    db.session.delete(sesion)
    db.session.commit()
    return jsonify({"data": {"message": "Sesión cerrada en ese dispositivo"}})


# ── Cerrar todas las otras sesiones (menos la actual) ──────────
@auth_bp.post("/sesiones/cerrar-otras")
@token_required
def cerrar_otras_sesiones(usuario_actual):
    from flask import g
    from app.models.sesion_activa import SesionActiva
    from app.models.token_revocado import TokenRevocado
    jti_actual = getattr(g, "jti_actual", None)
    otras = SesionActiva.query.filter(
        SesionActiva.usuario_id == usuario_actual.id,
        SesionActiva.jti != jti_actual,
    ).all()
    for s in otras:
        if not TokenRevocado.esta_revocado(s.jti):
            db.session.add(TokenRevocado(jti=s.jti, usuario_id=usuario_actual.id,
                                         expira_en=s.expira_en))
        db.session.delete(s)
    db.session.commit()
    return jsonify({"data": {"message": f"Se cerraron {len(otras)} sesiones", "cerradas": len(otras)}})
