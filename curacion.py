# -*- coding: utf-8 -*-
"""
curacion.py — Capa de datos + validación del golden record de dividendos (spec DosLentes v1).

Reglas de validación Pólaris v1. Modo de arranque: UNA persona (directo), con
versionado y auditoría íntegros. El motor solo lee estado='vigente'. Editar un
vigente NO sobrescribe: retira el anterior (estado='retirado', valid_to) e inserta
una versión nueva vigente (reproducibilidad, Anexo A.5).

Sin secretos: recibe la conexión psycopg2 del caller (el panel de admin la obtiene
de get_db_connection()).
"""
from __future__ import annotations
import re, datetime

# ── Dominios cerrados ────────────────────────────────────────────────────────
CIERRES = {"31-dic": "12-31", "31-ene": "01-31", "30-sep": "09-30", "31-mar": "03-31", "30-jun": "06-30"}
CLASES = {"estandar", "banca_seguros", "reit_socimi"}
TIPOS = {"ordinario", "extraordinario", "scrip"}
CONF = {"alta", "media", "baja"}
_FUENTE_PROHIBIDA = re.compile(r"(yfinance|estimaci)", re.I)      # B7
_RE_TICKER = re.compile(r"^[A-Z0-9]{1,6}\.[A-Z]{2}$")            # E1 (XXX.MC)
_RE_EJERCICIO = re.compile(r"^FY\d{4}$")                          # B3 (FY2025)

def _s(v): return "" if v is None else str(v).strip()
def _hoy(): return datetime.date.today()


# ── Validaciones — devuelven (errores_BLOQUEA, avisos_AVISA) ─────────────────
def validar_empresa(d: dict) -> tuple[list[str], list[str]]:
    e, a = [], []
    if not _RE_TICKER.match(_s(d.get("ticker"))): e.append("E1: ticker debe tener formato XXX.MC")
    if not _s(d.get("nombre")): e.append("E2: nombre requerido")
    cie = _s(d.get("cierre_ejercicio")) or "12-31"
    if cie not in CIERRES.values(): e.append(f"E3: cierre '{cie}' fuera del dominio cerrado")
    cl = _s(d.get("clase_exclusion")) or "estandar"
    if cl not in CLASES: e.append(f"E5: clase_exclusion '{cl}' inválida")
    # E6 (coherencia clase↔sector) es AVISA — la sugiere el formulario según el sector.
    return e, a

def _proc_bloquea(d, e):   # T1 + T5 — procedencia obligatoria para PUBLICAR una fila de hecho
    if not _s(d.get("fuente")): e.append("T1: 'fuente' requerida")
    if not _s(d.get("fecha_verificacion")): e.append("T1: 'fecha_verificacion' requerida")
    if not _s(d.get("verificado_por")): e.append("T1: 'verificado_por' requerido")
    fv = _s(d.get("fecha_verificacion"))
    if fv:
        try:
            if datetime.date.fromisoformat(fv[:10]) > _hoy(): e.append("T5: fecha_verificacion no puede ser futura")
        except ValueError: e.append("T5: fecha_verificacion no es fecha ISO (AAAA-MM-DD)")

def validar_bpa(d: dict) -> tuple[list[str], list[str]]:
    e, a = [], []
    if not _RE_TICKER.match(_s(d.get("ticker"))): e.append("B1: ticker inválido")
    if not _RE_EJERCICIO.match(_s(d.get("ejercicio"))): e.append("B3: ejercicio con formato FYaaaa (p.ej. FY2025)")
    bpa = d.get("bpa_auditado")
    if bpa is None or _s(bpa) == "":
        e.append("B5: bpa_auditado requerido para publicar (negativo permitido)")
    else:
        try: float(bpa)                                     # B5: negativo permitido; no se bloquea por signo
        except (TypeError, ValueError): e.append("B5: bpa_auditado no numérico")
    fte = _s(d.get("fuente"))
    if fte and _FUENTE_PROHIBIDA.search(fte): e.append("B7: la fuente del BPA no puede ser yfinance/estimación")
    _proc_bloquea(d, e)
    bn = d.get("beneficio_neto")
    if bn not in (None, "") and bpa not in (None, ""):      # B6 AVISA
        try:
            if (float(bn) < 0) != (float(bpa) < 0):
                a.append("B6: el signo de beneficio_neto no coincide con el de bpa_auditado")
        except (TypeError, ValueError): pass
    return e, a

