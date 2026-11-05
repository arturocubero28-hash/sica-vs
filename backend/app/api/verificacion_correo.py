"""
Verificación de correo antes de crear cuentas (Día 73).

    POST /api/v1/correo/verificaciones        { email, nombre? }
    GET  /api/v1/correo/verificaciones/<id>

El panel llama al POST cuando el administrador termina de llenar el
formulario, consulta el GET cada pocos segundos, y recién cuando el
estado es "entregado" manda el pedido de crear la cuenta con el id de
la verificación. Si rebota, no se creó nada: se corrige la dirección y
se verifica de nuevo.

Ver models/verificacion_correo.py para el porqué.
"""
import re
import uuid as _uuid
import datetime as dt

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.auth.security import roles_required
from app.models.usuario import Usuario
from app.models.verificacion_correo import VerificacionCorreo
from app.utils.residencial import residencial_id_heredado

verificacion_bp = Blueprint("verificacion_correo", __name__)

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


def _buscar(verif_id):
    try:
        clave = _uuid.UUID(str(verif_id))
    except (ValueError, TypeError):
        return None
    return VerificacionCorreo.query.filter_by(uuid_publico=clave).first()


def exigir_verificacion(email, verif_id):
    """
    Lo usan los endpoints que crean cuentas. Devuelve (verificacion, None)
    si se puede seguir, o (None, respuesta_de_error) si no.

    Con EXIGIR_VERIFICACION_CORREO apagado (desarrollo y pruebas) no exige
    nada y devuelve (None, None): el endpoint sigue como siempre.
    """
    if not current_app.config.get("EXIGIR_VERIFICACION_CORREO"):
        return None, None

    if not verif_id:
        return None, _err(
            "correo_no_verificado",
            "Antes de crear la cuenta hay que confirmar que el correo llega.", 400)
    v = _buscar(verif_id)
    if not v:
        return None, _err("correo_no_verificado", "La verificación del correo no existe.", 400)
    if (v.email or "").lower() != (email or "").strip().lower():
        # El correo cambió después de verificar: hay que verificar el nuevo.
        return None, _err(
            "correo_no_verificado",
            "El correo cambió después de verificarlo. Verificá el correo nuevo.", 400)
    if v.usada:
        return None, _err("correo_no_verificado",
                          "Esa verificación ya se usó para crear otra cuenta.", 400)
    if not v.vigente():
        return None, _err("correo_no_verificado",
                          "La verificación venció. Verificá el correo otra vez.", 400)
    if v.estado != "entregado":
        return None, _err(
            "correo_no_verificado",
            "Todavía no se confirmó que el correo haya llegado."
            if v.estado in ("enviando", "enviado", "demorado")
            else "El correo no llegó a esa dirección. Corregila antes de seguir.", 400)
    return v, None


def marcar_usada(v):
    """Llamar dentro de la misma transacción que crea la cuenta."""
    if v is not None:
        v.usada = True


@verificacion_bp.post("/verificaciones")
@roles_required("admin", "super_admin")
@limiter.limit("30 per minute")
def crear(usuario_actual):
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    nombre = (data.get("nombre") or "").strip()

    if not email or not _EMAIL.match(email):
        return _err("email_invalido", "El correo no tiene un formato válido.", 400)
    # Mejor enterarse AHORA de que el correo ya lo usa alguien, y no
    # después de esperar la entrega para que la creación falle igual.
    if Usuario.query.filter_by(email=email).first():
        return _err("email_duplicado", f"Ya existe un usuario con el correo {email}.", 409)

    from app.models.residencial import Residencial
    rid = residencial_id_heredado(usuario_actual)
    residencial = Residencial.query.get(rid) if rid else None
    nombre_residencial = residencial.nombre if residencial else "Residencial"

    v = VerificacionCorreo(email=email, residencial_id=rid,
                           creado_por_id=usuario_actual.id, estado="enviando")
    db.session.add(v)
    db.session.flush()

    from app.services.correo import enviar_verificacion, _resend_configurado
    if not _resend_configurado():
        if current_app.config.get("ENV") == "production":
            db.session.rollback()
            return _err("correo_no_configurado",
                        "El envío de correos no está configurado en el servidor.", 503)
        # Desarrollo sin Resend: se simula la entrega, para que el panel se
        # pueda usar igual. NUNCA en producción (ver el if de arriba).
        v.estado = "entregado"
        v.detalle = "Simulado: no hay RESEND_API_KEY en este entorno."
        v.resend_id = f"simulado-{v.uuid_publico}"
    else:
        ok, resend_id = enviar_verificacion(email, nombre, nombre_residencial)
        if not ok:
            v.estado = "error"
            v.detalle = "No se pudo enviar el correo. Probá de nuevo en un momento."
        else:
            v.estado = "enviado"
            v.resend_id = resend_id
    v.actualizado = dt.datetime.now(dt.timezone.utc)
    db.session.commit()
    return jsonify({"data": v.to_dict()}), 201


@verificacion_bp.get("/verificaciones/<verif_id>")
@roles_required("admin", "super_admin")
@limiter.limit("120 per minute")
def consultar(usuario_actual, verif_id):
    v = _buscar(verif_id)
    if not v:
        return _err("no_encontrada", "Verificación no encontrada", 404)
    rid = residencial_id_heredado(usuario_actual)
    if rid is not None and v.residencial_id is not None and v.residencial_id != rid:
        return _err("no_encontrada", "Verificación no encontrada", 404)
    return jsonify({"data": v.to_dict()})
