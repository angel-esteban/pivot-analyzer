# =============================================================================
# PivotAnalyzer v1.0
# Análisis técnico multi-timeframe con Pivot Points
# Autor: Scriptum / Angel Esteban
# Fecha: Junio 2026
# =============================================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import bcrypt
import io
import traceback

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Neon (PostgreSQL) via psycopg2
import psycopg2
import psycopg2.extras

# Technical indicators — pandas_ta con fallback manual
try:
    import pandas_ta as ta
    PANDAS_TA = True
except ImportError:
    PANDAS_TA = False

# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="PivotAnalyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS personalizado — optimizado para móvil
st.markdown("""
<style>
    .main > div { padding: 0.5rem 0.5rem; }
    .block-container { padding: 0.5rem 0.5rem 2rem; max-width: 900px; }
    h1 { font-size: 1.4rem !important; color: #1F4E79; }
    h2 { font-size: 1.1rem !important; color: #2E75B6; margin-top: 0.8rem; }
    h3 { font-size: 0.95rem !important; color: #1F4E79; }
    .stMetric { background: #F0F4F8; border-radius: 8px; padding: 0.4rem; }
    .semaforo-verde { color: #2E7D32; font-weight: bold; font-size: 1.1rem; }
    .semaforo-amarillo { color: #F57F17; font-weight: bold; font-size: 1.1rem; }
    .semaforo-rojo { color: #C62828; font-weight: bold; font-size: 1.1rem; }
    .nivel-r { color: #C62828; font-family: monospace; }
    .nivel-s { color: #2E7D32; font-family: monospace; }
    .nivel-pp { color: #1565C0; font-family: monospace; }
    .confluencia { background: #FFF9C4; border-left: 3px solid #F57F17; padding: 2px 6px; }
    div[data-testid="metric-container"] { background: #F0F4F8; border-radius: 8px; }
    .stButton button { width: 100%; }
    @media (max-width: 640px) {
        .block-container { padding: 0.3rem 0.2rem 2rem; }
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# CONEXIÓN NEON (PostgreSQL) — via psycopg2
# =============================================================================

def get_db_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def db_select(tabla: str, filtros: dict = None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            query = f"SELECT * FROM {tabla}"
            params = []
            if filtros:
                conds = [f"{col} = %s" for col in filtros]
                query += " WHERE " + " AND ".join(conds)
                params = list(filtros.values())
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

def db_insert(tabla: str, datos: dict):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cols = ", ".join(datos.keys())
            vals = ", ".join(["%s"] * len(datos))
            query = f"INSERT INTO {tabla} ({cols}) VALUES ({vals}) RETURNING *"
            cur.execute(query, list(datos.values()))
            conn.commit()
            return [dict(cur.fetchone())]
    finally:
        conn.close()

def db_update(tabla: str, datos: dict, filtro_col: str, filtro_val):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            sets = ", ".join([f"{k} = %s" for k in datos])
            query = f"UPDATE {tabla} SET {sets} WHERE {filtro_col} = %s RETURNING *"
            cur.execute(query, list(datos.values()) + [filtro_val])
            conn.commit()
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

def db_delete(tabla: str, filtro_col: str, filtro_val):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            query = f"DELETE FROM {tabla} WHERE {filtro_col} = %s RETURNING *"
            cur.execute(query, [filtro_val])
            conn.commit()
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# =============================================================================
# FUNCIONES DE AUTENTICACIÓN
# =============================================================================

def verificar_password(password: str, hash_stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hash_stored.encode('utf-8'))
    except Exception:
        return False


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')


def login_usuario(username: str, password: str):
    """Retorna dict del usuario si login correcto, None si falla."""
    try:
        datos = db_select("usuarios", {"username": username, "activo": True})
        if not datos:
            return None
        user = datos[0]
        if verificar_password(password, user["password_hash"]):
            db_update("usuarios", {"ultimo_acceso": datetime.now().isoformat()}, "id", user["id"])
            return user
        return None
    except Exception as e:
        st.error(f"Error de autenticación: {e}")
        return None


def pantalla_login():
    st.markdown("## 📊 PivotAnalyzer")
    st.markdown("*Análisis técnico multi-timeframe con Pivot Points*")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Acceso")
        username = st.text_input("Usuario", placeholder="tu_usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("🔐 Entrar", type="primary"):
            if username and password:
                with st.spinner("Verificando..."):
                    user = login_usuario(username, password)
                if user:
                    st.session_state["usuario"] = user
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos, o cuenta desactivada.")
            else:
                st.warning("Introduce usuario y contraseña.")

    st.markdown("---")
    st.caption("Análisis educativo. No constituye asesoramiento de inversión (MiFID II).")


# =============================================================================
# FUNCIONES DE DATOS — YFINANCE
# =============================================================================

@st.cache_data(ttl=900)  # 15 minutos de caché
def obtener_datos(ticker: str):
    """Descarga datos OHLCV y metadatos del ticker."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", auto_adjust=True)
        info = t.info
        return hist, info
    except Exception as e:
        return None, {}


def precio_actual(hist: pd.DataFrame):
    """Último cierre disponible."""
    if hist is None or hist.empty:
        return None
    return round(hist["Close"].iloc[-1], 4)


