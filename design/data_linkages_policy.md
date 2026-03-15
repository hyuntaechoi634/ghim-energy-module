# GHIM Energy Module — Data Pipeline, Module Linkages & Policy

## 1. Overview

External inputs enter the Energy module through three mechanisms that form a continuum:

```
                 gcamdata (R, land, water, energy)
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ Data Pipeline│ │ Module       │ │ Policy       │
  │ (pre-run)    │ │ Linkage      │ │ Framework    │
  │              │ │ (runtime)    │ │ (runtime)    │
  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
         │                │                │
         ▼                ▼                ▼
  ┌─────────────────────────────────────────────┐
  │         Energy Module Solver F(x)           │
  │  parameters   overrides    constraints      │
  └─────────────────────────────────────────────┘
```

| Layer | When | What | Example |
|-------|------|------|---------|
| **Data Pipeline** | Before model run | Process raw data → model parameters | IEA energy balances → carrier shares |
| **Module Linkage** | During solver loop | External module outputs → override defaults | AFOLU biomass supply curve → trade clearing |
| **Policy** | During solver loop | User-defined interventions → cost/constraint | Carbon price → LCOE adder |

**Key principle**: The data pipeline provides **defaults** for everything. When an external module (Climate, Water, AFOLU) connects, it **overrides** specific defaults at runtime. Policy adds **constraints** on top. The code path is identical — only the data source changes.


## 2. Data Pipeline

### 2.1 gcamdata as Foundation

GHIM's data processing mirrors GCAM's gcamdata R package. gcamdata already processes land-use (`module_aglu_*`), water (`module_water_*`), and energy (`module_energy_*`) chunks. We use gcamdata's **outputs** as our starting point.

```
gcamdata (R package)
├── module_energy_*    → IEA energy balances, tech costs, resource curves
├── module_aglu_*      → Crop production, biomass supply, land allocation
├── module_water_*     → Water availability, hydro potential, cooling water
├── module_emissions_* → CEDS emission factors
├── module_socio_*     → Population, GDP (SSP)
└── module_climate_*   → HDD/CDD, climate normals
```

### 2.2 Pipeline Stages

```
Stage 1: Raw Sources                Stage 2: gcamdata Processing
─────────────────                   ────────────────────────────
IEA WEB 2023                   ──→  Energy balances by R32 × carrier × sector
IIASA SSP (AR6)                ──→  GDP, Population, labor by country
NREL ATB 2024                  ──→  Technology cost assumptions
GEM 2024                       ──→  Plant-level capacity + age
FAO / AFOLU team               ──→  Biomass supply curves, ag output
USGS / Water team              ──→  Water availability, hydro potential
CEDS 2022                      ──→  Emission factors by fuel

Stage 3: GHIM Processing           Stage 4: Model Parameters
─────────────────────               ────────────────────────
gcamdata R32 → direct use      ──→  Regional energy balances
Country → R32 mapping          ──→  SSP trajectories per R32
Plant-level → R32 vintage      ──→  VintageStock initialization
R32 supply curves → direct     ──→  Fossil + biomass trade data
Tech costs → LCOE/LCOT         ──→  Logit calibration inputs
HDD/CDD normals                ──→  Buildings demand calibration
Water avail → hydro CF         ──→  Electricity capacity factors
```

### 2.3 What GHIM Takes from gcamdata (by domain)

#### Energy (core — always needed)

| gcamdata output | GHIM use | Loader |
|----------------|---------|--------|
| IEA energy balances (R32 × carrier × sector) | Base-year calibration of all demand sectors | `ghim/data/energy_cal.py` |
| Technology costs ($/kW, $/GJ) | LCOE/LCOT calculation, logit calibration | `ghim/data/energy_cal.py` |
| Fossil supply curves (R32 × grade) | Trade module supply curves | `ghim/data/trade_cal.py` |
| Electricity plant data (GEM) | VintageStock initialization | `ghim/data/gem_cal.py` |
| SSP socioeconomic data | GDP, population, labor force | `ghim/data/ssp.py` |

#### Land-Use / AFOLU (from gcamdata, overridable by AFOLU module)

| gcamdata output | GHIM use | Default behavior | Override when |
|----------------|---------|-----------------|---------------|
| Biomass supply curves (R32 × grade) | Biomass trade clearing | Static curves from gcamdata | AFOLU module provides dynamic curves |
| Agricultural output (R32 × period) | Agriculture energy demand driver | GDP-scaled approximation | AFOLU module provides $Q_{ag}(t)$ |
| Energy crop land potential (R32) | Biomass supply cap | Unconstrained | AFOLU module provides land allocation |
| Crop residue ratios | Residue grade in biomass supply | Fixed fraction | AFOLU module provides dynamic ratios |

#### Water (from gcamdata, overridable by Water module)

