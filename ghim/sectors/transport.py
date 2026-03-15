"""TransportSector — Passenger (6 powertrains) + Freight (5 powertrains).

Uses Powertrain.lcot() for logit competition.  VintageTracker per subsector
(S-curve for ICE/HEV/NG/FCEV, hard cutoff for BEV).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import Powertrain
from ghim.sectors.abc import DemandSector, Subsector


# Default passenger/freight split (calibrated per region)
DEFAULT_PASS_FRACTION = 0.60
DEFAULT_FREIGHT_FRACTION = 0.40


def _default_passenger_techs() -> list[Powertrain]:
    return [
        Powertrain(carrier="liquids", name="ICE",
                   efficiency=0.30, capex_vehicle=25000, lifetime=15,
                   energy_intensity=0.003, fom=800, annual_service=15000),
        Powertrain(carrier="biofuel", name="BiofuelICE",
                   efficiency=0.30, capex_vehicle=26000, lifetime=15,
                   energy_intensity=0.003, fom=800, annual_service=15000),
        Powertrain(carrier="liquids", name="HEV",
                   efficiency=0.45, capex_vehicle=30000, lifetime=15,
                   energy_intensity=0.0025, fom=700, annual_service=15000),
        Powertrain(carrier="electricity", name="BEV",
                   efficiency=0.85, capex_vehicle=35000, lifetime=15,
                   energy_intensity=0.002, fom=500, annual_service=15000),
        Powertrain(carrier="h2", name="FCEV",
                   efficiency=0.50, capex_vehicle=50000, lifetime=15,
                   energy_intensity=0.0025, fom=600, annual_service=15000),
        Powertrain(carrier="gas", name="NG",
                   efficiency=0.30, capex_vehicle=27000, lifetime=15,
                   energy_intensity=0.003, fom=750, annual_service=15000),
    ]


def _default_freight_techs() -> list[Powertrain]:
    return [
        Powertrain(carrier="liquids", name="Diesel",
                   efficiency=0.35, capex_vehicle=80000, lifetime=12,
                   energy_intensity=0.012, fom=5000, annual_service=60000),
        Powertrain(carrier="biofuel", name="BioDiesel",
                   efficiency=0.35, capex_vehicle=82000, lifetime=12,
                   energy_intensity=0.012, fom=5000, annual_service=60000),
        Powertrain(carrier="electricity", name="ElecTruck",
                   efficiency=0.80, capex_vehicle=120000, lifetime=12,
                   energy_intensity=0.005, fom=4000, annual_service=60000),
        Powertrain(carrier="h2", name="H2Truck",
                   efficiency=0.45, capex_vehicle=100000, lifetime=12,
                   energy_intensity=0.008, fom=4500, annual_service=60000),
        Powertrain(carrier="gas", name="LNGTruck",
                   efficiency=0.32, capex_vehicle=85000, lifetime=12,
                   energy_intensity=0.013, fom=5200, annual_service=60000),
    ]


class _TransportSubsector(Subsector):
    """Subsector that uses lcot() instead of levelized_cost() for Powertrains."""

    def calibrate(
        self,
        base_shares: np.ndarray,
        base_prices: dict[str, float],
    ) -> None:
        """Calibrate using lcot() costs ($/km), not levelized_cost() ($/GJ).

        Must match the cost function used in compute_shares() so preference
        factors are in the same cost space as the logit evaluation.
        """
        from ghim.energy.logit import preference_calibrate

        base_costs = np.array([
            t.lcot(base_prices.get(t.carrier, 5.0))
            if isinstance(t, Powertrain) else
            t.levelized_cost(base_prices.get(t.carrier, 5.0))
            for t in self.techs
        ])
        self.pref_factors = preference_calibrate(
            base_shares, base_costs, self.logit_scale,
        )
        self.last_shares = base_shares.copy()

    def price_index(self, prices: dict[str, float]) -> float:
        """Share-weighted average LCOT ($/km), consistent with compute_shares."""
        if self.last_shares is None:
            return 0.1
        total = 0.0
        for i, tech in enumerate(self.techs):
            cost = (
                tech.lcot(prices.get(tech.carrier, 5.0))
                if isinstance(tech, Powertrain)
                else tech.levelized_cost(prices.get(tech.carrier, 5.0))
            )
            total += self.last_shares[i] * cost
        return total

    def compute_shares(
        self,
        prices: dict[str, float],
        year: int = 2021,
        policy: Any = None,
    ) -> np.ndarray:
        from ghim.energy.logit import preference_logit

        # Use LCOT for powertrains
        costs = np.array([
            t.lcot(prices.get(t.carrier, 5.0))
            if isinstance(t, Powertrain) else
            t.levelized_cost(prices.get(t.carrier, 5.0))
            for t in self.techs
        ])
        pf = self._decayed_pref_factors(year)
        if policy is not None and hasattr(policy, "get_availability"):
            alpha = policy.get_availability([t.name for t in self.techs], year)
            if alpha is not None:
                costs = costs + (1.0 - np.asarray(alpha, dtype=float)) * 1e6
        shares = preference_logit(costs, pf, self.logit_scale)
        self.last_shares = shares
        return shares


class TransportSector(DemandSector):
    """Passenger + Freight transport.

    Powertrain-based LCOT logit with preference decay for new carriers
    (BEV, FCEV, biofuel).
    """

    income_elasticity: float = 0.7
    price_elasticity: float = -0.4

    # Income elasticity curve from gcamdata A52.inc_elas.csv.
    # Converted from 1990$k/cap to 2020$k/cap (×1.80 GDP deflator).
    _income_elas_curve: list[tuple[float, float]] = [
        (0.0, 1.25),
        (4.5, 1.10),     # 2.5 × 1.80
        (9.0, 0.86),     # 5 × 1.80
        (18.0, 0.62),    # 10 × 1.80
        (27.0, 0.50),    # 15 × 1.80
        (36.0, 0.45),    # 20 × 1.80
        (45.0, 0.41),    # 25 × 1.80
        (54.0, 0.35),    # 30 × 1.80
        (63.0, 0.30),    # 35 × 1.80
        (72.0, 0.25),    # 40 × 1.80
        (81.0, 0.18),    # 45 × 1.80
        (90.0, 0.12),    # 50 × 1.80
        (99.0, 0.05),    # 55 × 1.80
        (108.0, 0.0),    # 60 × 1.80
    ]

    def __init__(
        self,
        pass_fraction: float = DEFAULT_PASS_FRACTION,
    ) -> None:
        self.pass_fraction = pass_fraction
        self.freight_fraction = 1.0 - pass_fraction
        self.subsectors = [
            _TransportSubsector("transport.passenger", _default_passenger_techs()),
            _TransportSubsector("transport.freight", _default_freight_techs()),
        ]
        self.base_demand = 0.0
        self.base_gdp = 0.0
        self.base_price = 5.0

    @property
    def passenger(self) -> Subsector:
        return self.subsectors[0]

    @property
    def freight(self) -> Subsector:
        return self.subsectors[1]

    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        total = self.demand_envelope(rs)
        year = getattr(rs, "_year", None) or 2021

        result: dict[str, float] = {}
        for sub in self.subsectors:
            frac = (self.pass_fraction if "passenger" in sub.name
                    else self.freight_fraction)
            shares = sub.compute_shares(rs.carrier_prices, year=year, policy=policy)
            carrier_d = sub.carrier_demands(shares, total * frac)
            for c, v in carrier_d.items():
                result[c] = result.get(c, 0.0) + v
        return result

    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        co2 = 0.0
        demands = rs.sector_demand.get("transport", {})
        for carrier, ej in demands.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            co2 += cc * TC_TO_TCO2 * ej * 1e3
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
        self.passenger.base_demand = self.base_demand * self.pass_fraction
        self.freight.base_demand = self.base_demand * self.freight_fraction

        for sub in self.subsectors:
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
