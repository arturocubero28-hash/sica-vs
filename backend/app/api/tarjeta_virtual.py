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
    # Si no está en variable de entorno, intentar desde archivo montado
    service_key = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not service_key:
        import os
        key_file = "/app/google-wallet-key.json"
        if os.path.exists(key_file):
            with open(key_file) as f:
                service_key = f.read()
    if not service_key:
        return jsonify({"data": {
            "modo": "desarrollo",
            "nota": "Configurá GOOGLE_SERVICE_ACCOUNT_KEY para habilitar Google Wallet",
        }})

    # Firmar con la clave de servicio (JWT RS256)
    try:
        import google.auth.crypt
        import google.auth.jwt
        import google.oauth2.service_account
        import google.auth.transport.requests
        import requests as req

        key_data = json.loads(service_key)
        issuer_id = current_app.config.get("GOOGLE_ISSUER_ID", "")
        # Google no acepta guiones en el object id — se quitan del uuid
        uuid_limpio = str(tv.uuid_publico).replace("-", "")
        object_id = f"{issuer_id}.tv{uuid_limpio}"
        class_id  = f"{issuer_id}.acceso_residencial"
        titular   = residente.usuario
        nombre    = f"{titular.nombre} {titular.apellido}" if titular else "Residente"

        # Credenciales para la API REST
        creds = google.oauth2.service_account.Credentials.from_service_account_info(
            key_data,
            scopes=["https://www.googleapis.com/auth/wallet_object.issuer"])
        session = google.auth.transport.requests.AuthorizedSession(creds)

        # Definición del objeto genérico
        logo_url = current_app.config.get("LOGO_URL", "")
        generic_object = {
            "id": object_id,
            "classId": class_id,
            "genericType": "GENERIC_TYPE_UNSPECIFIED",
            "hexBackgroundColor": "#022E45",
            "cardTitle": {"defaultValue": {"language": "es", "value": "Residencial Villas del Sol"}},
            "subheader": {"defaultValue": {"language": "es", "value": "Tarjeta de Acceso"}},
            "header": {"defaultValue": {"language": "es", "value": nombre}},
            "barcode": {"type": "QR_CODE", "value": tv.codigo_hoy},
            "textModulesData": [
                {"header": "Tipo de acceso", "body": tv.tipo_acceso.capitalize(), "id": "tipo"},
            ],
            "state": "ACTIVE",
        }
        if logo_url:
            generic_object["logo"] = {
                "sourceUri": {"uri": logo_url},
                "contentDescription": {"defaultValue": {"language": "es", "value": "SICA-VS"}},
            }

        # Verificar que la clase exista; si no, crearla vía API
        # (la clase creada desde la consola web a veces no es visible para
        # la API REST hasta que el Perfil de Empresa está aprobado)
        class_url = f"https://walletobjects.googleapis.com/walletobjects/v1/genericClass/{class_id}"
        rc = session.get(class_url)
        current_app.logger.info(f"Google Wallet GET class: {rc.status_code}")
        if rc.status_code == 404:
            clase = {
                "id": class_id,
                "classTemplateInfo": {
                    "cardTemplateOverride": {
                        "cardRowTemplateInfos": [{
                            "twoItems": {
                                "startItem": {"firstValue": {"fields": [
                                    {"fieldPath": "object.textModulesData['tipo']"}
                                ]}},
                            }
                        }]
                    }
                },
            }
            rc2 = session.post(
                "https://walletobjects.googleapis.com/walletobjects/v1/genericClass",
                json=clase)
            current_app.logger.info(f"Google Wallet CREATE class: {rc2.status_code} — {rc2.text[:300]}")

        # Intentar crear el objeto; si ya existe (409) actualizarlo con PATCH
        api_base = "https://walletobjects.googleapis.com/walletobjects/v1/genericObject"
        r = session.post(api_base, json=generic_object)
        current_app.logger.info(f"Google Wallet POST object: {r.status_code} — {r.text[:500]}")
        if r.status_code == 409:
            # Ya existe — actualizar el QR del día y refrescar el logo por si cambió
            patch_body = {"barcode": {"type": "QR_CODE", "value": tv.codigo_hoy}}
            if logo_url:
                patch_body["logo"] = generic_object.get("logo")
            r2 = session.patch(f"{api_base}/{object_id}", json=patch_body)
            current_app.logger.info(f"Google Wallet PATCH object: {r2.status_code} — {r2.text[:500]}")
        elif r.status_code not in (200, 201):
            current_app.logger.error(f"Google Wallet object creation failed: {r.status_code} {r.text}")
            return _err("wallet_error", f"Google rechazó el objeto: {r.text[:200]}", 500)

        # Generar el JWT para el botón "Agregar a Wallet"
        signer = google.auth.crypt.RSASigner.from_service_account_info(key_data)
        token = google.auth.jwt.encode(signer, {
            "iss": key_data["client_email"],
            "aud": "google",
            "typ": "savetowallet",
            "iat": int(dt.datetime.utcnow().timestamp()),
            "payload": {"genericObjects": [{"id": object_id}]},
        }).decode("utf-8")

        wallet_url = f"https://pay.google.com/gp/v/save/{token}"
        return jsonify({"data": {"wallet_url": wallet_url}})

    except Exception as e:
        current_app.logger.error(f"Google Wallet error: {e}")
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

    # El object_id tiene formato: <issuer_id>.tv<uuid_sin_guiones>
    if ".tv" not in object_id:
        return _err("invalid_object", "ID de objeto inválido", 400)

    uuid_hex = object_id.split(".tv")[-1]
    # Reconstruir el UUID con guiones (8-4-4-4-12)
    if len(uuid_hex) == 32:
        uuid_str = f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-{uuid_hex[16:20]}-{uuid_hex[20:32]}"
    else:
        uuid_str = uuid_hex
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
