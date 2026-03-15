# GHIM Energy Module — OOP Implementation Design

## 1. Design Principles

1. **F(x) is king.** The entire model is a fixed-point problem $F(x^*) = x^*$. Every class exists to compute one piece of $F$. The solver orchestrates calls; sectors don't call each other.
2. **Shared state, not message passing.** Sectors read from and write to shared state objects. No direct sector-to-sector calls.
3. **Abstract base → concrete sectors.** Common interface for demand sectors and transformation sectors. New sectors plug in without changing the solver.
4. **External modules are swappable adapters.** Climate/Water/AFOLU each have an interface (ABC). Default adapter returns placeholder values. Real adapter wraps the external module's API.
5. **Region is a lightweight container.** `Region` groups its own `Economy`, demand sectors, transformation sectors, and resource endowments. `RegionState` holds all per-region mutable data. No scattered dicts keyed by region string — everything about a region lives in one place.
6. **Config is static, state is mutable.** `config.py` holds parameters (read-only). `RegionState` / `PeriodState` hold evolving model state (read-write per iteration).
7. **Carrier is an enum, not an object.** Carriers are identifiers that connect demand to supply. Dynamic properties (price, demand, supply) live in `RegionState`, not in the carrier itself.
8. **Vintage is optional composition.** `VintageTracker` attaches to technologies (EndUseTech / SupplyTech), not to carriers or sectors. `vintage: VintageTracker | None` — None means no vintage tracking.


## 2. Class Hierarchy

```
GHIMModel                                    # top-level orchestrator
├── Solver (ABC)                             # fixed-point solver
│   ├── DampedSolver                         # Phase 1: α·F(x) + (1-α)·x
│   ├── AndersonSolver                       # Phase 2: Anderson acceleration
│   └── NewtonKrylovSolver                   # Phase 3+: scipy wrapper
│
├── Region (×32)                             # lightweight container
│   ├── Economy                              # KLEM CES production function
│   ├── resources: {Carrier → ResourceSupply}  # fossil/uranium/biomass endowment
│   ├── DemandSector (ABC)                   # 5 final demand sectors
│   │   ├── IndustrySector                   # Subsector(EU) + Subsector(FS)
│   │   ├── BuildingsSector                  # Res/Com × Heating/Cooling/Other
│   │   ├── TransportSector                  # Passenger + Freight (Powertrain)
│   │   ├── AgricultureSector                # GDP-scaled, no vintage
│   │   └── BunkersSector                    # GDP-scaled, powertrain
│   └── TransformationSector (ABC)           # 5 secondary energy sectors
│       ├── ElectricitySector                # 17 SupplyTechs, LCOE logit
│       ├── HydrogenSector                   # 7 SupplyTechs, LCOH logit
│       ├── DistrictHeatingSector            # 4 SupplyTechs, LCOH logit
│       ├── BiofuelsSector                   # 3 SupplyTechs, LCOF logit
│       └── RefinedOilSector                 # 1 SupplyTech, pass-through
│
├── TradeModule                              # 5 commodities, bisection (global)
├── TechChange                               # learning curves + spillovers (global)
├── PolicyEngine                             # 13 policy instruments
│
└── ExternalInterface (ABC)                  # adapters for external modules
    ├── ClimateAdapter                       # ΔT, ΔP, HDD/CDD ↔ CO₂
    ├── WaterAdapter                         # cooling, hydro, water demand
    └── AFOLUAdapter                         # biomass supply, Q_ag, land
```


## 3. Core Data Classes

### 3.1 Carrier (Enum)

Identity only. No state, no behavior. Prevents typo-based silent bugs.

```python
from enum import Enum

class Carrier(str, Enum):
    ELECTRICITY = "electricity"
    GAS = "gas"
    COAL = "coal"
    LIQUIDS = "liquids"
    BIOMASS = "biomass"
    BIOFUEL = "biofuel"
    H2 = "h2"
    HEAT = "heat"
    OIL = "oil"           # primary (pre-refining)
    URANIUM = "uranium"    # primary

CARRIERS_7 = [Carrier.ELECTRICITY, Carrier.GAS, Carrier.COAL, Carrier.LIQUIDS,
              Carrier.BIOMASS, Carrier.BIOFUEL, Carrier.H2]
CARRIERS_8 = CARRIERS_7 + [Carrier.HEAT]

CARBON_COEFS = {
    # Direct combustion at demand side (tC/GJ of fuel)
    Carrier.COAL: 0.0257,      # ~94.6 kgCO₂/GJ
    Carrier.GAS: 0.0153,       # ~56.1 kgCO₂/GJ
    Carrier.LIQUIDS: 0.0200,   # ~73.3 kgCO₂/GJ (combustion by end user)
    Carrier.OIL: 0.0,          # carbon stays in product until refined → burned
    Carrier.BIOMASS: 0.0,      # carbon-neutral (biogenic)
    Carrier.BIOFUEL: 0.0,      # carbon-neutral
    Carrier.ELECTRICITY: 0.0,  # indirect (counted at generation via SupplyTech.carbon_coef)
    Carrier.H2: 0.0,           # indirect (counted at production via SupplyTech.carbon_coef)
    Carrier.HEAT: 0.0,         # indirect (counted at generation via SupplyTech.carbon_coef)
    Carrier.URANIUM: 0.0,
}

# Fugitive CH₄ from fossil production (tCH₄/EJ produced)
CH4_FUGITIVE = {
    Carrier.COAL: 0.37e6,      # coal mining
    Carrier.OIL:  0.12e6,      # oil production + processing
    Carrier.GAS:  0.22e6,      # gas production + processing + T&D
}

# GWP₁₀₀ values (AR6, Forster et al. 2021)
GWP100 = {"ch4": 27.9, "n2o": 273, "hfc": 1530}

# ---------------------------------------------------------------------------
# LULUCF anthropogenic emissions (exogenous, Phase 1)
# Source: EDGAR 2025 GHG Booklet, LULUCF_countries sheet, 2021 values
#         Aggregated to GCAM R32 via iso_GCAM_regID.csv
# Positive = net emission, Negative = net absorption (managed forest regrowth)
# Global net ≈ −0.35 GtCO₂ (anthropogenic LULUCF roughly balanced)
#
# IMPORTANT: This is the ANTHROPOGENIC component only (deforestation, managed
# forest regrowth, fires). Does NOT include natural sinks (ocean absorption,
# CO₂ fertilization effect). Natural sinks are irrelevant for Net-Zero
# accounting (UNFCCC: anthropogenic emissions − anthropogenic removals = 0).
# Phase 2+: replaced by AFOLU module (dynamic land-use change).
# ---------------------------------------------------------------------------
LULUCF_NET_CO2: dict[str, float] = {
    # GtCO₂/yr, 2021, EDGAR v8.0
    "USA":               -0.41,
    "Africa_Eastern":     0.64,
    "Africa_Northern":    0.04,
    "Africa_Southern":    0.15,
    "Africa_Western":    -0.27,
    "Australia_NZ":      -0.04,
    "Brazil":             0.42,
    "Canada":            -0.15,
    "Central America and Caribbean": -0.26,
    "Central Asia":      -0.08,
    "China":             -0.85,
    "EU-12":             -0.04,
    "EU-15":             -0.09,
    "Ukraine":           -0.01,
    "Europe_Non_EU":     -0.07,
    "European Free Trade Association": -0.02,
    "India":              0.74,
    "Indonesia":          1.24,
    "Japan":             -0.24,
    "Mexico":            -0.23,
    "Middle East":        0.00,
    "Pakistan":           0.05,
    "Russia":            -1.57,
    "South Africa":       0.15,
    "South America_Northern": -0.15,
    "South America_Southern":  0.05,
    "South Asia":         0.25,
    "South Korea":       -0.03,
    "Southeast Asia":     0.59,
    "Taiwan":            -0.01,
    "Argentina":         -0.04,
    "Colombia":          -0.11,
}
# Sum = −0.35 GtCO₂ (global anthropogenic LULUCF net, 2021)

TC_TO_TCO2 = 44.0 / 12.0      # tC → tCO₂
```

### 3.2 VintageTracker

Optional composition — attaches to any technology that needs vintage tracking. Handles S-curve retirement, profit shutdown, and construction pipeline. See `vintage_stock.md` for full design.

```python
@dataclass
class VintageTracker:
    """Vintage state + retirement/shutdown logic."""

    # Retirement config
    retirement_type: str = "s_curve"      # "s_curve" | "hard_cutoff"
    k: float = 0.1                        # steepness
    rho: float = 0.75                     # half-life ratio

    # Profit shutdown config
    shutdown_enabled: bool = True         # False for solar, wind, BEV (zero fuel cost)
    shutdown_median: float = -0.1         # m (50% shutdown point)
    shutdown_steepness: float = 6         # n

    # Construction pipeline config
    construction_delay: int = 0           # periods (nuclear=2, hydro=1, others=0)

    # Mutable state
    bins: dict[int, float] = field(default_factory=dict)      # install_year → EJ
    pipeline: dict[int, float] = field(default_factory=dict)  # delivery_year → EJ

    def surviving(self, current_year: int, lifetime: int) -> float:
        """Total surviving capacity after S-curve/hard-cutoff retirement."""
        ...

    def operating(self, current_year: int, lifetime: int, profit_rate: float) -> float:
        """Surviving × P(π). Reversible shutdown on top of physical retirement."""
        phys = self.surviving(current_year, lifetime)
        if not self.shutdown_enabled:
            return phys
        p_operate = 1.0 / (1.0 + math.exp(-self.shutdown_steepness * (profit_rate - self.shutdown_median)))
        return phys * p_operate

    def invest(self, year: int, amount: float) -> None:
        """Add new capacity. Respects construction delay."""
        if self.construction_delay > 0:
            delivery = year + self.construction_delay * TIMESTEP
            self.pipeline[delivery] = self.pipeline.get(delivery, 0.0) + amount
        else:
            self.bins[year] = self.bins.get(year, 0.0) + amount

    def deliver_pipeline(self, year: int) -> None:
        """Move pipeline capacity to bins when construction completes."""
        if year in self.pipeline:
            self.bins[year] = self.bins.get(year, 0.0) + self.pipeline.pop(year)

    def initialize_uniform(self, total: float, lifetime: int, base_year: int) -> None:
        """Create uniform vintage distribution so surviving = total at base_year."""
        ...
```

### 3.3 EndUseTech

Demand-side technology. 1:1 carrier mapping. Name defaults to carrier name; overridable for future sub-technology split.

```python
@dataclass
class EndUseTech:
    """Demand-side technology choice within a Subsector."""
    carrier: Carrier
    efficiency: float = 1.0              # service output / GJ input
    capex: float = 0.0                   # $/GJ-capacity annualized
    lifetime: int = 25                   # years
    fom: float = 0.0                     # fixed O&M $/GJ/yr
    name: str = ""                       # default: carrier name

    vintage: VintageTracker | None = None  # None = no vintage tracking

    def __post_init__(self):
        if not self.name:
            self.name = self.carrier.value

    def levelized_cost(self, carrier_price: float) -> float:
        """Cost per GJ of service."""
        return self.capex + carrier_price / self.efficiency + self.fom
```

Phase 1 degenerate case: `capex=0, eff=1.0` → `levelized_cost = carrier_price` (equivalent to carrier-level logit).

### 3.4 SupplyTech

Supply-side technology for transformation sectors. Has fuel input, carrier output, and richer cost structure (VOM, capacity factor, carbon coefficient, learning rate).

```python
@dataclass
class SupplyTech:
    """Supply-side technology (electricity, hydrogen, heat, biofuel, refining)."""
    name: str
    fuel_input: Carrier               # primary fuel consumed
    carrier_output: Carrier            # carrier produced
    efficiency: float                  # output/input ratio
    capex: float                       # $/kW
    fom: float = 0.0                   # fixed O&M $/kW/yr
    vom: float = 0.0                   # variable O&M $/GJ
    capacity_factor: float = 1.0       # annual average
    lifetime: int = 30                 # years
    carbon_coef: float = 0.0           # tC/GJ fuel input (fossil carbon)
    biogenic_coef: float = 0.0         # tC/GJ fuel input (biogenic carbon, for BECCS)
    capture_rate: float = 0.0          # CCS fraction (0.0–0.95)
    learning_rate: float = 0.0         # LBD rate (0-1)
    base_cumulative: float = 0.0       # GW at base year (for learning)

    vintage: VintageTracker | None = None

    def lcoe(self, raw_fuel_prices: dict[str, float], carbon_price: float = 0.0) -> float:
        """Levelized cost of energy ($/GJ output).

        IMPORTANT: Takes raw fuel prices (from trade clearing, no carbon tax).
        Carbon cost is added explicitly via self.carbon_coef — supports CCS
        (capture_rate reduces carbon cost).  Demand sectors handle their own
        carbon cost through CARBON_COEFS on consumer-facing carrier_prices.

        BECCS credit: if biogenic_coef > 0, captured biogenic carbon earns
        a negative emission credit (revenue at carbon_price per tCO₂ removed).
        """
        fuel_cost = raw_fuel_prices.get(self.fuel_input, 0.0) / self.efficiency
        # Fossil carbon cost (reduced by CCS capture)
        carbon_cost = (self.carbon_coef * TC_TO_TCO2
                       * (1 - self.capture_rate) * carbon_price / self.efficiency)
        # BECCS credit: captured biogenic carbon → negative emission → revenue
        beccs_credit = (self.biogenic_coef * TC_TO_TCO2
                        * self.capture_rate * carbon_price / self.efficiency)
        capital = self.capex / (self.capacity_factor * HOURS_PER_YEAR * GJ_PER_KWH)
        return capital + self.fom + fuel_cost + carbon_cost - beccs_credit + self.vom

    def annual_emissions_tc(self, fuel_input_ej: float) -> float:
        """Net CO₂ emissions (MtC). Negative for BECCS.

        fossil_net  = carbon_coef × (1 − capture_rate) × fuel_input  (≥ 0)
        biogenic_net = −biogenic_coef × capture_rate × fuel_input     (≤ 0)
        total = fossil_net + biogenic_net

        Biomass without CCS:  carbon_coef=0, biogenic_coef=0.0257, capture_rate=0
          → net = 0 − 0 = 0  (carbon-neutral)
        BECCS (biomass + CCS): carbon_coef=0, biogenic_coef=0.0257, capture_rate=0.9
          → net = 0 − 0.0257 × 0.9 × fuel = −0.0231 × fuel  (negative!)
        Coal CCS:  carbon_coef=0.0257, biogenic_coef=0, capture_rate=0.9
          → net = 0.0257 × 0.1 × fuel = +0.00257 × fuel  (small positive)
        """
        fossil_net = self.carbon_coef * (1 - self.capture_rate) * fuel_input_ej
        biogenic_net = -self.biogenic_coef * self.capture_rate * fuel_input_ej
        return fossil_net + biogenic_net
```

### 3.5 Powertrain

Transport-specific extension of EndUseTech. Adds km-based fields for LCOT calculation.

```python
@dataclass
class Powertrain(EndUseTech):
    """Transport powertrain. 1:1 carrier mapping, LCOT-based competition."""
    annual_service: float = 15000.0      # km/yr
    capex_vehicle: float = 0.0           # $/vehicle

    def lcot(self, carrier_price: float) -> float:
        """Levelized cost of transport ($/km)."""
        fuel = carrier_price / self.efficiency  # $/GJ-service
        capital = self.capex_vehicle / (self.annual_service * self.lifetime)
        return capital + fuel * GJ_PER_KM + self.fom / self.annual_service
```

### 3.6 Subsector

Groups EndUseTechs within a demand sector. Handles logit competition and vintage-aware gap-filling.

