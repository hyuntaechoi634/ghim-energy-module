# KLEM Macroeconomic Component

Detailed technical documentation for the CES-KLE macroeconomic driver in GHIM.

**Source files:**
- `ghim/econ/klem.py` — `KLEMDriver` class
- `ghim/solver/recursive.py` — `solve_period()`, `run_model()`
- `ghim/config.py` — parameters

---

## 1. Overview: What Does the KLEM Module Do?

The KLEM module answers a fundamental question: **how much energy does the economy need, and what happens when energy gets expensive?**

In many models, GDP is taken directly from SSP scenarios as a fixed input. GHIM instead treats GDP as **endogenous** — energy prices affect economic output, which affects investment, which changes the capital stock, which changes future GDP. This feedback loop is the core of the KLEM module.

The name "KLEM" stands for **Capital (K), Labor (L), Energy (E), Materials (M)**. GHIM implements a "KLE" variant: Materials are implicit in TFP (like GCAM), not modeled as a separate factor.

### 1.1 The Big Picture

```
    SSP Scenarios (Population, GDP|PPP)
                  │
    TFP calibrated once (A(t) so that Y ≈ Y_SSP in reference case)
                  │
                  ▼
    ┌────────────────────────────┐
    │    Value Added (inner)     │
    │  VA = TFP × K^α × L^(1-α) │  ← Cobb-Douglas
    └────────────┬───────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │  CES Energy Demand (outer) │
    │  E = f(VA, P_E; σ_KLE)    │  ← How much energy?
    └────────────┬───────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │  Energy Supply Chain       │
    │  Electricity, Refining,    │  ← What mix of fuels?
    │  Hydrogen, Final Demand    │
    └────────────┬───────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │  Energy Cost Feedback      │
    │  NetOutput = Y - cost      │  ← GDP drag from energy
    │  I = s × NetOutput         │
    │  K(t+1) = K(t) + I×dt     │  ← Lower K → lower future Y
    └────────────────────────────┘
```

The key insight: TFP is calibrated so that GDP matches the SSP path **in the absence of energy shocks**. Once energy prices change (from carbon pricing, resource depletion, technology learning, etc.), GDP diverges from the SSP reference — and this divergence propagates forward through capital accumulation.

---

## 2. The Two-Level Production Structure

GHIM uses a **two-level nested CES** (Constant Elasticity of Substitution) structure, following the WITCH/GCAM tradition:

```
Level 1 (inner):  VA = TFP × K^α × L^(1-α)     [Cobb-Douglas]
Level 2 (outer):  E  = E_base × (VA/VA_base) × (P_E/P_E_base)^(-σ_KLE)  [CES FOC]
Gross output:     Y  = VA                         [Energy via cost feedback]
```

### 2.1 Why Two Levels?

Each level captures a different type of substitution:

- **Level 1 (K vs L)**: Capital and labor are substitutes with elasticity = 1 (Cobb-Douglas). Richer countries invest more in capital (machines replace workers). This is standard growth theory.

- **Level 2 (VA vs E)**: Value-added and energy are substitutes with elasticity σ_KLE = 0.4. When energy gets expensive, the economy shifts toward less energy-intensive activities. The elasticity range 0.3–0.5 comes from empirical estimates (GCAM uses ~0.35, WITCH uses ~0.5).

### 2.2 Why Not Full CES(VA, E)?

The mathematically "pure" approach would compute gross output as `Y = CES(VA, E; σ)`. We tried this and discovered a fundamental problem:

**Unit mismatch**: VA is measured in billion USD while E is measured in EJ. These are incommensurable quantities. The CES function `(α₁ × VA^ρ + α₂ × E^ρ)^(1/ρ)` would mix dollars and joules in the same aggregation — which requires arbitrary scaling and produces fragile calibration.

