"""Region — lightweight container grouping a region's structural components.

No computation logic. Region is pure data: it groups an Economy, its demand
sectors, transformation sectors, and resource endowments in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ghim.econ.klem import KLEMDriver
    from ghim.sectors.abc import DemandSector, TransformationSector


@dataclass
class Region:
    """A single GCAM-style region with its own sectors and resource endowment."""

    name: str
    economy: KLEMDriver
    demand_sectors: list[DemandSector] = field(default_factory=list)
    transformation: list[TransformationSector] = field(default_factory=list)
    resources: dict[str, object] = field(default_factory=dict)
