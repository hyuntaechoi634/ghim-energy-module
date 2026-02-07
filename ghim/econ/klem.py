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
    CAPITAL_OUTPUT_RATIO,
    DEPRECIATION_RATE, LABOR_FORCE_PARTICIPATION,
    TIMESTEP, BASE_YEAR, MODEL_YEARS, HISTORICAL_YEARS, FUTURE_YEARS,
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

        # Capital stock (K/Y ratio from config)
        self.capital_stock = base_gdp * CAPITAL_OUTPUT_RATIO

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

        Two-step algorithm:
        1. **Backward K solve** — invert capital accumulation from K(BASE_YEAR)
           back through historical years to get K(HISTORY_START).
        2. **Forward TFP calibration** — starting from K(HISTORY_START), evolve K
           forward and back out A(t) = Y_SSP / (K^α * L^(1-α)) at each period.
        """
        decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP

        # --- Step 1: backward solve for historical K ---
        # historical_years_desc = [2015, 2010, 2005, 2000] (reverse, excluding BASE_YEAR)
        historical_years_desc = list(reversed(HISTORICAL_YEARS[:-1]))
        k_hist: dict[int, float] = {BASE_YEAR: self.capital_stock}

        k_next = self.capital_stock
        for year in historical_years_desc:
            y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
            inv = min(self.savings_rate * y_ssp, self.investment_cap_rate * k_next)
            # K(t) = (K(t+dt) - I * dt) / decay
            k_prev = (k_next - inv * TIMESTEP) / decay
            # Floor: K cannot be less than 1% of GDP
            k_prev = max(k_prev, 0.01 * y_ssp)
            k_hist[year] = k_prev
            k_next = k_prev

        # --- Step 2: TFP calibration ---
        self._tfp_trajectory = {}

        # Historical years: use backward-solved K directly
        for year in HISTORICAL_YEARS:
            y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
            pop = pop_by_year.get(year, self.base_population)
            labor = pop * LABOR_FORCE_PARTICIPATION
            k_ref = k_hist[year]

            kl = k_ref ** self.alpha * labor ** (1.0 - self.alpha)
            a = y_ssp / kl if kl > 0 else self.tfp
            self._tfp_trajectory[year] = a

        # Future years: forward-evolve K from BASE_YEAR
        k_ref = self.capital_stock  # K(BASE_YEAR)
        for year in FUTURE_YEARS:
            # Evolve K first (using previous period's Y_SSP)
            prev_year = year - TIMESTEP
            y_prev = ssp_gdp_by_year.get(prev_year, self.base_gdp)
            inv_ref = min(
                self.savings_rate * y_prev,
                self.investment_cap_rate * k_ref,
            )
            k_ref = decay * k_ref + inv_ref * TIMESTEP

            # Calibrate TFP
            y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
            pop = pop_by_year.get(year, self.base_population)
            labor = pop * LABOR_FORCE_PARTICIPATION

            kl = k_ref ** self.alpha * labor ** (1.0 - self.alpha)
            a = y_ssp / kl if kl > 0 else self.tfp
            self._tfp_trajectory[year] = a

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
