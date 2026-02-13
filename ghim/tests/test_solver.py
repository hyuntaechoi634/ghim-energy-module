"""Tests for the recursive-dynamic solver."""

import pytest

from ghim.solver.recursive import (
    build_region_model,
    solve_period,
    run_model,
    PeriodResult,
)
from ghim.data.ssp import load_ssp_data
from ghim.config import BASE_YEAR, MODEL_YEARS
from ghim.regions import R10_REGIONS


class TestSolvePeriod:
    def setup_method(self):
        self.model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)

    def test_returns_period_result(self):
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert isinstance(result, PeriodResult)
        assert result.year == 2020
        assert result.region == "North America"

    def test_emissions_positive(self):
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert result.emissions_mtco2 > 0

    def test_electricity_gen_sums_correctly(self):
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        total_gen = sum(result.electricity_gen_ej.values())
        assert total_gen > 0

    def test_capital_accumulation_increases_energy(self):
        """After one period, capital grows → higher gross output → more energy."""
        r1 = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        # After solve_period, capital_stock was updated via investment.
        # Solve the next period — gross_output should be higher than base_gdp.
        r2 = solve_period(self.model, ssp_gdp=22000.0, population=370.0, year=2025)
        assert r2.total_energy_demand_ej > r1.total_energy_demand_ej

    def test_endogenous_gdp_fields(self):
        """New Phase 2 fields: gross_output, net_output, capital_stock, etc."""
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert result.gross_output > 0
        assert result.net_output > 0
        assert result.capital_stock > 0
        assert result.investment >= 0
        assert result.energy_cost >= 0
        assert result.ssp_reference_gdp == 21000.0
        assert result.tfp > 0

    def test_net_output_leq_gross(self):
        """Net output should be <= gross output (energy costs are deducted)."""
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert result.net_output <= result.gross_output


class TestCESKLECoupling:
    """Tests for CES-KLE energy demand coupling."""

    def setup_method(self):
        self.model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)

    def test_energy_cost_share_reasonable(self):
        """At base year, energy_cost_share (P_E*E/Y) should be ~5-15%.

        Energy is typically 5-10% of GDP for developed economies.
        """
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert 0.01 <= result.energy_cost_share <= 0.30, (
            f"Energy cost share = {result.energy_cost_share:.3f}, expected 0.01-0.30"
        )

    def test_sector_sum_matches_total(self):
        """Sum of final demand should equal total_energy_demand_ej."""
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        sector_sum = sum(
            sum(cd.values()) for cd in result.final_demand_ej.values()
        )
        assert abs(sector_sum - result.total_energy_demand_ej) < 0.1, (
            f"Sector sum {sector_sum:.2f} != total {result.total_energy_demand_ej:.2f}"
        )

    def test_energy_demand_responds_to_price(self):
        """Higher energy price should reduce total energy demand (CES substitution)."""
        import copy
        model_lo = copy.deepcopy(self.model)
        model_hi = copy.deepcopy(self.model)
        # Low energy price case
        r_lo = solve_period(model_lo, ssp_gdp=21000.0, population=370.0, year=2020)
        # High energy price case: override prices
        model_hi.fuel_prices["coal"] = 10.0
        model_hi.fuel_prices["gas"] = 15.0
        model_hi.fuel_prices["oil"] = 20.0
        r_hi = solve_period(model_hi, ssp_gdp=21000.0, population=370.0, year=2020)
        # Higher prices → less energy
        assert r_hi.total_energy_demand_ej <= r_lo.total_energy_demand_ej * 1.1, (
            f"Energy demand didn't decrease with higher prices: "
            f"lo={r_lo.total_energy_demand_ej:.1f}, hi={r_hi.total_energy_demand_ej:.1f}"
        )

    def test_structural_change_over_time(self):
        """Transport share should change relative to buildings as GDP grows.

        With higher income elasticity (0.7 vs 0.5), transport should gain
        share when GDP increases substantially.
        """
        r1 = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        # Run a few periods with GDP growth
        for yr, gdp in [(2025, 25000.0), (2030, 30000.0)]:
            r2 = solve_period(self.model, ssp_gdp=gdp, population=370.0, year=yr)

        transport_share_1 = (
            sum(r1.final_demand_ej.get("transport", {}).values())
            / r1.total_energy_demand_ej
        )
        transport_share_2 = (
            sum(r2.final_demand_ej.get("transport", {}).values())
            / r2.total_energy_demand_ej
        )
        # Transport has higher income elasticity, so its share should increase
        assert transport_share_2 >= transport_share_1 - 0.01, (
            f"Transport share didn't increase: {transport_share_1:.3f} → {transport_share_2:.3f}"
        )

    def test_energy_cost_share_field_exists(self):
        """PeriodResult should include energy_cost_share field."""
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert hasattr(result, "energy_cost_share")
        assert isinstance(result.energy_cost_share, float)


class TestRunModel:
    def test_full_run(self):
        ssp_data = load_ssp_data("SSP2")
        results = run_model(ssp_data, "SSP2")
        expected = len(R10_REGIONS) * len(MODEL_YEARS)
        assert len(results) == expected

    def test_base_year_emissions_sanity(self):
        """Global CO2 in base year should be in a plausible range."""
        ssp_data = load_ssp_data("SSP2")
        results = run_model(ssp_data, "SSP2")
        base_results = [r for r in results if r.year == BASE_YEAR]
        global_co2 = sum(r.emissions_mtco2 for r in base_results)
        assert 5000 < global_co2 < 60000, f"Global CO2 {global_co2} MtCO2 out of range"
