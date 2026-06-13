-- =====================================================================
-- SICA-VS — Datos de prueba (seed)
-- Se carga automáticamente la primera vez que arranca la base de datos.
--
-- ⚠️  ADVERTENCIA DE SEGURIDAD — SOLO PARA DESARROLLO  ⚠️
-- Este archivo contiene usuarios con contraseñas conocidas (admin123).
-- NUNCA debe cargarse en un despliegue de producción.
-- Al desplegar a producción:
--   1. NO ejecutar este seed.
--   2. Crear el super_admin con una contraseña fuerte y única.
--   3. Marcarlo con debe_cambiar_password=TRUE para forzar el cambio
--      en el primer inicio de sesión.
-- El backend además se niega a arrancar en producción con secretos de
-- desarrollo (ver validar_config_produccion en config.py).
-- =====================================================================

-- Usuario administrador de prueba [DESARROLLO]
--   email:    admin@villasdelsol.hn
--   password: admin123
INSERT INTO usuarios (uuid_publico, nombre, apellido, email, telefono, password_hash, rol, activo)
VALUES (
    gen_random_uuid(),
    'Administrador', 'Villas del Sol',
    'admin@villasdelsol.hn', '50400000000',
    '$2b$12$.aD382fZtNj8RnhPKFWG.ebaopPsxjLEvUhEx9XPEafg45TkuEpa.',
    'admin', TRUE
);

-- Usuario guardia de prueba (password: admin123)
INSERT INTO usuarios (uuid_publico, nombre, apellido, email, telefono, password_hash, rol, activo)
VALUES (
    gen_random_uuid(),
    'Guardia', 'Caseta 1',
    'guardia1@villasdelsol.hn', '50400000001',
    '$2b$12$.aD382fZtNj8RnhPKFWG.ebaopPsxjLEvUhEx9XPEafg45TkuEpa.',
    'guardia', TRUE
);

-- Tres tarifas configurables
INSERT INTO tarifas (nombre, monto, descripcion, activa) VALUES
  ('Tarifa A - Estándar', 800.00, 'Casa o apartamento estándar', TRUE),
  ('Tarifa B - Premium',  1200.00, 'Vivienda de mayor tamaño', TRUE),
  ('Tarifa C - Reducida', 500.00, 'Apartamento pequeño', TRUE);

-- Los 4 accesos físicos
INSERT INTO accesos_fisicos (nombre, tipo, activo) VALUES
  ('Entrada Principal Vehicular', 'vehicular', TRUE),
  ('Entrada Secundaria Vehicular', 'vehicular', TRUE),
  ('Torniquete Peatonal Principal', 'peatonal', TRUE),
  ('Torniquete Peatonal Secundario', 'peatonal', TRUE);
