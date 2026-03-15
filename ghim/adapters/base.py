"""ExternalInterface ABC and default (no-op) adapters.

Phase 1: default adapters return placeholder values.
Phase 2+: real adapters wrap Hector, water module, AFOLU module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ghim.core.state import PeriodState


class ExternalInterface(ABC):
    """Adapter for an external module (Climate, Water, AFOLU)."""

    @abstractmethod
    def update(self, state: PeriodState) -> None:
        """Read energy outputs, write external results to each RegionState."""
        ...


class DefaultClimateAdapter(ExternalInterface):
    """No climate feedback — temperature anomaly stays at 0."""

    def update(self, state: PeriodState) -> None:
        for rs in state.regions.values():
            rs.temperature_anomaly = 0.0
            rs.precip_anomaly = 0.0


class DefaultWaterAdapter(ExternalInterface):
    """No water constraints — unlimited cooling, no hydro reduction."""

    def update(self, state: PeriodState) -> None:
        for rs in state.regions.values():
            rs.cooling_water_avail = float("inf")
            rs.hydro_water_fraction = 1.0
            rs.water_energy_demand = 0.0


class DefaultAFOLUAdapter(ExternalInterface):
    """Static biomass supply, no dynamic land-use feedback."""

    def update(self, state: PeriodState) -> None:
        # Phase 1: biomass supply is unchanged (uses calibrated values)
        pass
