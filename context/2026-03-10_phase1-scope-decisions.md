# Research Note — 2026-03-10: Phase 1 Scope Decisions & Negative Emissions Architecture

## Objective

Finalize Phase 1 scope decisions that had been open, design BECCS/negative emissions architecture, integrate LULUCF accounting from EDGAR data, and conduct initial comprehensive gap analysis of all design documents.

---

## 1. Region Resolution: R10 → R32

**Decision**: Phase 1 uses GCAM's 32 geopolitical regions (R32), not AR6 R10.

**Rationale**:
- GCAM data pipeline (`gcamdata`) already aggregates everything to R32
- Trade supply curves in `fos_curves_R32.csv` are natively R32
- Going to R10 would discard information unnecessarily
- R32 → R10 aggregation is trivial if ever needed for reporting
- State vector grows from 45 dim (4×10+5) to 133 dim (4×32+5) — still tractable for damped iteration

**Impact**: Updated `ghim/data/external/region_classification.tsv` mapping, all config constants, trade module region lists, SSP data loader.


## 2. Phase 1 Scope Decisions

Several open questions about Phase 1 scope were resolved:

| Component | Decision | Rationale |
|-----------|----------|-----------|
| **Buildings** | Full floorspace model (Gompertz satiation) | Needed for realistic demand projection; data available in gcamdata |
| **District Heating** | Included as transformation sector | Important for Europe/Russia/China; simple LCOH logit |
| **Materials nest** | $M = m \cdot Q$, $Y = Q - p_E \cdot E - p_M \cdot M$ | Leontief-like (σ_{KLE,M}=0.20) but not zero; consistent with economy.md |
| **GDP mode** | Endogenous (default), exogenous (config toggle) | Energy → GDP feedback is the key value-add; exogenous for debugging |
| **Savings rate** | Global $s = 0.22$ | PWT mean gross capital formation share; regional variation deferred to Phase 2 |


## 3. BECCS & Negative Emissions Architecture

### Problem
Need biomass+CCS technologies that produce **negative** net emissions (carbon dioxide removal).

### Design
Added `biogenic_coef` field to `SupplyTech` dataclass:

```
biogenic_coef: float = 0.0   # tCO₂/GJ of biogenic carbon (biomass techs only)
```

**LCOE with BECCS credit** (when carbon price τ > 0):
$$\text{beccs\_credit} = \text{biogenic\_coef} \times \text{TC\_TO\_TCO₂} \times \text{capture\_rate} \times \tau \;/\; \text{efficiency}$$

The credit makes biomass_ccs economically attractive at high carbon prices.

**Net emissions calculation**:
- Fossil techs: `fossil_co2 = carbon_coef × (1 - capture_rate) × generation / efficiency`
- Biomass techs: `biogenic_co2 = -biogenic_coef × capture_rate × generation / efficiency` (negative = removal)
- Net: `total = fossil_net - biogenic_net` → can be negative when BECCS dominates

**Technologies affected**:
| Tech | carbon_coef | biogenic_coef | capture_rate |
|------|-------------|---------------|-------------|
| biomass | 0 | 0.10 | 0.0 |
| biomass_ccs | 0 | 0.10 | 0.90 |
| coal_ccs | 0.0257 | 0 | 0.90 |
| gas_ccs | 0.0153 | 0 | 0.90 |

Written into `design/implementation.md` and `design/emiss.md`.


## 4. LULUCF & Net-Zero Accounting

### Data Source
EDGAR 2025 GHG Booklet (`data/emiss/EDGAR_2025_GHG_booklet_2025.xlsx`, LULUCF_countries sheet).

### Key Finding
**Only anthropogenic LULUCF counts for UNFCCC Net-Zero**, NOT natural sinks:

| Sink type | Magnitude (2021) | Included? |
|-----------|-------------------|-----------|
| Anthropogenic LULUCF | −0.35 GtCO₂ (net global) | **Yes** |
| Ocean absorption | −10.5 GtCO₂ | No |
| CO₂ fertilization | −11 GtCO₂ | No |
| Other terrestrial | varies | No |

This was a critical correction — natural sinks (~22 GtCO₂/yr) dwarf anthropogenic LULUCF. Including them would make Net-Zero trivially easy to achieve.

### Implementation
- `LULUCF_NET_CO2` dict: R32 region → MtCO₂ (aggregated from EDGAR country data)
- `EmissionResult` dataclass: `lulucf` field added
- `co2eq` property includes LULUCF
- `co2eq_excl_lulucf` property for reporting without LULUCF
- Phase 1: LULUCF is **static** (base-year values, no dynamic land-use change)
- Phase 2+: AFOLU module provides dynamic LULUCF trajectory


