"""Tests for GHIMModel — top-level orchestrator F(x) pass."""

import pytest

from ghim.core.carrier import Carrier, CARBON_COEFS, TC_TO_TCO2, LULUCF_NET_CO2
from ghim.core.emissions import EmissionResult
from ghim.core.region import Region
from ghim.core.state import PeriodState, RegionState
from ghim.model import GHIMModel
from ghim.adapters.base import (
    DefaultClimateAdapter,
    DefaultWaterAdapter,
    DefaultAFOLUAdapter,
)


# ===========================================================================
# Mock components for isolated testing
# ===========================================================================

class MockEconomy:
    """Minimal Economy that returns fixed values."""

    def __init__(self, base_gdp=1000.0, base_energy=10.0, base_price=5.0):
        self.base_gdp = base_gdp
        self.base_energy = base_energy
        self.base_energy_price = base_price
        self.sigma_kle = 0.4
        self.lfp = 0.6

    def compute_value_added(self, population):
        return self.base_gdp * 0.9  # VA ~90% of GDP

    def compute_energy_demand(self, value_added, energy_price):
        return self.base_energy

    def compute_gross_output(self, value_added, energy_ej):
        return self.base_gdp

    def compute_gdp(self, value_added, energy_ej, energy_price):
        return self.base_gdp

    def compute_investment(self, gross_output):
        return 0.22 * gross_output

    @staticmethod
    def composite_energy_price(carrier_prices, carrier_demands):
        total_cost = sum(
            carrier_prices.get(c, 5.0) * d
            for c, d in carrier_demands.items()
        )
        total_ej = sum(carrier_demands.values())
        return total_cost / total_ej if total_ej > 0 else 5.0


class MockDemandSector:
    """Returns fixed carrier demands."""

    def __init__(self, name, demands):
        self.name = name
        self.subsectors = []
        self._demands = demands

    def compute_demand(self, rs, policy=None):
        return dict(self._demands)

    def compute_emissions(self, rs):
        co2 = 0.0
        demands = rs.sector_demand.get(self.name, self._demands)
        for carrier, ej in demands.items():
            cc = CARBON_COEFS.get(carrier, CARBON_COEFS.get(Carrier(carrier) if carrier in [c.value for c in Carrier] else carrier, 0.0))
            co2 += cc * TC_TO_TCO2 * ej * 1e3
        return EmissionResult(co2=co2)

    def sector_price_index(self, rs):
        return 5.0


class MockTransformationSector:
    """Returns fixed generation and price."""

    def __init__(self, carrier_output, gen, price):
        self.carrier_output = carrier_output
        self._gen = gen
        self._price = price

    def compute_supply(self, rs, demand, policy=None):
        return dict(self._gen)

    def compute_price(self, rs):
        return self._price

    def compute_emissions(self, gen):
        return EmissionResult(co2=0.0)


# ===========================================================================
# Helper to build a single-region model
# ===========================================================================

def make_single_region_model(region_name="TestRegion", gdp=1000.0):
    """Build a GHIMModel with one region, mock sectors."""
    economy = MockEconomy(base_gdp=gdp)

    demand_sectors = [
        MockDemandSector("industry", {
            "electricity": 3.0, "gas": 2.0, "coal": 2.0,
            "liquids": 1.0, "biomass": 0.5,
        }),
        MockDemandSector("buildings", {
            "electricity": 2.0, "gas": 1.0, "heat": 0.5,
        }),
    ]

    transformation = [
        MockTransformationSector("electricity", {"coal": 5.0, "gas": 3.0, "solar": 2.0}, 20.0),
        MockTransformationSector("heat", {"gas_boiler": 0.5}, 10.0),
    ]

    region = Region(
        name=region_name,
        economy=economy,
        demand_sectors=demand_sectors,
        transformation=transformation,
    )

    model = GHIMModel(
        regions={region_name: region},
        climate=DefaultClimateAdapter(),
        water=DefaultWaterAdapter(),
        afolu=DefaultAFOLUAdapter(),
    )

    return model


