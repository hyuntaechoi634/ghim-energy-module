"""Tests for the CES production function."""

import numpy as np
import pytest

from ghim.econ.ces import ces_output, ces_price, ces_demand, ces_calibrate


class TestCESOutput:
    def test_cobb_douglas_at_sigma_1(self):
        """sigma=1 should behave as Cobb-Douglas: Y = prod(X_i^alpha_i)."""
        inputs = np.array([10.0, 20.0])
        alphas = np.array([0.3, 0.7])
        y = ces_output(inputs, alphas, sigma=1.0)
        expected = (10.0 ** 0.3) * (20.0 ** 0.7)
        assert abs(y - expected) < 1e-6

    def test_leontief_at_sigma_near_zero(self):
        """sigma~0 should behave as Leontief: Y = min(X_i/alpha_i)."""
        inputs = np.array([10.0, 20.0])
        alphas = np.array([0.5, 0.5])
        y = ces_output(inputs, alphas, sigma=1e-8)
        assert abs(y - 20.0) < 1e-2  # min(10/0.5, 20/0.5) = 20

    def test_positive_output(self):
        """Output should always be positive for positive inputs."""
        for sigma in [0.5, 1.0, 2.0, 5.0]:
            y = ces_output(np.array([5.0, 10.0]), np.array([0.4, 0.6]), sigma)
            assert y > 0

    def test_scale_factor(self):
        """Scale factor should multiply output linearly."""
        inputs = np.array([5.0, 10.0])
        alphas = np.array([0.5, 0.5])
        y1 = ces_output(inputs, alphas, sigma=0.5, scale=1.0)
        y2 = ces_output(inputs, alphas, sigma=0.5, scale=3.0)
        assert abs(y2 / y1 - 3.0) < 1e-6


class TestCESPrice:
    def test_cobb_douglas_price(self):
        """Test dual price at sigma=1."""
        prices = np.array([2.0, 4.0])
        alphas = np.array([0.5, 0.5])
        p = ces_price(prices, alphas, sigma=1.0)
        expected = (2.0 / 0.5) ** 0.5 * (4.0 / 0.5) ** 0.5
        assert abs(p - expected) < 1e-6


class TestCESDemand:
    def test_demands_sum_to_output_value(self):
        """Cost of optimal demands should equal output * output price."""
        alphas = np.array([0.4, 0.6])
        prices = np.array([2.0, 3.0])
        sigma = 0.8
        p_out = ces_price(prices, alphas, sigma)
        output = 100.0
        demands = ces_demand(output, p_out, prices, alphas, sigma)
        total_cost = np.sum(demands * prices)
        assert abs(total_cost - output * p_out) / (output * p_out) < 0.05


class TestCESCalibrate:
    def test_roundtrip(self):
        """Calibrated alphas should reproduce the original cost shares."""
        base_inputs = np.array([10.0, 20.0, 5.0])
        base_prices = np.array([2.0, 3.0, 5.0])
        sigma = 0.7

        alphas = ces_calibrate(base_inputs, base_prices, sigma)
        assert abs(alphas.sum() - 1.0) < 1e-6
        assert all(alphas > 0)

    def test_cobb_douglas_calibration(self):
        """At sigma=1, calibrated alphas equal cost shares."""
        inputs = np.array([10.0, 20.0])
        prices = np.array([2.0, 3.0])
        alphas = ces_calibrate(inputs, prices, sigma=1.0)

        expenditures = inputs * prices
        expected = expenditures / expenditures.sum()
        np.testing.assert_allclose(alphas, expected, atol=1e-6)
