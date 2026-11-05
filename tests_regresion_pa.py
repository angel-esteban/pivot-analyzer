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
    _check(vistas >= 6, f"PA3-02: se esperaban ≥6 descargas de histórico revisadas (vistas {vistas})")
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
    _check(_k8 is None or "rec" not in (_k8.get("razon") or "").lower(),
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
    for rsi, esperado in ((57.67, "Alcista"), (50, "Neutro"), (72, "Sobrecompra"), (28, "Sobreventa")):
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
    for k, objetivo in zip(["ath", "sma200", "resist", "fibo", "rsi", "vol"], [7, 7, 8, 7, 7, 7]):
        t = _APP[tab[k]]
        esc = next(e for e, p in t.items() if p == objetivo)
        comps.append({"escenario": esc})
    pt = _APP["calcular_puntuacion_tecnica"](*comps)
    _check(f"{pt['score_total']:.1f}" == "7.2", f"T-PA3-05e: diagnóstico {pt['score_total']} (esperado 7,2)")
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
    mrl = _A.serie_pagos([("2024-11-22", 0.1458), ("2025-05-08", 0.21637),
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
    cut = _A.serie_pagos([("2025-05-10", 0.60), ("2025-10-10", 0.60), ("2026-05-08", 0.40), ("2026-10-09", 0.40)])
    _check(_APP["evaluar_recorte_reciente"](cut, ref=ref)["estado"] == "recorte", "V3-2: recorte real no detectado")
    # Recorte solo en el último pago pero TTM estable → no dispara
    uno = _A.serie_pagos([("2025-05-10", 0.30), ("2025-10-10", 0.90), ("2026-05-08", 0.85), ("2026-10-09", 0.20)])
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
    yahoo = _A.serie_pagos([("2024-11-22", 0.18), ("2025-05-08", 0.22), ("2025-11-21", 0.20), ("2026-05-07", 0.0151)])
    man = [{"ticker": "MRL.MC", "fecha_ex": "2026-05-07", "importe_bruto": 0.0151, "tipo": "dividendo",
            "url_origen": URL, "activo": True},
           {"ticker": "MRL.MC", "fecha_ex": "2026-05-07", "importe_bruto": 0.20492995, "tipo": "prima",
            "url_origen": URL, "activo": True}]
    ser, ev = _APP["aplicar_dividendos_manuales"]("MRL.MC", yahoo, manuales=man)
    ttm = _APP["dpa_ttm"](ser, ref=ref)
    _check(abs(ttm - 0.42002995) < 1e-6, f"Decisión 3: TTM bruto MRL con prima = {ttm} (esperado 0,4200)")
    rc = _APP["evaluar_recorte_reciente"](ser, ref=ref)
    _check(rc["estado"] == "sin_recorte", f"Decisión 3: MRL sin K-RECENT_CUT ({rc})")
    _check(len(ser) == 4, "Decisión 3: el pago manual sustituye al de Yahoo del mismo evento (no se suma)")
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
    print("✅ Contrato de regresión Spec PA v1 + v2 + v3 — TODOS los tests unitarios PASAN.")
    print("   (PA-A-06/PA-M-02/03/04 y la revisión visual de PA2-01 se verifican sobre informes reales.)")
    print("   ⏸  T-PA2-03c pendiente de decisión de Polaris (payout crudo 7,5 sin DPA/BPA: el")
    print("      normalizador lo lee como 7,5 % y la spec espera N/A + K8).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
