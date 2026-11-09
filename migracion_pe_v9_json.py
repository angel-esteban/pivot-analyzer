"""Documento 28 (versión 2) de Pólaris — lecturas de escenario del semáforo, decisión del propietario del
08/11/2026. Migración de JSON, aditiva y reversible. Requiere migracion_pe_v8_json.py aplicada.

  criteria.json  semaforo_paso3: «lecturas» por color (lectura del método e invalidación con los valores del
                 día), frases de combinación con la estructura del Paso 2, aviso de señal automática y nota fija
                 nueva.
  glosario.json  términos «posición larga», «posición corta» e «invalidación» (PE-21).

Uso:  python migracion_pe_v9_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v9"

LECTURAS = {
    "verde": {
        "lectura": ("Lectura del método: los indicadores de corto plazo están alineados al alza. En análisis técnico, "
                    "este escenario se considera favorable para posiciones largas (compradoras)."),
        "clausulas": {"sar": "el mínimo de una sesión baja del SAR ({sar})",
                      "pp": "el cierre queda bajo el pivot diario ({pp})"},
        "plantilla": "La lectura se invalidaría si {clausulas}.",
        "sin_clausulas": "La lectura cambiaría si el semáforo baja del {verde}%.",
    },
    "amarillo": {
        "lectura": ("Lectura del método: los indicadores no apuntan en una dirección clara. En análisis técnico, este "
                    "escenario se considera sin sesgo: ni favorable ni desfavorable para posiciones largas o cortas."),
        "clausulas": {},
        "plantilla": "",
        "sin_clausulas": "La lectura cambiaría si el semáforo llega al {verde}% o baja del {amarillo}%.",
    },
    "rojo": {
        "lectura": ("Lectura del método: los indicadores de corto plazo están alineados a la baja. En análisis técnico, "
                    "este escenario se considera desfavorable para posiciones largas y se asocia a escenarios bajistas."),
        "clausulas": {"sar": "el máximo de una sesión supera el SAR ({sar})",
                      "pp": "el cierre queda sobre el pivot diario ({pp})"},
        "plantilla": "La lectura se invalidaría si {clausulas}.",
        "sin_clausulas": "La lectura cambiaría si el semáforo llega al {amarillo}% o más.",
    },
}
COMBINACION = {
    "mismo": "El momento y la estructura apuntan en el mismo sentido; el escenario es más consistente.",
    "distinto": ("El momento va en sentido contrario a la estructura del Paso 2 ({nota}, {etiqueta}); en análisis "
                 "técnico, un impulso contra la estructura se considera menos fiable."),
    "mixta": "La estructura del Paso 2 es mixta; el momento no tiene el respaldo de una tendencia de fondo clara.",
    "sin_direccion": "El momento no tiene una dirección clara; la estructura del Paso 2 es {etiqueta} ({nota}).",
}
AVISO = "Describe un escenario técnico; no es una señal automática ni sustituye a la gestión del riesgo."
NOTA_FIJA = ("Las lecturas describen el escenario técnico según el método. La decisión, el tamaño de la posición y "
             "el riesgo corresponden al usuario.")

GLOSARIO = {
    "posición larga": {
        "nombre_completo": "Posición larga (compradora)",
        "definicion": ("Posición que gana si el precio sube: se ha comprado el valor o un instrumento que replica su "
                       "subida. «Favorable para posiciones largas» describe un escenario técnico alcista."),
        "ejemplo": "Un semáforo verde se considera, en análisis técnico, un escenario favorable para posiciones largas.",
        "donde_aparece": ["app.py (Paso 3, Semáforo Global)"],
        "en_linea": "posición compradora: gana si el precio sube",
        "variantes": ["posiciones largas", "posición larga"],
    },
    "posición corta": {
        "nombre_completo": "Posición corta (vendedora)",
        "definicion": ("Posición que gana si el precio baja: se vende un valor prestado o se usa un instrumento que "
                       "replica su caída. Tiene riesgos propios, como el coste del préstamo."),
        "ejemplo": "Un semáforo amarillo se considera sin sesgo: ni favorable ni desfavorable para posiciones largas o cortas.",
        "donde_aparece": ["app.py (Paso 3, Semáforo Global)"],
        "en_linea": "posición vendedora: gana si el precio baja",
        "variantes": ["posiciones cortas", "posición corta"],
    },
    "invalidación": {
        "nombre_completo": "Invalidación de una lectura técnica",
        "definicion": ("Hecho o nivel de precio que, si se produce, deja sin validez la lectura técnica: el escenario "
                       "descrito ya no se sostiene. Enseñar qué invalida una lectura es tan importante como la lectura."),
        "ejemplo": "Con SAR alcista en 56,38 €, la lectura alcista se invalidaría si el mínimo de una sesión baja de ese nivel.",
        "donde_aparece": ["app.py (Paso 3, Semáforo Global)"],
        "en_linea": "hecho que dejaría sin validez la lectura",
        "variantes": ["invalidación"],
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
    s = c["semaforo_paso3"]
    s.setdefault(CLAVE_PREV, {"nota_fija": s.get("nota_fija")})
    s["lecturas"] = json.loads(json.dumps(LECTURAS))
    s["combinacion"] = dict(COMBINACION)
    s["aviso_senal"] = AVISO
    s["nota_fija"] = NOTA_FIJA
    _escribir("criteria.json", c)
    g = _leer("glosario.json")
    previos = g.setdefault(CLAVE_PREV, [k for k in GLOSARIO if k in g["terminos"]])
    for k, v in GLOSARIO.items():
        if k not in previos:
            g["terminos"][k] = dict(v)
    _escribir("glosario.json", g)
    return ["criteria.json", "glosario.json"]


def revertir():
    c = _leer("criteria.json")
    s = c["semaforo_paso3"]
    p = s.pop(CLAVE_PREV, None)
    if p:
        for k in ("lecturas", "combinacion", "aviso_senal"):
            s.pop(k, None)
        s["nota_fija"] = p["nota_fija"]
    _escribir("criteria.json", c)
    g = _leer("glosario.json")
    previos = g.pop(CLAVE_PREV, None)
    if previos is not None:
        for k in GLOSARIO:
            if k not in previos:
                g["terminos"].pop(k, None)
    _escribir("glosario.json", g)
    return ["criteria.json", "glosario.json"]


if __name__ == "__main__":
    if "semaforo_paso3" not in _leer("criteria.json"):
        sys.exit("Primero hay que aplicar migracion_pe_v8_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
