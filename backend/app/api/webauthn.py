"""
Módulo WebAuthn — login biométrico (huella / Face ID) vía Passkeys.

Flujo de REGISTRO (usuario ya logueado, activa la huella en su perfil):
  1. POST /webauthn/registro/iniciar    -> genera challenge de registro
  2. POST /webauthn/registro/completar  -> verifica y guarda la credencial

Flujo de LOGIN (entrar con huella, sin contraseña):
  1. POST /webauthn/login/iniciar    -> genera challenge de login (por email)
  2. POST /webauthn/login/completar  -> verifica y devuelve el JWT

Los challenges se guardan en Redis con expiración corta (5 min). Solo se
almacenan llaves públicas; la biometría nunca sale del dispositivo.
"""
import os
import json
import base64
import datetime as dt

import redis as redis_lib
from flask import Blueprint, request, jsonify, current_app

import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, ResidentKeyRequirement,
    UserVerificationRequirement, PublicKeyCredentialDescriptor,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.extensions import db
from app.models.usuario import Usuario
from app.models.credencial_webauthn import CredencialWebAuthn
from app.auth.security import token_required, generar_token

webauthn_bp = Blueprint("webauthn", __name__)


def _redis():
    return redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))


def _rp_id():
    return current_app.config.get("WEBAUTHN_RP_ID", "localhost")


def _origin():
    return current_app.config.get("WEBAUTHN_ORIGIN", "http://localhost:5173")


def _guardar_challenge(clave, challenge_bytes, extra=None):
    """Guarda el challenge en Redis por 5 minutos."""
    data = {"challenge": bytes_to_base64url(challenge_bytes)}
    if extra:
        data.update(extra)
    _redis().setex(f"webauthn:{clave}", 300, json.dumps(data))


def _leer_challenge(clave):
    raw = _redis().get(f"webauthn:{clave}")
    if not raw:
        return None
    _redis().delete(f"webauthn:{clave}")  # un solo uso
    return json.loads(raw)


