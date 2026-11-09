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


# ═════════════════════════════════════════════════════════════════════════════
# SPEC PA v2 (Polaris, 4-nov-2026) — PA2-01 … PA2-05
# Estos tests ejecutan el código REAL de app.py (arnes_tests_pa.py lo carga sin
# Streamlit ni red), no espejos de su lógica.
# ═════════════════════════════════════════════════════════════════════════════
import random as _random
import validador_nivel0 as _v0
import arnes_tests_pa as _A

_APP = _A.cargar_app()
_DIV_CRIT = None


def _crit(res, cid):
    return next(c for c in res["criterios"] if c["id"] == cid)


def _codigos(res):
    return [k.get("codigo") for k in res.get("killshots", [])]


# ─────────────────────────────────────────────────────────────────────────────
# PA2-02 · Camarilla = C ± R × 1,1/12, /6, /4, /2
# ─────────────────────────────────────────────────────────────────────────────
def test_pa2_02_camarilla():
    f = _APP["pivot_camarilla"]
    casos = {
        "T-PA2-02a": ((110, 100, 105), dict(R1=105.9167, R2=106.8333, R3=107.75, R4=110.5,
                                             S1=104.0833, S2=103.1667, S3=102.25, S4=99.5)),
        "T-PA2-02b": ((50.40, 48.00, 49.20), dict(R1=49.42, R2=49.64, R3=49.86, R4=50.52,
                                                  S1=48.98, S2=48.76, S3=48.54, S4=47.88)),
    }
    entradas = []
    for cid, ((H, L, C), esp) in casos.items():
        r = f(H, L, C)
        for k, v in esp.items():
            _check(abs(r[k] - v) <= 1e-4, f"{cid}: {k}={r[k]:.4f}, esperado {v:.4f}")
        entradas.append((H, L, C))
    rnd = _random.Random(20261104)
    for _ in range(20):
        L = rnd.uniform(1, 500); H = L + rnd.uniform(0.01, 50); C = rnd.uniform(L, H)
        entradas.append((H, L, C))
    for H, L, C in entradas:
        r, R = f(H, L, C), H - L
        orden = [r["S4"], r["S3"], r["S2"], r["S1"], C, r["R1"], r["R2"], r["R3"], r["R4"]]
        _check(all(a < b for a, b in zip(orden, orden[1:])),
               f"T-PA2-02c: orden S4<…<S1<C<R1<…<R4 roto para H={H} L={L} C={C}")
        _check(r["R1"] - C < 0.1 * R, f"T-PA2-02c: R1 no está 'muy próximo' (H={H} L={L} C={C})")
        _check(abs((r["R4"] - r["S4"]) - 1.1 * R) <= 1e-9 * max(1, R),
               f"T-PA2-02c: R4−S4 ≠ 1,1×R (H={H} L={L} C={C})")


# ─────────────────────────────────────────────────────────────────────────────
# PA2-03 · Payout extremo o con BPA negativo
# ─────────────────────────────────────────────────────────────────────────────
def test_pa2_03_payout():
    # a) DPA 0,60 · BPA 0,10 · crudo 6,00 → 600 %, KO crítico, payout_extremo, nunca N/A
    r = _A.simular_screening(_A.info_sana(dpa=0.60, bpa=0.10, payoutRatio=6.00))
    c = _crit(r, "payout_ratio")
    _check(c["estado"] == "ko", f"T-PA2-03a: payout debe ser KO (es {c['estado']})")
    _check("payout_extremo" in c.get("marcas", []), "T-PA2-03a: falta la marca payout_extremo")
    _check(abs(r["puntuacion_raw"] - 68.58) <= 1.0,
           f"T-PA2-03a: score ≈ 68,6 (es {r['puntuacion_raw']})")
    _check(r["estado_global"] == "parcial", f"T-PA2-03a: veredicto Parcial (es {r['estado_global']})")
    _check(any(k.get("codigo") == "K9" and "Payout" in k.get("razon", "") for k in r["killshots"]),
           "T-PA2-03a: el KO de payout debe verse en cabecera (K9)")
    # b) DPA 0,50 · BPA −0,20 · crudo −2,50 → no interpretable, KO, K1-BPA; con FCF malo → K1
    r = _A.simular_screening(_A.info_sana(dpa=0.50, bpa=-0.20, payoutRatio=-2.50))
    c = _crit(r, "payout_ratio")
    _check(c["estado"] == "ko" and "no interpretable" in c["mensaje"].lower(),
           "T-PA2-03b: payout 'no interpretable: BPA negativo' en KO")
    _check("K1-BPA" in _codigos(r) and r["estado_global"] == "parcial",
           f"T-PA2-03b: K1-BPA degrada a Parcial (es {r['estado_global']}, {_codigos(r)})")
    r = _A.simular_screening(_A.info_sana(dpa=0.50, bpa=-0.20, payoutRatio=-2.50, freeCashflow=1.0))
    _check("K1" in _codigos(r) and r["estado_global"] == "no_cumple",
           f"T-PA2-03b: con FCF insuficiente → K1, No cumple (es {r['estado_global']}, {_codigos(r)})")
    # c) Sin DPA ni BPA, crudo 7,50 → PENDIENTE de decisión de Polaris (ver nota en main()).
    # d) DPA 0,40 · BPA 0,50 · crudo −0,80 → 80 % recalculado, ~OK, incidencia registrada
    r = _A.simular_screening(_A.info_sana(dpa=0.40, bpa=0.50, payoutRatio=-0.80))
    c = _crit(r, "payout_ratio")
    _check(c["estado"] == "warning", f"T-PA2-03d: estado ~OK (es {c['estado']})")
    _check(abs(float(c.get("valor_raw") or 0) - 0.80) < 1e-9 if "valor_raw" in c else "80" in c["valor_fmt"],
           f"T-PA2-03d: payout recalculado 80 % (es {c['valor_fmt']})")
    _check("payout_crudo_inconsistente" in r.get("incidencias_dato", {}).get("payout_ratio", []),
           "T-PA2-03d: incidencia 'payout crudo inconsistente' registrada")
    # Resolver puro (lo comparten screener e ingesta)
    _check(_v0.resolver_payout(0.6, 0.1, 6.0)["marcas"] == ["payout_extremo"], "PA2-03: resolver 600 %")
    _check(_v0.resolver_payout(None, None, 7.5)["origen"] == "crudo", "PA2-03: sin DPA/BPA → crudo")
    # Control: valor sano sin cambios
    r = _A.simular_screening(_A.info_sana())
    _check(r["puntuacion"] == 100 and r["estado_global"] == "cumple" and not r["killshots"],
           "PA2-03 control: un valor sano sigue en 100 / Cumple sin señales")


def test_pa2_03_ingesta():
    import ingesta

    class _Cur:
        def execute(self, *a, **k): pass
        def fetchone(self): return None
        def fetchall(self): return []

    class _Conn:
        def cursor(self): return _Cur()
        def commit(self): pass
        def rollback(self): pass

    class _Fuente:
        def __init__(self, info): self._i = info
        def info(self, _t): return dict(self._i)
        def dividendos(self, _t): return []

    r = ingesta.ingerir_fundamental(["T.MC"], _Conn(), dry_run=True,
                                    fuente=_Fuente(_A.info_sana(dpa=0.6, bpa=0.1, payoutRatio=6.0)))
    f = r.filas[0]
    _check(abs((f.get("payout_ratio") or 0) - 6.0) < 1e-9, "PA2-03 ingesta: 600 % se guarda (no NULL)")
    _check(not f.get("incidencias"), "PA2-03 ingesta: payout extremo no es incidencia (no SOSPECHOSO)")
    _check("payout_extremo" in f.get("origen", ""), "PA2-03 ingesta: marca payout_extremo en origen")


# ─────────────────────────────────────────────────────────────────────────────
# PA2-04 · Umbral único de yield
# ─────────────────────────────────────────────────────────────────────────────
def test_pa2_04_yield():
    ev = _APP["evaluar_yield_dividendos"]
    casos = [  # (id, yield, estado screener, K3?, estado individual, banda)
        ("T-PA2-04a", 0.030, "ok",      False, "ok",      "entrada: yield en rango"),
        ("T-PA2-04b", 0.040, "ok",      False, "ok",      "entrada: yield atractivo"),
        ("T-PA2-04c", 0.020, "warning", True,  "warning", None),
        ("T-PA2-04d", 0.095, "ko",      False, "ko",      None),
    ]
    for cid, y, est_sc, k3, est_ind, banda in casos:
        r = _A.simular_screening(_A.info_sana(yield_obj=y))
        c = _crit(r, "dividend_yield")
        _check(c["estado"] == est_sc, f"{cid}: screener {c['estado']} ≠ {est_sc}")
        _check(("K3" in _codigos(r)) == k3, f"{cid}: K3 {'esperada' if k3 else 'no esperada'} ({_codigos(r)})")
        e = ev(y)
        _check(e["estado"] == est_ind and e["banda"] == banda,
               f"{cid}: individual {e} ≠ ({est_ind}, {banda})")
        _check(e["estado"] == c["estado"], f"T-PA2-04e: {cid} estado distinto screener/individual")
        lec = _APP["lectura_yield_dividendos"](y * 100)
        _check(lec["estado"] == c["estado"], f"T-PA2-04e: {cid} lectura individual distinta")
    if True:
        r = _A.simular_screening(_A.info_sana(yield_obj=0.020))
        _check(r["estado_global"] == "parcial", "T-PA2-04c: K3 degrada a Parcial")
    crit = _APP["_crit_dividendos"]("dividend_yield")
    _check(abs(float(crit.get("yield_entrada_atractiva", 0)) - 0.035) < 1e-12,
           "PA2-04: criteria.json debe traer yield_entrada_atractiva = 0.035")


# ─────────────────────────────────────────────────────────────────────────────
# PA2-05 · K-SECT (banca y seguros: evaluación sectorial parcial)
# ─────────────────────────────────────────────────────────────────────────────
_BANCO = dict(sector="Financial Services", industry="Banks - Diversified")
_SEGURO = dict(sector="Financial Services", industry="Insurance - Diversified")


def test_pa2_05_ksect():
    r = _A.simular_screening(_A.info_sana(**_BANCO))
    _check(r["estado_global"] == "parcial" and r["puntuacion"] == 100 and r["motivo"].startswith("K-SECT")
           and "faltan métricas regulatorias" in r["motivo"],
           f"T-PA2-05a: banco limpio → Parcial por K-SECT, score 100 ({r['estado_global']}, {r['puntuacion']}, {r['motivo']})")
    r = _A.simular_screening(_A.info_sana(floatShares=150_000_000, **_SEGURO))
    _check(r["estado_global"] == "no_cumple" and r["motivo"].startswith("K5"),
           f"T-PA2-05b: aseguradora free float 15 % → No cumple por K5 ({r['estado_global']}, {r['motivo']})")
    r = _A.simular_screening(_A.info_sana(bpa=-0.5, **_BANCO))
    _check(r["estado_global"] == "parcial" and r["motivo"].startswith("K1-BPA"),
           f"T-PA2-05c: banco BPA<0 → Parcial con motivo K1-BPA ({r['motivo']})")
    r = _A.simular_screening(_A.info_sana(sector="Utilities", industry="Utilities - Regulated Electric"))
    _check(r["estado_global"] == "cumple" and "K-SECT" not in _codigos(r),
           "T-PA2-05d: utility limpia → Cumple, sin K-SECT")
    r = _A.simular_screening(_A.info_sana(sector="Real Estate", industry="REIT - Office"))
    _check("K-SECT" not in _codigos(r), "PA2-05: Real Estate no se ve afectado")
    lote = ([_A.simular_screening(_A.info_sana(**_BANCO)) for _ in range(3)]
            + [_A.simular_screening(_A.info_sana(**_SEGURO)) for _ in range(2)]
            + [_A.simular_screening(_A.info_sana())])
    cnt = _APP["contar_estados_cribado"](lote)
    _check(cnt["n_sectorial_parcial"] == 5, f"T-PA2-05e: 'Evaluación sectorial parcial: 5' (es {cnt['n_sectorial_parcial']})")
    _check(cnt["descuadre"] == 0 and cnt["suma_estados"] == cnt["total"] == 6,
           "T-PA2-05e: los recuentos por veredicto suman el total")


# ─────────────────────────────────────────────────────────────────────────────
# PA2-01 · Redacción no prescriptiva
# ─────────────────────────────────────────────────────────────────────────────
_FUNCS_PA2_01 = {"_build_dividendos", "_build_swing", "_build_gestion_posicion", "_interpretar",
                 "_render_analisis_compra_div", "_render_analisis_venta_swing",
                 "generar_informe_estrategia_html", "generar_pdf_estrategia", "_lectura_integrada"}


def test_pa2_01_redaccion():
    prohib = _APP["terminos_prohibidos_en"]
    g = _APP["lectura_metodo_gestion"](3, 5, ["SAR bajista — tendencia invertida formalmente",
                                               "MACD cruzado a bajista", "RSI en sobrecompra extrema (78)"],
                                       9.50, 3.2)
    s = _APP["lectura_metodo_swing"](10.00, 11.00, 4, 5)
    d = _APP["lectura_metodo_dividendos"](4.0, 42, 9.87)
    for nombre, txt in (("gestión", g), ("swing", s), ("dividendos", d)):
        _check(not prohib(txt), f"T-PA2-01a: términos prohibidos en {nombre}: {prohib(txt)}")
    _check("La decisión corresponde al usuario" in g, "T-PA2-01a: falta 'La decisión corresponde al usuario'")
    _check("3 de 5" in g, "T-PA2-01a: gestión debe indicar 3 señales activas")
    _check("9,80" in s and not prohib(s), "T-PA2-01b: invalidación 2 % bajo 10,00 = 9,80")
    # Barrido estático de TODOS los literales de los bloques afectados (puntos, criterios,
    # lecturas, informe de estrategia, lectura integrada y cartera).
    import ast
    arbol = ast.parse(_A._RUTA_APP.read_text(encoding="utf-8"))
    for fn in ast.walk(arbol):
        if isinstance(fn, ast.FunctionDef) and fn.name in _FUNCS_PA2_01:
            doc = ast.get_docstring(fn, clean=False)
            for n in ast.walk(fn):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc:
                    t = prohib(n.value)
                    _check(not t, f"PA2-01: término prohibido {t} en {fn.name} (línea {n.lineno})")
    # d) Lectura Integrada (informe técnico HTML _LI_M y PDF _LIP_M): textos descriptivos,
    #    sin términos PA2-01 ni imperativos dirigidos al usuario.
    import re as _re
    _IMPERATIVOS = ("mantenerla", "busca", "espera", "vigila", "revisa", "ajusta", "valora",
                    "no es el momento", "para vender", "antes de actuar", "si tienes posicion",
                    "si ya tienes posicion", "si no has entrado", "si estas fuera", "cuidado")
    import unicodedata as _ud
    _nrm = lambda x: "".join(c for c in _ud.normalize("NFD", x.lower()) if _ud.category(c) != "Mn")
    vistos = 0
    for fn in ast.walk(arbol):
        if isinstance(fn, ast.FunctionDef) and fn.name in ("generar_informe_html", "generar_pdf"):
            for n in ast.walk(fn):
                if (isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("_LI_M", "_LIP_M")):
                    vistos += 1
                    for c in ast.walk(n.value):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            t = prohib(c.value)
                            _check(not t, f"PA2-01: término prohibido {t} en {n.targets[0].id} (línea {c.lineno})")
                            v = _nrm(c.value)
                            imp = [w for w in _IMPERATIVOS if _re.search(r"(?<!\w)" + w + r"(?!\w)", v)]
                            _check(not imp, f"PA2-01: imperativo {imp} en {n.targets[0].id} (línea {c.lineno})")
    _check(vistos == 2, f"PA2-01: deben encontrarse _LI_M y _LIP_M (encontrados {vistos})")
    # e) Ayudas de criterios: sin entidades HTML escapadas ni "los últimos 14 sesiones"
    for fn in ast.walk(arbol):
        if isinstance(fn, ast.FunctionDef) and fn.name in ("_build_dividendos", "_build_swing"):
            for n in ast.walk(fn):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    _check("&lt;" not in n.value and "&gt;" not in n.value,
                           f"PA2-01: entidad HTML literal en {fn.name} (línea {n.lineno})")
                    _check("los últimos 14 sesiones" not in n.value,
                           f"PA2-01: concordancia 'los últimos 14 sesiones' en {fn.name}")
    # f) Rótulo no duplicado
    _sr = _APP["_sin_rotulo_metodo"]
    _check(_sr("Lectura del método: X") == "X" and _sr("**Lectura del método:** X") == "X"
           and _sr("X") == "X", "PA2-01: _sin_rotulo_metodo elimina el rótulo inicial")
    # c) Informe de estrategia: sin "Recomendación final"/"Recomendación"; con "Lectura del método"
    est = [{"nombre": "🗂️ Gestión de posición", "color": "#7c3aed",
            "criterios": [("<b>SAR</b> bajista", 0)], "puntos": ["✅ Posición en beneficio"],
            "rec": g, "popover_md": ""}]
    html = _APP["generar_informe_estrategia_html"](ticker="TEST.MC", nombre="Test", precio=10.0,
                                                   ts="04/11/2026 12:00", estrategias=est)
    _check("Recomendación final" not in html and ">Recomendación<" not in html,
           "T-PA2-01c: el HTML no debe contener 'Recomendación final'")
    _check("Lectura del método" in html, "T-PA2-01c: el HTML debe contener 'Lectura del método'")
    _check(_APP["PIE_LECTURA_METODO"] in html, "PA2-01: pie fijo en el informe de estrategia HTML")
    _est_d = [dict(est[0], nombre="💰 Dividendos", rec=d)]   # d ya empieza por "Lectura del método:"
    _html_d = _APP["generar_informe_estrategia_html"](ticker="TEST.MC", nombre="Test", precio=10.0,
                                                      ts="04/11/2026 12:00", estrategias=_est_d)
    _check(_html_d.count("Lectura del método") == 1,
           f"PA2-01: rótulo 'Lectura del método' duplicado en el HTML ({_html_d.count('Lectura del método')} veces)")
    import importlib.util as _ilu
    pdf = None
    if _ilu.find_spec("reportlab") is not None:      # sin reportlab no se puede generar el PDF
        pdf = _APP["generar_pdf_estrategia"](ticker="TEST.MC", nombre="Test", precio=10.0,
                                            ts="04/11/2026 12:00", estrategias=est)
    else:
        _avisos.append("PDF de estrategia no comprobado: falta reportlab (pip install reportlab)")
    if pdf is not None:
        _check(pdf[:4] == b"%PDF", "T-PA2-01c: el PDF de estrategia se genera")
        try:
            import io
            from pypdf import PdfReader
            txt = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
            txt = " ".join(txt.split())
            _check("Recomendación final" not in txt and "RECOMENDACION" not in txt,
                   "T-PA2-01c: el PDF no debe contener 'Recomendación final'")
            _check("Lectura del método" in txt, "T-PA2-01c: el PDF debe contener 'Lectura del método'")
            _check("No es una recomendación de inversión" in txt, "PA2-01: pie fijo en el PDF")
        except ImportError:
            pass                                     # sin pypdf no se lee el texto del PDF


# ─────────────────────────────────────────────────────────────────────────────
# Job #32 · hallazgo 11 — sin "acceptable" (inglés) en los textos de criteria.json
# ─────────────────────────────────────────────────────────────────────────────
def test_job32_11_sin_acceptable():
    from pathlib import Path
    txt = Path(__file__).with_name("criteria.json").read_text(encoding="utf-8")
    _check("acceptable" not in txt.lower(), "Job #32 #11: 'acceptable' (inglés) en criteria.json; debe ser 'aceptable'")


# ═════════════════════════════════════════════════════════════════════════════
# Validación Polaris tras Spec PA v2 (Job #58 / estrategia NTGY) — V-1, S-1, S-2
# ═════════════════════════════════════════════════════════════════════════════
def test_v1_capa_mercado():
    import sys, types
    sana = _A.info_sana()
    neon = {k: sana[k] for k in ("trailingEps", "marketCap", "debtToEquity", "enterpriseToEbitda",
                                  "sector", "payoutRatio")}
    neon.update(_free_float_pct_neon=60.0, longName="Naturgy Energy Group, S.A.")
    hist = _A.historico_diario(sana["regularMarketPrice"], volumen=1_500_000)
    # a) Yahoo bloquea .info (401 Invalid Crumb) pero el histórico responde → yield, liquidez
    #    y free float se evalúan (no N/A) y el valor NO queda topado en 70.
    r = _A.simular_screening({}, historico=hist, neon=neon, neon_fecha="2026-11-02")
    for cid in ("dividend_yield", "volumen_diario", "free_float"):
        _check(_crit(r, cid)["estado"] != "sin_datos", f"V-1a: {cid} no debe quedar N/A con histórico disponible")
    _check(r["puntuacion"] > 70 and not r.get("error"), f"V-1a: score no topado en 70 (es {r['puntuacion']})")
    _check("Dato de Neon" in _crit(r, "free_float")["mensaje"] and "2026-11-02" in _crit(r, "free_float")["mensaje"],
           "V-1c: free float de Neon con su fecha")
    _check(r["nombre"].startswith("Naturgy"), "V-6: nombre desde Neon cuando .info falla")
    # b) N/A por falta de dato → K8
    _check(any(k["codigo"] == "K8" and "Flujo de caja libre" in k["razon"] for k in r["killshots"]),
           "V-1b: criterio N/A por falta de dato debe aparecer en K8")
    # c) Sin .info ni histórico → "Sin datos" (error) con motivo, nunca evaluado con N/A
    r2 = _A.simular_screening({}, historico=None, neon=neon)
    _check(r2.get("error") and r2.get("fallo_mercado") and r2["estado_global"] == "error",
           "V-1a: sin datos de mercado el valor va a 'Sin datos'")
    cnt = _APP["contar_estados_cribado"]([r, r2, _A.simular_screening(sana)])
    _check(cnt["n_fallo_mercado"] == 1 and cnt["n_error"] == 1 and cnt["descuadre"] == 0,
           "V-1a: cabecera cuenta el fallo de mercado en 'Sin datos' y marca el cribado")
    # Control: valor sano sin cambios
    r3 = _A.simular_screening(sana)
    _check(r3["puntuacion"] == 100 and r3["estado_global"] == "cumple" and not r3["killshots"],
           "V-1 control: valor sano sigue en 100 / Cumple sin señales")