**Primal-dual inconsistency**: The CES calibration function (`ces_calibrate`) works in the cost-function (dual) space, computing share parameters from base-year prices and quantities. But using those same share parameters in the production-function (primal) space to derive energy demand via the first-order condition doesn't reproduce base-year quantities. This is a known issue in CES modeling with heterogeneous-unit inputs.

**The resolution**: The CES first-order condition (FOC) can be shown to reduce to the clean isoelastic formula:

```
E = E_base × (VA / VA_base) × (P_E / P_E_base)^(-σ_KLE)
```

This is mathematically equivalent to the full CES FOC, reproduces base-year demand exactly by construction, responds to prices with the correct elasticity, and has no unit-mismatch issues. Gross output `Y = VA` because energy's contribution is captured through the cost feedback loop: higher energy costs → lower net output → lower investment → lower capital → lower future VA.

---

## 3. Energy Demand from CES First-Order Condition

The central equation of the KLEM module:

```
E(t) = E_base × (VA(t) / VA_base) × (P_E(t) / P_E_base)^(-σ_KLE)
```

### 3.1 How to Read This Equation

The equation has two multiplicative effects:

1. **Income effect** `(VA / VA_base)`: Energy demand grows proportionally with economic output. If the economy doubles, energy demand doubles (unitary income elasticity at the aggregate level). This is a standard assumption for the aggregate — sector-specific income elasticities handle the composition effect (see Section 7).

2. **Price effect** `(P_E / P_E_base)^(-σ_KLE)`: Higher energy prices reduce demand. With σ_KLE = 0.4:
   - A 10% price increase → ~4% demand reduction
   - A doubling of prices → ~24% demand reduction
   - The substitution is moderate — the economy can reduce energy use, but not easily

### 3.2 Where Does This Come From?

Starting from a CES production function `Y = CES(VA, E; σ)`, cost minimization gives the first-order condition:

```
E/VA = (α_E/α_VA)^σ × (P_VA/P_E)^σ
```

At the base year, this ratio equals `E_base/VA_base` by construction. At any other year, the ratio changes only due to price changes. Multiplying both sides by `VA` and normalizing to the base year gives exactly our formula.

### 3.3 Composite Energy Price

The "energy price" `P_E` is not a single number — the economy uses coal, gas, oil, electricity, biomass, and hydrogen. GHIM computes an **expenditure-weighted composite price**:

```
P_E = Σ_c (Price_c × Demand_c) / Σ_c Demand_c
```

This means fuels that represent a larger share of the energy bill have more influence on the composite price. If electricity costs $20/GJ and coal costs $2/GJ, but electricity is 60% of final demand, then electricity dominates the composite.

This replaces the old naive arithmetic mean, which would give coal and electricity equal weight regardless of their consumption shares.

### 3.4 AEEI (Autonomous Energy Efficiency Improvement)

When a policy scenario includes efficiency standards, the energy demand is further reduced:

```
E_effective(t) = E(t) × AEEI_factor(t)
```

AEEI < 1.0 represents exogenous technological progress in energy efficiency (better insulation, more efficient vehicles, etc.).

---

## 4. Value Added: The Cobb-Douglas Inner Nest

Value added (VA) is computed from a standard Cobb-Douglas production function:

```
VA(t) = A(t) × K(t)^α × L(t)^(1-α)
```

where:
- `A(t)` = Total Factor Productivity (TFP), calibrated from SSP (see Section 5)
- `K(t)` = Capital stock (billion USD PPP)
- `L(t)` = Labor force = Population × Labor Force Participation rate
- `α` = Capital share = 0.30 (standard Solow growth model value)

### 4.1 Regional Labor Force Participation

Different regions have very different labor force participation (LFP) rates. Using a single global value (65%) would systematically over-estimate labor in low-participation regions (Middle East: 51%) and under-estimate it in high-participation ones (Eastern Asia: 68%).

GHIM uses **ILO 2020 estimates** for each R10 region:

