"""Tests for ghim.core.learning — two-factor technology learning curves."""

import math

import pytest

from ghim.core.config import LearningConfig
from ghim.core.learning import (
    TechChange,
    TechLearningParams,
    TechLearningState,
    _lr_to_exponent,
    DEFAULT_SPILLOVERS,
    DEFAULT_RND_RATES,
    DEFAULT_FLOOR_FRACTIONS,
)


# ===========================================================================
# _lr_to_exponent
# ===========================================================================

class TestLRToExponent:
    def test_zero_rate(self):
        assert _lr_to_exponent(0.0) == 0.0

    def test_negative_rate(self):
        assert _lr_to_exponent(-0.1) == 0.0

    def test_rate_one_capped(self):
        assert _lr_to_exponent(1.0) == 10.0

    def test_rate_above_one_capped(self):
        assert _lr_to_exponent(1.5) == 10.0

    def test_20_pct(self):
        """LR=20% → λ = -ln(0.8)/ln(2) ≈ 0.3219."""
        expected = -math.log(0.8) / math.log(2.0)
        assert _lr_to_exponent(0.20) == pytest.approx(expected, rel=1e-6)

    def test_10_pct(self):
        """LR=10% → λ ≈ 0.1520."""
        expected = -math.log(0.9) / math.log(2.0)
        assert _lr_to_exponent(0.10) == pytest.approx(expected, rel=1e-6)

    def test_roundtrip(self):
        """λ → LR → λ roundtrip: LR = 1 - 2^(-λ)."""
        for lr in [0.05, 0.10, 0.15, 0.20, 0.30]:
            lam = _lr_to_exponent(lr)
            lr_back = 1.0 - 2.0 ** (-lam)
            assert lr_back == pytest.approx(lr, rel=1e-10)


# ===========================================================================
# TechChange construction
# ===========================================================================

class TestTechChangeInit:
    def test_default_config(self):
        tc = TechChange()
        assert tc.cost_floor_fraction == 0.20
        assert tc.knowledge_depreciation == 0.10
        assert tc.exogenous_rnd is True
        assert tc.tech_names == []

    def test_custom_config(self):
        cfg = LearningConfig(
            cost_floor_fraction=0.30,
            knowledge_depreciation=0.15,
            exogenous_rnd=False,
        )
        tc = TechChange(cfg)
        assert tc.cost_floor_fraction == 0.30
        assert tc.knowledge_depreciation == 0.15
        assert tc.exogenous_rnd is False


# ===========================================================================
# Registration
# ===========================================================================

class TestRegister:
    def setup_method(self):
        self.tc = TechChange()

    def test_basic_registration(self):
        self.tc.register("solar", capex_0=1000.0, cumulative_0=500.0, lbd_rate=0.20)
        assert "solar" in self.tc.tech_names
        assert self.tc.get_capex("solar") == 1000.0
        assert self.tc.get_cumulative("solar") == 500.0

    def test_floor_from_default_table(self):
        """Solar should use DEFAULT_FLOOR_FRACTIONS['solar'] = 0.15."""
        self.tc.register("solar", capex_0=1000.0, cumulative_0=100.0)
        params = self.tc._params["solar"]
        assert params.floor == pytest.approx(1000.0 * 0.15)

    def test_floor_explicit(self):
        self.tc.register(
            "solar", capex_0=1000.0, cumulative_0=100.0, floor_fraction=0.25,
        )
        params = self.tc._params["solar"]
        assert params.floor == pytest.approx(250.0)

    def test_floor_global_default(self):
        """Unknown tech uses global cost_floor_fraction from config."""
        self.tc.register("mystery_tech", capex_0=800.0, cumulative_0=50.0)
        params = self.tc._params["mystery_tech"]
        assert params.floor == pytest.approx(800.0 * 0.20)

    def test_cumulative_0_floor(self):
        """Cumulative_0 is floored at 1e-6 to avoid division by zero."""
        self.tc.register("new_tech", capex_0=500.0, cumulative_0=0.0)
        assert self.tc._params["new_tech"].cumulative_0 == pytest.approx(1e-6)

    def test_knowledge_0_default(self):
        self.tc.register("wind", capex_0=1200.0, cumulative_0=300.0)
        # Default knowledge_0=1.0, max(1.0, 1e-6) = 1.0
        assert self.tc._params["wind"].knowledge_0 == pytest.approx(1.0)
        assert self.tc.get_knowledge("wind") == 1.0

    def test_knowledge_0_custom(self):
        self.tc.register(
            "wind", capex_0=1200.0, cumulative_0=300.0, knowledge_0=5.0,
        )
        assert self.tc.get_knowledge("wind") == 5.0

    def test_lbd_exponent_stored(self):
        self.tc.register("solar", capex_0=1000.0, cumulative_0=500.0, lbd_rate=0.20)
        expected = -math.log(0.8) / math.log(2.0)
        assert self.tc._params["solar"].lbd_exponent == pytest.approx(expected)

    def test_rnd_exponent_stored(self):
        self.tc.register(
            "solar", capex_0=1000.0, cumulative_0=500.0, rnd_rate=0.15,
        )
        expected = -math.log(0.85) / math.log(2.0)
        assert self.tc._params["solar"].rnd_exponent == pytest.approx(expected)

    def test_no_learning(self):
        """Zero learning rates → zero exponents."""
        self.tc.register("fossil", capex_0=800.0, cumulative_0=1000.0)
        assert self.tc._params["fossil"].lbd_exponent == 0.0
        assert self.tc._params["fossil"].rnd_exponent == 0.0


