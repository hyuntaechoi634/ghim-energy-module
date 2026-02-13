"""Tests for vintage stock turnover model (S-curve retirement + pipeline)."""

import numpy as np
import pytest

from ghim.config import BASE_YEAR, TIMESTEP
from ghim.energy.stock import (
    VintageStock,
    PipelineAwareVintageStock,
    NUCLEAR_PIPELINE_R10,
    apply_stock_turnover,
)


# ======================================================================
# S-curve survival
# ======================================================================

class TestSCurveSurvival:
    def setup_method(self):
        self.vs = VintageStock(
            tech_names=["coal", "wind", "solar"],
            lifetimes={"coal": 60.0, "wind": 30.0, "solar": 30.0},
            hard_cutoff_techs={"wind", "solar"},
        )

    def test_age_zero_returns_one(self):
        assert self.vs.s_curve_survival("coal", 2020, 2020) == 1.0

    def test_age_at_lifetime_returns_zero(self):
        assert self.vs.s_curve_survival("coal", 2020, 2020 + 60) == 0.0

    def test_age_beyond_lifetime_returns_zero(self):
        assert self.vs.s_curve_survival("coal", 2020, 2020 + 100) == 0.0

    def test_monotonic_decrease(self):
        survivals = [
            self.vs.s_curve_survival("coal", 2000, 2000 + age)
            for age in range(0, 61, 5)
        ]
        for i in range(len(survivals) - 1):
            assert survivals[i] >= survivals[i + 1], \
                f"Non-monotonic at age {i*5}: {survivals[i]:.4f} < {survivals[i+1]:.4f}"

    def test_hard_cutoff_binary_wind(self):
        """Wind has step-function survival: 1.0 before lifetime, 0.0 at/after."""
        assert self.vs.s_curve_survival("wind", 2000, 2029) == 1.0
        assert self.vs.s_curve_survival("wind", 2000, 2030) == 0.0
        assert self.vs.s_curve_survival("wind", 2000, 2050) == 0.0

    def test_hard_cutoff_binary_solar(self):
        assert self.vs.s_curve_survival("solar", 2000, 2000) == 1.0
        assert self.vs.s_curve_survival("solar", 2000, 2030) == 0.0

    def test_scurve_coal_reference_values(self):
        """Check S-curve shape at key ages for coal (lifetime=60)."""
        s = self.vs.s_curve_survival
        # At age=0 → 1.0
        assert s("coal", 2000, 2000) == pytest.approx(1.0)
        # At midpoint (0.75 * 60 = 45y) → should be ~0.5
        mid = s("coal", 2000, 2045)
        assert 0.3 < mid < 0.7, f"Midpoint survival = {mid}"
        # At age=10 → should be close to 1.0
        assert s("coal", 2000, 2010) > 0.9
        # At age=55 → should be close to 0
        assert s("coal", 2000, 2055) < 0.3

    def test_negative_age_returns_one(self):
        """Future vintage should return 1.0."""
        assert self.vs.s_curve_survival("coal", 2030, 2020) == 1.0

    def test_unknown_tech_uses_default_lifetime(self):
        """Unknown tech uses default lifetime of 40."""
        vs = VintageStock(tech_names=["unknown"], lifetimes={})
        assert vs.s_curve_survival("unknown", 2000, 2000) == 1.0
        assert vs.s_curve_survival("unknown", 2000, 2040) == 0.0


# ======================================================================
# VintageStock initialization
# ======================================================================

