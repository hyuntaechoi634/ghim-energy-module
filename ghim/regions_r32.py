"""R32 (GCAM 32-region) definitions and mappings.

Maps ISO codes → GCAM_region_ID → R32 region names.
Also provides R32 → R10 mapping for data downscaling.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ghim.config import GHIM_DATA_EXT


# ---------------------------------------------------------------------------
# R32 region names (canonical order, from GCAM_region_names.csv)
# ---------------------------------------------------------------------------

R32_REGIONS: list[str] = [
    "USA",
    "Africa_Eastern",
    "Africa_Northern",
    "Africa_Southern",
    "Africa_Western",
    "Australia_NZ",
    "Brazil",
    "Canada",
    "Central America and Caribbean",
    "Central Asia",
    "China",
    "EU-12",
    "EU-15",
    "Ukraine",
    "Europe_Non_EU",
    "European Free Trade Association",
    "India",
    "Indonesia",
    "Japan",
    "Mexico",
    "Middle East",
    "Pakistan",
    "Russia",
    "South Africa",
    "South America_Northern",
    "South America_Southern",
    "South Asia",
    "South Korea",
    "Southeast Asia",
    "Taiwan",
    "Argentina",
    "Colombia",
]

NUM_R32_REGIONS: int = len(R32_REGIONS)

# GCAM region ID → R32 name
_GCAM_ID_TO_R32: dict[int, str] = {i + 1: name for i, name in enumerate(R32_REGIONS)}

# R32 name → GCAM region ID
_R32_TO_GCAM_ID: dict[str, int] = {name: i + 1 for i, name in enumerate(R32_REGIONS)}


# ---------------------------------------------------------------------------
# R32 → R10 mapping
# ---------------------------------------------------------------------------

R32_TO_R10: dict[str, str] = {
    "USA": "North America",
    "Africa_Eastern": "Africa",
    "Africa_Northern": "Africa",
    "Africa_Southern": "Africa",
    "Africa_Western": "Africa",
    "Australia_NZ": "Asia-Pacific Developed",
    "Brazil": "Latin America and Caribbean",
    "Canada": "North America",
    "Central America and Caribbean": "Latin America and Caribbean",
    "Central Asia": "Eurasia",
    "China": "Eastern Asia",
    "EU-12": "Europe",
    "EU-15": "Europe",
    "Ukraine": "Eurasia",
    "Europe_Non_EU": "Europe",
    "European Free Trade Association": "Europe",
    "India": "Southern Asia",
    "Indonesia": "South-East Asia and developing Pacific",
    "Japan": "Asia-Pacific Developed",
    "Mexico": "North America",
    "Middle East": "Middle East",
    "Pakistan": "Southern Asia",
    "Russia": "Eurasia",
    "South Africa": "Africa",
    "South America_Northern": "Latin America and Caribbean",
    "South America_Southern": "Latin America and Caribbean",
    "South Asia": "Southern Asia",
    "South Korea": "Asia-Pacific Developed",
    "Southeast Asia": "South-East Asia and developing Pacific",
    "Taiwan": "Eastern Asia",
    "Argentina": "Latin America and Caribbean",
    "Colombia": "Latin America and Caribbean",
}


# R10 → list of R32 sub-regions
def r10_to_r32_members() -> dict[str, list[str]]:
    """Invert R32_TO_R10: for each R10 region, list its R32 members."""
    result: dict[str, list[str]] = {}
    for r32, r10 in R32_TO_R10.items():
        result.setdefault(r10, []).append(r32)
    return result


# ---------------------------------------------------------------------------
# ISO → R32 mapping (for SSP aggregation)
# ---------------------------------------------------------------------------

def build_iso_to_r32() -> dict[str, str]:
    """Map ISO code (lowercase) → R32 region name, via iso_GCAM_regID.csv."""
    path = GHIM_DATA_EXT / "common" / "iso_GCAM_regID.csv"
    df = pd.read_csv(path, comment="#")
    df["r32"] = df["GCAM_region_ID"].map(_GCAM_ID_TO_R32)
    return dict(zip(df["iso"], df["r32"]))


def build_ssp_country_to_r32() -> dict[str, str]:
    """Map SSP country name → R32 region name.

    Chain: SSP country → ISO (iso_SSP_regID.csv) → GCAM_region_ID → R32.
    """
    iso_ssp = pd.read_csv(
        GHIM_DATA_EXT / "ssp" / "iso_SSP_regID.csv",
        comment="#",
    )
    iso_to_r32 = build_iso_to_r32()
    iso_ssp["r32"] = iso_ssp["iso"].map(iso_to_r32)
    return dict(zip(iso_ssp["ssp_country_name"], iso_ssp["r32"]))
