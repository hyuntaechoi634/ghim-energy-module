# GHIM Energy Module — Economy Design

## 1. Production Structure

### Nesting Tree

```
Q  = CES(KLE, M;  σ_{KLE,M})          Gross output
│
├── KLE = CES(KL, E;  σ_{KL,E})       Energized factor services
│   │
│   ├── KL = TFP × CES(K, L;  σ_{KL})   Factor services
│   │
│   └── E = CES(EL, NEL;  σ_{EL,NEL})    Energy composite
│
└── M                                   Materials
```

### Equations

Factor services:

$$KL = TFP(t) \times CES\bigl(K(t),\; L(t);\; \sigma_{KL}\bigr)$$

Energy composite:

$$E = CES\bigl(EL,\; NEL;\; \sigma_{EL,NEL}\bigr)$$

Energized factor services:

$$KLE = CES\bigl(KL,\; E;\; \sigma_{KL,E}\bigr)$$

Gross output:

$$Q = CES\bigl(KLE,\; M;\; \sigma_{KLE,M}\bigr)$$

where the CES function is:

$$CES(X_1, X_2;\; \sigma) = \bigl[\alpha_1 \, X_1^{\rho} + \alpha_2 \, X_2^{\rho}\bigr]^{1/\rho}, \quad \rho = \frac{\sigma - 1}{\sigma}$$


## 2. Variable Determination

### 2.1 Factor Services (KL)

**K(t)** — Capital stock (state variable).

$$K(t+\Delta t) = (1-\delta)^{\Delta t} \cdot K(t) + I_K \cdot \Delta t$$

Initialized at base year from Penn World Table (PWT 10.01) real capital stock (`rkna`, in 2017 national prices → converted to $2020). Alternatively, from capital-output ratio: $K_0 = \kappa \cdot Y_0$.

**L(t)** — Labor (exogenous).

$$L(t) = Pop(t) \times LFP$$

Population from SSP. Labor force participation rate (LFP) from ILO 2020, region-specific, time-invariant in Phase 1. PWT employment (`emp`) used for base-year cross-check.

**TFP(t)** — Total factor productivity (calibrated). See §4.

**KL** is computed directly from K, L, TFP. No iteration needed.


### 2.2 Energy (E, p_E)

**E** — Energy composite (EJ). Determined by CES first-order condition at the KL–E nest:

$$E = E_{base} \times \frac{KL}{KL_{base}} \times \left(\frac{p_E}{p_{E,base}}\right)^{-\sigma_{KL,E}}$$

This is an **isoelastic demand function** derived from the CES first-order condition (cost minimization at the KL–E nest). It is the macro-level total energy demand, distributed to final demand sectors (Industry, Buildings, Transport, Agriculture, Bunkers) via income/price-driven sectoral demand functions. Sectoral demands are scaled to match the CES total.

**EL, NEL** — Electricity and non-electric energy (EJ). Determined by the energy module bottom-up:

- EL = sum of electricity demand across all final demand sectors
- NEL = sum of non-electric carrier demands (refined liquids, gas, coal, hydrogen, heat, solids)

The EL/NEL split from bottom-up is reconciled with the CES-implied split. At macro level, the CES E-nest determines the relative price sensitivity between EL and NEL (σ_{EL,NEL} > 1 means substitutes → electrification possible).

**p_E** — Composite energy price ($/GJ). Expenditure-weighted average:

$$p_E = \frac{\sum_c p_c \times E_c}{\sum_c E_c}$$

where:

- $p_{EL}$ = weighted LCOE from electricity sector (17 generation technologies)
- $p_{NEL}$ = expenditure-weighted price across non-electric carriers

Both are determined endogenously by the energy module within the price iteration loop.


### 2.3 Materials (M, p_M)

**Phase 1**: Exogenous.

$$M = m \cdot Q$$

Materials scale proportionally with gross output. The coefficient $m$ is calibrated from base-year input-output data (intermediate input share of gross output). See §4.5.

Since M scales with Q and Q depends on M, this is resolved within the fixed-point iteration:

```
Iteration: given M_guess → Q = CES(KLE, M_guess) → M_new = m × Q → damped update
```