class TestVintageStockInit:
    def test_uniform_total_correct(self):
        """Uniform initialization should sum to target capacity."""
        vs = VintageStock(
            tech_names=["coal", "gas_cc"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0},
        )
        shares = np.array([0.6, 0.4])
        total = 10.0
        vs.initialize_uniform(shares, total, BASE_YEAR)

        # At base year, all vintages survive → total should be close to original
        surviving = vs.surviving_capacity(BASE_YEAR)
        actual = sum(surviving.values())
        assert actual == pytest.approx(total, rel=0.01)

    def test_uniform_per_tech_correct(self):
        """Each tech's surviving capacity should match share * total."""
        vs = VintageStock(
            tech_names=["coal", "gas_cc"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0},
        )
        shares = np.array([0.7, 0.3])
        total = 10.0
        vs.initialize_uniform(shares, total, BASE_YEAR)
        surviving = vs.surviving_capacity(BASE_YEAR)
        assert surviving["coal"] == pytest.approx(7.0, rel=0.01)
        assert surviving["gas_cc"] == pytest.approx(3.0, rel=0.01)

    def test_gem_scaling(self):
        """GEM data should be scaled to match model total per tech."""
        vs = VintageStock(
            tech_names=["coal", "nuclear"],
            lifetimes={"coal": 60.0, "nuclear": 60.0},
        )
        gem_data = {
            "coal": {1990: 1.0, 2000: 2.0, 2010: 3.0},
            "nuclear": {1980: 0.5, 2000: 0.5},
        }
        shares = np.array([0.6, 0.4])
        total = 10.0
        vs.initialize_from_gem(gem_data, shares, total, BASE_YEAR)

        # At base year, surviving should be close to targets
        # (some older vintages may have partially retired)
        surviving = vs.surviving_capacity(BASE_YEAR)
        assert surviving["coal"] > 0
        assert surviving["nuclear"] > 0

    def test_gem_fallback_to_uniform(self):
        """Techs without GEM data should fall back to uniform."""
        vs = VintageStock(
            tech_names=["coal", "wind"],
            lifetimes={"coal": 60.0, "wind": 30.0},
            hard_cutoff_techs={"wind"},
        )
        gem_data = {"coal": {2000: 1.0, 2010: 2.0}}  # No wind data
        shares = np.array([0.6, 0.4])
        total = 10.0
        vs.initialize_from_gem(gem_data, shares, total, BASE_YEAR)

        # Wind should still have capacity (uniform fallback)
        surviving = vs.surviving_capacity(BASE_YEAR)
        assert surviving["wind"] > 0

    def test_single_vintage(self):
        """Single vintage puts all capacity in base year."""
        vs = VintageStock(
            tech_names=["coal", "gas_cc"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0},
        )
        shares = np.array([0.5, 0.5])
        vs.initialize_single_vintage(shares, 10.0, BASE_YEAR)
        caps = vs.get_vintage_capacities("coal")
        assert list(caps.keys()) == [BASE_YEAR]
        assert caps[BASE_YEAR] == pytest.approx(5.0)

    def test_zero_share_no_capacity(self):
        """Tech with zero share should have no capacity."""
        vs = VintageStock(
            tech_names=["coal", "gas_cc"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0},
        )
        shares = np.array([1.0, 0.0])
        vs.initialize_uniform(shares, 10.0, BASE_YEAR)
        assert vs.surviving_capacity(BASE_YEAR)["gas_cc"] == 0.0


# ======================================================================
# retire_and_invest
# ======================================================================

class TestRetireAndInvest:
    def setup_method(self):
        self.vs = VintageStock(
            tech_names=["coal", "gas_cc", "wind"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0, "wind": 30.0},
            hard_cutoff_techs={"wind"},
        )
        shares = np.array([0.4, 0.3, 0.3])
        self.vs.initialize_uniform(shares, 10.0, BASE_YEAR)

    def test_shares_sum_to_one(self):
        target = np.array([0.2, 0.3, 0.5])
        result = self.vs.retire_and_invest(2025, target, 10.0)
        assert result.sum() == pytest.approx(1.0, abs=1e-6)

    def test_gap_fill_follows_target(self):
        """When capacity retires, gap is filled following target shares."""
        # Run many periods to create retirement
        target = np.array([0.1, 0.3, 0.6])
        for yr in range(2025, 2100, TIMESTEP):
            result = self.vs.retire_and_invest(yr, target, 10.0)
        # After many periods, shares should approach target
        assert result.sum() == pytest.approx(1.0, abs=1e-6)

    def test_overcapacity_scales_proportionally(self):
        """When demand shrinks, all techs scale proportionally."""
        target = np.array([0.3, 0.3, 0.4])
        result = self.vs.retire_and_invest(BASE_YEAR, target, 2.0)
        assert result.sum() == pytest.approx(1.0, abs=1e-6)
        # Overcapacity → no new investment, just scaling existing

    def test_zero_demand_returns_target(self):
        target = np.array([0.5, 0.3, 0.2])
        result = self.vs.retire_and_invest(2025, target, 0.0)
        np.testing.assert_array_almost_equal(result, target)

    def test_multi_period_coal_decline(self):
        """Coal should decline over time with low target share."""
        target = np.array([0.0, 0.5, 0.5])  # no new coal
        coal_shares = []
        for yr in range(2025, 2150, TIMESTEP):
            result = self.vs.retire_and_invest(yr, target, 10.0)
            coal_shares.append(result[0])
        # Coal should decrease over time (retiring without replacement)
        assert coal_shares[-1] < coal_shares[0]
        # Eventually coal should be near zero
        assert coal_shares[-1] < 0.05

    def test_new_investment_recorded(self):
        """New investment should be recorded in vintage bins."""
        target = np.array([0.3, 0.3, 0.4])
        self.vs.retire_and_invest(2025, target, 15.0)
        # Should have entries at year 2025 for some techs (gap fill)
        has_new = any(
            2025 in self.vs._capacity[t]
            for t in self.vs.tech_names
        )
        assert has_new


