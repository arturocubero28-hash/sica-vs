"""
Módulo de Cámaras — /api/v1/camaras/

CRUD de cámaras ONVIF/RTSP + proxy de video RTSP -> MJPEG para el navegador.
El navegador no puede leer RTSP directamente, así que el backend transcodifica
con OpenCV y sirve un stream MJPEG que se muestra en un <img>.
"""
import time

from flask import Blueprint, request, jsonify, Response, current_app

from app.extensions import db
from app.models.camara import Camara
from app.auth.security import token_required, roles_required, requiere_funcion_plan

camaras_bp = Blueprint("camaras", __name__)


# ── CRUD ──────────────────────────────────────────────────────────────────────
@camaras_bp.get("")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("control_fisico")
def listar_camaras(usuario_actual):
    from app.utils.residencial import scope_directo
    camaras = scope_directo(Camara.query, Camara, usuario_actual) \
        .order_by(Camara.orden.asc(), Camara.id.asc()).all()
    return jsonify({"data": [c.to_dict() for c in camaras]})


@camaras_bp.post("")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("control_fisico")
def crear_camara(usuario_actual):
    body = request.get_json() or {}
    if not body.get("nombre") or not body.get("ip"):
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Nombre e IP son obligatorios"}}), 400

    from app.utils.residencial import residencial_id_heredado
    cam = Camara(
        nombre=body["nombre"],
        ip=body["ip"],
        puerto_rtsp=int(body.get("puerto_rtsp", 554)),
        puerto_onvif=int(body.get("puerto_onvif", 80)),
        usuario=body.get("usuario"),
        password=body.get("password"),
        ruta_stream=body.get("ruta_stream", "/Streaming/Channels/101"),
        acceso_id=body.get("acceso_id"),
        activa=body.get("activa", True),
        orden=int(body.get("orden", 0)),
        residencial_id=residencial_id_heredado(usuario_actual),
    )
    db.session.add(cam)
    db.session.commit()
    return jsonify({"data": cam.to_dict()}), 201


@camaras_bp.put("/<uuid_camara>")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("control_fisico")
def editar_camara(usuario_actual, uuid_camara):
    from app.utils.residencial import pertenece_a_mi_residencial
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    # Día 48 — hallazgo de auditoría: antes solo se buscaba por UUID, sin
    # verificar residencial. Un admin de otra residencial podía editar una
    # cámara ajena si conocía (o adivinaba) su UUID. 404 en vez de 403
    # para no dejarle saber a quien prueba UUIDs si existe o no.
    if not cam or not pertenece_a_mi_residencial(cam, usuario_actual):
        return jsonify({"error": {"code": "no_encontrada", "message": "Cámara no encontrada"}}), 404

    body = request.get_json() or {}
    for campo in ("nombre", "ip", "usuario", "ruta_stream"):
        if campo in body:
            setattr(cam, campo, body[campo])
    if "password" in body and body["password"]:
        cam.password = body["password"]
    for campo in ("puerto_rtsp", "puerto_onvif", "orden", "acceso_id"):
        if campo in body and body[campo] is not None:
            setattr(cam, campo, int(body[campo]))
    if "activa" in body:
        cam.activa = bool(body["activa"])

    db.session.commit()
    return jsonify({"data": cam.to_dict()})


@camaras_bp.delete("/<uuid_camara>")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("control_fisico")
def eliminar_camara(usuario_actual, uuid_camara):
    from app.utils.residencial import pertenece_a_mi_residencial
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam or not pertenece_a_mi_residencial(cam, usuario_actual):
        return jsonify({"error": {"code": "no_encontrada", "message": "Cámara no encontrada"}}), 404
    db.session.delete(cam)
    db.session.commit()
    return jsonify({"data": {"eliminada": True}})


# ── Probar conexión a una cámara ───────────────────────────────────────────────
@camaras_bp.post("/<uuid_camara>/probar")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("control_fisico")
def probar_camara(usuario_actual, uuid_camara):
    from app.utils.residencial import pertenece_a_mi_residencial
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam or not pertenece_a_mi_residencial(cam, usuario_actual):
        return jsonify({"error": {"code": "no_encontrada", "message": "Cámara no encontrada"}}), 404

    try:
        import cv2
        cap = cv2.VideoCapture(cam.url_rtsp(), cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000)
        ok = cap.isOpened()
        if ok:
            ret, _ = cap.read()
            ok = ret
        cap.release()
        return jsonify({"data": {"online": bool(ok)}})
    except Exception as e:
        # No exponer el detalle del error al cliente (podría revelar IPs,
        # rutas o versiones internas). Se registra en el log del servidor.
        current_app.logger.warning("Error al verificar cámara %s: %s", cam.id, e)
        return jsonify({"data": {"online": False, "error": "No se pudo conectar a la cámara"}})


# ── Proxy de video RTSP -> MJPEG ───────────────────────────────────────────────
def _generar_mjpeg(url_rtsp):
    """Generador que lee frames RTSP con OpenCV y los emite como MJPEG."""
    import cv2

    cap = cv2.VideoCapture(url_rtsp, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        cap.release()
        return

    try:
        fallos = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                fallos += 1
                if fallos > 30:
                    break
                time.sleep(0.05)
                continue
            fallos = 0

            # Redimensionar para reducir ancho de banda (max 960px de ancho)
            h, w = frame.shape[:2]
            if w > 960:
                escala = 960 / w
                frame = cv2.resize(frame, (960, int(h * escala)))

            ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                continue

            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            time.sleep(0.04)  # ~25 fps máx
    finally:
        cap.release()


@camaras_bp.get("/<uuid_camara>/stream")
@token_required
@requiere_funcion_plan("control_fisico")
def stream_camara(usuario_actual, uuid_camara):
    # Día 48 — hallazgo de auditoría, el más grave de los cuatro: este
    # endpoint usa @token_required (CUALQUIER rol autenticado — residente,
    # guardia, cajero, no solo admin), y antes no verificaba residencial
    # en absoluto. Cualquier usuario logueado de CUALQUIER residencial
    # podía ver el STREAM DE VIDEO EN VIVO de una cámara ajena con solo
    # conocer su UUID. pertenece_a_mi_residencial() funciona para
    # cualquier rol (no solo admin), a diferencia de otros helpers de
    # este archivo pensados solo para el panel admin.
    from app.utils.residencial import pertenece_a_mi_residencial
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam or not cam.activa or not pertenece_a_mi_residencial(cam, usuario_actual):
        return jsonify({"error": {"code": "no_disponible",
                                  "message": "Cámara no disponible"}}), 404

    return Response(
        _generar_mjpeg(cam.url_rtsp()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