def datos_sesion(hist: pd.DataFrame, timeframe: str):
    """
    Retorna (H, L, C, O) de la sesión base según el timeframe.
    Para Pivot Points se usa la sesión ANTERIOR completa.
    """
    if hist is None or hist.empty:
        return None, None, None, None

    hoy = hist.index[-1].date()

    if timeframe == "Intradía":
        # Sesión de ayer
        ayer = hist[hist.index.date < hoy]
        if ayer.empty:
            return None, None, None, None
        sesion = ayer.iloc[-1]
        return float(sesion["High"]), float(sesion["Low"]), float(sesion["Close"]), float(sesion["Open"])

    elif timeframe == "Diario":
        # Mismo que intradía para datos diarios
        ayer = hist[hist.index.date < hoy]
        if ayer.empty:
            return None, None, None, None
        sesion = ayer.iloc[-1]
        return float(sesion["High"]), float(sesion["Low"]), float(sesion["Close"]), float(sesion["Open"])

    elif timeframe == "Semanal":
        # Semana anterior completa
        semana_actual = hist.index[-1].isocalendar()[1]
        año_actual = hist.index[-1].year
        semana_ant = hist[
            ~((hist.index.isocalendar().week == semana_actual) & (hist.index.year == año_actual))
        ]
        if semana_ant.empty:
            return None, None, None, None
        ultima_semana = semana_ant[semana_ant.index.isocalendar().week == semana_ant.index[-1].isocalendar()[1]]
        H = float(ultima_semana["High"].max())
        L = float(ultima_semana["Low"].min())
        C = float(ultima_semana["Close"].iloc[-1])
        O = float(ultima_semana["Open"].iloc[0])
        return H, L, C, O

    elif timeframe == "Trimestral":
        # Trimestre natural anterior
        mes_actual = hist.index[-1].month
        año_actual = hist.index[-1].year
        q_actual = (mes_actual - 1) // 3 + 1

        if q_actual == 1:
            q_ant, año_q = 4, año_actual - 1
        else:
            q_ant, año_q = q_actual - 1, año_actual

        meses_q = {1: [1,2,3], 2: [4,5,6], 3: [7,8,9], 4: [10,11,12]}
        meses = meses_q[q_ant]
        datos_q = hist[
            (hist.index.year == año_q) & (hist.index.month.isin(meses))
        ]
        if datos_q.empty:
            return None, None, None, None
        H = float(datos_q["High"].max())
        L = float(datos_q["Low"].min())
        C = float(datos_q["Close"].iloc[-1])
        O = float(datos_q["Open"].iloc[0])
        return H, L, C, O

    elif timeframe == "Anual":
        # Año natural anterior
        año_ant = hist.index[-1].year - 1
        datos_año = hist[hist.index.year == año_ant]
        if datos_año.empty:
            # Si no hay datos del año anterior, usar los últimos 252 días
            datos_año = hist.iloc[-252:-1] if len(hist) > 252 else hist.iloc[:-1]
        if datos_año.empty:
            return None, None, None, None
        H = float(datos_año["High"].max())
        L = float(datos_año["Low"].min())
        C = float(datos_año["Close"].iloc[-1])
        O = float(datos_año["Open"].iloc[0])
        return H, L, C, O

    return None, None, None, None


# =============================================================================
# CÁLCULO DE PIVOT POINTS — 6 SISTEMAS
# =============================================================================

def pivot_clasico(H, L, C):
    PP = (H + L + C) / 3
    R1 = 2*PP - L
    R2 = PP + (H - L)
    R3 = H + 2*(PP - L)
    S1 = 2*PP - H
    S2 = PP - (H - L)
    S3 = L - 2*(H - PP)
    return {"PP": PP, "R1": R1, "R2": R2, "R3": R3, "S1": S1, "S2": S2, "S3": S3}


def pivot_woodie(H, L, C):
    PP = (H + L + 2*C) / 4
    R1 = 2*PP - L
    R2 = PP + (H - L)
    R3 = H + 2*(PP - L)
    R4 = R3 + (H - L)
    S1 = 2*PP - H
    S2 = PP - (H - L)
    S3 = L - 2*(H - PP)
    S4 = S3 - (H - L)
    return {"PP": PP, "R1": R1, "R2": R2, "R3": R3, "R4": R4,
            "S1": S1, "S2": S2, "S3": S3, "S4": S4}


def pivot_camarilla(H, L, C):
    rango = H - L
    R1 = C + rango * 1.0833
    R2 = C + rango * 1.1666
    R3 = C + rango * 1.2500
    R4 = C + rango * 1.5000
    S1 = C - rango * 1.0833
    S2 = C - rango * 1.1666
    S3 = C - rango * 1.2500
    S4 = C - rango * 1.5000
    return {"R1": R1, "R2": R2, "R3": R3, "R4": R4,
            "S1": S1, "S2": S2, "S3": S3, "S4": S4}


def pivot_demark(H, L, C, O):
    if C < O:
        X = H + 2*L + C
    elif C > O:
        X = 2*H + L + C
    else:
        X = H + L + 2*C
    PP = X / 4
    R1 = X/2 - L
    S1 = X/2 - H
    return {"PP": PP, "R1": R1, "S1": S1}


def pivot_fibonacci(H, L, C):
    PP = (H + L + C) / 3
    rango = H - L
    R1 = PP + 0.382 * rango
    R2 = PP + 0.618 * rango
    R3 = PP + 1.000 * rango
    S1 = PP - 0.382 * rango
    S2 = PP - 0.618 * rango
    S3 = PP - 1.000 * rango
    return {"PP": PP, "R1": R1, "R2": R2, "R3": R3, "S1": S1, "S2": S2, "S3": S3}


def pivot_midpoints(H, L, C):
    pp_data = pivot_clasico(H, L, C)
    PP = pp_data["PP"]
    S1 = pp_data["S1"]
    S2 = pp_data["S2"]
    R1 = pp_data["R1"]
    R2 = pp_data["R2"]
    R3 = pp_data["R3"]
    M1 = (S2 + S1) / 2
    M2 = (S1 + PP) / 2
    M3 = (PP + R1) / 2
    M4 = (R1 + R2) / 2
    M5 = (R2 + R3) / 2
    return {"PP": PP, "M1": M1, "M2": M2, "M3": M3, "M4": M4, "M5": M5,
            "R1": R1, "R2": R2, "R3": R3, "S1": S1, "S2": S2}


SISTEMAS_PIVOT = {
    "Clásico": pivot_clasico,
    "Woodie": pivot_woodie,
    "Camarilla": pivot_camarilla,
    "DeMark": pivot_demark,
    "Fibonacci": pivot_fibonacci,
    "Mid-Points": pivot_midpoints,
}

TIMEFRAMES = ["Intradía", "Diario", "Semanal", "Trimestral", "Anual"]


def calcular_todos_pivots(hist: pd.DataFrame, sistema: str):
    """Calcula pivots para todos los timeframes con el sistema seleccionado."""
    resultados = {}
    for tf in TIMEFRAMES:
        H, L, C, O = datos_sesion(hist, tf)
        if H is None:
            resultados[tf] = None
            continue
        try:
            if sistema == "Clásico":
                resultados[tf] = pivot_clasico(H, L, C)
            elif sistema == "Woodie":
                resultados[tf] = pivot_woodie(H, L, C)
            elif sistema == "Camarilla":
                resultados[tf] = pivot_camarilla(H, L, C)
            elif sistema == "DeMark":
                resultados[tf] = pivot_demark(H, L, C, O)
            elif sistema == "Fibonacci":
                resultados[tf] = pivot_fibonacci(H, L, C)
            elif sistema == "Mid-Points":
                resultados[tf] = pivot_midpoints(H, L, C)
            # Guardar datos base
            resultados[tf]["_H"] = H
            resultados[tf]["_L"] = L
            resultados[tf]["_C"] = C
        except Exception:
            resultados[tf] = None
    return resultados


# =============================================================================
# DETECCIÓN DE CONFLUENCIAS
# =============================================================================

