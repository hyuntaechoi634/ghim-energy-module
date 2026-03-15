"""IndustrySector — Energy Use (8 carriers) + Feedstocks (5 carriers).

Two subsectors:
  EU (energy use): electricity, gas, coal, liquids, biomass, biofuel, h2, heat
  FS (feedstocks):  liquids, gas, biomass, biofuel, h2

EU efficiencies from gcamdata A32.globaltech_eff.csv (2005 base year).
FS efficiencies = 1.0 (feedstocks are embedded, not combusted).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import EndUseTech
from ghim.sectors.abc import DemandSector, Subsector, _interpolate_curve


# Default EU/FS split (global average; calibrated per region)
DEFAULT_EU_FRACTION = 0.75
DEFAULT_FS_FRACTION = 0.25


# Income elasticity curve from gcamdata A32.inc_elas_output.csv (verbatim).
# x-axis: per-capita industrial energy output (GJ/cap/yr), NOT GDP/cap.
# Unlike A42/A52, industry uses energy-per-capita as the satiation driver.
_IND_INCOME_ELAS_CURVE: list[tuple[float, float]] = [
    (0.0, 1.50),
    (3.0, 1.12),
    (5.0, 0.90),
    (7.0, 0.78),
    (10.0, 0.60),
    (14.0, 0.35),
    (18.0, 0.26),
    (26.0, 0.22),
    (38.0, 0.10),
    (42.0, 0.0),
    (46.0, -0.05),
]


class IndustrySector(DemandSector):
    """Industry: Energy Use + Feedstocks.

    Parameters
    ----------
    eu_fraction : float
        Fraction of total demand going to energy use (rest = feedstocks).
    """

    income_elasticity: float = 0.6
    price_elasticity: float = -0.4

    # Disable the GDP-based curve from ABC; we override with energy-based.
    _income_elas_curve: list[tuple[float, float]] | None = None

    def __init__(
        self,
        eu_fraction: float = DEFAULT_EU_FRACTION,
    ) -> None:
        self.eu_fraction = eu_fraction
        self.fs_fraction = 1.0 - eu_fraction
        # EU efficiencies from A32.globaltech_eff.csv (2005 column, non-cogen rows).
        # GCAM also has cogen techs (gas_cogen 0.603, coal_cogen 0.623, etc.)
        # but GHIM does not model cogeneration — uses direct combustion only.
        # FS efficiencies = 1.0 (feedstocks are embedded, not combusted).
        # biofuel eff=0.799: same as biomass (not in GCAM A32, GHIM assumption).
        self.subsectors = [
            Subsector("industry.EU", [
                EndUseTech(carrier="electricity", efficiency=1.0, lifetime=25),
                EndUseTech(carrier="gas", efficiency=0.884, lifetime=30),
                EndUseTech(carrier="coal", efficiency=0.865, lifetime=40),
                EndUseTech(carrier="liquids", efficiency=0.982, lifetime=25),
                EndUseTech(carrier="biomass", efficiency=0.799, lifetime=25),
                EndUseTech(carrier="biofuel", efficiency=0.799, lifetime=25),
                EndUseTech(carrier="h2", efficiency=1.0, lifetime=20),
                EndUseTech(carrier="heat", efficiency=1.0, lifetime=20),
            ]),
            Subsector("industry.FS", [
                EndUseTech(carrier="liquids", lifetime=30),
                EndUseTech(carrier="gas", lifetime=30),
                EndUseTech(carrier="biomass", lifetime=25),
                EndUseTech(carrier="biofuel", lifetime=25),
                EndUseTech(carrier="h2", lifetime=20),
            ]),
        ]
        self.base_demand = 0.0
        self.base_gdp = 0.0
        self.base_price = 5.0
        self._last_demand_ej: float = 0.0  # FE from previous period

    @property
    def eu(self) -> Subsector:
        return self.subsectors[0]

    @property
    def fs(self) -> Subsector:
        return self.subsectors[1]

    def _effective_income_elasticity(self, rs: RegionState) -> float:
        """Industry income elasticity from per-capita energy output.

        A32.inc_elas_output.csv uses GJ/cap/yr as the x-axis (not GDP/cap).
        Uses actual FE demand from previous solver iteration / period,
        not GDP-approximated demand (which overestimates energy/cap for
        fast-growing developing countries and causes premature satiation).
        """
        pop = getattr(rs, "population", 0.0) or self.base_population
        if pop <= 0 or self.base_demand <= 0:
            return self.income_elasticity

        # Use actual demand from previous iteration; fall back to base
        demand_ej = (
            self._last_demand_ej
            if self._last_demand_ej > 0
            else self.base_demand
        )
        # EJ / million people × 1e3 = GJ/cap
        energy_per_cap_gj = demand_ej * 1e3 / pop
        return _interpolate_curve(_IND_INCOME_ELAS_CURVE, energy_per_cap_gj)

    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        total = self.demand_envelope(rs)
        year = getattr(rs, "_year", None) or 2021

        eu_shares = self.eu.compute_shares(
            rs.carrier_prices, year=year, policy=policy,
        )
        fs_shares = self.fs.compute_shares(
            rs.carrier_prices, year=year, policy=policy,
        )

        eu_demand = self.eu.carrier_demands(eu_shares, total * self.eu_fraction)
        fs_demand = self.fs.carrier_demands(fs_shares, total * self.fs_fraction)

        result: dict[str, float] = {}
        for d in (eu_demand, fs_demand):
            for carrier, ej in d.items():
                result[carrier] = result.get(carrier, 0.0) + ej
        return result

    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        """Combustion CO2 from carrier demands."""
        co2 = 0.0
        demands = rs.sector_demand.get("industry", {})
        for carrier, ej in demands.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            co2 += cc * TC_TO_TCO2 * ej * 1e3  # MtCO2
        return EmissionResult(co2=co2)

    def calibrate(
        self,
        base_demands: dict[str, float],
        base_prices: dict[str, float],
        base_gdp: float,
        base_population: float = 0.0,
    ) -> None:
        self.base_gdp = base_gdp
        self.base_population = base_population
        self.base_demand = sum(base_demands.values())

        # Split demands into EU and FS based on fraction
        eu_total = self.base_demand * self.eu_fraction
        fs_total = self.base_demand * self.fs_fraction
        self.eu.base_demand = eu_total
        self.fs.base_demand = fs_total

        if eu_total > 0:
            eu_shares = np.array([
                base_demands.get(t.carrier, 0.0) / eu_total
                for t in self.eu.techs
            ])
            eu_shares = np.maximum(eu_shares, 1e-6)
            eu_shares /= eu_shares.sum()
            self.eu.calibrate(eu_shares, base_prices)

        if fs_total > 0:
            fs_shares = np.array([
                base_demands.get(t.carrier, 0.0) / fs_total
                for t in self.fs.techs
            ])
            fs_shares = np.maximum(fs_shares, 1e-6)
            fs_shares /= fs_shares.sum()
            self.fs.calibrate(fs_shares, base_prices)

        self.base_price = self.sector_price_index(
            RegionState(carrier_prices=base_prices),
        )