# ===========================================================================
# Spillovers
# ===========================================================================

class TestSpillovers:
    def setup_method(self):
        self.tc = TechChange()
        self.tc.register("wind", capex_0=1200.0, cumulative_0=800.0, lbd_rate=0.10)
        self.tc.register(
            "wind_offshore", capex_0=3000.0, cumulative_0=100.0, lbd_rate=0.15,
        )

    def test_set_spillover(self):
        self.tc.set_spillover("wind", "wind_offshore", 0.5)
        q_eff = self.tc.effective_cumulative("wind_offshore")
        assert q_eff == pytest.approx(100.0 + 0.5 * 800.0)

    def test_no_spillover(self):
        """Without spillovers, effective = own cumulative."""
        q_eff = self.tc.effective_cumulative("wind")
        assert q_eff == pytest.approx(800.0)

    def test_bidirectional_spillover(self):
        self.tc.set_spillover("wind", "wind_offshore", 0.5)
        self.tc.set_spillover("wind_offshore", "wind", 0.5)
        q_wind = self.tc.effective_cumulative("wind")
        q_off = self.tc.effective_cumulative("wind_offshore")
        assert q_wind == pytest.approx(800.0 + 0.5 * 100.0)
        assert q_off == pytest.approx(100.0 + 0.5 * 800.0)

    def test_load_default_spillovers(self):
        self.tc.load_default_spillovers()
        # Wind → wind_offshore should be set
        q_eff = self.tc.effective_cumulative("wind_offshore")
        assert q_eff > 100.0  # gained from wind spillover

    def test_design_doc_example(self):
        """§3.5 example: Wind onshore 800 GW + offshore 100 GW, φ=0.5."""
        self.tc.set_spillover("wind", "wind_offshore", 0.5)
        self.tc.set_spillover("wind_offshore", "wind", 0.5)
        assert self.tc.effective_cumulative("wind") == pytest.approx(850.0)
        assert self.tc.effective_cumulative("wind_offshore") == pytest.approx(500.0)

    def test_unregistered_from_tech_ignored(self):
        """Spillover from unregistered tech is silently ignored."""
        self.tc.set_spillover("nonexistent", "wind", 0.5)
        q_eff = self.tc.effective_cumulative("wind")
        assert q_eff == pytest.approx(800.0)  # no change

    def test_effective_cumulative_unregistered_tech(self):
        assert self.tc.effective_cumulative("nonexistent") == 0.0


# ===========================================================================
# Default data tables
# ===========================================================================

class TestDefaultTables:
    def test_spillover_symmetry(self):
        """All default spillovers should be symmetric: φ_ij = φ_ji."""
        for tech, targets in DEFAULT_SPILLOVERS.items():
            for target, phi in targets.items():
                reverse = DEFAULT_SPILLOVERS.get(target, {}).get(tech)
                assert reverse is not None, (
                    f"Missing reverse spillover: {target} → {tech}"
                )
                assert reverse == phi, (
                    f"Asymmetric spillover: {tech}→{target}={phi}, "
                    f"{target}→{tech}={reverse}"
                )

    def test_floor_fractions_in_range(self):
        for tech, f in DEFAULT_FLOOR_FRACTIONS.items():
            assert 0.0 < f < 1.0, f"{tech} floor fraction {f} out of range"

    def test_rnd_rates_in_range(self):
        for tech, r in DEFAULT_RND_RATES.items():
            assert 0.0 < r < 1.0, f"{tech} RND rate {r} out of range"

    def test_ccs_family_complete(self):
        """CCS family should have full cross-spillover."""
        ccs_techs = ["coal_ccs", "gas_ccs", "biomass_ccs"]
        for t in ccs_techs:
            assert t in DEFAULT_SPILLOVERS
            for other in ccs_techs:
                if other != t:
                    assert other in DEFAULT_SPILLOVERS[t]


