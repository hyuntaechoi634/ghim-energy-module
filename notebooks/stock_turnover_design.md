# Stock Turnover Redesign — Design Discussion Document

**Date**: 2026-02-10
**Status**: Draft for discussion
**Scope**: Electricity and hydrogen sectors only; demand sectors unchanged

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Survey of Stock Turnover Across 7 Major IAMs](#2-survey-of-stock-turnover-across-7-major-iams)
3. [GCAM Deep Dive](#3-gcam-deep-dive)
4. [GHIM's Current State](#4-ghims-current-state)
5. [Three Candidate Architectures](#5-three-candidate-architectures)
6. [Recommended Approach](#6-recommended-approach)
7. [Step-by-Step Implementation Plan](#7-step-by-step-implementation-plan)
8. [Verification Strategy](#8-verification-strategy)

---

## 1. Motivation

GHIM's current stock turnover uses a single equation to blend existing capacity shares toward logit-determined targets:

```
s_eff = s_current + (dt/tau) * (s_target - s_current)
```

This approach has fundamental limitations for **supply sectors** (electricity, hydrogen) where physical capital stocks determine output:

| Problem | Consequence |
|---------|-------------|
| **No plant age tracking** | A 5-year-old and 50-year-old coal plant retire at the same rate |
| **Homogeneous existing stock** | Cannot distinguish old coal plants from new ones |
| **Linear blend rate** | Real retirement follows S-curves, not constant fractions |
| **No concept of capacity (EJ)** | Only tracks shares, not the physical stock that produces them |
| **No early retirement** | Cannot model profit-based or policy-driven shutdown |
| **No lumpy retirement** | Cannot capture waves of plants retiring simultaneously (e.g., 1970s coal fleet) |
| **New investment mixed with old** | Logit target shares are applied to total output, not just new investment |

For **demand sectors** (buildings, transport, industry), share blending is appropriate — fuel-choice inertia in vehicle fleets, heating systems, and industrial furnaces is well captured by the tau-based approach. There is no need to track individual boiler vintages.

The redesign targets **electricity and hydrogen only**.

---

## 2. Survey of Stock Turnover Across 7 Major IAMs

### 2.1 GCAM — Explicit Vintage Bins

**Architecture**: Each 5-year model period creates a new technology vintage stored in `map<vintage_year, Technology*>`. Old vintages enter `VintageProductionState` and produce from residual capacity subject to multiplicative shutdown deciders.

**Retirement**: Two independent mechanisms multiply:
- **S-curve shutdown**: Smooth survival function centered at half-life, hard cutoff at lifetime
- **Profit shutdown**: Logistic function of `(revenue - variable_cost) / |variable_cost|`

**New investment**: Only the newest vintage receives new demand; old vintages produce from decaying capacity.

**Data**: Technology-specific parameters in `A23.globaltech_retirement.csv`:

| Technology | Lifetime | Half-life | Steepness | Profit median | Profit steepness |
|------------|----------|-----------|-----------|---------------|------------------|
| Coal (conv pul) | 60 yr | 30 yr | 0.1 | -0.1 | 6 |
| Gas CC | 45 yr | 22.5 yr | 0.1 | -0.1 | 6 |
| Nuclear (Gen II) | 60 yr | 30 yr | 0.1 | -0.1 | 6 |
| Biomass | 60 yr | 30 yr | 0.1 | -0.1 | 6 |
| Wind | 30 yr | — | — | — | — |
| Solar PV | 30 yr | — | — | — | — |
| Geothermal | 30 yr | — | — | -0.1 | 6 |
| Ref. liquids (steam/CT) | 45 yr | 22.5 yr | 0.1 | -0.5 | 6 |
| Wind offshore | 25 yr | — | — | — | — |

**Key insight**: Renewables (wind, solar) use hard lifetime cutoff only — no S-curve and no profit shutdown. This is because they have near-zero variable costs, making the profit decider inapplicable.

**Strengths**: Rich, realistic retirement behavior; well-calibrated from engineering data.
**Weaknesses**: Complex implementation; ~30 vintage objects per tech per sector per region.

### 2.2 MESSAGEix — Full LP Vintage Indexing

**Architecture**: Capacity is indexed by `(vintage_year, model_year)` as a full LP decision variable. The constraint `CAP(y^V, y) <= historical_new_cap(y^V) * remaining_capacity(y^V, y)` bounds old vintages.

**Retirement**: Hard lifetime cutoff via the `remaining_capacity` fraction (drops to zero at end of technical lifetime). The `technical_lifetime` parameter controls when capacity expires.

**New investment**: Endogenous LP decision `CAP_NEW(y)`. Old vintages can be idled (activity = 0) without explicit retirement — the LP naturally assigns zero dispatch when unprofitable.

**Strengths**: Mathematically elegant; early retirement is endogenous (LP just doesn't use it).
**Weaknesses**: Extremely large LP when many vintages × regions × technologies; requires commercial solver (CPLEX/Gurobi).

### 2.3 REMIND — Vintage-Weighted Depreciation

**Architecture**: Uses age-dependent depreciation weights `pm_omeg(vintage, year)` that track the fraction of capacity surviving. Weights are non-uniform: slow depreciation in the first half of life, accelerating in the second half (REMIND documentation calls this "bathtub curve" depreciation).

**Retirement**: The `pm_omeg` weight naturally declines toward zero at the technology lifetime. Additionally, `vm_capEarlyReti` is an explicit early retirement decision variable, capped at 4% per year to prevent unrealistic instant phase-outs.

**New investment**: `vm_deltaCap(t,regi,te)` is the LP/NLP decision variable for new capacity additions.

**Strengths**: Intermediate complexity; vintage tracking without per-vintage technology objects.
**Weaknesses**: The 4%/yr early retirement cap is somewhat arbitrary; non-linear programming adds solver complexity.

### 2.4 WITCH — Aggregated Stock with Lifetime-Calibrated Delta

**Architecture**: Single aggregated capital stock `K(tech)` per technology, no vintage tracking. Depreciation rate `delta` is calibrated so that `(1-delta)^lifetime ≈ 0` (i.e., roughly the inverse of technical lifetime).

**Retirement**: Exponential decay: `K(t+1) = K(t) * (1-delta)^dt + dt * Investment / SpecificCost`. No age-dependent behavior — a technology built 5 years ago depreciates at the same rate as one built 50 years ago.

**New investment**: Allocated based on a nested logit over levelized costs, with learning-by-doing affecting future costs.

**Equation**:
```
K(t+Δ) = K(t) × (1−δ)^Δ + Δ × I(t) / SC(t)
```

where `K` is capacity (GW), `δ` is the annual depreciation rate, `I` is investment ($/yr), and `SC` is specific cost ($/GW).

**Strengths**: Very simple; easy to calibrate; computationally trivial.
**Weaknesses**: No realistic retirement profile; cannot model plant age; no early retirement mechanism. All existing stock depreciates uniformly regardless of age.

### 2.5 TIMES/MARKAL — Capacity Transfer Coefficients

**Architecture**: Capacity is tracked via `COEF_CPT(vintage, period)` — transfer coefficients that define what fraction of vintage `v` capacity remains operational in period `t`. These are precomputed based on technical lifetime and process availability.

**Retirement**: Fractional availability declining at end of life. If a process has lifetime 30 and period length 5, the last period of availability gets `COEF_CPT < 1.0` reflecting partial overlap.

**New investment**: LP decision variable `VAR_NCAP(t,p)` for new capacity in period `t` of process `p`.

**Strengths**: Extremely precise lifetime accounting; well-suited for 5-year periods.
**Weaknesses**: Requires careful precomputation of transfer coefficients; no economic early retirement in the standard formulation (extensions like TIMES-VT add this).

### 2.6 IMAGE/TIMER — Simulation with Logit Investment

**Architecture**: Simulation model (not optimization). Tracks installed capacity with age classes. Investment is allocated via multinomial logit over levelized costs.

**Retirement**: Two mechanisms:
1. **Technical lifetime**: Hard cutoff when capacity reaches end of life
2. **Early retirement rule**: When operating cost of existing plant exceeds LCOE of new-build replacement, the old plant is retired early

**New investment**: Logit share allocation among technologies, similar to GCAM but without the vintage bin complexity.

**Strengths**: Intuitive early retirement rule; simulation-based (no solver needed).
**Weaknesses**: Less formal than LP approaches; early retirement rule is a heuristic.

### 2.7 E3ME/FTT — Lotka-Volterra Differential Equations

**Architecture**: Uses differential equations from evolutionary dynamics. Market shares evolve via:

```
dS_i/dt = S_i × Σ_j S_j × A_ij × F_ij
```

where `A_ij` is the substitution matrix and `F_ij` is a pairwise cost comparison function. The natural turnover rate `1/tau` controls how fast obsolete technologies are displaced.

**Retirement**: Implicit — technologies lose market share through competitive displacement. The rate constant `1/tau` (inverse of technology lifetime) sets the maximum rate of change.

**New investment**: Not explicitly modeled — share changes implicitly allocate capacity.

**Strengths**: Elegant mathematical framework; captures path dependence and lock-in.
**Weaknesses**: No explicit capacity tracking; parameters (substitution matrix) are difficult to calibrate; cannot directly represent policy interventions like coal bans.

### Summary Comparison

| Model | Vintage Tracking | Retirement Type | Early Retirement | Complexity | Closest to GHIM |
|-------|-----------------|----------------|------------------|------------|-----------------|
| **GCAM** | Full (5-yr bins) | S-curve × profit | Economic | High | Target |
| **MESSAGEix** | Full (LP indexed) | Hard lifetime | Endogenous (LP) | Very high | Over-engineered |
| **REMIND** | Weighted (pm_omeg) | Non-uniform depreciation | Explicit variable, 4%/yr cap | Medium-high | Possible |
| **WITCH** | **None** | Exponential δ | None | Low | Current ceiling |
| **TIMES** | Transfer coefficients | Fractional end-of-life | Not standard | Medium | Possible |
| **IMAGE/TIMER** | Age classes | Lifetime + cost rule | Heuristic | Medium | Good fit |
| **E3ME/FTT** | None (shares) | Competitive displacement | Implicit | Low-medium | Too different |

**GHIM is currently simpler than WITCH** — the simplest model in this comparison. Even WITCH tracks actual capacity in GW/EJ rather than pure shares.

---

## 3. GCAM Deep Dive

This section documents the actual GCAM implementation from this repository's C++ code (`cvs/objects/technologies/`).

### 3.1 Vintage Lifecycle — Production State Machine

Each technology vintage transitions through distinct states managed by `ProductionStateFactory`:

```
RetiredProductionState → FixedProductionState (calibration) or
                         VariableProductionState (new investment) →
                         VintageProductionState (aging, subject to shutdown) →
                         RetiredProductionState (end of life)
```

**State transition logic** (from `production_state_factory.cpp`):

```cpp
if (aInvestYear == currYear) {
    // NEW: receives variable demand from solver
    return new VariableProductionState();
}
else if ((currYear > aInvestYear) &&
         ((aInvestYear + aLifetimeYears - investTimeStep) >= currYear)) {
    // VINTAGE: produces from base output × shutdown coefficient
    return new VintageProductionState();
}
else {
    // RETIRED: zero output
    return new RetiredProductionState();
}
```

Key points:
- A vintage becomes "vintage" one period after its investment year
- It remains vintage until `investment_year + lifetime - timestep >= current_year`
- After that, it transitions to retired (zero output forever)

### 3.2 S-Curve Shutdown — Age-Based Retirement

The S-curve decider (`s_curve_shutdown_decider.cpp`) computes a survival fraction based on plant age:

```cpp
double numYears = currentYear - installationYear;
double initialDis = 1.0 - 1.0 / (1.0 + exp(mSteepness * (0.0 - mHalfLife)));
double disAdj = numYears <= mHalfLife
                ? (1.0 - numYears / mHalfLife) * initialDis
                : 0.0;
scaleFactor = 1.0 / (1.0 + exp(mSteepness * (numYears - mHalfLife))) + disAdj;
```

**Three-part formula**:
1. **Main S-curve**: `1 / (1 + exp(k × (age - halfLife)))` — logistic centered at half-life
2. **Initial displacement correction**: Prevents the S-curve from starting below 1.0 at age=0 (since `1/(1+exp(-k×halfLife))` is slightly less than 1)
3. **Linear ramp-down of correction**: `disAdj` ramps linearly from `initialDis` to 0 over the first half-life, then stays at 0

**Numerical example** (coal plant: `halfLife=30, steepness=0.1`):

| Age (yr) | S-curve term | disAdj | Survival |
|----------|-------------|--------|----------|
| 0 | 0.953 | 0.047 | **1.000** |
| 10 | 0.881 | 0.032 | **0.912** |
| 20 | 0.731 | 0.016 | **0.747** |
| 30 | 0.500 | 0.000 | **0.500** |
| 40 | 0.269 | 0.000 | **0.269** |
| 50 | 0.119 | 0.000 | **0.119** |
| 55 | 0.076 | 0.000 | **0.076** |
| 60 | — (retired) | — | **0.000** |

The hard cutoff at `lifetime=60` is enforced by the state machine, not the S-curve itself.

### 3.3 Profit Shutdown — Economic Early Retirement

The profit decider (`profit_shutdown_decider.cpp`) computes a survival fraction based on profitability:

```cpp
double midPointToSteepness = pow(mMedianShutdownPoint + 1, mSteepness);
double shutdownFraction = mMaxShutdown *
    (midPointToSteepness /
     (midPointToSteepness + pow(aCalculatedProfitRate + 1, mSteepness)));
scaleFactor = 1.0 - shutdownFraction;
```

Where the **profit rate** is:
```
pi = (revenue - variable_cost) / |variable_cost|
```

**Key behavior** (with default `median=-0.1, steepness=6`):

| Profit Rate (pi) | Meaning | Shutdown Fraction | Survival |
|-------------------|---------|-------------------|----------|
| +0.5 | 50% profit margin | 0.02 | **0.98** |
| +0.1 | 10% profit margin | 0.12 | **0.88** |
| 0.0 | Breakeven | 0.28 | **0.72** |
| -0.1 | Revenue = 90% of costs | 0.50 | **0.50** |
| -0.3 | Revenue = 70% of costs | 0.86 | **0.14** |
| -0.5 | Revenue = 50% of costs | 0.95 | **0.05** |
| -1.0 | Zero revenue | 1.00 | **0.00** |

**Critical note**: Only **variable costs** (fuel + O&M) matter — capital costs are sunk and excluded. This means:
- Renewables (zero fuel cost) are effectively immune to profit shutdown
- Coal plants under carbon pricing face increasing variable costs and can be shut down early
- The -0.1 median means 50% shutdown when losing 10% on variable costs (fairly aggressive)

### 3.4 Multiplicative Composition

When both deciders apply to a single vintage:

```
output = base_output × s_curve_survival × profit_survival
```

**Example**: A 35-year-old coal plant with profit rate -0.15 under carbon pricing:
- S-curve survival at age 35: `0.378`
- Profit survival at pi=-0.15: `0.38`
- Combined: `0.378 × 0.38 = 0.144` → only 14.4% of original capacity running

This multiplicative composition means early retirement and age-based retirement compound aggressively.

### 3.5 Data Pipeline — How GCAM Gets Parameters

1. **Retirement CSV** (`A23.globaltech_retirement.csv`): Specifies per-technology lifetime, half-life, steepness, profit parameters
2. **R chunk** (`module_energy_L223.elec_T.R`): Reads CSV, adds retirement parameters to technology XML
3. **XML output** (`electricity.xml`): Contains `<s-curve-shutdown-decider>` and `<profit-shutdown-decider>` elements nested within each `<technology>`
4. **C++ model reads XML**: Constructs `IShutdownDecider` objects, attaches to `Technology` instances

For GHIM, we bypass this pipeline entirely and hardcode parameters in `config.py`, since we only need 8 electricity + 2 hydrogen technologies.

---

## 4. GHIM's Current State

### 4.1 Share Blending Mechanism

The current stock turnover lives in `ghim/energy/stock.py` (17 lines of code):

```python
def apply_stock_turnover(current_shares, target_shares, dt=TIMESTEP, turnover_time=30.0):
    blend_rate = min(float(dt) / turnover_time, 1.0)
    new_shares = current_shares + blend_rate * (target_shares - current_shares)
    new_shares = np.maximum(new_shares, 0.0)
    return new_shares / new_shares.sum()
```

**Turnover times** (`config.py`):
- Electricity: 40 years
- Hydrogen: 25 years
- Transport: 15 years
- Industry: 30 years
- Buildings: 50 years
- Data centers: 7 years

**The blend rate for electricity is**: `dt/tau = 5/40 = 0.125` per period — each period, shares move 12.5% toward the target. This means after 40 years (8 periods), shares have moved `1 - (1-0.125)^8 = 0.66` of the way. It takes ~100 years to reach 95% convergence.

### 4.2 Where Stock Turnover Is Applied

**Supply sectors** (electricity, hydrogen):
- `ElectricitySector.compute_supply()` line 163: `apply_stock_turnover(self.current_shares, target_shares, TIMESTEP, self.turnover_time)`
- `HydrogenSector.compute_supply()` line 165: identical pattern

**Demand sectors** (via nested tree):
- `DemandNode.compute_carrier_demands()` line 204: `apply_stock_turnover(self.current_shares, target_shares, TIMESTEP, self.turnover_time)`
- Applied at **every nesting level** — both structural splits (passenger/freight) and fuel choices

### 4.3 The Nestable Demand Tree Architecture

GHIM has an infinitely nestable demand tree that already supports the kind of structure we want:

```python
@dataclass
class DemandLeaf:
    name: str
    carrier: str  # energy carrier

class DemandNode:
    name: str
    children: list[DemandNode | DemandLeaf]  # recursive nesting
    base_shares: dict[str, float]
    scale_k: float          # preference logit sensitivity
    turnover_time: float    # stock inertia
    logit_exp: float        # cost elasticity
```

Each `DemandNode` can contain other `DemandNode` instances, creating arbitrary depth. Preference-factor logit + stock turnover applies at each level.

**Current demand tree structure** (2 levels):

```
transport (structural: τ=50y, k=0.05)
├── passenger (fuel choice: τ=15y)
│   ├── refined liquids: 87%
│   ├── electricity: 5%
│   ├── gas: 4%, hydrogen: 2%, biomass: 2%
└── freight (fuel choice: τ=15y)
    ├── refined liquids: 95%
    └── gas: 2%, electricity: 1%, hydrogen: 1%, biomass: 1%
```

**Electricity and hydrogen sectors are currently FLAT** — they use `ElectricitySector` and `HydrogenSector` classes that bypass the demand tree entirely. This is the key architectural gap.

### 4.4 Technology Object

Each technology (`ghim/energy/technology.py`) stores:
- Static properties: efficiency, capital cost, O&M, capacity factor, lifetime, carbon coefficient
- Learning-by-doing state: cumulative capacity, learning rate, cost floor
- Logit state: share weight (legacy), used by `ElectricitySector` for competition

**Lifetimes in Technology objects** (currently only used for CRF calculation, not retirement):

| Tech | Lifetime (yr) | Capital Cost ($/kW) | Capacity Factor |
|------|--------------|---------------------|----------------|
| Coal | 40 | 1,500 | 0.75 |
| Gas CC | 30 | 900 | 0.60 |
| Nuclear | 60 | 5,500 | 0.90 |
| Hydro | 80 | 2,500 | 0.45 |
| Wind | 25 | 1,200 | 0.35 |
| Solar | 30 | 900 | 0.22 |
| Biomass | 30 | 2,500 | 0.70 |
| Oil | 30 | 800 | 0.30 |

Note: These lifetimes are for **CRF calculation** (capital recovery). For retirement S-curves, we'll use separate (typically longer) lifetimes — consistent with GCAM, where the financial lifetime differs from the physical lifetime.

### 4.5 What's Missing

| Feature | Demand tree has it | Supply sectors have it |
|---------|--------------------|----------------------|
| Arbitrary nesting | Yes | No (flat) |
| Per-level turnover time | Yes | Single tau only |
| Preference factor logit | Yes | Yes |
| Stock turnover | Yes (shares) | Yes (shares) |
| **Capacity tracking (EJ)** | **No** | **No** |
| **Vintage bins** | **No** | **No** |
| **S-curve retirement** | **No** | **No** |
| **Profit-based shutdown** | **No** | **No** |

---

## 5. Three Candidate Architectures

### Architecture A: WITCH-Style Depreciation (Simplest)

**Concept**: Track actual capacity in EJ per technology (not just shares). Apply a lifetime-calibrated depreciation rate to the aggregate stock. New investment fills the gap between total demand and surviving capacity.

```python
class CapacityStock:
    capacity: dict[str, float]  # tech_name -> EJ installed
    delta: dict[str, float]     # annual depreciation rate per tech

    def step(self, year, target_shares, total_demand_ej):
        # Depreciate existing stock
        for tech in capacity:
            capacity[tech] *= (1 - delta[tech]) ** TIMESTEP
        # New investment fills gap
        surviving = sum(capacity.values())
        new_investment = max(total_demand_ej - surviving, 0)
        for tech in capacity:
            capacity[tech] += target_shares[tech] * new_investment
```

**Depreciation rates** (calibrated from lifetimes):
- Coal (lifetime 60): `delta = 1 - 0.05^(1/60) = 0.049` → 4.9%/yr
- Gas CC (lifetime 45): `delta = 0.064` → 6.4%/yr
- Wind (lifetime 30): `delta = 0.095` → 9.5%/yr

**Pros**:
- Trivial to implement (~50 lines)
- Already a significant improvement over pure share blending (tracks actual EJ)
- New investment is clearly separated from existing stock
- Learning curves get correct cumulative capacity

**Cons**:
- No age-dependent retirement (same delta regardless of plant age)
- Cannot model lumpy retirement events
- No early retirement mechanism
- Depreciation is uniform — unrealistic (plants don't lose 5% per year continuously; they work fine and then fail)

**Verdict**: Minimal viable improvement. Gets capacity tracking right but retirement behavior is unrealistic. If the only goal is "better than share blending with minimal effort," this works.

### Architecture B: Vintage Bin Model (GCAM-Inspired, Recommended)

**Concept**: Track capacity by vintage year (installation period). Each vintage decays via S-curve survival function. New investment is allocated by logit target shares. Optionally, profit-based early retirement can be layered on.

```python
@dataclass
class VintageStock:
    tech_names: list[str]
    lifetimes: dict[str, float]
    half_life_ratio: float = 0.75
    steepness: float = 0.1
    # capacity[tech][vintage_year] = EJ installed
    _capacity: dict[str, dict[int, float]]

    def s_curve_survival(self, tech, vintage_year, current_year) -> float
    def surviving_capacity(self, current_year) -> dict[str, float]
    def retire_and_invest(self, year, target_shares, total_demand_ej) -> np.ndarray
```

**Memory footprint**: ~30 vintage bins × 8 techs × 10 regions = 2,400 floats = trivial.

**Pros**:
- Realistic age-based retirement (S-curve matches engineering data)
- Clear separation: existing capacity decays, new investment via logit
- Easy to add profit-based shutdown later
- Capacity in EJ enables correct learning curve accumulation
- Parameters directly portable from GCAM's calibrated data
- Modest complexity — simpler than GCAM (no state machine, no LP, no XML pipeline)

**Cons**:
- More complex than Architecture A (~200 lines)
- Historical vintage initialization requires assumptions about past investment patterns
- S-curve parameters need validation (but GCAM values provide a starting point)

**Verdict**: Best balance of realism and complexity. This is the recommended approach.

### Architecture C: Vintage Cohorts as Logit Sub-Nests (Most Ambitious)

**Concept**: Unify supply sectors into the `DemandNode`/`DemandLeaf` tree pattern. Each technology's vintages become sub-nests that participate in logit competition. Old vintages compete with new ones based on their (lower) variable costs vs. the (full LCOE) cost of new builds.

```
electricity (sector level)
├── coal
│   ├── coal_v2000 (vintage: 20yr old, low variable cost, declining capacity)
│   ├── coal_v2005 (vintage: 15yr old)
│   ├── coal_v2010 (vintage: 10yr old)
│   ├── coal_v2015 (vintage: 5yr old)
│   └── coal_new  (current period: full LCOE)
├── solar
│   ├── solar_v2010, solar_v2015
│   └── solar_new
└── ... (other techs)
```

**Competition logic**:
- **Top-level logit**: Allocates total generation among technology families
- **Sub-nest logit**: Within each technology, old vintages compete with new vintage
- Old vintages have **zero capital cost** (sunk) → only variable cost (fuel + O&M)
- New vintage has **full LCOE** including capital
- S-curve survival **caps** old vintage capacity (even if logit wants to dispatch more)

**Pros**:
- Unified architecture — same `DemandNode`/`DemandLeaf` everywhere
- Economic dispatch emerges naturally from cost competition
- Profit-based shutdown is implicit (expensive old plants lose logit share)
- Could represent CCS retrofits as a vintage transformation
- Intellectually elegant — one framework for everything

**Cons**:
- Significantly more complex to implement (~500+ lines)
- Sub-nest logit parameters are hard to calibrate (what share weight for a 30-year-old coal plant?)
- Old vintages don't really "compete" in the logit sense — they either run or they don't
- Mixes two different concepts: capacity survival (physical) and dispatch (economic)
- Creates very deep nesting (3+ levels) in electricity, potentially causing numerical issues
- Over-engineers a problem that has a simpler natural solution (vintage bins)

**Verdict**: Architecturally interesting but over-engineered for GHIM's needs. The logit framework isn't a natural fit for "does this 40-year-old plant still survive?" — that's a physical question, not an economic competition question. The dispatch order within vintages should be a simple survival curve, not a logit.

### Trade-Off Summary

| Dimension | A: WITCH-style δ | B: Vintage Bins | C: Logit Sub-Nests |
|-----------|-------------------|-----------------|---------------------|
| **Implementation effort** | ~50 LOC | ~200 LOC | ~500+ LOC |
| **Retirement realism** | Low (exponential) | High (S-curve) | High (S-curve + economic) |
| **Early retirement** | Not supported | Additive (optional) | Implicit via logit |
| **Capacity tracking** | Yes (aggregate) | Yes (per vintage) | Yes (per vintage) |
| **Lumpy retirement** | No | Yes | Yes |
| **Calibration difficulty** | Easy (just δ) | Moderate (S-curve params from GCAM) | Hard (sub-nest weights) |
| **Integration with existing code** | Minimal changes | Moderate | Major refactor |
| **Risk of bugs** | Very low | Low | Medium-high |
| **Matches IAM practice** | WITCH only | GCAM, IMAGE, REMIND | Novel (no model does this) |

---

## 6. Recommended Approach

**Architecture B: GCAM-Inspired Vintage Bin Model**, simplified for GHIM's 10-region, 5-year-step structure.

### Why Architecture B

1. **Sufficient realism**: S-curve retirement captures the key physics — plants work fine for decades, then retire in a concentrated window around their half-life. This is the most important behavioral improvement over share blending.

2. **Clear separation of concerns**: Old capacity decays via survival curves (physical process). New investment is allocated by logit (economic process). These are naturally distinct mechanisms that shouldn't be forced into the same framework.

3. **Proven approach**: GCAM, IMAGE/TIMER, and REMIND all use vintage-based tracking. The parameters are well-documented and calibrated against engineering data.

4. **Modest complexity**: ~200 lines of new code, concentrated in a single new class (`VintageStock`). The interface to `ElectricitySector` and `HydrogenSector` changes minimally.

5. **Optional extensions**: Profit-based shutdown can be added later as a separate module that multiplies with S-curve survival — exactly how GCAM does it. No architectural changes needed.

6. **Demand sectors unchanged**: The tau-based share blending in `DemandNode` remains appropriate for fuel choice inertia. No need to track individual boiler vintages in buildings.

### Design Decisions

**Scope**: Electricity and hydrogen sectors only.

**S-curve parameters**: Use GCAM values as defaults, but with adjusted lifetimes matching GHIM's `Technology.lifetime` field (which is currently used for CRF only). Add separate retirement lifetimes in `config.py`:

| Tech | CRF Lifetime | Retirement Lifetime | Half-life | Steepness |
|------|-------------|---------------------|-----------|-----------|
| Coal | 40 yr | 60 yr | 45 yr | 0.1 |
| Gas CC | 30 yr | 45 yr | 34 yr | 0.1 |
| Nuclear | 60 yr | 60 yr | 45 yr | 0.1 |
| Hydro | 80 yr | 80 yr | 60 yr | 0.1 |
| Wind | 25 yr | 30 yr | — | — |
| Solar | 30 yr | 30 yr | — | — |
| Biomass | 30 yr | 60 yr | 45 yr | 0.1 |
| Oil | 30 yr | 45 yr | 34 yr | 0.1 |
| SMR | 25 yr | 30 yr | 23 yr | 0.1 |
| Electrolysis | 20 yr | 25 yr | — | — |

For renewables and electrolysis: **no S-curve**, just hard lifetime cutoff (matching GCAM's practice — near-zero variable costs make profit shutdown irrelevant, and maintenance-driven failure is a step function, not a gradual decline).

**Historical initialization**: At base year (2020), spread existing capacity uniformly across past vintages back to `base_year - lifetime`. This is a simplification — in reality, investment was not uniform — but it produces a reasonable age distribution for the first few decades. A future improvement could use IEA capacity age data.

**Profit shutdown**: **Not in initial implementation**. The S-curve alone provides a major improvement over share blending. Profit shutdown adds significant complexity (requires per-vintage revenue/cost tracking, marginal profit calculation, carbon price propagation to variable costs). It can be layered on in a future iteration.

**New investment allocation**: Only the retirement gap (total demand minus surviving capacity) receives new investment, allocated by logit target shares. If demand grows, the growth also goes entirely to new investment. If demand shrinks below surviving capacity, no new investment occurs, and existing capacity is proportionally scaled down.

---

## 7. Step-by-Step Implementation Plan

### Step 1: `VintageStock` Class — `ghim/energy/stock.py`

Add alongside the existing `apply_stock_turnover()` function (which stays for demand sectors):

```python
@dataclass
class VintageStock:
    """Track capacity by vintage year with S-curve retirement.

    Used for electricity and hydrogen sectors where physical capital
    stock determines output and retirement follows age-dependent curves.
    """
    tech_names: list[str]
    lifetimes: dict[str, float]         # per-tech retirement lifetime (years)
    half_life_ratio: float = 0.75       # half_life = lifetime * ratio
    steepness: float = 0.1              # S-curve shape parameter

    # capacity[tech_name][vintage_year] = EJ of installed capacity
    _capacity: dict[str, dict[int, float]] = field(default_factory=dict)

    def s_curve_survival(self, tech: str, vintage_year: int, current_year: int) -> float:
        """Compute fraction of vintage capacity surviving at current_year.

        Matches GCAM's s_curve_shutdown_decider formula exactly.
        """
        ...

    def surviving_capacity(self, current_year: int) -> dict[str, float]:
        """Total surviving capacity per technology at current_year."""
        ...

    def effective_shares(self, current_year: int) -> np.ndarray:
        """Compute effective generation shares from surviving capacity."""
        ...

    def retire_and_invest(
        self, year: int, target_shares: np.ndarray, total_demand_ej: float,
    ) -> np.ndarray:
        """Retire old capacity via S-curve, invest gap via logit shares.

        Returns effective shares (surviving + new) for the period.
        """
        ...

    def initialize_from_base_year(
        self, shares: np.ndarray, total_ej: float, base_year: int,
    ) -> None:
        """Distribute base-year capacity across past vintages (uniform)."""
        ...
```

**S-curve formula** (matching GCAM `s_curve_shutdown_decider.cpp` exactly):

```python
def s_curve_survival(self, tech, vintage_year, current_year):
    age = current_year - vintage_year
    lifetime = self.lifetimes[tech]

    if age >= lifetime:
        return 0.0
    if age <= 0:
        return 1.0

    half_life = lifetime * self.half_life_ratio

    # Check if this tech uses S-curve (has half_life > 0)
    # Renewables/electrolysis: hard cutoff only
    if half_life <= 0:
        return 1.0 if age < lifetime else 0.0

    # GCAM S-curve formula
    initial_dis = 1.0 - 1.0 / (1.0 + math.exp(self.steepness * (0.0 - half_life)))
    dis_adj = (1.0 - age / half_life) * initial_dis if age <= half_life else 0.0
    survival = 1.0 / (1.0 + math.exp(self.steepness * (age - half_life))) + dis_adj

    return max(0.0, min(1.0, survival))
```

**`retire_and_invest()` logic**:

```python
def retire_and_invest(self, year, target_shares, total_demand_ej):
    # 1. Compute surviving capacity per tech
    surviving = self.surviving_capacity(year)
    total_surviving = sum(surviving.values())

    # 2. Compute retirement gap
    new_investment_ej = max(total_demand_ej - total_surviving, 0.0)

    # 3. If demand shrank below surviving: scale down proportionally
    if total_demand_ej < total_surviving and total_surviving > 0:
        scale = total_demand_ej / total_surviving
        for tech in surviving:
            surviving[tech] *= scale
        total_surviving = total_demand_ej
        new_investment_ej = 0.0

    # 4. Allocate new investment by logit target shares
    for i, tech in enumerate(self.tech_names):
        new_cap = target_shares[i] * new_investment_ej
        if new_cap > 0:
            self._capacity[tech][year] = new_cap

    # 5. Compute effective shares
    total = total_surviving + new_investment_ej
    if total <= 0:
        return target_shares  # degenerate case

    effective = np.zeros(len(self.tech_names))
    for i, tech in enumerate(self.tech_names):
        effective[i] = (surviving.get(tech, 0.0) +
                       self._capacity[tech].get(year, 0.0)) / total

    return effective
```

### Step 2: Per-Technology Retirement Lifetimes — `ghim/config.py`

```python
# Retirement parameters for vintage tracking (electricity + hydrogen)
# Retirement lifetime >= CRF lifetime (financial vs physical)
TECH_LIFETIMES: dict[str, float] = {
    "coal": 60.0, "gas_cc": 45.0, "nuclear": 60.0, "hydro": 80.0,
    "wind": 30.0, "solar": 30.0, "biomass": 60.0, "oil": 45.0,
    "smr": 30.0, "electrolysis": 25.0,
}

# S-curve parameters (matching GCAM defaults)
SCURVE_STEEPNESS: float = 0.1
SCURVE_HALFLIFE_RATIO: float = 0.75

# Technologies using hard cutoff only (no S-curve) — near-zero variable cost
HARD_CUTOFF_TECHS: set[str] = {"wind", "solar", "hydro", "electrolysis"}
```

Keep `TURNOVER_TIMES` unchanged (used by demand sectors).

### Step 3: Integrate into `ElectricitySector` — `ghim/energy/electricity.py`

Changes:
- `__init__`: Create `VintageStock` from tech list + `TECH_LIFETIMES`
- `calibrate()`: Call `vintage_stock.initialize_from_base_year(shares, total_ej, BASE_YEAR)` to spread base-year capacity across past vintage years
- `compute_supply()`: Replace `apply_stock_turnover()` call with `vintage_stock.retire_and_invest(year, target_shares, total_demand_ej)`
- `current_shares` property: Delegates to `vintage_stock.effective_shares()`

The logit computation (preference factors, decay, alpha, share constraints) **stays exactly the same** — it still produces `target_shares`. The only change is what happens after: instead of blending shares linearly, we track actual capacity and invest only the gap.

### Step 4: Integrate into `HydrogenSector` — `ghim/energy/hydrogen.py`

Same pattern as electricity. Simpler since only 2 technologies (SMR, electrolysis).

### Step 5: Demand Sectors — No Change

`ghim/energy/demand.py` continues to use `apply_stock_turnover()` with `TURNOVER_TIMES`. The nested tree share blending is appropriate for fuel-choice dynamics within demand sectors.

### Step 6: Historical Vintage Initialization

For the base year, distribute existing capacity across past vintages assuming uniform historical investment:

```python
def initialize_from_base_year(self, shares, total_ej, base_year):
    for i, tech in enumerate(self.tech_names):
        cap = shares[i] * total_ej
        lifetime = self.lifetimes[tech]
        n_vintages = int(lifetime // TIMESTEP)
        if n_vintages <= 0:
            n_vintages = 1
        per_vintage = cap / n_vintages
        oldest = base_year - int(lifetime) + TIMESTEP
        for yr in range(oldest, base_year + 1, TIMESTEP):
            self._capacity.setdefault(tech, {})[yr] = per_vintage
```

This gives each technology a uniform age distribution spanning its full retirement lifetime. At `year = base_year`, all vintages are alive; as the model progresses, the oldest vintages begin to retire via S-curve.

**Limitation**: Uniform initialization is a simplification. In reality:
- Coal investment peaked in the 1960s-1980s (rich countries) and 2000s-2010s (China/India)
- Solar/wind investment was near-zero before 2005 and exponential after 2010
- Nuclear had a boom in the 1970s-1980s and near-zero new builds since

A future improvement could use IEA/IRENA historical capacity data to initialize with realistic vintage distributions. For now, uniform is acceptable because:
1. It produces the correct **total** capacity at base year
2. The S-curve survival shape means small errors in age distribution wash out within 2-3 periods
3. It's conservative — overestimates survival of very old plants, but the S-curve corrects this quickly

### Step 7: Solver Integration — `ghim/solver/recursive.py`

Minor changes:
- Ensure `total_demand_ej` is passed to `compute_supply()` (already the case)
- Vintage state automatically persists since `ElectricitySector` and `HydrogenSector` are persistent objects on `RegionModel`
- No structural changes to the solver loop

### Step 8: Update Tests

**Modify existing**:
- `ghim/tests/test_electricity.py`: Coal ban test should show S-curve decline instead of linear blend. The coal share trajectory changes from exponential approach to a capacity-decline-driven curve.
- `ghim/tests/test_solver.py`: Verify vintage stock persists across periods (it will automatically since sector objects persist on `RegionModel`).

**New tests** in `ghim/tests/test_stock.py`:
- `test_s_curve_survival()` — verify formula matches GCAM's C++ implementation with known values
- `test_hard_lifetime_cutoff()` — renewables reach zero at exactly `lifetime` years
- `test_vintage_retirement_over_time()` — capacity declines realistically over a 100-year simulation
- `test_new_investment_fills_gap()` — logit target shares are applied only to the retirement gap
- `test_effective_shares_from_vintages()` — shares correctly computed from surviving capacity
- `test_initialize_from_base_year()` — correct uniform distribution across vintage years
- `test_demand_shrink()` — when demand drops below surviving capacity, proportional scaling applies
- `test_no_negative_capacity()` — capacity never goes negative

### Step 9: Update Validation Notebook

Re-run `notebooks/stock_turnover_validation.ipynb` with:
- S-curve survival plots (compare with old linear blend rate)
- Vintage capacity stacked area charts showing age structure evolution
- Coal ban experiment: compare old (linear blend decline) vs new (S-curve retirement)
- 2050/2100 electricity share comparison table

---

## 8. Verification Strategy

### Unit Tests

```bash
python -m pytest ghim/tests/test_stock.py -v
```

Key assertions:
- S-curve survival at `age=0` returns 1.0
- S-curve survival at `age=half_life` returns ~0.5 (with displacement adjustment)
- S-curve survival at `age >= lifetime` returns 0.0
- Hard cutoff techs return 1.0 for `age < lifetime`, 0.0 for `age >= lifetime`
- `retire_and_invest()` returns shares summing to 1.0
- Total capacity equals demand after retire_and_invest

### Sector Tests

```bash
python -m pytest ghim/tests/test_electricity.py ghim/tests/test_hydrogen.py -v
```

### Full Suite

```bash
python -m pytest ghim/tests/ -v
```

### Behavioral Checks

Run full model and compare 2050/2100 electricity shares (old vs new):

| Metric | Expected Change |
|--------|----------------|
| Coal 2050 share | Longer tail (S-curve) but still declining |
| Coal 2100 share | Near zero (all 60yr vintages retired) |
| Solar/wind 2050 | Higher (more new investment captured) |
| Nuclear 2050 | Higher (60yr lifetime means more persistence) |
| Gas CC 2050 | Similar (45yr lifetime ≈ old tau=40yr) |

### Validation Notebook

Re-run `notebooks/stock_turnover_validation.ipynb` with vintage-based plots showing:
1. S-curve survival curves for each technology (with GCAM comparison)
2. Vintage age structure evolution (stacked area: capacity by vintage cohort)
3. Coal ban experiment: linear blend vs S-curve retirement trajectory
4. Generation mix evolution 2020-2150 (old behavior vs new)

---

## Appendix A: S-Curve Survival Values (Reference Table)

Computed using GCAM formula with `steepness=0.1, half_life_ratio=0.75`:

### Coal (lifetime=60, half_life=45)

| Age | Survival |
|-----|----------|
| 0 | 1.000 |
| 5 | 0.960 |
| 10 | 0.917 |
| 15 | 0.867 |
| 20 | 0.805 |
| 25 | 0.727 |
| 30 | 0.633 |
| 35 | 0.527 |
| 40 | 0.419 |
| 45 | 0.318 |
| 50 | 0.231 |
| 55 | 0.161 |
| 60 | 0.000 (retired) |

### Gas CC (lifetime=45, half_life=34)

| Age | Survival |
|-----|----------|
| 0 | 1.000 |
| 5 | 0.951 |
| 10 | 0.895 |
| 15 | 0.826 |
| 20 | 0.739 |
| 25 | 0.630 |
| 30 | 0.506 |
| 35 | 0.382 |
| 40 | 0.272 |
| 45 | 0.000 (retired) |

### Wind (lifetime=30, hard cutoff)

| Age | Survival |
|-----|----------|
| 0-25 | 1.000 |
| 30 | 0.000 (retired) |

---

## Appendix B: Comparison with Current Share Blending

**Scenario**: Coal ban at 2035 (alpha=0 for coal technology).

**Current behavior** (share blending, tau=40yr):
```
Year 2035: coal share = base_share × (1 - 5/40) = 0.875 × base
Year 2040: coal share = 0.875 × (1 - 5/40) = 0.766 × base
Year 2060: coal share = 0.464 × base
Year 2080: coal share = 0.237 × base
Year 2100: coal share = 0.121 × base  ← still 12% of base after 65 years!
```

Problem: 65 years after the ban, 12% of original coal capacity "persists" in shares even though no physical coal plant could survive that long.

**New behavior** (vintage bins, lifetime=60yr):
```
Year 2035: coal share determined by surviving vintages (no new investment)
Year 2060: oldest vintages (pre-2000) fully retired, recent (2015-2035) at 50-90% survival
Year 2080: all vintages installed before 2020 retired; 2020-2035 vintages at S-curve decline
Year 2095: last vintage (2035) reaches age 60, retired → coal share = 0.000
```

The vintage model guarantees **zero coal** within `lifetime` years of the last investment. The share blending model has an asymptotic tail that never reaches zero.

---

## Appendix C: Files to Modify

| File | Change Type | Description |
|------|------------|-------------|
| `ghim/energy/stock.py` | Add class | `VintageStock` class (keep `apply_stock_turnover` for demand) |
| `ghim/config.py` | Add params | `TECH_LIFETIMES`, `SCURVE_*`, `HARD_CUTOFF_TECHS` |
| `ghim/energy/electricity.py` | Modify | Use `VintageStock` instead of `apply_stock_turnover` |
| `ghim/energy/hydrogen.py` | Modify | Use `VintageStock` instead of `apply_stock_turnover` |
| `ghim/energy/demand.py` | **No change** | Keeps share blending |
| `ghim/solver/recursive.py` | Minor | Ensure vintage state passes through correctly |
| `ghim/tests/test_stock.py` | **New file** | Vintage tracking unit tests |
| `ghim/tests/test_electricity.py` | Modify | Update for S-curve behavior |
| `ghim/tests/test_solver.py` | Modify | Verify vintage persistence |
| `notebooks/stock_turnover_validation.ipynb` | Update | Vintage-based plots and comparisons |
