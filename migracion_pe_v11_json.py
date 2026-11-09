"""Documento 31 de Pólaris (validación de F29), mejora C-1. Migración de JSON, aditiva y reversible.
Requiere migracion_pe_v10_json.py aplicada.

  criteria.json  semaforo_paso3.cotizacion_actual: título de la lista «Factores que cambiarían si la sesión
                 cerrara al precio actual» y su texto cuando no cambia ninguno.

Uso:  python migracion_pe_v11_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v11"
TITULO = "Factores que cambiarían si la sesión cerrara al precio actual"
SIN_CRUCES = "Ningún factor cambiaría si la sesión cerrara al precio actual: la lectura del último cierre se mantiene por ahora."


def _leer():
    with open(DIR / "criteria.json", encoding="utf-8") as f:
        return json.load(f)


def _escribir(d):
    with open(DIR / "criteria.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer()
    q = c["semaforo_paso3"]["cotizacion_actual"]
    q.setdefault(CLAVE_PREV, {"sin_cruces": q.get("sin_cruces")})
    q["titulo_lista"] = TITULO
    q["sin_cruces"] = SIN_CRUCES
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer()
    q = c["semaforo_paso3"]["cotizacion_actual"]
    p = q.pop(CLAVE_PREV, None)
    if p:
        q["sin_cruces"] = p["sin_cruces"]
        q.pop("titulo_lista", None)
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "cotizacion_actual" not in _leer().get("semaforo_paso3", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v10_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
