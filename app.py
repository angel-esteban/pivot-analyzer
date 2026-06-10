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

# HTTP para ECB Statistical Data Warehouse (sin API key)
import requests

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
    [data-testid="stMetricValue"] { font-size: 1.25rem !important; line-height: 1.3 !important; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.72rem !important; }
    /* Datos Fundamentales + Indicadores Técnicos + Volumen — valores pequeños, títulos más grandes */
    .fund-metrics [data-testid="stMetricValue"],
    .ind-metrics [data-testid="stMetricValue"] { font-size: 0.95rem !important; line-height: 1.2 !important; font-weight: 600 !important; }
    .fund-metrics [data-testid="stMetricLabel"],
    .ind-metrics [data-testid="stMetricLabel"] { font-size: 0.82rem !important; font-weight: 500 !important; color: #374151 !important; }
    /* Valores de selectbox y number_input más grandes */
    [data-testid="stSelectbox"] div[data-baseweb="select"] span,
    [data-testid="stSelectbox"] div[data-baseweb="select"] div { font-size: 1.05rem !important; }
    [data-testid="stNumberInput"] input { font-size: 1.05rem !important; }
    .stButton button { width: 100%; }
    @media (max-width: 640px) {
        .block-container { padding: 0.3rem 0.2rem 2rem; }
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# TOOLTIPS — Explicaciones para no financieros
# =============================================================================

TOOLTIPS = {
    "Precio":            "Último precio de cierre (~15 min de retraso). Refleja el valor al que cerró el activo en la última sesión.",
    "52W Máx / Mín":     "Precio máximo y mínimo registrados en los últimos 52 semanas (1 año). Indica el rango de fluctuación anual.",
    "Volumen hoy":       "Número de acciones o participaciones negociadas en la sesión actual. Un volumen alto indica mayor interés del mercado.",
    "Moneda":            "Divisa en la que cotiza el activo en su mercado de origen.",
    "Beta":              "Sensibilidad del activo respecto al mercado de referencia. Beta > 1: más volátil que el índice. Beta < 1: menos volátil. Beta < 0: correlación inversa con el mercado.",
    "RSI 14":            "Relative Strength Index (14 sesiones): mide si el activo está sobrecomprado (>70) o sobrevendido (<30). Entre 30-70 es zona neutra.",
    "MACD":              "Moving Average Convergence Divergence: diferencia entre dos medias móviles. Si supera su señal, la tendencia es alcista; si está por debajo, bajista.",
    "SAR":               "Parabolic Stop And Reverse: señal de reversión de tendencia. 'Alcista' = precio por encima del SAR. 'Bajista' = precio por debajo.",
    "Bollinger %B":      "Posición del precio dentro de las Bandas de Bollinger. 0% = banda inferior (sobrevendido). 50% = zona central. 100% = banda superior (sobrecomprado).",
    "SMA 20":            "Media Móvil Simple de 20 sesiones (~1 mes). Filtra el ruido a corto plazo y muestra la tendencia reciente.",
    "SMA 50":            "Media Móvil Simple de 50 sesiones (~2,5 meses). Indicador de tendencia de medio plazo ampliamente seguido por analistas.",
    "Ratio vs 10d":      "Volumen de hoy comparado con la media de las últimas 10 sesiones. Por encima del 100% indica actividad superior a la media reciente.",
    "Ratio vs 3m":       "Volumen de hoy comparado con la media de los últimos 3 meses. Útil para detectar movimientos inusuales respecto al comportamiento habitual.",
    "Nombre":            "Nombre completo de la empresa o fondo cotizado.",
    "Sector":            "Sector económico al que pertenece la empresa según la clasificación estándar de mercado.",
    "Industria":         "Industria específica dentro del sector. Permite comparar empresas con actividades similares.",
    "País":              "País donde está domiciliada legalmente la empresa y donde cotiza principalmente.",
    "Capitalización":    "Valor total de mercado = precio × número de acciones en circulación. Indica el tamaño de la compañía.",
    "PER":               "Price-to-Earnings (precio/beneficio): años que tardarías en recuperar la inversión si el beneficio fuera constante. Un PER más bajo puede indicar que la acción está más barata.",
    "PER forward":       "PER calculado con el beneficio estimado para los próximos 12 meses. Refleja las expectativas del mercado sobre el crecimiento futuro.",
    "P/Ventas":          "Precio sobre ventas: compara la capitalización de mercado con los ingresos anuales. Útil cuando la empresa no tiene beneficios todavía.",
    "P/Book":            "Precio sobre valor en libros: compara el precio de mercado con el valor contable de los activos netos. Por debajo de 1 puede indicar infravaloración.",
    "EV/EBITDA":         "Enterprise Value sobre EBITDA: medida de valoración independiente de la estructura financiera. Permite comparar empresas con distintos niveles de deuda.",
    "BPA":               "Beneficio Por Acción (últimos 12 meses): beneficio neto dividido entre el número de acciones. Es la base del cálculo del PER.",
    "BPA (TTM)":         "Beneficio Por Acción (Trailing Twelve Months — últimos 12 meses reales): beneficio neto dividido entre el número de acciones en circulación. Es la base del cálculo del PER.",
    "BPA forward":       "Beneficio Por Acción estimado para los próximos 12 meses según el consenso de analistas.",
    "Dividendo":         "Importe del dividendo anual por acción en la moneda del activo. Es la parte del beneficio que la empresa reparte a sus accionistas.",
    "Rentab. dividendo": "Dividendo anual dividido entre el precio actual, en porcentaje. Indica el 'rendimiento por cupón' que ofrece el activo vía dividendos.",
    "Beta":              "Medida de volatilidad respecto al mercado. Beta=1 → se mueve igual que el índice. Beta>1 → más volátil que el mercado. Beta<1 → más estable.",
    "52W Max":           "Precio máximo registrado en los últimos 52 semanas (1 año).",
    "52W Min":           "Precio mínimo registrado en los últimos 52 semanas (1 año).",
    "Obj. analistas":    "Precio objetivo medio fijado por los analistas que cubren el valor. Indica dónde esperan que cotice en los próximos 12 meses.",
    "Objetivo analistas":"Precio objetivo medio fijado por los analistas que cubren el valor. Indica dónde esperan que cotice en los próximos 12 meses.",
    "Nº analistas":      "Número de analistas que siguen el valor y han publicado una estimación de precio objetivo.",
    "AUM":               "Assets Under Management: patrimonio total gestionado por el ETF. Mayor AUM implica mayor liquidez y menor riesgo de cierre del fondo.",
    "TER":               "Total Expense Ratio: coste anual total del ETF expresado en porcentaje. Se descuenta automáticamente del rendimiento del fondo.",
    "Índice replicado":  "Índice de referencia que el ETF intenta replicar. Define qué activos componen el fondo y en qué proporción.",
}


# =============================================================================
# DATOS PARA DESPLEGABLE DE TICKERS
# =============================================================================

# IBEX 35 — Composición aproximada (revisiones semestrales del índice)
IBEX_35 = {
    "Acciona":                      "ANA.MC",
    "Acciona Energías Renovables":  "ANE.MC",
    "Acerinox":                     "ACX.MC",
    "ACS":                          "ACS.MC",
    "Aena":                         "AENA.MC",
    "Amadeus IT":                   "AMS.MC",
    "ArcelorMittal":                "MTS.MC",
    "Banco Santander":              "SAN.MC",
    "BBVA":                         "BBVA.MC",
    "CaixaBank":                    "CABK.MC",
    "Cellnex Telecom":              "CLNX.MC",
    "Colonial (Inmob.)":            "COL.MC",
    "Enagás":                       "ENG.MC",
    "Endesa":                       "ELE.MC",
    "Ferrovial":                    "FER.MC",
    "Fluidra":                      "FDR.MC",
    "Grifols":                      "GRF.MC",
    "IAG":                          "IAG.MC",
    "Iberdrola":                    "IBE.MC",
    "Inditex":                      "ITX.MC",
    "Indra":                        "IDR.MC",
    "Laboratorios Rovi":            "ROVI.MC",
    "Logista":                      "LOG.MC",
    "MAPFRE":                       "MAP.MC",
    "Meliá Hotels":                 "MEL.MC",
    "Merlin Properties":            "MRL.MC",
    "Naturgy":                      "NTGY.MC",
    "Puig Brands":                  "PUIG.MC",
    "Redeia (REE)":                 "REE.MC",
    "Repsol":                       "REP.MC",
    "Sacyr":                        "SCYR.MC",
    "Solaria":                      "SLR.MC",
    "Telefónica":                   "TEF.MC",
    "Unicaja Banco":                "UNI.MC",
    "Vidrala":                      "VID.MC",
}

# Eurostoxx 50 — Principales componentes (sufijos por país de cotización)
EUROSTOXX_50 = {
    "ASML Holding":         "ASML.AS",
    "SAP":                  "SAP.DE",
    "LVMH":                 "MC.PA",
    "Siemens":              "SIE.DE",
    "Allianz":              "ALV.DE",
    "TotalEnergies":        "TTE.PA",
    "Sanofi":               "SAN.PA",
    "L'Oréal":              "OR.PA",
    "Schneider Electric":   "SU.PA",
    "Airbus":               "AIR.PA",
    "Iberdrola":            "IBE.MC",
    "Deutsche Telekom":     "DTE.DE",
    "Inditex":              "ITX.MC",
    "Enel":                 "ENEL.MI",
    "AXA":                  "CS.PA",
    "BNP Paribas":          "BNP.PA",
    "Intesa Sanpaolo":      "ISP.MI",
    "Munich Re":            "MUV2.DE",
    "BBVA":                 "BBVA.MC",
    "Volkswagen (pref.)":   "VOW3.DE",
    "Infineon":             "IFX.DE",
    "Ferrari":              "RACE.MI",
    "Air Liquide":          "AI.PA",
    "Siemens Energy":       "ENR.DE",
    "Adyen":                "ADYEN.AS",
    "ING Group":            "INGA.AS",
    "Hermès":               "RMS.PA",
    "EssilorLuxottica":     "EL.PA",
    "Vinci":                "DG.PA",
    "UniCredit":            "UCG.MI",
    "Deutsche Börse":       "DB1.DE",
    "Safran":               "SAF.PA",
    "Engie":                "ENGI.PA",
    "Banco Santander":      "SAN.MC",
    "Kering":               "KER.PA",
    "Pernod Ricard":        "RI.PA",
    "Bayer":                "BAYN.DE",
    "Vonovia":              "VNA.DE",
    "Dassault Systèmes":    "DSY.PA",
    "Nokia":                "NOKIA.HE",
    "ENI":                  "ENI.MI",
    "BASF":                 "BAS.DE",
    "Stellantis":           "STLAM.MI",
    "Mercedes-Benz":        "MBG.DE",
    "Münchener Rück":       "MUV2.DE",
    "Amadeus IT":           "AMS.MC",
    "STMicroelectronics":   "STMPA.PA",
    "CRH":                  "CRH.L",
    "Koninklijke Philips":  "PHIA.AS",
}

# ETFs UCITS — Selección curada accesible desde España (via DeGiro, IB, Trade Republic)
# Nota: tickers en Euronext Amsterdam (.AS), Xetra (.DE) o Londres (.L)
ETFS_UCITS = {
    "🌐 Renta Variable Global": {
        "iShares Core MSCI World (Acc) — IWDA":    "IWDA.AS",
        "Vanguard FTSE All-World (Dist) — VWRL":   "VWRL.AS",
        "Vanguard FTSE All-World (Acc) — VWCE":    "VWCE.DE",
        "Xtrackers MSCI World (Acc) — XDWD":       "XDWD.DE",
        "Amundi Prime All Country World — PRNA":   "PRNA.PA",
        "iShares MSCI ACWI (Acc) — IUSQ":          "IUSQ.DE",
    },
    "🇺🇸 Renta Variable EEUU": {
        "iShares Core S&P 500 (Acc) — SXR8":       "SXR8.DE",
        "Vanguard S&P 500 (Dist) — VUSA":          "VUSA.AS",
        "iShares S&P 500 (Dist) — IUSA":           "IUSA.AS",
        "Invesco S&P 500 (Acc) — SPYL":            "SPYL.DE",
        "iShares Nasdaq 100 (Acc) — CNDX":         "CNDX.L",
        "Xtrackers Nasdaq 100 (Acc) — XNAS":       "XNAS.DE",
    },
    "🇪🇺 Renta Variable Europa": {
        "iShares Core Eurostoxx 50 (Acc) — CS51":  "CS51.DE",
        "iShares STOXX Europe 600 (Acc) — EXSA":   "EXSA.DE",
        "Vanguard FTSE Dev. Europe (Acc) — VEUR":  "VEUR.AS",
        "SPDR MSCI Europe (Acc) — SPEU":           "SPEU.DE",
        "Amundi MSCI Europe (Acc) — CE9":          "CE9.PA",
    },
    "🌏 Renta Variable Emergentes": {
        "iShares Core MSCI EM IMI (Acc) — IS3N":   "IS3N.DE",
        "Vanguard FTSE Emerging Mkts (Acc) — VFEM":"VFEM.AS",
        "Amundi MSCI EM (Acc) — PAEM":             "PAEM.PA",
        "iShares MSCI China (Acc) — CNYA":         "CNYA.L",
    },
    "📉 Renta Fija": {
        "iShares Core Euro Govt Bond (Acc) — IEGA":"IEGA.AS",
        "iShares € Corp Bond (Acc) — IEAC":        "IEAC.AS",
        "Vanguard EUR Eurozone Govt Bond — VETY":  "VETY.AS",
        "Amundi € Aggregate Bond (Acc) — EAGA":    "EAGA.PA",
        "iShares $ Treasury 7-10y EUR Hdg — IBTM": "IBTM.L",
        "iShares Global HY Bond EUR Hdg — GHYS":   "GHYS.L",
    },
    "🔬 Sectoriales / Temáticos": {
        "iShares Global Clean Energy — IQQH":      "IQQH.DE",
        "iShares Automation & Robotics — 2B76":    "2B76.DE",
        "Global X Semiconductor — SEMI":           "SEMI.L",
        "iShares Healthcare Innovation — HEAL":    "HEAL.L",
        "iShares MSCI World ESG Enhanced — IESW":  "IESW.DE",
        "Invesco EQQQ Nasdaq-100 (Dist) — EQQQ":  "EQQQ.L",
        "WisdomTree Battery Solutions — WBAT":     "WBAT.L",
        "iShares Physical Gold ETC — IGLN":        "IGLN.L",
    },
}

# Fallbacks estáticos para índices vía Wikipedia (por si falla la carga dinámica)
_FALLBACK_SP500 = {"Apple": "AAPL", "Microsoft": "MSFT", "NVIDIA": "NVDA",
                   "Amazon": "AMZN", "Alphabet A": "GOOGL", "Meta": "META",
                   "Tesla": "TSLA", "JPMorgan Chase": "JPM", "Berkshire B": "BRK-B"}
_FALLBACK_NDX   = {"Apple": "AAPL", "Microsoft": "MSFT", "NVIDIA": "NVDA",
                   "Amazon": "AMZN", "Meta": "META", "Tesla": "TSLA",
                   "Alphabet A": "GOOGL", "Broadcom": "AVGO", "Netflix": "NFLX"}
_FALLBACK_DOW   = {"Apple": "AAPL", "Microsoft": "MSFT", "UnitedHealth": "UNH",
                   "Goldman Sachs": "GS", "Home Depot": "HD", "Boeing": "BA",
                   "American Express": "AXP", "McDonald's": "MCD", "JPMorgan": "JPM"}
_FALLBACK_DAX   = {"SAP": "SAP.DE", "Siemens": "SIE.DE", "Allianz": "ALV.DE",
                   "Deutsche Telekom": "DTE.DE", "BMW": "BMW.DE", "BASF": "BAS.DE",
                   "Bayer": "BAYN.DE", "Mercedes-Benz": "MBG.DE", "Infineon": "IFX.DE",
                   "Adidas": "ADS.DE", "Münchener Rück": "MUV2.DE", "Volkswagen": "VOW3.DE"}
_FALLBACK_CAC   = {"LVMH": "MC.PA", "L'Oréal": "OR.PA", "TotalEnergies": "TTE.PA",
                   "Hermès": "RMS.PA", "Airbus": "AIR.PA", "Sanofi": "SAN.PA",
                   "Schneider Electric": "SU.PA", "Air Liquide": "AI.PA", "Vinci": "DG.PA"}
_FALLBACK_FTSE  = {"AstraZeneca": "AZN.L", "Shell": "SHEL.L", "HSBC": "HSBA.L",
                   "Unilever": "ULVR.L", "BP": "BP.L", "Rio Tinto": "RIO.L",
                   "GSK": "GSK.L", "Diageo": "DGE.L", "BAE Systems": "BA.L",
                   "Rolls-Royce": "RR.L", "Vodafone": "VOD.L", "Barclays": "BARC.L"}


@st.cache_data(ttl=86400)  # 24 horas — composición de índices cambia poco
def _cargar_wikipedia_index(url: str, sufijo: str = "") -> dict:
    """Extrae {nombre: ticker} de la tabla más relevante de una página Wikipedia."""
    try:
        tablas = pd.read_html(url)
        for t in tablas:
            cols = [c for c in t.columns if isinstance(c, str)]
            # Detectar columna de ticker y de nombre
            t_col = next((c for c in cols if any(k in c.lower()
                          for k in ["ticker", "symbol", "code", "abbreviation"])), None)
            n_col = next((c for c in cols if any(k in c.lower()
                          for k in ["company", "security", "name", "stock"])), None)
            if t_col and n_col:
                df = t[[n_col, t_col]].dropna()
                result = {}
                for _, row in df.iterrows():
                    nombre = str(row[n_col]).strip()
                    ticker = str(row[t_col]).strip()
                    if ":" in ticker:           # formato EXCHANGE:TICKER
                        ticker = ticker.split(":")[-1]
                    if sufijo and "." not in ticker:
                        ticker = ticker + sufijo
                    result[nombre] = ticker
                if len(result) > 5:
                    return dict(sorted(result.items()))
    except Exception:
        pass
    return {}


def obtener_tickers_mercado(mercado: str) -> dict:
    """Retorna {nombre: ticker_yfinance} para el mercado seleccionado."""
    if mercado == "🇪🇸 IBEX 35":
        return IBEX_35
    if mercado == "🌍 Eurostoxx 50":
        return EUROSTOXX_50
    if mercado == "🇺🇸 S&P 500":
        datos = _cargar_wikipedia_index(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        return datos or _FALLBACK_SP500
    if mercado == "🇺🇸 Nasdaq 100":
        datos = _cargar_wikipedia_index(
            "https://en.wikipedia.org/wiki/Nasdaq-100")
        return datos or _FALLBACK_NDX
    if mercado == "🇺🇸 Dow Jones 30":
        datos = _cargar_wikipedia_index(
            "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average")
        return datos or _FALLBACK_DOW
    if mercado == "🇩🇪 DAX 40":
        datos = _cargar_wikipedia_index(
            "https://en.wikipedia.org/wiki/DAX", sufijo=".DE")
        return datos or _FALLBACK_DAX
    if mercado == "🇫🇷 CAC 40":
        datos = _cargar_wikipedia_index(
            "https://en.wikipedia.org/wiki/CAC_40", sufijo=".PA")
        return datos or _FALLBACK_CAC
    if mercado == "🇬🇧 FTSE 100":
        datos = _cargar_wikipedia_index(
            "https://en.wikipedia.org/wiki/FTSE_100_Index", sufijo=".L")
        return datos or _FALLBACK_FTSE
    return {}


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
@st.cache_data(ttl=900)
def obtener_datos(ticker: str):
    """Descarga datos OHLCV y metadatos del ticker. Reintentos ante fallos transitorios."""
    import time as _time
    for _intento in range(3):
        try:
            t    = yf.Ticker(ticker)
            hist = t.history(period="1y", auto_adjust=True)
            if hist is None or hist.empty:
                if _intento < 2:
                    _time.sleep(1.5)
                    continue
                return None, {}
            try:
                info = t.info
            except Exception:
                info = {}
            return hist, info
        except Exception:
            if _intento < 2:
                _time.sleep(1.5)
    return None, {}


# =============================================================================
# DATOS MACRO — ECB API (sin clave) + yfinance
# =============================================================================

@st.cache_data(ttl=3600)
def obtener_historico_ecb(flow: str, series_key: str, n_obs: int = 72) -> "pd.Series | None":
    """Serie histórica mensual desde ECB SDMX API."""
    url = f"https://data-api.ecb.europa.eu/service/data/{flow}/{series_key}"
    try:
        r = requests.get(url, params={"lastNObservations": n_obs, "format": "jsondata"}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        ds = data["dataSets"][0]
        obs = (list(ds["series"].values())[0]["observations"]
               if "series" in ds else ds["observations"])
        # Índice temporal desde structure
        time_vals = data["structure"]["dimensions"]["observation"][0]["values"]
        result = {}
        for k, v in obs.items():
            idx = int(k)
            if idx < len(time_vals) and v[0] is not None:
                result[time_vals[idx]["id"]] = float(v[0])
        if not result:
            return None
        s = pd.Series(result)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:
        return None


@st.cache_data(ttl=3600)
def obtener_historico_bis(n_obs: int = 72) -> "pd.Series | None":
    """Fed Funds histórico mensual desde BIS WS_CBPOL."""
    try:
        r = requests.get(
            "https://stats.bis.org/api/v1/data/WS_CBPOL/M.US",
            params={"lastNObservations": n_obs},
            timeout=15,
            headers={"Accept": "application/vnd.sdmx.data+json", "User-Agent": "Mozilla/5.0"}
        )
        if r.status_code != 200:
            return None
        data = r.json()
        ds = data["data"]["dataSets"][0]
        obs = list(ds.get("series", {}).values())[0]["observations"]
        time_vals = data["data"]["structure"]["dimensions"]["observation"][0]["values"]
        result = {}
        for k, v in obs.items():
            idx = int(k)
            if idx < len(time_vals) and v[0] is not None:
                result[time_vals[idx]["id"]] = float(v[0])
        if not result:
            return None
        s = pd.Series(result)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:
        return None


@st.cache_data(ttl=86400)
def obtener_historico_ipc_eeuu(n_years: int = 6) -> "pd.Series | None":
    """US CPI YoY % histórico mensual desde BLS."""
    import json as _json
    from datetime import datetime as _dt
    try:
        year_now = _dt.now().year
        payload = {"seriesid": ["CUUR0000SA0"],
                   "startyear": str(year_now - n_years), "endyear": str(year_now)}
        r = requests.post("https://api.bls.gov/publicAPI/v2/timeseries/data/",
                          data=_json.dumps(payload), timeout=20,
                          headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        resp = r.json()
        if resp.get("status") != "REQUEST_SUCCEEDED":
            return None
        raw = resp["Results"]["series"][0]["data"]
        raw.sort(key=lambda x: (x["year"], x["period"]))
        result = {}
        for pt in raw:
            prev = [d for d in raw
                    if d["year"] == str(int(pt["year"]) - 1) and d["period"] == pt["period"]]
            if prev:
                yoy = (float(pt["value"]) / float(prev[0]["value"]) - 1) * 100
                month = int(pt["period"][1:])
                result[pd.Timestamp(int(pt["year"]), month, 1)] = round(yoy, 2)
        return pd.Series(result).sort_index() if result else None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def obtener_historico_yf(ticker: str, period: str = "2y") -> "pd.Series | None":
    """Cierre histórico desde yfinance."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        return hist["Close"] if not hist.empty else None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def obtener_hist_maximo(ticker: str) -> "pd.DataFrame | None":
    """Descarga el histórico máximo disponible (period='max') para detectar ATH reales."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="max", auto_adjust=True)
        if hist.empty or len(hist) < 50:
            return None
        return hist
    except Exception:
        return None


def analizar_maximos_historicos(hist_largo, precio: float, nombre: str) -> "dict | None":
    """
    Detecta la posición del precio respecto a los máximos históricos (ATH).

    Escenarios:
      subida_libre_establecida → precio ya supera ATH
      en_ath                   → precio en zona ATH (< 1% por debajo)
      aproximandose_cerca      → 1-3% por debajo del ATH
      aproximandose            → 3-8% por debajo del ATH
      referencia               → 8-25% por debajo del ATH
      lejos                    → más del 25% por debajo del ATH

    Proyección Fibonacci 127.2% sobre el tramo (mínimo anual previo → ATH)
    cuando el escenario es bullish (subida libre, en ATH o aproximándose).

    Returns dict con: ath, ath_fecha, dist_pct, escenario, target, texto
    """
    if hist_largo is None or len(hist_largo) < 50:
        return None

    # ── ATH ──────────────────────────────────────────────────────────────
    idx_ath = hist_largo["High"].idxmax()
    ath = float(hist_largo["High"].max())
    try:
        ath_fecha = idx_ath.strftime("%B %Y")
    except Exception:
        ath_fecha = str(idx_ath)[:7]

    # ── Distancia al ATH (negativa = precio por debajo) ──────────────────
    dist_pct = (precio - ath) / ath * 100

    # ── Escenario ────────────────────────────────────────────────────────
    if dist_pct > 0:
        escenario = "subida_libre_establecida"
    elif dist_pct > -1.0:
        escenario = "en_ath"
    elif dist_pct > -3.0:
        escenario = "aproximandose_cerca"
    elif dist_pct > -8.0:
        escenario = "aproximandose"
    elif dist_pct > -25.0:
        escenario = "referencia"
    else:
        escenario = "lejos"

    # ── Proyección Fibonacci 127.2% ──────────────────────────────────────
    target = None
    bullish = escenario in ("subida_libre_establecida", "en_ath",
                            "aproximandose_cerca", "aproximandose")
    if bullish:
        try:
            before_ath = hist_largo.loc[:idx_ath]
            # Mínimo del año previo al ATH (máximo 252 velas)
            lookback = before_ath.tail(252)
            last_low = float(lookback["Low"].min())
            if ath > last_low:
                raw = last_low + (ath - last_low) * 1.272
                target = round(raw, 4)
        except Exception:
            target = None

    # ── Plantilla narrativa ──────────────────────────────────────────────
    nombre_corto = nombre.split(" ")[0] if " " in nombre else nombre
    ath_str = f"{ath:.4f}"

    if escenario == "subida_libre_establecida":
        if target and target > precio:
            texto = (
                f"{nombre_corto} cotiza en zona de máximos históricos, en subida libre "
                f"por encima de los {ath_str} euros. El camino está despejado sin "
                f"resistencias técnicas definidas, con proyección de extensión "
                f"hacia los {target:.4f} euros."
            )
        else:
            texto = (
                f"{nombre_corto} cotiza en zona de máximos históricos, en subida libre "
                f"por encima de los {ath_str} euros y sin resistencias técnicas "
                f"definidas al alza."
            )

    elif escenario == "en_ath":
        texto = (
            f"{nombre_corto} cotiza prácticamente en sus máximos históricos "
            f"({ath_str} euros). La superación sostenida de este nivel dejaría "
            f"al valor en subida libre"
            + (f", con camino despejado hacia los {target:.4f} euros." if target else ".")
        )

    elif escenario == "aproximandose_cerca":
        texto = (
            f"{nombre_corto} se acerca muy de cerca a los máximos históricos que "
            f"presenta en los {ath_str} euros. Muy pendientes de la superación de "
            f"estos precios, ya que dejaría al valor en subida libre"
            + (
                f", con el camino despejado para buscar una extensión de las "
                f"subidas hasta los {target:.4f} euros."
                if target
                else "."
            )
        )

    elif escenario == "aproximandose":
        texto = (
            f"{nombre_corto} se acerca poco a poco a los máximos históricos que "
            f"presenta en los {ath_str} euros. Muy pendientes de la superación de "
            f"estos precios, ya que dejaría al valor en subida libre"
            + (
                f", con el camino despejado para que podamos ver una extensión de "
                f"las subidas hasta el nivel de los {target:.4f} euros."
                if target
                else "."
            )
        )

    elif escenario == "referencia":
        texto = (
            f"{nombre_corto} presenta sus máximos históricos en los {ath_str} euros "
            f"({abs(dist_pct):.1f}% de recorrido alcista potencial). "
            f"Nivel de referencia clave si las subidas continúan."
        )

    else:  # lejos
        texto = (
            f"{nombre_corto} cotiza con un descuento del {abs(dist_pct):.0f}% respecto "
            f"a sus máximos históricos de {ath_fecha} en los {ath_str} euros."
        )

    return {
        "ath":       ath,
        "ath_fecha": ath_fecha,
        "dist_pct":  dist_pct,
        "escenario": escenario,
        "target":    target,
        "texto":     texto,
    }


def analizar_sma200(hist, precio: float, nombre: str) -> "dict | None":
    """
    Detecta la pendiente y posible giro de la media móvil de 200 sesiones.

    Lógica de escenario:
      Calcula la pendiente de la SMA200 con una ventana de 5 sesiones.
      Compara la pendiente actual con la de hace 20 sesiones para detectar giros.

      Escenarios de pendiente:
        giro_alcista_reciente  → pendiente ahora positiva, era negativa hace 20 sesiones
        tendencia_alcista      → pendiente positiva sostenida (≥ 20 sesiones)
        giro_bajista_reciente  → pendiente ahora negativa, era positiva hace 20 sesiones
        tendencia_bajista      → pendiente negativa sostenida (≥ 20 sesiones)

      Cruzado con posición del precio (sobre / bajo SMA200) → 8 plantillas narrativas.

    Returns dict con: sma200, dist_pct, escenario, precio_sobre, pendiente_pct, texto
    """
    if hist is None or len(hist) < 210:
        return None

    cierre = hist["Close"]
    sma = cierre.rolling(200).mean()

    # Necesitamos al menos 220 valores para tener 20 sesiones de historial de pendiente
    sma_clean = sma.dropna()
    if len(sma_clean) < 25:
        return None

    sma200_val = float(sma_clean.iloc[-1])

    # Pendiente: diferencia de 5 sesiones (en valor absoluto y porcentual)
    slope_now_abs = float(sma_clean.iloc[-1] - sma_clean.iloc[-6])
    slope_now_pct = slope_now_abs / sma200_val * 100

    # Pendiente hace 20 sesiones (si hay suficientes datos)
    if len(sma_clean) >= 26:
        slope_past_abs = float(sma_clean.iloc[-21] - sma_clean.iloc[-26])
    else:
        slope_past_abs = slope_now_abs  # fallback: misma dirección

    # Umbral de "plana": menos de 0.03% de variación en 5 sesiones (ignorar ruido)
    UMBRAL_PLANO = sma200_val * 0.0003

    now_positiva = slope_now_abs > UMBRAL_PLANO
    now_negativa = slope_now_abs < -UMBRAL_PLANO
    past_positiva = slope_past_abs > UMBRAL_PLANO
    past_negativa = slope_past_abs < -UMBRAL_PLANO

    if now_positiva and past_negativa:
        escenario = "giro_alcista_reciente"
    elif now_negativa and past_positiva:
        escenario = "giro_bajista_reciente"
    elif now_positiva:
        escenario = "tendencia_alcista"
    elif now_negativa:
        escenario = "tendencia_bajista"
    else:
        escenario = "plana"

    precio_sobre = precio > sma200_val
    dist_pct = (precio - sma200_val) / sma200_val * 100

    # ── Plantillas narrativas (escenario × posición del precio) ──────────
    nombre_corto = nombre.split(" ")[0] if " " in nombre else nombre
    sma_str = f"{sma200_val:.4f}"
    dist_str = f"{abs(dist_pct):.1f}%"
    pos_str = "por encima" if precio_sobre else "por debajo"

    if escenario == "giro_alcista_reciente":
        if precio_sobre:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} acaba de girar al alza "
                f"en los {sma_str} euros, señal técnica de primer orden que indica "
                f"que la tendencia de largo plazo está cambiando de signo. "
                f"El precio cotiza un {dist_str} por encima de este nivel, "
                f"lo que refuerza la señal alcista."
            )
        else:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} ha iniciado un giro "
                f"alcista en los {sma_str} euros, aunque el precio todavía cotiza "
                f"por debajo de este nivel. La superación de la media sería una "
                f"señal técnica de fortaleza de primer orden."
            )

    elif escenario == "tendencia_alcista":
        if precio_sobre:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} mantiene pendiente "
                f"alcista, actuando como soporte dinámico en los {sma_str} euros. "
                f"El precio cotiza un {dist_str} por encima, en una estructura "
                f"técnica de largo plazo positiva."
            )
        else:
            texto = (
                f"A pesar de que la media de 200 sesiones de {nombre_corto} mantiene "
                f"pendiente alcista ({sma_str} euros), el precio ha perforado este "
                f"nivel clave. Señal de debilidad técnica a vigilar de cerca; "
                f"la recuperación por encima de la media sería prioritaria."
            )

    elif escenario == "giro_bajista_reciente":
        if not precio_sobre:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} acaba de girar a la "
                f"baja en los {sma_str} euros, señal de deterioro en la tendencia "
                f"de largo plazo. El precio cotiza por debajo de esta referencia "
                f"clave, lo que aumenta la presión vendedora estructural."
            )
        else:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} ha iniciado un giro "
                f"bajista en los {sma_str} euros. El precio aún cotiza por encima "
                f"de este nivel, pero el deterioro de la pendiente es una señal "
                f"de alerta que conviene monitorizar de cerca."
            )

    elif escenario == "tendencia_bajista":
        if not precio_sobre:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} mantiene pendiente "
                f"bajista con el valor cotizando {dist_str} por debajo de este "
                f"nivel ({sma_str} euros). Estructura de largo plazo negativa "
                f"que pesa sobre el sesgo técnico del valor."
            )
        else:
            texto = (
                f"La media de 200 sesiones de {nombre_corto} mantiene pendiente "
                f"bajista ({sma_str} euros), aunque el precio ha logrado situarse "
                f"un {dist_str} por encima de esta referencia. Recuperación "
                f"técnica a confirmar con la estabilización de la pendiente."
            )

    else:  # plana
        texto = (
            f"La media de 200 sesiones de {nombre_corto} se encuentra prácticamente "
            f"plana en los {sma_str} euros, con el precio cotizando un {dist_str} "
            f"{pos_str} de este nivel. Sin señal clara de tendencia de largo plazo."
        )

    return {
        "sma200":        sma200_val,
        "dist_pct":      dist_pct,
        "pendiente_pct": slope_now_pct,
        "escenario":     escenario,
        "precio_sobre":  precio_sobre,
        "texto":         texto,
    }


