"""Documento 32 de Pólaris, mejora Q-3. Migración de JSON, aditiva y reversible. Requiere migracion_pe_v11_json.py.

  criteria.json  semaforo_paso3.cotizacion_actual.nota_fija: alineada con el título «Factores que cambiarían si la
                 sesión cerrara al precio actual».

Uso:  python migracion_pe_v12_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v12"
NOTA = ("Los indicadores se calculan con sesiones cerradas. Este apartado indica qué factores cambiarían si la sesión "
        "cerrara al precio actual; el cambio solo se confirma con el cierre.")


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
    q.setdefault(CLAVE_PREV, {"nota_fija": q.get("nota_fija")})
    q["nota_fija"] = NOTA
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer()
    q = c["semaforo_paso3"]["cotizacion_actual"]
    p = q.pop(CLAVE_PREV, None)
    if p:
        q["nota_fija"] = p["nota_fija"]
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "titulo_lista" not in _leer().get("semaforo_paso3", {}).get("cotizacion_actual", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v11_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