def test_s1_posicion_52s():
    import numpy as np, pandas as pd
    f = _APP["posicion_rango_52s"]
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=252)
    close = np.linspace(22.81, 30.48, 252)
    h = pd.DataFrame({"High": close, "Low": close, "Close": close}, index=idx)
    r = f(29.42, {}, h)                         # .info vacío: antes salía 0 % "cerca de mínimos"
    _check(r is not None and abs(r["pos"] - 86.2) < 0.5, f"S-1: posición 52s ≈ 86 % (es {r})")
    r = f(29.42, {"fiftyTwoWeekHigh": 30.48, "fiftyTwoWeekLow": 22.81}, None)
    _check(r is not None and abs(r["pos"] - 86.2) < 0.5, "S-1: con datos de yfinance, mismo resultado")
    _check(f(29.42, {}, None) is None, "S-1: sin rango ni histórico → None (neutro, sin puntuar)")


def test_s2_payout_estrategia():
    import sys, types
    f = _APP["payout_para_estrategia"]
    r = f("NTGY.MC", {"trailingAnnualDividendRate": 1.80, "trailingEps": 2.2528}, None)
    _check(r["valor"] is not None and abs(r["valor"] - 0.799) < 0.001, f"S-2: payout = DPA/BPA (79,9 %), es {r}")
    # .info vacío → último dato validado de Neon (mismo dato que el screener)
    repo = types.ModuleType("repositorio")
    repo.componer_info = lambda *_a, **_k: ({"trailingEps": 2.2528, "payoutRatio": 0.799}, {}, set())
    prev = sys.modules.get("repositorio"); sys.modules["repositorio"] = repo
    viejos = {k: _APP.get(k) for k in ("get_db_connection", "release_db_connection")}
    _APP["get_db_connection"] = lambda: object(); _APP["release_db_connection"] = lambda _c: None
    try:
        r = f("NTGY.MC", {}, 1.80)
        _check(r["valor"] is not None and abs(r["valor"] - 0.799) < 0.001 and r["fuente"] == "Neon",
               f"S-2: sin .info, payout desde Neon (es {r})")
        repo.componer_info = lambda *_a, **_k: ({}, {}, set())
        r = f("NTGY.MC", {}, 1.80)
        _check(r["valor"] is None, "S-2: sin dato en ninguna fuente → None (neutro, nunca 'Sostenible')")
    finally:
        _APP.update(viejos)
        if prev is None: sys.modules.pop("repositorio", None)
        else: sys.modules["repositorio"] = prev


def test_v4_bpa_decimal_neon():
    """Job #60: con Yahoo bloqueado, el BPA llega de Neon como Decimal (numeric de Postgres).
    Debe usarse igual que un float: TEF (BPA < 0) → payout no interpretable + K1-BPA, no N/A."""
    from decimal import Decimal as D
    import pandas as pd
    _check(_v0.resolver_payout(0.30, D("-0.4300"), D("0.3488"))["origen"] == "bpa_no_positivo",
           "V-4: resolver_payout debe aceptar Decimal (BPA de Neon)")
    fechas = [pd.Timestamp(f"{y}-{m:02d}-15", tz="Europe/Madrid")
              for y in range(2014, 2027) for m in (6, 12) if (y, m) <= (2026, 6)]
    div = pd.Series([0.15] * len(fechas), index=pd.DatetimeIndex(fechas))
    neon = {"trailingEps": D("-0.4300"), "payoutRatio": D("0.3488"), "marketCap": D("19500000000"),
            "debtToEquity": D("227.6"), "enterpriseToEbitda": D("8.56"),
            "sector": "Communication Services", "_free_float_pct_neon": D("69.6"), "longName": "Telefónica, S.A."}
    r = _A.simular_screening({}, dividendos=div, historico=_A.historico_diario(3.44, volumen=11_000_000),
                             neon=neon, neon_fecha="2026-07-08", neon_invalidos={"payoutRatio"})
    c = _crit(r, "payout_ratio")
    _check(c["estado"] == "ko" and "no interpretable" in c["mensaje"].lower(),
           f"V-4: TEF con BPA de Neon → payout no interpretable (es {c['estado']}, {c['valor_fmt']})")
    _check("K1-BPA" in _codigos(r) and r["estado_global"] != "cumple",
           f"V-4: TEF no puede salir Cumple con BPA negativo ({r['estado_global']}, {_codigos(r)})")


# ─────────────────────────────────────────────────────────────────────────────
_avisos: list[str] = []


# ═════════════════════════════════════════════════════════════════════════════
# SPEC PA v3
# ═════════════════════════════════════════════════════════════════════════════
class _YFFalso:
    """yfinance simulado: con auto_adjust=True devuelve OHLC ajustado por dividendos
    (precios anteriores al ex-dividendo rebajados un 5 %); con False, el que cotizó."""
    def __init__(self, raw):
        self.raw = raw
        self.llamadas = []

    def Ticker(self, _tk):
        yf = self

        class _T:
            info = {"fiftyTwoWeekHigh": float(yf.raw["High"].max()),
                    "fiftyTwoWeekLow": float(yf.raw["Low"].min()),
                    "previousClose": float(yf.raw["Close"].iloc[-2])}

            def history(self, period="1y", auto_adjust=True, **_k):
                yf.llamadas.append(auto_adjust)
                if not auto_adjust:
                    return yf.raw.copy()
                adj = yf.raw.copy()
                corte = len(adj) // 2                       # ex-dividendo a mitad de serie
                for c in ("Open", "High", "Low", "Close"):
                    adj.iloc[:corte, adj.columns.get_loc(c)] *= 0.95
                return adj
        return _T()


def _hist_con_maximo_antiguo(precio=29.96, sesiones=252):
    """Serie cuyo máximo está ANTES del ex-dividendo (así el ajuste lo rebaja)."""
    import numpy as np
    h = _A.historico_diario(precio, sesiones)
    pico = sesiones // 4
    h.iloc[pico, h.columns.get_loc("High")] = precio * 1.04
    return h


def test_pa3_02_precios_sin_ajustar():
    import ast
    # Estático: toda descarga de histórico del análisis técnico pide auto_adjust=False.
    _FUNCS = {"obtener_datos", "obtener_hist_maximo", "_mini_analisis_cartera",
              "_evaluar_ticker_screening", "_pp_wizard_fragment"}
    arbol = ast.parse(_A._RUTA_APP.read_text(encoding="utf-8"))
    vistas = 0
    for fn in ast.walk(arbol):
        if isinstance(fn, ast.FunctionDef) and fn.name in _FUNCS:
            for n in ast.walk(fn):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "history"):
                    vistas += 1
                    kw = {k.arg: k.value for k in n.keywords}
                    ok = isinstance(kw.get("auto_adjust"), ast.Constant) and kw["auto_adjust"].value is False
                    _check(ok, f"PA3-02: history() sin auto_adjust=False en {fn.name} (línea {n.lineno})")
    # PE-15: el Paso 2 ya no descarga su propio histórico largo (usa obtener_hist_maximo, revisada arriba)
    _check(vistas >= 5, f"PA3-02: se esperaban ≥5 descargas de histórico revisadas (vistas {vistas})")
    # Funcional con yfinance simulado.
    raw = _hist_con_maximo_antiguo()
    yf = _YFFalso(raw)
    prev = _APP.get("yf")
    _APP["yf"] = yf
    try:
        hist, info = _APP["obtener_datos"]("NTGY.MC")
        largo = _APP["obtener_hist_maximo"]("NTGY.MC")
    finally:
        _APP["yf"] = prev
    _check(all(a is False for a in yf.llamadas), f"PA3-02: llamadas con ajuste {yf.llamadas}")
    # T-PA3-02a: máximo y mínimo 52s del histórico = los de la ficha (tolerancia 1 %)
    _check(abs(float(hist["High"].max()) / info["fiftyTwoWeekHigh"] - 1) <= 0.01,
           "T-PA3-02a: máximo 52s del histórico ≠ ficha")
    _check(abs(float(hist["Low"].min()) / info["fiftyTwoWeekLow"] - 1) <= 0.01,
           "T-PA3-02a: mínimo 52s del histórico ≠ ficha")
    # T-PA3-02b: ATH ≥ máximo 52s
    ath = _APP["analizar_maximos_historicos"](largo, 29.96, "Test")
    _check(ath is not None and ath["ath"] >= info["fiftyTwoWeekHigh"] - 1e-9,
           f"T-PA3-02b: ATH {ath and ath['ath']} < máx 52s {info['fiftyTwoWeekHigh']}")
    # T-PA3-02c: cierre de la sesión anterior de los pivots diarios = cierre anterior de cabecera
    H, L, C, O = _APP["datos_sesion"](hist, "Diario")
    _check(abs(C - info["previousClose"]) < 1e-9, f"T-PA3-02c: C pivot {C} ≠ cierre anterior {info['previousClose']}")
    _check(_APP["RANGO_52S_DESDE_HIST"] == "calculado desde histórico", "PA3-02: rótulo del rango 52s")


def test_pa3_02_live():
    """Solo con PA_LIVE=1 (red): NTGY y REP, máximo/mínimo 52s del histórico vs ficha."""
    import os
    if os.environ.get("PA_LIVE") != "1":
        _avisos.append("T-PA3-02a en vivo no ejecutado (activa con: set PA_LIVE=1)")
        return
    import yfinance as yf
    for tk in ("NTGY.MC", "REP.MC"):
        t = yf.Ticker(tk)
        h = t.history(period="1y", auto_adjust=False)
        i = t.info
        _check(abs(float(h["High"].max()) / i["fiftyTwoWeekHigh"] - 1) <= 0.01, f"T-PA3-02a {tk}: máximo")
        _check(abs(float(h["Low"].min()) / i["fiftyTwoWeekLow"] - 1) <= 0.01, f"T-PA3-02a {tk}: mínimo")


def _crit(r, cid):
    return next((c for c in r["criterios"] if c["id"] == cid), {})


def _serie_relativa(pagos_dias):
    """[(días atrás desde hoy, importe), ...] → serie de dividendos."""
    import pandas as pd
    hoy = pd.Timestamp.now(tz="Europe/Madrid").normalize()
    return _A.serie_pagos([(hoy - pd.Timedelta(days=d), v) for d, v in pagos_dias])


def test_pa3_03_dividendos():
    import pandas as pd
    ttm = _APP["dpa_ttm"]
    ref = pd.Timestamp("2026-11-05", tz="Europe/Madrid")
    base = [("2025-11-01", 0.50), ("2026-04-10", 0.60), ("2026-07-30", 0.60)]
    # T-PA3-03a
    d = ttm(_A.serie_pagos(base), ref=ref)
    _check(abs(d - 1.20) < 1e-9 and f"{d / 30:.2%}" == "4.00%", f"T-PA3-03a: DPA TTM {d} (esperado 1,20; yield 4,00 %)")
    # T-PA3-03b
    d = ttm(_A.serie_pagos(base + [("2025-11-20", 0.50)]), ref=ref)
    _check(abs(d - 1.70) < 1e-9 and f"{d / 30:.2%}" == "5.67%", f"T-PA3-03b: DPA TTM {d} (esperado 1,70; yield 5,67 %)")
    # El yield del screener usa esa misma regla (fechas relativas a hoy: 369, 209 y 98 días)
    y = _APP["_sc_dividend_yield_ttm"]({"regularMarketPrice": 30.0},
                                      _serie_relativa([(369, 0.50), (209, 0.60), (98, 0.60)]))
    _check(y == 0.04, f"T-PA3-03a: yield del screener {y} (esperado 0,04)")
    # T-PA3-03c — racha 3 años: CAGR n/d estructural, sin K8 ni techo por N/A
    r = _A.simular_screening(_A.info_sana(), dividendos=_A.serie_dividendos(0.8, anios=3))
    c = _crit(r, "crecimiento_dividendo")
    _check(c.get("valor_fmt") == "CAGR n/d (historial de 3 años)" and c.get("na_estructural"),
           f"T-PA3-03c: CAGR {c.get('valor_fmt')!r}")
    _k8 = next((k for k in r["killshots"] if k.get("codigo") == "K8"), None)
    _check(_k8 is None or "cagr" not in (_k8.get("razon") or "").lower(),
           f"T-PA3-03c: el CAGR n/d no debe entrar en K8 ({_k8})")
    _check(r["n_na_cap"] == 0, f"T-PA3-03c: el CAGR n/d no penaliza como N/A (n_na_cap {r['n_na_cap']})")
    # T-PA3-03d / e — K-RECENT_CUT
    def _cut(ultimo):
        pagos = [(60, ultimo), (425, 1.20)] + [(60 + 365 * k, 1.20 - 0.05 * (k - 1)) for k in range(2, 8)]
        return _A.simular_screening(_A.info_sana(), dividendos=_serie_relativa(pagos))
    r = _cut(0.80)
    _check("K-RECENT_CUT" in _codigos(r) and r["estado_global"] == "parcial"
           and r["motivo"].startswith("K-RECENT_CUT") and "−33%" in r["motivo"],
           f"T-PA3-03d: −33 % → K-RECENT_CUT, Parcial ({r['estado_global']}, {r['motivo']})")
    r = _cut(1.00)
    _check("K-RECENT_CUT" not in _codigos(r) and r["estado_global"] == "cumple",
           f"T-PA3-03e: −17 % → sin K-RECENT_CUT ({r['estado_global']}, {_codigos(r)})")
    # T-PA3-03f — payout con BPA < 0
    r = _A.simular_screening(_A.info_sana(bpa=-0.40))
    c = _crit(r, "payout_ratio")
    _check(c.get("valor_fmt") == "n/i (BPA < 0)" and c.get("estado") == "ko" and "K1-BPA" in _codigos(r),
           f"T-PA3-03f: payout {c.get('valor_fmt')!r} {c.get('estado')} {_codigos(r)}")
    # T-PA3-03g — free float crudo 105 %
    r = _A.simular_screening(_A.info_sana(floatShares=1_050_000_000))
    c = _crit(r, "free_float")
    _k8 = next((k for k in r["killshots"] if k.get("codigo") == "K8"), {})
    _check(c.get("valor_fmt") == "N/A (sospechoso)" and "100" not in str(c.get("valor_fmt"))
           and "sospechoso" in (_k8.get("razon") or ""),
           f"T-PA3-03g: free float {c.get('valor_fmt')!r}, K8 {_k8.get('razon')!r}")


# PA3-01 — términos ampliados y funciones que producen texto de informe (técnico, estrategia,
# cribado), incluidos sus textos de ayuda.
TERMINOS_PA3 = ("actuar", "antes de actuar", "qué vigilar", "mejor momento", "buen punto de entrada",
                "momento óptimo", "zona óptima", "esperar", "comprar en", "comprando", "percibirás",
                "entrada aceptable", "no buscamos")
_FUNCS_INFORME = {
    "generar_informe_html", "generar_pdf", "generar_informe_estrategia_html", "generar_pdf_estrategia",
    "_generar_pdf_screening", "_render_screening_resultados", "detectar_divergencias",
    "calcular_puntuacion_tecnica", "_interpretacion_semaforo", "_lectura_integrada",
    "_alertas_fundamentales", "bloque_fundamentales", "_build_dividendos", "_build_swing",
    "_build_gestion_posicion", "_interpretar", "_render_analisis_compra_div",
    "_render_analisis_venta_swing", "_evaluar_criterio", "_evaluar_ticker_screening",
    "lectura_metodo_gestion", "lectura_metodo_swing", "lectura_metodo_dividendos"}
SIN_TILDE_PA3 = ("QUE SIGNIFICA", "Descripcion", "DESCRIPCION DETALLADA", "Actua", "maximo",
                 "Aproximandose", "Analisis", "ANALISIS", "inversion", "margenes", "Farmaceuticos")


def _prohibidos_pa3(texto):
    import re as _re, unicodedata as _ud
    n = lambda x: "".join(c for c in _ud.normalize("NFD", x.lower()) if _ud.category(c) != "Mn")
    t = n((texto or "").replace(_APP["PIE_LECTURA_METODO"], ""))
    lista = tuple(_APP["TERMINOS_PROHIBIDOS_PA2"]) + TERMINOS_PA3
    return [w for w in lista if _re.search(r"(?<!\w)" + _re.escape(n(w)) + r"(?!\w)", t)]


def _literales_de(funcs):
    """Literales de texto (incluidas las partes fijas de los f-strings) de las funciones dadas,
    sin docstrings ni literales usados como clave/comparación (identificadores internos)."""
    import ast
    arbol = ast.parse(_A._RUTA_APP.read_text(encoding="utf-8"))
    claves = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant):
            claves.add(id(n.slice))
        if isinstance(n, ast.Dict):
            claves.update(id(k) for k in n.keys if isinstance(k, ast.Constant))
        if isinstance(n, ast.Compare):
            claves.update(id(c) for c in [n.left] + n.comparators if isinstance(c, ast.Constant))
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get"
                and n.args and isinstance(n.args[0], ast.Constant)):
            claves.add(id(n.args[0]))
    for fn in ast.walk(arbol):
        if isinstance(fn, ast.FunctionDef) and (fn.name in funcs or fn.name.startswith("analizar_")):
            doc = ast.get_docstring(fn, clean=False)
            for n in ast.walk(fn):
                if (isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc
                        and id(n) not in claves):
                    yield fn.name, n.lineno, n.value


