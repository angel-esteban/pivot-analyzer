"""
validador_coherencia.py — Validación de nivel 1: coherencia entre campos.

Complementa al validador de nivel 0 (rangos + ausente≠cero). La capa 0 caza lo
*implausible*; esta caza lo *internamente incoherente*: campos de yfinance que,
recalculados por una vía alternativa, no cuadran entre sí. Eso delata errores que
pasan el rango pero son falsos (payout mal, precio o nº de acciones desfasado,
unidades inconsistentes).

Opera sobre el dict `info` de yfinance (todos los campos disponibles a la vez).
Devuelve incidencias informativas; NO decide por sí mismo excluir el ticker —
esa política la fija quien lo llama (ingesta o screener).

Módulo puro, sin dependencias externas. Tolerancias generosas para no generar
falsos positivos (yfinance redondea y los campos legítimamente difieren algo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ResultadoCoherencia:
    coherente: bool = True
    incidencias: list[str] = field(default_factory=list)   # mensajes legibles
    checks: dict[str, str] = field(default_factory=dict)    # {nombre_check: 'ok'|'flag'|'n/a'}
    detalle: dict[str, str] = field(default_factory=dict)   # {nombre_check: mensaje} solo de los flag

    def resumen(self) -> str | None:
        return "; ".join(self.incidencias) if self.incidencias else None


# ── Helpers ──────────────────────────────────────────────────────────────────
def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None      # descarta NaN
    except (TypeError, ValueError):
        return None


def _div_rel(a: float, b: float) -> float:
    """Divergencia relativa entre a y b (0 = idénticos)."""
    m = max(abs(a), abs(b))
    return abs(a - b) / m if m else 0.0


def _precio(info: dict) -> float | None:
    return _num(info.get("regularMarketPrice") or info.get("currentPrice")
                or info.get("previousClose"))


# ── Comprobaciones relacionales ──────────────────────────────────────────────
# Cada check devuelve (estado, mensaje|None): estado en {'ok','flag','n/a'}.
def _c_market_cap(info: dict) -> tuple[str, str | None]:
    mcap, precio, shares = _num(info.get("marketCap")), _precio(info), _num(info.get("sharesOutstanding"))
    if not mcap or not precio or not shares:
        return "n/a", None
    esperado = precio * shares
    d = _div_rel(mcap, esperado)
    if d > 0.10:
        return "flag", (f"marketCap ({mcap:,.0f}) no cuadra con precio×acciones "
                        f"({esperado:,.0f}, dif {d:.0%}) — precio o nº de acciones desfasado")
    return "ok", None


def _c_free_float(info: dict) -> tuple[str, str | None]:
    flt, tot = _num(info.get("floatShares")), _num(info.get("sharesOutstanding"))
    if not flt or not tot:
        return "n/a", None
    ratio = flt / tot
    if ratio > 1.001:
        return "flag", f"floatShares ({flt:,.0f}) > sharesOutstanding ({tot:,.0f}) — imposible"
    if ratio <= 0:
        return "flag", "free float ≤ 0 — incoherente"
    return "ok", None


def _c_yield(info: dict) -> tuple[str, str | None]:
    drate, precio = _num(info.get("dividendRate")), _precio(info)
    tady = _num(info.get("trailingAnnualDividendYield"))
    if not drate or not precio or not tady or tady <= 0:
        return "n/a", None
    y_calc = drate / precio
    d = _div_rel(y_calc, tady)
    if d > 0.25:
        return "flag", (f"yield por dividendRate/precio ({y_calc:.2%}) discrepa del "
                        f"trailingAnnualDividendYield ({tady:.2%}, dif {d:.0%}) — posible problema de unidad")
    return "ok", None


def _c_payout(info: dict) -> tuple[str, str | None]:
    payout, drate, eps = _num(info.get("payoutRatio")), _num(info.get("dividendRate")), _num(info.get("trailingEps"))
    if payout is None or not drate or eps is None:
        return "n/a", None
    if eps <= 0:
        if payout > 0:
            return "flag", f"payoutRatio {payout:.0%} con BPA≤0 ({eps}) — payout contable no significativo"
        return "n/a", None
    p_calc = drate / eps
    d = _div_rel(payout, p_calc)
    if d > 0.25:
        return "flag", (f"payoutRatio ({payout:.0%}) discrepa del recalculado dividendRate/BPA "
                        f"({p_calc:.0%}, dif {d:.0%})")
    return "ok", None


def _c_ev_ebitda(info: dict) -> tuple[str, str | None]:
    ev_eb = _num(info.get("enterpriseToEbitda"))
    ev, ebitda = _num(info.get("enterpriseValue")), _num(info.get("ebitda"))
    if ev_eb is None or not ev or not ebitda:
        return "n/a", None
    calc = ev / ebitda
    d = _div_rel(ev_eb, calc)
    if d > 0.20:
        return "flag", (f"enterpriseToEbitda ({ev_eb:.1f}) discrepa de enterpriseValue/EBITDA "
                        f"({calc:.1f}, dif {d:.0%})")
    return "ok", None


_CHECKS: dict[str, Callable[[dict], tuple[str, str | None]]] = {
    "market_cap":  _c_market_cap,
    "free_float":  _c_free_float,
    "yield":       _c_yield,
    "payout":      _c_payout,
    "ev_ebitda":   _c_ev_ebitda,
}


def validar_coherencia(info: dict) -> ResultadoCoherencia:
    """Ejecuta todas las comprobaciones de coherencia sobre el dict info."""
    r = ResultadoCoherencia()
    for nombre, fn in _CHECKS.items():
        try:
            estado, msg = fn(info)
        except Exception:                       # noqa: BLE001 — un check no debe romper el resto
            estado, msg = "n/a", None
        r.checks[nombre] = estado
        if estado == "flag" and msg:
            r.coherente = False
            r.incidencias.append(msg)
            r.detalle[nombre] = msg
    return r


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    casos = {
        "COHERENTE": {
            "marketCap": 1_000_000_000, "regularMarketPrice": 10.0, "sharesOutstanding": 100_000_000,
            "floatShares": 60_000_000, "dividendRate": 0.40, "trailingAnnualDividendYield": 0.04,
            "payoutRatio": 0.50, "trailingEps": 0.80,
            "enterpriseToEbitda": 8.0, "enterpriseValue": 1_600_000_000, "ebitda": 200_000_000,
        },
        "MCAP_DESFASADO": {  # precio o acciones viejo
            "marketCap": 1_000_000_000, "regularMarketPrice": 10.0, "sharesOutstanding": 200_000_000,
        },
        "FLOAT_IMPOSIBLE": {"floatShares": 150, "sharesOutstanding": 100},
        "YIELD_UNIDAD": {  # dividendRate/precio=4% pero TADY dice 0.04%... (unidad)
            "dividendRate": 0.40, "regularMarketPrice": 10.0, "trailingAnnualDividendYield": 0.0004,
        },
        "PAYOUT_INCOHERENTE": {"payoutRatio": 0.60, "dividendRate": 0.40, "trailingEps": 2.00},  # calc=20% vs 60%
        "PAYOUT_BPA_NEG": {"payoutRatio": 1.11, "dividendRate": 0.30, "trailingEps": -0.42},
    }
    for nombre, info in casos.items():
        r = validar_coherencia(info)
        print(f"\n=== {nombre}  coherente={r.coherente}")
        print("   checks:", r.checks)
        for inc in r.incidencias:
            print("   !!", inc)