| gcamdata output | GHIM use | Default behavior | Override when |
|----------------|---------|-----------------|---------------|
| Hydro potential by region | Hydro CF calibration | Fixed from gcamdata | Water module provides dynamic allocation |
| Cooling water availability | Thermal plant constraint | Unconstrained ($\infty$) | Water module provides stress data |
| HDD/CDD climate normals | Buildings demand calibration | Fixed base-year values | Climate module provides projections |
| Water-for-energy intensity | Electricity demand adder | Implicit in Industry | Water module provides explicit demand |

#### Climate (from gcamdata/literature, overridable by Climate module)

| gcamdata output | GHIM use | Default behavior | Override when |
|----------------|---------|-----------------|---------------|
| HDD/CDD by region | Buildings heating/cooling demand | Fixed at base year | Climate module provides $HDD(T(t))$ |
| Solar/wind CF by region | Electricity capacity factors | Fixed at base year | Climate module provides CF anomalies |
| Temperature normals | Thermal efficiency baseline | Fixed | Climate module provides $\Delta T(t)$ |

### 2.4 Processing Pipeline Architecture

```python
# ghim/data/pipeline.py (conceptual)

class DataPipeline:
    """Processes gcamdata outputs into GHIM model parameters."""

    def __init__(self, gcamdata_dir: Path, external_dir: Path):
        self.gcamdata_dir = gcamdata_dir   # gcamdata CSV outputs
        self.external_dir = external_dir    # ghim/data/external/

    def process(self) -> ModelParameters:
        # Stage 1: Load gcamdata outputs
        energy = load_energy_balances(self.gcamdata_dir)
        ssp = load_ssp_data(self.external_dir / "ssp")
        fossil = load_fossil_curves(self.external_dir / "energy")
        gem = load_gem_data(self.external_dir / "energy")

        # Stage 2: Load land-use & water defaults from gcamdata
        biomass = load_biomass_curves(self.gcamdata_dir)   # from aglu chunks
        water = load_water_data(self.gcamdata_dir)         # from water chunks
        climate = load_climate_normals(self.gcamdata_dir)  # HDD/CDD

        # Stage 3: Aggregate R32 → R32
        energy_r10 = aggregate_to_r10(energy)
        fossil_r10 = aggregate_to_r10(fossil)
        biomass_r10 = aggregate_to_r10(biomass)

        # Stage 4: Calibrate model parameters
        params = calibrate(energy_r10, ssp, fossil_r10, biomass_r10,
                          gem, water, climate)
        return params
```

### 2.5 File Structure

```
ghim/data/
├── external/                    # All external data files
│   ├── ssp/                     # SSP socioeconomic (exists)
│   ├── energy/                  # IEA, GEM, tech costs (exists)
│   ├── common/                  # Region mappings (exists)
│   ├── climate/                 # HDD/CDD, CF anomalies (to create)
│   ├── water/                   # Water availability (to create)
│   └── afolu/                   # Biomass supply, ag output (to create)
├── ssp.py                       # SSP loader (exists)
├── trade_cal.py                 # Fossil supply curves (exists)
├── gem_cal.py                   # GEM electricity data (exists)
├── energy_cal.py                # IEA energy balances (to create)
├── climate_cal.py               # Climate data loader (to create)
├── water_cal.py                 # Water data loader (to create)
└── afolu_cal.py                 # AFOLU data loader (to create)
```


## 3. Module Linkages

### 3.1 Coupling Taxonomy

| Coupling Type | When | Frequency | Example |
|--------------|------|-----------|---------|
| **Data-stage** | Pre-run (pipeline) | Once per scenario | HDD/CDD normals, hydro potential |
| **Runtime-static** | Model initialization | Once per run | Biomass supply curves, resource potentials |
| **Runtime-dynamic** | Every solver period | Every 5-year step | $\Delta T \rightarrow$ thermal efficiency, biomass price |

**Design principle**: Every runtime-dynamic variable has a data-stage default from gcamdata. External modules override the default. Code sees the same interface regardless of source.

### 3.2 Adapter Pattern

```python
class ExternalInterface(ABC):
    """Base class for all external module connections."""

    @abstractmethod
    def get_value(self, region: str, period: int) -> float: ...

class DefaultAdapter(ExternalInterface):
    """Uses gcamdata default (data-stage values)."""
    def __init__(self, data: pd.DataFrame):
        self.data = data

    def get_value(self, region: str, period: int) -> float:
        return self.data.loc[(region, period), "value"]

class LiveAdapter(ExternalInterface):
    """Uses runtime values from connected module."""
    def __init__(self, module):
        self.module = module

    def get_value(self, region: str, period: int) -> float:
        return self.module.compute(region, period)
```

