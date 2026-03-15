"""Tests for ghim.core.vintage — enhanced VintageTracker."""

import numpy as np
import pytest

from ghim.core.config import VintageConfig, BASE_YEAR, TIMESTEP
from ghim.core.vintage import (
    VintageTracker,
    PipelineAwareVintageTracker,
    InvestmentResult,
    NUCLEAR_PIPELINE_R10,
)


# ===========================================================================
# VintageTracker basics (mirrors test_stock tests but for new class)
# ===========================================================================

class TestVintageTracker:
    def test_s_curve_age_zero(self):
        vt = VintageTracker(tech_names=["coal"], lifetimes={"coal": 60.0})
        assert vt.s_curve_survival("coal", 2020, 2020) == 1.0

    def test_s_curve_at_lifetime(self):
        vt = VintageTracker(tech_names=["coal"], lifetimes={"coal": 60.0})
        assert vt.s_curve_survival("coal", 2020, 2080) == 0.0

    def test_hard_cutoff(self):
        vt = VintageTracker(
            tech_names=["wind"],
            lifetimes={"wind": 30.0},
            hard_cutoff_techs={"wind"},
        )
        assert vt.s_curve_survival("wind", 2000, 2029) == 1.0
        assert vt.s_curve_survival("wind", 2000, 2030) == 0.0

    def test_uniform_init_reproduces_total(self):
        vt = VintageTracker(
            tech_names=["coal", "gas_cc"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0},
        )
        vt.initialize_uniform(np.array([0.6, 0.4]), 10.0, BASE_YEAR)
        surviving = vt.surviving_capacity(BASE_YEAR)
        assert sum(surviving.values()) == pytest.approx(10.0, rel=0.01)

    def test_retire_and_invest_returns_ndarray(self):
        vt = VintageTracker(
            tech_names=["coal", "wind"],
            lifetimes={"coal": 60.0, "wind": 30.0},
            hard_cutoff_techs={"wind"},
        )
        vt.initialize_uniform(np.array([0.5, 0.5]), 10.0, BASE_YEAR)
        result = vt.retire_and_invest(2025, np.array([0.3, 0.7]), 10.0)
        assert isinstance(result, np.ndarray)
        assert result.sum() == pytest.approx(1.0, abs=1e-6)


# ===========================================================================
# from_config factory
# ===========================================================================

class TestFromConfig:
    def test_default_config(self):
        vt = VintageTracker.from_config(["coal", "wind"])
        assert vt.steepness == VintageConfig().scurve_steepness
        assert vt.half_life_ratio == VintageConfig().scurve_halflife_ratio

    def test_custom_config(self):
        cfg = VintageConfig(scurve_steepness=0.2, scurve_halflife_ratio=0.5)
        vt = VintageTracker.from_config(["coal"], cfg=cfg)
        assert vt.steepness == 0.2
        assert vt.half_life_ratio == 0.5

    def test_custom_lifetimes(self):
        vt = VintageTracker.from_config(
            ["coal"], lifetimes={"coal": 100.0},
        )
        assert vt.lifetimes["coal"] == 100.0


# ===========================================================================
# InvestmentResult tracking
# ===========================================================================

class TestInvestmentResult:
    def setup_method(self):
        self.vt = VintageTracker(
            tech_names=["coal", "gas_cc", "wind"],
            lifetimes={"coal": 60.0, "gas_cc": 45.0, "wind": 30.0},
            hard_cutoff_techs={"wind"},
        )
        self.vt.initialize_uniform(np.array([0.4, 0.3, 0.3]), 10.0, BASE_YEAR)

    def test_last_result_populated(self):
        self.vt.retire_and_invest(2025, np.array([0.2, 0.3, 0.5]), 10.0)
        result = self.vt.last_result
        assert result is not None
        assert isinstance(result, InvestmentResult)

    def test_result_surviving_dict(self):
        self.vt.retire_and_invest(2025, np.array([0.2, 0.3, 0.5]), 10.0)
        result = self.vt.last_result
        assert "coal" in result.surviving
        assert "gas_cc" in result.surviving
        assert "wind" in result.surviving

    def test_result_gap_positive_when_demand_grows(self):
        """Increasing demand should produce positive gap."""
        self.vt.retire_and_invest(2025, np.array([0.2, 0.3, 0.5]), 15.0)
        result = self.vt.last_result
        assert result.gap_ej > 0

    def test_result_gap_zero_overcapacity(self):
        """Decreasing demand → overcapacity → gap = 0."""
        self.vt.retire_and_invest(BASE_YEAR, np.array([0.2, 0.3, 0.5]), 2.0)
        result = self.vt.last_result
        assert result.gap_ej == 0.0

    def test_result_new_investment_sums_to_gap(self):
        """Total new investment should equal the gap."""
        self.vt.retire_and_invest(2025, np.array([0.2, 0.3, 0.5]), 15.0)
        result = self.vt.last_result
        total_new = sum(result.new_investment.values())
        assert total_new == pytest.approx(result.gap_ej, rel=1e-6)

    def test_result_zero_demand(self):
        self.vt.retire_and_invest(2025, np.array([0.2, 0.3, 0.5]), 0.0)
        result = self.vt.last_result
        assert result.gap_ej == 0.0
        assert result.total_surviving_ej > 0

    def test_result_shares_match_return(self):
        """last_result.shares should match the returned ndarray."""
        ret = self.vt.retire_and_invest(2025, np.array([0.2, 0.3, 0.5]), 10.0)
        np.testing.assert_array_almost_equal(ret, self.vt.last_result.shares)


# ===========================================================================
# timestep parameter
# ===========================================================================

class TestTimestepParam:
    def test_custom_timestep(self):
        vt = VintageTracker(
            tech_names=["wind"],
            lifetimes={"wind": 30.0},
            hard_cutoff_techs={"wind"},
            timestep=10,
        )
        vt.initialize_uniform(np.array([1.0]), 5.0, 2020)
        surviving = vt.surviving_capacity(2020)
        assert surviving["wind"] == pytest.approx(5.0, rel=0.01)


# ===========================================================================
# PipelineAwareVintageTracker
# ===========================================================================

class TestPipelineAware:
    def setup_method(self):
        self.pvt = PipelineAwareVintageTracker(
            tech_names=["coal", "nuclear", "wind"],
            lifetimes={"coal": 60.0, "nuclear": 60.0, "wind": 30.0},
            hard_cutoff_techs={"wind"},
            construction_times={"nuclear": 2},
        )
        self.pvt.initialize_uniform(
            np.array([0.5, 0.3, 0.2]), 10.0, BASE_YEAR,
        )

    def test_construction_completion(self):
        self.pvt.initialize_under_construction({"nuclear": {2030: 0.5}})
        self.pvt.retire_and_invest(2025, np.array([0.3, 0.4, 0.3]), 10.0)
        result_2030 = self.pvt.retire_and_invest(
            2030, np.array([0.3, 0.4, 0.3]), 10.0,
        )
        assert result_2030.sum() == pytest.approx(1.0, abs=1e-6)

    def test_slow_build_routed_to_pipeline(self):
        target = np.array([0.0, 0.8, 0.2])
        self.pvt.retire_and_invest(2025, target, 20.0)
        assert self.pvt._under_construction_total("nuclear") > 0
        assert self.pvt._under_construction_total("coal") == 0.0

    def test_last_result_with_pipeline(self):
        self.pvt.retire_and_invest(2025, np.array([0.3, 0.4, 0.3]), 15.0)
        result = self.pvt.last_result
        assert result is not None
        assert result.shares.sum() == pytest.approx(1.0, abs=1e-6)