def analizar_resistencias_estructurales(
    niveles_ref, precio: float, nombre: str
) -> "dict | None":
    """
    Analiza la posición del precio respecto a los niveles estructurales reforzados
    (zonas donde coinciden un pivot y una media móvil).

    Escenarios:
        en_resistencia   → precio a <1.5% de la resistencia más cercana
        en_soporte       → precio a <1.5% del soporte más cercano
        zona_alta_rango  → posición en rango > 65%
        zona_baja_rango  → posición en rango < 35%
        zona_media_rango → posición en rango 35-65%
        sin_resistencia  → precio por encima de todos los niveles
        sin_soporte      → precio por debajo de todos los niveles

    Returns dict con: soporte, resistencia, dist_soporte, dist_resist,
                      pos_rango_pct, escenario, texto
    """
    if not niveles_ref or precio <= 0:
        return None

    # Separar por tipo
    soportes     = sorted(
        [n for n in niveles_ref if n.get("tipo") == "S"],
        key=lambda x: x["precio"], reverse=True
    )
    resistencias = sorted(
        [n for n in niveles_ref if n.get("tipo") == "R"],
        key=lambda x: x["precio"]
    )

    # Nivel más cercano por debajo / por encima
    soporte_cercano = next((n for n in soportes     if n["precio"] < precio * 0.9998), None)
    resist_cercana  = next((n for n in resistencias if n["precio"] > precio * 1.0002), None)

    if soporte_cercano is None and resist_cercana is None:
        return None

    # Distancias porcentuales
    dist_soporte = ((precio - soporte_cercano["precio"]) / precio * 100) if soporte_cercano else None
    dist_resist  = ((resist_cercana["precio"] - precio)  / precio * 100) if resist_cercana else None

    # Posición dentro del rango soporte–resistencia
    if soporte_cercano and resist_cercana:
        rango = resist_cercana["precio"] - soporte_cercano["precio"]
        pos_rango_pct = (precio - soporte_cercano["precio"]) / rango * 100 if rango > 0 else 50.0
    else:
        pos_rango_pct = None

    # Escenario
    if dist_resist is not None and dist_resist < 1.5:
        escenario = "en_resistencia"
    elif dist_soporte is not None and dist_soporte < 1.5:
        escenario = "en_soporte"
    elif resist_cercana is None:
        escenario = "sin_resistencia"
    elif soporte_cercano is None:
        escenario = "sin_soporte"
    elif pos_rango_pct is not None and pos_rango_pct > 65:
        escenario = "zona_alta_rango"
    elif pos_rango_pct is not None and pos_rango_pct < 35:
        escenario = "zona_baja_rango"
    else:
        escenario = "zona_media_rango"

    # ── Narrativas ───────────────────────────────────────────────────────────
    nombre_corto = nombre.split(" ")[0] if " " in nombre else nombre
    resist_str   = f"{resist_cercana['precio']:.4f} €"  if resist_cercana  else "—"
    sop_str      = f"{soporte_cercano['precio']:.4f} €" if soporte_cercano else "—"
    pivot_r      = resist_cercana.get("pivot",  "")     if resist_cercana  else ""
    pivot_s      = soporte_cercano.get("pivot", "")     if soporte_cercano else ""
    pivot_r_str  = f" ({pivot_r})"  if pivot_r  else ""
    pivot_s_str  = f" ({pivot_s})"  if pivot_s  else ""

    if escenario == "en_resistencia":
        texto = (
            f"{nombre_corto} cotiza a solo {dist_resist:.1f}% de la resistencia estructural "
            f"reforzada{pivot_r_str} en {resist_str} — zona de confluencia entre nivel pivot "
            f"y media móvil de alta relevancia. El precio se aproxima a un techo técnico "
            f"de primer orden. Superación con volumen sería señal de continuación alcista; "
            f"rechazo en la zona, señal de distribución."
        )
    elif escenario == "en_soporte":
        texto = (
            f"{nombre_corto} cotiza a {dist_soporte:.1f}% del soporte estructural "
            f"reforzado{pivot_s_str} en {sop_str} — zona de confluencia pivot + media móvil "
            f"con historial de absorción. El mantenimiento de este nivel será determinante "
            f"para el próximo movimiento de importancia."
        )
    elif escenario == "sin_resistencia":
        texto = (
            f"{nombre_corto} cotiza por encima de todos los niveles de resistencia "
            f"estructural identificados — el precio opera sin techo técnico reforzado conocido. "
            f"Mayor incertidumbre sobre el próximo nivel de referencia. "
            f"Soporte más cercano: {sop_str} ({dist_soporte:.1f}% por debajo)."
        )
    elif escenario == "sin_soporte":
        texto = (
            f"{nombre_corto} cotiza por debajo de todos los soportes estructurales "
            f"identificados — ausencia de suelo técnico reforzado, zona de mayor riesgo "
            f"para posiciones largas. La resistencia más cercana, ahora techo, "
            f"se sitúa en {resist_str} ({dist_resist:.1f}% arriba)."
        )
    elif escenario == "zona_alta_rango":
        texto = (
            f"{nombre_corto} opera en la zona alta del rango estructural "
            f"({pos_rango_pct:.0f}% del recorrido soporte–resistencia). "
            f"Distancia al techo reforzado{pivot_r_str} en {resist_str}: {dist_resist:.1f}%. "
            f"La asimetría riesgo/recompensa es desfavorable para nuevas entradas largas."
        )
    elif escenario == "zona_baja_rango":
        texto = (
            f"{nombre_corto} opera en la zona baja del rango estructural "
            f"({pos_rango_pct:.0f}% del recorrido soporte–resistencia). "
            f"Soporte reforzado{pivot_s_str} en {sop_str} a {dist_soporte:.1f}%. "
            f"La asimetría riesgo/recompensa favorece estrategias de valor y rebote técnico."
        )
    else:  # zona_media_rango
        texto = (
            f"{nombre_corto} cotiza en la zona media del rango estructural — soporte "
            f"reforzado{pivot_s_str} en {sop_str} ({dist_soporte:.1f}% abajo) y resistencia "
            f"reforzada{pivot_r_str} en {resist_str} ({dist_resist:.1f}% arriba). "
            f"Posición neutral con recorrido simétrico en ambas direcciones."
        )

    return {
        "soporte":       soporte_cercano,
        "resistencia":   resist_cercana,
        "dist_soporte":  dist_soporte,
        "dist_resist":   dist_resist,
        "pos_rango_pct": pos_rango_pct,
        "escenario":     escenario,
        "texto":         texto,
    }



def analizar_fibonacci(hist, precio: float, nombre: str) -> "dict | None":
    """
    Calcula niveles de retroceso y extensión de Fibonacci sobre el swing del año
    (máximo y mínimo de las últimas ~252 sesiones).

    Escenarios: extension_161, extension_127, en_maximo,
                retroceso_236, retroceso_382, retroceso_618,
                retroceso_786, swing_roto.
    """
    if hist is None or len(hist) < 60:
        return None

    n = min(252, len(hist))
    v = hist.tail(n)

    swing_max = float(v["High"].max())
    swing_min = float(v["Low"].min())
    idx_max   = v["High"].idxmax()
    idx_min   = v["Low"].idxmin()

    if swing_max <= swing_min or swing_max <= 0:
        return None

    rango   = swing_max - swing_min
    bullish = idx_max > idx_min          # True si el máximo es el evento más reciente

    # Posición relativa del precio (0 % = mínimo swing, 100 % = máximo swing)
    pos_pct = (precio - swing_min) / rango * 100

    # Niveles Fibonacci como precio absoluto
    FIB_LABELS = [
        ("161.8%", 161.8),
        ("127.2%", 127.2),
        ("100.0%", 100.0),
        ("78.6%",   78.6),
        ("61.8%",   61.8),
        ("50.0%",   50.0),
        ("38.2%",   38.2),
        ("23.6%",   23.6),
        ("0.0%",     0.0),
    ]
    niveles_precio = {
        label: swing_min + (pct / 100.0) * rango
        for label, pct in FIB_LABELS
    }

    # Nivel más cercano por debajo y por encima del precio actual
    below = {l: p for l, p in niveles_precio.items() if p <= precio * 1.0005}
    above = {l: p for l, p in niveles_precio.items() if p >= precio * 0.9995}

    fib_abajo  = max(below.items(), key=lambda x: x[1]) if below else None
    fib_arriba = min(above.items(), key=lambda x: x[1]) if above else None

    if fib_abajo:
        d = (precio - fib_abajo[1]) / precio * 100
        fib_abajo = {"label": fib_abajo[0], "precio": fib_abajo[1], "dist_pct": d}
    if fib_arriba:
        d = (fib_arriba[1] - precio) / precio * 100
        fib_arriba = {"label": fib_arriba[0], "precio": fib_arriba[1], "dist_pct": d}

    # ── Escenario ────────────────────────────────────────────────────────
    if pos_pct > 161.8:
        escenario = "extension_161"
    elif pos_pct > 127.2:
        escenario = "extension_127"
    elif pos_pct >= 90.0:
        escenario = "en_maximo"
    elif pos_pct >= 76.4:
        escenario = "retroceso_236"
    elif pos_pct >= 55.0:
        escenario = "retroceso_382"
    elif pos_pct >= 35.0:
        escenario = "retroceso_618"
    elif pos_pct >= 15.0:
        escenario = "retroceso_786"
    else:
        escenario = "swing_roto"

    # ── Narrativa ────────────────────────────────────────────────────────
    nombre_c   = nombre.split(" ")[0] if " " in nombre else nombre
    tipo_swing = "alcista" if bullish else "bajista"
    s_min = f"{swing_min:,.4f}"
    s_max = f"{swing_max:,.4f}"
    pos_s = f"{pos_pct:.1f}%"

    if escenario == "extension_161":
        texto = (
            f"{nombre_c} cotiza por encima del 161.8% de extensión del swing {tipo_swing} "
            f"({s_min} → {s_max}). Zona de impulso excepcional — el precio ha superado los dos "
            f"objetivos de extensión clásicos. El momentum es sólido pero los modelos de retorno "
            f"a la media señalan riesgo de corrección elevado desde estos niveles."
        )
    elif escenario == "extension_127":
        arriba_str = (
            f" Próximo objetivo: 161.8% en {fib_arriba['precio']:,.4f} "
            f"(+{fib_arriba['dist_pct']:.1f}%)."
        ) if fib_arriba and fib_arriba["label"] == "161.8%" else ""
        texto = (
            f"{nombre_c} ha alcanzado la extensión del 127.2% del swing {tipo_swing} "
            f"({s_min} → {s_max}) — objetivo clásico de proyección Fibonacci. Zona de posible "
            f"resistencia o consolidación; el precio ha recorrido un {pos_s} del swing.{arriba_str}"
        )
    elif escenario == "en_maximo":
        arriba_str = (
            f" Una ruptura activaría la extensión del 127.2% en "
            f"{fib_arriba['precio']:,.4f} como próximo objetivo."
        ) if fib_arriba else ""
        texto = (
            f"{nombre_c} cotiza cerca del máximo del swing {tipo_swing} ({s_max}), "
            f"en la zona del 100% de Fibonacci (posición en swing: {pos_s}). "
            f"Nivel de referencia crítico: la defensa o ruptura de este nivel determina "
            f"si el precio entra en territorio de extensión o inicia corrección.{arriba_str}"
        )
    elif escenario == "retroceso_236":
        texto = (
            f"{nombre_c} se encuentra en el primer retroceso Fibonacci (23.6%) del swing "
            f"{tipo_swing} ({s_min} → {s_max}). Pullback leve — posición {pos_s} del swing. "
            f"Esta zona actúa como soporte dinámico en tendencias fuertes; la pérdida del 23.6% "
            f"({niveles_precio['23.6%']:,.4f}) abriría el camino al 38.2%."
        )
    elif escenario == "retroceso_382":
        texto = (
            f"{nombre_c} cotiza en la zona de retroceso del 38.2-50% del swing {tipo_swing} "
            f"({s_min} → {s_max}) — retroceso estándar. Posición actual: {pos_s} del swing. "
            f"El nivel del 38.2% ({niveles_precio['38.2%']:,.4f}) es soporte de tendencia; "
            f"el 50.0% ({niveles_precio['50.0%']:,.4f}) marca el punto medio del movimiento. "
            f"La siguiente zona crítica al alza es el 61.8% (golden ratio)."
        )
    elif escenario == "retroceso_618":
        texto = (
            f"{nombre_c} cotiza en la 'zona dorada' de Fibonacci (50-61.8%) del swing {tipo_swing} "
            f"({s_min} → {s_max}) — el retroceso estadísticamente más relevante. "
            f"El nivel del 61.8% ({niveles_precio['61.8%']:,.4f}) es la referencia del Golden Ratio, "
            f"donde la mayoría de tendencias válidas encuentran soporte. "
            f"Posición actual: {pos_s} del swing."
        )
    elif escenario == "retroceso_786":
        texto = (
            f"{nombre_c} ha retrocedido al 78.6% del swing {tipo_swing} "
            f"({s_min} → {s_max}) — retroceso profundo. La estructura del swing queda muy debilitada. "
            f"Solo la defensa del nivel {niveles_precio['78.6%']:,.4f} mantiene técnicamente viva "
            f"la estructura {tipo_swing}. Posición actual: {pos_s} del swing."
        )
    else:  # swing_roto
        texto = (
            f"{nombre_c} ha perforado el origen del swing {tipo_swing} ({s_min}) — "
            f"estructura Fibonacci del período anual invalidada (posición: {pos_s}). "
            f"El precio opera por debajo del nivel de 0% Fibonacci. Nueva estructura en formación."
        )

    return {
        "swing_min":   swing_min,
        "swing_max":   swing_max,
        "bullish":     bullish,
        "pos_pct":     pos_pct,
        "niveles":     niveles_precio,
        "fib_abajo":   fib_abajo,
        "fib_arriba":  fib_arriba,
        "escenario":   escenario,
        "texto":       texto,
    }


def _macro_chart(series_dict: dict, unidad: str = "%", height: int = 260,
                 fecha_inicio: "pd.Timestamp | None" = None):
    """Plotly multi-línea para series macro. Devuelve fig."""
    import plotly.graph_objects as go
    COLORS = ["#2563eb", "#16a34a", "#dc2626", "#d97706", "#7c3aed", "#0891b2"]
    fig = go.Figure()
    for i, (nombre, serie) in enumerate(series_dict.items()):
        if serie is None or (hasattr(serie, "empty") and serie.empty):
            continue
        # Normalizar timezone: eliminar tz-info para comparación uniforme
        if hasattr(serie.index, "tz") and serie.index.tz is not None:
            serie.index = serie.index.tz_localize(None)
        if fecha_inicio is not None:
            fi = fecha_inicio.tz_localize(None) if hasattr(fecha_inicio, "tz") and fecha_inicio.tz else fecha_inicio
            serie = serie[serie.index >= fi]
        if serie.empty:
            continue
        fig.add_trace(go.Scatter(
            x=serie.index, y=serie.values, mode="lines", name=nombre,
            line=dict(color=COLORS[i % len(COLORS)], width=2),
            hovertemplate=f"<b>{nombre}</b><br>%{{x|%b %Y}}: %{{y:.2f}}{unidad}<extra></extra>"
        ))
    fig.update_layout(
        height=height, margin=dict(l=0, r=10, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=11)),
        hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickformat="%b %Y",
                   tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9",
                   ticksuffix=unidad, tickfont=dict(size=11)),
    )
    return fig

@st.cache_data(ttl=3600)  # 1 hora — tipos e inflación cambian poco
def obtener_dato_ecb(series_key: str, flow_ref: str = "FM"):
    """Último valor de una serie del BCE Statistical Data Warehouse (JSON).
    La API puede devolver dos estructuras distintas según la serie:
      - dataSets[0]["series"]["0:0:..."]["observations"]   ← formato habitual
      - dataSets[0]["observations"]                        ← formato compacto
    """
    url = f"https://data-api.ecb.europa.eu/service/data/{flow_ref}/{series_key}"
    try:
        r = requests.get(url, params={"lastNObservations": 1, "format": "jsondata"}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        ds = data["dataSets"][0]
        # Intenta estructura con "series" primero (formato más común)
        if "series" in ds:
            first_series = list(ds["series"].values())[0]
            obs = first_series["observations"]
        else:
            obs = ds["observations"]
        # Toma la última observación disponible
        last_key = sorted(obs.keys(), key=lambda x: int(x))[-1]
        val = obs[last_key][0]
        return float(val) if val is not None else None
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600)
def obtener_euribor_12m() -> float | None:
    """Euribor 12M (1 año) — ECB Data Portal FM flow.
    Clave correcta: EURIBOR1YD_ (no EURIBOR12MD_). Frecuencia mensual."""
    try:
        url = "https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"
        r = requests.get(url,
                         params={"lastNObservations": 1, "format": "jsondata"},
                         timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        ds = data["dataSets"][0]
        obs = (list(ds["series"].values())[0]["observations"]
               if "series" in ds else ds["observations"])
        if not obs:
            return None
        last_key = sorted(obs.keys(), key=lambda x: int(x))[-1]
        val = obs[last_key][0]
        return float(val) if val is not None else None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def obtener_fed_funds() -> float | None:
    """Fed Funds rate — BIS Central Bank Policy Rates (WS_CBPOL).
    Fuente: Bank for International Settlements, serie M.US."""
    try:
        r = requests.get(
            "https://stats.bis.org/api/v1/data/WS_CBPOL/M.US",
            params={"lastNObservations": 1},
            timeout=15,
            headers={"Accept": "application/vnd.sdmx.data+json",
                     "User-Agent": "Mozilla/5.0"}
        )
        if r.status_code != 200:
            return None
        data = r.json()
        ds = data["data"]["dataSets"][0]
        series = ds.get("series", {})
        if not series:
            return None
        obs = list(series.values())[0]["observations"]
        if not obs:
            return None
        last_key = sorted(obs.keys(), key=lambda x: int(x))[-1]
        val = obs[last_key][0]
        return float(val) if val is not None else None
    except Exception:
        return None


@st.cache_data(ttl=86400)  # Dato mensual — refrescar una vez al día
def obtener_ipc_eeuu() -> float | None:
    """US CPI YoY % — BLS public API (serie CUUR0000SA0, sin API key).
    Tasa interanual: (último mes / mismo mes año anterior - 1) × 100."""
    try:
        import json as _json
        # Solicitar los últimos 13 meses (necesitamos el actual + el de hace 12)
        from datetime import datetime
        year_now = datetime.now().year
        payload = {
            "seriesid": ["CUUR0000SA0"],
            "startyear": str(year_now - 1),
            "endyear":   str(year_now),
        }
        r = requests.post(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            data=_json.dumps(payload),
            timeout=20,
            headers={"Content-Type": "application/json",
                     "User-Agent": "Mozilla/5.0"}
        )
        if r.status_code != 200:
            return None
        resp = r.json()
        if resp.get("status") != "REQUEST_SUCCEEDED":
            return None
        series_data = resp["Results"]["series"][0]["data"]
        # Ordenar: año desc, período desc
        series_data.sort(key=lambda x: (x["year"], x["period"]), reverse=True)
        if len(series_data) < 2:
            return None
        latest = series_data[0]
        # Buscar el mismo mes del año anterior
        prev_year = [d for d in series_data
                     if d["year"] == str(int(latest["year"]) - 1)
                     and d["period"] == latest["period"]]
        if not prev_year:
            # Si no tenemos datos del año anterior en el rango, ampliar consulta
            payload2 = {
                "seriesid": ["CUUR0000SA0"],
                "startyear": str(year_now - 2),
                "endyear":   str(year_now - 1),
            }
            r2 = requests.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                data=_json.dumps(payload2),
                timeout=20,
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0"}
            )
            if r2.status_code != 200:
                return None
            resp2 = r2.json()
            if resp2.get("status") != "REQUEST_SUCCEEDED":
                return None
            prev_data = resp2["Results"]["series"][0]["data"]
            prev_year = [d for d in prev_data
                         if d["year"] == str(int(latest["year"]) - 1)
                         and d["period"] == latest["period"]]
        if not prev_year:
            return None
        yoy = (float(latest["value"]) / float(prev_year[0]["value"]) - 1) * 100
        return yoy
    except Exception:
        return None


