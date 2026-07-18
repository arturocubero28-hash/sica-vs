-- Solicitudes de baja (admin de edificio pide dar de baja a un inquilino)
CREATE TABLE IF NOT EXISTS solicitudes_baja (
    id BIGSERIAL PRIMARY KEY,
    uuid_publico UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    cuenta_id BIGINT NOT NULL REFERENCES cuentas(id),
    solicitada_por BIGINT NOT NULL REFERENCES usuarios(id),
    motivo TEXT NOT NULL,
    fecha_desocupacion DATE NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    respuesta_admin TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resuelto_en TIMESTAMPTZ
);

-- Nivelación de saldo idempotente: guardar el monto pleno antes de nivelar
ALTER TABLE cuotas ADD COLUMN IF NOT EXISTS monto_original NUMERIC(10,2);
ALTER TABLE cuotas ADD COLUMN IF NOT EXISTS nivelada BOOLEAN NOT NULL DEFAULT false;

-- Tarjetas virtuales (QR permanente que rota cada 24h para acceso sin guardia)
CREATE TABLE IF NOT EXISTS tarjetas_virtuales (
    id             BIGSERIAL PRIMARY KEY,
    uuid_publico   UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    cuenta_id      BIGINT NOT NULL REFERENCES cuentas(id) UNIQUE,
    residente_id   BIGINT NOT NULL REFERENCES residentes(id),
    codigo_hoy     VARCHAR(20) NOT NULL UNIQUE,
    codigo_anterior VARCHAR(20),
    estado         VARCHAR(20) NOT NULL DEFAULT 'activa',
    tipo_acceso    VARCHAR(20) NOT NULL DEFAULT 'peatonal',
    rotado_en      TIMESTAMPTZ DEFAULT now(),
    created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tarjetas_virtuales_codigo_hoy ON tarjetas_virtuales(codigo_hoy);
CREATE INDEX IF NOT EXISTS idx_tarjetas_virtuales_codigo_anterior ON tarjetas_virtuales(codigo_anterior);

-- Credenciales BLE (acceso por Bluetooth, atado al dispositivo)
CREATE TABLE IF NOT EXISTS credenciales_ble (
    id             BIGSERIAL PRIMARY KEY,
    uuid_publico   UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    cuenta_id      BIGINT NOT NULL REFERENCES cuentas(id),
    residente_id   BIGINT NOT NULL REFERENCES residentes(id),
    device_id      VARCHAR(128) NOT NULL,
    device_nombre  VARCHAR(120),
    token_hoy      VARCHAR(32) NOT NULL UNIQUE,
    token_anterior VARCHAR(32),
    clave_secreta  VARCHAR(64) NOT NULL,
    contador       BIGINT NOT NULL DEFAULT 0,
    estado         VARCHAR(20) NOT NULL DEFAULT 'activa',
    tipo_acceso    VARCHAR(20) NOT NULL DEFAULT 'peatonal',
    rotado_en      TIMESTAMPTZ DEFAULT now(),
    ultimo_uso     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_credenciales_ble_token_hoy ON credenciales_ble(token_hoy);
CREATE INDEX IF NOT EXISTS idx_credenciales_ble_residente ON credenciales_ble(residente_id);

-- Tipo de acceso que el admin autoriza para credenciales virtuales (QR/BLE)
-- de cada cuenta. Mismo concepto que el tipo_acceso de las tarjetas físicas.
ALTER TABLE cuentas ADD COLUMN IF NOT EXISTS tipo_acceso_virtual VARCHAR(20) NOT NULL DEFAULT 'peatonal';

-- PAY-11: defensa de segunda capa contra recibos duplicados. El correlativo
-- ahora se genera con un UPDATE atómico (ver ConfigRecibo.siguiente_correlativo),
-- pero un índice único parcial (solo cuando numero_recibo no es NULL) asegura
-- que la base de datos rechace cualquier duplicado que se colara por otra vía.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pagos_numero_recibo_unico
    ON pagos (numero_recibo) WHERE numero_recibo IS NOT NULL;

-- ACCESS-04: separar la placa que el residente declaró al crear la visita
-- (placa_vehiculo, ya existía) de la que el guardia observa físicamente
-- al momento del acceso. Antes el backend ignoraba la que digitaba el
-- guardia y siempre guardaba la declarada.
ALTER TABLE eventos_acceso ADD COLUMN IF NOT EXISTS placa_observada VARCHAR(20);

-- ACCESS-04: el guardia elige en qué punto de acceso está trabajando este
-- turno (queda fijo, normalmente un teléfono por punto). Se usa para
-- registrar correctamente por cuál punto entró/salió cada visita, en vez
-- de asumir siempre el mismo punto por defecto.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS punto_acceso_actual VARCHAR(80);

-- ACCESS-04: aperturas manuales de tranca sin visita asociada (el guardia
-- deja salir a alguien que vio, emergencias, etc.) Exige confirmación en
-- la app y queda auditado por separado de los eventos de visita normales.
CREATE TABLE IF NOT EXISTS aperturas_manuales (
    id             BIGSERIAL PRIMARY KEY,
    uuid_publico   UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    acceso_id      BIGINT NOT NULL REFERENCES accesos_fisicos(id),
    guardia_id     BIGINT NOT NULL REFERENCES usuarios(id),
    motivo         VARCHAR(255),
    ocurrido_en    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_aperturas_manuales_guardia ON aperturas_manuales(guardia_id);
CREATE INDEX IF NOT EXISTS idx_aperturas_manuales_acceso ON aperturas_manuales(acceso_id);

-- Múltiples comprobantes por pago (el residente puede subir varias fotos
-- para el mismo pago, ej. depositó en dos partes). El admin las revisa
-- juntas y aprueba/rechaza el pago completo, no cada imagen por separado.
CREATE TABLE IF NOT EXISTS comprobantes_pago (
    id           BIGSERIAL PRIMARY KEY,
    uuid_publico UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    pago_id      BIGINT NOT NULL REFERENCES pagos(id) ON DELETE CASCADE,
    archivo      VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comprobantes_pago_pago_id ON comprobantes_pago(pago_id);

-- DEVICE-06: el token de cada Raspberry Pi se guarda como HASH (SHA-256),
-- nunca en texto plano. Se renombra la columna y se agrega dispositivo_id
-- a eventos_acceso para saber qué Pi generó cada evento de residente.
--
-- ADVERTENCIA IMPORTANTE si ya hay dispositivos creados en producción:
-- este ALTER TABLE renombra la columna pero NO puede hashear
-- retroactivamente tokens ya existentes (el hash es de un solo sentido).
-- Cualquier dispositivo creado ANTES de esta migración debe REGENERAR
-- su token desde el panel de desarrollador después de aplicarla — el
-- token viejo dejará de servir porque token_hash quedará con el valor
-- en claro viejo, que no coincidirá con ningún hash real generado por
-- el backend nuevo.
ALTER TABLE dispositivos_pi RENAME COLUMN token TO token_hash;

ALTER TABLE eventos_acceso ADD COLUMN IF NOT EXISTS dispositivo_id BIGINT
    REFERENCES dispositivos_pi(id);
