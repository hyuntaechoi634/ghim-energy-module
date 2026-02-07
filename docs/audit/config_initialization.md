# Audit: Configuration & Initialization

**Scope**: `ghim/config.py`, `ghim/econ/klem.py`, `ghim/econ/ces.py`, `ghim/solver/recursive.py` (initialization path)

**Date**: 2026-02-06

---

## Issue Summary

| # | Issue | File | Severity |
|---|-------|------|----------|
| 1 | TFP trajectory uses 2020 K for 2000-2015 | `klem.py:77-95` | HIGH |
| 2 | Zero population → NaN TFP | `klem.py:85-86` | HIGH |
| 3 | Electricity/final demand accounting mismatch | `recursive.py:111-124` | MEDIUM |
| 4 | Price iteration silent non-convergence | `recursive.py:239-240` | MEDIUM |
| 5 | `PREF_DECAY_RATE` defined but never used | `config.py:61` | MEDIUM |
| 6 | `LABOR_FORCE_PARTICIPATION` not regional | `config.py:32` | MEDIUM |
| 7 | Hard-coded unit conversions | `electricity.py:126`, `recursive.py:265` | LOW |
| 8 | Dual logit systems | `electricity.py:55-76` | LOW |
| 9 | `EJ_PER_MTOE` defined but unused | `config.py:110` | LOW |

---

## Initialization Order

```
1. load_ssp_data(scenario)           → pop_df, gdp_df  (DataFrame, index=R10, cols=years)
       |
2. For each region:
       |
   2a. build_region_model(region, base_gdp, base_pop)
       |   |
       |   +-- KLEMDriver.__init__(base_gdp, base_pop, total_final_demand)
       |   |       capital_stock = base_gdp * 3.0
       |   |       labor = base_pop * 0.65
       |   |       tfp = base_gdp / (K^α * L^(1-α))
       |   |
       |   +-- ElectricitySector()
       |   |       total_generation_ej = DEFAULT_ELEC_TOTAL_EJ[region]
       |   |
       |   +-- FinalDemand(sector, base_ej) for each sector
       |   |
       |   +-- model.calibrate(base_gdp)
       |           electricity.calibrate(shares, prices)
       |           hydrogen.calibrate(shares, prices)
       |           demand.calibrate(prices, gdp)
       |
   2b. rm.klem.init_tfp_trajectory(ssp_gdp_series, pop_series)
       |   Iterates MODEL_YEARS (2000..2150)
       |   Uses constructor K (= base_gdp * 3.0, i.e. 2020 K)
       |   for ALL years including 2000-2015   ← BUG
       |
3. Solve period-by-period
       for year in MODEL_YEARS:
           for region in R10_REGIONS:
               solve_period(rm, ssp_gdp, pop, year)
```

---

## Issue Details

### Issue 1: TFP Trajectory Uses 2020 K for 2000-2015

**Severity**: HIGH

**Location**: `klem.py:67-95`

**Code**:
```python
def init_tfp_trajectory(
    self,
    ssp_gdp_by_year: dict[int, float],
    pop_by_year: dict[int, float],
) -> None:
    k_ref = self.capital_stock   # ← This is base_gdp * 3.0 (2020 value)
    self._tfp_trajectory = {}

    for year in MODEL_YEARS:    # 2000, 2005, 2010, 2015, 2020, ...
        y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
        pop = pop_by_year.get(year, self.base_population)
        labor = pop * LABOR_FORCE_PARTICIPATION

        kl = k_ref ** self.alpha * labor ** (1.0 - self.alpha)
        a = y_ssp / kl if kl > 0 else self.tfp
        self._tfp_trajectory[year] = a

        inv_ref = min(
            self.savings_rate * y_ssp,
            self.investment_cap_rate * k_ref,
        )
        decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP
        k_ref = decay * k_ref + inv_ref * TIMESTEP
```

**Root cause**: `k_ref` is initialized from `self.capital_stock`, which is set in `__init__()` at line 51:
```python
self.capital_stock = base_gdp * 3.0
```
where `base_gdp` is the **2020** GDP value (passed from `recursive.py:315`). The loop then iterates from year 2000, using this 2020-era capital stock to back-calculate TFP for years 2000-2015.