def detectar_confluencias(resultados: dict, tolerancia: float = 0.20):
    """
    Agrupa niveles de diferentes timeframes que estén dentro de ±tolerancia.
    Retorna lista de confluencias ordenadas por precio.
    """
    todos_niveles = []
    for tf, niveles in resultados.items():
        if niveles is None:
            continue
        for clave, precio in niveles.items():
            if clave.startswith("_"):
                continue
            tipo = "R" if clave.startswith("R") else ("S" if clave.startswith("S") else "PP")
            todos_niveles.append({
                "precio": round(precio, 4),
                "timeframe": tf,
                "nivel": clave,
                "tipo": tipo,
            })

    if not todos_niveles:
        return []

    # Ordenar por precio
    todos_niveles.sort(key=lambda x: x["precio"])

    # Agrupar dentro de tolerancia
    grupos = []
    usados = set()
    for i, n1 in enumerate(todos_niveles):
        if i in usados:
            continue
        grupo = [n1]
        usados.add(i)
        for j, n2 in enumerate(todos_niveles):
            if j in usados:
                continue
            if abs(n1["precio"] - n2["precio"]) <= tolerancia:
                grupo.append(n2)
                usados.add(j)
        if len(grupo) >= 2:
            precio_medio = round(sum(n["precio"] for n in grupo) / len(grupo), 4)
            tfs_distintos = len(set(n["timeframe"] for n in grupo))
            if tfs_distintos >= 3:
                estrellas = "★★★"
            elif tfs_distintos >= 2:
                estrellas = "★★"
            else:
                estrellas = "★"
            grupos.append({
                "precio": precio_medio,
                "niveles": grupo,
                "estrellas": estrellas,
                "tfs_distintos": tfs_distintos,
            })

    # Ordenar desc por precio
    grupos.sort(key=lambda x: x["precio"], reverse=True)
    return grupos


# =============================================================================
# INDICADORES TÉCNICOS
# =============================================================================

def calcular_rsi(serie: pd.Series, periodo: int = 14) -> float:
    """RSI — cálculo manual compatible con cualquier versión."""
    if PANDAS_TA:
        try:
            rsi = ta.rsi(serie, length=periodo)
            if rsi is not None and not rsi.empty:
                return round(float(rsi.iloc[-1]), 2)
        except Exception:
            pass
    # Fallback manual
    delta = serie.diff()
    ganancias = delta.where(delta > 0, 0.0)
    perdidas = -delta.where(delta < 0, 0.0)
    avg_gan = ganancias.ewm(com=periodo - 1, min_periods=periodo).mean()
    avg_per = perdidas.ewm(com=periodo - 1, min_periods=periodo).mean()
    rs = avg_gan / avg_per
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def calcular_macd(serie: pd.Series):
    """Retorna (macd, señal, histograma) — últimos valores."""
    if PANDAS_TA:
        try:
            macd_df = ta.macd(serie)
            if macd_df is not None and not macd_df.empty:
                cols = macd_df.columns.tolist()
                return (
                    round(float(macd_df[cols[0]].iloc[-1]), 4),
                    round(float(macd_df[cols[2]].iloc[-1]), 4),
                    round(float(macd_df[cols[1]].iloc[-1]), 4),
                )
        except Exception:
            pass
    # Fallback manual
    ema12 = serie.ewm(span=12, adjust=False).mean()
    ema26 = serie.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    señal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - señal
    return round(float(macd.iloc[-1]), 4), round(float(señal.iloc[-1]), 4), round(float(hist.iloc[-1]), 4)


def calcular_bollinger(serie: pd.Series, periodo: int = 20, std_dev: float = 2.0):
    """Retorna (banda_superior, media, banda_inferior, %B)."""
    if PANDAS_TA:
        try:
            bb = ta.bbands(serie, length=periodo, std=std_dev)
            if bb is not None and not bb.empty:
                cols = bb.columns.tolist()
                sup = float(bb[cols[0]].iloc[-1])
                med = float(bb[cols[1]].iloc[-1])
                inf = float(bb[cols[2]].iloc[-1])
                pct_b = (serie.iloc[-1] - inf) / (sup - inf) * 100 if sup != inf else 50
                return round(sup, 4), round(med, 4), round(inf, 4), round(pct_b, 1)
        except Exception:
            pass
    # Fallback manual
    med = serie.rolling(periodo).mean()
    std = serie.rolling(periodo).std()
    sup = med + std_dev * std
    inf_b = med - std_dev * std
    ultimo = serie.iloc[-1]
    sup_v, med_v, inf_v = float(sup.iloc[-1]), float(med.iloc[-1]), float(inf_b.iloc[-1])
    pct_b = (ultimo - inf_v) / (sup_v - inf_v) * 100 if sup_v != inf_v else 50
    return round(sup_v, 4), round(med_v, 4), round(inf_v, 4), round(pct_b, 1)


def calcular_sma_ema(serie: pd.Series, periodos=(20, 50, 200)):
    """Retorna dict {periodo: (SMA, EMA)}."""
    resultado = {}
    for p in periodos:
        if len(serie) >= p:
            sma = round(float(serie.rolling(p).mean().iloc[-1]), 4)
            ema = round(float(serie.ewm(span=p, adjust=False).mean().iloc[-1]), 4)
            resultado[p] = (sma, ema)
    return resultado


def calcular_sar(hist: pd.DataFrame):
    """Parabolic SAR — retorna (valor_sar, tendencia)."""
    if PANDAS_TA:
        try:
            sar_df = ta.psar(hist["High"], hist["Low"], hist["Close"])
            if sar_df is not None and not sar_df.empty:
                cols = sar_df.columns.tolist()
                # pandas_ta devuelve PSARl (long) y PSARs (short)
                long_col = [c for c in cols if "PSARl" in c or "long" in c.lower()]
                short_col = [c for c in cols if "PSARs" in c or "short" in c.lower()]
                if long_col and short_col:
                    sar_long = sar_df[long_col[0]].iloc[-1]
                    sar_short = sar_df[short_col[0]].iloc[-1]
                    if not np.isnan(sar_long):
                        return round(float(sar_long), 4), "ALCISTA"
                    elif not np.isnan(sar_short):
                        return round(float(sar_short), 4), "BAJISTA"
        except Exception:
            pass
    # Fallback simplificado
    sar_v = float(hist["Low"].rolling(5).min().iloc[-1])
    precio = float(hist["Close"].iloc[-1])
    tendencia = "ALCISTA" if precio > sar_v else "BAJISTA"
    return round(sar_v, 4), tendencia


# =============================================================================
# ANÁLISIS DE VOLUMEN
# =============================================================================

