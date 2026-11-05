"""
Webhooks entrantes (Día 72).

Hoy solo Resend, para enterarnos de que un correo NO llegó.

El problema que resuelve: administración daba de alta a un residente con
el correo mal escrito y nadie se enteraba. Resend acepta el envío (la
dirección tiene forma válida), el correo sale, el servidor del
destinatario lo rechaza porque el buzón no existe... y del lado nuestro
la cuenta simplemente se quedaba "pendiente" para siempre, sin ninguna
pista de por qué.

Resend avisa de eso por webhook. Acá se recibe ese aviso, se busca a quién
corresponde y se le marca el estado del correo, que el panel muestra junto
al residente.

CONFIGURACIÓN (una sola vez, en el panel de Resend):
  Webhooks → Add Webhook
    URL:     https://patronatovillasdelsol.com/api/v1/webhooks/resend
    Eventos: email.sent, email.delivered, email.bounced,
             email.complained, email.delivery_delayed
  Copiar el "Signing Secret" (empieza con whsec_) y ponerlo en el
  servidor como RESEND_WEBHOOK_SECRET.

SEGURIDAD: este endpoint es público (Resend no puede autenticarse con
nuestro JWT), así que la firma es lo único que separa un aviso legítimo de
cualquiera que descubra la URL y quiera marcar correos como rebotados.
Sin RESEND_WEBHOOK_SECRET configurado NO se procesa nada: es preferible
perder los avisos a aceptar cualquiera.
"""
import base64
import datetime as dt
import hashlib
import hmac
import logging

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint("webhooks", __name__)

# Tolerancia del reloj: un aviso firmado hace mucho rato se rechaza, para
# que nadie pueda reenviar una copia capturada de un aviso legítimo.
TOLERANCIA_SEGUNDOS = 300

# Qué estado deja cada evento de Resend.
#
# Día 73 — se agrega email.failed. Es distinto de bounced: bounced es "el
# servidor del destinatario lo rechazó" (buzón que no existe), failed es
# "Resend no pudo ni mandarlo". Para administración significan lo mismo —
# ese correo no llegó y hay que revisar la dirección — así que se trata
# igual, pero el detalle guarda cuál de los dos fue.
ESTADOS = {
    "email.sent": "enviado",
    "email.delivered": "entregado",
    "email.bounced": "rebotado",
    "email.failed": "rebotado",
    "email.complained": "queja",
    "email.delivery_delayed": "demorado",
}


def _firma_valida(cuerpo_crudo: bytes) -> bool:
    """
    Verifica la firma de Svix, que es la que usa Resend.

    El contenido firmado es "<id>.<timestamp>.<cuerpo>", con HMAC-SHA256 y
    la clave secreta en base64 después del prefijo whsec_. La cabecera
    svix-signature puede traer varias firmas separadas por espacio, cada
    una con su versión adelante ("v1,<firma>"): alcanza con que una
    coincida, porque así es como rotan la clave sin cortar el servicio.
    """
    secreto = current_app.config.get("RESEND_WEBHOOK_SECRET") or ""
    if not secreto:
        return False

    svix_id = request.headers.get("svix-id") or request.headers.get("webhook-id")
    svix_ts = request.headers.get("svix-timestamp") or request.headers.get("webhook-timestamp")
    svix_firma = request.headers.get("svix-signature") or request.headers.get("webhook-signature")
    if not (svix_id and svix_ts and svix_firma):
        return False

    try:
        edad = abs(dt.datetime.now(dt.timezone.utc).timestamp() - int(svix_ts))
    except (TypeError, ValueError):
        return False
    if edad > TOLERANCIA_SEGUNDOS:
        return False

    try:
        clave = base64.b64decode(secreto.split("_", 1)[1] if secreto.startswith("whsec_") else secreto)
    except Exception:
        return False

    firmado = svix_id.encode() + b"." + svix_ts.encode() + b"." + cuerpo_crudo
    esperada = base64.b64encode(hmac.new(clave, firmado, hashlib.sha256).digest()).decode()

    for parte in svix_firma.split(" "):
        _, _, valor = parte.partition(",")
        # compare_digest y no "==": comparar de largo variable filtra
        # información por el tiempo que tarda en fallar.
        if valor and hmac.compare_digest(valor, esperada):
            return True
    return False


