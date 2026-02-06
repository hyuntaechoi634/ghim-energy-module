"""Base data loading utilities for reading GCAM-format CSV files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ghim.config import GCAMDATA_EXT


def read_gcam_csv(rel_path: str, **kwargs) -> pd.DataFrame:
    """Read a GCAM-style CSV file (with ``#`` comment header) from extdata.

    Parameters
    ----------
    rel_path : str
        Path relative to ``input/gcamdata/inst/extdata/``.
    **kwargs
        Forwarded to :func:`pandas.read_csv`.
    """
    full_path = GCAMDATA_EXT / rel_path
    return pd.read_csv(full_path, comment="#", **kwargs)


def load_iso_gcam_mapping() -> pd.DataFrame:
    """Load the ISO → GCAM region ID mapping.

    Returns a DataFrame with columns: iso, country_name, GCAM_region_ID.
    """
    df = read_gcam_csv("common/iso_GCAM_regID.csv")
    return df[["iso", "country_name", "GCAM_region_ID"]]


def load_gcam_region_names() -> dict[int, str]:
    """Return a dict mapping GCAM_region_ID → region name."""
    df = read_gcam_csv("common/GCAM_region_names.csv")
    return dict(zip(df["GCAM_region_ID"], df["region"]))
