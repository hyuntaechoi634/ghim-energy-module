"""BunkersSector — International aviation + shipping.

Global (not per-region).  Uses world GDP as demand driver.
Powertrain-based logit on LCOT.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import Powertrain
from ghim.sectors.abc import DemandSector, Subsector
from ghim.sectors.transport import _TransportSubsector


DEFAULT_AVI_FRACTION = 0.55
DEFAULT_SHIP_FRACTION = 0.45


class BunkersSector(DemandSector):
    """International aviation + shipping bunkers.

    Sits on GHIMModel (not inside Region).  Uses world GDP as demand driver.
    """

    income_elasticity: float = 0.9
    price_elasticity: float = -0.2

    def __init__(
        self,
        avi_fraction: float = DEFAULT_AVI_FRACTION,
    ) -> None:
        self.avi_fraction = avi_fraction
        self.ship_fraction = 1.0 - avi_fraction
        self.subsectors = [
            _TransportSubsector("bunkers.aviation", [
                Powertrain(carrier="liquids", name="jet",
                           efficiency=0.15, capex_vehicle=0, lifetime=25,
                           energy_intensity=0.015, fom=0, annual_service=1),
                Powertrain(carrier="biofuel", name="saf",
                           efficiency=0.15, capex_vehicle=0, lifetime=25,
                           energy_intensity=0.015, fom=0, annual_service=1),
            ]),
            _TransportSubsector("bunkers.shipping", [
                Powertrain(carrier="liquids", name="marine",
                           efficiency=0.10, capex_vehicle=0, lifetime=30,
                           energy_intensity=0.020, fom=0, annual_service=1),
                Powertrain(carrier="gas", name="lng",
                           efficiency=0.12, capex_vehicle=0, lifetime=30,
                           energy_intensity=0.018, fom=0, annual_service=1),
            ]),
        ]
        self.base_demand = 0.0
        self.base_gdp = 0.0
        self.base_price = 5.0

    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        total = self.demand_envelope(rs)
        year = getattr(rs, "_year", None) or 2021

        result: dict[str, float] = {}
        for sub in self.subsectors:
            frac = (self.avi_fraction if "aviation" in sub.name
                    else self.ship_fraction)
            shares = sub.compute_shares(rs.carrier_prices, year=year, policy=policy)
            carrier_d = sub.carrier_demands(shares, total * frac)
            for c, v in carrier_d.items():
                result[c] = result.get(c, 0.0) + v
        return result

    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        co2 = 0.0
        demands = rs.sector_demand.get("bunkers", {})
        for carrier, ej in demands.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            co2 += cc * TC_TO_TCO2 * ej * 1e3
        return EmissionResult(co2=co2)

    def calibrate(
        self,
        base_demands: dict[str, float],
        base_prices: dict[str, float],
        base_gdp: float,
    ) -> None:
        self.base_gdp = base_gdp
        self.base_demand = sum(base_demands.values())

        for sub in self.subsectors:
            frac = (self.avi_fraction if "aviation" in sub.name
                    else self.ship_fraction)
            sub.base_demand = self.base_demand * frac
            if sub.base_demand > 0:
                shares = np.array([
                    base_demands.get(t.carrier, 0.0) / sub.base_demand
                    for t in sub.techs
                ])
                shares = np.maximum(shares, 1e-6)
                shares /= shares.sum()
                sub.calibrate(shares, base_prices)

        self.base_price = self.sector_price_index(
            RegionState(carrier_prices=base_prices),
        )
