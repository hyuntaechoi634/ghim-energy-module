# GHIM Energy Module — Industry Sector Design

## 1. Scope

Industry is a **final energy demand sector**. In Phase 1 it consumes energy driven by GDP and allocates across carriers via logit. It does not produce materials or have process emissions.

Phase 3 extends Industry into a **supply sector for M** (materials in the KLEM production function), with subsector production models, process emissions, and materials trade.


## 2. Sector Structure

```
Industry
├── Energy Use (EU)              × 7 carriers (logit)
└── Feedstocks (FS)              × 5 carriers (logit)
```

### Energy Use

Industrial energy consumption for heat, motive power, and other processes. Carriers compete via preference-factor logit with vintage stock turnover.

| Carrier | Examples | Phase 1 role |
|---------|----------|-------------|
| Electricity | Electric arc furnaces, motors | Growing share (electrification) |
| Gas | Process heat, boilers | Incumbent |
| Coal | Blast furnaces, kilns | Declining |
| Refined Oil | Diesel engines, petrochemical heat | Moderate |
| Solid Biomass | Biomass boilers, co-firing | Niche |
| Biofuels | Biofuel-fired boilers | Minor ($\alpha$ small) |
| Hydrogen | DRI steel, high-temp heat | Emerging |

### Feedstocks (Non-Energy Use)

Energy carriers used as **raw material inputs**, not combusted. Carbon remains in product. Carriers compete via preference-factor logit, with shareweights ($\alpha_i$) constraining physically infeasible substitutions.

| Carrier | Use case |
|---------|----------|
| Refined Oil | Naphtha → plastics, petrochemicals |
| Gas | Ammonia (NH₃) feedstock |
| Coal | Coking coal for steel (metallurgical) |
| Biomass | Bio-naphtha, bio-based plastics (PLA, PHA), biochar as reductant |
| Hydrogen | Green ammonia, methanol synthesis |

Feedstock carrier switching is constrained by physical process requirements. Shareweights ($\alpha_i = 0$) block infeasible substitutions (e.g., electricity cannot be a feedstock). Preference factors are calibrated to reproduce base-year shares and decay slowly, reflecting the long timescales of process change.


## 3. Production and Energy Demand

### Industry production

$$Prod(t) = A_{prod} \times Prod_{base} \times \left(\frac{Y(t)}{Y_{base}}\right)^{\alpha} \times \left(\frac{P(t)}{P_{base}}\right)^{\beta}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $A_{prod}$ | Industry TFP (productivity improvement) | 1.0 (no autonomous improvement) |
| $\alpha$ | Income elasticity of industrial production | **0.8** |
| $\beta$ | Price elasticity of industrial production | **−0.3** |
| $Y$ | GDP (net output from economy module) | Endogenous |
| $P$ | Industry price index (see below) | Endogenous |

$A_{prod} = 1.0$ means all production growth in Phase 1 comes from GDP growth and price effects. This is intentional: autonomous industrial productivity is hard to separate from economy-wide TFP (already calibrated in the economy module). Phase 3 calibrates $A_{prod}$ separately from industry output projections.

### Energy demand

Energy Use and Feedstocks are independent inputs to industry production, each with its own **fixed** intensity coefficient:

$$EU(t) = ei_{EU} \times Prod(t)$$
$$FS(t) = ei_{FS} \times Prod(t)$$
$$E_{ind}(t) = EU(t) + FS(t)$$

| Parameter | Meaning | Phase 1 |
|-----------|---------|---------|
| $ei_{EU}$ | Energy use intensity (GJ/unit Prod) | Fixed at base-year value |
| $ei_{FS}$ | Feedstock intensity (GJ/unit Prod) | Fixed at base-year value |

Both $ei_{EU}$ and $ei_{FS}$ are **constants** in Phase 1 — no AEEI. This is a deliberate design choice:

- **Phase 1**: Efficiency improvement comes only from **carrier switching** via logit (e.g., shifting from coal boilers to electric heat pumps). The intensity coefficients stay fixed.
- **Phase 2**: The energy services nest (see `economy.md` §6) introduces endogenous efficiency via R&D knowledge stock. At that point, $ei_{EU}$ is replaced by $ei_{EU} / H^{RD}$ where $H^{RD}$ is endogenously determined. No need to undo an exogenous AEEI assumption.

This clean separation avoids double-counting efficiency gains and keeps the Phase 1 → Phase 2 transition smooth.

### Industry price index

The industry price index $P$ is the **unit energy cost of production** ($/unit Prod):

$$P = ei_{EU} \times P_{EU} + ei_{FS} \times P_{FS}$$

where:

