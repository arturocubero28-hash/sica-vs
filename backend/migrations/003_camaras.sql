-- 003_camaras.sql — Módulo de cámaras ONVIF/RTSP

CREATE TABLE IF NOT EXISTS camaras (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    nombre          VARCHAR(100) NOT NULL,                 -- "Entrada Principal"
    ip              VARCHAR(45)  NOT NULL,                 -- 192.168.1.50
    puerto_rtsp     INTEGER      NOT NULL DEFAULT 554,
    puerto_onvif    INTEGER      NOT NULL DEFAULT 80,
    usuario         VARCHAR(60),
    password        VARCHAR(120),
    ruta_stream     VARCHAR(200) DEFAULT '/Streaming/Channels/101',  -- path RTSP típico Hikvision
    acceso_id       BIGINT       REFERENCES accesos_fisicos(id),
    activa          BOOLEAN      NOT NULL DEFAULT TRUE,
    orden           INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_camaras_activa ON camaras(activa);
CREATE INDEX IF NOT EXISTS idx_camaras_orden  ON camaras(orden);
