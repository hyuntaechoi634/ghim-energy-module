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
SIGMA_EM: float = 0.5    # Energy-Materials composite
SIGMA_E: float = 1.0     # Electric vs Non-electric energy
SIGMA_NE: float = 2.0    # Among non-electric fuels (coal, oil, gas, biomass)

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
GCAM3_TO_2020_DEFLATOR: float = 3.56   # 1975$ → 2020$ GDP deflator

# ---------------------------------------------------------------------------
# Carbon coefficients (tC per GJ of fuel input)
# Source: IPCC defaults, approximated
# ---------------------------------------------------------------------------
CARBON_COEFS: dict[str, float] = {
    "coal": 0.0257,           # ~94.6 kgCO2/GJ → 25.8 kgC/GJ
    "gas": 0.0153,            # ~56.1 kgCO2/GJ → 15.3 kgC/GJ
    "refined liquids": 0.0200, # ~73.3 kgCO2/GJ → 20.0 kgC/GJ
    "biomass": 0.0,           # carbon neutral (biogenic)
    "nuclear": 0.0,
    "hydro": 0.0,
    "wind": 0.0,
    "solar": 0.0,
    "geothermal": 0.0,
    "hydrogen": 0.0,          # emissions at production stage
    "electricity": 0.0,       # emissions at generation stage
}
