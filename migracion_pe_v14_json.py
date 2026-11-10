"""Datos macro guardados (aprobado por el propietario el 10/11/2026). Migración de JSON, aditiva y reversible.
Requiere migracion_pe_v13_json.py.

  criteria.json  avisos_datos: textos que indican al usuario que se trabaja con datos guardados.

Uso:  python migracion_pe_v14_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
TEXTOS = {
    "macro_guardado_valor": "dato guardado el {fecha}; la fuente no respondió",
    "macro_guardado_nota": ("Uno o más indicadores usan datos guardados porque la fuente no respondió. La lectura puede "
                            "no recoger el último dato publicado."),
    "macro_guardado_conclusion": "(con datos macro guardados)",
}


def _leer():
    with open(DIR / "criteria.json", encoding="utf-8") as f:
        return json.load(f)


def _escribir(d):
    with open(DIR / "criteria.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer()
    c["avisos_datos"].update(TEXTOS)
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer()
    for k in TEXTOS:
        c["avisos_datos"].pop(k, None)
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "avisos_datos" not in _leer():
        sys.exit("Primero hay que aplicar migracion_pe_v13_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
