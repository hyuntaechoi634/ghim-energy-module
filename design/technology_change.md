# GHIM Energy Module — Technology Change Design

## 1. Overview

Technology change drives cost decline in energy supply, demand, and transport technologies. Modeled via **two-factor learning curves**: Learning-by-Doing (LBD, from cumulative deployment) and Learning-by-Researching (RND, from R&D knowledge stock). Cross-technology spillovers allow related technologies to share learning.

Phase 1: global learning pool, exogenous R&D, cross-technology spillovers. Phase 2+: endogenous R&D via Energy Services Nest, partial regional spillovers, unified budget constraint.


## 2. Two-Factor Learning Curve

### 2.1 Core formula

$$capex_i(t) = capex_{i,0} \times \left(\frac{Q_i^{eff}(t)}{Q_{i,0}}\right)^{-\lambda_{LBD,i}} \times \left(\frac{H_i^{RD}(t)}{H_{i,0}}\right)^{-\lambda_{RND,i}}$$

subject to:

$$capex_i(t) \geq floor_i$$

| Symbol | Meaning |
|--------|---------|
| $capex_{i,0}$ | Initial capital cost ($/kW or $/vehicle) at base year |
| $Q_i^{eff}$ | Effective cumulative deployment (including spillovers, see §3) |
| $Q_{i,0}$ | Cumulative deployment at base year |
| $H_i^{RD}$ | R&D knowledge stock (see §4) |
| $H_{i,0}$ | Knowledge stock at base year |
| $\lambda_{LBD,i}$ | LBD exponent: $\lambda = -\ln(1 - LR) / \ln 2$ |
| $\lambda_{RND,i}$ | RND exponent (same formula with R&D learning rate) |
| $floor_i$ | Minimum cost floor |

### 2.2 Learning rate interpretation

Learning rate $LR$ = fractional cost reduction per doubling of cumulative deployment:

$$LR = 1 - 2^{-\lambda}$$

| $LR$ | $\lambda$ | Meaning |
|------|-----------|---------|
| 5% | 0.074 | Mature technology (nuclear, CCS) |
| 10% | 0.152 | Moderate learning (wind, batteries, heat pumps) |
| 15% | 0.234 | Fast learning (electrolysis, wind offshore) |
| 20% | 0.322 | Very fast learning (solar PV) |

### 2.3 Floor costs

Cost cannot decline below a physical/material floor:

$$floor_i = f_i \times capex_{i,0}$$

Default floor fraction: **$f = 0.20$** (20% of initial capex). Technology-specific overrides:

| Technology | Floor fraction $f_i$ | Rationale |
|-----------|---------------------|-----------|
| Solar PV | 0.15 | Glass, aluminum frame, silicon |
| Wind | 0.25 | Steel tower, concrete foundation |
| Battery (BEV) | 0.20 | Cathode materials, cell housing |
| Electrolysis | 0.20 | Membrane, balance of plant |
| Heat pumps | 0.25 | Compressor, heat exchanger |
| CCS | 0.30 | Capture equipment, compression |
| Nuclear | 0.50 | Safety systems, concrete, steel |
| H₂ DRI | 0.30 | Shaft furnace, reductant handling |

### 2.4 RND learning rates (Option B: WITCH values, exogenous RND trajectory)

RND exponents $\beta_{RND}$ from WITCH two-factor calibration:

| Technology | $\beta_{RND}$ | Source |
|-----------|---------------|--------|
| Solar PV | 0.15 | WITCH |
| Wind | 0.10 | WITCH |
| Nuclear | 0.08 | WITCH |
| Electrolysis | 0.12 | WITCH |
| CCS | 0.10 | WITCH |
| Batteries | 0.12 | WITCH |

When RND is active, LBD exponents ($\alpha_{LBD}$) must be adjusted downward to avoid double-counting the portion of observed learning historically driven by R&D:

| Technology | $\alpha_{LBD}$ (LBD-only) | $\alpha_{LBD}$ (with RND) |
|-----------|--------------------------|--------------------------|
| Solar PV | 0.20 | 0.12 |
| Wind | 0.12 | 0.08 |
| Nuclear | 0.03 | 0.03 (unchanged) |
| Electrolysis | 0.15 | 0.10 |
| CCS | 0.05 | 0.03 |
| Batteries | 0.10 | 0.06 |

RND knowledge stock:

$$H_i(t) = \sum_{\tau \leq t} (1 - \delta_H)^{t - \tau} \times RND_{i,\tau}$$

