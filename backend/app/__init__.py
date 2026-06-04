"""
SICA-VS — Sistema Integral de Control de Accesos
Copyright (c) 2026 Arturo Cubero. Todos los derechos reservados.

Software propietario. Prohibida su copia, distribución o uso comercial
sin autorización escrita del Autor. Ver archivo LICENSE.

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
    from app.models.cuenta import Cuota, Pago  # noqa: F401  cuotas y pagos
    from app.models.camara import Camara  # noqa: F401  cámaras ONVIF/RTSP
    from app.models.comunicado import Comunicado  # noqa: F401  comunicados
    from app.models.caja import SesionCaja, ConfigCaja, AjusteCaja  # noqa: F401
    from app.models.auditoria import LogAuditoria  # noqa: F401  auditoría forense

    # --- Registrar blueprints (endpoints) ---
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")

    # Cada dueño de módulo registra su blueprint aquí:
    from app.api.cuentas import cuentas_bp
    app.register_blueprint(cuentas_bp, url_prefix="/api/v1/unidades")

    from app.api.visitas import visitas_bp
    app.register_blueprint(visitas_bp, url_prefix="/api/v1/visitas")

    from app.api.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix="/api/v1/dashboard")

    from app.api.cuotas import cuotas_bp
    app.register_blueprint(cuotas_bp, url_prefix="/api/v1/cuotas")

    from app.api.camaras import camaras_bp
    app.register_blueprint(camaras_bp, url_prefix="/api/v1/camaras")

    from app.api.comunicados import comunicados_bp
    app.register_blueprint(comunicados_bp, url_prefix="/api/v1/comunicados")

    from app.api.reportes import reportes_bp
    app.register_blueprint(reportes_bp, url_prefix="/api/v1/reportes")

    from app.api.guardias import guardias_bp
    app.register_blueprint(guardias_bp, url_prefix="/api/v1/guardias")

    from app.api.caja import caja_bp
    app.register_blueprint(caja_bp, url_prefix="/api/v1/caja")

    from app.api.usuarios import usuarios_bp
    app.register_blueprint(usuarios_bp, url_prefix="/api/v1/usuarios")

    from app.api.desarrollador import dev_bp
    app.register_blueprint(dev_bp, url_prefix="/api/v1/dev")

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

    # Crear tablas que no existan (seguro: no toca tablas ni datos existentes).
    # Útil para la tabla 'camaras' que se añadió después del schema inicial.
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            app.logger.warning(f"db.create_all() omitido: {e}")

        # Migración ligera: agrega columnas nuevas a tablas existentes.
        # create_all() NO altera tablas que ya existen, así que las añadimos aquí.
        # Cada ALTER usa IF NOT EXISTS, por lo que es seguro ejecutarlo siempre.
        from sqlalchemy import text

        # Valores nuevos en ENUMs de PostgreSQL (ADD VALUE IF NOT EXISTS es idempotente).
        # Deben ir en su propia transacción (ALTER TYPE ... ADD VALUE no corre dentro de un bloque con otras).
        enums = [
            "ALTER TYPE rol_global ADD VALUE IF NOT EXISTS 'cajero'",
            "ALTER TYPE rol_global ADD VALUE IF NOT EXISTS 'desarrollador'",
            "ALTER TYPE metodo_pago ADD VALUE IF NOT EXISTS 'efectivo'",
            "ALTER TYPE metodo_pago ADD VALUE IF NOT EXISTS 'tarjeta_pos'",
            "ALTER TYPE metodo_pago ADD VALUE IF NOT EXISTS 'linea'",
        ]
        for sql in enums:
            try:
                with db.engine.connect() as conn:
                    conn.execution_options(isolation_level="AUTOCOMMIT").execute(text(sql))
            except Exception as e:
                app.logger.warning(f"ALTER TYPE omitido: {e}")

        columnas = [
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE cuentas ADD COLUMN IF NOT EXISTS activa BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE pagos ADD COLUMN IF NOT EXISTS sesion_caja_id BIGINT",
        ]
        for sql in columnas:
            try:
                db.session.execute(text(sql))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                app.logger.warning(f"Migración de columna omitida: {e}")

    # ── Hook de auditoría forense ──────────────────────────────────────────────
    # Registra automáticamente cada request a la API en log_auditoria.
    # Solo loguea endpoints de la API (no archivos estáticos).
    @app.after_request
    def _auditar(response):
        from flask import request, g
        from app.models.auditoria import LogAuditoria
        # Solo rutas de la API, ignorar health checks y estáticos
        if not request.path.startswith("/api/v1/"):
            return response
        # No loguear el endpoint de logs mismo (evitar recursión)
        if request.path.startswith("/api/v1/dev/"):
            return response
        try:
            usuario = getattr(g, "usuario_actual", None)
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
            if ip:
                ip = ip.split(",")[0].strip()[:45]
            log = LogAuditoria(
                usuario_id=usuario.id if usuario else None,
                email=usuario.email if usuario else None,
                rol=usuario.rol if usuario else None,
                metodo=request.method,
                endpoint=request.path[:200],
                status_code=response.status_code,
                ip=ip,
                user_agent=(request.user_agent.string or "")[:300],
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()  # nunca romper el response por error de log
        return response

    return app