def test_pa3_01_redaccion():
    import json
    # T-PA3-01a (estático): ningún término ampliado en los textos de informe
    for fn, ln, txt in _literales_de(_FUNCS_INFORME):
        t = _prohibidos_pa3(txt)
        _check(not t, f"T-PA3-01a: término prohibido {t} en {fn} (línea {ln})")
    # … ni en la descripción de las estrategias ni en los textos de criterios del cribado
    plant = json.loads(_A._RUTA_APP.with_name("strategy_texts.json").read_text(encoding="utf-8"))
    desc = _APP["textos_estrategia"](plant)
    for k, txt in desc.items():
        t = _prohibidos_pa3(txt)
        _check(not t, f"T-PA3-01a: término prohibido {t} en la descripción de {k}")
    crit = json.loads(_A._RUTA_APP.with_name("criteria.json").read_text(encoding="utf-8"))

    def _strs(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from _strs(v)
        elif isinstance(o, list):
            for v in o:
                yield from _strs(v)
        elif isinstance(o, str):
            yield o
    for txt in _strs(crit):
        t = _prohibidos_pa3(txt)
        _check(not t, f"T-PA3-01a: término prohibido {t} en criteria.json: {txt[:60]!r}")
    for _jf in ("ratios_referencia.json", "sector_knowledge.json"):   # notas que salen en informes
        _jd = json.loads(_A._RUTA_APP.with_name(_jf).read_text(encoding="utf-8"))
        for txt in _strs(_jd):
            t = _prohibidos_pa3(txt)
            _check(not t, f"T-PA3-01a: término prohibido {t} en {_jf}: {txt[:60]!r}")
    _check(_APP["escenario_legible"]("aproximandose_cerca") == "Aproximándose cerca"
           and _APP["escenario_legible"]("en_maximo") == "En máximo", "T-PA3-01c: escenarios sin tilde")
    # T-PA3-01a (dinámico): divergencia OBV bajista → texto en hipótesis
    import numpy as np
    h = _A.historico_diario(30.0, 120)
    h["Close"] = np.linspace(27, 30, 120); h["High"] = h["Close"] * 1.01; h["Low"] = h["Close"] * 0.99
    h["Volume"] = np.where(np.arange(120) % 2 == 0, 3e6, 1e5)   # sube el precio, el OBV cae
    h.iloc[1::2, h.columns.get_loc("Close")] = h["Close"].iloc[1::2] * 1.004
    divs = _APP["detectar_divergencias"](h, ventana=60) if "ventana" in _APP["detectar_divergencias"].__code__.co_varnames else _APP["detectar_divergencias"](h)
    _obv = [d for d in (divs or []) if d.get("tipo") == "OBV" and d.get("direccion") == "bajista"]
    if _obv:
        _check("posible distribución" in _obv[0]["descripcion"] and not _prohibidos_pa3(_obv[0]["descripcion"]),
               f"T-PA3-01a: divergencia OBV bajista sin hipótesis: {_obv[0]['descripcion']!r}")
    else:
        _avisos.append("T-PA3-01a: la serie sintética no produjo divergencia OBV bajista (texto verificado en estático)")
    import ast as _ast
    _src = _A._RUTA_APP.read_text(encoding="utf-8")
    for frase in ("Grandes inversores están deshaciendo posiciones", "acumulando discretamente",
                  "tienden a acumular órdenes ahí", "tienden a recomprar", "Momento óptimo de entrada"):
        _check(frase not in _src and all(frase not in v for v in desc.values()),
               f"PA3-01.3: sigue la afirmación {frase!r}")
    # T-PA3-01b
    d = desc.get("💰 Dividendos", "")
    _check("2,5%" in d and "75%" in d, "T-PA3-01b: la descripción de Dividendos debe contener '2,5%' y '75%'")
    for mal in ("3.5%: atractivo para estrategia", "< 60%", "RSI 30-45: sobreventa", "RSI 30–45: sobreventa"):
        _check(mal not in d, f"T-PA3-01b: la descripción de Dividendos contiene {mal!r}")
    _check("Configuración completa según el método" in d, "PA3-01.3: sección renombrada")
    # Los umbrales salen del motor: cambiar criteria cambia el texto
    _cr = json.loads(json.dumps(crit["carteras"]["dividendos"]["criterios"]))
    next(c for c in _cr if c["id"] == "payout_ratio")["umbral_ok"] = 0.70
    _d2 = _APP["textos_estrategia"](plant, criterios=_cr)["💰 Dividendos"]
    _check("70%" in _d2 and "Por debajo de 75%" not in _d2, "PA3-01.1: el texto no sale de criteria.json")
    # T-PA3-01c: plantillas sin las cadenas sin tilde
    import re as _re
    corpus = [t for _, _, t in _literales_de(_FUNCS_INFORME)] + list(desc.values())
    for w in SIN_TILDE_PA3:
        n = sum(len(_re.findall(r"(?<![\w&])" + _re.escape(w) + r"(?![\w;])", t)) for t in corpus)
        _check(n == 0, f"T-PA3-01c: {n} aparición(es) de {w!r} sin tilde en plantillas")


def _rsi_en_secciones(rsi):
    """Etiqueta de RSI en semáforo, consenso, tabla de indicadores, diagnóstico y estrategia."""
    import ast
    et = _APP["etiqueta_rsi"](rsi)
    _, _, fac = _APP["calcular_semaforo"](30.0, {"PP": 29.0}, rsi, 0.1, 0.05, 31, 28, None, "ALCISTA")
    sem = next(d for f, d, _ in fac if f == "RSI")
    _, señales, _ = _APP["calcular_convergencia_tecnica"]({}, {}, 30.0, rsi, 0.1, 0.05, 0.02, "ALCISTA", 50)
    con = next(l for n, l, *_ in señales if n == "RSI 14")
    cat, _ = _APP["clasificar_rsi"](rsi)
    esc = {"sobrecomprado": "sobrecompra", "alcista": "zona_alcista", "neutro": "zona_neutra",
           "bajista": "zona_bajista", "sobrevendido": "sobreventa"}[cat]
    return et, sem, con, esc


def test_pa3_05_coherencia():
    import ast
    # T-PA3-05a / b — una sola etiqueta de RSI en todas las secciones
    for rsi, esperado in ((57.67, "Alcista"), (50, "Neutro"), (72, "Alcista en sobrecompra"), (28, "Bajista en sobreventa")):   # doc. 28 b
        et, sem, con, esc = _rsi_en_secciones(rsi)
        _check(et == esperado and esperado in sem and esperado in con,
               f"T-PA3-05a/b: RSI {rsi} → {esperado} (etiqueta {et!r}, semáforo {sem!r}, consenso {con!r})")
    # Diagnóstico, tabla de indicadores y estrategia usan el mismo clasificador
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    arbol = ast.parse(src)
    fn = next(f for f in ast.walk(arbol) if isinstance(f, ast.FunctionDef) and f.name == "analizar_rsi")
    _check("clasificar_rsi" in ast.unparse(fn), "PA3-05: el Diagnóstico (analizar_rsi) no usa clasificar_rsi")
    _check("Sobrecomprado 🔴" not in src and 'rsi_val > 70' not in src,
           "PA3-05: queda una etiqueta de RSI propia en la tabla de indicadores")
    _check(src.count("etiqueta_rsi(_rsi)") >= 2, "PA3-05: la estrategia no muestra la etiqueta única de RSI")
    # T-PA3-05c — Fibonacci estándar
    import pandas as pd, numpy as np
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=252, tz="Europe/Madrid")
    c = np.linspace(22.8104, 30.4849, 252)
    h = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6}, index=idx)
    f = _APP["analizar_fibonacci"](h, 29.96, "Test")
    esp = {"23.6%": 28.6737, "38.2%": 27.5532, "50.0%": 26.6476, "61.8%": 25.7421, "78.6%": 24.4527,
           "127.2%": 32.5724, "161.8%": 35.2277}
    for k, v in esp.items():
        _check(abs(f["niveles"][k] - v) < 5e-4, f"T-PA3-05c: Fibonacci {k} = {f['niveles'][k]:.4f} (esperado {v})")
    # T-PA3-05d
    _check(f["frase_retroceso"] == "Retroceso del 6,8% del recorrido; entre el 0% y el 23,6%"
           and f["frase_retroceso"] in f["texto"],
           f"T-PA3-05d: {f['frase_retroceso']!r} / texto {f['texto'][:120]!r}")
    _check("32.5724" in f["texto"] and "en 30.4849" not in f["texto"],
           f"T-PA3-05c: la extensión 127,2% del texto no es 32,5724: {f['texto'][-120:]!r}")
    # T-PA3-05e — 7, 7, 8, 7, 7, 7 → 7,2 en Lectura Integrada y Diagnóstico
    tab = {"ath": "_PUNTUACIONES_ATH", "sma200": "_PUNTUACIONES_SMA200", "resist": "_PUNTUACIONES_RESIST",
           "fibo": "_PUNTUACIONES_FIBO", "rsi": "_PUNTUACIONES_RSI", "vol": "_PUNTUACIONES_VOL"}
    comps = []
    # Doc. 22: la SMA200 ya no tiene un tramo de 7; 7, 6, 8, 7, 7, 7 → 6,95 → 7,0 (redondeo hacia arriba en el 5)
    for k, objetivo in zip(["ath", "sma200", "resist", "fibo", "rsi", "vol"], [7, 6, 8, 7, 7, 7]):
        t = _APP[tab[k]]
        esc = next(e for e, p in t.items() if p == objetivo)
        comps.append({"escenario": esc})
    pt = _APP["calcular_puntuacion_tecnica"](*comps)
    _check(f"{pt['score_total']:.1f}" == "7.0", f"T-PA3-05e: diagnóstico {pt['score_total']} (esperado 7,0)")
    _check("round(_li_score_h*2)/2" not in src and "round(_lip_score*2)/2" not in src
           and "round(_sc2 * 2) / 2" not in src, "T-PA3-05e: queda un redondeo a 0,5 en otra sección")
    # Volumen alto con distribución no puntúa positivo
    comps_d = list(comps)
    comps_d[5] = {"escenario": "volumen_alto", "acc_dist": "distribucion"}
    pt_d = _APP["calcular_puntuacion_tecnica"](*comps_d)
    _check(pt_d["scores_ind"]["vol"]["puntos"] <= 5, "PA3-05.5: volumen con distribución puntúa como positivo")
    # T-PA3-05f — divergencia RSI alcista hace 40 sesiones y bajista hace 5: solo la bajista
    dep = _APP["depurar_divergencias"]([
        {"tipo": "RSI", "direccion": "alcista", "_idx": 19}, {"tipo": "RSI", "direccion": "bajista", "_idx": 54},
        {"tipo": "OBV", "direccion": "alcista"}], n_sesiones=60)
    rsi_d = [d for d in dep if d["tipo"] == "RSI"]
    _check(len(rsi_d) == 1 and rsi_d[0]["direccion"] == "bajista" and rsi_d[0]["sesiones_atras"] == 5,
           f"T-PA3-05f: {rsi_d}")
    _check(any(d["tipo"] == "OBV" for d in dep), "T-PA3-05f: no debe tocar otros indicadores")
    # PA3-05.6 — volumen sobre la última sesión completa
    en_curso = _APP["sesion_en_curso"]
    hoy = pd.Timestamp("2026-11-05 09:00", tz="Europe/Madrid")
    _check(en_curso(hoy, ahora=pd.Timestamp("2026-11-05 12:00", tz="Europe/Madrid")) is True
           and en_curso(hoy, ahora=pd.Timestamp("2026-11-05 18:00", tz="Europe/Madrid")) is False
           and en_curso(hoy, ahora=pd.Timestamp("2026-11-06 12:00", tz="Europe/Madrid")) is False,
           "PA3-05.6: detección de sesión en curso")


def test_pa3_04_confluencias():
    conf = _APP["detectar_confluencias"]
    tol = _APP["tolerancia_confluencia"](29.96)
    _check(abs(tol - 0.0899) < 1e-4, f"PA3-04 (F-8): tolerancia a 29,96 = {tol} (esperado 0,09 €)")
    # T-PA3-04a — DiaS1, DiaR1, DiaR2 de Camarilla a 0,03 € y ningún otro marco → sin confluencia
    r = conf({"Diario": {"S1": 29.90, "R1": 29.93, "R2": 29.96},
              "Semanal": {"R3": 31.50}, "Trimestral": {"S3": 27.0}, "Anual": {"PP": 25.0}},
             tolerancia=tol, precio=29.96)
    _check(r == [], f"T-PA3-04a: un solo marco no es confluencia ({r})")
    # T-PA3-04b — un nivel diario, SemR3 29,523 y TriR3 29,494 → ★★ (3 marcos)
    r = conf({"Diario": {"S1": 29.50, "S2": 29.47}, "Semanal": {"R3": 29.523},
              "Trimestral": {"R3": 29.494}, "Anual": {"PP": 25.0}}, tolerancia=tol, precio=29.96)
    _check(len(r) == 1 and r[0]["estrellas"] == "★★" and r[0]["tfs_distintos"] == 3
           and sum(1 for n in r[0]["niveles"] if n["timeframe"] == "Diario") == 1,
           f"T-PA3-04b: {r}")
    _check(all(n["tipo"] == "S" for n in r[0]["niveles"]) if r else False,
           "T-PA3-04c: niveles por debajo del precio deben ser S aunque se llamen R3")
    # T-PA3-04c — precio 29,96 y nivel 29,6568 → "S", distancia −1,01 %
    _check(_APP["tipo_por_precio"](29.6568, 29.96) == "S", "T-PA3-04c: tipo S")
    nk = _APP["_nivel_clave_mas_cercano"](29.96, resultados_pivots={"Semanal": {"R1": 29.6568}})
    _check(nk["tipo"] == "S" and f"{nk['dist_pct']:+.2f}" == "-1.01", f"T-PA3-04c: {nk}")
    niv, _, _ = _APP["calcular_convergencia_tecnica"]({"Semanal": {"R1": 29.6568}}, {50: (29.66, 29.70)},
                                                     29.96, 50, 0.1, 0.05, 0.02, "ALCISTA", 50, tolerancia=tol)
    _check(niv and all(n["tipo"] == "S" for n in niv), f"T-PA3-04c: convergencia {niv}")
    import ast
    _src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check("+{((nr[" not in _src, "T-PA3-04c: queda el signo doble '+-' en la tabla de niveles")
    # T-PA3-04d — Camarilla → semáforo con 6 factores, incluido "Precio vs PP"
    piv = _APP["calcular_todos_pivots"](_A.historico_diario(30.0, 300), "Camarilla")
    _, _, fac = _APP["calcular_semaforo"](30.0, piv["Diario"], 57, 0.1, 0.05, 31, 28,
                                         {"ratio_10d": 100.0}, "ALCISTA")
    _check(len(fac) == 6 and any(f == "Precio vs PP" for f, _, _ in fac),
           f"T-PA3-04d: semáforo con {len(fac)} factores: {[f for f, _, _ in fac]}")


def test_pa3_07_dictamen():
    import json
    crit = json.loads(_A._RUTA_APP.with_name("criteria.json").read_text(encoding="utf-8"))
    cp = next(c for c in crit["carteras"]["dividendos"]["criterios"] if c["id"] == "payout_ratio")
    _check(cp["umbral_ok"] == 0.75 and cp["umbral_warning"] == 0.85, "PA3-07 (F-5): bandas de payout 75/85")
    # T-PA3-07a — payout 87 %, BPA > 0, FCF cubre → KO + K1-Payout → Parcial
    r = _A.simular_screening(_A.info_sana(dpa=1.392, bpa=1.60))
    c = _crit(r, "payout_ratio")
    _check(c.get("estado") == "ko" and "K1-Payout" in _codigos(r) and r["estado_global"] == "parcial",
           f"T-PA3-07a: {c.get('estado')} {c.get('valor_fmt')} {_codigos(r)} {r['estado_global']}")
    # T-PA3-07b — payout 120 %, BPA > 0, FCF insuficiente → K1-FCF degradante
    r = _A.simular_screening(_A.info_sana(dpa=1.92, bpa=1.60, freeCashflow=1.0))
    _check("K1-FCF" in _codigos(r) and r["estado_global"] != "cumple",
           f"T-PA3-07b: {_codigos(r)} {r['estado_global']}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    import re as _re
    m = _re.search(r'_ks_aviso_degrade = \[k for k in killshots(.*?)\]', src, _re.S)
    _check(m is not None and '"K1-FCF"' in m.group(1), "T-PA3-07b: K1-FCF no está entre las degradantes")
    # T-PA3-07c — SOCIMI con yield 17 % → aceptado (no SOSPECHOSO); resto de sectores > 15 % sí
    v0 = __import__("validador_nivel0")
    _check(v0.validar_yield_ttm(0.17, "Real Estate").estado is v0.Estado.OK, "T-PA3-07c: SOCIMI 17 % debe aceptarse")
    _check(v0.validar_yield_ttm(0.17, "Utilities").estado is v0.Estado.SOSPECHOSO, "PA3-07 (F-3): 17 % fuera de RE es sospechoso")
    r = _A.simular_screening(_A.info_sana(sector="Real Estate", industry="REIT - Diversified", yield_obj=0.17))
    c = _crit(r, "dividend_yield")
    _check("sospechoso" not in str(c.get("valor_fmt")), f"T-PA3-07c: SOCIMI 17 % → {c.get('valor_fmt')}")
    # T-PA3-07d — patrimonio neto negativo → KO grave "patrimonio negativo"
    r = _A.simular_screening(_A.info_sana(debtToEquity=-80.0, bookValue=-1.2))
    c = _crit(r, "deuda_equity")
    _check(c.get("estado") == "ko" and c.get("valor_fmt") == "patrimonio negativo"
           and _APP["_gravedad_ko"]("deuda_equity", None, {"_de_crudo": -80.0}) == "grave",
           f"T-PA3-07d: {c.get('estado')} {c.get('valor_fmt')}")


def test_pa3_06_ficha_unidades_horas():
    import sys, types, datetime as _dt
    from decimal import Decimal
    # T-PA3-06a — informe sin ficha → nombre y free float presentes, con fecha
    f_est = _dt.datetime(2026, 11, 5, 9, 0)
    repo = types.ModuleType("repositorio")
    repo.componer_info = lambda *_a, **_k: (
        {"longName": "Naturgy Energy Group, S.A.", "_free_float_pct_neon": Decimal("32.20"),
         "debtToEquity": Decimal("227.6"), "enterpriseToEbitda": Decimal("8.13"), "sector": "Utilities"},
        {"estructural": {"actualizado_en": f_est}, "fundamental": {"actualizado_en": f_est}}, set())
    prev = sys.modules.get("repositorio")
    sys.modules["repositorio"] = repo
    try:
        info = _APP["completar_ficha_desde_neon"]("NTGY.MC", {}, conn=object())
    finally:
        if prev is None:
            sys.modules.pop("repositorio", None)
        else:
            sys.modules["repositorio"] = prev
    bf = _APP["bloque_fundamentales"](info)
    _check(info.get("_ficha_ausente") and bf["Nombre"].startswith("Naturgy")
           and bf["Free Float"].startswith("32.2%") and "05/11/2026" in bf["Free Float"]
           and _APP["FICHA_AUSENTE"] in bf.get("Fuente de datos", "").lower(),
           f"T-PA3-06a: {bf.get('Nombre')} | {bf.get('Free Float')} | {bf.get('Fuente de datos')}")
    # Con ficha no se toca nada
    _check(_APP["completar_ficha_desde_neon"]("X", {"longName": "X SA"}, conn=object()) == {"longName": "X SA"},
           "PA3-06: con ficha no se completa desde Neon")
    # T-PA3-06b — D/E de ACS → "2,6×" (también con Decimal de Neon)
    _check(_APP["_fmt_valor"](Decimal("260.4"), "deuda_equity") == "2,6×"
           and _APP["_fmt_valor"](260.4, "deuda_equity") == "2,6×"
           and bf["Deuda / Equity"] == "2,3×",
           f"T-PA3-06b: {_APP['_fmt_valor'](Decimal('260.4'), 'deuda_equity')} / {bf['Deuda / Equity']}")
    # T-PA3-06c — hora de datos ≤ hora de generación (ambas en Madrid)
    import zoneinfo
    datos = _dt.datetime.now(zoneinfo.ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y %H:%M")
    gen = _APP["ahora_madrid"]()
    _p = lambda t: _dt.datetime.strptime(t, "%d/%m/%Y %H:%M")
    _check(_p(datos) <= _p(gen), f"T-PA3-06c: datos {datos} > generado {gen}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check("datetime.now().strftime" not in src, "T-PA3-06c: queda una hora sin zona (UTC en la nube)")
    # T-PA3-06d — hueco 24,0871–24,2887 con precio 30,00 → −19,0 %
    import numpy as np, pandas as pd
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=60, tz="Europe/Madrid")
    c = np.concatenate([np.linspace(23.0, 24.0, 30), np.linspace(24.5, 30.0, 30)])
    h = pd.DataFrame({"Open": c, "High": c + 0.05, "Low": c - 0.05, "Close": c, "Volume": 1e6}, index=idx)
    h.iloc[29, h.columns.get_loc("High")] = 24.0871
    h.iloc[30, h.columns.get_loc("Low")] = 24.2887
    hs = _APP["detectar_huecos"](h, n_dias=60)
    g = next((x for x in hs if abs(x["gap_low"] - 24.0871) < 1e-4), None)
    _check(g is not None and f"{g['dist_pct']:.1f}" == "-19.0", f"T-PA3-06d: {g}")
    # D-10 — sin confirmación reforzada por encima
    _check("sin nivel de confirmación reforzado por encima del precio" == _APP["SIN_CONFIRMACION_TXT"],
           "PA3-06 (D-10): texto")


def test_v3_validacion_polaris():
    """Validación 10 de Polaris (Spec PA v3): V3-1 … V3-12."""
    import pandas as pd
    ref = pd.Timestamp("2026-11-05", tz="Europe/Madrid")
    # V3-1 — MRL con los pagos de la validación (fecha ex): la ventana TTM es correcta
    mrl = _A.serie_pagos([("2023-05-05", 0.196), ("2023-11-24", 0.162), ("2024-05-17", 0.194),
                          ("2024-11-22", 0.1458), ("2025-05-08", 0.21637),
                          ("2025-11-21", 0.162), ("2026-05-07", 0.21716)])
    _check(abs(_APP["dpa_ttm"](mrl, ref=ref) - 0.37916) < 1e-6, "V3-1: TTM MRL a 05/11/2026 = 0,379")
    _check(abs(_APP["dpa_ttm"](mrl, ref=ref, desfase_dias=365) - 0.36217) < 1e-6, "V3-1: TTM previo MRL = 0,362")
    r = _APP["evaluar_recorte_reciente"](mrl, ref=ref)
    _check(r["estado"] == "sin_recorte" and r["f_homologo"] == "08/05/2025",
           f"V3-2: MRL sin K-RECENT_CUT, homólogo 08/05/2025 ({r})")
    # V3-2 — calendario irregular (FER: 2 pagos frente a 4) → no dispara, va a K8
    fer = _A.serie_pagos([("2024-11-06", 0.4597), ("2024-12-13", 0.0346), ("2025-05-22", 0.3182),
                          ("2025-10-24", 0.4769), ("2025-12-04", 0.0770), ("2026-05-18", 0.5578)])
    r = _APP["evaluar_recorte_reciente"](fer, ref=ref)
    _check(r["estado"] == "irregular" and (r["n_act"], r["n_prev"]) == (2, 4), f"V3-2: FER {r}")
    # V3-2 — recorte real: último pago < 0,75 × homólogo y TTM −33 %
    cut = _A.serie_pagos([("2023-05-10", 0.50), ("2023-10-10", 0.50), ("2024-05-10", 0.50), ("2024-10-10", 0.50),
                          ("2025-05-10", 0.60), ("2025-10-10", 0.60), ("2026-05-08", 0.40), ("2026-10-09", 0.30)])
    _check(_APP["evaluar_recorte_reciente"](cut, ref=ref)["estado"] == "recorte", "V3-2: recorte real no detectado")
    # Recorte solo en el último pago pero TTM estable → no dispara
    uno = _A.serie_pagos([("2023-05-10", 0.30), ("2023-10-10", 0.90), ("2024-05-10", 0.30), ("2024-10-10", 0.90),
                          ("2025-05-10", 0.30), ("2025-10-10", 0.90), ("2026-05-08", 0.85), ("2026-10-09", 0.20)])
    _check(_APP["evaluar_recorte_reciente"](uno, ref=ref)["estado"] == "sin_recorte",
           "V3-2: con el TTM estable no debe dispararse")
    # V3-3 — K1-BPA sin cifra de payout
    rr = _A.simular_screening(_A.info_sana(bpa=-0.40))
    k1 = next((k for k in rr["killshots"] if k.get("codigo") == "K1-BPA"), {})
    _check(k1 and "DPA/BPA =" not in k1.get("razon", "") and "%" not in k1.get("razon", ""),
           f"V3-3: K1-BPA muestra cifra: {k1.get('razon')!r}")
    # V3-4 — redacción y nombres
    _check(_APP["nombre_breve"]("Repsol, S.A.") == "Repsol" and _APP["tipo_activo_legible"]("accion") == "Acción",
           "V3-4: nombre corto / tipo de activo")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    for frase in ("payout ratio <80%", "~3-4%", "participación institucional elevada"):
        _check(frase not in src, f"V3-4: queda {frase!r}")
    _check(_APP["resumen_alertas"]([{"nivel": "verde"}]) == "1 nota informativa", "V3-4: recuento de la lente fundamental")
    # V3-7 — beta propia fuera de rango con aviso
    _check(_APP["beta_txt"](-0.05).startswith("[VERIFICAR]") and _APP["beta_txt"](0.8) == "0.80", "V3-7: beta")
    # V3-8 — semáforo con los puntos reales
    _check(_APP["puntos_semaforo_txt"]([("a", "", 1), ("b", "", 1), ("c", "", 0.5), ("d", "", 0)]) == "2,5",
           "V3-8: puntos del semáforo")
    # V3-6 — misma extensión 127,2 % en ATH y Fibonacci
    import numpy as np
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=400, tz="Europe/Madrid")
    c = np.concatenate([np.linspace(14, 18, 148), np.linspace(15.21, 31.64, 252)])
    h = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6}, index=idx)
    ath = _APP["analizar_maximos_historicos"](h, 31.5, "Repsol, S.A.")
    fib = _APP["analizar_fibonacci"](h, 31.5, "Repsol, S.A.")
    _check(ath and ath.get("target") is not None and abs(ath["target"] - fib["niveles"]["127.2%"]) < 1e-3,
           f"V3-6: ATH {ath and ath.get('target')} vs Fibonacci {fib['niveles']['127.2%']:.4f}")
    _check("Repsol," not in (ath or {}).get("texto", ""), "V3-4: 'Repsol,' con coma en el diagnóstico")
    # V3-9 — pivots anuales con el año natural anterior completo
    idx2 = pd.bdate_range("2025-01-02", "2026-11-04", tz="Europe/Madrid")
    c2 = np.linspace(20, 30, len(idx2))
    h2 = pd.DataFrame({"Open": c2, "High": c2 + .1, "Low": c2 - .1, "Close": c2, "Volume": 1e6}, index=idx2)
    H, L, C, O = _APP["datos_sesion"](h2, "Anual")
    y25 = h2[h2.index.year == 2025]
    _check(abs(H - y25["High"].max()) < 1e-9 and abs(L - y25["Low"].min()) < 1e-9, "V3-9: rango anual 2025")
    # V3-11 — RSI con una decimal en la estrategia
    _check('f"RSI {_rsi:.1f} · {etiqueta_rsi(_rsi)}"' in src, "V3-11: RSI con una decimal")