where $\delta_H = 0.10$ (10% per 5-year period, ~2%/yr depreciation).

Phase 1: exogenous RND trajectories from IEA Energy Technology RD&D Budgets. Phase 2+: endogenous RND optimization.


## 3. Spillover Effects

### 3.1 Cross-regional spillovers

**Phase 1: Global learning pool.** Cumulative deployment is summed across all regions:

$$Q_i^{cum}(t) = \sum_r Q_{i,r}^{cum}(t)$$

All regions see the same cost. Justified for manufactured technologies — solar panels, batteries, and electrolyzers are globally traded goods. Manufacturing learning is not region-specific.

**Phase 2+: Partial regional spillover.** Split capex into global component (hardware) and local component (soft costs):

$$capex_i = capex_i^{global}(Q_i^{cum,global}) + capex_i^{local}(Q_{i,r}^{cum,local})$$

| Component | Share of capex | Spillover | Examples |
|-----------|---------------|-----------|----------|
| Hardware (global) | 50–70% | $\sigma = 1.0$ | Modules, turbines, cells |
| Soft costs (local) | 30–50% | $\sigma = 0.1$–$0.3$ | Permitting, labor, installation |

### 3.2 Cross-technology spillovers

Related technologies share knowledge. Effective cumulative deployment includes spillovers from related technologies:

$$Q_i^{eff}(t) = Q_i^{cum}(t) + \sum_{j \neq i} \phi_{ij} \times Q_j^{cum}(t)$$

where $\phi_{ij} \in [0, 1]$ is the spillover coefficient from technology $j$ to technology $i$.

### 3.3 Technology families and spillover matrix

Technologies are grouped into families that share knowledge. Spillovers are non-zero only within families (sparse matrix).

```
Solar Family
├── Solar PV       ←→  Solar CSP              φ = 0.2

Wind Family
├── Wind Onshore   ←→  Wind Offshore          φ = 0.5

CCS Family
├── Coal CCS       ←→  Gas CCS                φ = 0.8
├── Coal CCS       ←→  Biomass CCS            φ = 0.8
├── Gas CCS        ←→  Biomass CCS            φ = 0.8
├── H₂ Coal CCS    ←→  H₂ Gas CCS (SMR)      φ = 0.6
├── Elec CCS       ←→  H₂ CCS                φ = 0.5

Electrochemical Family
├── Electrolysis   ←→  FCEV fuel cell          φ = 0.3

Battery Family
├── BEV battery    ←→  Grid storage (Phase 2+) φ = 0.7
```

### 3.4 Spillover matrix (Phase 1)

| From ↓ \ To → | PV | CSP | On | Off | Coal CCS | Gas CCS | Bio CCS | Elys | FCEV FC | BEV Bat |
|---|----|-----|----|----|----------|---------|---------|------|---------|---------|
| Solar PV | — | 0.2 | | | | | | | | |
| Solar CSP | 0.2 | — | | | | | | | | |
| Wind Onshore | | | — | 0.5 | | | | | | |
| Wind Offshore | | | 0.5 | — | | | | | | |
| Coal CCS | | | | | — | 0.8 | 0.8 | | | |
| Gas CCS | | | | | 0.8 | — | 0.8 | | | |
| Biomass CCS | | | | | 0.8 | 0.8 | — | | | |
| Electrolysis | | | | | | | | — | 0.3 | |
| FCEV fuel cell | | | | | | | | 0.3 | — | |
| BEV battery | | | | | | | | | | — |

All unlisted entries are 0 (no cross-family spillover).

### 3.5 Example

Suppose at period $t$:
- Wind Onshore cumulative: 800 GW
- Wind Offshore cumulative: 100 GW

Effective experience:
- Wind Onshore: $800 + 0.5 \times 100 = 850$ GW
- Wind Offshore: $100 + 0.5 \times 800 = 500$ GW

Wind Offshore benefits significantly from Onshore's larger deployment base. This is realistic — offshore turbine design, materials, and manufacturing techniques derive heavily from onshore experience.


## 4. R&D Knowledge Stock

### 4.1 Knowledge accumulation

$$H_i(t+1) = (1 - \delta_H) \times H_i(t) + RD_i(t)$$

| Parameter | Meaning | Phase 1 |
|-----------|---------|---------|
| $H_i(t)$ | Knowledge stock for technology $i$ | Calibrated from cumulative R&D |
| $\delta_H$ | Knowledge depreciation rate | 10% per 5-year period (~2%/yr) |
| $RD_i(t)$ | R&D investment (billion $/period) | Exogenous trajectory |

