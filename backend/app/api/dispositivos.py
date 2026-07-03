"""
API de dispositivos móviles — registro de tokens FCM para notificaciones push.

La app móvil llama a estos endpoints:
- POST /dispositivos/registrar    → al iniciar sesión (guarda el token)
- POST /dispositivos/desregistrar → al cerrar sesión (desactiva el token)
"""
import datetime as dt
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.auth.security import token_required
from app.models.dispositivo_movil import DispositivoMovil

dispositivos_bp = Blueprint("dispositivos", __name__)


@dispositivos_bp.post("/registrar")
@token_required
def registrar(usuario_actual):
    """Registra o actualiza el token FCM del dispositivo del usuario.
    Si el token ya existía (mismo teléfono), lo reasigna a este usuario."""
    body = request.get_json(silent=True) or {}
    token = (body.get("fcm_token") or "").strip()
    plataforma = (body.get("plataforma") or "android").strip()

    if not token:
        return jsonify({"error": {"code": "TOKEN_REQUERIDO",
                                  "message": "Falta el token FCM"}}), 400

    # ¿Ya existe este token? (mismo teléfono)
    disp = DispositivoMovil.query.filter_by(fcm_token=token).first()
    if disp:
        # Reasignar al usuario actual y reactivar
        disp.usuario_id = usuario_actual.id
        disp.activo = True
        disp.plataforma = plataforma
        disp.ultima_actividad = dt.datetime.utcnow()
    else:
        disp = DispositivoMovil(
            fcm_token=token,
            usuario_id=usuario_actual.id,
            plataforma=plataforma,
        )
        db.session.add(disp)

    db.session.commit()
    return jsonify({"data": {"registrado": True}})


@dispositivos_bp.post("/desregistrar")
@token_required
def desregistrar(usuario_actual):
    """Desactiva el token FCM (al cerrar sesión). No lo borra para conservar
    el historial, solo lo marca inactivo."""
    body = request.get_json(silent=True) or {}
    token = (body.get("fcm_token") or "").strip()

    if token:
        disp = DispositivoMovil.query.filter_by(
            fcm_token=token, usuario_id=usuario_actual.id
        ).first()
        if disp:
            disp.activo = False
            db.session.commit()

    return jsonify({"data": {"desregistrado": True}})