def test_pagos_manuales_decision3():
    """Decisión 3 de Pólaris: pagos manuales (bruto, prima incluida) — aceptación MRL."""
    import pandas as pd
    import repositorio as repo
    ref = pd.Timestamp("2026-11-05", tz="Europe/Madrid")
    URL = "https://ir.merlinproperties.com/wp-content/uploads/2026/03/acuerdo.pdf"
    yahoo = _A.serie_pagos([("2023-05-05", 0.242), ("2023-11-24", 0.20), ("2024-05-17", 0.24),
                            ("2024-11-22", 0.18), ("2025-05-08", 0.22), ("2025-11-21", 0.20), ("2026-05-07", 0.0151)])
    man = [{"ticker": "MRL.MC", "fecha_ex": "2026-05-07", "importe_bruto": 0.0151, "tipo": "dividendo",
            "url_origen": URL, "activo": True},
           {"ticker": "MRL.MC", "fecha_ex": "2026-05-07", "importe_bruto": 0.20492995, "tipo": "prima",
            "url_origen": URL, "activo": True}]
    ser, ev = _APP["aplicar_dividendos_manuales"]("MRL.MC", yahoo, manuales=man)
    ttm = _APP["dpa_ttm"](ser, ref=ref)
    _check(abs(ttm - 0.42002995) < 1e-6, f"Decisión 3: TTM bruto MRL con prima = {ttm} (esperado 0,4200)")
    rc = _APP["evaluar_recorte_reciente"](ser, ref=ref)
    _check(rc["estado"] == "sin_recorte", f"Decisión 3: MRL sin K-RECENT_CUT ({rc})")
    _check(len(ser) == 7, "Decisión 3: el pago manual sustituye al de Yahoo del mismo evento (no se suma)")
    dsg = _APP["desglose_remuneracion"](ev, ref=ref)
    _check("0,2200 € = 0,0151 dividendo + 0,2049 prima" in dsg and "dato manual · fuente: " + URL in dsg,
           f"Decisión 3: desglose {dsg!r}")
    _check(ev[0]["difiere_yahoo"] is True and ev[0]["incluye_prima"], "Decisión 3: incidencia frente a Yahoo")
    # Extraordinario: fuera del yield y de K-RECENT_CUT
    ser2, ev2 = _APP["aplicar_dividendos_manuales"]("X", _A.serie_pagos([("2026-06-01", 1.0)]),
        manuales=[{"fecha_ex": "2026-06-02", "importe_bruto": 1.0, "tipo": "extraordinario", "url_origen": URL}])
    _check(len(ser2) == 0 and ev2[0]["extraordinario"] == 1.0, "Decisión 3: el extraordinario no entra en la serie")
    # Sin pagos manuales: la serie de Yahoo no cambia
    s3, e3 = _APP["aplicar_dividendos_manuales"]("X", yahoo, manuales=[])
    _check(s3 is yahoo and e3 == [], "Decisión 3: sin pagos manuales no cambia nada")
    # Screener: MRL con los pagos manuales → yield ~3,65 %, sin K3 ni K-RECENT_CUT, payout con "*"
    orig = _APP["aplicar_dividendos_manuales"]
    _APP["aplicar_dividendos_manuales"] = lambda tk, d, manuales=None: orig(tk, d, manuales=man)
    try:
        hoy = pd.Timestamp.now(tz="Europe/Madrid").normalize()
        desf = hoy - ref
        yahoo_rel = pd.Series(yahoo.values, index=yahoo.index + desf)
        man_rel = [dict(m, fecha_ex=str((pd.Timestamp(m["fecha_ex"]) + desf).date())) for m in man]
        _APP["aplicar_dividendos_manuales"] = lambda tk, d, manuales=None: orig(tk, d, manuales=man_rel)
        r = _A.simular_screening(_A.info_sana(dpa=0.215, bpa=0.60, yield_obj=0.0187, sector="Real Estate",
                                              industry="REIT - Office"), dividendos=yahoo_rel)
    finally:
        _APP["aplicar_dividendos_manuales"] = orig
    cy = _crit(r, "dividend_yield"); cp = _crit(r, "payout_ratio")
    _check("K3" not in _codigos(r) and "K-RECENT_CUT" not in _codigos(r),
           f"Decisión 3: MRL con pagos manuales no debe tener K3 ni K-RECENT_CUT ({_codigos(r)})")
    _check(cy.get("valor_fmt", "").startswith("3.6") and "dato manual" in cy.get("mensaje", ""),
           f"Decisión 3: yield {cy.get('valor_fmt')} · {cy.get('mensaje','')[-80:]!r}")
    _check(str(cp.get("valor_fmt", "")).endswith("*"), f"Decisión 3: payout con prima sin '*': {cp.get('valor_fmt')}")
    # Validación del alta
    ok = {"ticker": "MRL.MC", "fecha_ex": "2026-05-07", "importe_bruto": 0.2, "tipo": "prima", "url_origen": URL}
    _check(repo.validar_pago_manual(ok) is None, "Decisión 3: alta válida rechazada")
    for mal, k, v in (("importe 0", "importe_bruto", 0), ("tipo", "tipo", "otro"), ("sin fecha", "fecha_ex", None),
                      ("agregador", "url_origen", "https://stockanalysis.com/quote/bme/MRL/dividend"),
                      ("prensa", "url_origen", "https://www.finect.com/x"), ("sin https", "url_origen", "ir.merlin.com")):
        _check(repo.validar_pago_manual(dict(ok, **{k: v})) is not None, f"Decisión 3: debería rechazar ({mal})")


def test_decision12_r2_ciclo():
    """Decisión 12 de Pólaris (R2): yield por ciclo de pagos con calendario irregular (FER)."""
    import pandas as pd
    ref = pd.Timestamp("2026-11-05", tz="Europe/Madrid")
    fer = _A.serie_pagos([("2023-05-22", 0.30), ("2023-11-06", 0.43), ("2024-05-20", 0.3033), ("2024-11-06", 0.4597),
                          ("2024-12-13", 0.0346), ("2025-05-22", 0.3182), ("2025-10-24", 0.4769),
                          ("2025-12-04", 0.0770), ("2026-05-18", 0.5578)])
    r = _APP["remuneracion_para_yield"](fer, ref=ref)
    _check(r["metodo"] == "ciclo" and r["n"] == 3 and abs(r["importe"] - 1.1117) < 1e-6, f"R2 FER: {r}")
    _check(_APP["evaluar_recorte_reciente"](fer, ref=ref)["estado"] == "irregular", "R2 FER: K8 calendario irregular")
    ntgy = _A.serie_pagos([("2023-04-03", .4), ("2023-07-31", .4), ("2023-11-06", .5), ("2024-04-01", .4),
                           ("2024-07-29", .5), ("2024-11-04", .6), ("2025-04-07", .6), ("2025-07-28", .6),
                           ("2025-11-03", .6), ("2026-03-27", .57), ("2026-07-27", .6), ("2026-11-03", .6)])
    r = _APP["remuneracion_para_yield"](ntgy, ref=ref)
    _check(r["metodo"] == "ttm" and abs(r["importe"] - 1.77) < 1e-6, f"R2 NTGY sigue en TTM 1,77: {r}")
    # n pagos que no caben en 15 meses → se mantiene el TTM
    raro = _A.serie_pagos([("2023-03-01", .5), ("2024-03-01", .5), ("2025-03-01", .5), ("2026-10-01", .5)])
    _check(_APP["dpa_ciclo"](raro, ref=ref) is None or _APP["dpa_ciclo"](raro, ref=ref)[1] == 1, "R2: ciclo fuera de 15 meses")
    # Screener: el rótulo del método aparece en el criterio
    hoy = pd.Timestamp.now(tz="Europe/Madrid").normalize()
    fer_rel = pd.Series(fer.values, index=fer.index + (hoy - ref))
    rr = _A.simular_screening(_A.info_sana(dpa=1.1117, bpa=2.5, yield_obj=0.04), dividendos=fer_rel)
    c = _crit(rr, "dividend_yield")
    _check("ciclo 3 pagos" in c.get("valor_fmt", "") and c.get("valor_fmt", "").startswith("4.0")
           and "K3" not in _codigos(rr), f"R2 screener FER: {c.get('valor_fmt')} {_codigos(rr)}")


def test_decision14_r1_r3():
    """Decisión 14 de Pólaris: R1 solo Yahoo (calendario regular) y R3 importe anunciado."""
    import pandas as pd
    import repositorio as repo
    ref = pd.Timestamp("2026-11-05", tz="Europe/Madrid")
    ev = _APP["evaluar_recorte_reciente"]
    # GRF solo Yahoo → K8 sin homólogo comparable, sin K-RECENT_CUT
    grf = _A.serie_pagos([("2018-11-30", .2), ("2019-06-07", .145), ("2019-12-02", .2), ("2020-10-26", .1616),
                          ("2021-06-03", .364), ("2025-08-11", .15), ("2026-06-30", .0824)])
    r = ev(grf, ref=ref)
    _check(r["estado"] == "irregular" and "homólogo comparable" in r.get("motivo_k8", ""), f"D14 GRF: {r}")
    # REP (ene/jul, ≥ 3 ciclos) → por fecha, 0,551 frente a 0,50 → sin recorte
    rep = _A.serie_pagos([("2023-01-09", .35), ("2023-07-04", .35), ("2024-01-09", .40), ("2024-07-04", .50),
                          ("2025-01-10", .475), ("2025-07-04", .50), ("2026-01-12", .50), ("2026-07-06", .551)])
    r = ev(rep, ref=ref)
    _check(r["estado"] == "sin_recorte" and r.get("base") == "fecha" and r["homologo"] == 0.50, f"D14 REP: {r}")
    # Sintético regular: 3 ciclos de 2 pagos, último 0,30 frente a 0,50 y TTM −40 % → recorte
    sin = _A.serie_pagos([("2023-04-10", .5), ("2023-10-10", .5), ("2024-04-10", .5), ("2024-10-10", .5),
                          ("2025-04-10", .5), ("2025-10-10", .5), ("2026-04-10", .30), ("2026-10-09", .30)])
    r = ev(sin, ref=ref)
    _check(r["estado"] == "recorte" and abs(r["pct_ttm"] + 0.40) < 1e-9, f"D14 sintético: {r}")
    # R1 con pagos tipados (GRF): a cuenta 0,15 (2025) y complementario 0,0824 (2025) → sin homólogo del
    # mismo tipo en el ejercicio anterior → K8, sin disparo
    URL = "https://www.cnmv.es/x"
    tip = [{"fecha_ex": "2025-08-11", "importe_bruto": .15, "tipo": "dividendo_a_cuenta", "ejercicio": 2025, "url_origen": URL},
           {"fecha_ex": "2026-06-30", "importe_bruto": .0824, "tipo": "dividendo_complementario", "ejercicio": 2025, "url_origen": URL}]
    ser, _ = _APP["aplicar_dividendos_manuales"]("GRF.MC", grf, manuales=tip)
    r = ev(ser, ref=ref, manuales=tip)
    _check(r["estado"] == "irregular" and "mismo tipo" in r.get("motivo_k8", ""), f"D14 R1 tipados GRF: {r}")
    # R3 — TEF con anuncio 0,15 € (ejercicio 2026)
    tef = _A.serie_pagos([("2023-06-13", .15), ("2023-12-12", .15), ("2024-06-18", .15), ("2024-12-17", .15),
                          ("2025-06-17", .15), ("2025-12-16", .15), ("2026-06-16", .15)])
    an = [{"tipo": "anunciado", "ejercicio": 2026, "importe_bruto": 0.15, "fecha_anuncio": "2025-11-04",
           "url_origen": URL, "activo": True}]
    a = _APP["evaluar_anunciado"](tef, an, ref=ref)
    _check(a["estado"] == "activo" and a["recorte"] and abs(a["pct"] + 0.5) < 1e-9
           and a["base_txt"] == "DPA de los últimos 12 meses", f"D14 R3 TEF: {a}")
    _check(_APP["evaluar_anunciado"](tef, an, ref=pd.Timestamp("2027-12-31", tz="Europe/Madrid"))["estado"] == "activo"
           and _APP["evaluar_anunciado"](tef, an, ref=pd.Timestamp("2028-01-01", tz="Europe/Madrid"))["estado"] == "caducado",
           "D14 R3: caducidad 31/12/2027 → 01/01/2028")
    pag = an + [{"tipo": "dividendo_a_cuenta", "ejercicio": 2026, "importe_bruto": 0.144, "fecha_ex": "2026-12-15",
                 "url_origen": URL}]
    _check(_APP["evaluar_anunciado"](tef, pag, ref=pd.Timestamp("2026-12-20", tz="Europe/Madrid"))["estado"] == "cerrado",
           "D14 R3: pagos tipados del 96 % cierran el anuncio")
    # Screener TEF: K-RECENT_CUT "recorte anunciado (−50%)", yield ≈ 4,3 %, "TTM 8,7% · anunciado 4,3%"
    hoy = pd.Timestamp.now(tz="Europe/Madrid").normalize()
    tef_rel = pd.Series(tef.values, index=tef.index + (hoy - ref))
    prev = _APP.get("leer_pagos_manuales")
    _APP["leer_pagos_manuales"] = lambda tk: an
    try:
        rr = _A.simular_screening(_A.info_sana(dpa=0.30, bpa=0.40, yield_obj=0.0871,
                                               sector="Communication Services", industry="Telecom Services"),
                                  dividendos=tef_rel)
    finally:
        _APP["leer_pagos_manuales"] = prev
    c = _crit(rr, "dividend_yield")
    _check("K-RECENT_CUT" in _codigos(rr) and "recorte anunciado (−50%)" in rr["motivo"]
           and c.get("valor_fmt", "").startswith("4.4") and "TTM 8,7% · anunciado 4,4%" in c.get("valor_fmt", ""),
           f"D14 R3 screener TEF: {rr['motivo']} · {c.get('valor_fmt')}")
    # Validación del alta de tipos nuevos
    ok = {"ticker": "TEF.MC", "tipo": "anunciado", "importe_bruto": 0.15, "url_origen": URL,
          "ejercicio": 2026, "fecha_anuncio": "2025-11-04"}
    _check(repo.validar_pago_manual(ok) is None, "D14: alta de anunciado válida rechazada")
    _check(repo.validar_pago_manual(dict(ok, ejercicio=None)) is not None, "D14: anunciado sin ejercicio")
    _check(repo.validar_pago_manual({"ticker": "GRF.MC", "tipo": "dividendo_a_cuenta", "importe_bruto": .15,
                                     "fecha_ex": "2025-08-11", "url_origen": URL}) is not None,
           "D14: a cuenta sin ejercicio")


# ═════════════════════════════════════════════════════════════════════════════
# Spec PE v1 — «¿Por dónde empiezo?» · Paso 1 (T-PE-01a … T-PE-07a)
# ═════════════════════════════════════════════════════════════════════════════
def _textos_paso1_sector(sec: dict) -> list:
    """Textos del Contexto Sectorial en el orden de lectura del Paso 1 (igual que la UI)."""
    ciclo = sec.get("comportamiento_ciclo", {})
    fases = [p for p in _APP["FASES_CICLO"] if p in ciclo] + [p for p in ciclo if p not in _APP["FASES_CICLO"]]
    sens = _APP["sensibilidad_tipos_didactica"](sec)
    return ([sec.get("descripcion", "")] + [ciclo[p] for p in fases]
            + [sens["motivo"], sec.get("sensibilidad_tipos", {}).get("explicacion", "")]
            + list((sec.get("riesgos_especificos") or [])[:4]) + [sec.get("leccion_historica", "")])


def test_pe01_06_datos_y_formulas():
    import pandas as pd
    t = _APP["textos_tarjetas_paso1"]({"precio": 29.74, "sma200": 28.0493, "dist_pct": (29.74 / 28.0493 - 1) * 100,
                                       "h52": 31.12, "l52": 24.30, "pos_pct": (29.74 - 24.30) / (31.12 - 24.30) * 100,
                                       "vol_pct": 19.9, "vol_n": 249}, "€", "cierre del 05/11/2026")
    _check("+6,0%" in t["tend_valor"] and "SMA200 28,05 €" in t["tend_datos"] and "Precio 29,74 €" in t["tend_datos"],
           f"T-PE-01a tendencia: {t['tend_valor']} | {t['tend_datos']}")
    _check(t["rng_valor"].startswith("79,8%") and "Mín. 24,30 €" in t["rng_datos"] and "Máx. 31,12 €" in t["rng_datos"]
           and "(29,74 − 24,30) / (31,12 − 24,30) = 79,8%" in t["rng_formula"], f"T-PE-01a rango: {t}")
    _check("249" in t["vol_datos"] and "√252" in t["vol_formula"], f"T-PE-01c ventana de volatilidad: {t['vol_datos']}")
    # Hora y retraso: durante la sesión se muestra hora + '~15 min de retraso'
    _m = _APP["momento_cotizacion_txt"](pd.Timestamp("2026-11-06", tz="Europe/Madrid"),
                                       pd.Timestamp("2026-11-06 12:30", tz="Europe/Madrid"))
    _check("12:30" in _m and "15 min" in _m, f"T-PE-01a hora y retraso: {_m}")
    _m2 = _APP["momento_cotizacion_txt"](pd.Timestamp("2026-11-05", tz="Europe/Madrid"),
                                        pd.Timestamp("2026-11-06 12:30", tz="Europe/Madrid"))
    _check(_m2 == "cierre del 05/11/2026", f"T-PE-01a cierre anterior: {_m2}")
    # T-PE-01b / T-PE-06a — mismas funciones y datos que Análisis Técnico
    hist = _A.historico_diario(29.74, sesiones=252)
    for info in ({"fiftyTwoWeekHigh": 31.12, "fiftyTwoWeekLow": 24.30}, {}):
        d = _APP["datos_largo_plazo"](hist, info)
        h, l, dh = _APP["rango_52s"](info, hist)
        _check(d["precio"] == _APP["precio_actual"](hist)
               and d["sma200"] == _APP["calcular_sma_ema"](hist["Close"])[200][0]
               and (d["h52"], d["l52"], d["rango_desde_hist"]) == (h, l, dh)
               and d["vol_n"] == 251, f"T-PE-06a mismos valores que Análisis Técnico: {d}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check(src.count("rango_52s(info, hist)") >= 1 and "_lp = datos_largo_plazo(hist, _info)" in src,
           "T-PE-06a: Análisis Técnico y Paso 1 usan rango_52s / datos_largo_plazo")


def test_pe02_tramos():
    import copy
    crit = _APP["_cargar_criteria"]()
    cfg = crit.get("contexto_macro_tramos", {})
    _check(bool(cfg), "T-PE-02: criteria.json sin 'contexto_macro_tramos'")
    td = _APP["tramo_de"]
    _check(cfg["dist_sma200"]["tramos"][td(6.0, cfg["dist_sma200"]["tramos"])]["etiqueta"] == "Por encima", "T-PE-02a +6,0% → Por encima")
    _check(cfg["pos_52s"]["tramos"][td(79.8, cfg["pos_52s"]["tramos"])]["etiqueta"] == "Zona alta del año", "T-PE-02a 79,8% → Zona alta")
    _check(cfg["volatilidad"]["tramos"][td(19.9, cfg["volatilidad"]["tramos"])]["etiqueta"] == "Moderada", "T-PE-02a 19,9% → Moderada")
    _check(td(100, cfg["pos_52s"]["tramos"]) == 2 and td(-3, cfg["pos_52s"]["tramos"]) == 0
           and td(-10, cfg["dist_sma200"]["tramos"]) == 2 and td(10, cfg["dist_sma200"]["tramos"]) == 0,
           "T-PE-02: límites de tramo (desde ≤ v < hasta; extremos)")
    h = _APP["html_bloque_tramos"]("pos_52s", 79.8, "79,8%", crit)
    _check("Zona alta del año ◀ valor analizado" in h and "Tramos de referencia del método" in h,
           "T-PE-02a: tramo resaltado y rótulo del método")
    hv = _APP["html_bloque_tramos"]("volatilidad", 19.9, "19,9%", crit)
    _check("±19,9%" in hv and "no una previsión" in hv and "más oscila en euros la misma cantidad" in hv,   # doc. 23 E-10
           "T-PE-02: ejemplo de volatilidad y nota de tamaño")
    # mismos tramos que el informe de estrategia de Dividendos
    _b = [t["hasta"] for t in cfg["pos_52s"]["tramos"][:2]]
    _check(tuple(_b) == tuple(_APP["POS52_DIV"]), f"T-PE-02: tramos 52s {_b} ≠ POS52_DIV {_APP['POS52_DIV']}")
    # T-PE-02b — cambiar un tramo en criteria.json cambia la tabla sin tocar código
    c2 = copy.deepcopy(crit)
    c2["contexto_macro_tramos"]["pos_52s"]["tramos"][2]["desde"] = 85
    c2["contexto_macro_tramos"]["pos_52s"]["tramos"][1]["hasta"] = 85
    c2["contexto_macro_tramos"]["pos_52s"]["tramos"][1]["rango"] = "35% – 85%"
    h2 = _APP["html_bloque_tramos"]("pos_52s", 79.8, "79,8%", c2)
    _check("Zona media ◀ valor analizado" in h2 and "35% – 85%" in h2, "T-PE-02b: el tramo sale de criteria.json")


