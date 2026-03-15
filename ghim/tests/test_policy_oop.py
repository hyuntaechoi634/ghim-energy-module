"""Tests for Phase E: PolicyEngine wiring + EmissionsCapWrapper + OOP reporting.

Covers:
  - Carbon price wiring through F() and sectors
  - AEEI efficiency standards
  - Renewable subsidies affecting LCOE
  - Tech constraints (post-logit clamping)
  - EmissionsCapWrapper bisection
  - OOP reporting (DataFrame + IAMC)
"""

import pytest
import numpy as np

from ghim.core.config import BASE_YEAR
from ghim.core.carrier import Carrier
from ghim.core.state import PeriodState, RegionState
from ghim.model import GHIMModel
from ghim.solver.damped import DampedSolver
from ghim.adapters.base import (
    DefaultClimateAdapter,
    DefaultWaterAdapter,
    DefaultAFOLUAdapter,
)
from ghim.policy import (
    PolicyScenario,
    CarbonPricePolicy,
    EfficiencyStandard,
    RenewableSubsidy,
    TechConstraint,
    EmissionsCap,
    RevenueRecycling,
)


# ===================================================================
# Helpers
# ===================================================================

def _build_single_region_model(policy=None):
    """Build a single-region OOP model for testing."""
    from ghim.build import build_region
    region, rs = build_region("USA", 22000.0, 370.0)
    region.economy.init_tfp_trajectory(
        {BASE_YEAR: 22000.0, 2025: 23000.0, 2030: 24000.0},
        {BASE_YEAR: 370.0, 2025: 375.0, 2030: 380.0},
    )
    region.economy.set_tfp_for_year(2025)
    model = GHIMModel(
        regions={"USA": region},
        policy=policy,
        climate=DefaultClimateAdapter(),
        water=DefaultWaterAdapter(),
        afolu=DefaultAFOLUAdapter(),
    )
    state = PeriodState(
        period=2025,
        regions={"USA": rs},
        world_prices={"coal": 2.5, "oil": 8.0, "gas": 4.0},
    )
    return model, state


# ===================================================================
# Carbon Price
# ===================================================================

class TestCarbonPriceWiring:
    """Carbon price flows through F() to sectors and state."""

    def test_carbon_price_stored_on_region_state(self):
        policy = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 100.0}),
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        assert result.regions["USA"].carbon_price == 100.0

    def test_carbon_price_stored_on_period_state(self):
        policy = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 50.0}),
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        assert result.policy_carbon_price == 50.0

    def test_no_policy_carbon_price_zero(self):
        model, state = _build_single_region_model(None)
        result = model.F(state)
        assert result.regions["USA"].carbon_price == 0.0

    def test_carbon_price_reduces_emissions(self):
        model_no, state_no = _build_single_region_model(None)
        r_no = model_no.F(state_no)

        policy = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 200.0}),
        )
        model_cp, state_cp = _build_single_region_model(policy)
        r_cp = model_cp.F(state_cp)

        # Higher carbon price should reduce emissions (via demand + supply)
        assert r_cp.global_emissions < r_no.global_emissions

    def test_carbon_price_increases_electricity_price(self):
        model_no, state_no = _build_single_region_model(None)
        r_no = model_no.F(state_no)

        policy = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 100.0}),
        )
        model_cp, state_cp = _build_single_region_model(policy)
        r_cp = model_cp.F(state_cp)

        p_no = r_no.regions["USA"].carrier_prices.get(Carrier.ELECTRICITY, 0)
        p_cp = r_cp.regions["USA"].carrier_prices.get(Carrier.ELECTRICITY, 0)
        # Electricity price should increase due to carbon in LCOE
        assert p_cp > p_no

    def test_carbon_revenue_tracked(self):
        policy = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 50.0}),
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        rs = result.regions["USA"]
        # Revenue = τ × CO2_mt × 1e-3
        expected = 50.0 * rs.emissions_detail.co2 * 1e-3
        assert abs(rs.carbon_revenue - expected) < 0.01


# ===================================================================
# AEEI (Efficiency Standards)
# ===================================================================