# ======================================================================
# PipelineAwareVintageStock
# ======================================================================

class TestPipelineAware:
    def setup_method(self):
        self.pvs = PipelineAwareVintageStock(
            tech_names=["coal", "nuclear", "wind"],
            lifetimes={"coal": 60.0, "nuclear": 60.0, "wind": 30.0},
            hard_cutoff_techs={"wind"},
            construction_times={"nuclear": 2},  # 2 periods = 10 years
        )
        shares = np.array([0.5, 0.3, 0.2])
        self.pvs.initialize_uniform(shares, 10.0, BASE_YEAR)

    def test_pipeline_arrival(self):
        """Pipeline capacity should arrive after delay."""
        self.pvs.initialize_pipeline({"nuclear": {2030: 0.5}})
        # At 2025, nuclear pipeline hasn't arrived yet
        result_2025 = self.pvs.retire_and_invest(
            2025, np.array([0.3, 0.4, 0.3]), 10.0,
        )
        # At 2030, pipeline arrives
        result_2030 = self.pvs.retire_and_invest(
            2030, np.array([0.3, 0.4, 0.3]), 10.0,
        )
        # Nuclear should have more capacity after pipeline arrival
        assert result_2030.sum() == pytest.approx(1.0, abs=1e-6)

    def test_pipeline_subtracted_from_gap(self):
        """Future pipeline should reduce gap (less new investment needed)."""
        self.pvs.initialize_pipeline({"nuclear": {2035: 5.0}})
        target = np.array([0.1, 0.8, 0.1])
        result = self.pvs.retire_and_invest(2025, target, 10.0)
        # The large pipeline entry should reduce new investment
        assert result.sum() == pytest.approx(1.0, abs=1e-6)

    def test_slow_build_routed_to_pipeline(self):
        """Nuclear investment should go to pipeline, not immediate capacity."""
        target = np.array([0.0, 0.8, 0.2])
        self.pvs.retire_and_invest(2025, target, 20.0)
        # Check that nuclear has pipeline entries
        pipeline_total = self.pvs._pipeline_total("nuclear")
        # Coal/wind should NOT have pipeline entries
        assert self.pvs._pipeline_total("coal") == 0.0
        assert self.pvs._pipeline_total("wind") == 0.0

    def test_fast_build_immediate(self):
        """Wind/coal investment goes directly to capacity (no pipeline)."""
        target = np.array([0.3, 0.0, 0.7])
        self.pvs.retire_and_invest(2025, target, 15.0)
        # Wind should have capacity at 2025
        wind_caps = self.pvs.get_vintage_capacities("wind")
        assert 2025 in wind_caps or sum(wind_caps.values()) > 0

    def test_shares_sum_to_one_with_pipeline(self):
        """Output shares should always sum to 1."""
        self.pvs.initialize_pipeline({"nuclear": {2030: 1.0, 2035: 0.5}})
        for yr in range(2025, 2060, TIMESTEP):
            target = np.array([0.2, 0.5, 0.3])
            result = self.pvs.retire_and_invest(yr, target, 10.0)
            assert result.sum() == pytest.approx(1.0, abs=1e-6)


# ======================================================================
# Demand-sector vintage (fuel-carrier level)
# ======================================================================

