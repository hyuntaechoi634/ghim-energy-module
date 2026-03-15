"""CES-KLE macroeconomic driver with energy as an explicit production factor.

Full nested CES production function:
  Level 1 (inner):  VA = TFP x CES(K, L; sigma_KL)       [CES]
  Level 2 (outer):  Y  = A_CES x CES(VA, E_val; sigma_KLE) [CES]
    where E_val = E (EJ) x P_E_base ($/GJ) = billion USD

Energy demand from CES first-order condition:
  E = E_base x (VA/VA_base) x (P_E/P_E_base)^(-sigma_KLE)

Investment directly from gross output:
  I = s x Y    (no separate energy cost subtraction)

GDP is endogenous: when energy prices rise, E falls, CES output falls,
investment falls, capital stock grows slower, future GDP is lower.

TFP trajectory is calibrated once from the SSP GDP path so that
Y = CES(VA, E_val) = Y_SSP in the reference case (no energy shocks).
"""

from __future__ import annotations

import numpy as np

from ghim.core.config import (
    SIGMA_KL, SIGMA_KLE, CAPITAL_SHARE, SAVINGS_RATE, DEPRECIATION_RATE,
    TIMESTEP, BASE_YEAR, MODEL_YEARS, HISTORICAL_YEARS, FUTURE_YEARS,
    EconomyConfig,
)
from ghim.config import (
    MIN_ENERGY_COST_SHARE, INVESTMENT_CAP_RATE, CAPITAL_OUTPUT_RATIO,
    LABOR_FORCE_PARTICIPATION, REGIONAL_LFP,
)
from ghim.econ.ces import ces_output, ces_calibrate

# Module-level defaults from EconomyConfig for new KLEM parameters
_ECON = EconomyConfig()
SIGMA_EL_NEL: float = _ECON.sigma_el_nel      # 2.0
SIGMA_KLEM: float = _ECON.sigma_klem          # 0.20
MATERIALS_COEF: float = _ECON.materials_coef   # 0.45