class TestAEEI:
    """Efficiency standards reduce total energy demand."""

    def test_aeei_factor_stored(self):
        policy = PolicyScenario(
            efficiency_standards=EfficiencyStandard(
                rates={"global": {2020: 0.02}},  # 2% annual
            ),
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        rs = result.regions["USA"]
        # 2025 - 2021 = 4 years at 2%: (1-0.02)^4 ≈ 0.922
        assert 0.91 < rs.aeei_factor < 0.94

    def test_aeei_reduces_energy(self):
        model_no, state_no = _build_single_region_model(None)
        r_no = model_no.F(state_no)

        policy = PolicyScenario(
            efficiency_standards=EfficiencyStandard(
                rates={"global": {2020: 0.03}},  # 3% annual
            ),
        )
        model_aeei, state_aeei = _build_single_region_model(policy)
        r_aeei = model_aeei.F(state_aeei)

        e_no = sum(r_no.regions["USA"].final_demand.values())
        e_aeei = sum(r_aeei.regions["USA"].final_demand.values())
        assert e_aeei < e_no

    def test_no_aeei_factor_is_one(self):
        model, state = _build_single_region_model(None)
        result = model.F(state)
        assert result.regions["USA"].aeei_factor == 1.0


# ===================================================================
# Renewable Subsidies
# ===================================================================

class TestRenewableSubsidies:
    """Subsidies reduce LCOE and increase clean tech share."""

    def test_subsidy_reduces_effective_lcoe(self):
        """Subsidy directly reduces LCOE used in logit (target shares)."""
        from ghim.sectors.electricity import OOPElectricitySector

        elec = OOPElectricitySector(region="USA")
        fuel_prices = {
            "coal": 2.5, "gas": 4.0, "oil": 8.0,
            "refined liquids": 12.0, "nuclear": 0.7,
            "hydro": 0.0, "wind": 0.0, "solar": 0.0,
            "biomass": 3.0, "geothermal": 0.0, "uranium": 0.5,
            "h2": 15.0,
        }
        elec.calibrate({"coal": 0.3, "gas_cc": 0.3, "solar": 0.1}, fuel_prices,
                        total_generation_ej=5.0)

        # Compute supply without subsidy
        rs = RegionState(raw_fuel_prices=fuel_prices, carbon_price=0.0)
        rs._year = 2040
        gen_no = elec.compute_supply(rs, 5.0, policy=None)

        # Compute supply with solar subsidy — need fresh sector
        elec2 = OOPElectricitySector(region="USA")
        elec2.calibrate({"coal": 0.3, "gas_cc": 0.3, "solar": 0.1}, fuel_prices,
                         total_generation_ej=5.0)
        policy = PolicyScenario(
            renewable_subsidies=RenewableSubsidy(
                subsidies={"solar": {2020: 10.0}},
            ),
        )
        gen_sub = elec2.compute_supply(rs, 5.0, policy=policy)

        # Solar should get a larger share with subsidy
        assert gen_sub.get("solar", 0.0) > gen_no.get("solar", 0.0)


# ===================================================================
# Tech Constraints
# ===================================================================

class TestTechConstraints:
    """Post-logit share clamping."""

    def test_max_constraint_limits_share(self):
        policy = PolicyScenario(
            tech_constraints=[
                TechConstraint(
                    sector="electricity",
                    technology="coal",
                    constraint_type="max",
                    trajectory={2020: 0.10},  # max 10% coal
                ),
            ],
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        gen = result.regions["USA"].generation.get("electricity", {})
        total = sum(gen.values())
        if total > 0:
            coal_share = gen.get("coal", 0.0) / total
            assert coal_share <= 0.11  # within tolerance of 10%

    def test_min_constraint_ensures_minimum(self):
        policy = PolicyScenario(
            tech_constraints=[
                TechConstraint(
                    sector="electricity",
                    technology="wind",
                    constraint_type="min",
                    trajectory={2020: 0.20},  # min 20% wind
                ),
            ],
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        gen = result.regions["USA"].generation.get("electricity", {})
        total = sum(gen.values())
        if total > 0:
            wind_share = gen.get("wind", 0.0) / total
            assert wind_share >= 0.19  # within tolerance of 20%


# ===================================================================
# EmissionsCapWrapper
# ===================================================================

class TestEmissionsCapWrapper:
    """Bisection finds carbon price to achieve emissions cap."""

    def test_cap_finds_positive_price(self):
        from ghim.solver.emissions_cap import EmissionsCapWrapper

        model, state = _build_single_region_model(PolicyScenario())
        solver = DampedSolver(alpha=0.3, tol=1e-2, max_iter=30)

        # First get baseline emissions
        baseline = solver.solve(model, state)
        base_em = baseline.global_emissions

        # Set cap at 50% of baseline
        cap_wrapper = EmissionsCapWrapper(
            solver, tol=0.05, max_iter=15, price_ceiling=500.0,
        )
        result = cap_wrapper.solve(model, state, base_em * 0.5)

        assert result.policy_carbon_price > 0
        assert result.global_emissions <= base_em * 0.55  # within 5% tolerance

    def test_cap_not_needed_returns_baseline(self):
        from ghim.solver.emissions_cap import EmissionsCapWrapper

        model, state = _build_single_region_model(PolicyScenario())
        solver = DampedSolver(alpha=0.3, tol=1e-2, max_iter=30)

        baseline = solver.solve(model, state)
        base_em = baseline.global_emissions

        # Set cap above baseline — no price needed
        cap_wrapper = EmissionsCapWrapper(solver, tol=0.05, max_iter=5)
        result = cap_wrapper.solve(model, state, base_em * 2.0)
        assert result.policy_carbon_price == 0.0


# ===================================================================
# OOP Reporting
# ===================================================================

class TestOOPReporting:
    """DataFrame and IAMC output from PeriodState."""

    @pytest.fixture(autouse=True)
    def setup(self):
        model, state = _build_single_region_model(None)
        result = model.F(state)
        self.results = [result]

    def test_to_dataframe_shape(self):
        from ghim.output.oop_reporting import oop_to_dataframe
        df = oop_to_dataframe(self.results)
        assert len(df) == 1  # 1 region × 1 period
        assert "year" in df.columns
        assert "region" in df.columns
        assert "gdp_billion_usd" in df.columns

    def test_to_dataframe_values(self):
        from ghim.output.oop_reporting import oop_to_dataframe
        df = oop_to_dataframe(self.results)
        row = df.iloc[0]
        assert row["region"] == "USA"
        assert row["year"] == 2025
        assert row["gdp_billion_usd"] > 0
        assert row["total_energy_ej"] > 0
        assert row["emissions_co2eq_mt"] > 0

    def test_to_dataframe_policy_fields(self):
        from ghim.output.oop_reporting import oop_to_dataframe
        df = oop_to_dataframe(self.results)
        assert "carbon_price_usd_tco2" in df.columns
        assert "aeei_factor" in df.columns
        assert "carbon_revenue_billion_usd" in df.columns

    def test_to_iamc_has_required_variables(self):
        from ghim.output.oop_reporting import oop_to_iamc
        iamc = oop_to_iamc(self.results, model_name="GHIM", scenario_name="SSP2")
        variables = set(iamc["variable"].unique())
        required = {
            "GDP|PPP", "Population", "Final Energy",
            "Emissions|CO2", "Emissions|Kyoto Gases",
            "Price|Carbon", "Price|Final Energy",
        }
        for v in required:
            assert v in variables, f"Missing IAMC variable: {v}"

    def test_to_iamc_columns(self):
        from ghim.output.oop_reporting import oop_to_iamc
        iamc = oop_to_iamc(self.results)
        assert "model" in iamc.columns
        assert "scenario" in iamc.columns
        assert "region" in iamc.columns
        assert "variable" in iamc.columns
        assert "unit" in iamc.columns

    def test_to_iamc_values_nonnegative(self):
        from ghim.output.oop_reporting import oop_to_iamc
        iamc = oop_to_iamc(self.results)
        # GDP, population, energy should be non-negative
        for _, row in iamc.iterrows():
            if row["variable"] in ("GDP|PPP", "Population", "Final Energy"):
                year_cols = [c for c in iamc.columns if isinstance(c, int)]
                for yc in year_cols:
                    assert row[yc] >= 0, f"{row['variable']} negative at {yc}"


# ===================================================================
# Combined policy scenario
# ===================================================================

class TestCombinedPolicy:
    """Multiple policy instruments applied simultaneously."""

    def test_carbon_plus_aeei(self):
        policy = PolicyScenario(
            carbon_price=CarbonPricePolicy(trajectory={2020: 50.0}),
            efficiency_standards=EfficiencyStandard(
                rates={"global": {2020: 0.01}},
            ),
        )
        model, state = _build_single_region_model(policy)
        result = model.F(state)
        rs = result.regions["USA"]

        # Both should be active
        assert rs.carbon_price == 50.0
        assert rs.aeei_factor < 1.0
        assert rs.carbon_revenue > 0
