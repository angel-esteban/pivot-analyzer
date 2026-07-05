"""
umbrales.py — Fuente ÚNICA de umbrales de coherencia (Configuración).

Todos los umbrales/tolerancias/rangos de plausibilidad y SLA de frescura que la
spec PA marca [VERIFICAR] viven aquí, con su valor por defecto, y se pueden
sobreescribir desde Neon (tabla `umbrales_coherencia`, editable en Configuración ›
Umbrales de coherencia). Los validadores leen de aquí (no de constantes dispersas).

Cautelas de diseño:
 1) DEFAULTS == valores hoy hardcodeados y desplegados. Si nadie edita nada, el
    comportamiento es idéntico: nada cambia en silencio al desplegar.
 2) El input de Configuración se valida (RANGOS_INPUT): nadie puede meter un
    free-float máximo de 200 ni una tolerancia negativa.

Módulo sin dependencia de Streamlit. La lectura de Neon es opcional (fallback a
DEFAULTS si no hay conexión o la tabla está vacía), así que es seguro importarlo
desde los validadores puros.
"""
from __future__ import annotations

from typing import Any

# ── Valores por defecto (IDÉNTICOS a lo desplegado hoy) ──────────────────────
DEFAULTS: dict[str, float] = {
    # Rangos de plausibilidad (nivel 0)
    "beta_min":          0.0,    "beta_max":          3.0,     # validador_nivel0 RANGO_BETA_PLAUSIBLE
    "free_float_min":    0.0,    "free_float_max":    100.0,   # RANGO_FREE_FLOAT_PCT
    # Tolerancias de coherencia (nivel 1)
    "payout_tol_rel":    0.25,   "payout_tol_abs":    0.05,    # _c_payout: rel>25% Y abs>5pp
    "yield_techo":       0.15,   "yield_techo_reit":  0.20,    # _c_yield
    "ev_ebitda_tol":     0.20,                                 # _c_ev_ebitda
    "market_cap_tol":    0.10,                                 # _c_market_cap
    # Bandas de indicadores (clasificadores RSI / Bollinger %B)
    "rsi_sobrecompra":   70.0,   "rsi_alcista":       55.0,
    "rsi_bajista":       45.0,   "rsi_sobreventa":    30.0,
    "bb_alto":           80.0,   "bb_medio":          50.0,    "bb_bajo": 20.0,
    # SLA de frescura (días) — repositorio TOLERANCIA_DIAS
    "sla_estructural_dias": 365.0, "sla_fundamental_dias": 120.0,
}

# ── Rango admisible de CADA umbral en la UI (validación del input, Caución 2) ──
RANGOS_INPUT: dict[str, tuple[float, float]] = {
    "beta_min":          (-5.0, 2.0),   "beta_max":          (0.5, 10.0),
    "free_float_min":    (0.0, 99.0),   "free_float_max":    (1.0, 100.0),
    "payout_tol_rel":    (0.01, 1.0),   "payout_tol_abs":    (0.001, 0.5),
    "yield_techo":       (0.02, 0.5),   "yield_techo_reit":  (0.02, 0.6),
    "ev_ebitda_tol":     (0.01, 1.0),   "market_cap_tol":    (0.01, 1.0),
    "rsi_sobrecompra":   (55.0, 95.0),  "rsi_alcista":       (50.0, 70.0),
    "rsi_bajista":       (30.0, 50.0),  "rsi_sobreventa":    (5.0, 45.0),
    "bb_alto":           (55.0, 99.0),  "bb_medio":          (30.0, 70.0),  "bb_bajo": (1.0, 45.0),
    "sla_estructural_dias": (7.0, 3650.0), "sla_fundamental_dias": (1.0, 730.0),
}

# Pares (min, max) que además deben cumplir min < max
_PARES_MINMAX = [("beta_min", "beta_max"), ("free_float_min", "free_float_max")]

_cache: dict[str, float] | None = None


def actuales(conn: Any = None) -> dict[str, float]:
    """Devuelve los umbrales vigentes: DEFAULTS con overlay de Neon.

    - Con `conn`: lee la tabla y refresca la caché de proceso.
    - Sin `conn`: devuelve la caché (o DEFAULTS si aún no se cargó). Así los
      validadores puros llaman `actuales()` sin necesidad de BBDD.
    """
    global _cache
    if conn is None:
        return dict(_cache) if _cache is not None else dict(DEFAULTS)
    vals = dict(DEFAULTS)
    try:
        cur = conn.cursor()
        cur.execute("SELECT clave, valor FROM umbrales_coherencia")
        for clave, valor in cur.fetchall():
            if clave in DEFAULTS and valor is not None:
                vals[clave] = float(valor)
    except Exception:                        # noqa: BLE001 — tabla ausente / sin conexión -> defaults
        pass
    _cache = vals
    return dict(vals)


def invalidar_cache() -> None:
    """Fuerza recarga desde Neon en la próxima llamada con conn."""
    global _cache
    _cache = None


def validar_input(clave: str, valor: Any, vigentes: dict[str, float] | None = None) -> str | None:
    """Valida un valor propuesto para un umbral. Devuelve motivo de error o None si es válido."""
    if clave not in DEFAULTS:
        return f"clave desconocida: {clave}"
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "no es un número"
    if v != v:                               # NaN
        return "valor no válido (NaN)"
    lo, hi = RANGOS_INPUT.get(clave, (float("-inf"), float("inf")))
    if not (lo <= v <= hi):
        return f"fuera del rango admisible [{lo:g}, {hi:g}]"
    # Coherencia min < max
    ref = dict(vigentes or actuales())
    ref[clave] = v
    for cmin, cmax in _PARES_MINMAX:
        if clave in (cmin, cmax) and not (ref[cmin] < ref[cmax]):
            return f"'{cmin}' debe ser menor que '{cmax}' ({ref[cmin]:g} ≥ {ref[cmax]:g})"
    return None


def guardar(conn, clave: str, valor: Any, usuario: str) -> str | None:
    """Valida y persiste un umbral (con auditoría usuario+fecha). Devuelve error o None.
    Invalida la caché para que el próximo `actuales(conn)` lo recoja."""
    err = validar_input(clave, valor)
    if err:
        return err
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO umbrales_coherencia (clave, valor, actualizado_por) VALUES (%s, %s, %s) "
            "ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, "
            "actualizado_por = EXCLUDED.actualizado_por, actualizado_en = now()",
            [clave, float(valor), usuario])
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        return f"error al guardar: {e}"
    invalidar_cache()
    return None


def restaurar_default(conn, clave: str) -> str | None:
    """Borra el override de Neon (vuelve al DEFAULT) para una clave."""
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM umbrales_coherencia WHERE clave = %s", [clave])
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        return f"error al restaurar: {e}"
    invalidar_cache()
    return None