def validar_dividendo(d: dict) -> tuple[list[str], list[str]]:
    e, a = [], []
    if not _RE_TICKER.match(_s(d.get("ticker"))): e.append("D1: ticker inválido")
    imp = d.get("importe_eur")
    try:
        if imp is None or float(imp) <= 0: e.append("D2: importe_eur debe ser > 0")
    except (TypeError, ValueError): e.append("D2: importe_eur no numérico")
    if (_s(d.get("tipo")) or "ordinario") not in TIPOS: e.append("D3: tipo inválido")
    exd, pyd = _s(d.get("ex_date")), _s(d.get("pay_date"))
    exdd = None
    if exd:
        try: exdd = datetime.date.fromisoformat(exd[:10])
        except ValueError: e.append("D4: ex_date no es fecha ISO")
    else:
        e.append("D4: ex_date requerida")
    if pyd:
        try:
            if exdd and datetime.date.fromisoformat(pyd[:10]) < exdd: e.append("D4: ex_date debe ser ≤ pay_date")
        except ValueError: e.append("D4: pay_date no es fecha ISO")
    else:
        a.append("D5: sin pay_date -> se usa ex_date como referencia (pay_date_aprox=true)")
    if _s(d.get("tipo")) == "scrip": a.append("D7: en scrip, registra solo la parte en efectivo como importe_eur")
    _proc_bloquea(d, e)
    return e, a


# ── Reconciliación R1/R2 (pura) ──────────────────────────────────────────────
def reconciliar_payout(payout_calc, payout_yf, umbral: float = 0.10):
    """(revision_requerida, confianza, delta_pp). |Δ| > umbral (pp) -> revisión + confianza baja."""
    if payout_calc is None or payout_yf is None:
        return False, "media", None
    delta = abs(float(payout_calc) - float(payout_yf))
    if delta > umbral:
        return True, "baja", round(delta * 100, 1)
    return False, "alta", round(delta * 100, 1)


# ── Publicación con versionado (modo una-persona: directo a vigente) ─────────
def _siguiente_version(cur, tabla, cond_sql, params):
    cur.execute(f"SELECT COALESCE(MAX(version),0) FROM {tabla} WHERE {cond_sql}", params)
    return (cur.fetchone()[0] or 0) + 1

def guardar_empresa(conn, d, usuario):
    e, _a = validar_empresa(d)
    if e: raise ValueError("; ".join(e))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO empresa (ticker,nombre,cierre_ejercicio,cierre_confirmado,sector,clase_exclusion,notas,creado_por) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (ticker) DO UPDATE SET "
        "nombre=EXCLUDED.nombre, cierre_ejercicio=EXCLUDED.cierre_ejercicio, "
        "cierre_confirmado=EXCLUDED.cierre_confirmado, sector=EXCLUDED.sector, "
        "clase_exclusion=EXCLUDED.clase_exclusion, notas=EXCLUDED.notas",
        [d["ticker"], d.get("nombre"), d.get("cierre_ejercicio") or "12-31",
         bool(d.get("cierre_confirmado")), d.get("sector"), d.get("clase_exclusion") or "estandar",
         d.get("notas"), usuario])
    conn.commit()

