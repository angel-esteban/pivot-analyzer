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
    "🇯🇵 Renta Variable Japón": {
        "iShares Core MSCI Japan IMI (Acc) — IJPA":  "IJPA.AS",
        "Vanguard FTSE Japan (Acc) — VJPN":          "VJPN.AS",
        "Xtrackers MSCI Japan (Acc) — XMJP":         "XMJP.DE",
    },
    "🏠 REITs / Inmobiliario": {
        "iShares European Property Yield (Dist) — IPRP": "IPRP.AS",
        "iShares Developed Mkts Property Yield — IWDP":  "IWDP.AS",
        "Xtrackers FTSE EPRA NAREIT Dev. Eur — XREA":    "XREA.DE",
    },
    "📦 Materias Primas / Commodities": {
        "iShares Diversified Commodity Swap (Acc) — CMOD": "CMOD.L",
        "Invesco Physical Gold ETC — SGLD":                "SGLD.L",
        "WisdomTree Physical Gold — PHAU":                 "PHAU.L",
        "iShares Physical Silver ETC — SSLN":              "SSLN.L",
    },
    "💵 Mercado Monetario": {
        "Xtrackers EUR Overnight Rate Swap — XEON":       "XEON.DE",
        "Amundi Euro Liquidity Short Term — CSH2":         "CSH2.PA",
    },
    "📊 Small & Mid Caps": {
        "iShares MSCI World Small Cap (Acc) — IUSN":      "IUSN.DE",
        "SPDR MSCI Europe Small Cap (Acc) — ZPRX":        "ZPRX.DE",
        "iShares MSCI USA Small Cap (Acc) — RUSS":        "RUSS.L",
    },
}



# Metadatos estáticos por ticker — TER, política de distribución, índice replicado
# [VERIFICAR] TER puede actualizarse cuando la gestora lo modifica (infrecuente)
ETFS_META = {
    # Renta Variable Global
    "IWDA.AS": {"ter": 0.20, "dist": "Acumulación", "indice": "MSCI World"},
    "VWRL.AS": {"ter": 0.22, "dist": "Distribución", "indice": "FTSE All-World"},
    "VWCE.DE": {"ter": 0.22, "dist": "Acumulación", "indice": "FTSE All-World"},
    "XDWD.DE": {"ter": 0.19, "dist": "Acumulación", "indice": "MSCI World"},
    "PRNA.PA": {"ter": 0.05, "dist": "Acumulación", "indice": "Solactive GBS Global Markets Large & Mid Cap"},
    "IUSQ.DE": {"ter": 0.20, "dist": "Acumulación", "indice": "MSCI ACWI"},
    # Renta Variable EEUU
    "SXR8.DE": {"ter": 0.07, "dist": "Acumulación", "indice": "S&P 500"},
    "VUSA.AS": {"ter": 0.07, "dist": "Distribución", "indice": "S&P 500"},
    "IUSA.AS": {"ter": 0.07, "dist": "Distribución", "indice": "S&P 500"},
    "SPYL.DE": {"ter": 0.03, "dist": "Acumulación", "indice": "S&P 500"},
    "CNDX.L":  {"ter": 0.33, "dist": "Acumulación", "indice": "Nasdaq 100"},
    "XNAS.DE": {"ter": 0.20, "dist": "Acumulación", "indice": "Nasdaq 100"},
    # Renta Variable Europa
    "CS51.DE": {"ter": 0.10, "dist": "Acumulación", "indice": "Euro Stoxx 50"},
    "EXSA.DE": {"ter": 0.20, "dist": "Acumulación", "indice": "STOXX Europe 600"},
    "VEUR.AS": {"ter": 0.12, "dist": "Acumulación", "indice": "FTSE Developed Europe"},
    "SPEU.DE": {"ter": 0.12, "dist": "Acumulación", "indice": "MSCI Europe"},
    "CE9.PA":  {"ter": 0.15, "dist": "Acumulación", "indice": "MSCI Europe"},
    # Renta Variable Emergentes
    "IS3N.DE": {"ter": 0.18, "dist": "Acumulación", "indice": "MSCI EM IMI"},
    "VFEM.AS": {"ter": 0.22, "dist": "Acumulación", "indice": "FTSE Emerging Markets"},
    "PAEM.PA": {"ter": 0.20, "dist": "Acumulación", "indice": "MSCI Emerging Markets"},
    "CNYA.L":  {"ter": 0.40, "dist": "Acumulación", "indice": "MSCI China"},
    # Renta Fija
    "IEGA.AS": {"ter": 0.09, "dist": "Acumulación", "indice": "Bloomberg Euro Govt Bond"},
    "IEAC.AS": {"ter": 0.20, "dist": "Acumulación", "indice": "Bloomberg Euro Corporate Bond"},
    "VETY.AS": {"ter": 0.07, "dist": "Distribución", "indice": "Bloomberg Euro Govt Float Adj"},
    "EAGA.PA": {"ter": 0.14, "dist": "Acumulación", "indice": "Bloomberg Euro Aggregate"},
    "IBTM.L":  {"ter": 0.10, "dist": "Acumulación", "indice": "ICE US Treasury 7-10Y EUR Hdg"},
    "GHYS.L":  {"ter": 0.50, "dist": "Distribución", "indice": "Markit iBoxx Global HY EUR Hdg"},
    # Sectoriales / Temáticos
    "IQQH.DE": {"ter": 0.65, "dist": "Acumulación", "indice": "S&P Global Clean Energy"},
    "2B76.DE": {"ter": 0.40, "dist": "Acumulación", "indice": "STOXX® Global Automation & Robotics"},
    "SEMI.L":  {"ter": 0.50, "dist": "Acumulación", "indice": "Solactive Global Semiconductor"},
    "HEAL.L":  {"ter": 0.40, "dist": "Acumulación", "indice": "STOXX® Global Digital Security"},
    "IESW.DE": {"ter": 0.20, "dist": "Acumulación", "indice": "MSCI World ESG Enhanced Focus"},
    "EQQQ.L":  {"ter": 0.30, "dist": "Distribución", "indice": "Nasdaq 100"},
    "WBAT.L":  {"ter": 0.40, "dist": "Acumulación", "indice": "WisdomTree Battery Solutions"},
    "IGLN.L":  {"ter": 0.12, "dist": "Acumulación", "indice": "LBMA Gold Price PM"},
    # Renta Variable Japón
    "IJPA.AS": {"ter": 0.12, "dist": "Acumulación", "indice": "MSCI Japan IMI"},
    "VJPN.AS": {"ter": 0.15, "dist": "Acumulación", "indice": "FTSE Japan"},
    "XMJP.DE": {"ter": 0.09, "dist": "Acumulación", "indice": "MSCI Japan"},
    # REITs / Inmobiliario
    "IPRP.AS": {"ter": 0.40, "dist": "Distribución", "indice": "FTSE EPRA/NAREIT Europe Dividend+"},
    "IWDP.AS": {"ter": 0.59, "dist": "Distribución", "indice": "FTSE EPRA/NAREIT Developed"},
    "XREA.DE": {"ter": 0.33, "dist": "Acumulación", "indice": "FTSE EPRA/NAREIT Developed Europe"},
    # Materias Primas / Commodities
    "CMOD.L":  {"ter": 0.19, "dist": "Acumulación", "indice": "Bloomberg Commodity ex Agri & Livestock Capped"},
    "SGLD.L":  {"ter": 0.12, "dist": "Acumulación", "indice": "LBMA Gold Price PM"},
    "PHAU.L":  {"ter": 0.39, "dist": "Acumulación", "indice": "LBMA Gold Price PM"},
    "SSLN.L":  {"ter": 0.20, "dist": "Acumulación", "indice": "LBMA Silver Price"},
    # Mercado Monetario
    "XEON.DE": {"ter": 0.10, "dist": "Acumulación", "indice": "Solactive EUR Daily Overnight Rate"},
    "CSH2.PA": {"ter": 0.07, "dist": "Acumulación", "indice": "ICE BofA Euro Government Bill"},
    # Small & Mid Caps
    "IUSN.DE": {"ter": 0.35, "dist": "Acumulación", "indice": "MSCI World Small Cap"},
    "ZPRX.DE": {"ter": 0.30, "dist": "Acumulación", "indice": "MSCI Europe Small Cap"},
    "RUSS.L":  {"ter": 0.43, "dist": "Acumulación", "indice": "MSCI USA Small Cap"},
}

# Lookup inverso: ticker → categoría
_ETFS_CATEGORIA = {
    ticker: cat
    for cat, etfs in ETFS_UCITS.items()
    for ticker in etfs.values()
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
# FUNCIONES DE ALERTAS DE PRECIO (PostgreSQL)
# =============================================================================

def inicializar_tabla_alertas():
    """Crea la tabla alertas_precio si no existe (idempotente)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alertas_precio (
                    id          SERIAL PRIMARY KEY,
                    usuario_id  INTEGER NOT NULL,
                    ticker      VARCHAR(20) NOT NULL,
                    nombre      VARCHAR(100),
                    nivel       NUMERIC(18,6) NOT NULL,
                    condicion   VARCHAR(10) NOT NULL CHECK (condicion IN ('above','below')),
                    descripcion TEXT,
                    activa      BOOLEAN DEFAULT TRUE,
                    disparada   BOOLEAN DEFAULT FALSE,
                    creada_en   TIMESTAMP DEFAULT NOW(),
                    disparada_en TIMESTAMP
                )
            """)
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def crear_alerta_precio(usuario_id: int, ticker: str, nombre: str,
                        nivel: float, condicion: str, descripcion: str = "") -> bool:
    """Crea una alerta de precio para un usuario. Devuelve True si ok."""
    try:
        db_insert("alertas_precio", {
            "usuario_id":  usuario_id,
            "ticker":      ticker.upper().strip(),
            "nombre":      nombre or ticker,
            "nivel":       nivel,
            "condicion":   condicion,
            "descripcion": descripcion or "",
            "activa":      True,
            "disparada":   False,
        })
        return True
    except Exception:
        return False


def obtener_alertas_usuario(usuario_id: int, solo_activas: bool = True) -> list:
    """Devuelve las alertas de un usuario, opcionalmente solo las activas."""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=__import__("psycopg2").extras.RealDictCursor) as cur:
                if solo_activas:
                    cur.execute(
                        "SELECT * FROM alertas_precio WHERE usuario_id=%s AND activa=TRUE ORDER BY creada_en DESC",
                        [usuario_id]
                    )
                else:
                    cur.execute(
                        "SELECT * FROM alertas_precio WHERE usuario_id=%s ORDER BY creada_en DESC",
                        [usuario_id]
                    )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def desactivar_alerta(alerta_id: int) -> bool:
    """Desactiva (borra lógicamente) una alerta por ID."""
    try:
        db_update("alertas_precio", {"activa": False}, "id", alerta_id)
        return True
    except Exception:
        return False


