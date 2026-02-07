"""Inter-regional primary energy trade module.

Clears global markets for coal, oil, and gas via bisection to find
world prices where global supply equals global demand. Each region
faces a delivered price = world price + transport cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from ghim.config import (
    TRADED_FUELS,
    TRADE_PRICE_TOL,
    TRADE_MAX_ITER,
    TRADE_PRICE_FLOOR,
    TRADE_PRICE_CEILING,
)
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
    ) -> float:
        """Excess supply = total production - total demand at given world price."""
        total_production = 0.0
        total_demand = 0.0
        for region in regional_demands:
            supply = self.regional_supplies.get(region)
            if supply is not None:
                total_production += supply.production_at_price(world_price)
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
    ) -> TradeResult:
        """Find world price where global supply ≈ global demand via bisection.

        Because supply curves are step functions (discrete grades), the bisection
        finds the marginal price. If total supply capacity at the clearing price
        exceeds demand, production is scaled proportionally across regions.
        """
        total_demand = sum(regional_demands.values())

        # Edge case: zero demand
        if total_demand <= 0:
            return TradeResult(
                fuel=self.fuel,
                world_price=price_lo,
                regional_production={r: 0.0 for r in regional_demands},
                regional_demand=dict(regional_demands),
                net_exports={r: 0.0 for r in regional_demands},
            )

        # For step-function supply curves, find the cheapest grade cost
        # where total supply capacity >= total demand. This is the marginal cost.
        grade_costs = self._collect_grade_costs()

        world_price = price_hi  # fallback
        prev_cost = price_lo
        for cost in grade_costs:
            total_supply = sum(
                s.production_at_price(cost)
                for s in self.regional_supplies.values()
            )
            if total_supply >= total_demand:
                world_price = cost
                break
            prev_cost = cost

        # Fine-tune via bisection between previous grade and this one,
        # but ONLY if there's a price between prev_cost and world_price
        # where supply transitions smoothly (multiple regions/grades).
        prev_supply = sum(
            s.production_at_price(prev_cost)
            for s in self.regional_supplies.values()
        ) if prev_cost > price_lo else 0.0

        if prev_supply > 0 and prev_supply < total_demand and prev_cost < world_price:
            lo = prev_cost
            hi = world_price
            best_price = world_price
            for _ in range(TRADE_MAX_ITER):
                mid = (lo + hi) / 2.0
                excess = self._global_excess_supply(mid, regional_demands)
                if abs(excess) < TRADE_PRICE_TOL * total_demand:
                    best_price = mid
                    break
                if excess > 0:
                    hi = mid
                else:
                    lo = mid
            else:
                best_price = (lo + hi) / 2.0
            # Only use bisection result if it yields enough supply
            bisect_supply = sum(
                s.production_at_price(best_price)
                for s in self.regional_supplies.values()
            )
            if bisect_supply >= total_demand:
                world_price = best_price

        # Compute supply capacity at clearing price per region
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
            results[fuel] = self._markets[fuel].clear_market(demands)
        return results

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
