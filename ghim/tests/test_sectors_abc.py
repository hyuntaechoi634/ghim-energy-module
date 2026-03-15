"""Tests for sector ABCs, Subsector, AgricultureSector, RefinedOilSector."""

import numpy as np
import pytest

from ghim.core.carrier import CARBON_COEFS, TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import EndUseTech, SupplyTech
from ghim.sectors.abc import (
    Subsector,
    DemandSector,
    TransformationSector,
    CARRIER_PREF_DECAY,
)
from ghim.sectors.agriculture import AgricultureSector
from ghim.sectors.refining import RefinedOilSector


# ===========================================================================
# Subsector
# ===========================================================================

class TestSubsector:
    def setup_method(self):
        self.sub = Subsector("test", [
            EndUseTech(carrier="electricity"),
            EndUseTech(carrier="gas"),
            EndUseTech(carrier="coal"),
        ])

    def test_compute_shares_sum_to_one(self):
        prices = {"electricity": 20.0, "gas": 8.0, "coal": 4.0}
        shares = self.sub.compute_shares(prices)
        assert shares.sum() == pytest.approx(1.0, abs=1e-6)

    def test_cheaper_gets_higher_share(self):
        prices = {"electricity": 20.0, "gas": 8.0, "coal": 4.0}
        shares = self.sub.compute_shares(prices)
        # Coal is cheapest → highest share
        assert shares[2] > shares[1] > shares[0]

    def test_equal_prices_equal_shares(self):
        prices = {"electricity": 5.0, "gas": 5.0, "coal": 5.0}
        shares = self.sub.compute_shares(prices)
        np.testing.assert_allclose(shares, [1 / 3] * 3, atol=1e-6)

    def test_last_shares_cached(self):
        prices = {"electricity": 20.0, "gas": 8.0, "coal": 4.0}
        shares = self.sub.compute_shares(prices)
        assert self.sub.last_shares is not None
        np.testing.assert_array_equal(shares, self.sub.last_shares)

    def test_carrier_demands_sums_correctly(self):
        prices = {"electricity": 10.0, "gas": 10.0, "coal": 10.0}
        shares = self.sub.compute_shares(prices)
        demands = self.sub.carrier_demands(shares, 10.0)
        total = sum(demands.values())
        # With eff=1.0, total fuel = total service
        assert total == pytest.approx(10.0, rel=1e-6)

    def test_carrier_demands_efficiency(self):
        """Lower efficiency → more fuel per unit of service."""
        sub = Subsector("test", [
            EndUseTech(carrier="gas", efficiency=0.5),
        ])
        shares = np.array([1.0])
        demands = sub.carrier_demands(shares, 10.0)
        # 10 EJ service / 0.5 eff = 20 EJ fuel
        assert demands["gas"] == pytest.approx(20.0)

    def test_price_index_returns_float(self):
        prices = {"electricity": 20.0, "gas": 8.0, "coal": 4.0}
        self.sub.compute_shares(prices)
        pi = self.sub.price_index(prices)
        assert isinstance(pi, float)
        assert pi > 0

    def test_price_index_between_min_max(self):
        prices = {"electricity": 20.0, "gas": 8.0, "coal": 4.0}
        self.sub.compute_shares(prices)
        pi = self.sub.price_index(prices)
        assert 4.0 <= pi <= 20.0

    def test_calibrate_reproduces_shares(self):
        prices = {"electricity": 20.0, "gas": 8.0, "coal": 4.0}
        target = np.array([0.1, 0.3, 0.6])
        self.sub.calibrate(target, prices)
        result = self.sub.compute_shares(prices)
        np.testing.assert_allclose(result, target, atol=1e-3)