def verificar_y_disparar_alertas(usuario_id: int, ticker: str, precio: float) -> list:
    """
    Comprueba alertas activas del usuario para el ticker dado.
    Dispara (marca como disparada) las que se han cumplido y las devuelve.
    """
    disparadas = []
    try:
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=__import__("psycopg2").extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT * FROM alertas_precio
                       WHERE usuario_id=%s AND ticker=%s AND activa=TRUE AND disparada=FALSE""",
                    [usuario_id, ticker.upper().strip()]
                )
                alertas = [dict(r) for r in cur.fetchall()]
            for al in alertas:
                nivel = float(al["nivel"])
                cond  = al["condicion"]
                cumplida = (cond == "above" and precio >= nivel) or (cond == "below" and precio <= nivel)
                if cumplida:
                    with conn.cursor() as cur2:
                        cur2.execute(
                            "UPDATE alertas_precio SET disparada=TRUE, disparada_en=NOW(), activa=FALSE WHERE id=%s",
                            [al["id"]]
                        )
                    conn.commit()
                    disparadas.append(al)
        finally:
            conn.close()
    except Exception:
        pass
    return disparadas


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



def analizar_rsi(hist, precio: float, nombre: str) -> "dict | None":
    """
    Analiza el RSI de 14 períodos: zona, tendencia y divergencia precio-RSI.

    Escenarios: sobrecompra_extrema, sobrecompra, zona_alcista, zona_neutra,
                zona_bajista, sobreventa, sobreventa_extrema.
    """
    if hist is None or len(hist) < 20:
        return None

    cierre  = hist["Close"]
    delta   = cierre.diff()
    ganancia = delta.clip(lower=0).rolling(14).mean()
    perdida  = (-delta.clip(upper=0)).rolling(14).mean()
    rs       = ganancia / perdida.replace(0, float("nan"))
    rsi_serie = 100 - (100 / (1 + rs))
    rsi_clean = rsi_serie.dropna()

    if len(rsi_clean) < 6:
        return None

    rsi_val    = float(rsi_clean.iloc[-1])
    rsi_5ago   = float(rsi_clean.iloc[-6])
    trend_diff = rsi_val - rsi_5ago

    # ── Zona ─────────────────────────────────────────────────────────
    if rsi_val >= 80:
        escenario = "sobrecompra_extrema"
    elif rsi_val >= 70:
        escenario = "sobrecompra"
    elif rsi_val >= 55:
        escenario = "zona_alcista"
    elif rsi_val >= 45:
        escenario = "zona_neutra"
    elif rsi_val >= 30:
        escenario = "zona_bajista"
    elif rsi_val >= 20:
        escenario = "sobreventa"
    else:
        escenario = "sobreventa_extrema"

    # ── Tendencia del RSI (últimas 5 sesiones) ───────────────────────
    if trend_diff > 3:
        tendencia = "subiendo"
    elif trend_diff < -3:
        tendencia = "bajando"
    else:
        tendencia = "lateral"

    # ── Divergencia precio-RSI (ventana 20 sesiones) ─────────────────
    divergencia = None
    if len(rsi_clean) >= 20 and len(cierre) >= 20:
        precio_v = cierre.tail(20)
        rsi_v    = rsi_clean.tail(20)
        p_last, p_max, p_min = float(precio_v.iloc[-1]), float(precio_v.max()), float(precio_v.min())
        r_last, r_max, r_min = float(rsi_v.iloc[-1]), float(rsi_v.max()), float(rsi_v.min())
        # Divergencia bajista: precio en máximos pero RSI claramente por debajo de su máximo
        if p_last >= p_max * 0.99 and r_last < r_max - 8:
            divergencia = "bajista"
        # Divergencia alcista: precio en mínimos pero RSI claramente por encima de su mínimo
        elif p_last <= p_min * 1.01 and r_last > r_min + 8:
            divergencia = "alcista"

    # ── Narrativa ────────────────────────────────────────────────────
    nombre_c = nombre.split(" ")[0] if " " in nombre else nombre
    tend_str = {"subiendo": "con momentum creciente", "bajando": "con momentum decreciente",
                "lateral": "sin cambio de momentum significativo"}.get(tendencia, "")
    rsi_str  = f"{rsi_val:.1f}"

    div_txt = ""
    if divergencia == "bajista":
        div_txt = (
            f" ⚠️ Divergencia bajista detectada: el precio alcanza nuevos máximos "
            f"pero el RSI no confirma — señal clásica de debilitamiento del impulso."
        )
    elif divergencia == "alcista":
        div_txt = (
            f" 💡 Divergencia alcista detectada: el precio marca nuevos mínimos "
            f"pero el RSI no los acompaña — posible agotamiento de la presión vendedora."
        )

    if escenario == "sobrecompra_extrema":
        texto = (
            f"{nombre_c} presenta un RSI de {rsi_str}, en zona de sobrecompra extrema (>80) "
            f"{tend_str}. Históricamente, lecturas por encima de 80 señalan un activo "
            f"muy extendido en el corto plazo — no implican inversión inmediata, pero sí "
            f"que el margen de seguridad técnico es reducido.{div_txt}"
        )
    elif escenario == "sobrecompra":
        texto = (
            f"{nombre_c} cotiza con RSI {rsi_str} en zona de sobrecompra clásica (70-80) "
            f"{tend_str}. La zona 70-80 no es señal de venta automática — en tendencias "
            f"alcistas fuertes el RSI puede permanecer semanas en sobrecompra. "
            f"El nivel a vigilar es la pérdida del 70.{div_txt}"
        )
    elif escenario == "zona_alcista":
        texto = (
            f"{nombre_c} tiene un RSI de {rsi_str} en la zona alcista (55-70) "
            f"{tend_str}. Zona de momentum positivo: el precio opera con mayor presión "
            f"compradora que vendedora. En tendencias alcistas, el RSI suele "
            f"oscilar entre 40 y 80 sin entrar en zona de sobreventa.{div_txt}"
        )
    elif escenario == "zona_neutra":
        texto = (
            f"{nombre_c} presenta RSI {rsi_str} en zona neutra (45-55) "
            f"{tend_str}. El momentum no marca dirección clara — compradores y vendedores "
            f"en equilibrio. La ruptura del nivel 50 con convicción suele anticipar "
            f"el siguiente movimiento direccional.{div_txt}"
        )
    elif escenario == "zona_bajista":
        texto = (
            f"{nombre_c} cotiza con RSI {rsi_str} en zona bajista (30-45) "
            f"{tend_str}. Mayor presión vendedora que compradora. En tendencias bajistas, "
            f"el RSI suele oscilar entre 20 y 60 sin llegar a sobrecompra — "
            f"la zona 40-45 actúa frecuentemente como resistencia del RSI.{div_txt}"
        )
    elif escenario == "sobreventa":
        texto = (
            f"{nombre_c} presenta un RSI de {rsi_str} en zona de sobreventa (20-30) "
            f"{tend_str}. El activo cotiza con presión vendedora extrema. "
            f"Las lecturas en sobreventa pueden indicar oportunidad de rebote, "
            f"pero en tendencias bajistas fuertes el RSI puede permanecer deprimido. "
            f"Esperar confirmación de giro antes de actuar.{div_txt}"
        )
    else:  # sobreventa_extrema
        texto = (
            f"{nombre_c} tiene un RSI de {rsi_str} en sobreventa extrema (<20) "
            f"{tend_str}. Lecturas tan bajas son estadísticamente infrecuentes "
            f"y suelen corresponder a movimientos de capitulación. "
            f"Alta asimetría riesgo/recompensa potencial, pero la capitulación puede "
            f"prolongarse. Niveles de suporte estructural como referencia de entrada.{div_txt}"
        )

    return {
        "rsi_val":    rsi_val,
        "tendencia":  tendencia,
        "trend_diff": trend_diff,
        "divergencia": divergencia,
        "escenario":  escenario,
        "texto":      texto,
    }



def analizar_volumen(hist, nombre: str) -> "dict | None":
    """
    Analiza el volumen relativo y la señal de acumulación/distribución.

    Volumen relativo: media 5 sesiones vs media 20 sesiones.
    Acumulación/Distribución: compara volumen en días alcistas vs bajistas
    en la ventana de las últimas 10 sesiones (señal simplificada de OBV).

    Escenarios: volumen_excepcional, volumen_alto, volumen_normal,
                volumen_bajo, volumen_seco.
    """
    if hist is None or len(hist) < 22:
        return None

    vol = hist["Volume"]
    if vol.sum() == 0:
        return None

    cierre = hist["Close"]

    vol_5d  = float(vol.tail(5).mean())
    vol_20d = float(vol.tail(20).mean())

    if vol_20d == 0:
        return None

    vol_rel = vol_5d / vol_20d * 100        # 100 % = igual a la media 20d

    # ── Escenario de volumen ──────────────────────────────────────────
    if vol_rel >= 200:
        escenario = "volumen_excepcional"
    elif vol_rel >= 150:
        escenario = "volumen_alto"
    elif vol_rel >= 80:
        escenario = "volumen_normal"
    elif vol_rel >= 50:
        escenario = "volumen_bajo"
    else:
        escenario = "volumen_seco"

    # ── Señal acumulación / distribución (últimas 10 sesiones) ───────
    ventana = hist.tail(10)
    diff_c  = ventana["Close"].diff().fillna(0)
    vol_alc = float(ventana["Volume"][diff_c > 0].sum())
    vol_baj = float(ventana["Volume"][diff_c < 0].sum())
    total   = vol_alc + vol_baj

    if total > 0:
        ratio_alc = vol_alc / total
        if ratio_alc >= 0.62:
            acc_dist = "acumulacion"
        elif ratio_alc <= 0.38:
            acc_dist = "distribucion"
        else:
            acc_dist = "neutral"
    else:
        acc_dist = "neutral"

    # ── Narrativa ────────────────────────────────────────────────────
    nombre_c = nombre.split(" ")[0] if " " in nombre else nombre
    vol_rel_str = f"{vol_rel:.0f}%"
    acc_txt = {
        "acumulacion": "El flujo de volumen de las últimas 10 sesiones es predominantemente alcista — señal de acumulación.",
        "distribucion": "El volumen en días bajistas supera al alcista en las últimas 10 sesiones — señal de distribución.",
        "neutral": "El volumen se distribuye de forma equilibrada entre sesiones alcistas y bajistas.",
    }[acc_dist]

    if escenario == "volumen_excepcional":
        texto = (
            f"{nombre_c} registra un volumen medio de las últimas 5 sesiones equivalente al "
            f"{vol_rel_str} de su media de 20 días — nivel excepcional. Los episodios de "
            f"volumen >200% suelen marcar puntos de inflexión o confirmación de ruptura. "
            f"Requiere interpretar la dirección del precio para distinguir capitulación de "
            f"impulso. {acc_txt}"
        )
    elif escenario == "volumen_alto":
        texto = (
            f"{nombre_c} presenta un volumen reciente ({vol_rel_str} vs media 20d) "
            f"claramente por encima de la media — participación institucional elevada. "
            f"El movimiento de precio en este contexto tiene mayor credibilidad técnica. "
            f"{acc_txt}"
        )
    elif escenario == "volumen_normal":
        texto = (
            f"{nombre_c} opera con volumen en línea con su media histórica de 20 sesiones "
            f"({vol_rel_str}). Actividad dentro de rangos normales — sin señales de "
            f"participación extraordinaria. {acc_txt}"
        )
    elif escenario == "volumen_bajo":
        texto = (
            f"{nombre_c} cotiza con volumen reducido ({vol_rel_str} vs media 20d). "
            f"Baja participación — los movimientos de precio en este contexto son menos "
            f"fiables y más susceptibles de revertir ante cualquier catalizador de volumen. "
            f"{acc_txt}"
        )
    else:  # volumen_seco
        texto = (
            f"{nombre_c} presenta volumen muy por debajo de su media ({vol_rel_str} vs media 20d) "
            f"— mercado sin interés o en período de baja actividad (festivos, verano, etc.). "
            f"Las señales técnicas en volumen seco tienen escasa significancia estadística. "
            f"{acc_txt}"
        )

    return {
        "vol_5d":    vol_5d,
        "vol_20d":   vol_20d,
        "vol_rel":   vol_rel,
        "acc_dist":  acc_dist,
        "escenario": escenario,
        "texto":     texto,
    }



# Tabla de puntuaciones por componente y escenario (0 = bajista extremo, 10 = alcista extremo)
_PUNTUACIONES_ATH = {
    "subida_libre_establecida": 9,
    "en_ath":                   8,
    "aproximandose_cerca":      7,
    "aproximandose":            6,
    "referencia":               4,
    "lejos":                    2,
}
_PUNTUACIONES_SMA200 = {
    "giro_alcista_reciente":  9,
    "tendencia_alcista":      7,
    "plana":                  5,
    "giro_bajista_reciente":  2,
    "tendencia_bajista":      1,
}
_PUNTUACIONES_RESIST = {
    "en_soporte":       8,
    "zona_baja_rango":  7,
    "sin_resistencia":  8,
    "zona_media_rango": 5,
    "zona_alta_rango":  3,
    "en_resistencia":   2,
    "sin_soporte":      2,
}
_PUNTUACIONES_FIBO = {
    "extension_161":  9,
    "extension_127":  8,
    "en_maximo":      7,
    "retroceso_236":  6,
    "retroceso_382":  5,
    "retroceso_618":  7,   # golden ratio — potencial reversión alcista
    "retroceso_786":  3,
    "swing_roto":     1,
}
_PUNTUACIONES_RSI = {
    "sobrecompra_extrema": 2,   # extendido, riesgo de corrección
    "sobrecompra":         3,
    "zona_alcista":        7,
    "zona_neutra":         5,
    "zona_bajista":        3,
    "sobreventa":          7,   # potencial rebote
    "sobreventa_extrema":  8,   # capitulación, asimetría alcista
}
_PUNTUACIONES_VOL = {
    "volumen_excepcional": 7,   # neutro-alcista: amplifica dirección
    "volumen_alto":        7,
    "volumen_normal":      5,
    "volumen_bajo":        4,
    "volumen_seco":        3,
}
# Pesos de cada componente en el score final
_PESOS = {
    "ath":    0.15,
    "sma200": 0.20,
    "resist": 0.15,
    "fibo":   0.15,
    "rsi":    0.20,
    "vol":    0.15,
}


def calcular_puntuacion_tecnica(
    analisis_ath, analisis_sma200, analisis_resist,
    analisis_fibo, analisis_rsi, analisis_vol
) -> "dict":
    """
    Agrega los 6 componentes del Diagnóstico Técnico en un score 0-10.

    Retorna:
        score_total (float 0-10)
        scores_ind  (dict componente → {puntos, peso, contribucion, escenario})
        señal       ('alcista' | 'neutral' | 'bajista')
        conviccion  (int: número de componentes que coinciden con la señal)
        texto       (str narrativa)
    """
    componentes = [
        ("ath",    analisis_ath,    _PUNTUACIONES_ATH,    "ATH",          "📈 Máx. Histórico"),
        ("sma200", analisis_sma200, _PUNTUACIONES_SMA200, "SMA200",       "〰️ Media 200"),
        ("resist", analisis_resist, _PUNTUACIONES_RESIST, "Resistencias", "🧱 Niveles"),
        ("fibo",   analisis_fibo,   _PUNTUACIONES_FIBO,   "Fibonacci",    "📐 Fibonacci"),
        ("rsi",    analisis_rsi,    _PUNTUACIONES_RSI,    "RSI",          "⚡ RSI"),
        ("vol",    analisis_vol,    _PUNTUACIONES_VOL,    "Volumen",      "🔊 Volumen"),
    ]

    scores_ind  = {}
    score_num   = 0.0
    peso_total  = 0.0

    for key, analisis, tabla, nombre_c, icono in componentes:
        peso = _PESOS[key]
        if analisis and "escenario" in analisis:
            esc     = analisis["escenario"]
            pts     = tabla.get(esc, 5)
            contrib = pts * peso
            scores_ind[key] = {
                "nombre":      nombre_c,
                "icono":       icono,
                "escenario":   esc,
                "puntos":      pts,
                "peso":        peso,
                "contrib":     contrib,
                "disponible":  True,
            }
            score_num  += contrib
            peso_total += peso
        else:
            scores_ind[key] = {
                "nombre":     nombre_c,
                "icono":      icono,
                "escenario":  "—",
                "puntos":     5,
                "peso":       peso,
                "contrib":    0.0,
                "disponible": False,
            }

    # Normalizar si faltan componentes
    if peso_total > 0:
        score_total = score_num / peso_total * (peso_total / sum(_PESOS.values()))
        # Ajuste: si peso_total < 1 normalizamos al rango completo
        score_total = score_num / peso_total * 10 / 10
        # Simplificado: score = suma_contribuciones / peso_disponible
        score_total = score_num / peso_total
    else:
        score_total = 5.0

    # Señal
    if score_total >= 6.5:
        señal = "alcista"
    elif score_total <= 3.5:
        señal = "bajista"
    else:
        señal = "neutral"

    # Convicción: cuántos componentes disponibles coinciden con la señal
    conviccion = 0
    disp_total = sum(1 for v in scores_ind.values() if v["disponible"])
    for v in scores_ind.values():
        if not v["disponible"]:
            continue
        p = v["puntos"]
        if señal == "alcista" and p >= 6:
            conviccion += 1
        elif señal == "bajista" and p <= 4:
            conviccion += 1
        elif señal == "neutral" and 4 < p < 7:
            conviccion += 1

    # Narrativa
    score_str = f"{score_total:.1f}"
    conv_str  = f"{conviccion}/{disp_total}" if disp_total else "—"

    if señal == "alcista":
        if score_total >= 8:
            texto = (
                f"Puntuación técnica integrada de {score_str}/10 — sesgo fuertemente alcista. "
                f"{conviccion} de {disp_total} componentes confluyen en la lectura positiva. "
                f"La estructura técnica favorece al comprador en el contexto actual."
            )
        else:
            texto = (
                f"Puntuación técnica integrada de {score_str}/10 — sesgo alcista moderado. "
                f"{conviccion} de {disp_total} componentes con lectura positiva. "
                f"La estructura técnica es favorable pero sin convicción unánime."
            )
    elif señal == "bajista":
        if score_total <= 2:
            texto = (
                f"Puntuación técnica integrada de {score_str}/10 — sesgo fuertemente bajista. "
                f"{conviccion} de {disp_total} componentes confluyen en la lectura negativa. "
                f"La estructura técnica no favorece posiciones largas en este momento."
            )
        else:
            texto = (
                f"Puntuación técnica integrada de {score_str}/10 — sesgo bajista moderado. "
                f"{conviccion} de {disp_total} componentes con lectura negativa. "
                f"Prudencia técnica — esperar señales de mejora antes de actuar."
            )
    else:
        texto = (
            f"Puntuación técnica integrada de {score_str}/10 — zona neutral. "
            f"Los componentes no ofrecen dirección clara ({conv_str} en zona neutral). "
            f"Mercado en equilibrio técnico — priorizar análisis fundamental y macro."
        )

    return {
        "score_total": score_total,
        "scores_ind":  scores_ind,
        "señal":       señal,
        "conviccion":  conviccion,
        "disp_total":  disp_total,
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
    """Euribor 12M — scrape de euribor-rates.eu (tabla diaria/semanal).
    ECB FM API (EURIBOR1YD_) dejó de devolver datos — migrado a fuente web."""
    try:
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        r = requests.get("https://www.euribor-rates.eu/current-euribor-rates.asp",
                         headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            return None
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if cells and "12" in cells[0]:
                # cells[1] = latest value, e.g. "2.866 %"
                val_str = cells[1].replace("%", "").replace(",", ".").strip()
                return float(val_str)
        return None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def obtener_historico_euribor_12m(n_months: int = 24) -> "pd.Series | None":
    """Serie histórica mensual Euribor 12M — euribor-rates.eu/en/euribor-rates-by-year/."""
    try:
        import datetime
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        registros = {}
        current_year = datetime.datetime.now().year
        years_needed = (n_months // 12) + 2
        for yr in range(current_year, current_year - years_needed, -1):
            url = f"https://www.euribor-rates.eu/en/euribor-rates-by-year/{yr}/"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table")
            if not table:
                continue
            rows = table.find_all("tr")
            # Find column index for "Euribor 12 months"
            header = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
            try:
                col_idx = next(i for i, h in enumerate(header) if "12" in h)
            except StopIteration:
                continue
            for row in rows[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                if len(cells) <= col_idx:
                    continue
                try:
                    # Date format: "12/1/2025" → M/D/YYYY
                    date = pd.to_datetime(cells[0], format="%m/%d/%Y", errors="coerce")
                    if pd.isna(date):
                        date = pd.to_datetime(cells[0], errors="coerce")
                    if pd.isna(date):
                        continue
                    val_str = cells[col_idx].replace("%", "").replace(",", ".").strip()
                    registros[date] = float(val_str)
                except (ValueError, IndexError):
                    continue
            if len(registros) >= n_months:
                break
        if not registros:
            return None
        serie = pd.Series(registros).sort_index()
        return serie.tail(n_months)
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


# =============================================================================
# PESTAÑA RENTA FIJA
# =============================================================================

@st.cache_data(ttl=1800)
def _obtener_tipo_ecb_yc(tenor: str) -> "float | None":
    """Tipo spot de la curva AAA Euro Area desde ECB Yield Curve dataset.
    tenor: '3M','6M','1Y','2Y','3Y','5Y','7Y','10Y','15Y','20Y','30Y'
    """
    # ECB YC dataset series key format
    _map = {
        "3M": "SR_3M", "6M": "SR_6M", "1Y": "SR_1Y",
        "2Y": "SR_2Y", "3Y": "SR_3Y", "5Y": "SR_5Y",
        "7Y": "SR_7Y", "10Y": "SR_10Y", "15Y": "SR_15Y",
        "20Y": "SR_20Y", "30Y": "SR_30Y",
    }
    sr = _map.get(tenor)
    if not sr:
        return None
    series_key = f"B.U2.EUR.4F.G_N_A.SV_C_YM.{sr}"
    return obtener_dato_ecb(series_key, flow_ref="YC")


@st.cache_data(ttl=1800)
def _obtener_historico_yc(tenor: str, n_obs: int = 60) -> "pd.Series | None":
    """Histórico mensual de la curva AAA Euro Area para un tenor dado."""
    _map = {
        "3M": "SR_3M", "6M": "SR_6M", "1Y": "SR_1Y",
        "2Y": "SR_2Y", "5Y": "SR_5Y", "10Y": "SR_10Y", "30Y": "SR_30Y",
    }
    sr = _map.get(tenor)
    if not sr:
        return None
    return obtener_historico_ecb("YC", f"B.U2.EUR.4F.G_N_A.SV_C_YM.{sr}", n_obs)


@st.cache_data(ttl=1800)
def _obtener_tipo_pais_ecb(pais: str, tenor: str = "10Y") -> "float | None":
    """Tipo gobierno 10Y por país vía ECB IRS (Maastricht criterion rates).
    pais: 'ES','DE','FR','IT','PT','NL','BE'
    """
    # ECB IRS dataset — Maastricht long-term government bond yields
    # Serie: M.{CC}.EUR.RT.LB.A.A.A207.HSTA  (A207 = long-term govt bond yield)
    series_key = f"M.{pais}.EUR.RT.LB.A.A.A207.HSTA"
    val = obtener_dato_ecb(series_key, flow_ref="IRS")
    if val is not None:
        return val
    # Fallback: try alternative series format
    series_key2 = f"M.{pais}.EUR.RT.LB.X.X.10Y.D.HSTA"
    return obtener_dato_ecb(series_key2, flow_ref="IRS")


def _rf_metric(label: str, valor, suffix: str = "%", delta=None, help_txt: str = ""):
    """Tarjeta métrica unificada para renta fija."""
    if valor is None:
        st.metric(label, "N/D", help=help_txt)
    else:
        d_str = None
        if delta is not None:
            d_str = f"{delta:+.2f} pp"
        st.metric(label, f"{valor:.2f}{suffix}", delta=d_str, help=help_txt)


def _rf_card(titulo: str, tir: "float|None", plazo: str,
             color: str = "#1e3a5f", bg: str = "#f0f4ff",
             descripcion: str = ""):
    """Tarjeta visual para un instrumento de renta fija."""
    tir_txt = f"{tir:.2f}%" if tir is not None else "N/D"
    tir_color = "#16a34a" if (tir or 0) >= 0 else "#dc2626"
    st.markdown(
        f'<div style="background:{bg};border-left:4px solid {color};'
        f'border-radius:8px;padding:12px 16px;margin-bottom:8px">'
        f'<div style="font-size:11px;color:{color};font-weight:700;'
        f'text-transform:uppercase;letter-spacing:.5px">{plazo}</div>'
        f'<div style="font-size:22px;font-weight:800;color:{tir_color}">{tir_txt}</div>'
        f'<div style="font-size:12px;color:#64748b;margin-top:2px">{titulo}</div>'
        f'{"<div style=font-size:11px;color:#94a3b8;margin-top:3px>" + descripcion + "</div>" if descripcion else ""}'
        f'</div>',
        unsafe_allow_html=True
    )


def pestaña_renta_fija():
    """Pestaña de Renta Fija: Tesoro ES, curva tipos, prima de riesgo, calculadora."""
    import plotly.graph_objects as go

    st.markdown("### 💰 Renta Fija — Tesoro Público, Bonos y Letras")
    st.caption("Tipos de referencia en tiempo real · Fuente: ECB Statistical Data Warehouse · "
               "Los datos de la curva AAA corresponden a bonos soberanos de máxima calificación "
               "(Alemania, Países Bajos, Finlandia). Para tipos específicos españoles se indica el origen.")

    # ── Controles de periodo ─────────────────────────────────────────────────
    _rf_periodo = st.radio(
        "Periodo histórico",
        ["1A", "3A", "5A"],
        horizontal=True,
        key="rf_periodo",
        help="Periodo para los gráficos históricos"
    )
    _rf_n = {"1A": 12, "3A": 36, "5A": 60}[_rf_periodo]

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # BLOQUE 1 — TIPOS DE REFERENCIA BCE
    # ════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🏦 Tipos de Referencia del BCE")

    with st.expander("📖 ¿Qué son los tipos del BCE y cómo afectan a tu inversión?", expanded=False):
        st.markdown("""
**El BCE fija tres tipos oficiales** que son el punto de partida de toda la renta fija en euros:

- **Tipo de depósito (DFR):** lo que el BCE paga a los bancos por guardar su dinero en Frankfurt. Es el suelo del mercado monetario — ningún banco prestará a otro por menos de lo que le paga el BCE sin riesgo. Es el tipo más relevante para las Letras del Tesoro a corto plazo.
- **Tipo de refinanciación (MRO):** el tipo al que los bancos piden prestado al BCE a una semana. Marca el «precio oficial» del dinero a corto plazo.
- **Tipo de facilidad marginal (MLF):** el tipo de emergencia al que los bancos acceden a liquidez de un día para otro. Es el techo del mercado monetario.

