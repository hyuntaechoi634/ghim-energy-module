# GHIM Energy Module — Configuration Design

## 1. Overview

All model parameters live in **frozen dataclasses** with sensible defaults. The model runs out of the box with zero configuration files. An optional YAML file overrides only the parameters that differ from defaults — no boilerplate.

### Design Principles

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | Every parameter has a default | Model runs with `GHIMConfig()` — no config file required |
| 2 | Type-safe frozen dataclasses | IDE autocomplete, `mypy` checking, no string-keyed dicts |
| 3 | YAML override is shallow merge | Specify only what differs; defaults fill the rest |
| 4 | One dataclass per module | Mirrors model architecture; easy to pass subconfig to subsystem |
| 5 | Phase 1: global only | No per-region overrides (Phase 2+) |
| 6 | Immutable after load | `@dataclass(frozen=True)` — no accidental mutation during solver |


## 2. Config Modules

### 2.1 Root Config

`GHIMConfig` composes all module configs. Every field has a default factory.

```python
@dataclass(frozen=True)
class GHIMConfig:
    economy: EconomyConfig = field(default_factory=EconomyConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    electricity: ElectricityConfig = field(default_factory=ElectricityConfig)
    vintage: VintageConfig = field(default_factory=VintageConfig)
    trade: TradeConfig = field(default_factory=TradeConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    emissions: EmissionsConfig = field(default_factory=EmissionsConfig)
    time: TimeConfig = field(default_factory=TimeConfig)
    regions: RegionConfig = field(default_factory=RegionConfig)
```

### 2.2 EconomyConfig

CES production function parameters and macroeconomic constants.

```python
@dataclass(frozen=True)
class EconomyConfig:
    sigma_kl: float = 0.80
    sigma_kle: float = 0.40
    sigma_el_nel: float = 2.0
    sigma_klem: float = 0.20
    savings_rate: float = 0.22
    depreciation: float = 0.05
    materials_coef: float = 0.45
    capital_share: float = 0.30
    endogenous_gdp: bool = True
```

| Parameter | Default | Source / Justification |
|-----------|---------|----------------------|
| `sigma_kl` | 0.80 | K-L substitution. Oberfield & Raval 2021 (*Econometrica*), range 0.6-1.0 |
| `sigma_kle` | 0.40 | KL-E substitution. Mid-range of EPPA (MIT), GCAM, WITCH (0.3-0.5) |
| `sigma_el_nel` | 2.0 | EL-NEL substitution. Zhu et al. 2023, GTAP-E (1.5-3.0) |
| `sigma_klem` | 0.20 | KLE-M substitution. Near-Leontief. Koesler & Schymura 2015 (0.0-0.5) |
| `savings_rate` | 0.22 | Gross capital formation share. PWT 10.01 cross-country mean |
| `depreciation` | 0.05 | Annual capital depreciation. Standard literature, PWT `delta` cross-check |
| `materials_coef` | 0.45 | Non-energy intermediate share of gross output. OECD STAN / GTAP / WIOD (GDP/GO $\approx$ 0.48) |
| `capital_share` | 0.30 | $\alpha$ in $K^\alpha L^{1-\alpha}$. Complement of PWT `labsh` |
| `endogenous_gdp` | True | `True` = CES production function solves GDP. `False` = exogenous SSP GDP |

### 2.3 SolverConfig

Fixed-point solver parameters. See `solver.md` for algorithm details.

```python
@dataclass(frozen=True)
class SolverConfig:
    method: str = "damped"
    damping: float = 0.4
    tolerance: float = 1e-3
    max_iter: int = 50
    warm_start: bool = True
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `method` | `"damped"` | Phase 1. `"anderson"` (Phase 2), `"newton_krylov"` (Phase 3+) |
| `damping` | 0.4 | $\alpha$ in $x_{n+1} = (1-\alpha)x_n + \alpha F(x_n)$. Range 0.1-0.9 |
| `tolerance` | 1e-3 | Relative convergence criterion $\|\Delta x\| / \|x\|$ |
| `max_iter` | 50 | Maximum fixed-point iterations per period |
| `warm_start` | True | Use previous period's solution as initial guess |

### 2.4 ElectricityConfig

Electricity sector structural parameters.

```python
@dataclass(frozen=True)
class ElectricityConfig:
    num_techs: int = 17
    t_and_d_markup: float = 15.0
    profit_shutdown_steepness: float = 6.0
    profit_shutdown_median: float = -0.1
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `num_techs` | 17 | Full technology list (see `electricity.md`) |
| `t_and_d_markup` | 15.0 | Transmission & distribution markup ($/MWh). Phase 1: uniform |
| `profit_shutdown_steepness` | 6.0 | Logistic shutdown curve steepness (GCAM A23) |
| `profit_shutdown_median` | -0.1 | Profit ratio at 50% shutdown (GCAM default) |

### 2.5 VintageConfig

Vintage stock retirement parameters. See `vintage_stock.md` for retirement model.

