"""
repositorio.py — Capa de lectura de datos del screener desde Neon.

Reconstruye un dict con forma de `info` de yfinance (mismas claves que ya leen
los criterios) a partir de las tablas `instrumento` y `fundamental`, añadiendo el
estado de frescura de cada nivel. Así el screener puede leer de Neon (niveles 1-2)
sin cambiar la lógica de evaluación, y seguir pidiendo el nivel mercado en vivo.

Política de frescura (ver DISENO §6): cada nivel se etiqueta ok / cacheado /
caducado / sospechoso / ausente según su antigüedad y su flag `valido`.

Nota de alcance: en esta versión se sirven desde Neon los campos directos de
`.info` (payout, deuda, márgenes, sector, beta, TER, AUM...). Los criterios
*calculados* (free_float, dividend yield, RSI...) se siguen computando en vivo.
"""

from __future__ import annotations

import datetime
from typing import Any

# Columna en BD -> clave de yfinance que esperan los criterios de criteria.json
MAP_INSTRUMENTO = {
    "sector": "sector",
    "ter":    "annualReportExpenseRatio",
    "aum":    "totalAssets",
}
MAP_FUNDAMENTAL = {
    "payout_ratio":      "payoutRatio",
    "bpa":               "trailingEps",
    "debt_to_equity":    "debtToEquity",
    "ev_ebitda":         "enterpriseToEbitda",
    "revenue_growth":    "revenueGrowth",
    "gross_margins":     "grossMargins",
    "operating_margins": "operatingMargins",
    "roe":               "returnOnEquity",
    "peg_ratio":         "pegRatio",
    "earnings_growth":   "earningsGrowth",
    "market_cap":        "marketCap",
    "beta":              "beta",
}

# Tolerancia de obsolescencia por nivel (coincide con criteria.meta.niveles_dato)
TOLERANCIA_DIAS = {"estructural": 365, "fundamental": 120}

try:
    import psycopg2.extras as _extras
    _FACTORY = _extras.RealDictCursor
except Exception:                       # noqa: BLE001 — entorno de test sin psycopg2
    _FACTORY = None


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _leer_fila(conn, tabla: str, ticker: str) -> dict | None:
    cur = conn.cursor(cursor_factory=_FACTORY) if _FACTORY else conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {tabla} WHERE ticker = %s", [ticker])
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _estado_frescura(actualizado_en, tolerancia_dias: int, ahora, valido) -> str:
    if actualizado_en is None:
        return "ausente"
    if valido is False:
        return "sospechoso"
    dt = actualizado_en
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt)
        except ValueError:
            return "ok"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    edad = (ahora - dt).days
    if edad > tolerancia_dias:
        return "caducado"
    return "cacheado"


def componer_info(ticker: str, conn, ahora: datetime.datetime | None = None
                  ) -> tuple[dict[str, Any], dict[str, dict]]:
    """
    Devuelve (info, frescura):
      - info: dict con claves de yfinance pobladas desde Neon (solo valores no nulos)
      - frescura: {nivel: {estado, actualizado_en, valido}} para cada nivel persistido
    """
    ahora = ahora or _ahora()
    info: dict[str, Any] = {}
    frescura: dict[str, dict] = {}

    for tabla, mapa, nivel in (("instrumento", MAP_INSTRUMENTO, "estructural"),
                               ("fundamental", MAP_FUNDAMENTAL, "fundamental")):
        fila = _leer_fila(conn, tabla, ticker)
        if not fila:
            frescura[nivel] = {"estado": "ausente", "actualizado_en": None, "valido": None}
            continue
        for col, yk in mapa.items():
            v = fila.get(col)
            if v is not None:
                info[yk] = v
        frescura[nivel] = {
            "estado": _estado_frescura(fila.get("actualizado_en"),
                                       TOLERANCIA_DIAS[nivel], ahora, fila.get("valido")),
            "actualizado_en": fila.get("actualizado_en"),
            "valido": fila.get("valido"),
        }
    return info, frescura


def necesita_live(frescura: dict, nivel: str) -> bool:
    """True si ese nivel debe completarse con yfinance en vivo (ausente o caducado)."""
    return frescura.get(nivel, {}).get("estado") in ("ausente", "caducado")


def etiqueta_frescura(frescura: dict, nivel: str) -> str:
    """Etiqueta legible para el informe. Vacía si el dato es fresco/ok."""
    f = frescura.get(nivel, {})
    estado, ts = f.get("estado"), f.get("actualizado_en")
    if estado in (None, "ok"):
        return ""
    fecha = ""
    if ts is not None:
        d = ts if not isinstance(ts, str) else ts[:10]
        fecha = d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
    etiquetas = {
        "cacheado":   f"[DATO CACHEADO · {fecha}]",
        "caducado":   f"[DATO CADUCADO · {fecha} — refrescar]",
        "sospechoso": "[DATO SOSPECHOSO — verificar]",
        "ausente":    "[SIN DATO PERSISTIDO — en vivo]",
    }
    return etiquetas.get(estado, "")
