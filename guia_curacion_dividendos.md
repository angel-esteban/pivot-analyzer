# 📖 Guía de curación de dividendos — con ejemplo de Naturgy

Esta guía explica **cómo curar a mano** los datos de dividendo del *golden record* y **por qué** se hace así. La usamos como referencia cada vez que damos de alta o corregimos un valor.

---

## 1. La idea en una frase

El screening de dividendos necesita saber **cuánto renta un valor** y **si ese dividendo es sostenible**. Esas dos preguntas se responden con **dos lentes** distintas, y ambas se apoyan en datos que hay que **curar a mano desde fuentes oficiales**, porque el proveedor automático (yfinance) no los da bien o no los distingue.

- **Lente A — Renta:** ¿cuánto me da al año? → por **año natural**.
- **Lente B — Cobertura (payout):** ¿es sostenible? → por **ejercicio contable**.

---

## 2. Las tres reglas de oro

1. **Sin fuente, no vale.** Toda fila de BPA o de dividendo necesita `fuente` + `fecha de verificación` + `quién`. Un dato sin procedencia se rechaza.
2. **El BPA NUNCA sale de yfinance.** Solo de **CNMV / informe anual / IR** de la empresa. yfinance solo se usa como *contraste* (sanity check), nunca como valor.
3. **Ausente = N/A, nunca cero ni inventado.** Si no tienes el dato verificado, **no crees la fila**. El motor lo tratará como "evaluación incompleta", que es honesto; un número supuesto sería engañoso.

> No confundas **dividendo** con **BPA**. El "1,77 €/acción de 2025" de Naturgy es el **dividendo**, no el beneficio por acción. El payout = dividendo ÷ BPA.
>
> Y se cura **el último ejercicio cerrado y auditado**: a julio de 2026 es **FY2025** (cerrado el 31-dic-2025, cuentas publicadas en febrero de 2026), no 2024.

---

## 3. El flujo

**Formulario en pantalla → validación → Neon (fuente del motor).** Tú rellenas los formularios de *Administración → Curación dividendos*; al guardar, se valida y se escribe **directo a "vigente"** con versionado. Editar un dato **no lo sobrescribe**: crea una versión nueva y retira la anterior (así un run antiguo sigue siendo reproducible).

---

## 4. Los tres formularios

### 4.1. Ficha de empresa
Identidad del emisor. Campos clave:
- `ticker` (formato `XXX.MC`), `nombre`.
- `cierre_ejercicio`: la fecha de cierre contable. **No todas cierran en diciembre** (Logista 30-sep, Inditex 31-ene). Naturgy: **31-dic**.
- `clase_exclusion`: `estandar` (métricas normales) · `banca_seguros` (payout/EV-EBITDA/D-E no aplican) · `reit_socimi` (FCF/EV-EBITDA no aplican).

### 4.2. BPA por ejercicio (el eslabón débil)
- `bpa_auditado`: beneficio **por acción** del ejercicio, del **informe anual / CNMV**. Se permite **negativo** (Telefónica lo tiene).
- `fuente`: obligatoria y oficial. Se rechaza `yfinance` o "estimación".
- Al guardar, se muestra la **reconciliación**: el payout que resultaría vs el `payoutRatio` de yfinance. Si divergen más de **10 puntos**, se marca `[VERIFICAR]` y baja la confianza (no bloquea, pero avisa).

### 4.3. Clasificación de dividendos
- Los **importes y fechas** salen de los eventos observados (yfinance); tú añades la **clasificación**:
  - `tipo`: `ordinario` / `extraordinario` / `scrip`. Por defecto, todo es **ordinario** salvo que lo marques.
  - `con_cargo_a_ejercicio`: a qué ejercicio se imputa el dividendo (aunque se pague después).
- **Scrip:** registra solo la parte en **efectivo** como importe.
- Regla: `importe > 0`, `ex_date ≤ pay_date`.

---

## 5. "Con cargo" vs "pagado en el año" (importante)

Son dos ventanas distintas, **a propósito**:
- **Renta (Lente A):** cuenta los dividendos **pagados** dentro del año natural (caja real). Puede mezclar dos ejercicios; es correcto.
- **Payout (Lente B):** cuenta el dividendo **con cargo** al ejercicio ÷ el BPA **de ese mismo ejercicio**. **No** se divide la caja del año natural entre el BPA de un solo ejercicio — sería un error conceptual.

---

## 6. Ejemplo trabajado — Naturgy (NTGY.MC)

### Paso 1 · Ficha de empresa
| Campo | Valor |
|---|---|
| ticker | `NTGY.MC` |
| nombre | Naturgy Energy Group, S.A. |
| cierre_ejercicio | `31-dic` |
| sector | Utilities |
| clase_exclusion | `estandar` |

