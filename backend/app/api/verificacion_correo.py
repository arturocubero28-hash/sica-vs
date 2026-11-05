"""
Verificación de correo antes de crear cuentas (Día 73).

    POST /api/v1/correo/verificaciones        { email, nombre? }
    GET  /api/v1/correo/verificaciones/<id>

El panel llama al POST cuando el administrador termina de llenar el
formulario. Eso MANDA EL CORREO DE ACTIVACIÓN de verdad (con el enlace
para la contraseña) y devuelve el id de la verificación. El panel
consulta el GET cada pocos segundos, y recién cuando el estado es
"entregado" manda el pedido de crear la cuenta con ese id. Si rebota, no
se creó nada.

Ver models/verificacion_correo.py para el porqué de cada decisión.
"""
import re
import uuid as _uuid
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.auth.security import roles_required
from app.models.usuario import Usuario
from app.models.verificacion_correo import VerificacionCorreo, VIGENCIA
from app.utils.residencial import residencial_id_heredado

verificacion_bp = Blueprint("verificacion_correo", __name__)

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Estados en los que una verificación anterior todavía sirve para este
# correo y NO hace falta mandar otro. "error" queda afuera: ahí el envío
# falló y tiene sentido reintentar.
_REUSABLES = ("enviando", "enviado", "entregado", "demorado", "rebotado", "queja")


def _err(code, msg, status, **extra):
    cuerpo = {"code": code, "message": msg}
    cuerpo.update(extra)
    return jsonify({"error": cuerpo}), status


def _buscar(verif_id):
    try:
        clave = _uuid.UUID(str(verif_id))
    except (ValueError, TypeError):
        return None
    return VerificacionCorreo.query.filter_by(uuid_publico=clave).first()


def _donde_esta(usuario):
    """'Casa 24' / 'Edificio B · apto 3' — para decir a quién pertenece un correo."""
    try:
        from app.models.cuenta import Residente
        r = (Residente.query.filter_by(usuario_id=usuario.id, activo=True).first()
             or Residente.query.filter_by(usuario_id=usuario.id).first())
        if r and r.cuenta and r.cuenta.unidad:
            u = r.cuenta.unidad
            ident = (u.identificador or "").strip()
            # En Villas del Sol las casas se identifican solo con el número
            # ("60"), y "(60)" en un mensaje no se entiende. Se antepone el
            # tipo cuando el identificador no lo trae ya.
            if ident and not ident.lower().startswith(("casa", "edificio")):
                ident = f"{'Edificio' if u.tipo == 'edificio' else 'Casa'} {ident}"
            return f"{ident} · apto {r.cuenta.apartamento}" if r.cuenta.apartamento else ident
    except Exception:
        pass
    return None


def correo_ocupado(email):
    """
    Si el correo ya lo usa alguien, devuelve la respuesta de error lista;
    si no, None. Se usa en la verificación (para enterarse ANTES de mandar
    nada) y otra vez al crear (por si alguien lo ocupó en el medio).
    """
    otro = Usuario.query.filter_by(email=(email or "").strip().lower()).first()
    if not otro:
        return None
    donde = _donde_esta(otro)
    quien = f"{otro.nombre} {otro.apellido or ''}".strip()
    detalle = f" ({donde})" if donde else ""
    return _err(
        "email_duplicado",
        f"Ese correo ya está registrado para {quien}{detalle}. "
        f"Cada persona necesita su propio correo.",
        409, quien=quien, donde=donde)


