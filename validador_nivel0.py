"""
validador_nivel0.py — Validación de saneamiento (nivel 0) del screener.

Se ejecuta ANTES de cachear (niveles 1-2) o de puntuar (nivel 3). Resuelve dos
problemas de la extracción de yfinance:

  1. Ausente != cero. yfinance devuelve 0 / None / campo ausente de forma
     ambigua. Un payoutRatio de 0 puede significar "no reparte" o "no hay dato",
     y son cosas opuestas. Aquí el dato ausente se marca AUSENTE (-> NULL en BD),
     nunca como 0.
  2. Rangos de plausibilidad. Un valor fuera del rango razonable del campo
     (p.ej. payout 900 %, beta 40) se marca SOSPECHOSO y no se acepta como bueno.

Devuelve, por campo, el valor saneado y su estado. La capa de ingesta usa esos
estados para rellenar `valido` / `motivo_invalidez` en Neon y aplicar la política
de fallo del screener.

Módulo puro: sin dependencias de Streamlit ni yfinance. Testeable en aislamiento.
Ref. de diseño: DISENO_Persistencia_Datos_Screener.md (secciones 3, 5 y 6).

Importante sobre unidades: el validador espera valores en su unidad canónica
(decimales para ratios/porcentajes, como entrega yfinance.info y las funciones
calcular_*). La normalización porcentaje<->decimal es responsabilidad de la capa
de cálculo, no de este validador.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Estados y tipos
# ─────────────────────────────────────────────────────────────────────────────
class Estado(str, Enum):
    OK = "ok"                 # valor presente y dentro de rango
    AUSENTE = "ausente"       # sin dato -> NULL en BD (jamás 0)
    SOSPECHOSO = "sospechoso" # presente pero fuera de rango / tipo inválido


# Tokens que yfinance u otras fuentes usan para "sin dato".
_TOKENS_AUSENTE = {"", "none", "nan", "n/a", "na", "null", "-", "--", "—"}


@dataclass(frozen=True)
class FieldSpec:
    """Especificación de validación de un campo."""
    campo: str
    nivel_dato: str = "fundamental"          # estructural | fundamental | mercado
    tipo_valor: str = "ratio"                # ratio|porcentaje|moneda|entero|booleano|texto
    nullable: bool = True
    rango_valido: tuple[float, float] | None = None   # (min, max) inclusive; None = sin chequeo
    cero_sospechoso: bool = False            # True si 0 casi siempre significa "sin dato"


@dataclass
class ResultadoCampo:
    campo: str
    valor: Any                # valor saneado (None si AUSENTE o SOSPECHOSO)
    estado: Estado
    motivo: str | None = None
    valor_crudo: Any = None   # lo que entró, para trazabilidad


@dataclass
class ResultadoRegistro:
    """Resultado agregado de validar todos los campos de un ticker."""
    ticker: str
    valores: dict[str, Any] = field(default_factory=dict)         # {campo: valor_saneado}
    resultados: dict[str, ResultadoCampo] = field(default_factory=dict)
    valido: bool = True                                            # False si hay algún SOSPECHOSO
    motivo_invalidez: str | None = None

    def para_bd(self) -> dict[str, Any]:
        """Devuelve el dict listo para el UPSERT: valores + valido + motivo_invalidez."""
        return {**self.valores, "valido": self.valido,
                "motivo_invalidez": self.motivo_invalidez}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _es_ausente(v: Any) -> bool:
    """True si el valor representa 'sin dato'. OJO: 0 / 0.0 / False NO son ausentes."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):     # NaN de pandas/numpy
        return True
    if isinstance(v, str) and v.strip().lower() in _TOKENS_AUSENTE:
        return True
    return False


