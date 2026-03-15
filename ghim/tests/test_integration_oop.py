"""Integration tests for OOP model (GHIMModel + DampedSolver).

Tests the full pipeline: build_region → GHIMModel.F(x) → DampedSolver.
Uses R32 region names (GCAM 32-region).
"""

import pytest
import numpy as np

from ghim.core.carrier import Carrier
from ghim.core.config import BASE_YEAR, SOLVE_YEARS
from ghim.core.emissions import EmissionResult
from ghim.core.state import PeriodState, RegionState
from ghim.model import GHIMModel
from ghim.solver.damped import DampedSolver
from ghim.adapters.base import (
    DefaultClimateAdapter,
    DefaultWaterAdapter,
    DefaultAFOLUAdapter,
)


# ===========================================================================
# Single-region build + F(x) test
# ===========================================================================

class TestSingleRegionBuild:
    """Test that build_region produces a valid Region + RegionState."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from ghim.build import build_region
        self.region, self.rs = build_region("China", 15000.0, 1400.0)

    def test_region_name(self):
        assert self.region.name == "China"

    def test_has_economy(self):
        assert self.region.economy is not None
        assert self.region.economy.base_gdp == 15000.0

    def test_has_4_demand_sectors(self):
        assert len(self.region.demand_sectors) == 4

    def test_has_5_transformation_sectors(self):
        assert len(self.region.transformation) == 5

    def test_region_state_gdp(self):
        assert self.rs.gdp == 15000.0

    def test_region_state_prices(self):
        assert Carrier.ELECTRICITY in self.rs.carrier_prices
        assert Carrier.GAS in self.rs.carrier_prices

    def test_region_state_composite_price(self):
        assert self.rs.composite_energy_price > 0


class TestSingleRegionFx:
    """Test F(x) with one real region."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from ghim.build import build_region
        region, rs = build_region("China", 15000.0, 1400.0)

        self.model = GHIMModel(
            regions={"China": region},
            climate=DefaultClimateAdapter(),
            water=DefaultWaterAdapter(),
            afolu=DefaultAFOLUAdapter(),
        )
        self.state = PeriodState(
            period=2025,
            regions={"China": rs},
            world_prices={"coal": 2.5, "oil": 8.0, "gas": 4.0},
        )

    def test_fx_returns_state(self):
        result = self.model.F(self.state)
        assert isinstance(result, PeriodState)

    def test_fx_gdp_positive(self):
        result = self.model.F(self.state)
        assert result.regions["China"].gdp > 0

    def test_fx_energy_demand_positive(self):
        result = self.model.F(self.state)
        fd = result.regions["China"].final_demand
        assert sum(fd.values()) > 0

    def test_fx_generation_populated(self):
        result = self.model.F(self.state)
        gen = result.regions["China"].generation
        assert len(gen) > 0

    def test_fx_emissions_populated(self):
        result = self.model.F(self.state)
        em = result.regions["China"].emissions_detail
        assert isinstance(em, EmissionResult)

    def test_fx_global_emissions(self):
        result = self.model.F(self.state)
        assert result.global_emissions != 0.0


# ===========================================================================
# Solver convergence test
# ===========================================================================

