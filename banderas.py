# -*- coding: utf-8 -*-
"""
banderas.py — Motor de avisos v2 (Spec v2 §3-4). Estimadores del payout + tres banderas.

Diseño (decisiones D-006 + refinamientos Pólaris 2026-07-29):
  · PURO y testeable: no toca Neon ni Streamlit. El motor (app.py) construye el contexto
    con los valores que YA calcula y llama aquí; este módulo solo razona y devuelve banderas.
  · Estimadores AL VUELO (no se persisten en tablas vigentes). yfinance solo estima, nunca
    aterriza en bpa_ejercicio.
  · Zona segura vs zona de riesgo: un estimador cómodamente claro (sin bandera) deja que el
    motor emita "Cumple"; un valor MARCADO se capa a "revisar", nunca "Cumple".
  · Silencio de una bandera: (a) override 'vigente' curado, o (b) acuse anclado a la HUELLA
    (fingerprint) de los valores en conflicto — si el dato se mueve, la huella cambia y la
    bandera reaparece.
  · El 'vigente' curado manda; el estimador sigue vigilando en 2º plano: si diverge mucho del
    curado → bandera SUAVE (posible obsolescencia), que avisa pero NO cambia el veredicto.

Umbrales orientativos §4, marcados [VERIFICAR] — parámetros de diseño, no verdad cerrada.
"""
from __future__ import annotations
import hashlib

# ── Umbrales §4 [VERIFICAR] ──────────────────────────────────────────────────
B1_DIVERGENCIA_PP   = 0.10          # payout: |Δ| entre estimadores > 10 pp
# Suelo del payout = cap K1-Payout (85%) − tolerancia B1 (10 pp) = 75%. Techo 110% (Pólaris D-006).
B2_PAYOUT_LO        = 0.85 - B1_DIVERGENCIA_PP   # = 0.75
B2_PAYOUT_HI        = 1.10
B2_EVEBITDA_LO      = 20.0          # cerca del KO 22×
B2_EVEBITDA_HI      = 24.0
B2_FREEFLOAT_LO     = 0.18          # cerca del veto 20%
B2_FREEFLOAT_HI     = 0.22
B3_SALTO_YOY        = 0.40          # salto interanual ordinario > 40% sin extraordinario
#   NOTA [VERIFICAR]: el sub-señal de salto se soporta aquí, pero el motor NO debe alimentar
#   'salto_yoy_ordinario' con un cálculo ingenuo por año natural: la estructura interino+
#   complementario y el último año incompleto de yfinance generan falsos positivos (fatiga de
#   alertas). Diferido hasta reutilizar la lógica de tendencia robusta del motor
#   (_sc_cagr_dividendo_ventana / _sc_anos_reduccion_div). Los cortes ya los caza el veto K2;
#   los extraordinarios, B3-extraordinario. Hasta entonces, motor pasa salto_yoy_ordinario=None.
SOFT_OBSOLESCENCIA  = 0.15          # estimador vs vigente: divergencia que sugiere curado añejo


def _pct(x) -> str:
    return "n/d" if x is None else f"{float(x)*100:.1f}%"


def _huella(*valores) -> str:
    """Fingerprint estable de los valores en conflicto (redondeo para evitar ruido float).
    Un acuse ancla a esta huella: si los valores cambian, la huella cambia y la bandera vuelve."""
    partes = []
    for v in valores:
        if v is None:
            partes.append("na")
        elif isinstance(v, (int, float)):
            partes.append(f"{round(float(v), 4)}")
        else:
            partes.append(str(v))
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:12]


