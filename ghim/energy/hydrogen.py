"""Hydrogen production sector model.

Produces hydrogen via SMR (gas) and electrolysis (electricity),
using preference-factor logit competition with vintage-bin stock
turnover (S-curve retirement) and learning-by-doing.
"""

from __future__ import annotations

import numpy as np

from ghim.config import (
    HYDROGEN_LOGIT_EXP, PREF_LOGIT_SCALE,
    TURNOVER_TIMES, TIMESTEP, HOURS_PER_YEAR,
    LOGIT_EXP_PREF, PREF_DECAY_RATES, BASE_YEAR,
    TECH_RETIREMENT_LIFETIMES,
)
from ghim.energy.logit import (
    logit_shares, logit_calibrate,
    preference_logit, preference_calibrate,
    relative_pref_logit,
)
from ghim.energy.stock import apply_stock_turnover, VintageStock
from ghim.energy.technology import Technology, default_hydrogen_techs


class HydrogenSector:
    """Hydrogen production for a single region.

    Uses MERGE-style preference factor logit with stock turnover
    and learning-by-doing cost reduction.
    """

    def __init__(
        self,
        techs: list[Technology] | None = None,
        logit_exp: float = HYDROGEN_LOGIT_EXP,
        scale_k: float = PREF_LOGIT_SCALE,
        turnover_time: float = TURNOVER_TIMES["hydrogen"],
    ):
        self.techs = techs or default_hydrogen_techs()
        self.logit_exp = logit_exp
        self.scale_k = scale_k
        self.turnover_time = turnover_time
        self.total_output_ej = 0.0

        # Preference factors (calibrated at base year)
        self.pref_factors: np.ndarray | None = None
        self.base_pref_factors: np.ndarray | None = None

        # Stock turnover state
        self.current_shares: np.ndarray | None = None

        # Vintage stock
        self.vintage_stock: VintageStock | None = None

    @property
    def tech_names(self) -> list[str]:
        return [t.name for t in self.techs]

    def calibrate(
        self,
        base_shares: dict[str, float],
        fuel_prices: dict[str, float],
    ) -> None:
        """Calibrate preference factors to reproduce base-year production shares."""
        shares_arr = np.array([base_shares.get(t.name, 0.5) for t in self.techs])
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

        # Initialize vintage stock (uniform — no GEM data for hydrogen)
        self.vintage_stock = VintageStock(
            tech_names=self.tech_names,
            lifetimes={t.name: TECH_RETIREMENT_LIFETIMES.get(t.name, 30.0)
                       for t in self.techs},
        )
        self.vintage_stock.initialize_uniform(
            shares_arr, max(self.total_output_ej, 0.01), BASE_YEAR,
        )

    def _compute_pref_factors(
        self,
        year: int | None,
        pref_overrides: dict[str, float] | None = None,
    ) -> np.ndarray:
        """Compute per-tech preference factors for a given year."""
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
        demand_ej: float,
        years_from_base: int = 0,
        cost_adjustments: dict[str, float] | None = None,
        share_constraints: list | None = None,
        year: int | None = None,
        alpha: np.ndarray | None = None,
        pref_overrides: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute hydrogen production by technology.

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

        Returns dict of technology name -> output EJ.
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
                year, target_shares, max(demand_ej, 0.01),
            )
            self.current_shares = effective_shares
        elif self.current_shares is not None:
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
                year, "hydrogen",
            )
            self.current_shares = effective_shares

        self.total_output_ej = demand_ej
        prod_by_tech = {
            t.name: float(s * demand_ej)
            for t, s in zip(self.techs, effective_shares)
        }

        # Update learning curves with new capacity
        for t in self.techs:
            prod_ej = prod_by_tech.get(t.name, 0.0)
            if prod_ej > 0 and t.capacity_factor > 0:
                capacity_gw = prod_ej / (t.capacity_factor * HOURS_PER_YEAR * 3.6e-3 * 1e-6)
                t.update_learning(capacity_gw)

        return prod_by_tech

    def fuel_consumption(self, production_by_tech: dict[str, float]) -> dict[str, float]:
        """Compute fuel inputs required for hydrogen production."""
        consumption: dict[str, float] = {}
        tech_map = {t.name: t for t in self.techs}
        for name, prod_ej in production_by_tech.items():
            t = tech_map[name]
            if t.efficiency > 0:
                fuel_ej = prod_ej / t.efficiency
                consumption[t.fuel_input] = consumption.get(t.fuel_input, 0.0) + fuel_ej
        return consumption

    def weighted_cost(self, fuel_prices: dict[str, float]) -> float:
        """Weighted average cost of hydrogen ($/GJ)."""
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

    def emissions_mtc(self, production_by_tech: dict[str, float]) -> float:
        """Total emissions from hydrogen production (MtC)."""
        tech_map = {t.name: t for t in self.techs}
        return sum(tech_map[n].annual_emissions_tc(p) for n, p in production_by_tech.items())
