"""Tests for logit discrete choice."""

import numpy as np
import pytest

from ghim.energy.logit import (
    relative_cost_logit,
    absolute_cost_logit,
    logit_shares,
    logit_calibrate,
    logit_average_cost,
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