class TestSubsectorPrefDecay:
    def test_no_decay_mature_carriers(self):
        sub = Subsector("test", [
            EndUseTech(carrier="gas"),
            EndUseTech(carrier="coal"),
        ])
        sub.pref_factors = np.array([1.0, 2.0])
        decayed = sub._decayed_pref_factors(2021)
        np.testing.assert_array_equal(decayed, [1.0, 2.0])  # base year
        decayed_30 = sub._decayed_pref_factors(2051)
        np.testing.assert_array_equal(decayed_30, [1.0, 2.0])  # no decay

    def test_electricity_decays(self):
        sub = Subsector("test", [
            EndUseTech(carrier="electricity"),
            EndUseTech(carrier="gas"),
        ])
        sub.pref_factors = np.array([5.0, 5.0])
        decayed = sub._decayed_pref_factors(2051)  # 30 years
        # electricity decays at 2%/yr: 5.0 × (0.98)^30
        expected_elec = 5.0 * (1.0 - 0.02) ** 30
        assert decayed[0] == pytest.approx(expected_elec, rel=1e-6)
        assert decayed[1] == pytest.approx(5.0)  # gas: no decay

    def test_h2_decays_faster(self):
        sub = Subsector("test", [
            EndUseTech(carrier="h2"),
            EndUseTech(carrier="electricity"),
        ])
        sub.pref_factors = np.array([5.0, 5.0])
        decayed = sub._decayed_pref_factors(2051)
        # H2 at 3%, elec at 2%
        assert decayed[0] < decayed[1]  # H2 decays faster


# ===========================================================================
# DemandSector ABC
# ===========================================================================

class TestDemandSectorABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            DemandSector()

    def test_demand_envelope_basic(self):
        """AgricultureSector inherits demand_envelope."""
        ag = AgricultureSector()
        ag.base_demand = 10.0
        ag.base_gdp = 1000.0
        ag.base_price = 5.0

        rs = RegionState(gdp=1000.0)
        rs.carrier_prices = {"electricity": 5.0, "gas": 5.0, "coal": 5.0,
                             "liquids": 5.0, "biomass": 5.0, "biofuel": 5.0,
                             "h2": 5.0}
        # At base year with same GDP and prices → demand = base
        ag.subsectors[0].compute_shares(rs.carrier_prices)
        env = ag.demand_envelope(rs)
        assert env == pytest.approx(10.0, rel=0.1)

    def test_demand_envelope_gdp_growth(self):
        ag = AgricultureSector()
        ag.base_demand = 10.0
        ag.base_gdp = 1000.0
        ag.base_price = 5.0

        rs = RegionState(gdp=2000.0)
        rs.carrier_prices = {"electricity": 5.0, "gas": 5.0, "coal": 5.0,
                             "liquids": 5.0, "biomass": 5.0, "biofuel": 5.0,
                             "h2": 5.0}
        ag.subsectors[0].compute_shares(rs.carrier_prices)
        env = ag.demand_envelope(rs)
        # GDP doubled, α=0.3 → env = 10 × 2^0.3 ≈ 12.3
        assert env > 10.0
        assert env == pytest.approx(10.0 * 2.0 ** 0.3, rel=0.1)


# ===========================================================================
# TransformationSector ABC
# ===========================================================================

class TestTransformationSectorABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            TransformationSector()


# ===========================================================================
# AgricultureSector
# ===========================================================================

