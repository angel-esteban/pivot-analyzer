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
def obtener_datos(ticker: str):
    """Descarga datos OHLCV y metadatos del ticker."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", auto_adjust=True)
        info = t.info
        return hist, info
    except Exception as e:
        return None, {}


# =============================================================================
# DATOS MACRO — ECB API (sin clave) + yfinance
# =============================================================================

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
    """Euribor 12M — prueba varias claves de serie ECB hasta obtener un valor."""
    candidatos = [
        ("FM", "B.U2.EUR.RT.MM.EURIBOR12MD_.HSTA"),   # clave estándar (diaria)
        ("FM", "D.U2.EUR.RT.MM.EURIBOR12MD_.HSTA"),   # frecuencia D (diaria alt.)
        ("FM", "M.U2.EUR.RT.MM.EURIBOR12MD_.HSTA"),   # mensual
        ("FM", "B.U2.EUR.RT.MM.EURIBOR12MD.HSTA"),    # sin underscore final
        ("FM", "B.U2.EUR.4F.KR.EURIBOR12MD_.HSTA"),   # distinta clasificación
    ]
    for flow, key in candidatos:
        try:
            url = f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
            r = requests.get(url,
                             params={"lastNObservations": 1, "format": "jsondata"},
                             timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            ds = data["dataSets"][0]
            obs = (list(ds["series"].values())[0]["observations"]
                   if "series" in ds else ds["observations"])
            if not obs:
                continue
            last_key = sorted(obs.keys(), key=lambda x: int(x))[-1]
            val = obs[last_key][0]
            if val is not None:
                return float(val)
        except Exception:
            continue
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
    st.caption("Tipos e inflación: BCE Statistical Data Warehouse (actualización horaria) · "
               "Mercados: Yahoo Finance (~15 min de retraso)")

    # ── TIPOS DE INTERÉS ─────────────────────────────────────────────────────
    st.markdown("#### 📊 Tipos de Interés")
    col1, col2, col3, col4 = st.columns(4)

    with st.spinner("Cargando tipos BCE..."):
        dfr        = obtener_dato_ecb("B.U2.EUR.4F.KR.DFR.LEV")
        euribor12m = obtener_euribor_12m()
    us10y, us10y_d = obtener_precio_macro("^TNX")

    with col1:
        st.metric("BCE — DFR", f"{dfr:.2f}%" if dfr is not None else "—",
                  help="Tipo de la Facilidad de Depósito del BCE. Es el tipo de referencia de la zona euro: "
                       "condiciona el coste del dinero para bancos y, en cascada, hipotecas, bonos y valoraciones de activos.")
    with col2:
        st.metric("Euribor 12M", f"{euribor12m:.3f}%" if euribor12m is not None else "—",
                  help="Tipo al que los bancos europeos se prestan dinero a 12 meses. "
                       "Referencia directa para hipotecas variables en España.")
    with col3:
        if us10y is not None:
            st.metric("US Treasury 10Y", f"{us10y:.2f}%", delta=f"{us10y_d:+.2f}% (día)",
                      help="Rendimiento del bono soberano estadounidense a 10 años. "
                           "Tasa libre de riesgo de referencia global: cuando sube, "
                           "presiona a la baja las valoraciones de todos los activos de riesgo.")
        else:
            st.metric("US Treasury 10Y", "—")
    with col4:
        st.metric("Fed Funds", "→ fed.gov",
                  help="Tipo objetivo de la Reserva Federal. Dato actualizado en: "
                       "federalreserve.gov/releases/h15 · Se puede activar via FRED API Key.")

    # ── INFLACIÓN ────────────────────────────────────────────────────────────
    st.markdown("#### 📈 Inflación (IPC interanual — último dato disponible)")
    col5, col6, col7 = st.columns(3)

    with st.spinner("Cargando inflación BCE..."):
        hicp_eu = obtener_dato_ecb("M.U2.N.000000.4.ANR", "ICP")
        hicp_es = obtener_dato_ecb("M.ES.N.000000.4.ANR", "ICP")

    with col5:
        if hicp_eu is not None:
            semaforo = "🔴" if hicp_eu > 3 else ("🟡" if hicp_eu > 2 else "🟢")
            st.metric(f"IPC Eurozona {semaforo}", f"{hicp_eu:.1f}%",
                      help="HICP (Índice Armonizado de Precios al Consumo) de la zona euro en tasa interanual. "
                           "Objetivo BCE: ~2%. 🟢 ≤2% | 🟡 2-3% | 🔴 >3%")
        else:
            st.metric("IPC Eurozona", "—")
    with col6:
        if hicp_es is not None:
            semaforo = "🔴" if hicp_es > 3 else ("🟡" if hicp_es > 2 else "🟢")
            st.metric(f"IPC España {semaforo}", f"{hicp_es:.1f}%",
                      help="HICP de España en tasa interanual (INE/BCE). "
                           "Divergencias respecto a la media europea afectan la competitividad real española.")
        else:
            st.metric("IPC España", "—")
    with col7:
        st.metric("IPC EEUU", "→ FRED",
                  help="CPI EEUU actualizado en: fred.stlouisfed.org/series/CPIAUCSL "
                       "Se puede activar via FRED API Key en la configuración.")

    st.divider()

    # ── DIVISAS ──────────────────────────────────────────────────────────────
    st.markdown("#### 💱 Divisas (base EUR)")
    tickers_fx = {
        "EUR/USD": ("EURUSD=X",
                    "Cruce euro/dólar. Para el inversor español: afecta el retorno de activos en USD "
                    "sin cobertura de divisa. Por encima de 1.10 el USD está débil; por debajo de 1.05, fuerte."),
        "EUR/GBP": ("EURGBP=X",
                    "Cruce euro/libra esterlina. Referencia para exposición al mercado británico (FTSE 100, gilts)."),
        "EUR/JPY": ("EURJPY=X",
                    "Cruce euro/yen. El yen es divisa refugio: su debilidad sostenida indica apetito por el riesgo global."),
        "EUR/CHF": ("EURCHF=X",
                    "Cruce euro/franco suizo. El CHF también es refugio: cercano a 1.0 indica tensión en Europa."),
    }
    cols_fx = st.columns(4)
    for i, (nombre, (tkr, tooltip)) in enumerate(tickers_fx.items()):
        precio, delta = obtener_precio_macro(tkr)
        with cols_fx[i]:
            if precio is not None:
                st.metric(nombre, f"{precio:.4f}", delta=f"{delta:+.2f}%", help=tooltip)
            else:
                st.metric(nombre, "—", help=tooltip)

    # ── COMMODITIES ──────────────────────────────────────────────────────────
    st.markdown("#### 🛢️ Commodities")
    tickers_comm = {
        "Oro (USD/oz)":      ("GC=F",
                              "Precio del oro en futuros continuos (USD por onza troy). "
                              "Activo refugio por excelencia: sube en entornos de incertidumbre, "
                              "dólar débil e inflación elevada."),
        "Brent (USD/b)":     ("BZ=F",
                              "Petróleo Brent en futuros (USD por barril). Referencia europea del crudo: "
                              "componente directo de la inflación via energía y transporte."),
        "WTI (USD/b)":       ("CL=F",
                              "West Texas Intermediate, referencia estadounidense del crudo. "
                              "Normalmente cotiza con ligero descuento frente al Brent."),
        "Gas Natural (USD)": ("NG=F",
                              "Gas Natural Henry Hub (USD/MMBTU). Correlación con precios energéticos "
                              "europeos especialmente alta desde el shock 2021-22."),
    }
    cols_comm = st.columns(4)
    for i, (nombre, (tkr, tooltip)) in enumerate(tickers_comm.items()):
        precio, delta = obtener_precio_macro(tkr)
        with cols_comm[i]:
            if precio is not None:
                st.metric(nombre, f"{precio:.2f}", delta=f"{delta:+.2f}%", help=tooltip)
            else:
                st.metric(nombre, "—", help=tooltip)

    st.divider()

    # ── ÍNDICES Y VOLATILIDAD ────────────────────────────────────────────────
    st.markdown("#### 📉 Índices Bursátiles y Volatilidad")
    tickers_idx = [
        ("VIX",          "^VIX",
         "Volatilidad implícita del S&P 500 (CBOE). >30: pánico. 15-30: cautela. <15: complacencia. "
         "El VIX por encima de 25 históricamente coincide con correcciones del 10%+ en S&P 500."),
        ("S&P 500",      "^GSPC",
         "Índice de las 500 mayores empresas de EEUU. Referencia global de renta variable. "
         "Concentración actual en tecnología megacap sin precedente histórico cercano al Nifty Fifty de 1972."),
        ("Nasdaq 100",   "^NDX",
         "Las 100 mayores no-financieras del Nasdaq. Domina tecnología y growth: "
         "muy sensible a variaciones en tipos de interés reales (duración larga implícita)."),
        ("IBEX 35",      "^IBEX",
         "Índice de referencia de la bolsa española. Fuerte peso bancario (~30%) y utilities. "
         "Correlaciona con ciclo europeo y con la prima de riesgo periférica España-Alemania."),
        ("DAX 40",       "^GDAXI",
         "Índice de referencia alemán. Exportador puro: muy sensible al ciclo global, "
         "especialmente a China y la demanda manufacturera mundial."),
        ("Eurostoxx 50", "^STOXX50E",
         "Las 50 mayores empresas de la eurozona. Referencia de renta variable europea: "
         "base de la mayoría de ETFs UCITS de RV Europa accesibles desde España."),
    ]
    cols_idx = st.columns(3)
    for i, (nombre, tkr, tooltip) in enumerate(tickers_idx):
        precio, delta = obtener_precio_macro(tkr)
        with cols_idx[i % 3]:
            if precio is not None:
                fmt = f"{precio:,.2f}"
                st.metric(nombre, fmt, delta=f"{delta:+.2f}%", help=tooltip)
            else:
                st.metric(nombre, "—", help=tooltip)

    st.markdown("---")
    st.caption("**Fuentes:** BCE Statistical Data Warehouse (tipos e inflación, sin API key) · "
               "Yahoo Finance (mercados, FX, commodities, índices) · "
               "Análisis educativo — no constituye asesoramiento de inversión (MiFID II).")


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
                          tolerancia: float = 0.20) -> str:
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
.two-col  { display:grid; grid-template-columns:3fr 2fr; gap:20px; }
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
.fund-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
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
    ind_html = (
        _ind("RSI 14", f"{rsi_val:.1f}", rsi_sub) +
        _ind("MACD", f"{macd_val:.4f}", f"Hist: {macd_hist_val:+.4f}") +
        _ind("SAR", sar_tend, f"{sar_val:.4f}") +
        _ind("Bollinger %B", f"{pct_b:.1f}%")
    )
    for p_m in [20, 50, 200]:
        if p_m in medias:
            sma, ema = medias[p_m]
            diff = precio - sma
            ind_html += (
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

        # Pivots + Confluencias
        f'<div class="card two-col">\n'
        f'<div>\n<h2>&#128208; Pivot Points &#8212; {sistema}</h2>\n{pivot_blocks}</div>\n'
        f'<div>\n<h2>&#127919; Confluencias Multi-Timeframe</h2>\n{conf_html}</div>\n'
        f'</div>\n'

        # Indicadores + Volumen
        f'<div class="card two-col">\n'
        f'<div>\n<h2>&#128200; Indicadores T&#233;cnicos</h2>\n'
        f'<div class="ind-grid">{ind_html}</div>\n</div>\n'
        f'<div>\n<h2>&#128202; Volumen</h2>\n{vol_html}\n</div>\n'
        f'</div>\n'

        # Fundamentales
        f'{fund_section}\n'

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
# GENERACIÓN DE PDF
# =============================================================================

def generar_pdf(ticker: str, precio: float, sistema: str, resultados_pivots: dict,
                confluencias: list, semaforo: str, factores_semaforo: list,
                vol_data: dict, indicadores: dict, fundamentales: dict,
                nombre: str = "", tipo_activo: str = "", cambio: float = 0.0,
                cambio_pct: float = 0.0, h52=None, l52=None, currency: str = "",
                pct_semaforo: float = 0.0):
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
        if st.button("Salir", key="logout"):
            del st.session_state["usuario"]
            st.rerun()

    # Navegación
    tabs_list = ["📈 Análisis", "🌍 Macro"]
    if es_superadmin:
        tabs_list.append("⚙️ Usuarios")
    tabs_list.append("📖 Ayuda")

    tab_objs = st.tabs(tabs_list)
    tab_analisis = tab_objs[0]
    tab_macro    = tab_objs[1]

    if es_superadmin and len(tab_objs) >= 4:
        tab_admin = tab_objs[2]
        tab_ayuda = tab_objs[3]
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
            st.metric("Precio", f"{precio:.4f}", delta=var_str, help=TOOLTIPS["Precio"])
        with col_p2:
            h52 = info.get("fiftyTwoWeekHigh")
            l52 = info.get("fiftyTwoWeekLow")
            st.metric("52W Máx / Mín", f"{h52:.2f} / {l52:.2f}" if h52 and l52 else "—", help=TOOLTIPS["52W Máx / Mín"])
        with col_p3:
            vol_hoy = float(hist["Volume"].iloc[-1])
            st.metric("Volumen hoy", _fmt_numero(vol_hoy), help=TOOLTIPS["Volumen hoy"])
        with col_p4:
            currency = info.get("currency", "")
            st.metric("Moneda", currency if currency else "—", help=TOOLTIPS["Moneda"])

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
                    f'<div style="font-size:0.75rem;color:var(--text-color,#888);'
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
            st.markdown("### Pivot Points — " + sistema_activo)
            for tf in TIMEFRAMES:
                render_tabla_pivots(tf, resultados_pivots.get(tf), precio)

        with col_conf:
            if confluencias:
                st.markdown("### Confluencias Multi-Timeframe")
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
                st.markdown("### Confluencias")
                st.caption(f"Sin confluencias dentro de ±{tol_activa:.2f}€")

        st.divider()

        # ── Bloque 3: Indicadores Técnicos (izq) | Volumen (der) ─────────
        col_ind, col_vol = st.columns([3, 2])

        with col_ind:
            st.markdown("### Indicadores Técnicos")
            col_i1, col_i2, col_i3 = st.columns(3)
            with col_i1:
                st.metric("RSI 14", rsi_val,
                          delta="Sobrecomprado" if rsi_val > 70 else (
                              "Sobrevendido" if rsi_val < 30 else "Neutro"),
                          help=TOOLTIPS["RSI 14"])
                st.metric("MACD", f"{macd_val:.4f}",
                          delta=f"Hist: {macd_hist_val:.4f}", help=TOOLTIPS["MACD"])
            with col_i2:
                st.metric("SAR", sar_tend, delta=f"{sar_val:.4f}", help=TOOLTIPS["SAR"])
                st.metric("Bollinger %B", f"{pct_b:.1f}%", help=TOOLTIPS["Bollinger %B"])
            with col_i3:
                for p_m in [20, 50]:
                    if p_m in medias:
                        sma, ema = medias[p_m]
                        diff = precio - sma
                        st.metric(f"SMA {p_m}", f"{sma:.4f}",
                                  delta=f"{diff:+.4f} ({diff/sma*100:+.1f}%)",
                                  help=TOOLTIPS.get(f"SMA {p_m}"))

        with col_vol:
            if vol_data:
                st.markdown("### Volumen")
                col_v1, col_v2 = st.columns(2)
                with col_v1:
                    st.metric("Ratio vs 10d",
                              f"{vol_data['ratio_10d']:.0f}%",
                              delta=vol_data['clasificacion_10d'],
                              help=TOOLTIPS["Ratio vs 10d"])
                with col_v2:
                    st.metric("Ratio vs 3m",
                              f"{vol_data['ratio_3m']:.0f}%",
                              delta=vol_data['clasificacion_3m'],
                              help=TOOLTIPS["Ratio vs 3m"])
                st.caption(
                    f"Vol. hoy: {_fmt_numero(vol_data['volumen'])} | "
                    f"Media 10d: {_fmt_numero(vol_data['media_10d'])} | "
                    f"Media 3m: {_fmt_numero(vol_data['media_3m'])}")

        # Imagen adjunta
        if img_upload:
            st.divider()
            st.markdown("### 📷 Captura adjunta")
            st.image(img_upload, use_column_width=True)

        st.divider()

        # ── Bloque 4: Datos Fundamentales ────────────────────────────────
        if fundamentales:
            st.markdown("### Datos Fundamentales")
            fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
            cols_f = st.columns(3)
            for i, (k, v) in enumerate(fund_items):
                with cols_f[i % 3]:
                    st.metric(k, v, help=TOOLTIPS.get(k))

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
                        )
                    st.download_button(
                        label="📄 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"{ticker_activo}_{ts}.pdf",
                        mime="application/pdf",
                        key="dl_pdf",
                    )

    # ---- TAB MACRO ----
    with tab_macro:
        pestaña_macro()

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
