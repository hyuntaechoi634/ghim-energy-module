# Inter-Regional Energy Trade

Detailed technical documentation for the inter-regional primary energy trade module in GHIM.

**Source files:**
- `ghim/energy/trade.py` — `GlobalMarket`, `TradeModule`, `TradeResult`
- `ghim/energy/supply.py` — `ResourceSupply`, `ResourceGrade`
- `ghim/data/trade_cal.py` — supply curve data pipeline
- `ghim/solver/recursive.py` — `_solve_regions_for_period()`, `compute_primary_fuel_demand()`
- `ghim/config.py` — trade parameters

---

## 1. Overview

The trade module clears global markets for three primary fuels — **coal**, **oil**, and **gas** — via bisection on grade-based supply curves. Each region has a supply curve derived from GCAM's fossil resource data, and faces a delivered price equal to the world clearing price plus a region-specific transport cost.

The module enables inter-regional arbitrage: low-cost producers export to high-cost consumers, and world prices rise over time as cheaper grades deplete.

**Design lineage:** The supply curve structure follows GCAM (`subresource.cpp:cumulsupply()`), with piecewise-linear interpolation between grades. Market clearing uses pure bisection (not Newton-Raphson), which is unconditionally stable for the monotonic supply functions. Price and production smoothing mechanisms prevent cliff-like transitions at grade boundaries.

---

## 2. Supply Curves

### 2.1 Resource Grades

Each region's supply for each fuel is modeled as an ordered list of **grades**, each with a resource quantity (EJ) and extraction cost ($/GJ):

```python
@dataclass
class ResourceGrade:
    available: float       # EJ total in this grade
    extraction_cost: float # $/GJ
```

Grades are sorted by ascending extraction cost. As cumulative extraction progresses, cheaper grades deplete and more expensive grades become the marginal source.

### 2.2 Piecewise-Linear Production (`production_at_price`)

Given a world price `P`, each region's producible quantity is computed via **piecewise-linear interpolation** between grade boundaries:

```
For each grade i (sorted by cost):
    remaining_i = max(0, available_i - max(0, cumulative_extracted - sum(available_0..i-1)))

    if P >= cost_i:
        production += remaining_i           (full grade available)
    else:
        prev_cost = cost_{i-1} if i > 0 else 0
        if P > prev_cost:
            fraction = (P - prev_cost) / (cost_i - prev_cost)
            production += remaining_i * fraction   (linear ramp)
        break
```

Key properties:
- **Continuous**: No step-function discontinuities — production ramps linearly between grade costs
- **First grade ramps from 0**: When `i = 0`, `prev_cost = 0`, so production linearly increases from 0 at price 0 to full grade at `cost_0`
- **Depletion-aware**: As `cumulative_extracted` increases, remaining quantities in cheaper grades shrink, and the effective marginal cost rises
- **Capped**: Final production is `min(total, max_annual_production)` if a cap is set

This matches GCAM's `cumulsupply()` function (with a monotonicity constraint) and ensures the bisection solver converges smoothly.

### 2.3 Grade-Boundary Cliffs

When a region depletes through a grade, the cheapest remaining grade may cost more than the world equilibrium price. The piecewise-linear interpolation returns 0 production when the world price is below the depleted-grade boundary cost:

```
Example: Middle East oil
  Grade 3 (depleted): cost = $4.927/GJ
  Grade 4 (available): cost = $6.838/GJ

  If world_price = $4.860/GJ:
    price < grade_3_cost → 0 production (cliff!)
```

GCAM has the same behavior but mitigates it through finer grade granularity and multiple subresources per fuel. GHIM mitigates it through **production smoothing** (Section 7).

---

## 3. Data Pipeline

### 3.1 Source Data

Supply curves originate from GCAM's `PREBUILT_DATA.rda`, extracted via `scripts/export_fos_curves.R` into `ghim/data/external/energy/fos_curves_R32.csv`. This contains grade-level data for 32 GCAM regions, 3 fuels, multiple subresources per fuel.

### 3.2 R32 to R10 Aggregation (`trade_cal.py`)

```
fos_curves_R32.csv (32 GCAM regions)
    │
    ▼ GDP-share downscaling
Country-level curves (~200 countries)
    │
    ▼ ISO → R10 mapping (region_classification.tsv)
R10-level curves (10 AR6 regions)
    │
    ▼ Aggregate by (r10, fuel, extraction_cost)
Final supply curves
    │
    ▼ Convert 1975$ → 2020$ (× GCAM3_TO_2020_DEFLATOR = 3.79)
Ready for trade module
```