| Region | LFP Rate |
|--------|----------|
| Africa | 0.63 |
| Asia-Pacific Developed | 0.61 |
| Eastern Asia | 0.68 |
| Eurasia | 0.59 |
| Europe | 0.58 |
| Latin America and Caribbean | 0.62 |
| Middle East | 0.51 |
| North America | 0.61 |
| South-East Asia and developing Pacific | 0.67 |
| Southern Asia | 0.50 |

The effect is significant: Middle East (LFP=0.51) has 22% less effective labor than the global average, which raises its calibrated TFP correspondingly (since the same GDP must be explained with less labor input).

---

## 5. TFP Calibration

TFP is calibrated once at initialization to ensure that the model GDP matches the SSP projection **in the absence of energy shocks**. During simulation, TFP is fixed — GDP diverges from SSP only through the energy cost feedback loop.

### 5.1 Why Calibrate TFP?

TFP captures "everything else" — technology, institutions, governance, human capital — that explains GDP beyond K and L. By calibrating TFP from the SSP path, we:

1. Ensure the reference scenario tracks established SSP projections
2. Attribute all non-KL growth to TFP (a standard decomposition)
3. Isolate the energy cost feedback as the only source of GDP divergence

### 5.2 The Two-Step Algorithm

**Step 1: Backward K Solve (Historical Periods)**

Starting from `K(2020)`, invert the capital accumulation equation backward through 2015, 2010, 2005, 2000:

```
K(t) = (K(t+dt) - I × dt) / (1 - δ)^dt
```

where `I = min(s × Y_SSP(t), cap_rate × K(t+dt))`.

A floor of `0.01 × Y_SSP(t)` prevents negative capital. This produces historically consistent capital stocks: K(2000) < K(2005) < ... < K(2020).

**Step 2: Forward TFP Calibration (All Periods)**

With the full K trajectory, back out TFP at each period:

```
A(t) = Y_SSP(t) / (K(t)^α × L(t)^(1-α))
```

- **Historical years** use backward-solved K directly
- **Future years** evolve K forward from K(2020) using the standard accumulation law

After calibration, the solver's capital stock is reset to K(2000) so the recursive solver starts from the correct historical position.

### 5.3 Properties of the Calibrated TFP

- **Monotonically increasing** for growing GDP with constant population (typical SSP2/3)
- **Historical TFP ≥ base-year TFP** (because K(history) < K(2020), so higher A is needed to explain the same GDP)
- **No discontinuity** at the 2020→2025 boundary (both sides use K(2020) as anchor)

The last property is critical: an earlier bug used K(2000) for forward TFP calibration, producing a TFP spike at 2025 that caused a GDP surge.

---

## 6. Capital Stock Dynamics

### 6.1 Accumulation Law

Capital evolves via the perpetual inventory method:

```
K(t + dt) = (1 - δ)^dt × K(t) + I(t) × dt
```

where:
- `δ` = 0.05/year (annual depreciation)
- `(1 - δ)^dt` = 0.95^5 = 0.7738 (5-year decay factor)
- `I(t)` = annual investment rate

### 6.2 Investment

Investment is a constant fraction of net output, capped by the capital stock:

```
I(t) = min(s × NetOutput(t), cap_rate × K(t))
```

- `s` = 0.22 (savings rate, from Penn World Table)
- `cap_rate` = 0.10 (investment cap rate)

The cap prevents implausibly fast capital accumulation when GDP surges. It limits annual investment to 10% of the existing capital stock.

### 6.3 Base-Year Initialization

At the base year (2020), capital is initialized from the capital-output ratio:

```
K(2020) = Y_SSP(2020) × K/Y_ratio    (K/Y_ratio = 3.0)
```

For North America with base-year GDP of ~$21 trillion, this gives K = $63 trillion.

---

## 7. Energy Cost Feedback Loop

This is the loop that makes GDP endogenous:

### 7.1 Energy Cost

```
EnergyCost = E_total (EJ) × P_E_composite ($/GJ)
```