```python
@dataclass
class Subsector:
    """A group of competing EndUseTechs within a demand sector."""
    name: str
    techs: list[EndUseTech]
    pref_factors: np.ndarray | None = None
    last_shares: dict[str, float] | None = None   # cached from most recent compute_shares()

    def compute_shares(self, prices: dict[Carrier, float], policy: PolicyEngine) -> dict[str, float]:
        """Logit competition on levelized cost. Returns {tech.name: share}.

        Canonical logit formula:
            S_i = α_i · exp(β·(C_i + p_i)) / Σ_j α_j · exp(β·(C_j + p_j))

        where:
            α_i = availability {0, 1} (from TechAvailability policy)
            p_i = preference factor $/GJ (calibrated at base year, decays over time)
            β < 0 = cost sensitivity parameter
            C_i = levelized cost $/GJ
        """
        costs = np.array([t.levelized_cost(prices.get(t.carrier, 5.0)) for t in self.techs])
        pf = self._decayed_pref_factors(rs.period)
        raw_shares = preference_logit(costs, pf, beta=self.beta)

        # Apply vintage if any tech has tracker
        if any(t.vintage is not None for t in self.techs):
            result = self._vintage_adjust(raw_shares, ...)
        else:
            result = {t.name: s for t, s in zip(self.techs, raw_shares)}
        self.last_shares = result   # cache for price_index()
        return result

    def _vintage_adjust(self, target_shares, total_demand, period, prices):
        """Gap-fill: target - surviving → new investment. See vintage_stock.md §5."""
        actual = {}
        for t, target_s in zip(self.techs, target_shares):
            target = target_s * total_demand
            if t.vintage is not None:
                surviving = t.vintage.operating(period, t.lifetime, self._profit(t, prices))
                gap = target - surviving
                if gap > 0:
                    t.vintage.invest(period, gap)
                actual[t.name] = min(target, surviving + max(gap, 0))
            else:
                actual[t.name] = target
        return actual

    def carrier_demands(self, shares: dict[str, float], total_demand: float) -> dict[Carrier, float]:
        """Convert tech shares → carrier demands (EJ)."""
        result: dict[Carrier, float] = {}
        for t in self.techs:
            ej = shares.get(t.name, 0.0) / t.efficiency  # service → fuel
            result[t.carrier] = result.get(t.carrier, 0.0) + ej
        return result

    def price_index(self, prices: dict[Carrier, float]) -> float:
        """Share-weighted average cost of energy service in this subsector.

        P_sub = Σ_i (share_i × levelized_cost_i)

        Uses last_shares from most recent compute_shares() call.
        """
        if self.last_shares is None:
            return 5.0
        return sum(
            self.last_shares.get(t.name, 0.0) * t.levelized_cost(prices.get(t.carrier, 5.0))
            for t in self.techs
        )

    def calibrate(self, base_shares: dict[str, float], base_prices: dict[Carrier, float]) -> None:
        """Calibrate pref_factors from base-year shares and prices."""
        ...

    def _decayed_pref_factors(self, year: int) -> np.ndarray:
        """Apply exponential preference decay.

        p_i(t) = p_i(base) × (1 − decay_rate_i)^(t − t_base)

        Decay captures non-cost adoption barriers shrinking over time:
        familiarity, infrastructure build-out, behavioral inertia.
        """
        years = max(year - BASE_YEAR, 0)
        return np.array([
            pf * (1 - CARRIER_PREF_DECAY_RATES.get(t.carrier, 0.0)) ** years
            for t, pf in zip(self.techs, self.pref_factors)
        ])
```

**Carrier-level preference decay rates** (demand-side, annual):

| Carrier | Decay rate | Rationale |
|---------|-----------|-----------|
| Electricity | 0.02 | Electrification familiarity, charging infra |
| Hydrogen | 0.03 | New carrier, rapid learning curve |
| Biofuels | 0.02 | Drop-in fuel, moderate distribution barriers |
| Gas | 0.00 | Mature network |
| Coal | 0.00 | Mature |
| Refined liquids | 0.00 | Mature |
| Solid biomass | 0.00 | Traditional |
| Heat | 0.00 | Mature district heating infra |

These are **carrier-level** rates applied uniformly across demand sectors. Supply-side
technologies have separate, technology-specific decay rates (see §5.2 ElectricitySector,
§5.4 HydrogenSector). Both decay mechanisms are independent and additive in effect:
supply-side decay makes the technology cheaper in "soft cost" terms, demand-side decay
makes the carrier more acceptable to end users.

### 3.7 ResourceSupply

Per-region per-fuel supply curve. Belongs to Region (resource endowment is a regional property).

```python
@dataclass
class ResourceSupply:
    """Grade-based supply curve for one fuel in one region."""
    fuel: Carrier
    grades: list[tuple[float, float]]    # [(cost $/GJ, cumulative EJ), ...]
    max_annual_production: float         # EJ/yr cap
    transport_cost: float = 0.0          # $/GJ (region → world market)

    def production_at_price(self, price: float) -> float:
        """Piecewise-linear interpolation between grades."""
        ...

    def deplete(self, production: float) -> None:
        """Reduce available grades after extraction."""
        ...
```

### 3.8 Region

Lightweight container — groups a region's structural components. No computation logic.

```python
@dataclass
class Region:
    """A single GCAM-style region with its own sectors and resource endowment."""
    name: str
    economy: Economy
    demand_sectors: list[DemandSector]
    transformation: list[TransformationSector]
    resources: dict[Carrier, ResourceSupply] = field(default_factory=dict)
```

### 3.9 RegionState

All mutable per-region data for one period.

```python
@dataclass
class RegionState:
    """Per-region model state for one period."""

    # Economy
    gdp: float = 0.0                        # billion USD PPP
    population: float = 0.0                  # millions
    value_added: float = 0.0                 # VA
    capital_stock: float = 0.0               # K (billion USD)
    investment: float = 0.0                  # I (billion USD/yr)
    tfp: float = 1.0

    # Prices (two channels: raw for supply, consumer for demand)
    raw_fuel_prices: dict[Carrier, float] = field(default_factory=dict)   # trade-clearing, no carbon tax
    carrier_prices: dict[Carrier, float] = field(default_factory=dict)    # consumer-facing, carbon-inclusive
    sector_prices: dict[str, float] = field(default_factory=dict)         # sector → $/GJ (share-weighted)
    composite_energy_price: float = 5.0      # expenditure-weighted $/GJ, carbon-inclusive (for CES FOC)

    # Demands
    final_demand: dict[str, float] = field(default_factory=dict)     # carrier → EJ
    sector_demand: dict[str, dict[str, float]] = field(default_factory=dict)

    # Supply
    generation: dict[str, dict[str, float]] = field(default_factory=dict)  # carrier → tech → EJ

    # Trade
    net_exports: dict[str, float] = field(default_factory=dict)
    regional_production: dict[str, float] = field(default_factory=dict)

    # Emissions
    emissions: float = 0.0                   # MtCO₂eq (total)
    emissions_detail: EmissionResult = field(default_factory=EmissionResult)

    # External module outputs
    temperature_anomaly: float = 0.0
    precip_anomaly: float = 0.0
    hdd: float = 0.0
    cdd: float = 0.0
    cooling_water_avail: float = float('inf')
    hydro_water_fraction: float = 1.0
    water_energy_demand: float = 0.0
    biomass_supply: list = field(default_factory=list)
    ag_output: float = 0.0
```

### 3.10 PeriodState

Top-level state: all RegionStates + global fields.

```python
@dataclass
class PeriodState:
    """Full model state for one period."""
    period: int
    regions: dict[str, RegionState]

    # Global
    world_prices: dict[Carrier, float] = field(default_factory=dict)
    global_emissions: float = 0.0              # GtCO₂eq
    global_emissions_detail: EmissionResult = field(default_factory=EmissionResult)
```


### 3.11 Economy

Three-level CES production function for one region. Config and calibrated reference data are **immutable after initialization**. Mutable state (K, TFP, L, VA, GDP, I) lives in `RegionState`, not in Economy.

**Nesting structure (Phase 1):**

```
KL  = TFP × K^α × L^(1-α)              Cobb-Douglas (σ_KL = 1.0)
E   = CES(EL, NEL; σ_EL_NEL = 1.0)     Energy composite
KLE = CES(KL, E_val; σ_KLE = 0.4)       Energized factor services
Q   = CES(KLE, M; σ_KLE_M ≈ 0.2)       Gross output (M = m·Q, exogenous)
Y   = Q − p_E·E − p_M·M                 Net output = GDP
```

Phase 1: `M = m·Q` (exogenous, GDP-proportional). `Y = Q − p_E·E − p_M·M`. Phase 2+ makes M endogenous via industry subsectors.

```python
@dataclass
class Economy:
    """Three-level nested CES production function.

    Level 1:  KL  = TFP × K^α × L^(1-α)              (Cobb-Douglas, σ_KL=1.0)
    Level 2:  E   = CES(EL, NEL; σ_EL_NEL)            (energy composite)
              KLE = A_CES × CES(KL, E_val; σ_KLE)     (energized factors)
    Level 3:  Q   = CES(KLE, M; σ_KLE_M)  (Phase 1: M = m·Q, exogenous)
              Y   = Q − p_E·E − p_M·M                 (net output = GDP)

    Energy demand (CES FOC at KL-E nest):
        E = E_base × (KL/KL_base) × (p_E/p_E_base)^(-σ_KLE)

    EL/NEL split (CES FOC at E nest):
        EL = EL_base × (E/E_base) × (p_EL/p_EL_base)^(-σ_EL_NEL)

    Budget constraint:
        I_K = s × Y − I_E − Σ_i I_RND,i
        I_K ≥ 0              (energy + RND investment cannot exceed savings)
    """

    # ── Config (immutable after __init__) ──
    alpha: float = 0.3                         # capital share (Cobb-Douglas)
    savings_rate: float = 0.22                 # World Bank global average
    sigma_kl: float = 1.0                      # K-L: Cobb-Douglas (WITCH, EPPA, DICE)
    sigma_kle: float = 0.4                     # KL-E: complements (REMIND=0.5, EPPA=0.4)
    sigma_el_nel: float = 2.0                  # EL-NEL: substitutes (Zhu et al. 2023, GTAP-E)
    depreciation: float = 0.05                 # PWT standard, 5%/yr
    lfp: float = 0.65                          # labor force participation

    # ── Base-year reference (set during calibrate()) ──
    base_gdp: float = 0.0                     # billion USD PPP (= net output Y)
    base_gross_output: float = 0.0            # Q = Y + p_E·E
    base_population: float = 0.0              # millions
    base_energy: float = 0.0                  # EJ (total)
    base_el: float = 0.0                      # EJ (electricity)
    base_nel: float = 0.0                     # EJ (non-electric)
    base_energy_price: float = 5.0            # $/GJ (composite p_E)
    base_el_price: float = 20.0               # $/GJ (electricity)
    base_nel_price: float = 5.0               # $/GJ (non-electric)
    base_energy_value: float = 0.0            # E × p_E_base (billion USD)

    # ── CES internals (calibrated, immutable) ──
    _ces_alphas_e: np.ndarray = ...           # E-nest share params (EL, NEL)
    _ces_alphas_kle: np.ndarray = ...         # KLE-nest share params (KL, E_val)
    _ces_scale: float = 1.0                   # A_CES scale factor

    # ── TFP trajectory (calibrated from SSP, immutable after init) ──
    tfp_trajectory: dict[int, float] = field(default_factory=dict)

    # ================================================================
    # Calibration (called once at model setup)
    # ================================================================

    def calibrate(
        self,
        base_gdp: float,
        base_pop: float,
        base_energy_ej: float,
        base_energy_price: float,
        region_name: str,
    ) -> float:
        """Calibrate CES alphas, scale factor, and base-year TFP.

        Returns initial capital stock K₀ (for RegionState).
        """
        self.lfp = REGIONAL_LFP.get(region_name, LABOR_FORCE_PARTICIPATION)
        self.base_gdp = base_gdp
        self.base_population = base_pop
        self.base_energy = base_energy_ej
        self.base_energy_price = max(base_energy_price, 0.01)
        self.base_energy_value = base_energy_ej * self.base_energy_price

        # Initial capital from K/Y ratio
        k0 = base_gdp * CAPITAL_OUTPUT_RATIO
        l0 = base_pop * self.lfp

        # Inner CES: factor prices from competitive equilibrium
        r = self.alpha * base_gdp / k0          # rental rate
        w = (1 - self.alpha) * base_gdp / l0    # wage rate
        self._ces_alphas_kl = ces_calibrate([k0, l0], [r, w], self.sigma_kl)

        # Outer CES: VA and E_val both in billion USD
        self._ces_alphas = ces_calibrate(
            [base_gdp, self.base_energy_value], [1.0, 1.0], self.sigma_kle
        )
        ces_raw = ces_output(
            [base_gdp, self.base_energy_value],
            self._ces_alphas, self.sigma_kle, scale=1.0,
        )
        self._ces_scale = base_gdp / ces_raw

        # Iteratively solve TFP: CES(TFP × CES_KL, E_val) = GDP
        kl = self._ces_kl(k0, l0)
        self.tfp_trajectory[BASE_YEAR] = self._solve_tfp(kl, self.base_energy_value, base_gdp)

        # Energy cost share
        self.base_energy_cost_share = max(
            base_energy_price * base_energy_ej / base_gdp, MIN_ENERGY_COST_SHARE,
        )
        return k0

    def calibrate_tfp_trajectory(
        self,
        ssp_gdp: dict[int, float],
        pop: dict[int, float],
    ) -> None:
        """Pre-compute TFP for all future years from SSP GDP path.

        Forward-only algorithm:
        1. A(BASE_YEAR) already calibrated in calibrate().
        2. Evolve reference K forward: K(t+dt) = (1-δ)^dt K + s·Y_SSP·dt.
        3. At each year, solve A(t) s.t. CES(A·CES_KL, E_ref) = Y_SSP.

        Reference energy: E_ref = E_base × (Y_SSP / Y_base) (income scaling,
        no price shocks in reference).
        """
        decay = (1 - DEPRECIATION_RATE) ** TIMESTEP
        k_ref = self.base_gdp * CAPITAL_OUTPUT_RATIO

        for year in FUTURE_YEARS:
            prev_y = ssp_gdp.get(year - TIMESTEP, self.base_gdp)
            inv_ref = min(self.savings_rate * prev_y, self.investment_cap_rate * k_ref)
            k_ref = decay * k_ref + inv_ref * TIMESTEP

            y_ssp = ssp_gdp.get(year, self.base_gdp)
            labor = pop.get(year, self.base_population) * self.lfp

            kl = self._ces_kl(k_ref, labor)
            e_ref = self.base_energy * (y_ssp / self.base_gdp)
            e_val = e_ref * self.base_energy_price
            self.tfp_trajectory[year] = self._solve_tfp(kl, e_val, y_ssp)

    # ================================================================
    # Intra-period (called inside F(x), reads/writes RegionState)
    # ================================================================

    def compute_value_added(self, rs: RegionState) -> float:
        """VA = TFP × CES(K, L; σ_KL).

        Sets rs.labor, rs.tfp, rs.value_added.
        """
        rs.labor = rs.population * self.lfp
        rs.tfp = self.tfp_trajectory.get(rs.period, rs.tfp)
        va = rs.tfp * self._ces_kl(rs.capital_stock, rs.labor)
        rs.value_added = va
        return va

    def compute_energy_demand(self, rs: RegionState) -> float:
        """CES FOC: E = E_base × (VA/VA_base) × (P_E/P_E_base)^(-σ_KLE).

        Uses rs.value_added and rs.composite_energy_price.
        """
        va_ratio = rs.value_added / self.base_gdp if self.base_gdp > 0 else 1.0
        price_ratio = max(rs.composite_energy_price / self.base_energy_price, 0.01)
        return self.base_energy * va_ratio * price_ratio ** (-self.sigma_kle)

    def compute_gross_output(self, rs: RegionState, energy_ej: float) -> float:
        """Y = A_CES × CES(VA, E_val; σ_KLE).

        Sets rs.gdp.
        """
        e_val = energy_ej * self.base_energy_price
        y = ces_output(
            [rs.value_added, max(e_val, 0.01)],
            self._ces_alphas, self.sigma_kle, scale=self._ces_scale,
        )
        rs.gdp = y
        return y

    def compute_investment(self, rs: RegionState) -> float:
        """I = min(s × Y, cap_rate × K).

        Sets rs.investment. No energy cost subtraction — energy's
        effect on GDP captured through CES production function.
        """
        inv = min(self.savings_rate * rs.gdp,
                  self.investment_cap_rate * rs.capital_stock)
        rs.investment = inv
        return inv

    @staticmethod
    def composite_energy_price(
        carrier_prices: dict[Carrier, float],
        carrier_demands: dict[Carrier, float],
    ) -> float:
        """Expenditure-weighted composite energy price ($/GJ)."""
        total_cost = sum(carrier_prices.get(c, 5.0) * d
                         for c, d in carrier_demands.items())
        total_ej = sum(carrier_demands.values())
        return total_cost / total_ej if total_ej > 0 else 5.0

    # ================================================================
    # Inter-period (called BETWEEN periods, NOT inside F)
    # ================================================================

    def update_capital(self, rs: RegionState) -> None:
        """K(t+dt) = (1-δ)^dt × K + I × dt.

        Modifies rs.capital_stock in place.
        """
        decay = (1 - DEPRECIATION_RATE) ** TIMESTEP
        rs.capital_stock = decay * rs.capital_stock + rs.investment * TIMESTEP

    # ================================================================
    # Diagnostic (not used for investment)
    # ================================================================

    @staticmethod
    def energy_cost(energy_ej: float, price: float) -> float:
        """P_E × E in billion USD. Diagnostic only."""
        return energy_ej * price

    @staticmethod
    def energy_cost_share(energy_ej: float, price: float, gdp: float) -> float:
        """s_E = P_E × E / Y. Diagnostic only."""
        return energy_ej * price / gdp if gdp > 0 else 0.0

    # ================================================================
    # Internal helpers
    # ================================================================

    def _ces_kl(self, capital: float, labor: float) -> float:
        """Inner CES: CES(K, L; σ_KL)."""
        return ces_output([capital, labor], self._ces_alphas_kl, self.sigma_kl)

    def _solve_tfp(self, kl: float, e_val: float, target_y: float) -> float:
        """Newton-like TFP solve: find A s.t. CES(A×kl, e_val) = target_y."""
        if kl <= 0:
            return 1.0
        tfp = target_y / kl
        for _ in range(10):
            va = tfp * kl
            y = ces_output([va, max(e_val, 0.01)],
                           self._ces_alphas, self.sigma_kle, scale=self._ces_scale)
            if abs(y - target_y) / max(target_y, 1e-10) < 1e-10:
                break
            if y > 0:
                tfp *= target_y / y
        return tfp
```

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| Mutable state in `RegionState`, not `Economy` | Principle #6: config static, state mutable. Economy is config + calibration. |
| Methods take `rs: RegionState` | Principle #2: shared state. Economy reads/writes the same state object as sectors. |
| `calibrate()` returns `K₀` | Initial capital stock must be set on `RegionState` by the caller (model setup). |
| `tfp_trajectory` is `dict[int, float]` | Pre-computed once, immutable during solve. Lookup by period in `compute_value_added`. |
| `compute_*` methods set `rs.*` fields | Side effects are explicit: `compute_value_added` sets `rs.value_added`, etc. |
| `update_capital(rs)` is inter-period | Called in the run loop after `solver.solve()`, not inside `F(x)`. |
| `composite_energy_price` is `@staticmethod` | Pure function: prices × demands → scalar. No Economy state needed. |
| Diagnostic methods are `@staticmethod` | `energy_cost`, `energy_cost_share` for reporting only, not used in the solve loop. |