**Numerical trace** (example for North America, SSP2):
- `base_gdp` ≈ 23,000 billion USD (2020)
- `capital_stock` = 23,000 * 3.0 = 69,000
- Year 2000 SSP GDP ≈ 14,000 billion USD
- Year 2000 population ≈ 400 million, labor ≈ 260 million
- `kl` = 69,000^0.3 * 260^0.7 ≈ 25.8 * 53.1 ≈ 1,370
- `a(2000)` = 14,000 / 1,370 ≈ 10.2

If K were correctly scaled to 2000 (≈ 14,000 * 3.0 = 42,000):
- `kl` = 42,000^0.3 * 260^0.7 ≈ 21.8 * 53.1 ≈ 1,158
- `a(2000)` = 14,000 / 1,158 ≈ 12.1

**Impact**: TFP for 2000-2015 is systematically underestimated (because K is too high for those years). Since TFP is held fixed during simulation, the model's gross output for early years will be too low relative to SSP reference. The effect diminishes as `k_ref` evolves forward from 2020 and the trajectory self-corrects. The error is most pronounced for regions with large GDP growth between 2000-2020 (e.g., Eastern Asia, Southern Asia).

**Recommended fix**:
```python
def init_tfp_trajectory(self, ssp_gdp_by_year, pop_by_year):
    # Start K from the earliest available year, not 2020
    first_year = MODEL_YEARS[0]
    first_gdp = ssp_gdp_by_year.get(first_year, self.base_gdp)
    k_ref = first_gdp * 3.0  # K/Y ≈ 3 at year 2000

    self._tfp_trajectory = {}
    for year in MODEL_YEARS:
        # ... rest unchanged
```

---

### Issue 2: Zero Population → NaN TFP

**Severity**: HIGH

**Location**: `klem.py:85-86`

**Code**:
```python
kl = k_ref ** self.alpha * labor ** (1.0 - self.alpha)
a = y_ssp / kl if kl > 0 else self.tfp
```

**Root cause**: If `pop_by_year[year]` is 0 for any year, then `labor = 0 * 0.65 = 0`. With `alpha = 0.3`:
```
kl = k_ref^0.3 * 0^0.7 = 0
```
The guard `if kl > 0` catches this, falling back to `self.tfp` (the base-year TFP).

**However**, the same issue exists in `__init__()` at lines 57-58:
```python
kl = self.capital_stock ** self.alpha * self.labor ** (1.0 - self.alpha)
self.tfp = base_gdp / kl if kl > 0 else 1.0
```
If `base_population = 0` → `labor = 0` → `kl = 0` → `self.tfp = 1.0` (an arbitrary fallback). Then in `init_tfp_trajectory`, any zero-population year falls back to this arbitrary `1.0`.

