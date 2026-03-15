# GHIM Energy Module — Implementation Order

## Overview

Phase 1 OOP rewrite: R10/8-tech prototype → R32/17-tech full model. ~60–70% of existing code reusable. Estimated 6 weeks.

Dependency chain: Foundation → Economy + Vintage → Sectors → Integration → Polish.


## Phase A: Foundation (Week 1)

Everything else depends on these. No external dependencies.

| # | Component | File | Action | Why first |
|---|-----------|------|--------|-----------|
| 1 | `Carrier` enum + constants | `ghim/core/carrier.py` | **New** (impl.md §3.1) | Every module imports Carrier, CARBON_COEFS, GWP100 |
| 2 | `GHIMConfig` hierarchy | `ghim/core/config.py` | **New** (config.md) | Every module reads config; frozen dataclasses |
| 3 | `PeriodState` / `RegionState` | `ghim/core/state.py` | **New** (impl.md §3.3) | Shared mutable state; replaces scattered dicts |
| 4 | `ces.py` | `ghim/econ/ces.py` | **Reuse as-is** | Pure math, already correct (184 lines) |
| 5 | `logit.py` | `ghim/energy/logit.py` | **Reuse as-is** | Pure math, already correct (379 lines) |

**Tests**: Unit tests for Carrier enum, config loading (YAML override), state init/update.

**Milestone**: `GHIMConfig()` loads defaults, `RegionState` round-trips to/from dict.


## Phase B: Economy + Vintage (Week 2)

The macro backbone. Can test standalone with mock energy prices.

| # | Component | File | Action | Depends on |
|---|-----------|------|--------|------------|
| 6 | `Economy` class | `ghim/econ/economy.py` | **Refactor** klem.py → takes RegionState | Carrier, Config, CES |
| 7 | `VintageTracker` | `ghim/core/vintage.py` | **Enhance** stock.py → attach to techs | Config |
| 8 | `TechChange` | `ghim/core/learning.py` | **New** (technology_change.md) | Config, VintageTracker |
| 9 | `SupplyTech` / `EndUseTech` | `ghim/core/technology.py` | **Enhance** technology.py | Carrier, VintageTracker, TechChange |

**Key refactoring**:
- `KLEMDriver` → `Economy` class with `compute_va()`, `compute_energy_demand()`, `compute_gross_output()`, `update_capital()`
- Methods take `RegionState` (not raw floats)
- 4-level CES: Q = CES(KLE, M; 0.20), KLE = CES(KL, E; 0.40), KL = TFP × CES(K, L; 0.80), E = CES(EL, NEL; 2.0)
- Materials: M = 0.45 × Q (near-Leontief)

**Tests**: TFP calibration reproduces SSP GDP, CES demand elasticity, capital accumulation, learning curve cost reduction.

**Milestone**: `Economy` reproduces SSP2 GDP for one region with exogenous energy prices.


## Phase C: Sectors (Weeks 3–4)

Each sector is independent — **parallelizable across developers**. All inherit from `DemandSector` or `TransformationSector` ABC.

### Transformation Sectors (supply side)

| # | Component | File | Action | Techs | Complexity |
|---|-----------|------|--------|-------|------------|
| 10 | `ElectricitySector` | `ghim/sectors/electricity.py` | **Enhance** → ABC, 17 techs | Coal, Coal+CCS, Gas CC, Gas CC+CCS, Oil, Biomass, Biomass+CCS, Nuclear, Hydro, Solar PV, Solar CSP, Wind On, Wind Off, Geothermal, Ocean, H₂ turbine, Ammonia | High |
| 11 | `HydrogenSector` | `ghim/sectors/hydrogen.py` | **Enhance** → ABC, 7 techs | SMR, SMR+CCS, Coal Gasif, Coal Gasif+CCS, Electrolysis, Biomass Gasif, Biomass Gasif+CCS | Medium |
| 12 | `DistrictHeatingSector` | `ghim/sectors/district_heat.py` | **New** | Gas boiler, Coal boiler, Biomass boiler, Electric boiler, Heat pump, Geothermal | Medium |
| 13 | `BiofuelsSector` | `ghim/sectors/biofuels.py` | **New** | Biodiesel 1G, Cellulosic Ethanol 2G, BTL | Low |
| 14 | `RefinedOilSector` | `ghim/sectors/refining.py` | **Enhance** | Conventional refining (single tech) | Low |

### Demand Sectors (consumption side)

