"""DistrictHeatingSector — 4 techs: gas boiler, electric boiler, heat pump, biomass CHP."""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import TC_TO_TCO2
from ghim.core.config import BASE_YEAR
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import SupplyTech
from ghim.energy.logit import preference_logit, preference_calibrate
from ghim.config import PREF_LOGIT_SCALE
from ghim.sectors.abc import TransformationSector


def default_district_heat_techs() -> list[SupplyTech]:
    return [
        SupplyTech("gas_boiler", "gas", "heat",
                   efficiency=0.90, capex=200, fom=5, vom=0.1,
                   capacity_factor=0.50, lifetime=25,
                   carbon_coef=0.0153),
        SupplyTech("electric_boiler", "electricity", "heat",
                   efficiency=0.99, capex=150, fom=3, vom=0.05,
                   capacity_factor=0.50, lifetime=20),
        SupplyTech("heat_pump", "electricity", "heat",
                   efficiency=3.5, capex=800, fom=15, vom=0.0,
                   capacity_factor=0.40, lifetime=20),
        SupplyTech("biomass_chp", "biomass", "heat",
                   efficiency=0.80, capex=1500, fom=40, vom=0.3,
                   capacity_factor=0.60, lifetime=30,
                   biogenic_coef=0.0257),
    ]


class DistrictHeatingSector(TransformationSector):
    """District heating production sector."""

    carrier_output: str = "heat"

    def __init__(
        self,
        techs: list[SupplyTech] | None = None,
        scale_k: float = PREF_LOGIT_SCALE,
    ) -> None:
        self.techs = techs or default_district_heat_techs()
        self.scale_k = scale_k
        self.pref_factors: np.ndarray | None = None
        self.last_shares: np.ndarray | None = None

    def calibrate(
        self,
        base_shares: dict[str, float],
        base_prices: dict[str, float],
        total_production_ej: float = 0.0,
    ) -> None:
        self.total_production_ej = total_production_ej
        shares_arr = np.array([
            base_shares.get(t.name, 0.25) for t in self.techs
        ])
        shares_arr = np.maximum(shares_arr, 1e-6)
        shares_arr /= shares_arr.sum()
        costs = np.array([t.lcoe(base_prices) for t in self.techs])
        self.pref_factors = preference_calibrate(shares_arr, costs, self.scale_k)
        self.last_shares = shares_arr.copy()

    def compute_supply(
        self, rs: RegionState, demand_ej: float, policy: Any = None,
    ) -> dict[str, float]:
        carbon_price = getattr(rs, "carbon_price", 0.0)

        costs = np.array([
            t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price)
            for t in self.techs
        ])
        pf = self.pref_factors if self.pref_factors is not None else np.zeros(len(self.techs))
        shares = preference_logit(costs, pf, self.scale_k)
        self.last_shares = shares
        return {t.name: float(s * demand_ej) for t, s in zip(self.techs, shares)}

    def compute_price(self, rs: RegionState) -> float:
        if self.last_shares is None:
            return 10.0
        carbon_price = getattr(rs, "carbon_price", 0.0)
        costs = np.array([
            t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price)
            for t in self.techs
        ])
        return float(np.dot(self.last_shares, costs))

    def compute_emissions(self, generation: dict[str, float]) -> EmissionResult:
        tech_map = {t.name: t for t in self.techs}
        total_mtc = 0.0
        for name, gen_ej in generation.items():
            tech = tech_map.get(name)
            if tech is None or gen_ej <= 0:
                continue
            fuel_ej = gen_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            total_mtc += tech.annual_emissions_mtc(fuel_ej)
        return EmissionResult(co2=total_mtc * TC_TO_TCO2)

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
