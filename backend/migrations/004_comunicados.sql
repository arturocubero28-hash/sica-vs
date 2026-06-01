-- 004_comunicados.sql — Comunicados / anuncios para residentes

CREATE TABLE IF NOT EXISTS comunicados (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid_publico    UUID         NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    titulo          VARCHAR(160) NOT NULL,
    cuerpo          TEXT         NOT NULL,
    imagen          VARCHAR(255),
    creado_por      BIGINT       REFERENCES usuarios(id),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comunicados_fecha ON comunicados(created_at DESC);