| # | Component | File | Action | Structure | Complexity |
|---|-----------|------|--------|-----------|------------|
| 15 | `IndustrySector` | `ghim/sectors/industry.py` | **New** | Energy Use (7 carriers) + Feedstocks (4 carriers) | Medium |
| 16 | `BuildingsSector` | `ghim/sectors/buildings.py` | **New** | Res/Com × Heating/Cooling/Other × 8 carriers | **High** (floorspace saturation + service intensity) |
| 17 | `TransportSector` | `ghim/sectors/transport.py` | **New** | Passenger (6 powertrains) + Freight (5 powertrains) | High (LCOT + VOT) |
| 18 | `AgricultureSector` | `ghim/sectors/agriculture.py` | **New** | Single node × 7 carriers, GDP-scaled | Low |
| 19 | `BunkersSector` | `ghim/sectors/bunkers.py` | **New** | Aviation (2) + Shipping (2), region-less | Low |

### Sector ABCs

```
DemandSector (ABC)
├── compute_demand(rs: RegionState, cfg: GHIMConfig) → dict[Carrier, float]
├── compute_emissions(rs: RegionState) → EmissionResult
└── calibrate(base_data) → None

TransformationSector (ABC)
├── compute_supply(rs: RegionState, cfg: GHIMConfig) → SupplyResult
├── compute_price(rs: RegionState) → float
├── compute_emissions(rs: RegionState) → EmissionResult
└── calibrate(base_data) → None
```

**Recommended order within Phase C** (by dependency + complexity):
1. AgricultureSector (simplest, test ABC pattern)
2. RefinedOilSector (single tech, test TransformationSector ABC)
3. IndustrySector (EU + FS, moderate)
4. ElectricitySector (17 techs, reuse existing, most important)
5. HydrogenSector (mirrors electricity)
6. BiofuelsSector, DistrictHeatingSector
7. TransportSector, BunkersSector
8. BuildingsSector (most complex demand sector — do last)

**Tests**: Each sector tested in isolation with mock RegionState + mock prices. Verify: shares sum to 1, demand > 0, vintage retirement monotonic, emissions > 0.

**Milestone**: All 10 sectors pass unit tests independently.


## Phase D: Integration (Week 5)

Wire everything into the solver loop.

| # | Component | File | Action | Depends on |
|---|-----------|------|--------|------------|
| 20 | `TradeModule` | `ghim/trade/module.py` | **Enhance** → 5 commodities | All sectors (aggregate demand) |
| 21 | `EmissionsModule` | `ghim/core/emissions.py` | **New** (emiss.md) | All sectors, EDGAR data |
| 22 | `Region` container | `ghim/core/region.py` | **New** | Economy + all sectors + resources |
| 23 | `DampedSolver` | `ghim/solver/damped.py` | **Rewrite** recursive.py → Solver ABC | Region, PeriodState |
| 24 | `GHIMModel` | `ghim/model.py` | **New** | Solver, Region × 32, Trade, TechChange |

**Key design**:
- `GHIMModel.F(x)` = single model pass (7 steps from solver.md)
- `DampedSolver.solve(model, state)` = damped fixed-point iteration
- State vector: 133 dims (4 × 32 regional + 5 global)
- Inter-period updates (K, vintage, depletion, learning) happen BETWEEN periods

**Tests**: Single-region single-period convergence, multi-region trade clearing, full SSP2 reference run.

**Milestone**: `python -m ghim.run --scenario SSP2` produces results for all 32 regions, 2000–2150.


## Phase E: Polish (Week 6)

| # | Component | File | Action |
|---|-----------|------|--------|
| 25 | `PolicyEngine` | `ghim/policy/engine.py` | **Enhance** → composition of 8 instruments |
| 26 | `ExternalAdapters` | `ghim/adapters/` | **New** — DefaultClimate/Water/AFOLU |
| 27 | `Reporting` | `ghim/output/iamc.py` | **Enhance** → IAMC variable mapping |
| 28 | CLI | `ghim/run.py` | **Refactor** → load config, build model, solve, report |

**Tests**: Carbon tax scenario (GDP drops), emissions cap (bisection finds price), IAMC output validates.

**Milestone**: Full model with policy runs. IAMC-format CSV output.


## Reuse Summary

