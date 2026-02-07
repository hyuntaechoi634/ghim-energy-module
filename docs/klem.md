# KLEM Macroeconomic Component

Detailed technical documentation for the KLEM (Capital-Labor-Energy-Materials) macroeconomic driver in GHIM.

**Source files:**
- `ghim/econ/klem.py` — `KLEMDriver` class
- `ghim/solver/recursive.py` — `solve_period()`, `run_model()`
- `ghim/config.py` — parameters

---

## 1. Overview

KLEM implements a **DICE-style endogenous GDP** model where energy costs feed back into economic output. Unlike pure IAMs that take GDP as exogenous (from SSP scenarios), GHIM computes GDP endogenously: energy price shocks reduce net output, lower investment, shrink capital stock, and thus lower future GDP.

The production function is Cobb-Douglas:

```
Y(t) = A(t) * K(t)^alpha * L(t)^(1-alpha)
```

where:
- `Y` = gross output (billion USD PPP)
- `A` = total factor productivity (TFP)
- `K` = capital stock (billion USD PPP)
- `L` = labor force (millions of people)
- `alpha` = capital share (default 0.30)

TFP `A(t)` is **calibrated once** from the SSP GDP path so that `Y_model ≈ Y_SSP` in the absence of energy shocks. During simulation, TFP is fixed and GDP diverges from SSP only through energy cost feedback on capital accumulation.

---

## 2. Capital Stock Dynamics

### 2.1 Accumulation Law

Capital evolves via the standard perpetual inventory method:

```
K(t + dt) = (1 - delta)^dt * K(t) + I(t) * dt
```

where:
- `delta` = annual depreciation rate (default 0.05)
- `dt` = timestep in years (default 5)
- `(1 - delta)^dt` = multi-year decay factor (0.95^5 = 0.7738)
- `I(t)` = annual investment rate

### 2.2 Investment

Investment is a constant fraction of net output, capped by the capital stock:

```
I(t) = min(s * NetOutput(t), cap_rate * K(t))
```

- `s` = savings rate (default 0.22)
- `cap_rate` = investment cap rate (default 0.10)

The cap prevents implausibly fast capital accumulation when GDP surges (e.g., from windfall energy cost reductions). It limits annual investment to 10% of the existing capital stock.

### 2.3 Base-Year Initialization

At the base year (2020), capital is initialized from the capital-output ratio:

```
K(2020) = Y_SSP(2020) * CAPITAL_OUTPUT_RATIO    (default ratio = 3.0)
```

For a region with base-year GDP of $25 trillion (North America), this gives K = $75 trillion.

---

## 3. TFP Calibration

TFP is calibrated once during initialization via a two-step algorithm in `init_tfp_trajectory()`.

### 3.1 Step 1: Backward K Solve (Historical Periods)

Starting from `K(2020)`, the method inverts the capital accumulation equation backward through 2015, 2010, 2005, 2000:

```
K(t) = (K(t+dt) - I * dt) / (1 - delta)^dt
```

where investment uses SSP GDP for the period:

```
I = min(s * Y_SSP(t), cap_rate * K(t+dt))
```

A floor of `0.01 * Y_SSP(t)` prevents negative capital. This produces historically consistent capital stocks: K(2000) < K(2020).

### 3.2 Step 2: Forward TFP Calibration (All Periods)

With the full K trajectory (backward-solved for historical, forward-evolved for future periods), TFP is backed out at each period:

```
A(t) = Y_SSP(t) / (K(t)^alpha * L(t)^(1-alpha))
```

where `L(t) = Population(t) * LABOR_FORCE_PARTICIPATION` (default 0.65).

**Historical years** use the backward-solved K directly. **Future years** evolve K forward from K(2020) using:

```
K(t) = (1 - delta)^dt * K(t-dt) + I_ref * dt
I_ref = min(s * Y_SSP(t-dt), cap_rate * K(t-dt))
```

After TFP calibration, the solver's capital stock is reset to `K(2000)` so the recursive solver starts from the correct historical position.

### 3.3 Design Rationale

- TFP captures everything not explained by K and L (technology, institutions, etc.)
- Calibrating TFP from SSP ensures model GDP tracks SSP projections in the reference case
- Divergence arises only from the energy cost feedback loop (the whole point of endogenous GDP)
- Growing SSP GDP with constant capital share produces increasing TFP over time

---

## 4. Energy Demand

Total energy demand responds to GDP and energy prices:

```
E(t) = E_base * (Y(t) / Y_base) * (P(t) / P_base)^(-sigma_em)
```

- `E_base` = base-year total energy demand (EJ, from `DEFAULT_FINAL_DEMAND`)
- `Y(t) / Y_base` = GDP growth effect (unitary income elasticity at aggregate level)
- `P(t) / P_base` = energy price index (average carrier prices relative to base year)
- `sigma_em` = energy-materials substitution elasticity (default 0.5)

The price index uses the simple mean of all carrier prices:

```
P(t) / P_base = mean(carrier_prices_t) / mean(carrier_prices_base)
```

Carriers: coal, refined liquids, gas, electricity, biomass, hydrogen.

### 4.1 AEEI (Autonomous Energy Efficiency Improvement)

When a policy scenario includes efficiency standards, total energy demand is further multiplied by the cumulative AEEI factor:

```
E_effective(t) = E(t) * AEEI_factor(t)
```

AEEI_factor < 1.0 represents exogenous efficiency improvement (e.g., from building codes, vehicle standards).

---

## 5. Energy Cost Feedback

The feedback loop that makes GDP endogenous:

### 5.1 Energy Cost

```
EnergyCost = E_total(EJ) * AvgPrice($/GJ)
```

Note: 1 EJ = 10^9 GJ, so EJ * $/GJ directly gives billion USD.

### 5.2 Net Output

```
NetOutput = max(GrossOutput - EnergyCost, 0.01 * GrossOutput)
```

The 1% floor prevents zero or negative net output from causing model collapse. In practice this means energy costs cannot consume more than 99% of gross output.

### 5.3 Investment from Net Output

```
I = min(s * NetOutput, cap_rate * K)
```

Lower net output → lower investment → lower future K → lower future Y. This is the core feedback: an energy price shock today reduces GDP for many future periods through capital stock dynamics.

### 5.4 Revenue Recycling

If carbon pricing is active, carbon tax revenue can partially offset energy costs:

```
Revenue = CarbonPrice * Emissions_MtCO2 / 1000 * RecyclingFraction
EnergyCost_adjusted = max(EnergyCost - Revenue, 0)
```

This attenuates the GDP drag from carbon pricing.

---

## 6. Solver Integration

### 6.1 Period Solution (`solve_period`)

For each region in each period:

1. **Set TFP** from pre-computed trajectory
2. **Compute gross output**: `Y = A * K^alpha * L^(1-alpha)`
3. **Price iteration loop** (up to 100 iterations):
   - Compute energy price index
   - Compute total energy demand from KLEM
   - Apply AEEI to total energy demand
   - Compute final demand by sector and carrier (nested logit trees)
   - Compute electricity supply (preference logit + stock turnover + learning)
   - Compute refining supply
   - Compute hydrogen supply
   - Update electricity, refined liquids, hydrogen prices
   - Check convergence (relative price change < 0.001)
   - Damped update (50% damping on new prices)
4. **Compute energy cost and net output**
5. **Compute emissions** (electricity + refining + hydrogen + direct combustion)
6. **Revenue recycling** (if carbon pricing active)
7. **Compute investment and update capital stock** for next period

### 6.2 Full Model Run (`run_model`)

```
for year in [2000, 2005, ..., 2150]:
    for region in R10_REGIONS:
        solve_period(region, year)
```

With trade enabled, the solver first clears global fuel markets via the trade module (see `docs/trade.md`), then solves each region with the trade-determined delivered prices.

---

## 7. Final Demand Structure

Final energy demand is decomposed into three sectors, each with a nested logit tree for fuel switching.

### 7.1 Sector Trees

**Industry** (income elasticity 0.6):
```
industry
 +-- heavy (45%, tau=30y)
 |   +-- coal 35%, gas 25%, electricity 15%, refined liquids 10%, biomass 10%, hydrogen 5%
 +-- light (45%, tau=30y)
 |   +-- electricity 40%, gas 25%, refined liquids 15%, coal 10%, biomass 8%, hydrogen 2%
 +-- data_centers (10%, tau=7y)
     +-- electricity 100%
```

**Buildings** (income elasticity 0.5):
```
buildings
 +-- residential (55%, tau=50y)
 |   +-- electricity 35%, gas 30%, biomass 18%, refined liquids 12%, coal 4%, hydrogen 1%
 +-- commercial (45%, tau=50y)
     +-- electricity 50%, gas 30%, refined liquids 8%, biomass 8%, coal 2%, hydrogen 2%
```

**Transport** (income elasticity 0.7):
```
transport
 +-- passenger (60%, tau=15y)
 |   +-- refined liquids 87%, electricity 5%, gas 4%, hydrogen 2%, biomass 2%
 +-- freight (40%, tau=15y)
     +-- refined liquids 95%, gas 2%, electricity 1%, hydrogen 1%, biomass 1%
```

### 7.2 Fuel Switching Mechanism

Each node uses **MERGE-style preference factor logit**:

```
Share_i = exp(-k * (Cost_i + Pref_i)) / sum_j exp(-k * (Cost_j + Pref_j))
```

- `k` = scale parameter (default 0.3 for fuel nodes, 0.05 for structural nodes)
- `Cost_i` = levelized cost of fuel or subsector ($/GJ)
- `Pref_i` = calibrated preference factor ($/GJ equivalent)