Note: 1 EJ = 10^9 GJ, so EJ × $/GJ directly gives billion USD. The composite price is the expenditure-weighted average from Section 3.3.

### 7.2 Energy Cost Share

An important diagnostic metric:

```
energy_cost_share = EnergyCost / GrossOutput
```

At the base year, this is typically 5–10% for developed economies, 8–15% for developing economies. Values above 20% indicate severe energy burden. The model reports this as `PeriodResult.energy_cost_share`.

### 7.3 Net Output

```
NetOutput = max(GrossOutput - EnergyCost, 0.01 × GrossOutput)
```

The 1% floor prevents model collapse if energy costs exceed GDP (which can happen under extreme carbon pricing).

### 7.4 The Feedback Chain

```
Energy price ↑  →  P_E ↑  →  E demand ↓ (CES substitution)
                          →  EnergyCost ↑ (net of demand reduction)
                          →  NetOutput ↓
                          →  Investment ↓
                          →  K(t+1) ↓
                          →  VA(t+1) ↓
                          →  Y(t+1) ↓
```

A one-time energy price shock propagates for many periods through capital dynamics. With depreciation rate 0.05 and savings rate 0.22, the half-life of a capital shock is approximately 14 years (3 model periods). This means a carbon tax introduced at 2025 is still reducing GDP relative to the reference at 2040+.

### 7.5 Revenue Recycling

If carbon pricing is active, carbon tax revenue can partially offset energy costs:

```
Revenue = CarbonPrice × Emissions_MtCO2 / 1000 × RecyclingFraction
EnergyCost_adjusted = max(EnergyCost - Revenue, 0)
```

This attenuates the GDP drag from carbon pricing — an important policy design feature.

---

## 8. KLEM-Sector Coupling

A key design question: how does the macro-level energy demand (from CES) connect to the sector-level energy demands (from the nested logit demand trees)?

### 8.1 The Problem

The KLEM module determines **total** energy demand `E_total` based on macro variables (VA, composite price, σ_KLE). The demand sectors (industry, buildings, transport) determine **relative** energy demands based on income elasticities and fuel switching. These two quantities won't match in general:

```
E_klem ≠ Σ_sector E_sector
```

because the CES demand uses aggregate price elasticity while sector demands use sector-specific income elasticities.

### 8.2 The Solution: Natural CES Scaling

The solution is simple: sector demands determine the **composition** of energy use, while the CES total determines the **level**:

```python
# Scale sector demands to match CES total
sector_sum = sum(sum(cd.values()) for cd in raw_sector_demands.values())
scale = total_energy / sector_sum
scaled_demand = {carrier: demand * scale for carrier, demand in raw.items()}
```

The scaling factor `scale` is typically close to 1.0 and varies smoothly over time. There is no clamping — the CES naturally constrains the scaling.

### 8.3 Previous Approach (Deprecated)

The previous implementation used `KLEM_SCALE_CLAMP = (0.5, 2.0)` to prevent extreme scaling ratios. This was a band-aid fix for a poorly calibrated energy demand heuristic. The CES-based approach eliminates the need for clamping because:

1. The CES FOC is derived from the same economic theory as the sector demands
2. The composite energy price properly reflects the actual fuel mix
3. σ_KLE = 0.4 provides moderate substitution that doesn't diverge wildly

---

## 9. Solver Integration

### 9.1 Period Solution Flow (`solve_period`)

For each region in each period:

1. **Set TFP** from pre-computed trajectory
2. **Compute value added**: `VA = TFP × K^α × L^(1-α)`
3. **Price iteration loop** (up to 100 iterations):
   a. Compute CES energy demand: `E = E_base × (VA/VA_base) × (P_E/P_E_base)^(-σ)`
   b. Apply AEEI factor
   c. Compute CES gross output: `Y = VA`
   d. Compute raw sector demands (income-driven, from logit trees)
   e. Scale sector demands to match CES total (natural coupling)
   f. Solve electricity supply (8-tech preference logit + vintage stock + learning)
   g. Solve refining supply
   h. Solve hydrogen supply
   i. Update electricity, refined liquids, hydrogen prices
   j. Update composite energy price (expenditure-weighted)
   k. Check convergence (relative price change < 0.001)
   l. Damped update (50% damping on new prices)
