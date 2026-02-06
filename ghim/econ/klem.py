"""KLEM macro-economic driver.

Implements a nested CES production function:

    Output (Y)
    +-- Value Added (VA)  [CES, sigma_VA]
    |   +-- Capital (K)
    |   +-- Labor (L)
    +-- Energy-Materials (EM)  [CES, sigma_EM]
        +-- Energy (E)
        +-- Materials (M)

GDP from SSP scenarios drives the overall output trajectory.
Energy demand is derived from the CES nesting, driving the energy sector model.
"""

from __future__ import annotations

import numpy as np

from ghim.config import (
    SIGMA_VA, SIGMA_EM, SIGMA_E, SIGMA_NE,
    DEPRECIATION_RATE, TIMESTEP, LABOR_FORCE_PARTICIPATION,
    BASE_YEAR,
)
from ghim.econ.ces import ces_demand, ces_price, ces_calibrate


class KLEMDriver:
    """KLEM macro driver for a single region.

    In the recursive-dynamic mode, GDP is exogenous (from SSP).
    The KLEM structure determines the energy demand consistent
    with the given GDP and energy prices.
    """

    def __init__(
        self,
        base_gdp: float,           # billion USD PPP
        base_population: float,     # millions
        base_energy_demand_ej: float,  # total energy demand (EJ)
        sigma_va: float = SIGMA_VA,
        sigma_em: float = SIGMA_EM,
    ):
        self.sigma_va = sigma_va
        self.sigma_em = sigma_em

        # Base-year values
        self.base_gdp = base_gdp
        self.base_population = base_population
        self.base_energy = base_energy_demand_ej

        # Derive base-year factor allocations (simplified)
        # Assume: energy cost share ~8% of GDP, materials ~12%, rest is value added
        self.energy_cost_share = 0.08
        self.materials_cost_share = 0.12
        self.va_share = 1.0 - self.energy_cost_share - self.materials_cost_share

        # Capital stock (assume K/Y ratio of ~3)
        self.capital_stock = base_gdp * 3.0

        # Calibrated CES parameters for Y = f(VA, EM)
        base_em = base_gdp * (self.energy_cost_share + self.materials_cost_share)
        base_va = base_gdp * self.va_share
        self.alpha_y = ces_calibrate(
            np.array([base_va, base_em]),
            np.array([1.0, 1.0]),  # normalized base prices
            sigma_em,
        )

    def compute_energy_demand(
        self,
        gdp: float,
        population: float,
        energy_price: float,
    ) -> float:
        """Compute total energy demand (EJ) for a given period.

        Uses the CES demand function: energy demand responds to
        GDP growth and relative energy prices.

        Parameters
        ----------
        gdp : float
            Current-period GDP (billion USD PPP).
        population : float
            Current-period population (millions).
        energy_price : float
            Composite energy price index ($/GJ, relative to base year).

        Returns
        -------
        float
            Total energy demand in EJ.
        """
        # Scale energy demand based on GDP growth and price response
        gdp_ratio = gdp / self.base_gdp if self.base_gdp > 0 else 1.0

        # CES-based demand response:
        # E = E_base * (GDP/GDP_base) * (P_E/P_E_base)^(-sigma_em)
        price_ratio = energy_price  # already relative to base = 1.0
        if price_ratio <= 0:
            price_ratio = 1.0

        energy_demand = (
            self.base_energy
            * gdp_ratio
            * price_ratio ** (-self.sigma_em)
        )

        return energy_demand

    def update_capital(self, investment: float) -> None:
        """Advance capital stock by one period.

        K(t+1) = (1 - delta)^dt * K(t) + I * dt
        """
        decay = (1 - DEPRECIATION_RATE) ** TIMESTEP
        self.capital_stock = decay * self.capital_stock + investment * TIMESTEP