**¿Por qué importa al inversor en renta fija?**
Cuando el BCE sube tipos, los bonos existentes pierden valor (su cupón fijo vale menos en comparación con los nuevos bonos que pagan más). Cuando los baja, los bonos existentes suben. Esta relación inversa entre tipos y precio de los bonos es la regla más fundamental de la renta fija.

*En el ciclo 2022-2024 el BCE subió el DFR del -0,5% al 4,0% en 14 meses — el ciclo de subidas más agresivo de su historia — haciendo que los bonos de largo plazo perdieran hasta un 25% de valor.*
        """)
        st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

    _dfr   = obtener_dato_ecb("B.U2.EUR.4F.KR.DFR.LEV")
    _mro   = obtener_dato_ecb("B.U2.EUR.4F.KR.MRR_FR.LEV")
    _mlf   = obtener_dato_ecb("B.U2.EUR.4F.KR.MLFR.LEV")
    _euri3 = obtener_dato_ecb("B.U2.EUR.4F.MM.B.EURIBOR3MD_.HSTA")
    _euri6 = obtener_dato_ecb("B.U2.EUR.4F.MM.B.EURIBOR6MD_.HSTA")

    _bc1, _bc2, _bc3, _bc4, _bc5 = st.columns(5)
    with _bc1:
        _rf_metric("Depósito BCE (DFR)", _dfr, help_txt="Tipo de depósito del BCE — suelo del mercado monetario")
    with _bc2:
        _rf_metric("Refinanciación (MRO)", _mro, help_txt="Tipo de refinanciación principal del BCE")
    with _bc3:
        _rf_metric("Facilidad Marginal", _mlf, help_txt="Tipo de facilidad marginal de crédito — techo del mercado")
    with _bc4:
        _rf_metric("Euribor 3M", _euri3, help_txt="Tipo interbancario a 3 meses — referencia hipotecas y bonos corto")
    with _bc5:
        _rf_metric("Euribor 6M", _euri6, help_txt="Tipo interbancario a 6 meses")

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # BLOQUE 2 — CURVA DE TIPOS EURO AREA AAA
    # ════════════════════════════════════════════════════════════════════════
    st.markdown("#### 📐 Curva de Tipos — Euro Área (AAA)")

    with st.expander("📖 ¿Qué es la curva de tipos y cómo se interpreta?", expanded=False):
        st.markdown("""
**La curva de tipos** representa la relación entre el plazo de un bono y su rentabilidad (TIR).
En condiciones normales la curva es **ascendente**: a más plazo, más rentabilidad — porque el
inversor exige más por inmovilizar su dinero durante más tiempo y por asumir más incertidumbre.

**Formas de la curva y su significado económico:**

**1. Curva normal (ascendente):** los tipos a largo son más altos que a corto.
Señal de confianza en el crecimiento económico futuro. El mercado espera inflación moderada y
crecimiento. Es la forma «sana» de la curva.

**2. Curva invertida:** los tipos a corto son más altos que a largo.
Es la más temida por los economistas — históricamente ha precedido a todas las recesiones
en EE.UU. desde 1970. La lógica: si los inversores aceptan menos rentabilidad a largo plazo
que a corto, es porque esperan que los tipos caigan en el futuro (lo que ocurre cuando la
economía se desacelera y el banco central baja tipos). En 2022-2023, la curva americana
estuvo más invertida que en ningún momento desde 1981.

**3. Curva plana:** tipos similares en todos los plazos.
Señal de transición — el mercado no tiene convicción sobre la dirección de la economía.
Suele aparecer antes de un cambio de ciclo.

**4. Curva jorobada (humped):** los tipos de medio plazo son los más altos.
Situación temporal inusual que refleja expectativas complejas sobre la política monetaria.

**La curva AAA que ves aquí** corresponde a bonos soberanos de máxima calificación de la
Eurozona (esencialmente Alemania, Países Bajos y Finlandia). Es la referencia «libre de riesgo»
en euros. Los bonos españoles pagan algo más — esa diferencia es la prima de riesgo.
        """)
        st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

    _tenores_curva = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]
    _tipos_curva = []
    for _t in _tenores_curva:
        _v = _obtener_tipo_ecb_yc(_t)
        _tipos_curva.append(_v)

    # Métricas rápidas de puntos clave
    _yc_3m  = _tipos_curva[0]
    _yc_2y  = _tipos_curva[3]
    _yc_10y = _tipos_curva[7]
    _yc_30y = _tipos_curva[10]

    _cc1, _cc2, _cc3, _cc4 = st.columns(4)
    with _cc1:
        _rf_metric("AAA 3 meses", _yc_3m, help_txt="Tipo spot a 3 meses — curva AAA Euro Área")
    with _cc2:
        _rf_metric("AAA 2 años", _yc_2y, help_txt="Tipo spot a 2 años")
    with _cc3:
        _rf_metric("AAA 10 años", _yc_10y, help_txt="Tipo spot a 10 años — referencia bono largo plazo")
    with _cc4:
        # Pendiente curva: 10Y - 2Y
        if _yc_10y is not None and _yc_2y is not None:
            _pendiente = _yc_10y - _yc_2y
            _pend_color = "normal" if _pendiente >= 0 else "inverse"
            st.metric(
                "Pendiente 10A–2A",
                f"{_pendiente:+.2f} pp",
                help="Diferencia entre el tipo a 10 años y a 2 años. "
                     "Positivo = curva normal. Negativo = curva invertida (señal de alerta recesiva)."
            )
        else:
            _rf_metric("Pendiente 10A–2A", None)

    # Gráfico de la curva
    _tenores_disp = [_t for _t, _v in zip(_tenores_curva, _tipos_curva) if _v is not None]
    _valores_disp = [_v for _v in _tipos_curva if _v is not None]

    if len(_valores_disp) >= 3:
        _fig_curva = go.Figure()
        _fig_curva.add_trace(go.Scatter(
            x=_tenores_disp, y=_valores_disp,
            mode="lines+markers",
            line=dict(color="#1e3a5f", width=2.5),
            marker=dict(size=7, color="#1e3a5f"),
            fill="tozeroy",
            fillcolor="rgba(30,58,95,0.08)",
            name="Curva AAA EA",
            hovertemplate="%{x}: <b>%{y:.2f}%</b><extra></extra>"
        ))
        _fig_curva.update_layout(
            height=260, margin=dict(l=0, r=0, t=20, b=0),
            xaxis_title="Plazo", yaxis_title="TIR (%)",
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(gridcolor="#f1f5f9"),
            xaxis=dict(gridcolor="#f1f5f9"),
            showlegend=False
        )
        st.plotly_chart(_fig_curva, use_container_width=True)
    else:
        st.info("Datos de curva no disponibles en este momento. Reintentar en unos minutos.")

    # Histórico 10Y
    _h10y = _obtener_historico_yc("10Y", _rf_n)
    if _h10y is not None and len(_h10y) > 2:
        _fig_h10 = go.Figure()
        _fig_h10.add_trace(go.Scatter(
            x=_h10y.index, y=_h10y.values,
            mode="lines", line=dict(color="#1e3a5f", width=1.8),
            fill="tozeroy", fillcolor="rgba(30,58,95,0.07)",
            name="AAA 10Y",
            hovertemplate="%{x|%b %Y}: <b>%{y:.2f}%</b><extra></extra>"
        ))
        _fig_h10.update_layout(
            height=180, margin=dict(l=0, r=0, t=14, b=0),
            title=dict(text="Histórico TIR 10 años — AAA Euro Área", font=dict(size=12)),
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(gridcolor="#f1f5f9"),
            xaxis=dict(gridcolor="#f1f5f9"),
            showlegend=False
        )
        st.plotly_chart(_fig_h10, use_container_width=True)

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # BLOQUE 3 — PRIMA DE RIESGO Y COMPARATIVA EUROPEA
    # ════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🌍 Comparativa de Tipos Soberanos Europeos — 10 Años")

    with st.expander("📖 ¿Qué es la prima de riesgo y por qué importa?", expanded=False):
        st.markdown("""
**La prima de riesgo** (o *spread* soberano) es la diferencia entre la rentabilidad del bono
a 10 años de un país y la del bono alemán (el Bund), que es el activo «libre de riesgo»
de referencia en la Eurozona.

**¿Por qué el Bund alemán es la referencia?**
Alemania tiene la calificación crediticia más alta de Europa (AAA) y la economía más grande
de la Eurozona. Su bono es el activo más líquido y seguro en euros — el equivalente europeo
del Treasury estadounidense. Cuando los inversores tienen miedo, compran Bunds (su precio
sube, su rentabilidad cae). Cuando tienen apetito por el riesgo, los venden para comprar
activos con más rendimiento.

**Cómo interpretar la prima de riesgo española:**
- **< 50 pb (puntos básicos):** prima muy baja — el mercado trata la deuda española casi como
  la alemana. Situación de máxima confianza.
- **50–100 pb:** prima normal para España — refleja la diferencia estructural entre ambas economías.
- **100–200 pb:** prima elevada — el mercado empieza a pedir más compensación por el riesgo España.
  Señal de alerta moderada.
- **> 300 pb:** zona de crisis — es donde estuvo España en 2012 (llegó a 650 pb). A partir de aquí
  la sostenibilidad de la deuda empieza a cuestionarse.

**El momento histórico de referencia: julio 2012**
La prima de riesgo española llegó a 650 puntos básicos. El mercado descontaba una posible
reestructuración de la deuda. Mario Draghi pronunció su famoso «whatever it takes» y la prima
cayó en picado. Ese episodio muestra el poder del banco central como prestamista de último
recurso y por qué la credibilidad del BCE es el ancla del euro.
        """)
        st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

    # Países y sus datos
    _paises_rf = {
        "🇩🇪 Alemania": "DE",
        "🇫🇷 Francia":  "FR",
        "🇪🇸 España":   "ES",
        "🇮🇹 Italia":   "IT",
        "🇵🇹 Portugal": "PT",
        "🇳🇱 Países Bajos": "NL",
    }

    _tipos_paises = {}
    for _nombre_p, _cc in _paises_rf.items():
        _tipos_paises[_nombre_p] = _obtener_tipo_pais_ecb(_cc, "10Y")

    _tipo_de = _tipos_paises.get("🇩🇪 Alemania")

    # Tabla de comparativa
    _cols_paises = st.columns(len(_paises_rf))
    for _i, (_nombre_p, _tipo_p) in enumerate(_tipos_paises.items()):
        with _cols_paises[_i]:
            if _tipo_p is not None and _tipo_de is not None and _nombre_p != "🇩🇪 Alemania":
                _spread = (_tipo_p - _tipo_de) * 100  # en puntos básicos
                _sp_color = "#16a34a" if _spread < 100 else "#d97706" if _spread < 200 else "#dc2626"
                st.markdown(
                    f'<div style="background:#f8fafc;border-radius:8px;padding:10px 12px;'
                    f'border:1px solid #e2e8f0;text-align:center">'
                    f'<div style="font-size:12px;color:#64748b">{_nombre_p}</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#1e293b">'
                    f'{"N/D" if _tipo_p is None else f"{_tipo_p:.2f}%"}</div>'
                    f'<div style="font-size:11px;color:{_sp_color};font-weight:600">'
                    f'+{_spread:.0f} pb vs Bund</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div style="background:#f8fafc;border-radius:8px;padding:10px 12px;'
                    f'border:1px solid #e2e8f0;text-align:center">'
                    f'<div style="font-size:12px;color:#64748b">{_nombre_p}</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#1e293b">'
                    f'{"N/D" if _tipo_p is None else f"{_tipo_p:.2f}%"}</div>'
                    f'<div style="font-size:11px;color:#94a3b8">Referencia</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

    # Prima de riesgo España destacada
    _tipo_es = _tipos_paises.get("🇪🇸 España")
    if _tipo_es is not None and _tipo_de is not None:
        _prima_es = (_tipo_es - _tipo_de) * 100
        _prima_color = "#16a34a" if _prima_es < 100 else "#d97706" if _prima_es < 200 else "#dc2626"
        _prima_label = "Baja" if _prima_es < 100 else "Moderada" if _prima_es < 200 else "ELEVADA"
        st.markdown(
            f'<div style="background:#fafbfc;border:2px solid {_prima_color};border-radius:10px;'
            f'padding:14px 20px;margin-top:12px;display:flex;justify-content:space-between;'
            f'align-items:center">'
            f'<div><span style="font-size:12px;color:#64748b;font-weight:600">PRIMA DE RIESGO ESPAÑA vs ALEMANIA (10A)</span><br>'
            f'<span style="font-size:28px;font-weight:800;color:{_prima_color}">{_prima_es:.0f} pb</span>'
            f'<span style="font-size:13px;color:{_prima_color};margin-left:8px">({_prima_label})</span></div>'
            f'<div style="font-size:12px;color:#64748b;text-align:right">'
            f'ES: {_tipo_es:.2f}% · DE: {_tipo_de:.2f}%<br>'
            f'<span style="font-size:10px">Ref. histórica: máx. 650 pb (jul. 2012)</span></div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # BLOQUE 4 — LETRAS Y BONOS DEL TESORO (referencia desde curva AAA + spread)
    # ════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🏛️ Instrumentos del Tesoro Público Español")
    st.caption("TIR orientativa basada en tipos AAA Euro Área + spread histórico España. "
               "Para tipos exactos de la última subasta consultar [Tesoro Público](https://www.tesoro.es).")

    with st.expander("📖 Letras, Bonos y Obligaciones — ¿En qué se diferencian?", expanded=False):
        st.markdown("""
El Tesoro Público español emite deuda pública en tres formatos según el plazo:

**📄 Letras del Tesoro (3, 6, 9, 12 y 18 meses)**
Son instrumentos a corto plazo. Se emiten *al descuento*: compras por menos del valor nominal
(1.000€) y al vencimiento recibes los 1.000€ completos. La diferencia es tu rentabilidad.

*Ejemplo:* Compras una Letra a 12 meses por 975€ y recibes 1.000€ al vencimiento.
Tu rentabilidad efectiva es (1.000-975)/975 = 2,56% anual.

Son el equivalente español de los T-bills estadounidenses. Son los instrumentos más seguros
y líquidos del mercado español — usados por empresas para gestionar tesorería y por inversores
conservadores que buscan rentabilidad sin riesgo de crédito ni de duración.

**📋 Bonos del Estado (2, 3 y 5 años)**
Instrumentos a medio plazo. Pagan un *cupón anual fijo* más la devolución del principal
al vencimiento. Si los tipos suben después de tu compra, el bono pierde valor en mercado
secundario (aunque si lo mantienes hasta vencimiento recibes exactamente lo prometido).

**📜 Obligaciones del Estado (7, 10, 15, 30 y 50 años)**
Igual que los bonos pero a largo plazo. Tienen mayor *duración* (sensibilidad a los tipos):
una subida de 1% en los tipos puede hacer perder un 8-10% en mercado a una obligación a 10 años.
Son instrumentos para inversores con horizonte muy largo o para quien quiere asegurar
una rentabilidad fija durante décadas.

**¿Cómo comprar Deuda Pública española?**
- **Tesoro Directo** (tesoro.es): compra directa sin comisiones intermediarias. Mínimo 1.000€.
  Puedes mantener hasta vencimiento o vender en mercado secundario.
- **Banco o broker:** los ofrecen pero suelen cobrar comisiones. Ventaja: más comodidad operativa.
- **ETFs de renta fija UCITS:** exposición diversificada a bonos soberanos europeos sin
  vencimiento fijo. Recomendado para carteras de inversión pasiva.
        """)
        st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

    # Spread estimado ES vs AAA para ajustar tipos
    _spread_est = (_prima_es / 100) if (_tipo_es is not None and _tipo_de is not None) else 0.80

    # Instrumentos del Tesoro: plazo, tipo AAA base, descripción
    _instrumentos = [
        ("Letra 3M",  "3M",  "Corto plazo al descuento"),
        ("Letra 6M",  "6M",  "Corto plazo al descuento"),
        ("Letra 12M", "1Y",  "Corto plazo al descuento"),
        ("Letra 18M", "1Y",  "Corto plazo al descuento"),
        ("Bono 2A",   "2Y",  "Cupón anual · medio plazo"),
        ("Bono 3A",   "3Y",  "Cupón anual · medio plazo"),
        ("Bono 5A",   "5Y",  "Cupón anual · medio plazo"),
        ("Oblig. 10A","10Y", "Cupón anual · largo plazo"),
        ("Oblig. 15A","15Y", "Cupón anual · largo plazo"),
        ("Oblig. 30A","30Y", "Cupón anual · muy largo plazo"),
    ]

    _cols_inst = st.columns(5)
    for _i, (_nombre_inst, _tenor_inst, _desc_inst) in enumerate(_instrumentos):
        _base = _obtener_tipo_ecb_yc(_tenor_inst)
        _tir_est = (_base + _spread_est) if _base is not None else None
        _bg_inst = "#f0fdf4" if "Letra" in _nombre_inst else "#eff6ff" if "Bono" in _nombre_inst else "#faf5ff"
        _col_inst = "#16a34a" if "Letra" in _nombre_inst else "#1d4ed8" if "Bono" in _nombre_inst else "#7e22ce"
        with _cols_inst[_i % 5]:
            _rf_card(_nombre_inst, _tir_est, _desc_inst, color=_col_inst, bg=_bg_inst,
                     descripcion="TIR orientativa*")

    st.caption("\* TIR orientativa = tipo AAA Euro Área + spread histórico España. Para el tipo exacto de la última subasta consultar Tesoro Directo.")

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # BLOQUE 5 — CALCULADORA DE RENTABILIDAD NETA
    # ════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🧮 Calculadora de Rentabilidad Neta (IRPF)")

    with st.expander("📖 ¿Cómo tributan los bonos y letras en España?", expanded=False):
        st.markdown("""
**Los rendimientos de renta fija tributan en el IRPF como rendimientos del capital mobiliario**,
integrándose en la base imponible del ahorro. Esto significa que:

- Los intereses (cupones) y el descuento de las Letras tributan cuando se cobran.
- Las plusvalías por venta antes del vencimiento tributan cuando se venden.
- Los tipos actuales `[VERIFICAR con normativa del ejercicio en curso]`:
  - Hasta 6.000€: ~19%
  - 6.000€ – 50.000€: ~21%
  - 50.000€ – 200.000€: ~23%
  - Más de 200.000€: ~27%

**Las minusvalías pueden compensarse** con otras ganancias del ahorro del mismo año o
de los 4 años siguientes.

**El traspaso NO aplica a renta fija directa** — solo a fondos de inversión. Si vendes
un bono antes de vencimiento con pérdidas, puedes compensar con ganancias de acciones
o fondos (con límites). Los ETFs de renta fija tampoco se benefician del régimen de traspaso.