- $P_{EU}$ = expenditure-weighted carrier price from Energy Use logit ($/GJ)
- $P_{FS}$ = expenditure-weighted carrier price from Feedstocks logit ($/GJ)

Carrier switching (via logit) changes the carrier mix → changes $P_{EU}$ and $P_{FS}$ → changes $P$ → feeds back to $Prod$ via price elasticity $\beta < 0$.

### Carrier allocation (Energy Use)

Preference-factor logit with vintage stock turnover:

$$s_i = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (C_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (C_j + p_j)\bigr)}$$

| Parameter | Meaning |
|-----------|---------|
| $\alpha_i$ | Technology availability {0, 1} (policy override) |
| $\beta < 0$ | Cost sensitivity parameter |
| $C_i$ | Carrier price ($/GJ, from energy module) |
| $p_i$ | Preference factor ($/GJ, calibrated at base year, decays over time) |

Stock turnover constrains the speed of carrier switching. Equipment lifetime ~25–40 years. Note: stock turnover operates at the **carrier level** within EU — the EU/FS split itself is a fixed structural ratio, not a vintage-tracked choice.

### Carrier allocation (Feedstocks)

Same preference-factor logit as Energy Use:

$$s_i^{FS} = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (C_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (C_j + p_j)\bigr)}$$

Physical process constraints are encoded via shareweights:
- $\alpha_i = 0$ blocks infeasible substitutions (e.g., electricity, biofuels cannot be feedstocks)
- Large $p_i$ values maintain base-year structure
- In Phase 3, subsector-level process models replace aggregate logit

### Reconciliation with macro CES

The macro energy demand $E$ from the CES first-order condition determines **total** energy. Industry's share of that total comes from its income/price-driven demand relative to other sectors. Sectoral demands are scaled to match the CES total:

$$E_{ind}^{actual} = E_{ind}^{raw} \times \frac{E_{CES}}{\sum_{sectors} E_{sector}^{raw}}$$


## 4. Emissions

### Principle

- **Energy Use**: Combustion emissions via carbon coefficients
- **Feedstocks**: Zero combustion CO₂ (carbon stays in product)
- **Supply-side vs Demand-side**: Electricity, hydrogen, and refined liquids emissions are counted at the **supply side** (Secondary Energy). Only direct combustion of coal, gas at the demand site counts as demand-side emissions.

### Carbon coefficients

| Carrier | Coef (tC/GJ) | Demand-side CO₂? | Reason |
|---------|-------------|-------------------|--------|
| Coal | 0.0257 | Yes | Direct combustion |
| Gas | 0.0153 | Yes | Direct combustion |
| Refined Oil | 0.0 | No | Counted at refining (Supply) |
| Solid Biomass | 0.0 | No | Biogenic carbon (neutral) |
| Biofuels | 0.0 | No | Biogenic carbon (neutral) |
| Electricity | 0.0 | No | Counted at generation (Supply) |
| Hydrogen | 0.0 | No | Counted at production (Supply) |

### Industry emissions calculation

$$CO2_{ind} = \sum_{c \in \{coal, gas\}} EU_c \times coef_c \times \frac{44}{12}$$

Feedstocks contribute **zero** to this sum regardless of carrier.

### IAMC reporting

| Variable | Source | Tier |
|----------|--------|------|
| `Emissions\|CO2\|Energy\|Demand` | Σ all sectors' direct combustion | **1** |
| `Emissions\|CO2\|Energy\|Supply` | Electricity + refining + H₂ | **1** |
| `Emissions\|CO2\|Energy\|Demand\|Industry` | Industry Energy Use combustion only | 2 |
| `Emissions\|CO2\|Industrial Processes` | Phase 1: skip | 2 |

Tier-1 requires only Supply/Demand split, not per-sector. The per-sector breakdown (Tier-2) comes for free from the structure.


## 5. Calibration

### Intensity coefficients

From base-year IEA energy balances:

$$ei_{EU} = \frac{EU_{base}}{Prod_{base}}, \quad ei_{FS} = \frac{FS_{base}}{Prod_{base}}$$

Globally, feedstocks account for ~17% of total industrial energy (varies by region).

### Logit preference factors

For both Energy Use and Feedstocks, preference factors are calibrated by inverting the logit at base year:

$$p_i = \frac{1}{\beta} \cdot \ln\!\left(\frac{S_i}{S_r}\right) - (C_i - C_r)$$

where $r$ is the reference carrier.

### Elasticities

| Parameter | Phase 1 default | Range in literature | References |
|-----------|-----------------|---------------------|------------|
| $\alpha$ (income elasticity) | **0.8** | 0.5–1.0 | IEA WEO, GCAM |
| $\beta$ (price elasticity) | **−0.3** | −0.2 to −0.5 | GCAM, EPPA |

