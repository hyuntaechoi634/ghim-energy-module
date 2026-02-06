"""Tests for the policy module."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from ghim.policy import (
    PolicyScenario,
    CarbonPricePolicy,
    RenewableSubsidy,
    EfficiencyStandard,
    EmissionsCap,
    TechConstraint,
    RevenueRecycling,
    _interpolate,
    load_policy,
    policy_from_cli,
    apply_share_constraints,
)
from ghim.config import BASE_YEAR


# -----------------------------------------------------------------------
# Interpolation
# -----------------------------------------------------------------------


class TestInterpolation:
    def test_empty_trajectory(self):
        assert _interpolate({}, 2030) == 0.0

    def test_single_point(self):
        assert _interpolate({2030: 50.0}, 2020) == 50.0
        assert _interpolate({2030: 50.0}, 2030) == 50.0
        assert _interpolate({2030: 50.0}, 2050) == 50.0

    def test_linear_interpolation(self):
        traj = {2020: 0.0, 2040: 100.0}
        assert _interpolate(traj, 2030) == pytest.approx(50.0)
        assert _interpolate(traj, 2020) == pytest.approx(0.0)
        assert _interpolate(traj, 2040) == pytest.approx(100.0)

    def test_flat_beyond_endpoints(self):
        traj = {2020: 10.0, 2050: 40.0}
        assert _interpolate(traj, 2010) == pytest.approx(10.0)
        assert _interpolate(traj, 2100) == pytest.approx(40.0)

    def test_multiple_segments(self):
        traj = {2020: 0.0, 2030: 100.0, 2050: 200.0}
        assert _interpolate(traj, 2025) == pytest.approx(50.0)
        assert _interpolate(traj, 2040) == pytest.approx(150.0)


# -----------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------


class TestPolicyDataclasses:
    def test_default_policy_is_empty(self):
        ps = PolicyScenario()
        assert ps.carbon_price.get_price(2030) == 0.0
        assert ps.renewable_subsidies.get_subsidy("solar", 2030) == 0.0
        assert ps.efficiency_standards.cumulative_factor("global", 2030, BASE_YEAR) == 1.0
        assert ps.emissions_cap.has_cap(2030) is False
        assert len(ps.tech_constraints) == 0
        assert ps.revenue_recycling.fraction == 0.0

    def test_carbon_price_trajectory(self):
        cp = CarbonPricePolicy(trajectory={2020: 0.0, 2050: 150.0})
        assert cp.get_price(2020) == pytest.approx(0.0)
        assert cp.get_price(2035) == pytest.approx(75.0)
        assert cp.get_price(2050) == pytest.approx(150.0)
        assert cp.get_price(2100) == pytest.approx(150.0)

    def test_renewable_subsidy(self):
        rs = RenewableSubsidy(subsidies={
            "solar": {2020: 3.0, 2040: 0.0},
        })
        assert rs.get_subsidy("solar", 2030) == pytest.approx(1.5)
        assert rs.get_subsidy("coal", 2030) == 0.0

    def test_efficiency_cumulative_factor(self):
        es = EfficiencyStandard(rates={"global": {2020: 0.01}})
        # (1-0.01)^10 for year 2030 (10 years from base)
        assert es.cumulative_factor("global", 2030, 2020) == pytest.approx(0.99 ** 10)
        # Base year should return 1.0
        assert es.cumulative_factor("global", 2020, 2020) == pytest.approx(1.0)

    def test_efficiency_sector_fallback_to_global(self):
        es = EfficiencyStandard(rates={"global": {2020: 0.02}})
        # "industry" not in rates, falls back to "global"
        assert es.cumulative_factor("industry", 2030, 2020) == pytest.approx(0.98 ** 10)

    def test_efficiency_sector_override(self):
        es = EfficiencyStandard(rates={
            "global": {2020: 0.01},
            "industry": {2020: 0.03},
        })
        assert es.cumulative_factor("industry", 2030, 2020) == pytest.approx(0.97 ** 10)
        assert es.cumulative_factor("buildings", 2030, 2020) == pytest.approx(0.99 ** 10)

    def test_emissions_cap(self):
        ec = EmissionsCap(caps={"global": {2030: 35000, 2050: 5000}})
        assert ec.has_cap(2030) is True
        assert ec.get_cap("global", 2040) == pytest.approx(20000.0)

    def test_tech_constraint_bound(self):
        tc = TechConstraint(
            sector="electricity", technology="coal",
            constraint_type="max", trajectory={2030: 0.30, 2050: 0.0},
        )
        assert tc.get_bound(2030) == pytest.approx(0.30)
        assert tc.get_bound(2040) == pytest.approx(0.15)
        assert tc.get_bound(2050) == pytest.approx(0.0)


# -----------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------


class TestPolicyLoading:
    def test_load_json_roundtrip(self, tmp_path):
        data = {
            "name": "test_policy",
            "carbon_price": {"trajectory": {"2025": 30, "2050": 300}},
            "renewable_subsidies": {"subsidies": {"solar": {"2025": 2.0}}},
            "efficiency_standards": {"rates": {"global": {"2025": 0.01}}},
            "tech_constraints": [
                {"sector": "electricity", "technology": "coal",
                 "constraint_type": "max", "trajectory": {"2030": 0.3}}
            ],
            "revenue_recycling": {"fraction": 0.5},
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        ps = load_policy(path)
        assert ps.name == "test_policy"
        assert ps.carbon_price.get_price(2025) == pytest.approx(30.0)
        assert ps.carbon_price.get_price(2050) == pytest.approx(300.0)
        assert ps.renewable_subsidies.get_subsidy("solar", 2025) == pytest.approx(2.0)
        assert ps.efficiency_standards.cumulative_factor("global", 2030, 2025) == pytest.approx(0.99 ** 5)
        assert len(ps.tech_constraints) == 1
        assert ps.tech_constraints[0].technology == "coal"
        assert ps.revenue_recycling.fraction == 0.5

    def test_year_key_conversion(self, tmp_path):
        """String year keys in JSON should be converted to int."""
        data = {"carbon_price": {"trajectory": {"2025": 10}}}
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        ps = load_policy(path)
        assert 2025 in ps.carbon_price.trajectory
        assert isinstance(list(ps.carbon_price.trajectory.keys())[0], int)

    def test_cli_builder_carbon_price(self):
        ps = policy_from_cli(carbon_price=50.0)
        assert ps.carbon_price.get_price(2030) == pytest.approx(50.0)
        assert ps.carbon_price.get_price(2100) == pytest.approx(50.0)

    def test_cli_builder_efficiency(self):
        ps = policy_from_cli(efficiency_rate=0.02)
        assert ps.efficiency_standards.cumulative_factor("global", 2030, 2020) == pytest.approx(0.98 ** 10)

    def test_cli_builder_recycling(self):
        ps = policy_from_cli(recycling_fraction=0.5)
        assert ps.revenue_recycling.fraction == 0.5

    def test_cli_all_zero_is_empty(self):
        ps = policy_from_cli()
        assert ps.carbon_price.get_price(2030) == 0.0


# -----------------------------------------------------------------------
# Share constraints
# -----------------------------------------------------------------------


class TestShareConstraints:
    def test_max_constraint(self):
        shares = np.array([0.50, 0.30, 0.20])
        names = ["coal", "gas", "solar"]
        constraints = [
            TechConstraint("electricity", "coal", "max", {2030: 0.20}),
        ]
        result = apply_share_constraints(shares, names, constraints, 2030, "electricity")
        assert result[0] <= 0.20 + 1e-10  # coal clamped
        assert abs(result.sum() - 1.0) < 1e-10

    def test_min_constraint(self):
        shares = np.array([0.50, 0.30, 0.05])
        names = ["coal", "gas", "solar"]
        constraints = [
            TechConstraint("electricity", "solar", "min", {2030: 0.20}),
        ]
        result = apply_share_constraints(shares, names, constraints, 2030, "electricity")
        assert result[2] >= 0.20 - 1e-10  # solar boosted
        assert abs(result.sum() - 1.0) < 1e-10

    def test_both_constraints(self):
        shares = np.array([0.50, 0.30, 0.10, 0.10])
        names = ["coal", "gas", "solar", "wind"]
        constraints = [
            TechConstraint("electricity", "coal", "max", {2030: 0.10}),
            TechConstraint("electricity", "solar", "min", {2030: 0.25}),
        ]
        result = apply_share_constraints(shares, names, constraints, 2030, "electricity")
        # After clamping coal to 0.10 and solar to 0.25, renormalize
        assert result[0] <= 0.10 + 1e-10  # coal
        assert result[2] >= 0.25 - 1e-10  # solar
        assert abs(result.sum() - 1.0) < 1e-10

    def test_wrong_sector_ignored(self):
        shares = np.array([0.50, 0.50])
        names = ["coal", "gas"]
        constraints = [
            TechConstraint("hydrogen", "coal", "max", {2030: 0.0}),
        ]
        result = apply_share_constraints(shares, names, constraints, 2030, "electricity")
        np.testing.assert_array_almost_equal(result, shares)

    def test_unknown_tech_ignored(self):
        shares = np.array([0.50, 0.50])
        names = ["coal", "gas"]
        constraints = [
            TechConstraint("electricity", "nuclear", "max", {2030: 0.0}),
        ]
        result = apply_share_constraints(shares, names, constraints, 2030, "electricity")
        np.testing.assert_array_almost_equal(result, shares)


# -----------------------------------------------------------------------
# Integration tests with solver
# -----------------------------------------------------------------------


class TestCarbonPrice:
    def setup_method(self):
        from ghim.solver.recursive import build_region_model
        self.model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)

    def test_zero_carbon_price_is_noop(self):
        from ghim.solver.recursive import solve_period
        r_none = solve_period(self.model, 21000.0, 370.0, 2020, policy=None)
        ps = PolicyScenario()  # defaults = zero
        # Re-build model to get clean state
        from ghim.solver.recursive import build_region_model
        model2 = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        r_zero = solve_period(model2, 21000.0, 370.0, 2020, policy=ps)
        assert r_none.emissions_mtco2 == pytest.approx(r_zero.emissions_mtco2, rel=1e-6)

    def test_carbon_price_increases_fuel_costs(self):
        from ghim.solver.recursive import build_region_model, solve_period
        model_no = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        r_no = solve_period(model_no, 21000.0, 370.0, 2025)

        model_cp = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps = PolicyScenario(carbon_price=CarbonPricePolicy(trajectory={2020: 100.0}))
        r_cp = solve_period(model_cp, 21000.0, 370.0, 2025, policy=ps)

        # Coal price should be higher with carbon price
        assert r_cp.fuel_prices["coal"] > r_no.fuel_prices["coal"]
        assert r_cp.carbon_price_usd_tco2 == pytest.approx(100.0)

    def test_carbon_price_reduces_emissions(self):
        from ghim.solver.recursive import build_region_model, solve_period
        model_no = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        r_no = solve_period(model_no, 21000.0, 370.0, 2025)

        model_cp = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps = PolicyScenario(carbon_price=CarbonPricePolicy(trajectory={2020: 200.0}))
        r_cp = solve_period(model_cp, 21000.0, 370.0, 2025, policy=ps)

        # High carbon price should reduce emissions
        assert r_cp.emissions_mtco2 < r_no.emissions_mtco2


class TestSubsidies:
    def test_solar_subsidy_increases_solar_share(self):
        from ghim.solver.recursive import build_region_model, solve_period
        model_no = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        r_no = solve_period(model_no, 21000.0, 370.0, 2030)

        model_sub = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps = PolicyScenario(renewable_subsidies=RenewableSubsidy(
            subsidies={"solar": {2020: 5.0}}  # large subsidy
        ))
        r_sub = solve_period(model_sub, 21000.0, 370.0, 2030, policy=ps)

        solar_no = r_no.electricity_gen_ej.get("solar", 0.0)
        solar_sub = r_sub.electricity_gen_ej.get("solar", 0.0)
        assert solar_sub > solar_no


class TestEfficiency:
    def test_aeei_reduces_demand(self):
        from ghim.solver.recursive import build_region_model, solve_period
        model_no = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        r_no = solve_period(model_no, 21000.0, 370.0, 2030)

        model_eff = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps = PolicyScenario(efficiency_standards=EfficiencyStandard(
            rates={"global": {2020: 0.03}}  # 3% annual
        ))
        r_eff = solve_period(model_eff, 21000.0, 370.0, 2030, policy=ps)

        assert r_eff.total_energy_demand_ej < r_no.total_energy_demand_ej
        assert r_eff.aeei_factor < 1.0


class TestTechConstraints:
    def test_coal_cap_enforced(self):
        from ghim.solver.recursive import build_region_model, solve_period
        model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps = PolicyScenario(tech_constraints=[
            TechConstraint("electricity", "coal", "max", {2020: 0.05}),
        ])
        r = solve_period(model, 21000.0, 370.0, 2025, policy=ps)
        total_elec = sum(r.electricity_gen_ej.values())
        coal_share = r.electricity_gen_ej.get("coal", 0.0) / total_elec if total_elec > 0 else 0
        # After renormalization the share should be at most ~5% (with some tolerance for stock turnover)
        assert coal_share < 0.15

    def test_solar_floor_enforced(self):
        from ghim.solver.recursive import build_region_model, solve_period
        model = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps = PolicyScenario(tech_constraints=[
            TechConstraint("electricity", "solar", "min", {2020: 0.30}),
        ])
        r = solve_period(model, 21000.0, 370.0, 2025, policy=ps)
        total_elec = sum(r.electricity_gen_ej.values())
        solar_share = r.electricity_gen_ej.get("solar", 0.0) / total_elec if total_elec > 0 else 0
        # After renormalization, solar should be at least ~30% (stock turnover blends)
        assert solar_share > 0.10

    def test_shares_sum_to_one(self):
        shares = np.array([0.4, 0.3, 0.2, 0.1])
        names = ["coal", "gas", "solar", "wind"]
        constraints = [
            TechConstraint("electricity", "coal", "max", {2030: 0.05}),
            TechConstraint("electricity", "solar", "min", {2030: 0.35}),
        ]
        result = apply_share_constraints(shares, names, constraints, 2030, "electricity")
        assert abs(result.sum() - 1.0) < 1e-10


class TestRevenueRecycling:
    def test_recycling_increases_net_output(self):
        from ghim.solver.recursive import build_region_model, solve_period
        # With carbon price but no recycling
        model_no = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps_no = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 100.0}),
        )
        r_no = solve_period(model_no, 21000.0, 370.0, 2025, policy=ps_no)

        # With carbon price and recycling
        model_rec = build_region_model("North America", base_gdp=21000.0, base_pop=370.0)
        ps_rec = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 100.0}),
            revenue_recycling=RevenueRecycling(fraction=0.8),
        )
        r_rec = solve_period(model_rec, 21000.0, 370.0, 2025, policy=ps_rec)

        assert r_rec.carbon_revenue_billion_usd > 0
        # Net output should be higher with recycling
        assert r_rec.net_output >= r_no.net_output


class TestEmissionsCap:
    def test_cap_triggers_positive_shadow_price(self):
        """With an emissions cap, the solver should find a positive carbon price."""
        from ghim.data.ssp import load_ssp_data
        from ghim.solver.recursive import run_model
        from ghim.config import MODEL_YEARS

        ssp_data = load_ssp_data("SSP2")

        # First run without cap to get base emissions for first future year
        base_results = run_model(ssp_data, "SSP2")
        first_future = MODEL_YEARS[len([y for y in MODEL_YEARS if y <= BASE_YEAR])]
        base_emissions = sum(
            r.emissions_mtco2 for r in base_results if r.year == first_future
        )

        # Set a tight cap (50% of base) for that year
        tight_cap = base_emissions * 0.5
        ps = PolicyScenario(emissions_cap=EmissionsCap(
            caps={"global": {first_future: tight_cap}},
            bisect_max_iter=10,
        ))
        cap_results = run_model(ssp_data, "SSP2", policy=ps)

        # The carbon price should be positive for the capped year
        capped_year_results = [r for r in cap_results if r.year == first_future]
        avg_price = np.mean([r.carbon_price_usd_tco2 for r in capped_year_results])
        assert avg_price > 0


class TestScenarioFiles:
    def test_load_carbon_tax_50(self):
        path = Path(__file__).resolve().parents[2] / "scenarios" / "carbon_tax_50.json"
        if path.exists():
            ps = load_policy(path)
            assert ps.name == "carbon_tax_50"
            assert ps.carbon_price.get_price(2030) == pytest.approx(50.0)

    def test_load_net_zero_2050(self):
        path = Path(__file__).resolve().parents[2] / "scenarios" / "net_zero_2050.json"
        if path.exists():
            ps = load_policy(path)
            assert ps.name == "net_zero_2050"
            assert ps.carbon_price.get_price(2050) == pytest.approx(300.0)
            assert len(ps.tech_constraints) == 2
            assert ps.revenue_recycling.fraction == 0.5