@st.cache_data(ttl=900)  # 15 min — datos de mercado
def obtener_precio_macro(ticker: str):
    """Precio actual y variación diaria (%) de un ticker via yfinance."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", auto_adjust=True)
        if hist is None or hist.empty:
            return None, None
        precio = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else precio
        delta = (precio - prev) / prev * 100 if prev else 0
        return precio, delta
    except Exception:
        return None, None


def pestaña_macro():
    """Pestaña de contexto macroeconómico global."""
    st.markdown("### 🌍 Contexto Macroeconómico Global")

    # ── Selector de horizonte temporal ───────────────────────────────────────
    _hc1, _hc2 = st.columns([5, 3])
    with _hc1:
        st.caption("BCE/Euribor: ECB Data Portal · Fed Funds: BIS · IPC EEUU: BLS · "
                   "Mercados: Yahoo Finance (~15 min de retraso)")
    with _hc2:
        horizonte = st.radio("Horizonte histórico", ["6M", "1A", "3A", "5A"],
                             horizontal=True, index=1, key="macro_horizonte",
                             label_visibility="collapsed")

    _yf_period  = {"6M": "6mo", "1A": "2y", "3A": "3y", "5A": "5y"}[horizonte]
    _n_obs      = {"6M": 8, "1A": 15, "3A": 40, "5A": 65}[horizonte]
    _fecha_ini  = pd.Timestamp.now() - pd.DateOffset(
                    months={"6M": 6, "1A": 12, "3A": 36, "5A": 60}[horizonte])

    # ── TIPOS DE INTERÉS ─────────────────────────────────────────────────────
    st.markdown("#### 📊 Tipos de Interés")
    col1, col2, col3, col4 = st.columns(4)

    with st.spinner("Cargando tipos BCE y Fed..."):
        dfr        = obtener_dato_ecb("B.U2.EUR.4F.KR.DFR.LEV")
        euribor12m = obtener_euribor_12m()
        fed_funds  = obtener_fed_funds()
    us10y, us10y_d = obtener_precio_macro("^TNX")

    with col1:
        st.metric("BCE — DFR", f"{dfr:.2f}%" if dfr is not None else "—",
                  help="Tipo de la Facilidad de Depósito del BCE. Referencia de la zona euro.")
    with col2:
        st.metric("Euribor 12M", f"{euribor12m:.3f}%" if euribor12m is not None else "—",
                  help="Tipo interbancario a 12 meses. Referencia directa para hipotecas variables en España.")
    with col3:
        if us10y is not None:
            st.metric("US Treasury 10Y", f"{us10y:.2f}%", delta=f"{us10y_d:+.2f}% (día)",
                      help="Rendimiento del bono soberano EEUU a 10 años. Tasa libre de riesgo global.")
        else:
            st.metric("US Treasury 10Y", "—")
    with col4:
        st.metric("Fed Funds", f"{fed_funds:.2f}%" if fed_funds is not None else "—",
                  help="Tipo de política monetaria de la Fed. Fuente: BIS WS_CBPOL.")

    # Gráfico histórico — Tipos
    with st.spinner("Cargando histórico tipos..."):
        h_dfr      = obtener_historico_ecb("ECB", "B.U2.EUR.4F.KR.DFR.LEV", _n_obs)
        h_euribor  = obtener_historico_ecb("FM", "M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA", _n_obs)
        h_fedfunds = obtener_historico_bis(_n_obs)
        h_us10y    = obtener_historico_yf("^TNX", _yf_period)

    fig_tipos = _macro_chart({
        "BCE DFR": h_dfr,
        "Euribor 12M": h_euribor,
        "Fed Funds": h_fedfunds,
        "US Treasury 10Y": h_us10y,
    }, unidad="%", fecha_inicio=_fecha_ini)
    st.plotly_chart(fig_tipos, use_container_width=True, config={"displayModeBar": False})

    # ── INFLACIÓN ────────────────────────────────────────────────────────────
    st.markdown("#### 📈 Inflación (IPC interanual — último dato disponible)")
    col5, col6, col7 = st.columns(3)

    with st.spinner("Cargando inflación..."):
        hicp_eu  = obtener_dato_ecb("M.U2.N.000000.4.ANR", "ICP")
        hicp_es  = obtener_dato_ecb("M.ES.N.000000.4.ANR", "ICP")
        ipc_eeuu = obtener_ipc_eeuu()

    with col5:
        if hicp_eu is not None:
            sem = "🔴" if hicp_eu > 3 else ("🟡" if hicp_eu > 2 else "🟢")
            st.metric(f"IPC Eurozona {sem}", f"{hicp_eu:.1f}%",
                      help="HICP zona euro interanual. Objetivo BCE: ~2%.")
        else:
            st.metric("IPC Eurozona", "—")
    with col6:
        if hicp_es is not None:
            sem = "🔴" if hicp_es > 3 else ("🟡" if hicp_es > 2 else "🟢")
            st.metric(f"IPC España {sem}", f"{hicp_es:.1f}%",
                      help="HICP España interanual (INE/BCE).")
        else:
            st.metric("IPC España", "—")
    with col7:
        if ipc_eeuu is not None:
            sem = "🔴" if ipc_eeuu > 3 else ("🟡" if ipc_eeuu > 2 else "🟢")
            st.metric(f"IPC EEUU {sem}", f"{ipc_eeuu:.1f}%",
                      help="CPI EEUU interanual. Fuente: BLS.")
        else:
            st.metric("IPC EEUU", "—")

    # Gráfico histórico — Inflación
    _n_ipc = {"6M": 2, "1A": 3, "3A": 5, "5A": 7}[horizonte]
    with st.spinner("Cargando histórico inflación..."):
        h_hicp_eu = obtener_historico_ecb("ICP", "M.U2.N.000000.4.ANR", _n_obs)
        h_hicp_es = obtener_historico_ecb("ICP", "M.ES.N.000000.4.ANR", _n_obs)
        h_ipc_us  = obtener_historico_ipc_eeuu(_n_ipc)

    fig_ipc = _macro_chart({
        "IPC Eurozona": h_hicp_eu,
        "IPC España": h_hicp_es,
        "IPC EEUU": h_ipc_us,
    }, unidad="%", fecha_inicio=_fecha_ini)
    st.plotly_chart(fig_ipc, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # ── DIVISAS ──────────────────────────────────────────────────────────────
    st.markdown("#### 💱 Divisas (base EUR)")
    tickers_fx = {
        "EUR/USD": ("EURUSD=X",
                    "Cruce euro/dólar. Afecta retorno de activos USD sin cobertura. "
                    ">1.10: USD débil. <1.05: USD fuerte."),
        "EUR/GBP": ("EURGBP=X",
                    "Cruce euro/libra. Referencia para exposición al mercado británico."),
        "EUR/JPY": ("EURJPY=X",
                    "Cruce euro/yen. Yen es divisa refugio: debilidad sostenida indica apetito por riesgo."),
        "EUR/CHF": ("EURCHF=X",
                    "Cruce euro/franco suizo. CHF también es refugio: cercano a 1.0 indica tensión europea."),
    }
    cols_fx = st.columns(4)
    for i, (nombre, (tkr, tooltip)) in enumerate(tickers_fx.items()):
        precio, delta = obtener_precio_macro(tkr)
        with cols_fx[i]:
            st.metric(nombre, f"{precio:.4f}" if precio else "—",
                      delta=f"{delta:+.2f}%" if delta else None, help=tooltip)

    # Gráfico histórico — Divisas
    with st.spinner("Cargando histórico divisas..."):
        h_fx = {n: obtener_historico_yf(tkr, _yf_period)
                for n, (tkr, _) in tickers_fx.items()}
    fig_fx = _macro_chart(h_fx, unidad="", fecha_inicio=_fecha_ini)
    st.plotly_chart(fig_fx, use_container_width=True, config={"displayModeBar": False})

    # ── COMMODITIES ──────────────────────────────────────────────────────────
    st.markdown("#### 🛢️ Commodities")
    tickers_comm = {
        "Oro (USD/oz)":      ("GC=F",
                              "Oro en futuros (USD/oz troy). Refugio clásico: sube con incertidumbre, "
                              "dólar débil e inflación."),
        "Brent (USD/b)":     ("BZ=F",
                              "Petróleo Brent en futuros (USD/barril). Referencia europea del crudo."),
        "WTI (USD/b)":       ("CL=F",
                              "West Texas Intermediate, referencia EEUU. Cotiza con descuento vs Brent."),
        "Gas Natural (USD)": ("NG=F",
                              "Gas Natural Henry Hub (USD/MMBTU). Alta correlación con precios "
                              "energéticos europeos desde el shock 2021-22."),
    }
    cols_comm = st.columns(4)
    for i, (nombre, (tkr, tooltip)) in enumerate(tickers_comm.items()):
        precio, delta = obtener_precio_macro(tkr)
        with cols_comm[i]:
            st.metric(nombre, f"{precio:.2f}" if precio else "—",
                      delta=f"{delta:+.2f}%" if delta else None, help=tooltip)

    # Gráfico histórico — Commodities
    with st.spinner("Cargando histórico commodities..."):
        h_comm = {n: obtener_historico_yf(tkr, _yf_period)
                  for n, (tkr, _) in tickers_comm.items()}
    fig_comm = _macro_chart(h_comm, unidad=" USD", fecha_inicio=_fecha_ini)
    st.plotly_chart(fig_comm, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # ── ÍNDICES Y VOLATILIDAD ────────────────────────────────────────────────
    st.markdown("#### 📉 Índices Bursátiles y Volatilidad")
    tickers_idx = [
        ("VIX",          "^VIX",
         ">30: pánico. 15-30: cautela. <15: complacencia."),
        ("S&P 500",      "^GSPC",
         "500 mayores empresas EEUU. Referencia global de renta variable."),
        ("Nasdaq 100",   "^NDX",
         "100 mayores no-financieras Nasdaq. Muy sensible a tipos de interés reales."),
        ("IBEX 35",      "^IBEX",
         "Referencia bolsa española. Fuerte peso bancario (~30%) y utilities."),
        ("DAX 40",       "^GDAXI",
         "Índice alemán. Exportador puro: sensible al ciclo global y a China."),
        ("Eurostoxx 50", "^STOXX50E",
         "50 mayores empresas eurozona. Base de ETFs UCITS de RV Europa."),
    ]
    cols_idx = st.columns(3)
    for i, (nombre, tkr, tooltip) in enumerate(tickers_idx):
        precio, delta = obtener_precio_macro(tkr)
        with cols_idx[i % 3]:
            st.metric(nombre, f"{precio:,.2f}" if precio else "—",
                      delta=f"{delta:+.2f}%" if delta else None, help=tooltip)

    # Gráfico histórico — Índices (dos separados: VIX solo, índices de precio)
    with st.spinner("Cargando histórico índices..."):
        h_vix  = obtener_historico_yf("^VIX",     _yf_period)
        h_spx  = obtener_historico_yf("^GSPC",    _yf_period)
        h_ndx  = obtener_historico_yf("^NDX",     _yf_period)
        h_ibex = obtener_historico_yf("^IBEX",    _yf_period)
        h_dax  = obtener_historico_yf("^GDAXI",   _yf_period)
        h_sx50 = obtener_historico_yf("^STOXX50E",_yf_period)

    # Normalizar a base 100 para comparar en el mismo gráfico
    def _base100(s):
        if s is None or s.empty:
            return s
        if hasattr(s.index, "tz") and s.index.tz is not None:
            s = s.copy()
            s.index = s.index.tz_localize(None)
        s = s[s.index >= _fecha_ini]
        if s.empty:
            return s
        return (s / s.iloc[0]) * 100

    fig_idx = _macro_chart({
        "S&P 500":     _base100(h_spx),
        "Nasdaq 100":  _base100(h_ndx),
        "IBEX 35":     _base100(h_ibex),
        "DAX 40":      _base100(h_dax),
        "Eurostoxx 50":_base100(h_sx50),
    }, unidad="", fecha_inicio=_fecha_ini)
    fig_idx.update_layout(yaxis_title="Base 100")
    st.plotly_chart(fig_idx, use_container_width=True, config={"displayModeBar": False})

    # VIX aparte
    st.caption("**VIX — Volatilidad implícita**")
    fig_vix = _macro_chart({"VIX": h_vix}, unidad="", fecha_inicio=_fecha_ini, height=180)
    fig_vix.update_traces(line_color="#dc2626")
    fig_vix.add_hline(y=30, line_dash="dot", line_color="#dc2626",
                      annotation_text="Pánico (30)", annotation_position="right")
    fig_vix.add_hline(y=15, line_dash="dot", line_color="#16a34a",
                      annotation_text="Complacencia (15)", annotation_position="right")
    st.plotly_chart(fig_vix, use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")
    st.caption("**Fuentes:** BCE Statistical Data Warehouse · BIS WS_CBPOL · BLS · "
               "Yahoo Finance · Análisis educativo — no constituye asesoramiento de inversión (MiFID II).")


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

TIMEFRAMES = ["Diario", "Semanal", "Trimestral", "Anual"]


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
# DIVERGENCIAS TÉCNICAS
# =============================================================================

def detectar_divergencias(hist, n_sesiones=60):
    """
    Detecta divergencias entre precio y cuatro indicadores:
    RSI, MACD histograma, Volumen y OBV.
    Retorna lista de dicts: {tipo, direccion, descripcion, emoji, fuerza}
    """
    import numpy as _np_div

    if len(hist) < 30:
        return []

    df    = hist.tail(n_sesiones).copy()
    close = df["Close"].squeeze()
    vol   = df["Volume"].squeeze()
    divs  = []

    # ── Helper: extremos locales ─────────────────────────────────────
    def _extremos(s, order=5):
        v = s.values
        n = len(v)
        picos, valles = [], []
        for i in range(order, n - order):
            bloque = v[i - order: i + order + 1]
            if v[i] == bloque.max() and v[i] > bloque.mean():
                picos.append(i)
            if v[i] == bloque.min() and v[i] < bloque.mean():
                valles.append(i)
        return picos, valles

    # ── 1. RSI ───────────────────────────────────────────────────────
    try:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = 100 - (100 / (1 + gain / loss.replace(0, _np_div.nan)))

        picos, valles = _extremos(close, order=4)

        if len(picos) >= 2:
            p1, p2 = picos[-2], picos[-1]
            if close.iloc[p2] > close.iloc[p1] and rsi.iloc[p2] < rsi.iloc[p1]:
                dp  = (close.iloc[p2] - close.iloc[p1]) / close.iloc[p1] * 100
                dr  = rsi.iloc[p1] - rsi.iloc[p2]
                divs.append({
                    "tipo": "RSI", "direccion": "bajista", "emoji": "🔴",
                    "fuerza": "fuerte" if dr > 5 else "moderada",
                    "descripcion": (
                        f"Precio marcó nuevo máximo (+{dp:.1f}%) pero RSI cedió "
                        f"−{dr:.1f} pts. Posible agotamiento alcista."
                    ),
                })

        if len(valles) >= 2:
            v1, v2 = valles[-2], valles[-1]
            if close.iloc[v2] < close.iloc[v1] and rsi.iloc[v2] > rsi.iloc[v1]:
                dp = (close.iloc[v1] - close.iloc[v2]) / close.iloc[v1] * 100
                dr = rsi.iloc[v2] - rsi.iloc[v1]
                divs.append({
                    "tipo": "RSI", "direccion": "alcista", "emoji": "🟢",
                    "fuerza": "fuerte" if dr > 5 else "moderada",
                    "descripcion": (
                        f"Precio marcó nuevo mínimo (−{dp:.1f}%) pero RSI "
                        f"aguantó +{dr:.1f} pts. Posible agotamiento bajista."
                    ),
                })
    except Exception:
        pass

    # ── 2. MACD histograma ───────────────────────────────────────────
    try:
        ema12  = close.ewm(span=12, adjust=False).mean()
        ema26  = close.ewm(span=26, adjust=False).mean()
        hist_m = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()
        ref    = abs(hist_m.mean()) * 0.5

        picos, valles = _extremos(close, order=4)

        if len(picos) >= 2:
            p1, p2 = picos[-2], picos[-1]
            if close.iloc[p2] > close.iloc[p1] and hist_m.iloc[p2] < hist_m.iloc[p1]:
                divs.append({
                    "tipo": "MACD", "direccion": "bajista", "emoji": "🔴",
                    "fuerza": "fuerte" if abs(hist_m.iloc[p2] - hist_m.iloc[p1]) > ref else "moderada",
                    "descripcion": (
                        "Precio en nuevo máximo pero el histograma MACD "
                        "pierde altura. El momentum comprador se debilita."
                    ),
                })

        if len(valles) >= 2:
            v1, v2 = valles[-2], valles[-1]
            if close.iloc[v2] < close.iloc[v1] and hist_m.iloc[v2] > hist_m.iloc[v1]:
                divs.append({
                    "tipo": "MACD", "direccion": "alcista", "emoji": "🟢",
                    "fuerza": "fuerte" if abs(hist_m.iloc[v2] - hist_m.iloc[v1]) > ref else "moderada",
                    "descripcion": (
                        "Precio en nuevo mínimo pero el histograma MACD "
                        "reduce la presión. El momentum bajista se agota."
                    ),
                })
    except Exception:
        pass

    # ── 3. Volumen vs Precio ─────────────────────────────────────────
    try:
        x  = _np_div.arange(len(close))
        ps = _np_div.polyfit(x, close.values.astype(float), 1)[0] / float(close.mean())
        vs = _np_div.polyfit(x, vol.values.astype(float),   1)[0] / float(vol.mean())
        th = 0.0003

        if ps > th and vs < -th:
            divs.append({
                "tipo": "Volumen", "direccion": "bajista", "emoji": "🔴",
                "fuerza": "moderada",
                "descripcion": (
                    "Precio con pendiente alcista pero volumen cayendo. "
                    "Subida sin convicción compradora — posible trampa alcista."
                ),
            })
        elif ps < -th and vs > th:
            divs.append({
                "tipo": "Volumen", "direccion": "alcista", "emoji": "🟢",
                "fuerza": "moderada",
                "descripcion": (
                    "Precio con pendiente bajista pero volumen creciendo. "
                    "Posible acumulación institucional bajo la caída."
                ),
            })
    except Exception:
        pass

    # ── 4. OBV vs Precio ─────────────────────────────────────────────
    try:
        obv = (_np_div.sign(close.diff()) * vol).fillna(0).cumsum()
        x   = _np_div.arange(len(close))
        ps  = _np_div.polyfit(x, close.values.astype(float), 1)[0] / float(close.mean())
        os_ = _np_div.polyfit(x, obv.values.astype(float),   1)[0] / (abs(float(obv.mean())) + 1)
        th  = 0.0003

        if ps < -th and os_ > th:
            divs.append({
                "tipo": "OBV", "direccion": "alcista", "emoji": "🟢",
                "fuerza": "fuerte",
                "descripcion": (
                    "OBV acumula mientras el precio cae. "
                    "El dinero institucional compra la debilidad — "
                    "divergencia alcista de alta relevancia."
                ),
            })
        elif ps > th and os_ < -th:
            divs.append({
                "tipo": "OBV", "direccion": "bajista", "emoji": "🔴",
                "fuerza": "fuerte",
                "descripcion": (
                    "OBV distribuye mientras el precio sube. "
                    "Salida de manos fuertes bajo la subida — "
                    "divergencia bajista de alta relevancia."
                ),
            })
    except Exception:
        pass

    return divs


# =============================================================================
# HUECOS DE PRECIO
# =============================================================================

def detectar_huecos(hist: "pd.DataFrame", n_dias: int = 252,
                    min_pct: float = 0.3) -> list:
    """
    Detecta huecos de precio abiertos (no rellenados) en los últimos n_dias.
    - Hueco alcista: low[i] > high[i-1]  → zona de soporte potencial
    - Hueco bajista: high[i] < low[i-1]  → zona de resistencia potencial
    Un hueco se considera abierto si el precio nunca ha vuelto a cruzar la zona.
    Retorna lista de dicts ordenada por distancia al precio actual (más cercano primero).
    """
    if hist is None or len(hist) < 5:
        return []

    df = hist.tail(n_dias).copy()
    if len(df) < 5:
        return []

    precio_actual = float(df["Close"].iloc[-1])
    huecos = []

    for i in range(1, len(df)):
        prev_high = float(df["High"].iloc[i - 1])
        prev_low  = float(df["Low"].iloc[i - 1])
        curr_high = float(df["High"].iloc[i])
        curr_low  = float(df["Low"].iloc[i])
        fecha     = df.index[i]

        # ── Hueco alcista ─────────────────────────────────────────────────────
        if curr_low > prev_high:
            gap_low  = prev_high
            gap_high = curr_low
            gap_pct  = (gap_high - gap_low) / gap_low * 100
            if gap_pct < min_pct:
                continue
            # Abierto si ningún low posterior ha bajado de gap_low
            future_lows = df["Low"].iloc[i + 1:].values
            abierto = all(fl > gap_low for fl in future_lows) if len(future_lows) > 0 else True
            if abierto:
                dist_pct = (precio_actual - gap_high) / gap_high * 100
                dias = int((df.index[-1] - fecha).days) if hasattr(fecha, 'days') else 0
                try:
                    dias = int((df.index[-1] - fecha).days)
                except Exception:
                    dias = 0
                huecos.append({
                    "fecha":       fecha.strftime("%d/%m/%Y"),
                    "tipo":        "alcista",
                    "gap_low":     round(gap_low, 4),
                    "gap_high":    round(gap_high, 4),
                    "gap_pct":     round(gap_pct, 2),
                    "dist_pct":    round(dist_pct, 2),
                    "dias_abierto": dias,
                })

        # ── Hueco bajista ─────────────────────────────────────────────────────
        elif curr_high < prev_low:
            gap_low  = curr_high
            gap_high = prev_low
            gap_pct  = (gap_high - gap_low) / gap_low * 100
            if gap_pct < min_pct:
                continue
            # Abierto si ningún high posterior ha subido de gap_high
            future_highs = df["High"].iloc[i + 1:].values
            abierto = all(fh < gap_high for fh in future_highs) if len(future_highs) > 0 else True
            if abierto:
                dist_pct = (precio_actual - gap_low) / gap_low * 100
                try:
                    dias = int((df.index[-1] - fecha).days)
                except Exception:
                    dias = 0
                huecos.append({
                    "fecha":       fecha.strftime("%d/%m/%Y"),
                    "tipo":        "bajista",
                    "gap_low":     round(gap_low, 4),
                    "gap_high":    round(gap_high, 4),
                    "gap_pct":     round(gap_pct, 2),
                    "dist_pct":    round(dist_pct, 2),
                    "dias_abierto": dias,
                })

    # Ordenar: más cercano al precio actual primero
    huecos.sort(key=lambda x: abs(x["dist_pct"]))
    return huecos


# CONVERGENCIA TÉCNICA — Pivots + Medias + Indicadores
# =============================================================================

def calcular_convergencia_tecnica(resultados_pivots, medias, precio,
                                   rsi_val, macd_val, macd_señal,
                                   macd_hist_val, sar_tend, pct_b, tolerancia=0.30):
    """
    Detecta dos tipos de convergencia:
    1. Niveles reforzados: zonas donde un pivot y una media móvil coinciden.
    2. Señal direccional: acuerdo entre todos los indicadores sobre la dirección.
    """
    # ── 1. Niveles reforzados (precio pivot ≈ precio media) ──────────────────
    niveles_pivot = []
    for tf, nivs in resultados_pivots.items():
        if not nivs:
            continue
        for clave, val in nivs.items():
            if clave.startswith("_"):
                continue
            tipo = "R" if clave.startswith("R") else ("S" if clave.startswith("S") else "PP")
            niveles_pivot.append({"tf": tf, "nivel": clave, "tipo": tipo, "precio": val})

    niveles_reforzados = []
    for piv in niveles_pivot:
        for periodo, (sma, ema) in medias.items():
            if abs(piv["precio"] - sma) <= tolerancia:
                niveles_reforzados.append({
                    "precio": round((piv["precio"] + sma) / 2, 4),
                    "pivot": f"{piv['nivel']} {piv['tf'][:3]}",
                    "media": f"SMA{periodo}",
                    "tipo": piv["tipo"],
                    "detalle": f"{piv['nivel']} {piv['tf']} + SMA{periodo}",
                })
            if abs(piv["precio"] - ema) <= tolerancia:
                niveles_reforzados.append({
                    "precio": round((piv["precio"] + ema) / 2, 4),
                    "pivot": f"{piv['nivel']} {piv['tf'][:3]}",
                    "media": f"EMA{periodo}",
                    "tipo": piv["tipo"],
                    "detalle": f"{piv['nivel']} {piv['tf']} + EMA{periodo}",
                })

    # Deduplicar zonas muy cercanas (±tolerancia/2)
    niveles_reforzados.sort(key=lambda x: x["precio"], reverse=True)
    dedup = []
    for nr in niveles_reforzados:
        if not dedup or abs(nr["precio"] - dedup[-1]["precio"]) > tolerancia / 2:
            dedup.append(nr)

    # ── 2. Señal direccional ─────────────────────────────────────────────────
    señales = []

    # RSI
    if rsi_val is not None:
        if rsi_val > 70:
            señales.append(("RSI 14", "🔴 Sobrecomprado", "bajista", rsi_val))
        elif rsi_val < 30:
            señales.append(("RSI 14", "🟢 Sobrevendido", "alcista", rsi_val))
        elif rsi_val >= 55:
            señales.append(("RSI 14", "🔵 Zona alcista", "alcista", rsi_val))
        elif rsi_val <= 45:
            señales.append(("RSI 14", "🟠 Zona bajista", "bajista", rsi_val))
        else:
            señales.append(("RSI 14", "⚪ Neutro", "neutro", rsi_val))

    # MACD
    if macd_val is not None and macd_señal is not None:
        if macd_val > macd_señal and macd_hist_val > 0:
            señales.append(("MACD", "🟢 Alcista + acelerando", "alcista", macd_val))
        elif macd_val > macd_señal:
            señales.append(("MACD", "🔵 Alcista (histograma –)", "alcista", macd_val))
        elif macd_val < macd_señal and macd_hist_val < 0:
            señales.append(("MACD", "🔴 Bajista + acelerando", "bajista", macd_val))
        else:
            señales.append(("MACD", "🟠 Bajista (histograma +)", "bajista", macd_val))

    # SAR
    if sar_tend:
        if sar_tend == "ALCISTA":
            señales.append(("SAR Parabólico", "🟢 Tendencia alcista", "alcista", None))
        else:
            señales.append(("SAR Parabólico", "🔴 Tendencia bajista", "bajista", None))

    # Bollinger %B
    if pct_b is not None:
        if pct_b > 80:
            señales.append(("Bollinger %B", f"🔴 Sobrecomprado ({pct_b:.0f}%)", "bajista", pct_b))
        elif pct_b < 20:
            señales.append(("Bollinger %B", f"🟢 Sobrevendido ({pct_b:.0f}%)", "alcista", pct_b))
        elif pct_b >= 50:
            señales.append(("Bollinger %B", f"🔵 Mitad alta ({pct_b:.0f}%)", "alcista", pct_b))
        else:
            señales.append(("Bollinger %B", f"🟠 Mitad baja ({pct_b:.0f}%)", "bajista", pct_b))

    # Precio vs medias
    for periodo, (sma, ema) in sorted(medias.items()):
        if precio and sma:
            dir_sma = "alcista" if precio > sma else "bajista"
            emoji = "🟢" if dir_sma == "alcista" else "🔴"
            señales.append((f"SMA {periodo}", f"{emoji} Precio {'>' if dir_sma == 'alcista' else '<'} SMA{periodo}", dir_sma, sma))

    # Conteo
    alcistas = sum(1 for s in señales if s[2] == "alcista")
    bajistas = sum(1 for s in señales if s[2] == "bajista")
    total = len([s for s in señales if s[2] != "neutro"])

    if total > 0:
        pct_alcista = alcistas / total * 100
    else:
        pct_alcista = 50

    if pct_alcista >= 70:
        consenso = ("alcista", "🟢", f"{pct_alcista:.0f}% de indicadores alcistas")
    elif pct_alcista <= 30:
        consenso = ("bajista", "🔴", f"{100-pct_alcista:.0f}% de indicadores bajistas")
    else:
        consenso = ("mixto", "🟡", f"Sin consenso claro ({alcistas}↑ / {bajistas}↓)")

    return dedup, señales, consenso


def _url_google(query: str) -> str:
    import urllib.parse
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def _url_investopedia(termino: str) -> str:
    import urllib.parse
    return "https://www.investopedia.com/search?q=" + urllib.parse.quote(termino)


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
# GENERACIÓN DE INFORME HTML (multi-columna)
# =============================================================================

def generar_informe_html(ticker: str, nombre: str, tipo_activo: str, precio: float,
                          cambio: float, cambio_pct: float, h52, l52, currency: str,
                          sistema: str, resultados_pivots: dict, confluencias: list,
                          semaforo: str, pct_semaforo: float, factores_semaforo: list,
                          rsi_val, macd_val, macd_señal, macd_hist_val,
                          sar_val: float, sar_tend: str, pct_b: float,
                          medias: dict, vol_data: dict, fundamentales: dict,
                          tolerancia: float = 0.20,
                          niveles_reforzados: list = None,
                          señales_dir: list = None,
                          consenso_dir: tuple = None,
                          divergencias_tecnicas: list = None,
                          bb_sup: float = None,
                          bb_med: float = None,
                          bb_inf: float = None,
                          huecos: list = None) -> str:
    """Informe HTML self-contained con layout multi-columna (mismo diseño que pantalla)."""

    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    sem_colors = {"verde": "#22c55e", "amarillo": "#f59e0b", "rojo": "#ef4444"}
    sem_color  = sem_colors.get(semaforo, "#94a3b8")
    emoji_sem  = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(semaforo, "⚪")
    var_color  = "#22c55e" if cambio_pct >= 0 else "#ef4444"
    h52_str = f"{h52:.2f}" if h52 else "—"
    l52_str = f"{l52:.2f}" if l52 else "—"

    # CSS como string plano (los {} son CSS, no f-string)
    css = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',Arial,sans-serif; font-size:13px; color:#1e293b; background:#f1f5f9; }
.header { background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%); color:white; padding:24px 32px; }
.ticker-tag { font-size:13px; opacity:.75; margin-bottom:6px; letter-spacing:1px; text-transform:uppercase; }
.precio-row { display:flex; align-items:baseline; gap:18px; margin-bottom:10px; }
.precio-val { font-size:44px; font-weight:800; letter-spacing:-2px; }
.variacion  { font-size:20px; font-weight:600; }
.empresa    { font-size:14px; opacity:.9; margin-bottom:12px; }
.chips { display:flex; gap:10px; flex-wrap:wrap; }
.chip  { background:rgba(255,255,255,.18); border-radius:20px; padding:3px 12px; font-size:12px; }
.body  { padding:20px 32px 32px; }
h2 { font-size:12px; font-weight:700; color:#1e3a5f; text-transform:uppercase;
     letter-spacing:.8px; margin-bottom:12px; padding-bottom:5px; border-bottom:2px solid #2563eb; }
.card { background:white; border-radius:10px; padding:18px 20px; margin-bottom:14px;
        box-shadow:0 1px 4px rgba(0,0,0,.07); }
.pivot-row { display:grid; grid-template-columns:repeat(4,1fr) 1.6fr; gap:10px; align-items:start; }
.three-col { display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; }
.col-title { font-size:11px; font-weight:700; color:#1e3a5f; text-transform:uppercase;
             letter-spacing:.5px; margin-bottom:6px; padding-bottom:3px; border-bottom:1px solid #e2e8f0; }
.sem-row  { display:flex; gap:20px; align-items:flex-start; }
.sem-badge { min-width:88px; text-align:center; border:3px solid; border-radius:12px; padding:12px 8px; }
.sem-emoji { font-size:30px; line-height:1; }
.sem-label { font-size:15px; font-weight:800; margin-top:6px; }
.sem-pct   { font-size:22px; font-weight:700; color:#1e293b; }
.fac-grid  { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; flex:1; }
.fac-card  { background:#f1f5f9; border-radius:8px; padding:9px 11px; }
.fac-lbl   { font-size:11px; color:#64748b; font-weight:500; margin-bottom:3px; }
.fac-val   { font-size:13px; font-weight:700; }
.tf-block  { margin-bottom:16px; }
.tf-title  { font-size:12px; font-weight:700; color:#475569; background:#f1f5f9;
             padding:4px 10px; border-radius:4px; margin-bottom:6px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th { background:#1e3a5f; color:white; padding:5px 8px; text-align:left; font-weight:600; }
td { padding:4px 8px; border-bottom:1px solid #e2e8f0; }
tr:nth-child(even) td { background:#f8fafc; }
.nR  { color:#dc2626; font-weight:700; }
.nPP { color:#2563eb; font-weight:800; }
.nS  { color:#16a34a; font-weight:700; }
.dPos  { color:#dc2626; font-size:11px; }
.dNeg  { color:#16a34a; font-size:11px; }
.dZero { color:#2563eb; font-size:11px; font-weight:700; }
.conf-item   { background:#fffbeb; border-left:3px solid #f59e0b; border-radius:4px;
               padding:8px 12px; margin-bottom:8px; }
.conf-row    { display:flex; justify-content:space-between; align-items:center; margin-bottom:3px; }
.conf-precio { font-size:16px; font-weight:800; }
.conf-stars  { color:#f59e0b; }
.conf-dist   { font-size:11px; color:#64748b; }
.conf-nivs   { font-size:11px; color:#64748b; }
.empty { color:#94a3b8; font-style:italic; padding:16px 0; text-align:center; font-size:13px; }
.ind-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }
.ind-card { background:#f8fafc; border-radius:6px; padding:9px 11px; border:1px solid #e2e8f0; }
.ind-lbl  { font-size:11px; color:#64748b; margin-bottom:2px; }
.ind-val  { font-size:14px; font-weight:700; }
.ind-sub  { font-size:11px; color:#64748b; margin-top:2px; }
.vol-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px; }
.vol-card { background:#f8fafc; border-radius:6px; padding:9px 11px; border:1px solid #e2e8f0; }
.vol-lbl  { font-size:11px; color:#64748b; margin-bottom:2px; }
.vol-val  { font-size:18px; font-weight:700; }
.vol-sub  { font-size:11px; color:#64748b; }
.vol-det  { font-size:12px; color:#64748b; padding:8px 0; }
.fund-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
.fund-card { background:#f8fafc; border-radius:6px; padding:9px 11px; border:1px solid #e2e8f0; }
.fund-lbl  { font-size:11px; color:#64748b; margin-bottom:2px; }
.fund-val  { font-size:13px; font-weight:700; }
.footer { text-align:center; font-size:11px; color:#94a3b8; padding:16px 32px;
          border-top:1px solid #e2e8f0; }
@media print { body { background:white; } .card { box-shadow:none; border:1px solid #e2e8f0; } }
"""

    # ── Factores semáforo ────────────────────────────────────────────────
    fac_cards = "".join(
        f'<div class="fac-card">'
        f'<div class="fac-lbl">{fac}</div>'
        f'<div class="fac-val">{desc}</div>'
        f'</div>'
        for fac, desc, _ in factores_semaforo
    )

    # ── Pivot tables ─────────────────────────────────────────────────────
    niv_orden = ["R4","R3","R2","R1","PP","S1","S2","S3","S4","M1","M2","M3","M4","M5"]
    pivot_blocks = ""
    for tf in TIMEFRAMES:
        datos_tf = resultados_pivots.get(tf)
        if not datos_tf:
            continue
        filas = ""
        for nv in niv_orden:
            if nv not in datos_tf or nv.startswith("_"):
                continue
            val  = datos_tf[nv]
            dist = ((val - precio) / precio * 100) if precio else 0
            if abs(dist) < 0.001:
                dist_str, dist_cls = "PP", "dZero"
            elif dist > 0:
                dist_str, dist_cls = f"+{dist:.2f}%", "dPos"
            else:
                dist_str, dist_cls = f"{dist:.2f}%", "dNeg"
            nv_cls = ("nR" if nv.startswith("R") else
                      ("nPP" if nv == "PP" else
                       ("nS" if nv.startswith("S") else "")))
            filas += (
                f'<tr>'
                f'<td class="{nv_cls}">{nv}</td>'
                f'<td><b>{val:.4f}</b></td>'
                f'<td class="{dist_cls}">{dist_str}</td>'
                f'</tr>'
            )
        if filas:
            pivot_blocks += (
                f'<div class="tf-block">'
                f'<div class="tf-title">&#9658; {tf}</div>'
                f'<table>'
                f'<thead><tr><th>Nivel</th><th>Precio</th><th>Dist.</th></tr></thead>'
                f'<tbody>{filas}</tbody>'
                f'</table>'
                f'</div>'
            )

    # ── Confluencias ──────────────────────────────────────────────────────
    if confluencias:
        conf_items = ""
        for c in confluencias[:10]:
            niv_str = " · ".join(
                f"{n['timeframe'][:3]} {n['nivel']}" for n in c["niveles"])
            dist = ((c["precio"] - precio) / precio * 100) if precio else 0
            dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
            conf_items += (
                f'<div class="conf-item">'
                f'<div class="conf-row">'
                f'<span class="conf-precio">{c["precio"]:.4f}</span>'
                f'<span><span class="conf-stars">{c["estrellas"]}</span>'
                f'<span class="conf-dist"> {dist_str}</span></span>'
                f'</div>'
                f'<div class="conf-nivs">{niv_str}</div>'
                f'</div>'
            )
        conf_html = conf_items
    else:
        conf_html = f'<div class="empty">Sin confluencias &#177;{tolerancia:.2f}</div>'

    # ── Indicadores ───────────────────────────────────────────────────────
    def _ind(lbl, val, sub=""):
        sub_h = f'<div class="ind-sub">{sub}</div>' if sub else ""
        return (
            f'<div class="ind-card">'
            f'<div class="ind-lbl">{lbl}</div>'
            f'<div class="ind-val">{val}</div>'
            f'{sub_h}'
            f'</div>'
        )

    rsi_sub = ("Sobrecomprado 🔴" if rsi_val > 70
               else ("Sobrevendido 🟢" if rsi_val < 30 else "Neutro ⚪"))
    # Bandas de Bollinger — usar valores pasados o fallback a "—"
    bb_sup_str = f"{bb_sup:.4f}" if bb_sup is not None else "—"
    bb_med_str = f"{bb_med:.4f}" if bb_med is not None else "—"
    bb_inf_str = f"{bb_inf:.4f}" if bb_inf is not None else "—"
    ind_base_html = (
        _ind("RSI 14", f"{rsi_val:.1f}", rsi_sub) +
        _ind("MACD", f"{macd_val:.4f}") +
        _ind("MACD Señal", f"{macd_señal:.4f}") +
        _ind("MACD Histograma", f"{macd_hist_val:+.4f}", "↑ Alcista" if macd_hist_val > 0 else "↓ Bajista") +
        _ind("Bollinger Superior", bb_sup_str) +
        _ind("Bollinger Media", bb_med_str) +
        _ind("Bollinger Inferior", bb_inf_str) +
        _ind("Bollinger %B", f"{pct_b:.1f}%") +
        _ind("Parabolic SAR", sar_tend, f"{sar_val:.4f}")
    )
    ind_med_html = ""
    for p_m in [20, 50, 200]:
        if p_m in medias:
            sma, ema = medias[p_m]
            diff = precio - sma
            ind_med_html += (
                _ind(f"SMA {p_m}", f"{sma:.4f}",
                     f"Dist: {diff:+.4f} ({diff/sma*100:+.1f}%)") +
                _ind(f"EMA {p_m}", f"{ema:.4f}")
            )

    # ── Volumen ───────────────────────────────────────────────────────────
    if vol_data:
        vol_html = (
            f'<div class="vol-grid">'
            f'<div class="vol-card">'
            f'<div class="vol-lbl">Ratio vs 10 sesiones</div>'
            f'<div class="vol-val">{vol_data["ratio_10d"]:.0f}%</div>'
            f'<div class="vol-sub">{vol_data["clasificacion_10d"]}</div>'
            f'</div>'
            f'<div class="vol-card">'
            f'<div class="vol-lbl">Ratio vs 3 meses</div>'
            f'<div class="vol-val">{vol_data["ratio_3m"]:.0f}%</div>'
            f'<div class="vol-sub">{vol_data["clasificacion_3m"]}</div>'
            f'</div>'
            f'</div>'
            f'<div class="vol-det">'
            f'Sesi&#243;n: <b>{_fmt_numero(vol_data["volumen"])}</b> &nbsp;&#183;&nbsp; '
            f'Media 10d: <b>{_fmt_numero(vol_data["media_10d"])}</b> &nbsp;&#183;&nbsp; '
            f'Media 3m: <b>{_fmt_numero(vol_data["media_3m"])}</b>'
            f'</div>'
        )
    else:
        vol_html = '<div class="empty">Sin datos de volumen</div>'

    # ── Fundamentales ─────────────────────────────────────────────────────
    fund_section = ""
    if fundamentales:
        fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
        if fund_items:
            fund_cards = "".join(
                f'<div class="fund-card">'
                f'<div class="fund-lbl">{k}</div>'
                f'<div class="fund-val">{v}</div>'
                f'</div>'
                for k, v in fund_items
            )
            fund_section = (
                f'<div class="card">'
                f'<h2>&#128203; Datos Fundamentales</h2>'
                f'<div class="fund-grid">{fund_cards}</div>'
                f'</div>'
            )

    # ── Convergencia Técnica (HTML) ───────────────────────────────────────
    _conv_section = ""
    if niveles_reforzados or señales_dir:
        # Niveles reforzados
        niv_rows = ""
        for nr in (niveles_reforzados or []):
            dist = ((nr["precio"] - precio) / precio * 100) if precio else 0
            dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
            tipo_label = "Resistencia" if nr["tipo"] == "R" else ("Soporte" if nr["tipo"] == "S" else "Pivot")
            tipo_color = "#ef4444" if nr["tipo"] == "R" else ("#22c55e" if nr["tipo"] == "S" else "#3b82f6")
            niv_rows += (
                f'<tr>'
                f'<td style="font-weight:700;color:{tipo_color}">{nr["precio"]:.4f}</td>'
                f'<td style="color:#64748b;font-size:11px">{dist_str}</td>'
                f'<td>{nr["pivot"]}</td>'
                f'<td>{nr["media"]}</td>'
                f'<td style="color:{tipo_color};font-size:11px">{tipo_label}</td>'
                f'</tr>'
            )
        niv_html = (
            f'<table><thead><tr>'
            f'<th>Precio</th><th>Dist.</th><th>Pivot</th><th>Media</th><th>Tipo</th>'
            f'</tr></thead><tbody>{niv_rows}</tbody></table>'
            if niv_rows else '<div style="color:#94a3b8;font-size:12px">Sin niveles dentro de la tolerancia activa</div>'
        )
        # Señal de consenso
        cons_emoji = consenso_dir[1] if consenso_dir else "⚪"
        cons_label = consenso_dir[2] if consenso_dir else "—"
        dir_rows = ""
        for nombre_s, desc_s, dir_s, _ in (señales_dir or []):
            dir_color = "#22c55e" if dir_s == "alcista" else ("#ef4444" if dir_s == "bajista" else "#94a3b8")
            dir_rows += (
                f'<tr>'
                f'<td style="font-weight:600">{nombre_s}</td>'
                f'<td>{desc_s}</td>'
                f'<td style="color:{dir_color};font-weight:700;text-align:center">'
                f'{"↑" if dir_s == "alcista" else ("↓" if dir_s == "bajista" else "–")}</td>'
                f'</tr>'
            )
        _conv_section = (
            f'<div class="card">\n'
            f'<h2>&#128260; Convergencia T&#233;cnica</h2>\n'
            f'<div style="display:grid;grid-template-columns:1.2fr 1fr;gap:20px;align-items:start">\n'
            f'<div>\n'
            f'<div class="col-title">Niveles Reforzados (Pivot + Media M&#243;vil)</div>\n'
            f'{niv_html}\n'
            f'</div>\n'
            f'<div>\n'
            f'<div class="col-title">Se&#241;al de Consenso</div>\n'
            f'<div style="background:#f1f5f9;border-radius:8px;padding:10px 14px;margin-bottom:10px;'
            f'font-size:16px;font-weight:700">{cons_emoji} {cons_label}</div>\n'
            f'<table><thead><tr><th>Indicador</th><th>Estado</th><th style="text-align:center">Dir.</th>'
            f'</tr></thead><tbody>{dir_rows}</tbody></table>\n'
            f'</div>\n'
            f'</div>\n'
            f'</div>\n'
        )

    # ── Sección Divergencias Técnicas ────────────────────────────────────────
    _divs_section = ""
    if divergencias_tecnicas:
        _dv_alc = [d for d in divergencias_tecnicas if d["direccion"] == "alcista"]
        _dv_baj = [d for d in divergencias_tecnicas if d["direccion"] == "bajista"]

        def _div_badge(d):
            fuerza = d.get("fuerza", "media")
            f_color = {"fuerte": "#15803d", "media": "#d97706", "débil": "#94a3b8"}.get(fuerza, "#94a3b8")
            tipo_em = "🔼" if d["direccion"] == "alcista" else "🔽"
            return (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:6px 10px;background:#f8fafc;border-radius:6px;margin-bottom:6px;'
                f'border-left:3px solid {f_color}">'
                f'<span style="font-weight:600;font-size:12px">{tipo_em} {d["tipo"]} — {d["descripcion"]}</span>'
                f'<span style="font-size:11px;color:{f_color};text-transform:capitalize">{fuerza}</span>'
                f'</div>'
            )

        _alc_rows = "".join(_div_badge(d) for d in _dv_alc) if _dv_alc else '<div style="color:#94a3b8;font-size:12px">Sin divergencias alcistas</div>'
        _baj_rows = "".join(_div_badge(d) for d in _dv_baj) if _dv_baj else '<div style="color:#94a3b8;font-size:12px">Sin divergencias bajistas</div>'

        _divs_section = (
            f'<div class="card">\n'
            f'<h2>&#9889; Divergencias T&#233;cnicas</h2>\n'
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">\n'
            f'<div>\n'
            f'<div class="col-title" style="color:#15803d">&#9650; Alcistas</div>\n'
            f'{_alc_rows}\n'
            f'</div>\n'
            f'<div>\n'
            f'<div class="col-title" style="color:#dc2626">&#9660; Bajistas</div>\n'
            f'{_baj_rows}\n'
            f'</div>\n'
            f'</div>\n'
            f'</div>\n'
        )

    # ── Huecos de precio ──────────────────────────────────────────────────
    _huecos_section = ""
    if huecos:
        def _hueco_card(h):
            _tipo   = h["tipo"]
            _bg     = "#f0fdf4" if _tipo == "alcista" else "#fef2f2"
            _border = "#16a34a" if _tipo == "alcista" else "#dc2626"
            _label  = "Soporte potencial" if _tipo == "alcista" else "Resistencia potencial"
            _emoji  = "&#9650;" if _tipo == "alcista" else "&#9660;"
            _dist   = h["dist_pct"]
            _dcolor = "#16a34a" if _dist >= 0 else "#dc2626"
            _dstr   = f"+{_dist:.2f}%" if _dist >= 0 else f"{_dist:.2f}%"
            return (
                f'<div style="background:{_bg};border-left:4px solid {_border};'
                f'border-radius:6px;padding:10px 12px;margin-bottom:8px">'
                f'<div style="font-size:11px;color:{_border};font-weight:700;'
                f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">'
                f'{_emoji} Hueco {_tipo} &middot; {_label}</div>'
                f'<div style="font-size:13px;font-weight:700;color:#1e293b">'
                f'{h["gap_low"]:.4f} &#8211; {h["gap_high"]:.4f}</div>'
                f'<div style="font-size:12px;color:#475569;margin-top:3px">'
                f'Tama&#241;o: <b>{h["gap_pct"]:.2f}%</b> &nbsp;&middot;&nbsp; '
                f'Distancia: <b style="color:{_dcolor}">{_dstr}</b></div>'
                f'<div style="font-size:11px;color:#94a3b8;margin-top:3px">'
                f'{h["fecha"]} &middot; {h["dias_abierto"]}d abierto</div>'
                f'</div>'
            )
        _cards = "".join(_hueco_card(h) for h in huecos[:6])
        _huecos_section = (
            f'<div class="card">\n'
            f'<h2>&#128202; Huecos de Precio Abiertos</h2>\n'
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">\n'
            f'{_cards}\n'
            f'</div>\n'
            f'</div>\n'
        )

    # ── Ensamblar ─────────────────────────────────────────────────────────
    return (
        f'<!DOCTYPE html>\n<html lang="es">\n<head>\n'
        f'<meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>PivotAnalyzer &#8212; {ticker.upper()}</title>\n'
        f'<style>{css}</style>\n</head>\n<body>\n'

        f'<div class="header">\n'
        f'<div class="ticker-tag">&#128202; PivotAnalyzer &middot; {ticker.upper()}</div>\n'
        f'<div class="precio-row">\n'
        f'<span class="precio-val">{precio:.4f}'
        f'<span style="font-size:16px;opacity:.7;margin-left:8px">{currency}</span></span>\n'
        f'<span class="variacion" style="color:{var_color}">'
        f'{cambio:+.4f} ({cambio_pct:+.2f}%)</span>\n'
        f'</div>\n'
        f'<div class="empresa">{nombre}</div>\n'
        f'<div class="chips">\n'
        f'<span class="chip">52W m&#225;x: {h52_str}</span>\n'
        f'<span class="chip">52W m&#237;n: {l52_str}</span>\n'
        f'<span class="chip">{tipo_activo}</span>\n'
        f'<span class="chip">Sistema: {sistema}</span>\n'
        f'<span class="chip">Generado: {ahora}</span>\n'
        f'</div>\n</div>\n'

        f'<div class="body">\n'

        # Semáforo
        f'<div class="card">\n'
        f'<h2>&#128680; Sem&#225;foro Global</h2>\n'
        f'<div class="sem-row">\n'
        f'<div class="sem-badge" style="border-color:{sem_color}">\n'
        f'<div class="sem-emoji">{emoji_sem}</div>\n'
        f'<div class="sem-label" style="color:{sem_color}">{semaforo.upper()}</div>\n'
        f'<div class="sem-pct">{pct_semaforo:.0f}%</div>\n'
        f'</div>\n'
        f'<div class="fac-grid">{fac_cards}</div>\n'
        f'</div>\n</div>\n'

        # Pivots: 4 columnas paralelas + confluencias
        f'<div class="card">\n'
        f'<h2>&#128208; Pivot Points &#8212; {sistema}</h2>\n'
        f'<div class="pivot-row">\n'
        f'{pivot_blocks}'
        f'<div>\n<div class="col-title">Confluencias</div>\n{conf_html}</div>\n'
        f'</div>\n</div>\n'

        # Indicadores | Medias | Volumen — 3 columnas
        f'<div class="card three-col">\n'
        f'<div>\n<div class="col-title">Indicadores T&#233;cnicos</div>\n'
        f'<div class="ind-grid">{ind_base_html}</div>\n</div>\n'
        f'<div>\n<div class="col-title">Medias M&#243;viles</div>\n'
        f'<div class="ind-grid">{ind_med_html}</div>\n</div>\n'
        f'<div>\n<div class="col-title">Volumen</div>\n{vol_html}\n</div>\n'
        f'</div>\n'

        # Convergencia Técnica
        + _conv_section
        + _divs_section

        # Huecos de Precio
        + _huecos_section

        # Fundamentales
        + f'{fund_section}\n'

        f'</div>\n'  # end .body

        f'<div class="footer">\n'
        f'An&#225;lisis educativo &nbsp;&middot;&nbsp; '
        f'No constituye asesoramiento de inversi&#243;n regulado bajo MiFID II '
        f'(Directiva 2014/65/UE) &nbsp;&middot;&nbsp; '
        f'Datos con retraso ~15 min v&#237;a Yahoo Finance &nbsp;&middot;&nbsp; '
        f'PivotAnalyzer &mdash; Scriptum\n'
        f'</div>\n</body>\n</html>'
    )


# =============================================================================
# GENERACIÓN DE INFORME HTML — ESTRATEGIA
# =============================================================================

