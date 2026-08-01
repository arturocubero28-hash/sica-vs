"""
Instancias de extensiones compartidas.
Se definen aquí (sin app) para evitar imports circulares.
Cada módulo las importa desde aquí:  from app.extensions import db

SOCKET-17 (Auditoría Día 39): se eliminó Flask-SocketIO.
  El auditor reportó que estaba configurado con cors_allowed_origins="*",
  lo cual era cierto. Al revisar el historial resultó que era código
  muerto: entró en el commit inicial como andamiaje, nunca se le escribió
  un solo manejador de eventos ni una emisión, y el frontend nunca se
  conectó. El único uso previsto (avisar al residente de la entrada de su
  visita) quedó como un TODO que se eliminó el 3 de julio, cuando esa
  necesidad se resolvió con notificaciones push de Firebase — mejor
  solución para este caso, porque llegan al teléfono aunque la app esté
  cerrada, mientras que un WebSocket exige la app abierta y conectada.
  Además, el Dockerfile arranca gunicorn sin '-k eventlet', así que en
  producción no habría funcionado igual.

  Se eliminó en vez de solo corregir el CORS: la dependencia más segura
  es la que no está instalada. Si en el futuro hace falta tiempo real,
  volver a agregarlo es trivial — pero entonces con orígenes restringidos
  desde el principio.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()


def _key_func():
    """
    Identifica al cliente para el rate limiting por su IP real.
    Detrás de Nginx, la IP real viene en X-Forwarded-For (no en remote_addr).
    """
    from flask import request
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address()


# Límite global suave + límites estrictos por endpoint (definidos con decoradores)
#
# Día 50: se agregó RATE_LIMIT_DEFAULT como variable de entorno opcional,
# para poder aflojar este límite SOLO en pruebas de estrés locales (donde
# Locust manda el tráfico de cientos de "usuarios" simulados desde una
# sola IP real, la de la máquina de pruebas) sin tocar el valor real de
# producción. Sin la variable, se comporta exactamente igual que antes.
import os
limiter = Limiter(
    key_func=_key_func,
    default_limits=[os.environ.get("RATE_LIMIT_DEFAULT", "600 per hour")],
    storage_uri=None,                  # se setea en create_app con REDIS_URL
    strategy="fixed-window",
)
