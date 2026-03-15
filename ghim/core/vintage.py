"""Vintage-bin capacity tracker with S-curve retirement.

Enhanced version of ghim.energy.stock.VintageStock:
  - Accepts VintageConfig for parameters
  - Tracks investment results for reporting (last_result property)
  - timestep as instance parameter (not global import)

Two classes:
  VintageTracker            — standard S-curve retirement + gap-fill
  PipelineAwareVintageTracker — adds construction delay for nuclear/hydro
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ghim.core.config import VintageConfig, TIMESTEP
from ghim.config import TECH_RETIREMENT_LIFETIMES, CONSTRUCTION_TIMES


# ===================================================================
# Result dataclass
# ===================================================================

@dataclass
class InvestmentResult:
    """Detailed result from a retire_and_invest call."""

    shares: np.ndarray                   # effective shares (sum to 1)
    new_investment: dict[str, float]     # EJ added per tech this period
    surviving: dict[str, float]          # EJ surviving per tech
    total_surviving_ej: float
    gap_ej: float                        # demand − surviving (>0 = gap)


# ===================================================================
# VintageTracker
# ===================================================================

@dataclass
class VintageTracker:
    """Physical capacity tracker with S-curve retirement.

    Tracks installed capacity (EJ/yr) in vintage bins keyed by
    (tech_name, vintage_year).  Retirement follows a GCAM-style
    sigmoid survival curve, with optional hard-cutoff for
    deterministic-lifetime techs (wind, solar, etc.).

    Parameters
    ----------
    tech_names : list[str]
        Ordered technology names.
    lifetimes : dict[str, float]
        Retirement lifetime per tech (years).
    hard_cutoff_techs : set[str]
        Techs with step-function survival (1 before L, 0 after).
    half_life_ratio : float
        Fraction of lifetime at 50% retirement (ρ).
    steepness : float
        S-curve shape parameter (k).
    timestep : int
        Model timestep in years.
    """

    tech_names: list[str]
    lifetimes: dict[str, float] = field(
        default_factory=lambda: dict(TECH_RETIREMENT_LIFETIMES),
    )
    hard_cutoff_techs: set[str] = field(
        default_factory=lambda: set(VintageConfig().hard_cutoff_techs),
    )
    half_life_ratio: float = VintageConfig().scurve_halflife_ratio
    steepness: float = VintageConfig().scurve_steepness
    timestep: int = TIMESTEP

    # Profit shutdown parameters (GCAM A23.globaltech_retirement)
    # median_shutdown_point: profit_ratio at 50% shutdown (default -0.1)
    # profit_shutdown_steepness: logistic curve steepness (default 6)
    profit_shutdown_params: dict[str, tuple[float, float]] = field(
        default_factory=dict,
    )

    # Internal state
    _capacity: dict[str, dict[int, float]] = field(
        default_factory=dict, repr=False,
    )
    _last_result: InvestmentResult | None = field(
        default=None, repr=False,
    )

    def __post_init__(self) -> None:
        for tech in self.tech_names:
            if tech not in self._capacity:
                self._capacity[tech] = {}

    @classmethod
    def from_config(
        cls,
        tech_names: list[str],
        lifetimes: dict[str, float] | None = None,
        cfg: VintageConfig | None = None,
        timestep: int = TIMESTEP,
    ) -> VintageTracker:
        """Create from VintageConfig (preferred for new OOP code)."""
        cfg = cfg or VintageConfig()
        return cls(
            tech_names=tech_names,
            lifetimes=lifetimes or dict(TECH_RETIREMENT_LIFETIMES),
            hard_cutoff_techs=set(cfg.hard_cutoff_techs),
            half_life_ratio=cfg.scurve_halflife_ratio,
            steepness=cfg.scurve_steepness,
            timestep=timestep,
        )

    @property
    def last_result(self) -> InvestmentResult | None:
        """Most recent InvestmentResult from retire_and_invest."""
        return self._last_result

    # -- S-curve survival ------------------------------------------------

    def s_curve_survival(
        self, tech: str, vintage_year: int, current_year: int,
    ) -> float:
        """Fraction of vintage capacity surviving at *current_year*.

        GCAM-style sigmoid with displacement correction.  Hard-cutoff
        techs return 1.0 before lifetime, 0.0 at/after.
        """
        age = current_year - vintage_year
        if age <= 0:
            return 1.0

        lifetime = self.lifetimes.get(tech, 40.0)

        if tech in self.hard_cutoff_techs:
            return 1.0 if age < lifetime else 0.0

        if age >= lifetime:
            return 0.0

        rho = self.half_life_ratio
        k = self.steepness
        midpoint = rho * lifetime

        raw = 1.0 / (1.0 + math.exp(k * (age - midpoint)))
        raw_at_0 = 1.0 / (1.0 + math.exp(k * (0 - midpoint)))

        if raw_at_0 > 0:
            return min(raw / raw_at_0, 1.0)
        return 0.0

    # -- Capacity queries ------------------------------------------------

    def surviving_capacity(self, current_year: int) -> dict[str, float]:
        """Total surviving capacity (EJ/yr) per tech."""
        result: dict[str, float] = {}
        for tech in self.tech_names:
            total = 0.0
            for vintage_yr, cap in self._capacity.get(tech, {}).items():
                total += cap * self.s_curve_survival(
                    tech, vintage_yr, current_year,
                )
            result[tech] = total
        return result

    def total_surviving(self, current_year: int) -> float:
        """Sum of all surviving capacity across all techs."""
        return sum(self.surviving_capacity(current_year).values())

    # -- Profit shutdown ---------------------------------------------------

    def profit_shutdown_factor(
        self, tech: str, profit_ratio: float,
    ) -> float:
        """Fraction of capacity surviving after profit-based shutdown.

        GCAM-style logistic:
          shutdown_rate = (1+m)^n / ((1+m)^n + (1+π)^n)
          survival = 1 - shutdown_rate

        where π = profit_ratio = (market_price - var_cost) / var_cost,
        m = median_shutdown_point, n = steepness.

        Returns 1.0 (no shutdown) if tech has no profit shutdown params.
        """
        params = self.profit_shutdown_params.get(tech)
        if params is None:
            return 1.0
        median, steep = params
        # Clamp profit_ratio to avoid overflow
        pr = max(min(profit_ratio, 10.0), -0.99)
        num = (1.0 + median) ** steep
        den = num + (1.0 + pr) ** steep
        shutdown_rate = num / den if den > 0 else 0.0
        return max(1.0 - shutdown_rate, 0.0)

    # -- Investment & retirement -----------------------------------------

    def retire_and_invest(
        self,
        year: int,
        target_shares: np.ndarray,
        total_demand_ej: float,
        tech_var_costs: np.ndarray | None = None,
        market_price: float = 0.0,
    ) -> np.ndarray:
        """Compute effective shares after retirement + new investment.

        When tech_var_costs and market_price are provided, applies
        profit-based shutdown AFTER S-curve retirement.  Plants with
        high effective cost (incl. unobservable cost / pref_weight)
        relative to market_price are retired early.

        Returns ndarray of effective shares (sums to 1).
        Also stores detailed InvestmentResult in self.last_result.
        """
        target_shares = np.asarray(target_shares, dtype=float)
        surviving = self.surviving_capacity(year)
        total_surviving = sum(surviving.values())
        new_inv: dict[str, float] = {t: 0.0 for t in self.tech_names}

        if total_demand_ej <= 0:
            self._last_result = InvestmentResult(
                shares=target_shares.copy(),
                new_investment=new_inv,
                surviving=surviving,
                total_surviving_ej=total_surviving,
                gap_ej=0.0,
            )
            return target_shares

        # Apply profit-based shutdown to surviving capacity
        if (tech_var_costs is not None
                and market_price > 0
                and self.profit_shutdown_params):
            for i, tech in enumerate(self.tech_names):
                vc = tech_var_costs[i]
                if vc > 0:
                    profit_ratio = (market_price - vc) / vc
                else:
                    profit_ratio = 10.0  # zero cost → always profitable
                factor = self.profit_shutdown_factor(tech, profit_ratio)
                surviving[tech] *= factor
            total_surviving = sum(surviving.values())

        gap = total_demand_ej - total_surviving

        if gap <= 0:
            # Overcapacity: scale proportionally
            scale = (
                total_demand_ej / total_surviving
                if total_surviving > 0 else 0.0
            )
            effective = np.array([
                surviving.get(t, 0.0) * scale for t in self.tech_names
            ])
        else:
            # Gap: back-calculate new investment so that
            # (surviving + new) / total ≈ target_shares.
            # target_shares are EFFECTIVE targets (GCAM output),
            # not raw new-investment allocations.
            surv_arr = np.array([surviving.get(t, 0.0) for t in self.tech_names])
            desired = target_shares * total_demand_ej
            needed = desired - surv_arr
            needed = np.maximum(needed, 0.0)  # can't disinvest
            needed_sum = needed.sum()
            if needed_sum > 0:
                # Scale to fill the gap exactly
                new_investment_arr = needed * (gap / needed_sum)
            else:
                # All techs over-represented; fall back to target shares
                new_investment_arr = target_shares * gap

            for i, tech in enumerate(self.tech_names):
                if new_investment_arr[i] > 0:
                    self._capacity[tech][year] = (
                        self._capacity[tech].get(year, 0.0)
                        + new_investment_arr[i]
                    )
                    new_inv[tech] = new_investment_arr[i]
            effective = surv_arr + new_investment_arr

        # Normalize to shares
        total = effective.sum()
        if total > 0:
            effective /= total
        else:
            effective = target_shares.copy()

        self._last_result = InvestmentResult(
            shares=effective,
            new_investment=new_inv,
            surviving=surviving,
            total_surviving_ej=total_surviving,
            gap_ej=max(gap, 0.0),
        )
        return effective

    # -- Initialization --------------------------------------------------

    def initialize_uniform(
        self,
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """Distribute capacity uniformly across past vintage bins.

        Scales so surviving capacity at base_year = shares × total_ej.
        """
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            target_ej = shares[i] * total_ej
            if target_ej <= 0:
                continue
            self._init_uniform_single(tech, target_ej, base_year)

    def initialize_single_vintage(
        self,
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """All capacity as single base-year vintage (GCAM-style).

        No historical age distribution — all plants are age 0 at base year.
        S-curve retirement begins only as plants age from this point.
        """
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            cap = shares[i] * total_ej
            if cap > 0:
                self._capacity[tech][base_year] = cap

    def initialize_from_gem(
        self,
        gem_data: dict[str, dict[int, float]],
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """Initialize from GEM vintage distribution, scaled to model totals."""
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            target_cap = shares[i] * total_ej
            if target_cap <= 0:
                continue
            if tech in gem_data and gem_data[tech]:
                gem_total = sum(gem_data[tech].values())
                if gem_total > 0:
                    scale = target_cap / gem_total
                    for vintage_yr, cap in gem_data[tech].items():
                        self._capacity[tech][vintage_yr] = cap * scale
                else:
                    self._init_uniform_single(tech, target_cap, base_year)
            else:
                self._init_uniform_single(tech, target_cap, base_year)

    def initialize_single_vintage(
        self,
        shares: np.ndarray,
        total_ej: float,
        base_year: int,
    ) -> None:
        """Lump all capacity into a single base-year vintage bin."""
        shares = np.asarray(shares, dtype=float)
        for i, tech in enumerate(self.tech_names):
            cap_ej = shares[i] * total_ej
            if cap_ej > 0:
                self._capacity[tech][base_year] = cap_ej

    def _init_uniform_single(
        self, tech: str, target_ej: float, base_year: int,
    ) -> None:
        """Uniform init for one tech, scaled so surviving = target_ej."""
        lifetime = self.lifetimes.get(tech, 40.0)
        oldest = base_year - int(lifetime)
        ts = self.timestep
        if oldest % ts != 0:
            oldest = oldest - (oldest % ts)
        years = list(range(oldest, base_year + 1, ts))
        if not years:
            years = [base_year]

        survival_sum = sum(
            self.s_curve_survival(tech, yr, base_year) for yr in years
        )
        per_bin = target_ej / survival_sum if survival_sum > 0 else target_ej
        for yr in years:
            self._capacity[tech][yr] = per_bin

    # -- Maintenance -----------------------------------------------------

    def prune_retired(self, current_year: int) -> None:
        """Remove fully retired vintage entries (memory optimization)."""
        for tech in self.tech_names:
            bins = self._capacity.get(tech, {})
            dead = [
                yr for yr in bins
                if self.s_curve_survival(tech, yr, current_year) <= 0.0
            ]
            for yr in dead:
                del bins[yr]

    def get_vintage_capacities(self, tech: str) -> dict[int, float]:
        """Copy of vintage bins for a tech (debugging/reporting)."""
        return dict(self._capacity.get(tech, {}))


# ===================================================================
# PipelineAwareVintageTracker (construction delay for nuclear/hydro)
# ===================================================================

@dataclass
class PipelineAwareVintageTracker(VintageTracker):
    """VintageTracker with construction delay for slow-build techs.

    New investment for slow-build techs (nuclear, hydro) goes into
    an under-construction pool.  Capacity arrives after the delay.
    Fast-build techs go directly to capacity.
    """

    _under_construction: dict[str, dict[int, float]] = field(
        default_factory=dict, repr=False,
    )
    construction_times: dict[str, int] = field(
        default_factory=lambda: dict(CONSTRUCTION_TIMES),
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        for tech in self.tech_names:
            if tech not in self._under_construction:
                self._under_construction[tech] = {}

    def _under_construction_total(self, tech: str) -> float:
        """Total capacity under construction for a tech."""
        return sum(self._under_construction.get(tech, {}).values())

    def _complete_construction(self, year: int) -> None:
        """Move completed construction into active vintage bins."""
        for tech in self.tech_names:
            uc = self._under_construction.get(tech, {})
            arrived = uc.pop(year, 0.0)
            if arrived > 0:
                self._capacity[tech][year] = (
                    self._capacity[tech].get(year, 0.0) + arrived
                )

    def retire_and_invest(
        self,
        year: int,
        target_shares: np.ndarray,
        total_demand_ej: float,
        tech_var_costs: np.ndarray | None = None,
        market_price: float = 0.0,
    ) -> np.ndarray:
        """Override: handle construction completion and slow-build routing.

        1. Complete construction arriving this year.
        2. Compute surviving capacity.
        2b. Profit-based shutdown (if cost/price provided).
        3. Gap = demand − surviving − under_construction.
        4. Route new investment: slow-build → pipeline, fast → capacity.
        """
        target_shares = np.asarray(target_shares, dtype=float)

        self._complete_construction(year)

        surviving = self.surviving_capacity(year)
        total_surviving = sum(surviving.values())
        new_inv: dict[str, float] = {t: 0.0 for t in self.tech_names}

        if total_demand_ej <= 0:
            self._last_result = InvestmentResult(
                shares=target_shares.copy(),
                new_investment=new_inv,
                surviving=surviving,
                total_surviving_ej=total_surviving,
                gap_ej=0.0,
            )
            return target_shares

        # Profit-based shutdown
        if (tech_var_costs is not None
                and market_price > 0
                and self.profit_shutdown_params):
            for i, tech in enumerate(self.tech_names):
                vc = tech_var_costs[i]
                if vc > 0:
                    profit_ratio = (market_price - vc) / vc
                else:
                    profit_ratio = 10.0
                factor = self.profit_shutdown_factor(tech, profit_ratio)
                surviving[tech] *= factor
            total_surviving = sum(surviving.values())

        if total_surviving > total_demand_ej:
            # Overcapacity
            scale = (
                total_demand_ej / total_surviving
                if total_surviving > 0 else 0.0
            )
            effective = np.array([
                surviving.get(t, 0.0) * scale for t in self.tech_names
            ])
            gap = 0.0
        else:
            total_uc = sum(
                self._under_construction_total(t) for t in self.tech_names
            )
            gap = max(total_demand_ej - total_surviving - total_uc, 0.0)

            # Back-calculate new investment for effective target matching
            surv_arr = np.array([surviving.get(t, 0.0) for t in self.tech_names])
            desired = target_shares * total_demand_ej
            needed = desired - surv_arr
            needed = np.maximum(needed, 0.0)
            needed_sum = needed.sum()
            if needed_sum > 0:
                new_investment_arr = needed * (gap / needed_sum)
            else:
                new_investment_arr = target_shares * gap

            for i, tech in enumerate(self.tech_names):
                if new_investment_arr[i] <= 0:
                    continue
                new_inv[tech] = new_investment_arr[i]
                delay = self.construction_times.get(tech, 0)
                if delay > 0:
                    completion = year + delay * self.timestep
                    self._under_construction[tech][completion] = (
                        self._under_construction[tech].get(completion, 0.0)
                        + new_investment_arr[i]
                    )
                else:
                    self._capacity[tech][year] = (
                        self._capacity[tech].get(year, 0.0)
                        + new_investment_arr[i]
                    )

            # Effective = surviving + immediate (not pipeline)
            effective = np.array([
                surviving.get(t, 0.0) for t in self.tech_names
            ])
            for i, tech in enumerate(self.tech_names):
                delay = self.construction_times.get(tech, 0)
                if delay == 0:
                    effective[i] += new_investment_arr[i]

        total = effective.sum()
        if total > 0:
            effective /= total
        else:
            effective = target_shares.copy()

        self._last_result = InvestmentResult(
            shares=effective,
            new_investment=new_inv,
            surviving=surviving,
            total_surviving_ej=total_surviving,
            gap_ej=max(gap, 0.0),
        )
        return effective

    def initialize_under_construction(
        self, uc_data: dict[str, dict[int, float]],
    ) -> None:
        """Pre-populate under-construction pool (e.g. WNA nuclear data)."""
        for tech, by_year in uc_data.items():
            if tech in self._under_construction:
                self._under_construction[tech].update(by_year)
            else:
                self._under_construction[tech] = dict(by_year)


# ===================================================================
# Nuclear pipeline data (WNA, converted to EJ/yr)
# ===================================================================

NUCLEAR_PIPELINE_R10: dict[str, dict[int, float]] = {
    "Eastern Asia": {2025: 0.935, 2030: 0.395, 2035: 0.359},
    "Southern Asia": {2025: 0.204, 2030: 0.032, 2035: 0.070},
    "Europe": {2025: 0.187, 2030: 0.078, 2035: 0.136},
    "North America": {2025: 0.026, 2030: 0.025, 2035: 0.050},
    "Eurasia": {2025: 0.055, 2030: 0.080, 2035: 0.040},
    "Middle East": {2025: 0.037, 2030: 0.020, 2035: 0.015},
    "Africa": {2025: 0.0, 2030: 0.0, 2035: 0.010},
    "Latin America and Caribbean": {2025: 0.010, 2030: 0.005, 2035: 0.005},
    "South-East Asia and developing Pacific": {
        2025: 0.0, 2030: 0.005, 2035: 0.010,
    },
    "Developed Asia Pacific": {2025: 0.020, 2030: 0.015, 2035: 0.010},
}