Phase 1 uses `DefaultAdapter` everywhere. When Climate/Water/AFOLU modules connect, they replace the adapter with `LiveAdapter`. No code change in the Energy module.

### 3.3 Energy ↔ Climate (7 channels)

All same-period coupling. Climate outputs affect energy efficiency and demand; energy emissions feed back to climate.

| ID | Channel | Direction | Formula | Default |
|----|---------|-----------|---------|---------|
| C1 | Thermal efficiency penalty | Climate → Energy | $\eta_i = \eta_{ref} \times (1 - \beta_i \times \Delta T_r)$ | $\Delta T = 0$ |
| C2 | Hydropower CF | Climate → Energy | $CF_{hydro} = CF_{base} \times (1 + \gamma \times \Delta P_r / P_{base})$ | $\Delta P = 0$ |
| C3 | Solar irradiance | Climate → Energy | $CF_{solar} = CF_{base} \times (1 + \Delta GHI_r)$ | $\Delta GHI = 0$ |
| C4 | Wind resource | Climate → Energy | $CF_{wind} = CF_{base} \times (v_r / v_{base})^3$ | $v = v_{base}$ |
| C5 | Heating/Cooling degree days | Climate → Energy | $E_{heat} \propto HDD(T)$, $E_{cool} \propto CDD(T)$ | Base-year HDD/CDD |
| C6 | CO₂ emissions | Energy → Climate | $E_{CO2} = \sum FE \times coef \times 44/12$ | Always computed |
| C7 | Non-CO₂ forcing | Energy → Climate | Exogenous from CEDS/EDGAR | Data file |

**C5 is the strongest feedback** by magnitude. A 3°C warming can reduce heating 15–20% and increase cooling 30–50% in mid-latitudes. Cooling is almost pure electricity → large demand shift.

**Parameters:**

| Parameter | Value | Channel |
|-----------|-------|---------|
| $\beta_{coal/gas}^{therm}$ | 0.003 /°C | C1 |
| $\beta_{nuclear}^{therm}$ | 0.005 /°C | C1 |
| $\gamma_{hydro}$ | 0.5–1.0 | C2 |

**Data-stage files:**

| File | Contents | Source |
|------|----------|--------|
| `climate/hdd_cdd_{scenario}.csv` | HDD/CDD by R32 × period | Climate team or gcamdata |
| `climate/cf_anomalies_{scenario}.csv` | Solar/wind CF changes | Climate team |
| `climate/temperature_anomaly.csv` | Regional $\Delta T$ | Climate team |

### 3.4 Energy ↔ Water (4 channels)

All same-period coupling. Water constrains thermal generation and hydro output; energy provides electricity for water systems.

| ID | Channel | Direction | Formula | Default |
|----|---------|-----------|---------|---------|
| W1 | Cooling water constraint | Water → Energy | $cap_{thermal}^{max} = W_{cool}^{avail} / w^{specific}$ | Unconstrained |
| W2 | Hydropower allocation | Water → Energy | $E_{hydro} = E_{potential} \times W_{alloc} / W_{full}$ | Full allocation |
| W3 | Energy for water supply | Energy → Water | $E_{water} = Q_{water} \times e^{specific}$ | In Industry demand |
| W4 | Desalination energy | Energy → Water | $E_{desal} = Q_{desal} \times e_{desal}$ | $Q_{desal} = 0$ |

**Cooling water withdrawal rates:**

| Cooling type | Withdrawal (m³/MWh) | Consumption (m³/MWh) |
|-------------|---------------------|---------------------|
| Once-through | 75–190 | 1–2 |
| Wet tower | 2–4 | 1.5–3 |
| Dry cooling | 0 | 0 |
| Solar/Wind | 0 | 0 |

**Data-stage files:**

| File | Contents | Source |
|------|----------|--------|
| `water/cooling_water_avail.csv` | Cooling water by R32 × period | Water team or gcamdata |
| `water/hydro_allocation.csv` | Hydro water fraction by R32 | Water team or gcamdata |

### 3.5 Energy ↔ AFOLU (7 channels)

**Tightest coupling.** Biomass price, land allocation, and energy supply interact simultaneously.

| ID | Channel | Direction | Formula | Default |
|----|---------|-----------|---------|---------|
| A1 | Biomass supply curve | AFOLU → Energy | $Q_{bio}(p) = \sum_{g: c_g \leq p} q_g$ | Static from gcamdata |
| A2 | Energy crop land cap | AFOLU → Energy | $land_{ecrop} \leq land_{max}$ | Unconstrained |
| A3 | Crop residue supply | AFOLU → Energy | $Q_{residue} = \alpha \times Q_{ag}$ | GDP-scaled $Q_{ag}$ |
| A4 | Biofuel demand | Energy → AFOLU | $D_{bio} = \sum_{sectors} E_{biofuel}$ | Always computed |
| A5 | Biomass price signal | Energy → AFOLU | $p_{bio}^*$ from trade clearing | Always computed |
| A6 | Energy prices for agriculture | Energy → AFOLU | $cost_{ag} = \sum_c E_c \times p_c$ | Always computed |
| A7 | Agricultural energy demand | AFOLU → Energy | $E_{ag} = ei_{ag} \times Q_{ag}$ | GDP-scaled $Q_{ag}$ |

