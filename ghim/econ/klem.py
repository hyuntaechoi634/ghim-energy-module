"""DICE-style macroeconomic driver with energy feedback.

Production function:  Y = A(t) * K(t)^α * L(t)^(1-α)

GDP is endogenous: energy costs reduce net output, which reduces
investment, which lowers capital stock, which lowers future GDP.

TFP trajectory A(t) is calibrated once from the SSP GDP path
(so Y ≈ Y_SSP without energy shocks), then held fixed.
"""

from __future__ import annotations

from ghim.config import (
    SIGMA_EM,
    CAPITAL_SHARE, SAVINGS_RATE, INVESTMENT_CAP_RATE,
    DEPRECIATION_RATE, LABOR_FORCE_PARTICIPATION,
    TIMESTEP, BASE_YEAR, MODEL_YEARS,
)


class KLEMDriver:
    """DICE-style macro driver for a single region.

    Feedback loop:
        Y = A*K^α*L^(1-α)  →  energy demand  →  energy cost
        →  net_Y = Y - cost  →  I = s*net_Y  →  K(t+1)
    """

    def __init__(
        self,
        base_gdp: float,               # billion USD PPP
        base_population: float,         # millions
        base_energy_demand_ej: float,   # total energy demand (EJ)
        capital_share: float = CAPITAL_SHARE,
        savings_rate: float = SAVINGS_RATE,
        sigma_em: float = SIGMA_EM,
    ):
        # Parameters
        self.alpha = capital_share
        self.savings_rate = savings_rate
        self.investment_cap_rate = INVESTMENT_CAP_RATE
        self.sigma_em = sigma_em

        # Base-year values
        self.base_gdp = base_gdp
        self.base_population = base_population
        self.base_energy = base_energy_demand_ej

        # Capital stock (K/Y ratio ≈ 3)
        self.capital_stock = base_gdp * 3.0

        # Labor
        self.labor = base_population * LABOR_FORCE_PARTICIPATION

        # Calibrate base TFP: A = Y / (K^α * L^(1-α))
        kl = self.capital_stock ** self.alpha * self.labor ** (1.0 - self.alpha)
        self.tfp = base_gdp / kl if kl > 0 else 1.0

        # TFP trajectory (populated by init_tfp_trajectory)
        self._tfp_trajectory: dict[int, float] = {BASE_YEAR: self.tfp}

    # ------------------------------------------------------------------
    # TFP trajectory
    # ------------------------------------------------------------------

    def init_tfp_trajectory(
        self,
        ssp_gdp_by_year: dict[int, float],
        pop_by_year: dict[int, float],
    ) -> None:
        """Pre-compute TFP so that Y_model ≈ Y_SSP without energy shocks.

        Simulates a reference K path (assuming full savings of gross output)
        and backs out A(t) at each period.
        """
        k_ref = self.capital_stock
        self._tfp_trajectory = {}

        for year in MODEL_YEARS:
            y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
            pop = pop_by_year.get(year, self.base_population)
            labor = pop * LABOR_FORCE_PARTICIPATION

            kl = k_ref ** self.alpha * labor ** (1.0 - self.alpha)
            a = y_ssp / kl if kl > 0 else self.tfp
            self._tfp_trajectory[year] = a

            # Evolve reference K (no energy shock)
            inv_ref = min(
                self.savings_rate * y_ssp,
                self.investment_cap_rate * k_ref,
            )
            decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP
            k_ref = decay * k_ref + inv_ref * TIMESTEP

    def set_tfp_for_year(self, year: int) -> None:
        """Set current TFP from pre-computed trajectory."""
        if year in self._tfp_trajectory:
            self.tfp = self._tfp_trajectory[year]

    # ------------------------------------------------------------------
    # Production & demand
    # ------------------------------------------------------------------

    def compute_gross_output(self, population: float) -> float:
        """Gross output: Y = A * K^α * L^(1-α)."""
        self.labor = population * LABOR_FORCE_PARTICIPATION
        return self.tfp * self.capital_stock ** self.alpha * self.labor ** (1.0 - self.alpha)

    def compute_energy_demand(
        self,
        gross_output: float,
        energy_price_index: float,
    ) -> float:
        """Energy demand responsive to GDP and prices.

        E = E_base * (Y / Y_base) * (P / P_base)^(-σ)

        Parameters
        ----------
        gross_output : float
            Current gross output (billion USD PPP).
        energy_price_index : float
            Composite energy price relative to base year (P/P_base).

        Returns
        -------
        float
            Total energy demand in EJ.
        """
        gdp_ratio = gross_output / self.base_gdp if self.base_gdp > 0 else 1.0
        price_ratio = max(energy_price_index, 0.01)
        return self.base_energy * gdp_ratio * price_ratio ** (-self.sigma_em)

    # ------------------------------------------------------------------
    # Energy cost & net output
    # ------------------------------------------------------------------

    @staticmethod
    def compute_energy_cost(energy_ej: float, avg_price_per_gj: float) -> float:
        """Energy cost in billion USD.

        1 EJ = 1e9 GJ, so cost = EJ * $/GJ * 1e9 / 1e9 = EJ * $/GJ.
        """
        return energy_ej * avg_price_per_gj

    @staticmethod
    def compute_net_output(gross_output: float, energy_cost: float) -> float:
        """Net output = gross - energy cost, floored at 1% of gross."""
        net = gross_output - energy_cost
        return max(net, 0.01 * gross_output)

    def compute_investment(self, net_output: float) -> float:
        """Investment = min(s * net_output, cap_rate * K)."""
        return min(
            self.savings_rate * net_output,
            self.investment_cap_rate * self.capital_stock,
        )

    def update_capital(self, investment: float) -> None:
        """Advance capital stock by one period.

        K(t+dt) = (1 - δ)^dt * K(t) + I * dt
        """
        decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP
        self.capital_stock = decay * self.capital_stock + investment * TIMESTEP