# ── Estimadores del payout (al vuelo) ────────────────────────────────────────
def estimadores_payout(payout_campo, dividendo_ord_ejercicio, eps) -> dict:
    """Estimadores en paralelo del payout (§2). Ninguno es 'oficial' hasta resolver divergencia.
      E1 = campo del proveedor (payoutRatio).
      E2 = dividendo ordinario del ejercicio / BPA (EPS) del proveedor.
      E3 = parser CNMV (diferido — None por ahora).
    E2 solo se calcula con EPS > 0 (con EPS<=0 el payout no es interpretable: lo gobierna K1-BPA)."""
    e1 = float(payout_campo) if payout_campo is not None else None
    e2 = None
    if dividendo_ord_ejercicio is not None and eps is not None and float(eps) > 0:
        e2 = float(dividendo_ord_ejercicio) / float(eps)
    return {"E1_campo": e1, "E2_dpa_bpa": e2, "E3_cnmv": None}


# ── Motor de las tres banderas + suave ───────────────────────────────────────
def evaluar_banderas(ctx: dict) -> dict:
    """Evalúa B1/B2/B3 (+ suave) sobre el contexto de un ticker. Puro.

    ctx (todo opcional; el motor rellena lo que tiene):
      payout_campo        E1 (info['payoutRatio'])
      dividendo_ord_ejercicio  numerador de E2 (renta ordinaria del último ejercicio cerrado)
      eps                 info['trailingEps'] (denominador de E2)
      yield_ordinario     yield ordinario del último año natural cerrado (Lente A)
      racha_anios         años de racha continua de dividendo
      ev_ebitda           info['enterpriseToEbitda']
      free_float          fracción de free float (0-1)
      tiene_extraordinario  bool (Lente A)
      salto_yoy_ordinario  mayor salto interanual del dividendo ordinario en la ventana (fracción)
      base_suspendida     bool (CAGR n/d por base ≈0 / reanudación)
      fuente_rancia       bool (sin dato / dato caducado)
      sector_financiero   bool (payout no aplica: banca/seguros) -> B1/B2-payout se inhiben
      payout_vigente      payout curado 'vigente' si existe (para la bandera suave)

    Devuelve {estimadores, banderas:[...], capa_veredicto:bool}. Cada bandera:
      {codigo, tipo, motivo, valores, huella}. tipo: 'capa' (B1/B2/B3) | 'suave' (no capa)."""
    est = estimadores_payout(ctx.get("payout_campo"),
                             ctx.get("dividendo_ord_ejercicio"), ctx.get("eps"))
    e1, e2 = est["E1_campo"], est["E2_dpa_bpa"]
    # payout N/A estructural: banca/seguros Y SOCIMIs (spec §8). Inhibe B1, B2-payout y B2-EV/EBITDA
    # (métricas no válidas para ese modelo de negocio). yield/historial/free-float SÍ aplican.
    pna = bool(ctx.get("payout_na") if ctx.get("payout_na") is not None
               else ctx.get("sector_financiero"))
    banderas = []

    # ── B1 — Divergencia entre estimadores automáticos (payout) ──────────────
    # (Vía por la que se caza Logista: campo ~72% vs cálculo/parser ~99%.)
    if not pna and e1 is not None and e2 is not None and abs(e1 - e2) > B1_DIVERGENCIA_PP:
        banderas.append({
            "codigo": "B1", "tipo": "capa",
            "motivo": f"Divergencia de payout entre estimadores: campo {_pct(e1)} vs DPA/BPA {_pct(e2)} "
                      f"(Δ {abs(e1-e2)*100:.1f} pp > {B1_DIVERGENCIA_PP*100:.0f}). Revisar cuál es el bueno.",
            "valores": {"E1_campo": e1, "E2_dpa_bpa": e2},
            "huella": _huella("B1", e1, e2),
        })

    # ── B2 — Zona gris cerca de un umbral, SOLO métricas con ruido real (Pólaris D-006):
    # payout, EV/EBITDA y free float. yield (poco ruidoso) e historial (recuento, no ruido)
    # NO van en B2 — el historial pasa a B3 como "hueco de serie".
    motivos_b2, vals_b2 = [], {}
    payout_ref = e2 if e2 is not None else e1     # el más informativo disponible
    if not pna and payout_ref is not None and B2_PAYOUT_LO <= payout_ref <= B2_PAYOUT_HI:
        motivos_b2.append(f"payout {_pct(payout_ref)} en zona gris ({int(B2_PAYOUT_LO*100)}–{int(B2_PAYOUT_HI*100)}%)")
        vals_b2["payout"] = round(payout_ref, 4)
    _ev = ctx.get("ev_ebitda")
    if not pna and _ev is not None and B2_EVEBITDA_LO <= float(_ev) <= B2_EVEBITDA_HI:
        motivos_b2.append(f"EV/EBITDA {float(_ev):.1f}× (cerca del KO 22×)")
        vals_b2["ev_ebitda"] = round(float(_ev), 2)
    _ff = ctx.get("free_float")
    if _ff is not None and B2_FREEFLOAT_LO <= float(_ff) <= B2_FREEFLOAT_HI:
        motivos_b2.append(f"free float {_pct(_ff)} (cerca del veto 20%)")
        vals_b2["free_float"] = round(float(_ff), 4)
    if motivos_b2:
        banderas.append({
            "codigo": "B2", "tipo": "capa",
            "motivo": "Zona gris cerca de umbral: " + "; ".join(motivos_b2) + ".",
            "valores": vals_b2,
            "huella": _huella("B2", *[vals_b2[k] for k in sorted(vals_b2)]),
        })

    # ── B3 — Anomalía / firma de fallo ───────────────────────────────────────
    # (Vía por la que se caza un payout erróneamente BAJO, como el 72% de Logista, que B2 no vería.)
    motivos_b3, vals_b3 = [], {}
    if ctx.get("tiene_extraordinario"):
        motivos_b3.append("extraordinario detectado en la serie")
        vals_b3["extra"] = True
    _sy = ctx.get("salto_yoy_ordinario")
    if _sy is not None and abs(float(_sy)) > B3_SALTO_YOY:
        motivos_b3.append(f"salto interanual del dividendo ordinario {float(_sy)*100:+.0f}% (> {int(B3_SALTO_YOY*100)}%)")
        vals_b3["salto_yoy"] = round(float(_sy), 3)
    if ctx.get("base_suspendida"):
        motivos_b3.append("base de dividendo suspendida/reanudada (≈0)")
        vals_b3["base_susp"] = True
    _hs = ctx.get("hueco_serie")
    if _hs:
        _anos_hs = ", ".join(str(a) for a in _hs) if isinstance(_hs, (list, tuple)) else ""
        motivos_b3.append(f"hueco en la serie de dividendo ({_anos_hs})" if _anos_hs
                          else "hueco en la serie de dividendo (interrupción/año sin pago)")
        vals_b3["hueco_serie"] = list(_hs) if isinstance(_hs, (list, tuple)) else True
    if ctx.get("fuente_rancia"):
        motivos_b3.append("fuente nula o rancia")
        vals_b3["fuente_rancia"] = True
    if motivos_b3:
        banderas.append({
            "codigo": "B3", "tipo": "capa",
            "motivo": "Anomalía: " + "; ".join(motivos_b3) + ".",
            "valores": vals_b3,
            "huella": _huella("B3", *[f"{k}={vals_b3[k]}" for k in sorted(vals_b3)]),
        })

    # ── Bandera SUAVE — obsolescencia del dato curado (no capa el veredicto) ──
    _pv = ctx.get("payout_vigente")
    if _pv is not None and e2 is not None and abs(e2 - float(_pv)) > SOFT_OBSOLESCENCIA:
        banderas.append({
            "codigo": "B-soft", "tipo": "suave",
            "motivo": f"El estimador ({_pct(e2)}) se ha separado del payout curado vigente ({_pct(_pv)}): "
                      f"el dato curado puede estar obsoleto (¿reformulación?). No cambia el veredicto; "
                      f"conviene refrescar la curación.",
            "valores": {"E2_dpa_bpa": e2, "payout_vigente": float(_pv)},
            "huella": _huella("Bsoft", e2, float(_pv)),
        })

    capa = any(b["tipo"] == "capa" for b in banderas)
    return {"estimadores": est, "banderas": banderas, "capa_veredicto": capa}
