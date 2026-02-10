"""Final energy demand model with nested logit tree.

Computes energy demand by sector (industry, buildings, transport) driven by
GDP and population growth.  Each sector has a hierarchical tree of subsectors,
with preference-factor logit fuel switching and stock turnover at every level.

The nesting structure supports arbitrary depth.  Phase 2 defaults use 2 levels:
  Sector → Subsector → Fuel carrier

Example (transport):
  transport
  ├── passenger (τ=15y)
  │   ├── refined liquids
  │   ├── electricity
  │   ├── gas
  │   ├── hydrogen
  │   └── biomass
  └── freight (τ=15y)
      ├── refined liquids
      ├── gas
      ├── electricity
      ├── hydrogen
      └── biomass
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ghim.config import (
    DEMAND_LOGIT_EXP, BASE_YEAR, PREF_LOGIT_SCALE, TIMESTEP,
    TURNOVER_TIMES, LOGIT_EXP_PREF, PREF_DECAY_RATES,
)
from ghim.energy.logit import (
    logit_shares, logit_calibrate,
    preference_logit, preference_calibrate,
    relative_pref_logit,
)
from ghim.energy.stock import apply_stock_turnover

# Energy carriers available to final demand sectors
ENERGY_CARRIERS = ["coal", "refined liquids", "gas", "electricity", "biomass", "hydrogen"]

# Income elasticities of energy demand by sector
INCOME_ELASTICITY: dict[str, float] = {
    "industry": 0.6,
    "buildings": 0.5,
    "transport": 0.7,
}

# Legacy flat defaults (kept for backward compat / reference)
DEFAULT_FUEL_SHARES: dict[str, dict[str, float]] = {
    "industry": {
        "coal": 0.25, "refined liquids": 0.15, "gas": 0.25,
        "electricity": 0.25, "biomass": 0.08, "hydrogen": 0.02,
    },
    "buildings": {
        "coal": 0.05, "refined liquids": 0.10, "gas": 0.30,
        "electricity": 0.40, "biomass": 0.14, "hydrogen": 0.01,
    },
    "transport": {
        "coal": 0.0, "refined liquids": 0.90, "gas": 0.03,
        "electricity": 0.03, "biomass": 0.03, "hydrogen": 0.01,
    },
}


# ---------------------------------------------------------------------------
# Nested demand tree
# ---------------------------------------------------------------------------

@dataclass
class DemandLeaf:
    """Terminal node mapping to an energy carrier."""
    name: str
    carrier: str       # one of ENERGY_CARRIERS


class DemandNode:
    """Branch node in the nested demand tree.

    Children compete via preference-factor logit with stock turnover.
    Children can be other DemandNodes (branch) or DemandLeafs (terminal).
    """

    def __init__(
        self,
        name: str,
        children: list[DemandNode | DemandLeaf],
        base_shares: dict[str, float],
        scale_k: float = PREF_LOGIT_SCALE,
        turnover_time: float = 30.0,
        logit_exp: float = LOGIT_EXP_PREF,
    ):
        self.name = name
        self.children = children
        self.scale_k = scale_k
        self.turnover_time = turnover_time
        self.logit_exp = logit_exp

        # Ordered child names
        self._child_names = [c.name for c in children]

        # Normalize base shares
        raw = np.array([base_shares.get(n, 0.01) for n in self._child_names])
        raw = np.maximum(raw, 1e-6)
        self._base_shares = raw / raw.sum()

        # Preference factors (set during calibration)
        self.pref_factors: np.ndarray | None = None
        self.base_pref_factors: np.ndarray | None = None

        # Stock turnover state
        self.current_shares: np.ndarray | None = None

    def _child_cost(self, child: DemandNode | DemandLeaf, fuel_prices: dict[str, float]) -> float:
        """Get effective cost of a child (leaf=fuel price, branch=weighted avg)."""
        if isinstance(child, DemandLeaf):
            return fuel_prices.get(child.carrier, 5.0)
        return child.weighted_cost(fuel_prices)

    def weighted_cost(self, fuel_prices: dict[str, float]) -> float:
        """Weighted average cost using current (or base) shares."""
        costs = np.array([self._child_cost(c, fuel_prices) for c in self.children])
        shares = self.current_shares if self.current_shares is not None else self._base_shares
        return float(np.dot(shares, costs))

    def calibrate(self, fuel_prices: dict[str, float]) -> None:
        """Calibrate preference factors recursively (children first, then self)."""
        for child in self.children:
            if isinstance(child, DemandNode):
                child.calibrate(fuel_prices)

        costs = np.array([self._child_cost(c, fuel_prices) for c in self.children])
        self.pref_factors = preference_calibrate(
            self._base_shares, costs, self.scale_k, logit_exp=self.logit_exp,
        )
        self.base_pref_factors = self.pref_factors.copy()
        self.current_shares = self._base_shares.copy()

    def _compute_pref_factors(
        self,
        year: int | None,
        pref_override_map: dict[str, float] | None = None,
    ) -> np.ndarray:
        """Compute per-child preference factors for a given year."""
        if self.base_pref_factors is None:
            return np.zeros(len(self.children))

        years_elapsed = max((year or BASE_YEAR) - BASE_YEAR, 0)
        pf = np.empty(len(self.children))
        for i, child in enumerate(self.children):
            if pref_override_map and child.name in pref_override_map:
                pf[i] = pref_override_map[child.name]
            else:
                rate = PREF_DECAY_RATES.get(child.name, 0.0)
                # For leaf nodes, try carrier name too
                if isinstance(child, DemandLeaf) and rate == 0.0:
                    rate = PREF_DECAY_RATES.get(child.carrier, 0.0)
                pf[i] = self.base_pref_factors[i] * (1.0 - rate) ** years_elapsed
        return pf

    def compute_carrier_demands(
        self,
        total_ej: float,
        fuel_prices: dict[str, float],
        year: int | None = None,
        alpha_map: dict[str, float] | None = None,
        pref_override_map: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute energy demands by carrier, recursing into children.

        Parameters
        ----------
        year : int, optional
            Current model year for PF decay.
        alpha_map : dict, optional
            Child name -> 0.0/1.0 availability. Default 1.0 for all.
        pref_override_map : dict, optional
            Child name -> explicit $/GJ preference factor.
        """
        # Child costs (using previous-period shares for branches)
        costs = np.array([self._child_cost(c, fuel_prices) for c in self.children])

        # Build alpha array
        alpha = None
        if alpha_map:
            alpha = np.array([alpha_map.get(c.name, 1.0) for c in self.children])

        # Target shares from relative-pref logit
        if self.pref_factors is not None:
            pf = self._compute_pref_factors(year, pref_override_map)
            self.pref_factors = pf
            target_shares = relative_pref_logit(
                costs, pf, self.scale_k, self.logit_exp, alpha,
            )
        else:
            target_shares = self._base_shares

        # Stock turnover
        if self.current_shares is not None:
            effective = apply_stock_turnover(
                self.current_shares, target_shares, TIMESTEP, self.turnover_time,
            )
            self.current_shares = effective
        else:
            effective = target_shares
            self.current_shares = target_shares.copy()

        # Allocate to children and recurse
        result: dict[str, float] = {}
        for child, share in zip(self.children, effective):
            child_ej = float(share) * total_ej
            if isinstance(child, DemandLeaf):
                result[child.carrier] = result.get(child.carrier, 0.0) + child_ej
            else:
                sub = child.compute_carrier_demands(
                    child_ej, fuel_prices, year=year,
                    alpha_map=alpha_map, pref_override_map=pref_override_map,
                )
                for k, v in sub.items():
                    result[k] = result.get(k, 0.0) + v
        return result


