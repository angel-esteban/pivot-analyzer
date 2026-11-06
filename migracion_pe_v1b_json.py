"""Spec PE v1 — Decisiones 17 y 18 de Pólaris (cierre). Migración de JSON, aditiva y reversible.

Requiere haber aplicado antes migracion_pe_v1_json.py.
  sector_knowledge.json  sensibilidad_tipos: tabla definitiva (decisión 18 §2) + 'rotulo' +
                         'subtipos' de Financial Services por 'industry' de Yahoo;
                         lecciones: leccion_historica (con cifras citadas), leccion_cualitativa,
                         leccion_fuente, leccion_periodo, leccion_validada (decisión 17 §3, 18 §4).
  criteria.json          contexto_macro_tramos: 'como_leerlo' por tramo (decisión 18, P-1).
  macro_indicators.json  fase_ciclo_metodo: min_indicadores, reparto de voto, nota de subyacente.

Uso:  python migracion_pe_v1b_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

ROTULO_TIPOS = "Orientación cualitativa del método"

# Decisión 18 §2 — (intensidad, si_suben, motivo)
TIPOS = {
    "Utilities": ("alta", "perjudica", None),
    "Real Estate": ("alta", "perjudica", None),
    "Technology": ("alta", "perjudica", None),
    "Consumer Cyclical": ("media", "perjudica", None),
    "Communication Services": ("media", "perjudica", None),
    "Industrials": ("media", "perjudica", None),
    "Basic Materials": ("media", "perjudica", None),
    "Energy": ("baja", "perjudica",
               "depende sobre todo del precio del crudo y del gas; los tipos encarecen la "
               "financiación de sus grandes inversiones"),
    "Consumer Defensive": ("baja", "perjudica", None),
    "Healthcare": ("baja", "perjudica", None),
    "Financial Services": ("alta", "favorece",
                           "mejora el margen de intereses, el motor del beneficio bancario; si "
                           "suben demasiado, puede aumentar la morosidad"),
}
SUBTIPOS_FIN = {
    "banca": {"nombre": "banca", "intensidad": "alta", "si_suben": "favorece",
              "motivo": ("mejora el margen de intereses, el motor del beneficio bancario; si suben "
                         "demasiado, puede aumentar la morosidad"),
              "por_defecto": True},
    "seguros_gestoras": {"nombre": "seguros y gestoras", "intensidad": "media", "si_suben": "mixto",
                         "motivo": ("las aseguradoras reinvierten sus carteras de renta fija a mayor "
                                    "rentabilidad, mientras que las gestoras pueden ver caer el valor "
                                    "de los activos que gestionan y, con él, sus comisiones"),
                         "industrias_yahoo": ["Insurance - Diversified", "Insurance - Life",
                                              "Insurance - Property & Casualty",
                                              "Insurance - Reinsurance", "Insurance - Specialty",
                                              "Insurance Brokers", "Asset Management",
                                              "Capital Markets"]},
}

YF = "cálculo de PivotAnalyzer sobre Yahoo Finance (cierres diarios sin ajustar por dividendos)"
LECCIONES = {
    "Utilities": dict(
        leccion_historica=("Entre el 25/05/2022 y el 12/10/2022, en plena subida de tipos del BCE, "
                           "Iberdrola cayó un 19,3% desde su máximo (cierres diarios sin ajustar; "
                           "fuente: Yahoo Finance, cálculo de PivotAnalyzer). Es un ejemplo de cómo "
                           "una utility puede corregir cuando suben los tipos, aunque la caída "
                           "tuviera también otras causas."),
        leccion_cualitativa=("En 2022, en plena subida de tipos del BCE, Iberdrola corrigió con "
                             "fuerza desde su máximo: un ejemplo de cómo una utility puede corregir "
                             "cuando suben los tipos, aunque la caída tuviera también otras causas."),
        leccion_fuente="Yahoo Finance (IBE.MC, cierres diarios sin ajustar), cálculo de PivotAnalyzer",
        leccion_periodo="25/05/2022 (11,415 €) – 12/10/2022 (9,208 €)",
        leccion_validada=True),
    "Financial Services": dict(
        leccion_historica=("En 2012 la banca española necesitó ayuda europea porque sus balances "
                           "tenían activos inmobiliarios valorados muy por encima de lo que se podía "
                           "obtener por ellos. Bankia fue el caso más grave. Enseña a leer con cautela "
                           "el valor contable de los activos poco líquidos. En julio de 2012, la frase "
                           "de Mario Draghi («haremos lo que sea necesario») marcó el punto de giro de "
                           "la crisis del euro."),
        leccion_cualitativa=None, leccion_fuente=None, leccion_periodo="2012",
        leccion_validada=True),
    "Technology": dict(
        leccion_historica=("Entre el 10/03/2000 y el 09/10/2002, tras la burbuja puntocom, el Nasdaq "
                           "Composite cayó un 77,9% (de 5.048,62 a 1.114,11 puntos). Entre el "
                           "19/11/2021 y el 28/12/2022, en plena subida de tipos de la Reserva "
                           "Federal, cayó un 36,4% (de 16.057,44 a 10.213,29). Las valoraciones muy "
                           "altas del sector pueden corregir con fuerza, aunque cada caída tuvo "
                           "varias causas."),
        leccion_cualitativa=("Las tecnológicas han sufrido caídas muy fuertes cuando sus valoraciones "
                             "estaban muy altas, como tras la burbuja puntocom de 2000-2002 o durante "
                             "la subida de tipos de 2022."),
        leccion_fuente="Yahoo Finance (índice ^IXIC, cierres diarios), cálculo de PivotAnalyzer",
        leccion_periodo="10/03/2000 – 09/10/2002 y 19/11/2021 – 28/12/2022",
        leccion_validada=False),
    "Healthcare": dict(
        leccion_historica=("Entre el 09/10/2007 y el 09/03/2009, durante la crisis financiera, el S&P "
                           "500 cayó un 56,8% (de 1.565,15 a 676,53 puntos). En el mismo periodo, el "
                           "fondo cotizado XLV, que replica el sector sanitario del S&P 500, cayó un "
                           "40,6% desde su máximo del 10/12/2007. El sector también cayó, pero "
                           "bastante menos que el mercado."),
        leccion_cualitativa=("En la crisis financiera de 2007-2009 el sector sanitario también cayó, "
                             "pero bastante menos que el conjunto del mercado: su demanda depende poco "
                             "del ciclo."),
        leccion_fuente="Yahoo Finance (^GSPC y XLV, cierres diarios), cálculo de PivotAnalyzer",
        leccion_periodo="09/10/2007 – 09/03/2009 (XLV: desde el 10/12/2007)",
        leccion_validada=False),
    "Consumer Cyclical": dict(
        leccion_historica=("En España, el turismo supuso el 12,6% del PIB en 2024 (estimación avance "
                           "del INE). En 2020, con la pandemia, IAG cayó un 76,8% entre el 17/01/2020 "
                           "y el 03/08/2020 (de 5,22 a 1,21 €) y Meliá un 67,1% entre el 15/01/2020 y "
                           "el 18/03/2020 (de 8,34 a 2,74 €). Es un sector muy expuesto a un frenazo "
                           "brusco de la demanda."),
        leccion_cualitativa=("El turismo tiene mucho peso en la economía española. En 2020, la "
                             "pandemia hundió en pocas semanas la cotización de aerolíneas y hoteleras: "
                             "es un sector muy expuesto a un frenazo brusco de la demanda."),
        leccion_fuente=("INE, Cuenta Satélite del Turismo de España (nota de prensa del 22/12/2025); "
                        "Yahoo Finance (IAG.MC, MEL.MC, cierres diarios sin ajustar), cálculo de "
                        "PivotAnalyzer"),
        leccion_periodo="PIB: 2024 · cotizaciones: 15/01/2020 – 03/08/2020",
        leccion_validada=False),
    "Consumer Defensive": dict(
        leccion_historica=("En 2022, mientras el S&P 500 bajaba un 19,4% (del 31/12/2021 al "
                           "30/12/2022, de 4.766,18 a 3.839,50 puntos), el fondo XLP, que replica el "
                           "consumo básico del S&P 500, bajó un 3,3%. El sector también cayó, pero "
                           "mucho menos que el mercado."),
        leccion_cualitativa=("En 2022 el consumo básico estadounidense también cayó, pero mucho menos "
                             "que el conjunto del mercado."),
        leccion_fuente="Yahoo Finance (^GSPC y XLP, cierres diarios), cálculo de PivotAnalyzer",
        leccion_periodo="31/12/2021 – 30/12/2022",
        leccion_validada=False),
    "Energy": dict(
        leccion_historica=("El 20/04/2020 el contrato de futuros de petróleo WTI más próximo a vencer "
                           "cerró a −37,63 $ por barril, algo sin precedentes. El 08/03/2022, tras la "
                           "invasión de Ucrania, el Brent cerró a 127,98 $. En 2022 el fondo XLE "
                           "(energía del S&P 500) subió un 57,6% y fue el único de los 11 fondos "
                           "sectoriales del S&P 500 que acabó el año en positivo."),
        leccion_cualitativa=("El precio del petróleo puede moverse de forma extrema: en 2020 llegó a "
                             "cotizar en negativo en el mercado de futuros y en 2022 se disparó tras la "
                             "invasión de Ucrania. El sector energético sigue sobre todo al crudo."),
        leccion_fuente=("Yahoo Finance (CL=F, BZ=F y fondos Select Sector SPDR, cierres diarios), "
                        "cálculo de PivotAnalyzer"),
        leccion_periodo="20/04/2020; 08/03/2022; 31/12/2021 – 30/12/2022",
        leccion_validada=False),
    "Industrials": dict(
        leccion_historica=("Los índices de gestores de compras (PMI) manufactureros suelen girar "
                           "antes que los datos de producción. En la desaceleración industrial "
                           "europea de 2018-2019 dieron la señal antes de que empeoraran otros "
                           "indicadores."),
        leccion_cualitativa=None, leccion_fuente=None, leccion_periodo="2018-2019",
        leccion_validada=False),
    "Basic Materials": dict(
        leccion_historica=("Entre el 07/11/2001 y el 02/07/2008 el precio del cobre en el mercado de "
                           "futuros pasó de 0,604 a 4,078 $ por libra: se multiplicó por 6,8, en un "
                           "ciclo muy ligado a la demanda de China. Entre el 02/01/2014 y el "
                           "15/01/2016 cayó un 43,5% (de 3,43 a 1,94 $). El sector sigue de cerca "
                           "estos ciclos de precios."),
        leccion_cualitativa=("El cobre y otras materias primas viven ciclos largos de subidas y "
                             "caídas, muy ligados a la demanda de China. El sector sigue de cerca esos "
                             "ciclos."),
        leccion_fuente="Yahoo Finance (futuros de cobre HG=F, cierres diarios), cálculo de PivotAnalyzer",
        leccion_periodo="07/11/2001 – 02/07/2008 y 02/01/2014 – 15/01/2016",
        leccion_validada=False),
    "Real Estate": dict(
        leccion_historica=("En 2022, en un periodo de subidas de tipos del BCE, Merlin Properties cayó "
                           "un 31,1% entre el 20/04/2022 y el 27/09/2022 (de 10,85 a 7,48 €) y "
                           "Colonial un 44,7% entre el 04/01/2022 y el 12/10/2022 (de 8,43 a 4,66 €). "
                           "Muestra lo sensible que es el sector a los tipos, aunque la caída tuviera "
                           "también otras causas."),
        leccion_cualitativa=("En 2022, con el BCE subiendo tipos, las SOCIMI cotizadas españolas "
                             "corrigieron con fuerza: el sector es muy sensible a los tipos, aunque la "
                             "caída tuviera también otras causas."),
        leccion_fuente="Yahoo Finance (MRL.MC, COL.MC, cierres diarios sin ajustar), cálculo de PivotAnalyzer",
        leccion_periodo="04/01/2022 – 12/10/2022",
        leccion_validada=False),
    "Communication Services": dict(
        leccion_historica=("Telefónica cerró a 32,23 € el 06/03/2000, en plena euforia puntocom; el "
                           "24/07/2012 cotizaba a 8,53 € y el 09/02/2024 a 3,55 €. Una empresa puede "
                           "seguir operando con normalidad y, aun así, su acción no recuperar sus "
                           "máximos durante décadas. Las cifras no incluyen los dividendos cobrados."),
        leccion_cualitativa=("Telefónica marcó máximos en la euforia puntocom de 2000 y más de veinte "
                             "años después su acción seguía muy lejos de ellos: una empresa puede seguir "
                             "operando con normalidad y su acción no recuperar sus máximos durante "
                             "décadas."),
        leccion_fuente=("Yahoo Finance (TEF.MC, cierres diarios sin ajustar por dividendos ni "
                        "ampliaciones liberadas), cálculo de PivotAnalyzer"),
        leccion_periodo="06/03/2000; 24/07/2012; 09/02/2024",
        leccion_validada=False),
}

# Decisión 18, P-1 — «Cómo leerlo» por tramo (mismo orden que los tramos en criteria.json)
COMO_LEERLO = {
    "dist_sma200": [
        ("Estar muy por encima indica que el mercado viene revalorizando el valor, y también que el "
         "precio se ha alejado de su media; las correcciones hacia ella son habituales."),
        ("Estar por encima indica que el mercado viene revalorizando el valor en los últimos meses: la "
         "tendencia de largo plazo es alcista."),
        ("Estar por debajo indica que el precio lleva meses corrigiendo; la media actúa como referencia "
         "que el precio tendría que recuperar para volver a tendencia alcista."),
        ("Estar muy por debajo indica una tendencia bajista prolongada: el precio está lejos de su media "
         "y tendría que recuperar mucho terreno para volver a tendencia alcista."),
    ],
    "pos_52s": [
        ("En zona baja el mercado paga menos que en la mayor parte del año. Con el mismo dividendo, la "
         "rentabilidad por dividendo es mayor; conviene revisar por qué ha caído el precio."),
        ("En zona media el precio está cerca de lo habitual del último año: ni en la parte alta ni en "
         "la baja de su propio rango."),
        ("En zona alta el mercado paga más que en la mayor parte del año. Con el mismo dividendo, la "
         "rentabilidad por dividendo es menor."),
    ],
    "volatilidad": [
        "Volatilidad baja: el precio suele moverse poco. ",
        "Volatilidad moderada: oscilaciones habituales en un valor cotizado. ",
        "Volatilidad alta: el precio puede moverse con fuerza en pocas semanas. ",
        "Volatilidad muy alta: movimientos bruscos frecuentes. ",
    ],
}

FASE_EXTRA = {
    "min_indicadores": 4,
    "reparto_voto": "cada indicador reparte 1 voto entre las fases con las que coincide",
    "nota_subyacente_pp": 1.0,
    "nota_subyacente_texto": ("inflación impulsada sobre todo por la energía (general {general} · "
                              "subyacente {subyacente})"),
}


# Valores previos (tras migracion_pe_v1_json.py) para --revertir
PREV = {'Basic Materials': {'intensidad': 'media',
                     'leccion_historica': 'El superciclo de materias primas 2003-2008 impulsado por China '
                                          'multiplicó por 5 el precio del cobre. El colapso de 2015-2016 '
                                          'recordó que China puede frenar abruptamente. El nuevo superciclo '
                                          'de transición energética (cobre, litio) tiene fundamentos '
                                          'distintos pero riesgos similares de momento del ciclo.',
                     'motivo': 'los tipos altos frenan el crecimiento global y la demanda de materiales, y '
                               'suelen fortalecer el dólar, que encarece las materias primas',
                     'si_suben': 'perjudica'},
 'Communication Services': {'intensidad': 'media',
                            'leccion_historica': 'Telefónica en 2000 cotizaba a más de 20€ en plena euforia '
                                                 'puntocom. En 2012 llegó a 6€. En 2024 rondaba los 4€. 24 '
                                                 'años después de máximos, la acción no ha recuperado. '
                                                 'Ilustra cómo una empresa puede ser sólida operativamente '
                                                 'pero destruir valor para el accionista por exceso de deuda '
                                                 'y entorno competitivo difícil.',
                            'motivo': 'las telecos tienen mucha deuda y su dividendo compite con los bonos; '
                                      'las plataformas digitales se comportan como las tecnológicas',
                            'si_suben': 'perjudica'},
 'Consumer Cyclical': {'intensidad': 'media',
                       'leccion_historica': 'En España, el turismo supone ~12-13% del PIB. La pandemia de '
                                            '2020 destruyó el sector en semanas. IAG, Meliá y NH Hotels '
                                            'perdieron >60%. La recuperación de 2021-2023 fue igualmente '
                                            'violenta al alza. Volatilidad estructuralmente alta.',
                       'motivo': 'los tipos altos encarecen el crédito al consumo (hipotecas, tarjetas, '
                                 'coches) y recortan el gasto no esencial',
                       'si_suben': 'perjudica'},
 'Consumer Defensive': {'intensidad': 'baja',
                        'leccion_historica': 'En 2022 el consumo defensivo fue uno de los pocos sectores con '
                                             'retorno positivo mientras el S&P 500 caía un 18%. Inditex, sin '
                                             'ser estrictamente defensivo, demostró una capacidad '
                                             'extraordinaria de subir precios sin perder ventas durante la '
                                             'inflación 2021-2023.',
                        'motivo': 'la demanda se mantiene, pero tienen deuda y su dividendo compite con los '
                                  'bonos',
                        'si_suben': 'perjudica'},
 'Energy': {'intensidad': 'media',
            'leccion_historica': 'El desplome del petróleo a precios negativos en abril 2020 (-37$/barril) '
                                 'fue un evento histórico sin precedentes. En el otro extremo, el crudo a '
                                 '130$/barril en 2022 tras la invasión de Ucrania catapultó al sector '
                                 'energía como el único con retorno positivo ese año en el S&P 500.',
            'motivo': 'depende más del precio del petróleo, pero sus grandes inversiones se financian con '
                      'deuda',
            'si_suben': 'perjudica'},
 'Financial Services': {'intensidad': 'media',
                        'leccion_historica': 'Bankia 2012: riesgo de crédito oculto en activos inmobiliarios '
                                             'valorados a precio de burbuja. El rescate de 41.000M€ ilustra '
                                             'que el análisis del balance bancario requiere descuento '
                                             'agresivo de activos ilíquidos. El «haremos lo que sea '
                                             'necesario» de Draghi en julio 2012 fue la válvula.',
                        'motivo': 'en la banca comercial, los tipos más altos amplían el margen entre lo que '
                                  'cobra por préstamos y lo que paga por depósitos; tipos muy altos durante '
                                  'mucho tiempo elevan los impagos. En aseguradoras y gestoras el efecto es '
                                  'mixto',
                        'si_suben': 'favorece'},
 'Healthcare': {'intensidad': 'baja',
                'leccion_historica': 'Durante la recesión de 2008-2009 el sector healthcare cayó solo un 23% '
                                     'frente al -57% del S&P 500. En COVID (marzo 2020) fue de los primeros '
                                     'en recuperarse. Su rol como refugio está bien documentado '
                                     'históricamente.',
                'motivo': 'su demanda no depende del ciclo, pero las biotecnológicas sin beneficios se '
                          'valoran peor con tipos altos',
                'si_suben': 'perjudica'},
 'Industrials': {'intensidad': 'media',
                 'leccion_historica': 'Los PMI manufactureros cayeron por debajo de 50 en agosto 2019 '
                                      'anticipando desaceleración. El sector industrial europeo (con mucho '
                                      'peso en el DAX) lo reflejó con corrección del 15-20% antes de que los '
                                      'datos macroeconómicos se deterioraran. El PMI como adelantado '
                                      'funcionó.',
                 'motivo': 'financian proyectos largos con deuda; si la subida acompaña a una economía '
                           'fuerte, la demanda puede compensarlo',
                 'si_suben': 'perjudica'},
 'Real Estate': {'intensidad': 'alta',
                 'leccion_historica': 'En 2022-2023 las SOCIMIs españolas (Merlin, Colonial) cayeron 30-40% '
                                      'pese a resultados operativos sólidos. El motivo fue exclusivamente la '
                                      'subida de tipos. Ejemplo perfecto de cómo el contexto macro puede '
                                      'superar cualquier análisis fundamental del activo individual.',
                 'motivo': 'tienen mucha deuda, su dividendo compite con los bonos y el valor de los '
                           'inmuebles baja cuando suben los tipos',
                 'si_suben': 'perjudica'},
 'Technology': {'intensidad': 'media',
                'leccion_historica': 'En 2000-2002 el Nasdaq cayó un 78%. En 2022 un 33%. En ambos casos el '
                                     'detonante fue la subida de tipos combinada con múltiplos '
                                     'insostenibles. La diferencia: en 2022 las grandes tech tenían '
                                     'beneficios reales.',
                'motivo': 'su valor depende de beneficios lejanos en el tiempo, y con tipos más altos esos '
                          'beneficios futuros valen menos hoy',
                'si_suben': 'perjudica'},
 'Utilities': {'intensidad': 'alta',
               'leccion_historica': 'En el ciclo de subidas de tipos 2022-2023, Iberdrola cayó ~25% desde '
                                    'máximos pese a resultados récord, puramente por la presión de tipos '
                                    'sobre la valoración. Fue el ejemplo perfecto del doble impacto sobre '
                                    'utilities: mayor coste de deuda + menor atractivo del dividendo frente '
                                    'al bono.',
               'motivo': 'tienen mucha deuda (subidas de tipos encarecen la financiación) y su dividendo '
                         'compite con los bonos (si los bonos pagan más, el dividendo pierde atractivo)',
               'si_suben': 'perjudica'}}


def _leer(n):
    with open(DIR / n, encoding="utf-8") as f:
        return json.load(f)


def _escribir(n, d):
    with open(DIR / n, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    cambios = []
    s = _leer("sector_knowledge.json"); sec = s["sectores"]
    for k, (i, su, mot) in TIPOS.items():
        st_ = sec[k]["sensibilidad_tipos"]
        st_["intensidad"], st_["si_suben"] = i, su
        if mot:
            st_["motivo"] = mot
        st_["rotulo"] = ROTULO_TIPOS
    sec["Financial Services"]["sensibilidad_tipos"]["subtipos"] = SUBTIPOS_FIN
    for k, campos in LECCIONES.items():
        for kk, vv in campos.items():
            if vv is None:
                sec[k].pop(kk, None)
            else:
                sec[k][kk] = vv
    _escribir("sector_knowledge.json", s); cambios.append("sector_knowledge.json")
    c = _leer("criteria.json"); t = c["contexto_macro_tramos"]
    for blk, textos in COMO_LEERLO.items():
        for tr, tx in zip(t[blk]["tramos"], textos):
            tr["como_leerlo"] = tx
    _escribir("criteria.json", c); cambios.append("criteria.json")
    m = _leer("macro_indicators.json")
    m["fase_ciclo_metodo"].update(FASE_EXTRA)
    _escribir("macro_indicators.json", m); cambios.append("macro_indicators.json")
    return cambios


def revertir():
    s = _leer("sector_knowledge.json"); sec = s["sectores"]
    for k, p in PREV.items():
        st_ = sec[k]["sensibilidad_tipos"]
        for kk in ("intensidad", "si_suben", "motivo"):
            if p.get(kk) is not None:
                st_[kk] = p[kk]
        st_.pop("rotulo", None); st_.pop("subtipos", None)
        sec[k]["leccion_historica"] = p["leccion_historica"]
        for kk in ("leccion_cualitativa", "leccion_fuente", "leccion_periodo", "leccion_validada"):
            sec[k].pop(kk, None)
    _escribir("sector_knowledge.json", s)
    c = _leer("criteria.json")
    for blk in COMO_LEERLO:
        for tr in c["contexto_macro_tramos"][blk]["tramos"]:
            tr.pop("como_leerlo", None)
    _escribir("criteria.json", c)
    m = _leer("macro_indicators.json")
    for kk in FASE_EXTRA:
        m["fase_ciclo_metodo"].pop(kk, None)
    _escribir("macro_indicators.json", m)
    return ["sector_knowledge.json", "criteria.json", "macro_indicators.json"]


if __name__ == "__main__":
    if "contexto_macro_tramos" not in _leer("criteria.json"):
        sys.exit("Primero hay que aplicar migracion_pe_v1_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