**Mapping from current `KLEMDriver` to new `Economy`:**

| Current `KLEMDriver` | New `Economy` | Change |
|----------------------|---------------|--------|
| `__init__(base_gdp, ...)` | `calibrate(base_gdp, ...)` | Separated from construction |
| `self.capital_stock` | `rs.capital_stock` | Moved to RegionState |
| `self.tfp` | `rs.tfp` (current), `self.tfp_trajectory` (all) | Split: trajectory is config, current is state |
| `self.labor` | `rs.labor` | Moved to RegionState |
| `set_tfp_for_year(year)` | Implicit in `compute_value_added(rs)` | Lookup from trajectory, write to rs |
| `compute_value_added(pop)` | `compute_value_added(rs)` | Reads rs.population, writes rs.value_added |
| `compute_energy_demand(va, price)` | `compute_energy_demand(rs)` | Reads rs.value_added, rs.composite_energy_price |
| `compute_gross_output(va, e)` | `compute_gross_output(rs, e)` | Reads rs.value_added, writes rs.gdp |
| `compute_investment(gross)` | `compute_investment(rs)` | Reads rs.gdp, writes rs.investment |
| `update_capital(inv)` | `update_capital(rs)` | Reads/writes rs.capital_stock |
| `init_tfp_trajectory(...)` | `calibrate_tfp_trajectory(...)` | Same algorithm, renamed for clarity |


## 4. Abstract Base Classes

### 4.1 DemandSector

```python
class DemandSector(ABC):
    """Base class for final energy demand sectors.

    Every demand sector follows the same two-stage pattern:
    1. demand_envelope() → total sector energy (EJ), from GDP + price response
    2. compute_demand()  → carrier allocation via Subsector logit

    Price index flows bottom-up:
        EndUseTech.levelized_cost → Subsector.price_index → sector_price_index → P_E
    """

    subsectors: list[Subsector]

    # ── Demand driver parameters (set during calibrate()) ──
    base_demand: float = 0.0           # EJ at base year
    base_gdp: float = 0.0             # billion USD PPP at base year
    base_price: float = 5.0           # sector price index $/GJ at base year
    income_elasticity: float = 0.5    # α: GDP elasticity of demand
    price_elasticity: float = -0.3    # γ: own-price elasticity (negative)

    # ================================================================
    # Price index (bottom-up aggregation)
    # ================================================================

    def sector_price_index(self, rs: RegionState) -> float:
        """Demand-weighted average price across subsectors.

        P_sector = Σ_sub (E_sub / E_total) × P_sub

        where P_sub = Σ_i (share_i × levelized_cost_i).
        """
        total_e = 0.0
        weighted_p = 0.0
        for sub in self.subsectors:
            e_sub = sum(rs.sector_demand.get(sub.name, {}).values())
            p_sub = sub.price_index(rs.carrier_prices)
            weighted_p += e_sub * p_sub
            total_e += e_sub
        return weighted_p / total_e if total_e > 0 else self.base_price

    # ================================================================
    # Demand envelope (common pattern)
    # ================================================================

    def demand_envelope(self, rs: RegionState) -> float:
        """Total sector energy demand (EJ) before carrier allocation.

        E = base × (GDP/GDP_base)^α × (P_sector/P_sector_base)^γ

        GDP drives the level; sector price index provides demand response.
        Overridable for sectors with custom drivers (e.g., Buildings uses HDD/CDD).
        """
        gdp_ratio = rs.gdp / self.base_gdp if self.base_gdp > 0 else 1.0
        price_ratio = max(self.sector_price_index(rs) / self.base_price, 0.01)
        return self.base_demand * gdp_ratio ** self.income_elasticity \
                                * price_ratio ** self.price_elasticity

    # ================================================================
    # Abstract methods
    # ================================================================

    @abstractmethod
    def compute_demand(self, rs: RegionState, policy: PolicyEngine) -> dict[Carrier, float]:
        """Compute carrier demands (EJ). Returns {carrier: EJ}.

        Typical implementation:
            total = self.demand_envelope(rs)
            shares = subsector.compute_shares(rs.carrier_prices, policy)
            return subsector.carrier_demands(shares, total)
        """
        ...

    @abstractmethod
    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        """Combustion + sector-specific non-energy emissions."""
        ...

    @abstractmethod
    def calibrate(self, base_demands: dict[Carrier, float],
                  base_prices: dict[Carrier, float], base_gdp: float) -> None:
        """Calibrate preference factors, base_demand, base_price."""
        ...
```

**Sector-specific elasticities:**

| Sector | α (income) | γ (price) | Notes |
|--------|-----------|-----------|-------|
| Industry | 0.6 | −0.4 | Heavy industry energy-intensive |
| Buildings | 0.5 | −0.3 | Override `demand_envelope` for HDD/CDD |
| Transport | 0.7 | −0.4 | High income elasticity, moderate price response |
| Agriculture | 0.3 | −0.2 | Engel's law (low), inelastic to price |
| Bunkers | 0.6 | −0.2 | World-GDP-driven, captive demand |

### 4.2 TransformationSector

```python
class TransformationSector(ABC):
    """Base class for secondary energy production sectors.
    Contains SupplyTechs with optional VintageTrackers."""

    carrier_output: Carrier
    techs: list[SupplyTech]

    @abstractmethod
    def compute_supply(self, rs: RegionState, demand_ej: float, policy: PolicyEngine) -> dict[str, float]:
        """Compute generation (tech_name → EJ)."""
        ...

    @abstractmethod
    def compute_price(self, rs: RegionState) -> float:
        """Share-weighted carrier price ($/GJ)."""
        ...

    @abstractmethod
    def compute_emissions(self, generation: dict[str, float]) -> float:
        """Supply-side emissions (MtCO₂)."""
        ...

    @abstractmethod
    def calibrate(self, base_shares: dict[str, float], base_prices: dict[str, float]) -> None:
        ...

    def write_generation(self, rs: RegionState, generation: dict[str, float]) -> None:
        """Polymorphic write — each sector knows its own carrier_output."""
        rs.generation[self.carrier_output] = generation

    def update_vintage(self, year: int) -> None:
        """Deliver pipeline, called between periods."""
        for tech in self.techs:
            if tech.vintage is not None:
                tech.vintage.deliver_pipeline(year)
```

### 4.3 ExternalInterface

```python
class ExternalInterface(ABC):
    """Adapter for an external module (Climate, Water, AFOLU)."""

    @abstractmethod
    def update(self, state: PeriodState) -> None:
        """Read energy outputs, write external results to each RegionState."""
        ...
```


## 5. Concrete Sector Classes

### 5.1 IndustrySector(DemandSector)

```python
class IndustrySector(DemandSector):
    """Industry: Energy Use (7 EndUseTechs) + Feedstocks (5 EndUseTechs)."""

    def __init__(self):
        self.subsectors = [
            Subsector("EU", [
                EndUseTech(Carrier.ELECTRICITY, eff=1.0, lifetime=25),
                EndUseTech(Carrier.GAS,         eff=1.0, lifetime=30),
                EndUseTech(Carrier.COAL,        eff=1.0, lifetime=40),
                EndUseTech(Carrier.LIQUIDS,     eff=1.0, lifetime=25),
                EndUseTech(Carrier.BIOMASS,     eff=1.0, lifetime=25),
                EndUseTech(Carrier.BIOFUEL,     eff=1.0, lifetime=25),
                EndUseTech(Carrier.H2,          eff=1.0, lifetime=20),
            ]),
            Subsector("FS", [
                EndUseTech(Carrier.LIQUIDS,     eff=1.0, lifetime=30),
                EndUseTech(Carrier.GAS,         eff=1.0, lifetime=30),
                EndUseTech(Carrier.BIOMASS,     eff=1.0, lifetime=25),
                EndUseTech(Carrier.BIOFUEL,     eff=1.0, lifetime=25),
                EndUseTech(Carrier.H2,          eff=1.0, lifetime=20),
            ]),
        ]
        self.income_elasticity = 0.6
        self.price_elasticity = -0.4

    def compute_demand(self, rs, policy):
        total = self.demand_envelope(rs)  # GDP + price response
        eu_shares = self.subsectors[0].compute_shares(rs.carrier_prices, policy)
        fs_shares = self.subsectors[1].compute_shares(rs.carrier_prices, policy)

        eu_demand = self.subsectors[0].carrier_demands(eu_shares, total * self.eu_fraction)
        fs_demand = self.subsectors[1].carrier_demands(fs_shares, total * self.fs_fraction)

        # Merge
        result: dict[Carrier, float] = {}
        for d in [eu_demand, fs_demand]:
            for c, v in d.items():
                result[c] = result.get(c, 0.0) + v
        return result
```

Note: Phase 1 `eff=1.0` → `levelized_cost = carrier_price`. Equivalent to current carrier logit. Phase 2: fill in real efficiencies for electrification analysis.

### 5.2 BuildingsSector(DemandSector)

```python
class BuildingsSector(DemandSector):
    """Res/Com × Heating/Cooling/Other. 8 carriers including Heat."""

    def __init__(self):
        heating_techs = [
            EndUseTech(Carrier.GAS,         eff=0.90, lifetime=20),
            EndUseTech(Carrier.ELECTRICITY, eff=3.0,  lifetime=18),  # heat pump COP
            EndUseTech(Carrier.COAL,        eff=0.75, lifetime=25),
            EndUseTech(Carrier.LIQUIDS,     eff=0.85, lifetime=20),
            EndUseTech(Carrier.BIOMASS,     eff=0.70, lifetime=15),
            EndUseTech(Carrier.BIOFUEL,     eff=0.85, lifetime=20),
            EndUseTech(Carrier.H2,          eff=0.90, lifetime=20),
            EndUseTech(Carrier.HEAT,        eff=0.95, lifetime=30),  # district heat
        ]
        self.subsectors = [
            Subsector("residential.heating", heating_techs),
            Subsector("residential.cooling", [...]),  # mostly electricity
            Subsector("residential.other",   [...]),
            Subsector("commercial.heating",  [...]),
            Subsector("commercial.cooling",  [...]),
            Subsector("commercial.other",    [...]),
        ]

    def demand_envelope(self, rs):
        """Override: Full floorspace-service model from buildings.md.

        Phase 1 target: FS_pc = F_bar × (y_pc / (y_pc + y_half))^alpha × (P/P0)^beta_h
        Total FS = FS_pc × Pop. Service intensity × carrier logit per end-use.
        See design/buildings.md for complete derivation.
        """
        # Returns total; per-subsector split handled in compute_demand
        return self.base_demand * (rs.gdp / self.base_gdp) ** self.income_elasticity \
                                * max(self.sector_price_index(rs) / self.base_price, 0.01) ** self.price_elasticity

    def compute_demand(self, rs, policy):
        total = self.demand_envelope(rs)
        hdd_ratio = rs.hdd / self._hdd_base if self._hdd_base > 0 else 1.0
        cdd_ratio = rs.cdd / self._cdd_base if self._cdd_base > 0 else 1.0

        result: dict[Carrier, float] = {}
        for sub in self.subsectors:
            # Per-subsector climate scaling within the total envelope
            if "heating" in sub.name:
                sub_total = sub.base_demand / self.base_demand * total * hdd_ratio
            elif "cooling" in sub.name:
                sub_total = sub.base_demand / self.base_demand * total * cdd_ratio
            else:
                sub_total = sub.base_demand / self.base_demand * total

            shares = sub.compute_shares(rs.carrier_prices, policy)
            carrier_d = sub.carrier_demands(shares, sub_total)
            for c, v in carrier_d.items():
                result[c] = result.get(c, 0.0) + v
        return result
```

### 5.3 TransportSector(DemandSector)

```python
class TransportSector(DemandSector):
    """Passenger + Freight. Powertrain-based (LCOT logit)."""

    def __init__(self):
        self.subsectors = [
            Subsector("passenger", [
                Powertrain(Carrier.LIQUIDS,     name="ICE",  eff=0.30, lifetime=15),
                Powertrain(Carrier.BIOFUEL,     name="Bio",  eff=0.30, lifetime=15),
                Powertrain(Carrier.LIQUIDS,     name="HEV",  eff=0.45, lifetime=15),
                Powertrain(Carrier.ELECTRICITY, name="BEV",  eff=0.85, lifetime=15),
                Powertrain(Carrier.H2,          name="FCEV", eff=0.50, lifetime=15),
                Powertrain(Carrier.GAS,         name="NG",   eff=0.30, lifetime=15),
            ]),
            Subsector("freight", [...]),
        ]

    def compute_demand(self, rs, policy):
        total = self.demand_envelope(rs)  # GDP + price response
        result: dict[Carrier, float] = {}
        for sub in self.subsectors:
            if "passenger" in sub.name:
                sub_total = self.pass_fraction * total
            else:
                sub_total = self.freight_fraction * total

            shares = sub.compute_shares(rs.carrier_prices, policy)
            carrier_d = sub.carrier_demands(shares, sub_total)
            for c, v in carrier_d.items():
                result[c] = result.get(c, 0.0) + v
        return result
```

