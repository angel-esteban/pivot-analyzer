#!/usr/bin/env python3
"""
cron_fundamentales.py — Refresco programado del nivel fundamental (y dividendos).

Script AUTÓNOMO: no necesita la app abierta. Se conecta a Neon, carga el universo
de tickers desde la tabla `indices_config`, ejecuta la ingesta fundamental
(extracción yfinance -> validación nivel 0 -> UPSERT) y registra en `ingesta_log`.

Cadencia recomendada: SEMANAL (los fundamentales solo cambian con resultados).

──────────────────────────────────────────────────────────────────────────────
USO
  export DATABASE_URL="postgresql://...neon..."     # NUNCA hardcodear (repo público)
  python cron_fundamentales.py                       # todo el universo
  python cron_fundamentales.py --indice "IBEX 35"    # solo un índice
  python cron_fundamentales.py --tickers IBE.MC ACX.MC

CÓMO PROGRAMARLO
  - GitHub Actions (encaja con tu repo): workflow `schedule: cron` semanal, con
    DATABASE_URL como *repository secret*. Es la opción más limpia para tu setup.
  - Windows: Programador de tareas -> acción que ejecuta este script semanalmente.
  - Linux/cron:  0 3 * * 1  cd /ruta/proyecto && python cron_fundamentales.py
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

import ingesta

_DIR = Path(__file__).resolve().parent
CRITERIA_PATH = str(_DIR / "criteria.json")


def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def obtener_database_url() -> str:
    """Lee la cadena de conexión: primero de entorno, luego de .streamlit/secrets.toml."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secrets = _DIR / ".streamlit" / "secrets.toml"
    if secrets.is_file():
        try:
            import tomllib  # Python 3.11+
            with open(secrets, "rb") as f:
                val = tomllib.load(f).get("DATABASE_URL")
            if val:
                return val
        except Exception as e:                       # noqa: BLE001
            _log(f"No se pudo leer secrets.toml: {e}")
    raise SystemExit("ERROR: define DATABASE_URL en el entorno antes de ejecutar.")


def cargar_universo(conn, indice: str | None = None) -> list[str]:
    """Tickers desde indices_config (columna jsonb `tickers` = {nombre: ticker})."""
    cur = conn.cursor()
    try:
        if indice:
            cur.execute("SELECT tickers FROM indices_config WHERE nombre = %s", [indice])
        else:
            cur.execute("SELECT tickers FROM indices_config")
        filas = cur.fetchall()
    finally:
        cur.close()

    tickers: list[str] = []
    for (mapa,) in filas:
        if isinstance(mapa, str):
            import json
            try:
                mapa = json.loads(mapa)
            except Exception:                        # noqa: BLE001
                mapa = {}
        if isinstance(mapa, dict):
            tickers.extend(str(t) for t in mapa.values() if t)
    # dedupe preservando orden
    vistos, unicos = set(), []
    for t in tickers:
        if t not in vistos:
            vistos.add(t)
            unicos.append(t)
    return unicos


def ejecutar(conn, tickers: list[str], fuente=None):
    """Lanza la ingesta fundamental. `fuente` inyectable para test."""
    return ingesta.ingerir_fundamental(
        tickers, conn, criteria_path=CRITERIA_PATH, fuente=fuente, disparado_por="cron")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refresco fundamental del screener.")
    ap.add_argument("--indice", help="Nombre exacto del índice (si se omite, todo el universo).")
    ap.add_argument("--tickers", nargs="+", help="Lista explícita de tickers (ignora --indice).")
    args = ap.parse_args(argv)

    import psycopg2
    url = obtener_database_url()
    _log("Conectando a Neon...")
    conn = psycopg2.connect(url)
    try:
        tickers = args.tickers or cargar_universo(conn, args.indice)
        if not tickers:
            _log("No hay tickers que procesar. Fin.")
            return 1
        _log(f"Universo: {len(tickers)} tickers. Iniciando ingesta fundamental...")
        r = ejecutar(conn, tickers)
        _log(f"Resultado -> ok={r.ok} fallidos={r.fallidos} (log #{r.log_id})")
        if r.detalle_fallidos:
            for tk, motivo in r.detalle_fallidos.items():
                _log(f"  FALLO {tk}: {motivo}")
        # Éxito si al menos la mitad se procesó bien
        return 0 if r.ok >= max(1, r.procesados // 2) else 2
    finally:
        conn.close()
        _log("Conexión cerrada.")


if __name__ == "__main__":
    sys.exit(main())