def analisis_volumen(hist: pd.DataFrame):
    """
    Retorna dict con volumen actual, medias y clasificación.
    """
    if hist is None or len(hist) < 2:
        return None

    vol_hoy = float(hist["Volume"].iloc[-1])
    vol_10d = float(hist["Volume"].tail(11).iloc[:-1].mean()) if len(hist) > 10 else vol_hoy
    vol_3m = float(hist["Volume"].tail(63).mean()) if len(hist) > 20 else vol_hoy

    ratio_10d = (vol_hoy / vol_10d * 100) if vol_10d > 0 else 100
    ratio_3m = (vol_hoy / vol_3m * 100) if vol_3m > 0 else 100

    def clasificar(ratio):
        if ratio < 50:
            return "MUY BAJO", "🔴"
        elif ratio < 80:
            return "BAJO", "🟡"
        elif ratio < 120:
            return "NORMAL", "🟢"
        elif ratio < 200:
            return "ALTO", "🔵"
        else:
            return "MUY ALTO", "🟣"

    cls_10d, icono_10d = clasificar(ratio_10d)
    cls_3m, icono_3m = clasificar(ratio_3m)

    return {
        "volumen": vol_hoy,
        "media_10d": vol_10d,
        "media_3m": vol_3m,
        "ratio_10d": round(ratio_10d, 1),
        "ratio_3m": round(ratio_3m, 1),
        "clasificacion_10d": cls_10d,
        "icono_10d": icono_10d,
        "clasificacion_3m": cls_3m,
        "icono_3m": icono_3m,
    }


# =============================================================================
# SEMÁFORO GLOBAL
# =============================================================================

def calcular_semaforo(precio, pivots_diario, rsi_val, macd_val, macd_señal,
                      bb_sup, bb_inf, vol_data, sar_tendencia):
    """
    6 factores: precio vs PP, RSI, MACD, Bollinger %B, volumen, SAR.
    Retorna (color, puntuacion, factores_detalle).
    """
    factores = []
    puntos = 0

    # 1. Precio vs Pivot Point diario
    if pivots_diario and "PP" in pivots_diario:
        pp = pivots_diario["PP"]
        if precio > pp:
            factores.append(("Precio vs PP Diario", "✅ Por encima del PP", 1))
            puntos += 1
        else:
            factores.append(("Precio vs PP Diario", "❌ Por debajo del PP", 0))

    # 2. RSI
    if rsi_val is not None:
        if rsi_val < 30:
            factores.append(("RSI", f"⚠️ Sobrevendido ({rsi_val})", 0.5))
            puntos += 0.5
        elif rsi_val > 70:
            factores.append(("RSI", f"⚠️ Sobrecomprado ({rsi_val})", 0))
        elif rsi_val >= 50:
            factores.append(("RSI", f"✅ Positivo ({rsi_val})", 1))
            puntos += 1
        else:
            factores.append(("RSI", f"❌ Débil ({rsi_val})", 0))

    # 3. MACD vs Señal
    if macd_val is not None and macd_señal is not None:
        if macd_val > macd_señal:
            factores.append(("MACD", f"✅ MACD > Señal ({macd_val:.4f})", 1))
            puntos += 1
        else:
            factores.append(("MACD", f"❌ MACD < Señal ({macd_val:.4f})", 0))

    # 4. Bollinger %B
    if bb_sup is not None and bb_inf is not None and bb_sup != bb_inf:
        pct_b = (precio - bb_inf) / (bb_sup - bb_inf) * 100
        if 20 <= pct_b <= 80:
            factores.append(("Bollinger %B", f"✅ En zona central ({pct_b:.0f}%)", 1))
            puntos += 1
        elif pct_b < 20:
            factores.append(("Bollinger %B", f"⚠️ Cerca de banda inferior ({pct_b:.0f}%)", 0.5))
            puntos += 0.5
        else:
            factores.append(("Bollinger %B", f"⚠️ Cerca de banda superior ({pct_b:.0f}%)", 0.5))
            puntos += 0.5

    # 5. Volumen
    if vol_data:
        ratio = vol_data["ratio_10d"]
        if ratio >= 120:
            factores.append(("Volumen", f"✅ Por encima de media ({ratio:.0f}%)", 1))
            puntos += 1
        elif ratio >= 80:
            factores.append(("Volumen", f"✅ Volumen normal ({ratio:.0f}%)", 0.75))
            puntos += 0.75
        else:
            factores.append(("Volumen", f"❌ Volumen bajo ({ratio:.0f}%)", 0))

    # 6. Parabolic SAR
    if sar_tendencia:
        if sar_tendencia == "ALCISTA":
            factores.append(("Parabolic SAR", "✅ Tendencia alcista", 1))
            puntos += 1
        else:
            factores.append(("Parabolic SAR", "❌ Tendencia bajista", 0))

    max_puntos = len(factores)
    if max_puntos == 0:
        return "gris", 0, []

    pct = puntos / max_puntos * 100

    if pct >= 65:
        color = "verde"
    elif pct >= 40:
        color = "amarillo"
    else:
        color = "rojo"

    return color, round(pct, 0), factores


# =============================================================================
# DATOS FUNDAMENTALES
# =============================================================================

def bloque_fundamentales(info: dict, tipo: str = "accion"):
    """
    Retorna dict con datos fundamentales según tipo (accion / etf).
    """
    if not info:
        return {}

    if tipo == "accion":
        return {
            "Nombre": info.get("longName", info.get("shortName", "—")),
            "Sector": info.get("sector", "—"),
            "Industria": info.get("industry", "—"),
            "País": info.get("country", "—"),
            "Moneda": info.get("currency", "—"),
            "Capitalización": _fmt_numero(info.get("marketCap")),
            "PER": _fmt_ratio(info.get("trailingPE")),
            "PER forward": _fmt_ratio(info.get("forwardPE")),
            "P/Ventas": _fmt_ratio(info.get("priceToSalesTrailing12Months")),
            "P/Book": _fmt_ratio(info.get("priceToBook")),
            "EV/EBITDA": _fmt_ratio(info.get("enterpriseToEbitda")),
            "BPA (TTM)": _fmt_precio(info.get("trailingEps")),
            "BPA forward": _fmt_precio(info.get("forwardEps")),
            "Dividendo": _fmt_precio(info.get("dividendRate")),
            "Rentab. dividendo": _fmt_pct(info.get("dividendYield")),
            "Beta": _fmt_ratio(info.get("beta")),
            "52W Max": _fmt_precio(info.get("fiftyTwoWeekHigh")),
            "52W Min": _fmt_precio(info.get("fiftyTwoWeekLow")),
            "Objetivo analistas": _fmt_precio(info.get("targetMeanPrice")),
            "Nº analistas": str(info.get("numberOfAnalystOpinions", "—")),
        }
    else:  # ETF / índice
        return {
            "Nombre": info.get("longName", info.get("shortName", "—")),
            "Categoría": info.get("category", "—"),
            "Familia": info.get("fundFamily", "—"),
            "Moneda": info.get("currency", "—"),
            "Patrimonio": _fmt_numero(info.get("totalAssets")),
            "TER (expense ratio)": _fmt_pct(info.get("annualReportExpenseRatio") or info.get("expenseRatio")),
            "52W Max": _fmt_precio(info.get("fiftyTwoWeekHigh")),
            "52W Min": _fmt_precio(info.get("fiftyTwoWeekLow")),
            "Rentab. dividendo": _fmt_pct(info.get("dividendYield")),
            "Beta": _fmt_ratio(info.get("beta3Year") or info.get("beta")),
        }