Note: Transport Powertrain uses LCOT for logit, not plain `levelized_cost`. Subsector can dispatch to `lcot()` when techs are Powertrain instances.

### 5.4 ElectricitySector(TransformationSector)

```python
class ElectricitySector(TransformationSector):
    """17 SupplyTechs, LCOE logit, VintageTracker per tech."""

    def __init__(self):
        self.carrier_output = Carrier.ELECTRICITY
        self.techs = [
            SupplyTech("coal",       Carrier.COAL,    Carrier.ELECTRICITY, eff=0.40, lifetime=45,
                       vintage=VintageTracker(retirement_type="s_curve", shutdown_enabled=True)),
            SupplyTech("solar_pv",   Carrier.SOLAR,   Carrier.ELECTRICITY, eff=1.0,  lifetime=25,
                       vintage=VintageTracker(retirement_type="hard_cutoff", shutdown_enabled=False)),
            SupplyTech("biomass",    Carrier.BIOMASS, Carrier.ELECTRICITY, eff=0.35, lifetime=40,
                       biogenic_coef=0.0257,   # biogenic carbon (carbon-neutral: net=0 without CCS)
                       vintage=VintageTracker(retirement_type="s_curve")),
            SupplyTech("biomass_ccs", Carrier.BIOMASS, Carrier.ELECTRICITY, eff=0.30, lifetime=40,
                       biogenic_coef=0.0257, capture_rate=0.90,  # BECCS → negative emissions
                       capex=4500,  # $/kW — higher than biomass due to CCS equipment
                       vintage=VintageTracker(retirement_type="s_curve")),
            SupplyTech("coal_ccs",   Carrier.COAL,    Carrier.ELECTRICITY, eff=0.35, lifetime=40,
                       carbon_coef=0.0257, capture_rate=0.90,
                       capex=4000,
                       vintage=VintageTracker(retirement_type="s_curve")),
            SupplyTech("gas_ccs",    Carrier.GAS,     Carrier.ELECTRICITY, eff=0.52, lifetime=35,
                       carbon_coef=0.0153, capture_rate=0.90,
                       capex=2200,
                       vintage=VintageTracker(retirement_type="s_curve")),
            SupplyTech("nuclear",    Carrier.URANIUM, Carrier.ELECTRICITY, eff=0.33, lifetime=60,
                       vintage=VintageTracker(retirement_type="s_curve", construction_delay=2)),
            SupplyTech("hydro",      Carrier.HYDRO,   Carrier.ELECTRICITY, eff=1.0,  lifetime=80,
                       vintage=VintageTracker(retirement_type="s_curve", construction_delay=1)),
            # ... remaining techs (wind, solar_pv, solar_csp, oil, gas_cc, geothermal, etc.)
        ]

    def compute_supply(self, rs, demand_ej, policy):
        # Apply external linkages (C1-C4, W1-W2)
        ...
        # LCOE — uses raw_fuel_prices (no carbon tax), carbon cost via SupplyTech.lcoe()
        tau = policy.carbon_price.get_price(rs.period) if policy.carbon_price else 0.0
        raw = self._raw_fuel_prices(rs)
        lcoe = np.array([t.lcoe(raw, tau) for t in self.techs])
        # Logit → target shares
        target_shares = relative_pref_logit(lcoe, self.pref_factors, ...)
        # Vintage gap-fill per tech
        generation = {}
        for t, s in zip(self.techs, target_shares):
            target = s * demand_ej
            if t.vintage:
                surviving = t.vintage.operating(rs.period, t.lifetime, self._profit(t, rs))
                gap = target - surviving - self._under_construction(t)
                if gap > 0:
                    t.vintage.invest(rs.period, gap)
                generation[t.name] = surviving + max(gap, 0)
            else:
                generation[t.name] = target
        return generation

    def compute_price(self, rs):
        """Share-weighted LCOE + T&D markup."""
        ...
```

### 5.5 DistrictHeatingSector(TransformationSector)

```python
class DistrictHeatingSector(TransformationSector):
    """4 SupplyTechs: gas boiler, electric boiler, heat pump, biomass CHP."""

    def __init__(self):
        self.carrier_output = Carrier.HEAT
        self.techs = [
            SupplyTech("gas_boiler",     Carrier.GAS,         Carrier.HEAT, eff=0.90, lifetime=25),
            SupplyTech("electric_boiler", Carrier.ELECTRICITY, Carrier.HEAT, eff=0.99, lifetime=20),
            SupplyTech("heat_pump",      Carrier.ELECTRICITY,  Carrier.HEAT, eff=3.5,  lifetime=20),
            SupplyTech("biomass_chp",    Carrier.BIOMASS,      Carrier.HEAT, eff=0.80, lifetime=30),
        ]

    def compute_price(self, rs):
        """Share-weighted LCOH + distribution markup."""
        ...
```

### 5.6 TradeModule

Global market clearing. Reads supply curves from `Region.resources`, not owning them.

```python
class TradeModule:
    """Global market clearing for 5 primary commodities via bisection."""

    commodities = [Carrier.COAL, Carrier.OIL, Carrier.GAS, Carrier.URANIUM, Carrier.BIOMASS]

    def __init__(self):
        self.calibration_rents: dict[str, float] = {}
        self.prev_world_prices: dict[str, float] = {}

    def clear_markets(self, state: PeriodState, regions: dict[str, Region]) -> None:
        """Clear all commodity markets."""
        for fuel in self.commodities:
            # Global supply function: sum across regions
            def global_supply(price):
                return sum(
                    region.resources[fuel].production_at_price(price)
                    for region in regions.values()
                    if fuel in region.resources
                )

            # Global demand: sum across RegionStates
            total_demand = sum(
                rs.final_demand.get(fuel, 0.0) + self._transformation_demand(rs, fuel)
                for rs in state.regions.values()
            )

            # Bisection
            rent = self.calibration_rents.get(fuel, 0.0)
            world_price = self._bisection(global_supply, total_demand, rent)

            # Price clamping (30% max change per period)
            if fuel in self.prev_world_prices:
                prev = self.prev_world_prices[fuel]
                world_price = max(prev * 0.7, min(prev * 1.3, world_price))

            # Write results
            state.world_prices[fuel] = world_price
            for name, region in regions.items():
                rs = state.regions[name]
                if fuel in region.resources:
                    tc = region.resources[fuel].transport_cost
                    delivered = world_price + tc
                    rs.raw_fuel_prices[fuel] = delivered   # pre-carbon-tax (for SupplyTech.lcoe)
                    rs.carrier_prices[fuel] = delivered     # will be augmented with carbon tax in Step 6a
                    rs.regional_production[fuel] = region.resources[fuel].production_at_price(world_price)

    def update_depletion(self, state: PeriodState, regions: dict[str, Region]) -> None:
        """Inter-period: deplete resources based on production."""
        for name, region in regions.items():
            rs = state.regions[name]
            for fuel, supply in region.resources.items():
                prod = rs.regional_production.get(fuel, 0.0)
                supply.deplete(prod)
        self.prev_world_prices = dict(state.world_prices)
```

### 5.7 TechChange

Two-factor learning: cost falls with cumulative deployment (LBD) and R&D knowledge
stock (RND). Cross-tech spillovers via a family-level matrix.

$$capex(t) = capex_0 \times \left(\frac{Q_{eff}}{Q_0}\right)^{-\alpha_{LBD}} \times \left(\frac{H_{eff}}{H_0}\right)^{-\beta_{RND}}$$

where $Q_{eff}$ includes own + spillover cumulative, and $H_{eff}$ includes own + spillover
knowledge stock. See `technology_change.md` for derivation and parameter values.

```python
@dataclass
class TechChange:
    """Two-factor learning (LBD + RND) with cross-tech spillovers. Global."""

    # ── Per-technology parameters (immutable after init) ──
    alpha_lbd: dict[str, float]           # LBD exponent per tech
    beta_rnd: dict[str, float]            # RND exponent per tech (WITCH values)
    floor_fraction: dict[str, float]      # min cost as fraction of base capex
    base_cumulative_gw: dict[str, float]  # Q₀ per tech (GW)
    base_knowledge: dict[str, float]      # H₀ per tech family (bn$ cumulative R&D)
    base_capex: dict[str, float]          # capex₀ per tech ($/kW)

    # ── Spillover structure ──
    tech_families: list[str]              # e.g. ["solar", "wind", "nuclear", "ccs", "h2"]
    tech_to_family: dict[str, str]        # tech_name → family name
    spillover_matrix: np.ndarray          # |families| × |families|, diagonal = 1.0

    # ── Global parameters ──
    knowledge_depreciation: float = 0.10  # δ_H (annual)

    # ── State (mutated between periods) ──
    cumulative_gw: dict[str, float] = field(default_factory=dict)
    knowledge_stock: dict[str, float] = field(default_factory=dict)  # per family

    def update(self, state: PeriodState, regions: dict[str, Region],
               rnd_spending: dict[str, float] | None = None) -> None:
        """Called BETWEEN periods. Updates cumulative deployment, knowledge stock,
        and capex on all SupplyTechs across all regions.

        Args:
            state: completed period's state (for generation data)
            regions: all Region objects (to mutate SupplyTech.capex)
            rnd_spending: {family: bn$/yr} — Phase 1: exogenous (IEA RD&D);
                          Phase 2+: endogenous from budget constraint
        """
        # 1. Accumulate deployment (GW) across all regions
        for rs in state.regions.values():
            for carrier, techs in rs.generation.items():
                for tech_name, ej in techs.items():
                    gw = ej_to_gw(ej, self._capacity_factor(tech_name))
                    self.cumulative_gw[tech_name] = (
                        self.cumulative_gw.get(tech_name, 0.0) + gw
                    )

        # 2. Update knowledge stock per family: H(t+1) = (1−δ_H)·H(t) + RND(t)
        rnd = rnd_spending or {}
        for fam in self.tech_families:
            h_old = self.knowledge_stock.get(fam, self.base_knowledge.get(fam, 1.0))
            h_new = (1.0 - self.knowledge_depreciation) * h_old + rnd.get(fam, 0.0)
            self.knowledge_stock[fam] = h_new

        # 3. Update capex on all SupplyTechs
        for region in regions.values():
            for sector in region.transformation:
                for tech in sector.techs:
                    if tech.name not in self.alpha_lbd:
                        continue
                    q_eff = self._effective_cumulative(tech.name)
                    h_eff = self._effective_knowledge(tech.name)
                    q0 = self.base_cumulative_gw.get(tech.name, 1.0)
                    h0 = self.base_knowledge.get(self.tech_to_family.get(tech.name, ""), 1.0)
                    capex0 = self.base_capex[tech.name]

                    lbd_factor = (q_eff / q0) ** (-self.alpha_lbd[tech.name])
                    rnd_factor = (h_eff / h0) ** (-self.beta_rnd.get(tech.name, 0.0))
                    floor = capex0 * self.floor_fraction.get(tech.name, 0.20)

                    tech.capex = max(capex0 * lbd_factor * rnd_factor, floor)

    def _effective_cumulative(self, tech_name: str) -> float:
        """Own cumulative + spillover from other techs in same/related families."""
        fam_idx = self.tech_families.index(self.tech_to_family[tech_name])
        q_eff = 0.0
        for other_name, q in self.cumulative_gw.items():
            other_fam = self.tech_to_family.get(other_name, "")
            if other_fam in self.tech_families:
                j = self.tech_families.index(other_fam)
                q_eff += self.spillover_matrix[fam_idx, j] * q
        return max(q_eff, self.base_cumulative_gw.get(tech_name, 1.0))

    def _effective_knowledge(self, tech_name: str) -> float:
        """Own knowledge + spillover from related families."""
        fam = self.tech_to_family[tech_name]
        fam_idx = self.tech_families.index(fam)
        h_eff = 0.0
        for j, other_fam in enumerate(self.tech_families):
            h_eff += self.spillover_matrix[fam_idx, j] * self.knowledge_stock.get(other_fam, 1.0)
        return max(h_eff, self.base_knowledge.get(fam, 1.0))
```

**Phase 1 defaults:**

| Technology | Family | α_LBD | β_RND | Floor (% of base) |
|-----------|--------|-------|-------|-------------------|
| Solar PV | solar | 0.32 | 0.15 | 15% |
| Wind | wind | 0.10 | 0.10 | 25% |
| Nuclear | nuclear | 0.05 | 0.08 | 50% |
| Gas CC | — | 0.0 | 0.0 | 100% |
| Coal | — | 0.0 | 0.0 | 100% |
| Electrolysis | h2 | 0.18 | 0.12 | 20% |
| CCS (all) | ccs | 0.12 | 0.10 | 30% |
| Batteries | solar | 0.18 | 0.12 | 15% |

Phase 1 spillover matrix = identity (no cross-family spillovers). Phase 2+: off-diagonal
entries for solar↔batteries, CCS knowledge transfer across fossil+bio, etc.

Phase 1 `rnd_spending`: hardcoded annual values per family (placeholder until IEA RD&D
data access). When `rnd_spending=None`, only LBD is active (β_RND effectively zero
because H stays at H₀).


### 5.8 AgricultureSector(DemandSector)

```python
class AgricultureSector(DemandSector):
    """Production-index-driven sector. Single subsector, 7 carriers.
    Non-energy emissions (CH4, N2O) scale with production_index.

    GHG pricing: when cover_agriculture_ghg is enabled, a GHG cost adder
    is included in the sector price index, causing Q_ag to fall via price
    elasticity (γ=-0.2), which in turn reduces non-energy emissions.
    """

    income_elasticity = 0.3   # Engel's law
    price_elasticity = -0.2

    # Non-energy emission base values (from EDGAR, per region)
    base_ch4: float = 0.0    # MtCH4
    base_n2o: float = 0.0    # MtN2O

    def __init__(self):
        self.subsectors = [
            Subsector("agriculture", [
                EndUseTech(Carrier.ELECTRICITY, eff=1.0, lifetime=20),
                EndUseTech(Carrier.LIQUIDS,     eff=1.0, lifetime=15),  # diesel
                EndUseTech(Carrier.GAS,         eff=1.0, lifetime=20),
                EndUseTech(Carrier.COAL,        eff=1.0, lifetime=20),
                EndUseTech(Carrier.BIOMASS,     eff=1.0, lifetime=15),
                EndUseTech(Carrier.BIOFUEL,     eff=1.0, lifetime=15),
                EndUseTech(Carrier.H2,          eff=1.0, lifetime=15),
            ]),
        ]

    def production_index(self, rs: RegionState) -> float:
        """Agricultural production index (dimensionless, base year = 1.0).
        Not physical units — an aggregate index driven by GDP and energy price.
        Same driver for energy demand, CH₄, and N₂O emissions.
        Phase 2+: overridden by AFOLU crop/livestock output.
        """
        return self.demand_envelope(rs) / self.base_demand if self.base_demand > 0 else 1.0

    def sector_price_index(self, rs: RegionState) -> float:
        """Energy price + optional non-energy GHG cost adder.

        GHG adder = (base_CH₄ × GWP_CH₄ + base_N₂O × GWP_N₂O) × τ / base_demand
        Units: MtCO₂eq × $/tCO₂eq / EJ → need scaling to $/GJ.
        """
        base_price = super().sector_price_index(rs)
        if not (hasattr(rs, '_policy') and rs._policy.carbon_price.cover_agriculture_ghg):
            return base_price
        ghg_price = rs._policy.carbon_price.get_price(rs.period)
        if ghg_price <= 0 or self.base_demand <= 0:
            return base_price
        ghg_co2eq_mt = self.base_ch4 * GWP100["ch4"] + self.base_n2o * GWP100["n2o"]
        ghg_adder = ghg_co2eq_mt * ghg_price / (self.base_demand * 1e3)  # $/GJ
        return base_price + ghg_adder

    def compute_demand(self, rs, policy):
        total = self.demand_envelope(rs)
        shares = self.subsectors[0].compute_shares(rs.carrier_prices, policy)
        return self.subsectors[0].carrier_demands(shares, total)

    def compute_emissions(self, rs) -> EmissionResult:
        result = self._combustion_emissions(rs)
        idx = self.production_index(rs)
        result.ch4 += self.base_ch4 * idx
        result.n2o += self.base_n2o * idx
        return result
```

