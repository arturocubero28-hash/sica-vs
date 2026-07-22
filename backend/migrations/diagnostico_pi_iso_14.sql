-- =====================================================================
-- PI-ISO-14 (Auditoría Día 39) — Diagnóstico previo
--
-- Ejecutar ANTES de aplicar el fix, para saber exactamente qué queda
-- fuera con la política estricta de aislamiento por punto de acceso.
--
-- Uso (PowerShell):
--   docker compose exec -T db psql -U sicavs -d sicavs < backend/migrations/diagnostico_pi_iso_14.sql
-- =====================================================================

\echo '=== 1. TRANCAS SIN PUNTO DE ACCESO (dejan de funcionar) ==='
SELECT id,
       nombre,
       tipo,
       direccion,
       activo,
       relay_pin,
       punto_acceso,
       residencial_id
FROM accesos_fisicos
WHERE punto_acceso IS NULL OR punto_acceso = ''
ORDER BY id;

\echo ''
\echo '=== 2. TRANCAS CON EVENTOS REGISTRADOS (NO borrar: baja logica) ==='
-- Si una tranca huerfana tiene eventos, borrarla destruye evidencia
-- historica. En ese caso hay que desactivarla (activo=false) y crear
-- la nueva, no hacer DELETE.
SELECT a.id,
       a.nombre,
       a.punto_acceso,
       COUNT(e.id) AS eventos
FROM accesos_fisicos a
LEFT JOIN eventos_acceso e ON e.acceso_id = a.id
WHERE a.punto_acceso IS NULL OR a.punto_acceso = ''
GROUP BY a.id, a.nombre, a.punto_acceso
ORDER BY eventos DESC, a.id;

\echo ''
\echo '=== 3. DISPOSITIVOS PI SIN PUNTO (dejan de sincronizar) ==='
SELECT id,
       nombre,
       tipo,
       punto_acceso,
       activo,
       residencial_id,
       ultima_sync
FROM dispositivos_pi
WHERE tipo = 'acceso'
  AND (punto_acceso IS NULL OR punto_acceso = '')
ORDER BY id;

\echo ''
\echo '=== 4. PUNTOS DE ACCESO EN USO (referencia para reasignar) ==='
-- Los nombres de punto que ya existen y funcionan bien. Al recrear las
-- trancas hay que usar exactamente uno de estos (o crear uno nuevo y
-- asignarlo tambien a su Pi correspondiente).
SELECT punto_acceso,
       COUNT(*) AS trancas,
       SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END) AS entradas,
       SUM(CASE WHEN direccion = 'salida'  THEN 1 ELSE 0 END) AS salidas
FROM accesos_fisicos
WHERE punto_acceso IS NOT NULL AND punto_acceso <> ''
GROUP BY punto_acceso
ORDER BY punto_acceso;

\echo ''
\echo '=== 5. COHERENCIA Pi <-> TRANCAS (puntos que no coinciden) ==='
-- Una Pi cuyo punto_acceso no corresponde a ninguna tranca existente
-- va a sincronizar una lista vacia. Deberia dar 0 filas.
SELECT d.id   AS pi_id,
       d.nombre AS pi_nombre,
       d.punto_acceso AS pi_punto,
       (SELECT COUNT(*) FROM accesos_fisicos a
         WHERE a.punto_acceso = d.punto_acceso AND a.activo) AS trancas_de_su_punto
FROM dispositivos_pi d
WHERE d.tipo = 'acceso'
  AND d.punto_acceso IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM accesos_fisicos a
      WHERE a.punto_acceso = d.punto_acceso AND a.activo
  )
ORDER BY d.id;