**Step 1: GDP-share downscaling.** Each R32 region's grade quantities are split among its constituent countries proportionally to their GDP (PPP, 2020). For example, if country X has 40% of R32 region 1's GDP, it gets 40% of each grade's available quantity. Extraction costs are unchanged (cost is per GJ, independent of volume).

**Step 2: Country → R10 mapping.** Each country is mapped to an AR6 R10 region via `region_classification.tsv`. Countries without a direct mapping fall back to the R32 → R10 hardcoded mapping.

**Step 3: R10 aggregation.** Grades with the same extraction cost within an R10 region are summed. This produces the final per-(R10, fuel) supply curves.

**Step 4: Dollar conversion.** GCAM internally uses 1975 US dollars. All extraction costs are multiplied by `GCAM3_TO_2020_DEFLATOR = 3.79` (BEA GDP deflator, 105.381/27.800) to convert to 2020 US dollars.

### 3.3 Production Cap

Each (region, fuel) pair has a `max_annual_production` cap:

```
max_annual_production = base_year_production * production_cap_factor
```

Default `production_cap_factor = 3.0`. This prevents resource stocks (thousands of EJ) from being extracted in a single 5-year period. Base-year production comes from `DEFAULT_PRIMARY_ENERGY`.

### 3.4 Transport Costs

Region-specific transport cost adders ($/GJ) are applied on top of the world price:

```
delivered_price(region) = world_price + transport_cost(fuel, region)
```

Base transport costs: coal $0.50/GJ (bulk shipping), oil $0.30/GJ (tanker), gas $0.80/GJ (LNG/pipeline). Regional multipliers reflect geography — e.g., Middle East oil transport is 0.4x (major producer/exporter), Eastern Asia gas is 1.5x (long-distance LNG import).

---

## 4. Market Clearing

### 4.1 Bisection Algorithm (`GlobalMarket.clear_market`)

For each fuel independently, the algorithm finds a world price where global supply equals global demand:

```
excess_supply(P) = sum_r(production_r(P + rent)) - sum_r(demand_r)
```

**Pure bisection** over `[PRICE_FLOOR, PRICE_CEILING]`:

```
lo = 0.10 $/GJ
hi = 50.0 $/GJ
for i in 1..50:
    mid = (lo + hi) / 2
    excess = global_excess_supply(mid)
    if |excess| < TRADE_PRICE_TOL * total_demand:
        break
    if excess > 0: hi = mid    (supply > demand → lower price)
    else:          lo = mid    (supply < demand → raise price)
clearing_price = (lo + hi) / 2
```

Convergence tolerance: 1% of total demand. With 50 iterations on a monotonic continuous function, bisection achieves ~15 decimal digits of precision — far tighter than the 1% tolerance.

### 4.2 Scarcity Premium

If maximum supply capacity at `PRICE_CEILING` is still below demand:

```
scarcity_ratio = total_demand / supply_at_highest_grade_cost
clearing_price = min(highest_grade_cost * scarcity_ratio, PRICE_CEILING)
```

This gracefully handles extreme depletion scenarios where no feasible price clears the market.

### 4.3 Production Allocation

After finding the clearing price, production per region is:

```
raw_production(region) = region.supply.production_at_price(world_price)
```

If total capacity exceeds demand (because bisection found price where supply slightly overshoots), all regions are scaled down proportionally:

```
if total_capacity > total_demand:
    scale = total_demand / total_capacity
    production(region) = raw_production(region) * scale
```

Net exports: `net_exports(region) = production(region) - demand(region)`.

---

## 5. Calibration Rent

### 5.1 Problem

GCAM supply curves reflect extraction costs, not market prices. Observed 2020 oil prices ($6.76/GJ) are much higher than the extraction cost of the marginal grade being produced (~$2/GJ). The difference is **scarcity rent** — economic profit earned by inframarginal producers.

### 5.2 Rent Computation

At the first projection period (2025), a preliminary market clearing is run with zero rent to get extraction-cost prices:

```
rent(fuel) = max(0, observed_price - cleared_extraction_cost_price)
```

Observed prices from BP Statistical Review 2020:
- Coal: $1.75/GJ
- Oil: $6.76/GJ
- Gas: $3.85/GJ

### 5.3 Rent-Aware Clearing

After calibration, all subsequent clearings include the rent as a **price adder**:

```
supply is evaluated at: extraction_cost_price + rent
world_price returned:   extraction_cost_price + rent
```