4. **Compute energy cost** (expenditure-weighted composite × total EJ)
5. **Compute emissions** (electricity + refining + hydrogen + direct combustion)
6. **Revenue recycling** (if carbon pricing active)
7. **Compute net output, investment, update capital** for next period

### 9.2 Composite Price Update Within Iteration

A subtle but important detail: the composite energy price is updated **within** the price iteration loop (step 3j). As electricity and hydrogen prices converge, the composite price shifts, which changes the CES energy demand, which changes sector demands, which changes supply-side prices. This inner loop typically converges in 3–5 iterations.

### 9.3 Full Model Run (`run_model`)

```python
for year in [2000, 2005, ..., 2150]:
    if trade_enabled:
        clear_global_fuel_markets()  # bisection on coal, oil, gas
    for region in R10_REGIONS:
        solve_period(region, year, trade_prices=...)
```

With trade enabled, the solver first clears global fuel markets via the trade module, then solves each region with trade-determined delivered fuel prices.

---

## 10. Trade Integration

The trade module affects the KLEM driver through **delivered fuel prices**. When trade is enabled:

1. The trade module estimates regional fuel demands using `compute_primary_fuel_demand()` (which uses the same CES-KLE approach internally)
2. Global market clearing via bisection determines world prices for coal, oil, gas
3. Regional delivered prices = world price + transport cost
4. `solve_period()` receives these delivered prices, which enter the composite energy price calculation

The CES energy demand responds to trade-determined prices with the same σ_KLE elasticity. This creates a consistent macro-energy-trade feedback:

```
Higher world oil price → higher composite P_E → lower E demand → lower oil demand
→ lower world oil price (market clearing)
```

---

## 11. Design Decisions and Their Rationale

### 11.1 Why CES and not Leontief or Cobb-Douglas?

- **Leontief (σ=0)**: Fixed energy/GDP ratio. Unrealistic — economies do reduce energy use when prices rise.
- **Cobb-Douglas (σ=1)**: Too much substitution. Economies can't easily halve energy use when prices double.
- **CES (σ=0.4)**: Moderate substitution. Empirically grounded in the GCAM/WITCH range of 0.3–0.5.

### 11.2 Why Y = VA (not CES(VA, E))?

Energy's contribution to GDP is captured through the **cost feedback loop**, not through the production function output. This is equivalent to the "net output" interpretation used in DICE/RICE:

```
Y_gross = VA (how much the economy can produce)
Y_net = VA - EnergyCost (how much is left after paying for energy)
```

The cost feedback approach avoids the unit-mismatch problem (Section 2.2) and is standard in IAM literature.

### 11.3 Why Expenditure-Weighted Price?

Consider an economy using 80% cheap coal ($2/GJ) and 20% expensive electricity ($20/GJ):

- **Arithmetic mean**: ($2 + $20) / 2 = $11/GJ — overstates the true energy cost
- **Expenditure-weighted**: ($2×0.8 + $20×0.2) / 1.0 = $5.6/GJ — reflects actual spending

The expenditure-weighted price correctly represents the economy's actual energy cost burden.

### 11.4 Why Regional LFP?

The Middle East has 51% labor force participation (cultural factors, oil wealth) while Eastern Asia has 68%. Using the global average (65%) for both would:

