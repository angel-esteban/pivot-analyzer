"""Documento 25 de Pólaris (validación de F23 y decisiones). Migración de JSON, aditiva y reversible.
Requiere migracion_pe_v4_json.py aplicada.

  criteria.json          diagnostico_paso2: «qué es» y «cómo leerlo» del máximo histórico con «serie disponible»
                         (§3); tramo «sin_niveles» y niveles mensual/trimestral/anual con SMA50/SMA200 en
                         resistencias (§1, §2). contexto_macro_tramos.dist_sma200: sin «las correcciones hacia
                         ella son habituales» (V-2). conclusiones_paso1.valor.matiz_rango: «en la zona … del año» (V-2).
  crisis_patterns.json   Las 12 lecciones validadas (§5) con fuente, periodo y leccion_validada; AGG «sin contar
                         los cupones cobrados».
  sector_knowledge.json  Energía: lección de Pólaris comprobada con la EIA (RCLC1 y RBRTE); ITX validada.

Uso:  python migracion_pe_v5_json.py [--revertir]
"""
import copy
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v5"

QUE_ES_ATH = ("La distancia entre el precio y el máximo histórico de la serie disponible de Yahoo, que está ajustada "
              "por operaciones de capital.")
COMO_ATH = {
    "subida_libre_establecida": "El precio está por encima de cualquier nivel de la serie disponible: no hay máximos previos por encima que sirvan de referencia.",
    "en_ath": "El precio está prácticamente en el máximo histórico de la serie disponible.",
    "aproximandose_cerca": "Estar cerca del máximo histórico de la serie disponible indica que el precio está en la parte alta de esa serie.",
    "aproximandose": "El precio está algo por debajo del máximo histórico de la serie disponible: cerca de la parte alta, pero sin alcanzarla.",
    "referencia": "Estar lejos indica que el precio todavía está por debajo de niveles ya alcanzados en la serie disponible; el máximo queda como referencia lejana.",
    "lejos": "El precio está muy por debajo del máximo histórico de la serie disponible: niveles ya alcanzados en el pasado quedan muy lejos.",
}
COMO_RES = {
    "sin_resistencia": "No hay niveles reforzados por encima del precio entre los niveles calculados por el método (pivots mensuales, trimestrales y anuales que coinciden con la SMA50 o la SMA200); no significa que no existan otros techos.",
    "sin_soporte": "No hay niveles reforzados por debajo del precio entre los niveles calculados por el método (pivots mensuales, trimestrales y anuales que coinciden con la SMA50 o la SMA200); no significa que no existan otros suelos.",
    "sin_niveles": "El método no encuentra soportes ni resistencias reforzados entre sus niveles calculados; el componente no apoya ni resta a la estructura. No significa que no existan otras referencias de precio.",
}
SMA_BLOQUE_OLD = "Estar muy por encima también significa que el precio se ha alejado de su media, y las correcciones hacia ella son habituales."
SMA_BLOQUE_NEW = "Estar muy por encima también significa que el precio se ha alejado de su media: el método lo interpreta como un precio alejado de su referencia de largo plazo."
SMA_TRAMO_NEW = ("Estar muy por encima indica que el mercado viene revalorizando el valor; el método lo interpreta como "
                 "un precio alejado de su referencia de largo plazo.")
MATIZ_RANGO = {"Zona baja del año": "en la zona baja del año", "Zona media": "en la zona media del año",
               "Zona alta del año": "en la zona alta del año"}

