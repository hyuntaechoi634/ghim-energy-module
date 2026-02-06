"""Load and process SSP scenario data (population, GDP) aggregated to R10.

Uses the direct ISO → AR6 R10 mapping from mapping/region_classification.tsv.
"""

from __future__ import annotations

import pandas as pd

from ghim.config import GCAMDATA_EXT, MODEL_YEARS, DEFAULT_SSP
from ghim.regions import R10_REGIONS, build_iso_to_r10


def _load_ssp_raw() -> pd.DataFrame:
    """Load the compressed SSP database, returning only Population and GDP|PPP rows."""
    path = GCAMDATA_EXT / "socioeconomics" / "SSP" / "SSP_database_2024.csv.gz"
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
        GCAMDATA_EXT / "socioeconomics" / "SSP" / "iso_SSP_regID.csv",
        comment="#",
    )
    # Direct ISO → R10 mapping (uppercase ISO codes)
    iso_to_r10 = build_iso_to_r10()

    # Convert iso_ssp iso codes to uppercase to match
    iso_ssp["ISO_upper"] = iso_ssp["iso"].str.upper()
    iso_ssp["r10"] = iso_ssp["ISO_upper"].map(iso_to_r10)

    return dict(zip(iso_ssp["ssp_country_name"], iso_ssp["r10"]))


def load_ssp_data(scenario: str = DEFAULT_SSP) -> dict[str, pd.DataFrame]:
    """Load SSP population and GDP for a given scenario, aggregated to R10.

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

    # Filter to the requested scenario
    df = raw[raw["Scenario"] == scenario].copy()

    # Map countries to R10
    df["r10"] = df["Region"].map(country_to_r10)
    df = df.dropna(subset=["r10"])

    # Select only the year columns we need
    year_cols = [str(y) for y in MODEL_YEARS]
    available_cols = [c for c in year_cols if c in df.columns]

    result = {}
    for var_name, label in [("Population", "population"), ("GDP|PPP", "gdp")]:
        sub = df[df["Variable"] == var_name].copy()
        for c in available_cols:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        agg = sub.groupby("r10")[available_cols].sum()
        agg = agg.reindex(R10_REGIONS, fill_value=0.0)
        agg.columns = [int(c) for c in agg.columns]
        result[label] = agg

    return result