# ---------------------------------------------------------------------------
# Default 2-level sector trees
# ---------------------------------------------------------------------------

def _make_fuel_node(
    name: str,
    fuel_shares: dict[str, float],
    scale_k: float = PREF_LOGIT_SCALE,
    turnover_time: float = 30.0,
) -> DemandNode:
    """Helper: create a DemandNode whose children are fuel leaves."""
    children = [
        DemandLeaf(f"{name}_{carrier}", carrier)
        for carrier in fuel_shares
    ]
    base_shares = {f"{name}_{carrier}": share for carrier, share in fuel_shares.items()}
    return DemandNode(name, children, base_shares, scale_k, turnover_time)


def _default_transport_tree() -> DemandNode:
    """Transport: passenger/freight subsectors with fuel competition."""
    passenger = _make_fuel_node("passenger", {
        "refined liquids": 0.87, "electricity": 0.05, "gas": 0.04,
        "hydrogen": 0.02, "biomass": 0.02,
    }, turnover_time=TURNOVER_TIMES["transport"])

    freight = _make_fuel_node("freight", {
        "refined liquids": 0.95, "gas": 0.02, "electricity": 0.01,
        "hydrogen": 0.01, "biomass": 0.01,
    }, turnover_time=TURNOVER_TIMES["transport"])

    return DemandNode(
        "transport",
        [passenger, freight],
        {"passenger": 0.60, "freight": 0.40},
        scale_k=0.05,       # low sensitivity — structural split
        turnover_time=50.0,  # very slow structural change
    )