**Ventaja fiscal de las Letras:** al ser al descuento, la rentabilidad es *implícita* —
no hay retención en origen en la mayoría de casos si se compran en Tesoro Directo.
        """)
        st.caption("[VERIFICAR] · Tipos sujetos a cambios legislativos · No constituye asesoramiento fiscal")

    _calc_c1, _calc_c2, _calc_c3 = st.columns(3)
    with _calc_c1:
        _calc_importe = st.number_input("Importe invertido (€)", min_value=1000.0,
                                         max_value=10_000_000.0, value=10000.0,
                                         step=1000.0, key="rf_calc_imp")
    with _calc_c2:
        _calc_tir = st.number_input("TIR anual (%)", min_value=0.0, max_value=20.0,
                                     value=float(f"{(_yc_10y or 0) + _spread_est:.2f}") if _yc_10y else 3.0,
                                     step=0.05, format="%.2f", key="rf_calc_tir")
    with _calc_c3:
        _calc_plazo = st.selectbox("Plazo", ["3 meses", "6 meses", "1 año", "2 años", "5 años", "10 años"],
                                    index=2, key="rf_calc_plazo")

    _plazo_map = {"3 meses": 0.25, "6 meses": 0.5, "1 año": 1.0,
                  "2 años": 2.0, "5 años": 5.0, "10 años": 10.0}
    _plazo_a = _plazo_map[_calc_plazo]
    _rend_bruto = _calc_importe * (_calc_tir / 100) * _plazo_a
    _tipo_irpf = 0.19 if _rend_bruto <= 6000 else 0.21 if _rend_bruto <= 50000 else 0.23
    _impuestos = _rend_bruto * _tipo_irpf
    _rend_neto = _rend_bruto - _impuestos
    _tir_neta = (_rend_neto / _calc_importe / _plazo_a) * 100

    _res1, _res2, _res3, _res4 = st.columns(4)
    with _res1:
        st.metric("Rendimiento bruto", f"{_rend_bruto:,.2f} €")
    with _res2:
        st.metric(f"IRPF estimado ({_tipo_irpf*100:.0f}%)", f"-{_impuestos:,.2f} €")
    with _res3:
        st.metric("Rendimiento neto", f"{_rend_neto:,.2f} €")
    with _res4:
        st.metric("TIR neta anual", f"{_tir_neta:.2f}%")

    st.caption("[VERIFICAR] Cálculo orientativo. Tipo IRPF estimado según tramos vigentes (puede variar según comunidad autónoma y situación personal). Consultar con asesor fiscal para cálculo preciso.")

    # ETFs de renta fija UCITS accesibles desde España
    st.divider()
    st.markdown("#### 📊 ETFs de Renta Fija UCITS — Accesibles desde España")
    st.caption("Los ETFs UCITS son la vía más eficiente para exposición diversificada a renta fija sin vencimiento fijo.")

    _etfs_rf = [
        ("IBGS.AS",  "iShares Spain Govt Bond",       "Bonos soberanos España",         "Gubernamental ES"),
        ("IBGX.AS",  "iShares Core EUR Govt Bond",    "Bonos soberanos Eurozona",        "Gubernamental EA"),
        ("IEAG.AS",  "iShares Core EUR Agg Bond",     "Agregado EUR (govt+corp)",        "Agregado EUR"),
        ("IEGE.AS",  "iShares EUR Govt Bond 1-3yr",   "Bonos corto plazo EA",            "Corto plazo"),
        ("IBCI.AS",  "iShares EUR Inflation Bond",    "Bonos ligados a inflación EUR",   "Inflación"),
        ("EMBE.AS",  "iShares EM Govt Bond EUR Hdg",  "Bonos emergentes cubierto EUR",   "Emergentes"),
    ]

    _etf_cols = st.columns(3)
    for _ei, (_tick, _nm, _desc, _cat) in enumerate(_etfs_rf):
        with _etf_cols[_ei % 3]:
            try:
                _etf_info = yf.Ticker(_tick).fast_info
                _etf_price = float(_etf_info.get("lastPrice") or _etf_info.get("regularMarketPrice") or 0)
                _etf_prev  = float(_etf_info.get("previousClose") or _etf_price)
                _etf_chg   = ((_etf_price - _etf_prev) / _etf_prev * 100) if _etf_prev else 0
                _chg_color = "#16a34a" if _etf_chg >= 0 else "#dc2626"
                _price_str = f"{_etf_price:.2f} €" if _etf_price else "N/D"
                _chg_str   = f"{_etf_chg:+.2f}%" if _etf_price else ""
            except Exception:
                _price_str, _chg_str, _chg_color = "N/D", "", "#94a3b8"
            st.markdown(
                f'<div style="background:#f8fafc;border-radius:8px;padding:10px 12px;'
                f'border:1px solid #e2e8f0;margin-bottom:8px">'
                f'<div style="font-size:10px;color:#94a3b8;font-weight:600">{_cat}</div>'
                f'<div style="font-size:13px;font-weight:700;color:#1e293b">{_nm}</div>'
                f'<code style="font-size:11px">{_tick}</code>'
                f'<div style="font-size:11px;color:#64748b">{_desc}</div>'
                f'<div style="font-size:16px;font-weight:700;color:#1e293b;margin-top:4px">'
                f'{_price_str} <span style="font-size:12px;color:{_chg_color}">{_chg_str}</span></div>'
                f'</div>',
                unsafe_allow_html=True
            )

    st.caption("Precios orientativos via Yahoo Finance · Los ETFs UCITS son los únicos accesibles al minorista español bajo la regulación PRIIPs/MiFID II")



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
        h_euribor  = obtener_historico_euribor_12m(_n_obs)
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

    # ── PETRÓLEO ─────────────────────────────────────────────────────────────
    st.markdown("#### 🛢️ Petróleo — Brent vs WTI")
    _col_b, _col_w, _col_spread, _col_ng = st.columns(4)
    _brent_p, _brent_d = obtener_precio_macro("BZ=F")
    _wti_p,   _wti_d   = obtener_precio_macro("CL=F")
    _ng_p,    _ng_d    = obtener_precio_macro("NG=F")
    with _col_b:
        st.metric("Brent (USD/b)", f"{_brent_p:.2f}" if _brent_p else "—",
                  delta=f"{_brent_d:+.2f}% (día)" if _brent_d else None,
                  help="Petróleo Brent futuros. Referencia europea y global del crudo.")
    with _col_w:
        st.metric("WTI (USD/b)", f"{_wti_p:.2f}" if _wti_p else "—",
                  delta=f"{_wti_d:+.2f}% (día)" if _wti_d else None,
                  help="West Texas Intermediate. Referencia EEUU. Suele cotizar con descuento vs Brent.")
    with _col_spread:
        if _brent_p and _wti_p:
            st.metric("Spread Brent-WTI", f"{(_brent_p - _wti_p):.2f} USD",
                      help="Diferencial Brent menos WTI. Históricamente 0-5 USD positivo.")
        else:
            st.metric("Spread Brent-WTI", "—")
    with _col_ng:
        st.metric("Gas Natural (USD)", f"{_ng_p:.3f}" if _ng_p else "—",
                  delta=f"{_ng_d:+.2f}% (día)" if _ng_d else None,
                  help="Gas Natural Henry Hub (USD/MMBTU).")
    with st.spinner("Cargando histórico Petróleo..."):
        _h_brent = obtener_historico_yf("BZ=F", _yf_period)
        _h_wti   = obtener_historico_yf("CL=F", _yf_period)
        _h_ng    = obtener_historico_yf("NG=F", _yf_period)
    _fig_oil = _macro_chart({"Brent (USD/b)": _h_brent, "WTI (USD/b)": _h_wti},
                            unidad=" USD/b", fecha_inicio=_fecha_ini, height=250)
    st.plotly_chart(_fig_oil, use_container_width=True, config={"displayModeBar": False})
    st.caption("Gas Natural Henry Hub (USD/MMBTU)")
    _fig_ng = _macro_chart({"Gas Natural": _h_ng}, unidad=" USD", fecha_inicio=_fecha_ini, height=180)
    _fig_ng.update_traces(line_color="#f59e0b")
    st.plotly_chart(_fig_ng, use_container_width=True, config={"displayModeBar": False})

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
                          huecos: list = None,
                          analisis_ath=None,
                          analisis_sma200=None,
                          analisis_resist=None,
                          analisis_fibo=None,
                          analisis_rsi=None,
                          analisis_vol=None,
                          puntuacion_tec=None) -> str:
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
    if tipo_activo == "etf":
        _cat_etf_html = _ETFS_CATEGORIA.get(ticker)
        _comp_html = obtener_comparativa_etf(_cat_etf_html, ticker) if _cat_etf_html else []
        _comp_rows_html = ""
        for _e in _comp_html:
            _ter_s  = f"{_e['ter']:.2f}%" if _e['ter'] is not None else "—"
            _aum_s  = f"{_e['aum']/1e9:.1f}B" if _e['aum'] else "—"
            _r1a_s  = (f"+{_e['rent_1a']:.1f}%" if _e['rent_1a'] >= 0 else f"{_e['rent_1a']:.1f}%") if _e['rent_1a'] is not None else "—"
            _dist_badge = ('<span style="background:#dcfce7;color:#166534;padding:1px 6px;border-radius:4px;font-size:11px">Acc</span>'
                          if _e['dist'] == 'Acumulación' else
                          '<span style="background:#dbeafe;color:#1d4ed8;padding:1px 6px;border-radius:4px;font-size:11px">Dist</span>')
            _bg = 'background:#f0fdf4;font-weight:700' if _e['actual'] else ''
            _comp_rows_html += (
                f'<tr style="{_bg}">'
                f'<td style="font-family:monospace;font-size:11px">{_e["ticker"]}</td>'
                f'<td>{_ter_s}</td>'
                f'<td>{_dist_badge}</td>'
                f'<td style="font-size:11px">{_aum_s}</td>'
                f'<td>{_r1a_s}</td>'
                f'<td style="font-size:11px;color:#64748b">{_e["indice"]}</td>'
                f'</tr>'
            )
        _comp_table_html = ""
        if _comp_rows_html:
            _cat_label = _cat_etf_html or ""
            _comp_table_html = (
                f'<h3 style="margin:12px 0 6px;font-size:0.85rem;color:#1e293b">'
                f'&#127942; Comparativa &mdash; {_cat_label}</h3>'
                '<table style="width:100%;border-collapse:collapse;font-size:12px">'
                '<thead><tr style="background:#1e3a5f;color:white">'
                '<th style="padding:4px 8px;text-align:left">ETF</th>'
                '<th style="padding:4px 8px;text-align:left">TER</th>'
                '<th style="padding:4px 8px;text-align:left">Pol&iacute;tica</th>'
                '<th style="padding:4px 8px;text-align:left">AUM</th>'
                '<th style="padding:4px 8px;text-align:left">Rent. 1A</th>'
                '<th style="padding:4px 8px;text-align:left">&Iacute;ndice</th>'
                '</tr></thead>'
                f'<tbody>{_comp_rows_html}</tbody>'
                '</table>'
                '<p style="font-size:10px;color:#94a3b8;margin-top:4px">'
                'Ordenado por TER. &#11088; = ETF analizado.</p>'
            )
        fund_section = (
            '<div class="card">'
            '<h2>&#128203; Datos Fundamentales</h2>'
            '<p style="color:#64748b;font-size:0.9rem;margin:6px 0 8px">'
            '&#9888; <strong>No aplica</strong> &mdash; Los ETFs no tienen an&aacute;lisis fundamental propio '
            '(PER, BPA, capitalizaci&oacute;n, etc.). '
            'Eval&uacute;a el ETF por su &iacute;ndice replicado, TER, AUM y tracking error.'
            '</p>'
            + _comp_table_html +
            '</div>'
        )
    elif fundamentales:
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

    # ── Diagnóstico Técnico ──────────────────────────────────────────────
    _diag_rows_html = []
    _componentes_diag_html = [
        ("ATH",          analisis_ath),
        ("SMA200",       analisis_sma200),
        ("Resistencias", analisis_resist),
        ("Fibonacci",    analisis_fibo),
        ("RSI",          analisis_rsi),
        ("Volumen",      analisis_vol),
    ]
    for _cn_h, _ca_h in _componentes_diag_html:
        if _ca_h and "escenario" in _ca_h and "texto" in _ca_h:
            _esc_h = _ca_h["escenario"].replace("_", " ").title()
            _narr_h = _ca_h["texto"][:240] + "..." if len(_ca_h["texto"]) > 240 else _ca_h["texto"]
            _diag_rows_html.append(
                f'<tr>'
                f'<td style="font-weight:600;padding:5px 10px;white-space:nowrap;color:#1e3a5f">{_cn_h}</td>'
                f'<td style="padding:5px 10px;color:#374151;font-size:12px">{_esc_h}</td>'
                f'<td style="padding:5px 10px;font-size:12px;color:#555;line-height:1.5">{_narr_h}</td>'
                f'</tr>'
            )
    _score_row_html = ""
    if puntuacion_tec:
        _sc_h = puntuacion_tec["score_total"]
        _sn_h = puntuacion_tec["señal"]
        _col_h = {"alcista": "#16a34a", "bajista": "#dc2626", "neutral": "#64748b"}.get(_sn_h, "#64748b")
        _cv_h = puntuacion_tec["conviccion"]
        _dp_h = puntuacion_tec["disp_total"]
        _score_row_html = (
            f'<tr style="background:#f0f9ff">'
            f'<td colspan="3" style="padding:10px 12px">'
            f'<strong style="color:{_col_h};font-size:14px">&#127919; Puntuacion Tecnica: '
            f'{_sc_h:.1f}/10 &#8212; {_sn_h.upper()}</strong>'
            f'&nbsp;<span style="color:#64748b;font-size:12px">({_cv_h}/{_dp_h} componentes coinciden)</span>'
            f'<br/><span style="font-size:12px;color:#374151;line-height:1.6">'
            f'{puntuacion_tec["texto"]}</span>'
            f'</td></tr>'
        )
    _diag_section = ""
    if _diag_rows_html or _score_row_html:
        _diag_section = (
            f'<div style="margin:20px 0">'
            f'<div class="col-title" style="margin-bottom:10px">Diagnostico Tecnico</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:13px;'
            f'border:1px solid #e2e8f0;border-radius:6px;overflow:hidden">'
            f'<thead><tr style="background:#1e3a5f;color:#fff">'
            f'<th style="padding:8px 10px;text-align:left;width:120px">Componente</th>'
            f'<th style="padding:8px 10px;text-align:left;width:180px">Escenario</th>'
            f'<th style="padding:8px 10px;text-align:left">Narrativa</th>'
            f'</tr></thead>'
            f'<tbody style="background:#fff">'
            + "".join(_diag_rows_html)
            + _score_row_html
            + f'</tbody></table></div>'
        )

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

        # Diagnostico Tecnico
        + _diag_section

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
                huecos: list = None,
                analisis_ath=None,
                analisis_sma200=None,
                analisis_resist=None,
                analisis_fibo=None,
                analisis_rsi=None,
                analisis_vol=None,
                puntuacion_tec=None):
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
                    Paragraph(
                        (f'+{((nr["precio"]-precio)/precio*100):+.2f}%'
                         if precio else ""),
                        S_NRM
                    ),
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
    historia.append(Paragraph("Datos Fundamentales", S_H2))
    if tipo_activo == "etf":
        historia.append(Paragraph(
            "No aplica — Los ETFs no tienen análisis fundamental propio (PER, BPA, capitalización, etc.). "
            "Evalúa el ETF por su índice replicado, TER, AUM y tracking error.",
            _p(fontSize=8, textColor=colors.HexColor("#64748b"))
        ))
        _cat_etf_pdf = _ETFS_CATEGORIA.get(ticker)
        _comp_pdf = obtener_comparativa_etf(_cat_etf_pdf, ticker) if _cat_etf_pdf else []
        if _comp_pdf:
            historia.append(Spacer(1, 0.25*cm))
            _cat_label_pdf = _cat_etf_pdf or ""
            historia.append(Paragraph(f"Comparativa de categoría — {_cat_label_pdf}", S_H2))
            historia.append(Spacer(1, 0.12*cm))
            _comp_hdr_pdf = [
                Paragraph("ETF",       _p(fontSize=7, textColor=colors.white, fontName="Helvetica-Bold")),
                Paragraph("TER",       _p(fontSize=7, textColor=colors.white, fontName="Helvetica-Bold")),
                Paragraph("Política",  _p(fontSize=7, textColor=colors.white, fontName="Helvetica-Bold")),
                Paragraph("AUM",       _p(fontSize=7, textColor=colors.white, fontName="Helvetica-Bold")),
                Paragraph("Rent. 1A",  _p(fontSize=7, textColor=colors.white, fontName="Helvetica-Bold")),
                Paragraph("Índice",    _p(fontSize=7, textColor=colors.white, fontName="Helvetica-Bold")),
            ]
            _comp_rows_pdf = [_comp_hdr_pdf]
            for _ec in _comp_pdf:
                _ter_p  = f"{_ec['ter']:.2f}%" if _ec['ter'] is not None else "—"
                _aum_p  = f"{_ec['aum']/1e9:.1f}B" if _ec['aum'] else "—"
                _r1a_p  = (f"+{_ec['rent_1a']:.1f}%" if _ec['rent_1a'] >= 0 else f"{_ec['rent_1a']:.1f}%") if _ec['rent_1a'] is not None else "—"
                _fn_bold = "Helvetica-Bold" if _ec['actual'] else "Helvetica"
                _indice_short = (_ec['indice'][:28] + '…') if len(_ec.get('indice','')) > 28 else _ec.get('indice','—')
                _comp_rows_pdf.append([
                    Paragraph(_ec['ticker'],    _p(fontSize=7, fontName=_fn_bold)),
                    Paragraph(_ter_p,           _p(fontSize=7, fontName=_fn_bold)),
                    Paragraph(_ec['dist'],      _p(fontSize=7)),
                    Paragraph(_aum_p,           _p(fontSize=7)),
                    Paragraph(_r1a_p,           _p(fontSize=7, fontName=_fn_bold)),
                    Paragraph(_indice_short,    _p(fontSize=7)),
                ])
            # col widths: 2.2 + 1.5 + 2.5 + 1.5 + 2.0 + 8.3 = 18 cm
            _t_comp_pdf = Table(_comp_rows_pdf, colWidths=[2.2*cm, 1.5*cm, 2.5*cm, 1.5*cm, 2.0*cm, 8.3*cm])
            _t_comp_pdf.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), CA),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [BL, GF]),
                ("BACKGROUND",    (0,1), (-1,-1), colors.HexColor("#f0fdf4")),  # overridden per row below
                ("GRID",          (0,0), (-1,-1), 0.2, GB),
                ("TOPPADDING",    (0,0), (-1,-1), 2),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2),
                ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ]))
            # Highlight fila actual
            for _ri, _ec in enumerate(_comp_pdf, start=1):
                if _ec['actual']:
                    _t_comp_pdf.setStyle(TableStyle([("BACKGROUND", (0,_ri), (-1,_ri), colors.HexColor("#dcfce7"))]))
            historia.append(_t_comp_pdf)
    elif fundamentales:
        fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
        if fund_items:
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


    # ── DIAGNOSTICO TECNICO ───────────────────────────────────────────────
    _componentes_diag_pdf = [
        ("ATH",          analisis_ath),
        ("SMA200",       analisis_sma200),
        ("Resistencias", analisis_resist),
        ("Fibonacci",    analisis_fibo),
        ("RSI",          analisis_rsi),
        ("Volumen",      analisis_vol),
    ]
    _tiene_diag = any(a is not None for _, a in _componentes_diag_pdf)
    if _tiene_diag or puntuacion_tec:
        historia.append(Spacer(1, 0.3*cm))
        historia.append(Paragraph("Diagnostico Tecnico", S_H2))

        _dt_hdr = [Paragraph(h, _p(fontSize=6.5, fontName="Helvetica-Bold", textColor=BL))
                   for h in ["Componente", "Escenario", "Narrativa"]]
        _dt_rows = [_dt_hdr]
        for _cn_d, _ca_d in _componentes_diag_pdf:
            if _ca_d and "escenario" in _ca_d and "texto" in _ca_d:
                _esc_d = _ca_d["escenario"].replace("_", " ").title()
                _narr_d = _ca_d["texto"][:220] + "..." if len(_ca_d["texto"]) > 220 else _ca_d["texto"]
                _dt_rows.append([
                    Paragraph(_cn_d, _p(fontSize=7, fontName="Helvetica-Bold")),
                    Paragraph(_esc_d, S_NRM),
                    Paragraph(_narr_d, _p(fontSize=6.5)),
                ])
        if len(_dt_rows) > 1:
            _dt_t = Table(_dt_rows, colWidths=[2.2*cm, 3.0*cm, 11.3*cm])
            _dt_t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,0), CA),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [BL, GF]),
                ("GRID",          (0,0),(-1,-1), 0.2, GB),
                ("TOPPADDING",    (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
                ("LEFTPADDING",   (0,0),(-1,-1), 4),
                ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ]))
            historia.append(_dt_t)
            historia.append(Spacer(1, 0.2*cm))

        if puntuacion_tec:
            _sc_d  = puntuacion_tec["score_total"]
            _sn_d  = puntuacion_tec["señal"]
            _col_d = {"alcista": VE, "bajista": RO,
                      "neutral": colors.HexColor("#64748b")}.get(_sn_d, GB)
            _cv_d  = puntuacion_tec["conviccion"]
            _dt_d  = puntuacion_tec["disp_total"]
            historia.append(Paragraph(
                f"<b>Puntuacion Tecnica Integrada: {_sc_d:.1f}/10 -- {_sn_d.upper()}</b> "
                f"({_cv_d}/{_dt_d} componentes) -- {puntuacion_tec['texto']}",
                _p(fontSize=7.5, textColor=_col_d)
            ))
            historia.append(Spacer(1, 0.15*cm))

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


@st.cache_data(ttl=3600)
def obtener_comparativa_etf(categoria: str, ticker_actual: str) -> list[dict]:
    """Devuelve lista ordenada por TER de todos los ETFs de la categoría,
    enriquecidos con AUM y rentabilidad 1 año desde yfinance."""
    import yfinance as yf
    etfs_cat = ETFS_UCITS.get(categoria, {})
    resultado = []
    for nombre, tkr in etfs_cat.items():
        meta = ETFS_META.get(tkr, {})
        ter  = meta.get("ter")
        dist = meta.get("dist", "—")
        indice = meta.get("indice", "—")
        # Nombre corto: parte tras "— "
        nombre_corto = nombre.split("— ")[-1] if "— " in nombre else nombre
        aum = None
        rent_1a = None
        try:
            info = yf.Ticker(tkr).info
            aum  = info.get("totalAssets")
            hist = yf.Ticker(tkr).history(period="1y")
            if len(hist) >= 2:
                rent_1a = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
        except Exception:
            pass
        resultado.append({
            "ticker":       tkr,
            "nombre_corto": nombre_corto,
            "ter":          ter,
            "dist":         dist,
            "indice":       indice,
            "aum":          aum,
            "rent_1a":      rent_1a,
            "actual":       tkr == ticker_actual,
        })
    resultado.sort(key=lambda x: (x["ter"] is None, x["ter"] or 99))
    return resultado


def pantalla_analisis():
    usuario = st.session_state["usuario"]
    es_admin = usuario.get("rol") in ("superadmin", "admin")
    es_superadmin = usuario.get("rol") == "superadmin"
    inicializar_tabla_alertas()  # Crea tabla si no existe (idempotente)

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
    tabs_list = ["📈 Análisis Técnico", "🎯 Estrategia", "🤖 Análisis IA", "🌍 Macro", "💰 Renta Fija"]
    if es_superadmin:
        tabs_list.append("⚙️ Usuarios")
    tabs_list.append("📖 Ayuda")

    tab_objs = st.tabs(tabs_list)
    tab_analisis   = tab_objs[0]
    tab_estrategia = tab_objs[1]
    tab_ia         = tab_objs[2]
    tab_macro      = tab_objs[3]
    tab_rf         = tab_objs[4]

    if es_superadmin and len(tab_objs) >= 7:
        tab_admin = tab_objs[5]
        tab_ayuda = tab_objs[6]
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

        # ---- RSI ZONA / TENDENCIA / DIVERGENCIA ----
        analisis_rsi = analizar_rsi(hist, precio, nombre)

        # ---- VOLUMEN RELATIVO / ACUMULACIÓN-DISTRIBUCIÓN ----
        analisis_vol = analizar_volumen(hist, nombre)

        # ---- PUNTUACIÓN TÉCNICA INTEGRADA ----
        puntuacion_tec = calcular_puntuacion_tecnica(
            analisis_ath, analisis_sma200, analisis_resist,
            analisis_fibo, analisis_rsi, analisis_vol
        )





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
            "analisis_rsi":    analisis_rsi,
            "analisis_vol":    analisis_vol,
            "puntuacion_tec":  puntuacion_tec,
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
                    st.markdown("### 📐 Pivot Points — Guía completa para el inversor")
                    st.markdown("""
