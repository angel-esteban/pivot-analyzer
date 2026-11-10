"""Documento 35 de Pólaris, §2, §3 y §4. Migración de JSON, aditiva y reversible. Requiere migracion_pe_v12_json.py.

  criteria.json
    avisos_datos (clave nueva): aviso de volumen junto a un corte (margen de 1 punto) y aviso de barra sin cierre.
    semaforo_paso3.lecturas.verde / rojo: plantillas nuevas de la invalidación (plantilla_cambio, plantilla_igual)
      y de los niveles de apoyo (plantilla_apoyo). La «plantilla» del doc. 28 se guarda en _previo_pe_v13 y deja
      de usarse; las cláusulas del SAR y del pivot se mantienen (ahora son niveles de apoyo).
    semaforo_paso3.cotizacion_actual.apoyo_tocado (clave nueva).

Uso:  python migracion_pe_v13_json.py [--revertir]
"""
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CLAVE_PREV = "_previo_pe_v13"

AVISOS = {
    "margen_corte_volumen": 1.0,
    "volumen_junto_corte": ("El ratio está a menos de 1 punto del corte del {x}%. La fuente puede revisar ligeramente "
                            "el volumen de la última sesión hasta la mañana siguiente, y la puntuación podría cambiar."),
    "barra_sin_cierre": ("La sesión del {fecha_descartada} todavía no tiene cierre publicado en la fuente de datos; "
                         "los cálculos usan la última sesión completa ({fecha_usada}). Se actualizará cuando la fuente "
                         "lo publique."),
}
LECTURAS = {
    "verde": {
        "plantilla_cambio": ("La lectura se invalidaría con un cierre por {lado} de {nivel} ({dist}), que llevaría el "
                             "semáforo al {pct}% ({color})."),
        "plantilla_igual": ("Con un cierre igual al último ({cierre}), la lectura ya no se mantendría: el semáforo "
                            "pasaría al {pct}% ({color})."),
        "plantilla_apoyo": "Perdería apoyo si {clausulas}.",
    },
    "rojo": {
        "plantilla_cambio": ("La lectura se invalidaría con un cierre por {lado} de {nivel} ({dist}), que llevaría el "
                             "semáforo al {pct}% ({color})."),
        "plantilla_igual": ("Con un cierre igual al último ({cierre}), la lectura ya no se mantendría: el semáforo "
                            "pasaría al {pct}% ({color})."),
        "plantilla_apoyo": "Perdería apoyo si {clausulas}.",
    },
}
APOYO_TOCADO = "Hoy se ha tocado un nivel de apoyo de la lectura ({condicion}); se confirmará o no con el cierre."


def _leer():
    with open(DIR / "criteria.json", encoding="utf-8") as f:
        return json.load(f)


def _escribir(d):
    with open(DIR / "criteria.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def aplicar():
    c = _leer()
    c["avisos_datos"] = dict(AVISOS)
    sp = c["semaforo_paso3"]
    for col, nuevos in LECTURAS.items():
        lec = sp["lecturas"][col]
        lec.setdefault(CLAVE_PREV, {"plantilla": lec.get("plantilla")})
        lec.update(nuevos)
    sp["cotizacion_actual"]["apoyo_tocado"] = APOYO_TOCADO
    _escribir(c)
    return ["criteria.json"]


def revertir():
    c = _leer()
    c.pop("avisos_datos", None)
    sp = c["semaforo_paso3"]
    for col, nuevos in LECTURAS.items():
        lec = sp["lecturas"][col]
        for k in nuevos:
            lec.pop(k, None)
        p = lec.pop(CLAVE_PREV, None)
        if p:
            lec["plantilla"] = p["plantilla"]
    sp["cotizacion_actual"].pop("apoyo_tocado", None)
    _escribir(c)
    return ["criteria.json"]


if __name__ == "__main__":
    if "_previo_pe_v12" not in _leer().get("semaforo_paso3", {}).get("cotizacion_actual", {}):
        sys.exit("Primero hay que aplicar migracion_pe_v12_json.py")
    print("Revertido:" if "--revertir" in sys.argv else "Aplicado:",
          revertir() if "--revertir" in sys.argv else aplicar())
