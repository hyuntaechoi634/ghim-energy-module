"""Electricity generation sector model.

Computes electricity supply using preference-factor logit competition
among coal, gas, nuclear, hydro, wind, solar, biomass, and oil technologies.
Includes stock turnover and learning-by-doing.
"""

from __future__ import annotations

import numpy as np

from ghim.config import (
    ELEC_LOGIT_EXP, DISCOUNT_RATE, PREF_LOGIT_SCALE,
    TURNOVER_TIMES, TIMESTEP, HOURS_PER_YEAR,
)
from ghim.energy.logit import (
    logit_shares, logit_calibrate,
    preference_logit, preference_calibrate,
)
from ghim.energy.stock import apply_stock_turnover
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
    ):
        self.techs = techs or default_electricity_techs()
        self.logit_exp = logit_exp
        self.scale_k = scale_k
        self.turnover_time = turnover_time
        self.total_generation_ej = 0.0

        # Preference factors (calibrated at base year)
        self.pref_factors: np.ndarray | None = None
        self.base_pref_factors: np.ndarray | None = None

        # Stock turnover state
        self.current_shares: np.ndarray | None = None

    @property
    def tech_names(self) -> list[str]:
        return [t.name for t in self.techs]

    def calibrate(self, base_shares: dict[str, float], fuel_prices: dict[str, float]) -> None:
        """Calibrate preference factors to reproduce base-year generation shares."""
        shares_arr = np.array([base_shares.get(t.name, 0.01) for t in self.techs])
        shares_arr = shares_arr / shares_arr.sum()

        costs_arr = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])

        # Calibrate preference factors (MERGE-style)
        self.pref_factors = preference_calibrate(shares_arr, costs_arr, self.scale_k)
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

    def compute_supply(
        self,
        fuel_prices: dict[str, float],
        total_demand_ej: float,
        years_from_base: int = 0,
    ) -> dict[str, float]:
        """Compute electricity generation by technology.

        Uses preference logit for target shares, then applies stock
        turnover to blend with existing fleet.
        """
        costs = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])

        # Compute target shares from preference logit
        if self.pref_factors is not None:
            target_shares = preference_logit(costs, self.pref_factors, self.scale_k)
        else:
            weights = np.array([t.share_weight for t in self.techs])
            target_shares = logit_shares(costs, weights, self.logit_exp)

        # Apply stock turnover
        if self.current_shares is not None:
            effective_shares = apply_stock_turnover(
                self.current_shares, target_shares, TIMESTEP, self.turnover_time,
            )
            self.current_shares = effective_shares
        else:
            effective_shares = target_shares
            self.current_shares = target_shares.copy()

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
            shares = preference_logit(costs, self.pref_factors, self.scale_k)
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
