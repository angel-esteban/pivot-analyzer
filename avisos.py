# -*- coding: utf-8 -*-
"""
avisos.py — Persistencia del motor de avisos v2 (Spec v2 · D-006).

  · aviso_log   : LOG DE AUDITORÍA append-only, una fila por (run, ticker). Deja rastro de
                  los estimadores, banderas y veredicto para ver la deriva entre runs.
  · aviso_acuse : ACUSE "revisado y aceptado" anclado a la HUELLA de los valores en conflicto.
                  Silencia una bandera mientras esos valores no cambien.

Capa fina sobre las tablas creadas por migracion_avisos_v2_neon.sql. Recibe la conexión del
caller (no gestiona el pool). Todo defensivo: si las tablas no existen, el caller degrada a
"sin acuse / sin log" sin romper el screening.
"""
from __future__ import annotations
import json


def acuses_activos(conn, ticker: str | None = None) -> dict:
    """dict {(ticker, bandera, huella): tipo} de acuses vigentes. tipo derivado de la nota:
      · 'confirmado' → el dato es correcto: LEVANTA el cap (el veredicto puede alcanzar Cumple).
      · 'explicable' → aviso legítimo pero asumido: MANTIENE el cap, solo silencia (§8, regla dura).
      · 'otro'       → acuse antiguo/sin nota clara: por seguridad NO levanta el cap.
    (Sigue soportando `key in acuses` porque son las claves del dict.)"""
    cur = conn.cursor()
    if ticker:
        cur.execute("SELECT ticker, bandera, huella, COALESCE(nota,'') FROM aviso_acuse WHERE ticker=%s", [ticker])
    else:
        cur.execute("SELECT ticker, bandera, huella, COALESCE(nota,'') FROM aviso_acuse")
    out = {}
    for t, b, h, nota in cur.fetchall():
        _n = (nota or "").strip().lower()
        out[(t, b, h)] = ("confirmado" if _n.startswith("confirmado")
                          else "explicable" if _n.startswith("explicable") else "otro")
    return out


def guardar_acuse(conn, ticker: str, bandera: str, huella: str, usuario: str, nota: str | None = None):
    """Registra (o refresca) el acuse de una bandera concreta por su huella."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO aviso_acuse (ticker, bandera, huella, acuse_por, nota) "
        "VALUES (%s,%s,%s,%s,%s) "
        "ON CONFLICT (ticker, bandera, huella) DO UPDATE SET "
        "acuse_por=EXCLUDED.acuse_por, acuse_ts=now(), nota=EXCLUDED.nota",
        [ticker, bandera, huella, usuario, nota])
    conn.commit()


def borrar_acuse(conn, ticker: str, bandera: str, huella: str):
    """Retira un acuse (la bandera volverá a capar si sigue activa)."""
    cur = conn.cursor()
    cur.execute("DELETE FROM aviso_acuse WHERE ticker=%s AND bandera=%s AND huella=%s",
                [ticker, bandera, huella])
    conn.commit()


def registrar_log(conn, ticker: str, estimadores: dict, banderas: list, capa: bool,
                  veredicto: str, run_id: str | None = None):
    """Escribe una fila del log de auditoría (append-only) para este (run, ticker)."""
    cur = conn.cursor()
    _b = json.dumps([{"codigo": b.get("codigo"), "tipo": b.get("tipo"),
                      "huella": b.get("huella"), "motivo": b.get("motivo"),
                      "valores": b.get("valores"),          # cifras reales -> explicación llana en la bandeja
                      "acusada": bool(b.get("acusada"))} for b in banderas], ensure_ascii=False)
    cur.execute(
        "INSERT INTO aviso_log (run_id, ticker, payout_e1, payout_e2, payout_e3, banderas, capa, veredicto) "
        "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
        [run_id, ticker, estimadores.get("E1_campo"), estimadores.get("E2_dpa_bpa"),
         estimadores.get("E3_cnmv"), _b, bool(capa), veredicto])
    conn.commit()


def runs_marcado(conn, ticker: str, limite: int = 30) -> int:
    """nº de runs CONSECUTIVOS (desde el más reciente) en que el ticker salió capado."""
    cur = conn.cursor()
    cur.execute("SELECT capa FROM aviso_log WHERE ticker=%s ORDER BY run_ts DESC LIMIT %s",
                [ticker, limite])
    n = 0
    for (c,) in cur.fetchall():
        if c:
            n += 1
        else:
            break
    return n


def _dicts(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def leer_avisos_ultimo(conn, solo_capa: bool = True) -> list:
    """Estado actual de la bandeja: la ÚLTIMA fila del log por ticker. Si solo_capa, solo los
    que capan (marcados). Incluye 'runs_marcado' para la vista de deriva."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (ticker) ticker, run_ts, payout_e1, payout_e2, payout_e3,
               banderas, capa, veredicto
        FROM aviso_log ORDER BY ticker, run_ts DESC
    """)
    filas = _dicts(cur)
    if solo_capa:
        filas = [f for f in filas if f.get("capa")]
    for f in filas:
        f["runs_marcado"] = runs_marcado(conn, f["ticker"])
    return filas