### 5.9 BunkersSector(DemandSector)

```python
class BunkersSector(DemandSector):
    """International aviation + shipping. Global (not per-region).
    Powertrain-based logit on LCOT, draws fuel from global pool."""

    income_elasticity = 0.9   # aviation: ~1.0, shipping: ~0.8, blended
    price_elasticity = -0.2

    def __init__(self):
        self.subsectors = [
            Subsector("aviation", [
                Powertrain(Carrier.LIQUIDS, name="jet",  eff=0.15, lifetime=25),
                Powertrain(Carrier.BIOFUEL, name="saf",  eff=0.15, lifetime=25),
            ]),
            Subsector("shipping", [
                Powertrain(Carrier.LIQUIDS, name="marine", eff=0.10, lifetime=30),
                Powertrain(Carrier.GAS,     name="lng",    eff=0.12, lifetime=30),
            ]),
        ]

    def compute_demand(self, rs, policy):
        # Uses world GDP (sum across regions), not regional GDP
        total = self.demand_envelope(rs)
        result: dict[Carrier, float] = {}
        for sub in self.subsectors:
            frac = self.avi_fraction if "aviation" in sub.name else self.ship_fraction
            shares = sub.compute_shares(rs.carrier_prices, policy)
            carrier_d = sub.carrier_demands(shares, total * frac)
            for c, v in carrier_d.items():
                result[c] = result.get(c, 0.0) + v
        return result
```

Note: Bunkers sits on **GHIMModel**, not inside any Region. It uses world GDP as demand driver and draws fuel from the global pool before regional trade clearing.

### 5.10 HydrogenSector(TransformationSector)

```python
class HydrogenSector(TransformationSector):
    """2 SupplyTechs (Phase 1), LCOH logit, VintageTracker per tech."""

    def __init__(self):
        self.carrier_output = Carrier.H2
        self.techs = [
            SupplyTech("smr",          Carrier.GAS,         Carrier.H2, eff=0.72, lifetime=30,
                       capture_rate=0.0,
                       vintage=VintageTracker(retirement_type="s_curve", shutdown_enabled=True)),
            SupplyTech("electrolysis", Carrier.ELECTRICITY, Carrier.H2, eff=0.65, lifetime=25,
                       vintage=VintageTracker(retirement_type="hard_cutoff", shutdown_enabled=False)),
        ]

    def compute_supply(self, rs, demand_ej, policy):
        lcoh = np.array([t.lcoe(rs.carrier_prices) for t in self.techs])
        target_shares = relative_pref_logit(lcoh, self.pref_factors, ...)
        # Same vintage gap-fill pattern as ElectricitySector
        ...

    def compute_price(self, rs):
        """Share-weighted LCOH."""
        ...
```

### 5.11 BiofuelsSector(TransformationSector)

```python
class BiofuelsSector(TransformationSector):
    """Biomass → biofuel conversion. 2 SupplyTechs."""

    def __init__(self):
        self.carrier_output = Carrier.BIOFUEL
        self.techs = [
            SupplyTech("ethanol",    Carrier.BIOMASS, Carrier.BIOFUEL, eff=0.45, lifetime=30),
            SupplyTech("biodiesel",  Carrier.BIOMASS, Carrier.BIOFUEL, eff=0.50, lifetime=30),
        ]

    def compute_price(self, rs):
        """Share-weighted LCOF (levelized cost of fuel)."""
        ...
```

### 5.12 RefinedOilSector(TransformationSector)

```python
class RefinedOilSector(TransformationSector):
    """Oil → refined liquids. Single tech, pass-through.

    IMPORTANT: Refining is conversion, not combustion. The carbon in crude
    oil stays in the refined product and is released when the end user
    burns it. Therefore:
      - SupplyTech("refinery").carbon_coef = 0.0  (no CO₂ at refinery)
      - CARBON_COEFS[Carrier.LIQUIDS] = 0.0200    (CO₂ at demand side)
      - CARBON_COEFS[Carrier.OIL] = 0.0            (no double-count)
    Carbon tax on refined liquids enters via carrier_price adder (Step 6a),
    not via refinery LCOE.
    """

    def __init__(self):
        self.carrier_output = Carrier.LIQUIDS
        self.techs = [
            SupplyTech("refinery", Carrier.OIL, Carrier.LIQUIDS, eff=0.90, lifetime=40,
                       carbon_coef=0.0),  # conversion, not combustion
        ]

    def compute_supply(self, rs, demand_ej, policy, **kwargs):
        return {"refinery": demand_ej}

    def compute_price(self, rs, raw_fuel_prices=None, carbon_price=0.0):
        """Refinery price = raw oil / efficiency + VOM. No carbon cost here —
        carbon tax on liquids is applied at demand side (Step 6a)."""
        oil_price = (raw_fuel_prices or rs.raw_fuel_prices).get(Carrier.OIL, 8.0)
        return oil_price / self.techs[0].efficiency + self.techs[0].vom
```


## 6. External Module Adapters

### 6.1 Default Adapters

```python
class DefaultClimateAdapter(ExternalInterface):
    def update(self, state: PeriodState) -> None:
        for rs in state.regions.values():
            rs.temperature_anomaly = 0.0
            rs.precip_anomaly = 0.0

class DefaultWaterAdapter(ExternalInterface):
    def update(self, state: PeriodState) -> None:
        for rs in state.regions.values():
            rs.cooling_water_avail = float('inf')
            rs.hydro_water_fraction = 1.0
            rs.water_energy_demand = 0.0

class DefaultAFOLUAdapter(ExternalInterface):
    """Provides biomass supply curves and crop residue availability.

    Biomass supply has four components (Phase 1):
      1. Energy crops — exogenous regional potential (EJ), from IRENA/IPCC literature
      2. Crop residues — scales with Q_ag (agricultural production index)
      3. Forest residues — exogenous regional potential (EJ)
      4. Municipal solid waste — scales with population

    Total biomass supply enters trade clearing (TradeModule) alongside coal/oil/gas.
    Biomass is a renewable annual flow: no depletion, but supply-constrained.
    Phase 2+: AFOLU module makes energy crop land endogenous.
    """

    def __init__(self, biomass_curves: dict, base_residue_ej: dict[str, float]):
        self.curves = biomass_curves            # {region: [ResourceGrade, ...]}
        self.base_residue_ej = base_residue_ej  # {region: EJ} base-year crop residue

    def update(self, state: PeriodState) -> None:
        for name, rs in state.regions.items():
            # Static supply curve (energy crops + forest residues + MSW)
            base_grades = list(self.curves.get(name, []))

            # Dynamic component: crop residue scales with Q_ag
            q_ag = getattr(rs, 'production_index_ag', 1.0)
            residue_ej = self.base_residue_ej.get(name, 0.0) * q_ag

            # Add residue as a low-cost grade (collection cost ≈ 2 $/GJ)
            if residue_ej > 0:
                base_grades.append(ResourceGrade(
                    available=residue_ej,
                    extraction_cost=2.0,  # $/GJ collection + transport
                ))

            rs.biomass_supply = base_grades
```

### 6.2 Real Adapter (example)

```python
class HectorClimateAdapter(ExternalInterface):
    def __init__(self, hector_instance):
        self.hector = hector_instance

    def update(self, state: PeriodState) -> None:
        self.hector.set_emissions(state.period, state.global_emissions)
        self.hector.run_to(state.period)
        global_dt = self.hector.get_temperature(state.period)
        for name, rs in state.regions.items():
            rs.temperature_anomaly = global_dt * REGIONAL_SCALING[name]
            rs.precip_anomaly = self.hector.get_precip(name, state.period)
            rs.hdd = compute_hdd(rs.temperature_anomaly)
            rs.cdd = compute_cdd(rs.temperature_anomaly)
```


## 7. GHIMModel: Top-Level Orchestrator

```python
class GHIMModel:
    def __init__(
        self,
        regions: dict[str, Region],
        trade: TradeModule,
        tech_change: TechChange,
        policy: PolicyEngine,
        climate: ExternalInterface,
        water: ExternalInterface,
        afolu: ExternalInterface,
    ):
        self.regions = regions
        self.trade = trade
        self.tech_change = tech_change
        self.policy = policy
        self.climate = climate
        self.water = water
        self.afolu = afolu
        self.bunkers: BunkersSector | None = None  # global, not per-region

    def F(self, state: PeriodState) -> PeriodState:
        """One full model pass. Returns updated state.

        Price channels (critical for carbon tax correctness):
          raw_fuel_prices  = world_price + transport_cost  (no carbon tax)
          carrier_prices   = consumer-facing prices         (carbon-inclusive)

        Carbon tax enters at TWO points, each exactly once per emission:
          1. SupplyTech.lcoe(raw_prices, τ)  → carbon_cost in LCOE (CCS-aware)
          2. Direct-use fuels: raw + CARBON_COEFS × TC_TO_TCO2 × τ
        No double-counting: CARBON_COEFS[ELECTRICITY/H2/HEAT] = 0.
        """
        new = deepcopy(state)
        carbon_price = self.policy.carbon_price.get_price(new.period)
        ghg_price = carbon_price  # $/tCO₂eq, also applied to non-CO₂ if enabled

        # Step 1: External modules
        self.climate.update(new)
        self.water.update(new)
        self.afolu.update(new)

        for name, region in self.regions.items():
            rs = new.regions[name]

            # Step 2: Economy → VA, total energy demand
            region.economy.compute_value_added(rs)
            total_e = region.economy.compute_energy_demand(rs)

            # Step 3: Demand sectors → carrier demands
            #   Demand sectors see rs.carrier_prices (carbon-inclusive).
            raw_demands: dict[str, float] = {}
            for sector in region.demand_sectors:
                d = sector.compute_demand(rs, self.policy)
                for c, v in d.items():
                    raw_demands[c] = raw_demands.get(c, 0.0) + v
            raw_demands[Carrier.ELECTRICITY] = (
                raw_demands.get(Carrier.ELECTRICITY, 0.0) + rs.water_energy_demand
            )
            # Scale to CES total
            raw_sum = sum(raw_demands.values())
            scale = total_e / raw_sum if raw_sum > 0 else 1.0
            rs.final_demand = {c: v * scale for c, v in raw_demands.items()}

            # Step 4: Transformation sectors → generation, prices
            #   SupplyTech.lcoe() uses RAW fuel prices + explicit carbon_cost.
            #   This ensures CCS correctly pays reduced carbon cost.
            #   If fugitive CH₄ is priced, add to raw_fuel_prices (upstream cost).
            raw_fuel_prices = self._raw_fuel_prices(rs)
            if self.policy.carbon_price.cover_fugitive_ch4 and ghg_price > 0:
                for fuel in [Carrier.COAL, Carrier.OIL, Carrier.GAS]:
                    ch4_per_gj = CH4_FUGITIVE.get(fuel, 0.0) / 1e9
                    raw_fuel_prices[fuel] = raw_fuel_prices.get(fuel, 0.0) \
                        + ch4_per_gj * GWP100["ch4"] * ghg_price
            for sector in region.transformation:
                demand = rs.final_demand.get(sector.carrier_output, 0.0)
                gen = sector.compute_supply(
                    rs, demand, self.policy,
                    raw_fuel_prices=raw_fuel_prices, carbon_price=carbon_price,
                )
                price = sector.compute_price(rs, raw_fuel_prices, carbon_price)
                rs.carrier_prices[sector.carrier_output] = price
                sector.write_generation(rs, gen)

        # Step 5: Trade clearing (global)
        self.trade.clear_markets(new, self.regions)

        # Step 6: Build consumer-facing carrier prices (carbon-inclusive)
        for name, region in self.regions.items():
            rs = new.regions[name]

            # 6a. Direct-use fuels: raw price + CO₂ carbon tax + fugitive CH₄ cost
            for fuel in [Carrier.COAL, Carrier.GAS, Carrier.LIQUIDS,
                         Carrier.BIOMASS, Carrier.BIOFUEL]:
                raw = rs.raw_fuel_prices.get(fuel, rs.carrier_prices.get(fuel, 0.0))
                co2_adder = CARBON_COEFS.get(fuel, 0.0) * TC_TO_TCO2 * carbon_price
                ch4_adder = 0.0
                if self.policy.carbon_price.cover_fugitive_ch4:
                    ch4_per_gj = CH4_FUGITIVE.get(fuel, 0.0) / 1e9  # tCH₄/EJ → tCH₄/GJ
                    ch4_adder = ch4_per_gj * GWP100["ch4"] * ghg_price
                rs.carrier_prices[fuel] = raw + co2_adder + ch4_adder

            # Electricity, H₂, heat prices already include carbon cost via LCOE —
            # CARBON_COEFS[ELECTRICITY/H2/HEAT] = 0, so no adder in 6a.
            # LIQUIDS is a transformation output but refinery.carbon_coef=0
            # (conversion, not combustion), so its carbon tax comes from 6a above
            # via CARBON_COEFS[LIQUIDS]=0.0200.

            # 6b. Sector price indices (for next iteration's demand_envelope)
            for sector in region.demand_sectors:
                rs.sector_prices[sector.name] = sector.sector_price_index(rs)

            # 6c. Composite energy price (carbon-inclusive, for CES FOC)
            rs.composite_energy_price = Economy.composite_energy_price(
                rs.carrier_prices, rs.final_demand
            )

        # Step 7: CES gross output → GDP
        for name, region in self.regions.items():
            rs = new.regions[name]
            total_e = sum(rs.final_demand.values())
            region.economy.compute_gross_output(rs, total_e)

        # Step 8: Emissions (multi-gas, see emiss.md)
        total_global = EmissionResult()
        for name, region in self.regions.items():
            rs = new.regions[name]
            region_em = EmissionResult()

            # 8a. Transformation sectors (combustion − CCS capture − BECCS CDR)
            #     Uses SupplyTech.annual_emissions_tc() → can be negative for BECCS
            #     fossil:   carbon_coef × (1 − capture) × fuel_input   (≥ 0)
            #     biogenic: −biogenic_coef × capture × fuel_input      (≤ 0, BECCS only)
            for sector in region.transformation:
                gen = rs.generation.get(sector.carrier_output, {})
                region_em = region_em + sector.compute_emissions(gen)

            # 8b. Demand sectors (direct combustion + agriculture non-energy)
            #     Uses CARBON_COEFS on final carrier demands.
            #     CARBON_COEFS[LIQUIDS]=0.0200 (combustion), [ELECTRICITY/H2/HEAT]=0.
            for sector in region.demand_sectors:
                region_em = region_em + sector.compute_emissions(rs)

            # 8c. Fugitive CH₄ from fossil production
            for fuel in [Carrier.COAL, Carrier.OIL, Carrier.GAS]:
                prod = rs.regional_production.get(fuel, 0.0)
                region_em.ch4 += prod * CH4_FUGITIVE.get(fuel, 0.0)

            # 8d. Waste CH₄ (population + income scaled)
            region_em.ch4 += rs.population * WASTE_CH4_PER_CAPITA \
                             * (rs.gdp / rs.population) ** 0.3

            # 8e. F-Gases: EDGAR base × cooling growth × Kigali phase-down
            cooling_now = rs.sector_demand.get("buildings", {}).get("cooling_ej", 0.0)
            cooling_base = rs.base_cooling_ej
            cooling_growth = cooling_now / cooling_base if cooling_base > 0 else 1.0
            kigali_factor = policy.get_kigali_factor(period)
            region_em.f_gases += EDGAR_FGAS[region.name] * cooling_growth * kigali_factor

            # 8f. LULUCF anthropogenic emissions (exogenous, Phase 1)
            #     Source: EDGAR 2025, aggregated to R32.
            #     Positive = deforestation, Negative = managed forest regrowth.
            #     Phase 2+: replaced by AFOLU module (dynamic land-use change).
            #     NOTE: natural sinks (ocean, CO₂ fertilization) are NOT included
            #     — they are irrelevant for UNFCCC Net-Zero accounting.
            lulucf_r32 = self._get_lulucf(name)  # R32 lookup
            region_em.lulucf = lulucf_r32 * 1000.0  # GtCO₂→MtCO₂

            rs.emissions_detail = region_em
            rs.emissions = region_em.co2eq
            total_global = total_global + region_em

        # Bunkers emissions (global, not per-region)
        if self.bunkers is not None:
            bunker_em = self.bunkers.compute_emissions(new)
            total_global = total_global + bunker_em

        new.global_emissions = total_global.co2eq / 1000.0  # Mt → Gt (anthropogenic net)
        new.global_emissions_detail = total_global

        return new

    @staticmethod
    def _raw_fuel_prices(rs: RegionState) -> dict[Carrier, float]:
        """Extract raw fuel prices (trade-clearing, no carbon tax) for supply sectors.

        For traded fuels: world_price + transport_cost (set by TradeModule).
        For non-traded: use carrier_prices as-is (no carbon tax on biomass/biofuel).
        """
        # raw_fuel_prices is stored separately from consumer carrier_prices
        return dict(rs.raw_fuel_prices)
```