```python
@dataclass(frozen=True)
class VintageConfig:
    scurve_steepness: float = 0.1
    scurve_halflife_ratio: float = 0.75
    hard_cutoff_techs: tuple[str, ...] = (
        "wind_onshore", "wind_offshore", "solar_pv",
        "solar_csp", "electrolysis", "batteries",
    )
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `scurve_steepness` | 0.1 | $k$ in $S(a) = 1/(1+\exp(k(a-\rho L)))$ |
| `scurve_halflife_ratio` | 0.75 | $\rho$: retirement midpoint at 75% of lifetime |
| `hard_cutoff_techs` | 6 techs | No gradual retirement — full capacity until lifetime, then zero |

### 2.6 TradeConfig

Global commodity market clearing parameters. See `trade.md` for market design.

```python
@dataclass(frozen=True)
class TradeConfig:
    max_price_change: float = 0.30
    max_prod_decline: float = 0.30
    max_iter: int = 50
    demand_trade_rounds: int = 10
    demand_trade_damping: float = 0.5
    traded_fuels: tuple[str, ...] = ("coal", "oil", "gas", "uranium", "biomass")
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `max_price_change` | 0.30 | 30% max world price change per period (inter-period clamping) |
| `max_prod_decline` | 0.30 | 30% max regional production decline per period (inertia) |
| `max_iter` | 50 | Bisection iterations per commodity |
| `demand_trade_rounds` | 10 | Demand-trade iteration rounds within each $F$ evaluation |
| `demand_trade_damping` | 0.5 | Damping factor for demand-trade price updates |
| `traded_fuels` | 5 fuels | Commodities with global market clearing |

### 2.7 LearningConfig

Technology learning curve parameters. See `technology_change.md`.

```python
@dataclass(frozen=True)
class LearningConfig:
    cost_floor_fraction: float = 0.20
    knowledge_depreciation: float = 0.10
    exogenous_rnd: bool = True
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `cost_floor_fraction` | 0.20 | Minimum cost = 20% of initial capex. Tech-specific overrides possible |
| `knowledge_depreciation` | 0.10 | Per-period knowledge stock depreciation (~2%/yr over 5-year timestep) |
| `exogenous_rnd` | True | Phase 1: exogenous R&D spending. Phase 2: endogenous |

### 2.8 EmissionsConfig

Multi-gas emissions accounting. See `emiss.md`.

```python
@dataclass(frozen=True)
class EmissionsConfig:
    multi_gas: bool = True
    gwp100_ch4: float = 27.9
    gwp100_n2o: float = 273.0
    gwp100_hfc: float = 1530.0
```

| Parameter | Default | Source |
|-----------|---------|--------|
| `multi_gas` | True | Enable CO$_2$ + CH$_4$ + N$_2$O + F-gases |
| `gwp100_ch4` | 27.9 | AR6 WG1 Table 7.15 |
| `gwp100_n2o` | 273.0 | AR6 WG1 Table 7.15 |
| `gwp100_hfc` | 1530.0 | AR6 weighted average across HFC species |

### 2.9 TimeConfig

Model time horizon. Derived year lists computed as properties.

```python
@dataclass(frozen=True)
class TimeConfig:
    history_start: int = 2000
    base_year: int = 2021
    projection_start: int = 2025
    end_year: int = 2150
    timestep: int = 5

    @property
    def historical_years(self) -> list[int]:
        return list(range(self.history_start, self.base_year + 1, self.timestep))

    @property
    def future_years(self) -> list[int]:
        return list(range(self.projection_start, self.end_year + 1, self.timestep))

    @property
    def model_years(self) -> list[int]:
        return self.historical_years + self.future_years

    @property
    def solve_years(self) -> list[int]:
        return [self.base_year] + self.future_years
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `history_start` | 2000 | First historical year (SSP Historical Reference) |
| `base_year` | 2021 | Calibration year (CES shares, TFP, vintage initialization) |
| `projection_start` | 2025 | First projection year solved |
| `end_year` | 2150 | Last model year |
| `timestep` | 5 | Years per period |

### 2.10 RegionConfig

Regional structure.

```python
@dataclass(frozen=True)
class RegionConfig:
    num_regions: int = 32
    region_mapping_file: str = "ghim/data/external/common/GCAM_region_names.csv"
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `num_regions` | 32 | GCAM R32 regions |
| `region_mapping_file` | `GCAM_region_names.csv` | Region ID to name mapping |


## 3. Loading and Override

### 3.1 Loading function

```python
import yaml
from dataclasses import fields, replace

def load_config(yaml_path: str | None = None) -> GHIMConfig:
    """Load config with all defaults, optionally overridden by YAML."""
    cfg = GHIMConfig()  # all defaults
    if yaml_path is None:
        return cfg
    with open(yaml_path) as f:
        overrides = yaml.safe_load(f)
    return _merge(cfg, overrides)

