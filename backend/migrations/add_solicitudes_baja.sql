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