**¿Qué son y de dónde vienen los Pivot Points?**

Los Pivot Points nacieron en los corros de las bolsas de Chicago en los años 70 y 80, cuando
los *floor traders* (operadores en el parqué físico) necesitaban calcular rápidamente, antes
de que abriera el mercado, los niveles clave del día a partir de los datos de la sesión anterior.
Sin ordenadores, usaban la fórmula más simple posible: sumar el máximo, el mínimo y el cierre
del día anterior y dividir entre tres. Ese número — el **Pivot Point (PP)** — era el «centro de
gravedad» de la sesión pasada, y a partir de él calculaban resistencias (R1, R2, R3) y
soportes (S1, S2, S3).

Décadas después, el concepto no solo sobrevive sino que es más relevante que nunca: algoritmos
de trading institucional, sistemas HFT y plataformas profesionales lo calculan automáticamente,
lo que convierte esos niveles en *profecías autocumplidas* — funcionan en parte porque todos
los actores del mercado los conocen y reaccionan ante ellos.
""")
                    st.info("**Principio clave:** los Pivot Points no predicen el futuro — identifican zonas donde históricamente el mercado ha tomado decisiones. Tu trabajo es observar *cómo reacciona* el precio cuando llega a esas zonas.")
                    st.markdown("""
---

**La fórmula base (sistema Clásico) — paso a paso**

Imagina que ayer una acción cerró con estos datos: Máximo (H) = 25€, Mínimo (L) = 23€, Cierre (C) = 24€.

- **PP** = (25 + 23 + 24) / 3 = **24,00€** → el precio «justo» de referencia de la sesión anterior
- **R1** = 2×24 − 23 = **25,00€** → primera resistencia (coincide con el máximo de ayer, no es casualidad)
- **R2** = 24 + (25−23) = **26,00€** → segunda resistencia, rango completo por encima del PP
- **S1** = 2×24 − 25 = **23,00€** → primer soporte (coincide con el mínimo de ayer)
- **S2** = 24 − (25−23) = **22,00€** → segundo soporte, rango completo por debajo del PP

La elegancia matemática es que R1 y S1 «recuerdan» el máximo y mínimo de la sesión anterior.
""")
                    st.markdown("""
---

**Los 6 sistemas — cuándo usar cada uno**

| Sistema | Cómo calcula el PP | Mejor para | Característica |
|---------|-------------------|-----------|---------------|
| **Clásico** | (H+L+C)/3 | Cualquier activo y plazo | El más universal; máximo consenso |
| **Woodie** | (H+L+2C)/4 | Activos con cierres significativos | Da doble peso al cierre; PP ≠ media |
| **Camarilla** | (H+L+C)/3 + ajuste | Intradía y scalping | Niveles muy ceñidos al precio del día |
| **Fibonacci** | (H+L+C)/3 + ratios Fib | Inversores que ya usan Fibonacci | Niveles en 38.2%, 61.8%, 100% del rango |
| **DeMark** | Depende de si C>O, C<O o C=O | Mercados con apertura relevante | PP variable según contexto de la sesión |
| **CPR** | TC=(H+L)/2, BC=PP−(TC−PP) | Traders intradía avanzados | Mide si el día será estrecho o amplio |

Para el **inversor de medio-largo plazo**, el sistema **Clásico** es suficiente y es el que más
operadores tienen como referencia. Añadir Fibonacci es útil si quieres coherencia con el análisis
de retrocesos.
""")
                    st.markdown("""
---

**Los timeframes — por qué calcular los mismos niveles en 4 plazos**

Cada timeframe «habla» a un tipo diferente de participante del mercado:

- **Diario:** calculado con la sesión de ayer. Lo siguen traders de intradía y swing corto (1–3 días). El PP diario es el nivel de referencia más operativo para el día actual.
- **Semanal:** calculado con los datos de la semana anterior (lunes–viernes). Referencia para swing traders con horizonte de días. El PP semanal suele actuar como imán durante toda la semana.
- **Mensual:** calculado con el mes anterior completo. Lo usan inversores de posición y gestores de fondos para situar niveles macro. Una S2 mensual perdida a la baja es una señal técnica seria.
- **Anual:** calculado con el año anterior. Nivel de muy largo plazo; usado por analistas institucionales como referencia de valoración técnica estructural.

**Consejo práctico:** cuando el PP diario coincide aproximadamente con el PP semanal, ese nivel tiene doble peso. Si encima hay una confluencia con Fibonacci o una media móvil, es una zona de máxima atención.
""")
                    st.markdown("""
---

**Cómo interpretar el precio en relación al PP**

La posición del precio respecto al PP marca el **sesgo del día**:

- **Precio claramente sobre el PP** → sesgo alcista. El mercado «acepta» precios altos. R1 y R2 son objetivos naturales de subida.
- **Precio claramente bajo el PP** → sesgo bajista. Los vendedores controlan. S1 y S2 son los primeros soportes a vigilar.
- **Precio oscilando alrededor del PP** → indecisión. El mercado está buscando dirección. Esperar ruptura con volumen antes de actuar.

**El PP no es una línea mágica** — es una referencia. Lo que importa es la *reacción* del precio cuando llega a ese nivel: ¿rebota con fuerza y volumen? ¿Lo perfora sin resistencia? ¿Oscila sin decisión? La respuesta a esas preguntas tiene más valor que el nivel en sí.
""")
                    st.markdown("""
> ⚠️ **Errores frecuentes con los Pivot Points:**
>
> 1. Usarlos como señales de entrada automática sin confirmar con volumen o estructura de vela.
> 2. Olvidar que en tendencias fuertes el precio puede atravesar R1, R2 y R3 sin parar.
> 3. No actualizar los niveles — los Pivot Points se recalculan cada sesión/semana/mes.
""")
                    st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")
            for tf in TIMEFRAMES:
                render_tabla_pivots(tf, resultados_pivots.get(tf), precio)

        with col_conf:
            if confluencias:
                _ch1, _ch2 = st.columns([5, 1])
                with _ch1:
                    st.markdown("### Confluencias Multi-Timeframe")
                with _ch2:
                    with st.popover("ℹ️", use_container_width=True):
                        st.markdown("### 🔗 Confluencias Multi-Timeframe — Guía completa")
                        st.markdown("""
**¿Qué es una confluencia y por qué es tan poderosa?**

Imagina que cinco personas distintas, usando métodos diferentes, llegan de forma independiente
a la misma conclusión: «el precio de esta acción tiene una zona crítica en torno a 22,50€».
Eso es exactamente una confluencia técnica.

Una confluencia ocurre cuando **dos o más niveles de pivot de diferentes timeframes o sistemas
de cálculo convergen en la misma zona de precio** (dentro de un margen de tolerancia).
La clave está en la palabra *independiente*: si el soporte diario clásico, la resistencia
semanal de Fibonacci y el PP mensual coinciden todos alrededor de 22,50€, es porque
tres lógicas de cálculo distintas señalan el mismo punto — eso no es casualidad.

**¿Por qué funciona?**
Porque miles de operadores, algoritmos y fondos calculan esos niveles de forma automática.
Cuando el precio llega a esa zona, se acumulan órdenes de actores completamente distintos,
creando una barrera de oferta o demanda mucho más sólida que cualquier nivel aislado.
""")
                        st.info("**Regla de oro:** una confluencia ⭐⭐⭐ en soporte no es una señal de compra automática — es una señal de **máxima atención**. Observa cómo reacciona el precio, el volumen y los indicadores de momentum cuando llegue a esa zona.")
                        st.markdown("""
---

**El sistema de estrellas — cómo se calcula**

| Estrellas | Nº de niveles que coinciden | Qué significa en la práctica |
|-----------|---------------------------|------------------------------|
| ⭐ | 2 niveles | Zona notable — merece atención pero no es extraordinaria |
| ⭐⭐ | 3 niveles | Zona de alta probabilidad — soporte/resistencia sólido |
| ⭐⭐⭐ | 4 o más niveles | Zona institucional — muy difícil de romper sin catalizador |

La «tolerancia» que define si dos niveles «coinciden» es configurable en la app.
Una tolerancia estrecha (0,1%) solo agrupa niveles muy cercanos; una amplia (0,5%)
puede agrupar niveles que no son realmente el mismo punto.
""")
                        st.markdown("""
---

**Tipos de confluencias y su implicación**

**Confluencia de resistencias** (varios R1, R2, R_semanal... juntos):
Zona donde previsiblemente el precio encontrará vendedores.
- Si el precio llega aquí desde abajo: zona de toma de beneficios para posiciones largas. Esperar para ver si rompe con volumen antes de añadir posición.
- Si el precio rebota aquí repetidamente: resistencia estructural. Una ruptura definitiva al alza sería una señal alcista muy importante.

**Confluencia de soportes** (varios S1, S2, S_mensual... juntos):
Zona donde previsiblemente aparecerá demanda que frenará la caída.
- Si el precio llega aquí desde arriba: zona de posible apoyo. Un rebote con volumen y vela alcista confirma la zona.
- Si el precio la pierde con cierre por debajo: señal bajista seria — el soporte se ha convertido en resistencia.

**Confluencia mixta** (R de un timeframe + S de otro):
Zona de indecisión donde fuerzas opuestas se cancelan. El precio puede oscilar en el rango antes de definir dirección. Esperar la ruptura.
""")
                        st.markdown("""
---

**Cómo usar las confluencias en la práctica**

1. **Identifica las confluencias más próximas al precio actual** — las más relevantes para las próximas sesiones son las más cercanas.

2. **Espera la reacción, no anticipes** — nunca compres en una confluencia de soporte sin ver primero cómo reacciona el precio. Un soporte roto se convierte en resistencia.

3. **Combina con indicadores de momentum** — la señal más robusta es: confluencia ⭐⭐⭐ + RSI en zona de sobreventa + volumen decreciente en la caída + vela de inversión. Cuantos más factores coincidan, mayor probabilidad.

4. **Usa las confluencias para gestionar el riesgo** — una confluencia ⭐⭐⭐ es un excelente nivel de referencia para colocar un stop-loss. Si el precio cierra por debajo de ella, la tesis de soporte está invalidada.

5. **Recuerda que se recalculan** — las confluencias cambian con cada nueva sesión porque los Pivot Points se actualizan. Lo que hoy es una confluencia ⭐⭐⭐ puede no serlo mañana.
""")
                        st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")
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
                        st.markdown("### 🔗 Confluencias Multi-Timeframe — Guía completa")
                        st.markdown("""
**¿Qué es una confluencia y por qué es tan poderosa?**

Imagina que cinco personas distintas, usando métodos diferentes, llegan de forma independiente
a la misma conclusión: «el precio de esta acción tiene una zona crítica en torno a 22,50€».
Eso es exactamente una confluencia técnica.

Una confluencia ocurre cuando **dos o más niveles de pivot de diferentes timeframes o sistemas
de cálculo convergen en la misma zona de precio** (dentro de un margen de tolerancia).
La clave está en la palabra *independiente*: si el soporte diario clásico, la resistencia
semanal de Fibonacci y el PP mensual coinciden todos alrededor de 22,50€, es porque
tres lógicas de cálculo distintas señalan el mismo punto — eso no es casualidad.

**¿Por qué funciona?**
Porque miles de operadores, algoritmos y fondos calculan esos niveles de forma automática.
Cuando el precio llega a esa zona, se acumulan órdenes de actores completamente distintos,
creando una barrera de oferta o demanda mucho más sólida que cualquier nivel aislado.
""")
                        st.info("**Regla de oro:** una confluencia ⭐⭐⭐ en soporte no es una señal de compra automática — es una señal de **máxima atención**. Observa cómo reacciona el precio, el volumen y los indicadores de momentum cuando llegue a esa zona.")
                        st.markdown("""
---

**El sistema de estrellas — cómo se calcula**

| Estrellas | Nº de niveles que coinciden | Qué significa en la práctica |
|-----------|---------------------------|------------------------------|
| ⭐ | 2 niveles | Zona notable — merece atención pero no es extraordinaria |
| ⭐⭐ | 3 niveles | Zona de alta probabilidad — soporte/resistencia sólido |
| ⭐⭐⭐ | 4 o más niveles | Zona institucional — muy difícil de romper sin catalizador |

La «tolerancia» que define si dos niveles «coinciden» es configurable en la app.
Una tolerancia estrecha (0,1%) solo agrupa niveles muy cercanos; una amplia (0,5%)
puede agrupar niveles que no son realmente el mismo punto.
""")
                        st.markdown("""
---

**Tipos de confluencias y su implicación**

**Confluencia de resistencias** (varios R1, R2, R_semanal... juntos):
Zona donde previsiblemente el precio encontrará vendedores.
- Si el precio llega aquí desde abajo: zona de toma de beneficios para posiciones largas. Esperar para ver si rompe con volumen antes de añadir posición.
- Si el precio rebota aquí repetidamente: resistencia estructural. Una ruptura definitiva al alza sería una señal alcista muy importante.