def _fmt_numero(v):
    if v is None:
        return "—"
    if v >= 1e12:
        return f"{v/1e12:.2f}T"
    elif v >= 1e9:
        return f"{v/1e9:.2f}B"
    elif v >= 1e6:
        return f"{v/1e6:.2f}M"
    return f"{v:.0f}"


def _fmt_ratio(v):
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}x"
    except:
        return "—"


def _fmt_precio(v):
    if v is None:
        return "—"
    try:
        return f"{float(v):.4f}"
    except:
        return "—"


def _fmt_pct(v):
    if v is None:
        return "—"
    try:
        pct = float(v)
        if pct < 1:
            pct *= 100
        return f"{pct:.2f}%"
    except:
        return "—"


def detectar_tipo_activo(info: dict) -> str:
    qt = info.get("quoteType", "").lower()
    if qt in ("etf", "mutualfund", "index"):
        return "etf"
    return "accion"


# =============================================================================
# GENERACIÓN DE PDF
# =============================================================================

def generar_pdf(ticker: str, precio: float, sistema: str, resultados_pivots: dict,
                confluencias: list, semaforo: str, factores_semaforo: list,
                vol_data: dict, indicadores: dict, fundamentales: dict):
    """Genera un PDF con el análisis completo y retorna bytes."""

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm
    )

    styles = getSampleStyleSheet()
    azul = colors.HexColor("#1F4E79")
    azul_med = colors.HexColor("#2E75B6")
    azul_clar = colors.HexColor("#D5E8F0")
    verde = colors.HexColor("#2E7D32")
    rojo = colors.HexColor("#C62828")

    estilo_titulo = ParagraphStyle("titulo", parent=styles["Title"],
                                   fontSize=16, textColor=azul, spaceAfter=6)
    estilo_h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                                fontSize=11, textColor=azul_med, spaceAfter=4, spaceBefore=8)
    estilo_normal = ParagraphStyle("norm", parent=styles["Normal"],
                                   fontSize=8.5, spaceAfter=2)
    estilo_pie = ParagraphStyle("pie", parent=styles["Normal"],
                                fontSize=7, textColor=colors.grey,
                                alignment=TA_CENTER)

    historia = []
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Cabecera
    historia.append(Paragraph(f"📊 PivotAnalyzer — {ticker.upper()}", estilo_titulo))
    historia.append(Paragraph(
        f"Precio: <b>{precio:.4f}</b> | Sistema: {sistema} | Generado: {ahora}",
        estilo_normal
    ))
    historia.append(HRFlowable(width="100%", thickness=1, color=azul_med))
    historia.append(Spacer(1, 0.3*cm))

    # Semáforo
    historia.append(Paragraph("Semáforo Global", estilo_h2))
    color_texto = {"verde": "green", "amarillo": "orange", "rojo": "red"}.get(semaforo, "grey")
    emoji_sem = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(semaforo, "⚪")
    historia.append(Paragraph(
        f'<font color="{color_texto}"><b>{emoji_sem} {semaforo.upper()}</b></font>',
        estilo_normal
    ))
    for factor, descripcion, _ in factores_semaforo:
        historia.append(Paragraph(f"  • {factor}: {descripcion}", estilo_normal))
    historia.append(Spacer(1, 0.3*cm))

    # Pivot Points por timeframe
    historia.append(Paragraph(f"Pivot Points — Sistema {sistema}", estilo_h2))

    for tf in TIMEFRAMES:
        datos_tf = resultados_pivots.get(tf)
        if datos_tf is None:
            continue

        historia.append(Paragraph(f"<b>{tf}</b>", estilo_normal))

        tabla_datos = []
        niveles_orden = ["R3","R4","R3","R2","R1","PP","S1","S2","S3","S4","M1","M2","M3","M4","M5"]
        for nv in niveles_orden:
            if nv in datos_tf and not nv.startswith("_"):
                val = datos_tf[nv]
                dist = ((val - precio) / precio * 100) if precio else 0
                dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
                color_nv = "red" if nv.startswith("R") else ("blue" if nv == "PP" else "green")
                tabla_datos.append([
                    Paragraph(f'<font color="{color_nv}"><b>{nv}</b></font>', estilo_normal),
                    Paragraph(f"{val:.4f}", estilo_normal),
                    Paragraph(dist_str, estilo_normal),
                ])

        if tabla_datos:
            t = Table(tabla_datos, colWidths=[1.5*cm, 3*cm, 2.5*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), azul_clar),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F5F8FF")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]))
            historia.append(t)
        historia.append(Spacer(1, 0.15*cm))

    # Confluencias
    if confluencias:
        historia.append(Paragraph("Confluencias Multi-Timeframe", estilo_h2))
        conf_data = [["Precio", "Fiabilidad", "Niveles"]]
        for c in confluencias[:8]:
            niveles_str = ", ".join(f"{n['timeframe'][:3]} {n['nivel']}" for n in c["niveles"])
            conf_data.append([
                f"{c['precio']:.4f}",
                c["estrellas"],
                niveles_str[:60],
            ])
        t_conf = Table(conf_data, colWidths=[2.5*cm, 2*cm, 9*cm])
        t_conf.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), azul_med),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF9C4")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        historia.append(t_conf)
        historia.append(Spacer(1, 0.3*cm))

    # Indicadores técnicos
    historia.append(Paragraph("Indicadores Técnicos", estilo_h2))
    ind_data = []
    for k, v in indicadores.items():
        ind_data.append([k, str(v)])
    t_ind = Table(ind_data, colWidths=[5*cm, 8*cm])
    t_ind.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F5F8FF")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    historia.append(t_ind)

    # Fundamentales
    if fundamentales:
        historia.append(Paragraph("Datos Fundamentales", estilo_h2))
        fund_data = [[k, v] for k, v in fundamentales.items() if v != "—"]
        if fund_data:
            t_fund = Table(fund_data, colWidths=[5*cm, 8*cm])
            t_fund.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F5F8FF")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]))
            historia.append(t_fund)

    # Volumen
    if vol_data:
        historia.append(Paragraph("Análisis de Volumen", estilo_h2))
        vol_tabla = [
            ["Volumen sesión", _fmt_numero(vol_data["volumen"])],
            ["Media 10 sesiones", _fmt_numero(vol_data["media_10d"])],
            ["Media 3 meses", _fmt_numero(vol_data["media_3m"])],
            ["Ratio vs 10d", f"{vol_data['ratio_10d']:.1f}% — {vol_data['clasificacion_10d']}"],
            ["Ratio vs 3m", f"{vol_data['ratio_3m']:.1f}% — {vol_data['clasificacion_3m']}"],
        ]
        t_vol = Table(vol_tabla, colWidths=[5*cm, 8*cm])
        t_vol.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F5F8FF")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        historia.append(t_vol)

    # Pie de página
    historia.append(Spacer(1, 0.5*cm))
    historia.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    historia.append(Paragraph(
        "Análisis educativo. No constituye asesoramiento de inversión regulado bajo MiFID II. "
        "Datos con retraso ~15 min vía Yahoo Finance. PivotAnalyzer v1.0 — Scriptum",
        estilo_pie
    ))

    doc.build(historia)
    return buf.getvalue()


