"""Tests for Region container and external adapters."""

import pytest

from ghim.core.region import Region
from ghim.core.state import PeriodState, RegionState
from ghim.adapters.base import (
    ExternalInterface,
    DefaultClimateAdapter,
    DefaultWaterAdapter,
    DefaultAFOLUAdapter,
)


# ===========================================================================
# Region container
# ===========================================================================

class TestRegion:
    def test_create_minimal(self):
        """Region can be created with just a name and economy."""
        # Use a mock economy
        region = Region(name="USA", economy=None)
        assert region.name == "USA"
        assert region.demand_sectors == []
        assert region.transformation == []
        assert region.resources == {}

    def test_create_with_sectors(self):
        region = Region(
            name="China",
            economy=None,
            demand_sectors=["mock_ind", "mock_bld"],
            transformation=["mock_elec"],
            resources={"coal": "mock_supply"},
        )
        assert len(region.demand_sectors) == 2
        assert len(region.transformation) == 1
        assert "coal" in region.resources


# ===========================================================================
# ExternalInterface ABC
# ===========================================================================

class TestExternalInterface:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ExternalInterface()


# ===========================================================================
# DefaultClimateAdapter
# ===========================================================================

class TestDefaultClimateAdapter:
    def test_sets_zero_anomalies(self):
        adapter = DefaultClimateAdapter()
        state = PeriodState(
            period=2025,
            regions={"USA": RegionState(temperature_anomaly=1.5, precip_anomaly=0.5)},
        )
        adapter.update(state)
        assert state.regions["USA"].temperature_anomaly == 0.0
        assert state.regions["USA"].precip_anomaly == 0.0

    def test_handles_multiple_regions(self):
        adapter = DefaultClimateAdapter()
        state = PeriodState(
            period=2025,
            regions={
                "USA": RegionState(temperature_anomaly=2.0),
                "China": RegionState(temperature_anomaly=3.0),
            },
        )
        adapter.update(state)
        assert state.regions["USA"].temperature_anomaly == 0.0
        assert state.regions["China"].temperature_anomaly == 0.0


# ===========================================================================
# DefaultWaterAdapter
# ===========================================================================

class TestDefaultWaterAdapter:
    def test_sets_unlimited_water(self):
        adapter = DefaultWaterAdapter()
        state = PeriodState(
            period=2025,
            regions={"USA": RegionState(cooling_water_avail=100.0)},
        )
        adapter.update(state)
        rs = state.regions["USA"]
        assert rs.cooling_water_avail == float("inf")
        assert rs.hydro_water_fraction == 1.0
        assert rs.water_energy_demand == 0.0


# ===========================================================================
# DefaultAFOLUAdapter
# ===========================================================================

class TestDefaultAFOLUAdapter:
    def test_no_op(self):
        adapter = DefaultAFOLUAdapter()
        state = PeriodState(
            period=2025,
            regions={"USA": RegionState()},
        )
        # Should not raise
        adapter.update(state)
