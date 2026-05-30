"""
Módulo 3 — Endpoints de Visitas, QR y Acceso de Guardia.

Residente:
    POST /api/v1/visitas                    -> genera visita + QR
    GET  /api/v1/visitas/mias               -> historial de visitas del residente
    GET  /api/v1/mi-cuenta                  -> estado de cuenta del residente

Guardia:
    POST /api/v1/qr/validar                 -> valida un token QR
    POST /api/v1/accesos/visita             -> registra entrada/salida de visita
    GET  /api/v1/accesos/recientes          -> últimos eventos de acceso
"""
import datetime as dt
import os
import uuid as uuid_lib
import base64
import io

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw, ImageFont

from flask import Blueprint, request, jsonify, send_file

from app.extensions import db
from app.models.visita import Visita, CodigoQR, EventoAcceso
from app.models.cuenta import Cuenta, Residente
from app.auth.security import token_required, roles_required

visitas_bp = Blueprint("visitas", __name__)


def _mi_residente(usuario):
    """Encuentra el registro de Residente activo vinculado a este usuario."""
    return Residente.query.filter_by(usuario_id=usuario.id, activo=True).first()


def _guardar_foto_base64(b64_data, prefijo):
    """Guarda una foto base64 en /app/uploads y devuelve la ruta."""
    if not b64_data:
        return None
    try:
        os.makedirs("/app/uploads", exist_ok=True)
        nombre = f"{prefijo}_{uuid_lib.uuid4().hex[:12]}.jpg"
        ruta = f"/app/uploads/{nombre}"
        img_bytes = base64.b64decode(b64_data.split(",")[-1])
        with open(ruta, "wb") as f:
            f.write(img_bytes)
        return nombre
    except Exception:
        return None


# =====================================================================
# RESIDENTE: crear visita con QR
# =====================================================================
@visitas_bp.post("")
@token_required
def crear_visita(usuario_actual):
    """Genera una visita y su código QR.
    Body:
      { tipo: "unica"|"recurrente"|"repartidor",
        nombre_visitante, documento_id?, telefono?,
        empresa? (solo repartidor),
        placa_vehiculo?, en_vehiculo: bool,
        valido_hasta? (ISO, solo recurrente),
        modo_recurrencia?: "libre"|"una_por_dia" (solo recurrente)
      }
    """
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"error": {"code": "no_residente",
                                  "message": "No tienes una cuenta de residente activa"}}), 403

    cuenta = residente.cuenta
    if cuenta.bloqueada:
        return jsonify({"error": {"code": "cuenta_bloqueada",
                                  "message": "Tu cuenta está bloqueada por mora. No puedes generar QR."}}), 403

    data = request.get_json(silent=True) or {}
    tipo = data.get("tipo")
    if tipo not in ("unica", "recurrente", "repartidor"):
        return jsonify({"error": {"code": "tipo_invalido",
                                  "message": "El tipo debe ser unica, recurrente o repartidor"}}), 400

    nombre = (data.get("nombre_visitante") or "").strip()
    if not nombre:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "El nombre del visitante es obligatorio"}}), 400

    ahora = dt.datetime.utcnow()

    # Calcular vigencia según tipo
    if tipo == "unica":
        valido_hasta = ahora + dt.timedelta(hours=24)
    elif tipo == "recurrente":
        hasta_str = data.get("valido_hasta")
        if not hasta_str:
            return jsonify({"error": {"code": "datos_incompletos",
                                      "message": "Para visita recurrente, indica valido_hasta"}}), 400
        try:
            valido_hasta = dt.datetime.fromisoformat(hasta_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return jsonify({"error": {"code": "fecha_invalida",
                                      "message": "Formato de fecha inválido"}}), 400
    else:  # repartidor
        valido_hasta = ahora + dt.timedelta(hours=6)

    visita = Visita(
        cuenta_id=cuenta.id,
        generada_por=residente.id,
        tipo=tipo,
        nombre_visitante=nombre,
        documento_id=data.get("documento_id"),
        telefono=data.get("telefono"),
        empresa=data.get("empresa") if tipo == "repartidor" else None,
        placa_vehiculo=data.get("placa_vehiculo"),
        en_vehiculo=bool(data.get("en_vehiculo")),
        valido_desde=ahora,
        valido_hasta=valido_hasta,
        modo_recurrencia=data.get("modo_recurrencia") if tipo == "recurrente" else None,
    )
    db.session.add(visita)
    db.session.flush()

    qr = CodigoQR(visita_id=visita.id)
    db.session.add(qr)
    db.session.commit()

    return jsonify({"data": visita.to_dict()}), 201


# =====================================================================
# RESIDENTE: mis visitas
# =====================================================================
@visitas_bp.get("/mias")
@token_required
def mis_visitas(usuario_actual):
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"data": []})

    visitas = (Visita.query
               .filter_by(cuenta_id=residente.cuenta_id)
               .order_by(Visita.created_at.desc())
               .limit(50).all())
    return jsonify({"data": [v.to_dict() for v in visitas]})


