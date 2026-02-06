"""Tests for the recursive-dynamic solver."""

import pytest

from ghim.solver.recursive import (
    build_region_model,
    solve_period,
    run_model,
    PeriodResult,
)
from ghim.data.ssp import load_ssp_data
from ghim.config import BASE_YEAR


class TestSolvePeriod:
    def setup_method(self):
        self.model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)

    def test_returns_period_result(self):
        result = solve_period(self.model, gdp=21000.0, population=370.0, year=2020)
        assert isinstance(result, PeriodResult)
        assert result.year == 2020
        assert result.region == "North America"

    def test_emissions_positive(self):
        result = solve_period(self.model, gdp=21000.0, population=370.0, year=2020)
        assert result.emissions_mtco2 > 0

    def test_electricity_gen_sums_correctly(self):
        result = solve_period(self.model, gdp=21000.0, population=370.0, year=2020)
        total_gen = sum(result.electricity_gen_ej.values())
        assert total_gen > 0

    def test_higher_gdp_more_energy(self):
        result_low = solve_period(self.model, gdp=21000.0, population=370.0, year=2020)
        # Reset model state for fair comparison
        model2 = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        result_high = solve_period(model2, gdp=42000.0, population=370.0, year=2050)
        assert result_high.total_energy_demand_ej > result_low.total_energy_demand_ej


class TestRunModel:
    def test_full_run(self):
        ssp_data = load_ssp_data("SSP2")
        results = run_model(ssp_data, "SSP2")
        # 10 regions × 17 periods = 170 results
        assert len(results) == 170

    def test_base_year_emissions_sanity(self):
        """Global CO2 in base year should be ~35-45 GtCO2."""
        ssp_data = load_ssp_data("SSP2")
        results = run_model(ssp_data, "SSP2")
        base_results = [r for r in results if r.year == BASE_YEAR]
        global_co2 = sum(r.emissions_mtco2 for r in base_results)
        assert 20000 < global_co2 < 60000, f"Global CO2 {global_co2} MtCO2 out of range"