def _a_numero(v: Any) -> float | None:
    """Coacciona a float. Devuelve None si no es numérico (se tratará como SOSPECHOSO)."""
    if isinstance(v, bool):          # bool es subclase de int: no lo tratamos como número aquí
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", "."))
        except ValueError:
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Validación de un campo
# ─────────────────────────────────────────────────────────────────────────────
def validar_campo(valor_crudo: Any, spec: FieldSpec) -> ResultadoCampo:
    """Valida un único valor contra su especificación. No lanza excepciones."""
    # 1) Ausente (antes que nada: ausente != cero)
    if _es_ausente(valor_crudo):
        return ResultadoCampo(spec.campo, None, Estado.AUSENTE,
                              "sin dato en la fuente", valor_crudo)

    # 2) Texto y booleano: validación ligera
    if spec.tipo_valor == "texto":
        s = str(valor_crudo).strip()
        if not s:
            return ResultadoCampo(spec.campo, None, Estado.AUSENTE, "texto vacío", valor_crudo)
        return ResultadoCampo(spec.campo, s, Estado.OK, None, valor_crudo)

    if spec.tipo_valor == "booleano":
        if isinstance(valor_crudo, bool):
            return ResultadoCampo(spec.campo, valor_crudo, Estado.OK, None, valor_crudo)
        s = str(valor_crudo).strip().lower()
        if s in {"true", "1", "si", "sí", "yes"}:
            return ResultadoCampo(spec.campo, True, Estado.OK, None, valor_crudo)
        if s in {"false", "0", "no"}:
            return ResultadoCampo(spec.campo, False, Estado.OK, None, valor_crudo)
        return ResultadoCampo(spec.campo, None, Estado.SOSPECHOSO,
                              f"no es booleano: {valor_crudo!r}", valor_crudo)

    # 3) Numéricos
    num = _a_numero(valor_crudo)
    if num is None:
        return ResultadoCampo(spec.campo, None, Estado.SOSPECHOSO,
                              f"no es numérico: {valor_crudo!r}", valor_crudo)
    if math.isinf(num):
        return ResultadoCampo(spec.campo, None, Estado.SOSPECHOSO, "valor infinito", valor_crudo)

    # 3a) Cero como sentinela de "sin dato" para campos donde 0 es implausible
    if spec.cero_sospechoso and num == 0:
        return ResultadoCampo(spec.campo, None, Estado.SOSPECHOSO,
                              "0 implausible para este campo (probable dato ausente)", valor_crudo)

    # 3b) Rango de plausibilidad
    if spec.rango_valido is not None:
        lo, hi = spec.rango_valido
        if not (lo <= num <= hi):
            return ResultadoCampo(spec.campo, None, Estado.SOSPECHOSO,
                                  f"fuera de rango [{lo}, {hi}]: {num}", valor_crudo)

    # 3c) Entero: redondeo seguro
    if spec.tipo_valor == "entero":
        num = int(round(num))

    return ResultadoCampo(spec.campo, num, Estado.OK, None, valor_crudo)


# ─────────────────────────────────────────────────────────────────────────────
# Validación de un registro completo (un ticker)
# ─────────────────────────────────────────────────────────────────────────────
def validar_registro(ticker: str, datos_crudos: dict[str, Any],
                     specs: dict[str, FieldSpec]) -> ResultadoRegistro:
    """
    Valida todos los campos conocidos de un ticker.

    - Solo procesa campos presentes en `specs`; ignora claves desconocidas.
    - `valido` global = False si algún campo queda SOSPECHOSO (un AUSENTE no
      invalida el registro: simplemente va como NULL).
    - El valor saneado se guarda para todos los estados; en AUSENTE/SOSPECHOSO es None.
    """
    res = ResultadoRegistro(ticker=ticker)
    motivos: list[str] = []

    for campo, spec in specs.items():
        rc = validar_campo(datos_crudos.get(campo), spec)
        res.resultados[campo] = rc
        res.valores[campo] = rc.valor
        if rc.estado is Estado.SOSPECHOSO:
            res.valido = False
            motivos.append(f"{campo}: {rc.motivo}")

    res.motivo_invalidez = "; ".join(motivos) if motivos else None
    return res


