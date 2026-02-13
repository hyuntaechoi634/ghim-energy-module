"""Stock turnover model for gradual fleet/capacity transition.

Two approaches:
1. ``apply_stock_turnover()`` — simple share-blending (original, kept for
   structural nodes in the demand tree).
2. ``VintageStock`` / ``PipelineAwareVintageStock`` — GCAM-inspired vintage
   bin model with S-curve retirement and physical capacity tracking.

    NewStock_i = OldStock_i + (TargetShare_i - OldStock_i) * (dt / tau)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ghim.config import (
    TIMESTEP,
    SCURVE_STEEPNESS,
    SCURVE_HALFLIFE_RATIO,
    HARD_CUTOFF_TECHS,
    TECH_RETIREMENT_LIFETIMES,
    CONSTRUCTION_TIMES,
)


def apply_stock_turnover(
    current_shares: np.ndarray,
    target_shares: np.ndarray,
    dt: int = TIMESTEP,
    turnover_time: float = 30.0,
) -> np.ndarray:
    """Blend current stock shares toward logit-determined target shares.

    Parameters
    ----------
    current_shares : array of shape (n,)
        Stock/fleet shares from previous period (should sum to 1).
    target_shares : array of shape (n,)
        Ideal shares from logit for new investment (should sum to 1).
    dt : int
        Timestep in years.
    turnover_time : float
        Characteristic replacement time in years for this sector.

    Returns
    -------
    ndarray of shape (n,)
        Blended shares, renormalized to sum to 1.
    """
    current_shares = np.asarray(current_shares, dtype=float)
    target_shares = np.asarray(target_shares, dtype=float)

    blend_rate = min(float(dt) / turnover_time, 1.0)
    new_shares = current_shares + blend_rate * (target_shares - current_shares)

    # Ensure non-negative and renormalize
    new_shares = np.maximum(new_shares, 0.0)
    total = new_shares.sum()
    if total > 0:
        new_shares /= total
    return new_shares


# ---------------------------------------------------------------------------
# GCAM-inspired vintage bin model
# ---------------------------------------------------------------------------

@dataclass
class VintageStock:
    """Physical capacity tracker with S-curve retirement.

    Tracks installed capacity (EJ/yr) in vintage bins keyed by
    (tech_name, vintage_year).  Retirement follows a GCAM-style
    sigmoid survival curve, with optional hard-cutoff for techs
    like wind/solar whose lifetime is deterministic.

    Parameters
    ----------
    tech_names : list[str]
        Ordered technology names.
    lifetimes : dict[str, float]
        Retirement lifetime per tech (years).
    hard_cutoff_techs : set[str]
        Techs with step-function survival (1 before lifetime, 0 after).
    half_life_ratio : float
        Fraction of lifetime at which 50% of capacity has retired (rho).
    steepness : float
        S-curve shape parameter (k).
    """

    tech_names: list[str]
    lifetimes: dict[str, float] = field(default_factory=lambda: dict(TECH_RETIREMENT_LIFETIMES))
    hard_cutoff_techs: set[str] = field(default_factory=lambda: set(HARD_CUTOFF_TECHS))
    half_life_ratio: float = SCURVE_HALFLIFE_RATIO
    steepness: float = SCURVE_STEEPNESS
    # tech -> {vintage_year: capacity_ej}
    _capacity: dict[str, dict[int, float]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for tech in self.tech_names:
            if tech not in self._capacity:
                self._capacity[tech] = {}

    # -- S-curve survival ------------------------------------------------

    def s_curve_survival(self, tech: str, vintage_year: int, current_year: int) -> float:
        """Fraction of vintage capacity surviving at *current_year*.

        GCAM-style sigmoid with displacement correction.  Hard-cutoff techs
        return 1.0 before lifetime and 0.0 at/after.
        """
        age = current_year - vintage_year
        if age <= 0:
            return 1.0

        lifetime = self.lifetimes.get(tech, 40.0)

        # Hard cutoff for deterministic-lifetime techs
        if tech in self.hard_cutoff_techs:
            return 1.0 if age < lifetime else 0.0

        # After lifetime → dead
        if age >= lifetime:
            return 0.0

        # GCAM sigmoid: S(age) = 1 / (1 + exp(k * (age - rho*L)))
        # with displacement correction so S(0)~1 and S(L)~0
        rho = self.half_life_ratio
        k = self.steepness
        midpoint = rho * lifetime

        raw = 1.0 / (1.0 + math.exp(k * (age - midpoint)))
        raw_at_0 = 1.0 / (1.0 + math.exp(k * (0 - midpoint)))

        # Normalize so survival(age=0) = 1.0
        if raw_at_0 > 0:
            return min(raw / raw_at_0, 1.0)
        return 0.0

    # -- Capacity queries ------------------------------------------------

    def surviving_capacity(self, current_year: int) -> dict[str, float]:
        """Total surviving capacity (EJ/yr) per tech at *current_year*."""
        result: dict[str, float] = {}
        for tech in self.tech_names:
            total = 0.0
            for vintage_yr, cap in self._capacity.get(tech, {}).items():
                total += cap * self.s_curve_survival(tech, vintage_yr, current_year)
            result[tech] = total
        return result

    def total_surviving(self, current_year: int) -> float:
        """Sum of all surviving capacity across all techs."""
        return sum(self.surviving_capacity(current_year).values())

    # -- Investment & retirement -----------------------------------------

    def retire_and_invest(
        self,
        year: int,
        target_shares: np.ndarray,
        total_demand_ej: float,
    ) -> np.ndarray:
        """Compute effective shares after retirement + new investment.

        Parameters
        ----------
        year : int
            Current model year.
        target_shares : ndarray of shape (n_techs,)
            Logit-determined target shares for new investment (sums to 1).
        total_demand_ej : float
            Total sector demand in EJ/yr.

        Returns
        -------
        ndarray of shape (n_techs,)
            Effective shares (surviving + new investment) / demand.
            Always sums to 1.0.
        """
        target_shares = np.asarray(target_shares, dtype=float)
        surviving = self.surviving_capacity(year)

        total_surviving = sum(surviving.values())

        if total_demand_ej <= 0:
            # No demand: return target shares, no new investment
            return target_shares

        if total_surviving > total_demand_ej:
            # Overcapacity: scale all techs proportionally
            scale = total_demand_ej / total_surviving if total_surviving > 0 else 0.0
            effective = np.array([surviving.get(t, 0.0) * scale for t in self.tech_names])
        else:
            # Gap: fill with new investment following target shares
            gap = total_demand_ej - total_surviving
            new_investment = target_shares * gap
            # Record new vintage
            for i, tech in enumerate(self.tech_names):
                if new_investment[i] > 0:
                    self._capacity[tech][year] = (
                        self._capacity[tech].get(year, 0.0) + new_investment[i]
                    )
            effective = np.array([surviving.get(t, 0.0) for t in self.tech_names]) + new_investment

        # Normalize to shares
        total = effective.sum()
        if total > 0:
            effective /= total
        else:
            effective = target_shares.copy()
        return effective

    # -- Initialization methods ------------------------------------------

    def initialize_uniform(
        self,
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """Distribute capacity uniformly across past vintage bins.

        Creates vintage bins from (base_year - lifetime) to base_year at
        TIMESTEP intervals, then scales up so that *surviving* capacity at
        base_year matches ``shares * total_ej`` (compensating for S-curve
        decay of older vintages).
        """
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            target_ej = shares[i] * total_ej
            if target_ej <= 0:
                continue
            self._init_uniform_single(tech, target_ej, base_year)

    def initialize_from_gem(
        self,
        gem_data: dict[str, dict[int, float]],
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """Initialize from GEM vintage distribution, scaled to model totals.

        Parameters
        ----------
        gem_data : dict
            {tech: {vintage_year: capacity_ej}} from GEM preprocessing.
        shares : ndarray
            Target shares from calibration.
        total_ej : float
            Total sector generation/production in EJ/yr.
        base_year : int
            Model base year.
        """
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            target_cap = shares[i] * total_ej
            if target_cap <= 0:
                continue

            if tech in gem_data and gem_data[tech]:
                # Scale GEM data to match model's total for this tech
                gem_total = sum(gem_data[tech].values())
                if gem_total > 0:
                    scale = target_cap / gem_total
                    for vintage_yr, cap in gem_data[tech].items():
                        self._capacity[tech][vintage_yr] = cap * scale
                else:
                    self._init_uniform_single(tech, target_cap, base_year)
            else:
                # No GEM data for this tech → uniform fallback
                self._init_uniform_single(tech, target_cap, base_year)

    def initialize_single_vintage(
        self,
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """Lump all capacity into a single base-year vintage bin.

        Used for demand sectors where vintage distribution is unknown.
        """
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            cap_ej = shares[i] * total_ej
            if cap_ej > 0:
                self._capacity[tech][base_year] = cap_ej

    def _init_uniform_single(self, tech: str, target_ej: float, base_year: int) -> None:
        """Uniform init for a single tech, scaled so surviving = target_ej."""
        lifetime = self.lifetimes.get(tech, 40.0)
        oldest = base_year - int(lifetime)
        oldest = oldest - (oldest % TIMESTEP) if oldest % TIMESTEP != 0 else oldest
        years = list(range(oldest, base_year + 1, TIMESTEP))
        if not years:
            years = [base_year]

        # Compute survival weights: how much of each vintage survives at base_year
        survival_sum = sum(self.s_curve_survival(tech, yr, base_year) for yr in years)
        if survival_sum > 0:
            # Per-bin raw capacity so that sum(raw * survival) = target
            per_bin = target_ej / survival_sum
        else:
            per_bin = target_ej  # fallback (shouldn't happen)

        for yr in years:
            self._capacity[tech][yr] = per_bin

    # -- Maintenance -----------------------------------------------------

    def prune_retired(self, current_year: int) -> None:
        """Remove vintage entries that have fully retired (memory optimization)."""
        for tech in self.tech_names:
            bins = self._capacity.get(tech, {})
            dead = [
                yr for yr in bins
                if self.s_curve_survival(tech, yr, current_year) <= 0.0
            ]
            for yr in dead:
                del bins[yr]

    def get_vintage_capacities(self, tech: str) -> dict[int, float]:
        """Return a copy of vintage bins for a tech (for debugging/reporting)."""
        return dict(self._capacity.get(tech, {}))


# ---------------------------------------------------------------------------
# Pipeline-aware extension for nuclear / large hydro
# ---------------------------------------------------------------------------

@dataclass
class PipelineAwareVintageStock(VintageStock):
    """VintageStock with construction pipeline for slow-build technologies.

    Nuclear and large hydro take multiple periods to build.  New investment
    for these techs goes into a pipeline and arrives after a construction
    delay.  Fast-build techs (everything else) go directly to capacity.
    """

    # tech -> {completion_year: capacity_ej}
    _pipeline: dict[str, dict[int, float]] = field(default_factory=dict, repr=False)
    construction_times: dict[str, int] = field(default_factory=lambda: dict(CONSTRUCTION_TIMES))

    def __post_init__(self) -> None:
        super().__post_init__()
        for tech in self.tech_names:
            if tech not in self._pipeline:
                self._pipeline[tech] = {}

    def _pipeline_total(self, tech: str) -> float:
        """Total capacity in the pipeline for a tech."""
        return sum(self._pipeline.get(tech, {}).values())

    def _arrive_pipeline(self, year: int) -> None:
        """Move pipeline capacity that has arrived into active vintage bins."""
        for tech in self.tech_names:
            pipeline = self._pipeline.get(tech, {})
            arrived = pipeline.pop(year, 0.0)
            if arrived > 0:
                self._capacity[tech][year] = (
                    self._capacity[tech].get(year, 0.0) + arrived
                )

    def retire_and_invest(
        self,
        year: int,
        target_shares: np.ndarray,
        total_demand_ej: float,
    ) -> np.ndarray:
        """Override: handle pipeline arrivals and slow-build routing.

        1. Pop arrived pipeline capacity into vintage bins.
        2. Compute surviving capacity.
        3. Gap = demand - surviving - future pipeline.
        4. New investment for slow-build techs goes to pipeline.
        5. Fast-build techs go directly to capacity.
        """
        target_shares = np.asarray(target_shares, dtype=float)

        # Step 1: Arrive pipeline capacity
        self._arrive_pipeline(year)

        surviving = self.surviving_capacity(year)
        total_surviving = sum(surviving.values())

        if total_demand_ej <= 0:
            return target_shares

        if total_surviving > total_demand_ej:
            # Overcapacity
            scale = total_demand_ej / total_surviving if total_surviving > 0 else 0.0
            effective = np.array([surviving.get(t, 0.0) * scale for t in self.tech_names])
        else:
            # Subtract pipeline total from gap
            total_pipeline = sum(self._pipeline_total(t) for t in self.tech_names)
            gap = max(total_demand_ej - total_surviving - total_pipeline, 0.0)

            new_investment = target_shares * gap
            for i, tech in enumerate(self.tech_names):
                if new_investment[i] <= 0:
                    continue
                delay = self.construction_times.get(tech, 0)
                if delay > 0:
                    # Route to pipeline
                    completion = year + delay * TIMESTEP
                    self._pipeline[tech][completion] = (
                        self._pipeline[tech].get(completion, 0.0) + new_investment[i]
                    )
                else:
                    # Immediate capacity
                    self._capacity[tech][year] = (
                        self._capacity[tech].get(year, 0.0) + new_investment[i]
                    )

            # Effective = surviving + immediate new investment (not pipeline)
            effective = np.array([surviving.get(t, 0.0) for t in self.tech_names])
            for i, tech in enumerate(self.tech_names):
                delay = self.construction_times.get(tech, 0)
                if delay == 0:
                    effective[i] += new_investment[i]

        total = effective.sum()
        if total > 0:
            effective /= total
        else:
            effective = target_shares.copy()
        return effective

    def initialize_pipeline(self, pipeline_data: dict[str, dict[int, float]]) -> None:
        """Pre-populate pipeline from external data (e.g. WNA nuclear data).

        Parameters
        ----------
        pipeline_data : dict
            {tech: {completion_year: capacity_ej}}
        """
        for tech, by_year in pipeline_data.items():
            if tech in self._pipeline:
                self._pipeline[tech].update(by_year)
            else:
                self._pipeline[tech] = dict(by_year)


# ---------------------------------------------------------------------------
# Nuclear pipeline data (from WNA, converted to EJ/yr)
# ---------------------------------------------------------------------------
NUCLEAR_PIPELINE_R10: dict[str, dict[int, float]] = {
    "Eastern Asia": {2025: 0.935, 2030: 0.395, 2035: 0.359},
    "Southern Asia": {2025: 0.204, 2030: 0.032, 2035: 0.070},
    "Europe": {2025: 0.187, 2030: 0.078, 2035: 0.136},
    "North America": {2025: 0.026, 2030: 0.025, 2035: 0.050},
    "Eurasia": {2025: 0.055, 2030: 0.080, 2035: 0.040},
    "Middle East": {2025: 0.037, 2030: 0.020, 2035: 0.015},
    "Africa": {2025: 0.0, 2030: 0.0, 2035: 0.010},
    "Latin America and Caribbean": {2025: 0.010, 2030: 0.005, 2035: 0.005},
    "South-East Asia and developing Pacific": {2025: 0.0, 2030: 0.005, 2035: 0.010},
    "Developed Asia Pacific": {2025: 0.020, 2030: 0.015, 2035: 0.010},
}