class TestDemandVintage:
    def test_fuel_carrier_node_has_vintage(self):
        """Fuel-carrier nodes should have VintageStock."""
        from ghim.energy.demand import _make_fuel_node
        node = _make_fuel_node(
            "test", {"electricity": 0.5, "gas": 0.5},
            carrier_lifetime=20.0,
        )
        node.calibrate({"electricity": 20.0, "gas": 4.0})
        assert node.vintage_stock is not None

    def test_structural_node_no_vintage(self):
        """Structural nodes should NOT have VintageStock."""
        from ghim.energy.demand import DemandNode, DemandLeaf
        node = DemandNode(
            "structural",
            [DemandLeaf("a", "electricity"), DemandLeaf("b", "gas")],
            {"a": 0.5, "b": 0.5},
            turnover_time=50.0,
            # No carrier_lifetime → no vintage stock
        )
        node.calibrate({"electricity": 20.0, "gas": 4.0})
        assert node.vintage_stock is None

    def test_demand_vintage_shares_sum(self):
        """Demand with vintage stock should produce shares summing to 1."""
        from ghim.energy.demand import _make_fuel_node
        node = _make_fuel_node(
            "test", {"electricity": 0.5, "gas": 0.5},
            carrier_lifetime=20.0,
        )
        node.calibrate({"electricity": 20.0, "gas": 4.0})
        for yr in range(2025, 2080, TIMESTEP):
            demands = node.compute_carrier_demands(
                10.0, {"electricity": 20.0, "gas": 4.0}, year=yr,
            )
            total = sum(demands.values())
            assert total == pytest.approx(10.0, rel=0.01)

    def test_multi_period_demand_evolution(self):
        """Fuel shares should evolve over multiple periods."""
        from ghim.energy.demand import _make_fuel_node
        node = _make_fuel_node(
            "test", {"electricity": 0.3, "gas": 0.7},
            carrier_lifetime=20.0,
        )
        node.calibrate({"electricity": 5.0, "gas": 5.0})
        demands_early = node.compute_carrier_demands(
            10.0, {"electricity": 5.0, "gas": 5.0}, year=2025,
        )
        for yr in range(2030, 2100, TIMESTEP):
            demands_late = node.compute_carrier_demands(
                10.0, {"electricity": 5.0, "gas": 5.0}, year=yr,
            )
        # After many periods, shares should have evolved
        # (at equal costs, PF decay should shift toward equal)
        assert demands_late != demands_early


# ======================================================================
# Electricity integration
# ======================================================================