def test_pe03_sensibilidad_tipos():
    sec = _APP["SECTOR_KNOWLEDGE"]["sectores"]
    u = _APP["sensibilidad_tipos_didactica"](sec["Utilities"])
    _check(u["intensidad"] == "alta" and "suben</b>, suele <b>perjudicar" in u["frase"]
           and "bajan</b>, suele <b>favorecerlo" in u["frase"] and "compite con los bonos" in u["motivo"],
           f"T-PE-03a Utilities: {u}")
    b = _APP["sensibilidad_tipos_didactica"](sec["Financial Services"])
    _check(b["si_suben"] == "favorece" and "suele <b>favorecer</b> al sector" in b["frase"], f"T-PE-03b banca: {b}")
    for k, v in sec.items():
        s = _APP["sensibilidad_tipos_didactica"](v)
        _txt = (s["frase"] + s["badge"]).lower()
        _check(s["intensidad"] in ("alta", "media", "baja") and "muy negativa" not in _txt and "muy positiva" not in _txt,
               f"T-PE-03c {k}: {s['badge']}")
    # compatibilidad hacia atrás: formato antiguo solo con 'direccion'
    old = _APP["sensibilidad_tipos_didactica"]({"sensibilidad_tipos": {"direccion": "muy negativa"}})
    _check((old["intensidad"], old["si_suben"]) == ("alta", "perjudica"), f"T-PE-03: conversión direccion → {old}")


_INGLES_PASO1 = ("underperform", "outperform", "biotech", "tech growth", "e-commerce", "commodities", "driver",
                 "shale", "pricing power", "fintech", "top-5", "whatever it takes", "heavy weight", "cap rate",
                 "streaming wars", "patent cliff", "on-balance", "stranded assets", "timing", "retail", "mix de")


def test_pe04_terminos_en_linea():
    sec = _APP["SECTOR_KNOWLEDGE"]["sectores"]
    out, inf = _APP["explicar_terminos"](_textos_paso1_sector(sec["Utilities"]))
    _check("proxy de bono (" in out[0].lower(), f"T-PE-04a: {out[0][:200]}")
    _todo = " ".join(out).lower()
    _check(_todo.count("proxy de bono (") == 1, "T-PE-04a: la explicación no se repite")
    # T-PE-04b — en todos los sectores, cada término del glosario presente se explica en su 1.ª aparición
    gl = _APP["GLOSARIO_KB"]["terminos"]
    for k, v in sec.items():
        orig = _textos_paso1_sector(v)
        pres = _APP["terminos_presentes"](orig)
        out, inf = _APP["explicar_terminos"](orig)
        falta = sorted(pres - set(inf))
        _check(not falta, f"T-PE-04b {k}: términos sin explicación {falta}")
        for c, estado in inf.items():
            if estado == "insertado":
                _check(sum(o.count("(" + gl[c]["en_linea"] + ")") for o in out) == 1,
                       f"T-PE-04b {k}: '{c}' debe explicarse exactamente una vez")
        _ing = [w for w in _INGLES_PASO1 if w in " ".join(orig).lower()]
        _check(not _ing, f"T-PE-04 {k}: término en inglés sin traducir {_ing}")


def _ind(valor, previo, mx=None, mn=None, fuente="BCE"):
    return {"nombre": "x", "valor": valor, "previo": previo, "max_ref": mx if mx is not None else max(valor, previo),
            "min_ref": mn if mn is not None else min(valor, previo), "fecha": "10/2026", "fuente": fuente,
            "unidad": "%", "desactualizado": False}






def test_pe05_fase_ciclo():
    import copy
    p = _APP["params_fase_ciclo"]()
    _check(bool(p) and p.get("min_indicadores") == 4, "T-PE-05: macro_indicators.json sin 'fase_ciclo_metodo' completo")
    ev = _APP["evaluar_fase_ciclo"]
    exp = {"pib": _ind(2.0, 1.5), "inflacion": _ind(2.0, 2.0), "tipo_oficial": _ind(2.0, 2.0, 4.0, 2.0),
           "curva": _ind(1.0, 1.0), "paro": _ind(6.0, 6.5, 7.0, 6.0)}
    r = ev(exp, p)
    _check(r["fase"] == "expansion" and r["resaltar"] == ["expansion"] and r["votos"]["expansion"] == 4.0,
           f"T-PE-05a Expansión: {r['titulo']} {r['votos']}")
    mix = {"pib": _ind(2.0, 1.5), "inflacion": _ind(3.5, 2.5), "tipo_oficial": _ind(2.5, 2.0, 2.5, 1.5),
           "curva": _ind(1.0, 1.0), "paro": _ind(6.5, 6.0, 7.0, 6.0)}
    r2 = ev(mix, p)
    _check(r2["transicion"] == ("expansion", "pico") and r2["titulo"] == "Transición entre Expansión y Pico"
           and set(r2["resaltar"]) == {"expansion", "pico"}, f"T-PE-05b transición: {r2['titulo']} {r2['votos']}")
    h = _APP["html_fase_ciclo"](r, "zona_euro", p)
    _check(all(s in h for s in ("10/2026", "BCE", "2,0%", "Lectura orientativa")), "T-PE-05c: valor/fecha/fuente/nota")
    d = copy.deepcopy(exp); d["pib"]["desactualizado"] = True
    _check(ev(d, p)["votos"]["expansion"] == 3.0, "T-PE-05: dato desactualizado no cuenta")
    p2 = copy.deepcopy(p); p2["inflacion"]["objetivo_pct"] = 3.0; p2["inflacion"]["banda_cerca_pp"] = 0.2
    _check(ev(exp, p2)["votos"]["expansion"] == 3.5, "T-PE-05d: umbral de inflación desde el JSON")
    import pandas as pd
    s = pd.Series([1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4], index=pd.date_range("2026-03-01", periods=8, freq="MS"))
    rs = _APP["_resumen_serie"](s, 6, 24, "mensual", {"mensual": 4}, hoy="2026-11-06")
    _check(rs["valor"] == 2.4 and rs["previo"] == 1.2 and rs["fecha"] == "10/2026" and not rs["desactualizado"],
           f"T-PE-05: resumen de serie {rs}")
    rs2 = _APP["_resumen_serie"](s, 6, 24, "mensual", {"mensual": 4}, hoy="2027-06-01")
    _check(rs2["desactualizado"], "T-PE-05: antigüedad > máximo → desactualizado")
    _check(_APP["region_macro"]("NTGY.MC") == "zona_euro" and _APP["region_macro"]("AAPL") == "eeuu",
           "T-PE-05: región por ticker")


def test_pe_decision18_votos_y_minimo():
    p = _APP["params_fase_ciclo"](); ev = _APP["evaluar_fase_ciclo"]
    # Datos reales del 06/11/2026 (decisión 18 §3): Expansión 1,5 · Pico 2,5 · Recuperación 1
    real = {"pib": _ind(1.3, 0.6, 1.6, 0.6), "inflacion": {**_ind(4.0, 3.0), "subyacente": {"valor": 2.5, "fecha": "10/2026"}},
            "tipo_oficial": _ind(2.5, 2.0, 3.25, 2.0), "curva": _ind(0.33, 0.49, 0.8, 0.2),
            "paro": _ind(6.6, 6.5, 6.8, 6.2)}
    r = ev(real, p)
    _check(r["votos"] == {"expansion": 1.5, "pico": 2.5, "contraccion": 0.0, "recuperacion": 1.0}
           and r["titulo"] == "Transición entre Expansión y Pico", f"D18 §3 votos: {r['votos']} {r['titulo']}")
    h = _APP["html_fase_ciclo"](r, "zona_euro", p)
    _check("Expansión 1,5 · Pico 2,5" in h and "Expansión 0,5 · Pico 0,5" in h, "D18 §3: votos con decimales")
    _check("general 4,0% · subyacente 2,5%" in h and "subyacente 2,5%" in h, "D17 §1: nota de inflación subyacente")
    _check(_APP["nota_subyacente"]({"valor": 3.0, "subyacente": {"valor": 2.5}}, p) == "", "D17 §1: sin nota si la diferencia ≤ 1")
    # Decisión 17 §5 — mínimo 4 de 5
    tres = {k: v for k, v in real.items() if k not in ("pib", "curva")}
    r3 = ev(tres, p)
    _check(r3["fase"] is None and not r3["resaltar"] and r3["titulo"] == "Fase no determinable: datos insuficientes"
           and len(r3["faltan"]) == 2, f"D17 §5: {r3['titulo']} {r3.get('faltan')}")
    cuatro = {k: v for k, v in real.items() if k != "pib"}
    _check(ev(cuatro, p)["titulo"] != "Fase no determinable: datos insuficientes", "D17 §5: con 4 de 5 sí se asigna")


def test_pe_decision18_tipos_tramos_formulas():
    sec = _APP["SECTOR_KNOWLEDGE"]["sectores"]
    tabla = {"Utilities": ("alta", "perjudica"), "Real Estate": ("alta", "perjudica"), "Technology": ("alta", "perjudica"),
             "Consumer Cyclical": ("media", "perjudica"), "Communication Services": ("media", "perjudica"),
             "Industrials": ("media", "perjudica"), "Basic Materials": ("media", "perjudica"),
             "Energy": ("baja", "perjudica"), "Consumer Defensive": ("baja", "perjudica"), "Healthcare": ("baja", "perjudica")}
    sd = _APP["sensibilidad_tipos_didactica"]
    for k, (i, su) in tabla.items():
        r = sd(sec[k])
        _check((r["intensidad"], r["si_suben"]) == (i, su) and r["rotulo"] == "Orientación cualitativa del método",
               f"D18 §2 {k}: {r['intensidad']} {r['si_suben']}")
    b = sd(sec["Financial Services"]); b2 = sd(sec["Financial Services"], "Banks - Diversified")
    s_ = sd(sec["Financial Services"], "Insurance - Life")
    _check((b["intensidad"], b["si_suben"], b["subtipo"]) == ("alta", "favorece", "banca") and b2["subtipo"] == "banca",
           f"D18 §2 banca (por defecto y por industria): {b['badge']}")
    _check((s_["intensidad"], s_["si_suben"]) == ("media", "mixto") and "mixto" in s_["frase"], f"D18 §2 seguros: {s_['badge']}")
    # P-1 — «Cómo leerlo» del tramo analizado
    crit = _APP["_cargar_criteria"]()
    hb = _APP["html_bloque_tramos"]
    _check("Estar por debajo indica que el precio lleva meses corrigiendo" in hb("dist_sma200", -5.7, "−5,7%", crit)
           and "Estar por encima indica" not in hb("dist_sma200", -5.7, "−5,7%", crit), "D18 P-1: SMA200 por debajo")
    _check("En zona media" in hb("pos_52s", 43.6, "43,6%", crit), "D18 P-1: rango 52 s, zona media")
    hv = hb("volatilidad", 32.0, "32,0%", crit)
    _check("Volatilidad alta" in hv and "±32,0%" in hv, "D18 P-1: volatilidad alta + ejemplo")
    # P-2 — fórmula con precios sin redondear
    t = _APP["textos_tarjetas_paso1"]({"precio": 10.6449, "sma200": 11.28, "dist_pct": -5.63, "h52": 13.1249, "l52": 8.7151,
                                       "pos_pct": 43.5, "vol_pct": 32.0, "vol_n": 255}, "€")
    _check("sin redondear" in t["rng_formula"] and "sin redondear" in t["tend_formula"], "D18 P-2: aviso de redondeo")


def test_pe07_lecciones_fuente():
    sec = _APP["SECTOR_KNOWLEDGE"]["sectores"]
    lc = _APP["leccion_con_fuente"]
    _check(not _APP["leccion_tiene_cifra"]("En julio de 2012, entre 2000-2002 y el 25/05/2022") and
           _APP["leccion_tiene_cifra"]("cayó un 19,3%"), "T-PE-07: detección de cifras (años y fechas no cuentan)")
    for k, v in sec.items():
        r = lc(v.get("leccion_historica", ""), v.get("leccion_fuente"), v.get("leccion_periodo"),
               v.get("leccion_cualitativa"), v.get("leccion_validada"))
        if not r["verificar"]:
            _check(not _APP["leccion_tiene_cifra"](r["texto"]) or (v.get("leccion_fuente") and v.get("leccion_periodo")),
                   f"T-PE-07a {k}: cifra mostrada sin fuente y periodo")
        else:
            _check(not _APP["leccion_tiene_cifra"](r["texto"]) and r["marca"].startswith("[VERIFICAR"),
                   f"T-PE-07a {k}: con [VERIFICAR] no se muestran cifras ({r['texto'][:60]})")
        _check(_APP["leccion_tiene_cifra"](v.get("leccion_historica", "")) <= bool(v.get("leccion_fuente") and v.get("leccion_periodo")),
               f"T-PE-07a {k}: lección con cifras sin campos fuente/periodo")
    u = lc(sec["Utilities"]["leccion_historica"], sec["Utilities"]["leccion_fuente"], sec["Utilities"]["leccion_periodo"],
           sec["Utilities"].get("leccion_cualitativa"), sec["Utilities"].get("leccion_validada"))
    _check("19,3%" in u["texto"] and "25/05/2022" in u["texto"] and not u["verificar"], "D17 §2: lección de Iberdrola")
    f = lc(sec["Financial Services"]["leccion_historica"], None, "2012", None, True)
    _check("41.000" not in f["texto"] and "OCR" not in f["texto"] and "Bankia" in f["texto"] and not f["verificar"],
           "D18 §4: lección de Bankia")
    for k, c in _APP["CRISIS_PATTERNS"].get("crisis", {}).items():
        r = lc(c.get("leccion_operativa", ""), c.get("fuente"), c.get("periodo"), ocultar_cifras=False)
        _check(r["verificar"] == (_APP["leccion_tiene_cifra"](c.get("leccion_operativa", "")) and not c.get("fuente")),
               f"T-PE-07a crisis {k}")


def test_d17_macro_ipca_y_frescura():
    """Decisión 17 §6 — IPCA de Eurostat en Macro y control de frescura de las series."""
    import pandas as pd
    fr = _APP["frescura_serie"]
    m = lambda a, b: pd.Series(1.0, index=pd.date_range(a, b, freq="MS"))
    r = fr(m("2025-01-01", "2025-12-01"), "mensual", "2026-11-06")
    _check(r["desactualizado"] and r["aviso"] == "dato desactualizado (último: 12/2025)", f"D17 §6 mensual antiguo: {r}")
    _check(not fr(m("2026-01-01", "2026-09-01"), "mensual", "2026-11-06")["desactualizado"], "D17 §6: 09/2026 al 06/11 está al día (37 días)")
    _check(fr(m("2026-01-01", "2026-09-01"), "mensual", "2026-11-20")["desactualizado"], "D17 §6: 09/2026 al 20/11 desactualizado (51 días)")
    q = pd.Series(1.0, index=pd.to_datetime(["2026-01-01", "2026-04-01"]))
    _check(not fr(q, "trimestral", "2026-10-20")["desactualizado"] and fr(q, "trimestral", "2026-11-06")["desactualizado"],
           "D17 §6: trimestral, margen de 120 días")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _ini = src.index("def pestaña_macro():"); _fin = src.index("# ── DIVISAS", _ini)
    _check('obtener_hicp_eurostat("EA"' in src[_ini:_fin] and '"M.U2.N.000000.4.ANR", "ICP"' not in src[_ini:_fin]
           and 'obtener_historico_ecb("FM", "B.U2.EUR.4F.KR.DFR.LEV"' in src[_ini:_fin],
           "D17 §6: la pestaña Macro usa Eurostat (ECOICOP v2) y el DFR del flow FM")


_PROHIBIDOS_PE2 = ("comprar", "vender", "entrar", "salir", "reducir")   # + «compra»/«venta» como palabra (ver _hay_compra_venta)


def _hay_compra_venta(t: str) -> list:
    import re
    return re.findall(r"\b(?:compra|venta)\b", t)


def _lp_pe(precio, sma, h52, l52, vol):
    return {"precio": precio, "sma200": sma, "dist_pct": (precio / sma - 1) * 100, "h52": h52, "l52": l52,
            "pos_pct": (precio - l52) / (h52 - l52) * 100, "vol_pct": vol, "vol_n": 255}


def test_pe08_conclusion_valor():
    cv = _APP["conclusion_valor"]
    itx = cv(_lp_pe(58.90, 54.52, 60.64, 46.11, 25.6), "Industria de Diseño Textil", "€")
    _check(itx["clave"] == "a_favor" and "en la zona alta del año y con oscilaciones amplias" in itx["texto"] and "con oscilaciones amplias" in itx["texto"]
           and "un cierre por debajo de 54,52 €" in itx["texto"], f"T-PE-08 ITX: {itx['texto']}")
    san = cv(_lp_pe(10.64, 11.28, 13.12, 8.72, 32.0), "Banco Santander, S.A.", "€")
    _check(san["clave"] == "en_contra" and "en la zona media del año" in san["texto"] and "con oscilaciones amplias" in san["texto"]
           and "un cierre por encima de 11,28 €" in san["texto"], f"T-PE-08 SAN: {san['texto']}")
    ntgy = cv(_lp_pe(29.50, 28.07, 31.12, 24.30, 19.9), "Naturgy Energy Group", "€")
    _check(ntgy["clave"] == "a_favor" and "en la zona alta del año" in ntgy["texto"] and "oscilaciones" not in ntgy["texto"]
           and "un cierre por debajo de 28,07 €" in ntgy["texto"], f"T-PE-08 NTGY: {ntgy['texto']}")
    neu = cv(_lp_pe(10.12, 10.0, 11.0, 9.0, 18.0), "X", "€")
    _check(neu["clave"] == "neutra" and "neutra (precio pegado a su media)" in neu["texto"], f"T-PE-08 neutra: {neu['texto']}")
    alto = cv(_lp_pe(11.5, 10.0, 11.6, 9.0, 18.0), "X", "€")
    _check("de su media de 200 sesiones (muy por encima), en la zona alta del año" in alto["texto"]
           and "habituales" not in alto["texto"], f"T-PE-08 / V-2: matiz 'muy por encima' {alto['texto']}")


def test_pe09_pe10_conclusiones():
    sec = _APP["SECTOR_KNOWLEDGE"]["sectores"]
    sd, cs, cg = _APP["sensibilidad_tipos_didactica"], _APP["conclusion_sector"], _APP["conclusion_general"]
    trans = {"resaltar": ["expansion", "pico"], "titulo": "Transición entre Expansión y Pico"}
    san_s = cs(sec["Financial Services"], trans, "subiendo", sd(sec["Financial Services"]), "Servicios Financieros")
    itx_s = cs(sec["Consumer Cyclical"], trans, "subiendo", sd(sec["Consumer Cyclical"]), "Consumo Cíclico")
    ntg_s = cs(sec["Utilities"], trans, "subiendo", sd(sec["Utilities"]), "Utilities")
    _check(san_s["suma"] == 2.5 and san_s["clave"] == "a_favor", f"T-PE-09 SAN: {san_s['suma']} {san_s['clave']}")
    _check(itx_s["suma"] == 0.5 and itx_s["clave"] == "neutro", f"T-PE-09 ITX: {itx_s['suma']} {itx_s['clave']}")
    _check(ntg_s["suma"] == -1 and ntg_s["clave"] == "en_contra", f"T-PE-09 NTGY: {ntg_s['suma']} {ntg_s['clave']}")
    nd = cs(sec["Utilities"], {"resaltar": [], "titulo": "Fase no determinable: datos insuficientes"}, "subiendo",
            sd(sec["Utilities"]), "Utilities")
    _check(not nd["fase_determinable"] and nd["suma"] == -1 and "Fase del ciclo no determinable" in nd["texto"],
           f"T-PE-09 fase no determinable: {nd['texto']}")
    _check(cs(sec["Utilities"], trans, "bajando", sd(sec["Utilities"]), "U")["c_tipos"] == 1.0
           and cs(sec["Utilities"], trans, "estable", sd(sec["Utilities"]), "U")["c_tipos"] == 0.0, "T-PE-09: tipos bajando / estables")
    # tabla de efecto completa (4 fases × 11 sectores, valores −2…+2)
    for k, v in sec.items():
        ef = v.get("efecto_ciclo") or {}
        _check(set(ef) == {"expansion", "pico", "contraccion", "recuperacion"} and all(x in (-2, -1, 0, 1, 2) for x in ef.values()),
               f"T-PE-09 efecto_ciclo {k}: {ef}")
    cv = _APP["conclusion_valor"]
    v_itx = cv(_lp_pe(58.90, 54.52, 60.64, 46.11, 25.6), "Inditex", "€")
    v_san = cv(_lp_pe(10.64, 11.28, 13.12, 8.72, 32.0), "Santander", "€")
    v_ntg = cv(_lp_pe(29.50, 28.07, 31.12, 24.30, 19.9), "Naturgy", "€")
    g_itx, g_san, g_ntg = cg(v_itx, itx_s), cg(v_san, san_s), cg(v_ntg, ntg_s)
    _check(g_itx["clave"] == "mayoritariamente a favor", f"T-PE-10 ITX: {g_itx['clave']}")
    _check(g_san["clave"] == "señales cruzadas" and "domina ahora" in g_san["texto"], f"T-PE-10 SAN: {g_san['clave']}")
    _check(g_ntg["clave"] == "señales cruzadas", f"T-PE-10 NTGY: {g_ntg['clave']}")
    _check(cg(v_itx, None)["clave"] is None, "T-PE-10: sin ficha sectorial no se combina")
    # Redacción: sin términos de operativa (PA3-01 + lista de la spec)
    textos = " ".join(c["texto"] + " " + c.get("por_que", "") for c in
                      (v_itx, v_san, v_ntg, san_s, itx_s, ntg_s, nd, g_itx, g_san, g_ntg)).lower()
    textos += " " + _APP["params_conclusiones"]().get("nota_fija", "").lower()
    _malos = [t for t in tuple(TERMINOS_PA3) + _PROHIBIDOS_PE2 if t in textos] + _hay_compra_venta(textos)
    _check(not _malos, f"T-PE-10 redacción: términos de operativa {_malos}")


_EF_TXT = (("muy favorable", 2), ("muy positivo", 2), ("muy negativo", -2), ("negativo relativo", -1),
           ("neutral-negativo", -1), ("desfavorable", -1), ("favorable", 1), ("positivo", 1), ("negativo", -1),
           ("neutral", 0))


def _efecto_de_texto(t):
    t = t.split(" — ")[0].lower()
    for k, v in _EF_TXT:
        if t.startswith(k):
            return v
    return None


