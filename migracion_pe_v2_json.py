"""Spec PE v2 — Conclusiones del Paso 1 de «¿Por dónde empiezo?». Migración de JSON, aditiva y reversible.

Requiere migracion_pe_v1_json.py y migracion_pe_v1b_json.py aplicadas.
  criteria.json          + "conclusiones_paso1" (parámetros del método de PE-08/09/10)
  sector_knowledge.json  + "efecto_ciclo" por sector: {fase: −2…+2} (PE-09; Pólaris valida la tabla).
                         No se toca "comportamiento_ciclo" (sus textos siguen igual).

Uso:  python migracion_pe_v2_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

CONCLUSIONES = {
    "_descripcion": ("Spec PE v2 (PE-08, PE-09, PE-10). Parámetros del método para las conclusiones "
                     "del Paso 1. Describen el contexto; la decisión corresponde al usuario."),
    "rotulo": "Parámetros del método",
    "valor": {
        "umbral_sma200_pct": 2.0,
        "muy_por_encima_pct": 10.0,
        "tramos_vol_amplias": ["Alta", "Muy alta"],
        "matiz_rango": {"Zona baja del año": "cerca de mínimos del año",
                        "Zona media": "en la zona media del año",
                        "Zona alta del año": "cerca de máximos del año"},
    },
    "sector": {
        "intensidad_valor": {"alta": 1.0, "media": 0.5, "baja": 0.0},
        "corte_viento": 1.0,
        "texto_efecto": {"2": "muy favorable", "1": "favorable", "0": "neutral",
                         "-1": "desfavorable", "-2": "muy desfavorable"},
    },
    "matriz_general": {
        "a_favor|a_favor": {"texto": "viento a favor en los dos niveles", "grupo": "a_favor"},
        "a_favor|neutro": {"texto": "mayoritariamente a favor", "grupo": "a_favor"},
        "a_favor|en_contra": {"texto": "señales cruzadas", "grupo": "cruzadas"},
        "neutra|a_favor": {"texto": "mayoritariamente a favor", "grupo": "a_favor"},
        "neutra|neutro": {"texto": "sin dirección clara", "grupo": "sin_direccion"},
        "neutra|en_contra": {"texto": "mayoritariamente en contra", "grupo": "en_contra"},
        "en_contra|a_favor": {"texto": "señales cruzadas", "grupo": "cruzadas"},
        "en_contra|neutro": {"texto": "mayoritariamente en contra", "grupo": "en_contra"},
        "en_contra|en_contra": {"texto": "viento en contra en los dos niveles", "grupo": "en_contra"},
    },
    "que_mirar": {
        "cruzadas": ("Cuando valor y sector apuntan en direcciones distintas, la estructura (Paso 2) y "
                     "el momento (Paso 3) ayudan a ver cuál de las dos fuerzas domina ahora."),
        "a_favor": ("Con el contexto a favor, los pasos siguientes ayudan a ver si el precio está "
                    "extendido o cerca de niveles de referencia."),
        "en_contra": ("Con el contexto en contra, los pasos siguientes ayudan a ver si hay señales de "
                      "estabilización o si la debilidad continúa."),
        "sin_direccion": "Sin dirección de contexto, los niveles (Paso 4) son la referencia principal.",
    },
    "nota_fija": ("Conclusión automática del método a partir de los datos mostrados. Describe el "
                  "contexto; la decisión corresponde al usuario."),
}

# PE-09 — efecto de cada fase del ciclo por sector (asignado por FABER-PA a partir del texto de
# comportamiento_ciclo con la tabla de la spec; Pólaris valida). Orden: expansión, pico,
# contracción, recuperación.
EFECTO = {
    "Technology":             (2, -1, -1, 2),
    "Financial Services":     (1, 2, -2, 1),
    "Healthcare":             (0, 1, 2, -1),
    "Consumer Cyclical":      (2, 0, -2, 1),
    "Consumer Defensive":     (-1, 1, 2, -1),
    "Energy":                 (1, 0, -1, 2),
    "Utilities":              (-1, 1, 2, -1),
    "Industrials":            (2, 0, -1, 2),
    "Basic Materials":        (2, 0, -2, 2),
    "Real Estate":            (1, -1, -1, 2),
    "Communication Services": (0, 0, 0, 0),
}
FASES = ("expansion", "pico", "contraccion", "recuperacion")


def _leer(n):
    with open(DIR / n, encoding="utf-8") as f:
        return json.load(f)


def _escribir(n, d):
    with open(DIR / n, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer("criteria.json"); c["conclusiones_paso1"] = CONCLUSIONES; _escribir("criteria.json", c)
    s = _leer("sector_knowledge.json")
    for k, vals in EFECTO.items():
        s["sectores"][k]["efecto_ciclo"] = dict(zip(FASES, vals))
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


def revertir():
    c = _leer("criteria.json"); c.pop("conclusiones_paso1", None); _escribir("criteria.json", c)
    s = _leer("sector_knowledge.json")
    for k in EFECTO:
        s["sectores"][k].pop("efecto_ciclo", None)
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


if __name__ == "__main__":
    if "contexto_macro_tramos" not in _leer("criteria.json"):
        sys.exit("Primero hay que aplicar migracion_pe_v1_json.py y migracion_pe_v1b_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
