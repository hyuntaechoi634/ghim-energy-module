"""Inter-regional primary energy trade module.

Clears global markets for coal, oil, and gas via bisection to find
world prices where global supply equals global demand. Each region
faces a delivered price = world price + transport cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from ghim.core.config import TRADED_FUELS, TRADE_MAX_ITER
from ghim.config import TRADE_PRICE_TOL, TRADE_PRICE_FLOOR, TRADE_PRICE_CEILING
from ghim.energy.supply import ResourceSupply
from ghim.regions import R10_REGIONS


@dataclass
class TradeResult:
    """Market clearing result for one fuel."""
    fuel: str
    world_price: float                        # $/GJ (market-clearing)
    regional_production: dict[str, float]     # region → EJ
    regional_demand: dict[str, float]         # region → EJ
    net_exports: dict[str, float]             # region → EJ (positive = exporter)


class GlobalMarket:
    """Clear global market for ONE fuel via bisection."""

    def __init__(
        self,
        fuel: str,
        regional_supplies: dict[str, ResourceSupply],
        transport_costs: dict[str, float],
    ):
        self.fuel = fuel
        self.regional_supplies = regional_supplies  # region → ResourceSupply
        self.transport_costs = transport_costs       # region → $/GJ

    def _global_excess_supply(
        self,
        world_price: float,
        regional_demands: dict[str, float],
        price_adder: float = 0.0,
    ) -> float:
        """Excess supply = total production - total demand at given world price.

        Parameters
        ----------
        price_adder : float
            Constant adder (e.g. calibration rent) added to the bisection
            price when evaluating supply curves.  Supply is evaluated at
            ``world_price + price_adder`` so the clearing respects both
            extraction cost *and* rent simultaneously.
        """
        effective_price = world_price + price_adder
        total_production = 0.0
        total_demand = 0.0
        for region in regional_demands:
            supply = self.regional_supplies.get(region)
            if supply is not None:
                total_production += supply.production_at_price(effective_price)
            total_demand += regional_demands[region]
        return total_production - total_demand

    def _collect_grade_costs(self) -> list[float]:
        """Collect all unique grade costs across all regional supply curves."""
        costs: set[float] = set()
        for supply in self.regional_supplies.values():
            for grade in supply.grades:
                costs.add(grade.extraction_cost)
        return sorted(costs)

    def clear_market(
        self,
        regional_demands: dict[str, float],
        price_lo: float = TRADE_PRICE_FLOOR,
        price_hi: float = TRADE_PRICE_CEILING,
        price_adder: float = 0.0,
    ) -> TradeResult:
        """Find world price where global supply ≈ global demand via bisection.

        Supply curves are piecewise-linear (continuous), so pure bisection
        converges to the exact equilibrium price.  If total supply capacity
        at ``price_hi`` is still below demand, a scarcity premium scales
        the highest grade cost by the demand/supply ratio.

        Parameters
        ----------
        price_adder : float
            Constant adder (e.g. calibration rent) shifted into the supply
            evaluation.  Bisection searches over *extraction-cost* prices;
            supply is evaluated at ``extraction_cost_price + price_adder``.
            The returned ``world_price`` = extraction_cost_price + price_adder,
            so production allocation is already at the correct market price.
        """
        total_demand = sum(regional_demands.values())

        # Edge case: zero demand
        if total_demand <= 0:
            return TradeResult(
                fuel=self.fuel,
                world_price=price_lo + price_adder,
                regional_production={r: 0.0 for r in regional_demands},
                regional_demand=dict(regional_demands),
                net_exports={r: 0.0 for r in regional_demands},
            )

        # Check if max capacity (at price_hi + adder) can meet demand
        max_supply = sum(
            s.production_at_price(price_hi + price_adder)
            for s in self.regional_supplies.values()
        )

        if max_supply < total_demand:
            # Scarcity premium: price rises proportionally with excess demand
            grade_costs = self._collect_grade_costs()
            if grade_costs:
                highest_cost = grade_costs[-1]
                cap_supply = sum(
                    s.production_at_price(highest_cost + price_adder)
                    for s in self.regional_supplies.values()
                )
                if cap_supply > 0:
                    scarcity_ratio = total_demand / cap_supply
                    clearing_price = min(highest_cost * scarcity_ratio, price_hi)
                else:
                    clearing_price = price_hi
            else:
                clearing_price = price_hi
        else:
            # Pure bisection over extraction-cost prices: find price where
            # supply(price + adder) = demand
            lo, hi = price_lo, price_hi
            for _ in range(TRADE_MAX_ITER):
                mid = (lo + hi) / 2.0
                excess = self._global_excess_supply(mid, regional_demands, price_adder)
                if abs(excess) < TRADE_PRICE_TOL * total_demand:
                    lo = hi = mid
                    break
                if excess > 0:
                    hi = mid
                else:
                    lo = mid
            clearing_price = (lo + hi) / 2.0

        # World price includes the adder (rent)
        world_price = clearing_price + price_adder

        # Compute supply capacity at world_price per region
        raw_production: dict[str, float] = {}
        for region in regional_demands:
            supply = self.regional_supplies.get(region)
            raw_production[region] = supply.production_at_price(world_price) if supply else 0.0

        total_capacity = sum(raw_production.values())

        # Scale production to match total demand when capacity exceeds demand
        regional_production: dict[str, float] = {}
        if total_capacity > 0 and total_capacity > total_demand:
            scale = total_demand / total_capacity
            for region in regional_demands:
                regional_production[region] = raw_production[region] * scale
        else:
            regional_production = dict(raw_production)

        net_exports: dict[str, float] = {}
        for region in regional_demands:
            net_exports[region] = regional_production[region] - regional_demands[region]

        return TradeResult(
            fuel=self.fuel,
            world_price=world_price,
            regional_production=regional_production,
            regional_demand=dict(regional_demands),
            net_exports=net_exports,
        )


class TradeModule:
    """Coordinator for all traded fuels."""

    def __init__(
        self,
        regional_supplies: dict[str, dict[str, ResourceSupply]],
        transport_costs: dict[str, dict[str, float]],
        enabled: bool = True,
    ):
        """
        Parameters
        ----------
        regional_supplies : dict
            region → fuel → ResourceSupply
        transport_costs : dict
            fuel → region → $/GJ
        enabled : bool
            If False, solve_trade returns None (no-trade mode).
        """
        self.regional_supplies = regional_supplies
        self.transport_costs = transport_costs
        self.enabled = enabled
        self.calibration_rents: dict[str, float] = {}
        self.prev_world_prices: dict[str, float] = {}
        self.prev_regional_production: dict[str, dict[str, float]] = {}  # fuel → region → EJ

        # Build per-fuel GlobalMarket objects
        self._markets: dict[str, GlobalMarket] = {}
        for fuel in TRADED_FUELS:
            fuel_supplies: dict[str, ResourceSupply] = {}
            fuel_transport: dict[str, float] = {}
            for region in R10_REGIONS:
                if region in regional_supplies and fuel in regional_supplies[region]:
                    fuel_supplies[region] = regional_supplies[region][fuel]
                fuel_transport[region] = transport_costs.get(fuel, {}).get(region, 0.5)
            self._markets[fuel] = GlobalMarket(fuel, fuel_supplies, fuel_transport)

    def solve_trade(
        self,
        regional_fuel_demands: dict[str, dict[str, float]],
    ) -> dict[str, TradeResult] | None:
        """Clear all traded fuel markets.

        Parameters
        ----------
        regional_fuel_demands : dict
            region → fuel → demand (EJ)

        Returns
        -------
        dict mapping fuel → TradeResult, or None if trade disabled.
        """
        if not self.enabled:
            return None

        results: dict[str, TradeResult] = {}
        for fuel in TRADED_FUELS:
            demands = {r: regional_fuel_demands.get(r, {}).get(fuel, 0.0) for r in R10_REGIONS}
            adder = self.calibration_rents.get(fuel, 0.0)
            results[fuel] = self._markets[fuel].clear_market(demands, price_adder=adder)
        return results

    def update_depletion(
        self,
        trade_results: dict[str, TradeResult],
        timestep: int = 5,
    ) -> None:
        """Update cumulative extraction after a period.

        Increments each region's ``cumulative_extracted`` by its
        production × timestep so that cheaper grades deplete over time,
        causing marginal costs and world prices to rise.
        """
        for fuel in TRADED_FUELS:
            tr = trade_results[fuel]
            for region, production in tr.regional_production.items():
                supply = self.regional_supplies.get(region, {}).get(fuel)
                if supply is not None:
                    supply.cumulative_extracted += production * timestep

    def delivered_prices(
        self,
        trade_results: dict[str, TradeResult],
        region: str,
    ) -> dict[str, float]:
        """Compute delivered fuel prices for a region.

        delivered_price = world_price + transport_cost
        """
        prices: dict[str, float] = {}
        for fuel in TRADED_FUELS:
            tr = trade_results[fuel]
            tc = self.transport_costs.get(fuel, {}).get(region, 0.5)
            prices[fuel] = tr.world_price + tc
        return prices

    def calibrate_rents(
        self,
        trade_results: dict[str, TradeResult],
        observed_prices: dict[str, float],
    ) -> None:
        """Compute per-fuel scarcity rent at the first projection period.

        rent = max(0, observed_price - cleared_world_price)

        Called once; subsequent periods reuse the same rents.
        """
        if self.calibration_rents:
            return  # already calibrated
        for fuel in TRADED_FUELS:
            cleared = trade_results[fuel].world_price
            observed = observed_prices.get(fuel, 0.0)
            self.calibration_rents[fuel] = max(0.0, observed - cleared)

    def smooth_prices(
        self,
        trade_results: dict[str, TradeResult],
        max_change_rate: float,
    ) -> None:
        """Clamp rent-adjusted world prices to change at most *max_change_rate*
        per period relative to the previous period (in place).

        No-op if ``prev_world_prices`` is empty (first projection period).
        """
        if not self.prev_world_prices:
            return
        for fuel in TRADED_FUELS:
            prev = self.prev_world_prices.get(fuel)
            if prev is None or prev <= 0:
                continue
            current = trade_results[fuel].world_price
            lo = prev * (1.0 - max_change_rate)
            hi = prev * (1.0 + max_change_rate)
            trade_results[fuel].world_price = max(lo, min(hi, current))

    def record_world_prices(self, trade_results: dict[str, TradeResult]) -> None:
        """Store current world prices for next period's smoothing."""
        self.prev_world_prices = {
            fuel: trade_results[fuel].world_price for fuel in TRADED_FUELS
        }

    def smooth_production(
        self,
        trade_results: dict[str, TradeResult],
        max_decline_rate: float,
    ) -> None:
        """Clamp per-region production declines to at most *max_decline_rate*
        per period (in place). Excess production is redistributed by scaling
        down unconstrained regions so total production is preserved.

        Iterates until no region violates the limit (redistribution can push
        previously-unconstrained regions below their floor).

        No-op when ``prev_regional_production`` is empty (first projection period).
        Only constrains declines, not growth.
        """
        if not self.prev_regional_production:
            return

        for fuel in TRADED_FUELS:
            prev_prod = self.prev_regional_production.get(fuel)
            if prev_prod is None:
                continue
            if fuel not in trade_results:
                continue

            tr = trade_results[fuel]
            total_original = sum(tr.regional_production.values())
            if total_original <= 0:
                continue

            constrained: set[str] = set()

            # Iterate: floor violators, scale down the rest, repeat if
            # the scaling caused new violations.  Converges quickly because
            # each round locks at least one more region.
            for _ in range(len(tr.regional_production)):
                excess = 0.0
                new_constrained = False
                for region, prod in tr.regional_production.items():
                    if region in constrained:
                        continue
                    prev = prev_prod.get(region, 0.0)
                    if prev <= 0:
                        continue
                    floor = prev * (1.0 - max_decline_rate)
                    if prod < floor:
                        excess += floor - prod
                        tr.regional_production[region] = floor
                        constrained.add(region)
                        new_constrained = True

                if excess > 0:
                    unconstrained_total = sum(
                        tr.regional_production[r]
                        for r in tr.regional_production
                        if r not in constrained
                    )
                    if unconstrained_total > excess:
                        scale = (unconstrained_total - excess) / unconstrained_total
                        for region in tr.regional_production:
                            if region not in constrained:
                                tr.regional_production[region] *= scale

                if not new_constrained:
                    break

            # Recompute net exports in place
            for region in tr.regional_production:
                tr.net_exports[region] = (
                    tr.regional_production[region] - tr.regional_demand.get(region, 0.0)
                )

    def record_regional_production(
        self,
        trade_results: dict[str, TradeResult],
    ) -> None:
        """Store current regional production for next period's smoothing."""
        self.prev_regional_production = {
            fuel: dict(trade_results[fuel].regional_production)
            for fuel in TRADED_FUELS
            if fuel in trade_results
        }
