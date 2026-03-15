# GHIM Energy Module — Transport Sector Design

## 1. Scope

Transport is a **final energy demand sector** covering Passenger and Freight. Energy demand is driven by per-capita income and population. **Powertrains** compete via logit on LCOT (Levelized Cost of Transport) within each subsector, with each powertrain mapping to exactly one fuel carrier (1:1). LCOT includes time value (VOT/speed), which penalizes powertrains with lower effective speed (e.g., BEV charging downtime).

Phase 1 covers aggregate Passenger and Freight without mode disaggregation. Phase 2+ adds mode competition (road/rail/air/ship) and detailed vehicle technology parameters.

Bunkers (international aviation + international shipping) are a separate sector — see `design/bunkers.md`.


## 2. Sector Structure

```
Transport
├── Passenger                       (6 powertrains, LCOT logit)
│   ├── ICE                        → Refined Oil
│   ├── Bio-ICE                    → Biofuels
│   ├── HEV                        → Refined Oil
│   ├── BEV                        → Electricity
│   ├── FCEV                       → Hydrogen
│   └── NG                         → Gas
│
└── Freight                         (5 powertrains, LCOT logit)
    ├── Diesel                     → Refined Oil
    ├── Biodiesel                  → Biofuels
    ├── Electric                   → Electricity
    ├── FCEV                       → Hydrogen
    └── NG                         → Gas
```

### Powertrain → Fuel Mapping (1:1)

| Powertrain | Fuel Carrier | Phase 1 role |
|------------|-------------|-------------|
| ICE / Diesel | Refined Oil | Dominant |
| Bio-ICE / Biodiesel | Biofuels | Policy-driven (mandates) |
| HEV | Refined Oil | Transitional (higher efficiency) |
| BEV / Electric | Electricity | Growing (battery cost decline) |
| FCEV | Hydrogen | Emerging |
| NG | Gas | Niche |

Every powertrain maps to exactly one carrier. No blends, no dual fuel, no split ratios.

Passenger and Freight have **independent demand** — they do not compete with each other. Each has its own demand determined by income and price, and powertrains compete only within each subsector.


## 3. Service Demand

### 3.1 Passenger service demand

Per-capita passenger mobility (passenger-km/person):

$$pkm_{pc}(t) = pkm_{pc,base} \times \left(\frac{GDP_{pc}(t)}{GDP_{pc,base}}\right)^{\alpha_P} \times \left(\frac{P_P(t)}{P_{P,base}}\right)^{\beta_P}$$

Total passenger service demand:

$$SD_P(t) = pkm_{pc}(t) \times Pop(t)$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $pkm_{pc,base}$ | Base-year per-capita passenger-km | Calibrated from IEA/ITF |
| $\alpha_P$ | Income elasticity of passenger mobility | **0.8** |
| $\beta_P$ | Price elasticity of passenger mobility | **−0.3** |
| $P_P$ | Passenger transport price index ($/pkm, see §3.5) | Endogenous |

### 3.2 Freight service demand

Freight demand driven by per-capita GDP (proxy for economic freight intensity):

$$tkm_{pc}(t) = tkm_{pc,base} \times \left(\frac{GDP_{pc}(t)}{GDP_{pc,base}}\right)^{\alpha_F} \times \left(\frac{P_F(t)}{P_{F,base}}\right)^{\beta_F}$$

Total freight service demand:

$$SD_F(t) = tkm_{pc}(t) \times Pop(t)$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $tkm_{pc,base}$ | Base-year per-capita ton-km | Calibrated from IEA/ITF |
| $\alpha_F$ | Income elasticity of freight demand | **0.7** |
| $\beta_F$ | Price elasticity of freight demand | **−0.3** |
| $P_F$ | Freight transport price index ($/tkm, see §3.5) | Endogenous |

### 3.3 Powertrain competition

For each subsector $sub \in \{P, F\}$, powertrains compete via preference-factor logit on LCOT:

$$s_i^{sub} = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (LCOT_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (LCOT_j + p_j)\bigr)}$$

| Parameter | Meaning |
|-----------|---------|
| $\alpha_i$ | Technology availability {0, 1} (policy override) |
| $\beta < 0$ | Cost sensitivity parameter |
| $LCOT_i$ | Levelized cost of transport (see §3.4) |
| $p_i$ | Preference factor ($/pkm or $/tkm, calibrated at base year, decays over time) |

**Vintage tracking** constrains the speed of powertrain switching. Every powertrain has a `VintageTracker` — vehicle fleet is a physical stock that turns over gradually. An ICE car bought in 2025 stays on the road until ~2040; BEV sales don't instantly replace the fleet.

