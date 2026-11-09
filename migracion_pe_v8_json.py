"""Spec PE v4 (Paso 3, documento 24) y decisiones del documento 28 de Pólaris.
Migración de JSON, aditiva y reversible. Requiere migracion_pe_v7_json.py aplicada.

  criteria.json  bloque nuevo «semaforo_paso3»: cortes y mínimo de factores (PE-17, doc. 28 e/h), rótulos,
                 nota fija, textos de las fichas en tres niveles (PE-16, PE-18), parámetros y su porqué
                 (PE-21), notas informativas de los extremos (doc. 28 b/c) y textos de la relación con el
                 Paso 2 (PE-19).

Uso:  python migracion_pe_v8_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

SEMAFORO_PASO3 = {
    "_descripcion": ("Spec PE v4 (Paso 3) y doc. 28. Parámetros y textos del semáforo de momento. El corte se "
                     "compara con el porcentaje sin redondear; el redondeo a entero es solo para mostrarlo."),
    "cortes": {"verde": 65.0, "amarillo": 40.0},
    "min_factores": 4,
    "rotulos": {
        "verde": "Momento alcista: la mayoría de indicadores de corto plazo apuntan al alza.",
        "amarillo": "Momento mixto: los indicadores de corto plazo no coinciden.",
        "rojo": "Momento bajista: la mayoría de indicadores de corto plazo apuntan a la baja.",
        "gris": "Datos insuficientes para el semáforo ({n} de 6 factores).",
    },
    "nota_fija": "Los colores resumen el momento según el método; no indican qué hacer con una posición.",
    "intro": ("El Paso 3 mide el impulso de corto plazo, de unos días a pocas semanas, con seis indicadores. "
              "El Paso 2 mide la estructura de fondo; aquí se ve si el impulso reciente la acompaña."),
    "que_es": {
        "pp": "Precio de equilibrio de la sesión anterior: la media de su máximo, su mínimo y su cierre.",
        "rsi": "Compara la fuerza de las subidas y de las bajadas recientes en una escala de 0 a 100.",
        "macd": "Mide si la media rápida se separa o se acerca a la lenta: indica la dirección y la fuerza del impulso.",
        "bb": "Indica en qué parte de un canal de oscilación normal está el precio: 0 en la banda baja, 100 en la alta.",
        "vol": "Cuántas acciones se han negociado frente a lo habitual: mide la participación.",
        "sar": ("Un punto que sigue al precio por debajo en las subidas y por encima en las bajadas; cuando el "
                "precio lo cruza, el indicador gira."),
    },
    "mas_detalle": {
        "pp": ("PP = (H + L + C) / 3, con el máximo, el mínimo y el cierre de la sesión anterior. Solo vale para "
               "una sesión. Es una referencia muy usada en el corto plazo, por eso el método la vigila; no tiene "
               "capacidad de predicción propia."),
        "rsi": ("RSI = 100 − 100 / (1 + RS); RS = media de subidas / media de bajadas (media de Wilder, 14 "
                "sesiones). En tendencias fuertes puede quedarse mucho tiempo en sobrecompra o sobreventa."),
        "macd": ("MACD = EMA12 − EMA26; señal = EMA9 del MACD; histograma = MACD − señal. Va con retraso "
                 "respecto al precio y da cruces falsos en mercados laterales."),
        "bb": ("Bandas = SMA20 ± 2 desviaciones típicas (poblacionales, como en la definición de John "
               "Bollinger). %B = (precio − banda inferior) / (banda superior − banda inferior). En tendencias "
               "fuertes el precio puede «caminar» por una banda; tocarla no implica giro."),
        "vol": ("Ratio = volumen de la última sesión completa / media de las 10 sesiones anteriores. Sesión "
                "alcista = cierre por encima del cierre anterior. Las sesiones de vencimientos, cambios de "
                "índice o resultados lo distorsionan."),
        "sar": ("SAR(t+1) = SAR(t) + FA × (EP − SAR(t)), con EP el extremo de la tendencia; factor de "
                "aceleración 0,02, sube 0,02 con cada nuevo extremo, máximo 0,2. Gira cuando el mínimo (en "
                "tendencia alcista) o el máximo (en bajista) de una sesión toca el SAR. En mercados laterales "
                "gira con frecuencia."),
    },
    "parametros": {
        "pp": "Pivot clásico diario, sea cual sea el sistema elegido en la tabla: el Paso 3 mide el impulso de días a pocas semanas; los pivots de un mes o más se usan en el Paso 2.",
        "rsi": "14 sesiones, media de Wilder: periodo estándar del indicador; permite comparar con cualquier otra fuente.",
        "macd": "12, 26 y 9 sesiones: configuración estándar; es la que publican la mayoría de plataformas.",
        "bb": "20 sesiones y 2 desviaciones típicas: configuración estándar; con datos de comportamiento normal dejaría dentro del canal cerca del 95% de los cierres, aunque los precios reales tienen más extremos.",
        "vol": "Última sesión completa frente a la media de 10: mide el impulso reciente; el Paso 2 mide la participación sostenida (5 frente a 20).",
        "sar": "0,02 / 0,02 / 0,2 (inicio, paso y máximo del factor de aceleración): valores estándar del indicador.",
    },
    "como_leerlo": {
        "pp": {
            "encima": "El precio cerró por encima del equilibrio de la sesión anterior: el método lo interpreta como impulso diario al alza.",
            "debajo": "El precio cerró en o por debajo del equilibrio de la sesión anterior: el método lo interpreta como impulso diario a la baja.",
        },
        "rsi": {
            "sobrecompra": "Las subidas recientes dominan con mucha fuerza: sigue siendo impulso al alza, aunque el método vigila el posible agotamiento y por eso puntúa algo menos.",
            "alcista": "Las subidas recientes pesan más que las bajadas: impulso al alza.",
            "neutro": "Subidas y bajadas recientes están equilibradas: el impulso no tiene dirección clara.",
            "bajista": "Las bajadas recientes pesan más que las subidas: impulso a la baja.",
            "sobreventa": "Las bajadas recientes dominan con mucha fuerza: es impulso a la baja; el método no lo puntúa como rebote.",
        },
        "macd": {
            "encima": "La media rápida va por encima de su señal: el método lo interpreta como impulso al alza.",
            "debajo": "La media rápida va en o por debajo de su señal: el método lo interpreta como impulso a la baja.",
        },
        "bb": {
            "alta": "El precio está en la parte alta del canal: impulso al alza, aunque en esa zona el método vigila el posible agotamiento.",
            "mitad_alta": "El precio está por encima del centro del canal: impulso al alza.",
            "mitad_baja": "El precio está por debajo del centro del canal: impulso a la baja.",
            "baja": "El precio está en la parte baja del canal: impulso a la baja; el método no lo puntúa como rebote.",
        },
        "vol": {
            "alto_alcista": "Se negoció mucho más de lo habitual en una sesión de subida: el método lo interpreta como participación que acompaña al alza.",
            "alto_bajista": "Se negoció mucho más de lo habitual en una sesión que no subió: el método lo interpreta como participación que acompaña a la baja.",
            "normal": "Se negoció en línea con lo habitual: el volumen no apunta en ninguna dirección.",
            "bajo": "Se negoció menos de lo habitual: el volumen no apunta en ninguna dirección.",
        },
        "sar": {
            "alcista": "El SAR está por debajo del precio: el indicador marca tendencia de corto plazo al alza.",
            "bajista": "El SAR está por encima del precio: el indicador marca tendencia de corto plazo a la baja.",
        },
    },
    "notas_informativas": {
        "rsi_sobrecompra": "Zona que el análisis técnico vigila por posible agotamiento del impulso.",
        "rsi_sobreventa": "Zona que el análisis técnico vigila como posible rebote.",
        "bb_alta": "En tendencias fuertes el precio puede recorrer la banda superior; el método vigila el posible agotamiento.",
        "bb_baja": "En tendencias fuertes el precio puede recorrer la banda inferior; el método vigila el posible rebote.",
    },
    "diferencias": {
        "vol": ("El Paso 2 compara la media de 5 sesiones con la de 20 (participación sostenida). El Paso 3 compara "
                "la última sesión con la media de 10 (impulso reciente). Pueden no coincidir."),
        "rsi": ("Es el mismo RSI que en el Paso 2. En el Paso 2 mide la fuerza de fondo y la sobreventa no suma. "
                "En el Paso 3 mide el impulso reciente."),
    },
    "relacion": {
        "coherente": "La estructura de fondo y el impulso reciente apuntan en la misma dirección.",
        "matiza": "La estructura y el impulso reciente no coinciden del todo; el Paso 4 muestra los niveles donde se resolvería.",
        "contradice": ("El impulso reciente va en contra de la estructura de fondo. El método lo interpreta como un "
                       "movimiento de corto plazo que todavía no cambia la estructura."),
    },
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
    c["semaforo_paso3"] = json.loads(json.dumps(SEMAFORO_PASO3))
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer()
    c.pop("semaforo_paso3", None)
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "_previo_pe_v7" not in _leer().get("diagnostico_paso2", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v7_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
