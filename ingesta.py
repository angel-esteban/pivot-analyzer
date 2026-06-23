"""
ingesta.py — Capa de ingesta de datos del screener.

Flujo:  yfinance ─▶ validación nivel 0 ─▶ UPSERT a Neon ─▶ registro en ingesta_log

Tres entradas según nivel de dato (ver DISENO_Persistencia_Datos_Screener.md):
  - ingerir_estructural(...)   -> tabla `instrumento`         (refresco manual)
  - ingerir_fundamental(...)   -> tablas `fundamental` + `dividendo_pago` (cron+manual)
  - (el nivel mercado NO se ingiere: se consulta en vivo desde el screener)

Principios de diseño (alineados con la revisión de arquitectura):
  - Desacoplado de Streamlit: la conexión a BD y la fuente de datos se INYECTAN.
  - Identificadores SQL literales (constantes del módulo); valores parametrizados.
  - Reintentos ante fallos de red de yfinance.
  - Todo dato pasa por el validador de nivel 0 antes de persistirse.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from validador_nivel0 import (Estado, FieldSpec, cargar_specs_desde_criteria,
                              validar_campo)


# ─────────────────────────────────────────────────────────────────────────────
# Fuente de datos (inyectable). La de producción usa yfinance con reintentos.
# ─────────────────────────────────────────────────────────────────────────────
class FuenteYFinance:
    """Fuente real. Importa yfinance de forma perezosa (no se necesita para test)."""

    def __init__(self, reintentos: int = 3, espera: float = 1.5):
        self.reintentos = reintentos
        self.espera = espera

    def _ticker(self, ticker: str):
        import yfinance as yf
        return yf.Ticker(ticker)

    def info(self, ticker: str) -> dict[str, Any]:
        ult = None
        for intento in range(self.reintentos):
            try:
                info = self._ticker(ticker).info
                if info and len(info) > 3:
                    return info
            except Exception as e:        # noqa: BLE001 — se reintenta y se propaga al final
                ult = e
            time.sleep(self.espera)
        if ult:
            raise ult
        return {}

    def dividendos(self, ticker: str) -> list[tuple[Any, float]]:
        """Devuelve [(fecha_ex, importe), ...]. Convierte la Serie de pandas a lista."""
        for _ in range(self.reintentos):
            try:
                serie = self._ticker(ticker).dividends
                if serie is None or len(serie) == 0:
                    return []
                return [(idx.date() if hasattr(idx, "date") else idx, float(v))
                        for idx, v in serie.items()]
            except Exception:             # noqa: BLE001
                time.sleep(self.espera)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de cálculo (autónomos: no dependen de pandas ni de app.py)
# ─────────────────────────────────────────────────────────────────────────────
def _fcf_yield(info: dict, _div) -> float | None:
    fcf, mcap = info.get("freeCashflow"), info.get("marketCap")
    if fcf in (None, "") or not mcap:
        return None
    try:
        return float(fcf) / float(mcap)
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def _anos_div_consecutivos(_info, dividendos: list[tuple[Any, float]]) -> int | None:
    """Años consecutivos con pago, contando hacia atrás desde el último año con pago."""
    if not dividendos:
        return None
    anos = sorted({getattr(f, "year", None) or int(str(f)[:4])
                   for f, imp in dividendos if imp and imp > 0}, reverse=True)
    if not anos:
        return 0
    consec, esperado = 0, anos[0]
    for a in anos:
        if a == esperado:
            consec += 1
            esperado -= 1
        else:
            break
    return consec


def _cagr_dividendo_5y(_info, dividendos: list[tuple[Any, float]]) -> float | None:
    """CAGR del dividendo anual agregando los últimos 5 años completos disponibles."""
    if not dividendos:
        return None
    por_ano: dict[int, float] = {}
    for f, imp in dividendos:
        a = getattr(f, "year", None) or int(str(f)[:4])
        por_ano[a] = por_ano.get(a, 0.0) + float(imp)
    anos = sorted(por_ano)
    if len(anos) < 2:
        return None
    ventana = anos[-6:-1] if len(anos) >= 6 else anos[:-1]  # excluye el año en curso (incompleto)
    if len(ventana) < 2:
        ventana = anos
    ini, fin = por_ano[ventana[0]], por_ano[ventana[-1]]
    n = ventana[-1] - ventana[0]
    if ini <= 0 or n <= 0:
        return None
    return (fin / ini) ** (1 / n) - 1


def _tipo_activo(info: dict, _div):
    qt = (info.get("quoteType") or "").upper()
    return {"EQUITY": "accion", "ETF": "etf"}.get(qt, qt.lower() or None)


def _es_ucits(info: dict, _div):
    if (info.get("quoteType") or "").upper() != "ETF":
        return None
    nombre = (info.get("longName") or info.get("shortName") or "").upper()
    return "UCITS" in nombre or None     # None si no se puede afirmar (ausente, no False)


def _free_float_fraccion(info: dict, _div) -> float | None:
    flt, tot = info.get("floatShares"), info.get("sharesOutstanding")
    if not flt or not tot:
        return None
    try:
        return float(flt) / float(tot)
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def _fecha_resultados(info: dict, _div):
    ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError):
        return None


def _campo(clave: str) -> Callable:
    return lambda info, _div: info.get(clave)


# ─────────────────────────────────────────────────────────────────────────────
# Mapeo de columnas. (col_db, spec_key|None, extractor, transform|None)
#   spec_key None  -> se almacena tal cual, sin validación de nivel 0 (texto descriptivo)
#   transform      -> se aplica al valor saneado antes de almacenar
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Mapa:
    col: str
    spec_key: str | None
    extractor: Callable
    transform: Callable | None = None


MAPA_ESTRUCTURAL: list[Mapa] = [
    Mapa("nombre",         None,                     lambda i, d: i.get("longName") or i.get("shortName")),
    Mapa("isin",           None,                     _campo("isin")),
    Mapa("sector",         "sector",                 _campo("sector")),
    Mapa("industria",      None,                     _campo("industry")),
    Mapa("pais",           None,                     _campo("country")),
    Mapa("divisa",         None,                     _campo("currency")),
    Mapa("mercado",        None,                     _campo("exchange")),
    Mapa("tipo_activo",    None,                     _tipo_activo),
    Mapa("free_float_pct", "free_float",             _free_float_fraccion, lambda v: round(v * 100, 2)),
    Mapa("es_ucits",       "estructura_ucits",       _es_ucits),
    Mapa("ter",            "annualReportExpenseRatio", _campo("annualReportExpenseRatio")),
    Mapa("aum",            "totalAssets",            _campo("totalAssets")),
]

MAPA_FUNDAMENTAL: list[Mapa] = [
    Mapa("payout_ratio",      "payoutRatio",         _campo("payoutRatio")),
    Mapa("bpa",               "bpa",                 _campo("trailingEps")),
    Mapa("debt_to_equity",    "debtToEquity",        _campo("debtToEquity")),
    Mapa("ev_ebitda",         "enterpriseToEbitda",  _campo("enterpriseToEbitda")),
    Mapa("revenue_growth",    "revenueGrowth",       _campo("revenueGrowth")),
    Mapa("gross_margins",     "grossMargins",        _campo("grossMargins")),
    Mapa("operating_margins", "operatingMargins",    _campo("operatingMargins")),
    Mapa("roe",               "returnOnEquity",      _campo("returnOnEquity")),
    Mapa("peg_ratio",         "pegRatio",            _campo("pegRatio")),
    Mapa("earnings_growth",   "earningsGrowth",      _campo("earningsGrowth")),
    Mapa("fcf_yield",         "free_cash_flow",      _fcf_yield),
    Mapa("market_cap",        "marketCap",           _campo("marketCap")),
    Mapa("beta",              "beta",                _campo("beta")),
    Mapa("anos_div_consec",   "historial_dividendo", _anos_div_consecutivos),
    Mapa("cagr_dividendo_5y", "crecimiento_dividendo", _cagr_dividendo_5y),
    Mapa("fecha_resultados",  None,                  _fecha_resultados),
]

_COLS_INSTRUMENTO = [m.col for m in MAPA_ESTRUCTURAL] + ["ticker", "fuente", "valido", "motivo_invalidez"]
_COLS_FUNDAMENTAL = [m.col for m in MAPA_FUNDAMENTAL] + ["ticker", "fuente", "valido", "motivo_invalidez"]

_SPEC_PERMISIVA = FieldSpec("?", tipo_valor="ratio", rango_valido=None)


# ─────────────────────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResumenIngesta:
    nivel: str
    log_id: int | None = None
    procesados: int = 0
    ok: int = 0
    fallidos: int = 0
    detalle_fallidos: dict[str, str] = field(default_factory=dict)
    filas: list[dict] = field(default_factory=list)   # filas que se (intentaron) upsertar


# ─────────────────────────────────────────────────────────────────────────────
# Construcción de fila validada
# ─────────────────────────────────────────────────────────────────────────────
def _construir_fila(ticker: str, info: dict, dividendos: list,
                    mapa: list[Mapa], specs: dict[str, FieldSpec]) -> tuple[dict, bool, str | None]:
    fila: dict[str, Any] = {}
    motivos: list[str] = []
    valido = True
    for m in mapa:
        crudo = m.extractor(info, dividendos)
        if m.spec_key is None:                       # descriptivo: sin nivel 0
            fila[m.col] = crudo.strip() if isinstance(crudo, str) else crudo
            continue
        spec = specs.get(m.spec_key) or _SPEC_PERMISIVA
        rc = validar_campo(crudo, spec)
        val = rc.valor
        if val is not None and m.transform:
            val = m.transform(val)
        fila[m.col] = val
        if rc.estado is Estado.SOSPECHOSO:
            valido = False
            motivos.append(f"{m.col}: {rc.motivo}")
    return fila, valido, ("; ".join(motivos) or None)


# ─────────────────────────────────────────────────────────────────────────────
# SQL (identificadores literales, valores parametrizados)
# ─────────────────────────────────────────────────────────────────────────────
def _sql_upsert(tabla: str, columnas: list[str], conflicto: list[str]) -> str:
    cols = ", ".join(columnas)
    ph = ", ".join(["%s"] * len(columnas))
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in columnas if c not in conflicto)
    return (f"INSERT INTO {tabla} ({cols}) VALUES ({ph}) "
            f"ON CONFLICT ({', '.join(conflicto)}) DO UPDATE SET {sets}")


def _upsert(cur, tabla: str, columnas: list[str], conflicto: list[str], fila: dict) -> None:
    cur.execute(_sql_upsert(tabla, columnas, conflicto), [fila.get(c) for c in columnas])


# ─────────────────────────────────────────────────────────────────────────────
# Registro de auditoría (ingesta_log)
# ─────────────────────────────────────────────────────────────────────────────
def _abrir_log(cur, nivel: str, disparado_por: str, fuente: str) -> int:
    cur.execute(
        "INSERT INTO ingesta_log (nivel, disparado_por, fuente) VALUES (%s, %s, %s) RETURNING id",
        [nivel, disparado_por, fuente])
    return cur.fetchone()[0]


def _cerrar_log(cur, log_id: int, r: ResumenIngesta) -> None:
    cur.execute(
        "UPDATE ingesta_log SET fin = now(), tickers_procesados = %s, tickers_ok = %s, "
        "tickers_fallidos = %s, detalle_fallidos = %s::jsonb WHERE id = %s",
        [r.procesados, r.ok, r.fallidos, json.dumps(r.detalle_fallidos, ensure_ascii=False), log_id])


# ─────────────────────────────────────────────────────────────────────────────
# Orquestadores
# ─────────────────────────────────────────────────────────────────────────────
def _ingerir(nivel: str, tabla: str, columnas: list[str], mapa: list[Mapa],
             tickers: Iterable[str], conn, *, fuente=None, specs=None,
             criteria_path: str = "criteria.json", disparado_por: str = "cron",
             nombre_fuente: str = "yfinance", dry_run: bool = False,
             con_dividendos: bool = False) -> ResumenIngesta:
    fuente = fuente or FuenteYFinance()
    specs = specs or cargar_specs_desde_criteria(criteria_path)
    r = ResumenIngesta(nivel=nivel)
    cur = conn.cursor()

    if not dry_run:
        r.log_id = _abrir_log(cur, nivel, disparado_por, nombre_fuente)

    for ticker in tickers:
        r.procesados += 1
        try:
            info = fuente.info(ticker)
            if not info:
                raise ValueError("yfinance no devolvió datos (.info vacío)")
            dividendos = fuente.dividendos(ticker) if (con_dividendos or nivel == "fundamental") else []

            fila, valido, motivo = _construir_fila(ticker, info, dividendos, mapa, specs)
            fila.update(ticker=ticker, fuente=nombre_fuente, valido=valido, motivo_invalidez=motivo)
            r.filas.append(fila)

            if not dry_run:
                _upsert(cur, tabla, columnas, ["ticker"], fila)
                if con_dividendos:
                    for fecha_ex, importe in dividendos:
                        _upsert(cur, "dividendo_pago",
                                ["ticker", "fecha_ex", "importe", "fuente"], ["ticker", "fecha_ex"],
                                {"ticker": ticker, "fecha_ex": fecha_ex,
                                 "importe": importe, "fuente": nombre_fuente})
            r.ok += 1
        except Exception as e:               # noqa: BLE001 — un ticker no debe tumbar el lote
            r.fallidos += 1
            r.detalle_fallidos[ticker] = str(e)

    if not dry_run:
        _cerrar_log(cur, r.log_id, r)
        conn.commit()
    return r


def ingerir_estructural(tickers, conn, **kw) -> ResumenIngesta:
    return _ingerir("estructural", "instrumento", _COLS_INSTRUMENTO, MAPA_ESTRUCTURAL,
                    tickers, conn, disparado_por=kw.pop("disparado_por", "admin"), **kw)


def ingerir_fundamental(tickers, conn, **kw) -> ResumenIngesta:
    return _ingerir("fundamental", "fundamental", _COLS_FUNDAMENTAL, MAPA_FUNDAMENTAL,
                    tickers, conn, con_dividendos=True, **kw)
