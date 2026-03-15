# GHIM Energy Module — Trade Design

## 1. Overview

Trade clears global markets for primary energy commodities. Each commodity has regional supply curves and regional demands. A **world price** equilibrates global supply and demand; regions face **delivered prices** (world price + transport cost).

Trade clearing is embedded inside the model's fixed-point iteration $F(x) = x$. Each evaluation of $F$ runs bisection for each commodity independently. Cross-commodity interactions (e.g., gas price → coal demand) are resolved by the outer fixed-point solver.


## 2. Traded Commodities (5)

| Commodity | Resource Type | Supply Model | Phase 1 Data |
|-----------|--------------|-------------|--------------|
| Coal | Depletable | Grade-based curves | GCAM `fos_curves_R32.csv` |
| Oil | Depletable | Grade-based curves | GCAM `fos_curves_R32.csv` |
| Gas | Depletable | Grade-based curves | GCAM `fos_curves_R32.csv` |
| Uranium | Depletable | Grade-based curves | GCAM `L111.RsrcCurves_EJ_R_Uran` |
| Biomass | Renewable (annual flow) | Regional potential curves | GCAM `L111.RsrcCurves_EJ_R_Bior` |

### Demand sources by commodity

| Commodity | Demanded by |
|-----------|-------------|
| Coal | Electricity (coal, coal+CCS), H₂ production (coal gasif.), Industry EU, Buildings, Agriculture, District Heating |
| Oil | Oil Refining transformation (crude → refined products) |
| Gas | Electricity (gas, gas+CCS), H₂ production (SMR), Industry EU, Buildings, Agriculture, Transport (NG), District Heating |
| Uranium | Electricity (nuclear) |
| Biomass | Electricity (biomass, BECCS), Biorefining, H₂ production (biomass gasif.), Industry EU, Buildings, Agriculture, District Heating |


## 3. Supply Curves

### 3.1 Grade-based supply (fossil fuels + uranium)

Each region has a set of **grades** ordered by extraction cost. Each grade has a finite available quantity (EJ). Supply at a given price is the sum of all grades whose extraction cost ≤ price, with piecewise-linear interpolation:

$$Q_{supply,r}(p) = \sum_{g: c_{g,r} \leq p} q_{g,r} + \frac{p - c_{g,r}}{c_{g+1,r} - c_{g,r}} \times q_{g+1,r} \quad \text{(for the marginal grade)}$$

| Parameter | Meaning |
|-----------|---------|
| $c_{g,r}$ | Extraction cost of grade $g$ in region $r$ ($/GJ) |
| $q_{g,r}$ | Available quantity of grade $g$ in region $r$ (EJ) |

Piecewise-linear supply ensures continuity (no jumps at grade boundaries), which makes bisection well-behaved.

### Cumulative depletion

Depletable resources track cumulative extraction. As cheap grades are exhausted over time, the marginal cost rises:

$$available_{g,r}(t) = \max(0, \; q_{g,r} - cumulative\_extracted_{g,r}(t))$$

$$cumulative\_extracted_r(t+1) = cumulative\_extracted_r(t) + production_r(t) \times \Delta t$$

### 3.2 Biomass supply (renewable flow)

Biomass is a **renewable annual flow**, not a depletable stock. No cumulative depletion — supply replenishes each period. But total supply is constrained by **land availability** and **regional potential**.

$$Q_{biomass,r}(p) = \sum_{g: c_{g,r} \leq p} q_{g,r}^{annual}$$

| Biomass category | Supply driver | Phase 1 |
|-----------------|---------------|---------|
| Energy crops | Land allocation (AFOLU) | Exogenous potential |
| Crop residues | Agricultural output | Fixed fraction of $Q_{ag}$ |
| Forest residues | Forestry activity | Exogenous potential |
| Municipal solid waste | Population | Population-scaled |
| Traditional biomass | SSP scenario | Declining trajectory |

Total regional biomass supply capped by:

$$\sum_{uses} Biomass_{demand,r} \leq Biomass_{supply,r}$$

If demand exceeds supply, biomass price rises → biofuels become more expensive → logit share decreases. Market clearing via price iteration.

Phase 2+: AFOLU module constrains energy crop land allocation → biomass supply becomes endogenous.

### 3.3 Max annual production

All commodities have a max annual production cap per region to prevent unrealistic surges:

$$production_r(t) \leq cap\_factor \times production_{base,r}$$

Default: $cap\_factor = 3.0$ (3× base-year production).


## 4. Market Clearing

### 4.1 Bisection

For each commodity independently, find world price $p^W$ where global excess supply = 0:

$$\sum_{r} Q_{supply,r}(p^W + rent_r) = \sum_{r} D_r$$

Note: supply is evaluated at $p^W + rent_r$ (extraction cost + region-specific rent). See §6.1.

Bisection over $[p_{floor}, p_{ceiling}]$:

```
lo, hi = PRICE_FLOOR, PRICE_CEILING
for _ in range(MAX_ITER):   # ~20 iterations
    mid = (lo + hi) / 2
    excess = Σ_r supply_r(mid + rent_r) - Σ_r demand_r
    if |excess| < tol × Σ_r demand_r:
        break
    if excess > 0:    # oversupply → price too high
        hi = mid
    else:             # undersupply → price too low
        lo = mid
```

Bisection always converges (~20 iterations). Piecewise-linear supply is continuous and monotonically increasing in price, guaranteeing a unique root.

### 4.2 Net trade

Each region's net trade is production minus domestic demand:

$$X_r = Q_{supply,r}(p^W + rent_r) - D_r$$

- $X_r > 0$: net exporter
- $X_r < 0$: net importer
- $\sum_r X_r = 0$ by construction (global market clearing)

### 4.3 Scarcity premium

When demand exceeds maximum supply capacity at the ceiling price:

$$p^W = c_{highest} \times \frac{D_{total}}{Q_{max}} \quad (\text{capped at } p_{ceiling})$$

This signals absolute scarcity — all grades are exhausted and demand still exceeds supply.

### 4.4 Delivered prices

Regional delivered price = world price + transport cost:

$$p_{delivered,r} = p^W + tc_r$$

| Commodity | Transport cost range ($/GJ) | Source |
|-----------|---------------------------|--------|
| Coal | 0.50–0.65 | IEA Coal Trade |
| Oil | 0.24–0.30 | IEA Oil Market Report |
| Gas | 0.40–1.20 (pipeline vs LNG) | IEA Gas Trade |
| Uranium | ~0.05 (high energy density) | WNA |
| Biomass | 0.50–1.50 (bulky, regional) | IEA Bioenergy |

Phase 1: transport costs are fixed per region. Phase 2+: endogenous infrastructure investment (LNG terminals, pipeline capacity).


## 5. Integration with Fixed-Point Solver

### 5.1 How trade fits into $F(x) = x$

The state vector (see `economy.md` §5.2) includes 5 global world prices:

$$x = \bigl[\underbrace{Y_r,\; I_{E,r},\; p_{elec,r},\; p_{H_2,r}}_{4 \times 32},\; \underbrace{p^W_{coal},\; p^W_{oil},\; p^W_{gas},\; p^W_{bio},\; p^W_{U}}_{5}\bigr] \in \mathbb{R}^{133}$$

One evaluation of $F$:

```
F(x):
  1. Unpack Y, prices from x
  2. Compute sectoral demands (Industry, Buildings, Transport, Ag, Bunkers)
  3. Compute technology/carrier shares (logit)
  4. Aggregate fuel demands per region
  ─────────────────────────────────────────
  5. For fuel in [coal, oil, gas, uranium, biomass]:
         p^W_fuel ← bisection(fuel_demands)       # trade clearing
  ─────────────────────────────────────────
  6. p_elec ← weighted_LCOE(shares, fuel_prices)   # electricity
  7. p_RO ← refining_cost(p^W_oil)                 # refined oil
  8. p_BF ← weighted_LCOF(shares, p^W_bio)         # biofuels
  9. p_H2 ← weighted_LCOH(shares, fuel_prices)     # hydrogen
  10. p_Heat ← weighted_LCOH_DH(shares, fuel_prices) # district heat
  11. Y_new ← CES(K, L, E, M)                      # macro
  12. Return pack(Y_new, prices_new)
```

### 5.2 Why sequential bisection works

Alternative: solve all 5 commodity markets as a 5-dimensional root-finding problem within F.

In Phase 1, sequential bisection is **sufficient** because:

1. **Weak direct cross-effects**: Supply of coal doesn't depend on gas price. Supply curves are independent per commodity. Cross-effects are indirect (through the outer loop: gas price → electricity shares → coal demand).

2. **Fast**: 5 × ~20 iterations = ~100 supply curve evaluations per F call.

3. **Guaranteed convergence**: Bisection always works for monotone functions.

4. **Outer solver handles cross-effects**: Damped iteration on F propagates gas↔coal substitution across F evaluations (block Gauss-Seidel approach).

### 5.3 Convergence structure

```
Outer loop (fixed-point on F):  x_{n+1} = α·F(x_n) + (1-α)·x_n
  ├── Resolves cross-commodity effects (gas↔coal, oil↔biomass)
  ├── Resolves macro-energy feedback (Y↔E)
  ├── Resolves price-demand feedback (p↔D)
  ├── Typical: 3–10 iterations per period
  │
  └── Inner loop (bisection per commodity, inside each F):
      ├── Finds single-commodity clearing price
      ├── Always converges (~20 iterations)
      └── No cross-commodity interaction
```


## 6. Calibration

### 6.1 Rent calibration (per region, per commodity)

At the first projection period, calibration rents align model prices with observed market prices:

$$rent_{fuel,r} = \max(0, \; p_{observed,fuel} - p_{cleared,fuel})$$

The rent is **per-region, per-commodity**. It captures:
- Scarcity rents (OPEC market power for oil)
- Infrastructure constraints (pipeline access for gas)
- Quality premiums (coking coal vs thermal coal)
- Other factors not in the extraction cost curves

Computed once at the first projection period, held constant for all subsequent periods.

Rent enters bisection as a `price_adder`: supply for region $r$ is evaluated at $p^W + rent_{fuel,r}$, so the clearing price already incorporates regional rents. The returned world price includes rent.

### 6.2 Observed base-year prices

| Commodity | Observed price ($/GJ, 2020$) | Source |
|-----------|-------|--------|
| Coal | ~2.5–3.5 | IEA Coal Market Report |
| Oil | ~8–12 | Brent crude / IEA |
| Gas | ~3–6 (regional) | IEA, Henry Hub / TTF / JKM |
| Uranium | ~0.5–1.0 | WNA, spot market |
| Biomass | ~3–8 (regional) | IEA Bioenergy, IRENA |

### 6.3 GCAM deflator

GCAM supply curve costs are in 1975 USD. Conversion:

$$cost_{2020\$} = cost_{1975\$} \times 3.79$$

Deflator from BEA GDP deflator (FRED series GDPDEF): 1975$ → 2020$.


## 7. Stability Mechanisms

### 7.1 Inter-period price clamping

World prices are clamped to change at most 30% per period:

$$p^W(t) \in [p^W(t-1) \times 0.7, \; p^W(t-1) \times 1.3]$$

Prevents grade-boundary jumps where a small demand increase causes a large price jump (stepping onto the next grade).

### 7.2 Production inertia

Regional production declines are clamped to at most 30% per period:

$$production_r(t) \geq production_r(t-1) \times 0.7$$

Prevents cobweb oscillation where high prices cause overproduction, crashing prices next period. Growth is not constrained — only declines.

Excess production (from flooring declining regions) is redistributed by scaling down unconstrained regions to preserve total demand = total production.

### 7.3 Warm-start

Each period's trade clearing starts from the previous period's world prices. Since prices change slowly between periods, bisection converges in fewer iterations.

### 7.4 Demand-trade iteration

Within each F evaluation, demand and trade interact:

```
for round in range(MAX_ROUNDS):    # up to 10
    fuel_demands = compute_demands(prices)
    trade_results = clear_markets(fuel_demands)
    prices_new = delivered_prices(trade_results)
    if converged(prices, prices_new):
        break
    prices = dampen(prices, prices_new, factor=0.5)
```

50% damping prevents cobweb oscillation between demand estimation and trade clearing within a single F call.