_YF = "Yahoo Finance ({}, cierres diarios), cálculo de PivotAnalyzer"
CRISIS = {  # clave: (lección, fuente, periodo de la lección)
    "volcker_shock_1979_1982": (
        "Entre 1979 y 1982, la Reserva Federal de Paul Volcker subió los tipos con fuerza para frenar una inflación muy alta, aunque la economía entrara en recesión. Enseña que un banco central puede anteponer la estabilidad de los precios al crecimiento, como volvieron a hacer la Fed y el BCE en 2022-2023.",
        "Reserva Federal (historia de la política monetaria)", "1979 – 1982"),
    "black_monday_1987": (
        "El 19/10/1987 el S&P 500 cayó un 20,5% en una sola sesión (de 282,70 a 224,84 puntos). En los análisis posteriores se señaló que las coberturas automáticas de carteras, al vender todas a la vez, amplificaron la caída. Enseña que, cuando muchos inversores usan la misma cobertura, el riesgo no desaparece: se concentra.",
        _YF.format("^GSPC"), "16/10/1987 (282,70) – 19/10/1987 (224,84)"),
    "burbuja_japonesa_1989_2003": (
        "El Nikkei 225 cayó un 80,5% entre el 29/12/1989 (38.915,87) y el 28/04/2003 (7.607,88), en un periodo en que también se desplomaron los precios inmobiliarios. Enseña que, cuando estallan a la vez burbujas financieras e inmobiliarias, la recuperación puede tardar décadas.",
        _YF.format("^N225"), "29/12/1989 – 28/04/2003"),
    "sl_crisis_1989_1995": (
        "Muchas cajas de ahorro de EE. UU. financiaban hipotecas a largo plazo con depósitos a corto plazo; cuando subieron los tipos, cientos quebraron. En 2023, Silicon Valley Bank sufrió pérdidas por un desajuste parecido. Enseña que captar a corto y prestar a largo es uno de los riesgos bancarios más antiguos.",
        "FDIC (historia de la crisis de las cajas de ahorro)", "1989 – 1995"),
    "erm_crisis_1992": (
        "En septiembre de 1992 la libra esterlina y la lira tuvieron que salir del mecanismo de cambios del Sistema Monetario Europeo, pese a las subidas de tipos para defenderlas. Enseña que un tipo de cambio fijo es difícil de sostener cuando la política económica de fondo no lo acompaña.",
        "Historia del Sistema Monetario Europeo (salida de la libra y la lira del mecanismo de cambios)", "Septiembre de 1992"),
    "crisis_asiatica_ltcm_1997_1998": (
        "En 1998 el fondo LTCM tuvo que ser rescatado por un grupo de bancos, en una operación coordinada por la Reserva Federal de Nueva York. Sus modelos suponían que los movimientos extremos eran muy raros y que los activos no se moverían todos a la vez. Enseña que en las crisis las correlaciones suben y que los modelos basados en el pasado pueden fallar.",
        "Reserva Federal de Nueva York (rescate de LTCM)", "Septiembre de 1998"),
    "burbuja_puntocom_1999_2002": (
        "El Nasdaq Composite cayó un 77,9% entre el 10/03/2000 y el 09/10/2002. Muchas empresas de internet sin beneficios ni caja positiva desaparecieron, mientras otras con negocio rentable sobrevivieron. Enseña que una buena tecnología no garantiza una valoración sostenible.",
        _YF.format("^IXIC"), "10/03/2000 – 09/10/2002"),
    "gfc_2007_2009": (
        "El S&P 500 cayó un 56,8% entre el 09/10/2007 y el 09/03/2009. Productos complejos basados en hipotecas, que se consideraban seguros, resultaron estar expuestos al mismo riesgo inmobiliario. Enseña que la complejidad puede ocultar riesgos que solo aparecen cuando todo cae a la vez.",
        _YF.format("^GSPC"), "09/10/2007 – 09/03/2009"),
    "crisis_deuda_soberana_europea_2010_2012": (
        "Entre 2010 y 2012 se dispararon las primas de riesgo de varios países del euro. En julio de 2012, la frase de Mario Draghi («haremos lo que sea necesario») marcó el punto de giro. Enseña el peso que tiene la credibilidad de un banco central en los mercados de deuda.",
        "BCE (discurso de Mario Draghi en Londres, 26/07/2012)", "2010 – 2012"),
    "covid_crash_2020": (
        "El S&P 500 cayó un 33,9% entre el 19/02/2020 y el 23/03/2020, y recuperó el máximo anterior el 18/08/2020, con vacunas y estímulos públicos. Enseña que una caída por pánico, en la que bajan casi todos los activos a la vez, puede comportarse de forma distinta a una causada por un deterioro duradero de los beneficios.",
        _YF.format("^GSPC"), "19/02/2020 – 23/03/2020; máximo recuperado el 18/08/2020"),
    "inflacion_tipos_2022": (
        "En 2022 el S&P 500 bajó un 19,4% y el fondo de bonos estadounidenses AGG un 15,0% en precio, sin contar los cupones cobrados (del 31/12/2021 al 30/12/2022). Los bancos centrales subían los tipos con fuerza para frenar la inflación. Enseña que la diversificación entre acciones y bonos protege menos cuando la inflación es alta.",
        _YF.format("^GSPC y AGG"), "31/12/2021 – 30/12/2022"),
    "crisis_bancaria_regional_eeuu_2023": (
        "En marzo de 2023 quebraron varios bancos regionales de EE. UU., entre ellos Silicon Valley Bank, por un desajuste parecido al de las cajas de ahorro: depósitos a la vista invertidos en bonos a largo plazo que perdieron valor al subir los tipos. Las retiradas de depósitos fueron especialmente rápidas. Enseña a revisar cómo afectan las subidas de tipos al balance de un banco.",
        "FDIC y Reserva Federal (informes sobre las quiebras de marzo de 2023)", "Marzo de 2023"),
}