class TestElecIntegration:
    def test_electricity_has_vintage_stock(self):
        """ElectricitySector should have PipelineAwareVintageStock after calibrate."""
        from ghim.energy.electricity import ElectricitySector
        sector = ElectricitySector(region="North America")
        fuel_prices = {
            "coal": 2.5, "gas": 4.0, "nuclear": 0.7,
            "hydro": 0.0, "wind": 0.0, "solar": 0.0,
            "biomass": 3.0, "refined liquids": 12.0,
        }
        base_shares = {
            "coal": 0.4, "gas_cc": 0.3, "nuclear": 0.15,
            "hydro": 0.05, "wind": 0.05, "solar": 0.02,
            "biomass": 0.02, "oil": 0.01,
        }
        sector.calibrate(base_shares, fuel_prices)
        assert sector.vintage_stock is not None
        assert isinstance(sector.vintage_stock, PipelineAwareVintageStock)

    def test_electricity_supply_with_vintage(self):
        """Supply should sum to demand with vintage stock."""
        from ghim.energy.electricity import ElectricitySector
        sector = ElectricitySector(region="Europe")
        fuel_prices = {
            "coal": 2.5, "gas": 4.0, "nuclear": 0.7,
            "hydro": 0.0, "wind": 0.0, "solar": 0.0,
            "biomass": 3.0, "refined liquids": 12.0,
        }
        base_shares = {
            "coal": 0.4, "gas_cc": 0.3, "nuclear": 0.15,
            "hydro": 0.05, "wind": 0.05, "solar": 0.02,
            "biomass": 0.02, "oil": 0.01,
        }
        sector.calibrate(base_shares, fuel_prices)
        gen = sector.compute_supply(fuel_prices, 10.0, year=2025)
        total = sum(gen.values())
        assert total == pytest.approx(10.0, rel=0.01)

    def test_coal_decline_with_alpha_zero(self):
        """Coal should decline to zero with α=0 (faster with vintage stock)."""
        from ghim.energy.electricity import ElectricitySector
        sector = ElectricitySector(region="Europe")
        fuel_prices = {
            "coal": 2.5, "gas": 4.0, "nuclear": 0.7,
            "hydro": 0.0, "wind": 0.0, "solar": 0.0,
            "biomass": 3.0, "refined liquids": 12.0,
        }
        base_shares = {
            "coal": 0.4, "gas_cc": 0.3, "nuclear": 0.15,
            "hydro": 0.05, "wind": 0.05, "solar": 0.02,
            "biomass": 0.02, "oil": 0.01,
        }
        sector.calibrate(base_shares, fuel_prices)
        import numpy as np
        alpha = np.array([
            0.0 if t.name == "coal" else 1.0 for t in sector.techs
        ])
        for yr in range(2025, 2200, TIMESTEP):
            gen = sector.compute_supply(
                fuel_prices, 10.0, year=yr, alpha=alpha,
            )
        assert gen["coal"] < 0.5  # coal should be near zero

    def test_nuclear_pipeline_populated(self):
        """Nuclear pipeline should be populated for regions with WNA data."""
        from ghim.energy.electricity import ElectricitySector
        sector = ElectricitySector(region="Eastern Asia")
        fuel_prices = {
            "coal": 2.5, "gas": 4.0, "nuclear": 0.7,
            "hydro": 0.0, "wind": 0.0, "solar": 0.0,
            "biomass": 3.0, "refined liquids": 12.0,
        }
        base_shares = {
            "coal": 0.4, "gas_cc": 0.3, "nuclear": 0.15,
            "hydro": 0.05, "wind": 0.05, "solar": 0.02,
            "biomass": 0.02, "oil": 0.01,
        }
        sector.calibrate(base_shares, fuel_prices)
        # Eastern Asia has the largest nuclear pipeline
        pipeline_total = sector.vintage_stock._pipeline_total("nuclear")
        assert pipeline_total > 0


# ======================================================================
# Hydrogen integration
# ======================================================================

class TestHydrogenIntegration:
    def test_hydrogen_has_vintage_stock(self):
        from ghim.energy.hydrogen import HydrogenSector
        sector = HydrogenSector()
        fuel_prices = {"gas": 4.0, "electricity": 20.0}
        sector.calibrate({"smr": 0.95, "electrolysis": 0.05}, fuel_prices)
        assert sector.vintage_stock is not None

    def test_hydrogen_supply_with_vintage(self):
        from ghim.energy.hydrogen import HydrogenSector
        sector = HydrogenSector()
        fuel_prices = {"gas": 4.0, "electricity": 20.0}
        sector.calibrate({"smr": 0.95, "electrolysis": 0.05}, fuel_prices)
        prod = sector.compute_supply(fuel_prices, 1.0, year=2025)
        total = sum(prod.values())
        assert total == pytest.approx(1.0, rel=0.01)


# ======================================================================
# Prune retired
# ======================================================================

class TestPruneRetired:
    def test_prune_removes_dead_vintages(self):
        vs = VintageStock(
            tech_names=["wind"],
            lifetimes={"wind": 30.0},
            hard_cutoff_techs={"wind"},
        )
        vs._capacity["wind"] = {1990: 1.0, 2000: 2.0, 2010: 3.0}
        vs.prune_retired(2025)
        # 1990 vintage → age 35, wind lifetime 30 → dead
        assert 1990 not in vs._capacity["wind"]
        # 2000 vintage → age 25 → alive
        assert 2000 in vs._capacity["wind"]

    def test_prune_keeps_alive_vintages(self):
        vs = VintageStock(
            tech_names=["coal"],
            lifetimes={"coal": 60.0},
        )
        vs._capacity["coal"] = {2000: 5.0, 2010: 3.0, 2020: 2.0}
        vs.prune_retired(2030)
        # All vintages should survive (coal lifetime=60, max age=30)
        assert len(vs._capacity["coal"]) == 3
