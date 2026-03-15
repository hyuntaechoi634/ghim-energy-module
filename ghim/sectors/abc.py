"""Sector abstract base classes and the Subsector helper.

DemandSector      — final energy demand (industry, buildings, transport, etc.)
TransformationSector — secondary energy production (electricity, hydrogen, etc.)
Subsector         — logit competition among EndUseTechs within a demand sector

Policy parameter is typed as ``Any`` (stub). Phase E wires in PolicyEngine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ghim.core.config import BASE_YEAR
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import EndUseTech, SupplyTech
from ghim.energy.logit import preference_logit, preference_calibrate
from ghim.config import PREF_LOGIT_SCALE


# ===================================================================
# Helper: interpolate a curve (list of (x, y) tuples)
# ===================================================================

def _interpolate_curve(
    curve: list[tuple[float, float]], x: float,
) -> float:
    """Linearly interpolate a piecewise-linear curve."""
    if x <= curve[0][0]:
        return curve[0][1]
    if x >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        x0, y0 = curve[i]
        x1, y1 = curve[i + 1]
        if x0 <= x <= x1:
            alpha = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 + alpha * (y1 - y0)
    return curve[-1][1]


# ===================================================================
# Carrier-level preference decay rates (demand-side, annual)
# ===================================================================

CARRIER_PREF_DECAY: dict[str, float] = {
    "electricity": 0.02,
    "h2": 0.03,
    "biofuel": 0.02,
    # All others: 0.0 (mature, no decay)
}


# ===================================================================
# Subsector — logit competition among EndUseTechs
# ===================================================================

@dataclass
class Subsector:
    """A group of competing EndUseTechs within a demand sector.

    Handles logit competition on levelized cost with preference decay.
    """

    name: str
    techs: list[EndUseTech]
    logit_scale: float = PREF_LOGIT_SCALE
    pref_factors: np.ndarray | None = None
    last_shares: np.ndarray | None = None

    # Per-subsector base demand fraction (set during sector calibration)
    base_demand: float = 0.0

    # Year at which pref_factors were last calibrated (for decay computation)
    calibration_year: int = BASE_YEAR

    def compute_shares(
        self,
        prices: dict[str, float],
        year: int = BASE_YEAR,
        policy: Any = None,
    ) -> np.ndarray:
        """Compute tech shares via preference logit.

        Parameters
        ----------
        prices : dict
            Carrier prices in $/GJ, keyed by carrier name.
        year : int
            Current model year (for preference decay).
        policy : Any
            Policy object (stub: checked via hasattr).

        Returns
        -------
        ndarray of shape (n_techs,)
            Market shares summing to 1.
        """
        costs = np.array([
            t.levelized_cost(prices.get(t.carrier, 5.0))
            for t in self.techs
        ])

        pf = self._decayed_pref_factors(year)

        # Tech availability mask from policy (if present)
        if policy is not None and hasattr(policy, "get_availability"):
            alpha = policy.get_availability(
                [t.name for t in self.techs], year,
            )
            if alpha is not None:
                alpha = np.asarray(alpha, dtype=float)
                # Zero out unavailable techs by adding huge cost penalty
                costs = costs + (1.0 - alpha) * 1e6
        shares = preference_logit(costs, pf, self.logit_scale)
        self.last_shares = shares
        return shares

    def carrier_demands(
        self,
        shares: np.ndarray,
        total_demand_ej: float,
    ) -> dict[str, float]:
        """Convert tech shares + total demand → carrier demands (EJ).

        Accounts for tech efficiency: fuel_input = service / efficiency.
        """
        result: dict[str, float] = {}
        for i, tech in enumerate(self.techs):
            service_ej = shares[i] * total_demand_ej
            fuel_ej = service_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            result[tech.carrier] = result.get(tech.carrier, 0.0) + fuel_ej
        return result

    def price_index(self, prices: dict[str, float]) -> float:
        """Share-weighted average cost of energy service.

        Uses last_shares from most recent compute_shares() call.
        """
        if self.last_shares is None:
            return 5.0
        total = 0.0
        for i, tech in enumerate(self.techs):
            total += self.last_shares[i] * tech.levelized_cost(
                prices.get(tech.carrier, 5.0),
            )
        return total

    def calibrate(
        self,
        base_shares: np.ndarray,
        base_prices: dict[str, float],
    ) -> None:
        """Calibrate preference factors from base-year shares and prices."""
        base_costs = np.array([
            t.levelized_cost(base_prices.get(t.carrier, 5.0))
            for t in self.techs
        ])
        self.pref_factors = preference_calibrate(
            base_shares, base_costs, self.logit_scale,
        )
        self.last_shares = base_shares.copy()

    def _decayed_pref_factors(self, year: int) -> np.ndarray:
        """Apply exponential preference decay by carrier type.

        p_i(t) = p_i(cal) × (1 − decay_rate)^(t − t_cal)
        """
        if self.pref_factors is None:
            return np.zeros(len(self.techs))
        elapsed = max(year - self.calibration_year, 0)
        decayed = np.array([
            pf * (1.0 - CARRIER_PREF_DECAY.get(t.carrier, 0.0)) ** elapsed
            for t, pf in zip(self.techs, self.pref_factors)
        ])
        return decayed


# ===================================================================
# DemandSector ABC
# ===================================================================

class DemandSector(ABC):
    """Base class for final energy demand sectors.

    Two-stage pattern:
      1. demand_envelope() → total sector energy (EJ)
      2. compute_demand()  → carrier allocation via Subsector logit
    """

    subsectors: list[Subsector]

    # Demand driver parameters (set during calibrate or __init__)
    base_demand: float = 0.0
    base_gdp: float = 0.0
    base_price: float = 5.0
    base_population: float = 0.0
    income_elasticity: float = 0.5
    price_elasticity: float = -0.3

    # Per-period demand scaling (legacy, kept for backward compat; prefer sector_pref_weight)
    _demand_scale: float = 1.0

    # Sector-level preference weight added to sector_price_index ($/GJ).
    # Calibrated inversely each period so demand_envelope reproduces GCAM
    # sector totals via the price elasticity channel — replaces _demand_scale.
    sector_pref_weight: float = 0.0

    # Income elasticity curve: list of (gdp_per_cap_2020k, elasticity) tuples.
    # If None, uses fixed self.income_elasticity.
    # Source: gcamdata A32/A42/A52.inc_elas files (converted from 1990$ to 2020$).
    _income_elas_curve: list[tuple[float, float]] | None = None

    # ---- Price index (bottom-up aggregation) ----

    def sector_price_index(self, rs: RegionState) -> float:
        """Demand-weighted average price across subsectors + pref weight.

        P_sector = Σ (E_sub / E_total) × P_sub  +  sector_pref_weight
        """
        total_e = 0.0
        weighted_p = 0.0
        for sub in self.subsectors:
            e_sub = sub.base_demand if sub.base_demand > 0 else 1.0
            p_sub = sub.price_index(rs.carrier_prices)
            weighted_p += e_sub * p_sub
            total_e += e_sub
        base_pi = weighted_p / total_e if total_e > 0 else self.base_price
        return base_pi + self.sector_pref_weight

    # ---- Income elasticity (variable) ----

    def _effective_income_elasticity(self, rs: RegionState) -> float:
        """Income elasticity at current GDP per capita.

        If _income_elas_curve is set, interpolate from the curve.
        Otherwise return the fixed self.income_elasticity.
        """
        if self._income_elas_curve is None:
            return self.income_elasticity
        pop = getattr(rs, "population", 0.0) or self.base_population
        if pop <= 0:
            return self.income_elasticity
        gdp_per_cap_k = rs.gdp / pop  # billion$/million = $k/cap
        return _interpolate_curve(self._income_elas_curve, gdp_per_cap_k)

    # ---- Demand envelope (common pattern) ----

    def demand_envelope(self, rs: RegionState) -> float:
        """Total sector energy demand (EJ).

        E = base × (GDP/GDP_base)^α(y) × (P/P_base)^γ

        α(y) is either fixed or interpolated from _income_elas_curve.
        """
        if self.base_gdp <= 0 or self.base_demand <= 0:
            return 0.0
        gdp_ratio = rs.gdp / self.base_gdp
        alpha = self._effective_income_elasticity(rs)
        price_ratio = max(
            self.sector_price_index(rs) / self.base_price, 0.01,
        )
        return self.base_demand * (
            gdp_ratio ** alpha
            * price_ratio ** self.price_elasticity
        )

    # ---- Abstract methods ----

    @abstractmethod
    def compute_demand(
        self, rs: RegionState, policy: Any = None,
    ) -> dict[str, float]:
        """Compute carrier demands (EJ). Returns {carrier_name: EJ}."""
        ...

    @abstractmethod
    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        """Combustion + sector-specific non-energy emissions."""
        ...

    @abstractmethod
    def calibrate(
        self,
        base_demands: dict[str, float],
        base_prices: dict[str, float],
        base_gdp: float,
    ) -> None:
        """Calibrate from base-year data."""
        ...


# ===================================================================
# TransformationSector ABC
# ===================================================================

class TransformationSector(ABC):
    """Base class for secondary energy production sectors.

    Contains SupplyTechs competing via LCOE logit.
    """

    carrier_output: str
    techs: list[SupplyTech]

    @abstractmethod
    def compute_supply(
        self,
        rs: RegionState,
        demand_ej: float,
        policy: Any = None,
    ) -> dict[str, float]:
        """Compute generation per tech. Returns {tech_name: EJ}."""
        ...

    @abstractmethod
    def compute_price(self, rs: RegionState) -> float:
        """Share-weighted carrier price ($/GJ)."""
        ...

    @abstractmethod
    def compute_emissions(
        self, generation: dict[str, float],
    ) -> EmissionResult:
        """Supply-side emissions from generation."""
        ...

    @abstractmethod
    def calibrate(
        self,
        base_shares: dict[str, float],
        base_prices: dict[str, float],
    ) -> None:
        """Calibrate from base-year shares and prices."""
        ...
