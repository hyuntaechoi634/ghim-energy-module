"""Primary energy resource supply curves.

Models resource extraction cost as a function of cumulative production,
using a grade-based approach for fossil fuels and fixed costs for renewables.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ResourceGrade:
    """A single grade of a depletable resource.

    Attributes
    ----------
    available : float
        Total resource available in this grade (EJ).
    extraction_cost : float
        Cost of extraction ($/GJ).
    """
    available: float
    extraction_cost: float


@dataclass
class ResourceSupply:
    """Supply curve for a primary energy resource in one region.

    For fossil fuels: multiple grades with increasing extraction cost.
    For renewables: effectively unlimited at fixed cost (handled by
    the technology capital cost instead).
    """
    fuel: str
    grades: list[ResourceGrade]
    cumulative_extracted: float = 0.0

    def marginal_cost(self) -> float:
        """Return the current marginal extraction cost based on depletion."""
        cumul = 0.0
        for grade in self.grades:
            cumul += grade.available
            if self.cumulative_extracted < cumul:
                return grade.extraction_cost
        # All grades exhausted — return highest grade cost with scarcity premium
        return self.grades[-1].extraction_cost * 2.0

    def extract(self, amount_ej: float) -> float:
        """Extract a given amount and return the average cost.

        Updates cumulative_extracted in place.
        """
        cost_sum = 0.0
        remaining = amount_ej
        base = self.cumulative_extracted

        for grade in self.grades:
            grade_start = max(0, base - self._grade_cumulative_start(grade))
            grade_avail = max(0, grade.available - grade_start)
            take = min(remaining, grade_avail)
            if take > 0:
                cost_sum += take * grade.extraction_cost
                remaining -= take
                base += take
            if remaining <= 0:
                break

        # If demand exceeds all grades, supply at scarcity price
        if remaining > 0:
            cost_sum += remaining * self.grades[-1].extraction_cost * 2.0

        self.cumulative_extracted += amount_ej
        return cost_sum / amount_ej if amount_ej > 0 else 0.0

    def _grade_cumulative_start(self, target_grade: ResourceGrade) -> float:
        cumul = 0.0
        for grade in self.grades:
            if grade is target_grade:
                return cumul
            cumul += grade.available
        return cumul


def default_resource_supplies() -> dict[str, ResourceSupply]:
    """Return default global resource supply curves.

    These are approximate and will be scaled by region in the model.
    Values represent total global resources; regional allocation uses
    base-year production shares.
    """
    return {
        "coal": ResourceSupply("coal", [
            ResourceGrade(5000, 1.5),   # Low-cost reserves (EJ, $/GJ)
            ResourceGrade(10000, 2.5),
            ResourceGrade(20000, 4.0),
        ]),
        "gas": ResourceSupply("gas", [
            ResourceGrade(3000, 2.0),
            ResourceGrade(5000, 3.5),
            ResourceGrade(8000, 6.0),
        ]),
        "oil": ResourceSupply("oil", [
            ResourceGrade(2000, 4.0),
            ResourceGrade(3000, 7.0),
            ResourceGrade(5000, 12.0),
        ]),
        # Renewables: supply at zero fuel cost (cost is in technology capex)
        "nuclear": ResourceSupply("nuclear", [ResourceGrade(1e6, 0.7)]),
        "hydro": ResourceSupply("hydro", [ResourceGrade(1e6, 0.0)]),
        "wind": ResourceSupply("wind", [ResourceGrade(1e6, 0.0)]),
        "solar": ResourceSupply("solar", [ResourceGrade(1e6, 0.0)]),
        "biomass": ResourceSupply("biomass", [ResourceGrade(1e6, 2.0)]),
        "geothermal": ResourceSupply("geothermal", [ResourceGrade(1e6, 0.0)]),
    }