# ─────────────────────────────────────────────────────────────────────────────
# Specs por defecto (campos reales del screener)
# Rangos según DISENO_Persistencia_Datos_Screener.md §3.2 — afinar con datos reales.
# Unidades canónicas: ratios y porcentajes en decimal (0.75 = 75 %).
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_SPECS: dict[str, FieldSpec] = {
    # ── Nivel 1: estructural ──
    "sector":      FieldSpec("sector", "estructural", "texto", nullable=False),
    "free_float_pct": FieldSpec("free_float_pct", "estructural", "porcentaje",
                                rango_valido=(0, 100)),
    "annualReportExpenseRatio": FieldSpec("annualReportExpenseRatio", "estructural",
                                          "ratio", rango_valido=(0, 0.05), cero_sospechoso=True),
    "totalAssets": FieldSpec("totalAssets", "estructural", "moneda",
                             rango_valido=(0, 5e13), cero_sospechoso=True),
    # ── Nivel 2: fundamental ──
    "payoutRatio":       FieldSpec("payoutRatio", "fundamental", "ratio", rango_valido=(0, 5)),
    "debtToEquity":      FieldSpec("debtToEquity", "fundamental", "ratio", rango_valido=(0, 1000)),
    "enterpriseToEbitda":FieldSpec("enterpriseToEbitda", "fundamental", "ratio",
                                   rango_valido=(-50, 100), cero_sospechoso=True),
    "revenueGrowth":     FieldSpec("revenueGrowth", "fundamental", "porcentaje", rango_valido=(-2, 2)),
    "grossMargins":      FieldSpec("grossMargins", "fundamental", "porcentaje", rango_valido=(-2, 2)),
    "operatingMargins":  FieldSpec("operatingMargins", "fundamental", "porcentaje", rango_valido=(-2, 2)),
    "returnOnEquity":    FieldSpec("returnOnEquity", "fundamental", "porcentaje", rango_valido=(-2, 2)),
    "pegRatio":          FieldSpec("pegRatio", "fundamental", "ratio",
                                   rango_valido=(-10, 50), cero_sospechoso=True),
    "earningsGrowth":    FieldSpec("earningsGrowth", "fundamental", "porcentaje", rango_valido=(-5, 5)),
    "marketCap":         FieldSpec("marketCap", "fundamental", "moneda",
                                   rango_valido=(0, 5e13), cero_sospechoso=True),
    "beta":              FieldSpec("beta", "fundamental", "ratio",
                                   rango_valido=(-5, 5), cero_sospechoso=True),
    "bpa":               FieldSpec("bpa", "fundamental", "moneda", rango_valido=(-1e4, 1e4)),
    "fcf_yield":         FieldSpec("fcf_yield", "fundamental", "porcentaje", rango_valido=(-1, 1)),
    "cagr_dividendo_5y": FieldSpec("cagr_dividendo_5y", "fundamental", "porcentaje", rango_valido=(-1, 5)),
    "anos_div_consec":   FieldSpec("anos_div_consec", "fundamental", "entero", rango_valido=(0, 100)),
    # ── Nivel 3: mercado (se valida igual antes de puntuar, no se persiste) ──
    "dividend_yield_ttm":FieldSpec("dividend_yield_ttm", "mercado", "porcentaje", rango_valido=(0, 0.15)),
}


# Mapa: tipo_valor declarado en criteria.json -> default razonable si falta rango.
_TIPO_RANGO_FALLBACK = {
    "porcentaje": (-2, 2),
    "ratio": (-1000, 1000),
}


