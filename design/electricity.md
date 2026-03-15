# GHIM Energy Module — Electricity Sector Design

## 1. Scope

Electricity is a **secondary energy transformation sector**. It converts primary energy (coal, gas, oil, uranium, biomass, wind, solar, hydro, geothermal, ocean) into electricity via 17 competing technologies. Technology shares are determined by preference-factor logit on LCOE. Capacity evolves via vintage stock with S-curve retirement and profit-based shutdown.

Phase 1 covers single logit per region with VintageStock, learning curves, profit shutdown, and resource constraints. Phase 2+ adds storage, T&D detail, and cross-border trade.


## 2. Technology Tree

```
Secondary Energy | Electricity (17 technologies, single logit per region)
├── Coal                ├── Coal w/ CCS
├── Gas CC              ├── Gas CC w/ CCS
├── Oil
├── Biomass             ├── Biomass w/ CCS (BECCS)
├── Nuclear
├── Hydro
├── Solar | PV          ├── Solar | CSP
├── Wind | Onshore      ├── Wind | Offshore
├── Geothermal
├── Ocean
├── Hydrogen            ├── Ammonia
```

### Technology classification

| Category | Technologies | Fuel source |
|----------|-------------|-------------|
| Fossil | Coal, Gas CC, Oil | Trade module (world price) |
| Fossil + CCS | Coal w/ CCS, Gas CC w/ CCS | Trade module + CCS cost |
| Nuclear | Nuclear | Trade module (uranium) |
| Biomass | Biomass, Biomass w/ CCS | Trade module (biomass) |
| Renewable | Solar PV, Solar CSP, Wind Onshore, Wind Offshore, Hydro, Geothermal, Ocean | Free fuel, resource-constrained |
| Fuel-based | Hydrogen, Ammonia | From H₂/NH₃ production sector |

### CCS technologies

CCS variants have the same base technology but with additional capex, efficiency penalty, and CO₂ capture:

| Parameter | Coal w/ CCS | Gas CC w/ CCS | Biomass w/ CCS |
|-----------|-------------|---------------|----------------|
| Capture rate | 90% | 90% | 90% |
| Efficiency penalty | −8 pp | −7 pp | −8 pp |
| Additional capex | +60–80% | +50–70% | +80–100% |
| T&S cost ($/tCO₂) | 10–20 | 10–20 | 10–20 |
| Net emissions | ~10% of unabated | ~10% of unabated | **Negative** (biogenic C captured) |

Biomass w/ CCS (BECCS) produces **negative emissions** — biogenic carbon is captured and stored. This is a key technology for net-zero scenarios.

CCS technologies have $\alpha_i = 0$ (blocked) until a configurable availability year (default: 2030). They become competitive when carbon price exceeds the CCS cost premium.


## 3. Supply Determination

### 3.1 Electricity demand

Total electricity demand is the sum across all final demand sectors:

$$EL_{demand}(t) = \sum_{sectors} E_{sector,electricity}(t)$$

where each sector's electricity demand comes from its own demand function and carrier logit.

### 3.2 Technology shares

Preference-factor logit on LCOE:

$$s_i = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (LCOE_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (LCOE_j + p_j)\bigr)}$$

where:
- $\alpha_i$ = availability {0, 1}
- $\beta < 0$ = cost sensitivity parameter
- $LCOE_i$ = levelized cost of electricity ($/GJ)
- $p_i$ = preference factor ($/GJ, calibrated at base year, decays over time)

### 3.3 LCOE

$$LCOE_i = \frac{capex_i \cdot FCR}{CF_i \cdot 8760} + FOM_i + \frac{fuel_i}{eff_i} + \frac{coef_i \cdot (1 - capture_i) \cdot P_{carbon}}{eff_i} + VOM_i + TS_i$$

