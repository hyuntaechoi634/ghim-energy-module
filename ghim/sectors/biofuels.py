"""BiofuelsSector — biomass → biofuel conversion (2 techs)."""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.config import BASE_YEAR
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import SupplyTech
from ghim.energy.logit import preference_logit, preference_calibrate
from ghim.config import PREF_LOGIT_SCALE
from ghim.sectors.abc import TransformationSector


def default_biofuel_techs() -> list[SupplyTech]:
    return [
        SupplyTech("ethanol", "biomass", "biofuel",
                   efficiency=0.45, capex=2000, fom=50, vom=0.5,
                   capacity_factor=0.80, lifetime=30),
        SupplyTech("biodiesel", "biomass", "biofuel",
                   efficiency=0.50, capex=1800, fom=40, vom=0.4,
                   capacity_factor=0.80, lifetime=30),
    ]


class BiofuelsSector(TransformationSector):
    """Biomass → biofuel conversion.  Two techs, preference logit."""

    carrier_output: str = "biofuel"

    def __init__(
        self,
        techs: list[SupplyTech] | None = None,
        scale_k: float = PREF_LOGIT_SCALE,
    ) -> None:
        self.techs = techs or default_biofuel_techs()
        self.scale_k = scale_k
        self.pref_factors: np.ndarray | None = None
        self.last_shares: np.ndarray | None = None

    def calibrate(
        self,
        base_shares: dict[str, float],
        base_prices: dict[str, float],
    ) -> None:
        shares_arr = np.array([
            base_shares.get(t.name, 0.5) for t in self.techs
        ])
        shares_arr = np.maximum(shares_arr, 1e-6)
        shares_arr /= shares_arr.sum()

        costs = np.array([
            t.lcoe(base_prices) for t in self.techs
        ])
        self.pref_factors = preference_calibrate(shares_arr, costs, self.scale_k)
        self.last_shares = shares_arr.copy()

    def compute_supply(
        self, rs: RegionState, demand_ej: float, policy: Any = None,
    ) -> dict[str, float]:
        costs = np.array([t.lcoe(rs.raw_fuel_prices) for t in self.techs])
        pf = self.pref_factors if self.pref_factors is not None else np.zeros(len(self.techs))
        shares = preference_logit(costs, pf, self.scale_k)
        self.last_shares = shares
        return {t.name: float(s * demand_ej) for t, s in zip(self.techs, shares)}

    def compute_price(self, rs: RegionState) -> float:
        if self.last_shares is None:
            return 10.0
        costs = np.array([t.lcoe(rs.raw_fuel_prices) for t in self.techs])
        return float(np.dot(self.last_shares, costs))

    def compute_emissions(self, generation: dict[str, float]) -> EmissionResult:
        # Biofuel production: biogenic carbon, net zero without CCS
        return EmissionResult()

    def fuel_consumption(self, generation: dict[str, float]) -> dict[str, float]:
        tech_map = {t.name: t for t in self.techs}
        consumption: dict[str, float] = {}
        for name, gen_ej in generation.items():
            tech = tech_map.get(name)
            if tech is None or gen_ej <= 0:
                continue
            fuel_ej = gen_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            consumption[tech.fuel_input] = consumption.get(tech.fuel_input, 0.0) + fuel_ej
        return consumption
