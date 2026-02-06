# Recursive-Dynamic Solver

## Solution Approach

GHIM uses a **recursive-dynamic** (also called "myopic" or "period-by-period") solution method. Unlike intertemporal optimization models (such as REMIND or MERGE) that solve for the entire time horizon simultaneously, GHIM solves each 5-year period sequentially, using the results from period $t$ as initial conditions for period $t + \Delta t$.

This approach is computationally simpler and does not require agents to have perfect foresight about future prices and policies. It is the same method used by GCAM and is well-suited for scenario exploration where the focus is on "what-if" analysis rather than finding globally optimal pathways.

## Algorithm

For each period $t$ (2000, 2005, ..., 2150) and each region $r$:

### Step 1: Read drivers and initialize TFP

Retrieve exogenous population $Pop(r, t)$ and GDP $Y^{SSP}(r, t)$ from the SSP scenario data.

At model initialization (before the first period), call `init_tfp_trajectory()` to back out a total factor productivity (TFP) path $A(r, t)$ such that the Cobb-Douglas production function reproduces the SSP GDP trajectory in the absence of energy shocks:

$$Y^{SSP}(r, t) = A(r, t) \cdot K(r, t)^\alpha \cdot L(r, t)^{1-\alpha}$$

This TFP trajectory is computed once and held fixed for the entire simulation. The actual model GDP (net of energy costs) will deviate from the SSP path as endogenous energy dynamics take effect.

### Step 2: Price iteration (market clearing)

The model iterates on energy prices until supply costs converge. The iteration loop:

```
Initialize: prices = {carrier -> $/GJ} from previous period

[POLICY] Add carbon price to fossil fuel prices:
    p_f += carbon_coef_f * (44/12) * carbon_price

[POLICY] Prepare subsidy dicts and tech constraint lists

[POLICY] Compute AEEI cumulative factor

1. Set TFP from pre-computed trajectory: A = A(r, t)
2. Gross output from capital stock: Y = A * K^alpha * L^(1-alpha)

For iteration = 1, 2, ..., max_iter:
    3. Compute energy price index (relative to base year)
    4. KLEM: total energy demand E(t) from gross_output and price index
       [POLICY] E(t) *= AEEI_factor (global efficiency)
    5. Final demand: allocate E(t) across sectors and carriers via
       nested logit tree with preference factors and stock turnover
       [POLICY] Per-sector demand *= sector AEEI factor
    6. Electricity: compute generation mix and supply cost
       [POLICY] Subtract subsidies from tech costs
       [POLICY] Apply min/max share constraints after stock turnover
    7. Refining: compute refined liquids cost
    8. Hydrogen: compute production mix and supply cost
       [POLICY] Subtract subsidies from tech costs
       [POLICY] Apply min/max share constraints after stock turnover
    9. Update prices with damping:
       p_new = p_old + lambda * (p_supply - p_old)
   10. Check convergence: max|dp/p| < tolerance

After price convergence:
    11. Compute energy cost from equilibrium quantities and prices
    12. Compute emissions
    [POLICY] Revenue recycling: energy_cost -= carbon_price * emissions * fraction
    13. Net output: Y_net = Y_gross - energy_cost
    14. Investment: I = s * Y_net
    15. Capital update: K(t+dt) = (1-delta)^dt * K(t) + I * dt
```

Note that gross output is fully endogenous -- it depends on the capital stock $K$ accumulated from prior periods, not on the exogenous SSP GDP. The SSP GDP path is used only to initialize the TFP trajectory.

### Step 3: Post-solution

After convergence and the capital update:
- Compute CO$_2$ emissions from all combustion sources
- Apply preference factor decay for the next period (base-year values are frozen at calibration; decay shifts shares over time)
- Update learning curves: cumulative capacity drives cost reductions for eligible technologies
- Record the `PeriodResult` for this region and period (including policy fields: `carbon_price_usd_tco2`, `carbon_revenue_billion_usd`, `aeei_factor`)
- Use updated prices, capital stock, preference factors, stock shares, and cumulative capacity as initial conditions for the next period

### Step 4: Emissions cap bisection (optional)

When an emissions cap is active for a given year, `run_model()` wraps the year's solve with a bisection search:

1. Save region model states via `copy.deepcopy`
2. Bisect on a shadow carbon price $\tau \in [0, 2000]$ $/tCO$_2$
3. At each trial: solve all 10 regions, sum global emissions
4. Compare to cap: if within 2% tolerance, accept; otherwise narrow the search interval
5. Re-solve with the best carbon price found, which is reported in results

This allows the model to find the carbon price required to meet an exogenous emissions target without the user specifying the price directly.

## Convergence Parameters

| Parameter | Symbol | Value | Description |
|-----------|--------|-------|-------------|
| Price tolerance | $\epsilon_p$ | $10^{-3}$ | Relative price change threshold |
| Max iterations | $N_{max}$ | 100 | Maximum price iterations per period |
| Damping factor | $\lambda$ | 0.5 | Prevents oscillation in price updates |

The damping factor is critical: without it, the alternating supply-demand computation can oscillate. A value of $\lambda = 0.5$ means the price moves halfway toward the new equilibrium at each iteration, which provides a good balance between convergence speed and stability.

## Market clearing

The model clears three secondary energy markets in each period:

| Market | Supply side | Demand side |
|--------|------------|-------------|
| Electricity | Logit-weighted generation cost | Final demand from all sectors |
| Refined liquids | Refining LCOE (includes crude oil cost) | Transport and industrial demand |
| Hydrogen | Logit-weighted H$_2$ production cost | Industrial and transport demand |

Primary fuel markets (coal, gas, oil) use **exogenous prices** in Phase 1 -- they respond to resource depletion through the grade-based supply curves but do not iterate to market clearing. This is a simplification; full market clearing for primary fuels is planned for a future phase.

## Period linkage

Information that carries forward between periods:

| State variable | Mechanism |
|---------------|-----------|
| Fuel prices | Previous-period equilibrium prices serve as initial guess |
| Capital stock $K$ | Updated via $K(t+\Delta t) = (1-\delta)^{\Delta t} K(t) + I \cdot \Delta t$ |
| Preference factors | Base-year values frozen at calibration; decay applied each period to shift technology shares |
| Stock shares | Current shares persist via stock turnover (gradual fleet replacement) |
| Cumulative capacity | Tracks installed capacity for learning curve cost reductions |
| TFP trajectory | Fixed at initialization via `init_tfp_trajectory()`; not re-calibrated during the run |
| Resource depletion | Cumulative extraction updated for fossil fuels |

## Computational performance

The model solves 10 regions $\times$ 31 periods = 310 region-period combinations. Each typically converges in 3--10 price iterations. Total wall time is approximately **5--10 seconds** on a modern laptop (Python 3.11, no parallelization).

**Implementation**: [`ghim/solver/recursive.py`](../ghim/solver/recursive.py) -- functions `solve_period`, `run_model`, dataclasses `PeriodResult`, `RegionModel`. Policy injection uses [`ghim/policy.py`](../ghim/policy.py).
