"""GEM vintage capacity data loader.

Loads preprocessed GEM (Global Energy Monitor) vintage capacity data
from ``ghim/data/external/energy/gem_vintage_capacity_r10.csv``.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from ghim.config import GHIM_DATA_EXT

GEM_CSV_PATH = GHIM_DATA_EXT / "energy" / "gem_vintage_capacity_r10.csv"


@lru_cache(maxsize=1)
def load_gem_vintage_data() -> dict[str, dict[str, dict[int, float]]]:
    """Load GEM vintage data: {region: {tech: {vintage_year: ej}}}.

    Returns empty dict if the CSV doesn't exist (graceful fallback
    to uniform initialization).
    """
    if not GEM_CSV_PATH.exists():
        return {}

    result: dict[str, dict[str, dict[int, float]]] = {}
    with open(GEM_CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            region = row["region"]
            tech = row["tech"]
            vintage_year = int(row["vintage_year"])
            capacity_ej = float(row["capacity_ej_yr"])
            result.setdefault(region, {}).setdefault(tech, {})[vintage_year] = (
                result.get(region, {}).get(tech, {}).get(vintage_year, 0.0) + capacity_ej
            )
    return result
