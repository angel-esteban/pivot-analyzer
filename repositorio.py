"""
repositorio.py — Capa de lectura de datos del screener desde Neon.

Reconstruye un dict con forma de `info` de yfinance (mismas claves que ya leen
los criterios) a partir de las tablas `instrumento` y `fundamental`, añadiendo el
estado de frescura de cada nivel. Así el screener puede leer de Neon (niveles 1-2)
sin cambiar la lógica de evaluación, y seguir pidiendo el nivel mercado en vivo.

Política de frescura (ver DISENO §6): cada nivel se etiqueta ok / cacheado /
caducado / sospechoso / ausente según su antigüedad y su flag `valido`.

Nota de alcance: en esta versión se sirven desde Neon los campos directos de
`.info` (payout, deuda, márgenes, sector, beta, TER, AUM...). Los criterios
*calculados* (free_float, dividend yield, RSI...) se siguen computando en vivo.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import umbrales   # fuente única del SLA de frescura (Configuración)

# Columna en BD -> clave de yfinance que esperan los criterios de criteria.json
MAP_INSTRUMENTO = {
    "sector": "sector",
    # V-1(c) (Polaris, Job #58): último dato estructural validado, para cuando yfinance
    # no responde. Claves con "_" = solo de respaldo; nunca pisan un dato en vivo.
    "free_float_pct": "_free_float_pct_neon",
    "nombre":         "longName",
    "ter":    "annualReportExpenseRatio",
    "aum":    "totalAssets",
}
MAP_FUNDAMENTAL = {
    "payout_ratio":      "payoutRatio",
    "bpa":               "trailingEps",
    "debt_to_equity":    "debtToEquity",
    "ev_ebitda":         "enterpriseToEbitda",
    "revenue_growth":    "revenueGrowth",
    "gross_margins":     "grossMargins",
    "operating_margins": "operatingMargins",
    "roe":               "returnOnEquity",
    "peg_ratio":         "pegRatio",
    "earnings_growth":   "earningsGrowth",
    "market_cap":        "marketCap",
    "beta":              "beta",
}

# Tolerancia de obsolescencia por nivel (fallback; el valor vigente se lee de umbrales)
TOLERANCIA_DIAS = {"estructural": 365, "fundamental": 120}
_SLA_KEY = {"estructural": "sla_estructural_dias", "fundamental": "sla_fundamental_dias"}


def _tolerancia_dias(nivel: str) -> int:
    """SLA de frescura vigente para el nivel (Configuración › Umbrales), con fallback."""
    try:
        return int(umbrales.actuales()[_SLA_KEY[nivel]])
    except Exception:                        # noqa: BLE001
        return TOLERANCIA_DIAS.get(nivel, 365)

try:
    import psycopg2.extras as _extras
    _FACTORY = _extras.RealDictCursor
except Exception:                       # noqa: BLE001 — entorno de test sin psycopg2
    _FACTORY = None


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _leer_fila(conn, tabla: str, ticker: str) -> dict | None:
    cur = conn.cursor(cursor_factory=_FACTORY) if _FACTORY else conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {tabla} WHERE ticker = %s", [ticker])
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _estado_frescura(actualizado_en, tolerancia_dias: int, ahora, valido) -> str:
    if actualizado_en is None:
        return "ausente"
    if valido is False:
        return "sospechoso"
    dt = actualizado_en
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt)
        except ValueError:
            return "ok"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    edad = (ahora - dt).days
    if edad > tolerancia_dias:
        return "caducado"
    return "cacheado"


def componer_info(ticker: str, conn, ahora: datetime.datetime | None = None
                  ) -> tuple[dict[str, Any], dict[str, dict], set[str]]:
    """
    Devuelve (info, frescura, db_invalidos):
      - info: dict con claves de yfinance pobladas desde Neon (solo valores no nulos)
      - frescura: {nivel: {estado, actualizado_en, valido}} para cada nivel persistido
      - db_invalidos: set de campos (clave yfinance / id de criterio) que la BBDD marcó
        como NO fiables en la ingesta (columna `incidencias`). El screener lo usa para
        decidir si un campo de Neon es de fiar.
    """
    ahora = ahora or _ahora()
    info: dict[str, Any] = {}
    frescura: dict[str, dict] = {}
    db_invalidos: set[str] = set()

    for tabla, mapa, nivel in (("instrumento", MAP_INSTRUMENTO, "estructural"),
                               ("fundamental", MAP_FUNDAMENTAL, "fundamental")):
        fila = _leer_fila(conn, tabla, ticker)
        if not fila:
            frescura[nivel] = {"estado": "ausente", "actualizado_en": None, "valido": None}
            continue
        for col, yk in mapa.items():
            v = fila.get(col)
            if v is not None:
                info[yk] = v
        inc = fila.get("incidencias") or {}
        if isinstance(inc, str):
            try:
                inc = json.loads(inc)
            except Exception:
                inc = {}
        db_invalidos.update(inc.keys())
        frescura[nivel] = {
            "estado": _estado_frescura(fila.get("actualizado_en"),
                                       _tolerancia_dias(nivel), ahora, fila.get("valido")),
            "actualizado_en": fila.get("actualizado_en"),
            "valido": fila.get("valido"),
        }
    return info, frescura, db_invalidos


def necesita_live(frescura: dict, nivel: str) -> bool:
    """True si ese nivel debe completarse con yfinance en vivo (ausente o caducado)."""
    return frescura.get(nivel, {}).get("estado") in ("ausente", "caducado")


def etiqueta_frescura(frescura: dict, nivel: str) -> str:
    """Etiqueta legible para el informe. Vacía si el dato es fresco/ok."""
    f = frescura.get(nivel, {})
    estado, ts = f.get("estado"), f.get("actualizado_en")
    if estado in (None, "ok"):
        return ""
    fecha = ""
    if ts is not None:
        d = ts if not isinstance(ts, str) else ts[:10]
        fecha = d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
    etiquetas = {
        "cacheado":   f"[DATO CACHEADO · {fecha}]",
        "caducado":   f"[DATO CADUCADO · {fecha} — refrescar]",
        "sospechoso": "[DATO SOSPECHOSO — verificar]",
        "ausente":    "[SIN DATO PERSISTIDO — en vivo]",
    }
    return etiquetas.get(estado, "")


# ─────────────────────────────────────────────────────────────────────────────
# Pagos manuales de remuneración al accionista (decisión 3 de Pólaris, 05/11/2026)
# Tabla `dividendo_manual` (migracion_dividendo_manual.sql). Importes BRUTOS por acción.
# Solo fuentes de rango 1 (CNMV o web de inversores); el alta la hace un admin.
# ─────────────────────────────────────────────────────────────────────────────
TIPOS_PAGO_MANUAL = ("dividendo", "dividendo_a_cuenta", "dividendo_complementario", "prima",
                     "scrip", "extraordinario", "anunciado")
# Tipos que necesitan migracion_dividendo_manual_v2.sql (columnas ejercicio / fecha_anuncio)
TIPOS_V2 = ("dividendo_a_cuenta", "dividendo_complementario", "anunciado")
# Agregadores y prensa: NO son fuente de rango 1 para un pago manual.
DOMINIOS_NO_ADMITIDOS = ("stockanalysis.", "finect.", "investing.", "yahoo.", "dividendmax.",
                         "divvydiary.", "dividendpedia.", "stockevents.", "rankia.", "marketscreener.",
                         "tradingview.", "morningstar.", "bolsamania.", "expansion.", "cincodias.",
                         "eleconomista.", "estrategiasdeinversion.", "tipranks.", "getquin.",
                         "digrin.", "parqet.", "tradersunion.", "seekingalpha.", "google.")


def validar_pago_manual(d: dict) -> str | None:
    """Valida un pago manual antes de guardarlo. Devuelve el motivo de error o None."""
    try:
        imp = float(d.get("importe_bruto"))
    except (TypeError, ValueError):
        return "importe bruto no numérico"
    if not imp > 0:
        return "el importe bruto debe ser > 0"
    if not d.get("ticker"):
        return "falta el ticker"
    if d.get("tipo") not in TIPOS_PAGO_MANUAL:
        return f"tipo no válido (uno de: {', '.join(TIPOS_PAGO_MANUAL)})"
    if d.get("tipo") == "anunciado":
        # R3 (Pólaris): importe ANUAL total anunciado para un ejercicio; sin fecha ex
        if not d.get("ejercicio"):
            return "un importe anunciado necesita el ejercicio al que se refiere"
        if not d.get("fecha_anuncio"):
            return "un importe anunciado necesita la fecha del anuncio"
    elif not d.get("fecha_ex"):
        return "falta la fecha ex"
    if d.get("tipo") in ("dividendo_a_cuenta", "dividendo_complementario") and not d.get("ejercicio"):
        return "un dividendo a cuenta o complementario necesita el ejercicio al que se imputa"
    if d.get("ejercicio") not in (None, ""):
        try:
            if not 1990 <= int(d["ejercicio"]) <= 2100:
                return "ejercicio fuera de rango"
        except (TypeError, ValueError):
            return "ejercicio no numérico"
    url = str(d.get("url_origen") or "").strip().lower()
    if not url.startswith("https://"):
        return "falta la URL del documento de origen (https://…)"
    _host = url.split("/")[2] if len(url.split("/")) > 2 else ""
    if any(x in _host for x in DOMINIOS_NO_ADMITIDOS):
        return ("fuente no admitida: solo CNMV o la web de inversores de la empresa "
                "(los agregadores y la prensa no son fuente de rango 1)")
    if d.get("fecha_pago") and d.get("fecha_ex") and str(d["fecha_pago"]) < str(d["fecha_ex"]):
        return "la fecha de pago no puede ser anterior a la fecha ex"
    return None


def leer_dividendos_manuales(ticker: str, conn) -> list[dict]:
    """Pagos manuales ACTIVOS del ticker. Lista vacía si la tabla aún no existe."""
    cur = conn.cursor(cursor_factory=_FACTORY) if _FACTORY else conn.cursor()
    try:
        cur.execute("SELECT * FROM dividendo_manual WHERE ticker = %s AND activo "
                    "ORDER BY fecha_ex", [ticker])
        rows = cur.fetchall() or []
        if rows and not isinstance(rows[0], dict):
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in rows]
        return [dict(r) for r in rows]
    except Exception:                        # noqa: BLE001 — tabla ausente (migración no aplicada)
        try:
            conn.rollback()
        except Exception:
            pass
        return []
    finally:
        try:
            cur.close()
        except Exception:
            pass


def guardar_pago_manual(conn, d: dict, usuario: str) -> str | None:
    """Alta de un pago manual (validado). Devuelve error o None."""
    err = validar_pago_manual(d)
    if err:
        return err
    try:
        cur = conn.cursor()
        cols = ["ticker", "fecha_ex", "fecha_pago", "importe_bruto", "tipo", "url_origen", "nota",
                "alta_usuario"]
        vals = [d["ticker"].upper().strip(), d.get("fecha_ex") or None, d.get("fecha_pago") or None,
                float(d["importe_bruto"]), d["tipo"], d["url_origen"].strip(), d.get("nota") or None,
                usuario]
        # Columnas de la migración v2: solo si se informan (así funciona también sin ella)
        for c in ("ejercicio", "fecha_anuncio"):
            if d.get(c) not in (None, ""):
                cols.append(c)
                vals.append(int(d[c]) if c == "ejercicio" else d[c])
        cur.execute(f"INSERT INTO dividendo_manual ({', '.join(cols)}) "
                    f"VALUES ({', '.join(['%s'] * len(cols))})", vals)
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        if "uq_dividendo_manual" in str(e) or "duplicate key" in str(e):
            return "ya existe un pago de ese tipo para ese ticker y fecha ex (modifícalo en vez de duplicarlo)"
        if "dividendo_manual" in str(e) and "does not exist" in str(e):
            return "la tabla dividendo_manual no existe: ejecuta migracion_dividendo_manual.sql en Neon"
        if ("ejercicio" in str(e) or "fecha_anuncio" in str(e) or "tipo_check" in str(e)
                or "fecha_ex" in str(e)):
            return ("este tipo de pago necesita la migración v2: ejecuta "
                    "migracion_dividendo_manual_v2.sql en Neon")
        if "uq_dividendo_manual_anunciado" in str(e):
            return "ya hay un importe anunciado activo para ese ticker y ejercicio"
        return f"error al guardar: {e}"
    return None


def modificar_pago_manual(conn, pago_id: int, cambios: dict, usuario: str) -> str | None:
    """Modifica importe, fechas, URL, nota o activo (baja lógica) de un pago manual."""
    permitidos = {"importe_bruto", "fecha_pago", "url_origen", "nota", "activo"}
    cambios = {k: v for k, v in (cambios or {}).items() if k in permitidos}
    if not cambios:
        return "nada que modificar"
    if "importe_bruto" in cambios or "url_origen" in cambios:
        _base = {"ticker": "X", "fecha_ex": "2000-01-01", "tipo": "dividendo",
                 "importe_bruto": cambios.get("importe_bruto", 1), "url_origen": cambios.get("url_origen", "https://x")}
        err = validar_pago_manual(_base)
        if err:
            return err
    sets = ", ".join(f"{k} = %s" for k in cambios) + ", modificado_por = %s, modificado_en = now()"
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE dividendo_manual SET {sets} WHERE id = %s",
                    list(cambios.values()) + [usuario, int(pago_id)])
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        return f"error al modificar: {e}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Incidencias de calidad de las series de precios (docs. 25-27 de Pólaris)
# Tabla `incidencia_serie` (migracion_incidencia_serie.sql). Independiente de
# `incidencias`/`valido` de instrumento y fundamental: no afecta al screener.
# ─────────────────────────────────────────────────────────────────────────────
TIPO_SERIE_NO_AJUSTADA_ATH = "serie_no_ajustada_ath"


def registrar_incidencia_serie(conn, ticker: str, tipo: str, activa: bool,
                               detalle: dict | None = None) -> str | None:
    """Activa (alta o actualización) o desactiva la incidencia (ticker, tipo).
    · activa=True  → INSERT … ON CONFLICT: detalle y ultima_vez nuevos, activa = true
                     (primera_vez se conserva).
    · activa=False → solo desactiva una fila activa existente; si no hay, no hace nada.
    Devuelve un texto de error o None."""
    tk = (ticker or "").upper().strip()
    if not tk or not tipo:
        return "ticker y tipo son obligatorios"
    try:
        cur = conn.cursor()
        if activa:
            _sql = ("INSERT INTO incidencia_serie (ticker, tipo, detalle, activa) "
                    "VALUES (%s, %s, %s::jsonb, true) "
                    "ON CONFLICT (ticker, tipo){pred} DO UPDATE SET detalle = EXCLUDED.detalle, "
                    "ultima_vez = now(), activa = true")
            _args = [tk, tipo, json.dumps(detalle or {}, ensure_ascii=False, default=str)]
            try:   # doc. 35 §3: con la migración v2, la unicidad (ticker, tipo) es parcial (fecha_sesion IS NULL)
                cur.execute(_sql.format(pred=" WHERE fecha_sesion IS NULL"), _args)
            except Exception as e_v2:        # noqa: BLE001  — sin la migración v2: cláusula original
                if "fecha_sesion" not in str(e_v2):
                    raise
                conn.rollback()
                cur = conn.cursor()
                cur.execute(_sql.format(pred=""), _args)
        else:
            cur.execute(
                "UPDATE incidencia_serie SET activa = false, ultima_vez = now() "
                "WHERE ticker = %s AND tipo = %s AND activa",
                [tk, tipo])
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        if "incidencia_serie" in str(e) and "does not exist" in str(e):
            return "la tabla incidencia_serie no existe: ejecuta migracion_incidencia_serie.sql en Neon"
        return f"error al registrar la incidencia de serie: {e}"
    return None


TIPO_BARRA_SIN_CIERRE = "barra_sin_cierre"


def registrar_barra_sin_cierre(conn, ticker: str, fecha_sesion: str) -> str | None:
    """Doc. 35 §3 — Una fila por ticker y fecha de sesión (no una por consulta). Si ya existe, solo actualiza
    ultima_vez; si estaba cerrada y la barra vuelve a llegar sin cierre, se reabre (resuelta_en = NULL).
    Requiere migracion_incidencia_serie_v2.sql (columnas fecha_sesion y resuelta_en)."""
    tk = (ticker or "").upper().strip()
    if not tk or not fecha_sesion:
        return "ticker y fecha_sesion son obligatorios"
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO incidencia_serie (ticker, tipo, fecha_sesion, detalle, activa) "
            "VALUES (%s, %s, %s::date, %s::jsonb, true) "
            "ON CONFLICT (ticker, tipo, fecha_sesion) WHERE fecha_sesion IS NOT NULL "
            "DO UPDATE SET ultima_vez = now(), activa = true, resuelta_en = NULL",
            [tk, TIPO_BARRA_SIN_CIERRE, fecha_sesion,
             json.dumps({"fuente": "yahoo", "detalle": "barra diaria con Close vacío"}, ensure_ascii=False)])
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        if "fecha_sesion" in str(e) or "no unique or exclusion constraint" in str(e):
            return "falta la migración: ejecuta migracion_incidencia_serie_v2.sql en Neon"
        return f"error al registrar la barra sin cierre: {e}"
    return None


def resolver_barras_sin_cierre(conn, ticker: str, fechas_con_cierre: list[str]) -> str | None:
    """Doc. 35 §3 — Cierra (activa = false, resuelta_en = now()) las filas abiertas del ticker cuya fecha ya tiene
    cierre publicado. No toca filas de otros tipos."""
    tk = (ticker or "").upper().strip()
    if not tk or not fechas_con_cierre:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE incidencia_serie SET activa = false, resuelta_en = now(), ultima_vez = now() "
            "WHERE ticker = %s AND tipo = %s AND activa AND fecha_sesion = ANY(%s::date[])",
            [tk, TIPO_BARRA_SIN_CIERRE, list(fechas_con_cierre)])
        conn.commit()
    except Exception as e:                   # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        if "fecha_sesion" in str(e) or "resuelta_en" in str(e):
            return None                      # migración aún no aplicada: nada que resolver
        return f"error al resolver barras sin cierre: {e}"
    return None


def leer_incidencias_serie(conn, solo_activas: bool = True) -> list[dict]:
    """Filas de incidencia_serie (las activas primero, más recientes arriba). [] si no hay tabla."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ticker, tipo, detalle, primera_vez, ultima_vez, activa FROM incidencia_serie"
            + (" WHERE activa" if solo_activas else "")
            + " ORDER BY activa DESC, ultima_vez DESC")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:                        # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        return []
