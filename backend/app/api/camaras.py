"""
Módulo de Cámaras — /api/v1/camaras/

CRUD de cámaras ONVIF/RTSP + proxy de video RTSP -> MJPEG para el navegador.
El navegador no puede leer RTSP directamente, así que el backend transcodifica
con OpenCV y sirve un stream MJPEG que se muestra en un <img>.
"""
import time

from flask import Blueprint, request, jsonify, Response

from app.extensions import db
from app.models.camara import Camara
from app.auth.security import token_required, roles_required

camaras_bp = Blueprint("camaras", __name__)


# ── CRUD ──────────────────────────────────────────────────────────────────────
@camaras_bp.get("")
@roles_required("admin", "super_admin")
def listar_camaras(usuario_actual):
    camaras = Camara.query.order_by(Camara.orden.asc(), Camara.id.asc()).all()
    return jsonify({"data": [c.to_dict() for c in camaras]})


@camaras_bp.post("")
@roles_required("admin", "super_admin")
def crear_camara(usuario_actual):
    body = request.get_json() or {}
    if not body.get("nombre") or not body.get("ip"):
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Nombre e IP son obligatorios"}}), 400

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
    )
    db.session.add(cam)
    db.session.commit()
    return jsonify({"data": cam.to_dict()}), 201


@camaras_bp.put("/<uuid_camara>")
@roles_required("admin", "super_admin")
def editar_camara(usuario_actual, uuid_camara):
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam:
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
def eliminar_camara(usuario_actual, uuid_camara):
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam:
        return jsonify({"error": {"code": "no_encontrada", "message": "Cámara no encontrada"}}), 404
    db.session.delete(cam)
    db.session.commit()
    return jsonify({"data": {"eliminada": True}})


# ── Probar conexión a una cámara ───────────────────────────────────────────────
@camaras_bp.post("/<uuid_camara>/probar")
@roles_required("admin", "super_admin")
def probar_camara(usuario_actual, uuid_camara):
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam:
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
        return jsonify({"data": {"online": False, "error": str(e)}})


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
def stream_camara(usuario_actual, uuid_camara):
    cam = Camara.query.filter_by(uuid_publico=uuid_camara).first()
    if not cam or not cam.activa:
        return jsonify({"error": {"code": "no_disponible",
                                  "message": "Cámara no disponible"}}), 404

    return Response(
        _generar_mjpeg(cam.url_rtsp()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
