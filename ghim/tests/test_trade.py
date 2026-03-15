"""Tests for inter-regional primary energy trade module."""

import pytest
import numpy as np

from ghim.energy.supply import ResourceSupply, ResourceGrade
from ghim.energy.trade import GlobalMarket, TradeModule, TradeResult
from ghim.core.config import TRADED_FUELS
from ghim.config import TRADE_PRICE_TOL
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
        # Piecewise-linear from 0: grade 0 interpolated 100*(1.0-0)/(2.0-0) = 50.0
        assert supply.production_at_price(1.0) == pytest.approx(50.0, rel=1e-3)

    def test_above_all_grades(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        assert supply.production_at_price(10.0) == 300.0

    def test_between_grades(self):
        supply = _simple_supply("coal", [(100.0, 2.0), (200.0, 5.0)])
        # Piecewise-linear: grade 0 full (100) + grade 1 interpolated 200*(3-2)/(5-2)
        assert supply.production_at_price(3.0) == pytest.approx(166.667, rel=1e-3)

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
        # Grade 0 depleted (remaining=0); grade 1 interpolated: 200*(3-2)/(5-2)
        assert supply.production_at_price(3.0) == pytest.approx(66.667, rel=1e-3)
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
# Calibration Rent
# ---------------------------------------------------------------------------

class TestCalibrationRent:
    def _make_module(self):
        """Build a TradeModule with simple supplies."""
        supplies = {
            "R1": {"coal": _simple_supply("coal", [(500.0, 1.0), (500.0, 3.0)]),
                    "oil": _simple_supply("oil", [(200.0, 3.0), (200.0, 8.0)]),
                    "gas": _simple_supply("gas", [(300.0, 2.0), (300.0, 5.0)])},
        }
        transport = {
            "coal": {"R1": 0.3},
            "oil": {"R1": 0.3},
            "gas": {"R1": 0.5},
        }
        return TradeModule(supplies, transport, enabled=True)

    def test_rent_computation(self):
        """Rent = max(0, observed - cleared)."""
        tm = self._make_module()
        # Fake trade results with low cleared prices
        results = {
            "coal": TradeResult("coal", 1.5, {}, {}, {}),
            "oil": TradeResult("oil", 2.0, {}, {}, {}),
            "gas": TradeResult("gas", 2.5, {}, {}, {}),
        }
        observed = {"coal": 1.75, "oil": 6.76, "gas": 3.85}
        tm.calibrate_rents(results, observed)

        assert tm.calibration_rents["coal"] == pytest.approx(0.25)
        assert tm.calibration_rents["oil"] == pytest.approx(4.76)
        assert tm.calibration_rents["gas"] == pytest.approx(1.35)

    def test_rent_zero_when_cleared_exceeds_observed(self):
        """Rent should be zero if cleared > observed."""
        tm = self._make_module()
        results = {
            "coal": TradeResult("coal", 5.0, {}, {}, {}),
            "oil": TradeResult("oil", 10.0, {}, {}, {}),
            "gas": TradeResult("gas", 8.0, {}, {}, {}),
        }
        observed = {"coal": 1.75, "oil": 6.76, "gas": 3.85}
        tm.calibrate_rents(results, observed)

        assert tm.calibration_rents["coal"] == 0.0
        assert tm.calibration_rents["oil"] == 0.0
        assert tm.calibration_rents["gas"] == 0.0

    def test_clearing_with_rent_includes_adder(self):
        """clear_market with price_adder should return world_price that includes the adder."""
        supplies = {
            "R1": _simple_supply("oil", [(200.0, 3.0), (200.0, 8.0)]),
        }
        market = GlobalMarket("oil", supplies, {"R1": 0.3})
        # Clear without adder
        result_no_adder = market.clear_market({"R1": 50.0})
        # Clear with adder
        adder = 4.0
        result_with_adder = market.clear_market({"R1": 50.0}, price_adder=adder)
        # World price with adder should be higher by approximately the adder
        # (not exactly, because bisection finds different extraction-cost price)
        assert result_with_adder.world_price > result_no_adder.world_price
        # The difference should be close to the adder (within ~1 $/GJ for
        # this simple case where demand is well within first grade capacity)
        diff = result_with_adder.world_price - result_no_adder.world_price
        assert diff == pytest.approx(adder, abs=1.0)

    def test_clearing_with_rent_allocates_correctly(self):
        """Regions with grades below clearing+rent should produce (not get zero)."""
        # Region A has cheap oil (grade at 2.0), region B has expensive (grade at 6.0)
        supplies = {
            "A": _simple_supply("oil", [(100.0, 2.0), (100.0, 5.0)]),
            "B": _simple_supply("oil", [(100.0, 6.0), (100.0, 10.0)]),
        }
        market = GlobalMarket("oil", supplies, {"A": 0.3, "B": 0.5})
        # Without adder at low demand, only A produces (clearing price < 6.0)
        result_no_adder = market.clear_market({"A": 30.0, "B": 20.0})
        # With adder, supply evaluated at higher price → B also produces
        adder = 5.0
        result_with_adder = market.clear_market({"A": 30.0, "B": 20.0}, price_adder=adder)
        # B should have positive production with adder
        assert result_with_adder.regional_production["B"] > 0

    def test_calibrate_only_once(self):
        """calibrate_rents should not overwrite if already set."""
        tm = self._make_module()
        results1 = {
            "coal": TradeResult("coal", 1.0, {}, {}, {}),
            "oil": TradeResult("oil", 2.0, {}, {}, {}),
            "gas": TradeResult("gas", 2.0, {}, {}, {}),
        }
        observed = {"coal": 1.75, "oil": 6.76, "gas": 3.85}
        tm.calibrate_rents(results1, observed)
        original_rents = dict(tm.calibration_rents)

        # Call again with different results — should be no-op
        results2 = {
            "coal": TradeResult("coal", 5.0, {}, {}, {}),
            "oil": TradeResult("oil", 10.0, {}, {}, {}),
            "gas": TradeResult("gas", 8.0, {}, {}, {}),
        }
        tm.calibrate_rents(results2, observed)
        assert tm.calibration_rents == original_rents


# ---------------------------------------------------------------------------
# Price Smoothing
# ---------------------------------------------------------------------------

class TestPriceSmoothing:
    def _make_module(self):
        supplies = {
            "R1": {"coal": _simple_supply("coal", [(500.0, 1.0)]),
                    "oil": _simple_supply("oil", [(200.0, 3.0)]),
                    "gas": _simple_supply("gas", [(300.0, 2.0)])},
        }
        transport = {"coal": {"R1": 0.3}, "oil": {"R1": 0.3}, "gas": {"R1": 0.5}}
        return TradeModule(supplies, transport, enabled=True)

    def test_clamps_upward_spike(self):
        """Prices rising more than max_change_rate should be clamped."""
        tm = self._make_module()
        tm.prev_world_prices = {"coal": 2.0, "oil": 6.0, "gas": 4.0}
        results = {
            "coal": TradeResult("coal", 10.0, {}, {}, {}),  # +400%
            "oil": TradeResult("oil", 20.0, {}, {}, {}),    # +233%
            "gas": TradeResult("gas", 12.0, {}, {}, {}),    # +200%
        }
        tm.smooth_prices(results, 0.30)

        assert results["coal"].world_price == pytest.approx(2.6)   # 2.0 * 1.3
        assert results["oil"].world_price == pytest.approx(7.8)    # 6.0 * 1.3
        assert results["gas"].world_price == pytest.approx(5.2)    # 4.0 * 1.3

    def test_clamps_downward_spike(self):
        """Prices dropping more than max_change_rate should be clamped."""
        tm = self._make_module()
        tm.prev_world_prices = {"coal": 5.0, "oil": 10.0, "gas": 8.0}
        results = {
            "coal": TradeResult("coal", 1.0, {}, {}, {}),
            "oil": TradeResult("oil", 2.0, {}, {}, {}),
            "gas": TradeResult("gas", 1.0, {}, {}, {}),
        }
        tm.smooth_prices(results, 0.30)

        assert results["coal"].world_price == pytest.approx(3.5)   # 5.0 * 0.7
        assert results["oil"].world_price == pytest.approx(7.0)    # 10.0 * 0.7
        assert results["gas"].world_price == pytest.approx(5.6)    # 8.0 * 0.7

    def test_no_op_within_bounds(self):
        """Prices within max_change_rate should pass through unchanged."""
        tm = self._make_module()
        tm.prev_world_prices = {"coal": 2.0, "oil": 6.0, "gas": 4.0}
        results = {
            "coal": TradeResult("coal", 2.1, {}, {}, {}),   # +5%
            "oil": TradeResult("oil", 5.8, {}, {}, {}),     # -3%
            "gas": TradeResult("gas", 4.5, {}, {}, {}),     # +12.5%
        }
        tm.smooth_prices(results, 0.30)

        assert results["coal"].world_price == pytest.approx(2.1)
        assert results["oil"].world_price == pytest.approx(5.8)
        assert results["gas"].world_price == pytest.approx(4.5)

    def test_no_op_first_period(self):
        """When prev_world_prices is empty, smoothing should be a no-op."""
        tm = self._make_module()
        assert tm.prev_world_prices == {}
        results = {
            "coal": TradeResult("coal", 10.0, {}, {}, {}),
            "oil": TradeResult("oil", 20.0, {}, {}, {}),
            "gas": TradeResult("gas", 15.0, {}, {}, {}),
        }
        tm.smooth_prices(results, 0.30)

        assert results["coal"].world_price == 10.0
        assert results["oil"].world_price == 20.0
        assert results["gas"].world_price == 15.0

    def test_record_world_prices(self):
        """record_world_prices should store current prices."""
        tm = self._make_module()
        results = {
            "coal": TradeResult("coal", 2.5, {}, {}, {}),
            "oil": TradeResult("oil", 7.0, {}, {}, {}),
            "gas": TradeResult("gas", 4.5, {}, {}, {}),
        }
        tm.record_world_prices(results)
        assert tm.prev_world_prices == {"coal": 2.5, "oil": 7.0, "gas": 4.5}




# ---------------------------------------------------------------------------
# Production Smoothing
# ---------------------------------------------------------------------------

class TestProductionSmoothing:
    def _make_module(self):
        supplies = {
            "A": {"oil": _simple_supply("oil", [(500.0, 2.0), (500.0, 5.0)])},
            "B": {"oil": _simple_supply("oil", [(500.0, 3.0), (500.0, 7.0)])},
        }
        transport = {"oil": {"A": 0.3, "B": 0.5}}
        return TradeModule(supplies, transport, enabled=True)

    def test_clamps_production_decline(self):
        """Region A drops from 100→0, should be floored at 70; B reduced to compensate."""
        tm = self._make_module()
        tm.prev_regional_production = {"oil": {"A": 100.0, "B": 50.0}}
        results = {
            "oil": TradeResult(
                "oil", 5.0,
                regional_production={"A": 0.0, "B": 150.0},
                regional_demand={"A": 50.0, "B": 100.0},
                net_exports={"A": -50.0, "B": 50.0},
            ),
        }
        tm.smooth_production(results, 0.30)

        # A floored at 100 * 0.7 = 70
        assert results["oil"].regional_production["A"] == pytest.approx(70.0)
        # B reduced: 150 - 70 = 80
        assert results["oil"].regional_production["B"] == pytest.approx(80.0)
        # Net exports recomputed
        assert results["oil"].net_exports["A"] == pytest.approx(70.0 - 50.0)
        assert results["oil"].net_exports["B"] == pytest.approx(80.0 - 100.0)

    def test_no_op_within_bounds(self):
        """Decline within 30% passes through unchanged."""
        tm = self._make_module()
        tm.prev_regional_production = {"oil": {"A": 100.0, "B": 50.0}}
        results = {
            "oil": TradeResult(
                "oil", 5.0,
                regional_production={"A": 80.0, "B": 40.0},
                regional_demand={"A": 60.0, "B": 60.0},
                net_exports={"A": 20.0, "B": -20.0},
            ),
        }
        tm.smooth_production(results, 0.30)

        assert results["oil"].regional_production["A"] == pytest.approx(80.0)
        assert results["oil"].regional_production["B"] == pytest.approx(40.0)

    def test_no_op_first_period(self):
        """Empty prev_regional_production → no-op."""
        tm = self._make_module()
        assert tm.prev_regional_production == {}
        results = {
            "oil": TradeResult(
                "oil", 5.0,
                regional_production={"A": 0.0, "B": 150.0},
                regional_demand={"A": 50.0, "B": 100.0},
                net_exports={"A": -50.0, "B": 50.0},
            ),
        }
        tm.smooth_production(results, 0.30)
        # Should be unchanged
        assert results["oil"].regional_production["A"] == 0.0
        assert results["oil"].regional_production["B"] == 150.0

    def test_record_regional_production(self):
        """record_regional_production stores current production correctly."""
        tm = self._make_module()
        results = {
            "oil": TradeResult(
                "oil", 5.0,
                regional_production={"A": 80.0, "B": 120.0},
                regional_demand={"A": 100.0, "B": 100.0},
                net_exports={"A": -20.0, "B": 20.0},
            ),
        }
        tm.record_regional_production(results)
        assert tm.prev_regional_production["oil"] == {"A": 80.0, "B": 120.0}

    def test_growth_not_constrained(self):
        """300% growth should not be clamped."""
        tm = self._make_module()
        tm.prev_regional_production = {"oil": {"A": 10.0, "B": 50.0}}
        results = {
            "oil": TradeResult(
                "oil", 5.0,
                regional_production={"A": 40.0, "B": 60.0},
                regional_demand={"A": 50.0, "B": 50.0},
                net_exports={"A": -10.0, "B": 10.0},
            ),
        }
        tm.smooth_production(results, 0.30)
        # A grew 300% (10→40), should NOT be clamped
        assert results["oil"].regional_production["A"] == pytest.approx(40.0)
        assert results["oil"].regional_production["B"] == pytest.approx(60.0)
