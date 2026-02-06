"""R10 region definitions using AR6 10-region classification.

Mapping source: mapping/region_classification.tsv (ISO → AR6 R10 direct).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ghim.config import REPO_ROOT

# ---------------------------------------------------------------------------
# AR6 R10 region names (canonical order)
# ---------------------------------------------------------------------------
R10_REGIONS: list[str] = [
    "Africa",
    "Asia-Pacific Developed",
    "Eastern Asia",
    "Eurasia",
    "Europe",
    "Latin America and Caribbean",
    "Middle East",
    "North America",
    "South-East Asia and developing Pacific",
    "Southern Asia",
]

NUM_REGIONS: int = len(R10_REGIONS)

# Path to the region classification mapping file
_MAPPING_FILE = REPO_ROOT / "mapping" / "region_classification.tsv"


def load_region_mapping() -> pd.DataFrame:
    """Load the ISO → AR6 R10 region mapping.

    Returns DataFrame with columns: ISO, name, region_ar6_10.
    """
    return pd.read_csv(_MAPPING_FILE, sep="\t")


def build_country_to_r10() -> dict[str, str]:
    """Build a dict mapping country name → R10 region.

    Uses the 'name' column from region_classification.tsv.
    """
    df = load_region_mapping()
    return dict(zip(df["name"], df["region_ar6_10"]))


def build_iso_to_r10() -> dict[str, str]:
    """Build a dict mapping ISO code (uppercase) → R10 region."""
    df = load_region_mapping()
    return dict(zip(df["ISO"], df["region_ar6_10"]))


def r10_index(region_name: str) -> int:
    """Return the integer index (0-based) of an R10 region."""
    return R10_REGIONS.index(region_name)
