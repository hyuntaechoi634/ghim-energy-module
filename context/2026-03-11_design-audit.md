# Research Note — 2026-03-11: Design Audit & Parameter Reconciliation

## Objective

Comprehensive audit of all GHIM design documents (`design/`), `implementation.md`, and presentation slides (`present/ghim-19-mar-2026/slides.pdf`, 62pp) to identify gaps that would block Phase 1 implementation. Then resolve as many as possible in the same session.

---

## 1. Gap Analysis Items #11–20 (from prior session)

Resolved all 10 deferred medium-priority items:

| # | Item | Resolution |
|---|------|-----------|
| 11 | Logit signature undefined | `preference_logit()` = slides formula `exp(β(C+p))`. Already in impl.md §3.6 |
| 12 | Oil → Refined Liquids price | `p_liq = p_oil / eff + VOM`, eff=0.90. Already in impl.md §5.12 |
| 13 | **Demand-sector preference decay** | **New**: carrier-level annual rates added to impl.md §3.6. EL=0.02, H₂=0.03, Biofuel=0.02, rest=0.00. Separate from supply-side tech decay |
| 14 | Savings rate regional variation | Phase 1: global 0.22. Placeholder for Phase 2 regional PWT data |
| 15 | VintageStock.surviving() | Already implemented: S-curve + hard cutoff in `stock.py` |
| 16 | production_at_price() | Already implemented: piecewise-linear in `supply.py` |
| 17 | base_demands data loading | Data extraction task from gcamdata R32, not a design decision |
| 18 | **TechChange.__init__()** | **New**: full `@dataclass` constructor written into impl.md §5.7, with LBD+RND+spillover matrix, `_effective_cumulative()`, `_effective_knowledge()` methods |
| 19 | Q_ag base value | Dimensionless index (base=1.0). Clarified in impl.md §5.8 docstring |
| 20 | **Biomass residue → trade** | **New**: `DefaultAFOLUAdapter` expanded in impl.md §6.1 with Q_ag-scaled crop residue as low-cost grade (~2 $/GJ) |

Design doc changes: `implementation.md` updated at §3.6, §5.7, §5.8, §6.1.


## 2. Comprehensive Audit Findings

Four parallel audits: impl.md §1-1000, impl.md §1000-end, all other design docs, slides cross-reference.

### 2.1 Parameter Value Contradictions Found

10 contradictions between slides, design docs, and code:

| Parameter | Slides | economy.md | structure.md | electricity.md | vintage_stock.md | impl.md |
|-----------|--------|-----------|-------------|---------------|-----------------|---------|
| σ_KLE,M | ~0.5 | **0.20** | ~0.5 | — | — | ~0.2 |
| σ_EL,NEL | ~2.0 | **2.0** | ~2.0 | — | — | 1.0 |
| Coal lifetime | 60 | — | — | **60** | 45 | — |
| Gas CC lifetime | 45 | — | — | **45** | 35 | — |
| Oil lifetime | 45 | — | — | **45** | 40 | — |
| Biomass lifetime | 60 | — | — | **60** | 35 | — |
| Solar PV lifetime | 30 | — | — | **30** | 25 | — |
| Wind lifetime | 30 | — | — | **30** | 25 | — |
| Shutdown steepness | — | — | — | 10 | **6** | **6** |
| Logit formula | exp(β(C+p)) | — | — | exp(-kP)·C^β | — | exp(β(C+p)) |

Bold = authoritative value chosen.

**Key decision process:**
- **σ_KLE,M = 0.20**: economy.md already had this with Koesler & Schymura 2015 citation and full literature range (0.0–0.5). The slides' "~0.5" was an earlier iteration.
- **Lifetimes**: Verified against GCAM source data `A23.globaltech_retirement.csv`. GCAM values match electricity.md and slides. vintage_stock.md had wrong (shorter) values from an earlier draft.
- **Steepness = 6**: Confirmed from GCAM `A23.globaltech_retirement.csv` `profit.shutdown.steepness` column.
- **Logit**: User decision — `exp(β(C+p))` canonical form, single β parameter. The mixed `exp(-kP)·C^β` was an older notation from individual sector docs.
- **Composite energy price**: User chose expenditure-weighted average (not CES dual price index).

### 2.2 Structural Gaps in implementation.md

**15 undefined method bodies (`...` stubs)**: `Subsector.calibrate()`, `VintageTracker.surviving()`, `ResourceSupply.production_at_price()`, 6 transformation sector compute_supply/compute_price methods, `TradeModule._bisection()`, etc.

Note: ~5 of these are already implemented in current Python code (`stock.py`, `supply.py`, `trade.py`) — the design doc just hasn't been updated with the pseudocode.

**9 undefined data sources in build_model()**: `base_energy_ej`, `base_prices`, `base_demands`, `base_shares`, `base_gen`, `base_carrier_demand`, `biomass_curves`, etc. All are data extraction tasks from gcamdata, not design decisions.

**5 undefined constants**: `CARBON_COEFS`, `TC_TO_TCO2`, `CH4_FUGITIVE`, `GWP100`, `TRADED_FUELS` — straightforward to define.

### 2.3 config.md is Empty

The file contains only "TODO". Referenced from 10+ other docs. Must be written before coding. Low effort but blocking.

### 2.4 Slides Content Not in Docs

