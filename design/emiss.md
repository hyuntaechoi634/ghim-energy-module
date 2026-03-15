# GHIM Energy Module — Emissions Design

## 1. Overview

The energy module computes greenhouse gas emissions for CO$_2$, CH$_4$, N$_2$O, and F-Gases. All emissions are tracked by gas and by source, then converted to CO$_2$eq using GWP$_{100}$ for reporting and climate module coupling.

Only **land-use change CO$_2$** comes from the external AFOLU adapter. Everything else — including agricultural CH$_4$/N$_2$O and waste CH$_4$ — is computed within the energy module.


## 2. Gases and Sources

### 2.1 CO$_2$

| Source | Scope | Calculation | Phase |
|--------|-------|-------------|-------|
| Fuel combustion | All sectors | fuel (EJ) × emission factor (tCO$_2$/GJ) | 1 |
| CCS capture | Transformation | −capture_rate × combustion CO$_2$ | 1 |
| Industrial process | Industry | production × process factor (cement, steel) | 2 |
| Land-use change | AFOLU adapter | External input | 2+ |

Fuel combustion is the dominant source. Emission factors are per-fuel, not per-technology — burning 1 GJ of coal emits the same CO$_2$ whether in a power plant or a kiln.

### 2.2 CH$_4$

| Source | Scope | Calculation | Phase |
|--------|-------|-------------|-------|
| Fossil fuel fugitive | Trade/Production | regional_production × fugitive factor per fuel | 1 |
| Fuel combustion | All sectors | fuel (EJ) × combustion CH$_4$ factor (small) | 1 |
| Agriculture (enteric + rice + manure) | Agriculture | production_index × base_ch4 | 1 |
| Waste (landfill, wastewater) | Economy-wide | population × per-capita factor × income scaling | 1 |

Fugitive CH$_4$ from coal mining and oil/gas extraction is significant (~6 GtCO$_2$eq/yr globally). It scales with fossil fuel production, creating a direct link between trade volumes and non-CO$_2$ emissions.

### 2.3 N$_2$O

| Source | Scope | Calculation | Phase |
|--------|-------|-------------|-------|
| Fuel combustion | All sectors | fuel (EJ) × combustion N$_2$O factor (small) | 1 |
| Agriculture (soils + manure) | Agriculture | production_index × base_n2o | 1 |
| Industrial process | Industry | adipic/nitric acid production × factor | 2 |

Agricultural N$_2$O (soil emissions from nitrogen fertilizer) is the dominant source (~60% of total N$_2$O).

### 2.4 F-Gases (HFCs, PFCs, SF$_6$)

| Source | Scope | Calculation | Phase |
|--------|-------|-------------|-------|
| Refrigerants (HFCs) | Buildings cooling, Transport AC | EDGAR base × cooling growth × Kigali phase-down | 1 |
| Industrial (PFCs) | Industry | aluminum production proxy × factor | 2 |
| Electrical equipment (SF$_6$) | Electricity | grid capacity proxy × factor | 2 |

Phase 1 uses an **EDGAR-scaled proxy**: base-year F-gas emissions (from EDGAR v8.0, by R32) are scaled by cooling demand growth and the Kigali Amendment phase-down schedule. No stock model needed — the proxy is dimensionally consistent (MtCO₂eq in, MtCO₂eq out) and calibrated to real data. Phase 2+ adds a full HFC stock-flow model with vintage tracking.


## 3. Emission Factors

### 3.1 CO$_2$ from fuel combustion

```python
# tCO2 per GJ of fuel burned
CO2_FACTORS = {
    Carrier.COAL:     0.0946,   # 25.8 tC/TJ × 44/12 × 1e-3
    Carrier.OIL:      0.0733,   # 20.0 tC/TJ × 44/12 × 1e-3
    Carrier.LIQUIDS:  0.0733,   # same as oil (refined)
    Carrier.GAS:      0.0561,   # 15.3 tC/TJ × 44/12 × 1e-3
    Carrier.BIOMASS:  0.0,      # carbon-neutral (regrowth offsets)
    Carrier.BIOFUEL:  0.0,      # carbon-neutral
    Carrier.ELECTRICITY: 0.0,   # indirect (counted at generation)
    Carrier.H2:       0.0,      # indirect (counted at production)
    Carrier.HEAT:     0.0,      # indirect (counted at generation)
    Carrier.URANIUM:  0.0,      # no combustion
}
```