| Component | Meaning | Units |
|-----------|---------|-------|
| $capex_i$ | Capital cost, declines via learning curves | $/kW |
| $FCR$ | Fixed charge rate (annualized capital recovery) | 1/yr |
| $CF_i$ | Capacity factor (regional, technology-specific) | fraction |
| $FOM_i$ | Fixed O&M | $/kW/yr |
| $fuel_i$ | Fuel price (from trade module) | $/GJ |
| $eff_i$ | Thermal efficiency (1.0 for renewables) | fraction |
| $coef_i$ | Carbon coefficient | tC/GJ |
| $capture_i$ | CCS capture rate (0 for non-CCS, 0.9 for CCS) | fraction |
| $P_{carbon}$ | Carbon price | $/tCO₂ |
| $VOM_i$ | Variable O&M | $/MWh |
| $TS_i$ | CO₂ transport & storage cost (0 for non-CCS) | $/MWh |

**T&D markup**: A fixed transmission & distribution markup is added to the wholesale LCOE to get the retail electricity price seen by demand sectors:

$$p_{EL,retail} = p_{EL,wholesale} + TD_{markup}$$

Phase 1 default: $TD_{markup}$ = 15 $/MWh (~0.015 $/kWh). Phase 2+ replaces with detailed grid model.

### 3.4 Generation

$$EL_{supply,i}(t) = s_i(t) \times EL_{demand}(t)$$

Subject to VintageStock constraints (§4) and resource constraints (§5).

### 3.5 Electricity price

Share-weighted LCOE:

$$p_{EL} = \sum_i s_i \times LCOE_i + TD_{markup}$$

This price feeds back to final demand sectors as the electricity carrier price.

### 3.6 Fuel inputs to primary energy

$$Fuel_{i}(t) = \frac{EL_{supply,i}(t)}{eff_i}$$

These fuel demands enter the trade module for global market clearing (coal, gas, oil, uranium, biomass).

### 3.7 Emissions

$$CO2_{elec} = \sum_i Fuel_i \times coef_i \times (1 - capture_i) \times \frac{44}{12}$$

Reported as `Emissions|CO2|Energy|Supply|Electricity`.

For BECCS: $coef_{biomass} = 0$ (biogenic) but captured carbon is stored → reported as **negative emissions** (Carbon Dioxide Removal):

$$CDR_{BECCS} = Fuel_{BECCS} \times coef_{biomass}^{physical} \times capture_{BECCS} \times \frac{44}{12}$$


## 4. Vintage Stock

### 4.1 Effective capacity

$$Q_{eff,i}(t) = \sum_v C_{i,v} \cdot S(t - v) \cdot P(\pi_{i,v})$$

where:
- $C_{i,v}$: installed capacity of technology $i$ at vintage $v$ (EJ)
- $S(age)$: age-based survival fraction
- $P(\pi)$: profit-based operating fraction

Both factors multiply — a plant must be both **young enough** and **profitable enough** to operate.

### 4.2 Age-based retirement (S-curve)

$$S(a) = \frac{1/(1 + \exp(k \cdot (a - \rho \cdot L)))}{S(0)}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $\rho$ | Half-life ratio | **0.75** |
| $k$ | Steepness | **0.1** |
| $L$ | Technology lifetime (years) | Per-technology (see table) |

Hard cutoff at $L$ for all technologies. Renewables (solar, wind): hard cutoff only (no S-curve decline before $L$).

| Technology | Lifetime $L$ (years) |
|-----------|---------------------|
| Coal, Coal w/ CCS | 60 |
| Gas CC, Gas CC w/ CCS | 45 |
| Oil | 45 |
| Biomass, Biomass w/ CCS | 60 |
| Nuclear | 60 |
| Hydro | 80 |
| Solar PV | 30 |
| Solar CSP | 30 |
| Wind Onshore | 30 |
| Wind Offshore | 30 |
| Geothermal | 40 |
| Ocean | 30 |
| Hydrogen, Ammonia | 30 |

### 4.3 Profit-based shutdown

Plants that are unprofitable (variable cost exceeds revenue) shut down before age retirement:

$$\pi_i = \frac{p_{elec} - c_{var,i}}{|c_{var,i}|}$$

where:
- $p_{elec}$: wholesale electricity price ($/MWh)
- $c_{var,i}$: variable cost = $fuel_i / eff_i + coef_i \cdot (1-capture_i) \cdot P_{carbon} / eff_i + VOM_i$ ($/MWh)

Operating fraction as smooth S-curve:

$$P(\pi) = \frac{1}{1 + \exp(-\sigma \cdot (\pi - m))}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $m$ | Median shutdown point (π where P=0.5) | **−0.1** |
| $\sigma$ | Steepness (GCAM A23) | **6** |

Interpretation:
- $\pi > 0$: profitable → $P \approx 1$ (runs)
- $\pi \approx -0.1$: marginally unprofitable → $P \approx 0.5$ (50% shutdown)
- $\pi < -0.3$: deeply unprofitable → $P \approx 0$ (full shutdown)

This is the **primary mechanism for coal exit** under carbon pricing: $P_{carbon}$ ↑ → $c_{var,coal}$ ↑ → $\pi_{coal}$ ↓ → existing coal plants shut down before age retirement. Without profit shutdown, unprofitable plants run until they physically retire — unrealistic behavior.

Renewables have $c_{var} \approx 0$ (no fuel cost), so $\pi \gg 0$ always — they never profit-shut. This is correct: solar/wind curtailment is a dispatch issue (Phase 2+), not an economic shutdown.

### 4.4 Gap-filling

$$new\_capacity_i = \max(0,\; s_i \times EL_{demand} - surviving_i - pipeline_i)$$

New capacity fills the gap between demand allocation and surviving + in-construction capacity.

### 4.5 Construction pipeline

PipelineAwareVintageStock for long-build technologies:
- Nuclear: 2-period (10yr) construction delay
- Hydro: 1-period (5yr) construction delay

All other technologies: immediate delivery (build within one period).

### 4.6 Investment

$$I_{elec} = \sum_i new\_capacity_i \times capex_i$$

Feeds into budget constraint: $I_K = s \times Y - I_{energy}$.


## 5. Resource Constraints

### Renewable potential caps

Logit share is capped by regional resource potential:

$$s_i^{actual} = \min(s_i^{logit},\; s_i^{max\_potential})$$

Excess share redistributed to unconstrained technologies.

| Technology | Constraint type | Data source |
|-----------|----------------|-------------|
| Hydro | Max capacity (GW) | Economic potential per region |
| Wind Onshore | Graded supply curve (best sites first) | NREL, regional wind class CFs |
| Wind Offshore | Graded supply curve (depth/distance) | NREL, EEZ areas |
| Solar PV | Graded supply curve (irradiance) | Smith irradiance data, land area |
| Solar CSP | Graded supply curve (DNI) | DNI data, 5% area threshold |
| Geothermal | Max capacity (GW) | Geological survey |
| Ocean | Max capacity (GW) | Coastline potential |

### Fossil fuel prices

From trade module global market clearing (coal, gas, oil, uranium, biomass). See `design/trade.md`.


## 6. Learning Curves

Two-factor learning for capital cost decline:

$$capex_i(t) = capex_{i,0} \times \left(\frac{Q_i^{cum}}{Q_{i,0}}\right)^{-\lambda_{LBD}} \times \left(\frac{H_i^{RD}}{H_{i,0}}\right)^{-\lambda_{RND}}$$

Floor: $0.2 \times capex_{i,0}$.

| Technology | LBD Rate | RND Channel | Floor (% of initial) |
|-----------|---------|-------------|---------------------|
| Solar PV | 20% | High | 20% |
| Solar CSP | 15% | Medium | 25% |
| Wind Onshore | 12% | Medium | 30% |
| Wind Offshore | 10% | Medium | 30% |
| Nuclear | 3% | Low | 50% |
| CCS (all) | 5% | Medium | 40% |
| Hydrogen turbine | 10% | Medium | 30% |
| Batteries (storage, Phase 2+) | 15% | High | 15% |

