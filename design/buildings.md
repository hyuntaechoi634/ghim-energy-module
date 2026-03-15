# GHIM Energy Module — Buildings Sector Design

## 1. Scope

Buildings is a **final energy demand sector** covering Residential and Commercial subsectors. Energy demand is driven by floorspace (population × per-capita floorspace saturation), service intensity (climate × shell × affordability), and carrier choice via logit.

Phase 1 covers Residential and Commercial with three end-uses each (Heating, Cooling, Other), 8 energy carriers, and the full floorspace + service intensity model (with constant climate and shell parameters). Phase 2+ adds time-varying climate feedback (HDD/CDD), improving shell conductance, and technology efficiency curves.


## 2. Sector Structure

```
Buildings
├── Residential
│   ├── Heating                    × 8 carriers (logit)
│   ├── Cooling                    × 8 carriers (logit)
│   └── Other                      × 8 carriers (logit)
└── Commercial
    ├── Heating                    × 8 carriers (logit)
    ├── Cooling                    × 8 carriers (logit)
    └── Other                      × 8 carriers (logit)
```

### End-Use Services

| Service | What it covers | Key carriers |
|---------|---------------|-------------|
| Heating | Space heating, water heating | Gas (incumbent), electricity (heat pumps), biomass, hydrogen, heat (district), coal |
| Cooling | Space cooling, refrigeration | Electricity (dominant, ~95%+) |
| Other | Cooking, lighting, appliances, electronics | Electricity (growing), gas, biomass (traditional) |

### Carrier Table (8)

| Carrier | Heating | Cooling | Other |
|---------|---------|---------|-------|
| Electricity | Heat pumps | AC, refrigeration | Appliances, lighting |
| Gas | Boilers, water heaters | — | Cooking |
| Coal | Stoves (declining) | — | — |
| Refined Oil | Oil boilers | — | Generators |
| Solid Biomass | Traditional/modern stoves | — | Traditional cooking |
| Biofuels | Biofuel boilers | — | — |
| Hydrogen | Hydrogen boilers (emerging) | — | — |
| Heat | District heating | District cooling | — |

Carriers with "—" have $\alpha_c = 0$ for that end-use (blocked by availability switch). Heat (district heating/cooling) connects to the District Heating transformation sector.

End-use services are **independent** — they do not compete with each other via logit. Each service has its own demand determined by floorspace and climate; carriers compete only within each service.


## 3. Service Demand

The demand chain has four steps:

```
Step 1: Per-capita floorspace  FS_pc(y_pc)           — saturation with income
Step 2: Total floorspace       FS = FS_pc × Pop
Step 3: Service intensity      I_svc(DD, U, y/P)     — per m², thermal + non-thermal
Step 4: Energy demand          E = FS × I_svc × Σ(s_c / eff_c)
```

### 3.1 Per-capita floorspace (Step 1)

Floorspace per capita saturates with income — rich countries plateau:

$$FS_{pc}(t) = \bigl(\bar{F} - F_{min}\bigr) \left(1 - \exp\!\left(-\frac{\ln 2}{\hat{y}}\; y_{pc}(t) \left(\frac{P_h(t)}{P_{h,0}}\right)^{\!\beta_h}\right)\right) + F_{min}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $\bar{F}$ | Satiation level (m²/cap) | Regional (US ~75, EU ~45, India ~20) |
| $\hat{y}$ | Midpoint income at 50% of $\bar{F}$ ($/cap) | Regional |
| $F_{min}$ | Subsistence floor (m²/cap) | **5.0** |
| $P_h / P_{h,0}$ | Housing price index (relative to base year) | 1.0 (constant in Phase 1) |
| $\beta_h$ | Price elasticity of floorspace | **−0.3** |