Knowledge depreciates because older research becomes obsolete. 10% per period (~2%/year) is consistent with the WITCH two-factor calibration (see §2.4).

### 4.2 Phase 1: Exogenous R&D

R&D trajectories are read from data, not optimized:

$$RD_i(t) = RD_{i,base} \times g_i(t)$$

where $g_i(t)$ is a growth path from IEA Energy Technology RD&D Statistics or SSP technology assumptions.

| Technology group | Base R&D (bn$/yr) | Growth assumption | Source |
|-----------------|-------------------|-------------------|--------|
| Solar | ~3–5 | SSP-dependent | IEA RD&D |
| Wind | ~2–3 | SSP-dependent | IEA RD&D |
| Nuclear | ~10–15 | Flat/declining | IEA RD&D |
| CCS | ~1–3 | Growing (net-zero scenarios) | IEA RD&D |
| Hydrogen/electrolysis | ~1–2 | Fast growth | IEA RD&D |
| Batteries/EV | ~5–8 | Fast growth | IEA RD&D |
| Heat pumps | ~1–2 | Growing | IEA RD&D |

### 4.3 Phase 2+: Endogenous R&D and Energy Services Nest

In Phase 2, R&D connects to the macro economy via the **Energy Services Nest** — an additional CES level in the production function:

$$ES = CES(H^{RD}, E; \; \sigma_{ES} > 1)$$

where:
- $E$: physical energy input (EJ × base price = billion USD)
- $H^{RD}$: aggregate R&D knowledge stock (R&D-driven efficiency)
- $\sigma_{ES} > 1$: $H^{RD}$ substitutes for $E$

**Interpretation**: Same energy services, less physical energy → endogenous energy efficiency improvement (AEEI).

#### Aggregate R&D investment

$$I_{RD}^{agg} = s_{RD} \cdot Y \quad \text{(GDP fraction)}$$

$$I_{RD} \rightarrow H^{RD} \uparrow \quad \text{(knowledge stock accumulates)}$$

#### Unified Budget Constraint

$$s \cdot Y = I_K + I_{RD}^{agg} + \sum_j I_{RD,j}$$

- More R&D → less $K$ investment short-term
- But $H^{RD} \uparrow$ → $E \downarrow$ long-term (energy savings)
- Trade-off: physical capital vs knowledge capital

This budget constraint ensures R&D competes with physical investment for the same savings pool, preventing unrealistic simultaneous scaling of both.


## 5. Technologies with Learning

### 5.1 Electricity generation

| Technology | $\alpha_{LBD}$ | $\beta_{RND}$ | $Q_0$ (GW) | Floor |
|-----------|---------------|--------------|------------|-------|
| Solar PV | 0.12 (20%→12%) | 0.15 | ~710 | 15% |
| Solar CSP | 15% | — | ~6 | 20% |
| Wind Onshore | 0.08 (12%→8%) | 0.10 | ~740 | 25% |
| Wind Offshore | 15% | — | ~35 | 25% |
| Nuclear | 0.03 | 0.08 | ~440 | 50% |
| Coal CCS | 0.03 (5%→3%) | 0.10 | ~0.3 | 30% |
| Gas CCS | 0.03 (5%→3%) | 0.10 | ~0.1 | 30% |
| Biomass CCS | 0.03 (5%→3%) | 0.10 | ~0.1 | 30% |
| Coal | 1% | — | Mature | 80% |
| Gas CC | 1% | — | Mature | 80% |
| Hydro | 0% | — | Mature | — |
| Geothermal | 5% | — | ~15 | 40% |
| Ocean | 10% | — | ~0.5 | 30% |

Mature technologies (Coal, Gas CC, Hydro, Oil) have negligible learning — cost is already near floor.

### 5.2 Hydrogen production (7 techs)

| Technology | LBD Rate | Spillover from |
|-----------|---------|----------------|
| Electrolysis | 15% | FCEV fuel cell (φ=0.3) |
| SMR | 1% | Mature |
| SMR CCS | 5% | CCS family |
| Coal Gasification | 1% | Mature |
| Coal Gasification CCS | 5% | CCS family |
| Biomass Gasification | 8% | — |
| Biomass Gasification CCS | 5% | CCS family |

### 5.3 Transport powertrains