def _merge(cfg: GHIMConfig, overrides: dict) -> GHIMConfig:
    """Shallow merge: override matching fields on each sub-config."""
    updates = {}
    for f in fields(cfg):
        if f.name in overrides and isinstance(overrides[f.name], dict):
            sub_cfg = getattr(cfg, f.name)
            sub_overrides = {k: v for k, v in overrides[f.name].items()
                            if hasattr(sub_cfg, k)}
            updates[f.name] = replace(sub_cfg, **sub_overrides)
    return replace(cfg, **updates)
```

**Key behavior**:
- `GHIMConfig()` with no arguments gives a fully valid configuration
- `load_config(None)` returns all defaults
- `load_config("scenario.yaml")` overrides only specified fields
- Unknown keys in YAML are silently ignored (Phase 2: add strict validation)
- `replace()` from `dataclasses` creates a new frozen instance with modified fields

### 3.2 YAML override example

```yaml
# scenario_high_elasticity.yaml
# Only specify what differs from defaults.
economy:
  sigma_kle: 0.5
  endogenous_gdp: false

solver:
  tolerance: 1e-4
  max_iter: 100

trade:
  max_price_change: 0.20
  traded_fuels: [coal, oil, gas, uranium, biomass]
```

### 3.3 Programmatic override

For sensitivity analysis and scripting, configs can be built without YAML:

```python
from dataclasses import replace

base = GHIMConfig()
high_elast = replace(base, economy=replace(base.economy, sigma_kle=0.5))
low_savings = replace(base, economy=replace(base.economy, savings_rate=0.18))
```

### 3.4 CLI integration

```python
# ghim/run.py
parser.add_argument("--config", type=str, default=None, help="YAML config file")
parser.add_argument("--scenario", type=str, default="SSP2")
parser.add_argument("--no-trade", action="store_true")
parser.add_argument("--carbon-price", type=float, default=0.0)

cfg = load_config(args.config)
```

CLI flags (e.g., `--no-trade`, `--carbon-price`) are separate from the config system. They control the **scenario**, not the **model parameters**. Policy instruments live in scenario JSON files (see `PolicyEngine` in `implementation.md`), not in config.


## 4. Precedence

```
dataclass defaults  →  YAML file  →  (Phase 2: CLI flags)
     lowest                               highest
```

Phase 1 has two levels. YAML overrides dataclass defaults via `replace()`.

Phase 2+ adds CLI flag overrides on top (e.g., `--solver.damping=0.3`).


## 5. Relationship to Current `config.py`

The current `config.py` uses module-level constants (`SIGMA_KL = 0.8`, `SAVINGS_RATE = 0.22`, etc.). The migration path:

| Step | Action |
|------|--------|
| 1 | Define frozen dataclasses alongside existing constants |
| 2 | Thread `GHIMConfig` through `__init__` of model classes |
| 3 | Replace bare constant references (e.g., `config.SIGMA_KL`) with `cfg.economy.sigma_kl` |
| 4 | Remove module-level constants (keep only `GHIM_DATA_EXT` path constant and unit conversions) |

Constants that stay at module level (not part of config):
- `GHIM_DATA_EXT` — data path (deployment concern, not model parameter)
- Unit conversions (`EJ_PER_MTOE`, `TC_TO_TCO2`, etc.) — physical constants, never overridden
- `capital_recovery_factor()` — utility function


## 6. Phase 2+ Roadmap

### 6.1 Regional parameter overrides

Phase 1 uses global parameters (one value per parameter for all 32 regions). Phase 2 adds per-region overrides:

```yaml
# Phase 2 YAML
economy:
  sigma_kle: 0.40          # global default
  regional_overrides:
    "USA": { sigma_kle: 0.45 }
    "China": { sigma_kle: 0.35, savings_rate: 0.30 }
```

Implementation: `RegionalConfig[T]` wrapper that stores a default `T` plus `dict[str, partial[T]]` overrides.

### 6.2 Config inheritance chains

```
base.yaml → scenario.yaml → sensitivity.yaml
```

Each file specifies only its diff from the parent. `load_config()` accepts a list of paths and applies merges left to right.

### 6.3 JSON Schema validation

Auto-generate JSON Schema from dataclass type hints. Validate YAML at load time — catch typos (`sigma_kl: "abc"`) before the solver runs.

### 6.4 CLI flag precedence

Full precedence chain:

```
dataclass defaults → base.yaml → scenario.yaml → CLI flags
```


## 7. Summary

| Property | Phase 1 | Phase 2+ |
|----------|---------|----------|
| Config format | Frozen dataclasses + optional YAML | Same + JSON Schema validation |
| Scope | Global parameters only | + Regional overrides |
| Override | Single YAML, shallow merge | Inheritance chains, CLI flags |
| Validation | Python type hints (`mypy`) | + JSON Schema, range checks |
| Module configs | 9 (economy, solver, electricity, vintage, trade, learning, emissions, time, regions) | Same + policy, reporting |
| Mutability | Frozen after load | Same |
