"""Load and aggregate GCAM fossil supply curves to R10 for trade module.

Pipeline: R32 (fos_curves_R32.csv) → country (GDP-share downscale) → R10.
Costs converted from 1975$ to 2020$ using GDP deflator.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from ghim.core.config import BASE_YEAR
from ghim.config import GHIM_DATA_EXT, GCAM3_TO_2020_DEFLATOR
from ghim.regions import R10_REGIONS, build_iso_to_r10
from ghim.energy.supply import ResourceSupply, ResourceGrade

# ---------------------------------------------------------------------------
# R32 → R10 hardcoded mapping (32 GCAM regions → 10 AR6 regions)
# ---------------------------------------------------------------------------
_R32_TO_R10: dict[int, str] = {
    1: "North America",                            # USA
    2: "Africa",                                   # Africa_Eastern
    3: "Africa",                                   # Africa_Northern
    4: "Africa",                                   # Africa_Southern
    5: "Africa",                                   # Africa_Western
    6: "Asia-Pacific Developed",                   # Australia_NZ
    7: "Latin America and Caribbean",              # Brazil
    8: "North America",                            # Canada
    9: "Latin America and Caribbean",              # Central America and Caribbean
    10: "Eurasia",                                 # Central Asia
    11: "Eastern Asia",                            # China
    12: "Europe",                                  # EU-12
    13: "Europe",                                  # EU-15
    14: "Eurasia",                                 # Ukraine
    15: "Europe",                                  # Europe_Non_EU
    16: "Europe",                                  # European Free Trade Association
    17: "Southern Asia",                           # India
    18: "South-East Asia and developing Pacific",  # Indonesia
    19: "Asia-Pacific Developed",                  # Japan
    20: "North America",                           # Mexico
    21: "Middle East",                             # Middle East
    22: "Southern Asia",                           # Pakistan
    23: "Eurasia",                                 # Russia
    24: "Africa",                                  # South Africa
    25: "Latin America and Caribbean",             # South America_Northern
    26: "Latin America and Caribbean",             # South America_Southern
    27: "Southern Asia",                           # South Asia
    28: "Asia-Pacific Developed",                  # South Korea
    29: "South-East Asia and developing Pacific",  # Southeast Asia
    30: "Eastern Asia",                            # Taiwan
    31: "Latin America and Caribbean",             # Argentina
    32: "Latin America and Caribbean",             # Colombia
}

# GCAM resource name → GHIM fuel name
_RESOURCE_TO_FUEL: dict[str, str] = {
    "coal": "coal",
    "crude oil": "oil",
    "natural gas": "gas",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_r32_curves() -> pd.DataFrame:
    """Load fos_curves_R32.csv exported from PREBUILT_DATA.rda."""
    path = GHIM_DATA_EXT / "energy" / "fos_curves_R32.csv"
    df = pd.read_csv(path)
    # Map resource names to GHIM fuel names
    df["fuel"] = df["resource"].map(_RESOURCE_TO_FUEL)
    return df


def _load_country_gdp_shares() -> dict[int, dict[str, float]]:
    """Compute within-R32 GDP shares for country-level downscaling.

    Returns {R32_region_ID: {iso_upper: share}}.
    """
    # Load country → R32 mapping
    iso_gcam = pd.read_csv(GHIM_DATA_EXT / "common" / "iso_GCAM_regID.csv", comment="#")
    iso_gcam["iso_upper"] = iso_gcam["iso"].str.upper()

    # Load SSP GDP (base year, Historical Reference for 2020)
    ssp_path = GHIM_DATA_EXT / "ssp" / "SSP_database_2024.csv.gz"
    ssp = pd.read_csv(ssp_path, comment="#")
    gdp_rows = ssp[
        (ssp["Variable"] == "GDP|PPP")
        & (ssp["Scenario"].isin(["SSP2", "Historical Reference"]))
    ].copy()

    # Map SSP country names to ISO
    iso_ssp = pd.read_csv(GHIM_DATA_EXT / "ssp" / "iso_SSP_regID.csv", comment="#")
    ssp_to_iso = dict(zip(iso_ssp["ssp_country_name"], iso_ssp["iso"].str.upper()))
    gdp_rows["iso_upper"] = gdp_rows["Region"].map(ssp_to_iso)
    gdp_rows = gdp_rows.dropna(subset=["iso_upper"])

    # Get GDP for base year (prefer Historical Reference, fall back to SSP2)
    base_col = str(BASE_YEAR)
    if base_col in gdp_rows.columns:
        gdp_rows["gdp"] = pd.to_numeric(gdp_rows[base_col], errors="coerce").fillna(0)
    else:
        gdp_rows["gdp"] = 0.0

    # Keep best GDP per country (prefer Historical Reference)
    gdp_rows = gdp_rows.sort_values("Scenario", ascending=True)  # Historical Reference first
    gdp_by_iso = gdp_rows.drop_duplicates(subset=["iso_upper"], keep="first")[
        ["iso_upper", "gdp"]
    ].set_index("iso_upper")["gdp"].to_dict()

    # Build R32 → {iso: share}
    result: dict[int, dict[str, float]] = {}
    for r32_id, group in iso_gcam.groupby("GCAM_region_ID"):
        isos = group["iso_upper"].tolist()
        gdps = {iso: gdp_by_iso.get(iso, 0.0) for iso in isos}
        total = sum(gdps.values())
        if total > 0:
            shares = {iso: g / total for iso, g in gdps.items()}
        else:
            # Equal share fallback
            shares = {iso: 1.0 / len(isos) for iso in isos}
        result[int(r32_id)] = shares

    return result


def _downscale_to_country(
    r32_curves: pd.DataFrame,
    gdp_shares: dict[int, dict[str, float]],
) -> pd.DataFrame:
    """Split R32 grade availability to countries proportionally by GDP share."""
    rows = []
    for _, row in r32_curves.iterrows():
        r32_id = int(row["GCAM_region_ID"])
        shares = gdp_shares.get(r32_id, {})
        for iso, share in shares.items():
            rows.append({
                "iso": iso,
                "fuel": row["fuel"],
                "subresource": row["subresource"],
                "grade": row["grade"],
                "available": row["available"] * share,
                "extractioncost": row["extractioncost"],
            })
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def load_fossil_curves_r10() -> pd.DataFrame:
    """Full pipeline: R32 → country → R10. Convert 1975$ → 2020$.

    Returns DataFrame: r10, fuel, subresource, grade, available, extractioncost.
    """
    r32_curves = _load_r32_curves()
    gdp_shares = _load_country_gdp_shares()
    country_curves = _downscale_to_country(r32_curves, gdp_shares)

    # Map country → R10
    iso_to_r10 = build_iso_to_r10()
    country_curves["r10"] = country_curves["iso"].map(iso_to_r10)

    # Countries without R10 mapping: try via R32 mapping
    missing = country_curves["r10"].isna()
    if missing.any():
        # Fall back: use R32→R10 direct mapping via iso_GCAM_regID
        iso_gcam = pd.read_csv(GHIM_DATA_EXT / "common" / "iso_GCAM_regID.csv", comment="#")
        iso_to_r32 = dict(zip(iso_gcam["iso"].str.upper(), iso_gcam["GCAM_region_ID"]))
        for idx in country_curves[missing].index:
            iso = country_curves.loc[idx, "iso"]
            r32_id = iso_to_r32.get(iso)
            if r32_id is not None:
                country_curves.loc[idx, "r10"] = _R32_TO_R10.get(int(r32_id))

    country_curves = country_curves.dropna(subset=["r10"])

    # Aggregate to R10: sum available per (r10, fuel, subresource, grade, extractioncost)
    r10_curves = country_curves.groupby(
        ["r10", "fuel", "subresource", "grade", "extractioncost"], as_index=False
    )["available"].sum()

    # Convert 1975$ → 2020$
    r10_curves["extractioncost"] = r10_curves["extractioncost"] * GCAM3_TO_2020_DEFLATOR

    return r10_curves


def build_regional_supplies(
    production_cap_factor: float = 3.0,
) -> dict[str, dict[str, ResourceSupply]]:
    """Build region → fuel → ResourceSupply from GCAM fossil curves.

    Aggregates all subresources and grades within each (R10, fuel) pair
    into a single ResourceSupply with grades sorted by extraction cost.

    Parameters
    ----------
    production_cap_factor : float
        Max annual production = base_year_production * factor.
        Prevents resource stocks (thousands of EJ) from being fully
        available in a single period. Default 3.0 allows tripling
        of base-year production.
    """
    from ghim.data.energy_cal import DEFAULT_PRIMARY_ENERGY

    df = load_fossil_curves_r10()

    # Map from GHIM fuel names to DEFAULT_PRIMARY_ENERGY keys
    _fuel_to_pe = {"coal": "coal", "oil": "oil", "gas": "gas"}

    result: dict[str, dict[str, ResourceSupply]] = {}
    for region in R10_REGIONS:
        region_df = df[df["r10"] == region]
        pe = DEFAULT_PRIMARY_ENERGY.get(region, {})
        fuel_supplies: dict[str, ResourceSupply] = {}
        for fuel in ["coal", "oil", "gas"]:
            fuel_df = region_df[region_df["fuel"] == fuel]
            if fuel_df.empty:
                fuel_supplies[fuel] = ResourceSupply(fuel, [ResourceGrade(0.01, 100.0)])
                continue

            # Aggregate by extraction cost: sum available across subresources at same cost
            agg = fuel_df.groupby("extractioncost", as_index=False)["available"].sum()
            agg = agg.sort_values("extractioncost")

            grades = []
            for _, row in agg.iterrows():
                avail = row["available"]
                cost = row["extractioncost"]
                if avail > 0:
                    grades.append(ResourceGrade(avail, cost))

            if not grades:
                grades = [ResourceGrade(0.01, 100.0)]

            # Set max annual production from base-year data
            base_prod = pe.get(_fuel_to_pe[fuel], 1.0)
            max_annual = base_prod * production_cap_factor

            fuel_supplies[fuel] = ResourceSupply(
                fuel, grades, max_annual_production=max_annual,
            )
        result[region] = fuel_supplies

    return result


# ---------------------------------------------------------------------------
# Transport costs ($/GJ, region-specific)
# ---------------------------------------------------------------------------

def default_transport_costs() -> dict[str, dict[str, float]]:
    """Transport cost adders by fuel and region ($/GJ).

    Represents shipping/pipeline costs to move fuel from global market
    to each region. Landlocked/remote regions pay more for LNG.
    """
    # Base transport costs by fuel
    base: dict[str, float] = {
        "coal": 0.5,    # bulk shipping
        "oil": 0.3,     # tanker
        "gas": 0.8,     # LNG / pipeline
    }
    # Regional multipliers (1.0 = average; <1 for major exporters/producers)
    multipliers: dict[str, dict[str, float]] = {
        "Africa":                                  {"coal": 1.2, "oil": 0.9, "gas": 1.3},
        "Asia-Pacific Developed":                  {"coal": 1.0, "oil": 1.0, "gas": 1.2},
        "Eastern Asia":                            {"coal": 0.8, "oil": 1.0, "gas": 1.5},
        "Eurasia":                                 {"coal": 0.9, "oil": 0.7, "gas": 0.5},
        "Europe":                                  {"coal": 1.0, "oil": 0.9, "gas": 1.0},
        "Latin America and Caribbean":             {"coal": 1.3, "oil": 0.8, "gas": 0.9},
        "Middle East":                             {"coal": 1.5, "oil": 0.4, "gas": 0.6},
        "North America":                           {"coal": 0.7, "oil": 0.8, "gas": 0.6},
        "South-East Asia and developing Pacific":  {"coal": 1.0, "oil": 1.0, "gas": 1.2},
        "Southern Asia":                           {"coal": 1.0, "oil": 1.1, "gas": 1.4},
    }

    result: dict[str, dict[str, float]] = {}
    for fuel in ["coal", "oil", "gas"]:
        result[fuel] = {}
        for region in R10_REGIONS:
            mult = multipliers.get(region, {}).get(fuel, 1.0)
            result[fuel][region] = base[fuel] * mult

    return result
