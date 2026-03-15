"""AgricultureSector — GDP-scaled demand with non-energy GHG emissions.

Simplest demand sector.  Single subsector, 7 carriers.
Production index drives both energy demand and non-energy emissions (CH4, N2O).

Phase 1: eff=1.0 for all techs → levelized_cost = carrier_price.
Phase 2+: real efficiencies for electrification analysis.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import CARBON_COEFS, GWP100, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import EndUseTech
from ghim.sectors.abc import DemandSector, Subsector


class AgricultureSector(DemandSector):
    """Production-index-driven agriculture energy demand.

    Parameters
    ----------
    base_ch4 : float
        Base-year CH4 emissions (MtCH4).
    base_n2o : float
        Base-year N2O emissions (MtN2O).
    """

    income_elasticity: float = 0.3   # Engel's law
    price_elasticity: float = -0.2

    # Non-energy GHG defaults (EDGAR v8.0, global average per-region)
    DEFAULT_BASE_CH4: float = 2.0   # MtCH4
    DEFAULT_BASE_N2O: float = 0.3   # MtN2O

    def __init__(
        self,
        base_ch4: float | None = None,
        base_n2o: float | None = None,
    ) -> None:
        self.base_ch4 = base_ch4 if base_ch4 is not None else self.DEFAULT_BASE_CH4
        self.base_n2o = base_n2o if base_n2o is not None else self.DEFAULT_BASE_N2O
        self.subsectors = [
            Subsector("agriculture", [
                EndUseTech(carrier="electricity", lifetime=20),
                EndUseTech(carrier="liquids", lifetime=15),
                EndUseTech(carrier="gas", lifetime=20),
                EndUseTech(carrier="coal", lifetime=20),
                EndUseTech(carrier="biomass", lifetime=15),
                EndUseTech(carrier="biofuel", lifetime=15),
                EndUseTech(carrier="h2", lifetime=15),
            ]),
        ]
        self.base_demand = 0.0
        self.base_gdp = 0.0
        self.base_price = 5.0

    def sector_price_index(self, rs: RegionState) -> float:
        """Energy sector price plus GHG cost adder from non-CO₂ pricing.

        When agriculture GHG is priced (cover_agriculture_ghg=True), the
        model computes a $/GJ surcharge on rs.ag_ghg_cost_per_gj.
        This enters the demand_envelope via price_elasticity (γ=-0.2).
        """
        base_pi = super().sector_price_index(rs)
        ghg_adder = getattr(rs, "ag_ghg_cost_per_gj", 0.0)
        return base_pi + ghg_adder

    def production_index(self, rs: RegionState) -> float:
        """Agricultural production index (dimensionless, base=1.0).

        Same driver for energy demand, CH4, and N2O emissions.
        Phase 2+: overridden by AFOLU crop/livestock output.
        """
        if self.base_demand <= 0:
            return 1.0
        return self.demand_envelope(rs) / self.base_demand

    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        total = self.demand_envelope(rs)
        year = getattr(rs, "_year", None)
        shares = self.subsectors[0].compute_shares(
            rs.carrier_prices, year=year or 2021, policy=policy,
        )
        return self.subsectors[0].carrier_demands(shares, total)

    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        """Combustion CO2 + non-energy CH4/N2O scaled by production index."""
        # Combustion emissions from carrier demands
        co2 = 0.0
        demands = rs.sector_demand.get("agriculture", {})
        for carrier, ej in demands.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            co2 += cc * TC_TO_TCO2 * ej * 1e3  # MtCO2

        # Non-energy emissions scaled by production index
        idx = self.production_index(rs)
        ch4 = self.base_ch4 * idx
        n2o = self.base_n2o * idx

        return EmissionResult(co2=co2, ch4=ch4, n2o=n2o)

    def calibrate(
        self,
        base_demands: dict[str, float],
        base_prices: dict[str, float],
        base_gdp: float,
    ) -> None:
        """Calibrate from base-year carrier demands, prices, GDP."""
        self.base_gdp = base_gdp
        self.base_demand = sum(base_demands.values())
        self.subsectors[0].base_demand = self.base_demand

        if self.base_demand > 0:
            # Compute base shares from demands
            base_shares = np.array([
                base_demands.get(t.carrier, 0.0) / self.base_demand
                for t in self.subsectors[0].techs
            ])
            # Ensure shares sum to 1
            total = base_shares.sum()
            if total > 0:
                base_shares /= total
            else:
                base_shares = np.ones(len(self.subsectors[0].techs))
                base_shares /= base_shares.sum()

            self.subsectors[0].calibrate(base_shares, base_prices)
            self.base_price = self.subsectors[0].price_index(base_prices)