## 5. Technology Change: RND Naming & WITCH Values

### Naming
Renamed "LBR" (Learning-By-Researching) to "RND" (R&D) throughout — clearer, more standard.

### Two-Factor Learning Curve
$$\text{capex}(t) = \text{capex}_0 \times \left(\frac{Q_{eff}}{Q_0}\right)^{-\alpha_{LBD}} \times \left(\frac{H_{eff}}{H_0}\right)^{-\beta_{RND}}$$

### WITCH-Sourced Parameters

| Technology | α_LBD | β_RND | Floor (% of initial) |
|------------|--------|--------|---------------------|
| Solar PV | 0.32 | 0.15 | 15% |
| Wind | 0.10 | 0.10 | 25% |
| Nuclear | 0.00 | 0.08 | 50% |
| Electrolysis | 0.18 | 0.12 | 20% |
| CCS | 0.10 | 0.10 | 30% |
| Batteries | 0.18 | 0.12 | 15% |

### Knowledge Stock
$$H(t) = \sum_\tau (1 - \delta_H)^{T-\tau} \times RND_\tau, \quad \delta_H = 0.10$$

### Cross-Tech Spillovers
5 technology families with spillover matrix (diagonal = 1.0, off-diagonal = 0.1–0.3). Effective cumulative and knowledge computed via matrix multiplication.

Phase 1: global learning pool, exogenous RND (IEA RD&D data when available).


## 6. Budget Constraint with R&D Crowding

### Updated Formula
$$I_K = s \cdot Y - I_E - \sum_i I_{RND,i}$$

**Three-way crowding**: energy investment ($I_E$) AND R&D spending ($\sum I_{RND}$) crowd out general capital ($I_K$).

This means aggressive clean energy transitions have **two** GDP cost channels:
1. High $I_E$ (building solar, wind, CCS, electrolyzers)
2. High $\sum I_{RND}$ (funding R&D to bring costs down)

Both reduce $I_K$ → slower capital accumulation → lower future GDP.

Updated in: `design/economy.md` (solver step 11, phased implementation table), `design/implementation.md`.


## 7. Initial Gap Analysis: Items #1–20

Conducted first comprehensive gap analysis across all design documents. Identified 20 items, prioritized:

### High Priority (Items #1–10) — Resolved in session

| # | Item | Resolution |
|---|------|-----------|
| 1 | EmissionResult multi-gas | Designed: co2, ch4, n2o, f_gases, lulucf fields + co2eq properties |
| 2 | BECCS architecture | biogenic_coef on SupplyTech (see §3 above) |
| 3 | LULUCF data source | EDGAR 2025, anthropogenic only (see §4 above) |
| 4 | Net-Zero definition | UNFCCC: anthropogenic CO₂+non-CO₂+LULUCF = 0 |
| 5 | Non-CO₂ pricing | Unified $/tCO₂eq, per-gas coverage toggles |
| 6 | CH₄ fugitive rates | 0.37/0.12/0.22 ×10⁶ tCH₄/EJ for coal/oil/gas |
| 7 | F-gas treatment | Kigali phase-down (exogenous schedule) |
| 8 | Budget constraint I_RND | Added to formula (see §6 above) |
| 9 | R32 region decision | Confirmed R32 for Phase 1 (see §1 above) |
| 10 | Phase 1 scope | Buildings full, DH, Materials nest, endogenous GDP (see §2 above) |

### Medium Priority (Items #11–20) — Deferred to next session

| # | Item | Status |
|---|------|--------|
| 11 | Logit signature undefined | Deferred |
| 12 | Oil → Refined Liquids price | Deferred |
| 13 | Demand-sector preference decay | Deferred |
| 14 | Savings rate regional variation | Deferred |
| 15 | VintageStock.surviving() | Already in code |
| 16 | production_at_price() | Already in code |
| 17 | base_demands data loading | Data task |
| 18 | TechChange.__init__() | Deferred |
| 19 | Q_ag base value | Deferred |
| 20 | Biomass residue → trade | Deferred |


## 8. Files Modified

| File | Changes |
|------|---------|
| `design/implementation.md` | BECCS architecture (biogenic_coef, LCOE credit), EmissionResult multi-gas, non-CO₂ pricing §16.4, economy sigma_el_nel |
| `design/emiss.md` | BECCS negative emissions calculation, LULUCF accounting |
| `design/economy.md` | Budget constraint $I_K = sY - I_E - \sum I_{RND}$ |
| `design/linkages.md` | LULUCF interface parameters |
| `ghim/data/emiss/` | EDGAR LULUCF data extraction |
| Memory files | Updated with all decisions |