- Vehicle lifetime: ~15 years (passenger), ~20 years (freight)
- Retirement: S-curve for ICE/HEV/NG/FCEV; hard cutoff for BEV/Electric (battery degradation)
- Initialization: `initialize_uniform()` from base-year carrier shares × total transport EJ (no detailed registration data needed)
- Gap-filling: `target_share × total - surviving → new_investment` (same pattern as electricity)

Note: stock turnover operates at the **powertrain level** — the passenger/freight split itself is structurally determined by income and GDP, not by vintage-tracked choice.

### 3.4 Levelized Cost of Transport (LCOT)

$$LCOT_i = \frac{capex_i \times FCR}{annual\_SD_i} + \frac{C_{fuel,i}}{eff_i} + O\&M_i + \frac{VOT}{speed_i}$$

| Component | Meaning |
|-----------|---------|
| $capex_i$ | Vehicle capital cost ($/vehicle) |
| $FCR$ | Fixed charge rate (annualized capital recovery) |
| $annual\_SD_i$ | Annual service per vehicle (pkm or tkm) |
| $C_{fuel,i}$ | Fuel price of the mapped carrier ($/GJ) |
| $eff_i$ | Service efficiency (pkm/GJ or tkm/GJ) |
| $O\&M_i$ | Maintenance + insurance ($/pkm or $/tkm) |
| $VOT$ | Value of time ($/hr) |
| $speed_i$ | Effective speed (km/hr), including refueling/charging downtime |

### Value of Time (VOT)

$$VOT = \frac{GDP_{pc}}{hrs\_yr}$$

where $hrs\_yr$ ≈ 2000 (annual working hours). VOT rises with income — richer travelers value time more.

**Effective speed** $speed_i$ is not the driving speed but the **door-to-door average** including refueling/charging stops:

| Powertrain | Passenger effective speed | Freight effective speed | Why |
|------------|--------------------------|------------------------|-----|
| ICE / Diesel | Reference (1.0×) | Reference (1.0×) | 5 min refuel |
| Bio-ICE / Biodiesel | ≈ ICE | ≈ Diesel | Same refueling |
| HEV | ≈ ICE | — | Same refueling |
| BEV / Electric | **0.85–0.95×** | **0.75–0.90×** | Charging stops (30–60 min), range anxiety detours |
| FCEV | ≈ ICE | ≈ Diesel | 5 min refuel (but sparse infrastructure → lower in early years) |
| NG | 0.95× | 0.90× | Sparse refueling network |

The VOT/speed term creates a **natural headwind against BEV adoption** that a purely fuel-cost-based LCOT misses. BEV has lower fuel cost but higher time cost. As charging infrastructure improves and charging speed increases, BEV effective speed converges to ICE — this is captured by time-varying $speed_{BEV}(t)$ in Phase 2.

For freight, the penalty is larger: BEV trucks lose significant productive hours to charging, directly impacting fleet economics. This explains why freight electrification lags passenger.

### Efficiency by powertrain

| Powertrain | Passenger eff (pkm/GJ) | Freight eff (tkm/GJ) |
|------------|----------------------|---------------------|
| ICE / Diesel | ~400 | ~150 |
| Bio-ICE / Biodiesel | ~400 (≈ ICE) | ~150 (≈ Diesel) |
| HEV | ~550–600 (1.4× ICE) | — |
| BEV / Electric | ~1200 (3× ICE) | ~450 (3× Diesel) |
| FCEV | ~600 (1.5× ICE) | ~200 |
| NG | ~380 | ~140 |

All efficiencies **fixed** in Phase 1. Same rationale as Industry and Buildings: no exogenous improvement. Efficiency gains come from **powertrain switching** via logit (e.g., ICE → BEV gives ~3× efficiency). Phase 2 adds technology improvement curves.

BEV efficiency ~3× ICE is the key electrification mechanism: same service with ~1/3 the energy.

### Capex and learning curves

| Powertrain | Phase 1 capex (relative to ICE) | Learning |
|------------|-------------------------------|----------|
| ICE / Diesel | 1.0× (reference) | Mature (no decline) |
| Bio-ICE / Biodiesel | 1.0× (same vehicle) | — |
| HEV | ~1.15–1.25× | Slow decline |
| BEV / Electric | ~1.3–1.8× (battery-dominated) | **Battery LBD ~15–18%** |
| FCEV | ~2.0–3.0× | Fuel cell LBD ~15% |
| NG | ~1.05–1.15× | Mature |

BEV capex decline via two-factor learning:

$$capex_{BEV}(t) = capex_0 \times \left(\frac{Q^{cum}}{Q_0}\right)^{-\lambda_{LBD}}$$

Battery learning rate ~15–18% (cost halves per ~4× cumulative production). Floor at 30% of initial capex. This is the primary driver of BEV adoption.

### 3.5 Transport price index

Price indices aggregate bottom-up from powertrain LCOT:

**Subsector price index** (share-weighted LCOT):

$$P_{sub} = \sum_i s_i^{sub} \times LCOT_i$$

**Sector price index** (demand-weighted across subsectors):

$$P_{trn} = \frac{E_P \cdot P_P + E_F \cdot P_F}{E_P + E_F}$$

$P_{sub}$ feeds back into service demand (§3.1, §3.2) via the price elasticity. $P_{trn}$ feeds into the macro composite energy price $P_E$ via expenditure weighting.

### 3.6 Fuel demand

Each powertrain maps to exactly one fuel. Total fuel demand by carrier:

$$E_{fuel}(t) = \sum_{sub} \sum_{i \in pt(fuel)} \frac{SD_{sub}(t) \times s_i^{sub}(t)}{eff_i}$$

where $pt(fuel)$ is the set of powertrains that use carrier $fuel$.

Example: Refined Oil demand from transport = (ICE share × SD_P / eff_ICE) + (HEV share × SD_P / eff_HEV) + (Diesel share × SD_F / eff_Diesel).

### 3.7 Total transport energy demand

$$E_{trn}(t) = \sum_{sub} \sum_i \frac{SD_{sub}(t) \times s_i^{sub}(t)}{eff_i}$$

### 3.8 Reconciliation with macro CES

Same as Industry and Buildings. Sectoral demands are scaled to match the CES total:

$$E_{trn}^{actual} = E_{trn}^{raw} \times \frac{E_{CES}}{\sum_{sectors} E_{sector}^{raw}}$$


## 4. Emissions

### Principle

- Refined Oil emissions counted at refining (supply side), not tailpipe
- Direct combustion of Gas (NG vehicles) → demand-side emissions
- Electricity, Hydrogen → supply-side emissions
- Biofuels → carbon-neutral

### Carbon coefficients by fuel

| Fuel Carrier | Coef (tC/GJ) | Demand-side CO₂? |
|-------------|-------------|-------------------|
| Refined Oil | 0.0 | No (counted at refining) |
| Biofuels | 0.0 | No (biogenic) |
| Gas | 0.0153 | Yes (direct combustion) |
| Electricity | 0.0 | No (counted at generation) |
| Hydrogen | 0.0 | No (counted at production) |

### Transport emissions calculation

$$CO2_{trn} = \sum_{sub} E_{sub,gas} \times 0.0153 \times \frac{44}{12}$$

Only NG powertrain contributes to transport demand-side emissions.


## 5. Calibration

### Per-capita service demand

From base-year transport statistics (IEA Mobility Model, ITF Transport Outlook):

$$pkm_{pc,base} = \frac{PKM_{total,base}}{Pop_{base}}, \quad tkm_{pc,base} = \frac{TKM_{total,base}}{Pop_{base}}$$

### Powertrain efficiencies

Calibrated from base-year energy consumption and service output:

$$eff_i^{sub} = \frac{SD_{sub,base} \times s_{i,base}}{E_{sub,i,base}}$$

### Powertrain capex

From IEA Global EV Outlook (BEV/FCEV), auto industry data (ICE/HEV/NG).

### Effective speed

Calibrated from:
- Average trip distance and refueling/charging time data (AFDC, ChargePoint)
- Fleet utilization surveys (freight: ATA, IRU)
- Phase 1: constant per powertrain. Phase 2: time-varying as infrastructure improves.

### Logit preference factors

Calibrated by inverting the logit at base year:

$$p_i = \frac{1}{\beta} \cdot \ln\!\left(\frac{S_i}{S_r}\right) - (LCOT_i - LCOT_r)$$

### Elasticities

| Parameter | Phase 1 default | Range | References |
|-----------|-----------------|-------|------------|
| $\alpha_P$ (income, passenger) | **0.8** | 0.5–1.0 | ITF, GCAM (saturation at high income) |
| $\alpha_F$ (income, freight) | **0.7** | 0.5–0.9 | ITF, GCAM |
| $\beta$ (price elasticity) | **−0.3** | −0.2 to −0.5 | GCAM, IEA |

Income elasticity of passenger travel saturates at high GDP/cap. Phase 2+ can implement GDP-dependent elasticity.


## 6. User Configurables