def generar_informe_estrategia_html(ticker: str, nombre: str, precio: float,
                                     ts: str, estrategias: list) -> str:
    """
    Genera un informe HTML auto-contenido para una o varias estrategias.

    estrategias: list of dicts con claves:
      - nombre    : str  (ej. "💰 Dividendos")
      - color     : str  (hex del header)
      - criterios : list of (html_str, ok_int)  — salida de _build_xxx()
      - puntos    : list of str (HTML)           — salida de _interpretar()
      - rec       : str                          — recomendación narrativa
      - popover_md: str                          — texto markdown del ℹ️
    """
    import re as _re

    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── Convertidor markdown → HTML (formato de los popovers) ────────────
    def _md_to_html(md: str) -> str:
        lines = md.split("\n")
        out   = []
        in_ul = False

        def _inline(s):
            # **bold** y *italic*, evita solapamientos
            s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
            s = _re.sub(r"\*([^*]+?)\*",  r'<em style="color:#64748b">\1</em>', s)
            return s

        for raw in lines:
            line = raw.strip()

            # Línea vacía
            if not line:
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                continue

            # Separador
            if line == "---":
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                out.append('<hr style="border:none;border-top:1px solid #e2e8f0;margin:10px 0">')
                continue

            # Ítem de lista
            if line.startswith("- "):
                if not in_ul:
                    out.append('<ul style="margin:4px 0 6px 18px;padding:0">')
                    in_ul = True
                out.append(
                    f'<li style="margin-bottom:3px;font-size:12px;line-height:1.5">'
                    f'{_inline(line[2:])}</li>'
                )
                continue

            # Título italic *Disclaimer*
            if in_ul:
                out.append("</ul>")
                in_ul = False

            # Línea solo en bold (subtítulo de sección)
            m_h = _re.match(r"^\*\*(.+?)\*\*\s*(\*.+?\*)?$", line)
            if m_h:
                titulo = m_h.group(1)
                sub    = m_h.group(2) or ""
                sub_h  = (f' <em style="color:#64748b;font-size:11px">{sub[1:-1]}</em>'
                          if sub else "")
                out.append(
                    f'<div style="font-weight:700;font-size:12.5px;color:#1e3a5f;'
                    f'margin-top:10px;margin-bottom:3px">{titulo}{sub_h}</div>'
                )
            else:
                content = _inline(line)
                out.append(
                    f'<p style="font-size:12px;margin:3px 0;line-height:1.5;'
                    f'color:#374151">{content}</p>'
                )

        if in_ul:
            out.append("</ul>")
        return "\n".join(out)

    # ── CSS ──────────────────────────────────────────────────────────────
    css = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',Arial,sans-serif; font-size:13px;
       color:#1e293b; background:#f1f5f9; }
.header { background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%);
          color:white; padding:22px 32px; }
.ticker-tag { font-size:13px; opacity:.75; margin-bottom:4px;
              letter-spacing:1px; text-transform:uppercase; }
