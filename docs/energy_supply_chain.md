# Energy Supply Chain

The energy supply chain in GHIM follows a three-tier structure: **primary resources** are extracted and fed into **transformation sectors** (electricity, refining, hydrogen), which produce secondary energy carriers consumed by **final demand sectors** (industry, buildings, transport).

## Primary Energy Resources

Primary energy supply is modeled using **grade-based resource curves** for fossil fuels and fixed-cost supply for renewables.

### Fossil fuel supply curves

Each fossil resource (coal, gas, oil) has multiple extraction grades with increasing marginal cost. As cumulative extraction increases, the model moves to higher-cost grades, simulating resource depletion:

| Resource | Grade 1 (EJ, $/GJ) | Grade 2 (EJ, $/GJ) | Grade 3 (EJ, $/GJ) |
|----------|--------------------|--------------------|---------------------|
| Coal | 5,000 EJ @ $1.5 | 10,000 EJ @ $2.5 | 20,000 EJ @ $4.0 |
| Gas | 3,000 EJ @ $2.0 | 5,000 EJ @ $3.5 | 8,000 EJ @ $6.0 |
| Oil | 2,000 EJ @ $4.0 | 3,000 EJ @ $7.0 | 5,000 EJ @ $12.0 |

Once all grades are exhausted, a **scarcity premium** (2$\times$ highest grade cost) applies.

### Renewable resources

Renewable resources (wind, solar, hydro, geothermal) have effectively unlimited supply at zero fuel cost. Their cost is entirely captured through technology capital and O&M costs in the transformation sectors. Nuclear fuel is modeled at a fixed cost of $0.7/GJ.

**Implementation**: [`ghim/energy/supply.py`](../ghim/energy/supply.py) — classes `ResourceGrade`, `ResourceSupply`.

---

## Electricity Sector

The electricity sector is the most detailed transformation sector, with **8 competing generation technologies**:

### Technology parameters

| Technology | Fuel | Efficiency | Capital ($/kW) | CF | Lifetime | Carbon coef (tC/GJ) |
|-----------|------|-----------|---------------|-----|---------|---------------------|
| Coal | coal | 0.39 | 1,500 | 0.75 | 40 yr | 0.0257 |
| Gas CC | gas | 0.55 | 900 | 0.60 | 30 yr | 0.0153 |
| Nuclear | nuclear | 0.33 | 5,500 | 0.90 | 60 yr | 0 |
| Hydro | hydro | 1.00 | 2,500 | 0.45 | 80 yr | 0 |
| Wind | wind | 1.00 | 1,200 | 0.35 | 25 yr | 0 |
| Solar PV | solar | 1.00 | 900 | 0.22 | 30 yr | 0 |
| Biomass | biomass | 0.35 | 2,500 | 0.70 | 30 yr | 0 (biogenic) |
| Oil | refined liquids | 0.37 | 800 | 0.30 | 30 yr | 0.0200 |

Sources: NREL ATB 2023, IEA WEO 2023, GCAM defaults.

### Technology competition

Technologies compete for market share using the **relative cost logit** with $\beta = -4$:

$$
s_i = \frac{\alpha_i \cdot LCOE_i^{-4}}{\sum_j \alpha_j \cdot LCOE_j^{-4}}
$$

The logit exponent of $-4$ produces moderate cost sensitivity: cheaper technologies capture larger shares, but the model does not fully concentrate on a single technology, reflecting real-world market friction, policy preferences, and resource constraints.

### Preference factor logit

Technology competition now uses **MERGE-style preference factors** instead of GCAM share weights. The market share of technology $i$ is:

$$
s_i = \frac{\exp\bigl(-k \cdot (LCOE_i + P_i)\bigr)}{\sum_j \exp\bigl(-k \cdot (LCOE_j + P_j)\bigr)}
$$

where $k = 0.3$ is the logit slope and $P_i$ is a technology-specific preference factor. Preference factors encode non-cost advantages (policy support, reliability, public acceptance) that shift shares away from pure cost minimization.

Preference factors **decay at 2%/yr** toward zero, so that competition converges toward pure-cost outcomes over time:

$$
P_i(t) = P_i(0) \cdot (1 - 0.02)^{t - t_0}
$$

This ensures that near-term calibration fidelity is high while long-run projections are increasingly driven by economics.

### Stock turnover