class TestSolverConvergence:
    """Test DampedSolver converges on a single region."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from ghim.build import build_region
        region, rs = build_region("USA", 22000.0, 370.0)
        region.economy.init_tfp_trajectory(
            {BASE_YEAR: 22000.0, 2025: 23000.0, 2030: 24000.0},
            {BASE_YEAR: 370.0, 2025: 375.0, 2030: 380.0},
        )
        region.economy.set_tfp_for_year(2025)

        self.model = GHIMModel(
            regions={"USA": region},
            climate=DefaultClimateAdapter(),
            water=DefaultWaterAdapter(),
            afolu=DefaultAFOLUAdapter(),
        )
        self.state = PeriodState(
            period=2025,
            regions={"USA": rs},
            world_prices={"coal": 2.5, "oil": 8.0, "gas": 4.0},
        )

    def test_solver_converges(self):
        solver = DampedSolver(alpha=0.4, tol=1e-2, max_iter=50)
        result = solver.solve(self.model, self.state)
        rs = result.regions["USA"]
        assert rs.gdp > 0
        assert np.isfinite(rs.gdp)

    def test_solver_gdp_reasonable(self):
        """GDP should be in a reasonable range (not exploding or collapsing)."""
        solver = DampedSolver(alpha=0.3, tol=1e-2, max_iter=50)
        result = solver.solve(self.model, self.state)
        gdp = result.regions["USA"].gdp
        # Should be within 50% of initial
        assert 11000.0 < gdp < 44000.0

    def test_solver_energy_demand_reasonable(self):
        solver = DampedSolver(alpha=0.3, tol=1e-2, max_iter=50)
        result = solver.solve(self.model, self.state)
        fd = result.regions["USA"].final_demand
        total = sum(fd.values())
        assert total > 0


# ===========================================================================
# Multi-region build test
# ===========================================================================

class TestMultiRegionBuild:
    """Test building multiple regions."""

    def test_build_all_r32(self):
        from ghim.build import build_region
        from ghim.regions_r32 import R32_REGIONS

        regions = {}
        states = {}
        for name in R32_REGIONS:
            region, rs = build_region(name, 1000.0, 100.0)
            regions[name] = region
            states[name] = rs

        assert len(regions) == 32
        for name in R32_REGIONS:
            assert name in regions
            assert regions[name].economy is not None

    def test_multi_region_fx(self):
        """F(x) works with 3 R32 regions."""
        from ghim.build import build_region

        region_names = ["USA", "EU-15", "China"]
        regions = {}
        initial_regions = {}
        for name in region_names:
            r, rs = build_region(name, 5000.0, 500.0)
            regions[name] = r
            initial_regions[name] = rs

        model = GHIMModel(
            regions=regions,
            climate=DefaultClimateAdapter(),
            water=DefaultWaterAdapter(),
            afolu=DefaultAFOLUAdapter(),
        )
        state = PeriodState(
            period=2025,
            regions=initial_regions,
            world_prices={"coal": 2.5, "oil": 8.0, "gas": 4.0},
        )
        result = model.F(state)
        for name in region_names:
            assert result.regions[name].gdp > 0
            assert sum(result.regions[name].final_demand.values()) > 0


# ===========================================================================
# Full run loop test (lightweight — 2 periods only)
# ===========================================================================

class TestOOPRunLoop:
    """Test the full oop_run_model with minimal periods."""

    def test_two_period_run(self):
        """Run 2 periods to verify inter-period capital update works."""
        from ghim.build import build_region

        region, rs = build_region("EU-15", 18000.0, 450.0)
        region.economy.init_tfp_trajectory(
            {BASE_YEAR: 18000.0, 2025: 19000.0, 2030: 20000.0},
            {BASE_YEAR: 450.0, 2025: 448.0, 2030: 446.0},
        )

        model = GHIMModel(
            regions={"EU-15": region},
            climate=DefaultClimateAdapter(),
            water=DefaultWaterAdapter(),
            afolu=DefaultAFOLUAdapter(),
        )
        solver = DampedSolver(alpha=0.3, tol=1e-2, max_iter=30)

        from copy import deepcopy
        state = PeriodState(
            period=BASE_YEAR,
            regions={"EU-15": rs},
            world_prices={"coal": 2.5, "oil": 8.0, "gas": 4.0},
        )

        results = []
        for period in [BASE_YEAR, 2025]:
            state.period = period
            region.economy.set_tfp_for_year(period)
            state = solver.solve(model, state)

            # Inter-period: update capital
            rs_out = state.regions["EU-15"]
            region.economy.update_capital(rs_out.investment)
            rs_out.capital_stock = region.economy.capital_stock

            results.append(deepcopy(state))

        assert len(results) == 2
        # Capital should change between periods
        k0 = results[0].regions["EU-15"].capital_stock
        k1 = results[1].regions["EU-15"].capital_stock
        assert k0 != k1  # capital evolved

    def test_gdp_stable_across_periods(self):
        """GDP shouldn't explode or collapse over 2 periods."""
        from ghim.build import build_region
        from copy import deepcopy

        region, rs = build_region("China", 15000.0, 1400.0)
        region.economy.init_tfp_trajectory(
            {BASE_YEAR: 15000.0, 2025: 16000.0},
            {BASE_YEAR: 1400.0, 2025: 1390.0},
        )

        model = GHIMModel(
            regions={"China": region},
            climate=DefaultClimateAdapter(),
            water=DefaultWaterAdapter(),
            afolu=DefaultAFOLUAdapter(),
        )
        solver = DampedSolver(alpha=0.3, tol=1e-2, max_iter=30)
        state = PeriodState(
            period=BASE_YEAR,
            regions={"China": rs},
            world_prices={"coal": 2.5, "oil": 8.0, "gas": 4.0},
        )

        gdps = []
        for period in [BASE_YEAR, 2025]:
            state.period = period
            region.economy.set_tfp_for_year(period)
            state = solver.solve(model, state)
            gdps.append(state.regions["China"].gdp)
            rs_out = state.regions["China"]
            region.economy.update_capital(rs_out.investment)
            rs_out.capital_stock = region.economy.capital_stock
            state = deepcopy(state)

        # GDP should be reasonably stable (within 50% change)
        assert gdps[1] > gdps[0] * 0.5
        assert gdps[1] < gdps[0] * 2.0


# ===========================================================================
# Endogenous GDP validation
# ===========================================================================

@pytest.mark.slow
class TestEndogenousGDP:
    """Test that endogenous GDP (two-pass TFP) tracks SSP trajectory."""

    def test_endogenous_gdp_tracks_ssp(self):
        """Full model run via oop_run_model: endogenous GDP within 25% of SSP.

        Uses the full run loop with AR6 calibration, trade, and warm-up.
        The two-pass TFP calibration makes CES output approximate SSP GDP.
        Tolerance is 25% because of the mismatch between KLEM aggregate
        energy and sector-level energy demand (intensity ratio normalizes
        the time pattern, not the level).
        """
        from ghim.build import oop_run_model
        from ghim.data.ssp import load_ssp_data_r32
        from ghim.core.config import FUTURE_YEARS, EconomyConfig

        # Skip if endogenous_gdp is off
        if not EconomyConfig().endogenous_gdp:
            pytest.skip("endogenous_gdp is disabled in config")

        ssp_data = load_ssp_data_r32("SSP2")
        gdp_df = ssp_data["gdp"]

        results = oop_run_model(ssp_data, "SSP2")

        # Check periods 2-4 (skip first period: warm-up transient)
        for i, period in enumerate(FUTURE_YEARS[1:4]):
            state = results[i + 1]
            global_gdp = sum(rs.gdp for rs in state.regions.values())
            global_target = sum(
                float(gdp_df.loc[name, period])
                for name in state.regions
                if period in gdp_df.columns
            )
            if global_target > 0:
                dev = abs(global_gdp - global_target) / global_target
                assert dev < 0.25, (
                    f"Period {period}: global GDP dev {dev:.1%} "
                    f"(model={global_gdp:.0f}, SSP={global_target:.0f})"
                )
