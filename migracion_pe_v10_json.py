"""Documento 29 de Pólaris (validación de F28). Migración de JSON, aditiva y reversible.
Requiere migracion_pe_v9_json.py aplicada.

  criteria.json  semaforo_paso3:
    · sesion_cerrada: hora a partir de la cual la sesión del día se da por cerrada (§1a).
    · cotizacion_actual: corte de movimiento amplio en ATR y textos del apartado «Cotización actual» (§1b).
    · relacion.coherente_sin_direccion: casilla estructura mixta × momento mixto (§4).

Uso:  python migracion_pe_v10_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

SESION_CERRADA = {
    "Europe": "18:00",
    "America": "16:30",
    "porque": ("La sesión del día se da por cerrada después de la subasta de cierre (17:30–17:35 en el Mercado "
               "Continuo; 16:00 en Nueva York) y con margen para que Yahoo publique el dato definitivo, que llega con "
               "unos 15–20 minutos de retraso. Hora local de cada mercado. Fines de semana y festivos no son sesión."),
}
COTIZACION = {
    "titulo": "Cotización actual (retraso ~15 min)",
    "corte_atr_amplio": 1.0,
    "porque_corte": ("Un desplazamiento igual o mayor que la oscilación media diaria (1 ATR14) es un movimiento amplio "
                     "para ese valor; por debajo, queda dentro de lo habitual."),
    "sin_cruces": "Ningún nivel del método se ha cruzado hoy: la lectura del último cierre se mantiene por ahora.",
    "invalidacion_tocada": "La invalidación de la lectura ({condicion}) se ha tocado hoy; se confirmará o no con el cierre.",
    "nota_fija": ("Los indicadores se calculan con sesiones cerradas. Este apartado indica qué niveles del método se han "
                  "cruzado hoy; el cambio solo se confirma con el cierre."),
    "mercado_cerrado": "Mercado cerrado: los cálculos usan el último cierre ({fecha}).",
    "encabezado": "Cálculos con la sesión cerrada del {fecha} · cierre {cierre}",
}
REL_SIN_DIRECCION = ("Ni la estructura de fondo ni el impulso reciente marcan una dirección clara; coinciden en la falta "
                     "de sesgo.")


def _leer():
    with open(DIR / "criteria.json", encoding="utf-8") as f:
        return json.load(f)


def _escribir(d):
    with open(DIR / "criteria.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer()
    s = c["semaforo_paso3"]
    s["sesion_cerrada"] = dict(SESION_CERRADA)
    s["cotizacion_actual"] = dict(COTIZACION)
    s["relacion"]["coherente_sin_direccion"] = REL_SIN_DIRECCION
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer()
    s = c["semaforo_paso3"]
    s.pop("sesion_cerrada", None)
    s.pop("cotizacion_actual", None)
    s.get("relacion", {}).pop("coherente_sin_direccion", None)
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "lecturas" not in _leer().get("semaforo_paso3", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v9_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