## 8. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Commodity set | 5 (coal, oil, gas, uranium, biomass) | Add/remove via config |
| Supply curves (grades) | GCAM `fos_curves_R32.csv` | Per-commodity, per-region file |
| $cap\_factor$ (max production) | 3.0 | Global / per-commodity |
| Transport costs ($tc_r$) | Per-commodity, per-region | Per-commodity, per-region |
| $PRICE\_FLOOR$ | 0.01 $/GJ | Per-commodity |
| $PRICE\_CEILING$ | 100 $/GJ | Per-commodity |
| Price clamping rate | 30% per period | Global |
| Production inertia rate | 30% max decline | Global |
| Demand-trade damping | 0.5 | Global |
| Demand-trade max rounds | 10 | Global |
| Bisection tolerance | 1e-4 (relative) | Global |
| Bisection max iterations | 50 | Global |
| GCAM deflator | 3.79 (1975→2020$) | Global |
| Observed base-year prices | Per-commodity | Per-commodity |


## 9. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Fossil supply curves (grades) | GCAM `PREBUILT_DATA.rda` → `fos_curves_R32.csv` | R32 | Extraction costs in 1975$, convert via deflator |
| Uranium supply curves | GCAM `L111.RsrcCurves_EJ_R_Uran` | R32 | Same format as fossils |
| Biomass supply potential | GCAM `L111.RsrcCurves_EJ_R_Bior` | R32 | Annual flow, not depletable |
| Observed commodity prices | IEA, WNA | Global / regional | For rent calibration |
| Base-year production by region | IEA WEB via gcamdata | R32 | For production inertia baseline |
| Transport costs | IEA, literature | R32 | $/GJ per commodity per region |

### Data pipeline

```
GCAM PREBUILT_DATA.rda
  → scripts/export_fos_curves.R
  → ghim/data/external/energy/fos_curves_R32.csv   (costs in 1975$/GJ)
  → ghim/data/trade_cal.py  (deflation, aggregation, ResourceSupply objects)
```

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| Discovery/reserve growth curves | USGS, IEA WEO | For dynamic resource base |
| LNG terminal capacity | IEA Gas Trade | For gas market regionalization |
| Pipeline capacity by corridor | IEA, ENTSO-G | For gas transport constraints |
| H₂ trade infrastructure | IEA Hydrogen report | For hydrogen trade in Phase 2+ |
| Electricity interconnector capacity | ENTSO-E, regional grid data | For electricity trade in Phase 2+ |


## 10. IAMC Reporting Summary

### Prices (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Price\|Primary Energy\|Coal` | World price $p^W_{coal}$ |
| `Price\|Primary Energy\|Oil` | World price $p^W_{oil}$ |
| `Price\|Primary Energy\|Gas` | World price $p^W_{gas}$ |
| `Price\|Primary Energy\|Biomass` | World price $p^W_{bio}$ |

### Trade (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Trade\|Primary Energy\|Coal` | Net exports $X_r$ by region (EJ) |
| `Trade\|Primary Energy\|Oil` | Net exports $X_r$ by region (EJ) |
| `Trade\|Primary Energy\|Gas` | Net exports $X_r$ by region (EJ) |

### Primary Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Primary Energy\|{fuel}` | Sum of all fuel inputs across transformation + direct use |


## 11. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Commodities | Coal, Oil, Gas, Uranium, Biomass (5) | + Hydrogen, Electricity interconnectors |
| Supply curves | GCAM grade-based (static potential) | + Discovery/depletion dynamics |
| Biomass supply | Exogenous potential | AFOLU-constrained (land competition) |
| Market structure | Global pool (single world price) | + Regional markets (pipeline vs LNG for gas) |
| Transport costs | Fixed per region | + Infrastructure investment, LNG terminal capacity |
| OPEC behavior | Implicit in rent calibration | + Strategic supply withholding |
| Rent | Per-region, per-commodity, fixed at first projection | Same |
| Solver | Sequential bisection inside F | Same (sufficient for 5 commodities) |
| Depletion | Cumulative tracking (fossil, uranium) | + Discovery curves, reserve growth |
| Stability | Price clamping 30%, production inertia 30%, warm-start | Same |

### Phase transition notes

- **Phase 1 → 2**: Add hydrogen and electricity as traded commodities. Gas market splits into regional markets (pipeline-connected regions vs LNG-supplied). Biomass supply constrained by AFOLU land allocation. Transport costs become endogenous (infrastructure investment). Same bisection framework — just more commodities.
- **Phase 2 → 3**: OPEC strategic behavior (game-theoretic supply withholding). Discovery dynamics (new reserves found as price rises). Reserve growth models. Materials trade (steel, cement, chemicals) linked to Industry sector.