def make_initial_state(region_name="TestRegion", gdp=1000.0):
    """Initial PeriodState matching make_single_region_model."""
    rs = RegionState(
        gdp=gdp,
        population=100.0,
        capital_stock=3000.0,
        carrier_prices={
            Carrier.ELECTRICITY: 20.0,
            Carrier.GAS: 5.0,
            Carrier.COAL: 3.0,
            Carrier.LIQUIDS: 12.0,
            Carrier.BIOMASS: 3.0,
            Carrier.H2: 15.0,
            Carrier.HEAT: 10.0,
        },
        raw_fuel_prices={
            Carrier.COAL: 3.0,
            Carrier.GAS: 5.0,
            Carrier.OIL: 8.0,
        },
        composite_energy_price=5.0,
        hdd=1.0,
        cdd=1.0,
        base_gdp=gdp,
        base_energy_ej=10.0,
        base_energy_price=5.0,
    )
    return PeriodState(
        period=2025,
        regions={region_name: rs},
        world_prices={"coal": 3.0, "oil": 8.0, "gas": 5.0},
    )


# ===========================================================================
# Tests
# ===========================================================================

class TestGHIMModelInit:
    def test_create_minimal(self):
        model = GHIMModel(regions={})
        assert model.regions == {}
        assert model.trade is None
        assert model.policy is None

    def test_create_with_regions(self):
        model = make_single_region_model()
        assert "TestRegion" in model.regions
        assert model.climate is not None


