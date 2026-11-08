"""Documento 26 de Pólaris (validación de F24). Migración de JSON, aditiva y reversible.
Requiere migracion_pe_v5_json.py aplicada.

  criteria.json          diagnostico_paso2.como_leerlo.ath.referencia: texto propio del tramo
                         «a distancia media del máximo» (G-2).
  sector_knowledge.json  Fuente de la lección de Energía sin el nombre del agente (G-3) y las 8 lecciones
                         sectoriales validadas con los cambios pedidos (§3).

Uso:  python migracion_pe_v6_json.py [--revertir]
"""
import copy
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v6"
_FALTA = "__falta__"

COMO_ATH_REFERENCIA = ("El precio está claramente por debajo del máximo de la serie, pero no lejos: el máximo sigue "
                       "siendo una referencia visible.")

LECCIONES = {  # sector: campos que cambian
    "Energy": {
        "leccion_fuente": "EIA (series RCLC1 y RBRTE), comprobación de PivotAnalyzer",
    },
    "Technology": {"leccion_validada": True},
    "Healthcare": {
        "leccion_historica": ("Entre el 09/10/2007 y el 09/03/2009, durante la crisis financiera, el S&P 500 cayó un "
                              "56,8% (de 1.565,15 a 676,53 puntos) y el fondo cotizado XLV, que replica el sector "
                              "sanitario del S&P 500, un 39,7% (de 36,30 a 21,88 $). El sector también cayó, pero "
                              "bastante menos que el mercado."),
        "leccion_periodo": "09/10/2007 – 09/03/2009",
        "leccion_validada": True,
    },
    "Consumer Cyclical": {
        "leccion_historica": ("En España, el turismo supuso el 12,6% del PIB en 2024 (estimación avance del INE). "
                              "En 2020, con la pandemia, IAG cayó un 76,8% entre el 17/01/2020 y el 03/08/2020 y "
                              "Meliá un 67,1% entre el 15/01/2020 y el 18/03/2020 (de 8,34 a 2,74 €). Es un sector "
                              "muy expuesto a un frenazo brusco de la demanda."),
        "leccion_fuente": ("INE, Cuenta Satélite del Turismo de España (nota de prensa del 22/12/2025, 2024 en "
                           "estimación avance); Yahoo Finance (IAG.MC, MEL.MC, cierres diarios), cálculo de "
                           "PivotAnalyzer. De IAG solo se da el porcentaje: la serie de Yahoo está ajustada por la "
                           "ampliación de capital de 2020"),
        "leccion_validada": True,
    },
    "Consumer Defensive": {"leccion_validada": True},
    "Industrials": {
        "leccion_historica": ("Los índices de gestores de compras (PMI) manufactureros se publican antes que los "
                              "datos oficiales de producción y se usan como indicador adelantado de la actividad "
                              "industrial. Por debajo de 50 indican contracción."),
        "leccion_fuente": "Metodología de S&P Global / HCOB PMI",
        "leccion_periodo": "Metodología vigente",
        "leccion_validada": True,
    },
    "Basic Materials": {
        "leccion_historica": ("Entre el 07/11/2001 y el 02/07/2008 el precio del cobre en el mercado de futuros pasó "
                              "de 0,604 a 4,078 $ por libra: se multiplicó por 6,8, en un periodo de fuerte demanda "
                              "de China, entre otros factores. Entre el 02/01/2014 y el 15/01/2016 cayó un 43,5% "
                              "(de 3,43 a 1,94 $). El sector sigue de cerca estos ciclos de precios."),
        "leccion_validada": True,
    },
    "Real Estate": {"leccion_validada": True},
    "Communication Services": {
        "leccion_historica": ("Telefónica cerró a 32,23 € el 06/03/2000, en plena euforia puntocom; el 24/07/2012 "
                              "cotizaba a 8,53 € y el 09/02/2024 a 3,55 €. Una empresa puede seguir operando con "
                              "normalidad y, aun así, su acción no recuperar sus máximos durante décadas. Las cifras "
                              "no incluyen los dividendos cobrados ni las acciones recibidas en ampliaciones "
                              "liberadas (scrip)."),
        "leccion_validada": True,
    },
}


def _leer(n):
    with open(DIR / n, encoding="utf-8") as f:
        return json.load(f)


def _escribir(n, d):
    with open(DIR / n, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer("criteria.json")
    ath = c["diagnostico_paso2"]["como_leerlo"]["ath"]
    c["diagnostico_paso2"].setdefault(CLAVE_PREV, {"como_ath_referencia": ath.get("referencia")})
    ath["referencia"] = COMO_ATH_REFERENCIA
    _escribir("criteria.json", c)

    s = _leer("sector_knowledge.json")
    sec = s["sectores"]
    for k, campos in LECCIONES.items():
        sec[k].setdefault(CLAVE_PREV, {f: copy.deepcopy(sec[k].get(f, _FALTA)) for f in campos})
        sec[k].update(campos)
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


def revertir():
    c = _leer("criteria.json")
    p = c["diagnostico_paso2"].pop(CLAVE_PREV, None)
    if p:
        c["diagnostico_paso2"]["como_leerlo"]["ath"]["referencia"] = p["como_ath_referencia"]
    _escribir("criteria.json", c)

    s = _leer("sector_knowledge.json")
    for k in LECCIONES:
        prev = s["sectores"][k].pop(CLAVE_PREV, None)
        for f, v in (prev or {}).items():
            if v == _FALTA:
                s["sectores"][k].pop(f, None)
            else:
                s["sectores"][k][f] = v
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


if __name__ == "__main__":
    if "_previo_pe_v5" not in _leer("criteria.json").get("diagnostico_paso2", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v5_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
