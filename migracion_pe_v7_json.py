"""Documento 27 de Pólaris, H-2. Migración de JSON, aditiva y reversible. Requiere migracion_pe_v6_json.py.

  criteria.json  diagnostico_paso2.que_es.sma200: la nota combina pendiente y posición del precio (doc. 22).

Uso:  python migracion_pe_v7_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v7"
QUE_ES_SMA200 = ("Hacia dónde va la media de los últimos 200 cierres (sube, baja o está plana, y si ha girado en "
                 "las últimas semanas) y si el precio está por encima o por debajo de ella.")


def _leer():
    with open(DIR / "criteria.json", encoding="utf-8") as f:
        return json.load(f)


def _escribir(d):
    with open(DIR / "criteria.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer(); d = c["diagnostico_paso2"]
    d.setdefault(CLAVE_PREV, {"que_es_sma200": d["que_es"].get("sma200")})
    d["que_es"]["sma200"] = QUE_ES_SMA200
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer(); d = c["diagnostico_paso2"]
    p = d.pop(CLAVE_PREV, None)
    if p:
        d["que_es"]["sma200"] = p["que_es_sma200"]
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "_previo_pe_v6" not in _leer().get("diagnostico_paso2", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v6_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