Preference factors are calibrated at the base year so that the logit reproduces observed shares. Technologies with high observed shares despite high costs get negative (favorable) preference factors.

### 7.3 Stock Turnover

Shares don't jump to logit-determined targets instantly. Instead:

```
NewShare_i = OldShare_i + (TargetShare_i - OldShare_i) * (dt / tau)
```

where `tau` = sector-specific turnover time (years). For `dt = 5` years:
- Transport (tau=15y): 33% toward target per period
- Industry (tau=30y): 17% toward target per period
- Buildings (tau=50y): 10% toward target per period
- Electricity (tau=40y): 12.5% toward target per period

This models the inertia of physical capital: existing vehicles, boilers, power plants.

### 7.4 Total Demand Scaling

Each sector's total energy demand scales with GDP:

```
E_sector(t) = E_sector_base * (GDP(t) / GDP_base)^eta
```

where `eta` is the sector-specific income elasticity. Sub-unitary elasticities (<1.0) mean energy demand grows slower than GDP (decoupling).

---

## 8. Electricity Supply

The electricity sector uses 8 technologies competing via preference logit:

| Technology | Fuel Input | Efficiency | Base Capital Cost ($/kW) | Learning Rate |
|-----------|-----------|------------|-------------------------|---------------|
| coal | coal | 0.38 | 2000 | 0% |
| gas_cc | gas | 0.55 | 1000 | 0% |
| nuclear | nuclear | 0.33 | 5500 | 3% |
| hydro | hydro | 1.00 | 3000 | 0% |
| wind | wind | 1.00 | 1300 | 12% |
| solar | solar | 1.00 | 1000 | 20% |
| biomass | biomass | 0.30 | 2500 | 5% |
| oil | oil | 0.35 | 1500 | 0% |

### 8.1 Levelized Cost

```
LCOE = (CapitalCost * CRF) / (CF * 8760 * 3.6e-3) + FuelCost / Efficiency + O&M
```

where:
- `CRF` = capital recovery factor at 5% discount rate over plant lifetime
- `CF` = capacity factor
- `8760 * 3.6e-3` = conversion from $/kW to $/GJ (hours/year * GJ/kWh)

### 8.2 Learning-by-Doing

Technologies with positive learning rates reduce capital cost with experience:

```
Cost(t) = Cost_0 * (Q_cum(t) / Q_0)^(-learn_exp)
```

where `learn_exp = ln(1 - LR) / ln(2)`. A 20% learning rate (solar) means cost drops 20% per cumulative capacity doubling. Costs are floored at 20% of initial cost.

---

## 9. Parameters Reference

| Parameter | Symbol | Default | Source |
|-----------|--------|---------|--------|
| Capital share | alpha | 0.30 | Standard Cobb-Douglas |
| Savings rate | s | 0.22 | Penn World Table avg |
| Depreciation rate | delta | 0.05/yr | Standard assumption |
| Investment cap | cap_rate | 0.10 | Prevents >10%/yr growth |
| Capital-output ratio | K/Y | 3.0 | IMF WEO estimates |
| Labor participation | LFP | 0.65 | ILO global average |
| Energy-materials elasticity | sigma_em | 0.5 | WITCH/MERGE range |
| Timestep | dt | 5 years | GCAM convention |
| Price damping | - | 0.5 | Solver stability |
| Price tolerance | - | 0.001 | Convergence criterion |
| Max price iterations | - | 100 | Safety bound |
| Logit scale (fuels) | k | 0.3 | MERGE calibration |
| Logit scale (structural) | k | 0.05 | Slow structural change |

---

## 10. Data Sources

| Data | Source | Path |
|------|--------|------|
| Population | SSP Database 2024 | `ghim/data/external/ssp/SSP_database_2024.csv.gz` |
| GDP (PPP) | SSP Database 2024 | same |
| Historical data | "Historical Reference" scenario | same |
| Region mapping | AR6 R10 classification | `ghim/data/external/region_classification.tsv` |
| Base-year energy | Approximate IEA 2020 | `ghim/data/energy_cal.py` |

---

## 11. Known Limitations

1. **Global labor participation rate** — `LABOR_FORCE_PARTICIPATION` is a single global value (0.65) rather than region- and time-varying. This underestimates labor in high-participation economies and vice versa.

2. **Zero population fallback** — If a region has zero population, TFP defaults to a fallback value rather than handling it gracefully (`klem.py:85-86`).

3. **Price iteration non-convergence** — If the price iteration loop doesn't converge within 100 iterations, the solver silently continues with the last prices. No warning is emitted.

4. **PREF_DECAY_RATE defined but not wired** — The preference factor decay rate (0.02/yr) is defined in config but not applied during simulation. Preference factors remain at their base-year calibrated values.

5. **Approximate energy data** — Base-year energy values (`DEFAULT_PRIMARY_ENERGY`, `DEFAULT_ELEC_SHARES`, etc.) are approximate IEA 2020 values, not sourced from an actual IEA database extract.
