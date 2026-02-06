"""Model configuration: time horizon, constants, and settings."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
GCAMDATA_EXT = REPO_ROOT / "input" / "gcamdata" / "inst" / "extdata"

# ---------------------------------------------------------------------------
# Time horizon
# ---------------------------------------------------------------------------
BASE_YEAR: int = 2020
END_YEAR: int = 2100
TIMESTEP: int = 5  # years
MODEL_YEARS: list[int] = list(range(BASE_YEAR, END_YEAR + 1, TIMESTEP))
NUM_PERIODS: int = len(MODEL_YEARS)

# ---------------------------------------------------------------------------
# Economic parameters
# ---------------------------------------------------------------------------
DISCOUNT_RATE: float = 0.05
DEPRECIATION_RATE: float = 0.05  # annual capital depreciation
LABOR_FORCE_PARTICIPATION: float = 0.65  # fraction of population as labor

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
