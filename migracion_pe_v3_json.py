"""Spec PE v3 (Paso 2) + validación 21 de Pólaris (cierre PE v2). Migración de JSON, aditiva y reversible.

Requiere las migraciones pe_v1, pe_v1b y pe_v2 aplicadas.
  criteria.json          + "diagnostico_paso2": cortes y rótulos de la nota global, «qué es» de cada
                           componente y «cómo leerlo» por tramo (PE-11, PE-12, PE-13).
  sector_knowledge.json  · Energy: efecto_ciclo (+1, +1, −2, +1) y textos de pico, contracción y
                           recuperación (validación 21 §3).
                         · Financial Services y Communication Services: "subtipos_ciclo" por industry de
                           Yahoo, cada fila con su texto y su efecto (validación 21 §2).
                         · Textos sin cifras sin fuente (validación 21, C-2).

Uso:  python migracion_pe_v3_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
FASES = ("expansion", "pico", "contraccion", "recuperacion")

DIAG = {
    "_descripcion": ("Spec PE v3 (Paso 2). Cortes de la nota global del Diagnóstico Técnico (los usa el "
                     "motor) y textos didácticos por componente y tramo. Las notas de cada tramo están "
                     "en el código (_PUNTUACIONES_*), tal como puntúa el motor."),
    "cortes": {
        "alcista": 6.5, "bajista": 3.5,
        "rotulos": {"alcista": "Estructura alcista: la mayoría de componentes apoyan la tendencia.",
                    "mixta": "Estructura mixta: los componentes no coinciden.",
                    "bajista": "Estructura bajista: la mayoría de componentes señalan debilidad."},
    },
    "que_es": {
        "ath": "La distancia entre el precio y el máximo más alto que ha marcado el valor en toda su historia.",
        "sma200": ("La pendiente de la media de los últimos 200 cierres: si la media sube, baja o está plana, y "
                   "si ha cambiado de dirección en las últimas semanas."),
        "resist": ("Dónde está el precio respecto a los niveles reforzados más cercanos: puntos pivote que "
                   "coinciden con una media móvil, y que el análisis técnico usa como soportes y resistencias."),
        "fibo": ("Cuánto ha retrocedido el precio desde el máximo del último año, medido como porcentaje del "
                 "recorrido entre el mínimo y el máximo de ese periodo."),
        "rsi": ("El índice de fuerza relativa de 14 sesiones diarias: compara la magnitud de las subidas y de las "
                "bajadas recientes en una escala de 0 a 100."),
        "vol": ("El volumen negociado en las últimas 5 sesiones completas frente a su media de 20, y el reparto "
                "del volumen entre días de subida y de bajada en las últimas 10 sesiones."),
    },
    "como_leerlo": {
        "ath": {
            "subida_libre_establecida": "El precio está por encima de cualquier nivel alcanzado antes: no hay máximos previos por encima que sirvan de referencia.",
            "en_ath": "El precio está prácticamente en su máximo histórico, en la parte más alta de su historia.",
            "aproximandose_cerca": "Estar cerca del máximo histórico indica que el precio está en la parte alta de su historia.",
            "aproximandose": "El precio está algo por debajo de su máximo histórico: cerca de la parte alta de su historia, pero sin alcanzarla.",
            "referencia": "Estar lejos indica que el precio todavía está por debajo de niveles ya alcanzados; el máximo queda como referencia lejana.",
            "lejos": "El precio está muy por debajo de su máximo histórico: niveles ya alcanzados en el pasado quedan muy lejos.",
        },
        "sma200": {
            "giro_alcista_reciente": "La media de largo plazo ha empezado a subir hace poco, después de bajar: el método lo interpreta como un posible cambio de tendencia al alza.",
            "tendencia_alcista": "La media de largo plazo sube de forma sostenida: el método lo interpreta como tendencia alcista de fondo.",
            "plana": "La media de largo plazo apenas se mueve: el método no ve tendencia de fondo clara.",
            "giro_bajista_reciente": "La media de largo plazo ha empezado a bajar hace poco, después de subir: el método lo interpreta como un posible cambio de tendencia a la baja.",
            "tendencia_bajista": "La media de largo plazo baja de forma sostenida: el método lo interpreta como tendencia bajista de fondo.",
        },
        "resist": {
            "en_soporte": "El precio está apoyado sobre un nivel reforzado: el análisis técnico lo toma como zona donde la caída se ha frenado otras veces.",
            "sin_resistencia": "No hay niveles reforzados por encima del precio: el análisis técnico no ve techos cercanos en los niveles calculados.",
            "zona_baja_rango": "El precio está más cerca del soporte que de la resistencia: tiene más margen hasta el techo que hasta el suelo.",
            "zona_media_rango": "El precio está a media distancia entre el soporte y la resistencia más cercanos.",
            "zona_alta_rango": "El precio está más cerca de la resistencia que del soporte: tiene poco margen hasta el techo cercano.",
            "en_resistencia": "El precio está justo debajo de un nivel reforzado: el análisis técnico lo toma como zona donde las subidas se han frenado otras veces.",
            "sin_soporte": "No hay niveles reforzados por debajo del precio: el análisis técnico no ve suelos cercanos en los niveles calculados.",
        },
        "fibo": {
            "extension_161": "El precio ha superado con amplitud el máximo del swing: los niveles de extensión son la única referencia por encima.",
            "extension_127": "El precio ha superado el máximo del swing y se mueve en zona de extensión.",
            "en_maximo": "El precio está en la parte alta del recorrido del último año, con un retroceso pequeño desde el máximo.",
            "retroceso_236": "El precio ha corregido poco desde el máximo del año. Los retrocesos del 38,2%, 50% y 61,8% son los que más usan los analistas técnicos como referencia.",
            "retroceso_382": "El precio ha devuelto una parte moderada de la subida del año. Los retrocesos del 38,2%, 50% y 61,8% son los que más usan los analistas técnicos como referencia.",
            "retroceso_618": "El precio ha devuelto cerca de la mitad o más de la subida del año. El método puntúa esta zona al alza porque el análisis técnico la usa como posible zona de rebote.",
            "retroceso_786": "El precio ha devuelto la mayor parte de la subida del año: el recorrido alcista se ha debilitado mucho.",
            "swing_roto": "El precio está cerca del mínimo del año o por debajo: el recorrido alcista del swing se ha perdido.",
        },
        "rsi": {
            "sobrecompra_extrema": "El RSI está en niveles muy altos: el método lo interpreta como subida muy extendida en poco tiempo.",
            "sobrecompra": "El RSI está en sobrecompra: el método lo interpreta como subida extendida, en la que las correcciones son habituales.",
            "zona_alcista": "El RSI está en la banda alcista: las subidas recientes pesan más que las bajadas, sin llegar a extremos.",
            "zona_neutra": "El RSI está en la banda neutra: subidas y bajadas recientes están equilibradas.",
            "zona_bajista": "El RSI está en la banda bajista: las bajadas recientes pesan más que las subidas.",
            "sobreventa": "El RSI está en sobreventa: el método lo interpreta como caída extendida, tras la que los rebotes son habituales.",
            "sobreventa_extrema": "El RSI está en niveles muy bajos: el método lo interpreta como caída muy extendida en poco tiempo.",
        },
        "vol": {
            "volumen_excepcional": "Se negocia el doble o más de lo habitual: el método lo interpreta como un movimiento con mucha participación.",
            "volumen_alto": "Se negocia claramente más de lo habitual. Cuando las subidas vienen con más volumen que las bajadas, el método lo interpreta como mayor participación compradora.",
            "volumen_normal": "Se negocia un volumen en línea con lo habitual: el volumen no añade información a la tendencia.",
            "volumen_bajo": "Se negocia menos de lo habitual: el método da menos peso a los movimientos con poca participación.",
            "volumen_seco": "Se negocia muy poco: los movimientos con tan poca participación tienen poca significación para el método.",
        },
    },
}

ENERGY_CICLO = {"pico": "favorable — precios de la energía y de las materias primas suelen estar altos al final del ciclo",
                "contraccion": "muy negativo — la demanda y el precio del crudo caen con la actividad",
                "recuperacion": "favorable — la demanda se recupera con la actividad"}
ENERGY_EFECTO = {"expansion": 1, "pico": 1, "contraccion": -2, "recuperacion": 1}

SUB_FIN = {
    "banca": {"nombre": "banca", "por_defecto": True,
              "industrias_yahoo": ["Banks - Diversified", "Banks - Regional", "Credit Services", "Mortgage Finance"],
              "comportamiento_ciclo": {"expansion": "favorable — crecimiento del crédito y bajas provisiones",
                                       "pico": "muy favorable si los tipos suben — máximo margen de intereses; vigilar la calidad del crédito",
                                       "contraccion": "muy negativo — la morosidad dispara las provisiones",
                                       "recuperacion": "favorable — las provisiones se reducen y mejora la calidad de los activos"},
              "efecto_ciclo": {"expansion": 1, "pico": 2, "contraccion": -2, "recuperacion": 1}},
    "seguros": {"nombre": "seguros",
                "industrias_yahoo": ["Insurance - Diversified", "Insurance - Life", "Insurance - Property & Casualty",
                                     "Insurance - Reinsurance", "Insurance - Specialty", "Insurance Brokers"],
                "comportamiento_ciclo": {"expansion": "favorable — las primas crecen con la actividad",
                                         "pico": "favorable — reinvierten su renta fija a mayor rentabilidad",
                                         "contraccion": "negativo — caen las primas y el valor de sus inversiones",
                                         "recuperacion": "favorable — se recuperan la actividad y las primas"},
                "efecto_ciclo": {"expansion": 1, "pico": 1, "contraccion": -1, "recuperacion": 1}},
    "gestoras": {"nombre": "gestoras de activos",
                 "industrias_yahoo": ["Asset Management", "Capital Markets"],
                 "comportamiento_ciclo": {"expansion": "muy favorable — suben los activos gestionados y las comisiones",
                                          "pico": "neutral — los mercados pierden impulso",
                                          "contraccion": "muy negativo — caen los activos gestionados y los partícipes retiran dinero",
                                          "recuperacion": "muy favorable — los mercados se recuperan y vuelven las suscripciones"},
                 "efecto_ciclo": {"expansion": 2, "pico": 0, "contraccion": -2, "recuperacion": 2}},
}
SUB_COM = {
    "telecos": {"nombre": "telecos", "por_defecto": True, "industrias_yahoo": ["Telecom Services"],
                "comportamiento_ciclo": {"expansion": "neutral — ingresos estables, poco ligados al ciclo",
                                         "pico": "neutral — la deuda pesa más con tipos altos, pero los ingresos aguantan",
                                         "contraccion": "favorable — refugio relativo por sus ingresos recurrentes",
                                         "recuperacion": "neutral — otros sectores lideran la recuperación"},
                "efecto_ciclo": {"expansion": 0, "pico": 0, "contraccion": 1, "recuperacion": 0}},
    "plataformas": {"nombre": "plataformas digitales",
                    "industrias_yahoo": ["Internet Content & Information", "Entertainment"],
                    "comportamiento_ciclo": {"expansion": "favorable — crece la inversión en publicidad",
                                             "pico": "negativo — con tipos altos se valoran peor sus beneficios futuros",
                                             "contraccion": "neutral — cae la publicidad, pero su modelo de negocio resiste",
                                             "recuperacion": "favorable — la publicidad se recupera pronto"},
                    "efecto_ciclo": {"expansion": 1, "pico": -1, "contraccion": 0, "recuperacion": 1}},
}

# C-2 — (sector, ruta, antiguo, nuevo)
TEXTOS = [
    ("Financial Services", "descripcion", "En España representa >30% del IBEX 35.",
     "En España es el sector con más peso del IBEX 35."),
    ("Technology", "riesgos_especificos", "Concentración: las 5 mayores empresas representan >25% del S&P 500",
     "Concentración: unas pocas grandes empresas pesan mucho en los índices, como el S&P 500"),
    ("Utilities", "sensibilidad_tipos.explicacion",
     "(si el bono paga 4%, la utility a 4% de dividendo pierde atractivo)",
     "(por ejemplo, si el bono paga lo mismo que el dividendo, el dividendo pierde atractivo)"),
    ("Real Estate", "descripcion", "obligación de distribución de dividendos >80% del beneficio distribuible",
     "obligación legal de repartir como dividendo la mayor parte de su beneficio"),
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
    if isinstance(v, list):
        obj[partes[-1]] = [x.replace(old, new) for x in v]
    else:
        obj[partes[-1]] = v.replace(old, new)


def aplicar():
    c = _leer("criteria.json"); c["diagnostico_paso2"] = DIAG; _escribir("criteria.json", c)
    s = _leer("sector_knowledge.json"); sec = s["sectores"]
    e = sec["Energy"]
    e.setdefault("_pe_v3_prev", {"comportamiento_ciclo": dict(e["comportamiento_ciclo"]),
                                 "efecto_ciclo": dict(e["efecto_ciclo"])})
    e["comportamiento_ciclo"].update(ENERGY_CICLO); e["efecto_ciclo"] = dict(ENERGY_EFECTO)
    sec["Financial Services"]["subtipos_ciclo"] = SUB_FIN
    sec["Communication Services"]["subtipos_ciclo"] = SUB_COM
    for k, ruta, old, new in TEXTOS:
        _sust(sec[k], ruta, old, new)
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


def revertir():
    c = _leer("criteria.json"); c.pop("diagnostico_paso2", None); _escribir("criteria.json", c)
    s = _leer("sector_knowledge.json"); sec = s["sectores"]
    e = sec["Energy"]
    prev = e.pop("_pe_v3_prev", None)
    if prev:
        e["comportamiento_ciclo"] = prev["comportamiento_ciclo"]; e["efecto_ciclo"] = prev["efecto_ciclo"]
    sec["Financial Services"].pop("subtipos_ciclo", None)
    sec["Communication Services"].pop("subtipos_ciclo", None)
    for k, ruta, old, new in TEXTOS:
        _sust(sec[k], ruta, new, old)
    _escribir("sector_knowledge.json", s)
    return ["criteria.json", "sector_knowledge.json"]


if __name__ == "__main__":
    if "conclusiones_paso1" not in _leer("criteria.json"):
        sys.exit("Primero hay que aplicar migracion_pe_v2_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
