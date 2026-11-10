-- =============================================================================
-- migracion_serie_macro_guardada.sql  ·  APROBADA por el propietario el 10/11/2026
-- Última serie buena de cada indicador macro de la fase del ciclo (BCE, Eurostat, BIS, BLS, Tesoro de EE. UU.).
--
-- Uso: cuando una fuente no responde (incidencia del 10/11/2026 con la API del BCE desde Streamlit Cloud), la app
-- usa la serie guardada y lo INDICA al usuario («dato guardado el …; la fuente no respondió»).
-- Una fila por indicador (clave). Se sustituye cuando la descarga sale bien (solo si cambia o cada 6 h).
-- Tabla NUEVA e independiente: impacto sobre datos existentes NINGUNO. Datos públicos, sin datos personales.
--
-- Idempotente: se puede ejecutar varias veces. Reversión al final (DOWN). Sin credenciales.
-- =============================================================================

-- ── UP ───────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS serie_macro_guardada (
    clave          text        PRIMARY KEY,
    fuente         text        NOT NULL,
    datos          jsonb       NOT NULL,
    n_puntos       integer     NOT NULL,
    ultima_fecha   date,
    descargada_en  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE serie_macro_guardada IS
  'Última serie buena de cada indicador macro de la fase del ciclo. Respaldo cuando la fuente no responde; la app '
  'indica siempre al usuario que trabaja con datos guardados.';
COMMENT ON COLUMN serie_macro_guardada.clave IS 'Identificador de la serie (p. ej. ecb:FM/B.U2.EUR.4F.KR.DFR.LEV)';
COMMENT ON COLUMN serie_macro_guardada.datos IS 'jsonb {"YYYY-MM-DD": valor}';
COMMENT ON COLUMN serie_macro_guardada.descargada_en IS 'Momento de la última descarga buena';

-- ── Comprobación ─────────────────────────────────────────────────────────────
-- SELECT clave, fuente, n_puntos, ultima_fecha, descargada_en FROM serie_macro_guardada ORDER BY clave;

-- ── DOWN (reversión completa; solo si se decide deshacer) ────────────────────
-- DROP TABLE IF EXISTS serie_macro_guardada;
