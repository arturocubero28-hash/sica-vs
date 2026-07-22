-- =====================================================================
-- PI-ISO-14 (Auditoria Dia 39) — Limpieza de trancas huerfanas
--
-- Las trancas 1-4 se crearon antes del modelo multi-residencial (Dia 37)
-- y quedaron sin punto de acceso asignado. Con la politica estricta de
-- aislamiento por punto, ya no validan nada.
--
-- Criterio (coherente con AUDIT-12, "nunca destruir evidencia"):
--   - Tranca CON eventos historicos -> baja logica (activo = false)
--   - Tranca SIN eventos            -> DELETE limpio
--
-- Estado al momento de escribir esto (segun diagnostico_pi_iso_14.sql):
--   id 1  Entrada Principal Vehicular      14 eventos -> baja logica
--   id 2  Entrada Secundaria Vehicular      0 eventos -> DELETE
--   id 3  Torniquete Peatonal Principal     0 eventos -> DELETE
--   id 4  Torniquete Peatonal Secundario    0 eventos -> DELETE
--
-- El script NO usa esos ids a mano: decide por la cuenta real de eventos
-- en el momento de ejecutarse, para que sea seguro aunque algo haya
-- cambiado desde el diagnostico.
--
-- Uso (PowerShell):
--   docker compose cp backend\migrations\limpieza_pi_iso_14.sql db:/tmp/limpieza.sql
--   docker compose exec db psql -U sicavs -d sicavs -f /tmp/limpieza.sql
-- =====================================================================

BEGIN;

\echo '=== ANTES: trancas sin punto de acceso ==='
SELECT a.id, a.nombre, a.activo, COUNT(e.id) AS eventos
FROM accesos_fisicos a
LEFT JOIN eventos_acceso e ON e.acceso_id = a.id
WHERE a.punto_acceso IS NULL OR a.punto_acceso = ''
GROUP BY a.id, a.nombre, a.activo
ORDER BY a.id;

-- ---------------------------------------------------------------------
-- 1. BAJA LOGICA: trancas huerfanas QUE TIENEN eventos.
--    No se borran nunca: sus eventos son historial de accesos y
--    eliminarlos destruiria evidencia (mismo criterio que AUDIT-12).
--    Se marcan inactivas y se les pone un punto que deja claro que
--    son historicas, para que no vuelvan a aparecer como "sin punto".
-- ---------------------------------------------------------------------
UPDATE accesos_fisicos a
SET activo = false,
    punto_acceso = 'HISTORICO (pre-multiresidencial)'
WHERE (a.punto_acceso IS NULL OR a.punto_acceso = '')
  AND EXISTS (SELECT 1 FROM eventos_acceso e WHERE e.acceso_id = a.id);

\echo ''
\echo '=== Trancas dadas de baja logica (conservan su historial) ==='
SELECT id, nombre, activo, punto_acceso
FROM accesos_fisicos
WHERE punto_acceso = 'HISTORICO (pre-multiresidencial)'
ORDER BY id;

-- ---------------------------------------------------------------------
-- 2. DELETE: trancas huerfanas SIN ningun evento.
--    No hay nada que preservar, se eliminan limpio.
-- ---------------------------------------------------------------------
DELETE FROM accesos_fisicos a
WHERE (a.punto_acceso IS NULL OR a.punto_acceso = '')
  AND NOT EXISTS (SELECT 1 FROM eventos_acceso e WHERE e.acceso_id = a.id);

\echo ''
\echo '=== DESPUES: no debe quedar ninguna tranca activa sin punto ==='
SELECT COUNT(*) AS trancas_activas_sin_punto
FROM accesos_fisicos
WHERE activo = true
  AND (punto_acceso IS NULL OR punto_acceso = '');

\echo ''
\echo '=== Estado final de puntos de acceso ==='
SELECT punto_acceso,
       COUNT(*) FILTER (WHERE activo)     AS trancas_activas,
       COUNT(*) FILTER (WHERE NOT activo) AS trancas_inactivas,
       SUM(CASE WHEN direccion = 'entrada' AND activo THEN 1 ELSE 0 END) AS entradas,
       SUM(CASE WHEN direccion = 'salida'  AND activo THEN 1 ELSE 0 END) AS salidas
FROM accesos_fisicos
GROUP BY punto_acceso
ORDER BY punto_acceso;

-- Revisa la salida antes de confirmar.
-- Si algo no cuadra:  ROLLBACK;
COMMIT;
