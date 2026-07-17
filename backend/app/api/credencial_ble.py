"""
Credencial BLE — acceso por Bluetooth de baja energía, atado al dispositivo.

A diferencia de la tarjeta virtual QR, esta credencial vive en UN teléfono
específico. Diseñada con defensas de nivel profesional:

  - Atada al device_id: iniciar sesión en otro teléfono NO da acceso BLE
  - Clave secreta única para desafío-respuesta HMAC (nunca viaja en claro)
  - Rolling counter anti-repetición
  - Token rotado cada 24h
  - Máximo 1 dispositivo activo por residente

Endpoints (residente):
  GET  /mi-ble                → estado de la credencial
  POST /mi-ble/activar        → registra el dispositivo actual y genera credencial
  POST /mi-ble/suspender      → desactiva (perdió el teléfono)
  POST /mi-ble/reactivar      → reactiva con token y clave nuevos
  POST /mi-ble/registrar-uso  → incrementa el contador tras un acceso exitoso
"""
import secrets
import datetime as dt

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.auth.security import token_required
from app.models.cuenta import CredencialBLE, Residente

ble_bp = Blueprint("credencial_ble", __name__)


def _err(code, msg, status=400):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _mi_residente(usuario):
    r = Residente.query.filter_by(usuario_id=usuario.id, activo=True).first()
    if not r:
        return None, None
    return r, r.cuenta


def _generar_token():
    """Token BLE de 16 bytes en hex — lo que el teléfono transmite al lector."""
    for _ in range(10):
        t = "BLE" + secrets.token_hex(8).upper()  # BLE + 16 hex = 19 chars
        if not CredencialBLE.query.filter_by(token_hoy=t).first():
            return t
    raise RuntimeError("No se pudo generar token único")


@ble_bp.get("/mi-ble")
@token_required
def mi_ble(usuario_actual):
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    cred = CredencialBLE.query.filter_by(
        residente_id=residente.id, estado="activa").first()
    if not cred:
        return jsonify({"data": {"tiene_credencial": False}})

    return jsonify({"data": {"tiene_credencial": True, **cred.to_dict()}})


@ble_bp.post("/mi-ble/activar")
@token_required
def activar_ble(usuario_actual):
    """Registra el dispositivo actual y genera la credencial BLE.
    Si el residente ya tenía una credencial en otro dispositivo, la revoca
    (máximo 1 dispositivo activo por residente)."""
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    if cuenta.bloqueada:
        return _err("cuenta_bloqueada",
                    "Tu cuenta tiene mora pendiente. Regularizá el pago para activar el acceso BLE.", 403)

    data = request.get_json(silent=True) or {}
    device_id = (data.get("device_id") or "").strip()
    device_nombre = (data.get("device_nombre") or "Dispositivo").strip()[:120]
    if not device_id:
        return _err("device_requerido", "Falta el identificador del dispositivo", 400)

    # Revocar cualquier credencial previa del residente (en cualquier dispositivo)
    previas = CredencialBLE.query.filter_by(residente_id=residente.id).all()
    for p in previas:
        db.session.delete(p)

    cred = CredencialBLE(
        cuenta_id=cuenta.id,
        residente_id=residente.id,
        device_id=device_id,
        device_nombre=device_nombre,
        token_hoy=_generar_token(),
        clave_secreta=secrets.token_hex(32),  # 64 chars — clave HMAC
        contador=0,
        estado="activa",
        tipo_acceso=cuenta.tipo_acceso_virtual,
    )
    db.session.add(cred)
    db.session.commit()
    # incluir_secretos=True: el dispositivo dueño necesita la clave y el token
    return jsonify({"data": cred.to_dict(incluir_secretos=True)}), 201


@ble_bp.post("/mi-ble/suspender")
@token_required
def suspender_ble(usuario_actual):
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    cred = CredencialBLE.query.filter_by(
        residente_id=residente.id, estado="activa").first()
    if not cred:
        return _err("no_activa", "No tenés una credencial BLE activa", 404)

    cred.estado = "suspendida"
    db.session.commit()
    return jsonify({"data": {"ok": True, "message":
        "Acceso BLE suspendido. Dejará de funcionar en los próximos 5 minutos."}})


@ble_bp.post("/mi-ble/reactivar")
@token_required
def reactivar_ble(usuario_actual):
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    if cuenta.bloqueada:
        return _err("cuenta_bloqueada",
                    "Tu cuenta tiene mora pendiente. Regularizá el pago para reactivar.", 403)

    cred = CredencialBLE.query.filter_by(
        residente_id=residente.id, estado="suspendida").first()
    if not cred:
        return _err("no_suspendida", "No tenés una credencial BLE suspendida", 404)

    # Token, clave y contador nuevos — lo anterior queda invalidado
    cred.token_anterior = None
    cred.token_hoy = _generar_token()
    cred.clave_secreta = secrets.token_hex(32)
    cred.contador = 0
    cred.estado = "activa"
    cred.tipo_acceso = cuenta.tipo_acceso_virtual  # por si el admin lo cambió mientras estaba suspendida
    cred.rotado_en = dt.datetime.utcnow()
    db.session.commit()
    return jsonify({"data": cred.to_dict(incluir_secretos=True)})


@ble_bp.post("/mi-ble/registrar-uso")
@token_required
def registrar_uso_ble(usuario_actual):
    """El teléfono llama aquí después de un acceso exitoso para incrementar
    el rolling counter. Mantiene sincronizado el contador entre teléfono y servidor."""
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    cred = CredencialBLE.query.filter_by(
        residente_id=residente.id, estado="activa").first()
    if not cred:
        return _err("no_activa", "No tenés una credencial BLE activa", 404)

    cred.contador += 1
    cred.ultimo_uso = dt.datetime.utcnow()
    db.session.commit()
    return jsonify({"data": {"contador": cred.contador}})
