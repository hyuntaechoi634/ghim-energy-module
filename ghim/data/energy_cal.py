"""Load and process energy calibration data from GCAM, aggregated to R10.

This module reads the technology mapping (calibrated_techs.csv) which defines
the GCAM energy sector structure.  Actual base-year energy balance values
(EJ by region/sector/fuel) come from pre-processed IEA data or will be
populated with representative defaults when IEA proprietary data is unavailable.

Region keys use AR6 R10 names from ghim/data/external/region_classification.tsv.
"""

from __future__ import annotations

import pandas as pd

from ghim.data.loader import read_gcam_csv


def load_calibrated_techs() -> pd.DataFrame:
    """Load the calibrated technology mapping.

    Returns DataFrame with columns:
        sector, fuel, supplysector, subsector, technology,
        minicam.energy.input, calibration, secondary.output
    """
    return read_gcam_csv("energy/calibrated_techs.csv")


def load_fuel_mappings() -> pd.DataFrame:
    """Load IEA product -> GCAM fuel mapping."""
    return read_gcam_csv("energy/IEA_product_fuel.csv")


def get_electricity_techs() -> pd.DataFrame:
    """Return only electricity generation technologies from calibrated_techs."""
    df = load_calibrated_techs()
    return df[df["sector"] == "electricity generation"].copy()


def get_refining_techs() -> pd.DataFrame:
    """Return refining-related technologies."""
    df = load_calibrated_techs()
    mask = df["supplysector"].str.contains("refining", case=False, na=False)
    return df[mask].copy()


def get_hydrogen_techs() -> pd.DataFrame:
    """Return hydrogen production technologies."""
    df = load_calibrated_techs()
    mask = df["supplysector"].str.contains("H2", case=False, na=False) | \
           df["technology"].str.contains("hydrogen|H2", case=False, na=False)
    return df[mask].copy()


def get_demand_sectors() -> list[str]:
    """Return the list of final energy demand sector names."""
    df = load_calibrated_techs()
    exclude = {
        "electricity generation", "gas processing", "electricity ownuse",
        "electricity distribution", "gas pipeline", "heat",
    }
    demand = df[
        (df["calibration"] == "input")
        & (~df["sector"].isin(exclude))
    ]
    return sorted(demand["sector"].unique().tolist())


# ---------------------------------------------------------------------------
# Default base-year energy balance (EJ) for AR6 R10 regions
# Approximate values based on IEA 2020 data.
# ---------------------------------------------------------------------------

_FUELS = ["coal", "gas", "oil", "nuclear", "hydro", "wind", "solar", "biomass", "geothermal"]

DEFAULT_PRIMARY_ENERGY: dict[str, dict[str, float]] = {
    "North America":        {"coal": 12.0, "gas": 35.0, "oil": 28.0, "nuclear": 8.8, "hydro": 3.0, "wind": 3.5, "solar": 2.0, "biomass": 5.0, "geothermal": 0.3},
    "Europe":               {"coal": 5.0, "gas": 8.0, "oil": 5.0, "nuclear": 7.5, "hydro": 2.8, "wind": 4.5, "solar": 1.8, "biomass": 6.0, "geothermal": 0.2},
    "Asia-Pacific Developed":{"coal": 3.5, "gas": 5.0, "oil": 1.5, "nuclear": 3.0, "hydro": 1.2, "wind": 0.5, "solar": 1.0, "biomass": 1.0, "geothermal": 0.4},
    "Eurasia":              {"coal": 6.5, "gas": 27.0, "oil": 24.0, "nuclear": 2.2, "hydro": 2.0, "wind": 0.1, "solar": 0.05, "biomass": 1.0, "geothermal": 0.05},
    "Eastern Asia":         {"coal": 82.0, "gas": 7.0, "oil": 8.0, "nuclear": 3.5, "hydro": 4.5, "wind": 5.0, "solar": 3.0, "biomass": 4.5, "geothermal": 0.1},
    "Southern Asia":        {"coal": 16.0, "gas": 2.0, "oil": 1.5, "nuclear": 1.2, "hydro": 1.5, "wind": 1.5, "solar": 1.2, "biomass": 8.0, "geothermal": 0.01},
    "South-East Asia and developing Pacific": {"coal": 5.0, "gas": 9.0, "oil": 5.5, "nuclear": 0.3, "hydro": 1.2, "wind": 0.2, "solar": 0.3, "biomass": 6.0, "geothermal": 1.0},
    "Middle East":          {"coal": 0.1, "gas": 22.0, "oil": 50.0, "nuclear": 0.1, "hydro": 0.2, "wind": 0.05, "solar": 0.1, "biomass": 0.1, "geothermal": 0.0},
    "Latin America and Caribbean": {"coal": 0.8, "gas": 6.0, "oil": 14.0, "nuclear": 0.5, "hydro": 5.5, "wind": 1.0, "solar": 0.5, "biomass": 6.0, "geothermal": 0.2},
    "Africa":               {"coal": 4.0, "gas": 6.5, "oil": 7.5, "nuclear": 0.15, "hydro": 1.0, "wind": 0.1, "solar": 0.1, "biomass": 10.0, "geothermal": 0.1},
}

