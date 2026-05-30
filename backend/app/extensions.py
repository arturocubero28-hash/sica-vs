"""
Instancias de extensiones compartidas.
Se definen aquí (sin app) para evitar imports circulares.
Cada módulo las importa desde aquí:  from app.extensions import db
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO

db = SQLAlchemy()
migrate = Migrate()
# async_mode eventlet para que funcione con gunicorn -k eventlet en producción
socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")