class TestFx:
    def test_returns_period_state(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        assert isinstance(result, PeriodState)

    def test_does_not_mutate_input(self):
        model = make_single_region_model()
        state = make_initial_state()
        original_gdp = state.regions["TestRegion"].gdp
        model.F(state)
        assert state.regions["TestRegion"].gdp == original_gdp

    def test_sets_value_added(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        assert result.regions["TestRegion"].value_added > 0

    def test_sets_final_demand(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        fd = result.regions["TestRegion"].final_demand
        assert isinstance(fd, dict)
        assert sum(fd.values()) > 0

    def test_demand_scaled_to_ces_total(self):
        """Final demand should sum to the CES total energy demand."""
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        fd = result.regions["TestRegion"].final_demand
        # MockEconomy returns 10.0 EJ
        assert sum(fd.values()) == pytest.approx(10.0, rel=1e-3)

    def test_sets_generation(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        gen = result.regions["TestRegion"].generation
        assert "electricity" in gen
        assert "heat" in gen

    def test_updates_carrier_prices(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        # Electricity price should be set by transformation sector
        assert result.regions["TestRegion"].carrier_prices[Carrier.ELECTRICITY] == 20.0
        # Heat price
        assert result.regions["TestRegion"].carrier_prices[Carrier.HEAT] == 10.0

    def test_sets_composite_energy_price(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        assert result.regions["TestRegion"].composite_energy_price > 0

    def test_sets_gdp(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        assert result.regions["TestRegion"].gdp == 1000.0  # MockEconomy returns fixed

    def test_sets_investment(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        assert result.regions["TestRegion"].investment == pytest.approx(0.22 * 1000.0)

    def test_computes_emissions(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        # Should have emissions detail
        em = result.regions["TestRegion"].emissions_detail
        assert isinstance(em, EmissionResult)

    def test_lulucf_applied(self):
        """LULUCF for USA should be negative (net sink)."""
        model = make_single_region_model(region_name="USA")
        state = make_initial_state(region_name="USA")
        result = model.F(state)
        em = result.regions["USA"].emissions_detail
        # USA LULUCF is -0.41 GtCO2 = -410 MtCO2
        assert em.lulucf == pytest.approx(-410.0)

    def test_global_emissions_set(self):
        model = make_single_region_model()
        state = make_initial_state()
        result = model.F(state)
        assert result.global_emissions_detail is not None
        # global_emissions is in Gt
        assert isinstance(result.global_emissions, float)


class TestFxNoCarbonPrice:
    def test_no_carbon_adder_without_policy(self):
        """Without policy, direct-use fuel prices should equal raw prices."""
        model = make_single_region_model()
        model.policy = None
        state = make_initial_state()
        # Set raw prices
        state.regions["TestRegion"].raw_fuel_prices[Carrier.COAL] = 3.0
        result = model.F(state)
        # Coal price should be 3.0 (raw) + 0 (no carbon) = 3.0
        assert result.regions["TestRegion"].carrier_prices[Carrier.COAL] == pytest.approx(3.0)


class TestFxWithCarbonPrice:
    def test_carbon_price_adds_to_coal(self):
        """Carbon price adds to direct-use coal price."""
        model = make_single_region_model()

        class MockPolicy:
            def get_carbon_price(self, period):
                return 50.0  # $/tCO2

        model.policy = MockPolicy()
        state = make_initial_state()
        state.regions["TestRegion"].raw_fuel_prices[Carrier.COAL] = 3.0
        result = model.F(state)
        # Coal: raw=3.0 + CARBON_COEFS[COAL] * TC_TO_TCO2 * 50
        expected_adder = CARBON_COEFS[Carrier.COAL] * TC_TO_TCO2 * 50.0
        assert result.regions["TestRegion"].carrier_prices[Carrier.COAL] == pytest.approx(
            3.0 + expected_adder
        )

    def test_electricity_no_carbon_adder(self):
        """Electricity price comes from transformation, no direct carbon adder."""
        model = make_single_region_model()

        class MockPolicy:
            def get_carbon_price(self, period):
                return 50.0

        model.policy = MockPolicy()
        state = make_initial_state()
        result = model.F(state)
        # Electricity price set by MockTransformationSector (20.0)
        assert result.regions["TestRegion"].carrier_prices[Carrier.ELECTRICITY] == 20.0


class TestFxMultiRegion:
    def test_two_regions(self):
        """F(x) handles multiple regions."""
        economy1 = MockEconomy(base_gdp=5000.0)
        economy2 = MockEconomy(base_gdp=8000.0)

        demands = {"electricity": 3.0, "gas": 2.0}
        r1 = Region("USA", economy1,
                     [MockDemandSector("ind", demands)],
                     [MockTransformationSector("electricity", {"coal": 3.0}, 20.0)])
        r2 = Region("China", economy2,
                     [MockDemandSector("ind", demands)],
                     [MockTransformationSector("electricity", {"coal": 5.0}, 18.0)])

        model = GHIMModel(
            regions={"USA": r1, "China": r2},
            climate=DefaultClimateAdapter(),
            water=DefaultWaterAdapter(),
            afolu=DefaultAFOLUAdapter(),
        )

        state = PeriodState(
            period=2025,
            regions={
                "USA": RegionState(
                    gdp=5000.0, population=330.0,
                    carrier_prices={Carrier.ELECTRICITY: 20.0, Carrier.GAS: 5.0, Carrier.H2: 15.0, Carrier.HEAT: 10.0},
                    raw_fuel_prices={Carrier.COAL: 3.0},
                    composite_energy_price=5.0,
                ),
                "China": RegionState(
                    gdp=8000.0, population=1400.0,
                    carrier_prices={Carrier.ELECTRICITY: 18.0, Carrier.GAS: 4.0, Carrier.H2: 12.0, Carrier.HEAT: 8.0},
                    raw_fuel_prices={Carrier.COAL: 2.5},
                    composite_energy_price=4.0,
                ),
            },
            world_prices={"coal": 3.0, "oil": 8.0, "gas": 5.0},
        )

        result = model.F(state)
        assert "USA" in result.regions
        assert "China" in result.regions
        assert result.regions["USA"].gdp == 5000.0
        assert result.regions["China"].gdp == 8000.0
        assert result.global_emissions is not None


class TestFxExternalAdapters:
    def test_climate_adapter_called(self):
        """Climate adapter update() is called during F(x)."""
        called = False

        class TrackingClimate(DefaultClimateAdapter):
            def update(self, state):
                nonlocal called
                called = True
                super().update(state)

        model = make_single_region_model()
        model.climate = TrackingClimate()
        state = make_initial_state()
        model.F(state)
        assert called

    def test_water_adapter_called(self):
        called = False

        class TrackingWater(DefaultWaterAdapter):
            def update(self, state):
                nonlocal called
                called = True
                super().update(state)

        model = make_single_region_model()
        model.water = TrackingWater()
        state = make_initial_state()
        model.F(state)
        assert called