## 8. Solver

### 8.1 Key design: F(x) is a single pass, no inner loops

The current code has **two nested iteration loops** inside `solve_period()` (price iteration) and `_solve_regions_for_period()` (demand-trade iteration). In the OOP design, **both are eliminated**. F(x) computes one pass through all steps, and the **outer solver** handles all convergence:

```
Current code:                          OOP design:
─────────────                          ──────────
for trade_iter:                        solver.solve():
  for region:                            for n in range(max_iter):
    for price_iter:                        x_new = model.F(x)     ← one pass, no inner loops
      compute_demand()                     x = damp(x, x_new)
      compute_supply()                     if converged: break
      update_prices()
  trade.clear_markets()
```

Why this works: prices that don't converge in one F(x) pass converge across successive calls. The damped iteration handles electricity prices, trade prices, and GDP simultaneously rather than in nested sub-loops.

### 8.2 State vector

The solver iterates on a subset of PeriodState fields (**solved variables**). Everything else is **derived** within F(x).

| Solved (in state vector x) | Derived (computed inside F) |
|---------------------------|----------------------------|
| `rs.gdp` (Y_r) | `rs.value_added` |
| `rs.carrier_prices[ELECTRICITY]` | `rs.final_demand` |
| `rs.carrier_prices[H2]` | `rs.generation` |
| `rs.carrier_prices[HEAT]` | `rs.emissions` |
| `state.world_prices[fuel]` | `rs.sector_prices` |
| | `rs.composite_energy_price` |

**Dimension**: 3 prices × N_regions + N_traded_fuels + N_regions (GDP) = 4×32 + 5 = **133**.

### 8.3 Solver ABC and implementations

```python
class Solver(ABC):
    @abstractmethod
    def solve(self, model: GHIMModel, state: PeriodState) -> PeriodState:
        """Find fixed point: F(x*) = x*."""
        ...

class DampedSolver(Solver):
    """Phase 1: x_{n+1} = α·F(x) + (1-α)·x

    Guaranteed convergence when α < 1/L (L = Lipschitz constant of F).
    Typical α = 0.3–0.5. See solver.md §4 for theory.
    """

    def __init__(self, alpha: float = 0.5, tol: float = 1e-3, max_iter: int = 50):
        self.alpha = alpha
        self.tol = tol
        self.max_iter = max_iter

    def solve(self, model, state):
        x = state
        for n in range(self.max_iter):
            x_new = model.F(x)
            residual = self._residual(x, x_new)
            x = self._damp(x, x_new)
            if residual < self.tol:
                break
        return x

    def _residual(self, old: PeriodState, new: PeriodState) -> float:
        """Max relative change across all state vector components."""
        max_change = 0.0
        for name in old.regions:
            o, n = old.regions[name], new.regions[name]
            # GDP
            if o.gdp > 0:
                max_change = max(max_change, abs(n.gdp - o.gdp) / o.gdp)
            # Secondary carrier prices (solved)
            for c in [Carrier.ELECTRICITY, Carrier.H2, Carrier.HEAT]:
                p0 = o.carrier_prices.get(c, 1.0)
                p1 = n.carrier_prices.get(c, p0)
                if p0 > 0:
                    max_change = max(max_change, abs(p1 - p0) / p0)
        # World prices (solved)
        for fuel in TRADED_FUELS:
            p0 = old.world_prices.get(fuel, 1.0)
            p1 = new.world_prices.get(fuel, p0)
            if p0 > 0:
                max_change = max(max_change, abs(p1 - p0) / p0)
        return max_change

    def _damp(self, old: PeriodState, new: PeriodState) -> PeriodState:
        """Damp only state vector components. Derived fields come from new."""
        result = deepcopy(new)
        a = self.alpha
        for name in old.regions:
            o = old.regions[name]
            r = result.regions[name]
            # GDP
            r.gdp = a * r.gdp + (1 - a) * o.gdp
            # Secondary prices
            for c in [Carrier.ELECTRICITY, Carrier.H2, Carrier.HEAT]:
                r.carrier_prices[c] = (a * r.carrier_prices.get(c, 0)
                                       + (1 - a) * o.carrier_prices.get(c, 0))
        # World prices
        for fuel in TRADED_FUELS:
            result.world_prices[fuel] = (a * result.world_prices.get(fuel, 0)
                                         + (1 - a) * old.world_prices.get(fuel, 0))
        return result
```

### 8.4 Phase 2: Anderson acceleration via to_vector/from_vector

Anderson acceleration requires a flat numpy array interface. PeriodState provides `to_vector()` / `from_vector()` for this:

```python
@dataclass
class PeriodState:
    ...
    # State vector field ordering (set once at init)
    _region_names: list[str] = field(default_factory=list)

    def to_vector(self) -> np.ndarray:
        """Extract solved variables into flat array (133-dim)."""
        v = []
        for name in self._region_names:
            rs = self.regions[name]
            v.extend([
                rs.gdp,
                rs.carrier_prices.get(Carrier.ELECTRICITY, 20.0),
                rs.carrier_prices.get(Carrier.H2, 15.0),
                rs.carrier_prices.get(Carrier.HEAT, 10.0),
            ])
        for fuel in TRADED_FUELS:
            v.append(self.world_prices.get(fuel, 5.0))
        return np.array(v)

    def from_vector(self, v: np.ndarray) -> None:
        """Inject solved variables back from flat array."""
        i = 0
        for name in self._region_names:
            rs = self.regions[name]
            rs.gdp = v[i]; i += 1
            rs.carrier_prices[Carrier.ELECTRICITY] = v[i]; i += 1
            rs.carrier_prices[Carrier.H2] = v[i]; i += 1
            rs.carrier_prices[Carrier.HEAT] = v[i]; i += 1
        for fuel in TRADED_FUELS:
            self.world_prices[fuel] = v[i]; i += 1


class AndersonSolver(Solver):
    """Phase 2: Anderson acceleration with memory depth m.
    2–3× fewer iterations than damped. Same F, different mixing."""

    def __init__(self, m: int = 5, tol: float = 1e-6, max_iter: int = 50,
                 fallback_alpha: float = 0.3):
        self.m = m
        self.tol = tol
        self.max_iter = max_iter
        self.fallback_alpha = fallback_alpha

    def solve(self, model, state):
        def g(v):
            """g(x) = F(x) - x  (residual function for Anderson)."""
            state.from_vector(v)
            new = model.F(state)
            return new.to_vector() - v

        x0 = state.to_vector()
        try:
            from scipy.optimize import anderson
            x_star = anderson(g, x0, M=self.m, f_tol=self.tol, maxiter=self.max_iter)
            state.from_vector(x_star)
        except Exception:
            # Fallback to damped iteration
            fallback = DampedSolver(alpha=self.fallback_alpha, tol=self.tol, max_iter=self.max_iter)
            state = fallback.solve(model, state)
        return state


class NewtonKrylovSolver(Solver):
    """Phase 3+: For 100+ country resolution. Quadratic convergence."""

    def solve(self, model, state):
        from scipy.optimize import newton_krylov
        x0 = state.to_vector()
        def g(v):
            state.from_vector(v)
            new = model.F(state)
            return new.to_vector() - v
        x_star = newton_krylov(g, x0, f_tol=1e-6, maxiter=50)
        state.from_vector(x_star)
        return state
```

### 8.5 Intra-period vs inter-period boundary

**Critical invariant**: F(x) must be a **pure function** of the state vector (plus fixed config). No side effects that accumulate across iterations.

| Intra-period (inside F, repeatable) | Inter-period (after solver.solve, once per period) |
|-------------------------------------|---------------------------------------------------|
| `compute_value_added(rs)` | `economy.update_capital(rs)` — K(t+1) = (1-δ)K + I·dt |
| `compute_demand(rs, policy)` | `sector.update_vintage(year)` — deliver pipeline, retire |
| `compute_supply(rs, demand, policy)` | `trade.update_depletion(state)` — grades consumed |
| `clear_markets(state, regions)` | `tech_change.update(state)` — learning curves |
| `compute_gross_output(rs, e)` | `update_exogenous(state, ssp_data)` — population, etc. |
| `compute_emissions(rs)` | |

If inter-period updates leak into F(x), capital accumulates on every iteration → GDP explodes.


## 9. Run Loop (Recursive-Dynamic)

```python
def run_model(
    model: GHIMModel,
    solver: Solver,
    periods: list[int],
    ssp_data: dict,
) -> list[PeriodState]:
    """Solve period-by-period with warm-start."""
    results = []
    state = model.initialize(ssp_data, periods[0])

    for period in periods:
        # Update exogenous inputs
        state.period = period
        for name, rs in state.regions.items():
            rs.population = get_population(ssp_data, name, period)
            rs.period = period

        # Solve fixed-point for this period
        state = solver.solve(model, state)

        # Inter-period updates (NOT part of F)
        model.tech_change.update(state, model.regions)
        for name, region in model.regions.items():
            rs = state.regions[name]
            region.economy.update_capital(rs)               # K(t+1)
            region.economy.compute_investment(rs)           # I for next period warm-start
            for sector in region.transformation:
                sector.update_vintage(period)                # deliver pipeline, retire
            for sector in region.demand_sectors:
                for sub in sector.subsectors:
                    for tech in sub.techs:
                        if tech.vintage is not None:
                            tech.vintage.deliver_pipeline(period)
        model.trade.update_depletion(state, model.regions)  # resource grades

        results.append(deepcopy(state))
        # state carries forward as warm-start for next period

    return results
```


## 10. Configuration

### 10.1 Vintage tracking on/off

```python
# config.py
VINTAGE_ENABLED = {
    "electricity":          True,    # Phase 1
    "hydrogen":             True,    # Phase 1
    "district_heat":        True,    # Phase 1
    "biofuels":             False,   # Phase 2
    "refined_oil":          False,   # Never (pass-through)
    "transport.passenger":  True,    # Phase 1
    "transport.freight":    True,    # Phase 1
    "industry.eu":          False,   # Phase 2
    "industry.fs":          False,   # Phase 2
    "buildings.*":          False,   # Phase 2
    "bunkers.*":            False,   # Phase 2
    "agriculture.*":        False,   # Never (pref decay only)
}
```

Sector initialization reads this config. When `False`, EndUseTech/SupplyTech gets `vintage=None`. When `True`, a `VintageTracker` with appropriate parameters is attached. Turning on vintage for a sector = one config change, no code change.

### 10.2 EndUseTech efficiency calibration status

| Sector | Phase 1 | Phase 2+ | Data source |
|--------|---------|----------|-------------|
| Buildings Heating | Real (COP, boiler eff) | Same | IEA, ASHRAE |
| Buildings Cooling | Real (COP) | Same | IEA |
| Transport | Real (tank-to-wheel) | Same | ICCT, DOE |
| Industry EU | Placeholder (eff=1.0) | Real | IEA WEB, literature |
| Industry FS | Placeholder (eff=1.0) | Real | Process-specific |
| Agriculture | Placeholder (eff=1.0) | Real | FAO |


## 11. Migration Path from Current Code

| Step | What | Effort |
|------|------|--------|
| 1 | `Carrier` enum + `CARBON_COEFS` | Small |
| 2 | `VintageTracker` (refactor from current `VintageStock`) | Medium |
| 3 | `EndUseTech` + `SupplyTech` dataclasses | Small |
| 4 | `Subsector` with logit + vintage-aware gap-fill | Medium |
| 5 | `ResourceSupply` (refactor from current trade curves) | Small |
| 6 | `RegionState` + `PeriodState` + `Region` | Medium |
| 7 | `DemandSector` ABC, wrap existing demand code | Small |
| 8 | `TransformationSector` ABC on existing `ElectricitySector` | Small |
| 9 | `GHIMModel.F()` from `solve_period()` | Medium |
| 10 | `DampedSolver` from current iteration loop | Small |
| 11 | `ExternalInterface` + default adapters | Small |
| 12 | Sector implementations (Industry, Buildings, Transport, etc.) | Large |
| 13 | `TradeModule` refactor to read from `Region.resources` | Medium |
| 14 | `TechChange` with spillover matrix | Medium |

Steps 1–11: **refactoring** (no new behavior, existing tests pass). Steps 12–14: **new capabilities**.


## 12. File Layout (Target)

```
ghim/
├── model.py                    # GHIMModel
├── config.py                   # parameters + VINTAGE_ENABLED
├── carrier.py                  # Carrier enum, CARBON_COEFS, CARRIERS_7/8
├── region.py                   # Region container + R32 region list
├── state.py                    # RegionState + PeriodState
│
├── tech/
│   ├── base.py                 # EndUseTech, SupplyTech, Powertrain
│   ├── subsector.py            # Subsector (logit + vintage gap-fill)
│   ├── vintage.py              # VintageTracker
│   └── learning.py             # TechChange (learning + spillovers)
│
├── econ/
│   ├── economy.py              # Economy (wraps KLEMDriver)
│   └── ces.py                  # CES math functions
│
├── sector/
│   ├── base.py                 # DemandSector, TransformationSector ABCs
│   ├── industry.py             # IndustrySector
│   ├── buildings.py            # BuildingsSector
│   ├── transport.py            # TransportSector
│   ├── agriculture.py          # AgricultureSector
│   ├── bunkers.py              # BunkersSector
│   ├── electricity.py          # ElectricitySector
│   ├── hydrogen.py             # HydrogenSector
│   ├── district_heating.py     # DistrictHeatingSector
│   ├── biofuels.py             # BiofuelsSector
│   └── refined_oil.py          # RefinedOilSector
│
├── trade/
│   ├── resource.py             # ResourceSupply
│   ├── market.py               # TradeModule (global clearing)
│   └── calibration.py          # rent calibration, price clamping
│
├── external/
│   ├── base.py                 # ExternalInterface ABC
│   ├── climate.py              # ClimateAdapter
│   ├── water.py                # WaterAdapter
│   └── afolu.py                # AFOLUAdapter
│
├── solver/
│   ├── base.py                 # Solver ABC
│   ├── damped.py               # DampedSolver
│   ├── anderson.py             # AndersonSolver
│   └── newton.py               # NewtonKrylovSolver
│
├── policy/
│   └── engine.py               # PolicyEngine (13 instruments)
│
├── data/                       # data loaders
│   ├── ssp.py
│   ├── energy_cal.py
│   ├── trade_cal.py
│   ├── gem_cal.py
│   ├── climate_cal.py
│   ├── water_cal.py
│   └── afolu_cal.py
│
├── output/
│   ├── reporting.py            # CSV export
│   └── iamc.py                 # IAMC-format reporting
│
├── run.py                      # CLI entry point
└── tests/
```


## 13. Dual Implementation Strategy

### 13.1 OOP First (Python)

Primary platform: development, testing, research.

- ABCs enforce consistent interfaces
- Polymorphism enables drop-in sector/solver swapping
- Rich type hints and dataclasses
- Full pytest suite

### 13.2 Procedural Translation (Fortran-ready)