| Existing file | Lines | Action |
|---------------|-------|--------|
| `econ/ces.py` | 184 | Reuse as-is |
| `energy/logit.py` | 379 | Reuse as-is |
| `energy/technology.py` | 174 | Reuse, enhance with ABC fields |
| `energy/stock.py` | 463 | Reuse, rename to VintageTracker |
| `energy/demand.py` | 443 | Reuse DemandNode/DemandLeaf |
| `energy/supply.py` | 152 | Reuse Grade/ResourceSupply |
| `energy/trade.py` | 408 | Reuse GlobalMarket/TradeModule |
| `energy/electricity.py` | 285 | Reuse, extend to 17 techs |
| `energy/hydrogen.py` | 247 | Reuse, extend to 7 techs |
| `energy/refining.py` | 52 | Reuse as-is |
| `policy.py` | 369 | Reuse 8 instrument dataclasses |
| `data/ssp.py` | 173 | Reuse as-is |
| `data/trade_cal.py` | 286 | Reuse as-is |
| `data/energy_cal.py` | 125 | Reuse, extend for R32 |
| `data/gem_cal.py` | 39 | Reuse as-is |
| `config.py` | 251 | Replace with GHIMConfig hierarchy |
| `econ/klem.py` | 391 | Refactor → Economy class |
| `solver/recursive.py` | 984 | **Rewrite** → Solver ABC + GHIMModel |
| `output/reporting.py` | 120 | Enhance → IAMC format |
| Tests (9 files) | 2,163 | Keep all, extend |

**Total existing**: ~8,600 lines. **Reuse**: ~5,500 lines (~65%). **Rewrite**: ~3,100 lines.


## New Directory Structure

```
ghim/
├── core/                          # NEW: Foundation
│   ├── carrier.py                 # Carrier enum, CARBON_COEFS, GWP100
│   ├── config.py                  # GHIMConfig dataclass hierarchy
│   ├── state.py                   # PeriodState, RegionState
│   ├── vintage.py                 # VintageTracker (from stock.py)
│   ├── learning.py                # TechChange (learning curves + spillovers)
│   ├── technology.py              # SupplyTech, EndUseTech (from technology.py)
│   ├── emissions.py               # EmissionResult, compute_emissions()
│   └── region.py                  # Region container
│
├── econ/                          # ENHANCED: Economy
│   ├── ces.py                     # (reuse as-is)
│   └── economy.py                 # Economy class (from klem.py)
│
├── sectors/                       # NEW: OOP sectors
│   ├── abc.py                     # DemandSector, TransformationSector ABCs
│   ├── electricity.py             # ElectricitySector (17 techs)
│   ├── hydrogen.py                # HydrogenSector (7 techs)
│   ├── district_heat.py           # DistrictHeatingSector (6 techs)
│   ├── biofuels.py                # BiofuelsSector (3 techs)
│   ├── refining.py                # RefinedOilSector (1 tech)
│   ├── industry.py                # IndustrySector
│   ├── buildings.py               # BuildingsSector
│   ├── transport.py               # TransportSector
│   ├── agriculture.py             # AgricultureSector
│   └── bunkers.py                 # BunkersSector
│
├── trade/                         # ENHANCED: Trade
│   ├── module.py                  # TradeModule (from trade.py)
│   └── supply.py                  # ResourceSupply, Grade (from supply.py)
│
├── solver/                        # REWRITTEN: Solver
│   ├── abc.py                     # Solver ABC
│   └── damped.py                  # DampedSolver (Phase 1)
│
├── policy/                        # ENHANCED: Policy
│   ├── instruments.py             # 8 policy dataclasses (from policy.py)
│   └── engine.py                  # PolicyEngine composition
│
├── adapters/                      # NEW: External module interfaces
│   ├── abc.py                     # ClimateAdapter, WaterAdapter, AFOLUAdapter ABCs
│   └── defaults.py                # Default adapters (ΔT=0, unconstrained water, static AFOLU)
│
├── data/                          # REUSE: Data loading
│   ├── ssp.py                     # (reuse as-is)
│   ├── trade_cal.py               # (reuse as-is)
│   ├── energy_cal.py              # (enhance for R32)
│   ├── gem_cal.py                 # (reuse as-is)
│   ├── loader.py                  # (reuse as-is)
│   └── external/                  # (data files, reuse as-is)
│
├── output/                        # ENHANCED: Reporting
│   ├── reporting.py               # CSV export (enhance)
│   └── iamc.py                    # IAMC variable mapping (new)
│
├── model.py                       # NEW: GHIMModel orchestrator
├── run.py                         # REFACTOR: CLI entry point
└── tests/                         # KEEP + EXTEND
    └── ...                        # 234 existing tests + new tests per phase
```


## Critical Path

```
Week 1: [Carrier + Config + State]
              ↓
Week 2: [Economy + Vintage + Learning + Tech]
              ↓
Week 3: [AgricultureSector → IndustrySector → ElectricitySector]  ← parallel
Week 4: [BuildingsSector → TransportSector → remaining sectors]   ← parallel
              ↓
Week 5: [Trade + Emissions + Region + Solver + GHIMModel]
              ↓
Week 6: [Policy + Adapters + Reporting + CLI]
```
