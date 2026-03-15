"""BuildingsSector — Res/Com × Heating/Cooling/Other × 8 carriers.

Most complex demand sector.  Phase 1: demand_envelope with HDD/CDD scaling
for heating/cooling subsectors.  Full floorspace satiation model deferred
to Phase 2.

8 carriers including district Heat.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import EndUseTech
from ghim.sectors.abc import DemandSector, Subsector


def _heating_techs() -> list[EndUseTech]:
    """Building heating techs.

    Efficiencies set to 1.0 for all techs so that the logit preference
    factors fully absorb cost/efficiency differences.  The calibration
    pipeline (inverse logit on GCAM carrier shares) then reproduces
    target shares exactly.  Physical COP/efficiency is encoded in
    the preference factors rather than the cost function.
    """
    return [
        EndUseTech(carrier="gas", efficiency=1.0, lifetime=20),
        EndUseTech(carrier="electricity", efficiency=1.0, lifetime=20,
                   name="heat_pump"),
        EndUseTech(carrier="coal", efficiency=1.0, lifetime=15),
        EndUseTech(carrier="liquids", efficiency=1.0, lifetime=15),
        EndUseTech(carrier="biomass", efficiency=1.0, lifetime=15),
        EndUseTech(carrier="biofuel", efficiency=1.0, lifetime=15),
        EndUseTech(carrier="h2", efficiency=1.0, lifetime=20),
        EndUseTech(carrier="heat", efficiency=1.0, lifetime=20,
                   name="district_heat"),
    ]


def _cooling_techs() -> list[EndUseTech]:
    """Building cooling techs."""
    return [
        EndUseTech(carrier="electricity", efficiency=1.0, lifetime=15,
                   name="ac"),
    ]


def _other_techs() -> list[EndUseTech]:
    """Appliances, lighting, water heating, cooking."""
    return [
        EndUseTech(carrier="electricity", efficiency=1.0, lifetime=10),
        EndUseTech(carrier="gas", efficiency=1.0, lifetime=10),
        EndUseTech(carrier="coal", efficiency=1.0, lifetime=10),
        EndUseTech(carrier="liquids", efficiency=1.0, lifetime=10),
        EndUseTech(carrier="biomass", efficiency=1.0, lifetime=10),
        EndUseTech(carrier="heat", efficiency=1.0, lifetime=10,
                   name="district_heat"),
    ]


# Default subsector fractions of total buildings demand
_DEFAULT_FRACTIONS = {
    "residential.heating": 0.25,
    "residential.cooling": 0.05,
    "residential.other": 0.20,
    "commercial.heating": 0.20,
    "commercial.cooling": 0.10,
    "commercial.other": 0.20,
}


class BuildingsSector(DemandSector):
    """Residential + Commercial buildings with floorspace satiation.

    6 subsectors: Res/Com × Heating/Cooling/Other.
    Heating and cooling respond to HDD/CDD from external climate module.

    Floorspace satiation model (Phase 1):
      F(y) = F̄ − (F̄ − F_min) × exp(−y / ŷ)
      where y = GDP per capita ($k), F̄ = max floorspace per capita (m²/cap),
      ŷ = income at satiation midpoint, F_min = minimum floorspace.

    Total demand = F(y) × pop × d̄_svc × (P/P_base)^γ
    """

    income_elasticity: float = 0.5
    price_elasticity: float = -0.3

    # Income elasticity curve from gcamdata A42.inc_elas.csv.
    # Converted from 1990$k/cap to 2020$k/cap (×1.80 GDP deflator).
    _income_elas_curve: list[tuple[float, float]] = [
        (0.0, 1.25),
        (4.5, 1.0),      # 2.5 × 1.80
        (9.0, 0.85),     # 5 × 1.80
        (18.0, 0.70),    # 10 × 1.80
        (27.0, 0.60),    # 15 × 1.80
        (36.0, 0.50),    # 20 × 1.80
        (45.0, 0.40),    # 25 × 1.80
        (54.0, 0.33),    # 30 × 1.80
        (63.0, 0.27),    # 35 × 1.80
        (72.0, 0.20),    # 40 × 1.80
        (81.0, 0.15),    # 45 × 1.80
        (90.0, 0.10),    # 50 × 1.80
        (99.0, 0.05),    # 55 × 1.80
        (108.0, 0.0),    # 60 × 1.80
    ]

    # Satiation parameters (common IAM defaults)
    floorspace_max: float = 75.0      # m²/cap (satiation)
    floorspace_min: float = 15.0      # m²/cap (minimum)
    income_midpoint: float = 40.0     # $k/cap PPP (midpoint of S-curve)
    energy_intensity: float = 0.40    # GJ/m²/yr (energy service density)

    def __init__(
        self,
        use_floorspace: bool = True,
    ) -> None:
        self.use_floorspace = use_floorspace
        self.subsectors = [
            Subsector("residential.heating", _heating_techs()),
            Subsector("residential.cooling", _cooling_techs()),
            Subsector("residential.other", _other_techs()),
            Subsector("commercial.heating", _heating_techs()),
            Subsector("commercial.cooling", _cooling_techs()),
            Subsector("commercial.other", _other_techs()),
        ]
        self.base_demand = 0.0
        self.base_gdp = 0.0
        self.base_price = 5.0
        self.base_population = 0.0
        self._hdd_base: float = 1.0
        self._cdd_base: float = 1.0
        self._sub_fractions: dict[str, float] = dict(_DEFAULT_FRACTIONS)

    def floorspace_per_capita(self, gdp_per_cap_k: float) -> float:
        """Floorspace per capita (m²/cap) from income satiation curve.

        F(y) = F̄ − (F̄ − F_min) × exp(−y / ŷ)
        """
        return self.floorspace_max - (
            (self.floorspace_max - self.floorspace_min)
            * np.exp(-gdp_per_cap_k / self.income_midpoint)
        )

    def demand_envelope(self, rs: RegionState) -> float:
        """Total sector energy demand (EJ) with floorspace satiation.

        When use_floorspace=True:
          E = F(y) × pop × d̄_svc × (P/P_base)^γ / EJ_conversion
        Otherwise: standard demand_envelope from ABC.
        """
        if not self.use_floorspace or self.base_gdp <= 0 or rs.population <= 0:
            return super().demand_envelope(rs)

        gdp_per_cap_k = rs.gdp / rs.population  # billion USD / million = $k/cap
        floorspace_pc = self.floorspace_per_capita(gdp_per_cap_k)
        total_floorspace = floorspace_pc * rs.population  # million m²

        # Energy = floorspace × energy_intensity (GJ/m²/yr) × (1e6 m² / 1e9 GJ/EJ)
        # = floorspace_M_m2 × intensity × 1e-3 EJ
        energy_ej = total_floorspace * self.energy_intensity * 1e-3

        # Price response
        price_ratio = max(
            self.sector_price_index(rs) / self.base_price, 0.01,
        )
        energy_ej *= price_ratio ** self.price_elasticity

        return max(energy_ej, 0.0)

    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        total = self.demand_envelope(rs)
        year = getattr(rs, "_year", None) or 2021

        # Climate scaling for heating/cooling
        hdd_ratio = rs.hdd / self._hdd_base if self._hdd_base > 0 else 1.0
        cdd_ratio = rs.cdd / self._cdd_base if self._cdd_base > 0 else 1.0

        result: dict[str, float] = {}
        for sub in self.subsectors:
            frac = self._sub_fractions.get(sub.name, 0.1)
            sub_total = frac * total

            # Apply climate scaling
            if "heating" in sub.name:
                sub_total *= max(hdd_ratio, 0.0)
            elif "cooling" in sub.name:
                sub_total *= max(cdd_ratio, 0.0)

            shares = sub.compute_shares(
                rs.carrier_prices, year=year, policy=policy,
            )
            carrier_d = sub.carrier_demands(shares, sub_total)
            for c, v in carrier_d.items():
                result[c] = result.get(c, 0.0) + v
        return result

    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        co2 = 0.0
        demands = rs.sector_demand.get("buildings", {})
        for carrier, ej in demands.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            co2 += cc * TC_TO_TCO2 * ej * 1e3
        return EmissionResult(co2=co2)

    def calibrate(
        self,
        base_demands: dict[str, float],
        base_prices: dict[str, float],
        base_gdp: float,
        hdd_base: float = 1.0,
        cdd_base: float = 1.0,
        base_population: float = 0.0,
    ) -> None:
        self.base_gdp = base_gdp
        self.base_population = base_population
        self.base_demand = sum(base_demands.values())

        # Back-calibrate energy_intensity so floorspace model matches base demand
        if self.use_floorspace and base_population > 0 and base_gdp > 0:
            gdp_per_cap_k = base_gdp / base_population
            floorspace_pc = self.floorspace_per_capita(gdp_per_cap_k)
            total_floorspace = floorspace_pc * base_population  # million m²
            if total_floorspace > 0:
                # base_demand (EJ) = floorspace (M m²) × intensity × 1e-3
                self.energy_intensity = self.base_demand / (total_floorspace * 1e-3)
        self._hdd_base = max(hdd_base, 1e-6)
        self._cdd_base = max(cdd_base, 1e-6)

        for sub in self.subsectors:
            frac = self._sub_fractions.get(sub.name, 0.1)
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