.precio-row { display:flex; align-items:baseline; gap:14px; margin-bottom:8px; }
.precio-val { font-size:38px; font-weight:800; letter-spacing:-1.5px; }
.empresa    { font-size:13px; opacity:.85; }
.chips { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
.chip  { background:rgba(255,255,255,.18); border-radius:20px;
         padding:3px 11px; font-size:11.5px; }
.body  { padding:20px 32px 32px; }
.strat-block { background:white; border-radius:10px;
               box-shadow:0 1px 4px rgba(0,0,0,.08);
               margin-bottom:20px; overflow:hidden; }
.strat-hdr { padding:11px 16px; display:flex; align-items:center;
             justify-content:space-between; }
.strat-hdr-left { display:flex; align-items:center; gap:12px; }
.strat-title { font-size:15px; font-weight:700; color:white; }
.strat-score { font-size:28px; font-weight:800; color:white; line-height:1; }
.strat-pts   { font-size:10px; color:rgba(255,255,255,.7); }
.strat-vrd   { font-size:11px; font-weight:700; color:white;
               background:rgba(255,255,255,.2); border-radius:4px;
               padding:2px 8px; margin-left:6px; }
.strat-body  { display:grid; grid-template-columns:1fr 1fr; gap:0;
               border-top:1px solid #f1f5f9; }
.criteria-col { padding:14px 16px; border-right:1px solid #f1f5f9; }
.analysis-col { padding:14px 16px; }
.col-lbl { font-size:10px; font-weight:700; color:#64748b;
           text-transform:uppercase; letter-spacing:.6px; margin-bottom:8px; }
.crit-row { padding:4px 0; border-bottom:1px solid #f9fafb;
            font-size:12.5px; line-height:1.4; }
.punto-row { padding:3px 0; border-bottom:1px solid #f9fafb;
             font-size:12px; line-height:1.4; }
.rec-box { background:#f8fafc; border-radius:6px; padding:10px 12px;
           margin-top:10px; }
.rec-lbl { font-size:10px; font-weight:700; color:#374151;
           text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }
.rec-txt { font-size:12px; color:#111827; line-height:1.5; }
.explanation { padding:16px 20px; background:#fafbfc;
               border-top:2px solid #f1f5f9; }
.exp-lbl { font-size:10px; font-weight:700; color:#1e3a5f;
           text-transform:uppercase; letter-spacing:.6px;
           margin-bottom:10px; padding-bottom:5px;
           border-bottom:2px solid #2563eb; display:inline-block; }
.footer { text-align:center; font-size:11px; color:#94a3b8;
          padding:14px 32px; border-top:1px solid #e2e8f0; }
@media print { body { background:white; }
  .strat-block { box-shadow:none; border:1px solid #e2e8f0; } }
"""

    # ── Bloques por estrategia ────────────────────────────────────────────
    bloques = ""
    for est in estrategias:
        est_nombre  = est["nombre"]
        color       = est["color"]
        criterios   = est["criterios"]
        puntos      = est["puntos"]
        rec         = est["rec"]
        popover_md  = est["popover_md"]

        # Score
        total  = sum(ok for _, ok in criterios)
        maxpts = len(criterios) * 2
        pct    = int(total / maxpts * 100) if maxpts else 0
        if pct >= 70:   vrd = "OPORTUNIDAD"
        elif pct >= 45: vrd = "VIGILAR"
        else:           vrd = "NO ES EL MOMENTO"

        # Criterios HTML
        crit_rows = "".join(
            f'<div class="crit-row">{html}</div>'
            for html, _ in criterios
        )

        # Puntos de análisis HTML
        puntos_rows = "".join(
            f'<div class="punto-row">{p}</div>'
            for p in puntos
        ) if puntos else '<div style="color:#94a3b8;font-style:italic;font-size:12px">Sin análisis disponible</div>'

        rec_html = (
            f'<div class="rec-box">'
            f'<div class="rec-lbl">Recomendación</div>'
            f'<div class="rec-txt">{rec}</div>'
            f'</div>'
        ) if rec else ""

        exp_html = _md_to_html(popover_md)

        bloques += (
            f'<div class="strat-block">\n'
            f'  <div class="strat-hdr" style="background:{color}">\n'
            f'    <div class="strat-hdr-left">\n'
            f'      <span class="strat-title">{est_nombre}</span>\n'
            f'      <span class="strat-vrd">{vrd}</span>\n'
            f'    </div>\n'
            f'    <div style="text-align:right">\n'
            f'      <span class="strat-score">{pct}</span>'
            f'<span class="strat-pts">&thinsp;/100</span>\n'
            f'    </div>\n'
            f'  </div>\n'
            f'  <div class="strat-body">\n'
            f'    <div class="criteria-col">\n'
            f'      <div class="col-lbl">Criterios de evaluación</div>\n'
            f'      {crit_rows}\n'
            f'    </div>\n'
            f'    <div class="analysis-col">\n'
            f'      <div class="col-lbl">Análisis situacional</div>\n'
            f'      {puntos_rows}\n'
            f'      {rec_html}\n'
            f'    </div>\n'
            f'  </div>\n'
            f'  <div class="explanation">\n'
            f'    <div class="exp-lbl">&#128218; Descripción detallada de la estrategia</div>\n'
            f'    {exp_html}\n'
            f'  </div>\n'
            f'</div>\n'
        )

    return (
        f'<!DOCTYPE html>\n<html lang="es">\n<head>\n'
        f'<meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>PivotAnalyzer &#8212; Estrategia {ticker.upper()}</title>\n'
        f'<style>{css}</style>\n</head>\n<body>\n'

        f'<div class="header">\n'
        f'  <div class="ticker-tag">&#128202; PivotAnalyzer &middot; Informe de Estrategia</div>\n'
        f'  <div class="precio-row">\n'
        f'    <span class="precio-val">{ticker.upper()}</span>\n'
        f'    <span style="font-size:18px;opacity:.9">{nombre}</span>\n'
        f'  </div>\n'
        f'  <div class="chips">\n'
        f'    <span class="chip">Precio: {precio:.4f}</span>\n'
        f'    <span class="chip">Datos: {ts}</span>\n'
        f'    <span class="chip">Generado: {ahora}</span>\n'
        f'    <span class="chip">{len(estrategias)} estrategia{"s" if len(estrategias) > 1 else ""}</span>\n'
        f'  </div>\n'
        f'</div>\n'

        f'<div class="body">\n'
        f'{bloques}'
        f'</div>\n'

        f'<div class="footer">\n'
        f'An&#225;lisis educativo &nbsp;&middot;&nbsp; '
        f'No constituye asesoramiento de inversi&#243;n regulado bajo MiFID II '
        f'(Directiva 2014/65/UE) &nbsp;&middot;&nbsp; '
        f'PivotAnalyzer &mdash; Scriptum\n'
        f'</div>\n</body>\n</html>'
    )


# =============================================================================
# GENERACIÓN DE PDF — ESTRATEGIA
# =============================================================================

def generar_pdf_estrategia(ticker: str, nombre: str, precio: float,
                            ts: str, estrategias: list) -> bytes:
    """
    PDF de estrategia con scorecard + análisis + explicación detallada.

    estrategias: list of dicts con claves:
      - nombre    : str
      - color     : str hex
      - criterios : list of (html_str, ok_int)
      - puntos    : list of str  (texto plano / HTML simple)
      - rec       : str
      - popover_md: str  (markdown del ℹ️)
    """
    import re as _re

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    CA  = colors.HexColor("#1e3a5f")
    GF  = colors.HexColor("#f1f5f9")
    GB  = colors.HexColor("#e2e8f0")
    BL  = colors.white
    VE  = colors.HexColor("#16a34a")
    AM  = colors.HexColor("#f59e0b")
    RO  = colors.HexColor("#dc2626")

    def _strip(s: str) -> str:
        for em, rep in [("✅", "[+]"), ("⚠️", "[~]"), ("❌", "[-]"),
                        ("⛔", "[!]"), ("🔼", "^"), ("🔽", "v"),
                        ("🟢", ""), ("🟡", ""), ("🔴", ""), ("⚪", ""),
                        ("📊", ""), ("💰", ""), ("📈", ""), ("🏷️", ""),
                        ("🚀", ""), ("🔄", ""), ("🛡️", ""), ("📖", ""),
                        ("🌍", ""), ("📉", ""), ("💡", ""), ("🎯", "")]:
            s = s.replace(em, rep)
        return "".join(c if ord(c) < 256 else "??" for c in s).strip()

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _html_to_plain(html: str) -> str:
        text = _re.sub(r"<[^>]+>", " ", html)
        text = _re.sub(r"\s+", " ", text).strip()
        return _strip(text)

    _SS = getSampleStyleSheet()
    _n  = [0]
    def _p(**kw):
        _n[0] += 1
        return ParagraphStyle(f"_pes{_n[0]}", parent=_SS["Normal"], **kw)

    # Estilos
    S_HDR_T  = _p(fontName="Helvetica-Bold",    fontSize=20, textColor=BL)
    S_HDR_S  = _p(fontName="Helvetica",         fontSize=9,  textColor=colors.HexColor("#93c5fd"))
    S_HDR_P  = _p(fontName="Helvetica-Bold",    fontSize=14, textColor=BL, alignment=TA_RIGHT)
    S_HDR_D  = _p(fontName="Helvetica",         fontSize=7.5,textColor=BL, alignment=TA_RIGHT)
    S_EST_N  = _p(fontName="Helvetica-Bold",    fontSize=11, textColor=BL)
    S_EST_V  = _p(fontName="Helvetica-Bold",    fontSize=9,  textColor=BL, alignment=TA_CENTER)
    S_SCORE  = _p(fontName="Helvetica-Bold",    fontSize=22, textColor=BL, alignment=TA_RIGHT)
    S_SCORE2 = _p(fontName="Helvetica",         fontSize=7,  textColor=colors.HexColor("#dbeafe"), alignment=TA_RIGHT)
    S_SEC_H  = _p(fontName="Helvetica-Bold",    fontSize=7,  textColor=CA, spaceAfter=3)
    S_CRIT   = _p(fontName="Helvetica",         fontSize=7.5,spaceAfter=1, leading=10)
    S_PUNTO  = _p(fontName="Helvetica",         fontSize=7.5,spaceAfter=1, leading=10)
    S_REC_H  = _p(fontName="Helvetica-Bold",    fontSize=7,  textColor=CA, spaceBefore=4, spaceAfter=2)
    S_REC    = _p(fontName="Helvetica",         fontSize=7.5,leading=11,  textColor=colors.HexColor("#111827"))
    S_EXP_H  = _p(fontName="Helvetica-Bold",    fontSize=8,  textColor=CA, spaceBefore=5, spaceAfter=3)
    S_EXP_T  = _p(fontName="Helvetica-Bold",    fontSize=7.5,textColor=CA, spaceBefore=3, spaceAfter=2)
    S_EXP_P  = _p(fontName="Helvetica",         fontSize=7,  leading=10,  textColor=colors.HexColor("#374151"), spaceAfter=1)
    S_EXP_I  = _p(fontName="Helvetica-Oblique", fontSize=6.5,textColor=colors.HexColor("#64748b"), spaceAfter=1, leftIndent=4)
    S_EXP_LI = _p(fontName="Helvetica",         fontSize=7,  leading=10,  leftIndent=8,  spaceAfter=1)
    S_PIE    = _p(fontName="Helvetica",         fontSize=6.5,textColor=colors.grey, alignment=TA_CENTER)

    ahora    = datetime.now().strftime("%d/%m/%Y %H:%M")
    historia = []

    # ── Cabecera ──────────────────────────────────────────────────────────
    _nom = _strip((nombre or ticker)[:60])
    _tkr = ticker.upper()

    cab = Table(
        [[Paragraph(_tkr, S_HDR_T),
          Paragraph(_esc(_nom), _p(fontName="Helvetica-Bold", fontSize=11, textColor=BL, alignment=TA_CENTER)),
          Paragraph("Informe de Estrategia", S_HDR_S)],
         [Paragraph(f"Precio: {precio:.4f}", S_HDR_P),
          Paragraph(f"Datos: {_strip(ts)}", _p(fontName="Helvetica", fontSize=7.5, textColor=BL, alignment=TA_CENTER)),
          Paragraph(f"Generado: {ahora}", S_HDR_D)]],
        colWidths=[5*cm, 8*cm, 5*cm],
        rowHeights=[1.4*cm, 1.0*cm]
    )
    cab.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), CA),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    historia.append(cab)
    historia.append(Spacer(1, 0.3*cm))

    # ── Bloque por estrategia ─────────────────────────────────────────────
    for est in estrategias:
        est_nombre = _strip(est["nombre"])
        color_rl   = colors.HexColor(est["color"])
        criterios  = est["criterios"]
        puntos     = est["puntos"]
        rec        = _strip(est.get("rec") or "")
        popover_md = est.get("popover_md", "")

        total  = sum(ok for _, ok in criterios)
        maxpts = len(criterios) * 2
        pct    = int(total / maxpts * 100) if maxpts else 0
        if pct >= 70:   vrd = "OPORTUNIDAD"
        elif pct >= 45: vrd = "VIGILAR"
        else:           vrd = "NO ES EL MOMENTO"
        vrd_col = {"OPORTUNIDAD": VE, "VIGILAR": AM, "NO ES EL MOMENTO": RO}[vrd]

        # Header con color de estrategia
        hdr = Table(
            [[Paragraph(_esc(est_nombre), S_EST_N),
              Paragraph(vrd, S_EST_V),
              [Paragraph(str(pct), S_SCORE),
               Paragraph("/ 100", S_SCORE2)]]],
            colWidths=[8*cm, 5.5*cm, 4.5*cm]
        )
        hdr.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), color_rl),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("ALIGN",        (1, 0), (1, 0),   "CENTER"),
            ("ALIGN",        (2, 0), (2, 0),   "RIGHT"),
        ]))
        historia.append(hdr)

        # Dos columnas: criterios | análisis + recomendación
        crit_items  = []
        punto_items = []

        for html_str, ok in criterios:
            icon = "[+]" if ok == 2 else "[~]" if ok == 1 else "[-]"
            text = _html_to_plain(html_str).lstrip("[+][~][-]? ").strip()
            crit_items.append(Paragraph(f"{icon} {_esc(text)}", S_CRIT))
            crit_items.append(Spacer(1, 1))

        for p_html in puntos:
            text = _html_to_plain(p_html)
            punto_items.append(Paragraph(_esc(text), S_PUNTO))
            punto_items.append(Spacer(1, 1))

        if rec:
            punto_items.append(Paragraph("RECOMENDACION:", S_REC_H))
            punto_items.append(Paragraph(_esc(rec), S_REC))

        body = Table(
            [[crit_items, punto_items]],
            colWidths=[9*cm, 9*cm]
        )
        body.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
            ("BACKGROUND",   (0, 0), (0, -1),  GF),
            ("LINEAFTER",    (0, 0), (0, -1),   0.5, GB),
            ("BOX",          (0, 0), (-1, -1),  0.5, GB),
        ]))
        historia.append(body)

        # Explicación detallada (del markdown del popover)
        historia.append(Spacer(1, 0.15*cm))
        historia.append(Paragraph("DESCRIPCION DETALLADA DE LA ESTRATEGIA", S_EXP_H))

        for raw_line in popover_md.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if line == "---":
                historia.append(HRFlowable(width="100%", thickness=0.5,
                                           color=GB, spaceAfter=2, spaceBefore=2))
                continue
            if line.startswith("- "):
                content = _strip(line[2:])
                content = _re.sub(r"\*\*(.+?)\*\*", r"\1", content)
                content = _re.sub(r"\*([^*]+?)\*",  r"\1", content)
                historia.append(Paragraph(f"  {chr(8226)} {_esc(content)}", S_EXP_LI))
                continue
            # Detectar líneas solo-bold → título de sección
            m_bold = _re.match(r"^\*\*(.+?)\*\*\s*(\*.+?\*)?$", line)
            if m_bold:
                titulo  = _strip(m_bold.group(1))
                sub_raw = m_bold.group(2) or ""
                sub     = _strip(sub_raw[1:-1]) if sub_raw else ""
                label   = f"<b>{_esc(titulo)}</b>"
                if sub:
                    label += f"  <i>{_esc(sub)}</i>"
                historia.append(Paragraph(label, S_EXP_T))
                continue
            # Cursiva standalone
            if line.startswith("*") and line.endswith("*") and len(line) > 2:
                content = _strip(line[1:-1])
                content = _re.sub(r"\*\*(.+?)\*\*", r"\1", content)
                historia.append(Paragraph(f"<i>{_esc(content)}</i>", S_EXP_I))
                continue
            # Párrafo normal
            content = _strip(line)
            content = _re.sub(r"\*\*(.+?)\*\*", r"\1", content)
            content = _re.sub(r"\*([^*]+?)\*",  r"\1", content)
            historia.append(Paragraph(_esc(content), S_EXP_P))

        historia.append(Spacer(1, 0.4*cm))

    # ── Pie de página ────────────────────────────────────────────────────
    historia.append(HRFlowable(width="100%", thickness=0.5, color=GB,
                                spaceAfter=4, spaceBefore=4))
    historia.append(Paragraph(
        "Analisis educativo  |  No constituye asesoramiento de inversion regulado "
        "bajo MiFID II (Directiva 2014/65/UE)  |  PivotAnalyzer -- Scriptum",
        S_PIE
    ))

    doc.build(historia)
    return buf.getvalue()


# =============================================================================
# GENERACIÓN DE PDF
# =============================================================================

def generar_pdf(ticker: str, precio: float, sistema: str, resultados_pivots: dict,
                confluencias: list, semaforo: str, factores_semaforo: list,
                vol_data: dict, indicadores: dict, fundamentales: dict,
                nombre: str = "", tipo_activo: str = "", cambio: float = 0.0,
                cambio_pct: float = 0.0, h52=None, l52=None, currency: str = "",
                pct_semaforo: float = 0.0,
                niveles_reforzados: list = None, señales_dir: list = None,
                consenso_dir: tuple = None, divergencias_tecnicas: list = None,
                huecos: list = None):
    """PDF con precio prominente + pivots multi-columna en paralelo."""

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    # ── Colores ──────────────────────────────────────────────────────────
    CA  = colors.HexColor("#1e3a5f")   # azul oscuro
    CM  = colors.HexColor("#2563eb")   # azul medio
    CCL = colors.HexColor("#dbeafe")   # azul claro
    GF  = colors.HexColor("#f1f5f9")   # gris fondo
    GB  = colors.HexColor("#e2e8f0")   # gris borde
    VE  = colors.HexColor("#16a34a")   # verde
    RO  = colors.HexColor("#dc2626")   # rojo
    AM  = colors.HexColor("#f59e0b")   # amarillo
    ACL = colors.HexColor("#fffbeb")   # amarillo claro
    BL  = colors.white

    SC = {"verde": VE, "amarillo": AM, "rojo": RO}.get(semaforo, colors.grey)
    ST = {"verde": "VERDE", "amarillo": "AMARILLO", "rojo": "ROJO"}.get(semaforo, "—")
    # ● (U+25CF) con color — sustituye emoji (Helvetica no soporta Unicode > U+00FF)
    sem_hex = {"verde": "#22c55e", "amarillo": "#f59e0b", "rojo": "#ef4444"}.get(semaforo, "#94a3b8")
    SEM_DOT = f'<font color="{sem_hex}">&#9679;</font>'

    # Elimina emoji fuera de cp1252 (✅⚠️❌🟢🔴…) preservando texto en español
    def _strip(s: str) -> str:
        replacements = [("✅", "+"), ("⚠️", "~"), ("❌", "-"),
                        ("🟢", ""), ("🟡", ""), ("🔴", ""), ("⚪", "")]
        for em, rep in replacements:
            s = s.replace(em, rep)
        return s.strip()

    # ── Estilos (helper con contador para nombres únicos) ─────────────────
    _SS = getSampleStyleSheet()
    _n  = [0]
    def _p(**kw):
        _n[0] += 1
        return ParagraphStyle(f"_p{_n[0]}", parent=_SS["Normal"], **kw)

    S_TICK = _p(fontName="Helvetica-Bold", fontSize=18, textColor=BL)
    S_EMP  = _p(fontName="Helvetica",      fontSize=8,  textColor=BL)
    S_PRE  = _p(fontName="Helvetica-Bold", fontSize=28, textColor=BL, alignment=TA_RIGHT)
    S_CAM  = _p(fontName="Helvetica-Bold", fontSize=10, textColor=BL, alignment=TA_RIGHT)
    S_H52  = _p(fontName="Helvetica",      fontSize=7.5,textColor=BL, alignment=TA_RIGHT)
    S_CHIP = _p(fontName="Helvetica",      fontSize=7,  textColor=colors.HexColor("#475569"))
    S_H2   = _p(fontName="Helvetica-Bold", fontSize=9,  textColor=CA, spaceBefore=6, spaceAfter=3)
    S_MH   = _p(fontName="Helvetica-Bold", fontSize=6.5,textColor=colors.HexColor("#374151"), spaceAfter=2)
    S_NRM  = _p(fontName="Helvetica",      fontSize=7.5,spaceAfter=1)
    S_PIE  = _p(fontName="Helvetica",      fontSize=6.5,textColor=colors.grey, alignment=TA_CENTER)
    S_CP   = _p(fontName="Helvetica-Bold", fontSize=7.5,textColor=CA)
    S_CN   = _p(fontName="Helvetica",      fontSize=6,  textColor=colors.HexColor("#64748b"))

    ahora   = datetime.now().strftime("%d/%m/%Y %H:%M")
    historia = []

    # ── CABECERA ──────────────────────────────────────────────────────────
    h52_str = f"{l52:.2f} – {h52:.2f}" if h52 and l52 else "—"
    # Estilos exclusivos para la cabecera
    S_DLBL = _p(fontName="Helvetica",      fontSize=6,  textColor=colors.HexColor("#93c5fd"))
    S_DVAL = _p(fontName="Helvetica-Bold", fontSize=13, textColor=BL)
    S_NOM  = _p(fontName="Helvetica-Bold", fontSize=12, textColor=BL, alignment=TA_CENTER)
    S_TIP  = _p(fontName="Helvetica",      fontSize=9,  textColor=colors.HexColor("#93c5fd"),
                alignment=TA_RIGHT)

    # Fila superior: tabla interna 3 cols → ticker | empresa centrada | tipo derecha
    _nom = (nombre or ticker).replace("&", "&amp;")
    _tkr = ticker.upper().replace("&", "&amp;")
    _tip = tipo_activo.replace("&", "&amp;")
    # ancho disponible: 18cm - padding izq/der (10pt+10pt ≈ 0.71cm) = 17.29cm
    info_inner = Table(
        [[Paragraph(_tkr, S_TICK), Paragraph(_nom, S_NOM), Paragraph(_tip, S_TIP)]],
        colWidths=[4.5*cm, 8.29*cm, 4.5*cm]
    )
    info_inner.setStyle(TableStyle([
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))

    precio_cell = [Paragraph(f"PRECIO  {currency}", S_DLBL),
                   Paragraph(f"{precio:.4f}", S_DVAL)]
    cambio_cell = [Paragraph("VARIACIÓN", S_DLBL),
                   Paragraph(f"{cambio:+.4f}  ({cambio_pct:+.2f}%)", S_DVAL)]
    h52_cell    = [Paragraph("52 SEMANAS", S_DLBL),
                   Paragraph(h52_str, S_DVAL)]

    cab_t = Table(
        [[info_inner, "", ""],
         [precio_cell, cambio_cell, h52_cell]],
        colWidths=[6*cm, 6*cm, 6*cm],
        rowHeights=[1.8*cm, 1.8*cm]   # filas iguales en altura
    )
    cab_t.setStyle(TableStyle([
        ("SPAN",          (0,0),  (2,0)),
        ("BACKGROUND",    (0,0),  (-1,-1), CA),
        # fila superior: contenido centrado verticalmente
        ("VALIGN",        (0,0),  (2,0),   "MIDDLE"),
        # fila inferior: desde arriba
        ("VALIGN",        (0,1),  (-1,1),  "TOP"),
        ("LEFTPADDING",   (0,0),  (-1,-1), 10),
        ("RIGHTPADDING",  (0,0),  (-1,-1), 10),
        ("TOPPADDING",    (0,0),  (-1,-1), 10),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 10),
        # línea separadora con más aire respecto al bloque superior
        ("LINEABOVE",     (0,1),  (-1,1),  0.5, colors.HexColor("#2563eb")),
        ("TOPPADDING",    (0,1),  (-1,1),  10),
        ("BOTTOMPADDING", (0,1),  (-1,1),  10),
    ]))
    historia.append(cab_t)
    chips_t = Table(
        [[Paragraph(f"Generado: {ahora}   ·   Datos ~15 min de retraso vía Yahoo Finance", S_CHIP)]],
        colWidths=[18*cm]
    )
    chips_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), GF),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
    ]))
    historia.append(chips_t)
    historia.append(Spacer(1, 0.3*cm))

    # ── SEMÁFORO ──────────────────────────────────────────────────────────
    historia.append(Paragraph("Semáforo Global", S_H2))
    badge_t = Table(
        [[Paragraph(SEM_DOT, _p(fontName="Helvetica-Bold", fontSize=24, alignment=TA_CENTER))],
         [Paragraph(ST, _p(fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, textColor=SC))],
         [Paragraph(f"{pct_semaforo:.0f}%", _p(fontName="Helvetica-Bold", fontSize=13, alignment=TA_CENTER))]],
        colWidths=[2.8*cm]
    )
    badge_t.setStyle(TableStyle([
        ("BOX",           (0,0),(-1,-1), 2, SC),
        ("BACKGROUND",    (0,0),(-1,-1), GF),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
    ]))
    # Factores: 2 filas × 3 columnas
    fac_data, row_buf = [], []
    for i, (fac, desc, _) in enumerate(factores_semaforo):
        inner = Table(
            [[Paragraph(_strip(fac),  _p(fontSize=7.5, textColor=colors.HexColor("#6b7280")))],
             [Paragraph(_strip(desc), _p(fontSize=9,   fontName="Helvetica-Bold"))]],
            colWidths=[4.9*cm]
        )
        inner.setStyle(TableStyle([
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ]))
        row_buf.append(inner)
        if len(row_buf) == 3:
            fac_data.append(row_buf); row_buf = []
    if row_buf:
        while len(row_buf) < 3:
            row_buf.append(Paragraph("", S_NRM))
        fac_data.append(row_buf)
    fac_t = Table(fac_data, colWidths=[4.9*cm]*3)
    fac_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), GF),
        ("GRID",       (0,0),(-1,-1), 0.3, GB),
        ("VALIGN",     (0,0),(-1,-1), "TOP"),
    ]))
    sem_t = Table([[badge_t, fac_t]], colWidths=[3*cm, 15*cm])
    sem_t.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(0,0), 0),
        ("RIGHTPADDING", (0,0),(0,0), 8),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    historia.append(sem_t)
    historia.append(Spacer(1, 0.35*cm))

    # ── PIVOT POINTS MULTI-COLUMNA ────────────────────────────────────────
    historia.append(Paragraph(f"Pivot Points — Sistema {sistema}", S_H2))

    NIV = ["R4","R3","R2","R1","PP","S1","S2","S3","S4","M1","M2","M3","M4","M5"]
    PW  = 90    # ancho por columna pivot (pt)  — 4×90 + 150 = 510 pt = 18 cm
    CW  = 150   # ancho columna confluencias (pt)

    def _mini_pivot(tf, datos_tf):
        """Retorna lista de Flowables para una celda de timeframe."""
        hdr = [Paragraph(tf, S_MH)]
        if not datos_tf:
            return hdr + [Paragraph("Sin datos", S_NRM)]
        filas = [["Nv", "Precio", "Dist."]]
        tipos = []
        for nv in NIV:
            if nv not in datos_tf or nv.startswith("_"):
                continue
            val  = datos_tf[nv]
            dist = ((val - precio) / precio * 100) if precio else 0
            ds   = (f"+{dist:.1f}%" if dist > 0.005
                    else (f"{dist:.1f}%" if dist < -0.005 else "—"))
            filas.append([nv, f"{val:.3f}", ds])
            tipos.append(nv)
        mini = Table(filas, colWidths=[16, 37, 27])
        ts = [
            ("FONTSIZE",      (0,0),(-1,-1), 6),
            ("FONTNAME",      (0,0),(-1, 0), "Helvetica-Bold"),
            ("BACKGROUND",    (0,0),(-1, 0), CA),
            ("TEXTCOLOR",     (0,0),(-1, 0), BL),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [BL, GF]),
            ("GRID",          (0,0),(-1,-1), 0.2, GB),
            ("TOPPADDING",    (0,0),(-1,-1), 1),
            ("BOTTOMPADDING", (0,0),(-1,-1), 1),
            ("LEFTPADDING",   (0,0),(-1,-1), 2),
            ("RIGHTPADDING",  (0,0),(-1,-1), 2),
        ]
        for i, nv in enumerate(tipos, 1):
            if   nv.startswith("R"): ts += [("TEXTCOLOR",(0,i),(0,i),RO),("TEXTCOLOR",(2,i),(2,i),RO),("FONTNAME",(0,i),(0,i),"Helvetica-Bold")]
            elif nv == "PP":         ts += [("BACKGROUND",(0,i),(-1,i),CCL),("TEXTCOLOR",(0,i),(0,i),CM),("FONTNAME",(0,i),(0,i),"Helvetica-Bold")]
            elif nv.startswith("S"): ts += [("TEXTCOLOR",(0,i),(0,i),VE),("TEXTCOLOR",(2,i),(2,i),VE),("FONTNAME",(0,i),(0,i),"Helvetica-Bold")]
        mini.setStyle(TableStyle(ts))
        return hdr + [mini]

    def _conf_cell():
        hdr = [Paragraph("Confluencias", S_MH)]
        if not confluencias:
            return hdr + [Paragraph("Sin confluencias.", S_CN)]
        items = []
        for c in confluencias[:12]:
            niv_s = "  ".join(f"{n['timeframe'][:3]}{n['nivel']}" for n in c["niveles"])
            dist  = ((c["precio"] - precio) / precio * 100) if precio else 0
            ds    = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
            items += [
                Paragraph(f"<b>{c['precio']:.4f}</b>  {c['estrellas']}  "
                          f"<font color='#64748b'>{ds}</font>", S_CP),
                Paragraph(niv_s, S_CN),
                Spacer(1, 2),
            ]
        return hdr + items

    # Fila única: los 4 timeframes en paralelo + confluencias  (4×90 + 150 = 510pt)
    n_tf = len(TIMEFRAMES)
    row1 = [_mini_pivot(tf, resultados_pivots.get(tf)) for tf in TIMEFRAMES] + [_conf_cell()]
    t1 = Table([row1], colWidths=[PW]*n_tf + [CW])
    t1.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("RIGHTPADDING",  (0,0),(-1,-1), 4),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("BOX",           (0,0),(-1,-1), 0.5, GB),
        ("LINEBEFORE",    (1,0),(n_tf-1,0), 0.3, GB),
        ("LINEAFTER",     (n_tf-1,0),(n_tf-1,0), 1.2, CM),  # separador antes confluencias
        ("BACKGROUND",    (n_tf,0),(n_tf,0), ACL),           # fondo confluencias
    ]))
    historia.append(t1)
    historia.append(Spacer(1, 0.3*cm))

    # ── INDICADORES | MEDIAS | VOLUMEN (tres columnas) ────────────────────
    historia.append(Paragraph("Indicadores Técnicos y Volumen", S_H2))

    def _kv_ts(cws):
        """Tabla etiqueta-valor con estilo uniforme."""
        return TableStyle([
            ("ROWBACKGROUNDS",(0,0),(-1,-1), [BL, GF]),
            ("GRID",         (0,0),(-1,-1), 0.2, GB),
            ("TOPPADDING",   (0,0),(-1,-1), 2),
            ("BOTTOMPADDING",(0,0),(-1,-1), 2),
            ("LEFTPADDING",  (0,0),(-1,-1), 4),
            ("RIGHTPADDING", (0,0),(-1,-1), 4),
        ])

    _lbl = lambda t: _p(fontSize=7.5)
    _val = lambda t: _p(fontSize=7.5)

    # Separar indicadores base vs medias móviles
    ind_base, ind_medias = [], []
    for k, v in indicadores.items():
        row = [Paragraph(k, _lbl(k)), Paragraph(str(v), _val(v))]
        if k.startswith("SMA") or k.startswith("EMA"):
            ind_medias.append(row)
        else:
            ind_base.append(row)

    S_COL_H = _p(fontName="Helvetica-Bold", fontSize=7, textColor=CA, spaceAfter=2)

    # Col 0 — Indicadores técnicos  (3.5 + 3.0 = 6.5 cm)
    t_ind = Table(ind_base, colWidths=[3.5*cm, 3.0*cm])
    t_ind.setStyle(_kv_ts([3.5*cm, 3.0*cm]))
    ind_cell = [Paragraph("Indicadores", S_COL_H), t_ind]

    # Col 1 — Medias móviles  (2.2 + 3.0 = 5.2 cm; inner fit: 5.5 cm col − 8 pt pad)
    t_med = Table(ind_medias, colWidths=[2.2*cm, 3.0*cm]) if ind_medias else Table(
        [[Paragraph("—", _lbl(""))]], colWidths=[5.2*cm])
    t_med.setStyle(_kv_ts([2.2*cm, 3.0*cm]))
    med_cell = [Paragraph("Medias Móviles", S_COL_H), t_med]

    # Col 2 — Volumen  (3.0 + 2.7 = 5.7 cm; inner fit: 6.0 cm col − 8 pt pad)
    if vol_data:
        vr = [
            [Paragraph("Volumen sesión",    _lbl("")), Paragraph(_fmt_numero(vol_data["volumen"]),    _val(""))],
            [Paragraph("Media 10 sesiones", _lbl("")), Paragraph(_fmt_numero(vol_data["media_10d"]),  _val(""))],
            [Paragraph("Media 3 meses",     _lbl("")), Paragraph(_fmt_numero(vol_data["media_3m"]),   _val(""))],
            [Paragraph("Ratio vs 10d",      _lbl("")), Paragraph(f"{vol_data['ratio_10d']:.1f}% — {vol_data['clasificacion_10d']}", _val(""))],
            [Paragraph("Ratio vs 3m",       _lbl("")), Paragraph(f"{vol_data['ratio_3m']:.1f}% — {vol_data['clasificacion_3m']}",   _val(""))],
        ]
        t_vol = Table(vr, colWidths=[3.0*cm, 2.7*cm])
        t_vol.setStyle(_kv_ts([3.0*cm, 2.7*cm]))
        vol_cell = [Paragraph("Volumen", S_COL_H), t_vol]
    else:
        vol_cell = [Paragraph("Volumen", S_COL_H), Paragraph("Sin datos.", S_NRM)]

    # Tabla exterior 3 columnas: 6.5 + 5.5 + 6.0 = 18 cm
    iv_t = Table([[ind_cell, med_cell, vol_cell]], colWidths=[6.5*cm, 5.5*cm, 6.0*cm])
    iv_t.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("LINEBEFORE",   (1,0),(2,0),   0.5, GB),
        ("LEFTPADDING",  (1,0),(2,0),   8),
    ]))
    historia.append(iv_t)

    # ── CONVERGENCIA TÉCNICA ────────────────────────────────────────────────
    if niveles_reforzados or señales_dir or consenso_dir:
        historia.append(Paragraph("Convergencia Tecnica", S_H2))

        # Niveles reforzados
        if niveles_reforzados:
            niv_hdr = [Paragraph(h, _p(fontSize=6.5, fontName="Helvetica-Bold", textColor=BL))
                       for h in ["Precio", "Dist.", "Pivot", "Media", "Tipo"]]
            niv_rows_pdf = [niv_hdr]
            for nr in niveles_reforzados[:8]:
                tipo_color = VE if "soporte" in nr.get("tipo","").lower() else RO
                niv_rows_pdf.append([
                    Paragraph(f'{nr["precio"]:.4f}', S_NRM),
                    Paragraph(nr.get("dist_str", ""), S_NRM),
                    Paragraph(str(nr.get("pivot", "")), S_NRM),
                    Paragraph(str(nr.get("media", "")), S_NRM),
                    Paragraph(nr.get("tipo", ""), _p(fontSize=7, textColor=tipo_color)),
                ])
            t_niv = Table(niv_rows_pdf, colWidths=[2.5*cm, 1.8*cm, 2*cm, 2*cm, 3.7*cm])
            t_niv.setStyle(TableStyle([
                ("BACKGROUND",   (0,0),(-1,0), CA),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [BL, GF]),
                ("GRID",         (0,0),(-1,-1), 0.2, GB),
                ("TOPPADDING",   (0,0),(-1,-1), 2),
                ("BOTTOMPADDING",(0,0),(-1,-1), 2),
                ("LEFTPADDING",  (0,0),(-1,-1), 4),
            ]))
            historia.append(t_niv)
            historia.append(Spacer(1, 0.2*cm))

        # Señal consenso + indicadores direccionales
        if consenso_dir or señales_dir:
            cons_label = consenso_dir[2] if consenso_dir else "—"
            dir_hdr = [Paragraph(h, _p(fontSize=6.5, fontName="Helvetica-Bold", textColor=BL))
                       for h in ["Indicador", "Estado", "Dir."]]
            dir_rows_pdf = [dir_hdr]
            for nombre_s, desc_s, dir_s, _ in (señales_dir or []):
                dir_color = VE if dir_s == "alcista" else (RO if dir_s == "bajista" else colors.grey)
                dir_rows_pdf.append([
                    Paragraph(nombre_s, _p(fontSize=7, fontName="Helvetica-Bold")),
                    Paragraph(desc_s, S_NRM),
                    Paragraph("↑" if dir_s=="alcista" else ("↓" if dir_s=="bajista" else "–"),
                              _p(fontSize=8, fontName="Helvetica-Bold", textColor=dir_color)),
                ])
            t_dir = Table(dir_rows_pdf, colWidths=[3.5*cm, 9.5*cm, 1*cm])
            t_dir.setStyle(TableStyle([
                ("BACKGROUND",   (0,0),(-1,0), CA),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [BL, GF]),
                ("GRID",         (0,0),(-1,-1), 0.2, GB),
                ("TOPPADDING",   (0,0),(-1,-1), 2),
                ("BOTTOMPADDING",(0,0),(-1,-1), 2),
                ("LEFTPADDING",  (0,0),(-1,-1), 4),
            ]))
            historia.append(Paragraph(f"Señal de Consenso: {cons_label}", S_MH))
            historia.append(t_dir)
            historia.append(Spacer(1, 0.25*cm))

    # ── DIVERGENCIAS TÉCNICAS ────────────────────────────────────────────────
    if divergencias_tecnicas:
        historia.append(Paragraph("Divergencias Tecnicas", S_H2))
        _dv_alc = [d for d in divergencias_tecnicas if d["direccion"] == "alcista"]
        _dv_baj = [d for d in divergencias_tecnicas if d["direccion"] == "bajista"]

        for col_label, col_divs, col_color in [
            ("Alcistas", _dv_alc, VE),
            ("Bajistas", _dv_baj, RO),
        ]:
            if not col_divs:
                continue
            historia.append(Paragraph(col_label, _p(fontSize=7.5, fontName="Helvetica-Bold", textColor=col_color)))
            dv_hdr = [Paragraph(h, _p(fontSize=6.5, fontName="Helvetica-Bold", textColor=BL))
                      for h in ["Tipo", "Descripcion", "Fuerza"]]
            dv_rows = [dv_hdr]
            for d in col_divs:
                fuerza = d.get("fuerza", "media")
                f_color = {"fuerte": VE, "media": AM, "debil": colors.grey}.get(fuerza, colors.grey)
                dv_rows.append([
                    Paragraph(d.get("tipo", ""), _p(fontSize=7, fontName="Helvetica-Bold")),
                    Paragraph(d.get("descripcion", ""), S_NRM),
                    Paragraph(fuerza.capitalize(), _p(fontSize=7, textColor=f_color)),
                ])
            t_dv = Table(dv_rows, colWidths=[3.5*cm, 10*cm, 2.5*cm])
            t_dv.setStyle(TableStyle([
                ("BACKGROUND",   (0,0),(-1,0), CA),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [BL, GF]),
                ("GRID",         (0,0),(-1,-1), 0.2, GB),
                ("TOPPADDING",   (0,0),(-1,-1), 2),
                ("BOTTOMPADDING",(0,0),(-1,-1), 2),
                ("LEFTPADDING",  (0,0),(-1,-1), 4),
            ]))
            historia.append(t_dv)
            historia.append(Spacer(1, 0.15*cm))
        historia.append(Spacer(1, 0.1*cm))

    # ── FUNDAMENTALES (6 columnas: 3 pares etiqueta-valor) ───────────────
    if fundamentales:
        fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
        if fund_items:
            historia.append(Paragraph("Datos Fundamentales", S_H2))
            fund_rows, buf_r = [], []
            for k, v in fund_items:
                buf_r += [Paragraph(k, _p(fontSize=7, textColor=colors.HexColor("#64748b"))),
                          Paragraph(str(v), _p(fontSize=7, fontName="Helvetica-Bold"))]
                if len(buf_r) == 6:          # 3 pares por fila
                    fund_rows.append(buf_r); buf_r = []
            if buf_r:
                while len(buf_r) < 6: buf_r.append(Paragraph("", S_NRM))
                fund_rows.append(buf_r)
            # 3 pares × (2.2 cm label + 3.8 cm value) = 18 cm
            t_fund = Table(fund_rows, colWidths=[2.2*cm, 3.8*cm]*3)
            t_fund.setStyle(TableStyle([
                ("ROWBACKGROUNDS",(0,0),(-1,-1), [BL, GF]),
                ("GRID",         (0,0),(-1,-1), 0.2, GB),
                ("TOPPADDING",   (0,0),(-1,-1), 2),
                ("BOTTOMPADDING",(0,0),(-1,-1), 2),
                ("LEFTPADDING",  (0,0),(-1,-1), 4),
            ]))
            historia.append(t_fund)

    # ── Huecos de precio ──────────────────────────────────────────────────
    if huecos:
        historia.append(Spacer(1, 0.3*cm))
        historia.append(Paragraph("Huecos de Precio Abiertos", S_H2))
        historia.append(Spacer(1, 0.15*cm))

        _hue_data = [["Tipo", "Zona", "Tamano", "Distancia", "Fecha", "Dias"]]
        for _h in huecos[:8]:
            _tipo_str = "Alcista [+]" if _h["tipo"] == "alcista" else "Bajista [-]"
            _zona_str = f'{_h["gap_low"]:.4f} - {_h["gap_high"]:.4f}'
            _dist_str = f'{_h["dist_pct"]:+.2f}%'
            _hue_data.append([
                _tipo_str, _zona_str,
                f'{_h["gap_pct"]:.2f}%',
                _dist_str,
                _h["fecha"],
                str(_h["dias_abierto"]) + "d",
            ])

        _hue_col_widths = [2.2*cm, 4.8*cm, 1.8*cm, 2.2*cm, 2.4*cm, 1.4*cm]
        _hue_t = Table(_hue_data, colWidths=_hue_col_widths, repeatRows=1)
        _hue_style = [
            ("BACKGROUND",   (0, 0), (-1, 0), CA),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTSIZE",     (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, GF]),
            ("GRID",         (0, 0), (-1, -1), 0.2, GB),
            ("TOPPADDING",   (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ]
        # Color rows by tipo
        for _ri, _h in enumerate(huecos[:8], 1):
            _row_color = colors.HexColor("#f0fdf4") if _h["tipo"] == "alcista" else colors.HexColor("#fef2f2")
            _hue_style.append(("BACKGROUND", (0, _ri), (-1, _ri), _row_color))
        _hue_t.setStyle(TableStyle(_hue_style))
        historia.append(_hue_t)

    # ── PIE ───────────────────────────────────────────────────────────────
    historia.append(Spacer(1, 0.5*cm))
    historia.append(HRFlowable(width="100%", thickness=0.5, color=GB))
    historia.append(Paragraph(
        "Análisis educativo · No constituye asesoramiento de inversión regulado bajo MiFID II "
        "(Directiva 2014/65/UE) · Datos con retraso ~15 min vía Yahoo Finance · PivotAnalyzer — Scriptum",
        S_PIE
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
            ultimo = u.get('ultimo_acceso')
            ultimo_str = str(ultimo)[:16] if ultimo else '—'
            st.markdown(f"`{u.get('rol','usuario')}`  \n{ultimo_str}")
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
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("Salir", key="logout"):
                del st.session_state["usuario"]
                st.rerun()
        with bcol2:
            if st.button("🔄", key="refresh_data", help="Limpiar caché y recargar todos los datos"):
                st.cache_data.clear()
                st.rerun()

    # Navegación
    tabs_list = ["📈 Análisis Técnico", "🎯 Estrategia", "🤖 Análisis IA", "🌍 Macro"]
    if es_superadmin:
        tabs_list.append("⚙️ Usuarios")
    tabs_list.append("📖 Ayuda")

    tab_objs = st.tabs(tabs_list)
    tab_analisis  = tab_objs[0]
    tab_estrategia = tab_objs[1]
    tab_ia        = tab_objs[2]
    tab_macro     = tab_objs[3]

    if es_superadmin and len(tab_objs) >= 6:
        tab_admin = tab_objs[4]
        tab_ayuda = tab_objs[5]
    else:
        tab_admin = None
        tab_ayuda = tab_objs[-1]

    # ---- TAB ANÁLISIS ----
    with tab_analisis:
        # ── Fila 1: Mercado / Sistema / Tolerancia / Analizar ──────────────
        col1, col2, col3, col4 = st.columns([2.5, 2, 1.8, 1])
        with col1:
            mercado_sel = st.selectbox(
                "🗂️ Índice / Mercado",
                ["✏️ Escribir manualmente",
                 "🇪🇸 IBEX 35", "🌍 Eurostoxx 50",
                 "🇺🇸 S&P 500", "🇺🇸 Nasdaq 100", "🇺🇸 Dow Jones 30",
                 "🇩🇪 DAX 40", "🇫🇷 CAC 40", "🇬🇧 FTSE 100",
                 "📊 ETFs UCITS"],
                key="mercado_sel",
                help="Selecciona un índice para elegir el valor de una lista desplegable, "
                     "o 'Escribir manualmente' para introducir cualquier ticker de Yahoo Finance. "
                     "Sufijos de referencia: .MC (Madrid) · .DE (Xetra) · .PA (París) · .L (Londres) · .AS (Ámsterdam)"
            )
        with col2:
            sistema_sel = st.selectbox(
                "📐 Sistema Pivot", list(SISTEMAS_PIVOT.keys()),
                help="Método de cálculo de los Pivot Points. Clásico: el más universal y usado. "
                     "Woodie: doble peso al cierre, mejor en días con gap. "
                     "Camarilla: 8 niveles muy próximos al precio, ideal para intradía. "
                     "DeMark: condicional según dirección del día anterior. "
                     "Fibonacci: usa ratios 0.382, 0.618, 1.000. "
                     "Mid-Points: niveles intermedios entre los Clásicos."
            )
        with col3:
            tolerancia = st.number_input(
                "⚡ Tolerancia (€/$)", value=0.20, step=0.05,
                min_value=0.01, max_value=2.0, format="%.2f",
                help="Distancia máxima en precio para considerar que dos niveles de distintos timeframes "
                     "confluyen en la misma zona. Un valor más bajo (ej. 0.05€) detecta solo confluencias "
                     "muy precisas; uno más alto (ej. 0.50€) agrupa zonas más amplias. "
                     "Ajusta según la volatilidad y precio del activo analizado."
            )
        with col4:
            analizar = st.button("🔍 Analizar", type="primary")

        # ── Fila 2: Ticker (depende del mercado seleccionado) ──────────────
        if mercado_sel == "✏️ Escribir manualmente":
            ticker_input = st.text_input(
                "🔎 Ticker", value="NTGY.MC", placeholder="NTGY.MC, AAPL, SXR8.DE...",
                help="Símbolo del activo en Yahoo Finance. Ejemplos: NTGY.MC (Naturgy), "
                     "IBE.MC (Iberdrola), AAPL (Apple), SXR8.DE (ETF S&P 500 iShares). "
                     "Sufijos: .MC = Madrid · .DE = Xetra · .PA = París · .L = Londres · .AS = Ámsterdam"
            ).upper().strip()

        elif mercado_sel == "📊 ETFs UCITS":
            col_cat, col_etf = st.columns([1, 2])
            with col_cat:
                cat_etf = st.selectbox(
                    "📂 Categoría ETF", list(ETFS_UCITS.keys()),
                    help="Los ETFs UCITS son los únicos legalmente accesibles al minorista español "
                         "bajo la regulación PRIIPs/MiFID II. Los ETFs estadounidenses (SPY, QQQ...) "
                         "no están disponibles para residentes en España."
                )
            with col_etf:
                etfs_cat = ETFS_UCITS[cat_etf]
                etf_nombre = st.selectbox(
                    "🔎 ETF", list(etfs_cat.keys()),
                    help="Ticker en bolsa europea. .AS = Euronext Ámsterdam · "
                         ".DE = Xetra · .L = Londres. Elige el disponible en tu broker."
                )
                ticker_input = etfs_cat[etf_nombre]
            st.caption(f"Ticker seleccionado: `{ticker_input}` · Pulsa **Analizar** para consultar")

        else:
            # Índices bursátiles — carga dinámica Wikipedia + fallback estático
            with st.spinner(f"Cargando valores de {mercado_sel}..."):
                tickers_mercado = obtener_tickers_mercado(mercado_sel)
            if tickers_mercado:
                nombre_sel = st.selectbox(
                    f"🔎 Valor — {mercado_sel}",
                    list(tickers_mercado.keys()),
                    help=f"Valores del {mercado_sel}. El ticker de Yahoo Finance se asigna automáticamente. "
                         "Si el análisis falla, el ticker puede haber cambiado de símbolo — usa 'Escribir manualmente'."
                )
                ticker_input = tickers_mercado[nombre_sel]
                st.caption(f"Ticker: `{ticker_input}` · Pulsa **Analizar** para consultar")
            else:
                st.warning(f"No se pudieron cargar los tickers de {mercado_sel}. Introduce el ticker manualmente.")
                ticker_input = st.text_input("🔎 Ticker", value="", placeholder="Ej: AAPL, ITX.MC").upper().strip()

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
            st.error(
                f"No se pudieron obtener datos para **{ticker_activo}**. "
                f"Puede ser un fallo transitorio de Yahoo Finance — pulsa **🔄** para limpiar caché y vuelve a intentarlo. "
                f"Si persiste, verifica que el ticker es correcto (ej: `REP.MC`, `IBE.MC`)."
            )
            return

        precio = precio_actual(hist)
        if precio is None:
            st.error("Sin datos de precio.")
            return

        tipo_activo = detectar_tipo_activo(info)
        nombre = info.get("longName") or info.get("shortName") or ticker_activo

        # ---- PRECIO ACTUAL ----
        col_p1, col_p2, col_p3, col_p4 = st.columns([2.2, 2.1, 1.4, 1.1])
        cierre_ant = float(hist["Close"].iloc[-2]) if len(hist) > 1 else precio
        cambio = precio - cierre_ant
        cambio_pct = (cambio / cierre_ant * 100) if cierre_ant else 0
        var_str = f"{cambio:+.4f} ({cambio_pct:+.2f}%)"

        currency = info.get("currency", "")
        curr_str = f" {currency}" if currency else ""

        # Timestamp de carga del dato
        from datetime import datetime as _dt
        import zoneinfo as _zi
        ts_str = _dt.now(_zi.ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y %H:%M")

        with col_p1:
            st.metric("Precio", f"{precio:.4f}{curr_str}", delta=var_str, help=TOOLTIPS["Precio"])
        with col_p2:
            h52 = info.get("fiftyTwoWeekHigh")
            l52 = info.get("fiftyTwoWeekLow")
            st.metric("52W Máx / Mín", f"{h52:.2f} / {l52:.2f}" if h52 and l52 else "—", help=TOOLTIPS["52W Máx / Mín"])
        with col_p3:
            vol_hoy = float(hist["Volume"].iloc[-1])
            st.metric("Volumen hoy", _fmt_numero(vol_hoy), help=TOOLTIPS["Volumen hoy"])
        with col_p4:
            beta = info.get("beta")
            beta_str = f"{beta:.2f}" if beta is not None else "—"
            st.metric("Beta", beta_str,
                      help="Sensibilidad del activo respecto al mercado de referencia. "
                           "Beta > 1: más volátil que el índice. "
                           "Beta < 1: menos volátil. Beta < 0: correlación inversa.")

        st.markdown(
            f'<p style="font-size:0.88rem;color:#444;margin:4px 0 0 0">'
            f'<b>{nombre}</b> · {tipo_activo.upper()} · '
            f'Datos cargados: <b>{ts_str}</b> · Retraso ~15 min</p>',
            unsafe_allow_html=True
        )

        # ── Gráfico de evolución de precio ───────────────────────────────
        with st.expander("📈 Ver gráfico de precio"):
            import plotly.graph_objects as go
            import pandas as _pd_ch

            # ── helpers compartidos ──────────────────────────────────────
            def _chart_layout(fig, x_fmt, height=400, y_range=None):
                _yaxis = dict(showgrid=True, gridcolor="#e5e7eb",
                              gridwidth=1, griddash="dash",
                              tickfont=dict(size=10), domain=[0.22, 1.0],
                              showline=True, linecolor="#d1d5db",
                              autorange=True)
                if y_range:
                    _yaxis["range"] = y_range
                    _yaxis["autorange"] = False
                fig.update_layout(
                    height=height,
                    margin=dict(l=0, r=0, t=10, b=0),
                    plot_bgcolor="white", paper_bgcolor="white",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.01,
                                xanchor="left", x=0, font=dict(size=11)),
                    xaxis=dict(showgrid=True, gridcolor="#e5e7eb",
                               gridwidth=1, griddash="dash",
                               rangeslider=dict(visible=False),
                               tickformat=x_fmt, tickfont=dict(size=10),
                               showline=True, linecolor="#d1d5db"),
                    yaxis=_yaxis,
                    yaxis2=dict(showgrid=False, domain=[0.0, 0.18],
                                showticklabels=False),
                    xaxis_rangeslider_visible=False,
                )

            def _y_range(series, pad=0.015):
                """Rango Y ajustado al contenido con un pequeño margen."""
                _mn = float(series.min())
                _mx = float(series.max())
                _d  = (_mx - _mn) if _mx != _mn else _mn * 0.02
                return [_mn - _d * pad * 4, _mx + _d * pad * 2]

            def _add_volumen(fig, df):
                cols_v = [c for c in df.columns if str(c).lower() == "volume"]
                if cols_v:
                    fig.add_trace(go.Bar(
                        x=df.index, y=df[cols_v[0]],
                        name="Volumen", marker_color="#d1d5db",
                        yaxis="y2", showlegend=False,
                        hovertemplate="Vol: %{y:,.0f}<extra></extra>"
                    ))

            # ── tabs Intradía / Histórica ────────────────────────────────
            _tab_id, _tab_hist = st.tabs(["📊 Intradía", "📈 Histórica"])

            # ══ TAB INTRADÍA ══════════════════════════════════════════════
            with _tab_id:
                @st.cache_data(ttl=300)
                def _get_intraday(tkr):
                    import yfinance as yf
                    df = yf.download(tkr, period="1d", interval="5m",
                                     auto_adjust=True, progress=False,
                                     multi_level_index=False)
                    return df

                _id_df = _get_intraday(ticker_activo).copy()

                if _id_df.empty:
                    st.info("No hay datos intradía disponibles para esta sesión.")
                else:
                    if hasattr(_id_df.index, "tz") and _id_df.index.tz is not None:
                        _id_df.index = _id_df.index.tz_localize(None)

                    _id_close = [c for c in _id_df.columns if str(c).lower() == "close"][0]
                    _id_open_val = _id_df.iloc[0][_id_close]
                    _id_last_val = _id_df.iloc[-1][_id_close]
                    _id_color = "#e55c3a" if _id_last_val >= _id_open_val else "#2563eb"

                    # Rango horario completo del mercado (09:00–17:30 por defecto)
                    _id_fecha = _id_df.index[0].date()
                    _id_open_ts  = _pd_ch.Timestamp(f"{_id_fecha} 09:00:00")
                    _id_close_ts = _pd_ch.Timestamp(f"{_id_fecha} 17:30:00")

                    fig_id = go.Figure()

                    # Área gris para horas sin datos (mercado no abierto aún o ya cerrado)
                    _id_ultimo = _id_df.index[-1]
                    if _id_ultimo < _id_close_ts:
                        fig_id.add_vrect(
                            x0=_id_ultimo, x1=_id_close_ts,
                            fillcolor="#f3f4f6", opacity=0.6,
                            layer="below", line_width=0
                        )

                    # Línea de precio con relleno
                    _id_fill_rgba = "rgba(229,92,58,0.12)" if _id_color == "#e55c3a" else "rgba(37,99,235,0.12)"
                    fig_id.add_trace(go.Scatter(
                        x=_id_df.index,
                        y=_id_df[_id_close],
                        mode="lines",
                        name=ticker_activo,
                        line=dict(color=_id_color, width=2),
                        fill="tozeroy",
                        fillcolor=_id_fill_rgba,
                        hovertemplate="%{x|%H:%M}  <b>%{y:.4f}</b><extra></extra>",
                    ))

                    # Línea horizontal de apertura
                    fig_id.add_hline(
                        y=float(_id_open_val),
                        line_dash="dot", line_color="#9ca3af", line_width=1,
                    )
                    # Etiqueta "Apertura" en el eje Y, fuera del área del gráfico
                    fig_id.add_annotation(
                        xref="paper", x=-0.005,
                        yref="y",     y=float(_id_open_val),
                        text="Apertura",
                        showarrow=False,
                        xanchor="right",
                        yanchor="middle",
                        font=dict(size=9, color="#9ca3af"),
                        bgcolor="white",
                        borderpad=1,
                    )

                    _add_volumen(fig_id, _id_df)

                    _id_yr = _y_range(_id_df[_id_close])
                    fig_id.update_layout(
                        height=400,
                        margin=dict(l=58, r=0, t=10, b=0),
                        plot_bgcolor="white", paper_bgcolor="white",
                        hovermode="x unified",
                        showlegend=False,
                        xaxis=dict(
                            showgrid=True, gridcolor="#e5e7eb",
                            gridwidth=1, griddash="dash",
                            range=[_id_open_ts, _id_close_ts],
                            tickformat="%H:%M", tickfont=dict(size=10),
                            showline=True, linecolor="#d1d5db",
                            rangeslider=dict(visible=False),
                        ),
                        yaxis=dict(
                            showgrid=True, gridcolor="#e5e7eb",
                            gridwidth=1, griddash="dash",
                            tickfont=dict(size=10), domain=[0.22, 1.0],
                            range=_id_yr, autorange=False,
                        ),
                        yaxis2=dict(showgrid=False, domain=[0.0, 0.18],
                                    showticklabels=False),
                    )
                    st.plotly_chart(fig_id, use_container_width=True,
                                    config={"displayModeBar": False})

            # ══ TAB HISTÓRICA ═════════════════════════════════════════════
            with _tab_hist:
                _per_opts  = ["5D", "1M", "3M", "6M", "1A", "5A", "Todo"]
                _per_map   = {"5D": 5, "1M": 21, "3M": 63, "6M": 126,
                              "1A": 252, "5A": 1260, "Todo": 99999}

                _hc1, _hc2 = st.columns([4, 1])
                with _hc2:
                    _h_per = st.radio("Período", _per_opts,
                                      index=4, horizontal=False,
                                      key="hist_periodo")
                    _h_view = st.radio("Vista", ["Velas", "Línea", "OHLC"],
                                       index=0, horizontal=False,
                                       key="hist_vista")

                _h_n = _per_map.get(_h_per, 252)
                _h_df = hist.tail(_h_n).copy()
                if hasattr(_h_df.index, "tz") and _h_df.index.tz is not None:
                    _h_df.index = _h_df.index.tz_localize(None)

                _col_close = [c for c in _h_df.columns if str(c).lower() == "close"][0]
                _col_open  = [c for c in _h_df.columns if str(c).lower() == "open"][0]
                _col_high  = [c for c in _h_df.columns if str(c).lower() == "high"][0]
                _col_low   = [c for c in _h_df.columns if str(c).lower() == "low"][0]

                fig_hh = go.Figure()

                if _h_view == "Velas":
                    fig_hh.add_trace(go.Candlestick(
                        x=_h_df.index,
                        open=_h_df[_col_open], high=_h_df[_col_high],
                        low=_h_df[_col_low],   close=_h_df[_col_close],
                        name=ticker_activo,
                        increasing_line_color="#16a34a",
                        decreasing_line_color="#dc2626",
                        increasing_fillcolor="#16a34a",
                        decreasing_fillcolor="#dc2626",
                    ))
                elif _h_view == "OHLC":
                    fig_hh.add_trace(go.Ohlc(
                        x=_h_df.index,
                        open=_h_df[_col_open], high=_h_df[_col_high],
                        low=_h_df[_col_low],   close=_h_df[_col_close],
                        name=ticker_activo,
                        increasing_line_color="#16a34a",
                        decreasing_line_color="#dc2626",
                    ))
                else:
                    _h_last  = float(_h_df[_col_close].iloc[-1])
                    _h_first = float(_h_df[_col_close].iloc[0])
                    _h_lcolor = "#e55c3a" if _h_last >= _h_first else "#2563eb"
                    _h_fill_rgba = "rgba(229,92,58,0.08)" if _h_last >= _h_first else "rgba(37,99,235,0.08)"
                    fig_hh.add_trace(go.Scatter(
                        x=_h_df.index, y=_h_df[_col_close],
                        mode="lines", name=ticker_activo,
                        line=dict(color=_h_lcolor, width=2),
                        fill="tozeroy", fillcolor=_h_fill_rgba,
                    ))

                # Rango Y: basado en high/low para velas/OHLC, en close para línea
                if _h_view in ("Velas", "OHLC"):
                    import numpy as _np_ch
                    _h_yr = _y_range(_pd_ch.concat([_h_df[_col_high], _h_df[_col_low]]))
                else:
                    _h_yr = _y_range(_h_df[_col_close])

                # SMAs
                for _pm, _pc in [(20, "#f59e0b"), (50, "#7c3aed"), (200, "#94a3b8")]:
                    if len(_h_df) >= _pm:
                        _sma = _h_df[_col_close].rolling(_pm).mean()
                        fig_hh.add_trace(go.Scatter(
                            x=_h_df.index, y=_sma,
                            mode="lines", name=f"SMA{_pm}",
                            line=dict(color=_pc, width=1.2, dash="dot"),
                            hovertemplate=f"SMA{_pm}: %{{y:.4f}}<extra></extra>"
                        ))

                _add_volumen(fig_hh, _h_df)

                _h_xfmt = "%a %d %b" if _h_per == "5D" else "%d %b %y"
                with _hc1:
                    _chart_layout(fig_hh, _h_xfmt, y_range=_h_yr)
                    st.plotly_chart(fig_hh, use_container_width=True,
                                    config={"displayModeBar": False})

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

        # ---- CONVERGENCIA TÉCNICA ----
        niveles_reforzados, señales_dir, consenso_dir = calcular_convergencia_tecnica(
            resultados_pivots, medias, precio,
            rsi_val, macd_val, macd_señal, macd_hist_val, sar_tend, pct_b,
            tolerancia=tol_activa
        )

        # ---- DIVERGENCIAS TÉCNICAS ----
        divergencias_tecnicas = detectar_divergencias(hist)

        # ---- HUECOS DE PRECIO ----
        huecos_abiertos = detectar_huecos(hist)

        # ---- MÁXIMOS HISTÓRICOS (ATH) ----
        hist_maximo = obtener_hist_maximo(ticker_activo)
        analisis_ath = analizar_maximos_historicos(hist_maximo, precio, nombre)

        # ---- SMA200 GIRO / TENDENCIA ----
        analisis_sma200 = analizar_sma200(hist, precio, nombre)

        # ---- RESISTENCIAS ESTRUCTURALES ----
        analisis_resist = analizar_resistencias_estructurales(
            niveles_reforzados, precio, nombre
        )

        # ---- FIBONACCI RETRACEMENT/EXTENSIÓN ----
        analisis_fibo = analizar_fibonacci(hist, precio, nombre)


        # ---- FUNDAMENTALES ----
        fundamentales = bloque_fundamentales(info, tipo_activo)

        # ---- GUARDAR PARA PESTAÑA ESTRATEGIA ----
        st.session_state["estrategia_data"] = {
            "ticker":        ticker_activo,
            "nombre":        nombre,
            "precio":        precio,
            "tipo_activo":   tipo_activo,
            "info":          info,
            "hist":          hist,
            "medias":        medias,
            "rsi_val":       rsi_val,
            "macd_hist_val": macd_hist_val,
            "macd_val":      macd_val,
            "macd_señal":    macd_señal,
            "consenso_dir":  consenso_dir,
            "divergencias":  divergencias_tecnicas,
            "niveles_ref":   niveles_reforzados,
            "sar_tend":      sar_tend,
            "pct_b":         pct_b,
            "ts":            ts_str,
            "huecos":        huecos_abiertos,
            "analisis_ath":    analisis_ath,
            "analisis_sma200": analisis_sma200,
            "analisis_resist": analisis_resist,
            "analisis_fibo":   analisis_fibo,
        }

        # ======== LAYOUT PRINCIPAL ========

        # ── Bloque 1: Semáforo horizontal (ancho completo) ───────────────
        st.markdown("### Semáforo Global")
        emoji_color = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(color_sem, "⚪")
        css_class = f"semaforo-{color_sem}"

        col_badge, col_factores = st.columns([1, 5])
        with col_badge:
            st.markdown(
                f'<div class="{css_class}" style="text-align:center;padding:0.4rem 0">'
                f'<div style="font-size:2rem;line-height:1">{emoji_color}</div>'
                f'<div style="font-size:1rem;font-weight:bold;margin-top:0.2rem">'
                f'{color_sem.upper()}</div>'
                f'<div style="font-size:1.3rem;font-weight:bold">{pct_sem:.0f}%</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with col_factores:
            # Tarjetas HTML: evita truncado de st.metric en valores largos
            tarjetas_html = ""
            for factor, descripcion, _ in factores_sem:
                tarjetas_html += (
                    f'<div style="background:var(--secondary-background-color,#f0f2f6);'
                    f'border-radius:0.5rem;padding:0.55rem 0.75rem;flex:1;min-width:0">'
                    f'<div style="font-size:0.75rem;color:var(--text-color,#666);'
                    f'margin-bottom:0.25rem;font-weight:500">{factor}</div>'
                    f'<div style="font-size:0.95rem;font-weight:700;'
                    f'word-break:break-word;white-space:normal">{descripcion}</div>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.5rem">'
                f'{tarjetas_html}</div>',
                unsafe_allow_html=True
            )

        st.divider()

        # ── Bloque 2: Pivot Points (izq) | Confluencias (der) ────────────
        col_piv, col_conf = st.columns([3, 2])

        with col_piv:
            _ph1, _ph2 = st.columns([6, 1])
            with _ph1:
                st.markdown("### Pivot Points — " + sistema_activo)
            with _ph2:
                with st.popover("ℹ️", use_container_width=True):
                    st.markdown("""
**¿Qué son los Pivot Points?**

Los Pivot Points son niveles de precio calculados matemáticamente a partir de los datos de la sesión anterior (máximo, mínimo y cierre). Representan zonas donde el mercado ha demostrado interés histórico y donde operadores institucionales y algoritmos concentran órdenes.

---

**Cálculo base (sistema Clásico)**
- **PP** = (H + L + C) / 3 — centro de gravedad de la sesión anterior
- **R1** = 2×PP − L · **R2** = PP + (H−L) · **R3** = H + 2×(PP−L)
- **S1** = 2×PP − H · **S2** = PP − (H−L) · **S3** = L − 2×(H−PP)

---

**Sistemas disponibles**

| Sistema | Característica |
|---------|---------------|
| **Clásico** | Fórmula estándar; máximo consenso de mercado |
| **Woodie** | Mayor peso al cierre; PP ≠ media H/L/C |
| **Camarilla** | Niveles muy ceñidos al precio; ideal intradía |
| **Fibonacci** | Usa ratios 38.2 %, 61.8 %, 100 % sobre el rango |
| **DeMark** | PP depende de si el cierre fue alcista o bajista |
| **CPR** | Tres niveles (TC, PP, BC) que miden amplitud esperada del día |

---

**Timeframes calculados**
- **Diario (D1)**: sesión de ayer. Relevante para intradía y swing corto.
- **Semanal (W)**: semana anterior. Referencia swing 2–5 días.
- **Mensual (M)**: mes anterior. Niveles macro de alta probabilidad.

---

**Interpretación operativa**
- Precio **sobre el PP** → sesgo alcista; R1 y R2 son objetivos naturales.
- Precio **bajo el PP** → sesgo bajista; S1 y S2 son los primeros soportes.
- Un nivel donde el precio ha rebotado en sesiones previas tiene mayor peso estadístico.
- Los pivots no son señales de entrada por sí solos — actúan como **zonas de atención** donde se evalúa la reacción del precio (volumen, velocidad, estructura de vela).

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")
            for tf in TIMEFRAMES:
                render_tabla_pivots(tf, resultados_pivots.get(tf), precio)

        with col_conf:
            if confluencias:
                _ch1, _ch2 = st.columns([5, 1])
                with _ch1:
                    st.markdown("### Confluencias Multi-Timeframe")
                with _ch2:
                    with st.popover("ℹ️", use_container_width=True):
                        st.markdown("""
**¿Qué es una Confluencia?**

Una confluencia es una zona de precio donde **dos o más niveles de pivot de distintos timeframes o sistemas convergen** dentro de un margen de tolerancia. Cuantos más niveles coincidan, mayor es su relevancia técnica.

---

**Por qué importan**

Operadores institucionales, algoritmos y traders discrecionales calculan pivots de forma independiente. Cuando múltiples sistemas señalan la misma zona, se acumulan órdenes de distintos actores — convirtiéndola en una barrera más difícil de superar o en un trampolín más potente.

---

**Sistema de estrellas**

| Estrellas | Niveles coincidentes | Relevancia |
|-----------|---------------------|------------|
| ⭐ | 2 niveles | Notable — merece atención |
| ⭐⭐ | 3 niveles | Alta — zona de alta probabilidad |
| ⭐⭐⭐ | 4 o más niveles | Máxima — soporte/resistencia institucional |

---

**Implicaciones según tipo**

- **Confluencia de resistencias** (R1+R2+R_semanal…): zona donde el precio probablemente encuentre vendedores. Objetivo de toma de beneficios en largos o posible entrada en cortos con confirmación.
- **Confluencia de soportes** (S1+S2+S_semanal…): zona de potencial compra. Cuanto más cercana al precio y más ⭐, más relevante para gestionar stop o entrada.
- **Confluencia mixta** (R de un TF + S de otro): zona de indecisión — el precio puede oscilar dentro del rango antes de definir dirección.

---

**Cómo operarlas**

1. **No anticipar**: esperar que el precio llegue a la zona y observar la reacción (volumen, velas de inversión, reducción de momentum en RSI/MACD).
2. **Stop-loss de referencia**: un cierre por debajo de una confluencia ⭐⭐⭐ tiene mayor implicación bajista que romper una resistencia aislada.
3. **Combinar señales**: confluencia ⭐⭐⭐ en soporte + RSI < 30 + volumen bajo = escenario técnico de alta probabilidad de rebote. La convergencia entre sistemas es la clave.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")
                for c in confluencias:
                    dist = ((c["precio"] - precio) / precio * 100) if precio else 0
                    dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
                    niveles_str = " | ".join(
                        f"{n['timeframe'][:3]} {n['nivel']}" for n in c["niveles"][:4])
                    st.markdown(
                        f"**{c['precio']:.4f}** {c['estrellas']} &nbsp; `{dist_str}` "
                        f"<small>{niveles_str}</small>",
                        unsafe_allow_html=True
                    )
            else:
                _ch1, _ch2 = st.columns([5, 1])
                with _ch1:
                    st.markdown("### Confluencias")
                with _ch2:
                    with st.popover("ℹ️", use_container_width=True):
                        st.markdown("""
**¿Qué es una Confluencia?**

Una confluencia es una zona de precio donde **dos o más niveles de pivot de distintos timeframes o sistemas convergen** dentro de un margen de tolerancia. Cuantos más niveles coincidan, mayor es su relevancia técnica.

---

**Por qué importan**

Operadores institucionales, algoritmos y traders discrecionales calculan pivots de forma independiente. Cuando múltiples sistemas señalan la misma zona, se acumulan órdenes de distintos actores — convirtiéndola en una barrera más difícil de superar o en un trampolín más potente.

---

**Sistema de estrellas**

| Estrellas | Niveles coincidentes | Relevancia |
|-----------|---------------------|------------|
| ⭐ | 2 niveles | Notable — merece atención |
| ⭐⭐ | 3 niveles | Alta — zona de alta probabilidad |
| ⭐⭐⭐ | 4 o más niveles | Máxima — soporte/resistencia institucional |

---

**Implicaciones según tipo**

- **Confluencia de resistencias**: zona donde el precio probablemente encuentre vendedores.
- **Confluencia de soportes**: zona de potencial compra con mayor probabilidad de rebote.
- **Confluencia mixta**: zona de indecisión — esperar definición de dirección.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")
                st.caption(f"Sin confluencias dentro de ±{tol_activa:.2f}€")

        st.divider()

        # ── Bloque 3: Indicadores Técnicos | Medias Móviles | Volumen ─────
        # Construir HTML idéntico al informe
        def _ind_s(lbl, val, sub=""):
            sub_h = f'<div class="s-ind-sub">{sub}</div>' if sub else ""
            _sub_span = f" &nbsp;<span class='s-ind-sub'>{sub}</span>" if sub else ""
            return (
                f'<tr>'
                f'<td class="s-ind-lbl">{lbl}</td>'
                f'<td class="s-ind-val">{val}{_sub_span}</td>'
                f'</tr>'
            )

        rsi_sub_s = "Sobrecomprado 🔴" if rsi_val > 70 else ("Sobrevendido 🟢" if rsi_val < 30 else "Neutro ⚪")
        ind_rows = (
            _ind_s("RSI (14)", f"{rsi_val:.2f}", rsi_sub_s) +
            _ind_s("MACD", f"{macd_val:.4f}") +
            _ind_s("MACD Señal", f"{macd_señal:.4f}") +
            _ind_s("MACD Histograma", f"{macd_hist_val:+.4f}", "↑" if macd_hist_val > 0 else "↓") +
            _ind_s("Bollinger Superior", f"{bb_sup:.4f}") +
            _ind_s("Bollinger Media", f"{bb_med:.4f}") +
            _ind_s("Bollinger Inferior", f"{bb_inf:.4f}") +
            _ind_s("Bollinger %B", f"{pct_b:.1f}%") +
            _ind_s("Parabolic SAR", f"{sar_val:.4f}", sar_tend)
        )

        med_rows = ""
        for p_m in sorted(medias.keys()):
            sma, ema = medias[p_m]
            d_sma = precio - sma
            d_ema = precio - ema
            arr_s = "↑" if d_sma > 0 else "↓"
            arr_e = "↑" if d_ema > 0 else "↓"
            med_rows += (
                _ind_s(f"SMA {p_m}", f"{sma:.4f}", arr_s) +
                _ind_s(f"EMA {p_m}", f"{ema:.4f}", arr_e)
            )

        if vol_data:
            vol_rows = (
                _ind_s("Volumen sesión", _fmt_numero(vol_data["volumen"])) +
                _ind_s("Media 10 sesiones", _fmt_numero(vol_data["media_10d"])) +
                _ind_s("Media 3 meses", _fmt_numero(vol_data["media_3m"])) +
                _ind_s("Ratio vs 10d", f"{vol_data['ratio_10d']:.1f}%", f"— {vol_data['clasificacion_10d']}") +
                _ind_s("Ratio vs 3m", f"{vol_data['ratio_3m']:.1f}%", f"— {vol_data['clasificacion_3m']}")
            )
        else:
            vol_rows = "<tr><td colspan='2' style='color:#94a3b8;font-style:italic'>Sin datos</td></tr>"

        screen_ind_css = """
        <style>
        .s-ind-block { background:#fff; border-radius:10px; padding:16px 18px;
                       box-shadow:0 1px 4px rgba(0,0,0,.07); }
        .s-ind-title { font-size:11px; font-weight:700; color:#1e3a5f;
                       text-transform:uppercase; letter-spacing:.6px;
                       margin-bottom:8px; padding-bottom:4px;
                       border-bottom:2px solid #2563eb; }
        .s-ind-block table { width:100%; border-collapse:collapse; font-size:13px; }
        .s-ind-block tr:nth-child(even) td { background:#f8fafc; }
        .s-ind-block td { padding:5px 8px; border-bottom:1px solid #f1f5f9; }
        .s-ind-lbl { color:#64748b; font-size:12px; width:55%; }
        .s-ind-val { font-weight:700; color:#1e293b; }
        .s-ind-sub { font-size:11px; color:#64748b; font-weight:400; }
        </style>
        """

        # ── Cabeceras con ℹ️ para cada bloque ───────────────────────────
        _ih1, _ih2, _ih3 = st.columns([1.1, 1, 0.9])
        with _ih1:
            _ii1, _ii2 = st.columns([5, 1])
            with _ii1:
                st.markdown('<div class="s-ind-title" style="font-size:11px;font-weight:700;color:#1e3a5f;text-transform:uppercase;letter-spacing:.6px">Indicadores Técnicos</div>', unsafe_allow_html=True)
            with _ii2:
                with st.popover("ℹ️", use_container_width=True):
                    st.markdown("""
**RSI — Relative Strength Index (14 sesiones)**

Mide la velocidad y magnitud de los cambios de precio en una escala de 0 a 100.

**Cálculo:** RSI = 100 − [100 / (1 + (Media ganancias 14 días / Media pérdidas 14 días))]

| Zona | Valor | Interpretación |
|------|-------|---------------|
| Sobrecomprado | > 70 | El precio ha subido rápido; posible corrección |
| Neutro | 30–70 | Sin señal extrema; observar tendencia |
| Sobrevendido | < 30 | El precio ha caído rápido; posible rebote |

⚠️ En tendencias fuertes el RSI puede permanecer en zona extrema semanas. Siempre confirmar con precio y volumen.

---

**MACD — Moving Average Convergence Divergence**

Mide la diferencia entre dos medias exponenciales (EMA 12 y EMA 26). La línea de señal es una EMA 9 del MACD.

- **MACD > Señal** y Histograma positivo → momentum alcista
- **MACD < Señal** y Histograma negativo → momentum bajista
- **Cruce alcista** (MACD cruza señal hacia arriba) → señal de compra técnica
- **Histograma decreciendo** → el impulso se está agotando aunque la tendencia continúe

**Cálculo:** MACD = EMA(12) − EMA(26) · Señal = EMA(9) del MACD · Histograma = MACD − Señal

---

**Bandas de Bollinger**

Tres bandas calculadas sobre la SMA 20 ± 2 desviaciones estándar.

- **Banda superior** = SMA20 + 2σ · **Media** = SMA20 · **Inferior** = SMA20 − 2σ
- Contienen ~95% de los precios bajo distribución normal
- **%B = 0%** → precio en banda inferior (sobrevendido técnico) · **%B = 100%** → en banda superior (sobrecomprado técnico)
- **Contracción de bandas** (squeeze) precede movimientos explosivos

---

**Parabolic SAR**

Indicador de seguimiento de tendencia con aceleración geométrica.

- **Precio > SAR** → tendencia alcista; el SAR actúa como stop dinámico bajo el precio
- **Precio < SAR** → tendencia bajista; el SAR actúa como stop dinámico sobre el precio
- El SAR se mueve más rápido cuanto más tiempo lleva la tendencia (factor de aceleración 0.02–0.20)
- Útil para gestión de trailing stops, pero genera señales falsas en mercados laterales

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")
        with _ih2:
            _mi1, _mi2 = st.columns([5, 1])
            with _mi1:
                st.markdown('<div class="s-ind-title" style="font-size:11px;font-weight:700;color:#1e3a5f;text-transform:uppercase;letter-spacing:.6px">Medias Móviles</div>', unsafe_allow_html=True)
            with _mi2:
                with st.popover("ℹ️", use_container_width=True):
                    st.markdown("""
**SMA — Simple Moving Average**

Media aritmética de los N últimos cierres. Trata todos los días por igual.

**Cálculo:** SMA(N) = (C₁ + C₂ + … + Cₙ) / N

---

**EMA — Exponential Moving Average**

Promedio ponderado exponencialmente: los cierres recientes tienen más peso. Reacciona más rápido que la SMA al precio.

**Cálculo:** EMA(N) = Cierre × k + EMA_anterior × (1−k), donde k = 2/(N+1)

---

**Períodos y referencias institucionales**

| Periodo | Referencia | Uso |
|---------|-----------|-----|
| **20** | ~1 mes | Tendencia a corto plazo; Bollinger la usa como base |
| **50** | ~2,5 meses | La más seguida por fondos para medio plazo |
| **200** | ~10 meses | Separación bull/bear de largo plazo; ampliamente usada |

---

**Señales clave**

- **Precio sobre la media** (↑): tendencia alcista en ese plazo. La media actúa como soporte dinámico.
- **Precio bajo la media** (↓): tendencia bajista. La media actúa como resistencia dinámica.
- **Golden Cross**: SMA50 cruza SMA200 hacia arriba → señal alcista de largo plazo.
- **Death Cross**: SMA50 cruza SMA200 hacia abajo → señal bajista de largo plazo.
- **Precio muy alejado de la SMA200**: posible mean reversion; el mercado tiende a volver a la media.

---

**SMA vs EMA**
- SMA: más estable, menos señales falsas, más lenta.
- EMA: más rápida en captar giros, más señales falsas en laterales.
- Usar EMA en tendencias activas; SMA en mercados volátiles o para niveles de largo plazo.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")
        with _ih3:
            _vi1, _vi2 = st.columns([5, 1])
            with _vi1:
                st.markdown('<div class="s-ind-title" style="font-size:11px;font-weight:700;color:#1e3a5f;text-transform:uppercase;letter-spacing:.6px">Volumen</div>', unsafe_allow_html=True)
            with _vi2:
                with st.popover("ℹ️", use_container_width=True):
                    st.markdown("""
**Volumen — El indicador que confirma o niega**

El volumen es el número de acciones o participaciones negociadas en un periodo. Es el único indicador que no puede ser manipulado con el precio — refleja la convicción real detrás de cada movimiento.

---

**Principio básico**

> *"El volumen sigue a la tendencia hasta que la traiciona"*

- **Precio sube + volumen sube** → tendencia alcista con convicción ✅
- **Precio sube + volumen baja** → subida sin participación; riesgo de corrección ⚠️
- **Precio baja + volumen sube** → caída con distribución; señal bajista fuerte ❌
- **Precio baja + volumen baja** → corrección técnica; probable continuación alcista ✅

---

**Ratios de actividad**

- **Ratio vs 10d**: compara el volumen de hoy con la media de las últimas 10 sesiones.
  - > 150%: actividad muy alta — evento o catalizador probable
  - 80–120%: actividad normal
  - < 50%: sesión de baja participación — señales menos fiables

- **Ratio vs 3m**: compara con la media de 3 meses (contexto estructural).
  - Útil para detectar días de acumulación institucional (volumen alto sin movimiento de precio evidente).

---

**Clasificaciones**

| Clasificación | Ratio | Implicación |
|--------------|-------|------------|
| MUY ALTO | > 200% | Evento significativo; posible cambio de tendencia |
| ALTO | 130–200% | Confirmación de movimiento |
| NORMAL | 70–130% | Sesión habitual |
| BAJO | 40–70% | Baja convicción; desconfiar de rupturas |
| MUY BAJO | < 40% | Sin participación; esperar |

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")

        st.markdown(screen_ind_css + f"""
        <div style="display:grid;grid-template-columns:1.1fr 1fr 0.9fr;gap:14px;margin-bottom:0">
          <div class="s-ind-block">
            <table><tbody>{ind_rows}</tbody></table>
          </div>
          <div class="s-ind-block">
            <table><tbody>{med_rows}</tbody></table>
          </div>
          <div class="s-ind-block">
            <table><tbody>{vol_rows}</tbody></table>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # ── Bloque 3e: Divergencias Técnicas ─────────────────────────────
        _dv_h1, _dv_h2 = st.columns([6, 1])
        with _dv_h1:
            st.markdown("### ⚡ Divergencias Técnicas")
        with _dv_h2:
            with st.popover("ℹ️", use_container_width=True):
                st.markdown("""
**¿Qué es una divergencia técnica?**

Una divergencia ocurre cuando el **precio** y un **indicador** se mueven en direcciones opuestas en los extremos recientes. Señala que el movimiento del precio no está siendo respaldado por el momentum interno del mercado — precursor de posibles giros o agotamiento de tendencia.

> Principio: el precio miente antes que el indicador. Las divergencias detectan esa mentira.

---

**📊 RSI vs Precio**

Compara los máximos/mínimos del precio con los del RSI en las últimas 60 sesiones.

- **Alcista**: precio hace un mínimo más bajo, pero el RSI hace un mínimo más alto → los vendedores pierden fuerza aunque el precio siga cayendo. El rebote es inminente.
- **Bajista**: precio hace un máximo más alto, pero el RSI hace un máximo más bajo → los compradores se agotan. Alta probabilidad de corrección.

*Más fiable cuando el RSI se encuentra en zonas extremas (<35 alcista, >65 bajista).*

---

**📈 MACD Histograma vs Precio**

El histograma mide la aceleración del momentum (diferencia entre MACD y su señal). Diverge antes de que las líneas se crucen.

- **Alcista**: precio en nuevos mínimos, histograma con barras negativas que disminuyen → el impulso bajista se frena.
- **Bajista**: precio en nuevos máximos, histograma con barras positivas que disminuyen → el impulso alcista se frena.

*Suele anticipar el cruce de líneas MACD/Señal con 3–8 sesiones de adelanto.*

---

**📦 Volumen vs Precio**

Compara la pendiente del precio con la pendiente del volumen usando regresión lineal sobre las últimas 20 sesiones.

- **Alcista**: precio baja pero el volumen baja también → la caída no tiene participación vendedora. Corrección débil.
- **Bajista**: precio sube pero el volumen baja → la subida carece de convicción compradora. Movimiento sin respaldo.

*El volumen es el único indicador que no puede ser "dibujado" con el precio.*

---

**🏦 OBV (On-Balance Volume) vs Precio**

El OBV suma el volumen en días alcistas y lo resta en días bajistas. Captura el flujo neto de dinero antes de que el precio lo refleje.

- **Alcista**: precio en nuevos mínimos, pero el OBV aguanta o sube → dinero institucional acumulando en silencio.
- **Bajista**: precio en nuevos máximos, pero el OBV baja → distribución encubierta; los grandes operadores están vendiendo mientras el precio sube.

*Considerada la divergencia de mayor calidad: el dinero inteligente deja huella en el volumen antes que en el precio.*

---

**Gradación de fuerza**

| Fuerza | Criterio | Acción sugerida |
|--------|---------|----------------|
| **Fuerte** | Diferencia de pendientes significativa | Señal prioritaria; gestionar posición |
| **Moderada** | Divergencia incipiente | Señal de alerta; esperar confirmación |

---

**⚠️ Limitaciones importantes**
- Una divergencia puede persistir varias sesiones antes de resolverse.
- No son señales de entrada por sí solas — requieren confirmación de precio (vela de reversión, ruptura de estructura, cambio de volumen).
- En tendencias muy fuertes, las divergencias bajistas pueden fallar repetidamente.
- Se analizan sobre las últimas 60 sesiones; condiciones más antiguas no se consideran.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")

        if not divergencias_tecnicas:
            st.info("✅ Sin divergencias detectadas en las últimas 60 sesiones. Precio e indicadores alineados.")
        else:
            # Separar por dirección para mostrar en columnas
            _dv_alc = [d for d in divergencias_tecnicas if d["direccion"] == "alcista"]
            _dv_baj = [d for d in divergencias_tecnicas if d["direccion"] == "bajista"]

            _dv_col1, _dv_col2 = st.columns(2)

            def _dv_card(div):
                _bg  = "#f0fdf4" if div["direccion"] == "alcista" else "#fff1f2"
                _brd = "#16a34a" if div["direccion"] == "alcista" else "#dc2626"
                _fc  = "#166534" if div["direccion"] == "alcista" else "#991b1b"
                _tag = ("🔺 Alcista" if div["direccion"] == "alcista" else "🔻 Bajista")
                _fza = f' · <span style="font-size:0.72rem;opacity:0.8">{div["fuerza"].upper()}</span>'
                st.markdown(
                    f'<div style="background:{_bg};border-left:4px solid {_brd};'
                    f'border-radius:6px;padding:10px 12px;margin-bottom:8px">'
                    f'<div style="font-size:0.78rem;font-weight:700;color:{_fc};margin-bottom:4px">'
                    f'{div["emoji"]} {div["tipo"]} — {_tag}{_fza}</div>'
                    f'<div style="font-size:0.82rem;color:#374151;line-height:1.4">'
                    f'{div["descripcion"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            with _dv_col1:
                if _dv_alc:
                    st.markdown("**Señales alcistas**")
                    for d in _dv_alc:
                        _dv_card(d)
                else:
                    st.caption("Sin divergencias alcistas")

            with _dv_col2:
                if _dv_baj:
                    st.markdown("**Señales bajistas**")
                    for d in _dv_baj:
                        _dv_card(d)
                else:
                    st.caption("Sin divergencias bajistas")

        st.divider()

        # ── Bloque 3d: Convergencia Técnica ──────────────────────────────
        _cv_h1, _cv_h2 = st.columns([6, 1])
        with _cv_h1:
            st.markdown("### 🔀 Convergencia Técnica")
        with _cv_h2:
            with st.popover("ℹ️", use_container_width=True):
                st.markdown("""
**¿Qué es la Convergencia Técnica?**

La convergencia técnica cruza dos análisis que normalmente se realizan por separado: **niveles de precio relevantes** y **consenso de indicadores direccionales**. La idea central es que una señal respaldada por múltiples métodos independientes tiene mayor probabilidad de materializarse que una señal aislada.

---

**1. Niveles Reforzados — Doble anclaje de precio**

Son zonas donde **un nivel pivot y una media móvil coinciden** dentro del margen de tolerancia activo.

- El **pivot** representa memoria estadística del mercado: es una zona donde la interacción entre compradores y vendedores ha dejado huella en el pasado reciente.
- La **media móvil** representa la referencia dinámica de tendencia que siguen operadores institucionales, fondos y algoritmos.
- Cuando ambos coinciden en la misma zona, la concentración de órdenes esperada es mayor.

**Tipos de nivel:**
- 🟢 **Soporte reforzado**: zona donde el precio tiene alta probabilidad de encontrar demanda. Referencia para stop-loss en posiciones largas o zona de entrada vigilada.
- 🔴 **Resistencia reforzada**: zona donde el precio puede encontrar oferta. Objetivo de toma de beneficios o zona de entrada en cortos con confirmación.

*La tolerancia activa define cuánto margen de distancia se permite entre el pivot y la media para considerarlos coincidentes.*

---

**2. Señal de Consenso — Votación de indicadores**

Cada indicador "vota" por una dirección (alcista / bajista / neutro):

| Indicador | Criterio alcista | Criterio bajista |
|-----------|-----------------|-----------------|
| RSI | > 50 | < 50 |
| MACD | Histograma positivo | Histograma negativo |
| Parabolic SAR | Precio > SAR | Precio < SAR |
| Bollinger %B | > 50% | < 50% |
| Precio vs SMA20 | Precio > SMA20 | Precio < SMA20 |
| Precio vs SMA50 | Precio > SMA50 | Precio < SMA50 |
| Precio vs SMA200 | Precio > SMA200 | Precio < SMA200 |

El porcentaje de votos alcistas / bajistas forma la señal de consenso.

**Interpretación:**
- ≥ 70% alcista → convicción técnica alcista: los indicadores están alineados
- ≥ 70% bajista → convicción técnica bajista
- 40–60% → mercado lateral o sin dirección clara; señales menos fiables
- Consenso mixto (cerca del 50%) → evitar decisiones basadas solo en indicadores; priorizar estructura de precio y volumen

---

**Cómo usarlo en la práctica**

1. **Nivel reforzado + consenso alcista**: zona de soporte con indicadores a favor → escenario de alta probabilidad para valorar una entrada larga con stop bajo el nivel.
2. **Nivel reforzado + consenso bajista**: zona de resistencia con indicadores en contra → objetivo natural de toma de beneficios o entrada corta.
3. **Consenso mixto cerca de nivel reforzado**: esperar confirmación — el nivel puede actuar en cualquier dirección.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""")

        col_conv_niv, col_conv_dir = st.columns([3, 2])

        with col_conv_niv:
            st.markdown("**Niveles reforzados** *(pivot + media móvil)*")
            if niveles_reforzados:
                for nr in niveles_reforzados:
                    dist = ((nr["precio"] - precio) / precio * 100) if precio else 0
                    dist_str = f"+{dist:.2f}%" if dist >= 0 else f"{dist:.2f}%"
                    tipo_emoji = "🔴" if nr["tipo"] == "R" else ("🟢" if nr["tipo"] == "S" else "🔵")
                    tipo_label = "Resistencia" if nr["tipo"] == "R" else ("Soporte" if nr["tipo"] == "S" else "Pivot")
                    with st.container():
                        c1, c2, c3 = st.columns([3, 1, 2])
                        with c1:
                            st.markdown(
                                f"{tipo_emoji} **{nr['precio']:.4f}** `{dist_str}`  \n"
                                f"<small style='color:#555'>{nr['pivot']} · {nr['media']}</small>",
                                unsafe_allow_html=True
                            )
                        with c2:
                            q_google = f"{nr['pivot']} {nr['media']} {tipo_label} análisis técnico confluencia"
                            st.link_button("🔍", _url_google(q_google), help="Buscar en Google")
                        with c3:
                            termino_inv = f"{nr['media']} support resistance pivot"
                            st.link_button("📖 Investopedia", _url_investopedia(termino_inv), help="Buscar en Investopedia")
            else:
                st.caption(f"Sin niveles pivot+media dentro de ±{tol_activa:.2f}")

        with col_conv_dir:
            st.markdown("**Señal de consenso**")
            emoji_cons, label_cons = consenso_dir[1], consenso_dir[2]
            st.markdown(
                f'<div style="background:var(--secondary-background-color,#f0f2f6);'
                f'border-radius:0.5rem;padding:0.6rem 0.8rem;margin-bottom:0.6rem">'
                f'<span style="font-size:1.5rem">{emoji_cons}</span>'
                f'<span style="font-size:0.95rem;font-weight:700;margin-left:0.5rem">'
                f'{label_cons}</span></div>',
                unsafe_allow_html=True
            )
            for nombre_s, desc_s, dir_s, _ in señales_dir:
                q_google_s = f"{nombre_s} {desc_s.split()[1] if len(desc_s.split()) > 1 else ''} análisis técnico trading"
                c_s1, c_s2, c_s3 = st.columns([4, 1, 1])
                with c_s1:
                    st.markdown(
                        f"<small><b>{nombre_s}</b>: {desc_s}</small>",
                        unsafe_allow_html=True
                    )
                with c_s2:
                    st.link_button("🔍", _url_google(q_google_s), help=f"Google: {nombre_s}")
                with c_s3:
                    st.link_button("📖", _url_investopedia(nombre_s), help=f"Investopedia: {nombre_s}")

        st.divider()

        # ── Bloque 3f: Huecos de Precio ───────────────────────────────────
        st.markdown("### 📊 Huecos de Precio Abiertos")
        _h_info_md = """
**¿Qué es un hueco?**

Un hueco (*gap*) ocurre cuando el precio de apertura de una sesión es superior al máximo de la sesión anterior (hueco alcista) o inferior al mínimo anterior (hueco bajista). Los huecos abiertos actúan como imanes: el mercado tiende a volver a rellenarlos estadísticamente.

---

**Tipos**
- 🔼 **Alcista**: zona de soporte potencial. El precio subió dejando un vacío por debajo.
- 🔽 **Bajista**: zona de resistencia potencial. El precio cayó dejando un vacío por encima.

---

**Distancia**
- Positiva (+): el precio actual está *por encima* de la zona del hueco.
- Negativa (−): el precio actual está *por debajo* de la zona del hueco.

---

*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
"""
        with st.expander("ℹ️ Huecos de Precio", expanded=False):
            st.markdown(_h_info_md)

        if huecos_abiertos:
            _h_cols = st.columns(min(len(huecos_abiertos), 3))
            for _hi, _hue in enumerate(huecos_abiertos[:6]):
                with _h_cols[_hi % 3]:
                    _h_tipo    = _hue["tipo"]
                    _h_emoji   = "🔼" if _h_tipo == "alcista" else "🔽"
                    _h_color   = "#16a34a" if _h_tipo == "alcista" else "#dc2626"
                    _h_bg      = "#f0fdf4" if _h_tipo == "alcista" else "#fef2f2"
                    _h_label   = "Soporte potencial" if _h_tipo == "alcista" else "Resistencia potencial"
                    _h_dist    = _hue["dist_pct"]
                    _h_dist_str = f"+{_h_dist:.2f}%" if _h_dist >= 0 else f"{_h_dist:.2f}%"
                    _h_dist_color = "#16a34a" if _h_dist >= 0 else "#dc2626"
                    st.markdown(
                        f'<div style="background:{_h_bg};border-left:4px solid {_h_color};'
                        f'border-radius:6px;padding:10px 12px;margin-bottom:8px">'
                        f'<div style="font-size:11px;color:{_h_color};font-weight:700;'
                        f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">'
                        f'{_h_emoji} Hueco {_h_tipo} · {_h_label}</div>'
                        f'<div style="font-size:13px;font-weight:700;color:#1e293b">'
                        f'{_hue["gap_low"]:.4f} – {_hue["gap_high"]:.4f}</div>'
                        f'<div style="font-size:12px;color:#475569;margin-top:3px">'
                        f'Tamaño: <b>{_hue["gap_pct"]:.2f}%</b> · '
                        f'Distancia: <b style="color:{_h_dist_color}">{_h_dist_str}</b></div>'
                        f'<div style="font-size:11px;color:#94a3b8;margin-top:3px">'
                        f'{_hue["fecha"]} · {_hue["dias_abierto"]}d abierto</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
        else:
            st.caption("No se detectan huecos abiertos significativos (≥ 0.3%) en los últimos 252 días.")

        st.divider()

        # ── Bloque: Diagnóstico Técnico ───────────────────────────────────
        st.markdown("### 📝 Diagnóstico Técnico")

        # ── Componente 1: Máximos Históricos ─────────────────────────────
        if analisis_ath:
            _ath = analisis_ath
            _esc = _ath["escenario"]

            # Paleta de colores por escenario
            _colores_ath = {
                "subida_libre_establecida": ("#f0fdf4", "#16a34a", "🚀", "SUBIDA LIBRE"),
                "en_ath":                  ("#f0fdf4", "#16a34a", "🏔️", "EN MÁXIMOS HISTÓRICOS"),
                "aproximandose_cerca":     ("#fefce8", "#ca8a04", "⚡", "MUY CERCA DEL ATH"),
                "aproximandose":           ("#fefce8", "#ca8a04", "📈", "APROXIMÁNDOSE AL ATH"),
                "referencia":              ("#f8fafc", "#64748b", "📊", "REFERENCIA ATH"),
                "lejos":                   ("#f8fafc", "#94a3b8", "📉", "ATH LEJANO"),
            }
            _bg, _border, _emoji, _badge = _colores_ath.get(
                _esc, ("#f8fafc", "#64748b", "📊", "ATH")
            )

            # Métricas rápidas
            _c1, _c2, _c3 = st.columns(3)
            with _c1:
                st.metric(
                    "Máximo Histórico (ATH)",
                    f"{_ath['ath']:.4f} €",
                    help="Precio máximo absoluto en todo el histórico disponible"
                )
            with _c2:
                _dist_str = (
                    f"+{_ath['dist_pct']:.2f}%" if _ath["dist_pct"] >= 0
                    else f"{_ath['dist_pct']:.2f}%"
                )
                st.metric(
                    "Distancia al ATH",
                    _dist_str,
                    help="% que separa el precio actual del máximo histórico"
                )
            with _c3:
                if _ath["target"]:
                    st.metric(
                        "Proyección Fibonacci 127.2%",
                        f"{_ath['target']:.4f} €",
                        help="Extensión de Fibonacci 127.2% desde el mínimo del año previo al ATH"
                    )
                else:
                    st.metric("Fecha del ATH", _ath["ath_fecha"])

            # Tarjeta narrativa
            st.markdown(
                f'<div style="background:{_bg};border-left:4px solid {_border};'
                f'border-radius:8px;padding:14px 18px;margin-top:8px;">'
                f'<span style="font-size:11px;font-weight:700;color:{_border};'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'{_emoji} {_badge}</span>'
                f'<p style="margin:8px 0 0 0;font-size:15px;color:#1e293b;line-height:1.6;">'
                f'{_ath["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.caption("No se pudo calcular el análisis de máximos históricos para este valor.")

        # ── Componente 2: SMA200 — Tendencia y Giro ───────────────────────
        if analisis_sma200:
            _s = analisis_sma200
            _esc_s = _s["escenario"]

            # Paleta por escenario
            _colores_sma = {
                "giro_alcista_reciente":  ("#f0fdf4", "#16a34a", "🔄", "GIRO ALCISTA — MM200"),
                "tendencia_alcista":      ("#f0fdf4", "#16a34a", "📈", "TENDENCIA ALCISTA — MM200"),
                "giro_bajista_reciente":  ("#fef2f2", "#dc2626", "🔄", "GIRO BAJISTA — MM200"),
                "tendencia_bajista":      ("#fef2f2", "#dc2626", "📉", "TENDENCIA BAJISTA — MM200"),
                "plana":                  ("#f8fafc", "#64748b", "➡️", "MM200 LATERAL"),
            }
            _bg_s, _brd_s, _em_s, _badge_s = _colores_sma.get(
                _esc_s, ("#f8fafc", "#64748b", "📊", "MM200")
            )

            # Si el precio perfora la media en contra de la tendencia, matiz naranja
            _contradiccion = (
                (_esc_s == "tendencia_alcista" and not _s["precio_sobre"]) or
                (_esc_s == "tendencia_bajista" and _s["precio_sobre"]) or
                (_esc_s == "giro_bajista_reciente" and _s["precio_sobre"])
            )
            if _contradiccion:
                _bg_s, _brd_s = "#fffbeb", "#d97706"

            _c1s, _c2s, _c3s = st.columns(3)
            with _c1s:
                st.metric(
                    "Media 200 sesiones",
                    f"{_s['sma200']:.4f} €",
                    help="Valor actual de la media móvil simple de 200 sesiones"
                )
            with _c2s:
                _d_str = (
                    f"+{_s['dist_pct']:.2f}%" if _s["dist_pct"] >= 0
                    else f"{_s['dist_pct']:.2f}%"
                )
                st.metric(
                    "Distancia precio / MM200",
                    _d_str,
                    help="% que separa el precio actual de la media de 200 sesiones"
                )
            with _c3s:
                _pend_str = (
                    f"+{_s['pendiente_pct']:.3f}% / 5 ses." if _s["pendiente_pct"] >= 0
                    else f"{_s['pendiente_pct']:.3f}% / 5 ses."
                )
                st.metric(
                    "Pendiente MM200",
                    _pend_str,
                    help="Variación porcentual de la media en las últimas 5 sesiones"
                )

            st.markdown(
                f'<div style="background:{_bg_s};border-left:4px solid {_brd_s};'
                f'border-radius:8px;padding:14px 18px;margin-top:8px;">'
                f'<span style="font-size:11px;font-weight:700;color:{_brd_s};'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'{_em_s} {_badge_s}</span>'
                f'<p style="margin:8px 0 0 0;font-size:15px;color:#1e293b;line-height:1.6;">'
                f'{_s["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.caption("No hay suficientes datos para calcular la media de 200 sesiones.")

        # ── Componente 3: Resistencias y Soportes Estructurales ───────────
        analisis_resist = analisis_resist
        if analisis_resist:
            _r = analisis_resist
            _esc_r = _r["escenario"]

            # Paleta por escenario
            _colores_r = {
                "en_resistencia":   ("#fef2f2", "#dc2626", "🧱", "EN RESISTENCIA ESTRUCTURAL"),
                "zona_alta_rango":  ("#fef2f2", "#dc2626", "📛", "ZONA ALTA DEL RANGO"),
                "sin_soporte":      ("#fef2f2", "#dc2626", "⚠️", "SIN SOPORTE TÉCNICO"),
                "en_soporte":       ("#f0fdf4", "#16a34a", "🛡️", "EN SOPORTE ESTRUCTURAL"),
                "zona_baja_rango":  ("#f0fdf4", "#16a34a", "🎯", "ZONA BAJA DEL RANGO"),
                "sin_resistencia":  ("#f0fdf4", "#16a34a", "🚀", "SIN RESISTENCIA SOBRE EL PRECIO"),
                "zona_media_rango": ("#f8fafc", "#64748b", "↔️", "ZONA MEDIA DEL RANGO"),
            }
            _bg_r, _brd_r, _em_r, _badge_r = _colores_r.get(
                _esc_r, ("#f8fafc", "#64748b", "📊", "NIVELES ESTRUCTURALES")
            )

            _c1r, _c2r, _c3r = st.columns(3)
            with _c1r:
                if _r["soporte"]:
                    _sp = _r["soporte"]
                    st.metric(
                        "Soporte reforzado",
                        f"{_sp['precio']:.4f} €",
                        delta=f"-{_r['dist_soporte']:.2f}%" if _r["dist_soporte"] else None,
                        delta_color="inverse",
                        help=f"Nivel pivot + media móvil: {_sp.get('pivot','')}"
                    )
                else:
                    st.metric("Soporte reforzado", "—", help="Sin soporte identificado bajo el precio")
            with _c2r:
                if _r["resistencia"]:
                    _rs = _r["resistencia"]
                    st.metric(
                        "Resistencia reforzada",
                        f"{_rs['precio']:.4f} €",
                        delta=f"+{_r['dist_resist']:.2f}%" if _r["dist_resist"] else None,
                        help=f"Nivel pivot + media móvil: {_rs.get('pivot','')}"
                    )
                else:
                    st.metric("Resistencia reforzada", "—", help="Sin resistencia identificada sobre el precio")
            with _c3r:
                if _r["pos_rango_pct"] is not None:
                    st.metric(
                        "Posición en rango",
                        f"{_r['pos_rango_pct']:.0f}%",
                        help="% de posición entre el soporte y la resistencia más cercanos (0%=soporte, 100%=resistencia)"
                    )
                else:
                    st.metric("Posición en rango", "—", help="Insuficientes niveles para calcular el rango")

            st.markdown(
                f'<div style="background:{_bg_r};border-left:4px solid {_brd_r};'
                f'border-radius:8px;padding:14px 18px;margin-top:8px;">'
                f'<span style="font-size:11px;font-weight:700;color:{_brd_r};'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'{_em_r} {_badge_r}</span>'
                f'<p style="margin:8px 0 0 0;font-size:15px;color:#1e293b;line-height:1.6;">'
                f'{_r["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.caption("No se pudieron calcular niveles estructurales para este valor.")

        st.divider()


        # ── Componente 4: Fibonacci Retracement / Extensión ─────────────
        analisis_fibo = analisis_fibo
        if analisis_fibo:
            _f = analisis_fibo
            _esc_f = _f["escenario"]
            _colores_f = {
                "extension_161": ("#eff6ff", "#1d4ed8", "🚀", "EXTENSIÓN 161.8%"),
                "extension_127": ("#eff6ff", "#2563eb", "📈", "EXTENSIÓN 127.2%"),
                "en_maximo":     ("#f0fdf4", "#16a34a", "🏔️", "EN EL MÁXIMO DEL SWING"),
                "retroceso_236": ("#f0fdf4", "#15803d", "✅", "RETROCESO 23.6%"),
                "retroceso_382": ("#fefce8", "#ca8a04", "⚖️", "RETROCESO 38.2–50%"),
                "retroceso_618": ("#fff7ed", "#c2410c", "🌀", "ZONA DORADA 61.8%"),
                "retroceso_786": ("#fef2f2", "#dc2626", "⚠️", "RETROCESO PROFUNDO 78.6%"),
                "swing_roto":    ("#fef2f2", "#991b1b", "💥", "SWING ROTO"),
            }
            _bg_f, _col_f, _ico_f, _lab_f = _colores_f.get(
                _esc_f,
                ("#f8fafc", "#64748b", "📐", _esc_f.upper())
            )
            _fa = _f.get("fib_abajo")
            _fu = _f.get("fib_arriba")
            _c1_f, _c2_f, _c3_f = st.columns(3)
            with _c1_f:
                if _fa:
                    st.metric(
                        f"Fib debajo ({_fa['label']})",
                        f"{_fa['precio']:,.4f}",
                        delta=f"-{_fa['dist_pct']:.1f}%",
                        delta_color="off",
                        help="Nivel de Fibonacci más cercano por debajo del precio actual"
                    )
                else:
                    st.metric("Fib debajo", "—")
            with _c2_f:
                if _fu:
                    st.metric(
                        f"Fib arriba ({_fu['label']})",
                        f"{_fu['precio']:,.4f}",
                        delta=f"+{_fu['dist_pct']:.1f}%",
                        delta_color="off",
                        help="Nivel de Fibonacci más cercano por encima del precio actual"
                    )
                else:
                    st.metric("Fib arriba", "—")
            with _c3_f:
                st.metric(
                    "Posición en swing",
                    f"{_f['pos_pct']:.1f}%",
                    delta="alcista" if _f["bullish"] else "bajista",
                    delta_color="normal" if _f["bullish"] else "inverse",
                    help="0 % = mínimo del swing anual · 100 % = máximo · >100 % = extensión"
                )
            st.markdown(
                f'<div style="background:{_bg_f};border-left:4px solid {_col_f};'
                f'border-radius:6px;padding:12px 16px;margin-top:8px;">'
                f'<span style="font-weight:700;color:{_col_f};">'
                f'{_ico_f} FIBONACCI — {_lab_f}</span><br/>'
                f'<p style="margin:6px 0 0 0;font-size:0.92rem;color:#374151;">'
                f'{_f["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.caption("Datos insuficientes para calcular niveles de Fibonacci.")


        # ── Bloque 4: Datos Fundamentales ────────────────────────────────
        if fundamentales:
            st.markdown("### Datos Fundamentales")
            fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
            st.markdown('<div class="fund-metrics">', unsafe_allow_html=True)
            cols_f = st.columns(3)
            for i, (k, v) in enumerate(fund_items):
                with cols_f[i % 3]:
                    st.metric(k, v, help=TOOLTIPS.get(k))
            st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        # Descarga informe
        st.markdown("### 📥 Exportar informe")
        col_fmt, col_btn = st.columns([1, 3])
        with col_fmt:
            fmt_sel = st.radio("Formato", ["HTML", "PDF"],
                               horizontal=True, key="fmt_export")
        with col_btn:
            if st.button("⬇️ Generar informe", type="primary", key="btn_export"):
                ts = datetime.now().strftime("%Y%m%d_%H%M")
                if fmt_sel == "HTML":
                    with st.spinner("Generando HTML..."):
                        html_str = generar_informe_html(
                            ticker=ticker_activo,
                            nombre=nombre,
                            tipo_activo=tipo_activo,
                            precio=precio,
                            cambio=cambio,
                            cambio_pct=cambio_pct,
                            h52=info.get("fiftyTwoWeekHigh"),
                            l52=info.get("fiftyTwoWeekLow"),
                            currency=info.get("currency", ""),
                            sistema=sistema_activo,
                            resultados_pivots=resultados_pivots,
                            confluencias=confluencias,
                            semaforo=color_sem,
                            pct_semaforo=pct_sem,
                            factores_semaforo=factores_sem,
                            rsi_val=rsi_val,
                            macd_val=macd_val,
                            macd_señal=macd_señal,
                            macd_hist_val=macd_hist_val,
                            sar_val=sar_val,
                            sar_tend=sar_tend,
                            pct_b=pct_b,
                            medias=medias,
                            vol_data=vol_data,
                            fundamentales=fundamentales,
                            tolerancia=tol_activa,
                            niveles_reforzados=niveles_reforzados,
                            señales_dir=señales_dir,
                            consenso_dir=consenso_dir,
                            divergencias_tecnicas=divergencias_tecnicas,
                            bb_sup=bb_sup,
                            bb_med=bb_med,
                            bb_inf=bb_inf,
                            huecos=huecos_abiertos,
                        )
                    st.download_button(
                        label="📄 Descargar HTML",
                        data=html_str.encode("utf-8"),
                        file_name=f"{ticker_activo}_{ts}.html",
                        mime="text/html",
                        key="dl_html",
                    )
                else:
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
                            nombre=nombre,
                            tipo_activo=tipo_activo,
                            cambio=cambio,
                            cambio_pct=cambio_pct,
                            h52=info.get("fiftyTwoWeekHigh"),
                            l52=info.get("fiftyTwoWeekLow"),
                            currency=info.get("currency", ""),
                            pct_semaforo=pct_sem,
                            niveles_reforzados=niveles_reforzados,
                            señales_dir=señales_dir,
                            consenso_dir=consenso_dir,
                            divergencias_tecnicas=divergencias_tecnicas,
                            huecos=huecos_abiertos,
                        )
                    st.download_button(
                        label="📄 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"{ticker_activo}_{ts}.pdf",
                        mime="application/pdf",
                        key="dl_pdf",
                    )

    # ---- TAB ESTRATEGIA ----
    with tab_estrategia:
        ed = st.session_state.get("estrategia_data")

        if not ed:
            st.info("📊 Selecciona y analiza un valor en la pestaña **Análisis Técnico** para ver las estrategias.")
        else:
            import numpy as _np_est

            # ── Cabecera ─────────────────────────────────────────────────
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px">'
                f'<span style="font-size:1.3rem;font-weight:700">{ed["ticker"]}</span>'
                f'<span style="font-size:1rem;color:#555">{ed["nombre"]}</span>'
                f'<span style="font-size:0.85rem;color:#888;margin-left:auto">Datos: {ed["ts"]}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown(
                f'<p style="font-size:1.05rem;margin:0 0 12px 0">'
                f'Precio: <b>{ed["precio"]:.4f}</b></p>',
                unsafe_allow_html=True
            )

            # ── Helpers de scoring ────────────────────────────────────────
            def _criterio(ok, texto, detalle=""):
                if ok == 2:   icn, col = "✅", "#166534"
                elif ok == 1: icn, col = "⚠️", "#92400e"
                else:         icn, col = "❌", "#991b1b"
                det = f'<span style="color:#6b7280;font-size:0.78rem"> — {detalle}</span>' if detalle else ""
                return (
                    f'<div style="padding:4px 0;border-bottom:1px solid #f3f4f6;font-size:0.84rem">'
                    f'{icn} <span style="color:{col}">{texto}</span>{det}</div>',
                    ok
                )

            # Popovers detallados por estrategia (Streamlit markdown)
            _est_popover = {
                "💰 Dividendos": """
**💰 Estrategia de Dividendos — Rentas a largo plazo**

Busca maximizar la **rentabilidad por dividendo efectiva** comprando en el punto de menor precio relativo. El dividendo remunera la espera; el precio de entrada determina el yield real que percibirás.

---

**Orden de análisis (de mayor a menor peso):**

**1. Dividend Yield** *(criterio de selección)*
- ≥ 3.5%: atractivo para estrategia de rentas
- 2–3.5%: aceptable si el crecimiento del dividendo es sólido
- < 2%: insuficiente como estrategia de rentas pura
- *Punto clave: el yield mejora automáticamente cuando el precio cae. Comprar en correcciones aumenta la rentabilidad sin que la empresa cambie nada.*

**2. Payout Ratio** *(sostenibilidad del pago)*
- < 60%: dividendo muy sostenible; hay margen para crecer
- 60–75%: sostenible pero sin holgura; vigilar tendencia de beneficios
- > 75%: frágil; un trimestre malo puede recortar el dividendo
- *Un dividendo alto pero insostenible es una trampa. El recorte de dividendo destruye el yield y el precio simultáneamente.*

**3. Posición en rango 52 semanas** *(precio de entrada)*
- < 35% del rango: zona de valor; precio deprimido históricamente
- 35–65%: zona neutra; yield razonable pero no óptimo
- > 65%: cerca de máximos; el yield es el más bajo del año
- *Comprar cerca de mínimos anuales puede mejorar el yield efectivo un 20–40% respecto a comprar en máximos.*

**4. SMA200** *(confirmación de valor)*
- Precio bajo SMA200: zona de compra histórica para largo plazo
- Precio sobre SMA200: mercado ya ha revalorizado; el yield es más bajo
- *La SMA200 actúa como referencia del "precio justo a largo plazo". Por debajo es donde los gestores de fondos de renta encuentran valor.*

**5. RSI** *(timing de entrada)*
- RSI 30–45: sobreventa → zona óptima de entrada escalonada
- RSI 45–60: neutral; válido pero sin urgencia
- RSI > 65: sobrecomprado; esperar retroceso para mejorar precio medio

**6. Divergencias y soportes** *(confirmación técnica)*
- Divergencia alcista OBV activa: dinero institucional acumulando → señal de suelo
- Soporte pivot+media próximo: colchón estructural; referencia natural para stop

---

**Momento óptimo de entrada**
Todos los criterios alineados: yield ≥ 3.5% + precio bajo SMA200 + RSI < 45 + soporte reforzado activo + divergencia alcista OBV. Ese setup aparece pocas veces al año por valor — cuando aparece, es el punto de máxima asimetría riesgo/recompensa para rentas.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""",
                "📈 Swing 12-16 sem": """
**📈 Swing Trading 12–16 semanas — Posición tendencial**

Captura movimientos tendenciales de 3–4 meses subiendo a una tendencia ya establecida, no apostando por un giro. El objetivo es comprar el retroceso dentro de una tendencia alcista con recorrido claro hasta la siguiente resistencia.

---

**Orden de análisis:**

**1. Estructura de tendencia** *(condición necesaria — si falla, para aquí)*
- Precio > SMA50 > SMA200: tendencia alcista completa; el mercado confirma la dirección
- Precio > SMA50 pero SMA50 < SMA200: tendencia emergente; mayor riesgo
- Precio < SMA50: sin tendencia establecida; el swing no tiene base
- *Un swing en contra de la tendencia principal tiene una tasa de éxito estadísticamente inferior. No escalar un problema.*

**2. RSI** *(ventana de entrada)*
- RSI 42–62: zona ideal de entrada en retroceso dentro de tendencia
- RSI < 42: retroceso profundo; posible debilidad real, no solo corrección
- RSI > 65: sobreextendido; entrar ahora asume demasiado riesgo de corrección
- *El objetivo no es comprar el suelo exacto, sino comprar en una zona donde la relación riesgo/recompensa es favorable.*

**3. MACD histograma** *(momentum del movimiento)*
- Histograma positivo y creciente: impulso activo; señal de continuación
- Histograma positivo pero decreciente: impulso frena; esperar confirmación
- Histograma negativo: momentum bajista; el setup está en entredicho
- *El MACD histograma anticipa los cruces de líneas. Una divergencia bajista en histograma invalida el setup incluso si el precio sigue subiendo.*

**4. Divergencias técnicas** *(validación o invalidación)*
- Divergencia bajista RSI/MACD: señal de agotamiento → INVALIDA el setup hasta resolución
- Divergencia alcista activa: confirmación adicional del rebote dentro de tendencia
- *Una divergencia bajista activa en swing tendencial es el mayor riesgo del setup. Nunca ignorarla.*

**5. Niveles de soporte y resistencia** *(geometría del trade)*
- Soporte reforzado próximo: referencia lógica para stop-loss
- Resistencia identificada: objetivo de precio; define el ratio riesgo/beneficio
- Sin ambos identificados: el trade no tiene estructura; esperar

**6. Volumen** *(confirmación del movimiento)*
- Volumen creciente en el impulso: convicción compradora real
- Volumen decreciente en el retroceso: corrección sana dentro de tendencia (ideal)
- Volumen alto en caída: posible distribución; reevaluar

---

**Momento óptimo de entrada**
Tendencia completa (precio>SMA50>SMA200) + RSI en 45–58 en retroceso + histograma MACD positivo aunque decreciendo + soporte reforzado identificado + sin divergencias bajistas activas + volumen bajo en el retroceso. Stop bajo el soporte identificado. Objetivo: resistencia siguiente (ratio mínimo 1:2).

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""",
                "🏷️ Valor": """
**🏷️ Inversión en Valor — Filosofía Graham/Buffett**

Comprar participaciones en negocios de calidad a precios que ofrezcan un margen de seguridad respecto a su valor intrínseco. El tiempo y los beneficios compuestos hacen el trabajo. El timing es secundario al precio de entrada.

---

**Orden de análisis:**

**1. PER (Price/Earnings)** *(valoración fundamental)*
- < 12x: precio muy bajo respecto a beneficios; posible infravaloración
- 12–18x: rango de valor razonable para empresas maduras
- 18–25x: valoración justa; poco margen de seguridad
- > 25x: precio exigente; requiere crecimiento excepcional para justificarse
- *El PER solo tiene sentido en contexto: comparar con el sector, con el histórico del valor y con el crecimiento esperado de beneficios (PEG = PER / crecimiento BPA).*

**2. Descuento respecto a SMA200** *(precio vs valor histórico)*
- Precio ≥ 15% bajo SMA200: zona de valor histórico profunda
- Precio 5–15% bajo SMA200: descuento moderado; razonable
- Precio sobre SMA200: el mercado ya ha revalorizado; margen de seguridad reducido
- *La SMA200 aproxima el precio medio de largo plazo. Comprar bajo ella implica pagar menos que la media histórica.*

**3. Posición en rango 52W** *(temperatura del precio)*
- < 30% del rango: precio históricamente deprimido; el mercado descuenta problemas reales o exagera
- 30–55%: zona neutra; valoración equilibrada
- > 65%: cerca de máximos anuales; escaso margen de seguridad
- *El inversor en valor no busca comprar barato en términos absolutos, sino barato respecto al valor intrínseco. Un valor en máximos puede ser barato si el negocio crece rápido.*

**4. Beta defensiva** *(perfil de riesgo)*
- Beta < 0.7: activo defensivo; protege el capital en caídas de mercado
- Beta 0.7–1.1: comportamiento de mercado; aceptable
- Beta > 1.3: volátil; el margen de seguridad debe ser mayor para compensar
- *El valor no implica necesariamente baja volatilidad, pero los activos defensivos permiten mantener la posición psicológicamente durante el periodo de reconocimiento del valor.*

**5. Dividend yield** *(colchón de retorno)*
- Dividendo > 0: la espera tiene retribución mientras el mercado reconoce el valor
- Payout sostenible: el dividendo no compromete la inversión en el negocio
- *El dividendo no es un criterio de selección en valor, pero actúa como seguro: si el mercado tarda en reconocer el valor, el dividendo compensa la espera.*

**6. Divergencias técnicas** *(confirmación de acumulación)*
- Divergencia alcista OBV: el dinero inteligente acumula mientras el precio cae; señal de que el descuento es real pero temporal
- Soporte reforzado: colchón estructural que limita el riesgo de caída adicional

---

**Momento óptimo de entrada**
PER < 15x + precio ≥ 10% bajo SMA200 + posición < 40% en rango 52W + divergencia alcista OBV activa (acumulación) + soporte reforzado identificado. Entrada escalonada: no concentrar todo en un punto dado que el timing es secundario — el margen de seguridad es la protección.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""",
                "🚀 Momentum": """
**🚀 Momentum — Subirse al tren en marcha**

No es anticipar un giro sino confirmar y seguir una tendencia ya establecida con fuerza. El momentum se basa en la inercia del precio: lo que sube tiende a seguir subiendo mientras la convicción y el flujo de capital se mantengan.

---

**Orden de análisis:**

**1. Tendencia estructural** *(condición de base)*
- Precio > SMA50 > SMA200: tendencia alcista establecida en todos los plazos
- SAR alcista (precio sobre el SAR): la tendencia tiene dirección definida
- Consenso de indicadores ≥ 70% alcista: el conjunto de señales confirma la dirección
- *El momentum solo funciona en tendencias claras. En laterales, las señales son falsas y el coste por rotación es alto.*

**2. RSI** *(zona de momentum activo)*
- RSI 55–72: zona de momentum sin sobrecompra extrema; el tren sigue pero no está a punto de frenar
- RSI > 72: sobrecomprado; el momentum puede continuar pero el riesgo de corrección es elevado
- RSI < 50: momentum perdido; la tendencia se ha enfriado; no es el momento
- *En momentum puro, el RSI puede mantenerse en zona 60–75 semanas seguidas en tendencias fuertes. No salir solo porque el RSI está "alto".*

**3. MACD histograma** *(aceleración del impulso)*
- Histograma positivo y creciente: el impulso se acelera; señal más fuerte del setup
- Histograma positivo estable: impulso mantenido; válido pero sin aceleración
- Histograma positivo decreciente: el impulso frena; posible entrada tardía
- Histograma negativo: momentum perdido aunque el precio siga cerca de máximos
- *La trampa del momentum tardío: el precio puede estar alto pero el histograma ya declinando indica que el movimiento está maduro.*

**4. Volumen** *(convicción institucional)*
- Volumen creciente en la tendencia alcista: flujo de capital real respaldando el movimiento
- Volumen neutral: tendencia válida pero sin aceleración
- Volumen decreciente mientras el precio sube: movimiento sin convicción; riesgo de reversión
- *El momentum sin volumen creciente es frágil. Los grandes movimientos necesitan flujo institucional.*

**5. Divergencias bajistas** *(señal de alerta máxima)*
- Sin divergencias bajistas: setup limpio
- Divergencia bajista en RSI o MACD: el momentum se agota aunque el precio no lo refleje todavía; NO entrar
- *Una divergencia bajista en momentum es la señal de salida, no de entrada. Si aparece, el setup se invalida completamente.*

**6. Distancia a SMA50** *(extensión del movimiento)*
- < 8% sobre SMA50: movimiento con recorrido; la tendencia no está sobreextendida
- 8–15% sobre SMA50: vigilar; posible corrección a la media antes del siguiente impulso
- > 15% sobre SMA50: muy sobreextendido; la corrección a la media puede ser el siguiente movimiento

---

**Momento óptimo de entrada**
SAR alcista + consenso ≥ 70% alcista + RSI entre 55–68 + histograma MACD positivo y estable o creciente + volumen creciente en el impulso + SIN divergencias bajistas. Stop bajo SMA50. Objetivo: resistencia identificada o trailing stop al 8% desde máximos.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""",
                "🔄 Rebote Técnico": """
**🔄 Rebote Técnico — Capturar el giro desde sobreventa**

Operativa de alta probabilidad estadística a corto plazo: aprovechar el retorno a la media desde condiciones de sobreventa extrema. No es inversión de tendencia — es una corrección técnica dentro de una caída. Horizonte 2–4 semanas. Disciplina de stop es crítica.

---

**Orden de análisis:**

**1. RSI** *(condición necesaria — primero esto)*
- RSI < 30: sobreventa extrema; zona estadísticamente favorable a rebote
- RSI 30–38: sobreventa moderada; señal de interés pero sin urgencia
- RSI > 40: sin sobreventa; no hay base técnica para rebote a corto plazo; NO operar
- *El RSI < 30 no significa "comprar ahora" — significa que las condiciones para un rebote están presentes. Necesitas los otros factores para confirmar.*

**2. Bollinger %B** *(extensión de la caída)*
- %B < 0.10: precio en el extremo inferior de las bandas; zona de sobreventa estadística
- %B 0.10–0.20: sobreventa moderada; consistente con RSI
- %B > 0.25: la caída no es extrema en términos de volatilidad histórica; rebote técnico menos probable
- *Las Bandas de Bollinger miden la volatilidad histórica. Un precio en la banda inferior extrema tiene alta probabilidad estadística de revertir hacia la media (SMA20).*

**3. Divergencia alcista** *(confirmación clave)*
- Divergencia alcista RSI o OBV activa: el indicador forma mínimos más altos mientras el precio forma mínimos más bajos → la presión vendedora se agota
- Sin divergencia: el rebote es posible pero sin señal de confirmación → reducir tamaño o esperar
- *La divergencia alcista transforma una zona de sobreventa en un setup de alta convicción. Sin ella, el rebote puede ocurrir pero la probabilidad es menor.*

**4. Soporte técnico reforzado** *(zona de inflexión)*
- Nivel pivot + media móvil convergiendo en la zona de caída: suelo estructural; los compradores tienen una referencia clara
- Confluencia multi-timeframe en la misma zona: mayor probabilidad de rebote
- Sin soporte identificado: el precio puede seguir cayendo sin freno; evitar
- *El soporte no garantiza el rebote, pero define el precio de invalidación del setup. Si el soporte cede, la tesis es incorrecta.*

**5. Volumen** *(patrón de agotamiento vendedor)*
- Volumen decreciente en los últimos días de caída: los vendedores se agotan; el movimiento bajista pierde fuerza
- Volumen alto en vela de giro (martillo, envolvente alcista): señal de capitulación + entrada compradora
- Volumen creciente en la caída: distribución activa; el suelo puede estar más abajo

**6. Posición relativa en rango 52W**
- < 20% del rango: zona de mínimos históricos; más probable que el mercado reconozca el precio como barato
- > 40% del rango: la caída no es estadísticamente extrema en contexto anual

---

**Momento óptimo de entrada**
RSI < 32 + %B < 0.15 + divergencia alcista OBV o RSI activa + soporte reforzado identificado + volumen decreciendo en la caída. Entrada en la zona del soporte con stop ajustado un 2–3% por debajo. Objetivo: SMA20 o SMA50 (retorno a la media). Si el soporte cede, salir sin excusas.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""",
                "🛡️ Señal de Salida": """
**🛡️ Señal de Salida — Saber cuándo termina el trade**

Detecta cuándo reducir o cerrar una posición larga existente. Los criterios son el espejo de los de entrada: sobrecompra donde antes había sobreventa, distribución donde antes había acumulación, divergencias bajistas donde antes eran alcistas. La mayoría de inversores tienen criterios de entrada pero no de salida — aquí está el análisis.

---

**Orden de análisis:**

**1. RSI** *(temperatura del precio)*
- RSI > 70: sobrecompra técnica; zona de menor retorno esperado histórico
- RSI > 75: sobrecompra extrema; el rebote bajista tiene alta probabilidad estadística
- RSI entre 60–70: zona de precaución; vigilar pero no actuar todavía
- *El RSI alto no obliga a vender, pero sí obliga a revisar el stop y no añadir posición. En tendencias fuertes, el RSI puede mantenerse sobre 70 semanas — la divergencia bajista es la señal de acción.*

**2. Divergencias bajistas** *(señal de agotamiento — la más importante)*
- Divergencia bajista RSI: precio hace máximos más altos, RSI hace máximos más bajos → compradores pierden fuerza
- Divergencia bajista MACD histograma: el impulso alcista se agota aunque el precio siga subiendo
- Divergencia bajista OBV: el dinero institucional distribuye mientras el precio sube → los grandes venden a los pequeños
- *La divergencia bajista de OBV es la más grave: indica que los inversores con información o con tamaño suficiente para mover el mercado están reduciendo posición. El precio puede aguantar días o semanas, pero el suelo se ha debilitado.*

**3. Posición en rango 52W** *(contexto de precio)*
- > 85% del rango: precio cerca de máximos históricos anuales; la asimetría riesgo/recompensa es desfavorable
- > 70%: zona de precaución; la resistencia natural de máximos anteriores es relevante
- < 60%: precio no está en zona extrema de sobrecompra; otras señales deben dominar

**4. MACD histograma** *(velocidad de deterioro)*
- Histograma positivo pero decreciendo durante 3+ sesiones: el impulso alcista frena
- Cruce a negativo con precio todavía en máximos: señal de distribución
- Histograma positivo y estable: la tendencia mantiene fuerza; no actuar solo por RSI alto

**5. SAR** *(cambio de tendencia estructural)*
- SAR pasa de alcista a bajista (precio cruza debajo del SAR): señal técnica directa de cambio de tendencia; señal de reducción o cierre
- SAR aún alcista con RSI alto: la tendencia sigue; solo vigilar

**6. OBV** *(flujo de dinero institucional)*
- OBV decreciente mientras el precio sube o se mantiene: distribución silenciosa; la señal de salida más relevante
- OBV paralelo al precio: flujo neutral; no hay distribución activa
- *El OBV distribuyendo es el equivalente del OBV acumulando en la señal de compra. El dinero institucional se mueve antes que el precio.*

---

**Momento óptimo de reducción/salida**
RSI > 70 + divergencia bajista OBV o RSI activa + histograma MACD decreciendo + posición > 75% en rango 52W. Acción: reducir 30–50% de la posición, ajustar stop al nivel de soporte más reciente y dejar correr el resto con trailing stop. Si RSI > 75 + divergencia bajista fuerte: cerrar posición completa o cubrir con opciones.

---
*Análisis educativo · No constituye asesoramiento de inversión bajo MiFID II*
""",
            }

            def _scorecard(titulo, emoji_tit, criterios, color_hdr):
                """Returns (header_html, body_html) — header has the colored bar, body has score+criteria."""
                total  = sum(p for _, p in criterios)
                maxpts = len(criterios) * 2
                pct    = int(total / maxpts * 100)
                if pct >= 70:   vrd, vrd_col = "OPORTUNIDAD", "#166534"
                elif pct >= 45: vrd, vrd_col = "VIGILAR",     "#92400e"
                else:           vrd, vrd_col = "NO ES EL MOMENTO", "#991b1b"
                vrd_bg = {"OPORTUNIDAD": "#f0fdf4", "VIGILAR": "#fffbeb", "NO ES EL MOMENTO": "#fff1f2"}[vrd]
                filas = "".join(html for html, _ in criterios)
                hdr = (f'<div style="background:{color_hdr};padding:10px 14px;'
                       f'border-radius:8px 0 0 0;border:1px solid {color_hdr};border-bottom:none">'
                       f'<span style="color:white;font-weight:700;font-size:1rem">'
                       f'{emoji_tit} {titulo}</span></div>')
                body = (f'<div style="border:1px solid #e5e7eb;border-top:none;'
                        f'border-radius:0 0 8px 8px;overflow:hidden">'
                        f'<div style="background:{vrd_bg};padding:8px 14px;'
                        f'display:flex;align-items:center;gap:10px">'
                        f'<span style="font-size:1.4rem;font-weight:800;color:{vrd_col}">{pct}</span>'
                        f'<span style="font-size:0.65rem;color:{vrd_col};font-weight:600">/100</span>'
                        f'<span style="font-size:0.82rem;font-weight:700;color:{vrd_col};margin-left:4px">{vrd}</span>'
                        f'</div>'
                        f'<div style="padding:8px 14px">{filas}</div>'
                        f'</div>')
                return hdr, body

            # ── Extraer variables ─────────────────────────────────────────
            _info    = ed["info"]
            _hist    = ed["hist"]
            _medias  = ed["medias"]
            _rsi     = ed["rsi_val"]
            _mhist   = ed["macd_hist_val"]
            _mval    = ed["macd_val"]
            _mseñal  = ed["macd_señal"]
            _divs    = ed["divergencias"]
            _niv     = ed["niveles_ref"]
            _sar     = ed["sar_tend"]
            _pctb    = ed["pct_b"]
            _cons    = ed["consenso_dir"]
            _precio  = ed["precio"]

            try: _yield   = float(_info.get("dividendYield", 0) or 0) * 100
            except: _yield = 0.0
            try: _payout  = float(_info.get("payoutRatio",   0) or 0) * 100
            except: _payout = 0.0
            try: _pe      = float(_info.get("trailingPE",    0) or 0)
            except: _pe = 0.0
            try: _beta    = float(_info.get("beta",          1) or 1)
            except: _beta = 1.0
            try: _52h     = float(_info.get("fiftyTwoWeekHigh", _precio) or _precio)
            except: _52h = _precio
            try: _52l     = float(_info.get("fiftyTwoWeekLow",  _precio) or _precio)
            except: _52l = _precio

            _sma50  = float((_medias.get(50)  or (0, 0))[0])
            _sma200 = float((_medias.get(200) or (0, 0))[0])
            _sma20  = float((_medias.get(20)  or (0, 0))[0])

            _rng52 = _52h - _52l if _52h != _52l else 1
            _pos52 = (_precio - _52l) / _rng52 * 100  # 0=mín, 100=máx

            # Volume trend (last 20 sessions)
            try:
                _vols = _hist["Volume"].squeeze().tail(20).values.astype(float)
                _x20  = _np_est.arange(len(_vols))
                _vslope = _np_est.polyfit(_x20, _vols, 1)[0] / (_vols.mean() + 1)
            except: _vslope = 0.0

            # OBV trend (last 40 sessions)
            try:
                _cl40 = _hist["Close"].squeeze().tail(40)
                _vl40 = _hist["Volume"].squeeze().tail(40)
                _obv  = (_np_est.sign(_cl40.diff()) * _vl40).fillna(0).cumsum()
                _x40  = _np_est.arange(len(_obv))
                _obvs = _np_est.polyfit(_x40, _obv.values.astype(float), 1)[0] / (abs(float(_obv.mean())) + 1)
            except: _obvs = 0.0

            _div_alc = any(d["direccion"] == "alcista" for d in _divs)
            _div_baj = any(d["direccion"] == "bajista" for d in _divs)
            _div_rsi_baj = any(d["tipo"] == "RSI"  and d["direccion"] == "bajista" for d in _divs)
            _div_mcd_baj = any(d["tipo"] == "MACD" and d["direccion"] == "bajista" for d in _divs)
            _niv_soporte = [n for n in _niv if n["tipo"] == "S"]
            _niv_resist  = [n for n in _niv if n["tipo"] == "R"]

            # ══════════════════════════════════════════════════════════════
            # SELECTOR
            # ══════════════════════════════════════════════════════════════
            _est_opciones = ["Todas", "💰 Dividendos", "📈 Swing 12-16 sem",
                             "🏷️ Valor", "🚀 Momentum", "🔄 Rebote Técnico", "🛡️ Señal de Salida"]
            _est_sel = st.radio("Mostrar estrategia:", _est_opciones,
                                horizontal=True, key="est_selector",
                                label_visibility="collapsed")

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # ══════════════════════════════════════════════════════════════
            # DEFINICIÓN DE LAS 6 ESTRATEGIAS
            # ══════════════════════════════════════════════════════════════

            # ── Helper: estado de divergencias (texto descriptivo) ───────
            def _div_txt_alc():
                tipos = [d["tipo"] for d in _divs if d["direccion"] == "alcista"]
                return f"Alcista activa — {', '.join(tipos)}" if tipos else "Sin divergencias"

            def _div_txt_baj():
                tipos = [d["tipo"] for d in _divs if d["direccion"] == "bajista"]
                return f"Bajista activa — {', '.join(tipos)}" if tipos else "Sin divergencias bajistas"

            def _div_txt():
                alc = [d["tipo"] for d in _divs if d["direccion"] == "alcista"]
                baj = [d["tipo"] for d in _divs if d["direccion"] == "bajista"]
                if alc and not baj:   return f"Alcista — {', '.join(alc)}"
                if baj and not alc:   return f"⚠️ Bajista — {', '.join(baj)}"
                if alc and baj:       return f"Mixta — alc:{','.join(alc)} baj:{','.join(baj)}"
                return "Sin divergencias detectadas"

            def _build_dividendos():
                _yield_ok = _yield > 0 and _yield < 25  # >25% = dato yfinance anómalo
                _y_show   = _yield if _yield_ok else 0
                c = []
                c.append(_criterio(2 if _y_show >= 3.5 else 1 if _y_show >= 2 else 0,
                    f"Dividend yield {_y_show:.1f}%" + (" ⚠️ dato dudoso" if not _yield_ok and _yield > 0 else ""),
                    "≥3.5% atractivo · 2-3.5% aceptable · <2% insuficiente"))
                c.append(_criterio(2 if _sma200 > 0 and _precio < _sma200 else 1 if _sma200 == 0 else 0,
                    f"Precio vs SMA200 ({_sma200:.2f})" if _sma200 else "SMA200 no disponible",
                    f"{'Bajo SMA200 — zona de valor ✅' if _sma200 > 0 and _precio < _sma200 else f'Sobre SMA200 +{(_precio/_sma200-1)*100:.1f}% — precio caro' if _sma200 > 0 else ''}"))
                c.append(_criterio(2 if _rsi < 45 else 1 if _rsi < 55 else 0,
                    f"RSI {_rsi:.0f}",
                    f"{'Zona óptima de entrada ✅' if _rsi < 45 else 'Aceptable, sin urgencia ⚠️' if _rsi < 55 else 'Precio técnicamente caro para entrada ❌'}"))
                c.append(_criterio(2 if _pos52 < 35 else 1 if _pos52 < 60 else 0,
                    f"Posición 52W: {_pos52:.0f}% del rango",
                    f"{'Zona baja — buen precio relativo ✅' if _pos52 < 35 else 'Zona media ⚠️' if _pos52 < 60 else 'Cerca de máximos anuales ❌'}"))
                c.append(_criterio(2 if _payout > 0 and _payout < 70 else 1 if _payout < 90 else 0,
                    f"Payout ratio {_payout:.0f}%" if _payout else "Payout no disponible",
                    f"{'Sostenible ✅' if _payout < 70 else 'Ajustado ⚠️' if _payout < 90 else 'Riesgo de recorte ❌'}"))
                c.append(_criterio(2 if _div_alc and not _div_baj else 1 if not _div_baj else 0,
                    "Divergencias técnicas",
                    _div_txt()))
                c.append(_criterio(2 if _niv_soporte else 1,
                    "Soporte técnico identificado",
                    "Nivel pivot+media como colchón de entrada"))
                return c

            def _build_swing():
                tend_ok  = _sma50 > 0 and _sma200 > 0 and _precio > _sma50 and _sma50 > _sma200
                tend_par = _sma50 > 0 and _precio > _sma50 and not tend_ok
                c = []
                c.append(_criterio(2 if tend_ok else 1 if tend_par else 0,
                    "Tendencia alcista alineada",
                    f"{'Precio>SMA50>SMA200 ✅' if tend_ok else 'Precio>SMA50 pero SMA50<SMA200 ⚠️' if tend_par else f'Precio bajo SMA50 ({_sma50:.2f}) ❌'}"))
                c.append(_criterio(2 if _mhist > 0 and _mval > _mseñal else 1 if _mhist > 0 else 0,
                    f"MACD histograma {_mhist:+.4f}",
                    f"{'Positivo y acelerando ✅' if _mhist > 0 and _mval > _mseñal else 'Positivo pero perdiendo fuerza ⚠️' if _mhist > 0 else 'Negativo — sin momentum ❌'}"))
                c.append(_criterio(2 if 45 <= _rsi <= 62 else 1 if 38 <= _rsi <= 68 else 0,
                    f"RSI {_rsi:.0f}",
                    f"{'Ventana ideal de entrada ✅' if 45 <= _rsi <= 62 else 'Zona aceptable ⚠️' if 38 <= _rsi <= 68 else 'Sobreextendido — esperar ❌'}"))
                c.append(_criterio(2 if _vslope > 0.001 else 1 if _vslope > -0.001 else 0,
                    "Volumen de confirmación",
                    f"{'Creciente — confirma el movimiento ✅' if _vslope > 0.001 else 'Estable ⚠️' if _vslope > -0.001 else 'Cayendo — movimiento sin convicción ❌'}"))
                c.append(_criterio(2 if _niv_soporte and _niv_resist else 1 if _niv_soporte else 0,
                    "Mapa soporte/resistencia",
                    f"{'Soporte y resistencia definidos ✅' if _niv_soporte and _niv_resist else 'Solo soporte — sin objetivo claro ⚠️' if _niv_soporte else 'Sin niveles definidos ❌'}"))
                c.append(_criterio(0 if _div_rsi_baj or _div_mcd_baj else 1 if _div_baj else 2,
                    "Estado de divergencias",
                    _div_txt_baj()))
                c.append(_criterio(2 if _cons[0] == "alcista" else 1 if _cons[0] == "neutro" else 0,
                    f"Consenso técnico: {_cons[2]}",
                    "Todos los indicadores deben apuntar al alza"))
                return c

            def _build_valor():
                c = []
                c.append(_criterio(2 if 0 < _pe < 15 else 1 if _pe < 22 else 0,
                    f"PER {_pe:.1f}x" if _pe else "PER no disponible",
                    f"{'Barato ✅' if 0 < _pe < 15 else 'Razonable ⚠️' if _pe < 22 else 'Caro ❌' if _pe else 'Sin datos'}"))
                _dist200 = (_precio / _sma200 - 1) * 100 if _sma200 > 0 else 0
                c.append(_criterio(2 if _sma200 > 0 and _precio < _sma200 * 0.97 else
                                   1 if _sma200 > 0 and _precio < _sma200 * 1.03 else 0,
                    f"vs SMA200: {_dist200:+.1f}%" if _sma200 else "SMA200 no disponible",
                    f"{'Descuento >3% ✅' if _dist200 < -3 else 'En línea ⚠️' if abs(_dist200) < 3 else 'Prima sobre media ❌'}"))
                c.append(_criterio(2 if _beta < 0.8 else 1 if _beta < 1.2 else 0,
                    f"Beta {_beta:.2f}",
                    f"{'Defensivo ✅' if _beta < 0.8 else 'Neutro ⚠️' if _beta < 1.2 else 'Especulativo ❌'}"))
                c.append(_criterio(2 if _pos52 < 40 else 1 if _pos52 < 65 else 0,
                    f"Posición 52W: {_pos52:.0f}%",
                    f"{'Zona baja ✅' if _pos52 < 40 else 'Zona media ⚠️' if _pos52 < 65 else 'Cerca de máximos ❌'}"))
                c.append(_criterio(2 if _rsi < 50 else 1 if _rsi < 60 else 0,
                    f"RSI {_rsi:.0f}",
                    f"{'Sin sobrecompra técnica ✅' if _rsi < 50 else 'Aceptable ⚠️' if _rsi < 60 else 'Técnicamente caro ❌'}"))
                c.append(_criterio(2 if _div_alc else 1 if not _div_baj else 0,
                    "Acumulación (OBV/Volumen)",
                    _div_txt_alc()))
                c.append(_criterio(2 if 0 < _yield < 25 and _yield >= 2 else 1 if _yield > 0 else 0,
                    f"Yield {_yield:.1f}%" if _yield < 25 else "Yield (dato dudoso)",
                    "El dividendo remunera la espera"))
                return c

            def _build_momentum():
                c = []
                _dist50 = (_precio / _sma50 - 1) * 100 if _sma50 > 0 else 0
                c.append(_criterio(2 if _sma50 > 0 and _precio > _sma50 * 1.02 and _sma50 > _sma200
                                   else 1 if _sma50 > 0 and _precio > _sma50 else 0,
                    f"Fuerza vs SMA50: {_dist50:+.1f}%" if _sma50 else "SMA50 no disponible",
                    f"{'≥2% sobre SMA50 en tendencia ✅' if _dist50 >= 2 and _sma50 > _sma200 else 'Sobre SMA50 pero débil ⚠️' if _dist50 > 0 else 'Bajo SMA50 ❌'}"))
                c.append(_criterio(2 if 55 <= _rsi <= 72 else 1 if 50 <= _rsi <= 75 else 0,
                    f"RSI {_rsi:.0f}",
                    f"{'Momentum activo ✅' if 55 <= _rsi <= 72 else 'Zona válida ⚠️' if 50 <= _rsi <= 75 else 'Sobrecomprado — riesgo de corrección ❌' if _rsi > 75 else 'Sin momentum ❌'}"))
                c.append(_criterio(2 if _mhist > 0 and _mval > _mseñal else 1 if _mhist > 0 else 0,
                    f"MACD {_mhist:+.4f}",
                    f"{'Acelerando ✅' if _mhist > 0 and _mval > _mseñal else 'Positivo ⚠️' if _mhist > 0 else 'Negativo ❌'}"))
                c.append(_criterio(2 if _vslope > 0.002 else 1 if _vslope > 0 else 0,
                    "Volumen",
                    f"{'Acelerado ✅' if _vslope > 0.002 else 'Creciente ⚠️' if _vslope > 0 else 'Cayendo ❌'}"))
                c.append(_criterio(2 if _sar == "alcista" else 0,
                    f"SAR Parabólico: {_sar}",
                    f"{'Por debajo del precio — tendencia activa ✅' if _sar == 'alcista' else 'Por encima del precio — tendencia rota ❌'}"))
                c.append(_criterio(0 if _div_baj else 2,
                    "Señales de distribución",
                    _div_txt_baj()))
                c.append(_criterio(2 if _cons[0] == "alcista" else 1 if _cons[0] == "neutro" else 0,
                    f"Consenso: {_cons[2]}",
                    "Indicadores alineados al alza"))
                return c

            def _build_rebote():
                c = []
                c.append(_criterio(2 if _rsi < 30 else 1 if _rsi < 38 else 0,
                    f"RSI {_rsi:.0f}",
                    f"{'Sobreventa extrema ✅' if _rsi < 30 else 'Zona de interés ⚠️' if _rsi < 38 else 'Sin sobreventa — rebote sin base ❌'}"))
                c.append(_criterio(2 if _niv_soporte else 0,
                    "Soporte técnico",
                    f"{'Nivel pivot+media activo ✅' if _niv_soporte else 'Sin soporte — rebote sin ancla ❌'}"))
                c.append(_criterio(2 if _div_alc else 1 if not _div_baj else 0,
                    "Divergencia alcista",
                    _div_txt_alc()))
                c.append(_criterio(2 if _pctb is not None and _pctb < 0.1 else
                                   1 if _pctb is not None and _pctb < 0.25 else 0,
                    f"Bollinger %B: {_pctb:.2f}" if _pctb is not None else "Bollinger %B n/d",
                    f"{'Banda inferior extrema ✅' if _pctb and _pctb < 0.1 else 'Zona baja ⚠️' if _pctb and _pctb < 0.25 else 'Fuera de zona ❌'}"))
                c.append(_criterio(2 if _vslope > 0.001 else 1 if _vslope > -0.001 else 0,
                    "Volumen en soporte",
                    f"{'Creciendo — acumulación ✅' if _vslope > 0.001 else 'Estable ⚠️' if _vslope > -0.001 else 'Cayendo ❌'}"))
                c.append(_criterio(2 if _pos52 < 25 else 1 if _pos52 < 40 else 0,
                    f"Posición 52W: {_pos52:.0f}%",
                    f"{'Zona de mínimos anuales ✅' if _pos52 < 25 else 'Zona baja ⚠️' if _pos52 < 40 else 'Lejos de mínimos ❌'}"))
                return c

            def _build_salida():
                c = []
                c.append(_criterio(2 if _rsi > 70 else 1 if _rsi > 63 else 0,
                    f"RSI {_rsi:.0f}",
                    f"{'Sobrecompra — señal de salida ✅' if _rsi > 70 else 'Zona de vigilancia ⚠️' if _rsi > 63 else 'Sin sobrecompra ❌'}"))
                c.append(_criterio(2 if _div_rsi_baj or _div_mcd_baj else 1 if _div_baj else 0,
                    "Divergencia bajista",
                    _div_txt_baj()))
                c.append(_criterio(2 if _mhist < 0 and _mval < _mseñal else 1 if _mhist < 0 else 0,
                    f"MACD {_mhist:+.4f}",
                    f"{'Negativo con cruce bajista ✅' if _mhist < 0 and _mval < _mseñal else 'Negativo ⚠️' if _mhist < 0 else 'Aún positivo ❌'}"))
                c.append(_criterio(2 if _sar == "bajista" else 0,
                    f"SAR Parabólico: {_sar}",
                    f"{'Por encima del precio — tendencia rota ✅' if _sar == 'bajista' else 'Aún alcista ❌'}"))
                c.append(_criterio(2 if _pos52 > 85 else 1 if _pos52 > 70 else 0,
                    f"Posición 52W: {_pos52:.0f}%",
                    f"{'Cerca de máximos anuales ✅' if _pos52 > 85 else 'Zona alta ⚠️' if _pos52 > 70 else 'No en zona de salida ❌'}"))
                c.append(_criterio(2 if _obvs < -0.001 else 1 if _obvs < 0.001 else 0,
                    "OBV",
                    f"{'Distribuyendo — salida institucional ✅' if _obvs < -0.001 else 'Neutro ⚠️' if _obvs < 0.001 else 'Acumulando ❌'}"))
                c.append(_criterio(2 if _cons[0] == "bajista" else 1 if _cons[0] == "neutro" else 0,
                    f"Consenso: {_cons[2]}",
                    "Indicadores virados a bajista"))
                return c

            # ── Interpretación cualitativa por estrategia ─────────────────
            def _interpretar(key):
                puntos, rec = [], ""
                if key == "💰 Dividendos":
                    _y_ok = 0 < _yield < 25
                    _yv   = _yield if _y_ok else 0
                    if not _y_ok and _yield > 0:
                        puntos.append("⚠️ El yield que muestra el proveedor de datos parece anómalo — verifica el dividendo real en la web de la empresa.")
                    if _yv >= 3.5:
                        puntos.append(f"✅ Yield del {_yv:.1f}% por encima del umbral de interés para estrategia de rentas.")
                    elif _yv > 0:
                        puntos.append(f"⚠️ Yield del {_yv:.1f}% — retorno por dividendo modesto para estrategia de rentas pura.")
                    if _sma200 > 0 and _precio > _sma200:
                        gap = (_precio / _sma200 - 1) * 100
                        puntos.append(f"❌ Precio un {gap:.1f}% sobre SMA200 — no es zona de valor. Esperar retroceso hacia {_sma200:.2f}€ mejora significativamente el yield efectivo de entrada.")
                    elif _sma200 > 0:
                        puntos.append(f"✅ Precio bajo SMA200 — compras en zona de valor histórico.")
                    if _pos52 > 70:
                        puntos.append(f"❌ Precio en el {_pos52:.0f}% del rango anual — cerca de máximos. El coste de oportunidad de esperar una corrección es bajo.")
                    if _payout > 0 and _payout < 70:
                        puntos.append(f"✅ Payout del {_payout:.0f}% — dividendo bien cubierto por beneficios.")
                    elif _payout >= 70:
                        puntos.append(f"⚠️ Payout del {_payout:.0f}% — margen de cobertura ajustado. Revisar tendencia de BPA.")
                    # Recomendación
                    _entry_yield = (_yield / (_precio / _sma200)) if _sma200 > 0 and _precio > 0 else 0
                    if _pos52 > 65 and _sma200 > 0 and _precio > _sma200:
                        _gap = (_precio / _sma200 - 1) * 100
                        rec = (f"No es el momento óptimo. Precio un {_gap:.1f}% sobre SMA200 y en zona alta del rango anual — "
                               f"el yield efectivo es el más bajo del año. Zona de espera: SMA200 ({_sma200:.2f}€) con RSI < 45. "
                               f"Si el precio retrocede ahí, el yield efectivo mejoraría aproximadamente un {_gap:.0f}%.")
                    elif _pos52 > 60 or (_sma200 > 0 and _precio > _sma200):
                        rec = (f"Zona subóptima para entrada completa. Considera una posición parcial (30-40%) ahora "
                               f"y reserva capital para promediar si el precio retrocede hacia SMA200 ({_sma200:.2f}€) o RSI baja de 45.")
                    elif _rsi < 40 and _niv_soporte and _div_alc:
                        rec = (f"Setup óptimo activo: RSI en sobreventa ({_rsi:.0f}), soporte técnico presente y divergencia alcista confirmada. "
                               f"Entrada escalonada en 2-3 tramos. Stop por debajo del soporte identificado. "
                               f"La combinación yield + precio bajo + señal técnica es el escenario de máxima asimetría.")
                    elif _rsi < 45 and _niv_soporte:
                        rec = (f"Condiciones razonables. RSI en {_rsi:.0f} con soporte técnico activo. "
                               f"Entrada parcial (50%) con stop bajo soporte. Reservar capital para mejorar precio medio "
                               f"si hay corrección adicional.")
                    else:
                        rec = ("Vigilar sin comprometer capital. Esperar que RSI baje de 45 o que el precio llegue a zona de soporte "
                               "reforzado para tener una referencia técnica clara de stop.")

                elif key == "📈 Swing 12-16 sem":
                    tend_ok = _sma50 > 0 and _sma200 > 0 and _precio > _sma50 and _sma50 > _sma200
                    if tend_ok:
                        puntos.append("✅ Estructura tendencial completa — precio sobre SMA50 sobre SMA200.")
                    else:
                        puntos.append("❌ Estructura tendencial incompleta — el swing requiere tendencia previa establecida.")
                    if 45 <= _rsi <= 62:
                        puntos.append(f"✅ RSI en {_rsi:.0f} — ventana de entrada válida sin sobrecompra.")
                    elif _rsi > 65:
                        puntos.append(f"⚠️ RSI en {_rsi:.0f} — sobreextendido. Riesgo de corrección antes del impulso siguiente.")
                    if _div_rsi_baj or _div_mcd_baj:
                        puntos.append("❌ Divergencia bajista RSI/MACD activa — setup invalidado. Esperar resolución.")
                    elif _div_alc:
                        puntos.append("✅ Divergencia alcista activa — señal de apoyo al setup.")
                    if _niv_soporte and _niv_resist:
                        puntos.append("✅ Soporte y resistencia identificados — recorrido definido.")
                    elif not _niv_soporte:
                        puntos.append("⚠️ Sin soporte técnico claro — difícil establecer stop lógico.")
                    _soporte_str = f"{_niv_soporte[0]['precio']:.4f}€" if _niv_soporte else "no identificado"
                    _resist_str  = f"{_niv_resist[0]['precio']:.4f}€" if _niv_resist else "no identificada"
                    if _div_rsi_baj or _div_mcd_baj:
                        rec = ("⛔ Setup invalidado. Divergencia bajista activa — la tendencia muestra agotamiento interno "
                               "aunque el precio no lo refleje todavía. Esperar resolución de la divergencia (3-8 sesiones) "
                               "antes de considerar entrada. Comprar ahora es perseguir el precio en el peor momento.")
                    elif tend_ok and 45 <= _rsi <= 62 and not _div_baj and _niv_soporte:
                        _recorrido = ((_niv_resist[0]["precio"] / _niv_soporte[0]["precio"] - 1) * 100) if _niv_soporte and _niv_resist else 0
                        rec = (f"Setup técnico favorable. Entrada en zona de soporte reforzado ({_soporte_str}) "
                               f"con stop 2-3% por debajo. Objetivo: resistencia identificada ({_resist_str}). "
                               f"Recorrido potencial: ~{_recorrido:.1f}%. "
                               f"RSI en {_rsi:.0f} — ventana válida sin sobreextensión.")
                    elif tend_ok and _rsi > 62:
                        rec = (f"Tendencia correcta pero RSI en {_rsi:.0f} — sobreextendido. "
                               f"Esperar retroceso a soporte ({_soporte_str}) o RSI bajo 58 para mejorar el punto de entrada "
                               f"y aumentar el ratio riesgo/beneficio.")
                    else:
                        rec = (f"Setup incompleto. {'Tendencia no establecida — ' if not tend_ok else ''}"
                               f"esperar alineación precio>SMA50>SMA200 + RSI 45-62 + soporte identificado antes de comprometer capital.")

                elif key == "🏷️ Valor":
                    if _pe > 0:
                        puntos.append(f"{'✅' if _pe < 15 else '⚠️' if _pe < 22 else '❌'} PER {_pe:.1f}x — {'precio atractivo respecto a beneficios' if _pe < 15 else 'valoración razonable' if _pe < 22 else 'precio exigente para estrategia valor'}.")
                    if _sma200 > 0:
                        d = (_precio / _sma200 - 1) * 100
                        puntos.append(f"{'✅' if d < -3 else '⚠️' if abs(d) < 3 else '❌'} Cotiza a {d:+.1f}% {'bajo' if d < 0 else 'sobre'} SMA200 — referencia de valor histórico.")
                    if _pos52 > 65:
                        puntos.append(f"⚠️ En el {_pos52:.0f}% del rango anual. Valor genuino raramente se encuentra cerca de máximos.")
                    if _div_alc:
                        puntos.append("✅ OBV/Volumen mostrando acumulación — señal de que el mercado ya reconoce el descuento.")
                    if _pe > 0 and _pe < 15 and _pos52 < 40 and (_sma200 == 0 or _precio < _sma200):
                        rec = (f"Candidato de valor claro: PER {_pe:.1f}x + precio bajo SMA200 + zona baja del rango anual. "
                               f"Profundizar en FCF, nivel de deuda y ROCE antes de entrar. "
                               f"Si los fundamentales aguantan, entrada escalonada en 3 tramos con stop bajo soporte.")
                    elif _pe > 0 and _pe < 18 and _pos52 < 55:
                        rec = (f"Candidato moderado. PER {_pe:.1f}x razonable pero el precio no está en descuento máximo. "
                               f"Revisar tendencia de BPA y FCF yield. Entrada parcial posible con stop técnico claro.")
                    elif _pe <= 0:
                        rec = ("Sin datos de PER disponibles — imposible evaluar el margen de seguridad fundamental. "
                               "Profundizar en valoración por FCF o EV/EBITDA antes de considerar la posición.")
                    else:
                        rec = (f"Precio no refleja descuento suficiente para estrategia valor: PER {_pe:.1f}x + "
                               f"posición {_pos52:.0f}% en rango anual. El margen de seguridad es insuficiente. "
                               f"Esperar corrección hacia SMA200 ({_sma200:.2f}€) o PER < 15x para tener la asimetría adecuada.")

                elif key == "🚀 Momentum":
                    _dist50 = (_precio / _sma50 - 1) * 100 if _sma50 > 0 else 0
                    if _sar == "alcista" and _cons[0] == "alcista":
                        puntos.append("✅ SAR y consenso de indicadores alineados — tendencia activa confirmada.")
                    if 55 <= _rsi <= 72:
                        puntos.append(f"✅ RSI en {_rsi:.0f} — momentum activo sin sobrecompra extrema.")
                    elif _rsi > 72:
                        puntos.append(f"⚠️ RSI en {_rsi:.0f} — sobrecomprado. Entrada ahora asume riesgo de corrección a corto plazo.")
                    if _vslope > 0.001:
                        puntos.append("✅ Volumen creciente — el impulso tiene respaldo institucional.")
                    else:
                        puntos.append("⚠️ Volumen sin aceleración — verificar si el movimiento tiene continuidad.")
                    if _div_baj:
                        puntos.append("❌ Divergencia bajista detectada — señal de agotamiento. Momentum en riesgo.")
                    _sma50_str = f"{_sma50:.4f}€" if _sma50 > 0 else "SMA50"
                    _resist_str = f"{_niv_resist[0]['precio']:.4f}€" if _niv_resist else "resistencia siguiente"
                    if _sar == "alcista" and not _div_baj and 55 <= _rsi <= 70 and _vslope > 0:
                        _dist_sma50 = ((_precio / _sma50 - 1) * 100) if _sma50 > 0 else 0
                        rec = (f"Momentum activo y limpio. Entrada válida ahora con stop bajo SMA50 ({_sma50_str}). "
                               f"El precio está un {_dist_sma50:.1f}% sobre SMA50 — {'margen razonable' if _dist_sma50 < 8 else 'algo sobreextendido; considerar esperar retroceso a SMA50'}. "
                               f"Objetivo: {_resist_str}. Trailing stop al 8% desde máximos una vez en beneficio.")
                    elif _div_baj:
                        rec = ("⛔ No entrar. Divergencia bajista activa — el momentum se agota aunque el precio aguante. "
                               "Esperar resolución. Si ya estás en posición, ajustar stop a nivel de soporte más reciente.")
                    elif _rsi > 72:
                        rec = (f"RSI en {_rsi:.0f} — sobrecomprado. No perseguir el precio en este nivel. "
                               f"Esperar retroceso a SMA50 ({_sma50_str}) o RSI < 62 para reentrar con mejor ratio riesgo/beneficio.")
                    else:
                        rec = ("Momentum sin las condiciones completas. Esperar SAR alcista + RSI 55-70 + volumen creciente "
                               "para tener la confluencia de señales que define el setup.")

                elif key == "🔄 Rebote Técnico":
                    if _rsi < 30:
                        puntos.append(f"✅ RSI en {_rsi:.0f} — sobreventa extrema. Zona estadísticamente favorable a rebote.")
                    elif _rsi < 38:
                        puntos.append(f"⚠️ RSI en {_rsi:.0f} — sobreventa moderada. Señal de interés pero sin urgencia.")
                    else:
                        puntos.append(f"❌ RSI en {_rsi:.0f} — sin sobreventa. No hay base técnica para rebote a corto.")
                    if _div_alc:
                        puntos.append("✅ Divergencia alcista activa — confirmación clave para el rebote.")
                    else:
                        puntos.append("⚠️ Sin divergencia alcista confirmada — el rebote no está señalizado por indicadores.")
                    if _pctb is not None and _pctb < 0.15:
                        puntos.append(f"✅ %B Bollinger en {_pctb:.2f} — precio en banda inferior extrema.")
                    _soporte_str = f"{_niv_soporte[0]['precio']:.4f}€" if _niv_soporte else "soporte no identificado"
                    if _rsi < 32 and _niv_soporte and _div_alc and (_pctb is None or _pctb < 0.20):
                        rec = (f"Setup de rebote técnico de alta probabilidad. "
                               f"RSI en {_rsi:.0f} + divergencia alcista activa + soporte reforzado ({_soporte_str}). "
                               f"Entrada en zona del soporte con stop 2-3% por debajo. "
                               f"Objetivo: retorno a SMA20 o SMA50 (2-4 semanas). Si el soporte cede: salir sin excusas.")
                    elif _rsi < 38 and _niv_soporte:
                        rec = (f"Condiciones parciales. RSI en {_rsi:.0f} con soporte activo pero sin divergencia alcista confirmada. "
                               f"Posición reducida (30-40%) con stop muy ajustado. Esperar vela de giro o divergencia para completar.")
                    elif _rsi < 38 and not _niv_soporte:
                        rec = (f"RSI en {_rsi:.0f} indica sobreventa pero sin soporte técnico identificado — "
                               f"no hay referencia para el stop. No operar sin saber dónde se invalida la tesis.")
                    else:
                        rec = (f"Sin condiciones de rebote: RSI en {_rsi:.0f} sin sobreventa técnica. "
                               f"Esperar RSI < 35 + soporte + divergencia alcista para tener el setup completo.")

                elif key == "🛡️ Señal de Salida":
                    if _rsi > 70:
                        puntos.append(f"✅ RSI en {_rsi:.0f} — sobrecompra técnica. Zona históricamente de menor retorno esperado.")
                    if _div_rsi_baj or _div_mcd_baj:
                        tipos = [d["tipo"] for d in _divs if d["direccion"] == "bajista"]
                        puntos.append(f"✅ Divergencia bajista en {', '.join(tipos)} — señal de agotamiento de alta fiabilidad.")
                    if _pos52 > 85:
                        puntos.append(f"⚠️ En el {_pos52:.0f}% del rango anual — precio cerca de máximos. Asimetría riesgo/recompensa desfavorable.")
                    if _obvs < -0.001:
                        puntos.append("✅ OBV distribuyendo — el dinero institucional está saliendo bajo la subida.")
                    if not puntos:
                        puntos.append("Sin señales de salida activas. La posición no muestra síntomas de agotamiento.")
                    if _div_rsi_baj or _div_mcd_baj or (_obvs < -0.001):
                        _tipos_baj = [d["tipo"] for d in _divs if d["direccion"] == "bajista"]
                        rec = (f"⚠️ Señales de distribución activas ({', '.join(_tipos_baj) if _tipos_baj else 'OBV'}). "
                               f"Acción: reducir 40-50% de la posición al precio actual. "
                               f"Ajustar stop del resto al soporte técnico más reciente. "
                               f"Si RSI supera 75 o hay cruce bajista MACD: cerrar posición completa.")
                    elif _rsi > 70 and _pos52 > 75:
                        rec = (f"RSI en {_rsi:.0f} + precio en {_pos52:.0f}% del rango anual — asimetría desfavorable. "
                               f"Sin divergencia activa todavía, pero el riesgo/recompensa no justifica añadir posición. "
                               f"Ajustar stop al soporte más reciente y vigilar el histograma MACD para señal de deterioro.")
                    else:

                        rec = ("Sin señales de salida claras. Mantener posición con stop en soporte más reciente. "
                               "Vigilar divergencia bajista OBV/RSI como primer aviso de distribución.")

                return puntos, rec

            # ══════════════════════════════════════════════════════════════
            # RENDER
            # ══════════════════════════════════════════════════════════════
            _estrategias = {
                "💰 Dividendos":      ("#15803d", _build_dividendos),
                "📈 Swing 12-16 sem": ("#1d4ed8", _build_swing),
                "🏷️ Valor":           ("#7c3aed", _build_valor),
                "🚀 Momentum":        ("#b45309", _build_momentum),
                "🔄 Rebote Técnico":  ("#0f766e", _build_rebote),
                "🛡️ Señal de Salida": ("#be123c", _build_salida),
            }

            if _est_sel == "Todas":
                _keys = list(_estrategias.keys())
                for _fila in [_keys[:3], _keys[3:]]:
                    _cols = st.columns(len(_fila))
                    for _col, _k in zip(_cols, _fila):
                        _color, _fn = _estrategias[_k]
                        with _col:
                            _t_hdr, _t_body = _scorecard(
                                _k.split(" ", 1)[-1], _k.split(" ")[0], _fn(), _color
                            )
                            _th1, _th2 = st.columns([9, 1])
                            with _th1:
                                st.markdown(_t_hdr, unsafe_allow_html=True)
                            with _th2:
                                with st.popover("ℹ️", use_container_width=True):
                                    st.markdown(_est_popover.get(_k, ""))
                            st.markdown(_t_body, unsafe_allow_html=True)
                    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            else:
                _color, _fn  = _estrategias[_est_sel]
                _nombre_limpio = _est_sel.split(" ", 1)[-1]
                _emoji_est     = _est_sel.split(" ")[0]
                _c1, _c2 = st.columns([3, 2])
                with _c1:
                    _s_hdr, _s_body = _scorecard(_nombre_limpio, _emoji_est, _fn(), _color)
                    # Header row: colored bar + ℹ️ button, both inside the card column
                    _ch1, _ch2 = st.columns([9, 1])
                    with _ch1:
                        st.markdown(_s_hdr, unsafe_allow_html=True)
                    with _ch2:
                        with st.popover("ℹ️", use_container_width=True):
                            st.markdown(_est_popover.get(_est_sel, ""))
                    st.markdown(_s_body, unsafe_allow_html=True)
                with _c2:
                    _puntos, _rec = _interpretar(_est_sel)
                    st.markdown(
                        '<div style="border:1px solid #e5e7eb;border-radius:10px;'
                        'padding:14px 16px;height:100%">',
                        unsafe_allow_html=True
                    )
                    st.markdown("**Análisis**")
                    for _p in _puntos:
                        st.markdown(
                            f'<div style="font-size:0.83rem;padding:4px 0;'
                            f'border-bottom:1px solid #f3f4f6;line-height:1.4">{_p}</div>',
                            unsafe_allow_html=True
                        )
                    if _rec:
                        st.markdown(
                            f'<div style="margin-top:12px;background:#f8fafc;'
                            f'border-radius:6px;padding:10px 12px">'
                            f'<span style="font-size:0.75rem;font-weight:700;'
                            f'color:#374151;text-transform:uppercase;letter-spacing:.05em">'
                            f'Recomendación</span>'
                            f'<div style="font-size:0.85rem;color:#111827;margin-top:4px;'
                            f'line-height:1.45">{_rec}</div></div>',
                            unsafe_allow_html=True
                        )
                    st.markdown('</div>', unsafe_allow_html=True)

            # ── Exportar informe de estrategia ────────────────────────────────────────
            st.divider()
            st.markdown("### 📥 Exportar informe de estrategia")

            # Persistir informe entre re-renders con session_state
            for _ss_key in ("est_inf_data", "est_inf_fmt", "est_inf_ts", "est_inf_file"):
                if _ss_key not in st.session_state:
                    st.session_state[_ss_key] = None

            _col_fmt_est, _col_btn_est, _col_dl_est = st.columns([1, 2, 2])
            with _col_fmt_est:
                _fmt_est = st.radio("Formato", ["HTML", "PDF"],
                                    horizontal=True, key="fmt_est_export")
            with _col_btn_est:
                if st.button("⬇️ Generar informe", type="primary",
                             key="btn_est_export"):
                    _ts_dl   = datetime.now().strftime("%Y%m%d_%H%M")
                    _keys_dl = list(_estrategias.keys()) if _est_sel == "Todas" else [_est_sel]
                    _est_dl_data = []
                    for _k_dl in _keys_dl:
                        _c_dl, _f_dl = _estrategias[_k_dl]
                        _crit_dl     = _f_dl()
                        _pts_dl, _rc_dl = _interpretar(_k_dl)
                        _est_dl_data.append({
                            "nombre":     _k_dl,
                            "color":      _c_dl,
                            "criterios":  _crit_dl,
                            "puntos":     _pts_dl,
                            "rec":        _rc_dl,
                            "popover_md": _est_popover.get(_k_dl, ""),
                        })
                    with st.spinner("Generando..."):
                        if _fmt_est == "HTML":
                            _raw = generar_informe_estrategia_html(
                                ticker      = ed["ticker"],
                                nombre      = ed["nombre"],
                                precio      = ed["precio"],
                                ts          = ed["ts"],
                                estrategias = _est_dl_data,
                            ).encode("utf-8")
                            st.session_state["est_inf_fmt"]  = "html"
                            st.session_state["est_inf_file"] = (
                                f"{ed['ticker']}_estrategia_{_ts_dl}.html"
                            )
                        else:
                            _raw = generar_pdf_estrategia(
                                ticker      = ed["ticker"],
                                nombre      = ed["nombre"],
                                precio      = ed["precio"],
                                ts          = ed["ts"],
                                estrategias = _est_dl_data,
                            )
                            st.session_state["est_inf_fmt"]  = "pdf"
                            st.session_state["est_inf_file"] = (
                                f"{ed['ticker']}_estrategia_{_ts_dl}.pdf"
                            )
                    st.session_state["est_inf_data"] = _raw
                    st.session_state["est_inf_ts"]   = _ts_dl
                    st.rerun()

            with _col_dl_est:
                if st.session_state.get("est_inf_data") is not None:
                    _dl_fmt  = st.session_state["est_inf_fmt"]
                    _dl_file = st.session_state["est_inf_file"]
                    _dl_mime = "text/html" if _dl_fmt == "html" else "application/pdf"
                    st.download_button(
                        label     = f"📄 Descargar ({_dl_fmt.upper()})",
                        data      = st.session_state["est_inf_data"],
                        file_name = _dl_file,
                        mime      = _dl_mime,
                        key       = "dl_est_informe",
                    )
            # Disclaimer
            st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
            st.markdown(
                '<p style="font-size:0.75rem;color:#9ca3af;text-align:center;'
                'border-top:1px solid #f3f4f6;padding-top:10px;margin-top:4px">'
                'An\u00e1lisis educativo y orientativo \u00b7 Las puntuaciones se calculan '
                'autom\u00e1ticamente a partir de indicadores t\u00e9cnicos y fundamentales. '
                'No constituyen asesoramiento personalizado de inversi\u00f3n en el sentido '
                'de MiFID II / RD 217/2008. Para asesoramiento personalizado, contactar '
                'con una EAF o entidad autorizada por CNMV.</p>',
                unsafe_allow_html=True
            )

    # ---- TAB ANALISIS IA (proxima version) ----
    with tab_ia:
        st.markdown("## \U0001f916 An\u00e1lisis IA")
        st.info("**Esta funcionalidad est\u00e1 en desarrollo y estar\u00e1 disponible en una versi\u00f3n pr\u00f3xima.**")

    # ---- TAB MACRO ----
    with tab_macro:
        st.markdown("## 🌍 Análisis Macro")
        st.info("**Esta funcionalidad está en desarrollo y estará disponible en una versión próxima.**")

    # ---- TAB ADMIN (solo superadmin) ----
    if tab_admin is not None:
        with tab_admin:
            st.markdown("## ⚙️ Administración de Usuarios")
            st.info("**Panel de administración disponible solo para superadministradores.**")

    # ---- TAB AYUDA ----
    with tab_ayuda:
        st.markdown("## 📖 Ayuda")
        st.info("**Sección de ayuda en construcción.**")

# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if "usuario" not in st.session_state:
    pantalla_login()
else:
    pantalla_analisis()