def test_d21_subtipos_energy_textos():
    sec = _APP["SECTOR_KNOWLEDGE"]["sectores"]
    sub = _APP["sector_con_subtipo"]
    _check(sub(sec["Financial Services"], "Insurance - Life")["efecto_ciclo"] == {"expansion": 1, "pico": 1, "contraccion": -1, "recuperacion": 1},
           "D21 §2b seguros")
    _check(sub(sec["Financial Services"], "Asset Management")["efecto_ciclo"]["expansion"] == 2, "D21 §2b gestoras")
    _check(sub(sec["Financial Services"], None)["_subtipo_ciclo"] == "banca", "D21 §2b sin industria → banca")
    _check(sub(sec["Communication Services"], "Internet Content & Information")["efecto_ciclo"] ==
           {"expansion": 1, "pico": -1, "contraccion": 0, "recuperacion": 1}, "D21 §2a plataformas")
    _check(sub(sec["Communication Services"], "Telecom Services")["efecto_ciclo"]["contraccion"] == 1, "D21 §2a telecos")
    _check(sec["Energy"]["efecto_ciclo"] == {"expansion": 1, "pico": 1, "contraccion": -2, "recuperacion": 1}, "D21 §3 Energy")
    # Regla D21 §3: el número y el texto de cada celda dicen lo mismo
    filas = []
    for k, v in sec.items():
        if v.get("subtipos_ciclo"):
            filas += [(f"{k}/{n}", s_["comportamiento_ciclo"], s_["efecto_ciclo"]) for n, s_ in v["subtipos_ciclo"].items()]
        else:
            filas.append((k, v["comportamiento_ciclo"], v["efecto_ciclo"]))
    for n, cc, ef in filas:
        for f in ("expansion", "pico", "contraccion", "recuperacion"):
            _check(_efecto_de_texto(cc[f]) == ef[f], f"D21 §3 {n}.{f}: '{cc[f][:40]}' ≠ {ef[f]}")
    # C-2: sin cifras sin fuente en los textos sectoriales del Paso 1
    import re
    for k, v in sec.items():
        ts = [v["descripcion"], v["sensibilidad_tipos"]["explicacion"], v["sensibilidad_tipos"].get("motivo", "")] + \
             list(v["comportamiento_ciclo"].values()) + list(v.get("riesgos_especificos", [])[:4])
        for t in ts:
            t2 = re.sub(r"\b5G\b|S&P 500|IBEX 35", "", t)
            _check(not _APP["leccion_tiene_cifra"](t2), f"D21 C-2 {k}: cifra sin fuente en «{t[:60]}»")
    # SAN sigue en +2,5 con el subtipo banca
    trans = {"resaltar": ["expansion", "pico"], "titulo": "Transición entre Expansión y Pico"}
    sd = _APP["sensibilidad_tipos_didactica"]
    r = _APP["conclusion_sector"](sub(sec["Financial Services"], None), trans, "subiendo", sd(sec["Financial Services"]), "SF")
    _check(r["suma"] == 2.5, f"D21: SAN con banca {r['suma']}")
    _check("Historial insuficiente para la media de 200 sesiones (150 sesiones disponibles)" in _APP["html_historial_insuficiente"](150),
           "D21 §2d: historial insuficiente")




def test_pe11_fichas_componentes():
    puntos = {"ath": "_PUNTUACIONES_ATH", "sma200": "_PUNTUACIONES_SMA200", "resist": "_PUNTUACIONES_RESIST",
              "fibo": "_PUNTUACIONES_FIBO", "rsi": "_PUNTUACIONES_RSI", "vol": "_PUNTUACIONES_VOL"}
    crit = _APP["_cargar_criteria"]()
    for k, tab in puntos.items():
        filas = _APP["tabla_componente"](k)
        _check({e for e, *_ in filas} == set(_APP[tab]), f"T-PE-11: la tabla de {k} cubre todos los tramos del motor")
        _check(all(p == _APP[tab][e] for e, _t, _c, p in filas), f"T-PE-11: notas de {k} = las del motor")
        _check(all("_" not in _APP["titulo_escenario"](k, e) for e in _APP[tab]), f"T-PE-11a: títulos de {k} sin códigos")
        textos = [_APP["como_leerlo_componente"](k, e, crit) for e in _APP[tab]]
        _check(all(textos) and len(set(textos)) == len(textos), f"T-PE-11c: «cómo leerlo» de {k} por tramo")
    a, pt = _diag_ntgy()
    for k in puntos:
        h = _APP["html_ficha_componente"](k, a[k], pt["scores_ind"][k], 29.74, crit)
        _check("Datos usados" in h and "◀" in h and "Qué cambiaría esta nota" in h and "Qué es" in h, f"T-PE-11b {k}")
    _check("30,19 €" in _APP["que_cambiaria_componente"]("ath", a["ath"], 29.74), "T-PE-11: ATH −3% = 30,19 €")
    _check("29,51 €" in _APP["que_cambiaria_componente"]("fibo", a["fibo"], 29.74), "T-PE-11: perder el 23,6% = 29,51 €")
    r = _APP["datos_componente"]("rsi", a["rsi"], 29.74)
    _check("14 sesiones, diario" in r and "neutro 45–55" in r, f"T-PE-11d RSI: {r}")
    # Umbrales expuestos = umbrales del motor (máximo histórico y resistencias)
    import pandas as pd, numpy as np
    hl = pd.DataFrame({"High": np.r_[np.linspace(50, 100, 99), 100.0], "Low": 40.0, "Close": 60.0},
                      index=pd.bdate_range("2020-01-01", periods=100))
    esp = {101: "subida_libre_establecida", 99.5: "en_ath", 98: "aproximandose_cerca", 95: "aproximandose",
           80: "referencia", 70: "lejos"}
    for pr, e in esp.items():
        _check(_APP["analizar_maximos_historicos"](hl, pr, "X")["escenario"] == e, f"T-PE-11: ATH {pr} → {e}")
    niv = [{"precio": 101.0, "tipo": "R"}, {"precio": 90.0, "tipo": "S"}]
    _check(_APP["analizar_resistencias_estructurales"](niv, 100.0, "X")["escenario"] == "en_resistencia"
           and _APP["analizar_resistencias_estructurales"](niv, 98.0, "X")["escenario"] == "zona_alta_rango"
           and _APP["analizar_resistencias_estructurales"](niv, 95.0, "X")["escenario"] == "zona_media_rango",
           "T-PE-11: umbrales de resistencias (1,5% y 35/65%)")




def test_exportacion_imprimible_pasos():
    """Botón «Descargar el Paso N para imprimir»: el grabador reenvía a Streamlit y guarda el contenido."""
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *e): return False

    class _StFalso:
        def __init__(self): self.n = 0
        def markdown(self, *a, **k): self.n += 1
        def caption(self, *a, **k): self.n += 1
        def info(self, *a, **k): self.n += 1
        def expander(self, *a, **k): return _Ctx()
        def columns(self, n, **k): return [_Ctx() for _ in range(n)]

    real = _StFalso()
    g = _APP["_GrabadorPaso"](real)
    g.markdown("<div class='pp-card'>Paso</div>", unsafe_allow_html=True)
    with g.expander("Máximo histórico — Aproximándose (6/10)"):
        g.markdown("<p>ficha</p>", unsafe_allow_html=True)
    g.info("**Nota** final")
    c1, c2 = g.columns(2)
    _check(real.n == 3, "Exportación: el grabador reenvía las llamadas a Streamlit")
    h = _APP["html_exportacion_paso"](g.partes, "NTGY.MC", 2, "Estructura", "Naturgy Energy Group")
    _check(h.startswith("<!doctype html>") and "Paso 2 — Estructura" in h and "Naturgy Energy Group (NTGY.MC)" in h
           and "<details open><summary>Máximo histórico — Aproximándose (6/10)</summary><p>ficha</p></details>" in h
           and "<b>Nota</b> final" in h and ".pp-card{" in h, "Exportación: HTML imprimible del paso")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check("def _pp_wizard_cuerpo(st):" in src and "_pp_wizard_cuerpo(_grab)" in src
           and "_ph_export.download_button(" in src, "Exportación: botón en el fragmento del asistente")


def _diag_ntgy():
    res = {"precio": 29.95, "detalle": "R1 Mensual + SMA50", "pivot": "R1 Men", "tipo": "R"}
    sop = {"precio": 28.80, "detalle": "S1 Trimestral + SMA50", "pivot": "S1 Tri", "tipo": "S"}
    a = {"ath": {"escenario": "aproximandose", "ath": 31.12, "dist_pct": -4.43, "ath_fecha_dia": "26/10/2026"},
         "sma200": {"escenario": "tendencia_alcista", "escenario_nota": "tendencia_alcista_encima", "precio_sobre": True,
                    "sma200": 28.05, "dist_pct": 6.0, "pend_5_abs": 0.02, "pend_past_abs": 0.015, "umbral_plano": 0.0084},
         "resist": {"escenario": "en_resistencia", "resistencia": res, "soporte": sop, "dist_resist": 0.7,
                    "dist_soporte": 3.2, "pos_rango_pct": 82},
         "fibo": {"escenario": "retroceso_236", "swing_min": 24.30, "swing_max": 31.12, "fecha_min": "12/12/2025",
                  "fecha_max": "26/10/2026", "retroceso_max_pct": 20.2, "n_sesiones": 252, "frase_retroceso": "x"},
         "rsi": {"escenario": "zona_neutra", "rsi_val": 47.7},
         "vol": {"escenario": "volumen_normal", "vol_5d": 1e6, "vol_20d": 1.2e6, "vol_rel": 83, "acc_dist": "distribucion",
                 "vol_alc": 1.6e6, "vol_baj": 8.4e6}}
    pt = _APP["calcular_puntuacion_tecnica"](a["ath"], a["sma200"], a["resist"], a["fibo"], a["rsi"], a["vol"])
    return a, pt


def test_pe12_pe14_nota_y_conclusion():
    import copy
    a, pt = _diag_ntgy()
    calc = _APP["calculo_nota_global"](pt)
    _check(pt["score_total"] == 5.6 and calc["formula"].startswith("0,15 × 6") and calc["formula"].endswith("= 5,60 → 5,6"),
           f"T-PE-12a (doc. 22 §3, NTGY 5,6): {calc['formula']}")
    crit = _APP["_cargar_criteria"]()
    h = _APP["html_nota_global"](pt, crit)
    _check("Estructura mixta: los componentes no coinciden. ◀ nota actual" in h and "≥ 6,5" in h, "T-PE-12a: tramo mixta")
    c2 = copy.deepcopy(crit); c2["diagnostico_paso2"]["cortes"]["alcista"] = 5.0
    _check(_APP["tramo_estructura"](5.6, c2) == "alcista" and "≥ 5,0" in _APP["html_nota_global"](pt, c2), "T-PE-12b: corte desde criteria.json")
    c = _APP["conclusion_paso2"](pt, a, 29.74, {"clave": "a_favor"}, crit)
    for frag in ("estructura mixta (5,6/10)", "Apoyan: Media de 200 sesiones (8/10), Fibonacci (7/10)",
                 "Restan: Resistencias (2/10)", "Resistencias: un cierre por encima de 29,95 €", "matiza (Paso 1: a favor)"):
        _check(frag in c["texto"], f"T-PE-14 NTGY: falta «{frag}» en {c['texto']}")
    rel = lambda v, sc: _APP["conclusion_paso2"]({**pt, "score_total": sc}, a, 29.74, {"clave": v}, crit)["relacion"]
    _check(rel("a_favor", 7.0) == "coherente" and rel("en_contra", 3.0) == "coherente" and rel("a_favor", 3.0) == "contradice"
           and rel("en_contra", 7.0) == "contradice" and rel("neutra", 5.0) == "coherente" and rel("neutra", 7.0) == "matiza",
           "T-PE-14: regla de relación con el Paso 1")
    _check("no se puede establecer" in _APP["conclusion_paso2"](pt, a, 29.74, None, crit)["texto"], "T-PE-14: sin conclusión del Paso 1")
    # E-1: con el RSI como componente que resta, el «qué cambiaría» empieza por su nombre
    a2 = copy.deepcopy(a); a2["rsi"] = {"escenario": "zona_bajista", "rsi_val": 38.8}
    a2["resist"]["escenario"] = "zona_media_rango"
    pt2 = _APP["calcular_puntuacion_tecnica"](a2["ath"], a2["sma200"], a2["resist"], a2["fibo"], a2["rsi"], a2["vol"])
    c3 = _APP["conclusion_paso2"](pt2, a2, 10.7, {"clave": "en_contra"}, crit)
    _check("Qué cambiaría esta lectura:</b> RSI estructural: que el RSI supere 45 (pasaría a neutro, 5/10)" in c3["texto"],
           f"Doc. 23 E-1: {c3['texto']}")
    # T-PE-13a — redacción del Paso 2
    d2 = crit.get("diagnostico_paso2", {})
    textos = [c["texto"], c["por_que"], h] + list(d2.get("que_es", {}).values()) + list(d2["cortes"]["rotulos"].values())
    for comp in d2.get("como_leerlo", {}).values():
        textos += list(comp.values())
    for k in ("ath", "sma200", "resist", "fibo", "rsi", "vol"):
        textos.append(_APP["html_ficha_componente"](k, a[k], pt["scores_ind"][k], 29.74, crit))
    t = " ".join(textos).lower()
    _malos = [x for x in tuple(TERMINOS_PA3) + _PROHIBIDOS_PE2 + ("probabilidad",) if x in t] + _hay_compra_venta(t)
    _check(not _malos, f"T-PE-13a: términos no admitidos {_malos}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _i = src.index("    elif _step == 2:\n"); _j = src.index("# ── PASO 3: SEMÁFORO", _i)
    _check("probabilidades" not in src[_i:_j] and "0.618 es el nivel" not in src[_i:_j], "T-PE-13a: textos antiguos retirados")
    _check(src.count("diagnostico_tecnico(ticker_activo, hist, precio, nombre,") == 1
           and src.count("diagnostico_tecnico(_ticker, hist, _precio, _nombre)") == 1
           and 'yf.Ticker(_ticker).history(period="15y"' not in src, "T-PE-15a: misma función en informe y Paso 2")


def test_doc22_reglas_motor():
    import pandas as pd, numpy as np
    P = _APP
    _check(P["_PUNTUACIONES_SMA200"] == {"giro_alcista_encima": 9, "tendencia_alcista_encima": 8, "plana_encima": 6,
           "positiva_debajo": 5, "plana_debajo": 4, "negativa_encima": 4, "giro_bajista_debajo": 2,
           "tendencia_bajista_debajo": 1}, "Doc. 22 §2.1 tabla SMA200")
    _check(P["_PUNTUACIONES_FIBO"] == {"en_maximo": 8, "retroceso_236": 7, "retroceso_382": 6, "retroceso_500": 5,
           "retroceso_618": 4, "retroceso_786": 3, "swing_roto": 1}, "Doc. 22 §2.2 tabla Fibonacci")
    _check(P["_PUNTUACIONES_RSI"] == {"sobrecompra_extrema": 4, "sobrecompra": 6, "zona_alcista": 7, "zona_neutra": 5,
           "zona_bajista": 3, "sobreventa": 2, "sobreventa_extrema": 2}, "Doc. 22 §2.3 tabla RSI")
    idx = pd.bdate_range("2025-01-01", periods=260)
    sube = pd.Series(np.linspace(50, 100, 260), index=idx)
    h = pd.DataFrame({"Open": sube, "High": sube * 1.01, "Low": sube * 0.99, "Close": sube, "Volume": 1e6})
    _check(P["analizar_sma200"](h, 100.0, "X")["escenario_nota"] == "tendencia_alcista_encima", "Doc. 22 §2.1: alcista + encima")
    _check(P["analizar_sma200"](h, 60.0, "X")["escenario_nota"] == "positiva_debajo", "Doc. 22 §2.1: pendiente positiva + precio debajo")
    # Fibonacci por retroceso real y nota informativa (50–78,6 %)
    up = np.r_[np.linspace(100, 200, 200), np.linspace(200, 145, 52)]
    hf = pd.DataFrame({"Open": up, "High": up, "Low": up, "Close": up, "Volume": 1e6}, index=pd.bdate_range("2025-01-01", periods=252))
    f = P["analizar_fibonacci"](hf, 145.0, "X")
    _check(f["escenario"] == "retroceso_618" and "posible zona de rebote" in f["nota_informativa"], f"Doc. 22 §2.2: 55% → {f['escenario']}")
    f2 = P["analizar_fibonacci"](hf, 170.0, "X")
    _check(f2["escenario"] == "retroceso_382" and not f2["nota_informativa"], f"Doc. 22 §2.2: 30% → {f2['escenario']}")
    # RSI: sobreventa con nota informativa
    baja = pd.Series(np.r_[np.linspace(100, 98, 30), np.linspace(98, 60, 30)], index=pd.bdate_range("2025-01-01", periods=60))
    hr = pd.DataFrame({"Open": baja, "High": baja, "Low": baja, "Close": baja, "Volume": 1e6})
    r = P["analizar_rsi"](hr, 60.0, "X")
    _check(r["escenario"] in ("sobreventa", "sobreventa_extrema") and "posible rebote" in r["nota_informativa"]
           and "entrada" not in r["texto"], f"Doc. 22 §2.3: RSI {r['rsi_val']:.1f} {r['escenario']}")
    # Máximo anterior a la sesión actual (§2.4) y rótulo «Máximo desde» (E-2)
    hl = pd.DataFrame({"High": np.r_[np.linspace(50, 100, 99), 105.0], "Low": 40.0, "Close": 60.0},
                      index=pd.bdate_range("2012-01-02", periods=100))
    m = P["analizar_maximos_historicos"](hl, 103.0, "X")
    _check(m["ath"] == 100.0 and m["escenario"] == "subida_libre_establecida", f"Doc. 22 §2.4: {m['ath']} {m['escenario']}")
    m2 = P["analizar_maximos_historicos"](hl, 99.5, "X")
    _check(m2["escenario"] == "en_ath" and P["titulo_ficha"]("ath", m2) == "Máximo histórico (serie de Yahoo desde " + m2["desde"] + ")",
           "Doc. 23 E-2 / doc. 25 §3: rótulo del máximo con la serie de Yahoo")
    # Pivots del Diagnóstico: clásicos, sin diario (§2.6, E-8); redondeo hacia arriba en el 5 (§2.7)
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check("Diario" not in P["DIAG_TIMEFRAMES_NIVELES"] and 'calcular_todos_pivots(obtener_hist_pivots(ticker, hist), "Clásico",' in src,
           "Doc. 22 §2.6 / doc. 23 E-8: niveles del Diagnóstico")
    _check(P["diag_1d"](7.25) == 7.3 and P["diag_1d"](5.25) == 5.3 and P["diag_1d"](4.35) == 4.4 and P["diag_1d"](3.65) == 3.7,
           "Doc. 22 §2.7: redondeo hacia arriba en el 5")


def test_doc22_23_respaldo_y_textos():
    P = _APP
    sec = P["SECTOR_KNOWLEDGE"]["sectores"]
    _check(P["TICKER_SECTOR_FALLBACK"]["MRL.MC"] == "Real Estate" and P["TICKER_SECTOR_FALLBACK"]["COL.MC"] == "Real Estate"
           and P["TICKER_SECTOR_FALLBACK"]["ENG.MC"] == "Utilities" and P["TICKER_SECTOR_FALLBACK"]["VIS.MC"] == "Consumer Defensive",
           "Doc. 22 §4.5: tabla de sector de respaldo")
    fi = P["TICKER_INDUSTRIA_FALLBACK"]
    _check(P["sector_con_subtipo"](sec["Financial Services"], fi["MAP.MC"])["_subtipo_ciclo"] == "seguros"
           and P["sector_con_subtipo"](sec["Communication Services"], fi["CLNX.MC"])["_subtipo_ciclo"] == "telecos"
           and all(P["sector_con_subtipo"](sec["Financial Services"], fi[t])["_subtipo_ciclo"] == "banca"
                   for t in ("SAN.MC", "BBVA.MC", "CABK.MC", "SAB.MC", "BKT.MC", "UNI.MC")), "Doc. 22 §4.2: industria de respaldo")
    _check(P["sector_con_subtipo"](sec["Financial Services"], "Financial Data & Stock Exchanges")["_subtipo_ciclo"] == "gestoras de activos"
           and P["sector_con_subtipo"](sec["Financial Services"], "Capital Markets")["_subtipo_ciclo"] == "gestoras de activos",
           "Doc. 22 §4.1: Capital Markets y Financial Data con gestoras")
    itx = P["sector_con_subtipo"](sec["Consumer Cyclical"], fi["ITX.MC"])
    _check("Inditex" in itx["leccion_historica"] and itx["leccion_validada"] is True, "Doc. 23 E-6 / doc. 25 §5: lección ITX validada")
    _check("Redeia" in sec["Utilities"]["descripcion"] and "Red Eléctrica" not in sec["Utilities"]["descripcion"]
           and sec["Utilities"]["comportamiento_ciclo"]["pico"].startswith("positivo — los inversores rotan"), "Doc. 23 E-11")
    _check(not any("(costes fijos elevados)" in r for r in sec["Consumer Cyclical"]["riesgos_especificos"]), "Doc. 23 E-7")
    _check(P["tramos_contexto"]()["volatilidad"]["nota"] == "A más volatilidad, más oscila en euros la misma cantidad invertida.",
           "Doc. 23 E-10")
    a, pt = _diag_ntgy()
    _check("En las últimas 10 sesiones, el volumen se concentra en los días bajistas (84%)" in
           P["html_ficha_componente"]("vol", a["vol"], pt["scores_ind"]["vol"], 29.74), "Doc. 23 E-3: reparto del volumen")
    _check("Regla adicional" not in P["html_ficha_componente"]("vol", a["vol"], pt["scores_ind"]["vol"], 29.74)
           and "retira el tope" not in P["que_cambiaria_componente"]("vol", a["vol"], 29.74), "Doc. 23 E-9: tope que no actúa")
    alto = {**a["vol"], "escenario": "volumen_alto"}
    _check("retira el tope" in P["que_cambiaria_componente"]("vol", alto, 29.74), "Doc. 23 E-9: tope que sí actúa")
    sin = {**a["resist"], "resistencia": None, "soporte": None}
    _check("sin resistencia reforzada" in P["datos_componente"]("resist", sin, 10) and "sin soporte reforzado" in P["datos_componente"]("resist", sin, 10),
           "Doc. 23 E-4: concordancia")
    _check(P["_num_tip"](-0.00001) == "0,0000" and P["_num_tip"](-0.0668) == "−0,0668" and P["_num_tip"](0.0878) == "0,0878",
           "Doc. 23 E-5: signo y cero")


def test_doc25_pivots_mensuales_y_niveles():
    """Doc. 25 §1 — T-E8d (Paso 2 sin pivots semanales ni medias de 20) y T-E8e (pivot mensual)."""
    import pandas as pd, numpy as np
    P = _APP
    idx = pd.bdate_range("2025-01-02", "2026-11-06")
    rng = np.random.default_rng(7)
    c = pd.Series(30 + np.cumsum(rng.normal(0, 0.2, len(idx))), index=idx)
    h = pd.DataFrame({"Open": c.shift(1).fillna(c.iloc[0]), "High": c + 0.3, "Low": c - 0.3, "Close": c, "Volume": 1e6})
    # T-E8e: mes natural anterior (octubre de 2026)
    oc = h[(h.index.year == 2026) & (h.index.month == 10)]
    H, L, C, O = P["datos_sesion"](h, "Mensual")
    _check((H, L, C, O) == (float(oc["High"].max()), float(oc["Low"].min()), float(oc["Close"].iloc[-1]), float(oc["Open"].iloc[0])),
           "T-E8e: datos del mes natural anterior")
    pm = P["calcular_todos_pivots"](h, "Clásico", timeframes=("Mensual",))["Mensual"]
    _pp = pm.get("PP") if isinstance(pm, dict) else None
    _check(_pp is not None and abs(_pp - (H + L + C) / 3) < 1e-3, f"T-E8e: PP mensual = (H + L + C) / 3 ({_pp})")
    hj = h[h.index <= "2026-01-15"]   # enero → diciembre del año anterior
    dj = hj[(hj.index.year == 2025) & (hj.index.month == 12)]
    _check(P["datos_sesion"](hj, "Mensual")[0] == float(dj["High"].max()), "T-E8e: en enero usa diciembre del año anterior")
    _check(P["calcular_todos_pivots"](h, "Clásico").keys() == set(P["TIMEFRAMES"]), "Pivots: sin marcos indicados, los de siempre")
    # T-E8d: lo que recibe la convergencia desde niveles_diagnostico
    visto = {}
    orig_conv, orig_cache = P["calcular_convergencia_tecnica"], P["_hist_pivots_cache"]
    def _espia(rp, medias, precio, *a, **k):
        visto["tf"], visto["medias"] = set(rp), medias
        return [], [], None
    try:
        P["calcular_convergencia_tecnica"], P["_hist_pivots_cache"] = _espia, (lambda t: None)
        P["niveles_diagnostico"]("X.MC", h, float(c.iloc[-1]))
    finally:
        P["calcular_convergencia_tecnica"], P["_hist_pivots_cache"] = orig_conv, orig_cache
    _check(visto.get("tf") == {"Mensual", "Trimestral", "Anual"}, f"T-E8d: marcos del Paso 2 {visto.get('tf')}")
    _m = visto.get("medias") or {}
    _check(set(_m) == {50, 200} and all(np.isnan(v[1]) for v in _m.values()), f"T-E8d: solo SMA50 y SMA200 (sin EMA) {_m}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check("pivot clásico mensual, trimestral o anual que coincide con la SMA50 o la" in src
           and "pivot clásico semanal, trimestral o anual" not in src, "T-E8d: texto de la ficha")


def test_doc25_sin_niveles_y_redondeo():
    """Doc. 25 §2 (T-R1), §4 (redondeo) y avisos V-1 y V-3."""
    import copy
    import pandas as pd, numpy as np
    P = _APP
    _check(P["diag_1d"](6.05) == 6.1 and P["diag_1d"](5.75) == 5.8 and P["diag_1d"](7.25) == 7.3 and P["diag_1d"](3.65) == 3.7
           and P["diag_1d"](0.15 * 4 + 0.20 * 8 + 0.15 * 5 + 0.15 * 7 + 0.20 * 5 + 0.15 * 5) == 5.8, "Doc. 25 §4: redondeo con Decimal")
    _check(P["_PUNTUACIONES_RESIST"]["sin_niveles"] == 5, "T-R1: tramo «sin niveles reforzados cerca» = 5")
    idx = pd.bdate_range("2025-01-02", "2026-11-06")
    c = pd.Series(np.linspace(20, 30, len(idx)) + np.sin(np.arange(len(idx)) / 3.0) * 0.4, index=idx)
    h = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6})
    orig = {k: P[k] for k in ("niveles_diagnostico", "_hist_pivots_cache", "obtener_hist_maximo")}
    try:
        P["niveles_diagnostico"] = lambda *a, **k: []
        P["_hist_pivots_cache"] = lambda t: None
        P["obtener_hist_maximo"] = lambda *a, **k: h
        d = P["diagnostico_tecnico"]("X.MC", h, 30.0, "X", divergencias=[])
        d_corto = P["diagnostico_tecnico"]("X.MC", h.tail(150), 30.0, "X", divergencias=[])
    finally:
        P.update(orig)
    si = d["puntuacion"]["scores_ind"]
    _check(d["resist"]["escenario"] == "sin_niveles" and si["resist"]["disponible"] and si["resist"]["puntos"] == 5
           and all(v["disponible"] for v in si.values()), f"T-R1: sin confluencias → 5/10 {d['resist']}")
    calc = P["calculo_nota_global"](d["puntuacion"], d)
    _check("÷" not in calc["formula"] and "0,15 × 5 (resistencias" in calc["formula"].lower().replace("resistencias estructurales", "resistencias"),
           f"T-R1: sin repartir pesos {calc['formula']}")
    _check(d_corto["resist"] is None, "T-R1: «sin datos» solo si faltan sesiones o el pivot anual")
    crit = P["_cargar_criteria"]()
    f = P["html_ficha_componente"]("resist", d["resist"], si["resist"], 30.0, crit)
    for frag in ("Sin niveles reforzados cerca", "Ningún pivot mensual, trimestral o anual coincide con la SMA50 o la SMA200 (tolerancia: 0,3% del precio).",
                 "no apoya ni resta a la estructura", "llegue a coincidir con la SMA50 o la SMA200"):
        _check(frag in f, f"T-R1 ficha: falta «{frag}»")
    # V-1 y V-3: volumen
    a, pt = _diag_ntgy()
    fv = P["html_ficha_componente"]("vol", a["vol"], pt["scores_ind"]["vol"], 29.74, crit)
    _check("El volumen total está en línea con lo habitual." in fv and "no añade información" not in fv, "Doc. 25 V-1: volumen sin contradicción")
    _check("1,00 M / 1,20 M" in fv and "1.00M" not in fv, "Doc. 25 V-3: volumen con coma decimal")