# =============================================================================
# PANEL DE ADMINISTRACIÓN — GESTIÓN DE USUARIOS
# =============================================================================

def panel_admin():
    st.markdown("## ⚙️ Gestión de Usuarios")

    try:
        usuarios = db_select("usuarios")
        usuarios.sort(key=lambda x: x.get("creado_en", ""))
    except Exception as e:
        st.error(f"Error al obtener usuarios: {e}")
        return

    st.markdown(f"**{len(usuarios)} usuarios registrados**")

    for u in usuarios:
        col1, col2, col3, col4, col5 = st.columns([2, 2, 1.5, 1, 1])
        with col1:
            st.markdown(f"**{u['username']}**  \n{u.get('nombre','')}")
        with col2:
            st.markdown(f"`{u.get('rol','usuario')}`  \n{u.get('ultimo_acceso','—')[:16] if u.get('ultimo_acceso') else '—'}")
        with col3:
            estado = "✅ Activo" if u.get("activo") else "⛔ Inactivo"
            st.markdown(estado)
        with col4:
            if u.get("rol") != "superadmin":
                if u.get("activo"):
                    if st.button("Desactivar", key=f"des_{u['id']}"):
                        db_update("usuarios", {"activo": False}, "id", u["id"])
                        st.rerun()
                else:
                    if st.button("Activar", key=f"act_{u['id']}"):
                        db_update("usuarios", {"activo": True}, "id", u["id"])
                        st.rerun()
        with col5:
            if u.get("rol") != "superadmin":
                if st.button("🗑️", key=f"del_{u['id']}", help="Eliminar usuario"):
                    db_delete("usuarios", "id", u["id"])
                    st.rerun()

    st.divider()

    # Crear nuevo usuario
    st.markdown("### ➕ Nuevo usuario")
    with st.form("nuevo_usuario"):
        col1, col2 = st.columns(2)
        with col1:
            nuevo_user = st.text_input("Username")
            nuevo_nombre = st.text_input("Nombre completo")
        with col2:
            nuevo_pass = st.text_input("Contraseña", type="password")
            nuevo_rol = st.selectbox("Rol", ["usuario", "admin"])
        submitted = st.form_submit_button("Crear usuario")
        if submitted:
            if nuevo_user and nuevo_pass and nuevo_nombre:
                try:
                    ph = hash_password(nuevo_pass)
                    db_insert("usuarios", {
                        "username": nuevo_user,
                        "nombre": nuevo_nombre,
                        "password_hash": ph,
                        "rol": nuevo_rol,
                        "activo": True,
                    })
                    st.success(f"✅ Usuario '{nuevo_user}' creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear usuario: {e}")
            else:
                st.warning("Completa todos los campos.")

    st.divider()

    # Cambiar contraseña
    st.markdown("### 🔑 Cambiar contraseña")
    with st.form("cambiar_pass"):
        users_list = [u["username"] for u in usuarios]
        sel_user = st.selectbox("Usuario", users_list)
        nueva_pass = st.text_input("Nueva contraseña", type="password")
        confirmar = st.text_input("Confirmar contraseña", type="password")
        submitted2 = st.form_submit_button("Cambiar contraseña")
        if submitted2:
            if nueva_pass and nueva_pass == confirmar:
                try:
                    ph = hash_password(nueva_pass)
                    db_update("usuarios", {"password_hash": ph}, "username", sel_user)
                    st.success(f"✅ Contraseña de '{sel_user}' actualizada.")
                except Exception as e:
                    st.error(f"Error: {e}")
            elif nueva_pass != confirmar:
                st.error("Las contraseñas no coinciden.")
            else:
                st.warning("Introduce la nueva contraseña.")


# =============================================================================
# RENDERIZADO DE TABLA PIVOT POINTS
# =============================================================================

def render_tabla_pivots(tf_nombre: str, niveles: dict, precio_actual_val: float):
    """Muestra la tabla de un timeframe con colores y distancias."""
    if niveles is None:
        st.caption(f"*{tf_nombre}: sin datos*")
        return

    H = niveles.get("_H", "—")
    L = niveles.get("_L", "—")
    C = niveles.get("_C", "—")

    with st.expander(f"📅 {tf_nombre}  (H:{H:.2f} L:{L:.2f} C:{C:.2f})" if isinstance(H, float) else f"📅 {tf_nombre}", expanded=(tf_nombre == "Diario")):
        orden = ["R4","R3","R2","R1","PP","M5","M4","M3","M2","M1","S1","S2","S3","S4"]
        filas = []
        for nv in orden:
            if nv not in niveles or nv.startswith("_"):
                continue
            val = niveles[nv]
            dist = ((val - precio_actual_val) / precio_actual_val * 100) if precio_actual_val else 0
            dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
            if nv.startswith("R"):
                etiqueta = f"🔴 {nv}"
            elif nv == "PP":
                etiqueta = f"🔵 PP"
            elif nv.startswith("M"):
                etiqueta = f"⚪ {nv}"
            else:
                etiqueta = f"🟢 {nv}"
            filas.append({"Nivel": etiqueta, "Precio": f"{val:.4f}", "Distancia": dist_str})

        if filas:
            df_tabla = pd.DataFrame(filas)
            st.dataframe(df_tabla, use_container_width=True, hide_index=True,
                         column_config={
                             "Nivel": st.column_config.TextColumn(width="small"),
                             "Precio": st.column_config.TextColumn(width="small"),
                             "Distancia": st.column_config.TextColumn(width="small"),
                         })