Phase 1: $H^{RD}$ is exogenous (grows at fixed rate). Phase 2: endogenous R&D via energy services nest.


## 7. Module Interfaces (Phase 2+)

External modules affect electricity through **multipliers on existing parameters**. Phase 1 uses default values (1.0); external modules override when connected.

### 7.1 Interface parameters

| Parameter | Affects | Phase 1 | Phase 2+ source |
|-----------|---------|---------|----------------|
| `cf_multiplier[hydro]` | Hydro capacity factor | 1.0 | Climate (precipitation/runoff) |
| `cf_multiplier[solar]` | Solar capacity factor | 1.0 | Climate (irradiance change) |
| `cf_multiplier[wind]` | Wind capacity factor | 1.0 | Climate (wind speed change) |
| `eff_multiplier[thermal]` | Thermal plant efficiency | 1.0 | Climate (ambient temperature) |
| `cap_multiplier[thermal]` | Thermal plant max capacity | 1.0 | Water (cooling water availability) |
| `cap_multiplier[solar/wind]` | RE deployment ceiling | 1.0 | AFOLU (land competition) |
| `biomass_supply` | Biomass fuel availability | Exogenous | AFOLU (land allocation) |

### 7.2 Feedback directions

```
Climate → Electricity:
  Temperature → eff_multiplier (thermal cooling penalty)
  Precipitation → cf_multiplier[hydro]
  Irradiance/wind → cf_multiplier[solar/wind]

Water → Electricity:
  Water availability → cap_multiplier[thermal] (cooling water constraint)

AFOLU → Electricity:
  Land allocation → biomass_supply (biomass availability)
  Land competition → cap_multiplier[solar/wind] (RE land constraint)

Electricity → Other modules:
  Emissions → Climate module
  Biomass demand → AFOLU (land pressure)
  Water demand → Water module (cooling water consumption)
  Investment → Economy (budget constraint)
```


## 8. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Technology set | 17 technologies | Add/remove via config |
| $capex_i$ | Per-technology (NREL ATB) | Per-tech, per-region |
| $eff_i$ | Per-technology | Per-tech, per-region |
| $CF_i$ | Per-technology, per-region (gcamdata) | Per-tech, per-region |
| $FOM_i$, $VOM_i$ | Per-technology (NREL ATB) | Per-tech |
| $L_i$ (lifetime) | Per-technology (see §4.2) | Per-tech |
| $capture_i$ | 0.9 for CCS, 0 otherwise | Per-tech |
| $TS_i$ (transport & storage cost) | 15 $/tCO₂ | Per-tech, per-region |
| $TD_{markup}$ | 15 $/MWh | Per-region |
| CCS availability year | 2030 | Per-tech (policy JSON) |
| $\alpha_i$ (availability) | 1 (0 for CCS before avail. year) | Per-tech, per-period (policy JSON) |
| $P_i$ decay rate | Per-tech default | Per-tech override (policy JSON) |
| Learning rates ($\lambda_{LBD}$) | Per-tech (see §6) | Per-tech |
| Capex floor | Per-tech (see §6) | Per-tech |
| Profit shutdown $m$, $\sigma$ | −0.1, 6 (GCAM A23) | Global or per-tech |
| Resource potential caps | Per-region (gcamdata) | Per-tech, per-region |
| Logit parameter ($\beta$) | Global default | Sector override |
| $FCR$ | 0.08 (8% WACC, 30yr) | Global / regional / per-tech |

Three-level parameter specification applies: global scalar → regional → regional × temporal.