### Paso 2 · BPA FY2025 (el último ejercicio cerrado y auditado)
- A julio de 2026 el ejercicio a curar es **FY2025** (cerrado el 31-dic-2025; cuentas publicadas en febrero de 2026). Curar 2024 sería meter un dato viejo.
- Beneficio neto 2025 de Naturgy: **2.023 M€** (récord). Con ~969,6 M de acciones sale **≈ 2,09 €/acción**.
- ⚠️ Ese ≈2,09 € es un **cálculo de sanity check**, no la cifra auditada. Coge el **"Beneficio por acción"** exacto del **Informe Financiero Anual 2025 (CNMV)** (puede ser **mayor**: en 2025 Naturgy hizo una autoopa que reduce el nº de acciones y sube el BPA).
- `fuente`: *Naturgy — Informe Financiero Anual 2025 (CNMV)* · `confianza`: alta.

### Paso 3 · Dividendos con cargo a 2025
- El dividendo **con cargo a 2025** es **1,77 €/acción**, todo **ordinario**, en tres pagos:
  - 0,60 € (pagado 30-jul-2025)
  - 0,60 € (pagado 3-nov-2025)
  - 0,57 € complementario (Junta ~24-mar-2026, **pagado en 2026**)
- Crea una fila por cada pago: `tipo = ordinario`, `con_cargo_a_ejercicio = FY2025`, con su `ex_date` e importe. La suma = 1,77 €.
- 👀 El complementario se **paga en 2026** pero es **con cargo a 2025** — justo el concepto de la §5: la **renta** lo contaría en 2026; el **payout**, en 2025.

### Resultado — Lente B
**Payout ordinario FY2025 = 1,77 ÷ ≈2,09 ≈ 85%.** Está **justo en el borde** del cap K1-Payout (85–100%): aquí el **BPA exacto decide** si Naturgy queda "Cumple" o "Parcial". Es el mejor ejemplo de por qué el BPA se cura del informe auditado y no se aproxima. (Comparación: Logista ~99% sí se degrada a "Parcial".)

### Paso 3 (detalle) · Las ex-dates reales y una trampa

Los **importes y ex-dates** salen de los eventos observados (yfinance). Para Naturgy, los pagos **con cargo a FY2025** son tres:

| ex_date | importe € | tipo | con_cargo |
|---|---|---|---|
| 2025-07-28 | 0,60 | ordinario | FY2025 |
| 2025-11-03 | 0,60 | ordinario | FY2025 |
| 2026-03-27 | 0,57 | ordinario | FY2025 |

Suma = **1,77 €**.

**⚠️ Trampa:** existe otro pago de **0,60 € con ex-date 2025-04-07** que **NO va aquí** — es el **complementario de FY2024** (se abona en abril de 2025 tras la Junta de 2024). Con cargo a **FY2024**, no a 2025. Meterlo en 2025 inflaría el payout.

**Con cargo vs pagado en el año, en números (Naturgy):**
- **Renta 2025 (Lente A, año natural)** = lo pagado en 2025 = 0,60 (abr, de FY2024) + 0,60 (jul) + 0,60 (nov) = **1,80 €**.
- **Payout FY2025 (Lente B, con cargo)** = 0,60 (jul) + 0,60 (nov) + 0,57 (mar-2026) = **1,77 €**.

Son cifras distintas **a propósito**: 1,80 € es la caja del año natural; 1,77 € es lo devengado contra el beneficio de 2025. Cada una alimenta su lente.

---

## 7. Qué hace el motor con esto (los tres estados del payout)

- **`ok`** → payout = ordinario con cargo ÷ BPA auditado. Gobierna la sostenibilidad (cap K1-Payout).
- **`no_interpretable`** → BPA ≤ 0 (p. ej. Telefónica): el payout no es interpretable → KO, no un error.
- **`n/a` (transitorio)** → aún sin BPA curado. **No penaliza la nota**, pero **impide el veredicto "Cumple"** ("Parcial · evaluación incompleta"). Distinto del **N/A estructural** de banca/SOCIMIs, que sí puede ser "Cumple" porque el criterio genuinamente no aplica.

---

## 8. Checklist rápido al curar un valor

- [ ] Ficha de empresa creada, con el **cierre de ejercicio correcto**.
- [ ] BPA del ejercicio, del **informe anual/CNMV**, con fuente y fecha.
- [ ] Reconciliación revisada (si `[VERIFICAR]`, confirmar contra el informe antes de promover).
- [ ] Dividendos clasificados (ordinario/extra/scrip) con su `con_cargo_a_ejercicio`.
- [ ] Nada de placeholders: lo que no esté verificado, se deja sin crear.

---

*Fuentes del ejemplo Naturgy: nota de resultados 2025 (beneficio neto 2.023 M€) y página de dividendos de Naturgy (naturgy.com); verifica siempre el BPA en el Informe Financiero Anual en la CNMV.*