def test_doc25_maximo_serie_completa_y_lecciones():
    """Doc. 25 §3 (máximo con toda la serie, guarda de serie no ajustada) y §5 (lecciones)."""
    import pandas as pd, numpy as np
    P = _APP
    idx = pd.bdate_range("2004-01-02", "2026-11-06")
    hi = np.full(len(idx), 30.0); hi[800] = 38.97            # máximo de 2007, dentro de la serie
    h = pd.DataFrame({"High": hi, "Low": 25.0, "Close": 29.54}, index=idx)
    m = P["analizar_maximos_historicos"](h, 29.54, "Naturgy")
    _check(m["ath"] == 38.97 and m["escenario"] == "referencia" and not m["serie_recortada"]
           and P["_PUNTUACIONES_ATH"]["referencia"] == 4 and m["desde"] == "02/01/2004", f"Doc. 25 §3: máximo de toda la serie {m['ath']} {m['escenario']}")
    _check("serie de Yahoo desde el 02/01/2004" in m["texto"] and "ajustada por operaciones de capital" in m["texto"],
           "Doc. 25 §3: texto del componente (informe y pantalla)")
    crit = P["_cargar_criteria"]()
    pt = P["calcular_puntuacion_tecnica"](m, None, None, None, None, None)
    fa = P["html_ficha_componente"]("ath", m, pt["scores_ind"]["ath"], 29.54, crit)
    _check("Serie ajustada por operaciones de capital (splits y ampliaciones), por eso puede no coincidir con el precio nominal de la época." in fa
           and P["titulo_ficha"]("ath", m) == "Máximo histórico (serie de Yahoo desde 02/01/2004)" and "toda su historia" not in fa
           and "serie disponible" in fa, "Doc. 25 §3: ficha del máximo")
    hi2 = hi.copy(); hi2[800] = 1946.0                      # tramo antiguo sin ajustar (caso COL.MC)
    m2 = P["analizar_maximos_historicos"](pd.DataFrame({"High": hi2, "Low": 25.0, "Close": 29.54}, index=idx), 29.54, "X")
    _check(m2["serie_recortada"] and m2["ath"] == 30.0 and "no está ajustado" in m2["texto"], f"Doc. 25 §3: guarda de serie no ajustada {m2['ath']}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check('history(period="max", auto_adjust=False)' in src and "Máximo desde" not in src, "Doc. 25 §3: periodo máximo")
    # §5 — lecciones
    cr = P["CRISIS_PATTERNS"]["crisis"]
    _check(len(cr) == 12 and all(c.get("leccion_validada") is True and c.get("fuente") and c.get("leccion_periodo") for c in cr.values()),
           "Doc. 25 §5: 12 lecciones de crisis validadas con fuente y periodo")
    _check("sin contar los cupones cobrados" in cr["inflacion_tipos_2022"]["leccion_operativa"], "Doc. 25 §5: matiz AGG")
    lc = P["leccion_con_fuente"]
    for k, c in cr.items():
        r = lc(c["leccion_operativa"], c["fuente"], c["leccion_periodo"], validada=c["leccion_validada"], ocultar_cifras=False)
        _check(not r["verificar"] and r["fuente_txt"].startswith("Fuente: "), f"Doc. 25 §5: lección de crisis {k}")
    en = P["SECTOR_KNOWLEDGE"]["sectores"]["Energy"]
    _check("−37,63 $" in en["leccion_historica"] and "120 $" in en["leccion_historica"] and "EIA" in en["leccion_fuente"]
           and en["leccion_validada"] is True, "Doc. 25 §5: lección de energía con la EIA")
    textos = " ".join(c["leccion_operativa"] for c in cr.values()).lower() + " " + en["leccion_historica"].lower()
    # Textos validados por Pólaris: «vender», «entrar» y «salir» aparecen como hechos («al vender todas a la
    # vez», «salir del mecanismo de cambios»), no como indicaciones; se comprueba la lista PA3.
    _malos = [t for t in TERMINOS_PA3 if t in textos] + _hay_compra_venta(textos)
    _check(not _malos, f"Doc. 25 §5: términos de operativa {_malos}")
    _check("Lección operativa" not in src and "💡 <b>Lección histórica:</b>" in src, "Doc. 25 §5: rótulo de las lecciones de crisis")
    # V-2 — textos del tramo «más de +10%»
    t = P["tramos_contexto"]()["dist_sma200"]
    _check("habituales" not in t["como_leerlo"] and "habituales" not in t["tramos"][0]["como_leerlo"]
           and "precio alejado de su referencia de largo plazo" in t["tramos"][0]["como_leerlo"], "Doc. 25 V-2: tramo «más de +10%»")


def test_doc26_ticker_pivot_mensual_y_lecciones():
    """Doc. 26 — G-1 (pivot mensual visible), G-2, G-3, lecciones sectoriales y ticker junto al nombre del paso."""
    P = _APP
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    # Ticker a continuación del nombre de cada paso (tarjetas del asistente y títulos)
    _check("_tk_tit = f' &#183; <span style=\"white-space:nowrap\">{_tk_e}</span>'" in src
           and "+ _wnm + _tk_tit +" in src and src.count('.replace("@@TK@@", _tk_tit)') == 2
           and "Paso 3 — Momento{_tk_tit}:" in src and "Niveles concretos{_tk_tit}:" in src,
           "Ticker junto al nombre del paso")
    # G-1
    _check(P["TIMEFRAMES"] == ["Diario", "Semanal", "Trimestral", "Anual"]
           and P["TIMEFRAMES_TABLA"] == ["Diario", "Semanal", "Mensual", "Trimestral", "Anual"]
           and "for tf in TIMEFRAMES_TABLA:" in src and '"pivots_mensual": _pm_cl' in src
           and "PP = (máx. + mín. + cierre) / 3" in src, "Doc. 26 G-1: pivot mensual en las tablas")
    # G-2
    crit = P["_cargar_criteria"]()
    _check(crit["diagnostico_paso2"]["como_leerlo"]["ath"]["referencia"].startswith("El precio está claramente por debajo del máximo de la serie, pero no lejos"),
           "Doc. 26 G-2: «Cómo leerlo» del tramo de distancia media")
    # G-3 y lecciones
    sec = P["SECTOR_KNOWLEDGE"]["sectores"]
    _check(all(v.get("leccion_validada") is True for v in sec.values()), "Doc. 26 §3: 11 lecciones sectoriales validadas")
    _check(not any("FABER" in str(v.get("leccion_fuente", "")) for v in sec.values())
           and sec["Energy"]["leccion_fuente"] == "EIA (series RCLC1 y RBRTE), comprobación de PivotAnalyzer", "Doc. 26 G-3")
    _check("un 39,7% (de 36,30 a 21,88 $)" in sec["Healthcare"]["leccion_historica"]
           and sec["Healthcare"]["leccion_periodo"] == "09/10/2007 – 09/03/2009", "Doc. 26 §3: Healthcare, mismo periodo")
    _check("5,22" not in sec["Consumer Cyclical"]["leccion_historica"] and "12,6% del PIB" in sec["Consumer Cyclical"]["leccion_historica"]
           and "ampliación de capital de 2020" in sec["Consumer Cyclical"]["leccion_fuente"], "Doc. 26 §3: Consumer Cyclical")
    _check("entre otros factores" in sec["Basic Materials"]["leccion_historica"]
           and "muy ligado a la demanda" not in sec["Basic Materials"]["leccion_historica"], "Doc. 26 §3: Basic Materials")
    _check("ampliaciones liberadas (scrip)" in sec["Communication Services"]["leccion_historica"], "Doc. 26 §3: Communication Services")
    _check("Por debajo de 50 indican contracción" in sec["Industrials"]["leccion_historica"] and sec["Industrials"]["leccion_fuente"],
           "Doc. 26 §3: Industrials reformulada")
    lc = P["leccion_con_fuente"]
    for k, v in sec.items():
        r = lc(v["leccion_historica"], v.get("leccion_fuente"), v.get("leccion_periodo"), v.get("leccion_cualitativa"), v.get("leccion_validada"))
        _check(not r["verificar"], f"Doc. 26 §3: lección {k} publicable")
    t = " ".join(v["leccion_historica"] for v in sec.values()).lower()
    _malos = [x for x in TERMINOS_PA3 if x in t] + _hay_compra_venta(t)
    _check(not _malos, f"Doc. 26 §3: términos de operativa {_malos}")


def test_doc27_incidencia_serie():
    """Doc. 27 — Registro de la guarda de series no ajustadas en incidencia_serie: se activa y se desactiva."""
    import json, os
    import pandas as pd, numpy as np
    import repositorio as R
    P = _APP
    idx = pd.bdate_range("2004-01-02", "2026-11-06")
    hi = np.full(len(idx), 13.0); hi[700] = 1946.42           # caso COL.MC
    h_mala = pd.DataFrame({"Open": 13.0, "High": hi, "Low": 12.0, "Close": 12.5, "Volume": 1e6}, index=idx)
    hi2 = hi.copy(); hi2[700] = 15.0
    h_buena = h_mala.assign(High=hi2)
    d = P["detalle_serie_ath"](h_mala)
    _check(d and d["ratio"] > 20 and d["fecha_max_total"] == idx[700].strftime("%Y-%m-%d") and d["umbral"] == 20.0,
           f"Doc. 27: detalle de la guarda {d}")
    _check(P["detalle_serie_ath"](h_mala.tail(300)) is None, "Doc. 27: serie de menos de 15 años → sin detalle")
    # El Diagnóstico (función única) activa y desactiva el registro
    llamadas = []
    orig = {k: P[k] for k in ("_registrar_guarda_serie", "obtener_hist_maximo", "niveles_diagnostico", "_hist_pivots_cache")}
    try:
        P["_registrar_guarda_serie"] = lambda tk, activa, det="": llamadas.append((tk, activa, det))
        P["niveles_diagnostico"] = lambda *a, **k: []
        P["_hist_pivots_cache"] = lambda t: None
        for h in (h_mala, h_buena):
            P["obtener_hist_maximo"] = lambda *a, _h=h, **k: _h
            P["diagnostico_tecnico"]("COL.MC", h.tail(400), 12.5, "Colonial", divergencias=[])
    finally:
        P.update(orig)
    _check(len(llamadas) == 2 and llamadas[0][:2] == ("COL.MC", True) and json.loads(llamadas[0][2])["ratio"] > 20
           and llamadas[1] == ("COL.MC", False, ""), f"Doc. 27: activa y desactiva desde el Diagnóstico {llamadas}")
    # Repositorio: SQL emitido (conexión simulada)
    class _Cur:
        def __init__(s, log, err=None): s.log, s.err = log, err
        def execute(s, sql, params=None):
            if s.err: raise Exception(s.err)
            s.log.append((sql, params))
    class _Conn:
        def __init__(s, err=None): s.log, s.err, s.commits = [], err, 0
        def cursor(s): return _Cur(s.log, s.err)
        def commit(s): s.commits += 1
        def rollback(s): pass
    c = _Conn()
    _check(R.registrar_incidencia_serie(c, "col.mc", R.TIPO_SERIE_NO_AJUSTADA_ATH, True, {"ratio": 147.12}) is None
           and "ON CONFLICT (ticker, tipo) DO UPDATE" in c.log[0][0] and c.log[0][1][0] == "COL.MC" and c.commits == 1,
           "Doc. 27: activar = INSERT … ON CONFLICT")
    _check(R.registrar_incidencia_serie(c, "COL.MC", R.TIPO_SERIE_NO_AJUSTADA_ATH, False) is None
           and c.log[1][0].startswith("UPDATE incidencia_serie SET activa = false") and "primera_vez" not in c.log[0][0].split("DO UPDATE")[1],
           "Doc. 27: desactivar = UPDATE; primera_vez se conserva")
    _check("migracion_incidencia_serie.sql" in R.registrar_incidencia_serie(
               _Conn('relation "incidencia_serie" does not exist'), "COL.MC", "x", True, {}),
           "Doc. 27: sin tabla, aviso claro y sin excepción")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    sql = (_A._RUTA_APP.parent / "migracion_incidencia_serie.sql").read_text(encoding="utf-8")
    _check("CREATE TABLE IF NOT EXISTS incidencia_serie" in sql and "CREATE INDEX IF NOT EXISTS" in sql
           and "-- DROP TABLE IF EXISTS incidencia_serie;" in sql and "incidencias" not in src[src.index("def _registrar_guarda_serie"):src.index("def cortes_diagnostico")].replace("incidencia_serie", ""),
           "Doc. 27: migración idempotente con reversión y sin tocar `incidencias`")
    _check(P["_cargar_criteria"]()["diagnostico_paso2"]["que_es"]["sma200"].startswith("Hacia dónde va la media de los últimos 200 cierres"),
           "Doc. 27 H-2: «Qué es» de la SMA200")
    # En vivo contra Postgres (opcional): set PA_PG_DSN=postgresql://… (base de pruebas)
    dsn = os.environ.get("PA_PG_DSN")
    if not dsn:
        print("ℹ️  T-D27 en vivo no ejecutado (activa con: set PA_PG_DSN=<base de pruebas>)")
        return
    import psycopg2, uuid
    esq = "pa_test_" + uuid.uuid4().hex[:8]
    cn = psycopg2.connect(dsn)
    try:
        cur = cn.cursor(); cur.execute(f"CREATE SCHEMA {esq}"); cur.execute(f"SET search_path TO {esq}"); cn.commit()
        for _ in range(2):                                   # idempotente
            cur.execute(sql); cn.commit()
        lee = lambda: R.leer_incidencias_serie(cn, solo_activas=False)
        R.registrar_incidencia_serie(cn, "COL.MC", R.TIPO_SERIE_NO_AJUSTADA_ATH, True, {"ratio": 147.12})
        f1 = lee()
        R.registrar_incidencia_serie(cn, "COL.MC", R.TIPO_SERIE_NO_AJUSTADA_ATH, True, {"ratio": 150.0})
        f2 = lee()
        R.registrar_incidencia_serie(cn, "COL.MC", R.TIPO_SERIE_NO_AJUSTADA_ATH, False)
        f3 = lee()
        R.registrar_incidencia_serie(cn, "ITX.MC", R.TIPO_SERIE_NO_AJUSTADA_ATH, False)   # sin fila: no crea nada
        f4 = lee()
        _check(len(f1) == 1 and f1[0]["activa"] and f1[0]["detalle"]["ratio"] == 147.12, f"T-D27 vivo: alta {f1}")
        _check(len(f2) == 1 and f2[0]["detalle"]["ratio"] == 150.0 and f2[0]["primera_vez"] == f1[0]["primera_vez"]
               and f2[0]["ultima_vez"] >= f1[0]["ultima_vez"], "T-D27 vivo: actualización sin duplicar")
        _check(len(f3) == 1 and f3[0]["activa"] is False and R.leer_incidencias_serie(cn) == [], "T-D27 vivo: desactivación")
        _check(len(f4) == 1, "T-D27 vivo: desactivar un valor sin fila no crea nada")
        cur.execute("DROP TABLE IF EXISTS incidencia_serie"); cn.commit()   # DOWN
        cur.execute("SELECT to_regclass('incidencia_serie')"); _check(cur.fetchone()[0] is None, "T-D27 vivo: reversión")
    finally:
        cn.rollback(); cur = cn.cursor(); cur.execute(f"DROP SCHEMA IF EXISTS {esq} CASCADE"); cn.commit(); cn.close()


def test_pe_v4_sar_parabolico():
    """Spec PE v4 (PE-16/PE-21) — SAR parabólico de Wilder 0,02/0,2, igual que TA-Lib (valores de referencia
    calculados con TA-Lib 0.6, TA_SAR, sobre esta misma serie)."""
    import numpy as np, pandas as pd
    P = _APP
    k = np.arange(80)
    c = 50 + 4 * np.sin(k / 7.0) + k * 0.05
    h = np.round(c + 0.6 + 0.3 * np.cos(k / 3.0), 4); l = np.round(c - 0.6 - 0.2 * np.sin(k / 5.0), 4)
    sar, tr, _sig = P["psar_wilder"](h, l)
    ref = [51.0851, 50.9224, 50.8046, 49.141, 49.172928]
    _check(np.allclose(sar[-5:], ref, atol=1e-6) and tr[-5:].tolist() == [-1, -1, -1, 1, 1]
           and [i for i in range(2, 80) if tr[i] != tr[i - 1]] == [14, 34, 57, 78], f"PE v4: SAR = TA-Lib {sar[-5:]}")
    hist = pd.DataFrame({"Open": c, "High": h, "Low": l, "Close": c, "Volume": 1e6}, index=pd.bdate_range("2026-01-01", periods=80))
    d = P["calcular_sar_detalle"](hist)
    _check(d["tendencia"] == "ALCISTA" and d["fecha_giro"] == hist.index[78].strftime("%d/%m/%Y") and d["sesiones_desde_giro"] == 1
           and P["calcular_sar"](hist) == (round(ref[-1], 4), "ALCISTA"), f"PE v4: detalle del SAR {d}")
    # Caída sostenida → bajista (el «SAR» anterior, mínimo de 5 sesiones, daba alcista con cualquier rebote)
    b = 100 - k * 0.5 + np.where(k == 79, 1.2, 0)
    hb = pd.DataFrame({"Open": b, "High": b + 0.3, "Low": b - 0.3, "Close": b, "Volume": 1e6}, index=pd.bdate_range("2026-01-01", periods=80))
    _check(P["calcular_sar"](hb)[1] == "BAJISTA", "PE v4: SAR bajista en caída con rebote de un día")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check('hist["Low"].rolling(5).min()' not in src, "PE v4: retirado el «SAR» de mínimo de 5 sesiones")


def _hist_p3(n=120, sube=True, seed=3):
    import numpy as np, pandas as pd
    rng = np.random.default_rng(seed)
    c = 30 + np.cumsum(rng.normal(0.05 if sube else -0.05, 0.3, n))
    idx = pd.bdate_range("2026-05-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c + 0.4, "Low": c - 0.4, "Close": c,
                         "Volume": rng.integers(800_000, 1_200_000, n).astype(float)}, index=idx)


