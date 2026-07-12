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