## 9. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Electricity generation by tech | IEA WEB via gcamdata | R32 | For base-year tech shares |
| Installed capacity by tech | IRENA, WNA (nuclear) | R32 | For VintageStock initialization |
| Capacity factors | gcamdata (Smith irradiance, wind class CFs) | R32 | Regional renewable CFs |
| Technology costs (capex, FOM, VOM) | NREL ATB 2024 | Global + regional adj. | For LCOE calculation |
| Fuel prices | Trade module / IEA | R32 | For LCOE calculation |
| Hydro potential | gcamdata (`Hydropower_potential`) | R32 | Max hydro capacity |
| Wind/Solar potential | gcamdata (wind class, irradiance) | R32 | Graded supply curves |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| Fuel prices(t) | Trade module | Endogenous within solver loop |
| $P_{carbon}(t)$ | Policy JSON | User-specified carbon price path |
| Cumulative deployment | Model-endogenous | For learning curve capex decline |
| $H^{RD}(t)$ | Exogenous growth (Phase 1) | For RND channel |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| Storage costs (battery, pumped hydro) | NREL ATB, BloombergNEF | For storage technologies |
| Interconnector capacities | ENTSO-E, regional grid data | For cross-border trade |
| Cooling water coefficients | gcamdata (`Macknick_elec_water`) | For water constraint |
| Climate projections (HDD/CDD, precip) | CMIP6, climate module | For CF/eff multipliers |


## 10. IAMC Reporting Summary

### Secondary Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Secondary Energy\|Electricity` | Total generation |
| `Secondary Energy\|Electricity\|Coal` | Coal + Coal w/ CCS |
| `Secondary Energy\|Electricity\|Gas` | Gas CC + Gas CC w/ CCS |
| `Secondary Energy\|Electricity\|Oil` | Oil |
| `Secondary Energy\|Electricity\|Biomass` | Biomass + BECCS |
| `Secondary Energy\|Electricity\|Nuclear` | Nuclear |
| `Secondary Energy\|Electricity\|Hydro` | Hydro |
| `Secondary Energy\|Electricity\|Solar` | PV + CSP |
| `Secondary Energy\|Electricity\|Wind` | Onshore + Offshore |
| `Secondary Energy\|Electricity\|Geothermal` | Geothermal |
| `Secondary Energy\|Electricity\|Hydrogen` | Hydrogen + Ammonia |

### Capacity (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Capacity\|Electricity\|{source}` (GW) | From VintageStock |
| `Capacity Additions\|Electricity\|{source}` (GW/yr) | New investment |

### Prices (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Price\|Secondary Energy\|Electricity` | Share-weighted LCOE + T&D |

### Investment (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Investment\|Energy Supply\|Electricity\|{source}` | new_cap × capex |

### Emissions (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2\|Energy\|Supply\|Electricity` | Net (fossil emissions − BECCS CDR) |
| `Carbon Sequestration\|CCS\|Biomass` | BECCS CDR (negative emissions) |


## 11. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Technologies | 17 (single logit) | + Storage, flexible demand |
| CCS | 3 techs (Coal/Gas/Biomass w/ CCS), from 2030 | Same |
| Profit shutdown | S-curve on π | Same |
| Resource constraints | Static potential | Time-varying (Climate/AFOLU) |
| Efficiency | Fixed per tech | Climate-adjusted (temperature penalty) |
| Capacity factors | Static (gcamdata) | Climate-adjusted (CF multipliers) |
| Cooling water | Not modeled | Water module constraint |
| Cross-border trade | Not modeled | Interconnector flows |
| T&D | Fixed markup (15 $/MWh) | Detailed grid model |
| Storage | Not modeled | Battery + pumped hydro (dispatchable RE) |
| Demand response | Not modeled | Flexible load shifting |

### Phase transition notes

- **Phase 1 → 2**: Add storage technologies (battery, pumped hydro) that enable higher VRE penetration. CF and efficiency become time-varying via climate multipliers. Cross-border electricity trade via interconnector capacity constraints. T&D markup replaced by grid model. No structural change to logit or VintageStock — just more technologies and time-varying parameters.
- **Phase 2 → 3**: Hourly dispatch modeling (load duration curves or representative hours). Demand response (flexible EV charging, industrial demand shifting). Sub-regional grid congestion.
