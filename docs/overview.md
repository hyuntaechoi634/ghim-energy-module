# Model Overview

## Motivation

Current integrated assessment models (IAMs) such as GCAM, REMIND, and MESSAGE face several challenges:

- **Complexity and opacity**: Large codebases (often C++ or GAMS) make it difficult for researchers to understand, modify, and extend the models.
- **Rigid regional structures**: Most IAMs use model-specific regional aggregations that are hard to reconfigure.
- **Monolithic architecture**: Tightly coupled components make it difficult to test individual modules in isolation.

GHIM addresses these issues by providing a **modular, transparent, Python-based** energy model that:

1. Implements well-established economic theory (CES production functions, logit discrete choice) in readable, testable code.
2. Uses the standardized **AR6 10-region** classification for direct comparability with IPCC assessment reports.
3. Separates the macroeconomic driver, energy supply chain, and solver into independent modules.

## Design Philosophy

GHIM draws inspiration from several established models:

| Concept | Source | GHIM Implementation |
|---------|--------|-------------------|
| Nested CES production | WITCH, REMIND | `ghim.econ.ces` — KLEM nesting |
| Logit technology choice | GCAM | `ghim.energy.logit` — relative & absolute cost logit |
| Recursive-dynamic solving | GCAM, DICE/RICE | `ghim.solver.recursive` — period-by-period |
| Energy supply chain | WITCH, GCAM | Primary → Transformation → Final demand |

The model is intentionally simpler than full IAMs — it focuses on the energy sector without land use, water, or detailed climate feedback. This makes it suitable as a research and teaching tool, and as a platform for testing new modeling approaches before incorporating them into larger frameworks.

## Scope

### What GHIM models (Phase 1)

- **10 world regions** using the AR6 R10 classification
- **Macroeconomic driver**: GDP and population from SSP scenarios drive energy demand via KLEM-CES
- **Electricity generation**: 8 technologies competing via logit (coal, gas CC, nuclear, hydro, wind, solar, biomass, oil)
- **Oil refining**: Crude oil → refined liquids transformation
- **Hydrogen production**: SMR and electrolysis competing via logit
- **Final energy demand**: Industry, buildings, and transport sectors with fuel switching
- **CO$_2$ emissions**: From fossil fuel combustion across the supply chain
- **Time horizon**: 2020–2100 in 5-year steps

### What GHIM does not yet model

- Technology learning curves (cost reductions over time)
- Autonomous energy efficiency improvement (AEEI)
- Carbon pricing or climate policy
- Climate feedback (temperature → economic damages)
- Land use, agriculture, or non-CO$_2$ emissions
- Trade between regions

## Regional Specification

GHIM uses the **AR6 10-region (R10)** classification from the IPCC Sixth Assessment Report. Countries are mapped directly to R10 regions using ISO 3166-1 alpha-3 codes, without any intermediate aggregation step.

| Region | Key Countries |
|--------|---------------|
| Africa | Nigeria, South Africa, Ethiopia, Egypt, ... |
| Asia-Pacific Developed | Japan, South Korea, Australia, New Zealand |
| Eastern Asia | China, Mongolia, North Korea |
| Eurasia | Russia, Central Asian states, Ukraine |
| Europe | EU, UK, Norway, Switzerland, ... |
| Latin America and Caribbean | Brazil, Mexico, Argentina, ... |
| Middle East | Saudi Arabia, Iran, Iraq, UAE, ... |
| North America | USA, Canada |
| South-East Asia and developing Pacific | Indonesia, Thailand, Vietnam, Philippines, ... |
| Southern Asia | India, Pakistan, Bangladesh, ... |

The mapping file is at `mapping/region_classification.tsv` with columns: `ISO`, `name`, `region_ar6_10`.

## Model Architecture

The following diagram shows how data flows through the model:

```
                          SSP Scenarios
                      (Population, GDP|PPP)
                              │
                              ▼
                    ┌─────────────────────┐
                    │    KLEM Macro Driver │
                    │  (CES: K, L, E, M)  │
                    └────────┬────────────┘
                             │ Energy demand (EJ)
                             ▼
              ┌──────────────────────────────┐
              │      Final Demand Sectors     │
              │  Industry │ Buildings │ Transport │
              │  (logit fuel switching)       │
              └──────┬───────┬───────┬───────┘
                     │       │       │
         ┌───────────┘       │       └───────────┐
         ▼                   ▼                   ▼
    Electricity         Ref. Liquids         Hydrogen
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ 8 techs  │       │  Crude → │       │ SMR      │
    │ (logit)  │       │  Liquids │       │ Electrol.│
    └────┬─────┘       └────┬─────┘       └────┬─────┘
         │                  │                   │
         └────────┬─────────┴───────────────────┘
                  ▼
         Primary Energy Resources
         (coal, gas, oil, nuclear,
          hydro, wind, solar, biomass)
```

## Code Organization

```
ghim/
├── config.py                 # Time horizon, CES/logit parameters, constants
├── regions.py                # AR6 R10 region definitions, ISO→R10 mapping
├── data/
│   ├── ssp.py                # SSP population/GDP loading and R10 aggregation
│   ├── energy_cal.py         # Base-year energy balance defaults
│   └── loader.py             # CSV reading utilities
├── econ/
│   ├── ces.py                # CES production function (output, price, demand, calibrate)
│   └── klem.py               # KLEM macro driver (energy demand from GDP)
├── energy/
│   ├── logit.py              # Logit discrete choice (relative, absolute, calibrate)
│   ├── technology.py         # Technology dataclass and default parameters
│   ├── electricity.py        # Electricity sector (8-tech logit competition)
│   ├── refining.py           # Oil refining sector
│   ├── hydrogen.py           # Hydrogen production (SMR + electrolysis)
│   ├── demand.py             # Final demand by sector with fuel switching
│   └── supply.py             # Primary resource supply curves
├── solver/
│   └── recursive.py          # Period-by-period solver with market clearing
├── output/
│   └── reporting.py          # Results export (CSV, summary tables)
├── run.py                    # CLI entry point
└── tests/                    # 38 unit tests
```
