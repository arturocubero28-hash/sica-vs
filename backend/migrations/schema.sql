-- =====================================================================
-- SICA-VS — Sistema Integral de Control de Accesos
-- Residencial Villas del Sol, San Pedro Sula
-- Esquema de base de datos (PostgreSQL 15)
-- =====================================================================
-- Convenciones:
--   * Nombres de tabla en plural, snake_case.
--   * Toda tabla lleva id (PK), created_at y updated_at.
--   * Los borrados son lógicos (campo estado / activo), NUNCA físicos,
--     para conservar trazabilidad histórica.
--   * Los montos se guardan en NUMERIC(10,2) (Lempiras).
-- =====================================================================

-- Extensión para generar UUIDs (tokens de QR, identificadores públicos)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================================
-- 1. USUARIOS Y AUTENTICACIÓN
-- =====================================================================

-- Roles globales del sistema (no confundir con el rol DENTRO de una casa).
-- super_admin: equipo desarrollador / dueño del sistema
-- admin:       administración de la residencial
-- guardia:     personal de seguridad en casetas
-- residente:   titular o miembro de una casa/apartamento
CREATE TYPE rol_global AS ENUM ('super_admin', 'admin', 'guardia', 'residente');

CREATE TABLE usuarios (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID        NOT NULL DEFAULT gen_random_uuid(),  -- id seguro para exponer en API/app
    nombre          VARCHAR(120) NOT NULL,
    apellido        VARCHAR(120) NOT NULL,
    email           VARCHAR(160) NOT NULL UNIQUE,
    telefono        VARCHAR(30),
    password_hash   VARCHAR(255) NOT NULL,                -- bcrypt/argon2 (NUNCA texto plano)
    rol             rol_global   NOT NULL DEFAULT 'residente',
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,    -- baja lógica del usuario
    biometria_activa BOOLEAN     NOT NULL DEFAULT FALSE,   -- el usuario habilitó huella/Face ID
    ultimo_acceso   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Credenciales WebAuthn / Passkeys (huella digital, Face ID).
-- IMPORTANTE: la biometría NUNCA llega al servidor. El dispositivo guarda
-- la llave privada; aquí solo almacenamos la llave PÚBLICA y metadatos.
-- Un usuario puede registrar varios dispositivos (su teléfono, su tablet).
CREATE TABLE credenciales_webauthn (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      BIGINT      NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    credential_id   TEXT        NOT NULL UNIQUE,           -- identificador de la credencial (base64)
    public_key      TEXT        NOT NULL,                  -- llave pública del autenticador
    sign_count      BIGINT      NOT NULL DEFAULT 0,        -- contador anti-clonación
    dispositivo     VARCHAR(120),                          -- "iPhone de Arturo", "Tablet caseta 1"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- 2. ESTRUCTURA RESIDENCIAL: EDIFICIOS, CASAS, APARTAMENTOS
-- =====================================================================

-- Catálogo de tarifas de mantenimiento (3 configurables desde panel admin).
CREATE TABLE tarifas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          VARCHAR(80)  NOT NULL,                 -- "Tarifa A", "Tarifa Premium"
    monto           NUMERIC(10,2) NOT NULL,
    descripcion     VARCHAR(255),
    activa          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Tipo de unidad raíz.
--   casa     → unidad familiar individual: paga cuota, tiene titular.
--   edificio → CONTENEDOR de apartamentos: NO paga cuota propia, solo agrupa.
CREATE TYPE tipo_unidad AS ENUM ('casa', 'edificio');

-- UNIDADES = entidad raíz. Una casa o un edificio.
CREATE TABLE unidades (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    tipo            tipo_unidad  NOT NULL,
    identificador   VARCHAR(60)  NOT NULL,                 -- "Casa 24", "Edificio 1"
    direccion_ref   VARCHAR(160),                          -- referencia interna (bloque, sector)
    activa          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (identificador)
);

-- CUENTAS = la entidad que realmente PAGA y genera QR.
--   * Si la unidad es una casa  → 1 cuenta vinculada directamente a la casa.
--   * Si la unidad es edificio  → N cuentas (una por apartamento: 1A, 1B...).
-- Cada cuenta tiene su propio titular, su tarifa, su día de pago y su mora.
CREATE TABLE cuentas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    unidad_id       BIGINT      NOT NULL REFERENCES unidades(id),
    apartamento     VARCHAR(40),                           -- NULL si es casa; "1A","2B" si es apto
    tarifa_id       BIGINT      NOT NULL REFERENCES tarifas(id),
    dia_pago        SMALLINT    NOT NULL CHECK (dia_pago BETWEEN 1 AND 28),
                                -- día del mes en que vence la cuota (autollenado al alta, modificable)
    fecha_alta      DATE        NOT NULL DEFAULT CURRENT_DATE,
    estado          VARCHAR(20) NOT NULL DEFAULT 'al_dia',
                                -- 'al_dia' | 'por_vencer' | 'vencida' | 'en_mora'(bloqueada)
    bloqueada       BOOLEAN     NOT NULL DEFAULT FALSE,     -- TRUE = mora >= 3 días: bloquea acceso y QR
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (unidad_id, apartamento)
);

-- =====================================================================
-- 3. RESIDENTES (vínculo usuario ↔ cuenta)
-- =====================================================================

-- Rol dentro de la casa/apartamento (distinto del rol global).
--   titular → encargado de la cuenta: ve estado de cuenta, paga, genera QR,
--             gestiona miembros y tarjetas.
--   miembro → familiar/inquilino: genera QR y ve SU historial de visitas,
--             NO ve ni toca pagos.
CREATE TYPE rol_en_cuenta AS ENUM ('titular', 'miembro');

CREATE TABLE residentes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    usuario_id      BIGINT      NOT NULL REFERENCES usuarios(id),
    cuenta_id       BIGINT      NOT NULL REFERENCES cuentas(id),
    rol_cuenta      rol_en_cuenta NOT NULL DEFAULT 'miembro',
    relacion        VARCHAR(60),                           -- "propietario","inquilino","hijo","esposa"
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,      -- baja lógica (ej. inquilino que se va)
    fecha_ingreso   DATE        NOT NULL DEFAULT CURRENT_DATE,
    fecha_baja      DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (usuario_id, cuenta_id)
);