DEFAULT_ELEC_SHARES: dict[str, dict[str, float]] = {
    "North America":        {"coal": 0.20, "gas_cc": 0.40, "nuclear": 0.20, "hydro": 0.07, "wind": 0.08, "solar": 0.03, "biomass": 0.01, "oil": 0.01},
    "Europe":               {"coal": 0.15, "gas_cc": 0.20, "nuclear": 0.25, "hydro": 0.12, "wind": 0.15, "solar": 0.06, "biomass": 0.06, "oil": 0.01},
    "Asia-Pacific Developed":{"coal": 0.25, "gas_cc": 0.30, "nuclear": 0.15, "hydro": 0.08, "wind": 0.04, "solar": 0.08, "biomass": 0.05, "oil": 0.05},
    "Eurasia":              {"coal": 0.15, "gas_cc": 0.45, "nuclear": 0.18, "hydro": 0.18, "wind": 0.01, "solar": 0.005, "biomass": 0.01, "oil": 0.015},
    "Eastern Asia":         {"coal": 0.62, "gas_cc": 0.03, "nuclear": 0.05, "hydro": 0.17, "wind": 0.06, "solar": 0.04, "biomass": 0.02, "oil": 0.01},
    "Southern Asia":        {"coal": 0.70, "gas_cc": 0.04, "nuclear": 0.03, "hydro": 0.10, "wind": 0.05, "solar": 0.05, "biomass": 0.02, "oil": 0.01},
    "South-East Asia and developing Pacific": {"coal": 0.35, "gas_cc": 0.30, "nuclear": 0.02, "hydro": 0.10, "wind": 0.02, "solar": 0.02, "biomass": 0.05, "oil": 0.14},
    "Middle East":          {"coal": 0.01, "gas_cc": 0.65, "nuclear": 0.005, "hydro": 0.02, "wind": 0.005, "solar": 0.01, "biomass": 0.0, "oil": 0.30},
    "Latin America and Caribbean": {"coal": 0.05, "gas_cc": 0.20, "nuclear": 0.02, "hydro": 0.55, "wind": 0.08, "solar": 0.03, "biomass": 0.05, "oil": 0.02},
    "Africa":               {"coal": 0.30, "gas_cc": 0.30, "nuclear": 0.02, "hydro": 0.18, "wind": 0.03, "solar": 0.02, "biomass": 0.03, "oil": 0.12},
}

DEFAULT_ELEC_TOTAL_EJ: dict[str, float] = {
    "North America":         18.5,
    "Europe":                13.0,
    "Asia-Pacific Developed": 7.5,
    "Eurasia":                5.5,
    "Eastern Asia":          28.0,
    "Southern Asia":          6.0,
    "South-East Asia and developing Pacific": 5.0,
    "Middle East":            4.5,
    "Latin America and Caribbean": 5.0,
    "Africa":                 3.5,
}

DEFAULT_FINAL_DEMAND: dict[str, dict[str, float]] = {
    "North America":        {"industry": 18.0, "buildings": 20.0, "transport": 28.0},
    "Europe":               {"industry": 13.0, "buildings": 18.0, "transport": 14.0},
    "Asia-Pacific Developed":{"industry": 8.0, "buildings": 7.0, "transport": 6.0},
    "Eurasia":              {"industry": 10.0, "buildings": 10.0, "transport": 6.0},
    "Eastern Asia":         {"industry": 45.0, "buildings": 15.0, "transport": 15.0},
    "Southern Asia":        {"industry": 12.0, "buildings": 8.0, "transport": 5.0},
    "South-East Asia and developing Pacific": {"industry": 10.0, "buildings": 6.0, "transport": 6.0},
    "Middle East":          {"industry": 8.0, "buildings": 5.0, "transport": 8.0},
    "Latin America and Caribbean": {"industry": 8.0, "buildings": 5.0, "transport": 10.0},
    "Africa":               {"industry": 4.0, "buildings": 8.0, "transport": 4.0},
}
