"""Electricity generation sector model.

Computes electricity supply using preference-factor logit competition
among coal, gas, nuclear, hydro, wind, solar, biomass, and oil technologies.
Includes vintage-bin stock turnover with S-curve retirement, pipeline-aware
nuclear/hydro investment, and learning-by-doing.
"""

from __future__ import annotations

import numpy as np

from ghim.config import (
    ELEC_LOGIT_EXP, DISCOUNT_RATE, PREF_LOGIT_SCALE,
    TURNOVER_TIMES, TIMESTEP, HOURS_PER_YEAR,
    LOGIT_EXP_PREF, PREF_DECAY_RATES, BASE_YEAR,
    TECH_RETIREMENT_LIFETIMES,
)
from ghim.energy.logit import (
    logit_shares, logit_calibrate,
    preference_logit, preference_calibrate,
    relative_pref_logit,
)
from ghim.energy.stock import (
    apply_stock_turnover,
    PipelineAwareVintageStock,
    NUCLEAR_PIPELINE_R10,
)
from ghim.energy.technology import Technology, default_electricity_techs


class ElectricitySector:
    """Electricity generation sector for a single region.

    Uses MERGE-style preference factor logit with stock turnover
    and learning-by-doing cost reduction.
    """

    def __init__(
        self,
        techs: list[Technology] | None = None,
        logit_exp: float = ELEC_LOGIT_EXP,
        scale_k: float = PREF_LOGIT_SCALE,
        turnover_time: float = TURNOVER_TIMES["electricity"],
        region: str | None = None,
    ):
        self.techs = techs or default_electricity_techs()
        self.logit_exp = logit_exp
        self.scale_k = scale_k
        self.turnover_time = turnover_time
        self.total_generation_ej = 0.0
        self.region = region

        # Preference factors (calibrated at base year)
        self.pref_factors: np.ndarray | None = None
        self.base_pref_factors: np.ndarray | None = None

        # Stock turnover state
        self.current_shares: np.ndarray | None = None

        # Vintage stock (pipeline-aware for nuclear/hydro)
        self.vintage_stock: PipelineAwareVintageStock | None = None

    @property
    def tech_names(self) -> list[str]:
        return [t.name for t in self.techs]

    def calibrate(
        self,
        base_shares: dict[str, float],
        fuel_prices: dict[str, float],
        gem_vintage_data: dict[str, dict[int, float]] | None = None,
    ) -> None:
        """Calibrate preference factors to reproduce base-year generation shares.

        Parameters
        ----------
        gem_vintage_data : dict, optional
            {tech: {vintage_year: ej}} from GEM preprocessing.
            If provided, initializes vintage stock from GEM data.
        """
        shares_arr = np.array([base_shares.get(t.name, 0.01) for t in self.techs])
        shares_arr = shares_arr / shares_arr.sum()

        costs_arr = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])

        # Calibrate preference factors (relative-pref mode)
        self.pref_factors = preference_calibrate(
            shares_arr, costs_arr, self.scale_k, logit_exp=self.logit_exp,
        )
        self.base_pref_factors = self.pref_factors.copy()

        # Initialize stock shares to base-year
        self.current_shares = shares_arr.copy()

        # Also calibrate legacy share weights for backward compat
        weights = logit_calibrate(shares_arr, costs_arr, self.logit_exp)
        for t, w in zip(self.techs, weights):
            t.share_weight = float(w)

        # Initialize cumulative capacity for learning
        for t, s in zip(self.techs, shares_arr):
            if t.cumulative_capacity == 0.0:
                t.cumulative_capacity = t.base_cumulative

        # Initialize vintage stock with pipeline awareness
        self.vintage_stock = PipelineAwareVintageStock(
            tech_names=self.tech_names,
            lifetimes={t.name: TECH_RETIREMENT_LIFETIMES.get(t.name, 40.0)
                       for t in self.techs},
        )
        if gem_vintage_data:
            self.vintage_stock.initialize_from_gem(
                gem_vintage_data, shares_arr, self.total_generation_ej, BASE_YEAR,
            )
        else:
            self.vintage_stock.initialize_uniform(
                shares_arr, self.total_generation_ej, BASE_YEAR,
            )

        # Pre-populate nuclear pipeline from WNA data
        if self.region and self.region in NUCLEAR_PIPELINE_R10:
            pipeline = NUCLEAR_PIPELINE_R10[self.region]
            if pipeline:
                self.vintage_stock.initialize_pipeline({"nuclear": pipeline})

    def _compute_pref_factors(
        self,
        year: int | None,
        pref_overrides: dict[str, float] | None = None,
    ) -> np.ndarray:
        """Compute per-tech preference factors for a given year.

        Uses PF override if available, otherwise decays from base PF
        using per-technology decay rates from ``PREF_DECAY_RATES``.
        """
        if self.base_pref_factors is None:
            return np.zeros(len(self.techs))

        years_elapsed = max((year or BASE_YEAR) - BASE_YEAR, 0)
        pf = np.empty(len(self.techs))
        for i, t in enumerate(self.techs):
            if pref_overrides and t.name in pref_overrides:
                pf[i] = pref_overrides[t.name]
            else:
                rate = PREF_DECAY_RATES.get(t.name, 0.0)
                pf[i] = self.base_pref_factors[i] * (1.0 - rate) ** years_elapsed
        return pf

    def compute_supply(
        self,
        fuel_prices: dict[str, float],
        total_demand_ej: float,
        years_from_base: int = 0,
        cost_adjustments: dict[str, float] | None = None,
        share_constraints: list | None = None,
        year: int | None = None,
        alpha: np.ndarray | None = None,
        pref_overrides: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute electricity generation by technology.

        Uses relative-pref logit for target shares, then applies stock
        turnover to blend with existing fleet.

        Parameters
        ----------
        cost_adjustments : dict, optional
            Tech name -> $/GJ subsidy to subtract from costs.
        share_constraints : list, optional
            TechConstraint objects for min/max share bounds.
        year : int, optional
            Current model year (needed for share constraints and PF decay).
        alpha : ndarray, optional
            Binary availability array {0,1} per technology.
        pref_overrides : dict, optional
            Tech name -> $/GJ explicit preference factor override.
        """
        costs = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])

        # Apply cost adjustments (subsidies reduce costs)
        if cost_adjustments:
            for i, t in enumerate(self.techs):
                adj = cost_adjustments.get(t.name, 0.0)
                if adj > 0:
                    costs[i] = max(costs[i] - adj, 0.01)

        # Compute target shares from relative-pref logit
        if self.pref_factors is not None:
            pf = self._compute_pref_factors(year, pref_overrides)
            self.pref_factors = pf
            target_shares = relative_pref_logit(
                costs, pf, self.scale_k, self.logit_exp, alpha,
            )
        else:
            weights = np.array([t.share_weight for t in self.techs])
            target_shares = logit_shares(costs, weights, self.logit_exp)

        # Apply vintage stock turnover (S-curve retirement + new investment)
        if self.vintage_stock is not None and year is not None:
            effective_shares = self.vintage_stock.retire_and_invest(
                year, target_shares, total_demand_ej,
            )
            self.current_shares = effective_shares
        elif self.current_shares is not None:
            # Fallback to simple share-blending if vintage stock not initialized
            effective_shares = apply_stock_turnover(
                self.current_shares, target_shares, TIMESTEP, self.turnover_time,
            )
            self.current_shares = effective_shares
        else:
            effective_shares = target_shares
            self.current_shares = target_shares.copy()

        # Apply share constraints (min/max bounds)
        if share_constraints and year is not None:
            from ghim.policy import apply_share_constraints
            effective_shares = apply_share_constraints(
                effective_shares, self.tech_names, share_constraints,
                year, "electricity",
            )
            self.current_shares = effective_shares

        self.total_generation_ej = total_demand_ej
        gen_by_tech = {
            t.name: float(s * total_demand_ej)
            for t, s in zip(self.techs, effective_shares)
        }

        # Update learning curves with new capacity
        for t in self.techs:
            gen_ej = gen_by_tech.get(t.name, 0.0)
            if gen_ej > 0 and t.capacity_factor > 0:
                # Convert EJ output → GW capacity: GW = EJ / (CF * 8760h * 3.6e-3 GJ/kWh * 1e-6 EJ/GJ)
                capacity_gw = gen_ej / (t.capacity_factor * HOURS_PER_YEAR * 3.6e-3 * 1e-6)
                t.update_learning(capacity_gw)

        return gen_by_tech

    def weighted_cost(self, fuel_prices: dict[str, float]) -> float:
        """Compute the weighted average cost of electricity ($/GJ)."""
        costs = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])
        if self.current_shares is not None:
            shares = self.current_shares
        elif self.pref_factors is not None:
            shares = relative_pref_logit(
                costs, self.pref_factors, self.scale_k, self.logit_exp,
            )
        else:
            weights = np.array([t.share_weight for t in self.techs])
            shares = logit_shares(costs, weights, self.logit_exp)
        return float(np.dot(shares, costs))

    def fuel_consumption(
        self,
        generation_by_tech: dict[str, float],
    ) -> dict[str, float]:
        """Compute fuel input requirements given generation by technology."""
        consumption: dict[str, float] = {}
        tech_map = {t.name: t for t in self.techs}
        for name, gen_ej in generation_by_tech.items():
            t = tech_map[name]
            if t.efficiency > 0:
                fuel_ej = gen_ej / t.efficiency
            else:
                fuel_ej = 0.0
            consumption[t.fuel_input] = consumption.get(t.fuel_input, 0.0) + fuel_ej
        return consumption

    def emissions_mtc(self, generation_by_tech: dict[str, float]) -> float:
        """Total CO2 emissions from electricity generation (MtC)."""
        tech_map = {t.name: t for t in self.techs}
        total = 0.0
        for name, gen_ej in generation_by_tech.items():
            total += tech_map[name].annual_emissions_tc(gen_ej)
        return total