Source: IPCC 2006 Guidelines, Table 1.4 (default emission factors).

### 3.2 CH$_4$ and N$_2$O from fuel combustion

Small but non-zero. Per IPCC 2006 Guidelines Vol. 2 Ch. 2:

```python
# kg CH4 per TJ (= 1e-6 tCH4/GJ)
CH4_COMBUSTION = {
    Carrier.COAL: 1.0e-6,      # stationary combustion
    Carrier.OIL:  3.0e-6,      # stationary
    Carrier.GAS:  1.0e-6,      # stationary
    # Transport: higher factors (incomplete combustion)
    "transport_gasoline": 33.0e-6,
    "transport_diesel":   3.9e-6,
}

# kg N2O per TJ (= 1e-6 tN2O/GJ)
N2O_COMBUSTION = {
    Carrier.COAL: 1.5e-6,
    Carrier.OIL:  0.6e-6,
    Carrier.GAS:  0.1e-6,
}
```

### 3.3 CH$_4$ fugitive from fossil fuel production

```python
# tCH4 per EJ of fuel produced
CH4_FUGITIVE = {
    Carrier.COAL: 0.37e6,      # coal mining (underground + surface avg)
    Carrier.OIL:  0.12e6,      # oil production + processing
    Carrier.GAS:  0.22e6,      # gas production + processing + T&D
}
```

These are global averages. Regional variation is significant (e.g., Russian gas has higher fugitive rates than Norwegian). Phase 2: region-specific fugitive factors.

### 3.4 GWP$_{100}$ (AR6)

```python
GWP100 = {
    "co2":     1,
    "ch4":     27.9,     # AR6 (fossil: 29.8 with climate-carbon feedback)
    "n2o":     273,      # AR6
    "hfc":     1530,     # weighted average HFC mix
    "pfc":     7380,     # CF4
    "sf6":     25200,
}
```


## 4. Computation Architecture

### 4.1 Where emissions are computed

Emissions are computed **at the source**, not in a centralized module. Each sector/module computes its own emissions. The model aggregates in F(x) Step 8.

```
DemandSector.compute_emissions(demands)
  → CO2 combustion + CH4 combustion + N2O combustion
  → Agriculture also adds: CH4 enteric/rice, N2O soils/manure

TransformationSector.compute_emissions(generation)
  → CO2 combustion - CCS capture
  → CH4/N2O combustion

TradeModule.compute_fugitive_emissions(state, regions)
  → CH4 fugitive from coal/oil/gas production

Buildings/Transport (via DemandSector)
  → F-Gas leakage from cooling/AC stock

Economy-wide (in F(x) Step 8)
  → CH4 waste = f(population, gdp)
```

### 4.2 EmissionResult dataclass

```python
@dataclass
class EmissionResult:
    """Anthropogenic emissions by gas from a single source. Units: Mt per gas.

    co2 can be NEGATIVE for BECCS (captured biogenic carbon).
    lulucf is the anthropogenic land-use component (EDGAR):
      positive = deforestation, negative = managed forest regrowth.

    Natural sinks (ocean, CO₂ fertilization) are NOT included here —
    they are irrelevant for UNFCCC Net-Zero accounting.
    Phase 2+ Climate module can track them separately for concentration.
    """
    co2: float = 0.0        # MtCO2 (can be negative for BECCS)
    ch4: float = 0.0        # MtCH4
    n2o: float = 0.0        # MtN2O
    f_gases: float = 0.0    # MtCO2eq (already in CO2eq)
    lulucf: float = 0.0     # MtCO2 (anthropogenic: deforestation − managed regrowth)

    @property
    def co2eq(self) -> float:
        """Total anthropogenic GHG in MtCO2eq (= UNFCCC Net-Zero target)."""
        return (self.co2
                + self.ch4 * GWP100["ch4"]
                + self.n2o * GWP100["n2o"]
                + self.f_gases
                + self.lulucf)

    @property
    def co2eq_excl_lulucf(self) -> float:
        """Anthropogenic GHG excluding LULUCF (energy + industry + agriculture + waste)."""
        return (self.co2
                + self.ch4 * GWP100["ch4"]
                + self.n2o * GWP100["n2o"]
                + self.f_gases)

    def __add__(self, other: "EmissionResult") -> "EmissionResult":
        return EmissionResult(
            co2=self.co2 + other.co2,
            ch4=self.ch4 + other.ch4,
            n2o=self.n2o + other.n2o,
            f_gases=self.f_gases + other.f_gases,
            lulucf=self.lulucf + other.lulucf,
        )
```

