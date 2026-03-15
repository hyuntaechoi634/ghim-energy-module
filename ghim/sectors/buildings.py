"""BuildingsSector — Res/Com × Heating/Cooling/Other with independent subsector demands.

Each subsector (residential.heating, commercial.cooling, etc.) has its own
demand envelope driven by floorspace satiation, subsector-specific income
elasticity, and HDD/CDD for thermal services.  Total buildings demand is the
SUM of all subsector demands (bottom-up), not a top-down split.

Carrier competition occurs independently within each subsector via logit.

Data source: gcamdata A44.* parameter files.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import EndUseTech
from ghim.sectors.abc import DemandSector, Subsector, _interpolate_curve


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


# Per-subsector income elasticity defaults.
# "Other" (appliances, electronics) grows faster with income.
# Cooling grows fast in developing countries (AC penetration).
# Heating grows slowly (building shell improvement offsets income growth).
# Source: GCAM A44 satiation_mult + stylized income-dependence.
_DEFAULT_SUB_INCOME_ELAS: dict[str, float] = {
    "residential.heating": 0.40,
    "residential.cooling": 0.90,
    "residential.other": 0.70,
    "commercial.heating": 0.35,
    "commercial.cooling": 0.80,
    "commercial.other": 0.85,
}

# GCAM A44 service satiation multiplier (SSP2):
# "Others" services grow 1.3× base rate (appliance proliferation).
_DEFAULT_SATIATION_MULT: dict[str, float] = {
    "residential.other": 1.3,
    "commercial.other": 1.3,
}


class BuildingsSector(DemandSector):
    """Residential + Commercial buildings with independent subsector demands.

    6 subsectors: Res/Com × Heating/Cooling/Other.
    Each subsector computes its own demand envelope; total = SUM.

    Floorspace satiation model:
      F(y) = F̄ − (F̄ − F_min) × exp(−y / ŷ)
      drives the overall building energy intensity calibration.
    """

    income_elasticity: float = 0.5
    price_elasticity: float = -0.3

    # Income elasticity curve from gcamdata A42.inc_elas.csv.
    # Used as sector-level fallback; subsectors use their own elasticities.
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
    energy_intensity: float = 0.40    # GJ/m²/yr (calibrated at base year)

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

        # Per-subsector income elasticity and base price
        self._sub_income_elas: dict[str, float] = dict(_DEFAULT_SUB_INCOME_ELAS)
        self._sub_base_prices: dict[str, float] = {}

        # Legacy: still used by _apply_calibration for fraction update
        self._sub_fractions: dict[str, float] = {}

    def floorspace_per_capita(self, gdp_per_cap_k: float) -> float:
        """Floorspace per capita (m²/cap) from income satiation curve.

        F(y) = F̄ − (F̄ − F_min) × exp(−y / ŷ)
        """
        return self.floorspace_max - (
            (self.floorspace_max - self.floorspace_min)
            * np.exp(-gdp_per_cap_k / self.income_midpoint)
        )

    def demand_envelope(self, rs: RegionState) -> float:
        """Total sector energy demand (EJ).

        Sum of all subsector demands.  Used by sector_price_index
        and other aggregation methods.
        """
        return sum(
            self._subsector_demand(sub, rs)
            for sub in self.subsectors
        )

    def _subsector_demand(self, sub: Subsector, rs: RegionState) -> float:
        """Independent demand envelope for a single subsector.

        E_sub = base_demand_sub × (GDP/GDP₀)^α_sub × (P_sub/P₀_sub)^γ × climate
        """
        if sub.base_demand <= 0 or self.base_gdp <= 0:
            return 0.0

        gdp_ratio = rs.gdp / self.base_gdp
        alpha = self._sub_income_elas.get(
            sub.name, self.income_elasticity,
        )

        # Subsector price index
        sub_price = sub.price_index(rs.carrier_prices)
        sub_base_price = self._sub_base_prices.get(sub.name, self.base_price)
        price_ratio = max(sub_price / sub_base_price, 0.01) if sub_base_price > 0 else 1.0

        demand = sub.base_demand * (
            gdp_ratio ** alpha
            * price_ratio ** self.price_elasticity
        )

        # Climate scaling
        if "heating" in sub.name:
            hdd_ratio = rs.hdd / self._hdd_base if self._hdd_base > 0 else 1.0
            demand *= max(hdd_ratio, 0.0)
        elif "cooling" in sub.name:
            cdd_ratio = rs.cdd / self._cdd_base if self._cdd_base > 0 else 1.0
            demand *= max(cdd_ratio, 0.0)

        return max(demand, 0.0)

    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        year = getattr(rs, "_year", None) or 2021

        result: dict[str, float] = {}
        for sub in self.subsectors:
            sub_total = self._subsector_demand(sub, rs)

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
            frac = self._sub_fractions.get(sub.name, 1.0 / len(self.subsectors))
            sub.base_demand = self.base_demand * frac
            if sub.base_demand > 0:
                shares = np.array([
                    base_demands.get(t.carrier, 0.0) / sub.base_demand
                    for t in sub.techs
                ])
                shares = np.maximum(shares, 1e-6)
                shares /= shares.sum()
                sub.calibrate(shares, base_prices)

        # Set per-subsector base prices
        rs_cal = RegionState(carrier_prices=base_prices)
        for sub in self.subsectors:
            self._sub_base_prices[sub.name] = sub.price_index(rs_cal.carrier_prices)

        self.base_price = self.sector_price_index(rs_cal)

    def calibrate_subsector_demands(
        self,
        subsector_totals: dict[str, float],
        rs: RegionState | None = None,
    ) -> None:
        """Update subsector base_demands so demand_envelope reproduces targets.

        Back-calculates base_demand for each subsector such that
        ``_subsector_demand(sub, rs) ≈ target`` at current GDP/prices/climate.

        Parameters
        ----------
        subsector_totals : dict mapping subsector name → FE target in EJ
        rs : current RegionState (needed for GDP, prices, HDD/CDD)
        """
        for sub in self.subsectors:
            target = subsector_totals.get(sub.name)
            if target is None or target <= 0:
                continue

            if rs is None or self.base_gdp <= 0:
                sub.base_demand = target
                continue

            # Back-calculate: target = base × (GDP/GDP₀)^α × (P/P₀)^γ × climate
            gdp_ratio = rs.gdp / self.base_gdp
            alpha = self._sub_income_elas.get(sub.name, self.income_elasticity)
            income_factor = gdp_ratio ** alpha if gdp_ratio > 0 else 1.0

            sub_price = sub.price_index(rs.carrier_prices)
            sub_bp = self._sub_base_prices.get(sub.name, self.base_price)
            price_ratio = max(sub_price / sub_bp, 0.01) if sub_bp > 0 else 1.0
            price_factor = price_ratio ** self.price_elasticity

            climate_factor = 1.0
            if "heating" in sub.name:
                climate_factor = rs.hdd / self._hdd_base if self._hdd_base > 0 else 1.0
            elif "cooling" in sub.name:
                climate_factor = rs.cdd / self._cdd_base if self._cdd_base > 0 else 1.0
            climate_factor = max(climate_factor, 0.01)

            denom = income_factor * price_factor * climate_factor
            sub.base_demand = target / denom if denom > 0 else target

        # Update _sub_fractions for backward compat
        total = sum(sub.base_demand for sub in self.subsectors)
        if total > 0:
            self._sub_fractions = {
                sub.name: sub.base_demand / total
                for sub in self.subsectors
            }
        self.base_demand = total
