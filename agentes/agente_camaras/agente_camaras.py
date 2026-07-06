"""
AGENTE DE CÁMARAS — SICA-VS
============================
Programa independiente que corre en la Raspberry Pi de cámaras, en la LAN
de la residencial (junto al NVR). Su trabajo:

  1. Descargar del servidor central (nube) la lista de cámaras que le tocan,
     con sus credenciales RTSP (mismo mecanismo de token que el agente de
     accesos: X-Device-Token).
  2. Exponer un proxy MJPEG local para cada cámara (reutiliza EXACTAMENTE la
     misma lógica que ya corría en el backend: cv2.VideoCapture + imencode).
  3. Reportar un heartbeat periódico para que el panel sepa "agente conectado".
  4. NO abre ningún puerto hacia adentro: el acceso desde la nube llega a
     través de un túnel saliente (Cloudflare Tunnel / ngrok / Tailscale) que
     se configura aparte, apuntando al puerto de este agente.

No requiere Docker ni PostgreSQL. Solo Python 3 + OpenCV + Flask + requests.
Pensado para correr como servicio systemd (ver agente_camaras.service).

INSTALACIÓN EN LA RASPBERRY PI:
  sudo apt update && sudo apt install -y python3-pip python3-opencv
  pip3 install flask requests
  # Copiar este archivo y config.py a /home/pi/agente_camaras/
  # Editar config.py con la URL del servidor y el TOKEN del dispositivo
  python3 agente_camaras.py
"""
import time
import threading
import logging

import cv2
import requests
from flask import Flask, Response, jsonify

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("agente_camaras")

app = Flask(__name__)

# Caché en memoria de las cámaras asignadas a este agente. Se refresca
# periódicamente desde el servidor central (por si el admin agrega/quita
# cámaras sin tener que reiniciar la Pi).
_camaras = {}   # {uuid_camara: {url_rtsp, nombre, ...}}
_lock = threading.Lock()


def _headers():
    return {"X-Device-Token": config.DEVICE_TOKEN}


def _url_rtsp(cam):
    """Reconstruye la URL RTSP igual que Camara.url_rtsp() en el backend."""
    cred = ""
    if cam.get("usuario"):
        cred = f"{cam['usuario']}:{cam.get('password') or ''}@"
    ruta = cam.get("ruta_stream") or ""
    return f"rtsp://{cred}{cam['ip']}:{cam['puerto_rtsp']}{ruta}"


def descargar_config():
    """Descarga la lista de cámaras asignadas a este dispositivo."""
    try:
        res = requests.get(
            f"{config.SERVIDOR_URL}/api/v1/acceso/camaras/config",
            headers=_headers(), timeout=10,
        )
        res.raise_for_status()
        data = res.json()["data"]
        nuevas = {c["id"]: c for c in data["camaras"]}
        with _lock:
            _camaras.clear()
            _camaras.update(nuevas)
        log.info("Config actualizada: %d cámara(s) asignada(s)", len(nuevas))
    except Exception as e:
        log.warning("No se pudo descargar la config del servidor: %s", e)


def enviar_heartbeat():
    """Avisa al servidor que este agente sigue vivo."""
    try:
        requests.post(
            f"{config.SERVIDOR_URL}/api/v1/acceso/camaras/heartbeat",
            headers=_headers(), timeout=8,
        )
    except Exception as e:
        log.warning("Heartbeat falló (revisar conexión a internet): %s", e)


def _hilo_fondo():
    """Corre en segundo plano: refresca config y manda heartbeat."""
    ciclo = 0
    while True:
        enviar_heartbeat()
        # Refrescar la lista de cámaras cada ~5 heartbeats (menos frecuente)
        if ciclo % 5 == 0:
            descargar_config()
        ciclo += 1
        time.sleep(config.HEARTBEAT_SEGUNDOS)


def _generar_mjpeg(url_rtsp):
    """Idéntico al proxy que ya corría en el backend (cv2 -> MJPEG)."""
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


@app.get("/salud")
def salud():
    """Para verificar desde el navegador local que el agente está vivo."""
    with _lock:
        n = len(_camaras)
    return jsonify({"ok": True, "camaras_asignadas": n})


@app.get("/stream/<uuid_camara>")
def stream(uuid_camara):
    with _lock:
        cam = _camaras.get(uuid_camara)
    if not cam:
        return jsonify({"error": "Cámara no asignada a este agente"}), 404

    return Response(
        _generar_mjpeg(_url_rtsp(cam)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    log.info("Agente de cámaras SICA-VS iniciando...")
    log.info("Servidor central: %s", config.SERVIDOR_URL)

    descargar_config()  # primera carga antes de arrancar

    hilo = threading.Thread(target=_hilo_fondo, daemon=True)
    hilo.start()

    app.run(host="0.0.0.0", port=config.PUERTO_LOCAL, threaded=True)