# ===========================================================================
# compute_capex — LBD only
# ===========================================================================

class TestComputeCapexLBD:
    def setup_method(self):
        self.tc = TechChange()
        self.tc.register(
            "solar", capex_0=1000.0, cumulative_0=100.0, lbd_rate=0.20,
        )

    def test_no_deployment_no_reduction(self):
        """At base cumulative, ratio=1 → no cost change."""
        capex = self.tc.compute_capex("solar")
        assert capex == pytest.approx(1000.0)

    def test_doubling_gives_lr(self):
        """Doubling cumulative → 20% cost reduction (LR=0.20)."""
        self.tc.update_deployment({"solar": 100.0})  # 100→200
        capex = self.tc.compute_capex("solar")
        assert capex == pytest.approx(800.0, rel=1e-3)

    def test_quadrupling(self):
        """4x cumulative = 2 doublings → (0.8)^2 = 0.64."""
        self.tc.update_deployment({"solar": 300.0})  # 100→400
        capex = self.tc.compute_capex("solar")
        assert capex == pytest.approx(1000.0 * 0.64, rel=1e-3)

    def test_floor_binding(self):
        """Massive deployment should not go below floor."""
        self.tc.update_deployment({"solar": 1e9})
        capex = self.tc.compute_capex("solar")
        floor = self.tc._params["solar"].floor
        assert capex == pytest.approx(floor)
        assert capex >= floor

    def test_zero_lbd_rate(self):
        self.tc.register("fossil", capex_0=800.0, cumulative_0=1000.0)
        self.tc.update_deployment({"fossil": 5000.0})
        capex = self.tc.compute_capex("fossil")
        assert capex == pytest.approx(800.0)

    def test_current_capex_updated(self):
        """compute_capex should update state.current_capex."""
        self.tc.update_deployment({"solar": 100.0})
        self.tc.compute_capex("solar")
        assert self.tc.get_capex("solar") == pytest.approx(800.0, rel=1e-3)


# ===========================================================================
# compute_capex — RND only
# ===========================================================================

class TestComputeCapexRND:
    def setup_method(self):
        self.tc = TechChange()
        self.tc.register(
            "solar", capex_0=1000.0, cumulative_0=100.0,
            lbd_rate=0.0, rnd_rate=0.15, knowledge_0=1.0,
        )

    def test_no_rnd_no_reduction(self):
        """At base knowledge, ratio=1 → no RND cost change."""
        capex = self.tc.compute_capex("solar")
        assert capex == pytest.approx(1000.0)

    def test_rnd_doubling(self):
        """Doubling knowledge stock → 15% cost reduction."""
        # Need knowledge to double: H = (1-0.1)*1.0 + rnd = 2.0 → rnd = 1.1
        self.tc.update_knowledge({"solar": 1.1})
        capex = self.tc.compute_capex("solar")
        expected = 1000.0 * (2.0 ** (-_lr_to_exponent(0.15)))
        assert capex == pytest.approx(expected, rel=1e-3)

    def test_rnd_with_depreciation(self):
        """Knowledge depreciates: H = (1-δ)*H + RND."""
        self.tc.update_knowledge({"solar": 0.5})
        k = self.tc.get_knowledge("solar")
        expected_k = 0.9 * 1.0 + 0.5  # (1-0.1)*1.0 + 0.5 = 1.4
        assert k == pytest.approx(expected_k)


# ===========================================================================
# compute_capex — LBD + RND combined
# ===========================================================================