def cargar_specs_desde_criteria(ruta: str | Path) -> dict[str, FieldSpec]:
    """
    Construye las specs a partir de criteria.json.

    - Si el criterio ya tiene los metadatos tipados (nivel_dato, rango_valido,
      tipo_valor, nullable), los usa.
    - Si no, cae en DEFAULT_SPECS por nombre de campo; y si tampoco está, deriva
      un spec mínimo del tipo declarado. Así el módulo funciona tanto con el
      criteria.json actual como con el extendido.

    Clave de indexado, según cómo fluye el dato:
      - Campos crudos de yfinance.info (sin `funcion`) -> por `campo` (p.ej. payoutRatio).
      - Criterios calculados (`fuente: calculado` o con `funcion`) -> por `id`, porque
        varios pueden derivar del mismo campo origen (p.ej. dividend_yield,
        historial_dividendo y crecimiento_dividendo comparten campo "dividends").
    """
    data = json.loads(Path(ruta).read_text(encoding="utf-8"))
    specs: dict[str, FieldSpec] = {}

    for cartera in data.get("carteras", {}).values():
        for cr in cartera.get("criterios", []):
            es_calculado = bool(cr.get("funcion")) or cr.get("fuente") == "calculado"
            clave = cr.get("id") if es_calculado else (cr.get("campo") or cr.get("id"))
            if not clave or clave in specs:
                continue

            if "rango_valido" in cr or "nivel_dato" in cr:   # criteria.json ya tipado
                rango = cr.get("rango_valido")
                specs[clave] = FieldSpec(
                    campo=clave,
                    nivel_dato=cr.get("nivel_dato", "fundamental"),
                    tipo_valor=cr.get("tipo_valor", "ratio"),
                    nullable=cr.get("nullable", True),
                    rango_valido=tuple(rango) if rango else None,
                    cero_sospechoso=cr.get("cero_sospechoso", False),
                )
            elif clave in DEFAULT_SPECS:                      # default conocido
                specs[clave] = DEFAULT_SPECS[clave]
            else:                                             # derivar mínimo
                tipo = "texto" if cr.get("operador") == "in_list" else "ratio"
                specs[clave] = FieldSpec(
                    campo=clave, tipo_valor=tipo,
                    rango_valido=None if tipo == "texto" else _TIPO_RANGO_FALLBACK.get(tipo),
                )

    # Completa con cualquier default no referenciado en criteria.json.
    for clave, spec in DEFAULT_SPECS.items():
        specs.setdefault(clave, spec)
    return specs


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    casos = {
        "ACX.MC": {  # Acerinox: payout alto pero plausible, datos OK
            "sector": "Basic Materials", "payoutRatio": 2.21,
            "debtToEquity": 45.0, "marketCap": 2_500_000_000, "beta": 1.3,
        },
        "TEF.MC": {  # Telefónica: payout >100 % (plausible, no sospechoso), BPA negativo
            "sector": "Communication Services", "payoutRatio": 1.11,
            "bpa": -0.42, "debtToEquity": 280.0, "marketCap": 22_000_000_000,
        },
        "FALLO.MC": {  # yfinance devuelve basura/ausencias
            "sector": None,            # ausente -> NULL
            "payoutRatio": 0,          # 0 legítimo (no sospechoso): no reparte
            "marketCap": 0,            # 0 implausible -> SOSPECHOSO
            "beta": 42.0,              # fuera de rango -> SOSPECHOSO
            "debtToEquity": float("nan"),  # NaN -> AUSENTE
            "returnOnEquity": "n/a",   # token ausente
        },
    }
    specs = DEFAULT_SPECS
    for tk, datos in casos.items():
        r = validar_registro(tk, datos, specs)
        print(f"\n=== {tk}  valido={r.valido}  motivo={r.motivo_invalidez}")
        for campo, rc in r.resultados.items():
            if rc.valor_crudo is not None or rc.estado is not Estado.AUSENTE or campo in datos:
                marca = {"ok": "  ", "ausente": "··", "sospechoso": "!!"}[rc.estado.value]
                print(f"  {marca} {campo:22} crudo={rc.valor_crudo!r:>18} -> "
                      f"{rc.estado.value:11} valor={rc.valor!r}")
