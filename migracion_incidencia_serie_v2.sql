-- =============================================================================
-- migracion_incidencia_serie_v2.sql  ·  Documento 35 de Pólaris, §3 (aprobado por el propietario el 10/11/2026)
-- Registro de las barras diarias que la fuente publica sin cierre (tipo barra_sin_cierre).
--
-- Condiciones aprobadas:
--   · una sola fila por ticker y fecha de sesión, no una por consulta;
--   · la fila se cierra, con su fecha de resolución, cuando la fuente publica la barra completa;
--   · sin cambios en las filas existentes (la de COL.MC, tipo serie_no_ajustada_ath);
--   · migración aditiva y reversible.
--
-- Cambios:
--   1. Dos columnas nuevas y opcionales: fecha_sesion (date) y resuelta_en (timestamptz). Las filas existentes
--      quedan con NULL en ambas: sus valores no cambian.
--   2. La unicidad (ticker, tipo) pasa a ser un índice único PARCIAL para las filas sin fecha (las de siempre),
--      y se añade otro índice único parcial (ticker, tipo, fecha_sesion) para las filas con fecha.
--      Para las filas existentes la regla es la misma: una por ticker y tipo.
--
-- Orden de despliegue: ejecutar esta migración en Neon ANTES del push. El código nuevo también funciona sin
-- ella (no registra las barras y deja la app igual), pero el registro solo empieza tras ejecutarla.
-- Idempotente: se puede ejecutar varias veces. Reversión al final (DOWN). Sin credenciales.
-- =============================================================================

-- ── UP ───────────────────────────────────────────────────────────────────────
BEGIN;

ALTER TABLE incidencia_serie ADD COLUMN IF NOT EXISTS fecha_sesion date;
ALTER TABLE incidencia_serie ADD COLUMN IF NOT EXISTS resuelta_en  timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_incidencia_serie_sin_fecha
    ON incidencia_serie (ticker, tipo) WHERE fecha_sesion IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_incidencia_serie_con_fecha
    ON incidencia_serie (ticker, tipo, fecha_sesion) WHERE fecha_sesion IS NOT NULL;

ALTER TABLE incidencia_serie DROP CONSTRAINT IF EXISTS uq_incidencia_serie;

COMMENT ON COLUMN incidencia_serie.fecha_sesion IS
  'Fecha de la sesión afectada, en los tipos que van por sesión (barra_sin_cierre). NULL en los demás.';
COMMENT ON COLUMN incidencia_serie.resuelta_en IS
  'barra_sin_cierre: momento en que la app vio la barra ya completa (la fila pasa a activa = false).';
COMMENT ON COLUMN incidencia_serie.tipo IS
  'serie_no_ajustada_ath: el tramo antiguo de la serie de Yahoo no está ajustado por operaciones de capital y el '
  'máximo histórico usa la ventana de 15 años · barra_sin_cierre: la barra diaria de una sesión ya cerrada llegó '
  'sin cierre (Close vacío) y los cálculos usaron la sesión anterior';

COMMIT;

-- ── Comprobación ─────────────────────────────────────────────────────────────
-- SELECT ticker, tipo, fecha_sesion, activa, primera_vez, ultima_vez, resuelta_en
--   FROM incidencia_serie ORDER BY ultima_vez DESC;
-- Frecuencia por valor:
-- SELECT ticker, count(*) AS barras, max(fecha_sesion) AS ultima
--   FROM incidencia_serie WHERE tipo = 'barra_sin_cierre' GROUP BY ticker ORDER BY barras DESC;

-- ── DOWN (reversión completa; solo si se decide deshacer) ────────────────────
-- Las filas barra_sin_cierre se archivan antes de borrarlas, porque la restricción original (ticker, tipo)
-- no admite varias fechas del mismo ticker. Las filas anteriores (COL.MC) no se tocan.
-- BEGIN;
-- CREATE TABLE IF NOT EXISTS incidencia_serie_barras_archivo AS
--   SELECT * FROM incidencia_serie WHERE fecha_sesion IS NOT NULL;
-- DELETE FROM incidencia_serie WHERE fecha_sesion IS NOT NULL;
-- DROP INDEX IF EXISTS uq_incidencia_serie_con_fecha;
-- DROP INDEX IF EXISTS uq_incidencia_serie_sin_fecha;
-- ALTER TABLE incidencia_serie ADD CONSTRAINT uq_incidencia_serie UNIQUE (ticker, tipo);
-- ALTER TABLE incidencia_serie DROP COLUMN IF EXISTS resuelta_en;
-- ALTER TABLE incidencia_serie DROP COLUMN IF EXISTS fecha_sesion;
-- COMMIT;