With $\sigma_{KLE,M} \approx 0$ (near-Leontief), M is nearly proportional to Q, so this converges in 1–2 iterations.

**p_M** — Materials price.

Phase 1: exogenous, constant in real terms. Phase 3: endogenous from industry/materials sector.

**Phase 3+**: M becomes endogenous, connected to industry subsectors (steel, cement, chemicals). p_M determined by materials market clearing.


### 2.4 Gross Output (Q)

$$Q = CES\bigl(KLE,\; M;\; \sigma_{KLE,M}\bigr)$$

Q is the total value of goods and services produced. It includes intermediate inputs (energy, materials). Q ≠ GDP.


### 2.5 Net Output / GDP (Y)

$$Y = Q - p_E \cdot E - p_M \cdot M$$

This is the **national accounting definition of value added**. Y = GDP. Intermediate input costs are subtracted from gross output.

**Same-period response** (WITCH-style): When energy prices rise in period t, $p_E \cdot E$ increases, so $Y$ falls immediately — even though $KL = TFP \times CES(K,L)$ is unchanged. This is the key mechanism for energy price → GDP feedback within the same period.


## 3. Capital Accumulation and Budget Constraint

### Budget Constraint

$$I_K = s \cdot Y - I_{E} - \sum_i I_{RND,i}$$

| Term | Meaning | Phase 1 default |
|------|---------|-----------------|
| $s$ | Savings rate (fraction of GDP) | 0.22 (global, from PWT mean gross capital formation share) |
| $Y$ | Net output = GDP (not gross output Q) | — |
| $I_{E}$ | Energy sector investment (vintage stock gap-fill × capex) | Endogenous |
| $\sum_i I_{RND,i}$ | Technology RND spending across all families | Phase 1: exogenous (IEA RD&D) |
| $I_K$ | General capital investment (residual) | $= s \cdot Y - I_E - \sum I_{RND}$ |
| $\delta$ | Depreciation rate | 0.05 (standard literature value; cross-check with PWT `delta`) |

Energy and RND investment crowd out general capital: expensive energy transition → higher $I_{E} + \sum I_{RND}$ → lower $I_K$ → slower capital accumulation → lower future GDP.

### Capital Accumulation

$$K(t+\Delta t) = (1-\delta)^{\Delta t} \cdot K(t) + I_K \cdot \Delta t$$

### GDP Impact Channels

Energy price increase in period t:

| Channel | Timing | Mechanism |
|---------|--------|-----------|
| **Cost channel** | **Same period** | $p_E \uparrow \Rightarrow Y = Q - p_E \cdot E \downarrow$ |
| **Investment crowd-out** | Same period (I), next period (K) | $I_E + \sum I_{RND} \uparrow \Rightarrow I_K \downarrow \Rightarrow K(t+1) \downarrow$ |
| **Capital accumulation** | Next period onward | $K \downarrow \Rightarrow KL \downarrow \Rightarrow Q \downarrow \Rightarrow Y \downarrow$ |

Materials price increase: same mechanism via $p_M \cdot M$ term.


## 4. Calibration

### 4.1 Elasticities of Substitution (σ)

| Parameter | Nest | Phase 1 default | Range in literature | Key references |
|-----------|------|-----------------|---------------------|----------------|
| $\sigma_{KL}$ | K–L | **0.80** | 0.5–1.0 | Oberfield & Raval 2021 (*Econometrica*) |
| $\sigma_{KL,E}$ | KL–E | **0.40** | 0.3–0.5 | EPPA (MIT), GCAM, WITCH |
| $\sigma_{EL,NEL}$ | EL–NEL | **2.0** | 1.5–3.0 | Zhu et al. 2023, GTAP-E |
| $\sigma_{KLE,M}$ | KLE–M | **0.20** | 0.0–0.5 | Koesler & Schymura 2015 |

Phase 1 defaults are mid-range literature values. Final calibration via sensitivity analysis and cross-validation with SSP reference runs.

### 4.2 CES Share Parameters (α)

Calibrated from base-year cost shares at each nest level.

At each nest $CES(X_1, X_2; \sigma)$:

$$s_i = \frac{p_i \cdot X_i}{\sum_j p_j \cdot X_j}, \quad \alpha_i = \frac{s_i \cdot p_i^{\sigma - 1}}{\sum_j s_j \cdot p_j^{\sigma - 1}}$$

Note: when base-year prices are normalized to $p_i = 1$ (numeraire convention), this simplifies to $\alpha_i = s_i$.

Required base-year data:

| Nest | Inputs | Prices needed |
|------|--------|---------------|
| K–L | $K_0, L_0$ | $r_0 = \alpha_{cap} \cdot Y_0 / K_0$, $w_0 = (1-\alpha_{cap}) \cdot Y_0 / L_0$ |
| KL–E | $KL_0, E_0$ (EJ × $p_{E,base}$ for value units) | $p_{KL} = 1.0$ (numeraire), $p_E$ from energy module |
| EL–NEL | $EL_0, NEL_0$ | $p_{EL,0}$, $p_{NEL,0}$ from energy module |
| KLE–M | $KLE_0, M_0$ | $p_{KLE} = 1.0$, $p_{M,0}$ exogenous |

### 4.3 CES Scale Factor

$$A_{CES} = \frac{Q_{base}}{CES_{raw}(KLE_{base}, M_{base})}$$

Ensures $Q = Q_{base}$ at calibration year.

### 4.4 TFP Trajectory

TFP(t) is calibrated so that in the **reference scenario** (no policy, SSP exogenous), the model reproduces the SSP GDP path exactly.

For each future period:

1. Evolve reference K: $K_{ref}(t) = (1-\delta)^{\Delta t} \cdot K_{ref}(t-1) + I_{ref} \cdot \Delta t$
   - $I_{ref} = s \cdot Y_{SSP}(t-1) - I_{energy,ref}$
2. Compute reference E, M from base-year ratios scaled by income
3. Find TFP(t) such that:
   $$Y_{SSP}(t) = Q(t) - p_{E,ref} \cdot E_{ref}(t) - p_{M,ref} \cdot M_{ref}(t)$$
   where $Q(t) = CES\bigl(KLE(TFP(t)), M_{ref}(t)\bigr)$

Ratio-based iteration: $TFP \leftarrow TFP \times Y_{SSP} / Y_{model}$. Converges in 1–2 steps per period.

### 4.5 Materials Coefficient

$$m = \frac{p_{M,base} \cdot M_{base}}{Q_{base}}$$

The intermediate input share of non-energy materials in gross output.

**Phase 1 default**: $m = 0.45$ (global). Derived from OECD STAN, GTAP v10, and WIOD non-energy intermediate input shares (total intermediate ~0.50–0.53 of gross output, minus energy cost share ~0.05–0.08). This gives GDP/GO $\approx 0.48$, consistent with real-world global averages. Manufacturing-heavy regions (China, India) ~0.47–0.51, service-heavy (US, EU) ~0.35–0.40. Phase 1 uses the global average. Phase 2+: regionalized from GTAP extraction. Phase 3: endogenous via industry subsectors.


## 5. Solver Integration

### 5.1 Exogenous vs Endogenous Economy

The economy module supports two modes, controlled by a single configuration toggle:

| | Endogenous (default) | Exogenous (option) |
|---|---|---|
| **GDP** | $Y_r$ solved via CES production function | $Y_r = Y_{SSP,r}(t)$ — taken as given |
| **Y in state vector?** | Yes (32 additional dims) | No |
| **TFP role** | Calibrated to match SSP GDP exactly; policy shocks cause Y ≠ Y_SSP | Same calibration, SSP GDP reproduced exactly |
| **Energy → GDP feedback** | Full (energy prices → Y via cost + crowd-out channels) | None (one-way: GDP → energy demand) |
| **Use case** | Policy analysis, carbon pricing, energy transition scenarios | Baseline runs, energy-only analysis, debugging |

Endogenous GDP is the default. Switching to exogenous mode is a configuration change, not a code change. The CES production function is always computed; in exogenous mode, its Y is simply overwritten by SSP.

### 5.2 State Vector

Full state vector (endogenous economy):

