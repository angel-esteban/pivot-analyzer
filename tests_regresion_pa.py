"""
tests_regresion_pa.py — Contrato de regresión de la Spec PA (v1, CERRADA).

Los 12 hallazgos (PA-C-01 … PA-M-04) están implementados y desplegados. Este archivo
convierte sus CRITERIOS DE ACEPTACIÓN en tests automáticos para blindarlos contra
regresiones. NO reabre el spec: lo fija. El único delta vivo del re-envío es la
sección de umbrales configurables (Configuración › Umbrales de coherencia).

Ejecutar:   python tests_regresion_pa.py       ->  imprime PASS/FAIL y sale 1 si falla

Cobertura UNITARIA: PA-C-01, PA-C-02, PA-A-01(banda), PA-A-02, PA-A-03, PA-A-04,
                    PA-A-05, PA-M-01.
Verificación VISUAL (no unit, se comprueba al generar un informe real):
    PA-A-06 (periodo del swing en el bloque Fibonacci), PA-M-02 (frases completas),
    PA-M-03 (acentos/ñ), PA-M-04 (render de la tabla Pivot).

Nota: clasificar_rsi / clasificar_bollinger_pctB y la selección de "nivel clave" y la
"banda fib" viven en app.py (que importa Streamlit). Aquí se ESPEJAN sus algoritmos
puros para poder testarlos sin arrancar la app; si cambia la lógica en app.py, estos
espejos deben cambiar igual (por eso son el contrato).
"""
from __future__ import annotations

import validador_nivel0 as v0
import validador_coherencia as vc

_fallos: list[str] = []


def _check(cond: bool, msg: str) -> None:
    _fallos.append(msg) if not cond else None


# ─────────────────────────────────────────────────────────────────────────────
# PA-C-01 · Free float fuera de (0,100] no es válido
# ─────────────────────────────────────────────────────────────────────────────
def test_pa_c01_free_float():
    sp = v0.DEFAULT_SPECS["free_float_pct"]
    _check(v0.validar_campo(103.5, sp).estado is v0.Estado.SOSPECHOSO,
           "PA-C-01: free float 103.5 debe ser SOSPECHOSO (no se muestra)")
    _check(v0.validar_campo(60.0, sp).estado is v0.Estado.OK,
           "PA-C-01: free float 60 debe ser OK")
    _check(v0.RANGO_FREE_FLOAT_PCT == (0.0, 100.0),
           "PA-C-01: rango free float debe ser (0,100]")
    r = vc.validar_coherencia({"floatShares": 1_131_306_744, "sharesOutstanding": 1_092_346_076})
    _check(r.checks.get("free_float") == "flag",
           "PA-C-01: floatShares > sharesOutstanding debe marcar incoherencia")


# ─────────────────────────────────────────────────────────────────────────────
# PA-C-02 · Nivel clave = mínima distancia absoluta sobre el conjunto completo
# ─────────────────────────────────────────────────────────────────────────────
def _nivel_mas_cercano(precio, niveles):
    return min(niveles, key=lambda n: abs(n - precio))


def test_pa_c02_nivel_cercano():
    niveles = [21.8880, 21.6017, 21.5200, 21.6600]   # semanal + confluencia + diarios
    sel = _nivel_mas_cercano(21.5500, niveles)
    _check(abs(sel - 21.5200) < 1e-9, "PA-C-02: el más cercano a 21.55 debe ser 21.5200")
    _check(sel != 21.8880, "PA-C-02: nunca debe elegir el semanal 21.8880")


# ─────────────────────────────────────────────────────────────────────────────
# PA-A-01 · Narrativa Fibonacci desde la banda REAL (fib_abajo–fib_arriba)
# ─────────────────────────────────────────────────────────────────────────────
def _fib_banda(swing_min, swing_max, precio):
    rango = swing_max - swing_min
    niveles = {l: swing_min + p / 100 * rango for l, p in
               [("161.8%", 161.8), ("127.2%", 127.2), ("100.0%", 100), ("78.6%", 78.6),
                ("61.8%", 61.8), ("50.0%", 50), ("38.2%", 38.2), ("23.6%", 23.6), ("0.0%", 0)]}
    below = {l: v for l, v in niveles.items() if v <= precio * 1.0005}
    above = {l: v for l, v in niveles.items() if v >= precio * 0.9995}
    fa = max(below.items(), key=lambda x: x[1])[0] if below else None
    fu = min(above.items(), key=lambda x: x[1])[0] if above else None
    return f"{fa}–{fu}"


def test_pa_a01_fib_banda():
    _check(_fib_banda(11.9245, 24.9000, 21.5500) == "61.8%–78.6%",
           "PA-A-01: REP debe citar banda 61.8%–78.6%, no 38.2-50%")


