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
from app.extensions import db, migrate, socketio, limiter


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Seguridad: en producción, abortar si hay secretos inseguros (ver config.py)
    from app.config import validar_config_produccion
    validar_config_produccion()

    # Confiar en X-Forwarded-For solo del reverse proxy (1 salto). Sin esto, el
    # cliente podría falsear su IP en los logs de auditoría. En local sin proxy,
    # Werkzeug usa remote_addr normalmente.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # --- Extensiones ---
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    # Rate limiter con Redis como almacenamiento (consistente entre workers)
    limiter.storage_uri = app.config["REDIS_URL"]
    limiter.init_app(app)

    # --- Importar modelos (para que SQLAlchemy / Migrate los conozca) ---
    # Cada dueño de módulo agrega aquí su import cuando cree sus modelos.
    from app.models import usuario  # noqa: F401  (Integrante 1 — ejemplo base)
    from app.models import cuenta   # noqa: F401  (Integrante 2)
    from app.models import visita   # noqa: F401  (Integrante 3)
    from app.models.cuenta import Cuota, Pago  # noqa: F401  cuotas y pagos
    from app.models.camara import Camara  # noqa: F401  cámaras ONVIF/RTSP
    from app.models.comunicado import Comunicado  # noqa: F401  comunicados
    from app.models.caja import SesionCaja, ConfigCaja, AjusteCaja, SalidaCaja  # noqa: F401
    from app.models.auditoria import LogAuditoria  # noqa: F401  auditoría forense
    from app.models.token_revocado import TokenRevocado  # noqa: F401  blacklist JWT
    from app.models.sesion_activa import SesionActiva  # noqa: F401  sesiones/dispositivos
    from app.models.credencial_webauthn import CredencialWebAuthn  # noqa: F401  biometría WebAuthn
    from app.models.dispositivo import Dispositivo  # noqa: F401  Raspberry Pi de accesos

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

    from app.api.arreglos import arreglos_bp
    app.register_blueprint(arreglos_bp, url_prefix="/api/v1/arreglos")

    from app.api.recibos import recibos_bp
    app.register_blueprint(recibos_bp, url_prefix="/api/v1/recibos")

    from app.api.acceso import acceso_bp
    app.register_blueprint(acceso_bp, url_prefix="/api/v1/acceso")

    from app.api.inventario import inventario_bp
    app.register_blueprint(inventario_bp, url_prefix="/api/v1/inventario")

    from app.api.webauthn import webauthn_bp
    app.register_blueprint(webauthn_bp, url_prefix="/api/v1/auth/webauthn")

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

    @app.errorhandler(429)
    def rate_limit_excedido(e):
        return jsonify({"error": {
            "code": "demasiados_intentos",
            "message": "Demasiados intentos. Espera unos minutos antes de volver a intentar.",
        }}), 429

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
            # Información extendida de residentes (Día 6)
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS dni VARCHAR(20)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rtn VARCHAR(20)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS direccion_exacta VARCHAR(255)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS profesion VARCHAR(120)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS contacto_emergencia_nombre VARCHAR(120)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS contacto_emergencia_telefono VARCHAR(30)",
            # Foto extra del guardia: número asignado (Día 6)
            "ALTER TABLE eventos_acceso ADD COLUMN IF NOT EXISTS foto_numero_asignado VARCHAR(255)",
            # Tipo de acceso de cada tarjeta RFID (Día 13): vehicular abre
            # torniquetes y barreras; peatonal solo torniquetes.
            "ALTER TABLE tarjetas_proximidad ADD COLUMN IF NOT EXISTS tipo_acceso VARCHAR(20) NOT NULL DEFAULT 'vehicular'",
            # Código numérico para delivery (Día 6)
            "ALTER TABLE codigos_qr ADD COLUMN IF NOT EXISTS codigo_numerico VARCHAR(8)",
            # Arreglos de pago (Día 7): vincular cuota a su arreglo
            "ALTER TABLE cuotas ADD COLUMN IF NOT EXISTS arreglo_id BIGINT",
            "ALTER TABLE abonos_arreglo ADD COLUMN IF NOT EXISTS pago_id BIGINT",
            # Los pagos de abonos no tienen cuota directa: cuota_id puede ser null
            "ALTER TABLE pagos ALTER COLUMN cuota_id DROP NOT NULL",
            # Recibos SAR Fase 1 (Día 7): correlativo de recibo
            "ALTER TABLE pagos ADD COLUMN IF NOT EXISTS numero_recibo INTEGER",
            # Control de billetes al cierre (Día 9)
            "ALTER TABLE sesiones_caja ADD COLUMN IF NOT EXISTS desglose_billetes TEXT",
            # Dueño del edificio que avala inquilinos (Día 10)
            "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS propietario_id BIGINT REFERENCES usuarios(id)",
            # Login biométrico WebAuthn (Día 17): columnas que pudieron faltar si la
            # tabla se creó parcialmente en un arranque anterior.
            "ALTER TABLE credenciales_webauthn ADD COLUMN IF NOT EXISTS nombre_dispositivo VARCHAR(120)",
            "ALTER TABLE credenciales_webauthn ADD COLUMN IF NOT EXISTS transports VARCHAR(120)",
            "ALTER TABLE credenciales_webauthn ADD COLUMN IF NOT EXISTS ultimo_uso TIMESTAMPTZ",
            "ALTER TABLE credenciales_webauthn ADD COLUMN IF NOT EXISTS creada_en TIMESTAMPTZ",
            "ALTER TABLE credenciales_webauthn ADD COLUMN IF NOT EXISTS sign_count BIGINT NOT NULL DEFAULT 0",
            # Día 19 — Hardware de trancas: relay/GPIO y duración del pulso por acceso físico.
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS relay_pin INTEGER",
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS pulso_ms INTEGER NOT NULL DEFAULT 800",
            # Día 20 — Soporte multi-Pi: punto de acceso que identifica la Raspberry Pi.
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS punto_acceso VARCHAR(80)",
            # Índices en columnas más consultadas (Día 12 — F5 de la auditoría).
            # Aceleran mora, reportes, caja y dashboard cuando crecen los datos.
            "CREATE INDEX IF NOT EXISTS ix_cuotas_estado ON cuotas (estado)",
            "CREATE INDEX IF NOT EXISTS ix_cuotas_cuenta_id ON cuotas (cuenta_id)",
            "CREATE INDEX IF NOT EXISTS ix_pagos_estado ON pagos (estado)",
            "CREATE INDEX IF NOT EXISTS ix_pagos_cuenta_id ON pagos (cuenta_id)",
            "CREATE INDEX IF NOT EXISTS ix_visitas_estado ON visitas (estado)",
            "CREATE INDEX IF NOT EXISTS ix_visitas_cuenta_id ON visitas (cuenta_id)",
            "CREATE INDEX IF NOT EXISTS ix_eventos_acceso_visita_id ON eventos_acceso (visita_id)",
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
    def _headers_seguridad(response):
        """Headers de seguridad HTTP aplicados a todas las respuestas."""
        # Evita que el navegador adivine el tipo MIME (anti MIME-sniffing)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Impide que la app se embeba en iframes de otros sitios (anti clickjacking)
        response.headers["X-Frame-Options"] = "DENY"
        # Controla qué información de referer se envía
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Limita el acceso a APIs sensibles del navegador
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), payment=()"
        # HSTS: fuerza HTTPS (solo tiene efecto sobre https; inofensivo en http local)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Content-Security-Policy: restringe orígenes de scripts/estilos/imágenes.
        # 'unsafe-inline' se mantiene porque el frontend usa estilos inline y el SW;
        # se puede endurecer más en una fase posterior.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:; "
            "media-src 'self' blob:; "
            "frame-ancestors 'none'"
        )
        return response

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
            email_log = usuario.email if usuario else getattr(g, "email_intento", None)
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
            if ip:
                ip = ip.split(",")[0].strip()[:45]
            log = LogAuditoria(
                usuario_id=usuario.id if usuario else None,
                email=email_log,
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