The bisection still searches over extraction-cost prices, but supply curves are evaluated at the higher effective price. This means regions produce as if the market price is higher (because it is, including the rent), and the returned world price includes the rent.

**Rents are calibrated once and held constant** across all periods. They do not respond to market conditions — they represent the structural markup that makes extraction-cost curves match observed prices.

---

## 6. Demand-Trade Iteration

### 6.1 Cobweb Problem

Energy demand depends on fuel prices. Fuel prices depend on supply-demand balance. If demand is computed at one set of prices and then clearing produces different prices, the next period starts from the wrong demand estimate, causing oscillation.

### 6.2 Iteration Loop

Each projection period runs a demand-trade iteration:

```
for iter in 1..10:
    1. Estimate primary fuel demands per region (at current delivered prices)
    2. Clear global markets → world prices + regional production
    3. Compute delivered prices per region
    4. Check convergence (max price change < 2% relative)
    5. Damped update: price_new = price_old + 0.5 * (price_cleared - price_old)
```

If the loop doesn't converge (oscillating between two states at grade boundaries), the last two demand estimates are averaged and a final clearing is run.

### 6.3 Demand Estimation (`compute_primary_fuel_demand`)

A lightweight demand estimate that doesn't update model state. It computes:

1. Gross output from current capital stock
2. Total energy demand from KLEM
3. Final demand by carrier (using current logit shares, not updating them)
4. Electricity fuel consumption (from current electricity sector shares)
5. Refining oil consumption
6. Hydrogen fuel consumption

Returns `{coal: X, oil: Y, gas: Z}` in EJ for one region. This is the demand signal fed into trade clearing.

### 6.4 Warm-Start

Each period's iteration begins with the previous period's cleared delivered prices, not default prices. This places the starting point near the converged solution, typically achieving convergence in 2-3 iterations instead of 6-8.

---

## 7. Inter-Period Smoothing

After within-period clearing converges, two smoothing mechanisms prevent unrealistic inter-period jumps.

### 7.1 Price Smoothing (`smooth_prices`)

World prices are clamped to change at most 30% per period relative to the previous period:

```
lo = prev_price * 0.70
hi = prev_price * 1.30
world_price = clamp(world_price, lo, hi)
```

