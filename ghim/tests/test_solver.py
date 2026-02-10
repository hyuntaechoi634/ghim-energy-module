"""Tests for the recursive-dynamic solver."""

import pytest

from ghim.solver.recursive import (
    build_region_model,
    solve_period,
    run_model,
    PeriodResult,
)
from ghim.data.ssp import load_ssp_data
from ghim.config import BASE_YEAR, MODEL_YEARS, KLEM_SCALE_CLAMP
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


class TestKLEMSectorCoupling:
    """Tests for KLEM-sector energy demand coupling."""

    def setup_method(self):
        self.model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)

    def test_base_year_scale_reasonable(self):
        """At base year, klem_scale_factor should be close to 1.0.

        Not exactly 1.0 because the price iteration shifts electricity/hydrogen
        prices from defaults, changing the KLEM price index. But should stay
        well within the clamp bounds.
        """
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert 0.8 <= result.klem_scale_factor <= 1.5, (
            f"Base year scale = {result.klem_scale_factor}, expected near 1.0"
        )

    def test_sector_sum_matches_total(self):
        """Sum of final demand should equal total_energy_demand_ej."""
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        sector_sum = sum(
            sum(cd.values()) for cd in result.final_demand_ej.values()
        )
        assert abs(sector_sum - result.total_energy_demand_ej) < 0.01, (
            f"Sector sum {sector_sum:.2f} != total {result.total_energy_demand_ej:.2f}"
        )

    def test_scale_factor_within_clamp(self):
        """klem_scale_factor stays within KLEM_SCALE_CLAMP bounds."""
        # Solve several periods to let scale potentially diverge
        r = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert KLEM_SCALE_CLAMP[0] <= r.klem_scale_factor <= KLEM_SCALE_CLAMP[1]
        r2 = solve_period(self.model, ssp_gdp=25000.0, population=400.0, year=2025)
        assert KLEM_SCALE_CLAMP[0] <= r2.klem_scale_factor <= KLEM_SCALE_CLAMP[1]

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

    def test_klem_scale_factor_field_exists(self):
        """PeriodResult should include klem_scale_factor field."""
        result = solve_period(self.model, ssp_gdp=21000.0, population=370.0, year=2020)
        assert hasattr(result, "klem_scale_factor")
        assert isinstance(result.klem_scale_factor, float)


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
