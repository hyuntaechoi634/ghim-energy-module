"""GHIM configuration: frozen dataclass hierarchy with sensible defaults.

Every parameter has a default value -- the model runs with ``GHIMConfig()``
and zero configuration files.  An optional YAML file overrides only the
parameters that differ from defaults.

Design principles:
  1. Every parameter has a default (no boilerplate config files).
  2. Type-safe frozen dataclasses (IDE autocomplete, mypy checking).
  3. YAML override is shallow merge (specify only what differs).
  4. One dataclass per module (mirrors model architecture).
  5. Phase 1: global only (no per-region overrides).
  6. Immutable after load (no accidental mutation during solver).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any


# ===================================================================
# Sub-configs
# ===================================================================

@dataclass(frozen=True)
class TimeConfig:
    """Model time horizon.  Derived year lists are computed as properties."""

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
        """All years on the time grid (historical + future)."""
        return self.historical_years + self.future_years

    @property
    def solve_years(self) -> list[int]:
        """Years the solver runs: base_year (calibration) + future."""
        return [self.base_year] + self.future_years


@dataclass(frozen=True)
class EconomyConfig:
    """CES production function parameters and macroeconomic constants."""

    # 4-level CES nesting: Q = CES(KLE, M; sigma_klem)
    #   KLE = CES(KL, E; sigma_kle)
    #   KL  = TFP * CES(K, L; sigma_kl)
    #   E   = CES(EL, NEL; sigma_el_nel)
    sigma_kl: float = 0.80       # K-L substitution (Oberfield & Raval 2021)
    sigma_kle: float = 0.40      # KL-E substitution (GCAM/WITCH range 0.3-0.5)
    sigma_el_nel: float = 2.0    # EL-NEL substitution (Zhu et al. 2023)
    sigma_klem: float = 0.20     # KLE-M substitution (near-Leontief)

    savings_rate: float = 0.22   # gross capital formation share (PWT 10.01)
    depreciation: float = 0.05   # annual capital depreciation
    materials_coef: float = 0.45 # non-energy intermediate share of gross output
    capital_share: float = 0.30  # alpha in K^alpha * L^(1-alpha)

    endogenous_gdp: bool = True   # True = CES solves GDP; False = exogenous SSP


@dataclass(frozen=True)
class SolverConfig:
    """Fixed-point solver parameters."""

    method: str = "damped"       # Phase 1: damped; Phase 2: anderson
    damping: float = 0.4         # alpha in x_{n+1} = (1-a)x_n + a*F(x_n)
    tolerance: float = 1e-3      # relative convergence criterion
    max_iter: int = 50           # max fixed-point iterations per period
    warm_start: bool = True      # use previous period's solution as initial guess


@dataclass(frozen=True)
class ElectricityConfig:
    """Electricity sector structural parameters."""

    num_techs: int = 17
    t_and_d_markup: float = 15.0               # $/MWh T&D markup (Phase 1: uniform)
    profit_shutdown_steepness: float = 6.0      # logistic shutdown curve (GCAM A23)
    profit_shutdown_median: float = -0.1        # profit ratio at 50% shutdown


@dataclass(frozen=True)
class VintageConfig:
    """Vintage stock retirement parameters."""

    scurve_steepness: float = 0.1
    scurve_halflife_ratio: float = 0.75
    # Phase 1: use current tech names; Phase C renames to R32 names
    hard_cutoff_techs: tuple[str, ...] = (
        "wind", "solar", "electrolysis",
    )


@dataclass(frozen=True)
class TradeConfig:
    """Global commodity market clearing parameters."""

    max_price_change: float = 0.30       # 30% max world price change per period
    max_prod_decline: float = 0.30       # 30% max regional production decline per period
    max_iter: int = 50                   # bisection iterations per commodity
    demand_trade_rounds: int = 10        # demand-trade iteration rounds within each F
    demand_trade_damping: float = 0.5    # damping for demand-trade price updates
    # Phase 1: coal/oil/gas; Phase 2+: add uranium, biomass
    traded_fuels: tuple[str, ...] = ("coal", "oil", "gas")


@dataclass(frozen=True)
class LearningConfig:
    """Technology learning curve parameters."""

    cost_floor_fraction: float = 0.20    # min cost = 20% of initial capex
    knowledge_depreciation: float = 0.10 # per-period knowledge stock depreciation
    exogenous_rnd: bool = True           # Phase 1: exogenous R&D spending


@dataclass(frozen=True)
class EmissionsConfig:
    """Multi-gas emissions accounting."""

    multi_gas: bool = True
    gwp100_ch4: float = 27.9    # AR6 WG1 Table 7.15
    gwp100_n2o: float = 273.0   # AR6 WG1 Table 7.15
    gwp100_hfc: float = 1530.0  # AR6 weighted average across HFC species


@dataclass(frozen=True)
class RegionConfig:
    """Regional structure."""

    num_regions: int = 32
    region_mapping_file: str = "ghim/data/external/common/GCAM_region_names.csv"


# ===================================================================
# Root config
# ===================================================================

@dataclass(frozen=True)
class GHIMConfig:
    """Root configuration composing all module configs."""

    time: TimeConfig = field(default_factory=TimeConfig)
    economy: EconomyConfig = field(default_factory=EconomyConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    electricity: ElectricityConfig = field(default_factory=ElectricityConfig)
    vintage: VintageConfig = field(default_factory=VintageConfig)
    trade: TradeConfig = field(default_factory=TradeConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    emissions: EmissionsConfig = field(default_factory=EmissionsConfig)
    regions: RegionConfig = field(default_factory=RegionConfig)


# ===================================================================
# Loading and override
# ===================================================================

def load_config(yaml_path: str | None = None) -> GHIMConfig:
    """Load config with all defaults, optionally overridden by YAML."""
    cfg = GHIMConfig()
    if yaml_path is None:
        return cfg

    import yaml  # lazy import -- yaml not needed when using defaults only

    with open(yaml_path) as f:
        overrides = yaml.safe_load(f)
    if not overrides:
        return cfg
    return _merge(cfg, overrides)


def _merge(cfg: GHIMConfig, overrides: dict[str, Any]) -> GHIMConfig:
    """Shallow merge: override matching fields on each sub-config."""
    updates: dict[str, Any] = {}
    for f in fields(cfg):
        if f.name in overrides and isinstance(overrides[f.name], dict):
            sub_cfg = getattr(cfg, f.name)
            sub_overrides = {
                k: v for k, v in overrides[f.name].items()
                if hasattr(sub_cfg, k)
            }
            if sub_overrides:
                updates[f.name] = replace(sub_cfg, **sub_overrides)
    return replace(cfg, **updates) if updates else cfg


# ===================================================================
# Module-level aliases from default config
#
# These provide backward-compatible names so existing code can do:
#   from ghim.core.config import BASE_YEAR, SIGMA_KL, ...
#
# New OOP code (Phase B+) should accept GHIMConfig and use
# cfg.economy.sigma_kl, cfg.time.base_year, etc.
# ===================================================================
_DEFAULT = GHIMConfig()

# Time
HISTORY_START: int = _DEFAULT.time.history_start
BASE_YEAR: int = _DEFAULT.time.base_year
END_YEAR: int = _DEFAULT.time.end_year
TIMESTEP: int = _DEFAULT.time.timestep
HISTORICAL_YEARS: list[int] = _DEFAULT.time.historical_years
FUTURE_YEARS: list[int] = _DEFAULT.time.future_years
MODEL_YEARS: list[int] = _DEFAULT.time.model_years
SOLVE_YEARS: list[int] = _DEFAULT.time.solve_years
NUM_PERIODS: int = len(MODEL_YEARS)

# Economy
SIGMA_KL: float = _DEFAULT.economy.sigma_kl
SIGMA_KLE: float = _DEFAULT.economy.sigma_kle
SAVINGS_RATE: float = _DEFAULT.economy.savings_rate
DEPRECIATION_RATE: float = _DEFAULT.economy.depreciation
CAPITAL_SHARE: float = _DEFAULT.economy.capital_share

# Solver
PRICE_TOL: float = _DEFAULT.solver.tolerance
MAX_PRICE_ITER: int = _DEFAULT.solver.max_iter
PRICE_DAMP: float = _DEFAULT.solver.damping

# Electricity
PROFIT_SHUTDOWN_STEEPNESS: float = _DEFAULT.electricity.profit_shutdown_steepness
PROFIT_SHUTDOWN_MEDIAN: float = _DEFAULT.electricity.profit_shutdown_median

# Vintage
SCURVE_STEEPNESS: float = _DEFAULT.vintage.scurve_steepness
SCURVE_HALFLIFE_RATIO: float = _DEFAULT.vintage.scurve_halflife_ratio
HARD_CUTOFF_TECHS: tuple[str, ...] = _DEFAULT.vintage.hard_cutoff_techs

# Trade
TRADED_FUELS: tuple[str, ...] = _DEFAULT.trade.traded_fuels
TRADE_MAX_ITER: int = _DEFAULT.trade.max_iter
TRADE_MAX_PRICE_CHANGE: float = _DEFAULT.trade.max_price_change
TRADE_MAX_PROD_DECLINE: float = _DEFAULT.trade.max_prod_decline
TRADE_DEMAND_MAX_ITER: int = _DEFAULT.trade.demand_trade_rounds
TRADE_DEMAND_DAMP: float = _DEFAULT.trade.demand_trade_damping

# Learning
COST_FLOOR_FRACTION: float = _DEFAULT.learning.cost_floor_fraction
