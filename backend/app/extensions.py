"""
Instancias de extensiones compartidas.
Se definen aquí (sin app) para evitar imports circulares.
Cada módulo las importa desde aquí:  from app.extensions import db
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
# async_mode eventlet para que funcione con gunicorn -k eventlet en producción
socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")


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
limiter = Limiter(
    key_func=_key_func,
    default_limits=["600 per hour"],   # tope global generoso por IP
    storage_uri=None,                  # se setea en create_app con REDIS_URL
    strategy="fixed-window",
)
