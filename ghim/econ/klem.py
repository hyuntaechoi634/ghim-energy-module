"""CES-KLE macroeconomic driver with energy as an explicit factor.

Production function:  Y ≈ VA = TFP × K^α × L^(1-α)
Energy demand from CES first-order condition:
  E = E_base × (VA/VA_base) × (P_E/P_E_base)^(-σ_KLE)

GDP is endogenous: energy costs reduce net output, which reduces
investment, which lowers capital stock, which lowers future GDP.

TFP trajectory is calibrated once from the SSP GDP path
(so Y ≈ Y_SSP without energy shocks), then held fixed.

Key improvements over old DICE-style approach:
- σ_KLE (0.4, GCAM/WITCH range) replaces ad-hoc σ_EM (0.5)
- Expenditure-weighted composite energy price replaces naive mean
- Regional labor force participation from ILO 2020 data
- No KLEM_SCALE_CLAMP hack — CES naturally determines total energy
"""

from __future__ import annotations

import numpy as np

from ghim.config import (
    SIGMA_KLE, MIN_ENERGY_COST_SHARE,
    CAPITAL_SHARE, SAVINGS_RATE, INVESTMENT_CAP_RATE,
    CAPITAL_OUTPUT_RATIO,
    DEPRECIATION_RATE, LABOR_FORCE_PARTICIPATION,
    TIMESTEP, BASE_YEAR, MODEL_YEARS, HISTORICAL_YEARS, FUTURE_YEARS,
    REGIONAL_LFP,
)


