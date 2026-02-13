"""Model configuration: time horizon, constants, and settings."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GHIM_DATA_EXT = Path(__file__).resolve().parent / "data" / "external"

# ---------------------------------------------------------------------------
# Time horizon
# ---------------------------------------------------------------------------
HISTORY_START: int = 2000
BASE_YEAR: int = 2020
END_YEAR: int = 2150
TIMESTEP: int = 5  # years
HISTORICAL_YEARS: list[int] = list(range(HISTORY_START, BASE_YEAR + 1, TIMESTEP))
FUTURE_YEARS: list[int] = list(range(BASE_YEAR + TIMESTEP, END_YEAR + 1, TIMESTEP))
MODEL_YEARS: list[int] = HISTORICAL_YEARS + FUTURE_YEARS
NUM_PERIODS: int = len(MODEL_YEARS)

# ---------------------------------------------------------------------------
# Economic parameters
# ---------------------------------------------------------------------------
DISCOUNT_RATE: float = 0.05
DEPRECIATION_RATE: float = 0.05  # annual capital depreciation
LABOR_FORCE_PARTICIPATION: float = 0.65  # fraction of population as labor

# DICE-style endogenous GDP
CAPITAL_SHARE: float = 0.3          # alpha in K^alpha * L^(1-alpha)
SAVINGS_RATE: float = 0.22          # fraction of net output saved
INVESTMENT_CAP_RATE: float = 0.10   # max annual investment as fraction of K
CAPITAL_OUTPUT_RATIO: float = 3.0   # K/Y ratio for base-year capital calibration

# ---------------------------------------------------------------------------
# CES elasticities (KLEM nesting, WITCH-inspired defaults)
# ---------------------------------------------------------------------------
SIGMA_VA: float = 0.5    # Value Added: Capital vs Labor
SIGMA_EM: float = 0.5    # Energy-Materials composite (deprecated, kept for compat)
SIGMA_E: float = 1.0     # Electric vs Non-electric energy
SIGMA_NE: float = 2.0    # Among non-electric fuels (coal, oil, gas, biomass)

# CES-KLE: two-level nested CES production function
# Y = TFP × CES(VA, E; σ_KLE)  where VA = K^α × L^(1-α)
SIGMA_KLE: float = 0.4   # VA-Energy substitution (GCAM/WITCH range 0.3-0.5)
MIN_ENERGY_COST_SHARE: float = 0.05  # floor to prevent degenerate calibration

# Regional labor force participation rates (ILO 2020 estimates)
REGIONAL_LFP: dict[str, float] = {
    "Africa": 0.63,
    "Asia-Pacific Developed": 0.61,
    "Eastern Asia": 0.68,
    "Eurasia": 0.59,
    "Europe": 0.58,
    "Latin America and Caribbean": 0.62,
    "Middle East": 0.51,
    "North America": 0.61,
    "South-East Asia and developing Pacific": 0.67,
    "Southern Asia": 0.50,
}

# ---------------------------------------------------------------------------
# Logit parameters
# ---------------------------------------------------------------------------
DEFAULT_LOGIT_EXP: float = -3.0  # technology choice elasticity
ELEC_LOGIT_EXP: float = -4.0     # electricity sector
REFINING_LOGIT_EXP: float = -6.0
HYDROGEN_LOGIT_EXP: float = -3.0
DEMAND_LOGIT_EXP: float = -3.0   # fuel switching in final demand

# ---------------------------------------------------------------------------
# Preference factor parameters (MERGE-style logit)
# Share_i = exp(-k * (Cost_i + Pref_i)) / sum(exp(-k * (Cost_j + Pref_j)))
# ---------------------------------------------------------------------------
PREF_LOGIT_SCALE: float = 0.3       # k: sensitivity to cost ($/GJ)^-1
PREF_DECAY_RATE: float = 0.02       # annual decay rate for preference factors
# (1-0.02)^5 = 0.904 → ~10% decay per 5-year period; halve in ~35 years

# ---------------------------------------------------------------------------
# Relative preference logit (new default mode)
# s_i = α_i · exp(-k·P_i) · C_i^β / Σ_j α_j · exp(-k·P_j) · C_j^β
# ---------------------------------------------------------------------------
LOGIT_EXP_PREF: float = -4.0        # β for relative_pref_logit

# Per-technology annual decay rates for preference factors.
# Renewables/new tech decay faster (toward pure cost competition).
# Conventional fuels decay = 0 (no built-in preference drift).
PREF_DECAY_RATES: dict[str, float] = {
    "solar": 0.03, "wind": 0.03,
    "hydrogen": 0.03, "electrolysis": 0.03,
    "electricity": 0.02, "biomass": 0.02,
    "nuclear": 0.01, "refined liquids": 0.01,
    "coal": 0.0, "gas": 0.0, "gas_cc": 0.0,
    "hydro": 0.0, "oil": 0.0, "smr": 0.0,
}

# ---------------------------------------------------------------------------
# Stock turnover times (years)
# ---------------------------------------------------------------------------
TURNOVER_TIMES: dict[str, float] = {
    "electricity": 40.0,    # Power plants
    "hydrogen": 25.0,       # H2 plants
    "transport": 15.0,      # Vehicle fleet
    "industry": 30.0,       # Boilers/furnaces
    "buildings": 50.0,      # Heating systems
    "refining": 40.0,       # Refineries
    "data_centers": 7.0,    # Server hardware lifecycle
}

# ---------------------------------------------------------------------------
# Vintage stock retirement (GCAM-inspired S-curve)
# ---------------------------------------------------------------------------
TECH_RETIREMENT_LIFETIMES: dict[str, float] = {
    # Electricity
    "coal": 60.0, "gas_cc": 45.0, "nuclear": 60.0, "hydro": 80.0,
    "wind": 30.0, "solar": 30.0, "biomass": 60.0, "oil": 45.0,
    # Hydrogen
    "smr": 30.0, "electrolysis": 25.0,
}
SCURVE_STEEPNESS: float = 0.1           # k: S-curve shape parameter
SCURVE_HALFLIFE_RATIO: float = 0.75     # rho: more conservative than GCAM's 0.5
HARD_CUTOFF_TECHS: frozenset[str] = frozenset({"wind", "solar", "electrolysis"})

# Demand-sector carrier lifetimes (= equipment lifetime, not sector turnover)
CARRIER_RETIREMENT_LIFETIMES: dict[str, float] = {
    "transport": 20.0,      # vehicle fleet (all fuel types)
    "buildings": 30.0,      # heating systems (furnace/heat pump/boiler)
    "industry_heavy": 40.0, # industrial boilers/furnaces
    "industry_light": 25.0, # lighter equipment
    "data_centers": 10.0,   # server hardware lifecycle
}

# Profit shutdown (electricity only, stubs for now)
PROFIT_SHUTDOWN_MEDIAN: float = -0.1      # GCAM default
PROFIT_SHUTDOWN_STEEPNESS: float = 6.0
PROFIT_SHUTDOWN_OIL_MEDIAN: float = -0.5  # GCAM: refined liquids steam/CT

# Nuclear/hydro construction pipeline
CONSTRUCTION_TIMES: dict[str, int] = {"nuclear": 2, "hydro": 1}  # periods delay

# ---------------------------------------------------------------------------
# Learning-by-doing (WITCH-style experience curves)
# Cost(t) = Cost_0 * (Q_cum(t) / Q_0)^(-learn_exp)
# learn_exp = ln(1 - LR) / ln(2), where LR = learning rate
# ---------------------------------------------------------------------------
LEARNING_RATES: dict[str, float] = {
    # Electricity
    "solar": 0.20,          # 20% cost reduction per capacity doubling
    "wind": 0.12,           # 12%
    "biomass": 0.05,        # 5%
    "nuclear": 0.03,        # 3% (slow learning)
    "coal": 0.0,
    "gas": 0.0,
    "hydro": 0.0,
    "oil": 0.0,
    # Hydrogen
    "electrolysis": 0.15,   # 15% (scaling technology)
    "smr": 0.0,
    # Refining
    "oil_refining": 0.0,
}
COST_FLOOR_FRACTION: float = 0.2  # costs can't fall below 20% of initial

# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------
PRICE_TOL: float = 1e-3      # relative price convergence tolerance
MAX_PRICE_ITER: int = 100    # max iterations for market clearing
PRICE_DAMP: float = 0.5      # damping factor for price updates

# ---------------------------------------------------------------------------
# Energy unit conversions
# ---------------------------------------------------------------------------
EJ_PER_MTOE: float = 0.04186  # exajoules per million tonnes of oil equivalent
GJ_PER_KWH: float = 0.0036
HOURS_PER_YEAR: float = 8760.0
TC_TO_TCO2: float = 44.0 / 12.0  # tonnes carbon → tonnes CO2

# ---------------------------------------------------------------------------
# Capital recovery factor helper
# ---------------------------------------------------------------------------

def capital_recovery_factor(rate: float, lifetime: int) -> float:
    """Annualized payment factor for a given discount rate and lifetime."""
    if rate <= 0:
        return 1.0 / lifetime
    return rate * (1 + rate) ** lifetime / ((1 + rate) ** lifetime - 1)


# ---------------------------------------------------------------------------
# Default SSP scenario
# ---------------------------------------------------------------------------
DEFAULT_SSP: str = "SSP2"

# ---------------------------------------------------------------------------
# Carbon coefficients (tC per GJ of fuel input)
# Source: IPCC defaults, approximated
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Inter-regional trade
# ---------------------------------------------------------------------------
TRADED_FUELS: list[str] = ["coal", "oil", "gas"]
TRADE_PRICE_TOL: float = 0.01          # $/GJ tolerance for market clearing
TRADE_MAX_ITER: int = 50               # max bisection iterations
TRADE_PRICE_FLOOR: float = 0.1         # min world price $/GJ
TRADE_PRICE_CEILING: float = 50.0      # max world price $/GJ
TRADE_DEMAND_MAX_ITER: int = 10        # max demand-trade iterations per period
TRADE_DEMAND_DAMP: float = 0.5         # damping for price updates between iterations
TRADE_DEMAND_TOL: float = 0.02         # 2% relative price convergence for demand loop
TRADE_MAX_PRICE_CHANGE: float = 0.30   # max fractional price change per period (30%)
TRADE_MAX_PROD_DECLINE: float = 0.30   # max 30% production decline per region per period

# ---------------------------------------------------------------------------
# KLEM-Sector coupling (WITCH-style)
# ---------------------------------------------------------------------------
KLEM_SCALE_CLAMP: tuple[float, float] = (0.5, 2.0)  # deprecated, kept for compat
GCAM3_TO_2020_DEFLATOR: float = 3.79   # 1975$ → 2020$ GDP deflator (BEA 105.381/27.800)

# Observed 2020 fossil fuel prices (2020$/GJ) from BP Statistical Review
# via input/gcamdata/inst/extdata/energy/A10.rsrc_info_fossils.csv
# Converted: oil $41.84/bbl ÷ 6.193 GJ/bbl, coal avg($69.01,$50.13)/tonne ÷ 34.12 GJ/t,
# gas $4.06/mmBtu ÷ 1.055 GJ/mmBtu. These are world (extraction) prices, not delivered.
OBSERVED_FUEL_PRICES_2020: dict[str, float] = {
    "coal": 1.75,   # $/GJ
    "oil": 6.76,    # $/GJ
    "gas": 3.85,    # $/GJ
}

# ---------------------------------------------------------------------------
# Carbon coefficients (tC per GJ of fuel input)
# Source: IPCC defaults, approximated
# ---------------------------------------------------------------------------
CARBON_COEFS: dict[str, float] = {
    "coal": 0.0257,           # ~94.6 kgCO2/GJ → 25.8 kgC/GJ
    "gas": 0.0153,            # ~56.1 kgCO2/GJ → 15.3 kgC/GJ
    "refined liquids": 0.0,    # emissions at refining stage (avoid double-count)
    "biomass": 0.0,           # carbon neutral (biogenic)
    "nuclear": 0.0,
    "hydro": 0.0,
    "wind": 0.0,
    "solar": 0.0,
    "geothermal": 0.0,
    "hydrogen": 0.0,          # emissions at production stage
    "electricity": 0.0,       # emissions at generation stage
}
