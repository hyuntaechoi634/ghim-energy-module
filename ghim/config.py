"""Non-config constants: paths, unit conversions, per-tech data, logit parameters.

Structural model parameters have moved to ``ghim.core.config`` (frozen
dataclass hierarchy).  Carbon-related constants are in ``ghim.core.carrier``.

This file retains:
  - GHIM_DATA_EXT (deployment path)
  - Unit conversions (physical constants, never overridden)
  - capital_recovery_factor() (utility function)
  - Per-technology data dicts (logit, lifetimes, learning rates, etc.)
  - Calibration data (observed prices, deflators)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Re-export from ghim.core for backward compatibility
# (safety net -- prefer direct imports from ghim.core.config / ghim.core.carrier)
# ---------------------------------------------------------------------------
from ghim.core.config import (  # noqa: F401
    HISTORY_START, BASE_YEAR, END_YEAR, TIMESTEP,
    HISTORICAL_YEARS, FUTURE_YEARS, MODEL_YEARS, SOLVE_YEARS, NUM_PERIODS,
    SIGMA_KL, SIGMA_KLE, SAVINGS_RATE, DEPRECIATION_RATE, CAPITAL_SHARE,
    PRICE_TOL, MAX_PRICE_ITER, PRICE_DAMP,
    PROFIT_SHUTDOWN_STEEPNESS, PROFIT_SHUTDOWN_MEDIAN,
    SCURVE_STEEPNESS, SCURVE_HALFLIFE_RATIO, HARD_CUTOFF_TECHS,
    TRADED_FUELS, TRADE_MAX_ITER, TRADE_MAX_PRICE_CHANGE, TRADE_MAX_PROD_DECLINE,
    TRADE_DEMAND_MAX_ITER, TRADE_DEMAND_DAMP,
    COST_FLOOR_FRACTION,
)
from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2  # noqa: F401

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GHIM_DATA_EXT = Path(__file__).resolve().parent / "data" / "external"

# ---------------------------------------------------------------------------
# Economic parameters (not in config hierarchy -- per-tech / calibration data)
# ---------------------------------------------------------------------------
DISCOUNT_RATE: float = 0.05
LABOR_FORCE_PARTICIPATION: float = 0.65  # global fallback
INVESTMENT_CAP_RATE: float = 0.10        # max annual investment as fraction of K
CAPITAL_OUTPUT_RATIO: float = 3.0        # K/Y ratio for base-year calibration
MIN_ENERGY_COST_SHARE: float = 0.05      # floor for CES calibration

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
# CES elasticities (deprecated -- kept for compatibility only)
# New code uses EconomyConfig.sigma_kl, sigma_kle, sigma_el_nel, sigma_klem
# ---------------------------------------------------------------------------
SIGMA_VA: float = 0.5
SIGMA_EM: float = 0.5
SIGMA_E: float = 1.0
SIGMA_NE: float = 2.0

# ---------------------------------------------------------------------------
# Logit parameters
# ---------------------------------------------------------------------------
DEFAULT_LOGIT_EXP: float = -3.0
ELEC_LOGIT_EXP: float = -4.0
REFINING_LOGIT_EXP: float = -6.0
HYDROGEN_LOGIT_EXP: float = -3.0
DEMAND_LOGIT_EXP: float = -3.0

# Preference factor logit (MERGE-style)
PREF_LOGIT_SCALE: float = 0.3
PREF_DECAY_RATE: float = 0.0
LOGIT_EXP_PREF: float = -4.0

# Per-technology annual decay rates for preference factors
# All set to 0 — preference factors frozen post-calibration.
PREF_DECAY_RATES: dict[str, float] = {
    "solar": 0.0, "wind": 0.0,
    "hydrogen": 0.0, "electrolysis": 0.0,
    "electricity": 0.0, "biomass": 0.0,
    "nuclear": 0.0, "refined liquids": 0.0,
    "coal": 0.0, "gas": 0.0, "gas_cc": 0.0,
    "hydro": 0.0, "oil": 0.0, "smr": 0.0,
}

# ---------------------------------------------------------------------------
# Stock turnover times (years)
# ---------------------------------------------------------------------------
TURNOVER_TIMES: dict[str, float] = {
    "electricity": 40.0,
    "hydrogen": 25.0,
    "transport": 15.0,
    "industry": 30.0,
    "buildings": 50.0,
    "refining": 40.0,
    "data_centers": 7.0,
}

# ---------------------------------------------------------------------------
# Vintage stock retirement -- per-tech data
# (Structural params moved to VintageConfig in ghim.core.config)
# ---------------------------------------------------------------------------
TECH_RETIREMENT_LIFETIMES: dict[str, float] = {
    # Electricity
    "coal": 60.0, "gas_cc": 45.0, "nuclear": 60.0, "hydro": 80.0,
    "wind": 30.0, "solar": 30.0, "biomass": 60.0, "oil": 45.0,
    # Hydrogen
    "smr": 30.0, "electrolysis": 25.0,
}

# Demand-sector carrier lifetimes
CARRIER_RETIREMENT_LIFETIMES: dict[str, float] = {
    "transport": 20.0,
    "buildings": 30.0,
    "industry_heavy": 40.0,
    "industry_light": 25.0,
    "data_centers": 10.0,
}

# Profit shutdown (electricity only)
PROFIT_SHUTDOWN_OIL_MEDIAN: float = -0.5  # GCAM: refined liquids steam/CT

# Nuclear/hydro construction pipeline
CONSTRUCTION_TIMES: dict[str, int] = {"nuclear": 3}  # periods delay (15 years)

# ---------------------------------------------------------------------------
# Learning-by-doing (WITCH-style experience curves)
# (cost_floor_fraction moved to LearningConfig in ghim.core.config)
# ---------------------------------------------------------------------------
LEARNING_RATES: dict[str, float] = {
    "solar": 0.20, "wind": 0.12, "biomass": 0.05, "nuclear": 0.03,
    "coal": 0.0, "gas": 0.0, "hydro": 0.0, "oil": 0.0,
    "electrolysis": 0.15, "smr": 0.0, "oil_refining": 0.0,
}

# ---------------------------------------------------------------------------
# Energy unit conversions
# ---------------------------------------------------------------------------
EJ_PER_MTOE: float = 0.04186
GJ_PER_KWH: float = 0.0036
HOURS_PER_YEAR: float = 8760.0


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
# Trade solver parameters (not in TradeConfig)
# ---------------------------------------------------------------------------
TRADE_PRICE_TOL: float = 0.01
TRADE_PRICE_FLOOR: float = 0.1
TRADE_PRICE_CEILING: float = 50.0
TRADE_DEMAND_TOL: float = 0.02

# ---------------------------------------------------------------------------
# KLEM-Sector coupling
# ---------------------------------------------------------------------------
KLEM_SCALE_CLAMP: tuple[float, float] = (0.5, 2.0)  # deprecated
GCAM3_TO_2020_DEFLATOR: float = 3.79  # 1975$ -> 2020$ (BEA 105.381/27.800)

# Observed 2020 fossil fuel prices (2020$/GJ) from BP Statistical Review
OBSERVED_FUEL_PRICES_2020: dict[str, float] = {
    "coal": 1.75,
    "oil": 6.76,
    "gas": 3.85,
}