ENERGIA = {
    "leccion_historica": ("El 20/04/2020 el contrato de futuros de WTI de mayo cerró en −37,63 $ por barril, por primera "
                          "vez en negativo; en marzo de 2022, tras la invasión de Ucrania, el Brent superó los 120 $. "
                          "El sector energético sigue sobre todo al crudo."),
    "leccion_fuente": "EIA (series RCLC1, futuro WTI contrato 1 en NYMEX, y RBRTE, Brent spot), comprobado por FABER-PA",
    "leccion_periodo": "20/04/2020; marzo de 2022 (Brent por encima de 120 $ desde el 04/03/2022)",
    "leccion_validada": True,
}
CAMPOS_ENERGIA = tuple(ENERGIA)


def _leer(n):
    with open(DIR / n, encoding="utf-8") as f:
        return json.load(f)


def _escribir(n, d):
    with open(DIR / n, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


_FALTA = "__falta__"


def _guardar(obj, campos):
    return {k: copy.deepcopy(obj.get(k, _FALTA)) for k in campos}


def _restaurar(obj, prev):
    for k, v in prev.items():
        if v == _FALTA:
            obj.pop(k, None)
        else:
            obj[k] = v

# crisis_patterns.json está formateado a mano: se edita por texto, línea a línea, para no reformatear el
# archivo entero. La lección anterior se guarda en «leccion_operativa_previa_pe_v5» para poder revertir.
_CAMPO_PREV = "leccion_operativa_previa_pe_v5"


def _j(v):
    return json.dumps(v, ensure_ascii=False)


def _crisis_aplicar():
    ruta = DIR / "crisis_patterns.json"
    txt = ruta.read_text(encoding="utf-8")
    cp = json.loads(txt)
    for k, (lec, fte, per) in CRISIS.items():
        cr = cp["crisis"][k]
        if cr.get("leccion_validada") is not None:
            continue                                   # ya aplicada
        viejo = '"leccion_operativa": ' + _j(cr["leccion_operativa"])
        assert txt.count(viejo) == 1, k
        i = txt.index(viejo)
        ini = txt.rindex("\n", 0, i) + 1
        sang = txt[ini:i]
        nuevo = (viejo.replace(_j(cr["leccion_operativa"]), _j(lec)) + ",\n"
                 + sang + '"fuente": ' + _j(fte) + ",\n"
                 + sang + '"leccion_periodo": ' + _j(per) + ",\n"
                 + sang + '"leccion_validada": true,\n'
                 + sang + '"' + _CAMPO_PREV + '": ' + _j(cr["leccion_operativa"]))
        txt = txt.replace(viejo, nuevo)
    json.loads(txt)
    ruta.write_text(txt, encoding="utf-8")


def _crisis_revertir():
    ruta = DIR / "crisis_patterns.json"
    txt = ruta.read_text(encoding="utf-8")
    cp = json.loads(txt)
    for k, (lec, fte, per) in CRISIS.items():
        cr = cp["crisis"][k]
        if _CAMPO_PREV not in cr:
            continue
        nuevo = '"leccion_operativa": ' + _j(cr["leccion_operativa"])
        i = txt.index(nuevo)
        ini = txt.rindex("\n", 0, i) + 1
        sang = txt[ini:i]
        bloque = (nuevo + ",\n" + sang + '"fuente": ' + _j(cr["fuente"]) + ",\n"
                  + sang + '"leccion_periodo": ' + _j(cr["leccion_periodo"]) + ",\n"
                  + sang + '"leccion_validada": true,\n'
                  + sang + '"' + _CAMPO_PREV + '": ' + _j(cr[_CAMPO_PREV]))
        assert txt.count(bloque) == 1, k
        txt = txt.replace(bloque, '"leccion_operativa": ' + _j(cr[_CAMPO_PREV]))
    json.loads(txt)
    ruta.write_text(txt, encoding="utf-8")


def aplicar():
    c = _leer("criteria.json")
    d = c["diagnostico_paso2"]
    sma = c["contexto_macro_tramos"]["dist_sma200"]
    mv = c["conclusiones_paso1"]["valor"]
    if CLAVE_PREV not in d:
        d[CLAVE_PREV] = {"que_es_ath": d["que_es"].get("ath"), "como_ath": copy.deepcopy(d["como_leerlo"].get("ath")),
                         "como_resist": copy.deepcopy(d["como_leerlo"]["resist"]),
                         "sma_bloque": sma.get("como_leerlo"), "sma_tramo0": sma["tramos"][0].get("como_leerlo"),
                         "matiz_rango": copy.deepcopy(mv.get("matiz_rango"))}
    d["que_es"]["ath"] = QUE_ES_ATH
    d["como_leerlo"]["ath"] = dict(COMO_ATH)
    d["como_leerlo"]["resist"].update(COMO_RES)
    sma["como_leerlo"] = sma["como_leerlo"].replace(SMA_BLOQUE_OLD, SMA_BLOQUE_NEW)
    assert sma["tramos"][0].get("desde") == 10
    sma["tramos"][0]["como_leerlo"] = SMA_TRAMO_NEW
    mv["matiz_rango"] = dict(MATIZ_RANGO)
    _escribir("criteria.json", c)

    _crisis_aplicar()

    s = _leer("sector_knowledge.json")
    sec = s["sectores"]
    en = sec["Energy"]
    en.setdefault(CLAVE_PREV, _guardar(en, CAMPOS_ENERGIA))
    en.update(ENERGIA)
    sec["Consumer Cyclical"]["lecciones_industria"]["Apparel Retail"]["leccion_validada"] = True
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "crisis_patterns.json", "sector_knowledge.json"]


def revertir():
    c = _leer("criteria.json")
    d = c["diagnostico_paso2"]
    p = d.pop(CLAVE_PREV, None)
    if p:
        d["que_es"]["ath"] = p["que_es_ath"]
        d["como_leerlo"]["ath"] = p["como_ath"]
        d["como_leerlo"]["resist"] = p["como_resist"]
        sma = c["contexto_macro_tramos"]["dist_sma200"]
        sma["como_leerlo"] = p["sma_bloque"]
        sma["tramos"][0]["como_leerlo"] = p["sma_tramo0"]
        c["conclusiones_paso1"]["valor"]["matiz_rango"] = p["matiz_rango"]
    _escribir("criteria.json", c)

    _crisis_revertir()

    s = _leer("sector_knowledge.json")
    sec = s["sectores"]
    pe = sec["Energy"].pop(CLAVE_PREV, None)
    if pe:
        _restaurar(sec["Energy"], pe)
    sec["Consumer Cyclical"]["lecciones_industria"]["Apparel Retail"]["leccion_validada"] = False
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "crisis_patterns.json", "sector_knowledge.json"]


if __name__ == "__main__":
    if "_previo_pe_v4" not in _leer("criteria.json").get("diagnostico_paso2", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v4_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
