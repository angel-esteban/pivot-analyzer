"""
normalizador.py — Normalización de unidades de yfinance (corre ANTES de validar).

yfinance es inconsistente: un mismo campo llega a veces como fracción (0,045) y a
veces como porcentaje (4,5). Esta capa detecta el formato y lo lleva a la UNIDAD
CANÓNICA que esperan los criterios (fracción decimal: 0,75 = 75 %).

Filosofía CONSERVADORA: solo convierte cuando el valor es IMPOSIBLE en la unidad
canónica (por tanto, inequívocamente porcentaje). En la zona ambigua NO toca el
dato y deja que las capas 0 (rangos) y 1 (coherencia) actúen de red de seguridad.
Así nunca corrompe un valor correcto.

Módulo puro, sin dependencias.
"""

from __future__ import annotations

from typing import Any

# Campo yfinance -> (umbral, divisor)
#   Si |valor| > umbral, el valor NO puede ser la unidad canónica (fracción) y se
#   asume porcentaje → se divide por el divisor. Umbrales elegidos para que un valor
#   canónico legítimo (incluso extremo) jamás los supere.
_REGLAS: dict[str, tuple[float, float]] = {
    # Yields: como fracción nunca llegan al 100 % (1.0). >1 ⇒ viene en %.
    "dividendYield":                (1.0, 100.0),
    "trailingAnnualDividendYield":  (1.0, 100.0),
    "fiveYearAvgDividendYield":     (1.0, 100.0),
    # Payout: como fracción admite hasta ~5 (500 %). >5 ⇒ viene en %.
    "payoutRatio":                  (5.0, 100.0),
    # Márgenes: como fracción no superan ±200 % salvo casos patológicos. |v|>2 ⇒ %.
    "grossMargins":                 (2.0, 100.0),
    "operatingMargins":             (2.0, 100.0),
    "profitMargins":                (2.0, 100.0),
    "ebitdaMargins":                (2.0, 100.0),
    # Rentabilidades: idem márgenes.
    "returnOnEquity":               (2.0, 100.0),
    "returnOnAssets":               (2.0, 100.0),
    # Crecimientos: pueden ser grandes; umbral alto (>500 %) para no tocar turnarounds.
    "revenueGrowth":                (5.0, 100.0),
    "earningsGrowth":               (5.0, 100.0),
    "earningsQuarterlyGrowth":      (5.0, 100.0),
}


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None      # descarta NaN
    except (TypeError, ValueError):
        return None


def normalizar_info(info: dict) -> tuple[dict, dict[str, tuple[float, float]]]:
    """
    Devuelve (info_normalizado, cambios). `cambios` = {campo: (valor_original, valor_nuevo)}.
    No muta el dict de entrada.
    """
    out = dict(info)
    cambios: dict[str, tuple[float, float]] = {}
    for campo, (umbral, divisor) in _REGLAS.items():
        v = _num(out.get(campo))
        if v is None:
            continue
        if abs(v) > umbral:
            nuevo = v / divisor
            out[campo] = nuevo
            cambios[campo] = (v, nuevo)
    return out, cambios


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    casos = {
        "payout %":        {"payoutRatio": 52.8},
        "payout fraccion": {"payoutRatio": 0.528},
        "payout 221%":     {"payoutRatio": 2.21},
        "yield %":         {"dividendYield": 4.5},
        "yield fraccion":  {"dividendYield": 0.045},
        "margen %":        {"grossMargins": 45.0},
        "margen fraccion": {"grossMargins": 0.45},
        "roe fraccion":    {"returnOnEquity": 0.15},
        "growth fraccion": {"revenueGrowth": 0.15},
        "growth % grande": {"earningsGrowth": 1500.0},
        "d/e intacto":     {"debtToEquity": 150.0},
        "ausente":         {"payoutRatio": None},
    }
    ok=True
    esperado={"payout %":0.528,"payout fraccion":0.528,"payout 221%":2.21,"yield %":0.045,
              "yield fraccion":0.045,"margen %":0.45,"margen fraccion":0.45,"roe fraccion":0.15,
              "growth fraccion":0.15,"growth % grande":15.0}
    for nombre, info in casos.items():
        out, ch = normalizar_info(info)
        print(f"{nombre:18} {info} -> {out}   cambios={ch}")
        campo=list(info)[0]
        if nombre in esperado and out.get(campo)!=esperado[nombre]:
            ok=False; print("   !! ESPERABA", esperado[nombre])
    assert out["debtToEquity"]==150.0  # ultimo caso d/e intacto... ojo casos dict
    print("\nOK" if ok else "\nFALLOS")
