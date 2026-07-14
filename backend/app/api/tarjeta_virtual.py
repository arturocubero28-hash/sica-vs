"""
Tarjeta Virtual — QR permanente de acceso para residentes.

El residente activa su tarjeta virtual una sola vez. A partir de ahí:
  - Se genera un código de 10 dígitos que cambia cada 24h (medianoche)
  - El residente lo ve en la app como QR o lo agrega a Google/Apple Wallet
  - La Pi lo valida igual que una tarjeta RFID física — misma tabla, mismo flujo

Endpoints:
  GET  /mi-tarjeta-virtual          → estado de la tarjeta del residente
  POST /mi-tarjeta-virtual/activar  → crea la tarjeta si no existe
  POST /mi-tarjeta-virtual/suspender → la desactiva (ej. perdió el teléfono)
  POST /mi-tarjeta-virtual/reactivar → la reactiva
  GET  /mi-tarjeta-virtual/wallet-pass → pase para Google Wallet (JWT firmado)
"""
import secrets
import datetime as dt
import json
import base64

from flask import Blueprint, jsonify, request, current_app

from app.extensions import db
from app.auth.security import token_required
from app.models.cuenta import TarjetaVirtual, Residente, Cuenta

tv_bp = Blueprint("tarjeta_virtual", __name__)


def _err(code, msg, status=400):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _mi_residente(usuario):
    """Devuelve (residente, cuenta) del usuario actual o (None, None)."""
    r = Residente.query.filter_by(usuario_id=usuario.id, activo=True).first()
    if not r:
        return None, None
    return r, r.cuenta


def _generar_codigo_unico():
    """Genera un código SV + 10 dígitos que no exista ya en la tabla."""
    for _ in range(10):
        codigo = "SV" + str(secrets.randbelow(10 ** 10)).zfill(10)
        if not TarjetaVirtual.query.filter_by(codigo_hoy=codigo).first():
            return codigo
    raise RuntimeError("No se pudo generar un código único")


@tv_bp.get("/mi-tarjeta-virtual")
@token_required
def mi_tarjeta_virtual(usuario_actual):
    """Estado actual de la tarjeta virtual del residente."""
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    tv = TarjetaVirtual.query.filter_by(cuenta_id=cuenta.id).first()
    if not tv:
        return jsonify({"data": {"tiene_tarjeta": False}})

    return jsonify({"data": {
        "tiene_tarjeta": True,
        **tv.to_dict(),
    }})


@tv_bp.post("/mi-tarjeta-virtual/activar")
@token_required
def activar_tarjeta_virtual(usuario_actual):
    """Crea la tarjeta virtual del residente si no existe. Si ya existe la reactiva."""
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    if cuenta.bloqueada:
        return _err("cuenta_bloqueada",
                    "Tu cuenta tiene mora pendiente. Regularizá el pago para activar la tarjeta virtual.", 403)

    tv = TarjetaVirtual.query.filter_by(cuenta_id=cuenta.id).first()

    if tv:
        if tv.estado == "activa":
            return _err("ya_activa", "Tu tarjeta virtual ya está activa", 400)
        tv.estado = "activa"
        db.session.commit()
        return jsonify({"data": tv.to_dict()})

    # Primera vez — generar código y crear la tarjeta
    codigo = _generar_codigo_unico()
    tv = TarjetaVirtual(
        cuenta_id=cuenta.id,
        residente_id=residente.id,
        codigo_hoy=codigo,
        estado="activa",
        tipo_acceso="peatonal",
    )
    db.session.add(tv)
    db.session.commit()
    return jsonify({"data": tv.to_dict()}), 201


@tv_bp.post("/mi-tarjeta-virtual/suspender")
@token_required
def suspender_tarjeta_virtual(usuario_actual):
    """Suspende la tarjeta (ej. perdió el teléfono). El código deja de funcionar
    en el próximo sync de la Pi (máx 5 min)."""
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    tv = TarjetaVirtual.query.filter_by(cuenta_id=cuenta.id, estado="activa").first()
    if not tv:
        return _err("no_activa", "No tenés una tarjeta virtual activa", 404)

    tv.estado = "suspendida"
    db.session.commit()
    return jsonify({"data": {"ok": True, "message":
        "Tarjeta suspendida. Dejará de funcionar en los próximos 5 minutos."}})


@tv_bp.post("/mi-tarjeta-virtual/reactivar")
@token_required
def reactivar_tarjeta_virtual(usuario_actual):
    """Reactiva una tarjeta suspendida y genera un código nuevo (el anterior
    quedó potencialmente expuesto)."""
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    if cuenta.bloqueada:
        return _err("cuenta_bloqueada",
                    "Tu cuenta tiene mora pendiente. Regularizá el pago para reactivar.", 403)

    tv = TarjetaVirtual.query.filter_by(cuenta_id=cuenta.id, estado="suspendida").first()
    if not tv:
        return _err("no_suspendida", "No tenés una tarjeta virtual suspendida", 404)

    # Generar código nuevo — el anterior quedó comprometido
    tv.codigo_anterior = None  # no aceptar el código viejo bajo ninguna circunstancia
    tv.codigo_hoy = _generar_codigo_unico()
    tv.estado = "activa"
    tv.rotado_en = dt.datetime.utcnow()
    db.session.commit()
    return jsonify({"data": tv.to_dict()})


