# GHIM Energy Module — Design Principles

Eight principles guiding the architecture and development of the GHIM energy module.

These principles are the **why** and **what** of the model. For the **how**, see the individual design documents (`economy.md`, `structure.md`, `solver.md`, `resolution.md`, etc.).


## 1. Replicate SSP Baselines

The reference run reproduces SSP trajectories **exactly**. The model's value comes from deviation under policy or feedback.

- TFP calibrated to match SSP GDP path at every period
- Preference weights calibrated to match SSP energy mix
- CES share parameters calibrated from base-year cost shares
- Without policy or coupled feedbacks, the model adds nothing over SSP — **the deviation IS the model's contribution**

See: `economy.md` §4 Calibration, `structure.md` §Technology Choice.


## 2. Hard-Couple Energy and Economy

Energy is not an afterthought — it is a **production factor** inside the economy, and the economy drives energy demand.

- CES-KLEM production function: energy (EL, NEL) alongside capital, labor, materials
- Energy cost reduces GDP within the same period (σ < 1 → complements)
- Energy investment crowds out general capital via unified budget constraint
- Electrification captured structurally (σ_EL,NEL > 1 → substitutes)
- Full two-way feedback: Y → E demand → prices → Y, resolved simultaneously

This is the core distinguishing feature of GHIM versus soft-linked or one-way models.

See: `economy.md` for the full CES nesting, budget constraint, and feedback channels.


## 3. Solve Less, Simulate More

Use **logit + fixed-point iteration** to find general equilibrium, not optimization (LP/NLP).

- Technology shares: logit (closed-form, O(1) per tech)
- Price–quantity balance: fixed-point iteration
- Trade clearing: bisection (monotonic, guaranteed convergence)
- Macro ↔ energy: outer iteration until convergence

The full model is an explicit fixed-point problem: state vector **x**, mapping **F(x)** = one complete model pass, find **x\* = F(x\*)**. This gives:

- Principled convergence guarantees (Banach contraction mapping)
- Single residual for monitoring: ‖F(x) − x‖
- Drop-in solver upgrades (damped → Anderson → Newton-Krylov) without changing model logic

See: `solver.md` for state vector, convergence theory, and solution methods.


## 4. IAMC-Native Reporting

The model structure maps directly to IAMC variable names. **No translation layer.**

- Sector, carrier, and technology names in the code match IAMC nomenclature
- Reporting is a direct readout, not a post-hoc mapping
- Phase 1: Tier-1 coverage (sector × fuel, aggregate supply, GDP, emissions)
- Phase 2+: expanded to Tier-2/3 (subsectors, modes, end-uses)

See: `structure.md` — each section includes an IAMC Reporting Coverage table.


## 5. Transparent and Reproducible

Every parameter should be traceable to a published source. The entire workflow — from raw data to reported results — should be reproducible.

### Data transparency

- All external data stored in `ghim/data/external/` with source attribution
- Calibrated parameters (TFP, preference weights) are **derived**, not assumed
- When sources disagree, document the choice and reasoning
- Parameters not from published sources must include rationale and sensitivity range

### Reproducibility

- Open-source codebase
- Single data pipeline: gcamdata → GHIM input → model → IAMC output
- Deterministic: same inputs always produce same outputs (no stochastic elements in Phase 1)
- Version-pinned dependencies and data

### Core data sources

| Category | Source | Version |
|----------|--------|---------|
| Energy balances | IEA WEB | 2023 |
| Scenarios | IIASA SSP | AR6 (2024) |
| Emissions | CEDS | 1970–2022 |
| Trade | GTAP | v11 |
| Resources / Technology | NREL ATB | 2024 |
| Transport | UC Davis | 2013 |
| Land / Agriculture | FAO | 2024 |


## 6. User-Configurable

Easy to adjust resolution, nesting, sector structure, and parameters **without modifying model code**.

### What is configurable

| Dimension | Examples | Mechanism |
|-----------|----------|-----------|
| **Temporal** | Timestep (5yr, 1yr), horizon (2100, 2150) | Config file |
| **Spatial** | 32 GCAM regions (Phase 1), 100+ countries (Phase 2) | Region mapping file |
| **Sector nesting** | Add/remove subsectors, end-uses, carriers | Structure definition file |
| **Technology set** | Enable/disable techs, add new techs | Technology definition file |
| **Parameters** | Elasticities, savings rate, LFP, depreciation, learning rates | Parameter file or config |
| **Economy mode** | Exogenous (SSP GDP given) vs endogenous (CES-solved) | Single toggle |
| **Policy** | Carbon price, tech bans, share constraints, subsidies | Scenario JSON |

### Parameter flexibility

Every economic parameter accepts three levels of specificity:

1. **Global scalar** — single value for all regions and periods (Phase 1 default)
2. **Region-varying** — different value per region, constant over time
3. **Region × time-varying** — full flexibility (function of region and year)

Phase 1 uses global scalars. The interface is designed so that upgrading to regional or time-varying values requires **no code changes** — only data changes.

See: `config.md` for the full configuration specification.


## 7. Trade Everything

If the model produces a commodity, it should be tradeable via global market clearing.

- Phase 1: coal, oil, gas, uranium, biomass — single world price per commodity
- Phase 2+: electricity (interconnectors), hydrogen, liquids, materials, emissions permits
- All use the same framework: find world price where Σ supply = Σ demand
- Every commodity the model tracks should have a trade channel, even if initial implementation is simple net-export accounting

See: `structure.md` §Primary Energy — Trade, `economy.md` §5.2 State Vector for global price variables.


## 8. Design Interfaces for Module Linkage

The energy module will connect to climate, water, agriculture/land use, and other GHIM modules. **Design interfaces now, connect modules later.**

- Each interface is a **defined input/output contract** (typed function signature)
- Energy module runs standalone with **default/exogenous values** for all external inputs
- External modules override defaults when connected
- Same-period coupling throughout (no one-period lag)

| Module | → Energy | Energy → |
|--------|----------|----------|
| **Climate** | Temperature → TFP damage | Emissions → radiative forcing |
| **AFOLU** | Land availability → biomass constraint | Biomass demand → land pressure |
| **Water** | Water availability → cooling constraint | Water demand → water stress |
| **Finance** | Discount rates, WACC → tech cost | Investment needs → capital pressure |

See: `linkages.md` for the full 18-channel interface specification.
