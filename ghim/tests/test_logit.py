"""Tests for logit discrete choice."""

import numpy as np
import pytest

from ghim.energy.logit import (
    relative_cost_logit,
    absolute_cost_logit,
    logit_shares,
    logit_calibrate,
    logit_average_cost,
    relative_pref_logit,
    preference_calibrate,
    preference_decay,
)


class TestRelativeCostLogit:
    def test_shares_sum_to_one(self):
        costs = np.array([5.0, 10.0, 15.0])
        weights = np.array([1.0, 1.0, 1.0])
        shares = relative_cost_logit(costs, weights, logit_exp=-3.0)
        assert abs(shares.sum() - 1.0) < 1e-10

    def test_lower_cost_gets_higher_share(self):
        """With negative logit exponent, lower cost → higher share."""
        costs = np.array([5.0, 10.0])
        weights = np.array([1.0, 1.0])
        shares = relative_cost_logit(costs, weights, logit_exp=-3.0)
        assert shares[0] > shares[1]

    def test_more_negative_exp_more_concentrated(self):
        """More negative logit exp → shares more concentrated on cheapest."""
        costs = np.array([5.0, 10.0])
        weights = np.array([1.0, 1.0])
        shares_mild = relative_cost_logit(costs, weights, logit_exp=-1.0)
        shares_strong = relative_cost_logit(costs, weights, logit_exp=-6.0)
        # Strong should be more concentrated on first option
        assert shares_strong[0] > shares_mild[0]

    def test_single_technology(self):
        """Single technology should get 100% share."""
        shares = relative_cost_logit(np.array([5.0]), np.array([1.0]), -3.0)
        assert abs(shares[0] - 1.0) < 1e-10

    def test_equal_costs_equal_weights(self):
        """Equal costs and weights should give equal shares."""
        costs = np.array([5.0, 5.0, 5.0])
        weights = np.array([1.0, 1.0, 1.0])
        shares = relative_cost_logit(costs, weights, logit_exp=-3.0)
        np.testing.assert_allclose(shares, [1/3, 1/3, 1/3], atol=1e-10)


class TestAbsoluteCostLogit:
    def test_shares_sum_to_one(self):
        costs = np.array([5.0, 10.0, 15.0])
        weights = np.array([1.0, 1.0, 1.0])
        shares = absolute_cost_logit(costs, weights, logit_exp=-0.5)
        assert abs(shares.sum() - 1.0) < 1e-10


class TestLogitCalibrate:
    def test_roundtrip(self):
        """Calibrated weights should reproduce the original shares."""
        base_shares = np.array([0.5, 0.3, 0.2])
        base_costs = np.array([5.0, 8.0, 12.0])
        logit_exp = -3.0

        weights = logit_calibrate(base_shares, base_costs, logit_exp)
        recovered = relative_cost_logit(base_costs, weights, logit_exp)
        np.testing.assert_allclose(recovered, base_shares, atol=1e-6)

    def test_largest_weight_is_one(self):
        """GCAM convention: largest share weight = 1."""
        shares = np.array([0.6, 0.3, 0.1])
        costs = np.array([5.0, 8.0, 12.0])
        weights = logit_calibrate(shares, costs, logit_exp=-3.0)
        assert abs(weights.max() - 1.0) < 1e-10


class TestLogitAverageCost:
    def test_average_between_min_max(self):
        """Average cost should be between min and max individual costs."""
        costs = np.array([5.0, 10.0, 15.0])
        weights = np.array([1.0, 1.0, 1.0])
        avg = logit_average_cost(costs, weights, logit_exp=-3.0)
        assert 5.0 <= avg <= 15.0