# =====================================================================
# RESIDENTE: mi cuenta (estado de cuenta simplificado)
# =====================================================================
@visitas_bp.get("/mi-cuenta")
@token_required
def mi_cuenta(usuario_actual):
    residente = _mi_residente(usuario_actual)
    if not residente:
        return jsonify({"error": {"code": "no_residente",
                                  "message": "No tienes una cuenta de residente activa"}}), 403

    cuenta = residente.cuenta
    return jsonify({"data": {
        "cuenta": cuenta.to_dict(),
        "residente": residente.to_dict(),
    }})


# =====================================================================
# GUARDIA: validar QR
# =====================================================================
@visitas_bp.post("/qr/validar")
@roles_required("guardia", "admin", "super_admin")
def validar_qr(usuario_actual):
    """Recibe { token } y devuelve los datos de la visita si es válido."""
    data = request.get_json(silent=True) or {}
    token_str = (data.get("token") or "").strip()

    if not token_str:
        return jsonify({"error": {"code": "token_vacio",
                                  "message": "Escanea un código QR"}}), 400

    qr = CodigoQR.query.filter_by(token=token_str).first()
    if not qr:
        return jsonify({"error": {"code": "qr_invalido",
                                  "message": "Código QR no encontrado"}}), 404

    if qr.revocado:
        return jsonify({"error": {"code": "qr_revocado",
                                  "message": "Este código fue revocado"}}), 400

    visita = qr.visita
    ahora = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

    if visita.estado == "expirada":
        return jsonify({"error": {"code": "qr_expirado", "message": "Este código expiró"}}), 400

    if visita.valido_hasta:
        hasta = visita.valido_hasta
        if hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=dt.timezone.utc)
        if ahora > hasta:
            visita.estado = "expirada"
            db.session.commit()
            return jsonify({"error": {"code": "qr_expirado",
                                      "message": "Este código expiró"}}), 400

    if visita.tipo == "unica" and visita.estado == "usada":
        return jsonify({"error": {"code": "qr_usado",
                                  "message": "Este código de visita única ya fue utilizado"}}), 400

    # Check cuenta bloqueada
    cuenta = Cuenta.query.get(visita.cuenta_id)
    if cuenta and cuenta.bloqueada:
        return jsonify({"error": {"code": "cuenta_bloqueada",
                                  "message": "La cuenta del residente está bloqueada por mora"}}), 400

    return jsonify({"data": {
        "visita": visita.to_dict(),
        "valido": True,
        "mensaje": "QR válido. Puede proceder con la validación.",
    }})


# =====================================================================
# GUARDIA: registrar acceso de visita
# =====================================================================
@visitas_bp.post("/accesos/visita")
@roles_required("guardia", "admin", "super_admin")
def registrar_acceso_visita(usuario_actual):
    """Registra la entrada o salida de una visita.
    Body:
      { visita_id (uuid), direccion: "entrada"|"salida", acceso_id: int,
        foto_identidad?: base64, foto_placa?: base64 }
    """
    data = request.get_json(silent=True) or {}
    visita = Visita.query.filter_by(uuid_publico=data.get("visita_id")).first()
    if not visita:
        return jsonify({"error": {"code": "visita_invalida",
                                  "message": "Visita no encontrada"}}), 404

    direccion = data.get("direccion", "entrada")
    if direccion not in ("entrada", "salida"):
        direccion = "entrada"

    # Guardar fotos
    foto_id = _guardar_foto_base64(data.get("foto_identidad"), "id")
    foto_pl = _guardar_foto_base64(data.get("foto_placa"), "placa")

    evento = EventoAcceso(
        origen="visita",
        direccion=direccion,
        acceso_id=data.get("acceso_id", 1),
        visita_id=visita.id,
        guardia_id=usuario_actual.id,
        foto_identidad=foto_id,
        foto_placa=foto_pl,
        en_vehiculo=visita.en_vehiculo,
        placa_vehiculo=visita.placa_vehiculo,
    )
    db.session.add(evento)

    # Actualizar estado de la visita y QR
    if visita.tipo == "unica" and direccion == "entrada":
        visita.estado = "usada"
    if visita.qr:
        visita.qr.usos += 1

    db.session.commit()

    # TODO: Emitir notificación al residente via SocketIO + Resend
    # socketio.emit("visita_evento", {...}, room=f"cuenta_{visita.cuenta_id}")

    return jsonify({"data": {
        "evento": evento.to_dict(),
        "mensaje": f"Acceso registrado: {direccion}",
    }}), 201