- Under-estimate Middle East TFP by ~22% (because the model thinks there's more labor than there is)
- Over-estimate Eastern Asia TFP by ~5%

Regional LFP fixes these biases and produces more realistic TFP trajectories.

---

## 12. Parameters Reference

| Parameter | Symbol | Default | Source |
|-----------|--------|---------|--------|
| Capital share | α | 0.30 | Standard Solow growth model |
| Savings rate | s | 0.22 | Penn World Table average |
| Depreciation rate | δ | 0.05/yr | Standard assumption |
| Investment cap | cap_rate | 0.10 | Prevents >10%/yr capital growth |
| Capital-output ratio | K/Y | 3.0 | IMF WEO estimates |
| VA-Energy substitution | σ_KLE | 0.4 | GCAM/WITCH range 0.3–0.5 |
| Min energy cost share | — | 0.05 | Floor for calibration stability |
| Timestep | dt | 5 years | GCAM convention |
| Price damping | — | 0.5 | Solver stability |
| Price tolerance | — | 0.001 | Convergence criterion |
| Max price iterations | — | 100 | Safety bound |

---

## 13. Numerical Example

A worked example for North America at the base year (2020):

```
Inputs:
  GDP_SSP = 21,000 billion USD (PPP)
  Population = 370 million
  LFP = 0.61 (North America)
  Total final energy = 37.0 EJ
  Composite energy price = 7.5 $/GJ (expenditure-weighted)

Capital stock:
  K = 21,000 × 3.0 = 63,000 billion USD

Labor:
  L = 370 × 0.61 = 225.7 million

TFP (calibrated):
  KL = 63,000^0.3 × 225.7^0.7 = 5,073.6
  A = 21,000 / 5,073.6 = 4.14

Value Added:
  VA = 4.14 × 63,000^0.3 × 225.7^0.7 = 21,000 billion USD  ✓

CES Energy Demand (at base prices):
  E = 37.0 × (21,000 / 21,000) × (7.5 / 7.5)^(-0.4) = 37.0 EJ  ✓

If energy price doubles to 15.0 $/GJ:
  E = 37.0 × 1.0 × (15.0 / 7.5)^(-0.4) = 37.0 × 0.758 = 28.0 EJ
  → 24% demand reduction from 100% price increase

Energy cost:
  Cost = 28.0 × 15.0 = 420 billion USD
  Cost share = 420 / 21,000 = 2.0%

Net output:
  Y_net = 21,000 - 420 = 20,580 billion USD

Investment:
  I = min(0.22 × 20,580, 0.10 × 63,000) = min(4,528, 6,300) = 4,528 billion USD/yr
```

---

## 14. Data Sources

| Data | Source | Path |
|------|--------|------|
| Population | SSP Database 2024 | `ghim/data/external/ssp/SSP_database_2024.csv.gz` |
| GDP (PPP) | SSP Database 2024 | same |
| Historical data | "Historical Reference" scenario | same |
| Region mapping | AR6 R10 classification | `ghim/data/external/region_classification.tsv` |
| Base-year energy | Approximate IEA 2020 | `ghim/data/energy_cal.py` |
| Labor force participation | ILO 2020 estimates | Hardcoded in `ghim/config.py` |

---

## 15. Known Limitations

1. **Zero population fallback** — If a region has zero population, TFP defaults to a fallback value rather than handling it gracefully (`klem.py:80`).

2. **Price iteration non-convergence** — If the price iteration loop doesn't converge within 100 iterations, the solver silently continues with the last prices. No warning is emitted.

3. **Approximate energy data** — Base-year energy values (`DEFAULT_PRIMARY_ENERGY`, `DEFAULT_ELEC_SHARES`, etc.) are approximate IEA 2020 values, not sourced from an actual IEA database extract.

4. **LFP is time-invariant** — Regional labor force participation rates are fixed at 2020 values. In reality, LFP changes with economic development (tends to increase in developing regions, plateau in developed ones).

5. **Unitary aggregate income elasticity** — The CES FOC assumes E grows proportionally with VA at the aggregate level. Sector-specific elasticities (industry=0.6, buildings=0.5, transport=0.7) handle the composition effect, but the aggregate coupling always scales to match the CES total.