class TestComputeCapexCombined:
    def setup_method(self):
        self.tc = TechChange()
        self.tc.register(
            "solar", capex_0=1000.0, cumulative_0=100.0,
            lbd_rate=0.20, rnd_rate=0.15, knowledge_0=1.0,
        )

    def test_both_factors(self):
        """Cost = capex_0 × LBD_factor × RND_factor."""
        self.tc.update_deployment({"solar": 100.0})  # double cumulative
        self.tc.update_knowledge({"solar": 1.1})      # double knowledge
        capex = self.tc.compute_capex("solar")

        lbd_factor = 2.0 ** (-_lr_to_exponent(0.20))  # 0.8
        rnd_factor = 2.0 ** (-_lr_to_exponent(0.15))  # 0.85
        expected = 1000.0 * lbd_factor * rnd_factor
        assert capex == pytest.approx(expected, rel=1e-3)

    def test_floor_binds_combined(self):
        """Floor applies after both factors."""
        self.tc.update_deployment({"solar": 1e9})
        self.tc.update_knowledge({"solar": 1e6})
        capex = self.tc.compute_capex("solar")
        assert capex == self.tc._params["solar"].floor

    def test_spillover_affects_capex(self):
        """Spillover from related tech should lower capex."""
        self.tc.register(
            "solar_csp", capex_0=5000.0, cumulative_0=10.0, lbd_rate=0.15,
        )
        self.tc.update_deployment({"solar_csp": 100.0})  # 10→110

        # Without spillover
        capex_no_spill = self.tc.compute_capex("solar")

        # With spillover
        self.tc.set_spillover("solar_csp", "solar", 0.2)
        capex_with_spill = self.tc.compute_capex("solar")

        # Spillover should lower solar capex (more effective cumulative)
        # Only matters if solar has grown too (ratio > 1 needed)
        self.tc.update_deployment({"solar": 100.0})  # 100→200
        capex_no_spill2 = 1000.0 * ((200.0 / 100.0) ** (-_lr_to_exponent(0.20)))
        capex_with_spill2 = self.tc.compute_capex("solar")
        # Effective = 200 + 0.2*110 = 222
        expected = 1000.0 * ((222.0 / 100.0) ** (-_lr_to_exponent(0.20)))
        assert capex_with_spill2 == pytest.approx(expected, rel=1e-2)


# ===========================================================================
# compute_capex — edge cases
# ===========================================================================

class TestComputeCapexEdge:
    def test_unregistered_tech(self):
        tc = TechChange()
        assert tc.compute_capex("nonexistent") == 0.0

    def test_get_capex_unregistered(self):
        tc = TechChange()
        assert tc.get_capex("nonexistent") == 0.0

    def test_get_cumulative_unregistered(self):
        tc = TechChange()
        assert tc.get_cumulative("nonexistent") == 0.0

    def test_get_knowledge_unregistered(self):
        tc = TechChange()
        assert tc.get_knowledge("nonexistent") == 0.0

    def test_monotonic_decrease(self):
        """Capex should monotonically decrease with deployment."""
        tc = TechChange()
        tc.register("solar", capex_0=1000.0, cumulative_0=100.0, lbd_rate=0.20)
        prev = tc.compute_capex("solar")
        for _ in range(10):
            tc.update_deployment({"solar": 50.0})
            cur = tc.compute_capex("solar")
            assert cur <= prev
            prev = cur


# ===========================================================================
# update_deployment
# ===========================================================================

class TestUpdateDeployment:
    def setup_method(self):
        self.tc = TechChange()
        self.tc.register("solar", capex_0=1000.0, cumulative_0=100.0)
        self.tc.register("wind", capex_0=1200.0, cumulative_0=300.0)

    def test_add_deployment(self):
        self.tc.update_deployment({"solar": 50.0, "wind": 30.0})
        assert self.tc.get_cumulative("solar") == pytest.approx(150.0)
        assert self.tc.get_cumulative("wind") == pytest.approx(330.0)

    def test_ignore_negative(self):
        """Negative deployment should not reduce cumulative."""
        self.tc.update_deployment({"solar": -10.0})
        assert self.tc.get_cumulative("solar") == pytest.approx(100.0)

    def test_ignore_zero(self):
        self.tc.update_deployment({"solar": 0.0})
        assert self.tc.get_cumulative("solar") == pytest.approx(100.0)

    def test_ignore_unregistered(self):
        """Deployment for unregistered tech is silently ignored."""
        self.tc.update_deployment({"mystery": 100.0})
        assert "mystery" not in self.tc.tech_names

    def test_accumulate_multiple_periods(self):
        self.tc.update_deployment({"solar": 50.0})
        self.tc.update_deployment({"solar": 50.0})
        self.tc.update_deployment({"solar": 50.0})
        assert self.tc.get_cumulative("solar") == pytest.approx(250.0)


# ===========================================================================
# update_knowledge
# ===========================================================================