**A1 is the critical data dependency.** Biomass supply curves are required for trade clearing even in Phase 1. These must come from AFOLU team's gcamdata pipeline or GCAM data.

**Data-stage files:**

| File | Contents | Source |
|------|----------|--------|
| `afolu/biomass_supply_curves.csv` | R32 × grade → cost, qty | AFOLU team or gcamdata |
| `afolu/ag_output.csv` | Agricultural output by R32 × period | AFOLU team or gcamdata |
| `afolu/land_ecrop_max.csv` | Energy crop land cap by R32 | AFOLU team |

### 3.6 Runtime Interface Classes

```python
class ClimateInterface:
    def get_temperature_anomaly(self, region: str, period: int) -> float: ...
    def get_precipitation_anomaly(self, region: str, period: int) -> float: ...
    def get_hdd(self, region: str, period: int) -> float: ...
    def get_cdd(self, region: str, period: int) -> float: ...

class WaterInterface:
    def get_cooling_water_available(self, region: str, period: int) -> float: ...
    def get_hydro_water_fraction(self, region: str, period: int) -> float: ...
    def get_water_energy_demand(self, region: str, period: int) -> float: ...

class AFOLUInterface:
    def get_biomass_supply_curve(self, region: str, period: int) -> list[tuple]: ...
    def get_ag_output(self, region: str, period: int) -> float: ...
    def get_land_ecrop_max(self, region: str, period: int) -> float: ...
```

Each has a `Default*Adapter` that reads from data pipeline, and a `Live*Adapter` for runtime coupling.

### 3.7 Coupling Timing

**All same-period.** No lag anywhere. External modules are called inside the outer fixed-point loop $F(\mathbf{x})$. The damped iteration resolves circular dependencies within the same period.

```
Period t, iteration n:
  Climate(t) → ΔT, HDD/CDD     (from cumulative emissions)
  Water(t)   → cooling cap, hydro   (from climate + water state)
  AFOLU(t)   → biomass supply, Q_ag (from energy prices + demand)
  Energy(t)  → demands, supply, trade, emissions
  → feed back to Climate, Water, AFOLU
  → iterate until ||x_{n+1} - x_n|| / ||x_n|| < ε
```


## 4. Policy Framework

### 4.1 Policy as External Input

Policy interventions enter the model through the same mechanism as module linkages — they modify costs, constrain shares, or adjust parameters. The difference is that policies are **user-specified** (from JSON files or CLI flags), not computed by external modules.

```
Module output:   AFOLU → biomass supply curve → overrides default
Policy:          User  → carbon price        → adds to fuel cost
                 User  → tech ban            → sets α = 0
                 User  → share constraint    → clamps logit output
```

### 4.2 Policy Scenario Structure

A `PolicyScenario` is a JSON file containing any combination of the following instruments:

```json
{
  "name": "net_zero_2050",
  "carbon_price": { "trajectory": {"2025": 30, "2050": 300} },
  "renewable_subsidies": { "subsidies": {"solar": {"2025": 2.0, "2050": 0}} },
  "efficiency_standards": { "rates": {"global": {"2025": 0.01}} },
  "emissions_cap": { "caps": {"global": {"2030": 35000, "2050": 5000}} },
  "tech_constraints": [
    {"sector": "electricity", "technology": "coal", "constraint_type": "max",
     "trajectory": {"2030": 0.30, "2050": 0.0}}
  ],
  "tech_availability": { "schedules": {"electricity.coal": {"2025": 1, "2045": 0}} },
  "pref_overrides": { "overrides": {"demand.hydrogen": {"2025": 5.0, "2050": 0}} },
  "revenue_recycling": { "fraction": 0.5 }
}
```

All sub-policies default to no-op. Existing behavior unchanged without policy arguments.

### 4.3 Policy Instrument Taxonomy

Every policy instrument is one of four types:

| Type | Mechanism | Example |
|------|-----------|---------|
| **Cost adder** | Adds to or subtracts from technology/fuel cost | Carbon tax, subsidy, fuel tax |
| **Quantity constraint** | Limits or fixes output/share | Emissions cap, RES, fixed output |
| **Gate** | Enables or disables a technology | Tech availability (α switch) |
| **Parameter override** | Replaces a calibrated parameter | Pref factor override, WACC override |

### 4.4 Cost Adders

#### Carbon Tax

