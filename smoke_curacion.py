# -*- coding: utf-8 -*-
"""
smoke_curacion.py — Prueba de humo del versionado del golden record contra Neon REAL.
Usa un ticker ficticio TEST.MC y LIMPIA todo al final (no ensucia datos reales).

Verifica: alta v1 -> edición v2 (retira v1 con valid_to, solo 1 vigente) ->
una-sola-vigente por (ticker,ejercicio) -> rechazo de fuente yfinance ->
dividendos: mismo ex_date con distinto tipo coexisten; mismo (ticker,ex_date,tipo) versiona ->
importe<=0 rechazado.

DSN: env DATABASE_URL o .streamlit/secrets.toml (sin hardcodear secretos).
Uso (desde la carpeta del repo):  python smoke_curacion.py
"""
import os, sys
import verificacion

TK = "TEST.MC"; EJ = "FY2025"
_ok = [0]; _ko = [0]

def check(cond, msg):
    print(("  OK   " if cond else "  FALLO ") + msg)
    if cond: _ok[0] += 1
    else: _ko[0] += 1

def dsn():
    if os.environ.get("DATABASE_URL"): return os.environ["DATABASE_URL"]
    for p in (".streamlit/secrets.toml", os.path.expanduser("~/.streamlit/secrets.toml")):
        if os.path.exists(p):
            try: import tomllib as T
            except Exception: import tomli as T
            with open(p, "rb") as f: d = T.load(f)
            if d.get("DATABASE_URL"): return d["DATABASE_URL"]
    sys.exit("No hay DATABASE_URL (env ni .streamlit/secrets.toml).")

def limpiar(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM dividendo_clasificado WHERE ticker=%s", [TK])
    cur.execute("DELETE FROM bpa_ejercicio WHERE ticker=%s", [TK])
    cur.execute("DELETE FROM empresa WHERE ticker=%s", [TK])
    conn.commit()

def main():
    import psycopg2
    conn = psycopg2.connect(dsn())
    try:
        limpiar(conn)
        # 0) Ficha de empresa (FK)
        verificacion.guardar_empresa(conn, {"ticker": TK, "nombre": "Test SA", "cierre_ejercicio": "09-30",
                                        "clase_exclusion": "estandar"}, "smoke")
        proc = {"fuente": "Informe anual (CNMV)", "fecha_verificacion": "2026-07-24", "verificado_por": "smoke"}

        # 0.b) Cálculo puro de derivados (rediseño BPA 2026-07-29): 211 M€ / 100M acc -> BPA 2.11
        _c = verificacion.calcular_bpa_payout(211.0, 100_000_000, 1.00)
        check(abs(_c["bpa"] - 2.11) < 1e-6, f"calc BPA derivado = 2.11 (got {_c['bpa']})")
        check(abs(_c["payout"] - (100.0 / 211.0)) < 1e-6, "calc payout = div_total/recurrente")
        check(verificacion.calcular_bpa_payout(-50.0, 100_000_000, 1.00)["payout"] is None,
              "beneficio<0 -> payout no interpretable (None)")
        # cifras crudas de apoyo para las altas de BPA (base + recurrente M€ + nº acciones -> BPA derivado)
        def _bpa(rec_meur):  # acciones fijas 100M -> BPA = rec_meur/100
            return {"base_beneficio": "consolidado", "beneficio_recurrente_meur": rec_meur,
                    "numero_acciones": 100_000_000}

        # 1) BPA v1 (recurrente 211 M€ -> BPA derivado 2.11)
        v1 = verificacion.publicar_bpa(conn, {"ticker": TK, "ejercicio": EJ, **_bpa(211.0), **proc}, "smoke")
        vig = verificacion.leer_bpa(conn, TK)
        check(v1 == 1, f"alta BPA -> version 1 (got {v1})")
        check(len(vig) == 1 and abs(float(vig[0]["bpa_auditado"]) - 2.11) < 1e-6, "1 sola vigente, BPA derivado=2.11")

        # 2) BPA v2 (edición: recurrente 230 M€ -> BPA 2.30) -> versiona
        v2 = verificacion.publicar_bpa(conn, {"ticker": TK, "ejercicio": EJ, **_bpa(230.0), **proc}, "smoke")
        vig = verificacion.leer_bpa(conn, TK)
        check(v2 == 2, f"edición BPA -> version 2 (got {v2})")
        check(len(vig) == 1 and abs(float(vig[0]["bpa_auditado"]) - 2.30) < 1e-6, "sigue 1 sola vigente, BPA=2.30 (v2)")
        todas = verificacion.leer_bpa(conn, TK, solo_vigente=False)
        retiradas = [r for r in todas if r["estado"] == "retirado"]
        check(len(retiradas) == 1 and retiradas[0]["valid_to"] is not None, "v1 queda 'retirado' con valid_to")
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM bpa_ejercicio WHERE ticker=%s AND ejercicio=%s AND estado='vigente'", [TK, EJ])
        check(cur.fetchone()[0] == 1, "índice único parcial: exactamente 1 vigente por (ticker,ejercicio)")

        # 3) Rechazo de fuente prohibida (B10)
        try:
            verificacion.publicar_bpa(conn, {"ticker": TK, "ejercicio": "FY2024", **_bpa(100.0),
                                         "fuente": "yfinance", "fecha_verificacion": "2026-07-24", "verificado_por": "smoke"}, "smoke")
            check(False, "fuente 'yfinance' debía rechazarse")
        except ValueError as ex:
            check("B10" in str(ex), "fuente 'yfinance' rechazada (B10)")

        # 4) Dividendos: mismo ex_date distinto tipo coexisten; mismo (tk,ex,tipo) versiona
        verificacion.publicar_dividendo(conn, {"ticker": TK, "ex_date": "2025-06-10", "importe_eur": 1.20,
                                           "tipo": "ordinario", "con_cargo_a_ejercicio": EJ, **proc}, "smoke")
        verificacion.publicar_dividendo(conn, {"ticker": TK, "ex_date": "2025-06-10", "importe_eur": 0.50,
                                           "tipo": "extraordinario", "con_cargo_a_ejercicio": EJ, **proc}, "smoke")
        dv = verificacion.leer_dividendos(conn, TK)
        check(len(dv) == 2, f"ordinario + extraordinario mismo ex_date coexisten (got {len(dv)})")
        vd = verificacion.publicar_dividendo(conn, {"ticker": TK, "ex_date": "2025-06-10", "importe_eur": 1.30,
                                                "tipo": "ordinario", "con_cargo_a_ejercicio": EJ, **proc}, "smoke")
        dv = verificacion.leer_dividendos(conn, TK)
        ord_vig = [r for r in dv if r["tipo"] == "ordinario"]
        check(vd == 2 and len(dv) == 2 and float(ord_vig[0]["importe_eur"]) == 1.30,
              "reedición del ordinario -> v2, sigue 1 vigente por tipo (importe 1.30)")

        # 5) importe <= 0 rechazado (D2)
        try:
            verificacion.publicar_dividendo(conn, {"ticker": TK, "ex_date": "2025-09-01", "importe_eur": 0,
                                               "tipo": "ordinario", **proc}, "smoke")
            check(False, "importe_eur=0 debía rechazarse")
        except ValueError as ex:
            check("D2" in str(ex), "importe_eur<=0 rechazado (D2)")
    finally:
        limpiar(conn); conn.close()

    print(f"\nRESULTADO: {_ok[0]} OK, {_ko[0]} FALLOS")
    sys.exit(0 if _ko[0] == 0 else 1)

if __name__ == "__main__":
    main()
