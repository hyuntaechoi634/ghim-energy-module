"""Electricity generation sector model.

Computes electricity supply using logit-based technology competition
among coal, gas, nuclear, hydro, wind, solar, biomass, and oil technologies.
"""

from __future__ import annotations

import numpy as np

from ghim.config import ELEC_LOGIT_EXP, DISCOUNT_RATE
from ghim.energy.logit import logit_shares, logit_calibrate
from ghim.energy.technology import Technology, default_electricity_techs


class ElectricitySector:
    """Electricity generation sector for a single region.

    Attributes
    ----------
    techs : list[Technology]
        Available generation technologies.
    logit_exp : float
        Logit exponent for technology competition.
    total_generation_ej : float
        Current total electricity generation (EJ).
    """

    def __init__(
        self,
        techs: list[Technology] | None = None,
        logit_exp: float = ELEC_LOGIT_EXP,
    ):
        self.techs = techs or default_electricity_techs()
        self.logit_exp = logit_exp
        self.total_generation_ej = 0.0

    @property
    def tech_names(self) -> list[str]:
        return [t.name for t in self.techs]

    def calibrate(self, base_shares: dict[str, float], fuel_prices: dict[str, float]) -> None:
        """Calibrate share weights to reproduce base-year generation shares.

        Parameters
        ----------
        base_shares : dict
            Technology name → generation share (fractions summing to 1).
        fuel_prices : dict
            Fuel name → price in $/GJ.
        """
        shares_arr = np.array([base_shares.get(t.name, 0.01) for t in self.techs])
        # Normalize
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
        total_demand_ej: float,
    ) -> dict[str, float]:
        """Compute electricity generation by technology for given demand.

        Parameters
        ----------
        fuel_prices : dict
            Fuel name → price in $/GJ.
        total_demand_ej : float
            Total electricity demand (EJ).

        Returns
        -------
        dict
            Technology name → generation in EJ.
        """
        costs = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])
        weights = np.array([t.share_weight for t in self.techs])

        shares = logit_shares(costs, weights, self.logit_exp)
        self.total_generation_ej = total_demand_ej

        return {t.name: float(s * total_demand_ej) for t, s in zip(self.techs, shares)}

    def weighted_cost(self, fuel_prices: dict[str, float]) -> float:
        """Compute the weighted average cost of electricity ($/GJ)."""
        costs = np.array([
            t.levelized_cost(fuel_prices.get(t.fuel_input, 3.0))
            for t in self.techs
        ])
        weights = np.array([t.share_weight for t in self.techs])
        shares = logit_shares(costs, weights, self.logit_exp)
        return float(np.dot(shares, costs))

    def fuel_consumption(
        self,
        generation_by_tech: dict[str, float],
    ) -> dict[str, float]:
        """Compute fuel input requirements given generation by technology.

        Returns dict of fuel → consumption in EJ.
        """
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