Phase 1 defaults are mid-range. Final values via cross-validation with SSP reference runs.


## 6. User Configurables

Parameters the user can override without code changes:

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| $\alpha$ (income elasticity) | 0.8 | Global / regional |
| $\beta$ (price elasticity) | −0.3 | Global / regional |
| $ei_{EU}$ | Base-year calibrated | Regional (auto-calibrated from data) |
| $ei_{FS}$ | Base-year calibrated | Regional (auto-calibrated from data) |
| Carrier set (EU) | 7 carriers | Add/remove via config |
| Carrier set (FS) | 5 carriers | Add/remove via config |
| $\alpha_i$ (availability) | 1 for all | Per-carrier, per-period (policy JSON) |
| $P_i$ decay rate | Per-carrier default | Per-carrier override (policy JSON) |
| Stock turnover lifetime | 25–40 yr per carrier | Per-carrier override |
| Logit parameter ($\beta$) | Global default | Sector override |

The three-level parameter specification from `principle.md` §6 applies: global scalar → regional → regional × temporal. Phase 1 uses global defaults.


## 7. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Industrial FE by carrier | IEA WEB via gcamdata | R32 | `L1xx` energy balance chunks |
| EU / FS split | IEA WEB (non-energy use) | R32 | IEA reports non-energy use separately |
| Carrier prices | IEA, NREL ATB | R32 | For logit calibration |
| Industrial value added | SSP database or PWT | R32 | For $Prod_{base}$ and intensity calibration |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| GDP(t) | SSP database | Drives $Prod(t)$ via income elasticity |
| Population(t) | SSP database | Not directly used (Industry is GDP-driven, not per-capita) |
| Carrier prices(t) | Energy module | Endogenous within solver loop |

### Phase 3 additional data

| Data | Source | Notes |
|------|--------|-------|
| Subsector output (steel, cement, chemicals) | IEA, USGS, worldsteel | For disaggregated industry |
| Process emission factors | IPCC Guidelines | Cement calcination, chemical processes |
| Materials trade flows | GTAP | For materials market clearing |


## 8. IAMC Reporting Summary

### Final Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Industry` | EU + FS |
| `Final Energy\|Industry\|Electricity` | Electricity carrier total |
| `Final Energy\|Industry\|Liquids` | Refined Oil + Biofuels |
| `Final Energy\|Industry\|Liquids\|Oil` | Refined Oil carrier |
| `Final Energy\|Industry\|Liquids\|Biomass` | Biofuels carrier |
| `Final Energy\|Industry\|Solids` | Coal + Solid Biomass |
| `Final Energy\|Industry\|Solids\|Coal` | Coal carrier |
| `Final Energy\|Industry\|Solids\|Biomass` | Solid Biomass carrier |
| `Final Energy\|Industry\|Gases` | Gas total |
| `Final Energy\|Industry\|Hydrogen` | Hydrogen total |

### Final Energy (Tier-2, bonus)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Non-Energy Use\|{carrier}` | Feedstocks node directly |

### Emissions (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2` | Supply + Demand total |
| `Emissions\|CO2\|Energy\|Supply` | Electricity + refining + H₂ |
| `Emissions\|CO2\|Energy\|Demand` | Σ sector direct combustion (Industry EU included) |


## 9. Phased Implementation

| Component | Phase 1 | Phase 2 | Phase 3+ |
|-----------|---------|---------|----------|
| Subsectors | Aggregate (single Industry) | Same | Chemicals, Iron & Steel, Cement, Other |
| Energy Use | Logit × 7 carriers, fixed $ei_{EU}$ | $ei_{EU} / H^{RD}$ via energy services nest | Subsector-level logit |
| Feedstocks | Logit × 5 carriers (shareweight-constrained), fixed $ei_{FS}$ | Same | Process-level models |
| $A_{prod}$ | 1.0 | Same | Calibrated from industry output projections |
| Efficiency | Carrier switching only | Endogenous via R&D knowledge stock | Same |
| $ei_{FS}$ | Constant | Same | Process-dependent (e.g., circular economy) |
| Process emissions | Skip | Skip | Cement calcination, chemical process CO₂ |
| Materials supply | Not modeled | Not modeled | Industry becomes M supplier to KLEM |

### Phase transition notes

- **Phase 1 → 2**: Only change is adding the energy services nest in the economy module. Industry code is unchanged — $ei_{EU}$ is still a constant, but the economy module scales effective energy demand via $H^{RD}$.
- **Phase 2 → 3**: Major structural change. Industry splits into subsectors, each with own production model, carrier mix, and process emissions. Feedstock logit replaced by process-level models. Industry becomes the supplier of M to the KLEM production function.