# ─────────────────────────────────────────────────────────────────────────────
# PA-A-02 / PA-A-03 · Dirección única por indicador (espejo de app.py)
# ─────────────────────────────────────────────────────────────────────────────
def _clasificar_rsi(rsi):
    if rsi is None: return (None, None)
    if rsi > 70:  return ("sobrecomprado", "bajista")
    if rsi < 30:  return ("sobrevendido", "alcista")
    if rsi >= 55: return ("alcista", "alcista")
    if rsi <= 45: return ("bajista", "bajista")
    return ("neutro", "neutro")


def _clasificar_bollinger_pctB(p):
    if p is None: return (None, None)
    if p > 80:  return ("sobrecomprado", "bajista")
    if p < 20:  return ("sobrevendido", "alcista")
    if p >= 50: return ("mitad_alta", "alcista")
    return ("mitad_baja", "bajista")


def _diagnostico_rsi_zona(rsi):
    if rsi >= 80: return "sobrecompra_extrema"
    if rsi >= 70: return "sobrecompra"
    if rsi >= 55: return "zona_alcista"
    if rsi >= 45: return "zona_neutra"
    if rsi >= 30: return "zona_bajista"
    if rsi >= 20: return "sobreventa"
    return "sobreventa_extrema"


def test_pa_a02_bollinger_direccion_unica():
    # Barrido del spec: la dirección es única (misma fuente -> semáforo == consenso).
    esperado = {-20: "alcista", 5: "alcista", 30: "bajista", 50: "alcista", 80: "alcista", 110: "bajista"}
    for p, d in esperado.items():
        _check(_clasificar_bollinger_pctB(p)[1] == d,
               f"PA-A-02: %B={p} debe ser {d} en TODAS las secciones")


def test_pa_a03_rsi_neutro():
    # RSI 45.7 -> neutro en clasificador y zona_neutra en diagnóstico (mismas 3 secciones).
    _check(_clasificar_rsi(45.7)[1] == "neutro", "PA-A-03: RSI 45.7 dirección neutro")
    _check(_clasificar_rsi(45.7)[0] == "neutro", "PA-A-03: RSI 45.7 categoría neutro")
    _check(_diagnostico_rsi_zona(45.7) == "zona_neutra", "PA-A-03: RSI 45.7 zona_neutra en diagnóstico")


# ─────────────────────────────────────────────────────────────────────────────
# PA-A-04 · Beta fuera de [0,3] se marca (no es dato limpio)
# ─────────────────────────────────────────────────────────────────────────────
def test_pa_a04_beta():
    sp = v0.DEFAULT_SPECS["beta"]
    _check(v0.validar_campo(-0.15, sp).estado is v0.Estado.SOSPECHOSO, "PA-A-04: beta -0.15 SOSPECHOSA")
    _check(v0.validar_campo(1.30, sp).estado is v0.Estado.OK, "PA-A-04: beta 1.30 OK")
    _check(v0.validar_campo(3.50, sp).estado is v0.Estado.SOSPECHOSO, "PA-A-04: beta 3.50 SOSPECHOSA")
    _check(v0.RANGO_BETA_PLAUSIBLE == (0.0, 3.0), "PA-A-04: rango beta [0,3]")


# ─────────────────────────────────────────────────────────────────────────────
# PA-A-05 · Recorrido alcista = (objetivo − precio) / precio
# ─────────────────────────────────────────────────────────────────────────────
def _upside_pct(objetivo, precio):
    return (objetivo - precio) / precio * 100


def test_pa_a05_upside():
    _check(abs(_upside_pct(24.9000, 21.5500) - 15.545) < 0.05,
           "PA-A-05: upside a ATH desde precio ≈ 15.5%")


# ─────────────────────────────────────────────────────────────────────────────
# PA-M-01 · Sin dobles símbolos de porcentaje (el label ya trae %)
# ─────────────────────────────────────────────────────────────────────────────
def test_pa_m01_doble_porcentaje():
    label, dist = "61.8%", 7.9
    render = f"(nivel {label}, a {dist:.1f}% de distancia)"
    _check("%%" not in render, "PA-M-01: el render no debe contener '%%'")
    _check(render == "(nivel 61.8%, a 7.9% de distancia)", "PA-M-01: formato de nivel correcto")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    for fn in sorted(k for k in globals() if k.startswith("test_")):
        try:
            globals()[fn]()
        except Exception as e:                       # noqa: BLE001
            _fallos.append(f"{fn}: EXCEPCIÓN {e!r}")
    if _fallos:
        print(f"❌ {len(_fallos)} FALLO(S):")
        for m in _fallos:
            print("  -", m)
        return 1
    print("✅ Contrato de regresión Spec PA v1 — TODOS los tests unitarios PASAN.")
    print("   (PA-A-06/PA-M-02/03/04 son verificación visual sobre un informe real.)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