| Powertrain | Learning component | LBD Rate | Spillover from |
|-----------|-------------------|---------|----------------|
| BEV | Battery pack | 10% | Grid storage (Phase 2+) |
| FCEV | Fuel cell stack | 15% | Electrolysis (φ=0.3) |
| HEV | Battery (smaller) | 10% | BEV battery (φ=0.5) |
| ICE / Diesel | — | Mature | — |
| NG | — | Mature | — |

BEV learning is driven by battery cost reduction (~40% of vehicle cost). At 10% learning rate, cost halves per ~7× cumulative production.

### 5.4 Biofuels (3 techs)

| Technology | LBD Rate | Notes |
|-----------|---------|-------|
| Biodiesel (1st gen) | 3% | Mature process |
| Cellulosic Ethanol (2nd gen) | 10% | Still scaling up |
| Biomass-to-Liquids (BTL) | 8% | Pre-commercial |

### 5.5 Buildings

| Technology | Learning component | LBD Rate | RND Channel |
|-----------|-------------------|---------|-------------|
| Heat pumps | Compressor + system | 10% | Medium |

Heat pump learning reduces capex → lowers service cost → higher logit share for electrification in heating. This is a key mechanism for buildings decarbonization.

### 5.6 Industry

| Technology | Learning component | LBD Rate | RND Channel |
|-----------|-------------------|---------|-------------|
| H₂ DRI | Shaft furnace + H₂ reduction | 8% | Medium |

Hydrogen-based direct reduced iron (H₂ DRI) replaces coal-based blast furnace steelmaking. Learning from cumulative H₂ DRI deployment reduces capex and improves the economics of green steel.


## 6. Cumulative Deployment Tracking

### 6.1 Update rule

$$Q_i^{cum}(t+1) = Q_i^{cum}(t) + new\_capacity_i(t) \times \Delta t$$

For electricity and hydrogen: new capacity from VintageStock gap-filling.
For transport: new vehicle sales × capacity per vehicle.
For buildings (heat pumps): new installations from vintage gap-filling.
For industry (H₂ DRI): new capacity from vintage gap-filling.

### 6.2 Global vs regional

Phase 1: single global $Q_i^{cum}$ (sum across all regions).

```python
# In solver, after each period:
for tech in LEARNING_TECHS:
    global_new = sum(new_capacity[tech][r] for r in regions)
    Q_cum[tech] += global_new * timestep
```

### 6.3 Effective cumulative with spillovers

```python
# Before computing capex for period t:
for tech in LEARNING_TECHS:
    Q_eff[tech] = Q_cum[tech]
    for other, phi in SPILLOVER_MATRIX[tech].items():
        Q_eff[tech] += phi * Q_cum[other]
    capex[tech] = capex_0[tech] * (Q_eff[tech] / Q_0[tech]) ** (-lambda_lbd[tech])
                                * (H_rd[tech]  / H_0[tech])  ** (-lambda_lbr[tech])
    capex[tech] = max(capex[tech], floor[tech])
```


## 7. Connection to Model Components

### 7.1 Electricity sector

Learning curves update capex before LCOE calculation each period:

$$LCOE_i = \frac{capex_i(t) \times FCR}{CF_i \times 8760} + \frac{fuel_i}{eff_i} + \frac{coef_i \times P_{carbon}}{eff_i} + FOM_i + VOM_i$$

Lower capex → lower LCOE → higher logit share → more deployment → lower capex (positive feedback).

### 7.2 Transport powertrains

Learning curves update vehicle capex before LCOT calculation:

$$LCOT_i = \frac{capex_i(t) \times FCR}{annual\_SD_i} + \frac{C_{fuel,i}}{eff_i} + O\&M_i + \frac{VOT_i}{speed_i}$$

BEV battery learning → lower BEV capex → lower LCOT → higher BEV share → more battery production → lower battery cost.

### 7.3 Hydrogen production

Electrolysis capex declines via learning → green hydrogen becomes cheaper → higher electrolysis share → displaces SMR.

### 7.4 Buildings (Heat pumps)

Heat pump learning → lower equipment cost → lower service cost → higher electricity share in heating → displaces gas boilers.

### 7.5 Industry (H₂ DRI)

H₂ DRI learning → lower capex → lower cost of green steel → higher hydrogen share in industry feedstocks → displaces coal-based blast furnaces.

### 7.6 Budget constraint

Learning-driven cost decline reduces energy investment requirements:

$$I_{energy}(t) = \sum_i new\_capacity_i(t) \times capex_i(t)$$

Lower capex means the same deployment costs less → more capital available for general K accumulation → less macro drag from energy transition.