def exigir_verificacion(email, verif_id):
    """
    Lo usan los endpoints que crean cuentas. Devuelve:

      (None, None)         regla apagada (desarrollo/pruebas): seguir como siempre
      (v, None)            se puede crear. OJO: si v.ya_creo_algo(), es un
                           pedido REPETIDO y el endpoint tiene que devolver
                           lo que ya creó, no crear de nuevo.
      (None, respuesta)    no se puede: devolver esa respuesta.
    """
    if not current_app.config.get("EXIGIR_VERIFICACION_CORREO"):
        return None, None

    if not verif_id:
        return None, _err("correo_no_verificado",
                          "Antes de crear la cuenta hay que confirmar que el correo llega.", 400)
    v = _buscar(verif_id)
    if not v:
        return None, _err("correo_no_verificado", "La verificación del correo no existe.", 400)
    if (v.email or "").lower() != (email or "").strip().lower():
        return None, _err("correo_no_verificado",
                          "El correo cambió después de verificarlo. Verificá el correo nuevo.", 400)

    # Pedido repetido: se deja pasar para que el endpoint devuelva lo creado.
    if v.ya_creo_algo():
        return v, None
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


def marcar_usada(v, usuario, cuenta_id=None):
    """
    Llamar dentro de la MISMA transacción que crea la cuenta.

    Además deja anotado en el usuario el envío que ya le llegó: el correo
    de activación salió con la verificación, así que no se manda otro, y
    el panel muestra "Correo entregado" junto a la persona desde el primer
    momento. Con el id de Resend copiado, los avisos que lleguen después
    (una queja por spam, por ejemplo) también encuentran a la persona.
    """
    if v is None:
        return
    v.usada = True
    v.usuario_id = usuario.id
    v.cuenta_id = cuenta_id
    usuario.correo_estado = v.estado
    usuario.correo_detalle = None
    usuario.correo_resend_id = v.resend_id
    usuario.correo_actualizado = dt.datetime.now(dt.timezone.utc)


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
    # después de mandarle un enlace de activación a una cuenta ajena.
    ocupado = correo_ocupado(email)
    if ocupado:
        return ocupado

    rid = residencial_id_heredado(usuario_actual)

    # IDEMPOTENCIA — si ya hay una verificación reciente para este correo
    # que no se usó, se devuelve esa en vez de mandar otro correo. Cubre el
    # doble clic, volver atrás y adelante en el formulario, o reintentar
    # después de que se cortó la espera: la persona no recibe dos enlaces.
    # Si la anterior rebotó también se devuelve: volver a mandarle a una
    # dirección que no existe va a rebotar igual.
    desde = dt.datetime.now(dt.timezone.utc) - VIGENCIA
    previa = (VerificacionCorreo.query
              .filter(VerificacionCorreo.email == email,
                      VerificacionCorreo.usada.is_(False),
                      VerificacionCorreo.estado.in_(_REUSABLES),
                      VerificacionCorreo.created_at >= desde)
              .order_by(VerificacionCorreo.created_at.desc())
              .first())
    if previa is not None and (rid is None or previa.residencial_id in (None, rid)):
        return jsonify({"data": previa.to_dict()}), 200

    from app.models.residencial import Residencial
    residencial = Residencial.query.get(rid) if rid else None
    nombre_residencial = residencial.nombre if residencial else "Residencial"

    v = VerificacionCorreo(email=email, residencial_id=rid,
                           creado_por_id=usuario_actual.id, estado="enviando")
    db.session.add(v)
    db.session.flush()

    from app.services.correo import enviar_activacion_antes_de_crear, _resend_configurado
    if not _resend_configurado():
        if current_app.config.get("ENV") == "production":
            db.session.rollback()
            return _err("correo_no_configurado",
                        "El envío de correos no está configurado en el servidor.", 503)
        # Desarrollo sin Resend: se simula la entrega para poder usar el
        # panel. NUNCA en producción (ver el if de arriba).
        v.estado = "entregado"
        v.detalle = "Simulado: no hay RESEND_API_KEY en este entorno."
        v.resend_id = f"simulado-{v.uuid_publico}"
    else:
        # El mismo token que se generaría al crear la cuenta: un JWT con el
        # correo adentro. Sirve desde el momento en que la cuenta exista.
        token = jwt.encode(
            {"sub": email, "proposito": "activacion",
             "exp": dt.datetime.utcnow() + dt.timedelta(hours=48)},
            current_app.config["JWT_SECRET"], algorithm="HS256")
        ok, resend_id = enviar_activacion_antes_de_crear(email, nombre, token, nombre_residencial)
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