Existing power plant fleet changes gradually with a characteristic turnover time of $\tau = 40$ years. In each model period the generation mix adjusts toward the target (logit-derived) shares, but only partially:

$$
s_i^{\text{new}} = s_i^{\text{old}} + \bigl(s_i^{\text{target}} - s_i^{\text{old}}\bigr) \cdot \frac{\Delta t}{\tau}
$$

This creates **inertia** — even if solar becomes the cheapest technology, coal capacity does not disappear overnight. The 40-year timescale is consistent with typical power plant economic lifetimes.

### Learning curves

Four technologies experience endogenous cost reductions as cumulative global deployment grows:

| Technology | Learning rate | Cost floor (% of initial) |
|-----------|--------------|--------------------------|
| Solar PV | 20% | 20% |
| Wind | 12% | 20% |
| Biomass | 5% | 20% |
| Nuclear | 3% | 20% |

The learning rate is the fractional cost reduction per doubling of cumulative capacity. For example, a 20% learning rate means that each time cumulative solar PV deployment doubles, capital cost falls by 20%. Costs are bounded below at 20% of the initial capital cost to prevent unrealistically low asymptotic values.

### Calibration

In the base year (2020), share weights $\alpha_i$ are calibrated to reproduce observed regional electricity generation mixes. For example:

| Region | Coal | Gas | Nuclear | Hydro | Wind | Solar |
|--------|------|-----|---------|-------|------|-------|
| Eastern Asia | 62% | 3% | 5% | 17% | 6% | 4% |
| North America | 20% | 40% | 20% | 7% | 8% | 3% |
| Latin America | 5% | 20% | 2% | 55% | 8% | 3% |
| Europe | 15% | 20% | 25% | 12% | 15% | 6% |

### Fuel consumption and emissions

Given generation $G_i$ (EJ) by technology $i$ with efficiency $\eta_i$:

- **Fuel input**: $F_i = G_i / \eta_i$ (EJ of primary fuel)
- **Emissions**: $E_i = c_i \cdot F_i \cdot 10^9 / 10^6$ (MtC), where $c_i$ is the carbon coefficient (tC/GJ)

**Implementation**: [`ghim/energy/electricity.py`](../ghim/energy/electricity.py) — class `ElectricitySector`.

---

## Oil Refining Sector

The refining sector converts crude oil to refined liquid fuels (gasoline, diesel, jet fuel, etc.) at a fixed efficiency.

| Parameter | Value |
|-----------|-------|
| Efficiency | 0.90 (output/input) |
| Capital cost | $500/kW |
| Capacity factor | 0.85 |
| Carbon coefficient | 0.0200 tC/GJ |

Refining is modeled as a single representative technology. The cost of refined liquids is the LCOE of the refining process, which includes crude oil cost (passed through at $1/\eta$), capital charges, and O&M.

**Implementation**: [`ghim/energy/refining.py`](../ghim/energy/refining.py) — class `RefiningSector`.

---

## Hydrogen Sector

Hydrogen production uses two competing technologies:

| Technology | Fuel Input | Efficiency | Capital ($/kW) | CF | Base Share |
|-----------|-----------|-----------|---------------|-----|-----------|
| SMR (Steam Methane Reforming) | gas | 0.72 | 600 | 0.90 | 95% |
| Electrolysis | electricity | 0.70 | 1,000 | 0.50 | 5% |

Competition uses the **preference factor logit** ($k = 0.3$) with the same formulation as the electricity sector. Preference factors decay at 2%/yr toward pure-cost competition.

### Stock turnover

Hydrogen production capacity turns over with $\tau = 25$ years — faster than electricity ($\tau = 40$) because hydrogen plants are smaller and have shorter economic lifetimes:

$$
s_i^{\text{new}} = s_i^{\text{old}} + \bigl(s_i^{\text{target}} - s_i^{\text{old}}\bigr) \cdot \frac{\Delta t}{\tau}
$$

### Electrolysis learning

Electrolysis capital cost declines with a **15% learning rate** (cost falls 15% per doubling of cumulative electrolyzer deployment), with a cost floor at 20% of initial capital cost. This allows green hydrogen to become cost-competitive with SMR as renewable electricity prices fall and electrolyzer deployment scales up.

**Implementation**: [`ghim/energy/hydrogen.py`](../ghim/energy/hydrogen.py) — class `HydrogenSector`.

---

## Final Energy Demand

