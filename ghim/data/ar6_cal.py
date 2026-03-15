"""Load AR6 SSP baseline scenario data and map to GHIM model variables.

Data source: IIASA AR6 Scenario Explorer (ar6-public), SSP marker models.
File: ghim/data/external/ssp/ar6_ssp_baselines.csv

AR6 regions are R5:
  - OECD90 and EU (and EU candidate) countries
  - Asian countries except Japan
  - Countries from the Reforming Economies of the Former Soviet Union
  - Countries of the Middle East and Africa
  - Latin American countries
  - World

The model runs at R32; calibration maps R5 → R32.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ghim.config import GHIM_DATA_EXT
from ghim.regions_r32 import R32_REGIONS, R32_TO_R10


# ---------------------------------------------------------------------------
# AR6 R5 region definitions and mapping
# ---------------------------------------------------------------------------

AR6_R5_REGIONS: list[str] = [
    "OECD90 and EU (and EU candidate) countries",
    "Asian countries except Japan",
    "Countries from the Reforming Economies of the Former Soviet Union",
    "Countries of the Middle East and Africa",
    "Latin American countries",
]

# R32 → AR6 R5 mapping
R32_TO_R5: dict[str, str] = {
    # OECD90 and EU
    "USA": "OECD90 and EU (and EU candidate) countries",
    "Canada": "OECD90 and EU (and EU candidate) countries",
    "Mexico": "OECD90 and EU (and EU candidate) countries",
    "EU-12": "OECD90 and EU (and EU candidate) countries",
    "EU-15": "OECD90 and EU (and EU candidate) countries",
    "Europe_Non_EU": "OECD90 and EU (and EU candidate) countries",
    "European Free Trade Association": "OECD90 and EU (and EU candidate) countries",
    "Japan": "OECD90 and EU (and EU candidate) countries",
    "South Korea": "OECD90 and EU (and EU candidate) countries",
    "Australia_NZ": "OECD90 and EU (and EU candidate) countries",
    # Asian countries except Japan
    "China": "Asian countries except Japan",
    "Taiwan": "Asian countries except Japan",
    "India": "Asian countries except Japan",
    "Indonesia": "Asian countries except Japan",
    "Pakistan": "Asian countries except Japan",
    "South Asia": "Asian countries except Japan",
    "Southeast Asia": "Asian countries except Japan",
    # Reforming Economies
    "Russia": "Countries from the Reforming Economies of the Former Soviet Union",
    "Ukraine": "Countries from the Reforming Economies of the Former Soviet Union",
    "Central Asia": "Countries from the Reforming Economies of the Former Soviet Union",
    # Middle East and Africa
    "Middle East": "Countries of the Middle East and Africa",
    "Africa_Eastern": "Countries of the Middle East and Africa",
    "Africa_Northern": "Countries of the Middle East and Africa",
    "Africa_Southern": "Countries of the Middle East and Africa",
    "Africa_Western": "Countries of the Middle East and Africa",
    "South Africa": "Countries of the Middle East and Africa",
    # Latin America
    "Brazil": "Latin American countries",
    "Argentina": "Latin American countries",
    "Colombia": "Latin American countries",
    "Central America and Caribbean": "Latin American countries",
    "South America_Northern": "Latin American countries",
    "South America_Southern": "Latin American countries",
}

# R5 → list of R32 members
R5_TO_R32: dict[str, list[str]] = {}
for _r32, _r5 in R32_TO_R5.items():
    R5_TO_R32.setdefault(_r5, []).append(_r32)


# ---------------------------------------------------------------------------
# AR6 → GHIM variable mapping
# ---------------------------------------------------------------------------

# Electricity generation: AR6 variable → list of GHIM tech names that map to it
ELEC_AR6_TO_GHIM: dict[str, list[str]] = {
    "Secondary Energy|Electricity|Coal|w/o CCS": ["coal"],
    "Secondary Energy|Electricity|Coal|w/ CCS": ["coal_ccs"],
    "Secondary Energy|Electricity|Gas|w/o CCS": ["gas_cc"],
    "Secondary Energy|Electricity|Gas|w/ CCS": ["gas_cc_ccs"],
    "Secondary Energy|Electricity|Oil": ["oil"],
    "Secondary Energy|Electricity|Biomass|w/o CCS": ["biomass"],
    "Secondary Energy|Electricity|Biomass|w/ CCS": ["biomass_ccs"],
    "Secondary Energy|Electricity|Nuclear": ["nuclear", "nuclear_advanced"],
    "Secondary Energy|Electricity|Hydro": ["hydro", "hydro_reservoir"],
    "Secondary Energy|Electricity|Solar": ["solar", "solar_csp"],
    "Secondary Energy|Electricity|Wind": ["wind", "wind_offshore"],
    "Secondary Energy|Electricity|Geothermal": ["geothermal"],
}

# Within-category default splits (for AR6 categories with multiple GHIM techs)
# These are approximate 2020 global splits; the model's cost structure
# will adjust them once preferences are applied.
WITHIN_CATEGORY_SPLITS: dict[str, dict[str, float]] = {
    "Secondary Energy|Electricity|Nuclear": {
        "nuclear": 0.95, "nuclear_advanced": 0.05,
    },
    "Secondary Energy|Electricity|Hydro": {
        "hydro": 0.60, "hydro_reservoir": 0.40,
    },
    "Secondary Energy|Electricity|Solar": {
        "solar": 0.95, "solar_csp": 0.05,
    },
    "Secondary Energy|Electricity|Wind": {
        "wind": 0.75, "wind_offshore": 0.25,
    },
}

# Final energy carriers: AR6 variable → GHIM carrier name
FE_CARRIER_AR6_TO_GHIM: dict[str, str] = {
    "Final Energy|Electricity": "electricity",
    "Final Energy|Gases": "gas",
    "Final Energy|Liquids": "liquids",
    "Final Energy|Solids|Coal": "coal",
    "Final Energy|Solids|Biomass": "biomass",
    "Final Energy|Heat": "heat",
    "Final Energy|Hydrogen": "h2",
    "Final Energy|Solar": "solar_thermal",
}

# Sector totals: AR6 variable → GHIM sector name
SECTOR_AR6_TO_GHIM: dict[str, str] = {
    "Final Energy|Industry": "industry",
    "Final Energy|Residential and Commercial": "buildings",
    "Final Energy|Transportation": "transport",
}

# SSP scenario → (model, scenario) in AR6 database
SSP_MARKERS: dict[str, tuple[str, str]] = {
    "SSP1": ("IMAGE 3.0.1", "SSP1-Baseline"),
    "SSP2": ("MESSAGE-GLOBIOM 1.0", "SSP2-Baseline"),
    "SSP3": ("AIM/CGE 2.0", "SSP3-Baseline"),
    "SSP4": ("GCAM 4.2", "SSP4-Baseline"),
    "SSP5": ("REMIND-MAgPIE 1.5", "SSP5-Baseline"),
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_ar6_raw() -> pd.DataFrame:
    """Load the AR6 SSP baselines CSV into a long-form DataFrame."""
    path = GHIM_DATA_EXT / "ssp" / "ar6_ssp_baselines.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"AR6 baselines not found at {path}. "
            "Run the pyam download script first."
        )
    # pyam CSV format: Model,Scenario,Variable,Region,Unit,year columns...
    df = pd.read_csv(path, comment="#")
    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]
    # Melt year columns to long form if needed
    if "year" not in df.columns:
        id_cols = [c for c in df.columns if not str(c).isdigit()]
        year_cols = [c for c in df.columns if str(c).isdigit()]
        df = df.melt(
            id_vars=id_cols,
            value_vars=year_cols,
            var_name="year",
            value_name="value",
        )
        df["year"] = df["year"].astype(int)
    else:
        df["year"] = df["year"].astype(int)
        df["value"] = df["value"].astype(float)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def load_ar6_scenario(
    ssp: str,
    region: str = "World",
) -> pd.DataFrame:
    """Load AR6 data for a specific SSP scenario and region.

    Parameters
    ----------
    ssp : str
        SSP scenario name (e.g. "SSP2").
    region : str
        Region name (default "World"). Can be an R5 region name.

    Returns
    -------
    DataFrame with columns: variable, year, value
    """
    if ssp not in SSP_MARKERS:
        raise ValueError(f"Unknown SSP: {ssp}. Available: {list(SSP_MARKERS)}")
    model, scenario = SSP_MARKERS[ssp]
    df = _load_ar6_raw()
    mask = (
        (df["model"] == model)
        & (df["scenario"] == scenario)
        & (df["region"] == region)
    )
    result = df.loc[mask, ["variable", "year", "value"]].copy()
    result = result.dropna(subset=["value"])
    return result


def get_ar6_elec_shares(
    ssp: str,
    year: int,
    region: str = "World",
) -> dict[str, float]:
    """Get electricity generation shares from AR6 for a given year.

    Returns dict mapping GHIM tech name → generation share (0-1).
    Technologies not present in AR6 get share 0.
    """
    df = load_ar6_scenario(ssp, region)
    total_row = df.loc[
        (df["variable"] == "Secondary Energy|Electricity") & (df["year"] == year),
        "value",
    ]
    if total_row.empty:
        return {}
    total = float(total_row.iloc[0])
    if total <= 0:
        return {}

    shares: dict[str, float] = {}
    for ar6_var, ghim_techs in ELEC_AR6_TO_GHIM.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        if row.empty:
            ar6_val = 0.0
        else:
            ar6_val = max(float(row.iloc[0]), 0.0)

        if len(ghim_techs) == 1:
            shares[ghim_techs[0]] = ar6_val / total
        else:
            # Split within category
            splits = WITHIN_CATEGORY_SPLITS.get(ar6_var, {})
            for tech in ghim_techs:
                frac = splits.get(tech, 1.0 / len(ghim_techs))
                shares[tech] = (ar6_val * frac) / total

    # Add ocean (not in AR6, set to near-zero)
    shares.setdefault("ocean", 1e-6)

    # Normalize
    total_s = sum(shares.values())
    if total_s > 0:
        shares = {k: v / total_s for k, v in shares.items()}
    return shares


def get_ar6_fe_carrier_shares(
    ssp: str,
    year: int,
    region: str = "World",
) -> dict[str, float]:
    """Get final energy carrier shares from AR6.

    Returns dict mapping GHIM carrier name → share of total final energy.
    """
    df = load_ar6_scenario(ssp, region)
    total_row = df.loc[
        (df["variable"] == "Final Energy") & (df["year"] == year), "value",
    ]
    if total_row.empty:
        return {}
    total = float(total_row.iloc[0])
    if total <= 0:
        return {}

    shares: dict[str, float] = {}
    for ar6_var, ghim_carrier in FE_CARRIER_AR6_TO_GHIM.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        val = max(float(row.iloc[0]), 0.0) if not row.empty else 0.0
        shares[ghim_carrier] = val / total

    # Normalize
    total_s = sum(shares.values())
    if total_s > 0:
        shares = {k: v / total_s for k, v in shares.items()}
    return shares


def get_ar6_sector_totals(
    ssp: str,
    year: int,
    region: str = "World",
) -> dict[str, float]:
    """Get sector final energy totals (EJ/yr) from AR6.

    Returns dict mapping GHIM sector name → EJ/yr.
    If ``Final Energy|Residential and Commercial`` is missing, computes
    buildings as: total FE − industry − transport.
    """
    df = load_ar6_scenario(ssp, region)
    totals: dict[str, float] = {}
    for ar6_var, ghim_sector in SECTOR_AR6_TO_GHIM.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        totals[ghim_sector] = max(float(row.iloc[0]), 0.0) if not row.empty else 0.0

    # If buildings is 0, compute as residual from total FE
    if totals.get("buildings", 0.0) == 0.0:
        total_fe = get_ar6_total_final_energy(ssp, year, region)
        ind = totals.get("industry", 0.0)
        trn = totals.get("transport", 0.0)
        residual = total_fe - ind - trn
        if residual > 0:
            totals["buildings"] = residual

    return totals


def get_ar6_primary_energy(
    ssp: str,
    year: int,
    region: str = "World",
) -> dict[str, float]:
    """Get primary energy by fuel (EJ/yr) from AR6."""
    df = load_ar6_scenario(ssp, region)
    pe_vars = {
        "Primary Energy|Coal": "coal",
        "Primary Energy|Oil": "oil",
        "Primary Energy|Gas": "gas",
        "Primary Energy|Nuclear": "nuclear",
        "Primary Energy|Biomass": "biomass",
    }
    result: dict[str, float] = {}
    for ar6_var, fuel in pe_vars.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        result[fuel] = max(float(row.iloc[0]), 0.0) if not row.empty else 0.0
    return result


def get_ar6_emissions(
    ssp: str,
    year: int,
    region: str = "World",
) -> dict[str, float]:
    """Get emissions (Mt CO2/yr, Mt CH4/yr) from AR6."""
    df = load_ar6_scenario(ssp, region)
    em_vars = {
        "Emissions|CO2": "co2",
        "Emissions|CO2|Energy and Industrial Processes": "co2_energy",
        "Emissions|CH4": "ch4",
    }
    result: dict[str, float] = {}
    for ar6_var, key in em_vars.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        result[key] = float(row.iloc[0]) if not row.empty else 0.0
    return result


def get_ar6_total_final_energy(
    ssp: str,
    year: int,
    region: str = "World",
) -> float:
    """Get total final energy (EJ/yr) from AR6."""
    df = load_ar6_scenario(ssp, region)
    row = df.loc[(df["variable"] == "Final Energy") & (df["year"] == year), "value"]
    return max(float(row.iloc[0]), 0.0) if not row.empty else 0.0


def get_ar6_gdp(
    ssp: str,
    year: int,
    region: str = "World",
) -> float:
    """Get GDP|PPP (billion US$2005/yr) from AR6."""
    df = load_ar6_scenario(ssp, region)
    row = df.loc[(df["variable"] == "GDP|PPP") & (df["year"] == year), "value"]
    return max(float(row.iloc[0]), 0.0) if not row.empty else 0.0


def get_ar6_population(
    ssp: str,
    year: int,
    region: str = "World",
) -> float:
    """Get Population (million) from AR6."""
    df = load_ar6_scenario(ssp, region)
    row = df.loc[(df["variable"] == "Population") & (df["year"] == year), "value"]
    return float(row.iloc[0]) if not row.empty else 0.0


# Transport-specific carrier variables (only sector with carrier detail in AR6)
TRANSPORT_CARRIER_AR6: dict[str, str] = {
    "Final Energy|Transportation|Electricity": "electricity",
    "Final Energy|Transportation|Hydrogen": "h2",
    "Final Energy|Transportation|Liquids": "liquids",
}


def get_ar6_sector_carrier_shares(
    ssp: str,
    year: int,
    sector: str,
    region: str = "World",
) -> dict[str, float]:
    """Get carrier shares within a specific demand sector from AR6.

    For transport: uses transport-specific AR6 variables (3 carriers).
    For industry/buildings: subtracts transport carriers from total FE
    to get the non-transport carrier mix (much better proxy than using
    global aggregate shares which are biased by transport's liquids).
    """
    df = load_ar6_scenario(ssp, region)

    if sector == "transport":
        total_row = df.loc[
            (df["variable"] == "Final Energy|Transportation") & (df["year"] == year),
            "value",
        ]
        if not total_row.empty:
            total = float(total_row.iloc[0])
            if total > 0:
                shares: dict[str, float] = {}
                found = False
                for ar6_var, ghim_carrier in TRANSPORT_CARRIER_AR6.items():
                    row = df.loc[
                        (df["variable"] == ar6_var) & (df["year"] == year), "value"
                    ]
                    if not row.empty:
                        shares[ghim_carrier] = max(float(row.iloc[0]), 0.0) / total
                        found = True
                if found:
                    # Carriers not in AR6 at near-zero
                    for c in ("gas", "biofuel", "biomass"):
                        shares.setdefault(c, 1e-6)
                    total_s = sum(shares.values())
                    if total_s > 0:
                        shares = {k: v / total_s for k, v in shares.items()}
                    return shares

    # --- Industry / Buildings: residual (total FE − transport) carrier shares ---
    total_fe = get_ar6_total_final_energy(ssp, year, region)
    transport_fe = 0.0
    transport_row = df.loc[
        (df["variable"] == "Final Energy|Transportation") & (df["year"] == year),
        "value",
    ]
    if not transport_row.empty:
        transport_fe = max(float(transport_row.iloc[0]), 0.0)

    non_transport_fe = total_fe - transport_fe
    if non_transport_fe <= 0:
        return get_ar6_fe_carrier_shares(ssp, year, region)

    # Get total FE by carrier
    carrier_abs: dict[str, float] = {}
    for ar6_var, ghim_carrier in FE_CARRIER_AR6_TO_GHIM.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        carrier_abs[ghim_carrier] = max(float(row.iloc[0]), 0.0) if not row.empty else 0.0

    # Subtract transport carriers
    for ar6_var, ghim_carrier in TRANSPORT_CARRIER_AR6.items():
        row = df.loc[(df["variable"] == ar6_var) & (df["year"] == year), "value"]
        if not row.empty:
            carrier_abs[ghim_carrier] = max(
                carrier_abs.get(ghim_carrier, 0.0) - max(float(row.iloc[0]), 0.0),
                0.0,
            )

    # Normalize to shares
    total_residual = sum(carrier_abs.values())
    if total_residual <= 0:
        return get_ar6_fe_carrier_shares(ssp, year, region)

    shares = {k: v / total_residual for k, v in carrier_abs.items()}
    # Ensure all carriers present at minimum
    for c in ("biofuel", "h2"):
        shares.setdefault(c, 1e-6)
    total_s = sum(shares.values())
    if total_s > 0:
        shares = {k: v / total_s for k, v in shares.items()}
    return shares


def get_ar6_years(ssp: str) -> list[int]:
    """Get available years in the AR6 data for a given SSP."""
    df = load_ar6_scenario(ssp, "World")
    return sorted(df["year"].unique().tolist())