class TestAgricultureSector:
    def setup_method(self):
        self.ag = AgricultureSector(base_ch4=5.0, base_n2o=0.5)
        self.prices = {
            "electricity": 20.0, "gas": 8.0, "coal": 4.0,
            "liquids": 15.0, "biomass": 3.0, "biofuel": 12.0, "h2": 25.0,
        }
        self.demands = {
            "electricity": 0.5, "gas": 1.0, "coal": 2.0,
            "liquids": 1.5, "biomass": 0.5, "biofuel": 0.0, "h2": 0.0,
        }
        self.ag.calibrate(self.demands, self.prices, 1000.0)

    def test_calibrate_sets_base(self):
        assert self.ag.base_demand == pytest.approx(5.5)
        assert self.ag.base_gdp == pytest.approx(1000.0)

    def test_compute_demand_returns_dict(self):
        rs = RegionState(gdp=1000.0, carrier_prices=self.prices)
        result = self.ag.compute_demand(rs)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_compute_demand_sums_to_total(self):
        rs = RegionState(gdp=1000.0, carrier_prices=self.prices)
        result = self.ag.compute_demand(rs)
        total = sum(result.values())
        # Should be close to base_demand at base conditions
        assert total == pytest.approx(5.5, rel=0.2)

    def test_demand_increases_with_gdp(self):
        rs_low = RegionState(gdp=1000.0, carrier_prices=self.prices)
        rs_high = RegionState(gdp=2000.0, carrier_prices=self.prices)
        d_low = sum(self.ag.compute_demand(rs_low).values())
        d_high = sum(self.ag.compute_demand(rs_high).values())
        assert d_high > d_low

    def test_production_index_at_base(self):
        rs = RegionState(gdp=1000.0, carrier_prices=self.prices)
        self.ag.subsectors[0].compute_shares(self.prices)
        idx = self.ag.production_index(rs)
        assert idx == pytest.approx(1.0, rel=0.1)

    def test_emissions_ch4_n2o(self):
        rs = RegionState(gdp=1000.0, carrier_prices=self.prices)
        rs.sector_demand = {"agriculture": self.demands}
        self.ag.subsectors[0].compute_shares(self.prices)
        em = self.ag.compute_emissions(rs)
        assert em.ch4 == pytest.approx(5.0, rel=0.1)
        assert em.n2o == pytest.approx(0.5, rel=0.1)

    def test_emissions_scale_with_gdp(self):
        rs1 = RegionState(gdp=1000.0, carrier_prices=self.prices)
        rs1.sector_demand = {"agriculture": self.demands}
        rs2 = RegionState(gdp=2000.0, carrier_prices=self.prices)
        rs2.sector_demand = {"agriculture": self.demands}
        self.ag.subsectors[0].compute_shares(self.prices)
        em1 = self.ag.compute_emissions(rs1)
        em2 = self.ag.compute_emissions(rs2)
        # Higher GDP → higher production index → more CH4/N2O
        assert em2.ch4 > em1.ch4
        assert em2.n2o > em1.n2o

    def test_emissions_co2_from_combustion(self):
        demands_with_coal = {"coal": 1.0}
        rs = RegionState(gdp=1000.0, carrier_prices=self.prices)
        rs.sector_demand = {"agriculture": demands_with_coal}
        self.ag.subsectors[0].compute_shares(self.prices)
        em = self.ag.compute_emissions(rs)
        # coal: 0.0257 tC/GJ × 44/12 × 1 EJ × 1e3 = 94.2 MtCO2
        expected = CARBON_COEFS.get("coal", 0.0) * TC_TO_TCO2 * 1.0 * 1e3
        assert em.co2 == pytest.approx(expected, rel=1e-3)

    def test_seven_carriers(self):
        assert len(self.ag.subsectors[0].techs) == 7


# ===========================================================================
# RefinedOilSector
# ===========================================================================

class TestRefinedOilSector:
    def setup_method(self):
        self.ref = RefinedOilSector()

    def test_compute_supply_passthrough(self):
        rs = RegionState()
        result = self.ref.compute_supply(rs, 10.0)
        assert result == {"refinery": 10.0}

    def test_compute_supply_zero(self):
        rs = RegionState()
        result = self.ref.compute_supply(rs, 0.0)
        assert result == {"refinery": 0.0}

    def test_compute_supply_negative_clipped(self):
        rs = RegionState()
        result = self.ref.compute_supply(rs, -5.0)
        assert result == {"refinery": 0.0}

    def test_compute_price(self):
        rs = RegionState()
        rs.raw_fuel_prices = {"oil": 9.0}
        price = self.ref.compute_price(rs)
        # 9.0 / 0.90 + 0.2 = 10.2
        assert price == pytest.approx(10.2, rel=1e-6)

    def test_compute_price_higher_oil(self):
        rs1 = RegionState()
        rs1.raw_fuel_prices = {"oil": 5.0}
        rs2 = RegionState()
        rs2.raw_fuel_prices = {"oil": 15.0}
        assert self.ref.compute_price(rs2) > self.ref.compute_price(rs1)

    def test_fuel_input_ej(self):
        # 10 EJ output / 0.90 eff = 11.11 EJ input
        assert self.ref.fuel_input_ej(10.0) == pytest.approx(10.0 / 0.90)

    def test_emissions_zero(self):
        """Refinery has zero direct emissions (conversion, not combustion)."""
        em = self.ref.compute_emissions({"refinery": 10.0})
        assert em.co2 == 0.0
        assert em.ch4 == 0.0

    def test_single_tech(self):
        assert len(self.ref.techs) == 1
        assert self.ref.techs[0].name == "refinery"
        assert self.ref.techs[0].carbon_coef == 0.0

    def test_custom_efficiency(self):
        ref = RefinedOilSector(efficiency=0.85)
        assert ref.techs[0].efficiency == 0.85