class TestRelativePrefLogit:
    def test_shares_sum_to_one(self):
        costs = np.array([5.0, 10.0, 15.0])
        pf = np.array([0.0, 0.0, 0.0])
        shares = relative_pref_logit(costs, pf, scale_k=0.3, logit_exp=-4.0)
        assert abs(shares.sum() - 1.0) < 1e-10

    def test_lower_cost_higher_share(self):
        """With negative logit exp and equal PF, lower cost → higher share."""
        costs = np.array([5.0, 10.0])
        pf = np.array([0.0, 0.0])
        shares = relative_pref_logit(costs, pf, scale_k=0.3, logit_exp=-4.0)
        assert shares[0] > shares[1]

    def test_alpha_zero_produces_zero(self):
        """α=0 tech gets exactly zero share."""
        costs = np.array([5.0, 10.0, 15.0])
        pf = np.array([0.0, 0.0, 0.0])
        alpha = np.array([1.0, 0.0, 1.0])
        shares = relative_pref_logit(costs, pf, scale_k=0.3, logit_exp=-4.0, alpha=alpha)
        assert shares[1] == 0.0
        assert abs(shares.sum() - 1.0) < 1e-10

    def test_single_alpha_one(self):
        """Only one α=1 tech gets 100% share."""
        costs = np.array([5.0, 10.0, 15.0])
        pf = np.array([0.0, 0.0, 0.0])
        alpha = np.array([0.0, 1.0, 0.0])
        shares = relative_pref_logit(costs, pf, scale_k=0.3, logit_exp=-4.0, alpha=alpha)
        assert abs(shares[1] - 1.0) < 1e-10
        assert shares[0] == 0.0
        assert shares[2] == 0.0

    def test_reduces_to_relative_cost_when_pf_zero(self):
        """With all PF=0 and α=1, should match relative_cost_logit behavior."""
        costs = np.array([5.0, 10.0, 15.0])
        pf = np.zeros(3)
        shares_rp = relative_pref_logit(costs, pf, scale_k=0.3, logit_exp=-4.0)
        # relative_cost_logit with equal weights
        shares_rc = relative_cost_logit(costs, np.ones(3), logit_exp=-4.0)
        np.testing.assert_allclose(shares_rp, shares_rc, atol=1e-10)

    def test_pref_penalty_reduces_share(self):
        """Positive PF (penalty) should reduce share."""
        costs = np.array([5.0, 5.0])
        pf_neutral = np.array([0.0, 0.0])
        pf_penalty = np.array([0.0, 5.0])
        shares_n = relative_pref_logit(costs, pf_neutral, 0.3, -4.0)
        shares_p = relative_pref_logit(costs, pf_penalty, 0.3, -4.0)
        # With penalty on tech 1, its share should be lower
        assert shares_p[1] < shares_n[1]

    def test_logit_shares_mode_relative_pref(self):
        """logit_shares(mode='relative_pref') dispatches correctly."""
        costs = np.array([5.0, 10.0])
        pf = np.array([0.0, 1.0])
        direct = relative_pref_logit(costs, pf, 0.3, -4.0)
        via_dispatch = logit_shares(
            costs, pref_factors=pf, scale_k=0.3, logit_exp=-4.0,
            mode="relative_pref",
        )
        np.testing.assert_allclose(direct, via_dispatch, atol=1e-10)

    def test_all_alpha_zero_returns_uniform(self):
        """All α=0 returns uniform shares (degenerate case)."""
        costs = np.array([5.0, 10.0])
        pf = np.array([0.0, 0.0])
        alpha = np.array([0.0, 0.0])
        shares = relative_pref_logit(costs, pf, 0.3, -4.0, alpha=alpha)
        np.testing.assert_allclose(shares, [0.5, 0.5], atol=1e-10)


class TestRelativePrefCalibration:
    def test_roundtrip(self):
        """Calibrate → compute should reproduce base shares."""
        base_shares = np.array([0.5, 0.3, 0.15, 0.05])
        base_costs = np.array([5.0, 8.0, 12.0, 20.0])
        scale_k = 0.3
        logit_exp = -4.0

        pf = preference_calibrate(base_shares, base_costs, scale_k, logit_exp=logit_exp)
        recovered = relative_pref_logit(base_costs, pf, scale_k, logit_exp)
        np.testing.assert_allclose(recovered, base_shares, atol=1e-6)

    def test_reference_pf_zero(self):
        """Reference tech (largest share) should have PF=0."""
        base_shares = np.array([0.6, 0.3, 0.1])
        base_costs = np.array([5.0, 8.0, 12.0])
        pf = preference_calibrate(base_shares, base_costs, 0.3, logit_exp=-4.0)
        ref = int(np.argmax(base_shares))
        assert abs(pf[ref]) < 1e-10

    def test_backward_compat_absolute(self):
        """Without logit_exp, preference_calibrate uses absolute mode."""
        base_shares = np.array([0.5, 0.3, 0.2])
        base_costs = np.array([5.0, 8.0, 12.0])
        # This is the old behavior — should not raise
        pf = preference_calibrate(base_shares, base_costs, 0.3)
        assert pf is not None and len(pf) == 3

    def test_decay_reduces_pf(self):
        """preference_decay reduces PF magnitude toward zero."""
        pf = np.array([0.0, 2.0, -1.0])
        decayed = preference_decay(pf, years_elapsed=10, decay_rate=0.03)
        for i in range(len(pf)):
            assert abs(decayed[i]) <= abs(pf[i]) + 1e-10