# =============================================================================
# PANTALLA PRINCIPAL — ANÁLISIS
# =============================================================================

def pantalla_analisis():
    usuario = st.session_state["usuario"]
    es_admin = usuario.get("rol") in ("superadmin", "admin")
    es_superadmin = usuario.get("rol") == "superadmin"

    # Header
    col_t, col_u = st.columns([4, 1])
    with col_t:
        st.markdown("## 📊 PivotAnalyzer")
    with col_u:
        st.markdown(f"*{usuario.get('nombre', usuario.get('username'))}*")
        if st.button("Salir", key="logout"):
            del st.session_state["usuario"]
            st.rerun()

    # Navegación
    tabs_list = ["📈 Análisis"]
    if es_superadmin:
        tabs_list.append("⚙️ Usuarios")
    tabs_list.append("📖 Ayuda")

    tab_objs = st.tabs(tabs_list)
    tab_analisis = tab_objs[0]

    if es_superadmin and len(tab_objs) >= 2:
        tab_admin = tab_objs[1]
        tab_ayuda = tab_objs[2]
    else:
        tab_admin = None
        tab_ayuda = tab_objs[-1]

    # ---- TAB ANÁLISIS ----
    with tab_analisis:
        # Controles superiores
        col1, col2, col3, col4 = st.columns([2.5, 2, 1.5, 1])
        with col1:
            ticker_input = st.text_input("Ticker", value="NTGY.MC", placeholder="NTGY.MC, AAPL, SPY...",
                                          label_visibility="collapsed").upper().strip()
        with col2:
            sistema_sel = st.selectbox("Sistema Pivot", list(SISTEMAS_PIVOT.keys()),
                                        label_visibility="collapsed")
        with col3:
            tolerancia = st.number_input("Tolerancia confluencia (€/$)", value=0.20, step=0.05,
                                          min_value=0.01, max_value=2.0, format="%.2f",
                                          label_visibility="collapsed")
        with col4:
            analizar = st.button("🔍 Analizar", type="primary")

        # Upload de imagen
        img_upload = st.file_uploader("📷 Adjuntar captura (opcional)", type=["png","jpg","jpeg"],
                                       label_visibility="collapsed")

        if not analizar and "ultimo_ticker" not in st.session_state:
            st.info("Introduce un ticker y pulsa **Analizar**. Ejemplos: `NTGY.MC`, `IBE.MC`, `AAPL`, `SPY`")
            st.caption("Los datos tienen un retraso aproximado de 15 minutos (Yahoo Finance).")
            return

        # Si pulsa analizar, guardar ticker
        if analizar:
            st.session_state["ultimo_ticker"] = ticker_input
            st.session_state["ultimo_sistema"] = sistema_sel
            st.session_state["ultima_tolerancia"] = tolerancia

        ticker_activo = st.session_state.get("ultimo_ticker", ticker_input)
        sistema_activo = st.session_state.get("ultimo_sistema", sistema_sel)
        tol_activa = st.session_state.get("ultima_tolerancia", tolerancia)

        # ---- OBTENER DATOS ----
        with st.spinner(f"Obteniendo datos de {ticker_activo}..."):
            hist, info = obtener_datos(ticker_activo)

        if hist is None or hist.empty:
            st.error(f"No se pudieron obtener datos para **{ticker_activo}**. Verifica el ticker.")
            return

        precio = precio_actual(hist)
        if precio is None:
            st.error("Sin datos de precio.")
            return

        tipo_activo = detectar_tipo_activo(info)
        nombre = info.get("longName") or info.get("shortName") or ticker_activo

        # ---- PRECIO ACTUAL ----
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        cierre_ant = float(hist["Close"].iloc[-2]) if len(hist) > 1 else precio
        cambio = precio - cierre_ant
        cambio_pct = (cambio / cierre_ant * 100) if cierre_ant else 0
        var_str = f"{cambio:+.4f} ({cambio_pct:+.2f}%)"

        with col_p1:
            st.metric("Precio", f"{precio:.4f}", delta=var_str)
        with col_p2:
            h52 = info.get("fiftyTwoWeekHigh")
            l52 = info.get("fiftyTwoWeekLow")
            st.metric("52W Máx / Mín", f"{h52:.2f} / {l52:.2f}" if h52 and l52 else "—")
        with col_p3:
            vol_hoy = float(hist["Volume"].iloc[-1])
            st.metric("Volumen hoy", _fmt_numero(vol_hoy))
        with col_p4:
            currency = info.get("currency", "")
            st.metric("Moneda", currency if currency else "—")

        st.caption(f"**{nombre}** · {tipo_activo.upper()} · Datos: ~15 min de retraso")

        st.divider()

        # ---- CALCULAR PIVOTS ----
        resultados_pivots = calcular_todos_pivots(hist, sistema_activo)
        pivots_diario = resultados_pivots.get("Diario")

        # ---- INDICADORES ----
        cierre_serie = hist["Close"]
        rsi_val = calcular_rsi(cierre_serie)
        macd_val, macd_señal, macd_hist_val = calcular_macd(cierre_serie)
        bb_sup, bb_med, bb_inf, pct_b = calcular_bollinger(cierre_serie)
        medias = calcular_sma_ema(cierre_serie)
        sar_val, sar_tend = calcular_sar(hist)

        indicadores_dict = {
            "RSI (14)": f"{rsi_val}" + (" 🔴 Sobrecomprado" if rsi_val > 70 else " 🟢 Sobrevendido" if rsi_val < 30 else " ⚪ Neutro"),
            "MACD": f"{macd_val:.4f}",
            "MACD Señal": f"{macd_señal:.4f}",
            "MACD Histograma": f"{macd_hist_val:.4f}" + (" ↑" if macd_hist_val > 0 else " ↓"),
            "Bollinger Superior": f"{bb_sup:.4f}",
            "Bollinger Media": f"{bb_med:.4f}",
            "Bollinger Inferior": f"{bb_inf:.4f}",
            "Bollinger %B": f"{pct_b:.1f}%",
            "Parabolic SAR": f"{sar_val:.4f} ({sar_tend})",
        }
        for p, (sma, ema) in sorted(medias.items()):
            pos_sma = "↑" if precio > sma else "↓"
            pos_ema = "↑" if precio > ema else "↓"
            indicadores_dict[f"SMA {p}"] = f"{sma:.4f} {pos_sma}"
            indicadores_dict[f"EMA {p}"] = f"{ema:.4f} {pos_ema}"

        # ---- VOLUMEN ----
        vol_data = analisis_volumen(hist)

        # ---- SEMÁFORO ----
        color_sem, pct_sem, factores_sem = calcular_semaforo(
            precio, pivots_diario, rsi_val, macd_val, macd_señal,
            bb_sup, bb_inf, vol_data, sar_tend
        )

        # ---- CONFLUENCIAS ----
        confluencias = detectar_confluencias(resultados_pivots, tolerancia=tol_activa)

        # ---- FUNDAMENTALES ----
        fundamentales = bloque_fundamentales(info, tipo_activo)

        # ======== LAYOUT PRINCIPAL ========

        col_izq, col_der = st.columns([3, 2])

        with col_izq:
            st.markdown("### Pivot Points — " + sistema_activo)
            for tf in TIMEFRAMES:
                render_tabla_pivots(tf, resultados_pivots.get(tf), precio)

        with col_der:
            # Semáforo
            st.markdown("### Semáforo Global")
            emoji_color = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(color_sem, "⚪")
            css_class = f"semaforo-{color_sem}"
            st.markdown(f'<span class="{css_class}">{emoji_color} {color_sem.upper()} — {pct_sem:.0f}%</span>',
                        unsafe_allow_html=True)
            for factor, descripcion, _ in factores_sem:
                st.caption(f"• **{factor}**: {descripcion}")

            st.divider()

            # Indicadores compactos
            st.markdown("### Indicadores Técnicos")
            col_i1, col_i2 = st.columns(2)
            with col_i1:
                st.metric("RSI 14", rsi_val,
                          delta="Sobrecomprado" if rsi_val > 70 else ("Sobrevendido" if rsi_val < 30 else "Neutro"))
                st.metric("MACD", f"{macd_val:.4f}", delta=f"Hist: {macd_hist_val:.4f}")
                st.metric("SAR", sar_tend, delta=f"{sar_val:.4f}")
            with col_i2:
                st.metric("Bollinger %B", f"{pct_b:.1f}%")
                for p_m in [20, 50]:
                    if p_m in medias:
                        sma, ema = medias[p_m]
                        diff = precio - sma
                        st.metric(f"SMA {p_m}", f"{sma:.4f}",
                                  delta=f"{diff:+.4f} ({diff/sma*100:+.1f}%)")

            st.divider()

            # Volumen
            if vol_data:
                st.markdown("### Volumen")
                col_v1, col_v2 = st.columns(2)
                with col_v1:
                    st.metric("Ratio vs 10d",
                              f"{vol_data['ratio_10d']:.0f}%",
                              delta=vol_data['clasificacion_10d'])
                with col_v2:
                    st.metric("Ratio vs 3m",
                              f"{vol_data['ratio_3m']:.0f}%",
                              delta=vol_data['clasificacion_3m'])
                st.caption(f"Vol. hoy: {_fmt_numero(vol_data['volumen'])} | "
                           f"Media 10d: {_fmt_numero(vol_data['media_10d'])} | "
                           f"Media 3m: {_fmt_numero(vol_data['media_3m'])}")

            st.divider()

            # Confluencias
            if confluencias:
                st.markdown("### Confluencias Multi-Timeframe")
                for c in confluencias:
                    dist = ((c["precio"] - precio) / precio * 100) if precio else 0
                    dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
                    niveles_str = " | ".join(f"{n['timeframe'][:3]} {n['nivel']}" for n in c["niveles"][:4])
                    st.markdown(
                        f"**{c['precio']:.4f}** {c['estrellas']} &nbsp; `{dist_str}` "
                        f"<small>{niveles_str}</small>",
                        unsafe_allow_html=True
                    )
            else:
                st.markdown("### Confluencias")
                st.caption(f"Sin confluencias dentro de ±{tol_activa:.2f}€")

        # Imagen adjunta
        if img_upload:
            st.divider()
            st.markdown("### 📷 Captura adjunta")
            st.image(img_upload, use_column_width=True)

        st.divider()

        # Fundamentales
        if fundamentales:
            st.markdown("### Datos Fundamentales")
            fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
            cols_f = st.columns(3)
            for i, (k, v) in enumerate(fund_items):
                with cols_f[i % 3]:
                    st.metric(k, v)

        st.divider()

        # Descarga PDF
        st.markdown("### 📥 Exportar")
        col_pdf1, col_pdf2 = st.columns([1, 3])
        with col_pdf1:
            if st.button("Generar PDF"):
                with st.spinner("Generando PDF..."):
                    pdf_bytes = generar_pdf(
                        ticker=ticker_activo,
                        precio=precio,
                        sistema=sistema_activo,
                        resultados_pivots=resultados_pivots,
                        confluencias=confluencias,
                        semaforo=color_sem,
                        factores_semaforo=factores_sem,
                        vol_data=vol_data,
                        indicadores=indicadores_dict,
                        fundamentales=fundamentales,
                    )
                nombre_pdf = f"{ticker_activo}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                st.download_button(
                    label="📄 Descargar PDF",
                    data=pdf_bytes,
                    file_name=nombre_pdf,
                    mime="application/pdf",
                )

    # ---- TAB ADMIN ----
    if es_superadmin and tab_admin:
        with tab_admin:
            panel_admin()

    # ---- TAB AYUDA ----
    with tab_ayuda:
        st.markdown("### Guía rápida de Pivot Points")
        st.markdown("""
**Pivot Point (PP)** — Nivel de equilibrio calculado con datos de la sesión anterior (máx, mín, cierre).

**Resistencias (R1-R4)** — Por encima del PP. El precio tiende a frenarse o rebotar.

**Soportes (S1-S4)** — Por debajo del PP. Zonas de posible rebote al alza.

**Confluencia** — Cuando niveles de distintos timeframes coinciden en ±{tol} €. Mayor fiabilidad.

---
**Sistemas disponibles:**
- **Clásico** — El más universal. Base para todos los demás.
- **Woodie** — Doble peso al cierre. Mejor en días con gap.
- **Camarilla** — 8 niveles muy cerca del precio. Operativa intradía.
- **DeMark** — Condicional según dirección del día anterior. 1 sola resistencia y 1 soporte.
- **Fibonacci** — Usa ratios 0.382, 0.618, 1.000. Correcciones en tendencia.
- **Mid-Points** — Niveles intermedios entre los Clásicos. Lateralizaciones.

---
**Semáforo global:**
- 🟢 Verde (≥65%) — Sesgo técnico positivo
- 🟡 Amarillo (40-65%) — Sin sesgo claro
- 🔴 Rojo (<40%) — Sesgo técnico negativo

Factores: Precio vs PP Diario · RSI · MACD · Bollinger %B · Volumen · Parabolic SAR

---
*Análisis educativo. No constituye asesoramiento de inversión regulado bajo MiFID II (Directiva 2014/65/UE).*
        """)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main():
    if "usuario" not in st.session_state:
        pantalla_login()
    else:
        pantalla_analisis()


if __name__ == "__main__":
    main()
