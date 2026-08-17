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
from app.extensions import db, migrate, limiter


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
    # SOCKET-17: socketio.init_app() eliminado — era código muerto sin
    # manejadores ni emisiones. Ver la nota en extensions.py.
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    # Rate limiter con Redis como almacenamiento (consistente entre workers)
    #
    # Día 61 — bug real encontrado: el código anterior hacía
    # `limiter.storage_uri = app.config["REDIS_URL"]`, que PARECE
    # configurar el storage pero es un no-op silencioso. Flask-Limiter
    # guarda ese valor internamente como el atributo PRIVADO
    # `self._storage_uri` (con guion bajo), fijado una sola vez en el
    # constructor de Limiter() -- asignar `limiter.storage_uri` (sin
    # guion bajo, un nombre distinto) después de construido el objeto
    # solo crea un atributo nuevo y sin relación que la librería nunca
    # lee. Confirmado leyendo el código fuente instalado de
    # Flask-Limiter 3.8.0: init_app() busca primero la clave de
    # configuración de Flask RATELIMIT_STORAGE_URI, y si no la
    # encuentra, cae a "memory://" -- exactamente la advertencia
    # "Using the in-memory storage..." que aparecía en cada arranque
    # del backend desde el Día 50, sin que nadie lo notara porque el
    # rate limiting seguía funcionando igual (solo que sin persistir
    # entre reinicios ni compartirse entre el proceso backend y el
    # worker). El fix real: setear la clave de configuración de Flask
    # que la librería sí lee, ANTES de init_app().
    app.config["RATELIMIT_STORAGE_URI"] = app.config["REDIS_URL"]
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
    from app.models.residencial import Residencial  # noqa: F401  bases multi-residencial (Día 37)
    from app.models.plan import Plan  # noqa: F401  planes de suscripción (Día 50)
    from app.models.archivo_residencial import ArchivoResidencial  # noqa: F401  cuota de almacenamiento (Día 50)
    from app.models.suscripcion_pago import SuscripcionPago  # noqa: F401  pagos de suscripción (Día 50)
    from app.models.dispositivo_movil import DispositivoMovil  # noqa: F401  tokens FCM push
    from app.models.cuenta import ConfigResidencial  # noqa: F401  config global residencial

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

    from app.api.publico import publico_bp
    app.register_blueprint(publico_bp, url_prefix="/api/v1/publico")

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

    from app.api.suscripcion import suscripcion_bp
    app.register_blueprint(suscripcion_bp, url_prefix="/api/v1/suscripcion")

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

    from app.api.dispositivos import dispositivos_bp
    app.register_blueprint(dispositivos_bp, url_prefix="/api/v1/dispositivos")

    from app.api.tarjeta_virtual import tv_bp
    app.register_blueprint(tv_bp, url_prefix="/api/v1/acceso")

    from app.api.credencial_ble import ble_bp
    app.register_blueprint(ble_bp, url_prefix="/api/v1/acceso")

    # Inicializar Firebase Cloud Messaging (notificaciones push).
    # Si no está configurado (falta el archivo de credenciales), no rompe:
    # el servicio simplemente omite el envío de notificaciones.
    from app.services import notificaciones as _notif
    _notif.inicializar()

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
            # Aislación multi-residencial (Día 46): comunicados, tarifas e
            # inventario pasan de catálogo global a propios de cada residencial.
            # Las filas existentes se asignan a la residencial base (Villas del
            # Sol, id=1) para no dejarlas huérfanas. Idempotente por IF NOT EXISTS.
            "ALTER TABLE comunicados ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "ALTER TABLE tarifas ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "ALTER TABLE tipos_tarjeta ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "UPDATE comunicados SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            "UPDATE tarifas SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            "UPDATE tipos_tarjeta SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            # Saldo de caja por residencial (Día 47): config_caja era un
            # singleton (una sola fila, id=1) con el saldo inicial de TODO el
            # sistema. Ahora hay una fila POR residencial. La fila existente
            # (id=1) se asigna a la residencial base; de ahí en adelante cada
            # residencial nueva obtiene su propia fila con saldo_inicial=0
            # (ver ConfigCaja.get(residencial_id)). Sin UNIQUE todavía —se
            # agrega en la misma migración, protegido con un bloque que la
            # aplica solo si no existe, porque IF NOT EXISTS no aplica a
            # constraints como sí aplica a columnas.
            "ALTER TABLE config_caja ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "UPDATE config_caja SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            # AjusteCaja necesita residencial_id DIRECTO (no solo vía sesión):
            # los ajustes de tipo 'saldo_inicial' y 'conteo' son correcciones
            # a nivel de residencial, no atadas a ninguna sesión de caja en
            # particular (sesion_caja_id queda NULL para esos dos tipos). Sin
            # esta columna, esos ajustes quedarían invisibles para el cálculo
            # de saldo de cualquier residencial.
            "ALTER TABLE ajustes_caja ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "UPDATE ajustes_caja a SET residencial_id = ("
            "  SELECT u.residencial_id FROM sesiones_caja s "
            "  JOIN usuarios u ON u.id = s.cajero_id WHERE s.id = a.sesion_caja_id"
            ") WHERE a.residencial_id IS NULL AND a.sesion_caja_id IS NOT NULL",
            "UPDATE ajustes_caja SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            # Cámaras por residencial (Día 48 — hallazgo de auditoría de
            # seguridad: un admin de otra residencial podía editar, borrar
            # o ver el STREAM DE VIDEO EN VIVO de una cámara ajena, porque
            # Camara no tenía ninguna forma confiable de saber de quién
            # era). Backfill en dos pasos: primero se intenta inferir la
            # residencial real vía acceso_id o dispositivo_id (más
            # preciso); lo que quede sin resolver se asigna a la
            # residencial base, igual que el resto de las migraciones.
            "ALTER TABLE camaras ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "UPDATE camaras c SET residencial_id = ("
            "  SELECT a.residencial_id FROM accesos_fisicos a WHERE a.id = c.acceso_id"
            ") WHERE c.residencial_id IS NULL AND c.acceso_id IS NOT NULL",
            "UPDATE camaras c SET residencial_id = ("
            "  SELECT d.residencial_id FROM dispositivos_pi d WHERE d.id = c.dispositivo_id"
            ") WHERE c.residencial_id IS NULL AND c.dispositivo_id IS NOT NULL",
            "UPDATE camaras SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            # Recibos por residencial (Día 48 — hallazgo de auditoría:
            # ConfigRecibo era una sola fila global, igual patrón que
            # ConfigCaja antes del Día 47 — incluía el CORRELATIVO de
            # facturas compartido entre residenciales).
            "ALTER TABLE config_recibo ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            "UPDATE config_recibo SET residencial_id = (SELECT MIN(id) FROM residenciales) WHERE residencial_id IS NULL",
            # Día 49 — dos formas de controlar una tranca (económico: lector
            # Wiegand + relay directo a GPIO; premium: lector Cidron por
            # OSDP/RS-485 + relay externo por Modbus). El tipo ENUM se crea
            # con un bloque DO/EXCEPTION (Postgres no tiene "CREATE TYPE IF
            # NOT EXISTS" nativo) — a diferencia de "ALTER TYPE ... ADD
            # VALUE" (que sí necesita su propia lista con AUTOCOMMIT, ver
            # 'enums' más arriba), CREATE TYPE corre bien dentro de una
            # transacción normal, así que va en esta misma lista.
            "DO $$ BEGIN "
            "CREATE TYPE modo_control_acceso AS ENUM ('gpio', 'modbus'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$",
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS modo_control "
            "modo_control_acceso NOT NULL DEFAULT 'gpio'",
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS wiegand_d0_pin INTEGER",
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS wiegand_d1_pin INTEGER",
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS relay_canal INTEGER",
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS lector_direccion_osdp INTEGER",
            # Día 50 — sistema de suscripciones. La tabla 'planes' la crea
            # db.create_all() más arriba (tabla nueva); acá solo van las
            # columnas nuevas en 'residenciales', que sí es una tabla
            # existente. Todo nullable/con default a propósito: una
            # residencial sin plan asignado (como Villas del Sol hoy)
            # nunca se considera suspendida — ver Residencial.esta_suspendida().
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS plan_id BIGINT REFERENCES planes(id)",
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS fecha_proximo_pago DATE",
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS dias_gracia INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS almacenamiento_usado_bytes BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS upgrade_solicitado BOOLEAN NOT NULL DEFAULT false",
            # Día 50 (mismo día, generalización): FotoAcceso -> ArchivoResidencial
            # -- el usuario decidió que los comprobantes de pago comparten el
            # mismo pozo de cuota que las fotos de acceso. Si la tabla vieja
            # ya existe (se creó con el nombre anterior en un restart previo),
            # se renombra preservando cualquier fila que ya tuviera; si nunca
            # existió (instalación nueva), este RENAME falla silenciosamente
            # (capturado por el try/except de este mismo loop) y
            # db.create_all() más arriba ya crea la tabla completa con el
            # nombre nuevo, columnas incluidas.
            "ALTER TABLE IF EXISTS fotos_acceso RENAME TO archivos_residencial",
            "ALTER TABLE archivos_residencial ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) NOT NULL DEFAULT 'acceso'",
            "ALTER TABLE archivos_residencial ADD COLUMN IF NOT EXISTS pago_id BIGINT REFERENCES pagos(id)",
            # Día 51 — niveles de plan por flags de función. Default true:
            # los planes ya creados (Día 49-50) deben seguir con acceso
            # completo, tal como funcionaban antes de que este sistema
            # existiera.
            "ALTER TABLE planes ADD COLUMN IF NOT EXISTS permite_cuotas BOOLEAN NOT NULL DEFAULT true",
            "ALTER TABLE planes ADD COLUMN IF NOT EXISTS permite_notificaciones BOOLEAN NOT NULL DEFAULT true",
            # Día 53 — Sprint 1: pausa liviana de acceso, distinta de "activa"
            # (dar de baja). Default false: ninguna cuenta empieza pausada.
            "ALTER TABLE cuentas ADD COLUMN IF NOT EXISTS acceso_pausado BOOLEAN NOT NULL DEFAULT false",
            # Día 53 — Sprint 2: tercer flag de plan, para el plan Intermedio.
            "ALTER TABLE planes ADD COLUMN IF NOT EXISTS permite_control_fisico BOOLEAN NOT NULL DEFAULT true",
            # Día 54 — bug real: config_residencial era una sola fila
            # global, compartida por TODAS las residenciales. Se agrega
            # residencial_id (una config por residencial). La fila legado
            # (id=1, sin residencial_id) se backfillea a Villas del Sol --
            # la residencial original del proyecto, la que más probable
            # venía usando esos valores hasta ahora. Cualquier otra
            # residencial que ya tuviera cuotas activas (ej. una recién
            # subida a un plan con cuotas) arranca con los valores por
            # defecto (día 1, 7 días de gracia) la primera vez que se
            # consulte su config -- conviene revisarlos a mano si no son
            # los que corresponden.
            "ALTER TABLE config_residencial ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            """UPDATE config_residencial SET residencial_id = (
                   SELECT id FROM residenciales WHERE nombre = 'Villas del Sol' LIMIT 1
               ) WHERE residencial_id IS NULL""",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_config_residencial_unica ON config_residencial (residencial_id)",
            # Día 54 — Sprint 2: numero_recibo tenía un índice único GLOBAL,
            # pero el correlativo se calcula por residencial (ConfigRecibo,
            # ya corregido desde el Día 48) -- dos residenciales con su
            # propio primer recibo chocaban contra la restricción de la
            # base ("duplicate key... numero_recibo=1"). Se agrega
            # residencial_id a pagos (desnormalizado, ver evento
            # before_insert en models/cuenta.py), se backfillean los pagos
            # existentes resolviendo su residencial vía cuenta->unidad, se
            # quita el índice global viejo y se crea uno compuesto nuevo
            # (residencial_id, numero_recibo) -- cada residencial puede
            # tener su propio recibo #1 sin chocar con las demás.
            "ALTER TABLE pagos ADD COLUMN IF NOT EXISTS residencial_id BIGINT REFERENCES residenciales(id)",
            """UPDATE pagos SET residencial_id = (
                   SELECT u.residencial_id FROM cuentas c
                   JOIN unidades u ON u.id = c.unidad_id
                   WHERE c.id = pagos.cuenta_id
               ) WHERE residencial_id IS NULL""",
            "DROP INDEX IF EXISTS idx_pagos_numero_recibo_unico",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_pagos_numero_recibo_unico
                   ON pagos (residencial_id, numero_recibo) WHERE numero_recibo IS NOT NULL""",
            # Día 54 — limpieza del bug de arriba: cualquier ConfigRecibo
            # que haya quedado con el nombre "Residencial Villas del Sol"
            # PUESTO POR EL DEFAULT VIEJO (no a propósito por el admin) se
            # limpia a NULL, para que el fallback dinámico (nombre real de
            # la residencial) se active. Solo toca las filas de
            # residenciales que NO se llaman así de verdad -- si alguna sí
            # se llama "Residencial Villas del Sol" de casualidad, no se
            # le borra nada.
            """UPDATE config_recibo SET nombre_emisor = NULL
                   WHERE nombre_emisor = 'Residencial Villas del Sol'
                   AND residencial_id NOT IN (
                       SELECT id FROM residenciales WHERE nombre = 'Villas del Sol'
                   )""",
            # Mismo arreglo, mismo criterio, para direccion_emisor (otro
            # default hardcodeado encontrado en el mismo modelo apenas se
            # revisó con cuidado: "San Pedro Sula, Honduras" fijo).
            """UPDATE config_recibo SET direccion_emisor = NULL
                   WHERE direccion_emisor = 'San Pedro Sula, Honduras'
                   AND residencial_id NOT IN (
                       SELECT id FROM residenciales WHERE nombre = 'Villas del Sol'
                   )""",
            # Día 55 — días de gracia por casa (override del global de la
            # residencial). NULL = usa el global; no hace falta backfill,
            # null ya significa "sin override" para este campo.
            "ALTER TABLE cuentas ADD COLUMN IF NOT EXISTS dias_gracia SMALLINT",
            # Día 55 — Sprint 2a: marca de "cuotas pendientes de configurar".
            # Default false: ninguna residencial arranca con el wizard
            # pendiente; se enciende solo en la transición sin-cuotas ->
            # con-cuotas (ver marcar_config_cuotas_si_corresponde).
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS cuotas_config_pendiente BOOLEAN NOT NULL DEFAULT false",
            # Día 55 — el CHECK constraint de la base topaba dia_pago en 28,
            # así que guardar día 30 reventaba el commit con error 500 (el
            # "<!doctype" que veía el frontend). Se busca el constraint por
            # su definición (el nombre lo autogenera Postgres y puede variar)
            # y se reemplaza por uno que permita 1..30. El bloque DO/plpgsql
            # lo hace de forma segura aunque el constraint no exista o ya
            # esté actualizado.
            """DO $$
               DECLARE cname text;
               BEGIN
                 SELECT conname INTO cname FROM pg_constraint
                 WHERE conrelid = 'cuentas'::regclass
                   AND contype = 'c'
                   AND pg_get_constraintdef(oid) ILIKE '%dia_pago%28%';
                 IF cname IS NOT NULL THEN
                   EXECUTE 'ALTER TABLE cuentas DROP CONSTRAINT ' || quote_ident(cname);
                 END IF;
                 IF NOT EXISTS (
                   SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'cuentas'::regclass AND conname = 'cuentas_dia_pago_check_30'
                 ) THEN
                   ALTER TABLE cuentas ADD CONSTRAINT cuentas_dia_pago_check_30
                     CHECK (dia_pago BETWEEN 1 AND 30);
                 END IF;
               END $$;""",
            # Colores personalizables por residencial (Día 47). NULL =
            # usa el valor de fábrica (ver DEFAULT_COLOR_* en models/
            # residencial.py) — no hace falta backfill, a diferencia de
            # las migraciones anteriores: null ya significa "sin
            # personalizar" para este campo, no un dato huérfano.
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS color_primario VARCHAR(7)",
            "ALTER TABLE residenciales ADD COLUMN IF NOT EXISTS color_secundario VARCHAR(7)",
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
            # Día 21 — Dirección fija de la tranca (entrada/salida) como estándar.
            "ALTER TABLE accesos_fisicos ADD COLUMN IF NOT EXISTS direccion VARCHAR(10) NOT NULL DEFAULT 'entrada'",
            # Día 22 — Idempotencia de eventos reportados por la Pi.
            "ALTER TABLE eventos_acceso ADD COLUMN IF NOT EXISTS id_externo VARCHAR(80)",
            # Día 24 — vincular un pago a un abono de arreglo (prima/abonos)
            "ALTER TABLE pagos ADD COLUMN IF NOT EXISTS abono_id BIGINT REFERENCES abonos_arreglo(id)",
            # Día 24 — intervalo configurable entre abonos del arreglo
            "ALTER TABLE arreglos_pago ADD COLUMN IF NOT EXISTS intervalo_dias INTEGER NOT NULL DEFAULT 30",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_eventos_id_externo ON eventos_acceso (id_externo) WHERE id_externo IS NOT NULL",
            # Índices en columnas más consultadas (Día 12 — F5 de la auditoría).
            # Aceleran mora, reportes, caja y dashboard cuando crecen los datos.
            "CREATE INDEX IF NOT EXISTS ix_cuotas_estado ON cuotas (estado)",
            "CREATE INDEX IF NOT EXISTS ix_cuotas_cuenta_id ON cuotas (cuenta_id)",
            "CREATE INDEX IF NOT EXISTS ix_pagos_estado ON pagos (estado)",
            "CREATE INDEX IF NOT EXISTS ix_pagos_cuenta_id ON pagos (cuenta_id)",
            "CREATE INDEX IF NOT EXISTS ix_visitas_estado ON visitas (estado)",
            "CREATE INDEX IF NOT EXISTS ix_visitas_cuenta_id ON visitas (cuenta_id)",
            "CREATE INDEX IF NOT EXISTS ix_eventos_acceso_visita_id ON eventos_acceso (visita_id)",
            # Día 22 — Índices para los historiales de acceso (escalan con muchos
            # registros). Los historiales filtran por origen y ordenan por fecha.
            "CREATE INDEX IF NOT EXISTS ix_eventos_origen_fecha ON eventos_acceso (origen, ocurrido_en DESC)",
            "CREATE INDEX IF NOT EXISTS ix_eventos_acceso_id ON eventos_acceso (acceso_id)",
            "CREATE INDEX IF NOT EXISTS ix_eventos_tarjeta_id ON eventos_acceso (tarjeta_id)",
            "CREATE INDEX IF NOT EXISTS ix_eventos_residente_id ON eventos_acceso (residente_id)",
            # Día 25 — Índice en dni para la validación anti-moroso en el alta de
            # cuentas (evita escanear toda la tabla de usuarios).
            "CREATE INDEX IF NOT EXISTS ix_usuarios_dni ON usuarios (dni)",
            # Día 25 — La revisión de mora filtra por fecha de vencimiento.
            "CREATE INDEX IF NOT EXISTS ix_cuotas_vencimiento ON cuotas (fecha_vencimiento)",
            # Día 29 — Agente de cámaras: distinguir tipo de Pi (acceso/camara)
            # y su latido de conexión (distinto de ultima_sync, que es de accesos).
            "ALTER TABLE dispositivos_pi ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) NOT NULL DEFAULT 'acceso'",
            "ALTER TABLE dispositivos_pi ADD COLUMN IF NOT EXISTS ultimo_heartbeat TIMESTAMPTZ",
            "ALTER TABLE camaras ADD COLUMN IF NOT EXISTS dispositivo_id BIGINT REFERENCES dispositivos_pi(id)",
            # Día 29 — Información laboral/educativa del residente
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ocupacion VARCHAR(20)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS centro_estudios VARCHAR(160)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS lugar_trabajo VARCHAR(160)",
            # Día 29 — QR recurrentes bloqueados por defecto
            "ALTER TABLE cuentas ADD COLUMN IF NOT EXISTS qr_recurrente_habilitado BOOLEAN NOT NULL DEFAULT FALSE",
            # Día 29 — Límites de personas por unidad y aptos por edificio
            "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS max_residentes_extra INTEGER",
            "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS max_apartamentos INTEGER",
            # Día 29 (fix) — edificios contenedor sin cuota: tarifa/dia_pago opcionales
            "ALTER TABLE cuentas ALTER COLUMN tarifa_id DROP NOT NULL",
            "ALTER TABLE cuentas ALTER COLUMN dia_pago DROP NOT NULL",
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
        # ── Content-Security-Policy ──────────────────────────────────────
        # CSP-19 (Auditoría Día 39). El auditor reportó que este CSP tenía
        # 'unsafe-inline' y 'unsafe-eval' en script-src. Era cierto.
        #
        # CONTEXTO IMPORTANTE: este backend NO sirve HTML. De sus 180 rutas,
        # 179 son /api/ que devuelven JSON, y la única excepción es /static/.
        # Un CSP es una instrucción al navegador sobre qué puede ejecutar en
        # una PÁGINA HTML — en una respuesta JSON no tiene nada que hacer.
        # Quien sirve el HTML es Vite en desarrollo y Nginx en producción, y
        # ninguno pasa por acá.
        #
        # Aun así se endurece al máximo, por dos razones: cuesta nada (la API
        # no ejecuta scripts, así que no hay nada que romper) y evita que
        # alguien copie este CSP permisivo pensando que es el bueno.
        #
        # El CSP que SÍ importa es el de Nginx, que protege el HTML real.
        # Está escrito y comentado en deploy/nginx-sicavs.conf. Ver también
        # docs/CSP_Y_CABECERAS.md para por qué desarrollo y producción
        # difieren y qué hay que verificar al desplegar.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "        # nada permitido salvo lo que se liste
            "frame-ancestors 'none'; "    # no embebible en ningún iframe
            "base-uri 'none'; "           # no se puede reescribir la URL base
            "form-action 'none'"          # ningún formulario puede enviarse
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
            # Día 61 — BUG REAL encontrado (reportado en vivo: al crear una
            # casa con un email duplicado, la casa quedaba creada igual
            # pese al error). Causa: este commit() de más abajo, pensado
            # solo para guardar el registro de auditoría, en realidad
            # confirma TODO lo que haya quedado pendiente (flush() sin
            # commit ni rollback) en la sesión de SQLAlchemy durante el
            # resto del request -- incluyendo escrituras de negocio que
            # deberían haberse descartado porque el request terminó en
            # error. Caso real: crear_cuenta() guarda (flush) la Unidad
            # nueva ANTES de validar el email del titular; si el email ya
            # existe, el endpoint devuelve un error sin hacer rollback --
            # pero este commit() de auditoría, que corre en TODAS las
            # respuestas sin excepción, terminaba confirmando esa Unidad
            # "fantasma" igual, dejando la casa creada aunque el usuario
            # viera un error.
            #
            # Fix: se descarta primero cualquier cosa pendiente de negocio
            # (rollback) -- inofensivo si no hay nada pendiente, que es el
            # caso normal en un request exitoso donde el propio endpoint ya
            # hizo su commit -- y recién ahí se agrega y confirma el
            # registro de auditoría en una transacción propia y limpia. Así
            # el log de auditoría queda desacoplado de cualquier escritura
            # de negocio a medio hacer, sin importar si el endpoint que
            # corrió antes se olvidó de un rollback explícito en alguno de
            # sus caminos de error -- corrige esto de raíz para TODOS los
            # endpoints del backend, no solo crear_cuenta.
            db.session.rollback()

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
