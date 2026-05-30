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

from app.extensions import db
from app.models.usuario import Usuario
from app.auth.security import generar_token, token_required

auth_bp = Blueprint("auth", __name__)


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
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Email y contraseña son obligatorios"}}), 400

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario or not usuario.check_password(password):
        return jsonify({"error": {"code": "credenciales_invalidas",
                                  "message": "Email o contraseña incorrectos"}}), 401

    if not usuario.activo:
        return jsonify({"error": {"code": "usuario_inactivo",
                                  "message": "Tu usuario está inactivo. Revisá tu correo para activar tu cuenta."}}), 403

    usuario.ultimo_acceso = dt.datetime.utcnow()
    db.session.commit()

    token = generar_token(usuario)
    return jsonify({"data": {"token": token, "usuario": usuario.to_dict()}})


# ── Me ─────────────────────────────────────────────────────────
@auth_bp.get("/me")
@token_required
def me(usuario_actual):
    return jsonify({"data": {"usuario": usuario_actual.to_dict()}})


# ── Activación de cuenta ───────────────────────────────────────
@auth_bp.post("/activar")
def activar_cuenta():
    """El residente recibe un link con un token. Aquí define su contraseña."""
    data = request.get_json(silent=True) or {}
    token_str = data.get("token") or ""
    password = data.get("password") or ""

    if not token_str or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Token y contraseña son obligatorios"}}), 400
    if len(password) < 6:
        return jsonify({"error": {"code": "password_debil",
                                  "message": "La contraseña debe tener al menos 6 caracteres"}}), 400

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

    return jsonify({"data": {
        "message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña.",
        # SOLO EN DESARROLLO: devolver el token para pruebas
        "dev_token": token_reset,
    }})


# ── Restablecer contraseña ─────────────────────────────────────
@auth_bp.post("/reset")
def restablecer_password():
    data = request.get_json(silent=True) or {}
    token_str = data.get("token") or ""
    password = data.get("password") or ""

    if not token_str or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Token y nueva contraseña son obligatorios"}}), 400
    if len(password) < 6:
        return jsonify({"error": {"code": "password_debil",
                                  "message": "La contraseña debe tener al menos 6 caracteres"}}), 400

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