# =====================================================================
# GUARDIA/ADMIN: eventos recientes
# =====================================================================
@visitas_bp.get("/accesos/recientes")
@roles_required("guardia", "admin", "super_admin")
def accesos_recientes(usuario_actual):
    eventos = (EventoAcceso.query
               .order_by(EventoAcceso.ocurrido_en.desc())
               .limit(30).all())
    return jsonify({"data": [e.to_dict() for e in eventos]})


# =====================================================================
# QR como IMAGEN (tarjeta con diseño Villas del Sol)
# =====================================================================
# Colores del logo
COLOR_NARANJA = (244, 135, 35)
COLOR_AZUL = (2, 46, 69)
COLOR_BLANCO = (255, 255, 255)


def _generar_tarjeta_qr(visita):
    """Genera una imagen PNG tipo tarjeta con el QR y datos de la visita."""
    # 1. Generar el QR con módulos redondeados, color azul marino
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=10, border=2)
    qr.add_data(str(visita.qr.token))
    qr.make(fit=True)
    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=SolidFillColorMask(front_color=COLOR_AZUL, back_color=COLOR_BLANCO),
    ).convert("RGB")

    # 2. Lienzo de la tarjeta (blanco con franja naranja arriba)
    W, H = 600, 800
    card = Image.new("RGB", (W, H), COLOR_BLANCO)
    draw = ImageDraw.Draw(card)

    # Franja superior naranja con degradado sutil
    for y in range(140):
        # de naranja fuerte a naranja claro
        t = y / 140
        r = int(244 + (255 - 244) * t)
        g = int(135 + (200 - 135) * t)
        b = int(35 + (120 - 35) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Esquinas redondeadas naranjas decorativas abajo
    draw.rectangle([0, H - 12, W, H], fill=COLOR_NARANJA)

    # 3. Fuentes
    def fuente(size, bold=False):
        rutas = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for r in rutas:
            if os.path.exists(r):
                return ImageFont.truetype(r, size)
        return ImageFont.load_default()

    # 4. Título en la franja
    titulo = "RESIDENCIAL"
    sub = "VILLAS DEL SOL"
    f_tit = fuente(30, bold=True)
    f_sub = fuente(38, bold=True)
    draw.text((W // 2, 45), titulo, font=f_tit, fill=COLOR_BLANCO, anchor="mm")
    draw.text((W // 2, 92), sub, font=f_sub, fill=COLOR_BLANCO, anchor="mm")

    # 5. Pegar el QR centrado
    qr_size = 360
    qr_img = qr_img.resize((qr_size, qr_size))
    qr_x = (W - qr_size) // 2
    qr_y = 185
    # Marco naranja alrededor del QR
    draw.rounded_rectangle([qr_x - 14, qr_y - 14, qr_x + qr_size + 14, qr_y + qr_size + 14],
                           radius=20, outline=COLOR_NARANJA, width=4)
    card.paste(qr_img, (qr_x, qr_y))

    # 6. Datos de la visita
    y = qr_y + qr_size + 45
    tipos = {"unica": "Visita única", "recurrente": "Visita recurrente", "repartidor": "Repartidor"}
    f_nombre = fuente(34, bold=True)
    f_dato = fuente(22)

    draw.text((W // 2, y), visita.nombre_visitante, font=f_nombre, fill=COLOR_AZUL, anchor="mm")
    y += 45
    draw.text((W // 2, y), tipos.get(visita.tipo, visita.tipo), font=f_dato, fill=COLOR_NARANJA, anchor="mm")
    y += 38
    if visita.valido_hasta:
        vence = visita.valido_hasta.strftime("%d/%m/%Y %H:%M")
        draw.text((W // 2, y), f"Válido hasta: {vence}", font=fuente(18), fill=(110, 110, 110), anchor="mm")
    y += 30
    if visita.placa_vehiculo:
        draw.text((W // 2, y), f"Placa: {visita.placa_vehiculo}", font=fuente(18), fill=(110, 110, 110), anchor="mm")

    return card


@visitas_bp.get("/<visita_uuid>/qr-imagen")
@token_required
def qr_imagen(usuario_actual, visita_uuid):
    """Devuelve la imagen PNG de la tarjeta QR de una visita."""
    visita = Visita.query.filter_by(uuid_publico=visita_uuid).first()
    if not visita or not visita.qr:
        return jsonify({"error": {"code": "no_encontrada", "message": "Visita no encontrada"}}), 404

    card = _generar_tarjeta_qr(visita)
    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png",
                     download_name=f"qr_{visita.nombre_visitante.replace(' ', '_')}.png")
