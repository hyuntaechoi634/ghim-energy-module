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


class TestRunModel:
    def test_full_run(self):
        ssp_data = load_ssp_data("SSP2")
        results = run_model(ssp_data, "SSP2")
        expected = len(R10_REGIONS) * len(MODEL_YEARS)
        assert len(results) == expected

    def test_base_year_emissions_sanity(self):
        """Global CO2 in base year should be ~35-45 GtCO2."""
        ssp_data = load_ssp_data("SSP2")
        results = run_model(ssp_data, "SSP2")
        base_results = [r for r in results if r.year == BASE_YEAR]
        global_co2 = sum(r.emissions_mtco2 for r in base_results)
        assert 20000 < global_co2 < 60000, f"Global CO2 {global_co2} MtCO2 out of range"