class KLEMDriver:
    """CES-KLE macro driver for a single region.

    Full nested CES structure:
        Level 1 (inner):  VA = TFP x CES(K, L; sigma_KL)     (CES)
        Level 2 (outer):  Y  = A_CES x CES(VA, E_val; sigma_KLE)  (CES)
            where E_val = E (EJ) x P_E_base ($/GJ)

    Energy demand from CES FOC:
        E = E_base x (VA/VA_base) x (P_E/P_E_base)^(-sigma_KLE)

    Investment:  I = s x Y  (directly from CES gross output)
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
        sigma_kl: float = SIGMA_KL,
        sigma_kle: float = SIGMA_KLE,
        sigma_el_nel: float = SIGMA_EL_NEL,
        sigma_klem: float = SIGMA_KLEM,
        materials_coef: float = MATERIALS_COEF,
        base_el_fraction: float = 0.20, # electricity share of total energy at base year
        base_el_price: float = 20.0,    # $/GJ for electricity at base year
    ):
        # Parameters
        self.alpha = capital_share
        self.savings_rate = savings_rate
        self.investment_cap_rate = INVESTMENT_CAP_RATE
        self.sigma_kl = sigma_kl
        self.sigma_kle = sigma_kle
        self.sigma_el_nel = sigma_el_nel
        self.sigma_klem = sigma_klem
        self.materials_coef = materials_coef

        # Base-year values
        self.base_gdp = base_gdp
        self.base_population = base_population
        self.base_energy = base_energy_demand_ej
        self.base_energy_price = max(base_energy_price, 0.01)
        self.region = region

        # Energy value at base year (billion USD): E_val = E x P_E_base
        self.base_energy_value = base_energy_demand_ej * self.base_energy_price

        # EL-NEL split at base year
        self.base_el_ej = base_energy_demand_ej * base_el_fraction
        self.base_nel_ej = base_energy_demand_ej * (1.0 - base_el_fraction)
        self.base_el_price = max(base_el_price, 0.01)
        # Non-electricity price: expenditure-weighted residual
        nel_expenditure = max(
            self.base_energy_value - self.base_el_ej * self.base_el_price, 0.01
        )
        self.base_nel_price = (
            nel_expenditure / max(self.base_nel_ej, 0.01)
        )

        # Capital stock (K/Y ratio from config)
        self.capital_stock = base_gdp * CAPITAL_OUTPUT_RATIO

        # Regional labor force participation (ILO 2020)
        self.lfp = REGIONAL_LFP.get(region, LABOR_FORCE_PARTICIPATION)
        self.labor = base_population * self.lfp

        # ----------------------------------------------------------
        # Level 1 (inner): K-L nest
        # ----------------------------------------------------------
        k = self.capital_stock
        l = self.labor
        r = self.alpha * base_gdp / k if k > 0 else 1.0
        w = (1.0 - self.alpha) * base_gdp / l if l > 0 else 1.0

        self._ces_alphas_kl = ces_calibrate(
            np.array([k, l]),
            np.array([r, w]),
            self.sigma_kl,
        )

        kl = ces_output(
            np.array([k, l]),
            self._ces_alphas_kl,
            self.sigma_kl,
        )

        # ----------------------------------------------------------
        # Level 2: EL-NEL energy substitution
        # EL_val and NEL_val in billion USD, prices = 1.0
        # ----------------------------------------------------------
        el_val = max(self.base_el_ej * self.base_el_price, 0.01)
        nel_val = max(self.base_nel_ej * self.base_nel_price, 0.01)
        self._ces_alphas_el_nel = ces_calibrate(
            np.array([el_val, nel_val]),
            np.array([1.0, 1.0]),
            self.sigma_el_nel,
        )

        # ----------------------------------------------------------
        # Level 3: VA-Energy nest (KLE)
        # ----------------------------------------------------------
        va_approx = base_gdp
        e_val = max(self.base_energy_value, 0.01)
        self._ces_alphas = ces_calibrate(
            np.array([va_approx, e_val]),
            np.array([1.0, 1.0]),
            self.sigma_kle,
        )

        ces_raw = ces_output(
            np.array([va_approx, e_val]),
            self._ces_alphas,
            self.sigma_kle,
            scale=1.0,
        )
        self.base_energy_cost = self.base_energy * self.base_energy_price  # billion $

        # KLE₀ = (1-m)×Q₀ = GDP₀ + E_cost₀  (KLE's share of gross output)
        # NOT GDP₀ — KLE bundles value-added AND energy.
        kle_base = base_gdp + self.base_energy_cost
        self.base_kle = kle_base
        self._ces_scale = kle_base / ces_raw if ces_raw > 0 else 1.0

        # ----------------------------------------------------------
        # Level 4: KLE-M nest (KLEM) — near-Leontief
        # GDP = Q - P_E·E - P_M·M  (net output)
        # P_M·M = m × Q  (materials share of gross output)
        # => Q = (GDP + E_cost) / (1 - m)
        # ----------------------------------------------------------
        q_base = (base_gdp + self.base_energy_cost) / (1.0 - materials_coef)
        m_val_base = max(materials_coef * q_base, 0.01)
        self._ces_alphas_klem = ces_calibrate(
            np.array([kle_base, m_val_base]),
            np.array([1.0, 1.0]),
            self.sigma_klem,
        )
        q_raw = ces_output(
            np.array([kle_base, m_val_base]),
            self._ces_alphas_klem,
            self.sigma_klem,
            scale=1.0,
        )
        self._ces_scale_klem = q_base / q_raw if q_raw > 0 else 1.0
        self.base_m_val = m_val_base
        self.base_q = q_base

        # ----------------------------------------------------------
        # Iteratively calibrate TFP so that compute_gdp = GDP_base
        # GDP = Q - E_cost - M_cost where Q = CES(KLE, M; σ_KLEM)
        # At base year with p = p_base, this reproduces GDP_base.
        # ----------------------------------------------------------
        tfp_guess = base_gdp / kl if kl > 0 else 1.0
        for _ in range(20):
            va = tfp_guess * kl
            e_ej = self.base_energy * (va / self.base_gdp) if self.base_gdp > 0 else self.base_energy
            gdp_out = self._gdp_from_va(va, e_ej, self.base_energy_price)
            if base_gdp > 0 and abs(gdp_out - base_gdp) / base_gdp < 1e-10:
                break
            if gdp_out > 0:
                tfp_guess *= base_gdp / gdp_out
        self.tfp = tfp_guess
        self._base_tfp = tfp_guess  # preserve for init_tfp_trajectory re-calls

        # Energy cost share at base year
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
    # CES helpers
    # ------------------------------------------------------------------

    def _ces_kl(self, capital: float, labor: float) -> float:
        """Inner CES: CES(K, L; sigma_KL)."""
        return ces_output(
            np.array([max(capital, 0.01), max(labor, 0.01)]),
            self._ces_alphas_kl,
            self.sigma_kl,
        )

    def _ces_gross(self, va: float, energy_ej: float) -> float:
        """Y = A_CES x CES(VA, E_val) where E_val = E x P_E_base."""
        e_val = energy_ej * self.base_energy_price
        return ces_output(
            np.array([va, max(e_val, 0.01)]),
            self._ces_alphas,
            self.sigma_kle,
            scale=self._ces_scale,
        )

    def _gdp_from_va(self, va: float, energy_ej: float, energy_price: float) -> float:
        """GDP = Q - P_E·E - P_M·M (internal, no bounds check)."""
        kle = self._ces_gross(va, energy_ej)
        kle_ratio = kle / self.base_kle if self.base_kle > 0 else 1.0
        m_val = self.base_m_val * kle_ratio
        q = ces_output(
            np.array([kle, max(m_val, 0.01)]),
            self._ces_alphas_klem,
            self.sigma_klem,
            scale=self._ces_scale_klem,
        )
        e_cost = energy_ej * energy_price     # billion $
        m_cost = self.materials_coef * q       # P_M·M = m × Q
        return q - e_cost - m_cost

    def compute_gdp(self, va: float, energy_ej: float, energy_price: float) -> float:
        """GDP = Q − P_E·E − P_M·M  (net output).

        Parameters
        ----------
        va : float
            Value added = TFP × CES_KL(K, L) (billion USD).
        energy_ej : float
            KLEM energy demand (EJ) from compute_energy_demand.
        energy_price : float
            Composite energy price ($/GJ).

        Returns
        -------
        float
            GDP (billion USD).
        """
        gdp = self._gdp_from_va(va, energy_ej, energy_price)
        # Floor: GDP cannot go negative (extreme price shocks)
        q = self.compute_gross_output_klem(va, energy_ej)
        return max(gdp, 0.01 * q)

    # ------------------------------------------------------------------
    # TFP trajectory
    # ------------------------------------------------------------------

    def init_tfp_trajectory(
        self,
        ssp_gdp_by_year: dict[int, float],
        pop_by_year: dict[int, float],
        ref_energy_by_year: dict[int, float] | None = None,
        ref_gdp_by_year: dict[int, float] | None = None,
        ref_price_by_year: dict[int, float] | None = None,
    ) -> None:
        """Pre-compute TFP so that GDP = Q - P_E·E - P_M·M = Y_SSP.

        Forward-only algorithm starting from K(BASE_YEAR):
        1. A(BASE_YEAR) is already calibrated in __init__.
        2. Evolve a reference K forward using I = s x Y_SSP.
        3. At each future year, find A(t) via bisection on _gdp_from_va.

        Parameters
        ----------
        ref_energy_by_year : optional
            Equilibrium energy from a calibration pass (not used directly
            but kept for API compatibility).
        ref_gdp_by_year : optional
            Actual GDP from a calibration pass. Used for K evolution.
        ref_price_by_year : optional
            Equilibrium composite energy price from a calibration pass.
            When provided, TFP calibration accounts for energy price
            feedback (GDP = Q - P_E·E - P_M·M with actual P_E).
        """
        decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP

        # Base year: restore __init__ TFP
        base_tfp = getattr(self, "_base_tfp", self.tfp)
        self.tfp = base_tfp
        self._tfp_trajectory = {BASE_YEAR: base_tfp}

        # Forward-evolve reference K from K(BASE_YEAR).
        # Compute kl with *current* k_ref BEFORE evolving K,
        # matching the model's inter-period capital timing.
        k_ref = self.capital_stock
        bg = self.base_gdp if self.base_gdp > 0 else 1.0
        be = self.base_energy
        p_base = self.base_energy_price

        for year in FUTURE_YEARS:
            y_ssp = ssp_gdp_by_year.get(year, self.base_gdp)
            pop = pop_by_year.get(year, self.base_population)
            labor = pop * self.lfp

            if labor <= 0:
                self._tfp_trajectory[year] = self.tfp
                inv_ref = min(self.savings_rate * y_ssp, self.investment_cap_rate * k_ref)
                k_ref = decay * k_ref + inv_ref * TIMESTEP
                continue

            kl = self._ces_kl(k_ref, labor)
            if kl <= 0:
                self._tfp_trajectory[year] = self.tfp
                inv_ref = min(self.savings_rate * y_ssp, self.investment_cap_rate * k_ref)
                k_ref = decay * k_ref + inv_ref * TIMESTEP
                continue

            # Reference energy price: use calibration pass if available
            p_ref = p_base
            if ref_price_by_year is not None and year in ref_price_by_year:
                p_ref = ref_price_by_year[year]

            # Find TFP such that GDP = Q - P_E·E - P_M·M = Y_SSP
            # E = base_energy × (VA/base_gdp) × (p_ref/p_base)^(-σ_KLE)
            price_effect = max(p_ref / p_base, 0.01) ** (-self.sigma_kle)

            def _gdp_at_tfp(tfp_val: float) -> float:
                va = tfp_val * kl
                e_ej = be * (va / bg) * price_effect
                return self._gdp_from_va(va, e_ej, p_ref)

            tfp_lo = y_ssp / kl * 0.01
            tfp_hi = y_ssp / kl * 100.0
            tfp_guess = y_ssp / kl

            # Ensure bracket contains root
            for _ in range(10):
                if _gdp_at_tfp(tfp_hi) >= y_ssp:
                    break
                tfp_hi *= 10.0
            for _ in range(80):
                gdp_out = _gdp_at_tfp(tfp_guess)
                if y_ssp > 0 and abs(gdp_out - y_ssp) / y_ssp < 1e-10:
                    break
                if gdp_out < y_ssp:
                    tfp_lo = tfp_guess
                else:
                    tfp_hi = tfp_guess
                tfp_guess = (tfp_lo + tfp_hi) / 2.0
            self._tfp_trajectory[year] = tfp_guess

            # Evolve K for next period
            if ref_gdp_by_year is not None and year in ref_gdp_by_year:
                y_for_inv = ref_gdp_by_year[year]
            else:
                y_for_inv = y_ssp
            inv_ref = min(
                self.savings_rate * y_for_inv,
                self.investment_cap_rate * k_ref,
            )
            k_ref = decay * k_ref + inv_ref * TIMESTEP

    def set_tfp_for_year(self, year: int) -> None:
        """Set current TFP from pre-computed trajectory."""
        if year in self._tfp_trajectory:
            self.tfp = self._tfp_trajectory[year]

    # ------------------------------------------------------------------
    # Production & demand (CES-KLE)
    # ------------------------------------------------------------------

    def compute_value_added(self, population: float) -> float:
        """Value Added: VA = TFP x CES(K, L; sigma_KL)."""
        self.labor = population * self.lfp
        return self.tfp * self._ces_kl(self.capital_stock, self.labor)

    def compute_energy_demand(
        self,
        value_added: float,
        energy_price: float,
    ) -> float:
        """Energy demand from CES first-order condition.

        E = E_base x (VA / VA_base) x (P_E / P_E_base)^(-sigma_KLE)

        Derived from the CES cost-minimization FOC.  At base year this
        reproduces E_base exactly.  The response to price changes is
        governed by sigma_KLE (the VA-Energy substitution elasticity).

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
        """Gross output Y = A_CES x CES(VA, E_val; sigma_KLE).

        Energy is an explicit factor of production.  E_val = E x P_E_base
        converts energy from physical units (EJ) to value units (billion USD)
        using the base-year energy price as a fixed scaling constant.

        Parameters
        ----------
        value_added : float
            Value added from CES inner nest (billion USD).
        energy_ej : float
            Total energy input (EJ).

        Returns
        -------
        float
            Gross output Y (billion USD).
        """
        return self._ces_gross(value_added, energy_ej)

    @staticmethod
    def composite_energy_price(
        carrier_prices: dict[str, float],
        carrier_demands: dict[str, float],
    ) -> float:
        """Expenditure-weighted composite energy price ($/GJ).

        Parameters
        ----------
        carrier_prices : dict
            Carrier name -> price $/GJ.
        carrier_demands : dict
            Carrier name -> demand EJ.

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
    # Level 2: EL-NEL energy split
    # ------------------------------------------------------------------

    def compute_energy_split(
        self,
        total_energy_ej: float,
        el_price: float,
        nel_price: float,
    ) -> tuple[float, float]:
        """Split total energy demand into electricity and non-electricity.

        Uses CES FOC with σ_EL_NEL:
          E_EL  = E_EL_base × (E/E_base) × (P_EL/P_EL_base)^(-σ)
          E_NEL = E_NEL_base × (E/E_base) × (P_NEL/P_NEL_base)^(-σ)
          Then rescale so EL + NEL = total.

        Parameters
        ----------
        total_energy_ej : float
            Total energy demand from CES FOC (EJ).
        el_price : float
            Electricity price ($/GJ).
        nel_price : float
            Non-electricity composite price ($/GJ).

        Returns
        -------
        (el_ej, nel_ej) : tuple[float, float]
            Electricity and non-electricity demand (EJ).
        """
        if self.base_energy <= 0:
            return total_energy_ej * 0.2, total_energy_ej * 0.8

        e_ratio = total_energy_ej / self.base_energy
        el_pr = max(el_price / self.base_el_price, 0.01)
        nel_pr = max(nel_price / self.base_nel_price, 0.01)

        el_raw = self.base_el_ej * e_ratio * el_pr ** (-self.sigma_el_nel)
        nel_raw = self.base_nel_ej * e_ratio * nel_pr ** (-self.sigma_el_nel)

        # Rescale to preserve total
        raw_total = el_raw + nel_raw
        if raw_total > 0:
            scale = total_energy_ej / raw_total
            return el_raw * scale, nel_raw * scale
        return total_energy_ej * 0.2, total_energy_ej * 0.8

    # ------------------------------------------------------------------
    # Level 4: KLEM gross output (with materials)
    # ------------------------------------------------------------------

    def compute_gross_output_klem(
        self,
        value_added: float,
        energy_ej: float,
    ) -> float:
        """Gross output Q = A_KLEM × CES(KLE, M; σ_KLEM).

        M (materials) is determined by Leontief-like CES with σ_KLEM ≈ 0.20.
        At base year: Q = GDP / (1 - materials_coef).

        Parameters
        ----------
        value_added : float
            Value added from CES inner nest (billion USD).
        energy_ej : float
            Total energy input (EJ).

        Returns
        -------
        float
            Gross output Q (billion USD), > GDP by materials overhead.
        """
        kle = self._ces_gross(value_added, energy_ej)
        # M scales with KLE (near-Leontief): M_val = M_base × (KLE/KLE_base)
        kle_ratio = kle / self.base_kle if self.base_kle > 0 else 1.0
        m_val = self.base_m_val * kle_ratio
        return ces_output(
            np.array([kle, max(m_val, 0.01)]),
            self._ces_alphas_klem,
            self.sigma_klem,
            scale=self._ces_scale_klem,
        )

    # ------------------------------------------------------------------
    # Energy cost (diagnostic, not used for investment)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_energy_cost(energy_ej: float, avg_price_per_gj: float) -> float:
        """Energy cost in billion USD (diagnostic only).

        1 EJ = 1e9 GJ, so cost = EJ x $/GJ x 1e9 / 1e9 = EJ x $/GJ.
        """
        return energy_ej * avg_price_per_gj

    @staticmethod
    def compute_net_output(gross_output: float, energy_cost: float) -> float:
        """Net output = gross - energy cost (diagnostic for reporting).

        In the full CES approach, this is NOT used for investment.
        Investment comes directly from gross_output (I = s x Y).
        """
        net = gross_output - energy_cost
        return max(net, 0.01 * gross_output)

    # ------------------------------------------------------------------
    # Investment & capital
    # ------------------------------------------------------------------

    def compute_investment(self, gross_output: float) -> float:
        """Investment I = min(s x Y, cap_rate x K).

        In the full CES approach, investment comes from gross output
        directly -- no energy cost subtraction.  Energy's effect on GDP
        is captured through the CES production function itself.
        """
        return min(
            self.savings_rate * gross_output,
            self.investment_cap_rate * self.capital_stock,
        )

    def update_capital(self, investment: float) -> None:
        """Advance capital stock by one period.

        K(t+dt) = (1 - delta)^dt x K(t) + I x dt
        """
        decay = (1.0 - DEPRECIATION_RATE) ** TIMESTEP
        self.capital_stock = decay * self.capital_stock + investment * TIMESTEP
