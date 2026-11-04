"""
arnes_tests_pa.py — Carga las funciones REALES de app.py para los tests de regresión,
sin arrancar Streamlit ni tocar red/BBDD.

app.py importa Streamlit y ejecuta la UI a nivel de módulo, así que no se puede importar
tal cual. Este arnés parsea app.py (ast), ejecuta SOLO las sentencias de nivel superior
que definen cosas (imports, funciones, clases, asignaciones) y se salta las que pintan UI
(if/with/expr/for). Las librerías ausentes o con efectos (streamlit, yfinance, psycopg2,
plotly...) se sustituyen por un objeto permisivo. Así los tests ejercitan el código de
producción, no un espejo de su lógica.

Uso:
    from arnes_tests_pa import cargar_app, simular_screening
    app = cargar_app()
    app["pivot_camarilla"](110, 100, 105)
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

_RUTA_APP = Path(__file__).with_name("app.py")
_CACHE: dict | None = None


class _Permisivo:
    """Objeto que acepta cualquier atributo/llamada. Usado como decorador, devuelve la
    función decorada intacta (@st.cache_data, @st.cache_data(ttl=0), @st.dialog(...))."""
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _n):
        return _Permisivo()

    def __call__(self, *a, **k):
        if len(a) == 1 and not k and callable(a[0]) and not isinstance(a[0], _Permisivo):
            return a[0]
        return _Permisivo()

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def __contains__(self, _x):
        return False

    def __getitem__(self, _k):
        return _Permisivo()

    def __setitem__(self, _k, _v):
        pass

    def get(self, _k, d=None):
        return d


def _modulo_falso(nombre: str) -> types.ModuleType:
    m = types.ModuleType(nombre)
    m.__getattr__ = lambda _n: _Permisivo()          # type: ignore[attr-defined]
    return m


def cargar_app(forzar: bool = False) -> dict:
    """Devuelve el namespace con las definiciones de app.py (cacheado)."""
    global _CACHE
    if _CACHE is not None and not forzar:
        return _CACHE
    # Streamlit siempre falso: así nunca se pinta nada aunque esté instalado.
    _st = _modulo_falso("streamlit")
    _st.session_state = {}                           # type: ignore[attr-defined]
    _prev_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = _st
    src = _RUTA_APP.read_text(encoding="utf-8")
    arbol = ast.parse(src)
    ns: dict = {"__name__": "app_bajo_test", "__file__": str(_RUTA_APP)}
    try:
        for nodo in arbol.body:
            if not isinstance(nodo, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef, ast.Assign,
                                     ast.AnnAssign)):
                continue                              # UI / efectos a nivel de módulo
            codigo = compile(ast.Module(body=[nodo], type_ignores=[]), str(_RUTA_APP), "exec")
            try:
                exec(codigo, ns)
            except Exception:
                # Import ausente o asignación con efectos: se liga a un objeto permisivo.
                if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                    for alias in nodo.names:
                        ns[(alias.asname or alias.name).split(".")[0]] = _Permisivo()
                elif isinstance(nodo, ast.Assign):
                    for t in nodo.targets:
                        if isinstance(t, ast.Name):
                            ns.setdefault(t.id, _Permisivo())
    finally:
        if _prev_st is not None:
            sys.modules["streamlit"] = _prev_st
    _CACHE = ns
    return ns


# ─────────────────────────────────────────────────────────────────────────────
# Simulación de un ticker para el screener de dividendos (sin red ni BBDD)
# ─────────────────────────────────────────────────────────────────────────────
def serie_dividendos(dpa_ultimo: float, anios: int = 12, crecimiento: float = 0.05):
    """Un pago anual en junio, creciendo `crecimiento` al año, hasta el año pasado.
    El año pasado paga exactamente `dpa_ultimo`. Índice tz-aware (como yfinance)."""
    import datetime as _dt
    import pandas as pd
    fin = _dt.datetime.now(_dt.timezone.utc).year - 1
    fechas, importes = [], []
    for k in range(anios):
        anio = fin - (anios - 1 - k)
        fechas.append(pd.Timestamp(f"{anio}-06-15", tz="Europe/Madrid"))
        importes.append(dpa_ultimo / ((1 + crecimiento) ** (anios - 1 - k)))
    return pd.Series(importes, index=pd.DatetimeIndex(fechas), name="Dividends")


def historico_diario(precio: float, sesiones: int = 252, volumen: float = 1_000_000):
    """OHLCV diario sintético (tz Madrid) que termina en `precio`, con rango ±10 %."""
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=sesiones, tz="Europe/Madrid")
    close = np.linspace(precio * 0.9, precio, sesiones)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": np.full(sesiones, float(volumen))}, index=idx)


def info_sana(dpa: float = 0.80, bpa: float = 1.60, sector: str = "Industrials",
              industry: str = "Conglomerates", yield_obj: float = 0.04, **extra) -> dict:
    """info de yfinance con TODOS los criterios de dividendos en OK.
    yield = dpa/precio = yield_obj; payout = dpa/bpa; FCF yield = 2 × yield."""
    precio = dpa / yield_obj
    acciones = 1_000_000_000
    mcap = precio * acciones
    info = {
        "longName": "Valor de prueba", "sector": sector, "industry": industry,
        "regularMarketPrice": precio, "currentPrice": precio, "previousClose": precio,
        "trailingAnnualDividendRate": dpa, "dividendRate": dpa,
        "trailingAnnualDividendYield": dpa / precio,
        "trailingEps": bpa, "payoutRatio": (dpa / bpa) if bpa else None,
        "marketCap": mcap, "sharesOutstanding": acciones, "floatShares": acciones * 0.6,
        "freeCashflow": mcap * yield_obj * 2,
        "debtToEquity": 80.0, "enterpriseToEbitda": 10.0,
        "enterpriseValue": mcap * 1.3, "ebitda": mcap * 1.3 / 10.0,
        "averageVolume": 30_000_000 / precio,
    }
    info.update(extra)
    return info


def simular_screening(info: dict, dividendos=None, criterios: list | None = None,
                      historico=None, neon: dict | None = None, neon_fecha=None) -> dict:
    """Ejecuta el _evaluar_ticker_screening REAL con fuentes simuladas.
    - info: lo que devolvería yfinance .info ({} = Yahoo bloqueado, 401 Invalid Crumb).
    - historico: DataFrame OHLCV que devolvería Ticker.history() (endpoint sin crumb).
    - neon: dict con forma de info que devolvería repositorio.componer_info (por defecto vacío,
      como un ticker aún no ingerido); neon_fecha = fecha del nivel estructural."""
    import json
    app = cargar_app()
    if criterios is None:
        ruta = _RUTA_APP.with_name("criteria.json")
        criterios = json.loads(ruta.read_text(encoding="utf-8"))["carteras"]["dividendos"]["criterios"]
    if dividendos is None:
        dividendos = serie_dividendos(float(info.get("trailingAnnualDividendRate") or 0.8))

    class _TickerFalso:
        def __init__(self, _t):
            self.dividends = dividendos
            self.cashflow = None

        def history(self, *a, **k):
            return historico

    yf_falso = _modulo_falso("yfinance")
    yf_falso.Ticker = _TickerFalso                   # type: ignore[attr-defined]
    repo_falso = _modulo_falso("repositorio")
    _neon = dict(neon or {})
    _fresc = {"estructural": {"estado": "ok", "actualizado_en": neon_fecha, "valido": True}} if neon_fecha else {}
    repo_falso.componer_info = lambda *_a, **_k: (dict(_neon), dict(_fresc), set())   # type: ignore[attr-defined]

    guardado = {k: sys.modules.get(k) for k in ("yfinance", "repositorio")}
    viejos = {k: app.get(k) for k in ("_yf_info_con_retry", "get_db_connection",
                                      "release_db_connection")}
    sys.modules["yfinance"] = yf_falso
    sys.modules["repositorio"] = repo_falso
    app["_yf_info_con_retry"] = lambda _t, *a, **k: dict(info)
    app["get_db_connection"] = lambda: object()
    app["release_db_connection"] = lambda _c: None
    try:
        return app["_evaluar_ticker_screening"]("TEST.MC", criterios)
    finally:
        for k, v in guardado.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        app.update(viejos)