Final demand is modeled as a **2-level nested demand tree** for each of the three sectors. Each node in the tree uses the preference-factor logit ($k = 0.3$, preference decay at 2%/yr) and stock turnover to determine shares.

### Nested demand tree

Each sector is split into subsectors (level 1), and each subsector allocates demand across energy carriers (level 2):

```
Industry
├── Heavy industry — 45%        [τ=30y]
│   └── coal / gas / electricity / refined liquids / biomass / hydrogen
├── Light manufacturing — 45%   [τ=30y]
│   └── electricity / gas / refined liquids / coal / biomass / hydrogen
└── Data centers / AI — 10%     [τ=7y]
    └── electricity (100%)

Buildings
├── Residential — 55%           [τ=50y]
│   └── electricity / gas / biomass / refined liquids / coal / hydrogen
└── Commercial — 45%            [τ=50y]
    └── electricity / gas / refined liquids / biomass / coal / hydrogen

Transport
├── Passenger — 60%             [τ=15y]
│   └── refined liquids / electricity / gas / hydrogen / biomass
└── Freight — 40%               [τ=15y]
    └── refined liquids / gas / electricity / hydrogen / biomass
```

**Data centers as a separate subsector** is justified by IEA WEO 2024 projections: data center energy demand is nearly 100% electricity, is growing rapidly due to AI workloads, and has short equipment turnover cycles (~7 years). Separating it from traditional industry prevents the model from under-projecting electricity demand growth in regions with large cloud/AI infrastructure.

Stock turnover at each tree level follows the same formulation as the supply sectors:

$$
s_i^{\text{new}} = s_i^{\text{old}} + \bigl(s_i^{\text{target}} - s_i^{\text{old}}\bigr) \cdot \frac{\Delta t}{\tau}
$$

The turnover time $\tau$ varies by subsector to reflect real-world capital stock lifetimes — buildings turn over slowly ($\tau = 50$y), while data center equipment refreshes quickly ($\tau = 7$y).

### Demand sectors and base-year energy

Regional base-year final energy demand (EJ) for selected regions:

| Region | Industry | Buildings | Transport | Total |
|--------|----------|-----------|-----------|-------|
| North America | 18.0 | 20.0 | 28.0 | 66.0 |
| Eastern Asia | 45.0 | 15.0 | 15.0 | 75.0 |
| Europe | 13.0 | 18.0 | 14.0 | 45.0 |
| Southern Asia | 12.0 | 8.0 | 5.0 | 25.0 |

### Demand growth

Total energy demand in each sector grows with GDP according to an income elasticity:

$$
D(t) = D_0 \cdot \left(\frac{GDP(t)}{GDP_0}\right)^{\epsilon}
$$

| Sector | Income elasticity $\epsilon$ |
|--------|------------------------------|
| Industry | 0.6 |
| Buildings | 0.5 |
| Transport | 0.7 |

Income elasticities less than 1 imply that energy demand grows slower than GDP — reflecting structural change and efficiency improvements in an economy. Transport has the highest elasticity, consistent with empirical evidence that transport demand is strongly income-driven.

**Implementation**: [`ghim/energy/demand.py`](../ghim/energy/demand.py) — classes `DemandNode`, `DemandLeaf`, `FinalDemand`.

---

## Emissions Accounting

CO$_2$ emissions are computed at the point of fossil fuel combustion using IPCC default carbon coefficients:

| Fuel | Carbon coefficient | CO$_2$ intensity |
|------|-------------------|-----------------|
| Coal | 0.0257 tC/GJ | 94.6 kgCO$_2$/GJ |
| Gas | 0.0153 tC/GJ | 56.1 kgCO$_2$/GJ |
| Refined liquids | 0.0200 tC/GJ | 73.3 kgCO$_2$/GJ |
| Biomass | 0 (biogenic) | 0 |
| Nuclear, renewables | 0 | 0 |

Emissions are summed across three sources:

1. **Electricity generation**: Fossil fuel burned in power plants.
2. **Transformation sectors**: Refining and hydrogen production.
3. **Direct combustion**: Fossil fuels burned directly in final demand sectors.

The conversion from tonnes of carbon (tC) to tonnes of CO$_2$ uses the molecular weight ratio: $1 \text{ tC} = \frac{44}{12} \text{ tCO}_2 \approx 3.667 \text{ tCO}_2$.