- Floor constraint: $FS_{pc}(t) \geq FS_{pc,base}$ (no shrinkage — buildings don't disappear)
- The saturation curve captures that rich countries add floorspace slowly while developing countries grow fast
- $P_h$ is exogenous in Phase 1 (constant). Phase 3+ could endogenize via construction costs

### 3.2 Total floorspace (Step 2)

$$FS_{sub}(t) = FS_{pc,sub}(t) \times Pop(t)$$

Separate saturation parameters for Residential and Commercial. Commercial floorspace per capita is typically 30–50% of residential.

### 3.3 Service intensity per m² (Step 3)

**Thermal services** (Heating, Cooling):

$$I_{svc}(t) = DD_{svc}(t) \cdot U(t) \times d_{svc}\!\left(\frac{y_{pc}(t)}{P_{svc}(t)}\right)$$

| Term | Meaning | Phase 1 |
|------|---------|---------|
| $DD_{svc}$ | Degree days (HDD for heating, CDD for cooling) | Constant at base year |
| $U$ | Shell conductance (W/m²·K → GJ conversion) | Constant at base year |
| $d_{svc}$ | Service density — saturation function of affordability | Active |

**Non-thermal services** (Other: lighting, cooking, appliances):

$$I_{other}(t) = d_{other}\!\left(\frac{y_{pc}(t)}{P_{other}(t)}\right)$$

No degree-day or shell term — demand driven purely by income and service price.

### Service density $d_{svc}$

The service density is a saturation function of affordability ($y_{pc} / P_{svc}$):

$$d_{svc}(x) = \bar{d}_{svc} \left(1 - \exp\!\left(-\frac{\ln 2}{\hat{x}_{svc}} \cdot x \right)\right)$$

| Parameter | Meaning |
|-----------|---------|
| $\bar{d}_{svc}$ | Satiation level (max service per m²) |
| $\hat{x}_{svc}$ | Midpoint affordability (at 50% satiation) |
| $x = y_{pc} / P_{svc}$ | Affordability: higher income or lower price → more service |

This captures the key economic intuition: as people get richer or energy gets cheaper, they consume more heating/cooling/appliance services — but with diminishing returns (you can only heat a room to ~22°C).

### 3.4 Carrier allocation within each end-use (logit)

For each end-use service $svc$, carriers compete via preference-factor logit:

$$s_{c}^{svc} = \frac{\alpha_c \cdot \exp\!\bigl(\beta \cdot (C_c + p_c)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (C_j + p_j)\bigr)}$$

| Parameter | Meaning |
|-----------|---------|
| $\alpha_c$ | Technology availability {0, 1} (policy override) |
| $\beta < 0$ | Cost sensitivity parameter |
| $C_c$ | Carrier price ($/GJ, from energy module) |
| $p_c$ | Preference factor ($/GJ, calibrated at base year, decays over time) |

Stock turnover constrains the speed of carrier switching. Equipment lifetime ~15–25 years (boilers, heat pumps, AC units). Note: stock turnover operates at the **carrier level** within each end-use — the heating/cooling/other split itself is structurally determined by climate and income, not by vintage-tracked choice.

### 3.5 Energy demand per end-use (Step 4)

Each carrier has a service-to-energy efficiency $eff_c^{svc}$:

$$E_{sub,svc}(t) = FS_{sub}(t) \times I_{svc}(t) \times \sum_c \frac{s_c^{svc}(t)}{eff_c^{svc}}$$

### Carrier efficiencies

| Carrier | Heating | Cooling | Other |
|---------|---------|---------|-------|
| Electricity | 2.5–4.0 (heat pump COP) | 2.5–4.0 (AC COP) | ~1.0 |
| Gas | 0.80–0.95 (condensing boiler) | — | 0.60 (cooking) |
| Coal | 0.60–0.70 | — | — |
| Refined Oil | 0.80–0.85 | — | — |
| Solid Biomass | 0.15–0.70 (traditional–modern) | — | 0.15–0.30 (traditional) |
| Biofuels | 0.80–0.85 | — | — |
| Hydrogen | 0.85–0.90 | — | — |
| Heat | 0.95 (district) | 0.80 (district) | — |

All efficiencies **fixed** in Phase 1. Same rationale as Industry: no exogenous AEEI. Efficiency improvement comes only from **carrier switching** via logit (e.g., gas boiler → heat pump). Phase 2 adds technology learning curves for efficiencies.

Heat pump COP > 1 means electricity delivers more service per GJ than combustion. Switching from gas (eff ≈ 0.9) to heat pump (eff ≈ 3.0) reduces energy consumption by ~3×. This is the key mechanism for buildings electrification.

### 3.6 Service price

The service price $P_{svc}$ is the **cost per unit of service delivered** ($/GJ-service):

$$P_{svc} = \sum_c s_c^{svc} \times \frac{C_c}{eff_c^{svc}}$$

This feeds back into:
1. Service density $d_{svc}$ via affordability $y_{pc} / P_{svc}$ — higher service price → less service demand
2. Per-capita service demand level — affordability saturation

A heat pump at $C_{elec}$ = 25 $/GJ with COP = 3.0 has service price 8.3 $/GJ-service. A gas boiler at $C_{gas}$ = 12 $/GJ with eff = 0.9 has service price 13.3 $/GJ-service. Heat pumps are cheaper **per unit of heating** even when electricity costs more than gas.

### 3.7 Total buildings energy demand

$$E_{bld}(t) = \sum_{sub} \sum_{svc} E_{sub,svc}(t)$$

### 3.8 Reconciliation with macro CES

Same as Industry. The macro CES determines total energy $E_{CES}$. Buildings' share comes from its demand relative to other sectors:

$$E_{bld}^{actual} = E_{bld}^{raw} \times \frac{E_{CES}}{\sum_{sectors} E_{sector}^{raw}}$$


## 4. Emissions

Same framework as Industry.

### Principle

- Direct combustion of coal, gas at demand site → demand-side emissions
- Electricity, hydrogen, heat, refined liquids → supply-side emissions
- Biomass → carbon-neutral

### Carbon coefficients

| Carrier | Coef (tC/GJ) | Demand-side CO₂? |
|---------|-------------|-------------------|
| Coal | 0.0257 | Yes |
| Gas | 0.0153 | Yes |
| Refined Oil | 0.0 | No (counted at refining) |
| Solid Biomass | 0.0 | No (biogenic) |
| Biofuels | 0.0 | No (biogenic) |
| Electricity | 0.0 | No (counted at generation) |
| Hydrogen | 0.0 | No (counted at production) |
| Heat | 0.0 | No (counted at district heating plant) |

### Buildings emissions calculation

$$CO2_{bld} = \sum_{sub} \sum_{svc} \sum_{c \in \{coal, gas\}} E_{sub,svc,c} \times coef_c \times \frac{44}{12}$$


## 5. Calibration

### Per-capita floorspace

From UN-Habitat, national housing surveys, or IEA Buildings dataset:
- $FS_{pc,base}$ observed → pin the saturation curve at base year
- $\bar{F}$ from cross-country regression (satiation ~60–80 m²/cap for residential)
- $\hat{y}$ from regression midpoint

### Service intensity

From base-year IEA energy balances + efficiency assumptions:

$$I_{svc,base} = \frac{\sum_c E_{sub,svc,c,base} \times eff_c^{svc}}{FS_{sub,base}}$$

This converts energy (GJ) to service (GJ-service) using assumed efficiencies, then normalizes by floorspace.

### Logit preference factors

For each end-use, calibrated by inverting the logit at base year (same as Industry):

$$p_c = \frac{1}{\beta} \cdot \ln\!\left(\frac{S_c}{S_r}\right) - (C_c - C_r)$$

### Elasticities / parameters

| Parameter | Phase 1 default | Range | References |
|-----------|-----------------|-------|------------|
| $\alpha_{res}$ (income elast. floorspace) | implicit in saturation curve | — | Saturation function replaces constant elasticity |
| $\beta_h$ (price elast. floorspace) | **−0.3** | −0.1 to −0.5 | GCAM, REMIND |
| $\beta$ (logit cost sensitivity) | **−4.0** | — | GHIM default |

The floorspace saturation function replaces the traditional constant income elasticity — it naturally produces high elasticity at low income and low elasticity at high income.


## 6. User Configurables

Parameters the user can override without code changes:

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| $\bar{F}$ (satiation floorspace) | Regional | Per-region |
| $\hat{y}$ (midpoint income) | Regional | Per-region |
| $F_{min}$ (subsistence floor) | 5.0 | Global / regional |
| $\beta_h$ (floorspace price elast.) | −0.3 | Global / regional |
| $\bar{d}_{svc}$ (service density satiation) | Regional | Per-region, per-service |
| HDD, CDD | Base-year constant | Per-region (Phase 2: time-varying) |
| U (shell conductance) | Base-year constant | Per-region (Phase 2: time-varying) |
| Carrier set | 8 carriers | Add/remove via config |
| $\alpha_c$ (availability) | 1 for all | Per-carrier, per-period (policy JSON) |
| $P_c$ decay rate | Per-carrier default | Per-carrier override (policy JSON) |
| $eff_c^{svc}$ (efficiency) | Fixed per carrier | Per-carrier, per-service |
| Stock turnover lifetime | 15–25 yr per carrier | Per-carrier override |
| Logit parameter ($\beta$) | Global default | Sector override |

Three-level parameter specification applies: global scalar → regional → regional × temporal.


## 7. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Buildings FE by carrier and end-use | IEA WEB via gcamdata | R32 | `L1xx` energy balance chunks |
| Per-capita floorspace | UN-Habitat, national surveys | R32 | For saturation curve calibration |
| HDD, CDD | ERA5 / NOAA | R32 | Base-year climate normals |
| Carrier prices | IEA, NREL ATB | R32 | For logit calibration |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| GDP(t) | SSP database | Drives floorspace saturation and service density |
| Pop(t) | SSP database | Drives total floorspace |
| Carrier prices(t) | Energy module | Endogenous within solver loop |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| HDD/CDD projections | Climate module or CMIP6 | Time-varying degree days |
| Shell conductance trajectories | Building codes, IEA | U(t) improvement curves |
| Technology efficiency curves | NREL ATB, IEA | COP improvement for heat pumps, etc. |


## 8. IAMC Reporting Summary

### Final Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Residential and Commercial` | $E_{bld}$ |
| `Final Energy\|Residential and Commercial\|Electricity` | Electricity carrier total |
| `Final Energy\|Residential and Commercial\|Liquids` | Refined Oil + Biofuels |
| `Final Energy\|Residential and Commercial\|Solids` | Coal + Solid Biomass |
| `Final Energy\|Residential and Commercial\|Gases` | Gas total |
| `Final Energy\|Residential and Commercial\|Hydrogen` | Hydrogen total |
| `Final Energy\|Residential and Commercial\|Heat` | District heat total |

### Final Energy (Tier-2)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Residential\|{carrier}` | Residential subsector by carrier |
| `Final Energy\|Commercial\|{carrier}` | Commercial subsector by carrier |

### Final Energy (Tier-3)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Residential\|Heating\|{carrier}` | Direct from end-use node |
| `Final Energy\|Residential\|Cooling\|{carrier}` | Direct from end-use node |
| `Final Energy\|Commercial\|Heating\|{carrier}` | Direct from end-use node |

### Emissions (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2\|Energy\|Demand` | Includes buildings direct combustion |
| `Emissions\|CO2\|Energy\|Demand\|Residential and Commercial` | $CO2_{bld}$ (Tier-2) |


## 9. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Subsectors | Residential + Commercial | Same |
| End-uses | Heating, Cooling, Other | + Water heating, Lighting, Appliances split |
| Demand driver | Floorspace saturation × service intensity | Same |
| HDD/CDD | Constant (base year) | Time-varying (climate module feedback) |
| Shell conductance $U$ | Constant (base year) | Time-varying (building code improvement) |
| Service density $d_{svc}$ | Saturation function | Same |
| Carrier efficiencies | Fixed per carrier | Technology learning curves |
| Housing price $P_h$ | Constant (1.0) | Endogenous (construction costs) |
| Traditional biomass | Included in biomass carrier | Separate tracking (SSP-driven decline) |
| Carriers | 8 (incl. district heat) | Same |

### Phase transition notes

- **Phase 1 → 2**: Climate module provides time-varying HDD/CDD → heating demand declines, cooling demand rises with warming. Shell conductance $U(t)$ decreases over time (better insulation via building codes). Carrier efficiencies improve via technology curves. No structural code change — same equations, just time-varying inputs replacing constants.
- **Phase 2 → 3**: End-use disaggregation (water heating separated from space heating, lighting from appliances). Building shell modeled as explicit vintage stock (new builds vs. retrofits). Housing price endogenized.
