# -*- coding: utf-8 -*-
"""
lente.py — Lente A (renta) y Lente B (payout) del golden record de dividendos (spec DosLentes v1).

Principio: los importes se obtienen SUMANDO eventos observados (yfinance), NUNCA de un
campo-resumen del proveedor. La clasificación (ordinario/extraordinario/scrip) y el BPA
auditado vienen del golden record CURADO en Neon (vía curacion.leer_*). Sin BPA curado
-> payout N/A "evaluación incompleta" (nunca un número supuesto).

  · Lente A (renta): agrupa por AÑO NATURAL; yield del último año cerrado; CAGR sobre
    dividendo ORDINARIO (excluye extraordinarios). Alimenta K3 (yield) y K2 (CAGR).
  · Lente B (payout): dividendo ORDINARIO CON CARGO al ejercicio ÷ BPA auditado del
    ejercicio (NO la caja del año natural — §9.2). Alimenta K1-Payout. Degrada a N/A.

Módulo de cálculo: recibe la conexión del caller; sin secretos.
"""
from __future__ import annotations
import datetime

try:
    import curacion
except Exception:                        # noqa: BLE001 — testeable sin curacion
    curacion = None

TIPOS_RENTA = ("ordinario", "extraordinario", "scrip")


# ── Fuente de eventos (yfinance) y clasificación curada (Neon) ────────────────
def eventos_yfinance(ticker: str) -> list[tuple[datetime.date, float]]:
    """[(ex_date, importe)] de yfinance. Los .MC cotizan en EUR; para valores en otra
    divisa habría que normalizar a EUR por pay_date (§9.4) — fuera del alcance IBEX-35."""
    try:
        import yfinance as yf
        s = yf.Ticker(ticker).dividends
        if s is None or len(s) == 0:
            return []
        return [(idx.date() if hasattr(idx, "date") else idx, float(v)) for idx, v in s.items()]
    except Exception:                    # noqa: BLE001
        return []


def clasificacion_neon(conn, ticker: str) -> dict[str, str]:
    """{ex_date_iso: tipo} desde dividendo_clasificado VIGENTE (curado). Los eventos que
    no estén curados se tratan como 'ordinario' por defecto (regla de la spec)."""
    out: dict[str, str] = {}
    if conn is None or curacion is None:
        return out
    try:
        for d in curacion.leer_dividendos(conn, ticker):
            exd = d.get("ex_date")
            if exd is not None:
                k = exd.isoformat() if hasattr(exd, "isoformat") else str(exd)[:10]
                out[k] = d.get("tipo") or "ordinario"
    except Exception:                    # noqa: BLE001
        pass
    return out


# ── Lente A — renta por año natural ──────────────────────────────────────────
def renta_por_ano(eventos, clasificacion=None) -> dict[int, dict]:
    clasificacion = clasificacion or {}
    por: dict[int, dict] = {}
    for f, imp in eventos:
        if imp is None or imp <= 0:
            continue
        k = f.isoformat() if hasattr(f, "isoformat") else str(f)[:10]
        tipo = clasificacion.get(k, "ordinario")
        if tipo not in TIPOS_RENTA:
            tipo = "ordinario"
        d = por.setdefault(f.year, {"total": 0.0, "ordinario": 0.0, "extraordinario": 0.0, "scrip": 0.0})
        d["total"] += imp
        d[tipo] += imp
    return por


def yield_actual(por_ano: dict, precio, base: str = "total") -> float | None:
    """Renta del último año natural CERRADO ÷ precio. `base`='total' (bloque Renta) u
    'ordinario' (el que evalúa K3 — D-002: un extraordinario no recurrente no debe hacer
    pasar el filtro de rentas). Si no hay año cerrado, usa el más reciente."""
    if not por_ano or not precio:
        return None
    if base not in ("total", "ordinario"):
        base = "total"
    anos = sorted(por_ano)
    hoy = datetime.date.today().year
    cerrados = [a for a in anos if a < hoy]
    ref = cerrados[-1] if cerrados else anos[-1]
    try:
        return por_ano[ref][base] / float(precio)
    except Exception:                    # noqa: BLE001
        return None


