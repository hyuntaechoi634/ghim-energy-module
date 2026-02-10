"""Tests for demand tree with α and PF(t) support."""

import numpy as np
import pytest

from ghim.energy.demand import (
    DemandNode, DemandLeaf, FinalDemand,
    _make_fuel_node, ENERGY_CARRIERS,
)


def _simple_tree() -> DemandNode:
    """Simple 2-carrier demand node for testing."""
    children = [
        DemandLeaf("elec_leaf", "electricity"),
        DemandLeaf("gas_leaf", "gas"),
    ]
    return DemandNode(
        "test_node", children,
        base_shares={"elec_leaf": 0.6, "gas_leaf": 0.4},
        scale_k=0.3,
        turnover_time=30.0,
    )


class TestDemandNodeAlpha:
    def test_carrier_demands_sum_to_total(self):
        """Carrier demands should sum to total."""
        tree = _simple_tree()
        prices = {"electricity": 20.0, "gas": 4.0}
        tree.calibrate(prices)
        demands = tree.compute_carrier_demands(10.0, prices, year=2020)
        total = sum(demands.values())
        assert abs(total - 10.0) < 1e-6

    def test_alpha_zero_carrier_gets_zero(self):
        """α=0 carrier should get zero demand."""
        tree = _simple_tree()
        prices = {"electricity": 20.0, "gas": 4.0}
        tree.calibrate(prices)
        # Disable gas
        demands = tree.compute_carrier_demands(
            10.0, prices, year=2025,
            alpha_map={"elec_leaf": 1.0, "gas_leaf": 0.0},
        )
        # Gas share in target should be 0 (stock turnover still blends)
        # After first period with α=0, gas target = 0 but stock keeps some
        # Second call to let turnover take effect
        demands = tree.compute_carrier_demands(
            10.0, prices, year=2030,
            alpha_map={"elec_leaf": 1.0, "gas_leaf": 0.0},
        )
        # With many periods of α=0, gas should approach 0
        for _ in range(20):
            demands = tree.compute_carrier_demands(
                10.0, prices, year=2050,
                alpha_map={"elec_leaf": 1.0, "gas_leaf": 0.0},
            )
        assert demands.get("gas", 0.0) < 0.5  # should be very small

    def test_pf_override_shifts_shares(self):
        """PF override should shift shares away from penalized carrier.

        Uses equal-cost carriers so the PF effect is visible through
        stock turnover.
        """
        children = [
            DemandLeaf("a_leaf", "electricity"),
            DemandLeaf("b_leaf", "gas"),
        ]
        tree = DemandNode(
            "test", children,
            base_shares={"a_leaf": 0.5, "b_leaf": 0.5},
            scale_k=0.3, turnover_time=10.0,
        )
        prices = {"electricity": 10.0, "gas": 10.0}
        tree.calibrate(prices)

        # Run several periods with no override
        for yr in range(2025, 2100, 5):
            d_base = tree.compute_carrier_demands(10.0, prices, year=yr)

        # Reset and apply penalty on b_leaf
        tree2 = DemandNode(
            "test", [
                DemandLeaf("a_leaf", "electricity"),
                DemandLeaf("b_leaf", "gas"),
            ],
            base_shares={"a_leaf": 0.5, "b_leaf": 0.5},
            scale_k=0.3, turnover_time=10.0,
        )
        tree2.calibrate(prices)
        for yr in range(2025, 2100, 5):
            d_penalized = tree2.compute_carrier_demands(
                10.0, prices, year=yr,
                pref_override_map={"b_leaf": 10.0},
            )
        # Gas (b_leaf) should have lower share with penalty
        assert d_penalized.get("gas", 0.0) < d_base.get("gas", 0.0)

    def test_year_passthrough(self):
        """Year parameter should be accepted without error."""
        tree = _simple_tree()
        prices = {"electricity": 20.0, "gas": 4.0}
        tree.calibrate(prices)
        # Should not raise
        demands = tree.compute_carrier_demands(10.0, prices, year=2050)
        assert sum(demands.values()) > 0


class TestFinalDemandAlpha:
    def test_compute_demand_with_year(self):
        """FinalDemand.compute_demand should accept year parameter."""
        fd = FinalDemand("industry", base_demand_ej=10.0)
        prices = {
            "coal": 2.5, "gas": 4.0, "electricity": 20.0,
            "refined liquids": 12.0, "biomass": 3.0, "hydrogen": 15.0,
        }
        fd.calibrate(prices, base_gdp=1000.0)
        demands = fd.compute_demand(1000.0, prices, year=2025)
        assert sum(demands.values()) > 0