This prevents sudden price jumps when a region crosses a grade boundary (e.g., depleting a cheap grade causes the marginal cost to jump to the next grade's cost).

**No-op at first projection period** (no previous prices to compare against).

### 7.2 Production Smoothing (`smooth_production`)

Per-region production declines are clamped to at most 30% per period:

```
floor = prev_production * 0.70
if current_production < floor:
    current_production = floor
```

**Iterative redistribution:** When constrained regions are floored, the "excess" production (added back to constrained regions) is absorbed by scaling down unconstrained regions. If this scaling causes new regions to violate the 30% limit, they are also floored, and the process repeats. The algorithm converges in at most N iterations (one per region).

```
constrained = {}
repeat:
    for region not in constrained:
        if production < prev * 0.70:
            production = prev * 0.70
            constrained.add(region)
            excess += (floor - original_production)
    scale_down unconstrained regions by excess
    if no new constrained: break
recompute net_exports
```

**Key properties:**
- Only constrains **declines**, not growth (a region can triple production in one period)
- Preserves total production (redistribution is zero-sum)
- No-op at first projection period (no previous production to compare)
- 30% decline per 5 years allows halving in ~10 years (0.7^2 = 0.49), consistent with real-world field decline rates

### 7.3 Processing Order

For each projection period:

```
1. Demand-trade iteration loop → solve_trade() (clearing with rent)
2. smooth_prices()               → clamp ±30% world price changes
3. smooth_production()           → clamp 30% max regional decline
4. record_world_prices()         → store for next period
5. record_regional_production()  → store for next period
6. Recompute delivered prices from smoothed values
7. Solve each region with delivered prices
8. update_depletion()            → uses SMOOTHED production
```

---

## 8. Resource Depletion

After each period, cumulative extraction is updated:

```
supply.cumulative_extracted += production * timestep
```

This shifts the supply curve rightward: cheaper grades have less remaining resource, and the effective marginal cost rises. Over time, this causes world prices to increase, reflecting real-world resource scarcity.

Depletion uses the **smoothed** production values (after `smooth_production`), so the actual depletion path is consistent with the reported production.

---

## 9. Historical Period Handling

For years 2000-2020 (historical periods), the trade module uses **observed prices** rather than market clearing:

```
delivered_price(region, fuel) = OBSERVED_FUEL_PRICES_2020[fuel] + transport_cost(region, fuel)
```

Synthetic trade results are created with `production = demand = DEFAULT_PRIMARY_ENERGY` per region (no trade flow). Depletion is accumulated at base-year production rates so that by 2025, supply curves reflect 20+ years of historical extraction.

At the base year (2020), `prev_world_prices` and `prev_regional_production` are seeded from observed prices and `DEFAULT_PRIMARY_ENERGY` respectively, providing the reference for first-projection-period smoothing.

---

## 10. Integration with Solver

### 10.1 Initialization (`run_model`)

```python
regional_supplies = build_regional_supplies()   # R32→country→R10 pipeline
transport_costs = default_transport_costs()      # region-specific $/GJ
trade_module = TradeModule(regional_supplies, transport_costs, enabled=True)
```

### 10.2 Per-Period Call

```python
period_results, prev_trade_prices = _solve_regions_for_period(
    region_models, gdp_df, pop_df, year, policy,
    trade_module, prev_trade_prices,
)
```

Returns:
- `period_results`: list of `PeriodResult` with trade metadata (world prices, net exports, domestic production, calibration rents)
- `prev_trade_prices`: dict of region → fuel → delivered price, passed to next period for warm-start

### 10.3 No-Trade Mode

With `--no-trade` flag, `trade_module = None` and all regions use default fuel prices from `_default_fuel_prices()`. No market clearing, no depletion, no trade flows.

---

## 11. Parameters Reference

| Parameter | Value | Description |
|-----------|-------|-------------|
| `TRADED_FUELS` | ["coal", "oil", "gas"] | Fuels with global markets |
| `TRADE_PRICE_TOL` | 0.01 $/GJ | Market clearing tolerance |
| `TRADE_MAX_ITER` | 50 | Bisection iterations per clearing |
| `TRADE_PRICE_FLOOR` | 0.10 $/GJ | Minimum world price |
| `TRADE_PRICE_CEILING` | 50.0 $/GJ | Maximum world price |
| `TRADE_DEMAND_MAX_ITER` | 10 | Max demand-trade iterations per period |
| `TRADE_DEMAND_DAMP` | 0.50 | Damping for price updates between demand iterations |
| `TRADE_DEMAND_TOL` | 0.02 | 2% relative price convergence for demand loop |
| `TRADE_MAX_PRICE_CHANGE` | 0.30 | Max 30% price change per period |
| `TRADE_MAX_PROD_DECLINE` | 0.30 | Max 30% production decline per region per period |
| `GCAM3_TO_2020_DEFLATOR` | 3.79 | 1975$ → 2020$ conversion (BEA deflator) |
| `production_cap_factor` | 3.0 | Max annual production = 3x base-year |

### Observed 2020 Fuel Prices

| Fuel | Price ($/GJ) | Source |
|------|-------------|--------|
| Coal | 1.75 | BP Statistical Review 2020, avg thermal coal |
| Oil | 6.76 | BP 2020, $41.84/bbl / 6.193 GJ/bbl |
| Gas | 3.85 | BP 2020, $4.06/mmBtu / 1.055 GJ/mmBtu |

---

## 12. Output Fields

Each `PeriodResult` includes trade metadata:

| Field | Type | Description |
|-------|------|-------------|
| `world_prices` | dict[str, float] | Fuel → world clearing price ($/GJ) |
| `net_exports_ej` | dict[str, float] | Fuel → net exports (EJ, positive = exporter) |
| `domestic_production_ej` | dict[str, float] | Fuel → regional production (EJ) |
| `calibration_rents` | dict[str, float] | Fuel → calibration rent ($/GJ) |

---

## 13. Known Limitations

1. **Single world price per fuel** — No price differentiation between grades of the same fuel (e.g., Brent vs WTI oil, thermal vs coking coal). All regions face the same world price plus transport cost.

2. **Static transport costs** — Transport costs are fixed parameters, not responsive to trade volumes, infrastructure investment, or route congestion.

3. **No strategic behavior** — OPEC-style production coordination is not modeled. All regions produce at their supply-curve-determined level.

4. **Static rents** — Calibration rents are computed once at 2025 and held constant. In reality, rents respond to market structure changes (new discoveries, technology shifts, policy changes).

5. **No fuel quality differentiation** — Coal is coal; the model doesn't distinguish between grades (anthracite, bituminous, lignite) within a fuel type.

6. **Approximate base-year data** — `DEFAULT_PRIMARY_ENERGY` values are approximate IEA 2020 values, affecting the production cap and depletion seeding.