$$C_{fuel,i}^{policy} = C_{fuel,i} + coef_i \times (1 - capture_i) \times P_{carbon} \times \frac{44}{12}$$

- Enters LCOE, LCOT, carrier cost at the **fuel level** (not per-technology)
- Trajectory: year → $/tCO₂ (linearly interpolated between waypoints)
- Applies to all sectors uniformly
- CCS technologies benefit: $capture = 0.9$ → only 10% of carbon cost applies

```json
"carbon_price": {"trajectory": {"2025": 30, "2050": 300}}
```

#### Technology Subsidy

$$C_i^{policy} = C_i - subsidy_i(t)$$

Per-technology cost reduction ($/GJ or $/kW). Can be applied to:
- **Capex subsidy**: reduces LCOE/LCOT capital term (e.g., solar ITC, wind PTC)
- **Operating subsidy**: reduces variable cost (e.g., feed-in tariff premium)
- **Negative subsidy = tax**: technology-specific surcharge

```json
"subsidies": {
  "electricity.solar": {"capex": {"2025": 500, "2040": 0}, "unit": "$/kW"},
  "electricity.wind":  {"opex": {"2025": 1.5, "2040": 0}, "unit": "$/GJ"}
}
```

#### Fuel Tax / Excise

$$C_{carrier}^{policy} = C_{carrier} + tax_{carrier}(t)$$

Per-carrier cost adder ($/GJ). Different from carbon tax — applies uniformly to a fuel regardless of carbon content. Used for:
- Fuel excise duty (gasoline/diesel tax)
- Gas levy (methane fee)
- Electricity surcharge

```json
"fuel_taxes": {
  "refined_oil": {"trajectory": {"2025": 2.0, "2030": 3.0}, "unit": "$/GJ"},
  "gas":         {"trajectory": {"2025": 0.5}, "unit": "$/GJ"}
}
```

#### Green Finance / WACC Override

Technology-specific discount rate override:

$$WACC_{clean} = WACC_{base} - subsidy_{spread}$$

Lowers the annualized capital recovery factor (FCR) for targeted technologies → lower LCOE → higher logit share.

```json
"green_finance": {
  "overrides": {"electricity.solar": {"2025": 0.03}, "electricity.wind": {"2025": 0.02}}
}
```

### 4.5 Quantity Constraints

#### Emissions Cap

$$E_{CO2}(P_{carbon}^*) \leq Cap(t)$$

Find carbon price $P_{carbon}^*$ via bisection such that total emissions meet the cap. Parameters:
- Bisection tolerance: 2%
- Max iterations: 20
- Price ceiling: 2000 $/tCO₂
- Scope: global or regional

This wraps the carbon price instrument — the cap determines the required price endogenously.

```json
"emissions_cap": {"caps": {"global": {"2030": 35000, "2050": 5000, "2060": 0}}}
```

#### Price Floor / Ceiling

$$p_{floor}(t) \leq p_{commodity} \leq p_{ceiling}(t)$$

Bounds on commodity prices in trade clearing. Used for:
- **Carbon price floor**: minimum effective carbon price (e.g., EU ETS floor)
- **Oil price ceiling**: strategic petroleum reserve intervention
- **Electricity price floor**: prevent negative prices from excess renewables

```json
"price_bounds": {
  "carbon":      {"floor": {"2025": 20}, "ceiling": {}},
  "electricity": {"floor": {"2025": 0.5}, "ceiling": {}}
}
```

Implementation: clamp cleared price to bounds after bisection. If floor binds, excess supply is curtailed.

#### Renewable Energy Standard (RES)

$$\sum_{i \in \text{renewables}} s_i(t) \geq RES(t)$$

Minimum share for a **group** of technologies in a market. Different from per-technology share constraints — RES applies to the aggregate.

| RES type | Technologies in group | Market |
|----------|----------------------|--------|
| RPS (Renewable Portfolio Standard) | Solar, Wind, Hydro, Geothermal, Ocean, Biomass | Electricity |
| Clean Energy Standard | RPS + Nuclear + CCS | Electricity |
| Biofuel Blend Mandate | Bio-ICE, SAF, Biodiesel | Transport fuels |
| Green Hydrogen Standard | Electrolysis | Hydrogen |

Implementation: if aggregate renewable share falls below RES target, redistribute from non-qualifying technologies.

```json
"res": [
  {"market": "electricity", "group": ["solar", "wind", "hydro", "geothermal", "biomass"],
   "min_share": {"2030": 0.40, "2050": 0.80}},
  {"market": "transport", "group": ["bio_ice", "biodiesel"],
   "min_share": {"2030": 0.10}}
]
```

#### Fixed Output

$$Q_i(t) = Q_i^{fixed}(t) \quad \text{(overrides logit)}$$

