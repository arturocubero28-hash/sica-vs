"""
Application Factory de SICA-VS.

Patrón a seguir por todo el equipo:
  1. Cada módulo define sus modelos en app/models/<modulo>.py
  2. Cada módulo define su blueprint en app/api/<modulo>.py
  3. Aquí solo se registran. NO se escribe lógica de negocio en este archivo.
"""
from flask import Flask, jsonify
from flask_cors import CORS

from app.config import Config
from app.extensions import db, migrate, socketio


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Extensiones ---
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    # --- Importar modelos (para que SQLAlchemy / Migrate los conozca) ---
    # Cada dueño de módulo agrega aquí su import cuando cree sus modelos.
    from app.models import usuario  # noqa: F401  (Integrante 1 — ejemplo base)
    from app.models import cuenta   # noqa: F401  (Integrante 2)
    from app.models import visita   # noqa: F401  (Integrante 3)
    # from app.models import pago        # Integrante 4

    # --- Registrar blueprints (endpoints) ---
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")

    # Cada dueño de módulo registra su blueprint aquí:
    from app.api.cuentas import cuentas_bp
    app.register_blueprint(cuentas_bp, url_prefix="/api/v1/unidades")

    from app.api.visitas import visitas_bp
    app.register_blueprint(visitas_bp, url_prefix="/api/v1/visitas")

    # --- Healthcheck y manejo de errores estándar ---
    @app.get("/api/v1/health")
    def health():
        return jsonify({"data": {"status": "ok", "service": "sica-vs"}})

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": {"code": "not_found", "message": "Recurso no encontrado"}}), 404

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"error": {"code": "server_error", "message": "Error interno"}}), 500

    return app
