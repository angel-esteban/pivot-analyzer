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


# ─────────────────────────────────────────────────────────────────────────────
_avisos: list[str] = []


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
    print("✅ Contrato de regresión Spec PA v1 + v2 — TODOS los tests unitarios PASAN.")
    print("   (PA-A-06/PA-M-02/03/04 y la revisión visual de PA2-01 se verifican sobre informes reales.)")
    print("   ⏸  T-PA2-03c pendiente de decisión de Polaris (payout crudo 7,5 sin DPA/BPA: el")
    print("      normalizador lo lee como 7,5 % y la spec espera N/A + K8).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
