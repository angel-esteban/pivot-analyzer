"""
monitor_calidad.py — Monitor de cobertura y frescura de los datos del screener.

NO valida valores: vigila el PROCESO. Lee lo ya persistido en Neon y responde:
  - Cobertura: ¿qué % del universo trae cada campo? (caza que yfinance deje de
    devolver un campo → su cobertura se desploma).
  - Frescura: ¿cuánto envejecen los datos? ¿hay fundamentales con resultados ya
    publicados (fecha_resultados pasada) sin refrescar desde entonces?
  - Tendencia de incidencias: nº de tickers con cada campo marcado en las últimas
    ingestas (vía ingesta_log) → degradación silenciosa de la fuente.

Solo lectura. Conexión inyectable. La lógica de agregación/alertas es pura y testeable;
el SQL usa identificadores literales.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

try:
    import psycopg2.extras as _extras
    _FACTORY = _extras.RealDictCursor
except Exception:                       # noqa: BLE001
    _FACTORY = None

# Columnas cuya cobertura se mide (las que alimentan criterios)
COLS_FUNDAMENTAL = ["payout_ratio", "bpa", "debt_to_equity", "ev_ebitda", "revenue_growth",
                    "gross_margins", "operating_margins", "roe", "peg_ratio", "earnings_growth",
                    "fcf_yield", "market_cap", "beta", "anos_div_consec", "cagr_dividendo_5y"]
COLS_INSTRUMENTO = ["sector", "free_float_pct", "ter", "aum", "es_ucits"]

TOLERANCIA_DIAS = {"estructural": 365, "fundamental": 120}
UMBRAL_COBERTURA_BAJA = 0.50    # < 50 % del universo → alerta
# Campos solo de ETF: en universos de acciones están vacíos legítimamente → no alertar
COLS_CONDICIONALES = {"ter", "aum", "es_ucits"}


@dataclass
class InformeMonitor:
    cobertura: dict[str, dict] = field(default_factory=dict)      # {tabla: {campo: {n,total,pct}}}
    frescura: dict[str, dict] = field(default_factory=dict)       # {tabla: {...}}
    incidencias_tendencia: dict[str, int] = field(default_factory=dict)  # {campo: nº tickers}
    alertas: list[str] = field(default_factory=list)


def _cur(conn):
    return conn.cursor(cursor_factory=_FACTORY) if _FACTORY else conn.cursor()


# ── Cobertura ────────────────────────────────────────────────────────────────
def cobertura(conn, tabla: str, cols: list[str]) -> dict[str, dict]:
    sel = "count(*) AS _total, " + ", ".join(f"count({c}) AS {c}" for c in cols)
    cur = _cur(conn)
    try:
        cur.execute(f"SELECT {sel} FROM {tabla}")
        row = dict(cur.fetchone() or {})
    finally:
        cur.close()
    total = row.get("_total", 0) or 0
    return {c: {"n": row.get(c, 0) or 0, "total": total,
                "pct": ((row.get(c, 0) or 0) / total if total else 0.0)} for c in cols}


# ── Frescura ─────────────────────────────────────────────────────────────────
def frescura(conn, tabla: str, nivel: str) -> dict:
    tol = TOLERANCIA_DIAS.get(nivel, 120)
    extra = ""
    if tabla == "fundamental":
        extra = (", count(*) FILTER (WHERE fecha_resultados IS NOT NULL "
                 "AND fecha_resultados < current_date "
                 "AND actualizado_en::date < fecha_resultados) AS sin_refresco_tras_resultados")
    cur = _cur(conn)
    try:
        cur.execute(
            f"SELECT count(*) AS total, min(actualizado_en) AS mas_antiguo, "
            f"max(actualizado_en) AS mas_reciente, "
            f"count(*) FILTER (WHERE actualizado_en < now() - make_interval(days => %s)) AS caducados"
            f"{extra} FROM {tabla}", [tol])
        row = dict(cur.fetchone() or {})
    finally:
        cur.close()
    row["tolerancia_dias"] = tol
    return row


# ── Tendencia de incidencias (pura: separa parseo de la query) ───────────────
def _agregar_incidencias(filas_log: list[dict]) -> dict[str, int]:
    """Cuenta, sobre la ingesta más reciente de cada nivel, cuántos tickers tienen
    cada campo marcado. filas_log = [{nivel, detalle_fallidos(dict|str), ...}]."""
    contador: dict[str, int] = {}
    niveles_vistos = set()
    for fila in filas_log:                       # asume orden id DESC (más reciente primero)
        nivel = fila.get("nivel")
        if nivel in niveles_vistos:
            continue                              # solo la corrida más reciente por nivel
        niveles_vistos.add(nivel)
        det = fila.get("detalle_fallidos") or {}
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except Exception:
                det = {}
        incid = det.get("incidencias", {}) if isinstance(det, dict) else {}
        for _ticker, campos in (incid or {}).items():
            for campo in (campos or {}):
                contador[campo] = contador.get(campo, 0) + 1
    return dict(sorted(contador.items(), key=lambda kv: kv[1], reverse=True))


def incidencias_tendencia(conn, n: int = 6) -> dict[str, int]:
    cur = _cur(conn)
    try:
        cur.execute("SELECT id, nivel, detalle_fallidos FROM ingesta_log "
                    "ORDER BY id DESC LIMIT %s", [n])
        filas = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
    return _agregar_incidencias(filas)


# ── Alertas (puras) ──────────────────────────────────────────────────────────
def _alertas(cobertura_tablas: dict, frescura_tablas: dict, incid: dict[str, int]) -> list[str]:
    al: list[str] = []
    for tabla, cob in cobertura_tablas.items():
        for campo, m in cob.items():
            if campo in COLS_CONDICIONALES:
                continue
            if m["total"] > 0 and m["pct"] < UMBRAL_COBERTURA_BAJA:
                al.append(f"Cobertura baja en {tabla}.{campo}: {m['pct']:.0%} "
                          f"({m['n']}/{m['total']}) — ¿yfinance dejó de traer este campo?")
    for tabla, fr in frescura_tablas.items():
        if fr.get("caducados"):
            al.append(f"{fr['caducados']} registros caducados en {tabla} "
                      f"(> {fr['tolerancia_dias']} días sin refrescar).")
        if fr.get("sin_refresco_tras_resultados"):
            al.append(f"{fr['sin_refresco_tras_resultados']} valores con resultados ya "
                      f"publicados sin refrescar — conviene re-ingerir fundamentales.")
    for campo, n in incid.items():
        if n >= 5:
            al.append(f"Campo '{campo}' marcado en {n} tickers en la última ingesta — posible degradación.")
    return al


def informe(conn) -> InformeMonitor:
    inf = InformeMonitor()
    inf.cobertura["fundamental"] = cobertura(conn, "fundamental", COLS_FUNDAMENTAL)
    inf.cobertura["instrumento"] = cobertura(conn, "instrumento", COLS_INSTRUMENTO)
    inf.frescura["fundamental"] = frescura(conn, "fundamental", "fundamental")
    inf.frescura["instrumento"] = frescura(conn, "instrumento", "estructural")
    inf.incidencias_tendencia = incidencias_tendencia(conn)
    inf.alertas = _alertas(inf.cobertura, inf.frescura, inf.incidencias_tendencia)
    return inf
