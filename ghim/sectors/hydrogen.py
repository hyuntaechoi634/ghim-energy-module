"""HydrogenSector — LCOH logit with vintage stock turnover.

Phase 1: 2 techs (SMR, electrolysis).  Mirrors electricity pattern.
Phase 2+: expand to 7 techs (SMR+CCS, coal gasif, biomass gasif, etc.)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import TC_TO_TCO2
from ghim.core.config import BASE_YEAR
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import SupplyTech
from ghim.core.vintage import VintageTracker
from ghim.energy.logit import relative_pref_logit, preference_calibrate
from ghim.config import (
    HYDROGEN_LOGIT_EXP,
    PREF_LOGIT_SCALE,
    PREF_DECAY_RATES,
    TECH_RETIREMENT_LIFETIMES,
)
from ghim.sectors.abc import TransformationSector


def default_hydrogen_supply_techs() -> list[SupplyTech]:
    """Default hydrogen production technologies.

    Sources (all values converted to $2020):
    - SMR: H2A 2018, Central Natural Gas. FeedstockIO=156249 BTU/kg → eff=0.73 (LHV).
      NEcost=$0.32/kg (2016$) consistent with capex=600, fom=15, vom=0.2 at CF=0.90.
    - Electrolysis: H2A 2018 PEM. NEcost=$1.18/kg (2016$), improving 56% to 2040.
      System eff ~67% (LHV, 2020 PEM). Capex $1400/kW (IRENA 2020 range: $1100-1800).
    """
    return [
        SupplyTech("smr", "gas", "h2",
                   efficiency=0.73, capex=600, fom=15, vom=0.2,
                   capacity_factor=0.90, lifetime=30,
                   carbon_coef=0.0153,
                   base_cumulative=100.0, learning_rate=0.0),
        SupplyTech("electrolysis", "electricity", "h2",
                   efficiency=0.67, capex=1400, fom=30, vom=0.1,
                   capacity_factor=0.50, lifetime=25,
                   base_cumulative=1.0, learning_rate=0.15),
    ]


_H2_LIFETIMES: dict[str, float] = {
    "smr": 30.0, "electrolysis": 25.0,
}

_H2_HARD_CUTOFF: set[str] = {"electrolysis"}


class OOPHydrogenSector(TransformationSector):
    """Hydrogen production sector.  One instance per region."""

    carrier_output: str = "h2"

    def __init__(
        self,
        techs: list[SupplyTech] | None = None,
        logit_exp: float = HYDROGEN_LOGIT_EXP,
        scale_k: float = PREF_LOGIT_SCALE,
    ) -> None:
        self.techs = techs or default_hydrogen_supply_techs()
        self.logit_exp = logit_exp
        self.scale_k = scale_k

        self.pref_factors: np.ndarray | None = None
        self.base_pref_factors: np.ndarray | None = None
        self.last_shares: np.ndarray | None = None
        self.total_production_ej: float = 0.0
        self.vintage: VintageTracker | None = None

    @property
    def tech_names(self) -> list[str]:
        return [t.name for t in self.techs]

    def calibrate(
        self,
        base_shares: dict[str, float],
        base_prices: dict[str, float],
        total_production_ej: float = 0.0,
    ) -> None:
        self.total_production_ej = total_production_ej

        shares_arr = np.array([
            base_shares.get(t.name, 1e-4) for t in self.techs
        ])
        shares_arr = np.maximum(shares_arr, 1e-6)
        shares_arr /= shares_arr.sum()

        costs_arr = np.array([
            t.lcoe(base_prices, carbon_price=0.0) for t in self.techs
        ])

        self.pref_factors = preference_calibrate(
            shares_arr, costs_arr, self.scale_k, logit_exp=self.logit_exp,
        )
        self.base_pref_factors = self.pref_factors.copy()
        self.last_shares = shares_arr.copy()

        names = self.tech_names
        lifetimes = {n: _H2_LIFETIMES.get(n, 25.0) for n in names}
        self.vintage = VintageTracker(
            tech_names=names,
            lifetimes=lifetimes,
            hard_cutoff_techs=_H2_HARD_CUTOFF & set(names),
        )
        self.vintage.initialize_uniform(
            shares_arr, total_production_ej, BASE_YEAR,
        )

    def compute_supply(
        self,
        rs: RegionState,
        demand_ej: float,
        policy: Any = None,
    ) -> dict[str, float]:
        carbon_price = getattr(rs, "carbon_price", 0.0)
        year = getattr(rs, "_year", None) or BASE_YEAR

        # Renewable subsidies from policy
        subsidies = np.zeros(len(self.techs))
        if policy is not None and hasattr(policy, "renewable_subsidies"):
            for i, t in enumerate(self.techs):
                subsidies[i] = policy.renewable_subsidies.get_subsidy(t.name, year)

        lcoh = np.array([
            t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price)
            for t in self.techs
        ]) - subsidies
        lcoh = np.maximum(lcoh, 0.01)

        pf = self._compute_pref_factors(year)
        target_shares = relative_pref_logit(
            lcoh, pf, self.scale_k, self.logit_exp,
        )

        if self.vintage is not None:
            effective_shares = self.vintage.retire_and_invest(
                year, target_shares, demand_ej,
            )
        else:
            effective_shares = target_shares

        self.last_shares = effective_shares
        self.total_production_ej = demand_ej

        return {
            t.name: float(s * demand_ej)
            for t, s in zip(self.techs, effective_shares)
        }

    def compute_price(self, rs: RegionState) -> float:
        if self.last_shares is None:
            return 15.0
        carbon_price = getattr(rs, "carbon_price", 0.0)
        lcoh = np.array([
            t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price)
            for t in self.techs
        ])
        return float(np.dot(self.last_shares, lcoh))

    def compute_emissions(
        self, generation: dict[str, float],
    ) -> EmissionResult:
        tech_map = {t.name: t for t in self.techs}
        total_mtc = 0.0
        for name, gen_ej in generation.items():
            tech = tech_map.get(name)
            if tech is None or gen_ej <= 0:
                continue
            fuel_ej = gen_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            total_mtc += tech.annual_emissions_mtc(fuel_ej)
        return EmissionResult(co2=total_mtc * TC_TO_TCO2)

    def fuel_consumption(
        self, generation: dict[str, float],
    ) -> dict[str, float]:
        tech_map = {t.name: t for t in self.techs}
        consumption: dict[str, float] = {}
        for name, gen_ej in generation.items():
            tech = tech_map.get(name)
            if tech is None or gen_ej <= 0:
                continue
            fuel_ej = gen_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            consumption[tech.fuel_input] = (
                consumption.get(tech.fuel_input, 0.0) + fuel_ej
            )
        return consumption

    def _compute_pref_factors(self, year: int) -> np.ndarray:
        if self.base_pref_factors is None:
            return np.zeros(len(self.techs))
        elapsed = max(year - BASE_YEAR, 0)
        return np.array([
            self.base_pref_factors[i] * (1.0 - PREF_DECAY_RATES.get(t.name, 0.0)) ** elapsed
            for i, t in enumerate(self.techs)
        ])
