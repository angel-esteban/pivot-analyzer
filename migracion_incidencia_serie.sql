-- =============================================================================
-- migracion_incidencia_serie.sql  ·  APROBADA por el propietario el 08/11/2026
-- Documentos 25-27 de Pólaris: registro de la guarda de series de precios no ajustadas.
--
-- Cuando el máximo de toda la serie diaria de Yahoo supera más de 20 veces el máximo de
-- los últimos 15 años (caso COL.MC), el máximo histórico usa solo la ventana de 15 años.
-- Cada activación se registra aquí, con el ticker y el ratio. Si Yahoo corrige la serie,
-- la fila pasa a activa = false.
--
-- Diseño: tabla NUEVA e independiente. No se usa `incidencias` de instrumento/fundamental,
-- que está ligada a `valido` y marcaría como sospechosos los fundamentales del valor.
-- Sin clave ajena a instrumento: el Análisis Técnico admite tickers fuera del screener.
-- Impacto sobre datos existentes: NINGUNO.
--
-- Idempotente: se puede ejecutar varias veces. Reversión al final (DOWN).
-- Ejecutar en Neon › SQL Editor (no contiene credenciales).
-- =============================================================================

-- ── UP ───────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidencia_serie (
    id           bigserial   PRIMARY KEY,
    ticker       text        NOT NULL,
    tipo         text        NOT NULL,
    detalle      jsonb,
    primera_vez  timestamptz NOT NULL DEFAULT now(),
    ultima_vez   timestamptz NOT NULL DEFAULT now(),
    activa       boolean     NOT NULL DEFAULT true,
    CONSTRAINT uq_incidencia_serie UNIQUE (ticker, tipo)
);

COMMENT ON TABLE incidencia_serie IS
  'Incidencias de calidad de las series de precios (no de los fundamentales). Una fila por ticker y '
  'tipo: se actualiza en cada detección y se desactiva cuando deja de darse.';
COMMENT ON COLUMN incidencia_serie.tipo IS
  'serie_no_ajustada_ath: el tramo antiguo de la serie de Yahoo no está ajustado por operaciones de '
  'capital y el máximo histórico usa la ventana de 15 años';
COMMENT ON COLUMN incidencia_serie.detalle IS
  'jsonb con ratio, max_total, fecha_max_total, max_ventana, ventana_desde y umbral';
COMMENT ON COLUMN incidencia_serie.primera_vez IS 'Primera detección (no cambia al reactivarse)';
COMMENT ON COLUMN incidencia_serie.ultima_vez IS 'Última detección o desactivación';
COMMENT ON COLUMN incidencia_serie.activa IS 'false = la última comprobación ya no la detecta';

CREATE INDEX IF NOT EXISTS ix_incidencia_serie_activa
    ON incidencia_serie (tipo, ticker) WHERE activa;

-- ── Comprobación ─────────────────────────────────────────────────────────────
-- SELECT ticker, tipo, activa, detalle->>'ratio' AS ratio, primera_vez, ultima_vez
--   FROM incidencia_serie ORDER BY ultima_vez DESC;

-- ── DOWN (reversión completa; solo si se decide deshacer) ────────────────────
-- DROP TABLE IF EXISTS incidencia_serie;