| OOP Concept | Procedural Equivalent |
|-------------|----------------------|
| `Region` container | `i_region` index into flat arrays |
| `RegionState` | Struct of arrays: `gdp(n_region)`, `prices(n_carrier, n_region)` |
| `Subsector.compute_shares()` | `compute_shares_<sector>(i_region, ...)` |
| `EndUseTech` list | Arrays: `eff(n_tech)`, `capex(n_tech)`, `lifetime(n_tech)` |
| `VintageTracker` | `vintage(n_tech, n_vintage, n_region)` 3D array |
| `model.F(state)` | `model_pass(arrays, ...)` subroutine |
| Polymorphic dispatch | Explicit sector loop |

**Why OOP → Procedural is easier than reverse:**
- Mechanical flattening (loss-free)
- Scientific computing has decades of Fortran-from-OOP experience


## 14. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Language | Python OOP | + Procedural translation |
| Regions | 32 (GCAM R32) | 100+ (country-level) |
| Sectors | All 5 demand + 5 transformation | Same |
| EndUseTech eff | Real (Buildings, Transport), Placeholder (others) | All real |
| Vintage tracking | Electricity + Hydrogen + Transport | All sectors |
| Solver | DampedSolver ($\alpha = 0.3$–$0.5$) | AndersonSolver ($M = 5$) |
| External modules | Default adapters | Live adapters |
| Policy | Full 13-instrument framework | + Endogenous R&D |

### Phase transition notes

- **Phase 1 → 2**: Turn on vintage for remaining demand sectors (config change). Fill in real EndUseTech efficiencies. Replace DampedSolver with AndersonSolver. Connect live external adapters. Add endogenous R&D.
- **Phase 2 → 3**: Procedural translation for HPC. Newton-Krylov for 100+ countries. IDC on LCOE. Pipeline cancellation. Building shell vintage.


## 15. Initialization & Calibration Sequence

How the model is built from data before `solver.solve()` is ever called.

```python
def build_model(ssp_data: dict, scenario: str, policy: PolicyScenario) -> tuple[GHIMModel, PeriodState]:
    """Complete model initialization pipeline."""

    pop_df, gdp_df = ssp_data["population"], ssp_data["gdp"]

    # ── Step 1: Build Regions ──
    regions: dict[str, Region] = {}
    initial_state = PeriodState(period=BASE_YEAR, regions={})

    for region_name in R32_REGIONS:
        base_gdp = float(gdp_df.loc[region_name, BASE_YEAR])
        base_pop = float(pop_df.loc[region_name, BASE_YEAR])

        # 1a. Economy calibration
        economy = Economy()
        k0 = economy.calibrate(base_gdp, base_pop, base_energy_ej, base_energy_price, region_name)
        economy.calibrate_tfp_trajectory(
            ssp_gdp={y: float(gdp_df.loc[region_name, y]) for y in MODEL_YEARS},
            pop={y: float(pop_df.loc[region_name, y]) for y in MODEL_YEARS},
        )

        # 1b. Demand sectors
        demand_sectors = [
            IndustrySector(),
            BuildingsSector(),
            TransportSector(),
            AgricultureSector(),
        ]
        for sector in demand_sectors:
            sector.calibrate(base_demands[sector.name], base_prices, base_gdp)

        # 1c. Transformation sectors
        transformation = [
            ElectricitySector(region=region_name),
            HydrogenSector(),
            DistrictHeatingSector(),
            BiofuelsSector(),
            RefinedOilSector(),
        ]
        for sector in transformation:
            sector.calibrate(base_shares[sector.carrier_output], base_prices)

        # 1d. Resource endowments (from trade_cal)
        resources = load_resource_supplies(region_name)

        # 1e. Initialize vintage trackers
        for sector in transformation:
            for tech in sector.techs:
                if tech.vintage is not None:
                    tech.vintage.initialize_uniform(
                        total=base_gen[tech.name], lifetime=tech.lifetime, base_year=BASE_YEAR
                    )
        for sector in demand_sectors:
            for sub in sector.subsectors:
                for tech in sub.techs:
                    if tech.vintage is not None:
                        tech.vintage.initialize_uniform(
                            total=base_carrier_demand[tech.name], lifetime=tech.lifetime, base_year=BASE_YEAR
                        )

        # 1f. Assemble Region
        regions[region_name] = Region(
            name=region_name, economy=economy,
            demand_sectors=demand_sectors, transformation=transformation,
            resources=resources,
        )

        # 1g. Initialize RegionState (warm-start for first period)
        initial_state.regions[region_name] = RegionState(
            gdp=base_gdp, population=base_pop,
            capital_stock=k0, tfp=economy.tfp_trajectory[BASE_YEAR],
            carrier_prices=dict(base_prices),
            composite_energy_price=Economy.composite_energy_price(base_prices, base_demands_total),
        )

    # ── Step 2: Global components ──
    trade = TradeModule(regions)
    tech_change = TechChange(base_cumulative=...)
    bunkers = BunkersSector()
    bunkers.calibrate(...)

    # ── Step 3: External adapters ──
    climate = DefaultClimateAdapter()
    water = DefaultWaterAdapter()
    afolu = DefaultAFOLUAdapter(biomass_curves)

    # ── Step 4: Assemble model ──
    model = GHIMModel(regions, trade, tech_change, policy,
                      climate, water, afolu)
    model.bunkers = bunkers

    return model, initial_state
```

**Calibration order matters:**
1. Economy first (GDP determines sector demand envelopes)
2. Demand sectors second (need base_gdp for calibration)
3. Transformation sectors third (need fuel prices for LCOE)
4. Vintage initialization last (needs calibrated base-year quantities)

**Mapping from current code:**

| Current function | New OOP equivalent |
|-----------------|-------------------|
| `build_region_model()` | Steps 1a–1f above |
| `_default_fuel_prices()` | `load_base_prices()` from data |
| `rm.calibrate(gdp)` | Per-sector `calibrate()` calls |
| `rm.klem.init_tfp_trajectory()` | `economy.calibrate_tfp_trajectory()` |
| `TradeModule(supplies, costs)` | `TradeModule(regions)` reads from `Region.resources` |


## 16. PolicyEngine

### 16.1 Design: Composition, not inheritance

Policy instruments are **dataclass containers** queried by sectors during F(x). No inheritance hierarchy — each instrument has its own interface. `PolicyScenario` composes them all.

```python
@dataclass
class PolicyScenario:
    """Container for all policy instruments. Passed to F(x)."""
    name: str = "reference"
    carbon_price: CarbonPricePolicy = field(default_factory=CarbonPricePolicy)
    renewable_subsidies: RenewableSubsidy = field(default_factory=RenewableSubsidy)
    efficiency_standards: EfficiencyStandard = field(default_factory=EfficiencyStandard)
    emissions_cap: EmissionsCap = field(default_factory=EmissionsCap)
    tech_constraints: list[TechConstraint] = field(default_factory=list)
    revenue_recycling: RevenueRecycling = field(default_factory=RevenueRecycling)
    tech_availability: TechAvailability = field(default_factory=TechAvailability)
    pref_overrides: PrefFactorOverride = field(default_factory=PrefFactorOverride)


@dataclass
class CarbonPricePolicy:
    """GHG pricing instrument. Single price in $/tCO₂eq.

    Phase 1 default: CO₂-only (cover_co2=True, rest False).
    Phase 2+: enable non-CO₂ coverage for comprehensive GHG tax.
    """
    trajectory: dict[int, float] = field(default_factory=dict)  # year → $/tCO₂eq

    # Coverage toggles — which GHGs respond to the price signal
    cover_co2: bool = True               # CO₂ from combustion (supply + demand)
    cover_fugitive_ch4: bool = False      # CH₄ from fossil production → fuel price adder
    cover_agriculture_ghg: bool = False   # CH₄/N₂O from agriculture → sector price adder
    cover_fgases: bool = False            # F-gases → cooling cost adder

    def get_price(self, year: int) -> float:
        return _interpolate(self.trajectory, year)


@dataclass
class RenewableSubsidy:
    """Production tax credit or feed-in premium for clean technologies.
    Applied in Step 4 (Transformation): reduces effective LCOE for eligible techs.
    """
    eligible_techs: list[str] = field(default_factory=list)
    # e.g., ["solar_pv", "wind", "wind_offshore"]
    subsidy_per_gj: float = 0.0        # $/GJ production subsidy
    # Alternative: percentage of capex
    capex_subsidy_frac: float = 0.0    # fraction of capex covered (0-1)
    start_year: int = 2025
    end_year: int = 2100
    phase_out_years: int = 0           # linear phase-out over N years after end_year

    def get_subsidy(self, tech_name: str, year: int) -> float:
        """Returns $/GJ subsidy for tech in given year. 0 if not eligible or expired."""
        if tech_name not in self.eligible_techs:
            return 0.0
        if year < self.start_year or year > self.end_year + self.phase_out_years:
            return 0.0
        if year > self.end_year:
            frac = 1.0 - (year - self.end_year) / self.phase_out_years
            return self.subsidy_per_gj * frac
        return self.subsidy_per_gj


@dataclass
class EfficiencyStandard:
    """Mandatory energy efficiency improvement applied to demand sectors.
    Reduces energy intensity by a fixed annual rate (AEEI).
    Applied in Step 1 (Demand): multiplies demand envelope by efficiency factor.
    """
    sector_rates: dict[str, float] = field(default_factory=dict)
    # e.g., {"industry": 0.01, "buildings": 0.015, "transport": 0.01}
    # Annual efficiency improvement rate (0.01 = 1%/yr)
    start_year: int = 2025

    def efficiency_factor(self, sector: str, year: int) -> float:
        """Returns multiplier on energy demand (< 1.0 means less energy needed)."""
        rate = self.sector_rates.get(sector, 0.0)
        years = max(year - self.start_year, 0)
        return (1.0 - rate) ** years


@dataclass
class EmissionsCap:
    """Absolute emissions cap (MtCO2eq). Solved via bisection on shadow carbon price.
    Wraps the outer solver: finds τ such that total emissions ≤ cap.
    See §16.3 for bisection algorithm.
    """
    caps: dict[int, float] = field(default_factory=dict)
    # {year: MtCO2eq cap}, linearly interpolated between specified years
    gas_coverage: str = "co2_only"     # "co2_only" | "all_ghg" | "co2_and_ch4"
    exclude_lulucf: bool = True        # cap applies to co2eq_excl_lulucf by default
    price_floor: float = 0.0           # $/tCO2eq minimum shadow price
    price_ceiling: float = 5000.0      # $/tCO2eq maximum shadow price
    bisection_tol: float = 0.01        # convergence tolerance (fraction of cap)

    def get_cap(self, year: int) -> float | None:
        """Returns cap for year (MtCO2eq), or None if uncapped."""
        if not self.caps:
            return None
        years = sorted(self.caps.keys())
        if year < years[0]:
            return None
        if year >= years[-1]:
            return self.caps[years[-1]]
        # Linear interpolation
        for i in range(len(years) - 1):
            if years[i] <= year < years[i + 1]:
                frac = (year - years[i]) / (years[i + 1] - years[i])
                return self.caps[years[i]] * (1 - frac) + self.caps[years[i + 1]] * frac
        return None


@dataclass
class TechConstraint:
    """Minimum or maximum share constraints on technologies or carriers.
    Applied after logit in Step 2/4: clips shares and renormalizes.
    """
    min_shares: dict[str, dict[int, float]] = field(default_factory=dict)
    # {"sector.tech": {year: min_share}} e.g., {"electricity.solar_pv": {2030: 0.10}}
    max_shares: dict[str, dict[int, float]] = field(default_factory=dict)
    # {"sector.tech": {year: max_share}} e.g., {"electricity.coal": {2035: 0.20}}

    def get_min(self, key: str, year: int) -> float:
        """Returns minimum share for sector.tech at year. 0.0 if unconstrained."""
        return self._interpolate(self.min_shares.get(key, {}), year, default=0.0)

    def get_max(self, key: str, year: int) -> float:
        """Returns maximum share for sector.tech at year. 1.0 if unconstrained."""
        return self._interpolate(self.max_shares.get(key, {}), year, default=1.0)

    @staticmethod
    def _interpolate(schedule: dict[int, float], year: int, default: float) -> float:
        if not schedule:
            return default
        years = sorted(schedule.keys())
        if year <= years[0]:
            return schedule[years[0]]
        if year >= years[-1]:
            return schedule[years[-1]]
        for i in range(len(years) - 1):
            if years[i] <= year < years[i + 1]:
                frac = (year - years[i]) / (years[i + 1] - years[i])
                return schedule[years[i]] * (1 - frac) + schedule[years[i + 1]] * frac
        return default


@dataclass
class RevenueRecycling:
    """How carbon tax revenue is recycled back to the economy.
    Applied in Step 8 (post-emissions): adjusts investment or transfers.
    Phase 1: diagnostic only (revenue computed but not recycled).
    """
    mode: str = "lump_sum"             # "lump_sum" | "capital_subsidy" | "labor_tax_cut" | "none"
    recycling_fraction: float = 1.0    # fraction of revenue recycled (0-1)
    # Phase 1: mode="none", revenue tracked as diagnostic
    # Phase 2+: lump_sum adds to Y, capital_subsidy reduces WACC, labor_tax_cut boosts L

    def compute_revenue(self, carbon_price: float, total_emissions_mtco2: float) -> float:
        """Carbon tax revenue in billion $/yr."""
        return carbon_price * total_emissions_mtco2 / 1e3  # $/tCO2 × MtCO2 / 1000 = bn$


@dataclass
class TechAvailability:
    """Controls α_i (availability switches) per technology per period.
    Applied in Step 2/4: sets α_i = 0 for unavailable technologies.
    Default: all techs available (α = 1). Override to block/unblock.
    """
    schedules: dict[str, dict[int, int]] = field(default_factory=dict)
    # {"sector.tech": {year: 0_or_1}}
    # e.g., {"electricity.coal_ccs": {2025: 0, 2030: 1}}  # CCS available from 2030
    # e.g., {"electricity.coal": {2040: 0}}                 # no new coal after 2040

    def is_available(self, key: str, year: int) -> bool:
        """Returns True if tech is available at year."""
        schedule = self.schedules.get(key, {})
        if not schedule:
            return True  # default: available
        years = sorted(schedule.keys())
        # Step function: use most recent year's value
        avail = 1
        for y in years:
            if y <= year:
                avail = schedule[y]
        return bool(avail)


@dataclass
class PrefFactorOverride:
    """Direct override of preference factors for specific technologies.
    Applied in Step 2/4: replaces calibrated p_i with policy-specified value.
    Use for subsidies that aren't cost-based (e.g., consumer incentives, mandates).
    """
    overrides: dict[str, dict[int, float]] = field(default_factory=dict)
    # {"sector.tech": {year: pref_factor_value}}
    # e.g., {"transport.bev": {2025: -5.0, 2030: -3.0, 2040: 0.0}}
    # Negative p_i = preference BONUS (makes tech more attractive)

    def get_override(self, key: str, year: int) -> float | None:
        """Returns overridden pref factor, or None if not overridden."""
        schedule = self.overrides.get(key, {})
        if not schedule:
            return None
        years = sorted(schedule.keys())
        if year < years[0]:
            return None
        # Linear interpolation
        if year >= years[-1]:
            return schedule[years[-1]]
        for i in range(len(years) - 1):
            if years[i] <= year < years[i + 1]:
                frac = (year - years[i]) / (years[i + 1] - years[i])
                return schedule[years[i]] * (1 - frac) + schedule[years[i + 1]] * frac
        return None


@dataclass
class PolicyEngine:
    """Composition of all policy instruments. Passed to F(x) steps.

    Each instrument is a dataclass with its own query interface.
    Sectors call the relevant instrument during their compute_*() methods.
    Default-constructed PolicyEngine is a no-policy reference scenario.
    """
    carbon_price: CarbonPricePolicy = field(default_factory=CarbonPricePolicy)
    renewable_subsidy: RenewableSubsidy = field(default_factory=RenewableSubsidy)
    efficiency_standard: EfficiencyStandard = field(default_factory=EfficiencyStandard)
    emissions_cap: EmissionsCap = field(default_factory=EmissionsCap)
    tech_constraint: TechConstraint = field(default_factory=TechConstraint)
    revenue_recycling: RevenueRecycling = field(default_factory=RevenueRecycling)
    tech_availability: TechAvailability = field(default_factory=TechAvailability)
    pref_override: PrefFactorOverride = field(default_factory=PrefFactorOverride)
```