def test_pe_v4_paso3_reglas_doc28():
    """Doc. 28 — Reglas nuevas: T-a (volumen alto en sesión bajista), T-b/c (extremos), T-h (corte sin redondear),
    T-PE-17b/c (cortes de la configuración, factor no disponible), mínimo de 4 factores, Bollinger poblacional."""
    import copy
    import numpy as np, pandas as pd
    P = _APP
    P.setdefault("PANDAS_TA", False)
    ev = P["evaluar_semaforo"]
    pv = {"_H": 31.0, "_L": 29.0, "_C": 30.0}                    # PP = 30
    vol = lambda r, alc: {"volumen": 1.0, "media_10d": 1.0, "ratio_10d": r, "sesion_alcista": alc}
    # T-a — volumen
    _check(ev(30.5, pv, 60, 1, 0, 32, 28, vol(130, False), "ALCISTA")["factores"]["vol"]["puntos"] == 0
           and ev(30.5, pv, 60, 1, 0, 32, 28, vol(130, True), "ALCISTA")["factores"]["vol"]["puntos"] == 1
           and ev(30.5, pv, 60, 1, 0, 32, 28, vol(100, False), "ALCISTA")["factores"]["vol"]["puntos"] == 0.5
           and ev(30.5, pv, 60, 1, 0, 32, 28, vol(50, False), "ALCISTA")["factores"]["vol"]["puntos"] == 0.5,
           "T-a: volumen alto bajista 0 · alto alcista 1 · normal 0,5 · bajo 0,5")
    # T-b/c — extremos del RSI y de %B con la misma etiqueta en semáforo, consenso y convergencia
    f = ev(30.5, pv, 72, 1, 0, 32, 28, vol(100, True), "ALCISTA")["factores"]
    _, señ, _ = P["calcular_convergencia_tecnica"]({}, {}, 30.5, 72, 1, 0, 0.1, "ALCISTA", 85)
    con_rsi = next(l for nm, l, *_ in señ if nm == "RSI 14"); dir_rsi = next(dd for nm, _l, dd, *_ in señ if nm == "RSI 14")
    con_bb = next(l for nm, l, *_ in señ if nm == "Bollinger %B"); dir_bb = next(dd for nm, _l, dd, *_ in señ if nm == "Bollinger %B")
    _check(f["rsi"]["puntos"] == 0.75 and f["rsi"]["etiqueta"] == "Alcista en sobrecompra" and "Alcista en sobrecompra" in con_rsi
           and dir_rsi == "alcista" and P["etiqueta_rsi"](72) == "Alcista en sobrecompra", f"T-b: RSI 72 {f['rsi']} {con_rsi} {dir_rsi}")
    f2 = ev(30.5, pv, 25, 1, 0, 32, 28, vol(100, True), "ALCISTA")["factores"]
    _check(f2["rsi"]["puntos"] == 0 and f2["rsi"]["etiqueta"] == "Bajista en sobreventa"
           and P["clasificar_rsi"](25)[1] == "bajista", "T-b: RSI 25 → 0, bajista en sobreventa")
    fb = ev(31.8, pv, 60, 1, 0, 32, 28, vol(100, True), "ALCISTA")["factores"]["bb"]      # %B 95
    _check(fb["puntos"] == 0.75 and fb["etiqueta"] == "Parte alta del canal" and "Parte alta del canal" in con_bb and dir_bb == "alcista"
           and ev(28.2, pv, 60, 1, 0, 32, 28, vol(100, True), "ALCISTA")["factores"]["bb"]["puntos"] == 0, "T-c: extremos de %B")
    # T-PE-16e — %B con un decimal
    _check(fb["valor_txt"] == "95,0%", f"T-PE-16e: %B con un decimal ({fb['valor_txt']})")
    # T-h — REP 4/6 = 66,7 % → verde con el corte sin redondear; 65 exacto → verde; 64,9 → amarillo
    r = ev(29.90, {"_H": 30.5, "_L": 29.11, "_C": 30.21}, 52.62, 0.2135, 0.1, 31, 28, vol(115, True), "ALCISTA")
    _check(abs(r["pct"] - 66.6667) < 1e-3 and r["color"] == "verde" and P["_pct_entero"](r["pct"]) == 67, f"T-h: REP {r['pct']} {r['color']}")
    crit = copy.deepcopy(P["_cargar_criteria"]())
    crit["semaforo_paso3"]["cortes"]["verde"] = 66.7
    r2 = ev(29.90, {"_H": 30.5, "_L": 29.11, "_C": 30.21}, 52.62, 0.2135, 0.1, 31, 28, vol(115, True), "ALCISTA", criterios=crit)
    _check(r2["color"] == "amarillo" and "≥ 67%" in P["html_calculo_semaforo"](r2, crit), "T-PE-17b: el corte de la configuración cambia el tramo")
    # T-PE-17c y mínimo de 4 factores
    r3 = ev(30.5, pv, 60, 1, 0, 32, 28, None, "ALCISTA")
    h3 = P["html_calculo_semaforo"](r3)
    _check(r3["n_disponibles"] == 5 and "/ 5 =" in h3 and "sin volumen fiable en la sesión" in h3 and "sobre los 5 restantes" in h3,
           "T-PE-17c: factor no disponible baja el denominador y se explica")
    r4 = ev(30.5, None, None, 1, 0, 32, 28, None, "ALCISTA")
    _check(r4["color"] == "gris" and "Datos insuficientes para el semáforo (3 de 6 factores)" in P["html_calculo_semaforo"](r4)
           and "Datos insuficientes" in P["conclusion_paso3"](r4, {}, None)["texto"], "Doc. 28 e): menos de 4 factores → gris")
    # T-PE-17a — el cálculo visible reproduce el porcentaje
    _check("4 / 6 = 66,7% → 67%" in P["html_calculo_semaforo"](r), "T-PE-17a: cálculo visible")
    # Doc. 28 g) — Bollinger con desviación poblacional
    serie = pd.Series(np.r_[np.linspace(10, 12, 19), 12.5])
    sup, med, inf, _pb = P["calcular_bollinger"](serie)
    _check(abs((sup - med) - 2 * float(serie.std(ddof=0))) < 1e-3, "Doc. 28 g): Bollinger con desviación poblacional")
    # Volumen con dirección de la sesión
    h = _hist_p3()
    v = P["analisis_volumen"](h)
    _check(v["sesion_alcista"] == (h["Close"].iloc[-1] > h["Close"].iloc[-2]) and v["var_pct"] is not None, "Doc. 28 a): dirección de la sesión")


def test_pe_v4_paso3_fichas_y_conclusion():
    """PE-16, PE-18, PE-19, PE-20 y PE-21 — fichas, tres niveles, conclusión, coherencia con el informe."""
    import re as _r
    P = _APP
    P.setdefault("PANDAS_TA", False)
    h = _hist_p3()
    c = h["Close"]; precio = float(c.iloc[-1])
    rp = P["calcular_todos_pivots"](h, "Clásico")
    rsi = P["calcular_rsi"](c); m, ms, mh = P["calcular_macd"](c); bs, bm, bi, pb = P["calcular_bollinger"](c)
    vol = P["analisis_volumen"](h); sar_v, sar_t = P["calcular_sar"](h)
    sem = P["evaluar_semaforo"](precio, rp["Diario"], rsi, m, ms, bs, bi, vol, sar_t)
    d3 = P["datos_paso3"](h, rp["Diario"], precio)
    # T-PE-20a — Paso 3 = informe (misma función); T-PE-20c — con Camarilla el PP sigue siendo el clásico
    col, pct, fac = P["calcular_semaforo"](precio, rp["Diario"], rsi, m, ms, bs, bi, vol, sar_t)
    _check(col == sem["color"] and pct == sem["pct"] and len(fac) == sem["n_disponibles"], "T-PE-20a: Paso 3 = informe")
    cam = P["calcular_todos_pivots"](h, "Camarilla")
    _check(P["evaluar_semaforo"](precio, cam["Diario"], rsi, m, ms, bs, bi, vol, sar_t)["pp"] == sem["pp"], "T-PE-20c: PP clásico con Camarilla")
    # T-PE-16d — mismo RSI que el Paso 2
    _check(d3["rsi"]["valor"] == rsi and abs(P["analizar_rsi"](h, precio, "X")["rsi_val"] - rsi) < 0.01, "T-PE-16d: RSI del Paso 3 = Paso 2")
    # T-PE-16a/b, T-PE-18a — fichas
    crit = P["_cargar_criteria"]()
    for k in P["SEM_FACTORES"]:
        f = sem["factores"][k]
        tit = P["titulo_factor"](k, f)
        _check(not _r.search(r"\b[a-z]+_[a-z_]+\b", tit) and "/1)" in tit, f"T-PE-16a: título sin códigos ({tit})")
        fi = P["html_ficha_factor"](k, f, d3, crit)
        for frag in ("Qué es:", "Datos usados:", "Parámetros y por qué:", "◀", "Cómo leerlo:", "Qué cambiaría esta puntuación:",
                     "Más detalle: fórmula y limitaciones"):
            _check(frag in fi, f"T-PE-16b/18a: ficha {k} sin «{frag}»")
        qc = P["que_cambiaria_factor"](k, f, d3)
        _check(qc.startswith(P["SEM_TITULOS"][k].split(" (")[0].split(" 14")[0]) or qc.startswith(("RSI", "MACD", "SAR", "Bollinger", "Volumen")),
               f"E-1: «qué cambiaría» empieza por el indicador ({qc})")
        _check(any(w in crit["semaforo_paso3"]["mas_detalle"][k] for w in ("puede", "no tiene", "retraso", "distorsionan", "gira")),
               f"T-PE-18a: el nivel avanzado de {k} incluye una limitación")
    _check("No disponible" not in P["datos_factor_txt"]("pp", sem["factores"]["pp"], d3) and "PP = (máx. + mín. + cierre) / 3" in
           P["datos_factor_txt"]("pp", sem["factores"]["pp"], d3), "T-PE-16b: datos del PP con fórmula")
    fv = P["datos_factor_txt"]("vol", sem["factores"]["vol"], d3)
    _check("Sesión completa del" in fv and "sesión" in fv, "T-PE-16c: el volumen indica la sesión usada")
    vc = dict(vol); vc["sesion_en_curso_descartada"] = True
    _check("La sesión en curso no se usa" in P["datos_factor_txt"]("vol", sem["factores"]["vol"], {**d3, "vol": vc}),
           "T-PE-16c: sesión en curso indicada")
    _check("que el mínimo de una sesión baje de" in P["que_cambiaria_factor"]("sar", {"disponible": True, "escenario": "alcista"}, d3)
           and "que el máximo de una sesión supere" in P["que_cambiaria_factor"]("sar", {"disponible": True, "escenario": "bajista"}, d3),
           "Doc. 28 f): «qué cambiaría» del SAR con mínimo / máximo")
    _check("acelera" in P["datos_factor_txt"]("macd", sem["factores"]["macd"], d3) or "frena" in P["datos_factor_txt"]("macd", sem["factores"]["macd"], d3),
           "Doc. 28 d): histograma informativo del MACD")
    # PE-19 — conclusión y matriz con el Paso 2
    for tr2, sc in (("alcista", 7.3), ("mixta", 5.0), ("bajista", 2.0)):
        for colr, rel in (("verde", {"alcista": "coherente", "mixta": "matiza", "bajista": "contradice"}[tr2]),
                          ("amarillo", {"alcista": "matiza", "mixta": "coherente", "bajista": "matiza"}[tr2]),
                          ("rojo", {"alcista": "contradice", "mixta": "matiza", "bajista": "coherente"}[tr2])):
            s2 = dict(sem); s2["color"] = colr
            _check(P["conclusion_paso3"](s2, d3, {"score_total": sc})["relacion"] == rel, f"PE-19: matriz {tr2} × {colr}")
    cc = P["conclusion_paso3"](sem, d3, {"score_total": 7.3})
    _check(cc["texto"].startswith("<b>Conclusión del Paso 3: momento") and "A favor:" in cc["texto"] and "En contra:" in cc["texto"]
           and "Relación con la estructura (Paso 2):" in cc["texto"], f"PE-19: conclusión {cc['texto']}")
    if cc.get("factor_qc"):
        _qc = cc["texto"].split("Qué cambiaría esta lectura:</b> ")[1]
        _check(_qc.startswith(("Precio frente", "RSI", "MACD", "Bollinger", "Volumen", "SAR")), "PE-19: qué cambiaría empieza por el indicador")
    # Zonas que vigila el método: notas del Paso 2
    z = P["zonas_vigila"]({"fibo": {"nota_informativa": "x", "retroceso_max_pct": 55.1}}, sem)
    _check(z and z[0].startswith("Retroceso del 55,1% del swing anual (Paso 2)") and "En el Paso 3: MACD" in z[0], f"PE-19: zonas {z}")
    # Redacción: sin indicaciones de operativa en textos del semáforo (informe y Paso 3)
    p3 = crit["semaforo_paso3"]
    textos = " ".join([json_dump(p3), P["_interpretacion_semaforo"]("verde", 71, P["tuplas_semaforo"](sem)), cc["texto"]]).lower()
    # Doc. 28 v2: se admiten las lecturas de escenario («favorable para posiciones largas», «invalidación»); no se
    # admiten imperativos dirigidos al usuario (T-L2)
    _malos = [t for t in tuple(TERMINOS_PA3) + ("probabilidad", "trampa") if t in textos] + _hay_compra_venta(textos)
    _malos += _r.findall(r"\b(?:compra|vende|entra|compre|venda|vendan|compren)\b", textos)
    _check(not _malos, f"PE-13/doc. 28 v2 (T-L2): términos no admitidos {_malos}")
    src = _A._RUTA_APP.read_text(encoding="utf-8")
    _check("trampa frecuente para principiantes" not in src and "Aunque la estructura sea buena" not in src,
           "Doc. 28: textos fijos S-6 y S-7 retirados")


def json_dump(o):
    import json
    return json.dumps(o, ensure_ascii=False)


def test_doc28_v2_lecturas_escenario():
    """Doc. 28 v2 — T-L1: lectura, invalidación con los valores del día y combinación con el Paso 2 por color;
    T-L2: sin imperativos dirigidos al usuario."""
    import re as _r
    P = _APP
    sar_up = {"sar_siguiente": 56.3813, "tendencia": "ALCISTA"}
    sar_dn = {"sar_siguiente": 30.2776, "tendencia": "BAJISTA"}
    le = P["lectura_escenario"]
    # ITX: verde, estructura alcista 7,3; precio bajo el PP → solo la cláusula del SAR
    a = le("verde", 59.04, 60.0533, sar_up, {"score_total": 7.3})
    _check(a["lectura"].startswith("Lectura del método: los indicadores de corto plazo están alineados al alza")
           and "favorable para posiciones largas (compradoras)" in a["lectura"]
           and a["invalidacion"] == "La lectura se invalidaría si el mínimo de una sesión baja del SAR (56,38 €)."
           and a["combinacion"].startswith("El momento y la estructura apuntan en el mismo sentido"), f"T-L1 ITX: {a}")
    # Verde con precio sobre el PP → dos cláusulas
    a2 = le("verde", 61.0, 60.0533, sar_up, {"score_total": 7.3})
    _check("o si el cierre queda bajo el pivot diario (60,05 €)" in a2["invalidacion"], f"T-L1: verde con PP {a2['invalidacion']}")
    # REP: verde, estructura mixta 6,1
    r = le("verde", 29.90, 29.94, {"sar_siguiente": 28.8344, "tendencia": "ALCISTA"}, {"score_total": 6.1})
    _check(r["combinacion"].startswith("La estructura del Paso 2 es mixta") and "28,83 €" in r["invalidacion"], f"T-L1 REP: {r}")
    # NTGY: rojo, SAR bajista y precio bajo el PP → dos cláusulas; estructura mixta
    n = le("rojo", 29.54, 29.7267, sar_dn, {"score_total": 5.8})
    _check("desfavorable para posiciones largas" in n["lectura"]
           and n["invalidacion"] == ("La lectura se invalidaría si el máximo de una sesión supera el SAR (30,28 €) o si el "
                                     "cierre queda sobre el pivot diario (29,73 €).")
           and n["combinacion"].startswith("La estructura del Paso 2 es mixta"), f"T-L1 NTGY: {n}")
    # SAN: rojo con SAR alcista → solo la cláusula del pivot
    s_ = le("rojo", 10.696, 10.8413, {"sar_siguiente": 10.1184, "tendencia": "ALCISTA"}, {"score_total": 3.7})
    _check("SAR" not in s_["invalidacion"] and "pivot diario (10,84 €)" in s_["invalidacion"], f"T-L1 SAN: {s_['invalidacion']}")
    # Amarillo: cortes leídos de criteria.json; sentido contrario
    y = le("amarillo", 10.0, 10.0, sar_up, {"score_total": 7.3})
    _check(y["invalidacion"] == "La lectura cambiaría si el semáforo llega al 65% o baja del 40%."
           and "sin sesgo" in y["lectura"], f"T-L1 amarillo: {y}")
    d = le("verde", 10.0, 9.0, sar_up, {"score_total": 2.0})
    _check(d["combinacion"].startswith("El momento va en sentido contrario a la estructura del Paso 2 (2,0/10, estructura bajista)"),
           f"T-L1 sentido contrario: {d['combinacion']}")
    _check(a["aviso"] == "Describe un escenario técnico; no es una señal automática ni sustituye a la gestión del riesgo."
           and a["nota_fija"].startswith("Las lecturas describen el escenario técnico según el método"), "Doc. 28 v2: aviso y nota fija")
    # Informe: el Semáforo Global incluye la lectura
    t = P["_interpretacion_semaforo"]("rojo", 16.7, [("SAR", "x", 0)], precio=29.54, pp=29.7267, sar_det=sar_dn, pt_paso2={"score_total": 5.8})
    _check("**Lectura del método:**" in t and "**Invalidación:**" in t and "no es una señal automática" in t, "T-L1: informe con lectura")
    # Glosario
    g = P["GLOSARIO"]["terminos"] if "GLOSARIO" in P else __import__("json").load(open(_A._RUTA_APP.parent / "glosario.json", encoding="utf-8"))["terminos"]
    _check(all(k in g for k in ("posición larga", "posición corta", "invalidación")), "Doc. 28 v2: glosario")
    # T-L2
    textos = " ".join(str(v) for v in (a, a2, r, n, s_, y, d)).lower() + " " + t.lower()
    _malos = _r.findall(r"\b(?:compra|vende|entra|compre|venda|vendan|compren)\b", textos)
    _check(not _malos, f"T-L2: imperativos dirigidos al usuario {_malos}")


def _dependencias_ok() -> bool:
    """Los tests de la Spec PA v2 ejecutan el motor real, que necesita pandas y numpy.
    Si faltan, se avisa con la instrucción exacta en vez de fallar con errores confusos."""
    import importlib.util as _ilu
    faltan = [m for m in ("pandas", "numpy") if _ilu.find_spec(m) is None]
    if faltan:
        print(f"⚠️  Faltan librerías en este Python: {', '.join(faltan)}.")
        print("   Instálalas una vez con:")
        print("       python -m pip install -r requirements.txt pypdf")
        print("   y vuelve a lanzar:  python tests_regresion_pa.py")
        return False
    return True


def main():
    if not _dependencias_ok():
        return 2
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
    for _a in _avisos:
        print("ℹ️ ", _a)
    print("✅ Contrato de regresión Spec PA v1 + v2 + v3 + Spec PE v1 + v2 + v3 — TODOS los tests unitarios PASAN.")
    print("   (PA-A-06/PA-M-02/03/04 y la revisión visual de PA2-01 se verifican sobre informes reales.)")
    print("   ⏸  T-PA2-03c pendiente de decisión de Polaris (payout crudo 7,5 sin DPA/BPA: el")
    print("      normalizador lo lee como 7,5 % y la spec espera N/A + K8).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
