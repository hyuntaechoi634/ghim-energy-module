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

GHIM draws inspiration from several established models. The core philosophy: **"DICE + energy"** — endogenous GDP with a detailed energy sector.

| Concept | Source | GHIM Implementation |
|---------|--------|-------------------|
| Endogenous GDP | DICE/RICE | `ghim.econ.klem` — $Y = A K^\alpha L^{1-\alpha}$ with energy cost feedback |
| Preference factor logit | MERGE | `ghim.energy.logit` — $\exp(-k(C_i + P_i)) / \Sigma$ with decay |
| Learning-by-doing | WITCH | `ghim.energy.technology` — experience curves for all technologies |
| Stock turnover inertia | WITCH, GCAM | `ghim.energy.stock` — sector-specific turnover times |
| Nested CES production | WITCH, REMIND | `ghim.econ.ces` — KLEM nesting |
| Logit technology choice | GCAM | `ghim.energy.logit` — relative & absolute cost logit |
| Recursive-dynamic solving | GCAM, DICE/RICE | `ghim.solver.recursive` — period-by-period |
| Energy supply chain | WITCH, GCAM | Primary → Transformation → Final demand |

The model is intentionally simpler than full IAMs — it focuses on the energy sector without land use, water, or detailed climate feedback. This makes it suitable as a research and teaching tool, and as a platform for testing new modeling approaches before incorporating them into larger frameworks.

## Scope

### What GHIM models

- **10 world regions** using the AR6 R10 classification
- **Endogenous GDP**: DICE-style production function $Y = A K^\alpha L^{1-\alpha}$, with TFP trajectory calibrated from SSP scenarios, and energy cost → net output → investment → capital feedback
- **Time horizon**: 2000–2150 in 5-year steps (31 periods)
- **Electricity generation**: 8 technologies competing via preference-factor logit, with stock turnover ($\tau = 40$ yr) and learning curves
- **Oil refining**: Crude oil → refined liquids transformation
- **Hydrogen production**: SMR and electrolysis competing via preference logit, with stock turnover ($\tau = 25$ yr) and electrolysis learning
- **Final energy demand**: Industry (heavy/light/data centers), buildings (residential/commercial), and transport (passenger/freight) — nested 2-level logit tree with stock turnover at each level
- **Technology dynamics**: WITCH-style experience curves — solar (20% learning rate), wind (12%), electrolysis (15%), with cost floor at 20% of initial
- **CO$_2$ emissions**: From fossil fuel combustion across the supply chain

### What GHIM does not yet model

- Autonomous energy efficiency improvement (AEEI)
- Carbon pricing or climate policy
- Climate feedback (temperature → economic damages)
- Land use, agriculture, or non-CO$_2$ emissions
- Trade between regions
- Historical period tracking (2000–2020 periods use SSP data, not IEA actuals)

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

The following diagram shows how data flows through the model. The key feedback loop (DICE-style): energy costs reduce net output, which reduces investment, which lowers future capital stock and GDP.

```
                          SSP Scenarios
                     (Population, GDP|PPP)
                              │
              TFP calibration │ (A(t) so Y ≈ Y_SSP)
                              ▼
                    ┌─────────────────────┐
                    │  DICE GDP Engine    │
                    │ Y = A·K^α·L^(1-α)  │──────────────┐
                    └────────┬────────────┘              │
                             │ Gross output              │
                             ▼                           │
              ┌──────────────────────────────┐           │
              │      Final Demand Sectors     │           │
              │  Industry │ Buildings │ Transport │       │
              │  (nested logit + stock turnover)│        │
              └──────┬───────┬───────┬───────┘           │
                     │       │       │                   │
         ┌───────────┘       │       └───────────┐       │
         ▼                   ▼                   ▼       │
    Electricity         Ref. Liquids         Hydrogen    │
    ┌──────────┐       ┌──────────┐       ┌──────────┐  │
    │ 8 techs  │       │  Crude → │       │ SMR      │  │
    │ pref logit│      │  Liquids │       │ Electrol.│  │
    │ +learning │       └────┬─────┘       │ +learning│  │
    └────┬─────┘             │             └────┬─────┘  │
         └───────┬───────────┴──────────────────┘        │
                 ▼                                       │
        Energy Cost ($B) ─────────────────────────┐      │
                                                  ▼      │
                                           Net Output    │
                                           = Y - Cost    │
                                                  │      │
                                           Investment    │
                                           I = s·Y_net   │
                                                  │      │
                                           K(t+1) ◄──────┘
```

## Code Organization

```
ghim/
├── config.py                 # Time horizon, DICE/CES/logit parameters, learning rates
├── regions.py                # AR6 R10 region definitions, ISO→R10 mapping
├── data/
│   ├── ssp.py                # SSP population/GDP loading, R10 aggregation, 2150 extrapolation
│   ├── energy_cal.py         # Base-year energy balance defaults
│   └── loader.py             # CSV reading utilities
├── econ/
│   ├── ces.py                # CES production function (output, price, demand, calibrate)
│   └── klem.py               # DICE-style macro driver (Y=AK^αL^(1-α), endogenous GDP)
├── energy/
│   ├── logit.py              # Logit: relative, absolute, preference-factor, calibrate
│   ├── stock.py              # Stock turnover (gradual technology transition)
│   ├── technology.py         # Technology dataclass with learning curves
│   ├── electricity.py        # Electricity sector (pref logit + stock + learning)
│   ├── refining.py           # Oil refining sector
│   ├── hydrogen.py           # Hydrogen production (pref logit + stock + learning)
│   ├── demand.py             # Nested demand tree (DemandNode/DemandLeaf)
│   └── supply.py             # Primary resource supply curves
├── solver/
│   └── recursive.py          # Period-by-period solver with endogenous GDP feedback
├── output/
│   └── reporting.py          # Results export (CSV, summary tables, GDP comparison)
├── run.py                    # CLI entry point
└── tests/                    # 40 unit tests
```
