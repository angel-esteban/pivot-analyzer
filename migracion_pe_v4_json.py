"""Documentos 22 y 23 de Pólaris (reglas del Diagnóstico y avisos de las exportaciones).
Migración de JSON, aditiva y reversible. Requiere migracion_pe_v3_json.py aplicada.

  criteria.json          diagnostico_paso2.como_leerlo: tramos nuevos de la SMA200 (pendiente × posición)
                         y de Fibonacci (niveles reales); resistencias «del método» (doc. 22 §2.5);
                         contexto_macro_tramos.volatilidad.nota en general (doc. 23 E-10).
  sector_knowledge.json  Utilities: «Redeia» y texto de pico (doc. 23 E-11); Consumer Cyclical: riesgo sin
                         paréntesis repetido (E-7) y lección por industria «Apparel Retail» (E-6);
                         Financial Services: «Financial Data & Stock Exchanges» con gestoras (doc. 22 §4.1).

Uso:  python migracion_pe_v4_json.py [--revertir]
"""
import copy
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v4"

COMO_SMA = {
    "giro_alcista_encima": "La media de largo plazo ha empezado a subir hace poco y el precio está por encima: el método lo interpreta como un posible cambio de tendencia al alza ya acompañado por el precio.",
    "tendencia_alcista_encima": "La media de largo plazo sube y el precio está por encima: el método lo interpreta como tendencia alcista de fondo confirmada por el precio.",
    "plana_encima": "La media de largo plazo apenas se mueve y el precio está por encima: sin tendencia de fondo clara, con el precio en la parte favorable.",
    "positiva_debajo": "La media de largo plazo sube, pero el precio ha caído por debajo: la tendencia de fondo sigue al alza y el precio no la acompaña ahora.",
    "plana_debajo": "La media de largo plazo apenas se mueve y el precio está por debajo: sin tendencia de fondo clara, con el precio en la parte débil.",
    "negativa_encima": "La media de largo plazo baja, aunque el precio está por encima: la tendencia de fondo sigue a la baja y el precio intenta separarse de ella.",
    "giro_bajista_debajo": "La media de largo plazo ha empezado a bajar hace poco y el precio está por debajo: el método lo interpreta como un posible cambio de tendencia a la baja acompañado por el precio.",
    "tendencia_bajista_debajo": "La media de largo plazo baja y el precio está por debajo: el método lo interpreta como tendencia bajista de fondo confirmada por el precio.",
}
COMO_FIBO = {
    "en_maximo": "El precio está en la parte alta del recorrido del último año, con un retroceso pequeño desde el máximo.",
    "retroceso_236": "El precio ha corregido poco desde el máximo del año (hasta el 23,6% del recorrido).",
    "retroceso_382": "El precio ha devuelto una parte moderada de la subida del año (hasta el 38,2%).",
    "retroceso_500": "El precio ha devuelto hasta la mitad de la subida del año.",
    "retroceso_618": "El precio ha devuelto más de la mitad de la subida del año: la estructura del swing se debilita.",
    "retroceso_786": "El precio ha devuelto la mayor parte de la subida del año: el recorrido alcista se ha debilitado mucho.",
    "swing_roto": "El precio ha devuelto casi toda la subida del año: el recorrido alcista del swing está casi anulado.",
}
COMO_RES = {
    "sin_resistencia": "No hay niveles reforzados por encima del precio entre los niveles calculados por el método (pivots semanales, trimestrales y anuales que coinciden con una media); no significa que no existan otros techos.",
    "sin_soporte": "No hay niveles reforzados por debajo del precio entre los niveles calculados por el método (pivots semanales, trimestrales y anuales que coinciden con una media); no significa que no existan otros suelos.",
}
NOTA_VOL = "A más volatilidad, más oscila en euros la misma cantidad invertida."

LECCION_ITX = {
    "leccion_historica": ("Entre el 19/02/2020 y el 16/03/2020, con el cierre de tiendas por la pandemia, Inditex "
                          "cayó un 37,1% (de 32,08 a 20,17 €). El comercio de moda depende de que las tiendas estén "
                          "abiertas y del gasto no esencial de las familias."),
    "leccion_cualitativa": ("En 2020, el cierre de tiendas por la pandemia hundió en pocas semanas la cotización de "
                            "las empresas de moda: el sector depende del gasto no esencial de las familias."),
    "leccion_fuente": "Yahoo Finance (ITX.MC, cierres diarios sin ajustar), cálculo de PivotAnalyzer",
    "leccion_periodo": "19/02/2020 (32,08 €) – 16/03/2020 (20,17 €)",
    "leccion_validada": False,
}

