#!/usr/bin/env python3
"""Preprocess GEM Excel trackers into aggregated vintage capacity CSV.

Reads Global Energy Monitor (GEM) Excel tracker files, filters for
operating plants, maps to R10 regions, bins start years into 5-year
periods, converts MW to EJ/yr, and writes a single aggregated CSV.

Usage:
    python scripts/preprocess_gem.py --input-dir /path/to/gem_trackers/
    python scripts/preprocess_gem.py --input-dir data/mapping/gem/ --output ghim/data/external/energy/gem_vintage_capacity_r10.csv

The input directory should contain GEM Excel files with names like:
  - Global-Coal-Plant-Tracker-*.xlsx
  - Global-Gas-Plant-Tracker-*.xlsx  (or Oil-Gas combined)
  - Global-Nuclear-Power-Tracker-*.xlsx
  - Global-Hydropower-Tracker-*.xlsx
  - Global-Wind-Power-Tracker-*.xlsx
  - Global-Solar-Power-Tracker-*.xlsx
  - Global-Bioenergy-Power-Tracker-*.xlsx
"""

from __future__ import annotations

import argparse
import csv
import difflib
import sys
from pathlib import Path

import pandas as pd

# Add repo root for ghim imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ghim.config import GHIM_DATA_EXT, TIMESTEP, BASE_YEAR

DEFAULT_OUTPUT = GHIM_DATA_EXT / "energy" / "gem_vintage_capacity_r10.csv"

# ---- Constants ----

# Capacity factors for MW→EJ conversion
CAPACITY_FACTORS: dict[str, float] = {
    "coal": 0.60,
    "gas_cc": 0.45,
    "nuclear": 0.85,
    "hydro": 0.40,
    "wind": 0.30,
    "solar": 0.18,
    "biomass": 0.50,
    "oil": 0.20,
}

# GEM tracker file pattern → GHIM tech name mapping
TRACKER_TECH_MAP: dict[str, str] = {
    "coal": "coal",
    "nuclear": "nuclear",
    "hydro": "hydro",
    "hydropower": "hydro",
    "wind": "wind",
    "solar": "solar",
    "bioenergy": "biomass",
}

# GEM oil/gas tracker: fuel column values → tech
OIL_GAS_FUEL_MAP: dict[str, str] = {
    "gas": "gas_cc",
    "natural gas": "gas_cc",
    "lng": "gas_cc",
    "methane": "gas_cc",
    "oil": "oil",
    "diesel": "oil",
    "fuel oil": "oil",
    "petroleum": "oil",
    "crude": "oil",
    "coal": "coal",  # some multi-fuel trackers
}

OLDEST_VINTAGE = 1960


