"""Hydrogen production sector model.

Produces hydrogen via SMR (gas) and electrolysis (electricity),
using logit-based competition between pathways.
"""

from __future__ import annotations

import numpy as np

from ghim.config import HYDROGEN_LOGIT_EXP
from ghim.energy.logit import logit_shares, logit_calibrate
from ghim.energy.technology import Technology, default_hydrogen_techs


class HydrogenSector:
    """Hydrogen production for a single region."""

    def __init__(
        self,
        techs: list[Technology] | None = None,
        logit_exp: float = HYDROGEN_LOGIT_EXP,
    ):
        self.techs = techs or default_hydrogen_techs()
        self.logit_exp = logit_exp
        self.total_output_ej = 0.0

    def calibrate(
        self,
        base_shares: dict[str, float],
        fuel_prices: dict[str, float],
    ) -> None:
        """Calibrate share weights from base-year shares."""
        shares_arr = np.array([base_shares.get(t.name, 0.5) for t in self.techs])
        shares_arr = shares_arr / shares_arr.sum()
        costs_arr = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])
        weights = logit_calibrate(shares_arr, costs_arr, self.logit_exp)
        for t, w in zip(self.techs, weights):
            t.share_weight = float(w)

    def compute_supply(
        self,
        fuel_prices: dict[str, float],
        demand_ej: float,
    ) -> dict[str, float]:
        """Compute hydrogen production by technology.

        Returns dict of technology name → output EJ.
        """
        costs = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])
        weights = np.array([t.share_weight for t in self.techs])
        shares = logit_shares(costs, weights, self.logit_exp)
        self.total_output_ej = demand_ej

        return {t.name: float(s * demand_ej) for t, s in zip(self.techs, shares)}

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
        weights = np.array([t.share_weight for t in self.techs])
        shares = logit_shares(costs, weights, self.logit_exp)
        return float(np.dot(shares, costs))

    def emissions_mtc(self, production_by_tech: dict[str, float]) -> float:
        """Total emissions from hydrogen production (MtC)."""
        tech_map = {t.name: t for t in self.techs}
        return sum(tech_map[n].annual_emissions_tc(p) for n, p in production_by_tech.items())