def _default_industry_tree() -> DemandNode:
    """Industry: heavy/light/data_centers subsectors with fuel competition.

    Data centers separated per IEA WEO 2024 — nearly 100% electricity,
    high growth rate, short equipment turnover (~7 years).
    """
    heavy = _make_fuel_node("heavy", {
        "coal": 0.35, "gas": 0.25, "electricity": 0.15,
        "refined liquids": 0.10, "biomass": 0.10, "hydrogen": 0.05,
    }, turnover_time=TURNOVER_TIMES["industry"])

    light = _make_fuel_node("light", {
        "electricity": 0.40, "gas": 0.25, "refined liquids": 0.15,
        "coal": 0.10, "biomass": 0.08, "hydrogen": 0.02,
    }, turnover_time=TURNOVER_TIMES["industry"])

    # Data centers: 100% electricity, short turnover
    data_centers = _make_fuel_node("data_centers", {
        "electricity": 1.0,
    }, turnover_time=TURNOVER_TIMES.get("data_centers", 7.0))

    return DemandNode(
        "industry",
        [heavy, light, data_centers],
        {"heavy": 0.45, "light": 0.45, "data_centers": 0.10},
        scale_k=0.05,
        turnover_time=50.0,
    )


def _default_buildings_tree() -> DemandNode:
    """Buildings: residential/commercial subsectors with fuel competition."""
    residential = _make_fuel_node("residential", {
        "electricity": 0.35, "gas": 0.30, "biomass": 0.18,
        "refined liquids": 0.12, "coal": 0.04, "hydrogen": 0.01,
    }, turnover_time=TURNOVER_TIMES["buildings"])

    commercial = _make_fuel_node("commercial", {
        "electricity": 0.50, "gas": 0.30, "refined liquids": 0.08,
        "biomass": 0.08, "coal": 0.02, "hydrogen": 0.02,
    }, turnover_time=TURNOVER_TIMES["buildings"])

    return DemandNode(
        "buildings",
        [residential, commercial],
        {"residential": 0.55, "commercial": 0.45},
        scale_k=0.05,
        turnover_time=60.0,
    )


_DEFAULT_TREES = {
    "transport": _default_transport_tree,
    "industry": _default_industry_tree,
    "buildings": _default_buildings_tree,
}


def _default_sector_tree(sector: str) -> DemandNode:
    """Get default nested tree for a sector, or flat fallback."""
    factory = _DEFAULT_TREES.get(sector)
    if factory is not None:
        return factory()
    # Fallback: flat tree from legacy fuel shares
    fuel_shares = DEFAULT_FUEL_SHARES.get(sector, {c: 1.0 / len(ENERGY_CARRIERS) for c in ENERGY_CARRIERS})
    return _make_fuel_node(sector, fuel_shares, turnover_time=30.0)


# ---------------------------------------------------------------------------
# FinalDemand: backward-compatible interface wrapping the nested tree
# ---------------------------------------------------------------------------

class FinalDemand:
    """Final energy demand for one sector in one region.

    Wraps a nested DemandNode tree with GDP-driven total demand scaling.
    The tree handles fuel switching via preference logit + stock turnover
    at every nesting level.
    """

    def __init__(
        self,
        sector: str,
        base_demand_ej: float,
        tree: DemandNode | None = None,
        income_elasticity: float | None = None,
    ):
        self.sector = sector
        self.base_demand_ej = base_demand_ej
        self.income_elasticity = income_elasticity or INCOME_ELASTICITY.get(sector, 0.6)
        self.tree = tree or _default_sector_tree(sector)
        self._base_gdp: float = 0.0

    def calibrate(self, fuel_prices: dict[str, float], base_gdp: float) -> None:
        """Calibrate preference factors throughout the tree and store base GDP."""
        self._base_gdp = base_gdp
        self.tree.calibrate(fuel_prices)

    def compute_demand(
        self,
        gdp: float,
        fuel_prices: dict[str, float],
        year: int | None = None,
        alpha_map: dict[str, float] | None = None,
        pref_override_map: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute fuel demand by carrier for a given period.

        Total demand scales with GDP growth via income elasticity.
        Fuel allocation is determined by the nested logit tree.

        Parameters
        ----------
        year : int, optional
            Current model year for PF decay.
        alpha_map : dict, optional
            Child name -> 0.0/1.0 availability.
        pref_override_map : dict, optional
            Child name -> explicit $/GJ preference factor.

        Returns dict of carrier -> demand in EJ.
        """
        if self._base_gdp > 0:
            gdp_ratio = gdp / self._base_gdp
        else:
            gdp_ratio = 1.0

        total_demand = self.base_demand_ej * (gdp_ratio ** self.income_elasticity)
        return self.tree.compute_carrier_demands(
            total_demand, fuel_prices, year=year,
            alpha_map=alpha_map, pref_override_map=pref_override_map,
        )