Parameters the user can override without code changes:

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| $\alpha_P$, $\alpha_F$ (income elasticity) | 0.8, 0.7 | Global / regional |
| $\beta$ (price elasticity) | −0.3 | Global / regional |
| Powertrain set (Passenger) | 6 powertrains | Add/remove via config |
| Powertrain set (Freight) | 5 powertrains | Add/remove via config |
| $capex_i$ | Per-powertrain | Per-powertrain, per-region |
| $eff_i$ | Per-powertrain | Per-powertrain, per-region |
| $speed_i$ | Per-powertrain | Per-powertrain (Phase 2: time-varying) |
| $O\&M_i$ | Per-powertrain | Per-powertrain |
| Learning rate ($\lambda_{LBD}$) | BEV 15%, FCEV 15% | Per-powertrain |
| Capex floor | 30% of initial | Per-powertrain |
| $\alpha_i$ (availability) | 1 for all | Per-powertrain, per-period (policy JSON) |
| $P_i$ decay rate | Per-powertrain default | Per-powertrain override (policy JSON) |
| Vehicle lifetime | 12–15 yr (pass.), 10–20 yr (freight) | Per-powertrain |
| Logit parameter ($\beta$) | Global default | Sector override |

Three-level parameter specification applies: global scalar → regional → regional × temporal.


## 7. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Passenger-km, ton-km | ITF Transport Outlook, IEA Mobility | R32 | For service demand calibration |
| Transport FE by fuel | IEA WEB via gcamdata | R32 | `L1xx` energy balance chunks |
| Powertrain market shares | IEA Global EV Data Explorer | R32 | BEV/FCEV/ICE stock shares |
| Vehicle capex | IEA GEO, BloombergNEF | Global + regional adjustments | For LCOT calculation |
| Fuel prices | IEA, energy module | R32 | For logit calibration |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| GDP(t), GDP_pc(t) | SSP database | Drives service demand + VOT |
| Pop(t) | SSP database | Drives total service demand |
| Fuel prices(t) | Energy module | Endogenous within solver loop |
| Cumulative deployment | Model-endogenous | For learning curve capex decline |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| Mode-level service (road/rail/air/ship) | ITF, UIC, ICAO | For mode disaggregation |
| Average trip distance by mode | National travel surveys | For VOT/speed by mode |
| Charging infrastructure projections | IEA GEVO, national plans | For BEV speed improvement |
| Load factors (passengers/vehicle, tons/vehicle) | IEA, fleet surveys | Explicit load factor modeling |


## 8. IAMC Reporting Summary

### Final Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Transportation` | $E_{trn}$ |
| `Final Energy\|Transportation\|Liquids` | Refined Oil + Biofuels |
| `Final Energy\|Transportation\|Liquids\|Oil` | Refined Oil (from ICE + HEV + Diesel) |
| `Final Energy\|Transportation\|Liquids\|Biomass` | Biofuels (from Bio-ICE + Biodiesel) |
| `Final Energy\|Transportation\|Electricity` | Electricity (from BEV + Electric) |
| `Final Energy\|Transportation\|Hydrogen` | Hydrogen (from FCEV) |
| `Final Energy\|Transportation\|Gases` | Gas (from NG) |

### Final Energy (Tier-2)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Transportation\|Passenger\|{fuel}` | Passenger subsector by fuel carrier |
| `Final Energy\|Transportation\|Freight\|{fuel}` | Freight subsector by fuel carrier |

### Emissions (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2\|Energy\|Demand` | Includes transport direct combustion (NG only) |
| `Emissions\|CO2\|Energy\|Demand\|Transportation` | $CO2_{trn}$ (Tier-2) |


## 9. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Subsectors | Passenger + Freight (aggregate) | Same |
| Modes | No mode disaggregation | Road/Rail/Air/Ship with logit competition |
| Competition | Powertrain logit on LCOT | Same + mode logit on generalized cost |
| Powertrains | 6 Passenger + 5 Freight = 11 | + PHEV, mode-specific variants |
| **Vintage tracking** | **All powertrains (S-curve/hard cutoff)** | Same |
| LCOT | capex + fuel + O&M + VOT/speed | Same + mode-specific infrastructure costs |
| VOT | $GDP_{pc}/hrs\_yr$; speed fixed per powertrain | Speed time-varying (infra improvement) |
| Learning | BEV battery, FCEV fuel cell | Same + component-level learning |
| Efficiency | Fixed per powertrain | Time-varying (technology improvement) |
| Price index | Subsector (LCOT) + sector (demand-weighted) | Same |
| Income elasticity | Constant | GDP-dependent (saturation) |
| Load factor | Implicit in efficiency | Explicit (passengers/vehicle, tons/vehicle) |
| Biofuels | Separate powertrain (Bio-ICE) | Same + blend mandates within ICE |

### Phase transition notes

- **Phase 1 → 2**: Add mode disaggregation (road/rail/air/ship) within Passenger and Freight. Each mode gets its own powertrain set and logit. VOT becomes mode-differentiating (air fast but expensive, rail slower but cheaper). BEV effective speed becomes time-varying as charging networks expand. No structural change to LCOT formula — just more entries.
- **Phase 2 → 3**: Load factors explicit, component-level learning (battery vs motor vs power electronics separately), autonomous vehicles (affect VOT), shared mobility (affect annual_SD per vehicle).