### 4.3 Sector emission methods

ABC signature updated to return `EmissionResult`:

```python
class DemandSector(ABC):
    @abstractmethod
    def compute_emissions(self, demands: dict[str, float]) -> EmissionResult:
        """Combustion + sector-specific non-CO2."""
        ...

class TransformationSector(ABC):
    @abstractmethod
    def compute_emissions(self, generation: dict[str, float]) -> EmissionResult:
        """Combustion - CCS capture + combustion CH4/N2O."""
        ...
```

Example — ElectricitySector:

```python
def compute_emissions(self, generation: dict[str, float]) -> EmissionResult:
    co2 = 0.0
    ch4 = 0.0
    n2o = 0.0
    for tech in self.techs:
        ej = generation.get(tech.name, 0.0)
        fuel_input = ej / tech.efficiency
        # CO2
        gross_co2 = fuel_input * CO2_FACTORS.get(tech.fuel_input, 0.0) * 1000  # EJ→PJ→Mt
        captured = gross_co2 * tech.capture_rate
        co2 += gross_co2 - captured
        # CH4, N2O
        ch4 += fuel_input * CH4_COMBUSTION.get(tech.fuel_input, 0.0) * 1e3
        n2o += fuel_input * N2O_COMBUSTION.get(tech.fuel_input, 0.0) * 1e3
    return EmissionResult(co2=co2, ch4=ch4, n2o=n2o)
```

Example — AgricultureSector:

```python
def compute_emissions(self, rs: RegionState) -> EmissionResult:
    # Fuel combustion (standard)
    result = self._combustion_emissions(rs.final_demand["agriculture"])

    # Non-energy: production index drives both CH4 and N2O
    idx = self.production_index(rs)
    result.ch4 += self.base_ch4 * idx
    result.n2o += self.base_n2o * idx

    return result
```

### 4.4 F(x) Step 8 aggregation

```python
# In GHIMModel.F():
# Step 8: Emissions
total_global = EmissionResult()

for name, region in self.regions.items():
    rs = new.regions[name]
    region_em = EmissionResult()

    # Transformation sectors
    for sector in region.transformation:
        gen = rs.generation.get(sector.carrier_output, {})
        region_em = region_em + sector.compute_emissions(gen)

    # Demand sectors
    for sector in region.demand_sectors:
        region_em = region_em + sector.compute_emissions(rs.final_demand)

    # Fugitive CH4 from fossil production
    for fuel in [Carrier.COAL, Carrier.OIL, Carrier.GAS]:
        prod = rs.regional_production.get(fuel, 0.0)
        region_em.ch4 += prod * CH4_FUGITIVE.get(fuel, 0.0)

    # Waste CH4
    region_em.ch4 += rs.population * WASTE_CH4_PER_CAPITA * (rs.gdp / rs.population) ** 0.3

    # F-Gases: EDGAR base × cooling demand growth × Kigali phase-down
    cooling_now = rs.final_demand.get("cooling_ej", 0.0)
    cooling_base = rs.base_cooling_ej                     # base-year cooling energy (EJ)
    cooling_growth = cooling_now / cooling_base if cooling_base > 0 else 1.0
    kigali_factor = policy.get_kigali_factor(period)      # 1.0 at base, declining per schedule
    region_em.f_gases += EDGAR_FGAS[region] * cooling_growth * kigali_factor

    rs.emissions_detail = region_em
    rs.emissions = region_em.co2eq
    total_global = total_global + region_em

new.global_emissions = total_global.co2eq / 1000.0  # Mt → Gt
new.global_emissions_detail = total_global
```