class KLEMDriver:
    """CES-KLE macro driver for a single region.

    Two-level structure:
        Level 1 (inner):  VA = TFP × K^α × L^(1-α)  (Cobb-Douglas)
        Level 2 (outer):  E demand from CES FOC: E/VA ∝ (P_E)^(-σ)
        Gross output:     Y = VA  (energy's contribution via cost feedback)

    Feedback loop:
        VA → CES FOC → E demand → energy cost
        → net_Y = Y - cost → I = s*net_Y → K(t+1)
    """

    def __init__(
        self,
        base_gdp: float,               # billion USD PPP
        base_population: float,         # millions
        base_energy_demand_ej: float,   # total energy demand (EJ)
        base_energy_price: float = 5.0, # composite energy price $/GJ at base year
        region: str = "",               # for regional LFP lookup
        capital_share: float = CAPITAL_SHARE,
        savings_rate: float = SAVINGS_RATE,
        sigma_kle: float = SIGMA_KLE,
    ):
        # Parameters
        self.alpha = capital_share
        self.savings_rate = savings_rate
        self.investment_cap_rate = INVESTMENT_CAP_RATE
        self.sigma_kle = sigma_kle

        # Base-year values
        self.base_gdp = base_gdp
        self.base_population = base_population
        self.base_energy = base_energy_demand_ej
        self.base_energy_price = max(base_energy_price, 0.01)
        self.region = region

        # Capital stock (K/Y ratio from config)
        self.capital_stock = base_gdp * CAPITAL_OUTPUT_RATIO

        # Regional labor force participation (ILO 2020)
        self.lfp = REGIONAL_LFP.get(region, LABOR_FORCE_PARTICIPATION)
        self.labor = base_population * self.lfp

        # Calibrate base TFP: A such that VA = base_gdp at base year
        kl = self.capital_stock ** self.alpha * self.labor ** (1.0 - self.alpha)
        self.tfp = base_gdp / kl if kl > 0 else 1.0

        # Energy cost share at base year: s_E = P_E × E / GDP
        self.base_energy_cost_share = max(
            base_energy_price * base_energy_demand_ej / base_gdp
            if base_gdp > 0 else MIN_ENERGY_COST_SHARE,
            MIN_ENERGY_COST_SHARE,
        )

        # TFP trajectory (populated by init_tfp_trajectory)
        self._tfp_trajectory: dict[int, float] = {BASE_YEAR: self.tfp}

        # Backward compat alias
        self.sigma_em = sigma_kle

    # ------------------------------------------------------------------
    # TFP trajectory
    # ------------------------------------------------------------------

    def init_tfp_trajectory(
        self,
        ssp_gdp_by_year: dict[int, float],
        pop_by_year: dict[int, float],
    ) -> None:
        """Pre-compute TFP so that Y_model ≈ Y_SSP without energy shocks.

        Forward-only algorithm starting from K(BASE_YEAR):
        1. A(BASE_YEAR) is already calibrated in __init__.
        2. Evolve a reference K forward using the savings rate and SSP GDP.
        3. At each future year, back out A(t) = Y_SSP / (K^α * L^(1-α)).

        The reference K trajectory represents "what K would be if the economy
        followed the SSP path with no energy shocks."  During simulation,
        actual K diverges through the energy cost feedback loop.
        """
        decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP

        # Base year: TFP already calibrated in __init__
        self._tfp_trajectory = {BASE_YEAR: self.tfp}

        # Forward-evolve reference K from K(BASE_YEAR)
        k_ref = self.capital_stock
        for year in FUTURE_YEARS:
            prev_year = year - TIMESTEP
            y_prev = ssp_gdp_by_year.get(prev_year, self.base_gdp)
            inv_ref = min(
                self.savings_rate * y_prev,
                self.investment_cap_rate * k_ref,
            )
            k_ref = decay * k_ref + inv_ref * TIMESTEP

            y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
            pop = pop_by_year.get(year, self.base_population)
            labor = pop * self.lfp

            kl = k_ref ** self.alpha * labor ** (1.0 - self.alpha)
            a = y_ssp / kl if kl > 0 else self.tfp
            self._tfp_trajectory[year] = a

    def set_tfp_for_year(self, year: int) -> None:
        """Set current TFP from pre-computed trajectory."""
        if year in self._tfp_trajectory:
            self.tfp = self._tfp_trajectory[year]

    # ------------------------------------------------------------------
    # Production & demand (CES-KLE)
    # ------------------------------------------------------------------

    def compute_value_added(self, population: float) -> float:
        """Value Added: VA = TFP × K^α × L^(1-α)  (Cobb-Douglas)."""
        self.labor = population * self.lfp
        return self.tfp * self.capital_stock ** self.alpha * self.labor ** (1.0 - self.alpha)

    def compute_energy_demand(
        self,
        value_added: float,
        energy_price: float,
    ) -> float:
        """Energy demand from CES first-order condition.

        E = E_base × (VA / VA_base) × (P_E / P_E_base)^(-σ_KLE)

        Derived from the CES cost-minimization FOC:
          E/VA = (α_E/α_VA)^σ × (P_VA/P_E)^σ

        At base year this reproduces E_base exactly. The response to
        price changes is governed by σ_KLE (the VA-Energy substitution
        elasticity).

        Parameters
        ----------
        value_added : float
            Current value added VA (billion USD PPP).
        energy_price : float
            Composite energy price ($/GJ).

        Returns
        -------
        float
            Total energy demand in EJ.
        """
        va_ratio = value_added / self.base_gdp if self.base_gdp > 0 else 1.0
        price_ratio = max(energy_price / self.base_energy_price, 0.01)
        return self.base_energy * va_ratio * price_ratio ** (-self.sigma_kle)

    def compute_gross_output(
        self,
        value_added: float,
        energy_ej: float,
    ) -> float:
        """Gross output Y ≈ VA.

        In a two-level CES, Y = CES(VA, E) ≈ VA when energy's cost share
        is small (~5%).  Energy's contribution to the economy is captured
        through the cost feedback loop (net_output = gross - energy_cost).

        Parameters
        ----------
        value_added : float
            Value added from Cobb-Douglas inner nest (billion USD).
        energy_ej : float
            Total energy input (EJ). Not directly used in Y calculation
            but kept in signature for interface consistency and potential
            future CES aggregation.
        """
        return value_added

    @staticmethod
    def composite_energy_price(
        carrier_prices: dict[str, float],
        carrier_demands: dict[str, float],
    ) -> float:
        """Expenditure-weighted composite energy price ($/GJ).

        Parameters
        ----------
        carrier_prices : dict
            Carrier name → price $/GJ.
        carrier_demands : dict
            Carrier name → demand EJ.

        Returns
        -------
        float
            Weighted average energy price.
        """
        total_cost = sum(
            carrier_prices.get(c, 5.0) * d
            for c, d in carrier_demands.items()
        )
        total_ej = sum(carrier_demands.values())
        return total_cost / total_ej if total_ej > 0 else 5.0

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