class TestUpdateKnowledge:
    def setup_method(self):
        self.tc = TechChange()
        self.tc.register(
            "solar", capex_0=1000.0, cumulative_0=100.0, knowledge_0=1.0,
        )
        self.tc.register(
            "wind", capex_0=1200.0, cumulative_0=300.0, knowledge_0=2.0,
        )

    def test_knowledge_with_rnd(self):
        """H(t+1) = (1-δ)*H(t) + RND."""
        self.tc.update_knowledge({"solar": 0.5})
        expected = 0.9 * 1.0 + 0.5
        assert self.tc.get_knowledge("solar") == pytest.approx(expected)

    def test_knowledge_no_rnd(self):
        """Without RND spending, knowledge depreciates only."""
        self.tc.update_knowledge({})
        expected = 0.9 * 1.0
        assert self.tc.get_knowledge("solar") == pytest.approx(expected)

    def test_multiple_techs(self):
        self.tc.update_knowledge({"solar": 0.5, "wind": 1.0})
        assert self.tc.get_knowledge("solar") == pytest.approx(0.9 * 1.0 + 0.5)
        assert self.tc.get_knowledge("wind") == pytest.approx(0.9 * 2.0 + 1.0)

    def test_knowledge_accumulates(self):
        """Multiple periods of RND investment."""
        for _ in range(5):
            self.tc.update_knowledge({"solar": 0.2})

        # H_0=1, each step: H = 0.9*H + 0.2
        h = 1.0
        for _ in range(5):
            h = 0.9 * h + 0.2
        assert self.tc.get_knowledge("solar") == pytest.approx(h)

    def test_custom_depreciation(self):
        cfg = LearningConfig(knowledge_depreciation=0.20)
        tc = TechChange(cfg)
        tc.register("solar", capex_0=1000.0, cumulative_0=100.0, knowledge_0=1.0)
        tc.update_knowledge({"solar": 0.5})
        expected = 0.8 * 1.0 + 0.5
        assert tc.get_knowledge("solar") == pytest.approx(expected)


# ===========================================================================
# compute_all_capex
# ===========================================================================

class TestComputeAllCapex:
    def test_returns_all_techs(self):
        tc = TechChange()
        tc.register("solar", capex_0=1000.0, cumulative_0=100.0, lbd_rate=0.20)
        tc.register("wind", capex_0=1200.0, cumulative_0=300.0, lbd_rate=0.10)
        result = tc.compute_all_capex()
        assert "solar" in result
        assert "wind" in result
        assert len(result) == 2

    def test_matches_individual(self):
        tc = TechChange()
        tc.register("solar", capex_0=1000.0, cumulative_0=100.0, lbd_rate=0.20)
        tc.register("wind", capex_0=1200.0, cumulative_0=300.0, lbd_rate=0.10)
        tc.update_deployment({"solar": 100.0, "wind": 300.0})

        all_capex = tc.compute_all_capex()
        for tech in ["solar", "wind"]:
            individual = tc.compute_capex(tech)
            assert all_capex[tech] == pytest.approx(individual)


# ===========================================================================
# register_from_technologies (bulk helper)
# ===========================================================================

class TestRegisterFromTechnologies:
    def test_from_tech_objects(self):
        """Register from mock Technology-like objects."""

        class MockTech:
            def __init__(self, name, capital_cost, base_cumulative, learning_rate):
                self.name = name
                self.capital_cost = capital_cost
                self.base_cumulative = base_cumulative
                self.learning_rate = learning_rate

        techs = [
            MockTech("solar", 1000.0, 500.0, 0.20),
            MockTech("wind", 1200.0, 300.0, 0.10),
        ]
        tc = TechChange()
        tc.register_from_technologies(techs)

        assert "solar" in tc.tech_names
        assert "wind" in tc.tech_names
        assert tc.get_capex("solar") == pytest.approx(1000.0)
        assert tc.get_capex("wind") == pytest.approx(1200.0)

    def test_override_lbd_rates(self):
        class MockTech:
            def __init__(self, name, capital_cost):
                self.name = name
                self.capital_cost = capital_cost
                self.base_cumulative = 100.0

        techs = [MockTech("solar", 1000.0)]
        tc = TechChange()
        tc.register_from_technologies(techs, lbd_rates={"solar": 0.25})

        expected = _lr_to_exponent(0.25)
        assert tc._params["solar"].lbd_exponent == pytest.approx(expected)

    def test_exogenous_rnd_disables_rnd(self):
        """When exogenous_rnd=True (Phase 1 default), rnd_rate=0."""

        class MockTech:
            def __init__(self, name, capital_cost):
                self.name = name
                self.capital_cost = capital_cost
                self.base_cumulative = 100.0

        # exogenous_rnd=True → rnd_rate passed as 0.0
        tc = TechChange(LearningConfig(exogenous_rnd=True))
        techs = [MockTech("solar", 1000.0)]
        tc.register_from_technologies(techs)
        assert tc._params["solar"].rnd_exponent == 0.0

    def test_endogenous_rnd_uses_defaults(self):
        """When exogenous_rnd=False, DEFAULT_RND_RATES are used."""

        class MockTech:
            def __init__(self, name, capital_cost):
                self.name = name
                self.capital_cost = capital_cost
                self.base_cumulative = 100.0

        tc = TechChange(LearningConfig(exogenous_rnd=False))
        techs = [MockTech("solar", 1000.0)]
        tc.register_from_technologies(techs)
        expected = _lr_to_exponent(DEFAULT_RND_RATES["solar"])
        assert tc._params["solar"].rnd_exponent == pytest.approx(expected)