def publicar_bpa(conn, d, usuario, revision_requerida=False, confianza="media"):
    """Retira la versión vigente anterior (si hay) e inserta una nueva versión vigente."""
    e, _a = validar_bpa(d)
    if e: raise ValueError("; ".join(e))
    cur = conn.cursor()
    ver = _siguiente_version(cur, "bpa_ejercicio", "ticker=%s AND ejercicio=%s",
                             [d["ticker"], d["ejercicio"]])
    cur.execute("UPDATE bpa_ejercicio SET estado='retirado', valid_to=now() "
                "WHERE ticker=%s AND ejercicio=%s AND estado='vigente'", [d["ticker"], d["ejercicio"]])
    cur.execute(
        "INSERT INTO bpa_ejercicio (ticker,ejercicio,periodo,bpa_auditado,beneficio_neto,fuente,url,"
        "fecha_verificacion,estado,version,valid_from,creado_por,revisado_por,revision_requerida,confianza) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'vigente',%s,now(),%s,%s,%s,%s)",
        [d["ticker"], d["ejercicio"], d.get("periodo"), d["bpa_auditado"], d.get("beneficio_neto"),
         d["fuente"], d.get("url"), d["fecha_verificacion"], ver, usuario, usuario,
         bool(revision_requerida), confianza])
    conn.commit()
    return ver

def publicar_dividendo(conn, d, usuario, revision_requerida=False, confianza="media"):
    """Igual que publicar_bpa, versionado sobre (ticker, ex_date, tipo)."""
    e, _a = validar_dividendo(d)
    if e: raise ValueError("; ".join(e))
    tipo = _s(d.get("tipo")) or "ordinario"
    pay_aprox = not _s(d.get("pay_date"))
    cur = conn.cursor()
    ver = _siguiente_version(cur, "dividendo_clasificado", "ticker=%s AND ex_date=%s AND tipo=%s",
                             [d["ticker"], d["ex_date"], tipo])
    cur.execute("UPDATE dividendo_clasificado SET estado='retirado', valid_to=now() "
                "WHERE ticker=%s AND ex_date=%s AND tipo=%s AND estado='vigente'",
                [d["ticker"], d["ex_date"], tipo])
    cur.execute(
        "INSERT INTO dividendo_clasificado (ticker,ex_date,pay_date,pay_date_aprox,importe_eur,tipo,"
        "con_cargo_a_ejercicio,fuente,url,fecha_verificacion,estado,version,valid_from,creado_por,"
        "revisado_por,revision_requerida,confianza) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'vigente',%s,now(),%s,%s,%s,%s)",
        [d["ticker"], d["ex_date"], d.get("pay_date"), pay_aprox, d["importe_eur"], tipo,
         d.get("con_cargo_a_ejercicio"), d["fuente"], d.get("url"), d["fecha_verificacion"], ver,
         usuario, usuario, bool(revision_requerida), confianza])
    conn.commit()
    return ver

def retirar(conn, tabla, id_fila, motivo, usuario):
    """P3: borrar = marcar 'retirado' con motivo/fecha (no elimina físicamente)."""
    if tabla not in ("bpa_ejercicio", "dividendo_clasificado"): raise ValueError("tabla no permitida")
    cur = conn.cursor()
    cur.execute(f"UPDATE {tabla} SET estado='retirado', valid_to=now(), motivo_retiro=%s, revisado_por=%s "
                f"WHERE id=%s AND estado='vigente'", [motivo, usuario, id_fila])
    conn.commit()


# ── Lecturas para el formulario ──────────────────────────────────────────────
def _dicts(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def leer_empresas(conn):
    cur = conn.cursor(); cur.execute("SELECT * FROM empresa ORDER BY ticker"); return _dicts(cur)

def leer_bpa(conn, ticker=None, solo_vigente=True):
    cur = conn.cursor()
    q = "SELECT * FROM bpa_ejercicio WHERE 1=1"; p = []
    if solo_vigente: q += " AND estado='vigente'"
    if ticker: q += " AND ticker=%s"; p.append(ticker)
    q += " ORDER BY ticker, ejercicio"
    cur.execute(q, p); return _dicts(cur)

def leer_dividendos(conn, ticker=None, solo_vigente=True):
    cur = conn.cursor()
    q = "SELECT * FROM dividendo_clasificado WHERE 1=1"; p = []
    if solo_vigente: q += " AND estado='vigente'"
    if ticker: q += " AND ticker=%s"; p.append(ticker)
    q += " ORDER BY ticker, ex_date"
    cur.execute(q, p); return _dicts(cur)