Exogenously set output for a specific technology. Logit is bypassed for that technology; remaining share distributed among other technologies.

Used for:
- Government nuclear build plan (fixed GW by year)
- Guaranteed coal phase-out schedule (fixed declining output)
- Contracted hydro output (fixed by water rights)

```json
"fixed_output": [
  {"sector": "electricity", "technology": "nuclear",
   "trajectory": {"2030": 3.0, "2040": 5.0}, "unit": "EJ"},
  {"sector": "electricity", "technology": "coal",
   "trajectory": {"2030": 8.0, "2040": 4.0, "2050": 0}, "unit": "EJ"}
]
```

Implementation: subtract fixed output from total demand before logit; add back after.

#### Share Constraints (per-technology min/max)

$$s_i^{min}(t) \leq s_i \leq s_i^{max}(t)$$

Applied **after** logit computation. Iterative clamp-and-redistribute algorithm preserves total shares = 1. Used for:
- Coal cap: `"electricity.coal": max 0% by 2050`
- Minimum nuclear: `"electricity.nuclear": min 10%`
- Biofuel mandate: `"transport.bio_ice": min 10% by 2030`

```json
"tech_constraints": [
  {"sector": "electricity", "technology": "coal",
   "constraint_type": "max", "trajectory": {"2030": 0.30, "2050": 0.0}}
]
```

### 4.6 Gates

#### Technology Availability ($\alpha$ switch)

$$\alpha_i(t) \in \{0, 1\}$$

Binary gate: $\alpha = 0$ removes technology from logit competition entirely. Used for:
- Phase-out: `"electricity.coal": {"2025": 1, "2045": 0}` (coal ban by 2045)
- Phase-in: `"transport.fcev": {"2020": 0, "2030": 1}` (FCEV available from 2030)
- Technology ban: `"electricity.nuclear": {"2020": 0}` (no nuclear ever)

Interpolated: rounds to 0/1 at threshold 0.5. Simpler than share constraint — α=0 means the technology doesn't exist in that period.

```json
"tech_availability": {"schedules": {"electricity.coal": {"2025": 1, "2045": 0}}}
```

### 4.7 Parameter Overrides

#### Preference Factor Override

$$P_i(t) = P_i^{override}(t) \quad \text{(replaces calibrated decay)}$$

Explicit trajectory for non-cost preference factor ($/GJ). Overrides the default SSP-calibrated decay path. Used for:
- Policy-driven technology push (lower P for hydrogen → higher share)
- Mandate simulation (force adoption beyond cost-optimal)

```json
"pref_overrides": {"overrides": {"demand.hydrogen": {"2025": 5.0, "2050": 0}}}
```

#### Efficiency Standards (AEEI)

$$E_{sector}(t) = E_{sector}^{raw}(t) \times (1 - r_{AEEI})^{t - t_{base}}$$

**Phase 1 note**: AEEI is available as a policy instrument but NOT used in baseline runs. Baseline efficiency gains come only from carrier/tech switching via logit. AEEI is a policy lever (e.g., appliance standards, building codes) that can be layered on top.

```json
"efficiency_standards": {"rates": {"global": {"2025": 0.01, "2050": 0.02}}}
```

#### Revenue Recycling

$$\Delta cost_{energy} = -f_{recycle} \times Revenue_{carbon}$$

Fraction of carbon tax revenue returned as energy cost reduction. Diagnostic only in CES approach — carbon price flows through composite energy price → CES production function. Revenue recycling partially offsets the GDP drag.

```json
"revenue_recycling": {"fraction": 0.5}
```

### 4.8 Instrument Summary

| Instrument | Type | JSON key | Scope | Phase 1 |
|------------|------|----------|-------|---------|
| Carbon tax | Cost adder | `carbon_price` | Global | Yes |
| Technology subsidy | Cost adder | `subsidies` | Per-tech, per-period | Yes |
| Fuel tax | Cost adder | `fuel_taxes` | Per-carrier, per-period | Yes |
| Green finance | Cost adder | `green_finance` | Per-tech, per-period | Phase 2+ |
| Emissions cap | Quantity | `emissions_cap` | Global / regional | Yes |
| Price floor/ceiling | Quantity | `price_bounds` | Per-commodity | Yes |
| RES | Quantity | `res` | Per-market | Yes |
| Fixed output | Quantity | `fixed_output` | Per-tech, per-period | Yes |
| Share constraint | Quantity | `tech_constraints` | Per-tech, per-period | Yes |
| Tech availability | Gate | `tech_availability` | Per-tech, per-period | Yes |
| Pref override | Param override | `pref_overrides` | Per-tech, per-period | Yes |
| AEEI | Param override | `efficiency_standards` | Per-sector or global | Yes |
| Revenue recycling | Param override | `revenue_recycling` | Global | Yes |