## 8. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| LBD learning rate per technology | §5 tables | Per-technology |
| RND learning rate $\beta_{RND}$ per technology | §2.4 table (WITCH values) | Per-technology |
| Floor fraction $f_i$ | 0.20 default, tech-specific overrides | Per-technology |
| Spillover matrix $\phi_{ij}$ | §3.4 | Per-technology-pair |
| Knowledge depreciation $\delta_H$ | 10% per period | Global |
| R&D trajectories $RD_i(t)$ | IEA RD&D | Per-technology, per-period |
| Initial cumulative deployment $Q_{i,0}$ | §5 tables | Per-technology |
| Initial capex $capex_{i,0}$ | Calibration data | Per-technology |

Three-level parameter specification applies: global scalar → regional → regional × temporal.
Note: In Phase 1 (global learning pool), regional overrides are not needed for learning rates. Regional differentiation matters only in Phase 2+ when soft-cost learning is separated.


## 9. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Cumulative deployment by technology | IRENA, IEA, GEM | Global | For $Q_{i,0}$ |
| Technology capex ($/kW, $/vehicle) | IRENA, NREL ATB, IEA WEO | Global | For $capex_{i,0}$ |
| Historical learning rates | Literature meta-analyses | Per-technology | For $\lambda_{LBD}$ validation |
| R&D spending by technology | IEA Energy Technology RD&D | Country → global | For $H_{i,0}$ and $RD_{i,base}$ |
| Spillover coefficients | Literature (Söderholm & Klaassen) | Per-family | For $\phi_{ij}$ |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| R&D growth paths $g_i(t)$ | IEA ETP, SSP technology assumptions | Per-technology |
| New capacity deployment | VintageStock (endogenous) | Updates $Q_i^{cum}$ each period |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| Soft cost breakdown | NREL, IRENA | For global/local capex split |
| R&D productivity estimates | Endogenous growth literature | For Energy Services Nest calibration |
| Patent data | OECD REGPAT | For knowledge stock validation |


## 10. IAMC Reporting Summary

| Variable | How reported |
|----------|-------------|
| `Capital Cost\|Electricity\|{source}` ($/kW) | $capex_i(t)$ after learning |
| `Capital Cost\|Hydrogen\|{source}` ($/kW) | $capex_i(t)$ after learning |
| `Capital Cost\|Transport\|{powertrain}` ($/vehicle) | $capex_i(t)$ after learning |
| `Cumulative Capacity\|Electricity\|{source}` (GW) | $Q_i^{cum}(t)$ |
| `Investment\|Energy Supply\|Electricity\|{source}` | $new\_cap \times capex$ |
| `Investment\|R&D\|Energy` | $\sum_i RD_i(t)$ |


## 11. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| LBD | Global cumulative, all learning techs | + Regional soft-cost learning |
| RND | Exogenous R&D trajectories (IEA RD&D), WITCH $\beta_{RND}$ values | Endogenous R&D (Energy Services Nest) |
| Cross-tech spillovers | Spillover matrix (§3.4) | + R&D spillover matrix |
| Regional spillovers | Global pool ($\sigma = 1$) | Partial ($\sigma < 1$ for soft costs) |
| Floor costs | 20% default + tech-specific overrides | + Material cost floor model |
| Knowledge depreciation | 10% per period ($\delta_H = 0.10$) | Same or calibrated |
| Budget constraint | R&D exogenous (no competition with K) | Unified: $s \cdot Y = I_K + I_{RD}$ |
| Energy Services Nest | Not active ($E = ES$) | $ES = CES(H^{RD}, E; \sigma_{ES} > 1)$ |
| Heat pump learning | 10% LBD | Same + soft-cost regional |
| H₂ DRI learning | 8% LBD | Same |
| Path dependence | Implicit (LBD is path-dependent) | + Lock-in modeling |
| Deployment tracking | From VintageStock + vehicle sales | Same |

### Phase transition notes

- **Phase 1 → 2**: Activate Energy Services Nest: insert $H^{RD}$ node between KL and E in CES tree. R&D becomes endogenous via unified budget constraint ($s \cdot Y = I_K + I_{RD}^{agg} + \sum_j I_{RD,j}$). Split capex into global hardware and local soft costs. No structural code change for LBD — just add soft-cost component and regional tracking.
- **Phase 2 → 3**: Endogenous R&D allocation (optimization over technology-specific R&D). Patent-based knowledge stock validation. Lock-in modeling (path dependence creates technology winners that crowd out alternatives).
