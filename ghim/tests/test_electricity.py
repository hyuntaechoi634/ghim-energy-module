"""Tests for electricity sector model."""

import numpy as np
import pytest

from ghim.energy.electricity import ElectricitySector
from ghim.energy.technology import Technology, default_electricity_techs


class TestElectricitySector:
    def setup_method(self):
        self.sector = ElectricitySector()
        self.fuel_prices = {
            "coal": 2.5, "gas": 4.0, "nuclear": 0.7,
            "hydro": 0.0, "wind": 0.0, "solar": 0.0,
            "biomass": 3.0, "refined liquids": 12.0,
        }

    def test_supply_sums_to_demand(self):
        demand_ej = 10.0
        gen = self.sector.compute_supply(self.fuel_prices, demand_ej)
        total = sum(gen.values())
        assert abs(total - demand_ej) < 1e-6

    def test_all_techs_get_some_share(self):
        gen = self.sector.compute_supply(self.fuel_prices, 10.0)
        for tech_name, ej in gen.items():
            assert ej >= 0

    def test_fuel_consumption_positive(self):
        gen = self.sector.compute_supply(self.fuel_prices, 10.0)
        consumption = self.sector.fuel_consumption(gen)
        for fuel, ej in consumption.items():
            assert ej >= 0

    def test_calibration_reproduces_shares(self):
        base_shares = {"coal": 0.4, "gas_cc": 0.3, "nuclear": 0.15,
                       "hydro": 0.05, "wind": 0.05, "solar": 0.02,
                       "biomass": 0.02, "oil": 0.01}
        self.sector.calibrate(base_shares, self.fuel_prices)
        gen = self.sector.compute_supply(self.fuel_prices, 10.0)
        total = sum(gen.values())
        for tech, expected_share in base_shares.items():
            actual_share = gen[tech] / total
            # After calibration, shares should be close to target
            assert abs(actual_share - expected_share) < 0.05, \
                f"{tech}: expected {expected_share:.3f}, got {actual_share:.3f}"

    def test_emissions_from_fossil(self):
        gen = self.sector.compute_supply(self.fuel_prices, 10.0)
        emissions = self.sector.emissions_mtc(gen)
        assert emissions > 0  # Should have some fossil generation

    def test_weighted_cost_positive(self):
        cost = self.sector.weighted_cost(self.fuel_prices)
        assert cost > 0


class TestTechnology:
    def test_levelized_cost_positive(self):
        for tech in default_electricity_techs():
            cost = tech.levelized_cost(3.0)
            assert cost > 0, f"{tech.name} has non-positive LCOE"

    def test_zero_fuel_cost_renewable(self):
        """Wind/solar with zero fuel price should still have positive LCOE (capital)."""
        for tech in default_electricity_techs():
            if tech.fuel_input in ("wind", "solar", "hydro"):
                cost = tech.levelized_cost(0.0)
                assert cost > 0