**Confluencia de soportes** (varios S1, S2, S_mensual... juntos):
Zona donde previsiblemente aparecerá demanda que frenará la caída.
- Si el precio llega aquí desde arriba: zona de posible apoyo. Un rebote con volumen y vela alcista confirma la zona.
- Si el precio la pierde con cierre por debajo: señal bajista seria — el soporte se ha convertido en resistencia.

**Confluencia mixta** (R de un timeframe + S de otro):
Zona de indecisión donde fuerzas opuestas se cancelan. El precio puede oscilar en el rango antes de definir dirección. Esperar la ruptura.
""")
                        st.markdown("""
---

**Cómo usar las confluencias en la práctica**

1. **Identifica las confluencias más próximas al precio actual** — las más relevantes para las próximas sesiones son las más cercanas.

2. **Espera la reacción, no anticipes** — nunca compres en una confluencia de soporte sin ver primero cómo reacciona el precio. Un soporte roto se convierte en resistencia.

3. **Combina con indicadores de momentum** — la señal más robusta es: confluencia ⭐⭐⭐ + RSI en zona de sobreventa + volumen decreciente en la caída + vela de inversión. Cuantos más factores coincidan, mayor probabilidad.

4. **Usa las confluencias para gestionar el riesgo** — una confluencia ⭐⭐⭐ es un excelente nivel de referencia para colocar un stop-loss. Si el precio cierra por debajo de ella, la tesis de soporte está invalidada.

5. **Recuerda que se recalculan** — las confluencias cambian con cada nueva sesión porque los Pivot Points se actualizan. Lo que hoy es una confluencia ⭐⭐⭐ puede no serlo mañana.
""")
                        st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")
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
                    st.markdown("### 📉 Indicadores Técnicos — Guía didáctica completa")
                    st.markdown("""
Los **indicadores técnicos** son fórmulas matemáticas que transforman el historial de precios
(y a veces el volumen) en señales visuales que ayudan a interpretar el estado del mercado.
No predicen el futuro — describen el presente y sugieren probabilidades basadas en
comportamientos históricos similares.

Hay dos grandes familias: los indicadores de **momentum** (¿con qué fuerza se mueve el precio?)
y los de **tendencia/volatilidad** (¿en qué dirección y con qué amplitud?).
""")
                    st.markdown("---")
                    st.markdown("#### 📊 RSI — Índice de Fuerza Relativa (14 sesiones)")
                    st.markdown("""
El RSI fue creado por J. Welles Wilder en 1978 y publicado en su libro *«New Concepts in
Technical Trading Systems»*. Es probablemente el indicador de momentum más utilizado del
mundo por su simplicidad conceptual y su fiabilidad en condiciones extremas.

**¿Qué mide?**
Compara la magnitud de las subidas recientes con la de las bajadas recientes. Si en los
últimos 14 días el precio ha subido mucho más de lo que ha bajado, el RSI será alto (el
activo tiene «fuerza» reciente). Si las bajadas han dominado, el RSI será bajo.

**La fórmula simplificada:**
RSI = 100 - [100 / (1 + promedio_subidas_14d / promedio_bajadas_14d)]

**Las zonas y su significado real:**
""")
                    st.markdown("""
| RSI | Zona | Lo que indica |
|-----|------|--------------|
| > 80 | Sobrecompra extrema | El activo ha subido muy rápido. Señal de agotamiento potencial. No es señal de venta automática — en tendencias alcistas puede permanecer aquí semanas. |
| 70–80 | Sobrecompra | Precaución para nuevas compras. Esperar corrección antes de entrar. |
| 55–70 | Zona alcista | Momentum positivo y saludable. La tendencia tiene fuerza. |
| 45–55 | Zona neutra | Sin señal clara. El mercado está indeciso. |
| 30–45 | Zona bajista | Momentum negativo. La debilidad domina. |
| 20–30 | Sobreventa | Posible agotamiento vendedor. Ojo a señales de rebote. |
| < 20 | Sobreventa extrema | Caída muy intensa. Probable rebote técnico, aunque no necesariamente el suelo definitivo. |

**Las divergencias — la señal más avanzada del RSI:**
Una divergencia alcista ocurre cuando el precio hace un nuevo mínimo pero el RSI no lo confirma
(hace un mínimo más alto). Indica que el momentum bajista se está agotando. La divergencia bajista
es la contraria. Son señales de alerta temprana, no de acción inmediata.
""")
                    st.markdown("---")
                    st.markdown("#### 📈 MACD — Convergencia/Divergencia de Medias Móviles")
                    st.markdown("""
El MACD fue desarrollado por Gerald Appel a finales de los años 70. Combina dos medias
exponenciales para capturar tanto la dirección de la tendencia como su momentum.

**Los tres componentes:**
- **Línea MACD** = EMA(12) − EMA(26). Positiva cuando la media corta está sobre la larga (tendencia alcista). Negativa en lo contrario.
- **Línea de señal** = EMA(9) del MACD. La media del propio MACD — suaviza las señales.
- **Histograma** = MACD − Señal. La diferencia entre ambas líneas. Cuando crece, el momentum aumenta; cuando decrece, el impulso se agota.

**Las señales más usadas:**
- **Cruce alcista:** MACD cruza la señal hacia arriba → momentum positivo emergente. Más fiable si ocurre por debajo de cero.
- **Cruce bajista:** MACD cruza la señal hacia abajo → momentum negativo. Más fiable si ocurre por encima de cero.
- **Histograma decreciente:** aunque la tendencia continúe, el impulso se está agotando. Señal de alerta sin ser señal de giro.
- **Divergencia MACD/precio:** similar a la del RSI — el precio hace nuevos extremos que el MACD no confirma.
""")
                    st.markdown("---")
                    st.markdown("#### 📏 Bandas de Bollinger")
                    st.markdown("""
Desarrolladas por John Bollinger en los años 80, las Bandas de Bollinger son un indicador
de volatilidad que envuelve el precio entre dos bandas calculadas estadísticamente.

**Cómo se construyen:**
- **Banda media** = SMA de 20 sesiones (la media del precio en el último mes)
- **Banda superior** = Banda media + 2 desviaciones estándar
- **Banda inferior** = Banda media − 2 desviaciones estándar

Bajo una distribución estadística normal, el 95% de los precios caen dentro de las bandas.
Cuando el precio toca o sale de una banda, está en una situación estadísticamente inusual.

**%B — dónde está el precio dentro de las bandas:**
- **%B = 100%** → precio exactamente en la banda superior (sobrecompra estadística)
- **%B = 50%** → precio en la banda media
- **%B = 0%** → precio exactamente en la banda inferior (sobreventa estadística)
- **%B negativo o > 100%** → el precio ha salido de las bandas (evento extremo)

**El squeeze de Bollinger:**
Cuando las bandas se contraen mucho (baja volatilidad), suele preceder un movimiento explosivo.
No indica la dirección, solo que algo está a punto de moverse con fuerza.
""")
                    st.markdown("---")
                    st.markdown("#### 🔵 Parabolic SAR")
                    st.markdown("""
El Parabolic SAR (*Stop And Reverse*) fue también creado por J. Welles Wilder. Es un indicador
de seguimiento de tendencia que aparece como puntos por encima o por debajo del precio.

**Lectura directa:**
- **Puntos bajo el precio** → tendencia alcista activa. El SAR marca un stop dinámico que va subiendo con la tendencia.
- **Puntos sobre el precio** → tendencia bajista activa. El SAR marca un nivel de invalidación que va bajando.

**Cómo funciona el «parabólico»:**
El SAR se acelera exponencialmente cuanto más dura la tendencia (factor de aceleración que comienza en 0.02 y llega hasta 0.20). Esto hace que los puntos se acerquen cada vez más al precio, provocando eventualmente el «volteo» (el SAR se invierte de lado).

**Su mayor utilidad — el trailing stop:**
El SAR es excelente para gestionar posiciones en tendencia: a medida que el precio sube, el SAR sube con él, protegiéndote de una reversión. Si el precio cierra por debajo del SAR, la tendencia alcista está invalidada.

**Su mayor limitación:**
En mercados laterales genera señales falsas continuamente. Solo funciona bien en mercados con tendencia definida.
""")
                    st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")
        with _ih2:
            _mi1, _mi2 = st.columns([5, 1])
            with _mi1:
                st.markdown('<div class="s-ind-title" style="font-size:11px;font-weight:700;color:#1e3a5f;text-transform:uppercase;letter-spacing:.6px">Medias Móviles</div>', unsafe_allow_html=True)
            with _mi2:
                with st.popover("ℹ️", use_container_width=True):
                    st.markdown("### 📈 Medias Móviles — Guía didáctica completa")
                    st.markdown("""
Las **medias móviles** son uno de los instrumentos más antiguos del análisis técnico y,
probablemente, los más utilizados por gestores profesionales. Su lógica es engañosamente
simple: en lugar de mirar el precio de hoy, miramos el promedio de los últimos N precios.
Esto elimina el ruido diario y revela la tendencia subyacente.

La palabra «móvil» significa que cada día se recalcula: entra el precio de hoy y sale el
más antiguo. La línea resultante «se mueve» suavemente con el precio.
""")
                    st.markdown("---")
                    st.markdown("#### SMA — Media Móvil Simple")
                    st.markdown("""
La **SMA** (*Simple Moving Average*) suma los últimos N cierres y los divide entre N.
Trata cada día con el mismo peso, independientemente de si fue ayer o hace 200 días.

**Ejemplo con SMA(5):** si los últimos 5 cierres son 10, 11, 12, 11, 12 → SMA(5) = 56/5 = 11,2

**Ventaja:** muy estable, pocas señales falsas, fácil de interpretar.
**Desventaja:** reacciona lentamente a cambios bruscos de precio. En un mercado que gira rápido, la señal llega tarde.
""")
                    st.markdown("#### EMA — Media Móvil Exponencial")
                    st.markdown("""
La **EMA** (*Exponential Moving Average*) aplica más peso a los precios recientes. El precio
de ayer importa más que el de hace una semana. Esto la hace más sensible y rápida.

**El multiplicador:** k = 2 / (N + 1). Para EMA(20): k = 2/21 ≈ 0,095.
Cada día: EMA_hoy = Cierre_hoy × k + EMA_ayer × (1 − k)

**Ventaja:** reacciona antes a los giros del precio.
**Desventaja:** más señales falsas en mercados laterales porque se «agita» más con el ruido diario.

**¿Cuándo usar SMA y cuándo EMA?**
- Usa **EMA** para detectar cambios de tendencia rápidos (trading más activo).
- Usa **SMA** para niveles de largo plazo y como filtro de tendencia principal (inversión).
""")
                    st.markdown("---")
                    st.markdown("#### Los períodos clave y su significado institucional")
                    st.markdown("""
No todos los períodos son iguales. Los siguientes están tan extendidos que forman parte de los
sistemas automáticos de miles de fondos de inversión y algoritmos:

| Período | Plazo aproximado | Por qué importa |
|---------|----------------|----------------|
| **SMA 20** | ~1 mes | Base de las Bandas de Bollinger. Tendencia de corto plazo. Muchos traders de swing la usan como primer soporte. |
| **SMA 50** | ~2,5 meses | La más seguida por fondos para medio plazo. Una pérdida de la SMA50 es la primera señal de debilidad seria. |
| **SMA 200** | ~10 meses de trading | La referencia definitiva de largo plazo. Divide el universo de inversión en «por encima = bullish» y «por debajo = bearish». |
| **EMA 12/26** | Corto/medio plazo | Base del cálculo del MACD. Las más usadas en análisis de momentum. |

**Por qué la SMA200 es tan especial:**
Casi todos los gestores institucionales, fondos de pensiones y sistemas cuantitativos calculan
la SMA200. Cuando el precio cae hacia ella, aparece demanda institucional de forma casi automática.
Cuando la pierde, aparece presión vendedora sistemática. Es una referencia que funciona en parte
porque todos la usan — la profecía autocumplida más potente del análisis técnico.
""")
                    st.markdown("---")
                    st.markdown("#### Las señales más importantes")
                    st.markdown("""
**1. Precio vs media — el estado de la tendencia:**
- Precio sobre la media con la media subiendo → tendencia alcista confirmada en ese plazo. La media actúa como soporte dinámico.
- Precio bajo la media con la media bajando → tendencia bajista. La media actúa como resistencia dinámica.
- Precio oscilando alrededor de la media → mercado lateral sin tendencia definida.

**2. Golden Cross — la señal alcista de largo plazo:**
La SMA50 cruza la SMA200 hacia arriba. Indica que el momentum de medio plazo supera al de largo plazo.
Históricamente, precede períodos alcistas sostenidos. No funciona como señal de entrada de precisión
(llega tarde) pero confirma que el régimen de mercado ha cambiado a alcista.

**3. Death Cross — la señal bajista de largo plazo:**
La SMA50 cruza la SMA200 hacia abajo. El régimen ha pasado a bajista.
Misma lógica: señal de contexto, no de timing preciso.

**4. Precio muy alejado de la SMA200 (sobreextensión):**
Un precio un 30% o más por encima de su SMA200 está estadísticamente «lejos de casa».
Los mercados tienden a volver a sus medias (*mean reversion*). No es señal de venta, pero
sí de que los retornos esperados desde ese punto son menores que en condiciones normales.
""")
                    st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")
        with _ih3:
            _vi1, _vi2 = st.columns([5, 1])
            with _vi1:
                st.markdown('<div class="s-ind-title" style="font-size:11px;font-weight:700;color:#1e3a5f;text-transform:uppercase;letter-spacing:.6px">Volumen</div>', unsafe_allow_html=True)
            with _vi2:
                with st.popover("ℹ️", use_container_width=True):
                    st.markdown("### 📦 Volumen — Guía didáctica completa")
                    st.markdown("""
**¿Qué es el volumen y por qué es el indicador más honesto del mercado?**

El volumen es el número total de acciones (o participaciones, contratos, unidades) que han
cambiado de manos en un período determinado. A diferencia del precio — que puede ser influido
por un solo operador con mucho capital en un momento de baja liquidez — el volumen refleja la
*participación real* del mercado. No se puede falsificar: cada transacción tiene un comprador
y un vendedor, y ambos quedan registrados.

Por eso los analistas dicen que el volumen es «la gasolina» del mercado. Un movimiento de
precio sin volumen es como un coche que avanza cuesta abajo — puede ir lejos, pero sin motor
propio. Un movimiento con volumen alto tiene convicción detrás.
""")
                    st.info("**Principio fundamental:** el volumen confirma o niega el movimiento del precio. Nunca analices el precio sin mirar el volumen.")
                    st.markdown("---")
                    st.markdown("#### Las 4 combinaciones precio-volumen que debes memorizar")
                    st.markdown("""
| Precio | Volumen | Señal | Lo que está pasando |
|--------|---------|-------|---------------------|
| ⬆️ Sube | ⬆️ Alto | ✅ Alcista sólida | Los compradores están entrando con convicción. La tendencia tiene combustible. |
| ⬆️ Sube | ⬇️ Bajo | ⚠️ Alerta | El precio sube pero nadie está comprando con fuerza. La subida puede agotarse pronto. |
| ⬇️ Baja | ⬆️ Alto | ❌ Bajista seria | Los vendedores están distribuyendo (vendiendo) activamente. Señal de debilidad importante. |
| ⬇️ Baja | ⬇️ Bajo | ✅ Corrección técnica | El precio cede pero nadie está vendiendo con urgencia. Corrección sana en tendencia alcista. |

La combinación más peligrosa es la segunda: precio subiendo con volumen decreciente es la
firma clásica de una tendencia alcista que está perdiendo participantes — los inversores que
compraron antes van vendiendo mientras los nuevos van entrando. Cuando los nuevos se agoten, el
precio puede caer bruscamente aunque visualmente «todo parecía bien».
""")
                    st.markdown("---")
                    st.markdown("#### Volumen relativo — cómo leer los ratios")
                    st.markdown("""
El volumen absoluto (número de acciones) no dice nada por sí solo — hay valores que negocian
millones de acciones al día y otros que negocian miles. Lo que importa es el volumen de hoy
*en relación* al volumen habitual: el **volumen relativo**.

**Ratio vs 10 sesiones** (actividad reciente):
Compara el volumen medio de los últimos 5 días con la media de las últimas 10 sesiones.

| Ratio | Clasificación | Lo que sugiere |
|-------|--------------|----------------|
| > 200% | Excepcional | Algo importante está ocurriendo: noticias, resultados, OPA, cambio institucional |
| 150–200% | Muy alto | Participación elevada; el movimiento del precio tiene mayor credibilidad |
| 80–150% | Normal | Sesión habitual; señales con fiabilidad estándar |
| 50–80% | Bajo | Poca participación; cuidado con rupturas técnicas — pueden ser falsas |
| < 50% | Muy bajo | El mercado está dormido. Esperar antes de actuar sobre señales técnicas |

**Una ruptura de resistencia con volumen bajo es una trampa frecuente.** Los operadores
experimentados esperan ver volumen significativo para confirmar que la ruptura es real
y no un movimiento de baja liquidez.
""")
                    st.markdown("---")
                    st.markdown("#### Acumulación y Distribución — el movimiento del dinero inteligente")
                    st.markdown("""
Más allá del volumen total, importa *en qué tipo de sesiones* se concentra el volumen:
¿en días en que el precio sube (acumulación) o en días en que baja (distribución)?

**Acumulación:** el volumen se concentra en sesiones alcistas.
Indica que los inversores institucionales («dinero inteligente» — fondos, gestores, aseguradoras)
están comprando posiciones gradualmente, sin querer mover el precio de golpe. Es una señal
alcista de fondo, aunque el precio no lo muestre todavía de forma dramática.

**Distribución:** el volumen se concentra en sesiones bajistas.
Los grandes inversores están *vendiendo* sus posiciones mientras los inversores minoristas
aún compran. Es una señal bajista de fondo. El mercado puede seguir subiendo visualmente
mientras la distribución ocurre, hasta que los compradores se agotan.

*Esta lógica es la base del Método Wyckoff, desarrollado por Richard Wyckoff a principios
del siglo XX, y sigue siendo uno de los marcos de análisis más respetados para entender
el comportamiento institucional en los mercados.*
""")
                    st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

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
        with st.expander("📖 ¿Qué son los Huecos de Precio? — Guía didáctica", expanded=False):
            st.markdown("#### 📊 Huecos de Precio (*Gaps*) — Todo lo que necesitas saber")
            st.markdown("""
**¿Qué es exactamente un hueco de precio?**

Imagina que un valor cierra el lunes a 10,00 €. El martes, antes de abrir el mercado, llegan
noticias importantes (resultados empresariales, un evento macro, una noticia sectorial).
La demanda o la oferta se desplaza tanto que el valor *abre directamente a 10,50 €* — sin que
ninguna operación se haya ejecutado entre 10,00 € y 10,50 €. Ese vacío en el gráfico, esa
zona donde *no hubo ninguna transacción*, es un **hueco de precio**.