$$x = \bigl[\underbrace{Y_r,\; I_{E,r},\; p_{elec,r},\; p_{H_2,r}}_{4 \times 32 = 128},\; \underbrace{p^W_{coal},\; p^W_{oil},\; p^W_{gas},\; p^W_{bio},\; p^W_{U}}_{5}\bigr] \in \mathbb{R}^{133}$$

In exogenous mode, $Y_r$ is removed from the state vector → $\mathbb{R}^{101}$ (3×32 + 5).

### 5.3 Economy Module Pass

Within the period-by-period solver, the economy module operates as follows:

```
For each period t:
  1. Set TFP(t), K(t), L(t)          [given]
  2. KL = TFP × CES(K, L)            [factor services, computed once]

  Price iteration loop:
    3. E = E_base × (KL/KL_base) × (pE/pE_base)^(-σ_{KL,E})   [CES FOC]
    4. Distribute E to sectors → sectoral demands               [energy module]
    5. Supply: electricity, refining, hydrogen → new prices      [energy module]
    6. pE = Σ(p_c × E_c) / Σ(E_c)                              [expenditure-weighted price]
    7. M = m × Q (with inner iteration if needed)                [materials demand]
    8. Q = CES(KLE, M)                                          [gross output]
    9. Y = Q − pE·E − pM·M                                     [net output = GDP]
    10. Check convergence → repeat or exit

  After convergence:
    11. I_K = s × Y − I_E − Σ_i I_RND,i                         [budget constraint]
    12. K(t+Δt) = (1−δ)^Δt × K(t) + I_K × Δt                  [capital update]
```

**Convergence criterion**: $\max_i |x_i^{(n+1)} - x_i^{(n)}| / |x_i^{(n)}| < \epsilon$, with $\epsilon = 10^{-4}$.

Solved via damped fixed-point iteration: $x^{(n+1)} = (1-\alpha)\,x^{(n)} + \alpha\,F(x^{(n)})$. See `solver.md` for details on solution methods (damped iteration, Anderson acceleration).


## 6. Phased Implementation

| Component | Phase 1 | Phase 2 | Phase 3+ |
|-----------|---------|---------|----------|
| K–L | CES, Cobb-Douglas calibration | Same | Same |
| E | EL/NEL split, CES | + Energy services (R&D substitutes for E) | Same |
| M | Exogenous ($M = m \cdot Q$) | Same | Endogenous (industry sectors) |
| $p_E$ | From energy module | + Green finance (tech-specific WACC) | Same |
| $p_M$ | Exogenous | Same | Materials market clearing |
| Budget | $I_K = sY - I_E - \sum I_{RND}$ | Same | + Government, fiscal policy |
| Labor | Exogenous (Pop × LFP) | Same | + Labor market frictions |
| Economy mode | Endogenous (CES, default) | Same | Same |


## 7. Data Sources

All economy data comes from **gcamdata** (already aggregated to R32) or SSP databases.

| Variable | Source | gcamdata location | Notes |
|----------|--------|-------------------|-------|
| $K_0$ | PWT 10.01 `rkna` | `inst/extdata/socioeconomics/PWT/pwt1001.csv` | Real capital stock, 2017 national prices |
| $L_0$ | PWT 10.01 `emp` | Same file | Employment (millions), cross-check only |
| Pop(t) | SSP database | `ghim/data/external/ssp/SSP_database_2024.csv.gz` | SSP1–5, by R32 |
| GDP(t) | SSP database (GDP\|PPP) | Same file | For TFP calibration + exog mode |
| LFP | ILO 2020 | Hardcoded per R32 | Time-invariant in Phase 1 |
| $E_0$, $p_{E,0}$ | IEA via gcamdata | `L1xx` energy balance chunks | Base-year energy quantities + prices |
| $\alpha_{cap}$ | PWT `labsh` | `pwt1001.csv` column `labsh` | Capital share = $1 - labsh$ |
| $\delta$ | PWT `delta` | `pwt1001.csv` column `delta` | Cross-check for depreciation rate |

**No additional aggregation needed**: gcamdata already provides R32-level data. The GHIM data pipeline reads gcamdata outputs directly.

Phase 1 uses approximate IEA 2020 values for energy (as in current code). Phase 2+ will integrate actual gcamdata energy balance chunks for precise base-year calibration.
