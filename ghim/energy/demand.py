"""Final energy demand model.

Computes energy demand by sector (industry, buildings, transport) driven by
GDP and population growth.  Fuel switching across energy carriers uses logit
discrete choice.
"""

from __future__ import annotations

import numpy as np

from ghim.config import DEMAND_LOGIT_EXP, BASE_YEAR
from ghim.energy.logit import logit_shares, logit_calibrate

# Energy carriers available to final demand sectors
ENERGY_CARRIERS = ["coal", "refined liquids", "gas", "electricity", "biomass", "hydrogen"]

# Default fuel shares in final demand by sector (base year, approximate global avg)
DEFAULT_FUEL_SHARES: dict[str, dict[str, float]] = {
    "industry": {
        "coal": 0.25, "refined liquids": 0.15, "gas": 0.25,
        "electricity": 0.25, "biomass": 0.08, "hydrogen": 0.02,
    },
    "buildings": {
        "coal": 0.05, "refined liquids": 0.10, "gas": 0.30,
        "electricity": 0.40, "biomass": 0.14, "hydrogen": 0.01,
    },
    "transport": {
        "coal": 0.0, "refined liquids": 0.90, "gas": 0.03,
        "electricity": 0.03, "biomass": 0.03, "hydrogen": 0.01,
    },
}

# Income elasticities of energy demand by sector
INCOME_ELASTICITY: dict[str, float] = {
    "industry": 0.6,
    "buildings": 0.5,
    "transport": 0.7,
}


class FinalDemand:
    """Final energy demand for one sector in one region.

    Attributes
    ----------
    sector : str
        Sector name ("industry", "buildings", "transport").
    base_demand_ej : float
        Base-year total demand (EJ).
    fuel_shares : dict[str, float]
        Base-year fuel mix shares.
    share_weights : dict[str, float]
        Calibrated logit share weights for fuel switching.
    logit_exp : float
        Logit exponent for fuel switching.
    income_elasticity : float
        GDP elasticity of energy demand.
    """

    def __init__(
        self,
        sector: str,
        base_demand_ej: float,
        fuel_shares: dict[str, float] | None = None,
        logit_exp: float = DEMAND_LOGIT_EXP,
    ):
        self.sector = sector
        self.base_demand_ej = base_demand_ej
        self.fuel_shares = fuel_shares or DEFAULT_FUEL_SHARES.get(sector, {})
        self.logit_exp = logit_exp
        self.income_elasticity = INCOME_ELASTICITY.get(sector, 0.6)
        self.share_weights: dict[str, float] = {}
        self._base_gdp: float = 0.0

    def calibrate(self, fuel_prices: dict[str, float], base_gdp: float) -> None:
        """Calibrate share weights and store base-year GDP."""
        self._base_gdp = base_gdp
        carriers = list(self.fuel_shares.keys())
        shares = np.array([self.fuel_shares[c] for c in carriers])
        shares = np.maximum(shares, 1e-6)
        shares = shares / shares.sum()
        costs = np.array([fuel_prices.get(c, 5.0) for c in carriers])

        weights = logit_calibrate(shares, costs, self.logit_exp)
        self.share_weights = dict(zip(carriers, weights))

    def compute_demand(
        self,
        gdp: float,
        fuel_prices: dict[str, float],
    ) -> dict[str, float]:
        """Compute fuel demand by carrier for a given period.

        Parameters
        ----------
        gdp : float
            Current period GDP (billion USD PPP).
        fuel_prices : dict
            Energy carrier → price ($/GJ).

        Returns
        -------
        dict of carrier → demand in EJ.
        """
        # Total demand scales with GDP growth via income elasticity
        if self._base_gdp > 0:
            gdp_ratio = gdp / self._base_gdp
        else:
            gdp_ratio = 1.0

        total_demand = self.base_demand_ej * (gdp_ratio ** self.income_elasticity)

        # Fuel switching via logit
        carriers = list(self.share_weights.keys())
        if not carriers:
            carriers = list(self.fuel_shares.keys())
            weights = np.array([self.fuel_shares.get(c, 0.1) for c in carriers])
        else:
            weights = np.array([self.share_weights[c] for c in carriers])

        costs = np.array([fuel_prices.get(c, 5.0) for c in carriers])
        shares = logit_shares(costs, weights, self.logit_exp)

        return {c: float(s * total_demand) for c, s in zip(carriers, shares)}
