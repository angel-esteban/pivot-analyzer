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
  python cron_fundamentales.py --nivel estructural   # sector, free float, nombre…
  python cron_fundamentales.py --nivel ambos         # estructural + fundamental

  Desde Windows, doble clic en refrescar_screener.bat (IBEX 35, ambos niveles).

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


_LOG_FILE: Path | None = None   # si se usa --log-dir, además de la consola se escribe aquí


def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{ts}] {msg}"
    print(linea, flush=True)
    if _LOG_FILE is not None:
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(linea + "\n")
        except Exception:                            # noqa: BLE001
            pass


def obtener_database_url() -> str:
    """Lee la cadena de conexión: primero de entorno, luego de .streamlit/secrets.toml."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secrets = _DIR / ".streamlit" / "secrets.toml"
    if secrets.is_file():
        try:
            try:
                import tomllib  # Python 3.11+
                with open(secrets, "rb") as f:
                    val = tomllib.load(f).get("DATABASE_URL")
            except ModuleNotFoundError:              # Python < 3.11: lectura mínima de la línea
                val = None
                for _ln in secrets.read_text(encoding="utf-8").splitlines():
                    if _ln.strip().startswith("DATABASE_URL"):
                        val = _ln.split("=", 1)[1].strip().strip('"').strip("'")
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


def ejecutar(conn, tickers: list[str], fuente=None, nivel: str = "fundamental",
             disparado_por: str = "cron"):
    """Lanza la ingesta del nivel pedido ('fundamental' o 'estructural'). `fuente` inyectable para test."""
    fn = ingesta.ingerir_estructural if nivel == "estructural" else ingesta.ingerir_fundamental
    return fn(tickers, conn, criteria_path=CRITERIA_PATH, fuente=fuente, disparado_por=disparado_por)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refresco fundamental del screener.")
    ap.add_argument("--indice", help="Nombre exacto del índice (si se omite, todo el universo).")
    ap.add_argument("--tickers", nargs="+", help="Lista explícita de tickers (ignora --indice).")
    ap.add_argument("--nivel", choices=["fundamental", "estructural", "ambos"], default="fundamental",
                    help="Qué tablas refrescar (por defecto 'fundamental', como el cron semanal).")
    ap.add_argument("--origen", default="cron",
                    help="Etiqueta para ingesta_log (p. ej. 'pc' al lanzarlo a mano).")
    ap.add_argument("--log-dir", help="Carpeta donde guardar también el registro (p. ej. logs).")
    args = ap.parse_args(argv)
    if args.log_dir:
        global _LOG_FILE
        _d = Path(args.log_dir)
        if not _d.is_absolute():
            _d = _DIR / _d
        _d.mkdir(parents=True, exist_ok=True)
        _LOG_FILE = _d / f"refresco_{datetime.datetime.now():%Y-%m-%d_%H%M}.log"

    import psycopg2
    url = obtener_database_url()
    _log("Conectando a Neon...")
    conn = psycopg2.connect(url)
    try:
        tickers = args.tickers or cargar_universo(conn, args.indice)
        if not tickers:
            _log("No hay tickers que procesar. Fin.")
            return 1
        niveles = ["estructural", "fundamental"] if args.nivel == "ambos" else [args.nivel]
        codigo = 0
        for nivel in niveles:
            _log(f"Universo: {len(tickers)} tickers. Iniciando ingesta {nivel}...")
            r = ejecutar(conn, tickers, nivel=nivel, disparado_por=args.origen)
            _log(f"Resultado {nivel} -> ok={r.ok} fallidos={r.fallidos} (log #{r.log_id})")
            if r.detalle_fallidos:
                for tk, motivo in r.detalle_fallidos.items():
                    _log(f"  FALLO {tk}: {motivo}")
            # Éxito si al menos la mitad se procesó bien
            if r.ok < max(1, r.procesados // 2):
                codigo = 2
        return codigo
    finally:
        conn.close()
        _log("Conexión cerrada.")


if __name__ == "__main__":
    sys.exit(main())