# ===========================================================================
# Integration: multi-period learning trajectory
# ===========================================================================

class TestLearningTrajectory:
    def test_solar_30yr_trajectory(self):
        """Solar PV: 20% LR, 6 periods of 100 GW each → predictable decline."""
        tc = TechChange()
        tc.register("solar", capex_0=1000.0, cumulative_0=100.0, lbd_rate=0.20)

        trajectory = [tc.compute_capex("solar")]
        for _ in range(6):
            tc.update_deployment({"solar": 100.0})
            trajectory.append(tc.compute_capex("solar"))

        # Each capex should be ≤ previous (monotonic decrease)
        for i in range(1, len(trajectory)):
            assert trajectory[i] <= trajectory[i - 1]

        # Final capex: cum = 700, ratio = 7.0
        lam = _lr_to_exponent(0.20)
        expected_final = max(1000.0 * (7.0 ** (-lam)), 1000.0 * 0.15)
        assert trajectory[-1] == pytest.approx(expected_final, rel=1e-3)

    def test_lbd_rnd_trajectory(self):
        """Combined LBD+RND over multiple periods."""
        tc = TechChange()
        tc.register(
            "solar", capex_0=1000.0, cumulative_0=100.0,
            lbd_rate=0.12, rnd_rate=0.15, knowledge_0=1.0,
        )

        trajectory = [tc.compute_capex("solar")]
        for _ in range(5):
            tc.update_deployment({"solar": 100.0})
            tc.update_knowledge({"solar": 0.3})
            trajectory.append(tc.compute_capex("solar"))

        # Monotonic decrease
        for i in range(1, len(trajectory)):
            assert trajectory[i] <= trajectory[i - 1]

        # Should be meaningfully cheaper after 5 periods
        assert trajectory[-1] < 0.9 * trajectory[0]

    def test_floor_eventually_reached(self):
        """With enough deployment, floor should bind."""
        tc = TechChange()
        tc.register("solar", capex_0=1000.0, cumulative_0=100.0, lbd_rate=0.20)

        for _ in range(50):
            tc.update_deployment({"solar": 1000.0})

        capex = tc.compute_capex("solar")
        floor = tc._params["solar"].floor
        assert capex == pytest.approx(floor)

    def test_spillover_accelerates_learning(self):
        """Tech with spillover learns faster than without."""
        # Without spillover
        tc1 = TechChange()
        tc1.register(
            "wind_offshore", capex_0=3000.0, cumulative_0=50.0, lbd_rate=0.15,
        )
        tc1.register("wind", capex_0=1200.0, cumulative_0=800.0, lbd_rate=0.10)

        # With spillover
        tc2 = TechChange()
        tc2.register(
            "wind_offshore", capex_0=3000.0, cumulative_0=50.0, lbd_rate=0.15,
        )
        tc2.register("wind", capex_0=1200.0, cumulative_0=800.0, lbd_rate=0.10)
        tc2.set_spillover("wind", "wind_offshore", 0.5)

        for _ in range(5):
            tc1.update_deployment({"wind": 100.0, "wind_offshore": 20.0})
            tc2.update_deployment({"wind": 100.0, "wind_offshore": 20.0})

        capex_no_spill = tc1.compute_capex("wind_offshore")
        capex_spill = tc2.compute_capex("wind_offshore")
        assert capex_spill < capex_no_spill