def _load_region_map() -> dict[str, str]:
    """Load country name → R10 region mapping."""
    tsv_path = GHIM_DATA_EXT / "region_classification.tsv"
    region_map: dict[str, str] = {}
    with open(tsv_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            name = row["name"].strip()
            region = row["region_ar6_10"].strip()
            region_map[name] = region
            # Also index by lowercase for fuzzy matching
            region_map[name.lower()] = region
    return region_map


def _match_country(name: str, region_map: dict[str, str]) -> str | None:
    """Map a country name to R10 region, with fuzzy fallback."""
    # Exact match
    if name in region_map:
        return region_map[name]
    if name.lower() in region_map:
        return region_map[name.lower()]

    # Fuzzy match on lowercase keys
    lower_keys = [k for k in region_map if k == k.lower()]
    matches = difflib.get_close_matches(name.lower(), lower_keys, n=1, cutoff=0.8)
    if matches:
        return region_map[matches[0]]
    return None


def _bin_year(year: float | int, oldest: int = OLDEST_VINTAGE, newest: int = BASE_YEAR) -> int:
    """Round year to nearest TIMESTEP boundary, clamped to [oldest, newest]."""
    yr = int(round(year))
    yr = max(oldest, min(yr, newest))
    # Round to nearest TIMESTEP
    return round(yr / TIMESTEP) * TIMESTEP


def _mw_to_ej(mw: float, capacity_factor: float) -> float:
    """Convert MW capacity to EJ/yr output."""
    return mw * capacity_factor * 8760 * 3600 / 1e18


def _detect_tech_from_filename(filename: str) -> str | None:
    """Infer tech type from GEM tracker filename."""
    fname = filename.lower()
    for pattern, tech in TRACKER_TECH_MAP.items():
        if pattern in fname:
            return tech
    if "oil" in fname or "gas" in fname:
        return "oil_gas"  # special: needs fuel column splitting
    return None


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first matching column name (case-insensitive)."""
    lower_cols = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_cols:
            return lower_cols[cand.lower()]
    return None


def process_tracker(
    filepath: Path,
    region_map: dict[str, str],
    stats: dict,
) -> list[dict]:
    """Process a single GEM Excel tracker file.

    Returns list of {region, tech, vintage_year, capacity_mw, capacity_ej_yr}.
    """
    tech = _detect_tech_from_filename(filepath.name)
    if tech is None:
        print(f"  WARNING: Cannot determine tech from filename: {filepath.name}")
        return []

    # Read Excel — try first sheet
    try:
        df = pd.read_excel(filepath, sheet_name=0)
    except Exception as e:
        print(f"  ERROR reading {filepath.name}: {e}")
        return []

    # Find relevant columns
    status_col = _find_column(df, ["Status", "status", "Plant status"])
    country_col = _find_column(df, ["Country/area", "Country", "Country/Area", "country"])
    capacity_col = _find_column(df, ["Capacity (MW)", "Capacity(MW)", "capacity_mw", "Capacity MW"])
    start_col = _find_column(df, [
        "Start year", "Commission year", "Start Year",
        "Commissioning year", "Year of commissioning",
        "Operating start year",
    ])
    fuel_col = _find_column(df, ["Fuel", "fuel", "Fuel type", "Technology"])

    if status_col is None or country_col is None or capacity_col is None:
        print(f"  WARNING: Missing required columns in {filepath.name}")
        print(f"    Available: {list(df.columns[:10])}")
        return []

    # Filter to operating plants
    df = df[df[status_col].astype(str).str.lower().str.strip() == "operating"].copy()
    if df.empty:
        print(f"  No operating plants in {filepath.name}")
        return []

    # Convert capacity to numeric
    df[capacity_col] = pd.to_numeric(df[capacity_col], errors="coerce")
    df = df.dropna(subset=[capacity_col])

    # Handle start year
    if start_col:
        df[start_col] = pd.to_numeric(df[start_col], errors="coerce")

    records: list[dict] = []
    unmatched_countries: set[str] = set()
    imputed_years = 0

    for _, row in df.iterrows():
        country = str(row[country_col]).strip()
        region = _match_country(country, region_map)
        if region is None:
            unmatched_countries.add(country)
            continue

        mw = float(row[capacity_col])
        if mw <= 0:
            continue

        # Determine tech for oil/gas tracker
        row_tech = tech
        if tech == "oil_gas" and fuel_col:
            fuel_val = str(row.get(fuel_col, "")).lower().strip()
            row_tech = OIL_GAS_FUEL_MAP.get(fuel_val, "gas_cc")
        elif tech == "oil_gas":
            row_tech = "gas_cc"

        # Vintage year
        if start_col and pd.notna(row.get(start_col)):
            vintage = _bin_year(row[start_col])
        else:
            vintage = BASE_YEAR  # will be overwritten by median imputation
            imputed_years += 1

        cf = CAPACITY_FACTORS.get(row_tech, 0.40)
        ej = _mw_to_ej(mw, cf)

        records.append({
            "region": region,
            "tech": row_tech,
            "vintage_year": vintage,
            "capacity_mw": mw,
            "capacity_ej_yr": ej,
        })

    # Impute missing start years with median of same tech+region
    if imputed_years > 0 and start_col:
        # Compute medians from records that have real years
        from collections import defaultdict
        medians: dict[tuple[str, str], float] = {}
        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for rec in records:
            if rec["vintage_year"] != BASE_YEAR or imputed_years == 0:
                groups[(rec["tech"], rec["region"])].append(rec["vintage_year"])
        for key, yrs in groups.items():
            if yrs:
                medians[key] = _bin_year(sorted(yrs)[len(yrs) // 2])
        # Apply
        for rec in records:
            if rec["vintage_year"] == BASE_YEAR and imputed_years > 0:
                key = (rec["tech"], rec["region"])
                if key in medians:
                    rec["vintage_year"] = int(medians[key])

    stats[filepath.name] = {
        "records": len(records),
        "unmatched_countries": unmatched_countries,
        "imputed_years": imputed_years,
        "total_mw": sum(r["capacity_mw"] for r in records),
    }

    return records


def aggregate_records(records: list[dict]) -> pd.DataFrame:
    """Aggregate records by (region, tech, vintage_year)."""
    df = pd.DataFrame(records)
    if df.empty:
        return df
    agg = df.groupby(["region", "tech", "vintage_year"]).agg({
        "capacity_mw": "sum",
        "capacity_ej_yr": "sum",
    }).reset_index()
    return agg.sort_values(["region", "tech", "vintage_year"])


def main():
    parser = argparse.ArgumentParser(description="Preprocess GEM trackers to vintage CSV")
    parser.add_argument(
        "--input-dir", type=Path, required=True,
        help="Directory containing GEM Excel tracker files",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if not args.input_dir.exists():
        print(f"ERROR: Input directory does not exist: {args.input_dir}")
        sys.exit(1)

    # Find Excel files
    excel_files = sorted(args.input_dir.glob("*.xlsx")) + sorted(args.input_dir.glob("*.xls"))
    if not excel_files:
        print(f"ERROR: No Excel files found in {args.input_dir}")
        sys.exit(1)

    print(f"Found {len(excel_files)} Excel tracker files")

    region_map = _load_region_map()
    all_records: list[dict] = []
    stats: dict = {}

    for filepath in excel_files:
        print(f"Processing: {filepath.name}")
        records = process_tracker(filepath, region_map, stats)
        all_records.extend(records)

    if not all_records:
        print("ERROR: No records extracted from any tracker file")
        sys.exit(1)

    # Aggregate and write
    agg_df = aggregate_records(all_records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    agg_df.to_csv(args.output, index=False)
    print(f"\nWrote {len(agg_df)} aggregated records to {args.output}")

    # Validation summary
    print("\n=== Validation Summary ===\n")
    total_by_tech: dict[str, float] = {}
    for rec in all_records:
        tech = rec["tech"]
        total_by_tech[tech] = total_by_tech.get(tech, 0.0) + rec["capacity_mw"]

    print("Total capacity by tech (GW):")
    for tech in sorted(total_by_tech, key=lambda t: -total_by_tech[t]):
        gw = total_by_tech[tech] / 1000
        print(f"  {tech:>12}: {gw:>8.1f} GW")

    print("\nPer-tracker statistics:")
    all_unmatched: set[str] = set()
    total_imputed = 0
    for name, s in stats.items():
        print(f"  {name}: {s['records']} records, {s['total_mw']/1000:.1f} GW")
        if s["unmatched_countries"]:
            print(f"    Unmatched countries: {sorted(s['unmatched_countries'])}")
            all_unmatched.update(s["unmatched_countries"])
        if s["imputed_years"]:
            print(f"    Imputed start years: {s['imputed_years']}")
            total_imputed += s["imputed_years"]

    if all_unmatched:
        print(f"\nAll unmatched countries ({len(all_unmatched)}): {sorted(all_unmatched)}")
    print(f"Total imputed start years: {total_imputed}")


if __name__ == "__main__":
    main()
