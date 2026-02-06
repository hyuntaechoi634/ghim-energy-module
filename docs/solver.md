# Recursive-Dynamic Solver

## Solution Approach

GHIM uses a **recursive-dynamic** (also called "myopic" or "period-by-period") solution method. Unlike intertemporal optimization models (such as REMIND or MERGE) that solve for the entire time horizon simultaneously, GHIM solves each 5-year period sequentially, using the results from period $t$ as initial conditions for period $t + \Delta t$.

This approach is computationally simpler and does not require agents to have perfect foresight about future prices and policies. It is the same method used by GCAM and is well-suited for scenario exploration where the focus is on "what-if" analysis rather than finding globally optimal pathways.

## Algorithm

For each period $t$ (2020, 2025, ..., 2100) and each region $r$:

### Step 1: Read drivers

Retrieve exogenous population $Pop(r, t)$ and GDP $Y(r, t)$ from the SSP scenario data.

### Step 2: Price iteration (market clearing)

The model iterates on energy prices until supply costs converge. The iteration loop:

```
Initialize: prices = {carrier → $/GJ} from previous period

For iteration = 1, 2, ..., max_iter:
    1. Compute energy price index (relative to base year)
    2. KLEM: total energy demand E(t) from GDP and price index
    3. Final demand: allocate E(t) across sectors and carriers via logit
    4. Electricity: compute generation mix and supply cost
    5. Refining: compute refined liquids cost
    6. Hydrogen: compute production mix and supply cost
    7. Update prices with damping:
       p_new = p_old + λ · (p_supply - p_old)
    8. Check convergence: max|Δp/p| < tolerance
```

### Step 3: Post-solution

After convergence:
- Compute CO$_2$ emissions from all combustion sources
- Record the `PeriodResult` for this region and period
- Use updated prices and state as initial conditions for the next period

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

Primary fuel markets (coal, gas, oil) use **exogenous prices** in Phase 1 — they respond to resource depletion through the grade-based supply curves but do not iterate to market clearing. This is a simplification; full market clearing for primary fuels is planned for Phase 2.

## Period linkage

Information that carries forward between periods:

| State variable | Mechanism |
|---------------|-----------|
| Fuel prices | Previous-period equilibrium prices serve as initial guess |
| Share weights | Calibrated logit weights persist (no learning curves yet) |
| Capital stock | Updated via $K(t+\Delta t) = (1-\delta)^{\Delta t} K(t) + I \cdot \Delta t$ |
| Resource depletion | Cumulative extraction updated for fossil fuels |

## Computational performance

The model solves 10 regions $\times$ 17 periods = 170 region-period combinations. Each typically converges in 3–10 price iterations. Total wall time is approximately **5 seconds** on a modern laptop (Python 3.11, no parallelization).

**Implementation**: [`ghim/solver/recursive.py`](../ghim/solver/recursive.py) — functions `solve_period`, `run_model`, dataclasses `PeriodResult`, `RegionModel`.