### 4.5 RegionState additions

```python
@dataclass
class RegionState:
    ...
    # Emissions (existing)
    emissions: float = 0.0                          # MtCO2eq (total)

    # Emissions detail (new)
    emissions_detail: EmissionResult = field(default_factory=EmissionResult)
```


## 5. Agriculture Non-Energy Emissions

Agriculture non-energy emissions are driven by the **production index** $Q_{ag}(t)$ — the same index that drives energy demand (see `agriculture.md` §3.1). No separate livestock/rice/fertilizer sub-indices in Phase 1.

### 5.1 Single-index scaling

$$CH_4^{ag}(t) = CH_{4,0}^{ag} \times Q_{ag}(t)$$
$$N_2O^{ag}(t) = N_2O_{0}^{ag} \times Q_{ag}(t)$$

where $Q_{ag}(t)$ is the production index (base = 1.0), driven by GDP and energy prices (Engel's law income elasticity $\alpha_{ag} = 0.3$).

This aggregates:
- **CH$_4$**: enteric fermentation + rice cultivation + manure
- **N$_2$O**: fertilizer soil emissions + manure management

Both scale proportionally with aggregate agricultural production. The approximation is reasonable in Phase 1 because all agricultural sub-activities correlate with overall production growth.

Phase 2+: AFOLU module provides separate livestock/crop indices, enabling finer decomposition.

### 5.2 Base-year data

Source: EDGAR v8.0 (Emissions Database for Global Atmospheric Research)

| Emission | Global total (2020) | Unit |
|----------|-------------------|------|
| CH$_4$ agriculture (enteric + rice + manure) | 2,600 | MtCO$_2$eq |
| N$_2$O agriculture (soils + manure) | 2,600 | MtCO$_2$eq |
| CH$_4$ waste (landfill + wastewater) | 800 | MtCO$_2$eq |
| CH$_4$ fugitive (fossil production) | 3,700 | MtCO$_2$eq |
| F-Gases | 1,200 | MtCO$_2$eq |

These are disaggregated to R32 regions using EDGAR gridded data.


## 6. F-Gas Modeling

### 6.1 Phase 1: EDGAR-scaled proxy

F-gas emissions are scaled from EDGAR v8.0 base-year data by R32 region. No stock model — dimensionally consistent proxy:

$$F_{gas,r}(t) = F_{gas,r}^{base} \times \frac{E_{cool,r}(t)}{E_{cool,r}^{base}} \times \kappa(t)$$

where:

| Symbol | Meaning | Unit |
|--------|---------|------|
| $F_{gas,r}^{base}$ | EDGAR base-year F-gas emissions for region $r$ | MtCO$_2$eq |
| $E_{cool,r}(t) / E_{cool,r}^{base}$ | Cooling energy demand growth ratio | dimensionless |
| $\kappa(t)$ | Kigali phase-down factor | dimensionless (1.0 at base, declining) |

```python
EDGAR_FGAS = {
    "USA": 170.0,       # MtCO2eq (2021)
    "China": 230.0,
    "EU-12": 85.0,
    # ... all R32 regions, total ~1,200 MtCO2eq
}

def compute_fgas(region, cooling_ej, cooling_base_ej, kigali_factor):
    growth = cooling_ej / cooling_base_ej if cooling_base_ej > 0 else 1.0
    return EDGAR_FGAS[region] * growth * kigali_factor  # MtCO2eq
```

**Why this works**: The dominant driver is the Kigali phase-down schedule (exogenous policy). Cooling demand growth captures the income/climate effect. The product is in MtCO₂eq throughout — no unit conversion issues.

### 6.2 Kigali Amendment

HFC phase-down schedule enters as a policy instrument:

```json
{
    "f_gas_phase_down": {
        "type": "share_constraint",
        "target_gas": "hfc",
        "schedule": {
            "2025": 1.0,
            "2030": 0.70,
            "2035": 0.50,
            "2040": 0.30,
            "2045": 0.20
        }
    }
}
```

This caps HFC consumption relative to baseline. Alternative refrigerants (low-GWP HFOs, CO$_2$, ammonia) replace HFCs.

### 6.3 Phase 2+: Full stock model (deferred)

Phase 2 adds a vintage-tracked HFC stock model:

```
HFC_stock(t) = HFC_stock(t-1) × (1 - disposal_rate) + new_equipment × charge_per_unit
HFC_emission(t) = HFC_stock(t) × annual_leakage_rate
```

| Parameter | Value | Source |
|-----------|-------|--------|
| Annual leakage rate | 5–10% of stock | IPCC/TEAP |
| Disposal recovery rate | 70% | UNEP |
| Charge per unit | ~0.5 kg/kW cooling capacity | Industry data |

This requires cooling **capacity** (kW) rather than cooling **energy** (EJ), plus refrigerant-specific vintage tracking. Not needed in Phase 1 since the Kigali schedule is the primary policy lever.


## 7. CCS and Negative Emissions

### 7.1 CCS capture

Each CCS technology has a `capture_rate` (0.0–0.95):

$$CO_2^{net} = CO_2^{gross} \times (1 - capture\_rate)$$

Captured CO$_2$ is tracked separately for:
- Storage requirement reporting (GtCO$_2$/yr)
- Storage cost ($/tCO$_2$) added to technology LCOE
- Storage capacity constraints (Phase 2+)

### 7.2 BECCS (negative emissions)

Biomass CCS technologies (biomass_ccs in electricity, biomass_gasification_ccs in hydrogen) produce **negative net CO$_2$**.

**Key insight**: biomass has two carbon coefficients:
- `carbon_coef = 0.0` (fossil carbon — zero, because biomass has no fossil carbon)
- `biogenic_coef = 0.0257` tC/GJ (physical biogenic carbon released on combustion)

Without CCS, net = 0 (carbon-neutral: biogenic CO$_2$ emitted but offset by regrowth). With CCS, captured biogenic CO$_2$ is sequestered underground → net removal from atmosphere:

$$CO_2^{net} = \underbrace{carbon\_coef \times (1 - capture)}_{\text{fossil (= 0 for biomass)}} - \underbrace{biogenic\_coef \times capture \times fuel\_input}_{\text{BECCS CDR (negative)}}$$

```python
# SupplyTech.annual_emissions_tc() for BECCS:
#   carbon_coef=0, biogenic_coef=0.0257, capture_rate=0.9
#   → net = 0 − 0.0257 × 0.9 × fuel_input = −0.0231 × fuel_input (tC/GJ)
#   → In tCO₂: −0.0231 × 44/12 = −0.0847 tCO₂/GJ

# Comparison:
# Biomass (no CCS):   net = 0 − 0 = 0  (carbon-neutral)
# Coal CCS:           net = 0.0257 × 0.1 = +0.00257 tC/GJ  (small positive)
# BECCS:              net = 0 − 0.0231 = −0.0231 tC/GJ     (NEGATIVE!)
```

**LCOE credit**: Under a carbon price $\tau$, BECCS earns a credit that reduces its LCOE:

$$LCOE_{BECCS} = capital + fuel + vom - \underbrace{biogenic\_coef \times TC\_TO\_TCO2 \times capture \times \tau / eff}_{\text{CDR revenue ($/GJ)}}$$

At $100/tCO₂, BECCS credit ≈ $8.5/GJ — significant enough to make BECCS competitive with fossil+CCS when carbon prices are high.

### 7.3 LULUCF and carbon removals

#### Net-Zero accounting (UNFCCC definition)

$$\text{Anthropogenic emissions} - \text{Anthropogenic removals} = 0$$

Natural sinks (ocean CO$_2$ absorption ~10.5 GtCO$_2$/yr, CO$_2$ fertilization ~11 GtCO$_2$/yr) are **not part of Net-Zero accounting**. They maintain the current atmospheric CO$_2$ but cannot offset additional anthropogenic emissions. Net-Zero requires that *human-caused* emissions balance *human-caused* removals.

| Component | Global (2021) | In Net-Zero? | Phase 1 | Phase 2+ |
|-----------|:-:|:---:|---|---|
| Fossil fuel + industry CO$_2$ | +36.8 GtCO$_2$ | ✅ | Model computes | Same |
| LULUCF (anthropogenic) | −0.35 GtCO$_2$ | ✅ | Exogenous (EDGAR R32) | AFOLU module |
| BECCS | ~0 | ✅ | Endogenous (biogenic_coef) | + Storage constraints |
| DAC | ~0 | ✅ | Not modeled | Phase 2+ technology |
| Ocean sink | −10.5 GtCO$_2$ | ❌ | Not included | Climate module (concentration only) |
| CO$_2$ fertilization | −11 GtCO$_2$ | ❌ | Not included | Climate module (concentration only) |

#### LULUCF data

Source: EDGAR 2025 GHG Booklet, `LULUCF_countries` sheet (2021 values), aggregated to GCAM R32 via `iso_GCAM_regID.csv`.

- **Deforestation**: +4.5 GtCO$_2$ (tropical: Indonesia, Brazil, Africa)
- **Managed forest regrowth**: −4.9 GtCO$_2$ (Russia, China, USA, Japan)
- **Net**: −0.35 GtCO$_2$ (roughly balanced globally)

Phase 1: fixed per-R32 values (see `implementation.md` §3.1 `LULUCF_NET_CO2`). Phase 2+: AFOLU module provides dynamic land-use change → LULUCF responds to policy (e.g., REDD+ reduces deforestation, afforestation programs increase absorption).


## 8. Policy Interactions

| Policy | Emission channel | Mechanism |
|--------|-----------------|-----------|
| Carbon tax | CO$_2$ combustion | Raises fuel cost → demand shift → lower emissions |
| Emissions cap | Total CO$_2$eq | Bisection finds carbon price that meets cap |
| Kigali phase-down | F-Gases | Caps HFC consumption schedule |
| Methane pledge | CH$_4$ | Reduction target → fugitive reduction cost curve |
| CCS subsidy | CO$_2$ capture | Lowers effective cost of CCS technologies |
| AEEI | All | Reduces energy intensity → less fuel → less emissions |

### 8.1 Emissions cap implementation

The emissions cap finds a carbon price endogenously:

```python
def find_carbon_price_for_cap(model, state, target_emissions):
    """Bisection: find carbon_price such that total_emissions ≤ target."""
    def emissions_at_price(p):
        model.policy.carbon_price = p
        solved = solver.solve(model, state)
        return solved.global_emissions_detail.co2eq / 1000.0  # Gt

    price = bisect(lambda p: emissions_at_price(p) - target_emissions,
                   0.0, MAX_CARBON_PRICE)
    return price
```


## 9. Reporting

### 9.1 IAMC format

| Variable | Gas | Unit |
|----------|-----|------|
| `Emissions\|CO2\|Energy` | CO$_2$ | Mt CO$_2$/yr |
| `Emissions\|CO2\|Energy\|Supply\|Electricity` | CO$_2$ | Mt CO$_2$/yr |
| `Emissions\|CO2\|Energy\|Demand\|Industry` | CO$_2$ | Mt CO$_2$/yr |
| `Emissions\|CO2\|Industrial Processes` | CO$_2$ | Mt CO$_2$/yr |
| `Emissions\|CH4\|Energy\|Supply` | CH$_4$ | Mt CH$_4$/yr |
| `Emissions\|CH4\|Fugitive` | CH$_4$ | Mt CH$_4$/yr |
| `Emissions\|CH4\|Agriculture` | CH$_4$ | Mt CH$_4$/yr |
| `Emissions\|CH4\|Waste` | CH$_4$ | Mt CH$_4$/yr |
| `Emissions\|N2O\|Agriculture` | N$_2$O | Mt N$_2$O/yr |
| `Emissions\|F-Gases` | HFC+PFC+SF$_6$ | Mt CO$_2$eq/yr |
| `Emissions\|Kyoto Gases` | All | Mt CO$_2$eq/yr |
| `Emissions\|CO2\|AFOLU` | CO$_2$ | Mt CO$_2$/yr |
| `Carbon Sequestration\|CCS` | CO$_2$ | Mt CO$_2$/yr |
| `Carbon Sequestration\|CCS\|Biomass` | CO$_2$ | Mt CO$_2$/yr |
| `Emissions\|CO2\|AFOLU\|LULUCF` | CO$_2$ | Mt CO$_2$/yr |

### 9.2 Decomposition by sector

`EmissionResult` tracks by gas. To decompose by sector, each sector returns its own `EmissionResult`. Aggregation:

```python
RegionState.emissions_by_sector: dict[str, EmissionResult]
# e.g., {"electricity": EmissionResult(...), "industry": EmissionResult(...), ...}
```


## 10. Data Requirements

### Base-year calibration

| Data | Source | Resolution |
|------|--------|------------|
| CO$_2$ from fuel combustion | IEA CO$_2$ Emissions | Country → R32 |
| CH$_4$ by source | EDGAR v8.0 | Gridded → R32 |
| N$_2$O by source | EDGAR v8.0 | Gridded → R32 |
| F-Gas by source | EDGAR v8.0 + UNEP | Country → R32 |
| Fugitive CH$_4$ factors | IPCC 2006 Guidelines | Global (Phase 1), regional (Phase 2) |
| Livestock/rice proxies | FAO | Country → R32 |
| HFC stock estimates | UNEP/TEAP | Country → R32 |


## 11. User Configurables

| Parameter | Default | Scope |
|-----------|---------|-------|
| CO$_2$ emission factors | IPCC 2006 defaults | Per fuel |
| CH$_4$ fugitive factors | Global average | Per fuel, per region (Phase 2) |
| GWP values | AR6 | Global |
| Agriculture income elasticity ($\alpha_{ag}$) | 0.3 | Global |
| Waste CH$_4$ per capita | EDGAR-derived | Per region |
| EDGAR F-gas base (per R32) | EDGAR v8.0 | MtCO$_2$eq per region |
| Kigali phase-down schedule | Default schedule | Policy JSON |
| BECCS gross emission factor | 0.10 tCO$_2$/GJ | Per biomass type |


## 12. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| CO$_2$ combustion | Full (all sectors) | Same |
| CCS capture | Full (capture_rate on SupplyTech) | + Storage constraints |
| CH$_4$ fugitive | Global-average factors | Regional factors |
| CH$_4$ agriculture | Production-index-scaled | AFOLU module feedback (separate indices) |
| CH$_4$ waste | Population-scaled | Income elasticity |
| N$_2$O agriculture | Production-index-scaled | AFOLU module feedback (separate indices) |
| N$_2$O combustion | Emission factors | Same |
| F-Gases | EDGAR base × cooling growth × Kigali | HFC stock-flow model |
| Industrial process CO$_2$ | Not included | Production × process factor |
| BECCS negative emissions | Full (biogenic_coef + capture) | + Storage cost curves |
| DAC | Not modeled | Technology in CO₂ removal sector |
| LULUCF sink | Exogenous fixed per-region | AFOLU module (dynamic) |
| Ocean sink | Exogenous fixed global | Climate module (CO₂-dependent) |
| Emissions cap | Bisection on carbon price | Same |

### Phase transition notes

- **Phase 1 → 2**: Regional CH$_4$ fugitive factors. Connect AFOLU module for agricultural emissions feedback. Add industrial process CO$_2$ (requires production tracking in Industry sector). Full HFC stock-flow model.
- **Phase 2 → 3**: Storage capacity constraints for CCS. Methane abatement cost curves (leak detection, flaring reduction). Country-level emission inventories.