def _usuario_del_evento(datos):
    """
    A quién corresponde este aviso.

    Primero por el id del envío, que es exacto. Si no aparece (un envío
    anterior a este cambio), se cae a la dirección de destino — menos
    preciso, porque si al residente ya le corrigieron el correo, el aviso
    del correo viejo no debe pisar el estado del nuevo.
    """
    email_id = datos.get("email_id")
    if email_id:
        u = Usuario.query.filter_by(correo_resend_id=email_id).first()
        if u:
            return u
    destinos = datos.get("to") or []
    if isinstance(destinos, str):
        destinos = [destinos]
    for destino in destinos:
        u = Usuario.query.filter_by(email=(destino or "").strip().lower()).first()
        if u and not u.correo_resend_id:
            return u
    return None


@webhooks_bp.post("/resend")
@limiter.limit("240 per minute")
def resend():
    cuerpo_crudo = request.get_data()
    if not _firma_valida(cuerpo_crudo):
        if not current_app.config.get("RESEND_WEBHOOK_SECRET"):
            logger.warning("Webhook de Resend recibido pero RESEND_WEBHOOK_SECRET no está configurado")
        return jsonify({"error": {"code": "firma_invalida",
                                  "message": "Firma inválida"}}), 401

    evento = request.get_json(silent=True) or {}
    tipo = evento.get("type") or ""
    datos = evento.get("data") or {}

    estado = ESTADOS.get(tipo)
    if not estado:
        # Un evento que no nos interesa igual se responde 200: si
        # devolviéramos error, Resend lo reintentaría para siempre.
        return jsonify({"data": {"ignorado": tipo}}), 200

    # Día 73 — ¿es el correo de verificación de alguien que todavía no
    # existe? Se mira primero porque es lo más urgente: hay un
    # administrador esperando en pantalla esta respuesta para poder crear
    # la cuenta. Su id de envío nunca coincide con el de un usuario (al
    # usuario no se le registra), así que los dos caminos no se pisan.
    from app.models.verificacion_correo import VerificacionCorreo
    email_id = datos.get("email_id")
    verif = (VerificacionCorreo.query.filter_by(resend_id=email_id).first()
             if email_id else None)
    if verif is not None:
        # Mismo criterio que con los usuarios: un rebote no se pisa con un
        # aviso más viejo que llegue tarde.
        if not (verif.estado == "rebotado" and estado in ("enviado", "entregado", "demorado")):
            verif.estado = estado
            verif.actualizado = dt.datetime.now(dt.timezone.utc)
            if tipo in ("email.bounced", "email.failed"):
                rebote = datos.get("bounce") or datos.get("failed") or {}
                verif.detalle = (rebote.get("message") or rebote.get("reason")
                                 or rebote.get("subType")
                                 or "El servidor del destinatario rechazó el correo.")[:1000]
            elif tipo == "email.complained":
                verif.detalle = "El destinatario marcó el correo como spam."
            db.session.commit()
        # Si la cuenta todavía no se creó, no hay usuario que actualizar.
        # Si ya se creó, la persona lleva copiado este mismo id de envío
        # (ver marcar_usada) y se sigue abajo para actualizarla también.
        if not verif.usuario_id:
            return jsonify({"data": {"ok": True, "verificacion": verif.estado}}), 200

    usuario = _usuario_del_evento(datos)
    if not usuario:
        return jsonify({"data": {"sin_destinatario": True}}), 200

    # Un "entregado" que llega después de un "rebotado" sería raro, pero el
    # orden de los webhooks no está garantizado: un rebote no se pisa con
    # un estado más viejo. Lo que sí puede avanzar es enviado → entregado.
    if usuario.correo_estado == "rebotado" and estado in ("enviado", "entregado", "demorado"):
        return jsonify({"data": {"ignorado_por_rebote_previo": True}}), 200

    usuario.correo_estado = estado
    usuario.correo_actualizado = dt.datetime.now(dt.timezone.utc)
    if tipo in ("email.bounced", "email.failed"):
        rebote = datos.get("bounce") or datos.get("failed") or {}
        por_defecto = ("El servidor del destinatario rechazó el correo."
                       if tipo == "email.bounced"
                       else "El correo no se pudo enviar.")
        usuario.correo_detalle = (rebote.get("message")
                                  or rebote.get("reason")
                                  or rebote.get("subType")
                                  or por_defecto)[:1000]
        logger.warning("Correo no entregado (%s) para %s: %s",
                       tipo, usuario.email, usuario.correo_detalle)
    elif tipo == "email.complained":
        usuario.correo_detalle = "El destinatario marcó el correo como spam."
    else:
        usuario.correo_detalle = None
    db.session.commit()

    return jsonify({"data": {"ok": True, "estado": estado}}), 200