Los huecos son especialmente frecuentes en la apertura del mercado, cuando acumula toda la
información procesada fuera del horario bursátil. También aparecen en activos con baja
liquidez o en momentos de alta volatilidad como publicaciones de resultados o decisiones de
tipos de interés.
""")
            st.info("**Regla fundamental:** un hueco es una zona del gráfico donde **no se negoció** en su momento. "
                    "El mercado tiende a «volver» a esas zonas para que se produzcan esas transacciones pendientes — "
                    "de ahí la expresión popular *«los huecos se cierran»*.")
            st.markdown("---")
            st.markdown("#### 🔼 Huecos Alcistas — Soporte potencial")
            st.markdown("""
Se forman cuando el precio de **apertura** de una sesión es **superior** al máximo de la sesión anterior.
El precio «saltó hacia arriba» sin pasar por esa zona intermedia.

**¿Por qué actúan como soporte?**
Piénsalo así: todos los que compraron antes del hueco ganaron dinero de golpe. Si el precio
vuelve a bajar hacia esa zona, esos mismos inversores — que en su momento no pudieron comprar
más barato — pueden volver a comprar con convicción. Esa demanda latente convierte la zona
del hueco en un suelo natural.

**Ejemplo real:** una empresa publica resultados excelentes después del cierre. Al día siguiente
abre un 4% por encima. Semanas después, si el precio retrocede hacia esa zona, muchos inversores
que se perdieron la subida inicial entrarán comprando, frenando la caída.
""")
            st.markdown("#### 🔽 Huecos Bajistas — Resistencia potencial")
            st.markdown("""
Se forman cuando el precio de **apertura** cae **por debajo** del mínimo de la sesión anterior.
El precio «cayó en caída libre» saltándose esa zona.

**¿Por qué actúan como resistencia?**
Todos los que compraron justo antes del hueco bajista quedaron «atrapados» con pérdidas.
Cuando el precio sube de vuelta hacia esa zona, su impulso natural es vender para «recuperar»
lo perdido, lo que genera presión vendedora. Esa oferta latente convierte la zona en un techo.

**Ejemplo real:** un profit warning hace que una acción abra un 6% por debajo del cierre anterior.
Cuando semanas después el precio intenta recuperarse hacia esa zona, los inversores que compraron
antes de la caída venderán para «salir sin pérdidas», dificultando la subida.
""")
            st.markdown("---")
            st.markdown("#### 📐 Cómo leer las métricas de cada hueco")
            col_h1, col_h2, col_h3 = st.columns(3)
            with col_h1:
                st.markdown("""
**Zona del hueco (rango)**

Los dos precios que delimitan el hueco:
el mínimo y el máximo de esa zona vacía.
El hueco está «cerrado» cuando el precio
cotiza dentro de ese rango.
""")
            with col_h2:
                st.markdown("""
**Tamaño (%)**

Anchura del hueco expresada en porcentaje.
Huecos grandes (>3%) son más significativos
y tienen más fuerza como soporte/resistencia.
Huecos pequeños (<0,5%) tienen menos
relevancia técnica.
""")
            with col_h3:
                st.markdown("""
**Distancia (%)**

Qué tan lejos está el precio actual del hueco.
- Positiva (+): precio por encima del hueco.
  Si es alcista → hueco por debajo como soporte.
- Negativa (−): precio por debajo del hueco.
  Si es bajista → hueco por encima como resistencia.
""")
            st.markdown("---")
            st.markdown("#### ⏱️ El factor tiempo: ¿cuánto llevan abiertos?")
            st.markdown("""
Un hueco abierto hace **pocas sesiones** es más «fresco» y probablemente aún esté en la memoria
del mercado — mayor probabilidad de que actúe como soporte/resistencia próxima.

Un hueco abierto hace **muchos meses** puede haber perdido relevancia operativa si el precio
ha desarrollado muchas estructuras por encima o por debajo. Sin embargo, cuando el precio
llega a esa zona por primera vez, puede desencadenar reacciones importantes porque muchos
sistemas automáticos lo tienen identificado.

La herramienta muestra huecos de los últimos **252 días hábiles** (aprox. 1 año), ordenados
por distancia al precio actual — de los más próximos a los más lejanos.
""")
            st.markdown("---")
            st.markdown("#### ⚠️ Limitaciones importantes que debes conocer")
            st.warning("""
**Los huecos NO siempre se cierran.**
Aunque la estadística histórica muestra que la mayoría de huecos acaban cerrándose,
hay huecos que permanecen abiertos durante años (especialmente huecos de ruptura en
activos muy alcistas). Tratar un hueco como una garantía de movimiento es un error.

**El contexto importa más que el hueco:**
Un hueco alcista puede no actuar como soporte si la tendencia de fondo es bajista,
si hay noticias negativas, o si el volumen en la zona fue muy bajo.
Úsalo como un nivel de *atención*, no como una señal de acción automática.
""")
            st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

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

        with st.expander("📖 ¿Cómo funciona el Diagnóstico Técnico? — Guía didáctica completa", expanded=False):
            st.markdown("#### 🧭 El Diagnóstico Técnico: un cuadro de mandos para el inversor")
            st.markdown("""
El **Diagnóstico Técnico** no es una bola de cristal — es un sistema de verificación estructurado que
analiza el mismo activo desde **6 ángulos diferentes**, cada uno midiendo una dimensión distinta
del comportamiento del precio. La lógica es simple: si la mayoría de los ángulos apuntan en la misma
dirección, la señal tiene más solidez. Si se contradicen, el mercado está enviando señales mixtas y
conviene ser más prudente.

Piénsalo como el diagnóstico médico de una revisión completa: un solo indicador en zona de riesgo
no implica necesariamente un problema, pero si cinco de los seis indican lo mismo, la señal es mucho
más difícil de ignorar.
""")
            st.markdown("---")

            # Component descriptions in 2 columns
            _dc1, _dc2 = st.columns(2)

            with _dc1:
                st.markdown("##### 🏔️ Componente 1 — Máximos Históricos (ATH)")
                st.markdown("""
El **ATH** (*All-Time High*) es el precio más alto que ha alcanzado un activo en toda su historia.
Su distancia al precio actual es uno de los indicadores más potentes de análisis técnico.

**¿Por qué es tan relevante el ATH?**
Cuando un activo alcanza nuevos máximos históricos, *no hay vendedores atrapados*.
Todos los que compraron en cualquier momento de la historia están en beneficio. Esto elimina
la presión vendedora de quienes esperaban «recuperar» su inversión, creando un entorno
técnicamente muy favorable para continuar subiendo.

**Extensión de Fibonacci 127.2%:**
Cuando el precio supera el ATH, el siguiente objetivo técnico de referencia se calcula
con la extensión de Fibonacci del 127.2% sobre el rango del último ciclo bajista previo
al ATH. Es un nivel de proyección, no una garantía.

**Cómo interpretarlo:**
- Precio cerca del ATH (< 5% de distancia): zona de máxima atención. La ruptura puede ser explosiva.
- Precio muy por debajo del ATH (> 30%): el activo necesita recuperar mucho terreno antes de estar en «modo subida libre».
""")
                st.markdown("##### 📈 Componente 2 — Media Móvil 200 Sesiones (MM200)")
                st.markdown("""
La **Media Móvil de 200 sesiones** (aproximadamente 10 meses de cotización) es el indicador
de tendencia más seguido por gestores institucionales, fondos de pensiones y análisis cuantitativo
en todo el mundo.

**¿Qué mide exactamente?**
Calcula el precio medio de cierre de las últimas 200 sesiones. Su pendiente indica la dirección
de la tendencia de largo plazo; la posición del precio respecto a ella indica el régimen actual.

**La regla de los dos estados:**
- **Precio sobre MM200 con pendiente alcista:** tendencia alcista de largo plazo confirmada. Los retrocesos son oportunidades de compra para inversores con horizonte de meses.
- **Precio bajo MM200 con pendiente bajista:** tendencia bajista de largo plazo. Los rebotes son oportunidades de venta para operadores más ágiles.

**La distancia importa:**
Un precio un 30% por encima de su MM200 está «sobreextendido». Aunque la tendencia sea alcista,
la probabilidad de una corrección hacia la media es alta. No es una señal de venta, pero sí una
señal de *no comprar agresivamente*.
""")
                st.markdown("##### 🎯 Componente 3 — Resistencias Estructurales")
                st.markdown("""
Las **resistencias y soportes estructurales** son niveles de precio donde históricamente el mercado
ha reaccionado de forma repetida. Son zonas donde la oferta o la demanda han sido especialmente
intensas en el pasado.

**¿De dónde vienen estos niveles?**
Se calculan a partir de los sistemas de pivots (clásico, Fibonacci, Camarilla, Woodie, DeMark)
analizando los precios históricos. Cuando varios sistemas independientes coinciden en el mismo
nivel, ese nivel se considera **reforzado** — tiene más probabilidad de actuar como soporte o resistencia.

**Cómo leer la posición en rango:**
- Si el precio está cerca de una **resistencia reforzada**: el precio puede frenar o retroceder.
  Romperla al alza con volumen es una señal alcista poderosa.
- Si el precio está cerca de un **soporte reforzado**: zona donde la demanda puede aparecer.
  Perderlo a la baja con volumen es una señal bajista seria.
""")

            with _dc2:
                st.markdown("##### 🌀 Componente 4 — Fibonacci")
                st.markdown("""
Los **niveles de Fibonacci** en trading se basan en la observación de que los precios tienden
a retroceder en proporciones matemáticas específicas (23.6%, 38.2%, 50%, 61.8%, 78.6%) antes
de reanudar su tendencia principal.

**¿De dónde viene esto?**
La secuencia de Fibonacci (0, 1, 1, 2, 3, 5, 8, 13, 21...) genera ratios como 0.618, 0.382 o 0.236
que aparecen recurrentemente en la naturaleza y, según la observación técnica, también en los mercados.
Más allá de la explicación teórica, su poder real viene de la **profecía autocumplida**: millones de
traders los usan, lo que hace que los precios reaccionen en esos niveles.

**El swing relevante:**
El sistema detecta el swing más significativo de los últimos 252 días (el máximo y mínimo más amplios)
y calcula los niveles de retroceso entre ambos extremos.

**Escenarios clave:**
- **Retroceso al 61.8%:** el nivel más «mágico» del Fibonacci, conocido como la «ratio áurea». Un rebote aquí es muy seguido por la comunidad técnica.
- **Retroceso al 78.6%:** zona de «último cartucho». Si el precio cede este nivel, generalmente el swing completo está en riesgo.
- **Extensiones 127.2% y 161.8%:** objetivos de precio cuando el precio supera el máximo del swing y busca nuevos territorios.
""")
                st.markdown("##### 📉 Componente 5 — RSI (Índice de Fuerza Relativa)")
                st.markdown("""
El **RSI** (*Relative Strength Index*) fue creado por J. Welles Wilder en 1978 y es uno de los
indicadores de momentum más utilizados del mundo. Mide la velocidad y magnitud de los movimientos
de precio recientes, oscilando entre 0 y 100.

**La fórmula simplificada:**
Compara el promedio de subidas de los últimos 14 días con el promedio de bajadas. Un RSI alto
indica que las subidas han dominado con fuerza; un RSI bajo, que las bajadas han sido intensas.

**Las 7 zonas del RSI:**
- **RSI > 80:** Sobrecompra extrema — el activo ha subido muy rápido. Señal de agotamiento potencial.
- **RSI 70-80:** Sobrecompra — precaución para nuevas compras.
- **RSI 55-70:** Zona alcista — momentum positivo, tendencia saludable.
- **RSI 45-55:** Zona neutra — sin señal clara.
- **RSI 30-45:** Zona bajista — momentum negativo.
- **RSI 20-30:** Sobreventa — posible agotamiento vendedor.
- **RSI < 20:** Sobreventa extrema — caída muy intensa, posible rebote técnico.

**Las divergencias — la señal más potente:**
Una *divergencia alcista* ocurre cuando el precio hace un mínimo más bajo pero el RSI hace un
mínimo más alto. Indica que el momentum bajista se está agotando aunque el precio siga cayendo.
La *divergencia bajista* es la contraria: precio sube a nuevos máximos pero el RSI no los confirma.
Las divergencias son señales de alerta temprana — no predicen el giro exacto, pero avisan de que
el movimiento actual pierde fuerza interna.
""")
                st.markdown("##### 📦 Componente 6 — Volumen Relativo y Acumulación/Distribución")
                st.markdown("""
El **volumen** es «la munición» del mercado. Un movimiento de precio con alto volumen tiene
mucha más credibilidad que el mismo movimiento con volumen escaso.

**Volumen relativo (5d vs 20d):**
Compara el volumen medio de las últimas 5 sesiones con el de las últimas 20 sesiones.
Un ratio > 150% indica que el interés reciente es inusualmente alto — algo está pasando.
Un ratio < 50% indica mercado dormido, con pocas manos activas.

**Acumulación vs. Distribución:**
Analiza si el volumen está dominado por sesiones alcistas (acumulación — los grandes inversores
están comprando) o bajistas (distribución — los grandes inversores están vendiendo).

- **Acumulación:** el dinero «inteligente» (fondos, institucionales) está entrando. Señal alcista de fondo.
- **Distribución:** el dinero «inteligente» está saliendo mientras los minoristas aún compran. Señal bajista de fondo.

*El análisis de acumulación/distribución es una de las técnicas del Método Wyckoff, desarrollado
por Richard Wyckoff a principios del siglo XX y aún vigente como marco de análisis institucional.*
""")

            st.markdown("---")
            st.markdown("#### 🎯 La Puntuación Técnica Integrada — cómo se calcula")
            st.markdown("""
La **Puntuación Técnica** (0-10) agrega los 6 componentes en una única métrica ponderada.
Cada componente tiene un peso diferente según su relevancia estadística:
""")
            _pw1, _pw2, _pw3 = st.columns(3)
            with _pw1:
                st.markdown("""
| Componente | Peso |
|---|---|
| MM200 | 20% |
| RSI | 20% |
| ATH | 15% |
""")
            with _pw2:
                st.markdown("""
| Componente | Peso |
|---|---|
| Fibonacci | 15% |
| Resistencias | 15% |
| Volumen | 15% |
""")
            with _pw3:
                st.markdown("""
**Interpretación:**
- **≥ 6.5** → Señal alcista
- **3.5 – 6.5** → Señal neutral
- **≤ 3.5** → Señal bajista

La convicción (0-6) mide
cuántos componentes
apuntan en la dirección
de la señal mayoritaria.
""")
            st.warning("""
