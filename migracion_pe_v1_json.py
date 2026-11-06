"""Spec PE v1 — Migración de los JSON de conocimiento («¿Por dónde empiezo?», Paso 1).

Cambios ADITIVOS y reversibles (no se borra ningún campo existente):
  criteria.json          + clave "contexto_macro_tramos" (PE-02, tramos de referencia del método)
  macro_indicators.json  + clave "fase_ciclo_metodo"     (PE-05, umbrales de la fase del ciclo)
  glosario.json          + campos "en_linea"/"variantes" y términos nuevos (PE-04)
  sector_knowledge.json  sensibilidad_tipos: + intensidad(alta|media|baja), si_suben, motivo (PE-03);
                         el antiguo "intensidad" se conserva como "intensidad_v1";
                         "direccion" y "explicacion" se conservan;
                         sustituciones de términos en inglés en textos del Paso 1 (PE-04).

Uso:
    python migracion_pe_v1_json.py            # aplica (idempotente: repetirla no cambia nada)
    python migracion_pe_v1_json.py --revertir # deshace exactamente lo que añade/sustituye
    python migracion_pe_v1_json.py --comprobar # solo informa del estado
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────────
# PE-02 — Tramos de referencia del método (criteria.json)
# ─────────────────────────────────────────────────────────────────────────────
TRAMOS = {
    "_descripcion": ("Spec PE v1 (PE-02). Tramos de referencia del método para el Paso 1 de "
                     "«¿Por dónde empiezo?». Son parámetros del método, no una norma de mercado. "
                     "Convención: desde ≤ valor < hasta (el último tramo incluye su 'hasta')."),
    "rotulo": "Tramos de referencia del método",
    "dist_sma200": {
        "titulo": "Tendencia frente a la SMA200",
        "columna": "Distancia a la SMA200",
        "que_es": ("La SMA200 es la media de los últimos 200 cierres diarios, unos 10 meses de "
                   "cotización. Es la referencia de tendencia de largo plazo más usada."),
        "como_leerlo": ("Estar por encima indica que el mercado viene revalorizando el valor. Estar "
                        "muy por encima también significa que el precio se ha alejado de su media, "
                        "y las correcciones hacia ella son habituales."),
        "tramos": [
            {"desde": 10, "hasta": None, "rango": "Más de +10%", "etiqueta": "Muy por encima",
             "lectura": "Muy por encima: tendencia alcista y precio alejado de su media"},
            {"desde": 0, "hasta": 10, "rango": "De 0% a +10%", "etiqueta": "Por encima",
             "lectura": "Por encima: tendencia alcista"},
            {"desde": -10, "hasta": 0, "rango": "De −10% a 0%", "etiqueta": "Por debajo",
             "lectura": "Por debajo: tendencia débil o en corrección"},
            {"desde": None, "hasta": -10, "rango": "Menos de −10%", "etiqueta": "Muy por debajo",
             "lectura": "Muy por debajo: tendencia bajista"}
        ]
    },
    "pos_52s": {
        "titulo": "Posición en el rango de 52 semanas",
        "columna": "Posición",
        "que_es": "Dónde está el precio entre el mínimo (0%) y el máximo (100%) del último año.",
        "como_leerlo": ("En zona alta el mercado paga más que en la mayor parte del año. Con el "
                        "mismo dividendo, la rentabilidad por dividendo es menor."),
        "nota": "Los mismos tramos que usa el informe de estrategia de Dividendos.",
        "tramos": [
            {"desde": 0, "hasta": 35, "rango": "0% – 35%", "etiqueta": "Zona baja del año",
             "lectura": "Zona baja del año"},
            {"desde": 35, "hasta": 60, "rango": "35% – 60%", "etiqueta": "Zona media",
             "lectura": "Zona media"},
            {"desde": 60, "hasta": 100, "rango": "60% – 100%", "etiqueta": "Zona alta del año",
             "lectura": "Zona alta del año"}
        ]
    },
    "volatilidad": {
        "titulo": "Volatilidad histórica anualizada",
        "columna": "Volatilidad anualizada",
        "que_es": ("Cuánto suele oscilar el precio en un año, medido con las variaciones diarias "
                   "pasadas."),
        "como_leerlo": ("Una volatilidad del {vol} significa que, si las oscilaciones se "
                        "comportasen como en el pasado, en aproximadamente dos de cada tres años el "
                        "precio acabaría dentro de un ±{vol} respecto al inicio. Es una aproximación "
                        "estadística basada en datos pasados, no una previsión."),
        "nota": ("Alta volatilidad = tamaño de posición más pequeño para el mismo riesgo real: con "
                 "el doble de volatilidad, la misma cantidad invertida oscila el doble en euros."),
        "tramos": [
            {"desde": None, "hasta": 15, "rango": "Menos de 15%", "etiqueta": "Baja",
             "lectura": "Baja"},
            {"desde": 15, "hasta": 25, "rango": "15% – 25%", "etiqueta": "Moderada",
             "lectura": "Moderada"},
            {"desde": 25, "hasta": 40, "rango": "25% – 40%", "etiqueta": "Alta",
             "lectura": "Alta"},
            {"desde": 40, "hasta": None, "rango": "Más de 40%", "etiqueta": "Muy alta",
             "lectura": "Muy alta"}
        ]
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# PE-05 — Parámetros de la fase del ciclo (macro_indicators.json)
# ─────────────────────────────────────────────────────────────────────────────
FASE_CICLO = {
    "_descripcion": ("Spec PE v1 (PE-05). Regla del método para la fase actual del ciclo. Cada "
                     "indicador se lee en su dirección de los últimos 'ventana_meses'. Asignación: "
                     "la fase con más indicadores coincidentes; empate o diferencia de "
                     "'diferencia_transicion' o menos → «Transición entre X e Y»."),
    "ventana_meses": 6,
    "ventana_extremos_meses": 24,
    "diferencia_transicion": 1,
    "max_antiguedad_meses": {"trimestral": 7, "mensual": 4, "diaria": 1},
    "pib": {"estable_pp": 0.3, "desaceleracion_fuerte_pp": 1.0, "bajo_pct": 1.0},
    "inflacion": {"objetivo_pct": 2.0, "banda_cerca_pp": 0.5, "estable_pp": 0.2},
    "tipo_oficial": {"estable_pb": 25, "tolerancia_extremo_pb": 10},
    "curva": {"estable_pp": 0.15},
    "paro": {"estable_pp": 0.2, "tolerancia_minimo_pp": 0.2},
    "nota_fija": "Lectura orientativa: las fases del ciclo solo se confirman con certeza a posteriori."
}

# ─────────────────────────────────────────────────────────────────────────────
# PE-04 — Explicaciones en línea (glosario.json). Los 6 primeros textos son los de la spec.
# clave: (nombre, en_linea, [variantes])  — variantes: formas que se buscan en el texto.
# ─────────────────────────────────────────────────────────────────────────────
TERMINOS_NUEVOS = {
    "proxy_de_bono": ("Proxy de bono",
        "valor que se comporta como un bono: se compra sobre todo por su renta estable, por lo que "
        "su precio tiende a subir cuando bajan los tipos y a bajar cuando suben", ["proxy de bono"]),
    "semirregulados": ("Ingresos semirregulados",
        "parte de sus ingresos los fija un regulador y otra parte depende del mercado",
        ["semirregulados"]),
    "ciclicos": ("Sectores cíclicos",
        "sectores cuyas ventas y beneficios suben y bajan con la economía: construcción, materias "
        "primas, automóvil, ocio…", ["cíclicos"]),
    "rotacion_defensiva": ("Rotación defensiva",
        "cuando los inversores pasan dinero de sectores cíclicos a sectores estables ante un "
        "posible frenazo económico", ["rotación defensiva"]),
    "compresion_spread": ("Compresión de spread",
        "reducción de la diferencia de rentabilidad respecto a la deuda pública; en la práctica, "
        "la financiación del sector se abarata", ["compresión de spread"]),
    "demanda_inelastica": ("Demanda inelástica",
        "el consumo apenas baja aunque suban los precios o empeore la economía, como la luz o el "
        "agua", ["demanda de electricidad inelástica", "demanda inelástica"]),
    "defensivos": ("Sectores defensivos",
        "sectores cuya demanda apenas depende de la marcha de la economía: alimentación, sanidad, "
        "servicios públicos…", ["defensivos", "defensivo"]),
    "multiplos": ("Múltiplos de valoración",
        "veces que el precio contiene el beneficio u otra magnitud de la empresa, como el PER",
        ["expansión de múltiplos", "compresión de múltiplos", "múltiplos"]),
    "compresion_valoracion": ("Compresión de valoración",
        "el mercado pasa a pagar menos por cada euro de beneficio", ["compresión de valoración"]),
    "PMI": ("Índice de gestores de compras",
        "encuesta mensual a directivos de compras: por encima de 50 indica que la actividad crece "
        "y por debajo de 50, que se contrae", ["PMI manufactureros", "PMI"]),
    "SOCIMI": ("SOCIMI",
        "sociedad cotizada de inversión inmobiliaria, obligada a repartir la mayor parte de su "
        "beneficio", ["SOCIMIs", "SOCIMI"]),
    "REIT": ("REIT",
        "equivalente estadounidense de las SOCIMI", ["REITs", "REIT"]),
    "tasa_capitalizacion": ("Tasa de capitalización",
        "renta anual de un inmueble dividida por su valor; si sube, el valor del inmueble baja",
        ["tasa de capitalización"]),
    "vacancia": ("Vacancia", "porcentaje de superficie o inmuebles sin alquilar", ["vacancia"]),
    "morosidad": ("Morosidad", "préstamos que los clientes dejan de pagar", ["morosidad"]),
    "provisiones": ("Provisiones",
        "dinero que el banco aparta para cubrir las pérdidas esperadas por impagos",
        ["provisiones"]),
    "curva_empinada": ("Curva empinada",
        "gran diferencia entre los tipos de interés a largo plazo y los de corto plazo",
        ["curva empinada"]),
    "efecto_riqueza": ("Efecto riqueza",
        "las familias gastan menos cuando baja el valor de sus ahorros e inversiones",
        ["efecto riqueza"]),
    "consumo_discrecional": ("Consumo discrecional",
        "gasto en bienes y servicios no esenciales", ["consumo discrecional"]),
    "palanca_operativa": ("Palanca operativa",
        "peso alto de los costes fijos: pequeñas variaciones de ventas mueven mucho el beneficio",
        ["palanca operativa"]),
    "activos_varados": ("Activos varados",
        "activos que pierden su valor antes de tiempo, por ejemplo por la transición energética",
        ["activos varados"]),
    "OPEP": ("OPEP+", "cártel de países productores de petróleo y sus aliados, como Rusia",
        ["OPEP+"]),
    "FDA_EMA": ("FDA / EMA", "agencias del medicamento de EE. UU. y de la Unión Europea",
        ["FDA/EMA"]),
    "Basilea": ("Basilea IV", "normas internacionales de capital mínimo para los bancos",
        ["Basilea IV"]),
    "ESG": ("ESG", "criterios ambientales, sociales y de buen gobierno", ["ESG"]),
    "CNMC": ("CNMC", "Comisión Nacional de los Mercados y la Competencia, el regulador español",
        ["CNMC"]),
    "SP500": ("S&P 500", "índice de las 500 mayores empresas cotizadas de EE. UU.",
        ["S&P 500"]),
    "Nasdaq": ("Nasdaq", "índice de la bolsa tecnológica de EE. UU.", ["Nasdaq"]),
    "DAX": ("DAX", "índice de las 40 mayores empresas alemanas", ["DAX"]),
    "superciclo": ("Superciclo de materias primas",
        "periodo largo, de varios años, de precios altos de las materias primas",
        ["superciclo"]),
    "intermitencia_renovable": ("Intermitencia renovable",
        "la producción solar y eólica depende del tiempo y no es constante",
        ["intermitencia renovable"]),
    "retribucion_regulada": ("Retribución regulada",
        "ingresos que fija el regulador por la actividad regulada (redes, distribución)",
        ["retribución regulada"]),
    "puntocom": ("Burbuja puntocom",
        "subida y desplome de las empresas de internet entre 1999 y 2002", ["puntocom"]),
}
# Términos que ya existen en glosario.json: solo se les añade en_linea y variantes.
EN_LINEA_EXISTENTES = {
    "capex": ("inversión en activos fijos: plantas, maquinaria, redes", ["capex"]),
    "NIM": ("margen de intereses: diferencia entre lo que el banco cobra por los préstamos y lo "
            "que paga por los depósitos", ["NIM"]),
    "FCF": ("flujo de caja libre: la caja que queda tras pagar la operativa y las inversiones",
            ["FCF"]),
    "DMA": ("leyes europeas de mercados y de servicios digitales", ["DMA/DSA"]),
}

# ─────────────────────────────────────────────────────────────────────────────
# PE-03 — Sensibilidad a tipos. Conversión de la spec + motivo breve (Pólaris valida la tabla).
# direccion original → (intensidad, si_suben)
#   muy negativa → alta+perjudica · negativa → media+perjudica · neutra → baja+neutro
#   positiva → media+favorece · muy positiva → alta+favorece
#   Valores no previstos en la spec (revisados por FABER-PA, pendientes de Pólaris):
#   "negativa moderada" → media+perjudica · "neutral-negativa leve" → baja+perjudica
#   "positiva (banca comercial) / mixta (...)" → media+favorece (motivo indica la excepción)
# ─────────────────────────────────────────────────────────────────────────────
SENSIBILIDAD = {
    "Technology": ("media", "perjudica",
        "su valor depende de beneficios lejanos en el tiempo, y con tipos más altos esos "
        "beneficios futuros valen menos hoy"),
    "Financial Services": ("media", "favorece",
        "en la banca comercial, los tipos más altos amplían el margen entre lo que cobra por "
        "préstamos y lo que paga por depósitos; tipos muy altos durante mucho tiempo elevan los "
        "impagos. En aseguradoras y gestoras el efecto es mixto"),
    "Healthcare": ("baja", "perjudica",
        "su demanda no depende del ciclo, pero las biotecnológicas sin beneficios se valoran peor "
        "con tipos altos"),
    "Consumer Cyclical": ("media", "perjudica",
        "los tipos altos encarecen el crédito al consumo (hipotecas, tarjetas, coches) y recortan "
        "el gasto no esencial"),
    "Consumer Defensive": ("baja", "perjudica",
        "la demanda se mantiene, pero tienen deuda y su dividendo compite con los bonos"),
    "Energy": ("media", "perjudica",
        "depende más del precio del petróleo, pero sus grandes inversiones se financian con deuda"),
    "Utilities": ("alta", "perjudica",
        "tienen mucha deuda (subidas de tipos encarecen la financiación) y su dividendo compite "
        "con los bonos (si los bonos pagan más, el dividendo pierde atractivo)"),
    "Industrials": ("media", "perjudica",
        "financian proyectos largos con deuda; si la subida acompaña a una economía fuerte, la "
        "demanda puede compensarlo"),
    "Basic Materials": ("media", "perjudica",
        "los tipos altos frenan el crecimiento global y la demanda de materiales, y suelen "
        "fortalecer el dólar, que encarece las materias primas"),
    "Real Estate": ("alta", "perjudica",
        "tienen mucha deuda, su dividendo compite con los bonos y el valor de los inmuebles baja "
        "cuando suben los tipos"),
    "Communication Services": ("media", "perjudica",
        "las telecos tienen mucha deuda y su dividendo compite con los bonos; las plataformas "
        "digitales se comportan como las tecnológicas"),
}

# PE-04 — Sustituciones de términos en inglés en los textos del Paso 1 (old → new, por sector).
SUSTITUCIONES = [
    ("Technology", "comportamiento_ciclo.expansion", "expansión de múltiplos", "expansión de múltiplos"),
    ("Technology", "riesgos_especificos", "Concentración: top-5 empresas representan >25% del S&P 500",
     "Concentración: las 5 mayores empresas representan >25% del S&P 500"),
    ("Technology", "sensibilidad_tipos.explicacion", "La relación inversa tipos↑ = tech↓",
     "La relación inversa tipos↑ = tecnológicas↓"),
    ("Financial Services", "riesgos_especificos", "Disrupción fintech en márgenes de comisiones",
     "Competencia de las empresas tecnológicas financieras en los márgenes de comisiones"),
    ("Financial Services", "leccion_historica",
     "OCR (on-balance sheet credit risk) oculto en activos", "riesgo de crédito oculto en activos"),
    ("Financial Services", "leccion_historica", "El 'whatever it takes' de Draghi",
     "El «haremos lo que sea necesario» de Draghi"),
    ("Healthcare", "comportamiento_ciclo.expansion",
     "neutral — underperforms en expansión frente a cíclicos",
     "neutral — rendimiento inferior en expansión frente a cíclicos"),
    ("Healthcare", "comportamiento_ciclo.contraccion",
     "refugio clásico; outperformance consistente", "refugio clásico; rendimiento superior consistente"),
    ("Healthcare", "sensibilidad_tipos.explicacion",
     "el subsector biotech (sin beneficios) sufre compresión de múltiplos similar a tech growth",
     "el subsector de biotecnología (sin beneficios) sufre compresión de múltiplos similar a las tecnológicas de crecimiento"),
    ("Healthcare", "riesgos_especificos",
     "Expiración de patentes ('patent cliff') con entrada de genéricos",
     "Expiración de patentes con entrada de genéricos"),
    ("Healthcare", "riesgos_especificos", "pérdida de valor repentina en biotech",
     "pérdida de valor repentina en biotecnología"),
    ("Consumer Cyclical", "riesgos_especificos", "Disrupción del e-commerce sobre retail tradicional",
     "Competencia del comercio electrónico sobre el comercio tradicional"),
    ("Consumer Cyclical", "descripcion", "lujo y retail no esencial", "lujo y comercio minorista no esencial"),
    ("Utilities", "riesgos_especificos", "Cambio en mix de generación", "Cambio en la combinación de fuentes de generación"),
    ("Consumer Cyclical", "riesgos_especificos", "Alta palanca operativa en retail",
     "Alta palanca operativa en el comercio minorista"),
    ("Consumer Defensive", "descripcion", "Underperformer en expansión, refugio en contracción.",
     "Rendimiento inferior en expansión, refugio en contracción."),
    ("Consumer Defensive", "comportamiento_ciclo.expansion",
     "negativo relativo — underperformance frente a cíclicos",
     "negativo relativo — rendimiento inferior frente a cíclicos"),
    ("Consumer Defensive", "comportamiento_ciclo.contraccion", "outperformance clásico",
     "rendimiento superior clásico"),
    ("Consumer Defensive", "sensibilidad_tipos.explicacion", "(distribución, retail alimentario)",
     "(distribución, comercio de alimentación)"),
    ("Consumer Defensive", "leccion_historica", "demostró pricing power extraordinario",
     "demostró una capacidad extraordinaria de subir precios sin perder ventas"),
    ("Energy", "riesgos_especificos", "(OPEP+, geopolítica, shale)",
     "(OPEP+, geopolítica, petróleo de esquisto)"),
    ("Energy", "riesgos_especificos", "Riesgo de activos varados (stranded assets) en transición energética",
     "Riesgo de activos varados en la transición energética"),
    ("Utilities", "comportamiento_ciclo.expansion",
     "negativo relativo — underperformance frente a cíclicos",
     "negativo relativo — rendimiento inferior frente a cíclicos"),
    ("Industrials", "leccion_historica", "(DAX heavy weight)", "(con mucho peso en el DAX)"),
    ("Basic Materials", "descripcion",
     "Los precios de commodities (cobre, acero, aluminio) son el principal driver.",
     "Los precios de las materias primas (cobre, acero, aluminio) son el factor principal."),
    ("Basic Materials", "comportamiento_ciclo.pico", "precios de commodities tienden",
     "precios de las materias primas tienden"),
    ("Basic Materials", "comportamiento_ciclo.contraccion", "caída brutal de precios de commodities",
     "caída brutal de precios de las materias primas"),
    ("Basic Materials", "sensibilidad_tipos.explicacion",
     "El cobre es el mejor barómetro de crecimiento global ('Dr. Copper').",
     "El cobre es el mejor barómetro de crecimiento global (en el mercado lo llaman «doctor cobre»)."),
    ("Basic Materials", "sensibilidad_tipos.explicacion", "encarece las commodities en dólares",
     "encarece las materias primas en dólares"),
    ("Basic Materials", "riesgos_especificos", "Ciclicidad extrema: precios de commodities muy volátiles",
     "Ciclicidad extrema: precios de las materias primas muy volátiles"),
    ("Basic Materials", "leccion_historica", "El superciclo de commodities 2003-2008",
     "El superciclo de materias primas 2003-2008"),
    ("Basic Materials", "leccion_historica", "riesgos similares de timing",
     "riesgos similares de momento del ciclo"),
    ("Real Estate", "sensibilidad_tipos.explicacion", "(cap rate se expande → valor del activo cae)",
     "(la tasa de capitalización sube → el valor del activo cae)"),
    ("Real Estate", "riesgos_especificos", "Deterioro del retail físico por e-commerce",
     "Deterioro del comercio físico por el comercio electrónico"),
    ("Communication Services", "sensibilidad_tipos.explicacion",
     "Las plataformas digitales se parecen más a tech growth.",
     "Las plataformas digitales se parecen más a las tecnológicas de crecimiento."),
    ("Communication Services", "riesgos_especificos", "Fragmentación del entretenimiento (streaming wars)",
     "Fragmentación del entretenimiento (guerra entre plataformas de vídeo en línea)"),
]


def _leer(nombre):
    with open(DIR / nombre, encoding="utf-8") as f:
        return json.load(f)


def _escribir(nombre, datos):
    with open(DIR / nombre, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _get_set(sector: dict, ruta: str, old: str, new: str) -> bool:
    """Sustituye old→new en el campo indicado por ruta ('a.b' o lista). True si cambia algo."""
    partes = ruta.split(".")
    obj = sector
    for p in partes[:-1]:
        obj = obj.get(p, {})
    k = partes[-1]
    v = obj.get(k)
    if isinstance(v, list):
        nv = [x.replace(old, new) if isinstance(x, str) else x for x in v]
        if nv != v:
            obj[k] = nv
            return True
        return False
    if isinstance(v, str) and old in v:
        obj[k] = v.replace(old, new)
        return True
    return False


def aplicar():
    cambios = []
    c = _leer("criteria.json")
    if c.get("contexto_macro_tramos") != TRAMOS:
        c["contexto_macro_tramos"] = TRAMOS
        _escribir("criteria.json", c); cambios.append("criteria.json: contexto_macro_tramos")

    m = _leer("macro_indicators.json")
    if m.get("fase_ciclo_metodo") != FASE_CICLO:
        m["fase_ciclo_metodo"] = FASE_CICLO
        _escribir("macro_indicators.json", m); cambios.append("macro_indicators.json: fase_ciclo_metodo")

    g = _leer("glosario.json"); t = g.setdefault("terminos", {}); n_g = 0
    for k, (nombre, linea, variantes) in TERMINOS_NUEVOS.items():
        nuevo = {"nombre_completo": nombre, "definicion": linea[0].upper() + linea[1:] + ".",
                 "en_linea": linea, "variantes": variantes, "donde_aparece": ["sector_knowledge.json"],
                 "_origen": "Spec PE v1 (PE-04)"}
        if t.get(k) != nuevo:
            t[k] = nuevo; n_g += 1
    for k, (linea, variantes) in EN_LINEA_EXISTENTES.items():
        if k in t and (t[k].get("en_linea") != linea or t[k].get("variantes") != variantes):
            t[k]["en_linea"] = linea; t[k]["variantes"] = variantes; n_g += 1
    if n_g:
        _escribir("glosario.json", g); cambios.append(f"glosario.json: {n_g} términos")

    s = _leer("sector_knowledge.json"); sec = s.get("sectores", {}); n_s = 0
    for k, (intens, si_suben, motivo) in SENSIBILIDAD.items():
        st_ = sec.get(k, {}).get("sensibilidad_tipos")
        if st_ is None:
            continue
        if "intensidad_v1" not in st_ and "intensidad" in st_:
            st_["intensidad_v1"] = st_["intensidad"]; n_s += 1
        for kk, vv in (("intensidad", intens), ("si_suben", si_suben), ("motivo", motivo)):
            if st_.get(kk) != vv:
                st_[kk] = vv; n_s += 1
    for k, ruta, old, new in SUSTITUCIONES:
        if k in sec and old != new and _get_set(sec[k], ruta, old, new):
            n_s += 1
    if n_s:
        _escribir("sector_knowledge.json", s); cambios.append(f"sector_knowledge.json: {n_s} cambios")
    return cambios


def revertir():
    cambios = []
    c = _leer("criteria.json")
    if c.pop("contexto_macro_tramos", None) is not None:
        _escribir("criteria.json", c); cambios.append("criteria.json")
    m = _leer("macro_indicators.json")
    if m.pop("fase_ciclo_metodo", None) is not None:
        _escribir("macro_indicators.json", m); cambios.append("macro_indicators.json")
    g = _leer("glosario.json"); t = g.get("terminos", {}); n = 0
    for k in TERMINOS_NUEVOS:
        if t.pop(k, None) is not None:
            n += 1
    for k in EN_LINEA_EXISTENTES:
        if k in t:
            n += int(t[k].pop("en_linea", None) is not None); t[k].pop("variantes", None)
    if n:
        _escribir("glosario.json", g); cambios.append("glosario.json")
    s = _leer("sector_knowledge.json"); sec = s.get("sectores", {}); n = 0
    for k in SENSIBILIDAD:
        st_ = sec.get(k, {}).get("sensibilidad_tipos")
        if not st_:
            continue
        for kk in ("si_suben", "motivo"):
            n += int(st_.pop(kk, None) is not None)
        if "intensidad_v1" in st_:
            st_["intensidad"] = st_.pop("intensidad_v1"); n += 1
    for k, ruta, old, new in SUSTITUCIONES:
        if k in sec and old != new and _get_set(sec[k], ruta, new, old):
            n += 1
    if n:
        _escribir("sector_knowledge.json", s); cambios.append("sector_knowledge.json")
    return cambios


if __name__ == "__main__":
    if "--revertir" in sys.argv:
        print("Revertido:", revertir() or "nada que revertir")
    elif "--comprobar" in sys.argv:
        c = _leer("criteria.json"); m = _leer("macro_indicators.json")
        print("contexto_macro_tramos:", "sí" if "contexto_macro_tramos" in c else "no")
        print("fase_ciclo_metodo:", "sí" if "fase_ciclo_metodo" in m else "no")
    else:
        print("Aplicado:", aplicar() or "sin cambios (ya estaba aplicado)")