# ══════════════════════════════════════════════════════════════════
# REGISTRO (el usuario activa la huella en su perfil)
# ══════════════════════════════════════════════════════════════════
@webauthn_bp.post("/registro/iniciar")
@token_required
def registro_iniciar(usuario_actual):
    # Excluir credenciales ya registradas (no registrar el mismo dispositivo 2 veces)
    existentes = CredencialWebAuthn.query.filter_by(usuario_id=usuario_actual.id).all()
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in existentes
    ]

    opciones = webauthn.generate_registration_options(
        rp_id=_rp_id(),
        rp_name=current_app.config.get("WEBAUTHN_RP_NAME", "SICA-VS"),
        user_id=str(usuario_actual.id).encode(),
        user_name=usuario_actual.email,
        user_display_name=f"{usuario_actual.nombre} {usuario_actual.apellido}",
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    _guardar_challenge(f"reg:{usuario_actual.id}", opciones.challenge)
    # options_to_json devuelve un string JSON listo para el navegador
    return current_app.response_class(
        webauthn.options_to_json(opciones), mimetype="application/json")


@webauthn_bp.post("/registro/completar")
@token_required
def registro_completar(usuario_actual):
    data = request.get_json(silent=True) or {}
    credential = data.get("credential")
    nombre_dispositivo = (data.get("nombre_dispositivo") or "Mi dispositivo").strip()[:120]
    if not credential:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Falta la credencial"}}), 400

    guardado = _leer_challenge(f"reg:{usuario_actual.id}")
    if not guardado:
        return jsonify({"error": {"code": "challenge_expirado",
                                  "message": "El registro expiró, intentá de nuevo"}}), 400

    try:
        verificacion = webauthn.verify_registration_response(
            credential=json.dumps(credential),
            expected_challenge=base64url_to_bytes(guardado["challenge"]),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
        )
    except Exception as e:
        return jsonify({"error": {"code": "verificacion_fallida",
                                  "message": f"No se pudo verificar la huella: {e}"}}), 400

    cred = CredencialWebAuthn(
        usuario_id=usuario_actual.id,
        credential_id=bytes_to_base64url(verificacion.credential_id),
        public_key=bytes_to_base64url(verificacion.credential_public_key),
        sign_count=verificacion.sign_count,
        nombre_dispositivo=nombre_dispositivo,
        transports=",".join(credential.get("response", {}).get("transports", []) or []),
    )
    db.session.add(cred)
    db.session.commit()
    return jsonify({"data": {"mensaje": "Huella registrada", "dispositivo": cred.to_dict()}}), 201


# ══════════════════════════════════════════════════════════════════
# LOGIN (entrar con huella, sin contraseña)
# ══════════════════════════════════════════════════════════════════
@webauthn_bp.post("/login/iniciar")
def login_iniciar():
    """
    Inicia el login con huella SIN pedir email (passkey discoverable).
    No se pasa allow_credentials: el teléfono muestra las cuentas que tiene
    guardadas para este sitio y el usuario elige con la huella.
    """
    opciones = webauthn.generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    # Guardamos el challenge bajo una clave global temporal por IP+navegador.
    # Como no hay email, usamos el challenge mismo como clave de recuperación.
    challenge_b64 = bytes_to_base64url(opciones.challenge)
    _redis().setex(f"webauthn:disc:{challenge_b64}", 300, "1")
    return current_app.response_class(
        webauthn.options_to_json(opciones), mimetype="application/json")


@webauthn_bp.post("/login/completar")
def login_completar():
    data = request.get_json(silent=True) or {}
    credential = data.get("credential")
    if not credential:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Faltan datos"}}), 400

    # Recuperar el challenge que enviamos (viene dentro de clientDataJSON,
    # pero lo validamos contra el que guardamos en Redis).
    import base64 as _b64
    try:
        client_data_b64 = credential.get("response", {}).get("clientDataJSON", "")
        # base64url decode con padding
        padded = client_data_b64 + "=" * (-len(client_data_b64) % 4)
        client_data = json.loads(_b64.urlsafe_b64decode(padded))
        challenge_recibido = client_data.get("challenge", "")
    except Exception:
        return jsonify({"error": {"code": "datos_invalidos",
                                  "message": "Datos de la huella inválidos"}}), 400

    # Verificar que ese challenge lo emitimos nosotros (anti-replay)
    if not _redis().get(f"webauthn:disc:{challenge_recibido}"):
        return jsonify({"error": {"code": "challenge_expirado",
                                  "message": "El inicio de sesión expiró, intentá de nuevo"}}), 400
    _redis().delete(f"webauthn:disc:{challenge_recibido}")  # un solo uso

    # Descubrir el usuario por la credencial (el teléfono nos dice cuál usó)
    cred_id = credential.get("id")
    cred = CredencialWebAuthn.query.filter_by(credential_id=cred_id).first()
    if not cred:
        return jsonify({"error": {"code": "credencial_invalida",
                                  "message": "Esta huella no está registrada en el sistema"}}), 400

    try:
        verificacion = webauthn.verify_authentication_response(
            credential=json.dumps(credential),
            expected_challenge=base64url_to_bytes(challenge_recibido),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        return jsonify({"error": {"code": "verificacion_fallida",
                                  "message": f"No se pudo verificar la huella: {e}"}}), 400

    usuario = Usuario.query.filter_by(id=cred.usuario_id).first()
    if not usuario or not usuario.activo:
        return jsonify({"error": {"code": "usuario_inactivo",
                                  "message": "Usuario inactivo"}}), 403

    cred.sign_count = verificacion.new_sign_count
    cred.ultimo_uso = dt.datetime.now(dt.timezone.utc)
    usuario.ultimo_acceso = dt.datetime.utcnow()

    token, jti, expira = generar_token(usuario, devolver_jti=True)
    from app.models.sesion_activa import SesionActiva, describir_dispositivo
    ua = (request.user_agent.string or "")[:300]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    db.session.add(SesionActiva(
        usuario_id=usuario.id, jti=jti,
        dispositivo=describir_dispositivo(ua), user_agent=ua, ip=ip[:45],
        expira_en=expira,
    ))
    db.session.commit()

    return jsonify({"data": {
        "token": token,
        "usuario": usuario.to_dict(),
    }})


# ══════════════════════════════════════════════════════════════════
# GESTIÓN (ver y quitar dispositivos con huella)
# ══════════════════════════════════════════════════════════════════
@webauthn_bp.get("/credenciales")
@token_required
def listar_credenciales(usuario_actual):
    creds = CredencialWebAuthn.query.filter_by(usuario_id=usuario_actual.id).all()
    return jsonify({"data": [c.to_dict() for c in creds]})


@webauthn_bp.delete("/credenciales/<int:cred_id>")
@token_required
def eliminar_credencial(usuario_actual, cred_id):
    cred = CredencialWebAuthn.query.filter_by(id=cred_id, usuario_id=usuario_actual.id).first()
    if not cred:
        return jsonify({"error": {"code": "no_encontrado", "message": "No encontrada"}}), 404
    db.session.delete(cred)
    db.session.commit()
    return jsonify({"data": {"mensaje": "Dispositivo eliminado"}})