**Importante — el Diagnóstico Técnico no es una señal de compra/venta:**
Todos los componentes de este diagnóstico son indicadores *rezagados* o *contemporáneos* — describen
lo que **ha ocurrido**, no lo que **ocurrirá**. Una puntuación alta indica que las condiciones técnicas
*actuales* son favorables según el análisis histórico, pero el futuro depende de factores que ningún
indicador técnico puede anticipar: noticias, cambios macro, liquidez, comportamiento de grandes inversores.
Úsalo como un filtro de contexto, no como un oráculo.
""")
            st.caption("Análisis educativo · No constituye asesoramiento personalizado de inversión bajo MiFID II")

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



        # ── Componente 5: RSI Zona / Tendencia / Divergencia ─────────────
        if analisis_rsi:
            _ri = analisis_rsi
            _esc_ri = _ri["escenario"]
            _colores_ri = {
                "sobrecompra_extrema": ("#fef2f2", "#991b1b", "🔴", "SOBRECOMPRA EXTREMA (RSI >80)"),
                "sobrecompra":         ("#fef2f2", "#dc2626", "⬆️", "SOBRECOMPRA (RSI 70–80)"),
                "zona_alcista":        ("#f0fdf4", "#16a34a", "📈", "ZONA ALCISTA (RSI 55–70)"),
                "zona_neutra":         ("#f8fafc", "#64748b", "↔️", "ZONA NEUTRA (RSI 45–55)"),
                "zona_bajista":        ("#fff7ed", "#c2410c", "📉", "ZONA BAJISTA (RSI 30–45)"),
                "sobreventa":          ("#eff6ff", "#1d4ed8", "⬇️", "SOBREVENTA (RSI 20–30)"),
                "sobreventa_extrema":  ("#eff6ff", "#1e3a8a", "🔵", "SOBREVENTA EXTREMA (RSI <20)"),
            }
            _bg_ri, _col_ri, _ico_ri, _lab_ri = _colores_ri.get(
                _esc_ri, ("#f8fafc", "#64748b", "📊", _esc_ri.upper())
            )

            # Si hay divergencia, matiz especial en el borde
            if _ri["divergencia"] == "bajista":
                _col_ri = "#dc2626"
            elif _ri["divergencia"] == "alcista":
                _col_ri = "#16a34a"

            _tend_icon = {"subiendo": "↑", "bajando": "↓", "lateral": "→"}.get(
                _ri["tendencia"], "→"
            )
            _div_label = {
                "alcista": "✅ Divergencia alcista",
                "bajista": "⚠️ Divergencia bajista",
            }.get(_ri["divergencia"], "Ninguna")

            _c1_ri, _c2_ri, _c3_ri = st.columns(3)
            with _c1_ri:
                st.metric(
                    "RSI (14 períodos)",
                    f"{_ri['rsi_val']:.1f}",
                    help="Relative Strength Index calculado sobre 14 sesiones. "
                         "Zona sobrecompra >70 · Zona sobreventa <30"
                )
            with _c2_ri:
                st.metric(
                    "Tendencia RSI",
                    f"{_tend_icon} {_ri['tendencia'].capitalize()}",
                    delta=f"{_ri['trend_diff']:+.1f} pts (5 ses.)",
                    delta_color="normal" if _ri["trend_diff"] >= 0 else "inverse",
                    help="Variación del RSI respecto a 5 sesiones atrás"
                )
            with _c3_ri:
                st.metric(
                    "Divergencia precio-RSI",
                    _div_label,
                    help="Divergencia bajista: precio en máximos pero RSI no confirma. "
                         "Divergencia alcista: precio en mínimos pero RSI no confirma."
                )
            st.markdown(
                f'<div style="background:{_bg_ri};border-left:4px solid {_col_ri};'
                f'border-radius:6px;padding:12px 16px;margin-top:8px;">'
                f'<span style="font-weight:700;color:{_col_ri};">'
                f'{_ico_ri} RSI — {_lab_ri}</span><br/>'
                f'<p style="margin:6px 0 0 0;font-size:0.92rem;color:#374151;">'
                f'{_ri["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.caption("Datos insuficientes para calcular el RSI.")

        st.divider()



        # ── Componente 6: Volumen Relativo / Acumulación-Distribución ────
        if analisis_vol:
            _v = analisis_vol
            _esc_v = _v["escenario"]
            _colores_v = {
                "volumen_excepcional": ("#fdf4ff", "#7e22ce", "🔊", "VOLUMEN EXCEPCIONAL"),
                "volumen_alto":        ("#eff6ff", "#1d4ed8", "📶", "VOLUMEN ALTO"),
                "volumen_normal":      ("#f8fafc", "#64748b", "📊", "VOLUMEN NORMAL"),
                "volumen_bajo":        ("#fff7ed", "#c2410c", "🔉", "VOLUMEN BAJO"),
                "volumen_seco":        ("#fef2f2", "#dc2626", "🔇", "VOLUMEN SECO"),
            }
            _bg_v, _col_v, _ico_v, _lab_v = _colores_v.get(
                _esc_v, ("#f8fafc", "#64748b", "📊", _esc_v.upper())
            )
            _acc_label = {
                "acumulacion": "✅ Acumulación",
                "distribucion": "⚠️ Distribución",
                "neutral":     "↔️ Neutral",
            }.get(_v["acc_dist"], "—")
            _acc_color = {
                "acumulacion": "normal",
                "distribucion": "inverse",
                "neutral": "off",
            }.get(_v["acc_dist"], "off")

            _c1_v, _c2_v, _c3_v = st.columns(3)
            with _c1_v:
                st.metric(
                    "Vol. relativo (5d/20d)",
                    f"{_v['vol_rel']:.0f}%",
                    delta=f"{_v['vol_rel']-100:+.0f}% vs media",
                    delta_color="normal" if _v["vol_rel"] >= 100 else "inverse",
                    help="Media de volumen de las últimas 5 sesiones como % de la media de 20 sesiones. "
                         "100 % = igual a la media histórica reciente."
                )
            with _c2_v:
                st.metric(
                    "Media vol. 5 días",
                    f"{_v['vol_5d']:,.0f}",
                    help="Volumen medio de las últimas 5 sesiones"
                )
            with _c3_v:
                st.metric(
                    "Flujo 10 sesiones",
                    _acc_label,
                    delta_color=_acc_color,
                    help="Señal de acumulación/distribución: compara el volumen en días alcistas "
                         "vs bajistas en las últimas 10 sesiones. ≥62% alcista = acumulación · "
                         "≤38% alcista = distribución."
                )
            st.markdown(
                f'<div style="background:{_bg_v};border-left:4px solid {_col_v};'
                f'border-radius:6px;padding:12px 16px;margin-top:8px;">'
                f'<span style="font-weight:700;color:{_col_v};">'
                f'{_ico_v} VOLUMEN — {_lab_v}</span><br/>'
                f'<p style="margin:6px 0 0 0;font-size:0.92rem;color:#374151;">'
                f'{_v["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.caption("Datos de volumen no disponibles para este valor.")

        st.divider()



        # ── Componente 7: Puntuación Técnica Integrada ───────────────────
        puntuacion_tec = puntuacion_tec  # variable local ya calculada
        if puntuacion_tec:
            _pt = puntuacion_tec
            _score = _pt["score_total"]
            _señal = _pt["señal"]

            _cfg_señal = {
                "alcista": ("#f0fdf4", "#16a34a", "🟢", "SESGO ALCISTA"),
                "neutral": ("#f8fafc", "#64748b", "⚪", "ZONA NEUTRAL"),
                "bajista": ("#fef2f2", "#dc2626", "🔴", "SESGO BAJISTA"),
            }
            _bg_pt, _col_pt, _ico_pt, _lab_pt = _cfg_señal.get(
                _señal, ("#f8fafc", "#64748b", "⚪", "NEUTRAL")
            )

            # Score en formato grande
            _c1_pt, _c2_pt, _c3_pt = st.columns(3)
            with _c1_pt:
                st.metric(
                    "Puntuación Técnica",
                    f"{_score:.1f} / 10",
                    help="Media ponderada de los 6 componentes del Diagnóstico Técnico. "
                         "0–3.5 = bajista · 3.5–6.5 = neutral · 6.5–10 = alcista"
                )
            with _c2_pt:
                st.metric(
                    "Señal",
                    f"{_ico_pt} {_señal.capitalize()}",
                    help="Señal técnica agregada basada en la puntuación total"
                )
            with _c3_pt:
                st.metric(
                    "Convicción",
                    f"{_pt['conviccion']}/{_pt['disp_total']} componentes",
                    help="Número de componentes que coinciden con la señal dominante"
                )

            # Tarjeta narrativa
            st.markdown(
                f'<div style="background:{_bg_pt};border-left:4px solid {_col_pt};'
                f'border-radius:6px;padding:12px 16px;margin-top:8px;">'
                f'<span style="font-weight:700;color:{_col_pt};">'
                f'🎯 DIAGNÓSTICO TÉCNICO INTEGRADO — {_lab_pt}</span><br/>'
                f'<p style="margin:6px 0 0 0;font-size:0.92rem;color:#374151;">'
                f'{_pt["texto"]}</p>'
                f'</div>',
                unsafe_allow_html=True
            )

            # ── Botón de explicación ──────────────────────────────────
            with st.expander("📖 ¿Cómo se calcula esta puntuación?"):
                st.markdown(
                    "La puntuación técnica integrada es una **media ponderada** de los "
                    "6 componentes del Diagnóstico Técnico. Cada componente aporta una "
                    "puntuación de **0 a 10** según su escenario actual, y se pondera "
                    "por su relevancia en el análisis técnico multi-método."
                )

                # Tabla de desglose
                import pandas as _pd_score
                _filas = []
                for _k, _info in _pt["scores_ind"].items():
                    _disp = "✅" if _info["disponible"] else "—"
                    _pts_str = str(_info["puntos"]) if _info["disponible"] else "—"
                    _peso_str = f"{_info['peso']*100:.0f}%"
                    _contrib_str = f"{_info['contrib']:.2f}" if _info["disponible"] else "—"
                    _filas.append({
                        "Componente":    _info["icono"] + " " + _info["nombre"],
                        "Escenario":     _info["escenario"].replace("_", " ").title(),
                        "Puntos (0-10)": _pts_str,
                        "Peso":          _peso_str,
                        "Contribucion":  _contrib_str,
                        "Datos":         _disp,
                    })
                _df_score = _pd_score.DataFrame(_filas)
                st.dataframe(_df_score, hide_index=True, use_container_width=True)

                st.markdown("**Rangos de señal:**")
                st.markdown(
                    "- Rojo **0.0 – 3.4** Sesgo bajista  "
                    "- Blanco **3.5 – 6.4** Zona neutral  "
                    "- Verde **6.5 – 10** Sesgo alcista"
                )
                st.markdown("**Puntuaciones por escenario — referencia rápida:**")
                _tabla_ref = {
                    "Componente":        ["ATH", "SMA200", "Resistencias", "Fibonacci", "RSI", "Volumen"],
                    "Bajista (1-3)":     [
                        "Lejos del maximo",
                        "Tendencia bajista",
                        "En resistencia / sin soporte",
                        "Swing roto / retroceso 78.6%",
                        "Sobrecompra extrema / zona bajista",
                        "Volumen seco",
                    ],
                    "Neutro (4-6)":      [
                        "Aproximandose",
                        "Plana",
                        "Zona media",
                        "Retrocesos medios",
                        "Zona neutra",
                        "Normal",
                    ],
                    "Alcista (7-9)":     [
                        "En ATH / Subida libre",
                        "Tendencia / Giro alcista",
                        "En soporte / sin resistencia",
                        "Extension / zona dorada",
                        "Zona alcista / sobreventa",
                        "Alto / excepcional",
                    ],
                }
                import pandas as _pd2
                st.dataframe(_pd2.DataFrame(_tabla_ref), hide_index=True, use_container_width=True)
                st.caption(
                    "Analisis educativo. No constituye asesoramiento personalizado "
                    "de inversion bajo MiFID II. El analisis tecnico no predice "
                    "el comportamiento futuro de los precios."
                )

        st.divider()




        # ── Bloque 4: Datos Fundamentales ────────────────────────────────
        st.markdown("### Datos Fundamentales")
        if tipo_activo == "etf":
            st.markdown(
                '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
                'padding:10px 16px;color:#64748b;font-size:0.85rem;margin-bottom:12px">'
                '⚠️ <strong>No aplica</strong> — Los ETFs no tienen análisis fundamental propio '
                '(PER, BPA, capitalización, etc.). Compara por TER, AUM y rentabilidad histórica.'
                '</div>',
                unsafe_allow_html=True
            )
            # ── Comparativa de categoría ──────────────────────────────────
            _cat_etf = _ETFS_CATEGORIA.get(ticker_activo)
            if _cat_etf:
                st.markdown(f"#### 🏆 Comparativa — {_cat_etf}")
                _comp = obtener_comparativa_etf(_cat_etf, ticker_activo)
                # Encabezado
                _hc = st.columns([2.2, 1, 1, 1.2, 1.4, 1.2])
                for _col, _lbl in zip(_hc, ["ETF", "TER", "Política", "AUM", "Rentab. 1A", "Índice"]):
                    _col.markdown(f"<span style='font-size:0.75rem;color:#64748b;font-weight:600'>{_lbl}</span>",
                                  unsafe_allow_html=True)
                for _e in _comp:
                    _bg  = "background:#eff6ff;border-radius:6px;padding:2px 4px" if _e["actual"] else ""
                    _tag = " ⬅️" if _e["actual"] else ""
                    _ter_str  = f"{_e['ter']:.2f}%" if _e["ter"] is not None else "—"
                    _aum_str  = (_fmt_numero(_e["aum"]) if _e["aum"] else "—")
                    _r1a_str  = (f"{_e['rent_1a']:+.1f}%" if _e["rent_1a"] is not None else "—")
                    _r1a_col  = "#166534" if (_e["rent_1a"] or 0) > 0 else "#991b1b"
                    _dist_badge = (
                        '<span style="background:#dcfce7;color:#166534;font-size:0.7rem;'
                        'padding:1px 6px;border-radius:10px;font-weight:600">Acc</span>'
                        if _e["dist"] == "Acumulación" else
                        '<span style="background:#dbeafe;color:#1e40af;font-size:0.7rem;'
                        'padding:1px 6px;border-radius:10px;font-weight:600">Dist</span>'
                    )
                    _rc = st.columns([2.2, 1, 1, 1.2, 1.4, 1.2])
                    _rc[0].markdown(
                        f'<div style="{_bg}"><span style="font-weight:{"700" if _e["actual"] else "400"}'
                        f';font-size:0.85rem">{_e["nombre_corto"]}{_tag}</span></div>',
                        unsafe_allow_html=True)
                    _rc[1].markdown(f'<span style="font-size:0.85rem;font-weight:700;color:#0f172a">{_ter_str}</span>',
                                    unsafe_allow_html=True)
                    _rc[2].markdown(_dist_badge, unsafe_allow_html=True)
                    _rc[3].markdown(f'<span style="font-size:0.82rem">{_aum_str}</span>',
                                    unsafe_allow_html=True)
                    _rc[4].markdown(
                        f'<span style="font-size:0.85rem;font-weight:600;color:{_r1a_col}">{_r1a_str}</span>',
                        unsafe_allow_html=True)
                    _rc[5].markdown(f'<span style="font-size:0.75rem;color:#64748b">{_e["indice"]}</span>',
                                    unsafe_allow_html=True)
                st.caption("Ordenado por TER (menor = más barato). AUM y rentabilidad 1A desde Yahoo Finance.")
        elif fundamentales:
            fund_items = [(k, v) for k, v in fundamentales.items() if v != "—"]
            st.markdown('<div class="fund-metrics">', unsafe_allow_html=True)
            cols_f = st.columns(5)
            for i, (k, v) in enumerate(fund_items):
                with cols_f[i % 5]:
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
                            analisis_ath=analisis_ath,
                            analisis_sma200=analisis_sma200,
                            analisis_resist=analisis_resist,
                            analisis_fibo=analisis_fibo,
                            analisis_rsi=analisis_rsi,
                            analisis_vol=analisis_vol,
                            puntuacion_tec=puntuacion_tec,
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
                            analisis_ath=analisis_ath,
                            analisis_sma200=analisis_sma200,
                            analisis_resist=analisis_resist,
                            analisis_fibo=analisis_fibo,
                            analisis_rsi=analisis_rsi,
                            analisis_vol=analisis_vol,
                            puntuacion_tec=puntuacion_tec,
                        )
                    st.download_button(
                        label="📄 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"{ticker_activo}_{ts}.pdf",
                        mime="application/pdf",
                        key="dl_pdf",
                    )

    # ---- ALERTAS DE PRECIO ----
    with tab_analisis:
        _u_id = usuario.get("id")
        analizado = "estrategia_data" in st.session_state
        # Recuperar precio y ticker desde session_state cuando analizado es True
        if analizado and not "precio" in dir():
            _ed_al2 = st.session_state.get("estrategia_data", {})
            precio        = _ed_al2.get("precio", 0.0)
            ticker_activo = _ed_al2.get("ticker", "")
            nombre        = _ed_al2.get("nombre", "")
        # Verificar alertas disparadas con el precio actual
        if analizado and precio and _u_id:
            _disp = verificar_y_disparar_alertas(_u_id, ticker_activo, precio)
            for _da in _disp:
                _cond_txt = "superó" if _da["condicion"] == "above" else "bajó de"
                st.toast(f"🔔 ALERTA: {_da['ticker']} {_cond_txt} {float(_da['nivel']):.4f}", icon="🔔")
                st.warning(
                    f"**🔔 Alerta disparada:** {_da.get('descripcion') or _da['ticker']} — "
                    f"precio {_cond_txt} **{float(_da['nivel']):.4f}** "
                    f"(actual: {precio:.4f})",
                    icon="🔔"
                )

        with st.expander("🔔 Alertas de precio", expanded=False):
            if not _u_id:
                st.info("Inicia sesión para usar alertas.")
            else:
                st.markdown("**Nueva alerta**")
                _al1, _al2, _al3, _al4 = st.columns([2, 1.5, 1.5, 1])
                with _al1:
                    _al_ticker = st.text_input("Ticker", value=ticker_activo if analizado else "",
                                               key="al_ticker").upper().strip()
                with _al2:
                    _al_nivel = st.number_input("Nivel de precio",
                                                value=float(precio) if (analizado and precio) else 0.0,
                                                format="%.4f", step=0.01, key="al_nivel")
                with _al3:
                    _al_cond = st.selectbox("Condición",
                                            ["Por encima de (≥)", "Por debajo de (≤)"],
                                            key="al_cond")
                with _al4:
                    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                    _al_btn = st.button("➕ Añadir", key="al_add_btn", use_container_width=True)
                _al_desc = st.text_input("Descripción (opcional)", key="al_desc",
                                          placeholder="Ej: Resistencia clave / soporte SMA200")

                if _al_btn:
                    if not _al_ticker:
                        st.error("Introduce un ticker.")
                    elif _al_nivel <= 0:
                        st.error("El nivel debe ser mayor que 0.")
                    else:
                        _al_cond_val = "above" if "encima" in _al_cond else "below"
                        _al_nombre = nombre if (analizado and _al_ticker == ticker_activo) else _al_ticker
                        _ok = crear_alerta_precio(_u_id, _al_ticker, _al_nombre,
                                                  _al_nivel, _al_cond_val, _al_desc)
                        if _ok:
                            st.success(f"✅ Alerta creada: {_al_ticker} {'≥' if _al_cond_val=='above' else '≤'} {_al_nivel:.4f}")
                            st.rerun()
                        else:
                            st.error("Error al crear la alerta. Revisa la conexión a BD.")

                st.divider()

                # Niveles sugeridos desde pivots
                if analizado and _al_ticker == ticker_activo and "estrategia_data" in st.session_state:
                    _ed_al = st.session_state["estrategia_data"]
                    _pv_al = _ed_al.get("resultados_pivots", {})
                    _sug_niveles = []
                    for _sys_al, _pdata_al in _pv_al.items():
                        if isinstance(_pdata_al, dict):
                            for _k_al, _v_al in _pdata_al.items():
                                if isinstance(_v_al, (int, float)) and _v_al > 0:
                                    _sug_niveles.append((_k_al, float(_v_al), _sys_al))
                    if _sug_niveles:
                        _sug_niveles.sort(key=lambda x: abs(x[1] - precio))
                        st.markdown("**Niveles sugeridos** (los más próximos al precio actual)")
                        _sg_cols = st.columns(5)
                        for _si, (_sk, _sv, _ss) in enumerate(_sug_niveles[:10]):
                            with _sg_cols[_si % 5]:
                                _dist_al = (_sv - precio) / precio * 100
                                _dist_col = "#22c55e" if _dist_al >= 0 else "#ef4444"
                                st.markdown(
                                    f'<div style="border:1px solid #e2e8f0;border-radius:6px;'
                                    f'padding:6px 8px;text-align:center;font-size:11px;margin-bottom:4px">'
                                    f'<b style="font-size:12px">{_sv:.4f}</b><br>'
                                    f'<span style="color:#64748b">{_sk}</span><br>'
                                    f'<span style="color:{_dist_col}">{_dist_al:+.2f}%</span>'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )

                # Alertas activas
                st.markdown("**Mis alertas activas**")
                _alertas_all = obtener_alertas_usuario(_u_id, solo_activas=True)
                if not _alertas_all:
                    st.caption("Sin alertas activas. Crea una arriba.")
                else:
                    _ah = st.columns([1.5, 1.5, 2, 1.5, 1.5, 2, 1])
                    for _hdr, _txt in zip(_ah, ["Ticker", "Nivel", "Condición", "Tipo", "Creada", "Descripción", ""]):
                        _hdr.markdown(f"**{_txt}**")
                    for _aal in _alertas_all:
                        _ac = st.columns([1.5, 1.5, 2, 1.5, 1.5, 2, 1])
                        _ac[0].markdown(f"`{_aal['ticker']}`")
                        _ac[1].markdown(f"{float(_aal['nivel']):.4f}")
                        _cond_lbl = "Precio ≥ nivel" if _aal["condicion"] == "above" else "Precio ≤ nivel"
                        _ac[2].markdown(_cond_lbl)
                        _ac[3].markdown(_aal.get("descripcion") or "—")
                        _fec = _aal.get("creada_en")
                        _ac[4].markdown(str(_fec)[:10] if _fec else "—")
                        _ac[5].markdown("—")
                        if _ac[6].button("🗑️", key=f"del_al_{_aal['id']}", help="Desactivar alerta"):
                            desactivar_alerta(_aal["id"])
                            st.rerun()

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
                        use_container_width=True,
                    )
                    _ts_val = st.session_state.get("est_inf_ts", "")
                    if _ts_val:
                        st.caption(f"Generado: {_ts_val}")

    # ---- TAB IA ----
    with tab_ia:
        st.info("🤖 Análisis IA — próximamente disponible.")

    # ---- TAB MACRO ----
    with tab_macro:
        pestaña_macro()

    # ---- TAB RENTA FIJA ----
    with tab_rf:
        pestaña_renta_fija()

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

**Confluencia** — Cuando niveles de distintos timeframes coinciden. Mayor fiabilidad.

---
**Sistemas disponibles:**
- **Clásico** — El más universal. Base para todos los demás.
- **Woodie** — Doble peso al cierre. Mejor en días con gap.
- **Camarilla** — 8 niveles muy cerca del precio. Operativa intradía.
- **DeMark** — Condicional según dirección del día anterior.
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