@tv_bp.get("/mi-tarjeta-virtual/wallet-pass")
@token_required
def wallet_pass(usuario_actual):
    """
    Devuelve el JWT firmado para Google Wallet Pass.
    La wallet llama a este endpoint cada vez que necesita actualizar el pase —
    típicamente después de la rotación de medianoche.

    El pass contiene el código del día como QR. Google Wallet lo muestra
    sin conexión una vez descargado.
    """
    residente, cuenta = _mi_residente(usuario_actual)
    if not residente:
        return _err("no_residente", "No sos residente activo", 403)

    tv = TarjetaVirtual.query.filter_by(cuenta_id=cuenta.id, estado="activa").first()
    if not tv:
        return _err("no_activa", "No tenés una tarjeta virtual activa", 404)

    if cuenta.bloqueada:
        return _err("cuenta_bloqueada",
                    "Tu cuenta tiene mora pendiente. La tarjeta está bloqueada.", 403)

    titular = residente.usuario
    nombre = f"{titular.nombre} {titular.apellido}" if titular else "Residente"

    # Objeto del pase para Google Wallet (Generic Pass)
    pass_obj = {
        "iss": current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", ""),
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(dt.datetime.utcnow().timestamp()),
        "payload": {
            "genericObjects": [{
                "id": f"{current_app.config.get('GOOGLE_ISSUER_ID', 'demo')}.tv_{tv.uuid_publico}",
                "classId": f"{current_app.config.get('GOOGLE_ISSUER_ID', 'demo')}.acceso_residencial",
                "genericType": "GENERIC_TYPE_UNSPECIFIED",
                "hexBackgroundColor": "#022E45",
                "logo": {
                    "sourceUri": {"uri": current_app.config.get("LOGO_URL", "")},
                    "contentDescription": {"defaultValue": {"language": "es", "value": "SICA-VS"}},
                },
                "cardTitle": {
                    "defaultValue": {"language": "es", "value": "Residencial Villas del Sol"}
                },
                "subheader": {
                    "defaultValue": {"language": "es", "value": "Tarjeta de Acceso"}
                },
                "header": {
                    "defaultValue": {"language": "es", "value": nombre}
                },
                "barcode": {
                    "type": "QR_CODE",
                    "value": tv.codigo_hoy,
                },
                "textModulesData": [
                    {"header": "Tipo de acceso", "body": tv.tipo_acceso.capitalize(), "id": "tipo"},
                ],
                "validTimeInterval": {
                    "start": {"date": dt.datetime.utcnow().isoformat() + "Z"},
                    "end": {"date": (dt.datetime.utcnow().replace(hour=0, minute=0, second=0)
                                    + dt.timedelta(days=1)).isoformat() + "Z"},
                },
            }]
        }
    }

    # Si no están configuradas las credenciales de Google → devolver el objeto
    # sin firmar (modo desarrollo / Apple Wallet usa el QR directo)
    service_key = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not service_key:
        return jsonify({"data": {
            "modo": "desarrollo",
            "nota": "Configurá GOOGLE_SERVICE_ACCOUNT_KEY para habilitar Google Wallet",
        }})

    # Firmar con la clave de servicio (JWT RS256)
    try:
        import google.auth.crypt
        import google.auth.jwt
        signer = google.auth.crypt.RSASigner.from_service_account_info(json.loads(service_key))
        token = google.auth.jwt.encode(signer, pass_obj).decode("utf-8")
        wallet_url = f"https://pay.google.com/gp/v/save/{token}"
        return jsonify({"data": {
            "wallet_url": wallet_url,
            "codigo_hoy": tv.codigo_hoy,
        }})
    except Exception as e:
        return _err("wallet_error", f"No se pudo generar el pase: {str(e)}", 500)


@tv_bp.post("/wallet-callback")
def wallet_callback():
    """
    Google Wallet llama a este endpoint cuando el pase del residente expira
    (a medianoche) para obtener el QR actualizado.

    Google envía un JSON con el objeto del pase que necesita actualizar.
    El servidor responde con el pase actualizado (nuevo codigo_hoy).

    Este endpoint es público (sin token del residente) — Google se autentica
    con su propia firma en el cuerpo del request.
    """
    data = request.get_json(silent=True) or {}
    object_id = data.get("objectId", "")

    # El object_id tiene formato: <issuer_id>.tv_<uuid_publico>
    if ".tv_" not in object_id:
        return _err("invalid_object", "ID de objeto inválido", 400)

    uuid_str = object_id.split(".tv_")[-1]
    tv = TarjetaVirtual.query.filter_by(uuid_publico=uuid_str, estado="activa").first()
    if not tv:
        return jsonify({"error": "Pass not found or inactive"}), 404

    if tv.cuenta.bloqueada:
        # Pase bloqueado por mora — Google lo marcará como expirado
        return jsonify({"result": "PASS_SHOULD_BE_UPDATED", "expiredTimeMillis": 0}), 200

    # Responder con el nuevo QR (Google lo actualiza silenciosamente en la Wallet)
    return jsonify({
        "result": "PASS_SHOULD_BE_UPDATED",
        "updatedObject": {
            "barcode": {
                "type": "QR_CODE",
                "value": tv.codigo_hoy,
            }
        }
    })