def cagr_ordinario(por_ano: dict, ventana: int = 5, eps_dpa: float = 0.01) -> float | None:
    """CAGR del dividendo ORDINARIO por año natural — para el DISPLAY del bloque 'Renta'.

    NO es el valor del gate K2 (K2 usa la función robusta del motor,
    `_sc_cagr_dividendo_ventana`, sobre pay-date). Pero aplica las MISMAS guardas, para que
    el display NUNCA muestre un crecimiento que contradiga el veto K2 (decisión Polaris):
      · excluye el año en curso incompleto,
      · se limita a la racha CONTINUA más reciente (sin cross-gap),
      · usa ventana+1 puntos (= `ventana` intervalos),
      · guarda de base casi-cero (≤ eps_dpa €): suspensión/reanudación -> `n/d` (None).
    Verificado: CLNX -22.5% · UNI n/d (coincide con K2). Sin la guarda, el cálculo ingenuo
    daría CLNX +155% / UNI +44% (base de reanudación), contradiciendo el veto.
    """
    anual = [(a, por_ano[a]["ordinario"]) for a in sorted(por_ano) if por_ano[a]["ordinario"] > 0]
    hoy = datetime.date.today()
    if hoy.month < 12:                                  # excluir año en curso incompleto
        anual = [(a, v) for a, v in anual if a < hoy.year]
    if len(anual) < 2:
        return None
    years = [a for a, _ in anual]
    streak = 1
    for i in range(len(years) - 1, 0, -1):              # racha continua desde el más reciente
        if years[i] - years[i - 1] == 1:
            streak += 1
        else:
            break
    cont = anual[-streak:]
    ult = cont[-min(int(ventana) + 1, len(cont)):]      # ventana+1 puntos = `ventana` intervalos
    if len(ult) < 2:
        return None
    vals = [v for _, v in ult]
    if min(vals) <= eps_dpa:                            # #G — base suspendida/reanudación -> n/d
        return None
    ini, fin, n = vals[0], vals[-1], len(ult) - 1
    if ini <= 0 or n <= 0:
        return None
    return (fin / ini) ** (1 / n) - 1


def lente_a(conn, ticker: str, precio) -> dict:
    """Lente A completa para un ticker (renta por año, yield actual, CAGR ordinario, badge extra)."""
    por = renta_por_ano(eventos_yfinance(ticker), clasificacion_neon(conn, ticker))
    return {
        "por_ano": por,
        "yield_total": yield_actual(por, precio, "total"),          # bloque "Renta"
        "yield_ordinario": yield_actual(por, precio, "ordinario"),  # el que evalúa K3 (D-002)
        "cagr_ordinario": cagr_ordinario(por),                      # el que evalúa K2 (D-003)
        "tiene_extraordinario": any(por[a]["extraordinario"] > 0 or por[a]["scrip"] > 0 for a in por),
    }


# ── Lente B — payout / cobertura por ejercicio contable ──────────────────────
def payout_ordinario(conn, ticker: str, ejercicio: str) -> dict:
    """Payout ordinario = dividendo ORDINARIO con cargo al `ejercicio` ÷ BPA auditado (Neon).
    estado:
      'ok'              -> payout calculado (con su confianza, heredada del BPA).
      'no_interpretable'-> BPA<=0 (p.ej. TEF): payout no interpretable (KO), no error.
      'n/a'             -> sin BPA vigente curado o sin dividendos ordinarios con cargo
                           -> "evaluación incompleta" (NUNCA un número supuesto).
    """
    if conn is None or curacion is None:
        return {"payout": None, "estado": "n/a", "motivo": "sin acceso al golden record", "confianza": "baja"}
    bpas = [b for b in curacion.leer_bpa(conn, ticker) if b.get("ejercicio") == ejercicio]
    if not bpas or bpas[0].get("bpa_auditado") is None:
        return {"payout": None, "estado": "n/a", "motivo": "sin BPA auditado vigente", "confianza": "baja"}
    b = bpas[0]
    bpa = float(b["bpa_auditado"])
    if bpa <= 0:
        return {"payout": None, "estado": "no_interpretable", "bpa": bpa,
                "motivo": "BPA<=0 (payout no interpretable)", "confianza": b.get("confianza", "media")}
    div_ord = sum(float(d["importe_eur"]) for d in curacion.leer_dividendos(conn, ticker)
                  if d.get("tipo") == "ordinario" and d.get("con_cargo_a_ejercicio") == ejercicio
                  and d.get("importe_eur") is not None)
    if div_ord <= 0:
        return {"payout": None, "estado": "n/a", "bpa": bpa,
                "motivo": "sin dividendos ordinarios con cargo curados", "confianza": "baja"}
    return {"payout": div_ord / bpa, "bpa": bpa, "div_ordinario": div_ord, "estado": "ok",
            "confianza": b.get("confianza", "media"), "fuente": b.get("fuente")}


def payout_total(conn, ticker: str, ejercicio: str) -> dict:
    """Payout TOTAL = (ordinario + extraordinario) con cargo ÷ BPA. Solo CONTEXTO (no gobierna)."""
    base = payout_ordinario(conn, ticker, ejercicio)
    if base.get("estado") != "ok":
        return base
    div_tot = sum(float(d["importe_eur"]) for d in curacion.leer_dividendos(conn, ticker)
                  if d.get("tipo") in ("ordinario", "extraordinario")
                  and d.get("con_cargo_a_ejercicio") == ejercicio and d.get("importe_eur") is not None)
    return {**base, "payout_total": div_tot / base["bpa"], "div_total": div_tot}
