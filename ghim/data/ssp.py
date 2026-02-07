"""Load and process SSP scenario data (population, GDP) aggregated to R10.

Uses the direct ISO → AR6 R10 mapping from ghim/data/external/region_classification.tsv.
Merges real historical data from the "Historical Reference" scenario (pre-2020)
with SSP scenario projections (2020+). Extends to 2150 via extrapolation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ghim.config import GHIM_DATA_EXT, MODEL_YEARS, DEFAULT_SSP, BASE_YEAR, END_YEAR, TIMESTEP
from ghim.regions import R10_REGIONS, build_iso_to_r10


def _load_ssp_raw() -> pd.DataFrame:
    """Load the compressed SSP database, returning only Population and GDP|PPP rows."""
    path = GHIM_DATA_EXT / "ssp" / "SSP_database_2024.csv.gz"
    df = pd.read_csv(path, comment="#")
    mask = df["Variable"].isin(["Population", "GDP|PPP"])
    return df.loc[mask].copy()


def _build_ssp_country_to_r10() -> dict[str, str]:
    """Map SSP country names to R10 via ISO codes.

    Chain: SSP country name → ISO (from iso_SSP_regID.csv) → R10 (from
    mapping/region_classification.tsv, direct mapping).
    """
    # SSP country name ↔ ISO (lowercase in this file)
    iso_ssp = pd.read_csv(
        GHIM_DATA_EXT / "ssp" / "iso_SSP_regID.csv",
        comment="#",
    )
    # Direct ISO → R10 mapping (uppercase ISO codes)
    iso_to_r10 = build_iso_to_r10()

    # Convert iso_ssp iso codes to uppercase to match
    iso_ssp["ISO_upper"] = iso_ssp["iso"].str.upper()
    iso_ssp["r10"] = iso_ssp["ISO_upper"].map(iso_to_r10)

    return dict(zip(iso_ssp["ssp_country_name"], iso_ssp["r10"]))


def _extrapolate_beyond(df: pd.DataFrame, last_data_year: int = 2100) -> pd.DataFrame:
    """Extrapolate DataFrame columns beyond last_data_year using trailing growth rate.

    For GDP: uses compound annual growth rate from 2090-2100.
    For population: uses linear extrapolation from last two data points.
    """
    existing_years = sorted([c for c in df.columns if isinstance(c, int)])
    needed_years = [y for y in MODEL_YEARS if y > last_data_year]

    if not needed_years:
        return df

    # Find the last two available data years for growth rate calculation
    available = [y for y in existing_years if y <= last_data_year]
    if len(available) < 2:
        # Not enough data to extrapolate — fill with last known value
        last_val = df[available[-1]] if available else 0.0
        for y in needed_years:
            df[y] = last_val
        return df

    y_prev = available[-2]  # e.g. 2090
    y_last = available[-1]  # e.g. 2100
    dt_ref = y_last - y_prev

    for y in needed_years:
        dt = TIMESTEP
        # Per-region growth rate from last interval
        ratio = df[y_last] / df[y_prev].replace(0, np.nan)
        ratio = ratio.fillna(1.0)
        # Annualize: (ratio)^(1/dt_ref) gives annual growth
        annual_growth = ratio ** (1.0 / dt_ref)
        # Apply for dt years from previous column
        prev_year = y - TIMESTEP
        if prev_year in df.columns:
            df[y] = df[prev_year] * annual_growth ** dt
        else:
            # Fallback: extrapolate from last known
            years_beyond = y - y_last
            df[y] = df[y_last] * annual_growth ** years_beyond

    return df


def _aggregate_to_r10(
    df: pd.DataFrame,
    var_name: str,
    year_cols: list[str],
    country_to_r10: dict[str, str],
) -> pd.DataFrame:
    """Aggregate country-level data to R10 for a single variable.

    Returns DataFrame with index=R10_REGIONS, columns=int years.
    """
    sub = df[df["Variable"] == var_name].copy()
    sub["r10"] = sub["Region"].map(country_to_r10)
    sub = sub.dropna(subset=["r10"])
    available = [c for c in year_cols if c in sub.columns]
    for c in available:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    agg = sub.groupby("r10")[available].sum()
    agg = agg.reindex(R10_REGIONS, fill_value=0.0)
    agg.columns = [int(c) for c in agg.columns]
    return agg


def load_ssp_data(scenario: str = DEFAULT_SSP) -> dict[str, pd.DataFrame]:
    """Load SSP population and GDP for a given scenario, aggregated to R10.

    Merges real historical data from the "Historical Reference" scenario
    (years before BASE_YEAR) with SSP scenario projections (BASE_YEAR onward).

    Parameters
    ----------
    scenario : str
        One of "SSP1", "SSP2", "SSP3", "SSP4", "SSP5".

    Returns
    -------
    dict with keys ``"population"`` and ``"gdp"``, each a DataFrame
    with index=R10 region, columns=model years (int), values in
    millions (pop) and billion USD_2017 PPP (gdp).
    """
    raw = _load_ssp_raw()
    country_to_r10 = _build_ssp_country_to_r10()

    # Validate scenario
    df_ssp = raw[raw["Scenario"] == scenario]
    if df_ssp.empty:
        valid = sorted(raw["Scenario"].unique())
        raise ValueError(
            f"SSP scenario '{scenario}' not found in database. "
            f"Valid scenarios: {valid}"
        )

    df_hist = raw[raw["Scenario"] == "Historical Reference"]

    all_year_cols = [str(y) for y in MODEL_YEARS]

    result = {}
    for var_name, label in [("Population", "population"), ("GDP|PPP", "gdp")]:
        # Aggregate SSP scenario data (2020+)
        agg_ssp = _aggregate_to_r10(df_ssp, var_name, all_year_cols, country_to_r10)

        # Aggregate Historical Reference data (pre-2020)
        agg_hist = _aggregate_to_r10(df_hist, var_name, all_year_cols, country_to_r10)

        # Merge: historical for years < BASE_YEAR, SSP for years >= BASE_YEAR
        merged = pd.DataFrame(index=R10_REGIONS)
        for y in MODEL_YEARS:
            if y < BASE_YEAR and y in agg_hist.columns:
                merged[y] = agg_hist[y]
            elif y in agg_ssp.columns:
                merged[y] = agg_ssp[y]
            elif y in agg_hist.columns:
                # Fallback to historical if SSP doesn't have this year
                merged[y] = agg_hist[y]
            else:
                merged[y] = 0.0

        # Extrapolate beyond 2100
        merged = _extrapolate_beyond(merged, last_data_year=2100)

        # Reorder columns to MODEL_YEARS
        final_cols = [y for y in MODEL_YEARS if y in merged.columns]
        result[label] = merged[final_cols]

    return result