TEXTOS = [  # (sector, ruta, antiguo, nuevo)
    ("Utilities", "descripcion", "Iberdrola, Endesa, Red Eléctrica.", "Iberdrola, Endesa, Redeia."),
    ("Utilities", "comportamiento_ciclo.pico",
     "positivo — rotación defensiva, bajan tipos a futuro = compresión de spread",
     "positivo — los inversores rotan hacia sectores estables y empiezan a descontar bajadas de tipos, que "
     "favorecen a los valores que se comportan como bonos"),
    ("Consumer Cyclical", "riesgos_especificos", "Alta palanca operativa en el comercio minorista (costes fijos elevados)",
     "Alta palanca operativa en el comercio minorista"),
]


def _leer(n):
    with open(DIR / n, encoding="utf-8") as f:
        return json.load(f)


def _escribir(n, d):
    with open(DIR / n, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _sust(sec, ruta, old, new):
    obj = sec
    partes = ruta.split(".")
    for p in partes[:-1]:
        obj = obj[p]
    v = obj[partes[-1]]
    obj[partes[-1]] = [x.replace(old, new) for x in v] if isinstance(v, list) else v.replace(old, new)


def aplicar():
    c = _leer("criteria.json")
    d = c["diagnostico_paso2"]
    if CLAVE_PREV not in d:
        d[CLAVE_PREV] = {"como_leerlo": copy.deepcopy(d["como_leerlo"]),
                         "nota_vol": c["contexto_macro_tramos"]["volatilidad"].get("nota")}
    d["como_leerlo"]["sma200"] = dict(COMO_SMA)
    d["como_leerlo"]["fibo"] = dict(COMO_FIBO)
    d["como_leerlo"]["resist"].update(COMO_RES)
    c["contexto_macro_tramos"]["volatilidad"]["nota"] = NOTA_VOL
    _escribir("criteria.json", c)
    s = _leer("sector_knowledge.json"); sec = s["sectores"]
    for k, ruta, old, new in TEXTOS:
        _sust(sec[k], ruta, old, new)
    sec["Consumer Cyclical"]["lecciones_industria"] = {"Apparel Retail": dict(LECCION_ITX)}
    g = sec["Financial Services"]["subtipos_ciclo"]["gestoras"]["industrias_yahoo"]
    if "Financial Data & Stock Exchanges" not in g:
        g.append("Financial Data & Stock Exchanges")
    t = sec["Financial Services"]["sensibilidad_tipos"]["subtipos"]["seguros_gestoras"]["industrias_yahoo"]
    if "Financial Data & Stock Exchanges" not in t:
        t.append("Financial Data & Stock Exchanges")
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


def revertir():
    c = _leer("criteria.json")
    d = c["diagnostico_paso2"]
    prev = d.pop(CLAVE_PREV, None)
    if prev:
        d["como_leerlo"] = prev["como_leerlo"]
        c["contexto_macro_tramos"]["volatilidad"]["nota"] = prev["nota_vol"]
    _escribir("criteria.json", c)
    s = _leer("sector_knowledge.json"); sec = s["sectores"]
    for k, ruta, old, new in TEXTOS:
        _sust(sec[k], ruta, new, old)
    sec["Consumer Cyclical"].pop("lecciones_industria", None)
    for lst in (sec["Financial Services"]["subtipos_ciclo"]["gestoras"]["industrias_yahoo"],
                sec["Financial Services"]["sensibilidad_tipos"]["subtipos"]["seguros_gestoras"]["industrias_yahoo"]):
        if "Financial Data & Stock Exchanges" in lst:
            lst.remove("Financial Data & Stock Exchanges")
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


if __name__ == "__main__":
    if "diagnostico_paso2" not in _leer("criteria.json"):
        sys.exit("Primero hay que aplicar migracion_pe_v3_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