### 16.2 How policy enters F(x)

Policy is **not a step** in F(x) — it modifies other steps:

| Policy instrument | Where in F(x) | Mechanism |
|-------------------|--------------|-----------|
| Carbon/GHG price (supply) | Step 4 | `SupplyTech.lcoe(raw_prices, τ)` adds `carbon_coef × (1−capture) × τ / eff` |
| Carbon/GHG price (demand) | Step 6a | `carrier_price += CARBON_COEFS × TC_TO_TCO2 × τ` on direct-use fuels |
| Fugitive CH₄ cost | Step 6a | `carrier_price += CH4_FUGITIVE × GWP100_CH4 × τ` (if `cover_fugitive_ch4`) |
| Tech availability (α) | Step 3, 4 | Logit `α_i = 0` blocks technology |
| Pref factor override | Step 3, 4 | Override calibrated pref factor |
| Renewable subsidy | Step 4 | `lcoe -= subsidy` before logit |
| Share constraint | Step 3, 4 | Post-logit clamp + redistribute |
| Efficiency standard | Step 3 | `demand *= cumulative_factor` |
| Revenue recycling | Step 8 | Carbon revenue offsets energy cost (diagnostic) |
| Emissions cap | **Outside** solver | Bisection on GHG price wrapping `solver.solve()` |

**Carbon tax: no double-counting invariant.**

```
Raw fuel prices (from trade)
    │
    ├──→ SupplyTech.lcoe(raw, τ)     carbon_cost = carbon_coef × (1-capture) × τ / eff
    │    → electricity/H₂/heat prices include carbon cost via LCOE
    │
    └──→ carrier_prices (Step 6a)     direct_fuel += CARBON_COEFS[fuel] × TC_TO_TCO₂ × τ
         CARBON_COEFS[electricity/H₂/heat] = 0  ← no double-count
```

Transformation sectors see **raw** prices and add carbon_cost explicitly (CCS gets reduced rate). Demand sectors see **consumer** prices where carbon tax is already embedded. Electricity/H₂/heat have zero CARBON_COEFS because their carbon cost is already in the LCOE-derived price.

### 16.3 Emissions cap: bisection wrapper

The emissions cap doesn't fit inside F(x) — it wraps the entire solve:

```python
def solve_with_cap(model, solver, state, cap_target):
    """Bisection: find carbon price such that emissions ≤ cap."""
    def emissions_at_price(p):
        model.policy.carbon_price = CarbonPricePolicy(trajectory={state.period: p})
        solved = solver.solve(model, deepcopy(state))
        return solved.global_emissions

    price = bisect(lambda p: emissions_at_price(p) - cap_target, 0.0, MAX_CARBON_PRICE)
    model.policy.carbon_price = CarbonPricePolicy(trajectory={state.period: price})
    return solver.solve(model, state)
```

### 16.4 Non-CO₂ GHG pricing

The `CarbonPricePolicy` is a **unified GHG price** ($/tCO₂eq). Each non-CO₂ gas has a coverage toggle that determines whether the price signal affects economic behavior. Emission *accounting* always includes all gases; coverage toggles control only the *price signal*.

#### 16.4.1 Fugitive CH₄ from fossil production (`cover_fugitive_ch4`)

Fossil extraction/processing leaks CH₄. Pricing these emissions raises the effective cost of fossil fuels, accelerating transition.

**Mechanism**: Adder on direct-use fuel prices (Step 6a):

$$\Delta P_{fuel} = \frac{CH4\_FUGITIVE_{fuel}}{10^9} \times GWP_{CH_4} \times \tau$$

where $CH4\_FUGITIVE$ is in tCH₄/EJ and the $10^9$ converts to tCH₄/GJ.

| Fuel | CH₄ fugitive (tCH₄/EJ) | Adder per $/tCO₂eq ($/GJ) | % of CO₂ adder |
|------|------------------------|---------------------------|----------------|
| Coal | 370,000 | 0.0103 | 11% |
| Oil | 120,000 | 0.0033 | — |
| Gas | 220,000 | 0.0061 | 11% |

Not negligible: at $100/tCO₂eq, fugitive CH₄ adds ~$1.0/GJ to coal (vs ~$9.4/GJ for CO₂).

**Supply-side effect**: When `cover_fugitive_ch4=True`, the CH₄ adder is also applied to `raw_fuel_prices` in Step 4 (before SupplyTech.lcoe). This means coal/gas power plants also see higher fuel costs from fugitive pricing — correct because fugitive emissions are upstream of both power generation and direct use.

#### 16.4.2 Agricultural non-energy emissions (`cover_agriculture_ghg`)

Agriculture emits CH₄ (enteric fermentation, rice paddies) and N₂O (fertilizers, manure), both scaling with the production index $Q_{ag}$.

**Mechanism**: GHG cost adder on the agriculture sector price index:

$$P_{ag}^{GHG} = P_{ag} + \frac{(base\_CH_4 \times GWP_{CH_4} + base\_N_2O \times GWP_{N_2O}) \times \tau}{E_{ag,base}}$$

This raises $P_{ag}$ → reduces $Q_{ag}$ via price elasticity $\gamma_{ag} = -0.2$ → reduces both energy demand AND non-energy emissions.

```python
class AgricultureSector(DemandSector):
    def sector_price_index(self, rs: RegionState) -> float:
        """Agriculture price index with optional non-energy GHG cost."""
        base_price = super().sector_price_index(rs)
        if not self.policy.carbon_price.cover_agriculture_ghg:
            return base_price
        ghg_price = self.policy.carbon_price.get_price(rs.period)
        ghg_intensity = (
            (self.base_ch4 * GWP100["ch4"] + self.base_n2o * GWP100["n2o"])
            / self.base_demand  # MtCO₂eq per EJ
        )
        ghg_adder = ghg_intensity * 1e6 * ghg_price / 1e9  # $/GJ
        return base_price + ghg_adder
```

**Feedback loop**: Higher P_ag → lower Q_ag → lower CH₄/N₂O (since non-energy emissions scale with Q_ag). This is the correct first-order response. Phase 2+ (AFOLU module) can provide more granular livestock vs crop decomposition.

#### 16.4.3 F-gases (`cover_fgases`)

F-gases (HFCs from air conditioning and refrigeration) are better addressed by the **Kigali Amendment** phase-down than by carbon pricing, because:
1. F-gas alternatives (low-GWP refrigerants) are technology substitution, not demand reduction
2. HFC leakage is equipment-dependent, not linearly proportional to service demand
3. The Kigali phase-down schedule is already agreed internationally

**Phase 1**: EDGAR-scaled proxy with Kigali phase-down. F-gas emissions = EDGAR base-year (MtCO₂eq per R32) × cooling demand growth ratio × Kigali factor. No stock model, no unit conversion issues.
```python
KIGALI_SCHEDULE = {2025: 1.0, 2030: 0.70, 2035: 0.50, 2040: 0.30, 2045: 0.20}
f_gas = EDGAR_FGAS[region] * (cooling_ej / cooling_base_ej) * kigali_factor
```

**Phase 2+**: If `cover_fgases=True`, add HFC cost to cooling services:
$$\Delta P_{cooling} = FGAS\_INTENSITY \times GWP_{HFC} \times \tau$$
This would increase cooling cost → shift to lower-GWP technologies (e.g., CO₂/ammonia systems). Full HFC stock-flow model with vintage tracking replaces the proxy.

#### 16.4.4 Waste CH₄

Population-driven with weak income elasticity. Limited abatement via carbon pricing (waste management is infrastructure, not fuel choice). **Not priced** in either phase — reported as diagnostic only. Phase 3+: waste management MAC (marginal abatement cost) curve.

#### 16.4.5 Summary: Non-CO₂ coverage by phase

| GHG source | Phase 1 | Phase 2+ | Mechanism |
|------------|---------|----------|-----------|
| CO₂ combustion | ✅ Priced | ✅ Priced | LCOE + carrier_price adder |
| Fugitive CH₄ | ❌ Reported only | ✅ Priced | Fuel price adder (Step 6a) |
| Agriculture CH₄/N₂O | ❌ Reported only | ✅ Priced | Sector price adder → Q_ag response |
| F-gases | ❌ Kigali phase-down | ✅ Optional pricing | Cooling cost adder |
| Waste CH₄ | ❌ Reported only | ❌ Reported only | MAC curve (Phase 3+) |

**Emissions cap interaction**: When `EmissionsCap` bisects on the GHG price to meet a CO₂eq target, the non-CO₂ coverage toggles determine which gases respond to the price. With `cover_fugitive_ch4=True`, the cap can be met partly through fossil CH₄ reduction (cheaper than CO₂ abatement in some cases). Without non-CO₂ coverage, the bisection must achieve the entire CO₂eq target through CO₂ reduction alone, leading to a higher shadow carbon price.

### 16.5 Policy loading

```python
# From JSON file
policy = load_policy("scenarios/net_zero_2050.json")

# From CLI
policy = policy_from_cli(carbon_price=50, efficiency_rate=0.01)

# Programmatic
policy = PolicyScenario(
    carbon_price=CarbonPricePolicy(trajectory={2025: 30, 2030: 80, 2050: 250}),
    tech_availability=TechAvailability(schedules={"electricity.coal_new": {2030: 0}}),
)
```

All trajectory parameters use **linear interpolation** between waypoints, flat beyond endpoints. JSON keys auto-converted to int via `_int_keys()`.


## 17. Reporting & Output

### 17.1 PeriodState → Output

```python
class Reporter:
    """Extracts structured output from solver results."""

    @staticmethod
    def to_dataframe(results: list[PeriodState]) -> pd.DataFrame:
        """Flatten all regions × periods into one DataFrame."""
        rows = []
        for state in results:
            for name, rs in state.regions.items():
                rows.append({
                    "year": state.period, "region": name,
                    "gdp": rs.gdp, "population": rs.population,
                    "total_energy_ej": sum(rs.final_demand.values()),
                    "emissions_co2eq_mt": rs.emissions,
                    "emissions_co2_mt": rs.emissions_detail.co2,
                    "emissions_ch4_mt": rs.emissions_detail.ch4,
                    "capital_stock": rs.capital_stock,
                    "investment": rs.investment,
                    "composite_energy_price": rs.composite_energy_price,
                    # Per-carrier demands
                    **{f"demand_{c.value}_ej": rs.final_demand.get(c, 0.0) for c in CARRIERS_7},
                    # Per-carrier prices
                    **{f"price_{c.value}": rs.carrier_prices.get(c, 0.0) for c in CARRIERS_7},
                    # Sector prices
                    **{f"sector_price_{s}": rs.sector_prices.get(s, 0.0)
                       for s in ["industry", "buildings", "transport", "agriculture"]},
                    # Trade
                    **{f"world_price_{f}": state.world_prices.get(f, 0.0) for f in TRADED_FUELS},
                    **{f"net_exports_{f}": rs.net_exports.get(f, 0.0) for f in TRADED_FUELS},
                })
        return pd.DataFrame(rows)

    @staticmethod
    def to_iamc(results: list[PeriodState]) -> pd.DataFrame:
        """IAMC long format: model|scenario|region|variable|unit|year|value."""
        ...
```

### 17.2 IAMC variable mapping

```python
IAMC_MAPPING = {
    "GDP|PPP":                         lambda rs: rs.gdp,
    "Population":                      lambda rs: rs.population,
    "Final Energy":                    lambda rs: sum(rs.final_demand.values()),
    "Final Energy|Electricity":        lambda rs: rs.final_demand.get(Carrier.ELECTRICITY, 0),
    "Emissions|CO2":                   lambda rs: rs.emissions_detail.co2,
    "Emissions|CO2|excl LULUCF":       lambda rs: rs.emissions_detail.co2eq_excl_lulucf,
    "Emissions|CH4":                   lambda rs: rs.emissions_detail.ch4,
    "Emissions|N2O":                   lambda rs: rs.emissions_detail.n2o,
    "Emissions|F-Gases":               lambda rs: rs.emissions_detail.f_gases,
    "Emissions|Kyoto Gases":           lambda rs: rs.emissions_detail.co2eq,     # net (with sinks)
    "Emissions|Kyoto Gases|excl LULUCF": lambda rs: rs.emissions_detail.co2eq_excl_lulucf,
    "Emissions|CO2|AFOLU":             lambda rs: rs.emissions_detail.lulucf,
    "Carbon Sequestration|CCS":        lambda rs: -min(rs.emissions_detail.co2, 0),  # captured CO2
    "Primary Energy|Coal":             lambda rs: rs.regional_production.get(Carrier.COAL, 0),
    "Price|Carbon":                    lambda state: state.policy_carbon_price,
    ...
}
```


## 18. Testing Strategy

### 18.1 Unit tests (per class)

| Class | What to test | Key assertions |
|-------|-------------|----------------|
| `Economy` | `calibrate()` reproduces base GDP | `compute_gross_output(rs, base_e) ≈ base_gdp` |
| `Economy` | TFP trajectory | `CES(TFP[y] × KL, E_ref) ≈ Y_SSP[y]` for all y |
| `Economy` | Energy demand FOC | `compute_energy_demand(rs) ≈ base_energy` at base prices |
| `Subsector` | Logit shares sum to 1 | `sum(shares.values()) ≈ 1.0` |
| `Subsector` | Calibrated pref reproduce base shares | After `calibrate()`, `compute_shares() ≈ base_shares` |
| `Subsector` | `price_index` consistency | Higher carrier prices → higher price_index |
| `VintageTracker` | `initialize_uniform` + `surviving` | `surviving(base_year) ≈ total` |
| `VintageTracker` | S-curve retirement | `surviving(base_year + lifetime) ≈ 0` |
| `EndUseTech` | `levelized_cost` | `capex + price/eff + fom` |
| `DemandSector` | `demand_envelope` response | Higher GDP → higher demand; higher price → lower demand |
| `DemandSector` | `sector_price_index` | Expenditure-weighted average of subsector prices |
| `TransformationSector` | `compute_supply` adds up | `sum(gen.values()) ≈ demand_ej` |
| `TransformationSector` | `compute_price` | share-weighted LCOE ≥ min(LCOE) |
| `ResourceSupply` | `production_at_price` | Monotonically increasing in price |
| `TradeModule` | Market clearing | `Σ supply(p*) ≈ Σ demand` |
| `EmissionResult` | `__add__`, `co2eq` | Component-wise addition, GWP weighting |
| `PolicyScenario` | Carbon price interpolation | `get_price(2027) ≈ lerp(2025, 2030)` |

### 18.2 Integration tests

| Test | What | Pass criterion |
|------|------|---------------|
| **F(x) single pass** | `model.F(state)` returns valid state | No NaN, positive GDP/prices |
| **Solver convergence** | `DampedSolver.solve()` converges | `residual < tol` within `max_iter` |
| **Base-year reproduction** | Solve at BASE_YEAR | GDP ≈ SSP GDP, energy ≈ calibration |
| **Price response** | Double energy prices | GDP < base GDP (CES feedback) |
| **Carbon price** | Apply $100/tCO2 | Coal demand ↓, emissions ↓, renewable share ↑ |
| **Trade clearing** | Enable trade | World prices within [floor, ceiling], Σ exports ≈ 0 |
| **Multi-period** | `run_model()` 3 periods | Capital grows, TFP follows trajectory |
| **Vintage inertia** | Solar cost → 0 | Coal doesn't disappear instantly (S-curve) |
| **BECCS negative** | biomass_ccs with τ=$200 | co2 < 0 for BECCS tech, LCOE reduced by CDR credit |
| **Emissions cap** | Cap at 50% of base | Carbon price > 0, emissions ≤ cap |

### 18.3 Regression tests

```python
def test_no_regression():
    """Run reference scenario, compare key outputs against saved baseline."""
    results = run_model(ssp_data, scenario="SSP2")
    baseline = load_baseline("tests/baselines/ssp2_reference.csv")
    for var in ["gdp", "emissions_co2", "total_energy"]:
        assert_allclose(results[var], baseline[var], rtol=0.01)
```

Baseline regenerated explicitly (`pytest --update-baseline`), never auto-updated.