**How to trigger**: This can happen when:
1. SSP scenario name is wrong (Issue #1 in input_processing.md) — all-zeros data
2. A region has zero population in the SSP database for a specific year (unlikely but possible for edge-case regions)

**Impact**: With `tfp = 1.0` and `K = 0`, `compute_gross_output()` returns:
```python
1.0 * 0^0.3 * 0^0.7 = 0.0
```
The model produces zero output but doesn't crash. The fallback value `1.0` has no physical meaning and masks the underlying data issue.

**Recommended fix**:
```python
def __init__(self, base_gdp, base_population, base_energy_demand_ej, ...):
    if base_population <= 0:
        raise ValueError(
            f"base_population must be positive, got {base_population}"
        )
    if base_gdp <= 0:
        raise ValueError(
            f"base_gdp must be positive, got {base_gdp}"
        )
    # ... rest unchanged
```

---

### Issue 3: Electricity/Final Demand Accounting Mismatch

**Severity**: MEDIUM

**Location**: `recursive.py:111-124`

**Code** (in `build_region_model`):
```python
# Base-year total final demand
fd = DEFAULT_FINAL_DEMAND.get(region, {"industry": 5.0, "buildings": 5.0, "transport": 5.0})
total_final = sum(fd.values())

# ...

# KLEM driver
klem = KLEMDriver(base_gdp, base_pop, total_final)

# Electricity sector
elec = ElectricitySector()
elec.total_generation_ej = DEFAULT_ELEC_TOTAL_EJ.get(region, 5.0)
```

**Root cause**: `DEFAULT_FINAL_DEMAND` and `DEFAULT_ELEC_TOTAL_EJ` are defined independently in `energy_cal.py`. Final demand includes electricity consumption by end-use sectors, but electricity generation (`DEFAULT_ELEC_TOTAL_EJ`) is a separate number that should be at least as large as the electricity component of final demand (plus transmission losses).

There is no explicit link between the two. The KLEM driver receives `total_final` (sum of industry + buildings + transport) as its `base_energy_demand_ej`, which is final energy only. The electricity sector gets a separate `total_generation_ej`. These should be consistent: electricity generation = electricity share of final demand / (1 - losses).

**Example for North America**:
- `DEFAULT_FINAL_DEMAND`: industry=18.0, buildings=20.0, transport=28.0 → total=66.0 EJ
- `DEFAULT_ELEC_TOTAL_EJ`: 18.5 EJ
- Implied electricity share of final demand: ~15 EJ (rough estimate from carrier shares in demand)
- 18.5 EJ generation for ~15 EJ final consumption → ~19% losses (reasonable for T&D)

The numbers are roughly consistent by construction, but this is coincidental. Changing one without the other creates an accounting gap.

**Impact**: If defaults are modified, the model won't detect the inconsistency. Energy balance won't close: generation won't match consumption.

**Recommended fix**: Either derive `DEFAULT_ELEC_TOTAL_EJ` from `DEFAULT_FINAL_DEMAND` plus a loss factor, or add an assertion:
```python
# At initialization, verify approximate consistency
for region in R10_REGIONS:
    elec_gen = DEFAULT_ELEC_TOTAL_EJ[region]
    total_demand = sum(DEFAULT_FINAL_DEMAND[region].values())
    if elec_gen > total_demand:
        warnings.warn(
            f"{region}: electricity generation ({elec_gen} EJ) exceeds "
            f"total final demand ({total_demand} EJ)"
        )
```

---

### Issue 4: Price Iteration Silent Non-Convergence

**Severity**: MEDIUM

**Location**: `recursive.py:239-240`

**Code**:
```python
if max_change < PRICE_TOL:
    break
```

**Root cause**: The price iteration loop runs up to `MAX_PRICE_ITER = 100` iterations. If it doesn't converge (i.e., `max_change >= PRICE_TOL` for all 100 iterations), the loop exits silently and the model continues with the last iteration's prices.

**Impact**: Non-convergence means supply-demand equilibrium was not achieved. Prices may be oscillating or diverging. The model continues with potentially wrong prices, which feed into energy costs, net output, and capital accumulation. The error compounds across periods.

**How to detect**: Currently impossible without adding instrumentation. The user has no way to know if any period/region failed to converge.

**Recommended fix**:
```python
for iteration in range(MAX_PRICE_ITER):
    # ... existing iteration logic ...
    if max_change < PRICE_TOL:
        break
else:
    # Loop completed without break → non-convergence
    import warnings
    warnings.warn(
        f"Price iteration did not converge for {rm.name} in year {year} "
        f"(max_change={max_change:.6f}, tol={PRICE_TOL})"
    )
```

---

### Issue 5: `PREF_DECAY_RATE` Defined but Never Used

**Severity**: MEDIUM

**Location**: `config.py:61`

**Code**:
```python
PREF_DECAY_RATE: float = 0.02       # annual decay rate for preference factors
# (1-0.02)^5 = 0.904 → ~10% decay per 5-year period; halve in ~35 years
```

**Verification**: Grep for `PREF_DECAY_RATE` across the entire `ghim/` directory returns only the definition in `config.py:61`. It is never imported or referenced elsewhere.

**Root cause**: The preference decay mechanism was designed (documented in the config comment) but never implemented. In `ElectricitySector.compute_supply()` (electricity.py:82-129), preference factors are used but never decayed:
```python
if self.pref_factors is not None:
    target_shares = preference_logit(costs, self.pref_factors, self.scale_k)
```
`self.pref_factors` is set once during calibration (`electricity.py:66`) and never modified afterward.

**Impact**: Without preference decay, incumbent technologies retain their calibrated advantage indefinitely. The preference factors lock in base-year biases (e.g., coal's preference in Eastern Asia) and never erode, even as costs change dramatically. This counteracts the learning curve mechanism — even if solar becomes much cheaper, coal retains its preference premium.

**Design intent** (from comment): Preferences should decay by ~10% per 5-year period, halving in ~35 years. This would allow cost-competitive technologies to gain market share over time.

**Recommended fix**: In `ElectricitySector.compute_supply()`, add decay:
```python
# After computing target_shares, decay preference factors
if self.pref_factors is not None and self.base_pref_factors is not None:
    decay = (1.0 - PREF_DECAY_RATE) ** TIMESTEP
    # Decay toward zero (reducing preference advantages over time)
    self.pref_factors = self.pref_factors * decay
```

---

### Issue 6: `LABOR_FORCE_PARTICIPATION` Not Regional

**Severity**: MEDIUM

**Location**: `config.py:32`

**Code**:
```python
LABOR_FORCE_PARTICIPATION: float = 0.65  # fraction of population as labor
```

**Usage**: `klem.py:54`, `klem.py:83`, `klem.py:108`
```python
self.labor = base_population * LABOR_FORCE_PARTICIPATION    # __init__
labor = pop * LABOR_FORCE_PARTICIPATION                     # init_tfp_trajectory
self.labor = population * LABOR_FORCE_PARTICIPATION         # compute_gross_output
```

**Root cause**: Labor force participation rate varies significantly by region: ~58% in Southern Asia (low female participation), ~62% in Europe, ~68% in Eastern Asia, ~55% in Middle East. Using a global 0.65 introduces systematic bias.

**Impact**: For regions with low actual participation (Middle East, Southern Asia), labor is overstated → TFP is calibrated lower to compensate → the production function undervalues labor's contribution. This doesn't affect base-year calibration (TFP absorbs the error) but distorts the response to population changes: a 10% population increase should contribute more to GDP in a high-participation region than a low-participation one, but the model treats them identically.

**Recommended fix**: Make `LABOR_FORCE_PARTICIPATION` a per-region dict or load from data:
```python
LABOR_FORCE_PARTICIPATION: dict[str, float] = {
    "Africa": 0.63,
    "Asia-Pacific Developed": 0.62,
    "Eastern Asia": 0.68,
    "Eurasia": 0.60,
    "Europe": 0.58,
    "Latin America and Caribbean": 0.62,
    "Middle East": 0.55,
    "North America": 0.62,
    "South-East Asia and developing Pacific": 0.67,
    "Southern Asia": 0.52,
}
```

---

### Issue 7: Hard-Coded Unit Conversions

**Severity**: LOW

**Location**: `electricity.py:125-126`, `recursive.py:265`, `technology.py:61`, `technology.py:79`, `hydrogen.py:131`

**Code examples**:
```python
# electricity.py:125-126
capacity_gw = gen_ej / (t.capacity_factor * HOURS_PER_YEAR * 3.6e-3 * 1e-6)

# recursive.py:265
direct_emissions += cc * ej * 1e9 / 1e6  # tC -> MtC

# technology.py:61
annual_output_gj_per_kw = self.capacity_factor * HOURS_PER_YEAR * 3.6e-3  # GJ/yr per kW

# technology.py:79
return self.carbon_coef * input_ej * 1e9 / 1e6  # MtC
```

**Root cause**: The conversion factor `3.6e-3` (GJ per kWh) is equivalent to `GJ_PER_KWH` defined in `config.py:111`, but the code uses the magic number instead. Similarly, `1e9 / 1e6` (= 1e3, converting EJ×tC/GJ to MtC) appears twice without explanation.

**Impact**: No functional issue. Readability concern — a developer modifying unit handling must grep for magic numbers rather than changing a single config constant.

**Recommended fix**: Replace magic numbers with config constants:
```python
from ghim.config import GJ_PER_KWH

# electricity.py:126
capacity_gw = gen_ej / (t.capacity_factor * HOURS_PER_YEAR * GJ_PER_KWH * 1e-6)
```

And define a new constant for EJ-to-GJ conversion:
```python
# config.py
GJ_PER_EJ: float = 1e9
MT_PER_T: float = 1e-6
```

---

### Issue 8: Dual Logit Systems

**Severity**: LOW

**Location**: `electricity.py:55-76`

**Code**:
```python
def calibrate(self, base_shares, fuel_prices):
    # ...
    # Calibrate preference factors (MERGE-style)
    self.pref_factors = preference_calibrate(shares_arr, costs_arr, self.scale_k)
    self.base_pref_factors = self.pref_factors.copy()

    # Initialize stock shares to base-year
    self.current_shares = shares_arr.copy()

    # Also calibrate legacy share weights for backward compat
    weights = logit_calibrate(shares_arr, costs_arr, self.logit_exp)
    for t, w in zip(self.techs, weights):
        t.share_weight = float(w)
```

**Root cause**: Two logit systems are calibrated and maintained:
1. **Preference factor logit** (MERGE-style): `preference_calibrate()` → `self.pref_factors`
2. **Relative-cost logit** (GCAM-style): `logit_calibrate()` → `t.share_weight`

During `compute_supply()` (line 99-103), only the preference logit is used when `self.pref_factors is not None` (which is always true after calibration). The legacy logit weights are calibrated but never used in practice.

**Impact**: Wasted computation during calibration and potential confusion about which system is active. The `share_weight` attribute on each `Technology` object is set but never read in the active code path.

**Recommended fix**: Either remove the legacy logit calibration:
```python
# Remove lines 73-75:
#   weights = logit_calibrate(shares_arr, costs_arr, self.logit_exp)
#   for t, w in zip(self.techs, weights):
#       t.share_weight = float(w)
```
Or explicitly document which system is primary and add a flag to select between them.

---

### Issue 9: `EJ_PER_MTOE` Defined but Unused

**Severity**: LOW

**Location**: `config.py:110`

**Code**:
```python
EJ_PER_MTOE: float = 0.04186  # exajoules per million tonnes of oil equivalent
```

**Verification**: Grep for `EJ_PER_MTOE` across `ghim/` returns only the definition. Not imported anywhere.

**Impact**: Dead code. The constant is correct (1 Mtoe ≈ 0.04186 EJ) but serves no purpose.

**Recommended fix**: Remove if not planned for future use, or add a `# TODO` comment if needed later.

---

## Parameter Inventory

Every constant in `config.py` with its usage status:

| Parameter | Value | Used? | Used In |
|-----------|-------|-------|---------|
| `GHIM_DATA_EXT` | `Path(...)` | YES | `regions.py`, `loader.py`, `ssp.py` |
| `HISTORY_START` | `2000` | YES | `config.py` (derives `HISTORICAL_YEARS`) |
| `BASE_YEAR` | `2020` | YES | `ssp.py`, `klem.py`, `recursive.py` |
| `END_YEAR` | `2150` | YES | `config.py` (derives `FUTURE_YEARS`) |
| `TIMESTEP` | `5` | YES | `ssp.py`, `klem.py`, `recursive.py`, `electricity.py` |
| `HISTORICAL_YEARS` | `[2000..2020]` | YES | `config.py` (part of `MODEL_YEARS`) |
| `FUTURE_YEARS` | `[2025..2150]` | YES | `config.py` (part of `MODEL_YEARS`) |
| `MODEL_YEARS` | `[2000..2150]` | YES | `ssp.py`, `klem.py`, `recursive.py` |
| `NUM_PERIODS` | `31` | YES | Used in tests |
| `DISCOUNT_RATE` | `0.05` | YES | `technology.py` (CRF for LCOE) |
| `DEPRECIATION_RATE` | `0.05` | YES | `klem.py` (capital decay) |
| `LABOR_FORCE_PARTICIPATION` | `0.65` | YES | `klem.py` (global, see Issue #6) |
| `CAPITAL_SHARE` | `0.3` | YES | `klem.py` (alpha) |
| `SAVINGS_RATE` | `0.22` | YES | `klem.py` (investment) |
| `INVESTMENT_CAP_RATE` | `0.10` | YES | `klem.py` (investment cap) |
| `SIGMA_VA` | `0.5` | NO | Defined but not used in current code |
| `SIGMA_EM` | `0.5` | YES | `klem.py` (energy demand price response) |
| `SIGMA_E` | `1.0` | NO | Defined but not used in current code |
| `SIGMA_NE` | `2.0` | NO | Defined but not used in current code |
| `DEFAULT_LOGIT_EXP` | `-3.0` | YES | `demand.py` (default logit) |
| `ELEC_LOGIT_EXP` | `-4.0` | YES | `electricity.py` |
| `REFINING_LOGIT_EXP` | `-6.0` | YES | `refining.py` |
| `HYDROGEN_LOGIT_EXP` | `-3.0` | YES | `hydrogen.py` |
| `DEMAND_LOGIT_EXP` | `-3.0` | YES | `demand.py` |
| `PREF_LOGIT_SCALE` | `0.3` | YES | `electricity.py`, `hydrogen.py` |
| `PREF_DECAY_RATE` | `0.02` | **NO** | Defined but never used (Issue #5) |
| `TURNOVER_TIMES` | `dict` | YES | `electricity.py`, `hydrogen.py`, `demand.py` |
| `LEARNING_RATES` | `dict` | YES | `technology.py` |
| `COST_FLOOR_FRACTION` | `0.2` | YES | `technology.py` |
| `PRICE_TOL` | `1e-3` | YES | `recursive.py` |
| `MAX_PRICE_ITER` | `100` | YES | `recursive.py` |
| `PRICE_DAMP` | `0.5` | YES | `recursive.py` |
| `EJ_PER_MTOE` | `0.04186` | **NO** | Never imported (Issue #9) |
| `GJ_PER_KWH` | `0.0036` | NO | Defined but magic number `3.6e-3` used instead (Issue #7) |
| `HOURS_PER_YEAR` | `8760.0` | YES | `electricity.py`, `hydrogen.py`, `technology.py` |
| `TC_TO_TCO2` | `44/12` | YES | `recursive.py` |
| `DEFAULT_SSP` | `"SSP2"` | YES | `ssp.py`, `run.py` |
| `CARBON_COEFS` | `dict` | YES | `recursive.py`, `technology.py` |
| `capital_recovery_factor()` | function | YES | `technology.py` |

**Unused parameters**: `SIGMA_VA`, `SIGMA_E`, `SIGMA_NE`, `PREF_DECAY_RATE`, `EJ_PER_MTOE`, `GJ_PER_KWH`

Note: `SIGMA_VA`, `SIGMA_E`, `SIGMA_NE` are CES elasticities reserved for future KLEM nesting (capital-labor, electric vs non-electric, among non-electric fuels). They are not yet wired into the production function.

---

## TFP Calibration Walkthrough

### Step 1: Constructor (`klem.py:30-58`)

Given base-year (2020) values:
```
base_gdp = GDP_SSP(2020)        # billion USD PPP
base_population = Pop_SSP(2020) # millions
base_energy = total_final       # EJ (sum of industry + buildings + transport)
```

Derived values:
```
K = base_gdp * 3.0              # K/Y ratio assumption
L = base_population * 0.65      # labor force
KL = K^0.3 * L^0.7
A_base = base_gdp / KL          # base TFP
```

### Step 2: Trajectory (`klem.py:67-95`)

For each year t in [2000, 2005, ..., 2150]:
```
Y_SSP(t) = SSP GDP for year t
Pop(t) = SSP population for year t
L(t) = Pop(t) * 0.65

KL(t) = K_ref(t)^0.3 * L(t)^0.7
A(t) = Y_SSP(t) / KL(t)

I_ref = min(0.22 * Y_SSP(t), 0.10 * K_ref(t))
K_ref(t+5) = (1 - 0.05)^5 * K_ref(t) + I_ref * 5
```

### Step 3: Simulation (`klem.py:106-109`)

At each period, TFP is retrieved from the trajectory:
```
A(t) = _tfp_trajectory[t]       # fixed
Y = A(t) * K(t)^0.3 * L(t)^0.7 # K is endogenous (different from K_ref)
```

The difference between `K_ref` (reference path) and actual `K` (endogenous) creates the energy cost feedback: energy costs reduce net output, reduce investment, reduce K, reduce Y relative to SSP.

---

## Capital Accumulation Verification

Equation in `klem.py:161-167`:
```python
def update_capital(self, investment):
    decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP
    self.capital_stock = decay * self.capital_stock + investment * TIMESTEP
```

This discretizes the continuous depreciation equation K'(t) = I - δK as:
```
K(t+dt) = (1-δ)^dt * K(t) + I * dt
```

With δ=0.05, dt=5: `(1-0.05)^5 = 0.7738`. So each period, ~23% of capital depreciates. This is standard DICE-style accumulation.

**Potential issue**: `investment * TIMESTEP` assumes constant investment over the period. With `SAVINGS_RATE = 0.22` and `INVESTMENT_CAP_RATE = 0.10`, the cap binds when `0.22 * net_output > 0.10 * K`, i.e., when `net_output > 0.45 * K`. With K/Y ≈ 3, this means the cap binds when net_output < 0.45 * 3 * gross_output, which is always true. So the investment cap is essentially always binding, limiting investment to 10% of K per year. This is a design choice, not a bug.

---

## CES Calibration Correctness

`ces.py:144-184` implements standard CES calibration from Arrow-Chenery-Minhas-Solow (1961).

Given observed inputs X_i, prices p_i, and assumed σ:
1. Compute cost shares: s_i = p_i * X_i / Σ(p_j * X_j)
2. Recover α_i = s_i * p_i^(σ-1) / Σ(s_j * p_j^(σ-1))
3. Normalize: α_i / Σ(α_j)

Special cases correctly handled:
- σ = 1 (Cobb-Douglas): α_i = s_i (cost shares = CES shares)
- σ → 0 (Leontief): α_i = X_i / Y (fixed proportions)

**Verification**: The `ces_output` → `ces_calibrate` → `ces_output` roundtrip reproduces base-year output. This is tested in the test suite.

---

## Edge Case Table

| Condition | Trigger | Behavior | Consequence |
|-----------|---------|----------|-------------|
| Zero GDP | Bad SSP scenario | `capital_stock = 0`, `kl = 0` | TFP = 1.0 (arbitrary), Y = 0 forever |
| Zero population | Bad SSP scenario | `labor = 0`, `kl = 0` | TFP = 1.0 (arbitrary), Y = 0 forever |
| Zero energy demand | `base_energy = 0` | `compute_energy_demand()` returns 0 | No energy costs, full GDP available |
| Negative net output | Large energy costs | Floored at 1% of gross | `max(net, 0.01 * gross_output)` at `klem.py:152` |
| Price non-convergence | Oscillating markets | Uses last iteration prices | Silent, may compound errors |
| Zero fuel price | Renewables (hydro, wind, solar) | LCOE = capital cost only | Correct behavior |
| Very high energy price | Supply shock | `price_ratio ** (-0.5)` → demand drops | Correct, bounded by max() on price_ratio |

---

## Unit Consistency Matrix

| Function | Input Units | Output Units |
|----------|-------------|--------------|
| `KLEMDriver.__init__` | GDP: B$, pop: M, energy: EJ | — |
| `compute_gross_output` | pop: M | B$ |
| `compute_energy_demand` | GDP: B$, price index: dimensionless | EJ |
| `compute_energy_cost` | energy: EJ, price: $/GJ | B$ (EJ × $/GJ = 1e9 GJ × $/GJ / 1e9 = B$) |
| `compute_net_output` | GDP: B$, cost: B$ | B$ |
| `compute_investment` | net_output: B$ | B$/yr |
| `update_capital` | investment: B$/yr | K: B$ |
| `ElectricitySector.compute_supply` | prices: $/GJ, demand: EJ | gen: EJ |
| `ElectricitySector.weighted_cost` | prices: $/GJ | $/GJ |
| `Technology.levelized_cost` | fuel_price: $/GJ | $/GJ |
| `Technology.annual_emissions_tc` | output: EJ | MtC |
| `FinalDemand.compute_demand` | GDP: B$, prices: $/GJ | carrier: EJ |
| `solve_period` → `emissions_mtco2` | — | MtCO2 |

**Key conversions in the code**:
- EJ → GJ: × 1e9 (used in energy cost: `energy_ej * avg_price_per_gj` works because EJ × $/GJ = 1e9 × $ / 1e9 = B$)
- EJ → GW capacity: `EJ / (CF × 8760h × 3.6e-3 GJ/kWh × 1e-6 EJ/GJ)` at `electricity.py:126`
- tC/GJ × EJ × 1e9 GJ/EJ / 1e6 t/Mt = MtC at `recursive.py:265`
