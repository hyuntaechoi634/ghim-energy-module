"""Policy scenario definitions and loading.

Supports carbon pricing, renewable subsidies, efficiency standards,
emissions caps, technology constraints, and revenue recycling.
All defaults are zero/disabled — existing behavior is unchanged
without policy arguments.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


def _interpolate(trajectory: dict[int, float], year: int) -> float:
    """Linear interpolation between trajectory waypoints.

    Held flat beyond endpoints.
    """
    if not trajectory:
        return 0.0
    years = sorted(trajectory.keys())
    if year <= years[0]:
        return trajectory[years[0]]
    if year >= years[-1]:
        return trajectory[years[-1]]
    # Find bracketing years
    for i in range(len(years) - 1):
        if years[i] <= year <= years[i + 1]:
            y0, y1 = years[i], years[i + 1]
            v0, v1 = trajectory[y0], trajectory[y1]
            frac = (year - y0) / (y1 - y0)
            return v0 + frac * (v1 - v0)
    return trajectory[years[-1]]  # pragma: no cover


def _int_keys(d: dict) -> dict[int, float]:
    """Convert string keys to int (JSON loads keys as strings)."""
    return {int(k): float(v) for k, v in d.items()}


@dataclass
class CarbonPricePolicy:
    """Carbon price trajectory (year -> $/tCO2)."""
    trajectory: dict[int, float] = field(default_factory=dict)

    def get_price(self, year: int) -> float:
        return _interpolate(self.trajectory, year)


@dataclass
class RenewableSubsidy:
    """Per-technology subsidies (tech -> year -> $/GJ cost reduction)."""
    subsidies: dict[str, dict[int, float]] = field(default_factory=dict)

    def get_subsidy(self, tech: str, year: int) -> float:
        if tech not in self.subsidies:
            return 0.0
        return _interpolate(self.subsidies[tech], year)


@dataclass
class EfficiencyStandard:
    """Autonomous energy efficiency improvement rates.

    rates: sector|"global" -> year -> annual improvement rate.
    cumulative_factor returns (1-rate)^elapsed for demand scaling.
    """
    rates: dict[str, dict[int, float]] = field(default_factory=dict)

    def cumulative_factor(self, sector: str, year: int, base_year: int) -> float:
        """Return cumulative efficiency multiplier for *sector* at *year*.

        Falls back to "global" if sector-specific rate is absent.
        Returns 1.0 if no rates are defined.
        """
        key = sector if sector in self.rates else "global"
        if key not in self.rates:
            return 1.0
        rate = _interpolate(self.rates[key], year)
        elapsed = max(year - base_year, 0)
        return (1.0 - rate) ** elapsed


@dataclass
class EmissionsCap:
    """Emissions cap trajectory (scope -> year -> MtCO2).

    scope is typically "global"; regional caps possible but not yet used.
    """
    caps: dict[str, dict[int, float]] = field(default_factory=dict)
    bisect_tol: float = 0.02       # 2% tolerance
    bisect_max_iter: int = 20
    bisect_price_max: float = 2000.0  # $/tCO2 upper bound for bisection

    def get_cap(self, scope: str, year: int) -> float | None:
        if scope not in self.caps:
            return None
        return _interpolate(self.caps[scope], year)

    def has_cap(self, year: int) -> bool:
        for scope in self.caps:
            cap = self.get_cap(scope, year)
            if cap is not None:
                return True
        return False


@dataclass
class TechConstraint:
    """Share constraint for a specific technology in a sector."""
    sector: str
    technology: str
    constraint_type: str  # "max" or "min"
    trajectory: dict[int, float] = field(default_factory=dict)

    def get_bound(self, year: int) -> float:
        return _interpolate(self.trajectory, year)


@dataclass
class RevenueRecycling:
    """Fraction of carbon revenue recycled to reduce energy cost."""
    fraction: float = 0.0


@dataclass
class TechAvailability:
    """Binary α schedules: "sector.tech" -> {year: 0|1}.

    Controls whether a technology is available (α=1) or disabled (α=0)
    in each period.  Default = available for all unlisted technologies.
    Interpolates between waypoints (rounds to 0 or 1).
    """
    schedules: dict[str, dict[int, int]] = field(default_factory=dict)

    def is_available(self, sector: str, tech: str, year: int) -> bool:
        key = f"{sector}.{tech}"
        if key not in self.schedules:
            return True
        val = _interpolate(self.schedules[key], year)
        return val >= 0.5


@dataclass
class PrefFactorOverride:
    """Explicit P(t) trajectories: "sector.tech" -> {year: $/GJ}.

    Overrides the default decay-based preference factor for specific
    technologies.  Structured for future outer-loop SSP calibration.
    """
    overrides: dict[str, dict[int, float]] = field(default_factory=dict)

    def get_override(self, sector: str, tech: str, year: int) -> float | None:
        key = f"{sector}.{tech}"
        if key not in self.overrides:
            return None
        return _interpolate(self.overrides[key], year)


@dataclass
class PolicyScenario:
    """Root policy container. All sub-policies default to no-op."""
    name: str = "none"
    carbon_price: CarbonPricePolicy = field(default_factory=CarbonPricePolicy)
    renewable_subsidies: RenewableSubsidy = field(default_factory=RenewableSubsidy)
    efficiency_standards: EfficiencyStandard = field(default_factory=EfficiencyStandard)
    emissions_cap: EmissionsCap = field(default_factory=EmissionsCap)
    tech_constraints: list[TechConstraint] = field(default_factory=list)
    revenue_recycling: RevenueRecycling = field(default_factory=RevenueRecycling)
    tech_availability: TechAvailability = field(default_factory=TechAvailability)
    pref_overrides: PrefFactorOverride = field(default_factory=PrefFactorOverride)


# -----------------------------------------------------------------------
# Loading helpers
# -----------------------------------------------------------------------

def load_policy(path: str | Path) -> PolicyScenario:
    """Load a PolicyScenario from a JSON file."""
    path = Path(path)
    with open(path) as f:
        raw = json.load(f)

    ps = PolicyScenario(name=raw.get("name", path.stem))

    # Carbon price
    if "carbon_price" in raw:
        cp = raw["carbon_price"]
        ps.carbon_price = CarbonPricePolicy(
            trajectory=_int_keys(cp.get("trajectory", {})),
        )

    # Renewable subsidies
    if "renewable_subsidies" in raw:
        rs = raw["renewable_subsidies"]
        subs = {}
        for tech, traj in rs.get("subsidies", {}).items():
            subs[tech] = _int_keys(traj)
        ps.renewable_subsidies = RenewableSubsidy(subsidies=subs)

    # Efficiency standards
    if "efficiency_standards" in raw:
        es = raw["efficiency_standards"]
        rates = {}
        for scope, traj in es.get("rates", {}).items():
            rates[scope] = _int_keys(traj)
        ps.efficiency_standards = EfficiencyStandard(rates=rates)

    # Emissions cap
    if "emissions_cap" in raw:
        ec = raw["emissions_cap"]
        caps = {}
        for scope, traj in ec.get("caps", {}).items():
            caps[scope] = _int_keys(traj)
        ps.emissions_cap = EmissionsCap(caps=caps)

    # Tech constraints
    if "tech_constraints" in raw:
        for tc in raw["tech_constraints"]:
            ps.tech_constraints.append(TechConstraint(
                sector=tc["sector"],
                technology=tc["technology"],
                constraint_type=tc["constraint_type"],
                trajectory=_int_keys(tc.get("trajectory", {})),
            ))

    # Revenue recycling
    if "revenue_recycling" in raw:
        rr = raw["revenue_recycling"]
        ps.revenue_recycling = RevenueRecycling(fraction=rr.get("fraction", 0.0))

    # Tech availability (binary α schedules)
    if "tech_availability" in raw:
        ta = raw["tech_availability"]
        schedules = {}
        for key, traj in ta.get("schedules", {}).items():
            schedules[key] = {int(k): int(v) for k, v in traj.items()}
        ps.tech_availability = TechAvailability(schedules=schedules)

    # Preference factor overrides
    if "pref_overrides" in raw:
        po = raw["pref_overrides"]
        overrides = {}
        for key, traj in po.get("overrides", {}).items():
            overrides[key] = _int_keys(traj)
        ps.pref_overrides = PrefFactorOverride(overrides=overrides)

    return ps


def policy_from_cli(
    carbon_price: float = 0.0,
    efficiency_rate: float = 0.0,
    recycling_fraction: float = 0.0,
) -> PolicyScenario:
    """Build a PolicyScenario from simple CLI flag values.

    Creates constant (time-invariant) policies.
    """
    ps = PolicyScenario(name="cli")

    if carbon_price > 0:
        # Constant price from 2020 onward
        ps.carbon_price = CarbonPricePolicy(trajectory={2020: carbon_price})

    if efficiency_rate > 0:
        ps.efficiency_standards = EfficiencyStandard(
            rates={"global": {2020: efficiency_rate}},
        )

    if recycling_fraction > 0:
        ps.revenue_recycling = RevenueRecycling(fraction=recycling_fraction)

    return ps


def apply_share_constraints(
    shares: "np.ndarray",
    tech_names: list[str],
    constraints: list[TechConstraint],
    year: int,
    sector: str,
) -> "np.ndarray":
    """Clamp technology shares to min/max bounds and renormalize.

    Parameters
    ----------
    shares : ndarray
        Current technology shares (sum to 1).
    tech_names : list[str]
        Technology names matching shares indices.
    constraints : list[TechConstraint]
        Active constraints (filtered externally or here by sector).
    year : int
        Current model year.
    sector : str
        Sector name to filter constraints.

    Returns
    -------
    ndarray
        Adjusted shares summing to 1.
    """
    import numpy as np

    adjusted = shares.copy().astype(float)
    name_to_idx = {n: i for i, n in enumerate(tech_names)}
    n = len(adjusted)

    # Collect applicable bounds
    max_bounds: dict[int, float] = {}
    min_bounds: dict[int, float] = {}
    for tc in constraints:
        if tc.sector != sector:
            continue
        if tc.technology not in name_to_idx:
            continue
        idx = name_to_idx[tc.technology]
        bound = tc.get_bound(year)
        if tc.constraint_type == "max":
            max_bounds[idx] = bound
        elif tc.constraint_type == "min":
            min_bounds[idx] = bound

    if not max_bounds and not min_bounds:
        return adjusted

    # Iterative clamp-and-redistribute (handles interactions between constraints)
    fixed = np.zeros(n, dtype=bool)
    for _ in range(n):
        changed = False
        for idx, bound in max_bounds.items():
            if not fixed[idx] and adjusted[idx] > bound:
                excess = adjusted[idx] - bound
                adjusted[idx] = bound
                fixed[idx] = True
                # Distribute excess to unfixed techs proportionally
                unfixed = ~fixed
                unfixed_sum = adjusted[unfixed].sum()
                if unfixed_sum > 0:
                    adjusted[unfixed] += excess * (adjusted[unfixed] / unfixed_sum)
                changed = True
        for idx, bound in min_bounds.items():
            if not fixed[idx] and adjusted[idx] < bound:
                deficit = bound - adjusted[idx]
                adjusted[idx] = bound
                fixed[idx] = True
                # Take deficit from unfixed techs proportionally
                unfixed = ~fixed
                unfixed_sum = adjusted[unfixed].sum()
                if unfixed_sum > 0:
                    adjusted[unfixed] -= deficit * (adjusted[unfixed] / unfixed_sum)
                changed = True
        if not changed:
            break

    # Floor negative shares
    adjusted = np.maximum(adjusted, 0.0)

    # Final renormalize (should already sum to ~1.0)
    total = adjusted.sum()
    if total > 0:
        adjusted = adjusted / total
    else:
        adjusted = np.ones(n) / n

    return adjusted