### 4.9 Policy Entry Points in F(x)

| Instrument | Where in F(x) | Mechanism |
|------------|---------------|-----------|
| Carbon tax | Step 2 (LCOE/LCOT) | Adds to fuel cost term |
| Technology subsidy | Step 2 (LCOE/LCOT) | Subtracts from capex or opex |
| Fuel tax | Step 2 (carrier cost) | Adds to carrier price |
| Green finance | Step 2 (LCOE FCR) | Lowers annualized capital cost |
| Tech availability | Step 2 (logit) | Sets $\alpha_i = 0$ or $1$ |
| Pref override | Step 2 (logit) | Replaces $P_i(t)$ in logit |
| Share constraint | After Step 2 | Clamps shares, redistributes |
| RES | After Step 2 | Aggregate floor on renewable group |
| Fixed output | Before/after Step 2 | Subtract fixed from total, logit on remainder |
| Price floor/ceiling | Step 4 (trade) | Clamp cleared price |
| Emissions cap | Wraps full F(x) | Outer bisection on carbon price |
| AEEI | Step 1 (demand) | Scales demand downward |
| Revenue recycling | Step 6 (macro) | Reduces energy cost in CES |


## 5. Unified View: How Everything Enters F(x)

### 5.1 Complete Model Pass with All External Inputs

```
F(x):
  Y, prices = unpack(x)

  # ═══ Data Pipeline defaults (loaded once) ═══════════════════
  # Already in parameters: energy balances, tech costs, supply curves,
  # HDD/CDD, hydro CF, biomass supply — all from gcamdata

  # ═══ Module Linkage overrides (each iteration) ══════════════
  ΔT, ΔP        = climate_adapter.get_anomalies(period)      # C1-C5
  W_cool, W_hydro = water_adapter.get_constraints(period)     # W1-W2
  E_water        = water_adapter.get_energy_demand(period)     # W3-W4
  biomass_curves = afolu_adapter.get_supply(period)            # A1
  Q_ag           = afolu_adapter.get_ag_output(period)         # A3,A7

  # ═══ Policy instruments (user-specified) ════════════════════
  P_carbon       = policy.carbon_price.get_price(period)
  alpha          = policy.tech_availability.is_available(...)
  P_override     = policy.pref_overrides.get_override(...)
  aeei_factor    = policy.efficiency_standards.cumulative_factor(...)

  # ═══ Step 1: Final Energy Demand ════════════════════════════
  Apply climate impacts: HDD/CDD → buildings, η → thermal
  Apply water constraints: W_cool cap, hydro allocation
  Add water energy demand: E_water → electricity demand
  Apply AEEI: demand *= aeei_factor (if policy active)

  # ═══ Step 2: Technology Share (Logit) ═══════════════════════
  Apply carbon price to fuel costs
  Apply tech availability (α gates)
  Apply pref overrides (P_i replacement)
  Compute logit shares
  Apply share constraints (clamp + redistribute)

  # ═══ Step 3: Primary Energy Demand ══════════════════════════
  Aggregate carrier demands across sectors

  # ═══ Step 4: Global Market Clearing (Trade) ═════════════════
  Clear fossil markets (coal, oil, gas) via bisection
  Clear biomass market using AFOLU supply curves

  # ═══ Step 5: Secondary Market Clearing ══════════════════════
  Electricity dispatch (merit order + logit)
  Hydrogen production mix
  District heating dispatch

  # ═══ Step 6: Macro Economy Update ══════════════════════════
  Y = Q - p_E·E - p_M·M  (CES net output)
  Apply revenue recycling (if policy active)

  # ═══ Step 7: Financial Market Clearing ═════════════════════
  I_K = s·Y - I_energy - I_RD

  # ═══ Feed back to external modules ═════════════════════════
  climate_adapter.receive(CO2_emissions)                      # C6
  afolu_adapter.receive(biomass_price, biofuel_demand, prices) # A4-A6
  water_adapter.receive(cooling_demand, elec_price)

  return pack(Y_new, prices_new)
```

### 5.2 Emissions Cap Wrapper

When an emissions cap is active, the entire F(x) is wrapped in an outer bisection:

```python
def solve_with_cap(period, cap):
    def emissions_at_price(p_carbon):
        policy.carbon_price = p_carbon
        x_star = fixed_point(F, x0)       # full solve
        return compute_emissions(x_star)

    # Bisection: find p_carbon such that emissions ≤ cap
    p_star = bisect(lambda p: emissions_at_price(p) - cap,
                    lo=0, hi=2000, tol=0.02)
    return p_star
```

### 5.3 Phase 1 Default Configuration

