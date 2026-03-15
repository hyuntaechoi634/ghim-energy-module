"""RefinedOilSector — oil → refined liquids (single tech, pass-through).

Simplest transformation sector.  Refining is conversion, not combustion:
  - SupplyTech("refinery").carbon_coef = 0.0 (no CO2 at refinery)
  - CARBON_COEFS[LIQUIDS] = 0.0200 (CO2 at demand side when burned)
  - Carbon tax on liquids enters via carrier_price adder, not refinery LCOE.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import SupplyTech
from ghim.sectors.abc import TransformationSector


class RefinedOilSector(TransformationSector):
    """Oil → refined liquids.  Single tech pass-through."""

    carrier_output: str = "liquids"

    def __init__(
        self,
        efficiency: float = 0.90,
        capex: float = 500.0,
        fom: float = 15.0,
        vom: float = 0.2,
        lifetime: int = 40,
    ) -> None:
        self.techs = [
            SupplyTech(
                name="refinery",
                fuel_input="oil",
                carrier_output="liquids",
                efficiency=efficiency,
                capex=capex,
                fom=fom,
                vom=vom,
                capacity_factor=0.85,
                lifetime=lifetime,
                carbon_coef=0.0,  # conversion, not combustion
            ),
        ]
        self._last_shares: dict[str, float] = {"refinery": 1.0}

    def compute_supply(
        self,
        rs: RegionState,
        demand_ej: float,
        policy: Any = None,
    ) -> dict[str, float]:
        """Pass-through: all demand met by single refinery tech."""
        return {"refinery": max(demand_ej, 0.0)}

    def compute_price(self, rs: RegionState) -> float:
        """Refinery price = oil_price / efficiency + VOM.

        No carbon cost here — carbon tax on liquids is applied at
        demand side (Step 6a in solver).
        """
        oil_price = rs.raw_fuel_prices.get("oil", 8.0)
        tech = self.techs[0]
        return oil_price / tech.efficiency + tech.vom

    def fuel_input_ej(self, output_ej: float) -> float:
        """Crude oil input required for given refined output."""
        return output_ej / self.techs[0].efficiency

    def compute_emissions(
        self, generation: dict[str, float],
    ) -> EmissionResult:
        """Refinery has zero direct CO2 (conversion, not combustion)."""
        return EmissionResult()

    def calibrate(
        self,
        base_shares: dict[str, float],
        base_prices: dict[str, float],
    ) -> None:
        """No calibration needed for single-tech pass-through."""
        pass
