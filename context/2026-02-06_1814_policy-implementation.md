# Session: Policy Variables Implementation
**Date**: 2026-02-06
**Branch**: `cht/proj/phase-1`
**Commit**: `d70e2ddf0` — "Add policy variables: carbon pricing, subsidies, AEEI, emissions caps, tech constraints, revenue recycling"

## What Was Done

Implemented a complete policy layer for the GHIM energy model, going from zero policy infrastructure to 6 fully functional policy instruments with tests and documentation.

### New Files Created
- `ghim/policy.py` (~220 lines) — All policy dataclasses + loading + share constraint algorithm
- `ghim/tests/test_policy.py` (~280 lines) — 36 tests covering unit + integration
- `scenarios/carbon_tax_50.json` — Constant $50/tCO2 example
- `scenarios/net_zero_2050.json` — Multi-instrument decarbonization scenario
- `docs/policy.md` — Full policy documentation page

### Files Modified
- `ghim/solver/recursive.py` — 6 policy injection points in `solve_period()`, emissions cap bisection in `run_model()`, 3 new `PeriodResult` fields
- `ghim/energy/electricity.py` — `cost_adjustments`, `share_constraints`, `year` params on `compute_supply()`
- `ghim/energy/hydrogen.py` — Same pattern as electricity
- `ghim/run.py` — 4 new CLI args (`--policy`, `--carbon-price`, `--efficiency-rate`, `--recycling-fraction`)
- `ghim/output/reporting.py` — 3 new output columns
- 8 documentation pages updated

### Policy Types Implemented
1. **Carbon price** — $/tCO2 added to fossil fuel prices via CARBON_COEFS
2. **Renewable subsidies** — Per-tech $/GJ cost reduction
3. **Efficiency standards (AEEI)** — Cumulative demand multiplier (1-r)^elapsed
4. **Emissions cap** — Global MtCO2 cap with bisection on shadow carbon price
5. **Tech constraints** — Min/max share bounds with iterative clamp-and-redistribute
6. **Revenue recycling** — Fraction of carbon revenue offsets energy costs

### Key Design Decisions
- Carbon price injected at fuel level, NOT in `levelized_cost()` — automatic efficiency penalty
- AEEI in solver, NOT in `FinalDemand` — keeps demand class policy-unaware
- Share constraints use iterative clamp-and-redistribute (not preference factor adjustment)
- Emissions cap uses `copy.deepcopy` + bisection at `run_model()` level

### Test Results
- **76/76 tests pass** (40 existing + 36 new, zero regressions)
- All policy tests cover both unit behavior and solver integration
- Emissions cap test verifies positive shadow price under tight cap

### Bug Fixed During Implementation
- `apply_share_constraints()` initially used naive clamp-then-renormalize which inflated max-constrained shares back above the bound. Fixed with iterative clamp-and-redistribute algorithm.

## What's Still Missing (from audit)
- **HIGH**: TFP trajectory uses 2020 K for years 2000-2015 (`klem.py:77`)
- **HIGH**: Silent failure on invalid SSP scenario (`ssp.py:107`)
- **HIGH**: Zero population → arbitrary TFP fallback (`klem.py:85-86`)
- **MEDIUM**: Price iteration non-convergence is silent (`recursive.py:239`)
- **MEDIUM**: `PREF_DECAY_RATE` defined but never wired in (`config.py:61`)
- **MEDIUM**: `LABOR_FORCE_PARTICIPATION` global not regional (`config.py:32`)
- No climate feedback (temperature → damages)
- Default energy data is approximate, not from actual IEA database

## Next Steps (Potential)
- Wire in `PREF_DECAY_RATE` (currently defined but unused)
- Add regional carbon pricing (currently only global)
- CCS technologies as abatement option
- Climate module integration (Hector/FaIR)
- Fix HIGH-priority audit issues