| External Input | Phase 1 Source | Runtime Override |
|---------------|---------------|-----------------|
| Energy balances | IEA WEB via gcamdata | — (always from data) |
| SSP trajectories | IIASA SSP database | — (always from data) |
| Fossil supply curves | GCAM PREBUILT_DATA | — (always from data) |
| Biomass supply curves | gcamdata AFOLU chunks | AFOLU module |
| HDD/CDD | gcamdata climate normals | Climate module |
| Hydro CF | GEM + gcamdata | Climate + Water modules |
| Cooling water | Unconstrained (∞) | Water module |
| Ag output | GDP-scaled approximation | AFOLU module |
| Carbon price | 0 (no policy) | User JSON |
| Tech availability | All available (α=1) | User JSON |


## 6. Data Exchange Format

### 6.1 CSV Convention

All inter-team data exchange files follow one format:

```csv
region,period,variable,value,unit
R32AFRICA,2020,biomass_grade1_cost,2.5,$/GJ
R32AFRICA,2020,biomass_grade1_qty,8.3,EJ
R32AFRICA,2025,hdd,2500,degree-days
```

### 6.2 Region Mapping

Phase 1 uses **32 GCAM-style regions** (R32). gcamdata already processes data at R32 resolution — no aggregation needed. Country-level data (SSP, GEM) is mapped to R32 using `ghim/data/external/common/iso_GCAM_regID.csv` and `GCAM_region_names.csv`.

Phase 2+: 100+ country resolution. Country-level data used directly; gcamdata R32 outputs disaggregated to countries by GDP/population share.

### 6.3 Scenario Naming

```
{module}_{variable}_{scenario}.csv

Examples:
  climate_hdd_cdd_SSP2-4.5.csv
  afolu_biomass_supply_SSP2.csv
  water_cooling_avail_SSP2.csv
```

When no scenario suffix is given, the file applies to all scenarios (e.g., `water_specific_energy.csv` — physical constants, not scenario-dependent).


## 7. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| gcamdata output directory | `ghim/data/external/` | Config file |
| External data directory (climate/water/afolu) | `ghim/data/external/{module}/` | Config file |
| Default adapter type | Default (gcamdata) | Per-module (Default or Live) |
| Carbon tax trajectory | 0 (none) | Policy JSON |
| Technology subsidies | None | Policy JSON (per-tech, per-period) |
| Fuel taxes | None | Policy JSON (per-carrier, per-period) |
| Green finance WACC overrides | None | Policy JSON (per-tech) |
| Emissions cap | None | Policy JSON (global/regional) |
| Price floor/ceiling | None | Policy JSON (per-commodity) |
| RES targets | None | Policy JSON (per-market) |
| Fixed output schedules | None | Policy JSON (per-tech, per-period) |
| Share constraints (min/max) | None | Policy JSON (per-tech) |
| Tech availability ($\alpha$) | All available | Policy JSON (per-tech) |
| Pref factor overrides | None (calibrated decay) | Policy JSON (per-tech) |
| AEEI rates | 0 (no standards) | Policy JSON (per-sector or global) |
| Revenue recycling fraction | 0 | Policy JSON |


## 8. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| **Data Pipeline** | Manual CSV processing, R32→R32 | Automated workflow (Drake/Snakemake) |
| **gcamdata integration** | Read existing outputs | Extend gcamdata with GHIM-specific chunks |
| **Climate coupling** | Data-stage defaults ($\Delta T = 0$) | Runtime dynamic (Climate inside F loop) |
| **Water coupling** | Unconstrained defaults | Runtime dynamic (Water inside F loop) |
| **AFOLU coupling** | Static biomass from gcamdata | Runtime dynamic (AFOLU inside F loop) |
| **Adapter pattern** | DefaultAdapter everywhere | LiveAdapter when modules connect |
| **Carbon price** | Exogenous trajectory | + Endogenous via emissions cap bisection |
| **Tech availability** | Binary α gates | Same |
| **Share constraints** | Clamp + redistribute | Same |
| **Emissions cap** | Outer bisection on F(x) | Same + regional caps |
| **AEEI** | Policy-only (not in baseline) | Endogenous via Energy Services Nest |
| **Revenue recycling** | Diagnostic only | + Direct investment channeling |
| **Green finance** | Not implemented | WACC override per technology |
| **Inter-team data exchange** | Manual CSV exchange | Automated pipeline with versioning |

### Phase transition notes

- **Phase 1 → 2**: Replace DefaultAdapters with LiveAdapters as modules connect. No Energy code change — same interface, different implementation. Automate data pipeline with Drake/Snakemake. Add endogenous R&D via Energy Services Nest (replaces AEEI policy lever with endogenous efficiency). Activate green finance WACC overrides.
- **Phase 2 → 3**: Full runtime coupling with all three modules inside F(x). Regional emissions caps. Endogenous R&D allocation. Automated cross-team data pipeline with dependency tracking and version control.