| Slide content | Status |
|--------------|--------|
| Dual OOP + Procedural (Fortran-ready) strategy (slide 33) | Not documented |
| "Adjustable rolling foresight" Phase 2 (slides 2, 5) | solver.md says Anderson, not foresight |
| Phase 2+ trade: Steel, Aluminum (slide 7) | trade.md doesn't mention materials trade |
| `s_RD` parameter for aggregate R&D fraction (slide 10) | No value in any doc |


## 3. Resolutions Applied

### 3.1 Logit Formula Unified (10 formulas in 7 files)

Updated all sector design docs to canonical form:
$$S_i = \alpha_i \cdot \exp(\beta \cdot (C_i + p_i)) \;/\; \Sigma_j$$

Files changed: `electricity.md`, `industry.md`, `buildings.md`, `transport.md`, `bunkers.md`, `agriculture.md`, `other_transformation.md`

Also updated calibration formula in all 5 demand-sector docs:
$$p_i = (1/\beta) \cdot \ln(S_i/S_{ref}) - (C_i - C_{ref})$$

Parameter tables simplified from two-parameter (k, β) to single-parameter (β < 0).

### 3.2 Parameter Contradictions Fixed (5 edits)

1. `structure.md`: σ_KLE,M → 0.20 (was ~0.5)
2. `implementation.md`: σ_EL,NEL → 2.0 (was 1.0 in Economy class)
3. `vintage_stock.md`: 10 lifetime values updated to match GCAM A23
4. `electricity.md`: profit shutdown steepness → 6 (was 10)
5. `economy.md`: composite energy price → expenditure-weighted (was CES dual)

### 3.3 Policy Instrument Classes Written

All 7 missing policy dataclasses added to implementation.md §16:
- `RenewableSubsidy` (production tax credit, capex grant, phase-out)
- `EfficiencyStandard` (per-sector annual AEEI)
- `EmissionsCap` (absolute cap + bisection on shadow price)
- `TechConstraint` (min/max share bounds with interpolation)
- `RevenueRecycling` (lump_sum / capital_subsidy / labor_tax_cut)
- `TechAvailability` (binary on/off schedules per tech per period)
- `PrefFactorOverride` (direct p_i override with interpolation)
- `PolicyEngine` (composition of all 8)

### 3.4 Buildings & Sector Splits: Data Found in gcamdata

Key finding: the "missing parameters" are actually **data extraction tasks**, not design decisions.

**Buildings floorspace satiation:**
- Commercial: `A44.satiation_flsp.csv` — region class A-E (17–27 m²/cap SSP2)
- Residential: Gompertz function in `L144.building_det_flsp.R` — F̄=150 (USA) / 100 (non-USA), parameters fit via NLS per region
- Service density: multipliers from `A44.demand_satiation_mult.csv` — heating 1.1×, others 1.3×

**Industry EU/FS split:**
- Default 93% energy use / 7% feedstock from `A32.globaltech_coef.csv`
- Region-specific from IEA NONENUSE flow in `L132.industry.R`

**Transport passenger/freight:**
- Not a ratio parameter — disaggregated from IEA via UCD database shares
- R32-specific computed in `L152/L154` R chunks

**Bunkers aviation/shipping:**
- Already separate IEA flows (AVBUNK vs MARBUNK) — no split parameter needed
- Independent sectors in GCAM (`trn_aviation_intl`, `trn_shipping_intl`)
- Elasticities: aviation (α=1.0, γ=-1.0), shipping (α=0.4, γ=-0.65)


## 4. Remaining Items

### Tier 1 (before coding)
- [ ] Write `config.md`
- [ ] Define 5 missing constants (CARBON_COEFS, TC_TO_TCO2, CH4_FUGITIVE, GWP100, TRADED_FUELS)
- [ ] Fill remaining `...` method stubs in impl.md that don't have code equivalents (6 transformation sector methods)
- [ ] Extract R32 base-year data from gcamdata: buildings Gompertz params, industry EU/FS, transport pass/freight, energy balances

### Tier 2 (can parallel with coding)
- [ ] Document slides-only content (Fortran track, rolling foresight, materials trade)
- [ ] B11: Materials coefficient m — need literature value (~0.25 from OECD I/O)
- [ ] Complete tech/subsector lists in impl.md (Buildings cooling `[...]`, Transport freight `[...]`)

### Tier 3 (defer to implementation phase)
- [ ] IAMC reporting mapping (`to_iamc()` body)
- [ ] Data loader functions for build_model()
- [ ] Integration testing strategy


## 5. Files Modified Today

| File | Changes |
|------|---------|
| `design/implementation.md` | §3.6 demand decay, §5.7 TechChange full constructor, §5.8 Q_ag clarification, §6.1 biomass→trade, §16 all 7 policy classes, σ_EL_NEL fix |
| `design/economy.md` | Budget constraint (solver step 11, phased table), composite price → expenditure-weighted |
| `design/structure.md` | σ_KLE,M → 0.20 |
| `design/vintage_stock.md` | 10 lifetime values → GCAM A23 |
| `design/electricity.md` | Logit formula, shutdown steepness → 6 |
| `design/industry.md` | Logit formula + calibration |
| `design/buildings.md` | Logit formula + calibration |
| `design/transport.md` | Logit formula + calibration |
| `design/bunkers.md` | Logit formula + calibration |
| `design/agriculture.md` | Logit formula + calibration |
| `design/other_transformation.md` | Logit formula (3 sectors) |
| `paper/ghim_energy_module.tex` | Model description paper draft (12pp, compiles clean) |