-- Garantiza un solo titular activo por cuenta.
CREATE UNIQUE INDEX uq_titular_por_cuenta
    ON residentes (cuenta_id)
    WHERE rol_cuenta = 'titular' AND activo = TRUE;

-- =====================================================================
-- 4. TARJETAS DE PROXIMIDAD (una casa puede tener varias)
-- =====================================================================

CREATE TYPE estado_tarjeta AS ENUM ('activa', 'bloqueada', 'extraviada', 'baja');

CREATE TABLE tarjetas_proximidad (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    card_uid        VARCHAR(64)  NOT NULL UNIQUE,           -- UID físico del chip RFID
    cuenta_id       BIGINT       NOT NULL REFERENCES cuentas(id),
    residente_id    BIGINT       REFERENCES residentes(id),  -- a qué persona se asignó (puede ser NULL temporal)
    etiqueta        VARCHAR(80),                            -- "Tarjeta principal","Auto 2","Empleada"
    estado          estado_tarjeta NOT NULL DEFAULT 'activa',
    fecha_asignacion DATE        NOT NULL DEFAULT CURRENT_DATE,
    fecha_baja      DATE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- 5. ACCESOS FÍSICOS Y DISPOSITIVOS (Raspberry Pi, lectores, relés)
-- =====================================================================

CREATE TYPE tipo_acceso AS ENUM ('vehicular', 'peatonal');

-- Los 4 puntos de acceso de la residencial.
CREATE TABLE accesos_fisicos (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          VARCHAR(80)  NOT NULL,                  -- "Entrada Principal Vehicular"
    tipo            tipo_acceso  NOT NULL,
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Dispositivos físicos en cada acceso (Raspberry Pi, lector QR, lector RFID, relé).
-- El campo último_latido permite saber si el dispositivo está en línea.
CREATE TABLE dispositivos (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acceso_id       BIGINT       NOT NULL REFERENCES accesos_fisicos(id),
    tipo            VARCHAR(40)  NOT NULL,                  -- "raspberry","lector_qr","lector_rfid","rele"
    identificador   VARCHAR(80)  NOT NULL UNIQUE,           -- serial / hostname
    modelo          VARCHAR(80),                            -- "ZKTeco CMP300","Skylink 4500","SK-TX1000HD"
    en_linea        BOOLEAN      NOT NULL DEFAULT FALSE,
    ultimo_latido   TIMESTAMPTZ,                            -- heartbeat para detectar caída de conexión
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- 6. VISITAS Y CÓDIGOS QR
-- =====================================================================

-- Tres modalidades, presentadas como 3 cards al residente.
CREATE TYPE tipo_visita AS ENUM ('unica', 'recurrente', 'repartidor');

-- Para visita recurrente: cómo se permite el uso del QR.
--   libre        → entra y sale las veces que quiera durante la vigencia.
--   una_por_dia  → una entrada y una salida por día.
CREATE TYPE modo_recurrencia AS ENUM ('libre', 'una_por_dia');

CREATE TABLE visitas (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    cuenta_id           BIGINT      NOT NULL REFERENCES cuentas(id),
    generada_por        BIGINT      NOT NULL REFERENCES residentes(id), -- quién creó el QR (trazabilidad)
    tipo                tipo_visita NOT NULL,

    -- Datos del visitante (todos los necesarios para que el guardia lo identifique)
    nombre_visitante    VARCHAR(160) NOT NULL,
    documento_id        VARCHAR(40),                        -- cédula / identidad declarada
    telefono            VARCHAR(30),
    empresa             VARCHAR(120),                        -- para repartidor: "PedidosYa","Uber Eats"
    placa_vehiculo      VARCHAR(20),                         -- si viene en carro
    en_vehiculo         BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Vigencia
    valido_desde        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valido_hasta        TIMESTAMPTZ,                         -- recurrente: fecha fin; única: fin del día
    modo_recurrencia    modo_recurrencia,                    -- solo aplica si tipo='recurrente'

    estado              VARCHAR(20) NOT NULL DEFAULT 'activa', -- 'activa'|'usada'|'expirada'|'revocada'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Código QR concreto asociado a una visita. Token firmado y único.
CREATE TABLE codigos_qr (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    visita_id       BIGINT      NOT NULL REFERENCES visitas(id) ON DELETE CASCADE,
    token           UUID        NOT NULL DEFAULT gen_random_uuid() UNIQUE, -- lo que codifica el QR
    usos            INT         NOT NULL DEFAULT 0,         -- cuántas veces se ha escaneado
    revocado        BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- 7. EVENTOS DE ACCESO (la bitácora digital — reemplaza la física)
-- =====================================================================

CREATE TYPE direccion_acceso AS ENUM ('entrada', 'salida');

-- Quién originó el evento.
--   residente → pasó tarjeta de proximidad.
--   visita    → el guardia validó un QR y dio acceso.
CREATE TYPE origen_evento AS ENUM ('residente', 'visita');

CREATE TABLE eventos_acceso (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    origen          origen_evento NOT NULL,
    direccion       direccion_acceso NOT NULL,
    acceso_id       BIGINT      NOT NULL REFERENCES accesos_fisicos(id),

    -- Si fue un residente con tarjeta:
    tarjeta_id      BIGINT      REFERENCES tarjetas_proximidad(id),
    residente_id    BIGINT      REFERENCES residentes(id),

    -- Si fue una visita validada por guardia:
    visita_id       BIGINT      REFERENCES visitas(id),
    guardia_id      BIGINT      REFERENCES usuarios(id),    -- qué guardia autorizó (trazabilidad)
    foto_identidad  VARCHAR(255),                           -- ruta del archivo en /uploads
    foto_placa      VARCHAR(255),

    en_vehiculo     BOOLEAN     NOT NULL DEFAULT FALSE,
    placa_vehiculo  VARCHAR(20),
    ocurrido_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- offline-first: si la Raspberry registró sin conexión, se sincroniza luego
    sincronizado    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_eventos_ocurrido ON eventos_acceso (ocurrido_en DESC);
CREATE INDEX idx_eventos_visita   ON eventos_acceso (visita_id);

-- =====================================================================
-- 8. CUOTAS Y PAGOS
-- =====================================================================

-- Una cuota por cuenta por mes. Se generan en lote según el dia_pago de cada cuenta.
CREATE TABLE cuotas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    cuenta_id       BIGINT      NOT NULL REFERENCES cuentas(id),
    periodo         DATE        NOT NULL,                   -- primer día del mes que cubre (2026-06-01)
    monto           NUMERIC(10,2) NOT NULL,                 -- copiado de la tarifa al generar
    fecha_vencimiento DATE      NOT NULL,
    estado          VARCHAR(20) NOT NULL DEFAULT 'pendiente', -- 'pendiente'|'pagada'|'vencida'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cuenta_id, periodo)
);

CREATE TYPE metodo_pago AS ENUM ('transferencia', 'pasarela');  -- pasarela = "disponible más adelante"
CREATE TYPE estado_pago AS ENUM ('en_revision', 'aprobado', 'rechazado');

-- Pago que sube el residente. El admin lo revisa y aprueba.
CREATE TABLE pagos (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid(),
    cuota_id            BIGINT      NOT NULL REFERENCES cuotas(id),
    cuenta_id           BIGINT      NOT NULL REFERENCES cuentas(id),
    subido_por          BIGINT      NOT NULL REFERENCES usuarios(id),  -- el titular
    metodo              metodo_pago NOT NULL DEFAULT 'transferencia',
    monto               NUMERIC(10,2) NOT NULL,
    comprobante_archivo VARCHAR(255),                       -- ruta del comprobante en /uploads
    referencia          VARCHAR(120),                       -- nº de transferencia declarado
    estado              estado_pago NOT NULL DEFAULT 'en_revision',
    revisado_por        BIGINT      REFERENCES usuarios(id),  -- qué admin aprobó/rechazó
    revisado_en         TIMESTAMPTZ,
    nota_admin          VARCHAR(255),                        -- motivo de rechazo, observaciones
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- 9. NOTIFICACIONES
-- =====================================================================

-- Tipos: visita_entro, visita_salio, pago_por_vencer, pago_vence_hoy,
--        pago_atrasado, acceso_bloqueado, pago_aprobado, pago_rechazado.
CREATE TABLE notificaciones (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      BIGINT      NOT NULL REFERENCES usuarios(id),
    tipo            VARCHAR(40)  NOT NULL,
    titulo          VARCHAR(160) NOT NULL,
    mensaje         TEXT         NOT NULL,
    leida           BOOLEAN      NOT NULL DEFAULT FALSE,
    enviada_email   BOOLEAN      NOT NULL DEFAULT FALSE,    -- si ya se mandó vía Resend
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notif_usuario ON notificaciones (usuario_id, leida);

-- =====================================================================
-- 10. AUDITORÍA (acciones sensibles del admin/guardia)
-- =====================================================================

CREATE TABLE auditoria (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      BIGINT      REFERENCES usuarios(id),
    accion          VARCHAR(80) NOT NULL,                   -- "aprobo_pago","bloqueo_cuenta","creo_casa"
    entidad         VARCHAR(60),                            -- tabla afectada
    entidad_id      BIGINT,
    detalle         JSONB,                                  -- snapshot del cambio
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- FIN DEL ESQUEMA
-- =====================================================================
