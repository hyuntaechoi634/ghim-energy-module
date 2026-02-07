"""Tests for inter-regional primary energy trade module."""

import pytest
import numpy as np

from ghim.energy.supply import ResourceSupply, ResourceGrade
from ghim.energy.trade import GlobalMarket, TradeModule, TradeResult
from ghim.config import TRADED_FUELS, TRADE_PRICE_TOL
from ghim.regions import R10_REGIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _simple_supply(fuel: str, grades: list[tuple[float, float]]) -> ResourceSupply:
    """Helper: create a ResourceSupply from (available, cost) tuples."""
    return ResourceSupply(fuel, [ResourceGrade(a, c) for a, c in grades])


@pytest.fixture
def two_region_supplies():
    """Two regions: 'A' is cheap producer, 'B' is expensive."""
    return {
        "A": _simple_supply("oil", [(100.0, 2.0), (200.0, 5.0), (100.0, 10.0)]),
        "B": _simple_supply("oil", [(50.0, 8.0), (50.0, 15.0)]),
    }


@pytest.fixture
def two_region_transport():
    return {"A": 0.5, "B": 1.0}


# ---------------------------------------------------------------------------
# ResourceSupply.production_at_price()
# ---------------------------------------------------------------------------

class TestProductionAtPrice:
    def test_below_all_grades(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        assert supply.production_at_price(1.0) == 0.0

    def test_above_all_grades(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        assert supply.production_at_price(10.0) == 300.0

    def test_between_grades(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        assert supply.production_at_price(3.0) == 100.0

    def test_at_grade_cost(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        assert supply.production_at_price(5.0) == 300.0

    def test_with_partial_depletion(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        supply.cumulative_extracted = 50.0
        assert supply.production_at_price(10.0) == 250.0

    def test_with_full_depletion_of_first_grade(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        supply.cumulative_extracted = 100.0
        assert supply.production_at_price(3.0) == 0.0  # only grade 1 is cheap enough, but depleted
        assert supply.production_at_price(10.0) == 200.0


# ---------------------------------------------------------------------------
# GlobalMarket
# ---------------------------------------------------------------------------

class TestGlobalMarket:
    def test_clears_market(self, two_region_supplies, two_region_transport):
        market = GlobalMarket("oil", two_region_supplies, two_region_transport)
        demands = {"A": 80.0, "B": 30.0}
        result = market.clear_market(demands)

        assert isinstance(result, TradeResult)
        assert result.fuel == "oil"
        assert result.world_price > 0

        # Global balance: total production should approximately equal total demand
        total_prod = sum(result.regional_production.values())
        total_dem = sum(result.regional_demand.values())
        assert abs(total_prod - total_dem) < TRADE_PRICE_TOL * total_dem * 2

    def test_net_exports_sum_to_zero(self, two_region_supplies, two_region_transport):
        market = GlobalMarket("oil", two_region_supplies, two_region_transport)
        demands = {"A": 50.0, "B": 60.0}
        result = market.clear_market(demands)

        # Net exports should sum approximately to zero globally
        net_sum = sum(result.net_exports.values())
        total_dem = sum(demands.values())
        assert abs(net_sum) < TRADE_PRICE_TOL * total_dem * 5

    def test_cheap_region_is_exporter(self, two_region_supplies, two_region_transport):
        market = GlobalMarket("oil", two_region_supplies, two_region_transport)
        # Region A has cheap oil, B has expensive — A should export
        demands = {"A": 50.0, "B": 60.0}
        result = market.clear_market(demands)

        assert result.net_exports["A"] > 0  # A is net exporter
        assert result.net_exports["B"] < 0  # B is net importer

    def test_zero_demand(self, two_region_supplies, two_region_transport):
        market = GlobalMarket("oil", two_region_supplies, two_region_transport)
        demands = {"A": 0.0, "B": 0.0}
        result = market.clear_market(demands)
        assert result.world_price >= 0
        assert all(v == 0.0 for v in result.net_exports.values())

    def test_price_between_bounds(self, two_region_supplies, two_region_transport):
        market = GlobalMarket("oil", two_region_supplies, two_region_transport)
        demands = {"A": 80.0, "B": 30.0}
        result = market.clear_market(demands)
        assert 0.1 <= result.world_price <= 50.0


# ---------------------------------------------------------------------------
# TradeModule
# ---------------------------------------------------------------------------

class TestTradeModule:
    def _make_module(self):
        """Build a TradeModule with simple 3-region setup."""
        supplies = {
            "R1": {"coal": _simple_supply("coal", [(500.0, 1.0), (500.0, 3.0)]),
                    "oil": _simple_supply("oil", [(200.0, 3.0), (200.0, 8.0)]),
                    "gas": _simple_supply("gas", [(300.0, 2.0), (300.0, 5.0)])},
            "R2": {"coal": _simple_supply("coal", [(100.0, 2.0), (100.0, 5.0)]),
                    "oil": _simple_supply("oil", [(500.0, 2.0), (500.0, 6.0)]),
                    "gas": _simple_supply("gas", [(100.0, 3.0), (100.0, 7.0)])},
        }
        transport = {
            "coal": {"R1": 0.3, "R2": 0.5},
            "oil": {"R1": 0.3, "R2": 0.2},
            "gas": {"R1": 0.5, "R2": 0.8},
        }
        # Patch R10_REGIONS for this test
        return TradeModule(supplies, transport, enabled=True)

    def test_solve_returns_dict(self):
        tm = self._make_module()
        demands = {
            "R1": {"coal": 100.0, "oil": 50.0, "gas": 80.0},
            "R2": {"coal": 50.0, "oil": 100.0, "gas": 30.0},
        }
        results = tm.solve_trade(demands)
        assert results is not None
        for fuel in TRADED_FUELS:
            assert fuel in results
            assert isinstance(results[fuel], TradeResult)

    def test_disabled_returns_none(self):
        tm = self._make_module()
        tm.enabled = False
        results = tm.solve_trade({"R1": {"coal": 10.0}})
        assert results is None

    def test_delivered_prices_positive(self):
        tm = self._make_module()
        demands = {
            "R1": {"coal": 100.0, "oil": 50.0, "gas": 80.0},
            "R2": {"coal": 50.0, "oil": 100.0, "gas": 30.0},
        }
        results = tm.solve_trade(demands)
        dp = tm.delivered_prices(results, "R1")
        for fuel in TRADED_FUELS:
            assert dp[fuel] > 0
            # Delivered price = world_price + transport > world_price
            assert dp[fuel] > results[fuel].world_price


# ---------------------------------------------------------------------------
# Trade data loading (integration)
# ---------------------------------------------------------------------------

class TestTradeCal:
    def test_load_fossil_curves_r10(self):
        from ghim.data.trade_cal import load_fossil_curves_r10
        df = load_fossil_curves_r10()
        assert len(df) > 0
        assert set(df.columns) >= {"r10", "fuel", "available", "extractioncost"}
        # All R10 regions should have some data
        regions_in_data = set(df["r10"].unique())
        for r in R10_REGIONS:
            assert r in regions_in_data, f"Missing region: {r}"

    def test_costs_converted_to_2020_dollars(self):
        from ghim.data.trade_cal import load_fossil_curves_r10
        from ghim.config import GCAM3_TO_2020_DEFLATOR
        df = load_fossil_curves_r10()
        # All costs should be > 0.3 (the deflator is ~3.56x)
        assert df["extractioncost"].min() > 0.3

    def test_build_regional_supplies(self):
        from ghim.data.trade_cal import build_regional_supplies
        supplies = build_regional_supplies()
        assert len(supplies) == len(R10_REGIONS)
        for region in R10_REGIONS:
            assert region in supplies
            for fuel in ["coal", "oil", "gas"]:
                assert fuel in supplies[region]
                s = supplies[region][fuel]
                assert isinstance(s, ResourceSupply)
                assert len(s.grades) > 0

    def test_middle_east_has_large_oil(self):
        from ghim.data.trade_cal import build_regional_supplies
        supplies = build_regional_supplies()
        me_oil = supplies["Middle East"]["oil"]
        total_oil = sum(g.available for g in me_oil.grades)
        # Middle East should have large oil resources
        assert total_oil > 1000, f"Middle East oil too small: {total_oil} EJ"

    def test_eurasia_has_large_gas(self):
        from ghim.data.trade_cal import build_regional_supplies
        supplies = build_regional_supplies()
        gas = supplies["Eurasia"]["gas"]
        total = sum(g.available for g in gas.grades)
        assert total > 1000, f"Eurasia gas too small: {total} EJ"

    def test_transport_costs(self):
        from ghim.data.trade_cal import default_transport_costs
        tc = default_transport_costs()
        for fuel in ["coal", "oil", "gas"]:
            assert fuel in tc
            for region in R10_REGIONS:
                assert region in tc[fuel]
                assert tc[fuel][region] > 0


# ---------------------------------------------------------------------------
# Solver integration with trade
# ---------------------------------------------------------------------------

class TestSolverTradeIntegration:
    @pytest.fixture(autouse=True)
    def setup(self):
        from ghim.data.ssp import load_ssp_data
        self.ssp_data = load_ssp_data("SSP2")

    def test_run_model_with_trade(self):
        from ghim.solver.recursive import run_model
        results = run_model(self.ssp_data, "SSP2", trade_enabled=True)
        assert len(results) > 0
        # Check that trade fields are populated
        first = results[0]
        assert hasattr(first, "world_prices")
        assert hasattr(first, "net_exports_ej")
        assert hasattr(first, "domestic_production_ej")

    def test_run_model_without_trade(self):
        from ghim.solver.recursive import run_model
        results = run_model(self.ssp_data, "SSP2", trade_enabled=False)
        assert len(results) > 0
        # Trade fields should be empty dicts
        first = results[0]
        assert first.world_prices == {}
        assert first.net_exports_ej == {}

    def test_world_prices_populated(self):
        from ghim.solver.recursive import run_model
        results = run_model(self.ssp_data, "SSP2", trade_enabled=True)
        # Pick a future year result
        future_results = [r for r in results if r.year == 2050]
        assert len(future_results) > 0
        for r in future_results:
            for fuel in TRADED_FUELS:
                assert fuel in r.world_prices
                assert r.world_prices[fuel] > 0

    def test_global_net_exports_balance(self):
        """Net exports across all regions should sum to ~0 for each fuel at base year."""
        from ghim.solver.recursive import run_model
        results = run_model(self.ssp_data, "SSP2", trade_enabled=True)
        # Check base year (2020) where demand estimates are most accurate
        year_results = [r for r in results if r.year == 2020]
        assert len(year_results) > 0
        for fuel in TRADED_FUELS:
            net_sum = sum(r.net_exports_ej.get(fuel, 0.0) for r in year_results)
            total_prod = sum(r.domestic_production_ej.get(fuel, 0.0) for r in year_results)
            if total_prod > 0:
                # Net exports should approximately balance (within 10% of production)
                assert abs(net_sum) < total_prod * 0.10, \
                    f"Net exports for {fuel} in 2020 don't balance: {net_sum:.2f} EJ"

    def test_middle_east_exports_oil(self):
        """Middle East should be a net oil exporter."""
        from ghim.solver.recursive import run_model
        results = run_model(self.ssp_data, "SSP2", trade_enabled=True)
        me_2020 = [r for r in results if r.year == 2020 and r.region == "Middle East"]
        assert len(me_2020) == 1
        assert me_2020[0].net_exports_ej.get("oil", 0.0) > 0, \
            "Middle East should be a net oil exporter"

    def test_trade_prices_in_reasonable_range(self):
        """World prices should be in a reasonable range."""
        from ghim.solver.recursive import run_model
        results = run_model(self.ssp_data, "SSP2", trade_enabled=True)
        for r in results:
            if r.world_prices:
                for fuel, price in r.world_prices.items():
                    assert 0.1 <= price <= 50.0, \
                        f"World price for {fuel} in {r.year}: {price} $/GJ out of range"
