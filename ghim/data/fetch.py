"""Fetch GCAM Reference scenario data from BaseX database.

Extracts GDP, population, national accounts, final energy by sector × carrier,
and electricity generation by technology — for all 32 GCAM regions, all years.

Usage:
    python -m ghim.data.fetch              # Extract all tables
    python -m ghim.data.fetch --dry-run    # Show what would be extracted

Output: ghim/data/external/gcam_ref/ directory with Parquet + CSV files.

Requires: basex CLI (apt install basex) and a GCAM BaseX database at
    output/database_basexdb/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pandas as pd

from ghim.config import GHIM_DATA_EXT

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASEX_CMD = "basex"
DB_NAME = "database_basexdb"
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "output"
OUTPUT_DIR = GHIM_DATA_EXT / "gcam_ref"

BASEX_CONF = Path.home() / "basex" / ".basex"


def _ensure_dbpath() -> None:
    """Make sure ~/.basex/DBPATH points to our output/ directory."""
    if not BASEX_CONF.exists():
        return
    text = BASEX_CONF.read_text()
    target = f"DBPATH = {DB_PATH}"
    if target not in text:
        import re
        text = re.sub(r"DBPATH = .+", target, text)
        BASEX_CONF.write_text(text)


def _basex_query(xquery: str) -> str:
    """Run an XQuery against the opened database, return stdout."""
    cmd = [BASEX_CMD, "-c", f"OPEN {DB_NAME}", "-q", xquery]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"BaseX query failed:\n{result.stderr}\nQuery: {xquery[:200]}"
        )
    # Filter out warning lines
    lines = [
        ln for ln in result.stdout.splitlines()
        if not ln.startswith("[warning]")
    ]
    return "\n".join(lines)


def _parse_pipe_delimited(raw: str, columns: list[str]) -> pd.DataFrame:
    """Parse pipe-delimited BaseX output into a DataFrame."""
    if not raw.strip():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(StringIO(raw), sep="|", header=None, names=columns)
    return df


# ---------------------------------------------------------------------------
# Extraction queries
# ---------------------------------------------------------------------------

def fetch_population() -> pd.DataFrame:
    """Population (thousands) by region and year."""
    print("  Extracting population...")
    raw = _basex_query("""
for $r in /scenario/world/region
let $rname := string($r/@name)
for $p in $r/demographics/populationMiniCAM
let $year := string($p/@year)
let $pop := string($p/total-population)
return concat($rname, '|', $year, '|', $pop)
""")
    df = _parse_pipe_delimited(raw, ["region", "year", "population_thous"])
    df["year"] = df["year"].astype(int)
    df["population_thous"] = pd.to_numeric(df["population_thous"], errors="coerce")
    return df


def fetch_national_accounts() -> pd.DataFrame:
    """National accounts (GDP, capital, investment, etc.) by region and year.

    Units: million 1990$.
    """
    print("  Extracting national accounts...")
    raw = _basex_query("""
for $r in /scenario/world/region
let $rname := string($r/@name)
for $na in $r/nationalAccount
let $year := string($na/@year)
for $acc in $na/account
return concat($rname, '|', $year, '|', string($acc/@name), '|', string($acc/@unit), '|', string($acc))
""")
    df = _parse_pipe_delimited(raw, ["region", "year", "variable", "unit", "value"])
    df["year"] = df["year"].astype(int)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fetch_final_energy_by_sector_fuel() -> pd.DataFrame:
    """Final energy demand by end-use sector and fuel carrier.

    Based on Main_queries.xml "final energy consumption by sector and fuel":
      *[@type='sector' and (@name='building' or @name='industry' or
        @name='transportation' or exists(child::keyword/@final-energy))]
      //*[@type='input' and not(excluded names)]/demand-physical

    GCAM XML: technology[@year] is the period (no 'period' element).
    """
    print("  Extracting final energy by sector × fuel...")
    # Excluded inputs (from Main_queries.xml filter):
    #   limestone, process heat *, industrial energy use, industrial feedstocks,
    #   renewable, trn_*, oil-credits, waste biomass for paper
    raw = _basex_query("""
for $r in /scenario/world/region
let $rname := string($r/@name)
for $s in $r/*[@type='sector']
let $sname := string($s/@name)
where $sname = 'building' or $sname = 'industry' or $sname = 'transportation'
   or exists($s/keyword/@final-energy)
for $inp in $s//*[@type='input']
let $iname := string($inp/@name)
where not($iname = 'limestone'
   or $iname = 'process heat cement'
   or $iname = 'process heat food processing'
   or $iname = 'industrial energy use'
   or $iname = 'process heat paper'
   or $iname = 'waste biomass for paper'
   or $iname = 'industrial feedstocks'
   or $iname = 'renewable'
   or contains($iname, 'trn_')
   or $iname = 'oil-credits')
for $dp in $inp/demand-physical
where number($dp) > 0
let $year := string($dp/@vintage)
let $tech := $inp/parent::*
let $sub := $tech/parent::*
return concat($rname, '|', $sname, '|', string($sub/@name), '|',
              string($tech/@name), '|', $iname, '|', $year, '|', string($dp))
""")
    df = _parse_pipe_delimited(
        raw,
        ["region", "sector", "subsector", "technology", "fuel", "year", "demand_ej"],
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["demand_ej"] = pd.to_numeric(df["demand_ej"], errors="coerce")
    return df


def fetch_electricity_generation() -> pd.DataFrame:
    """Electricity generation (EJ) by technology, region, year.

    Based on Main_queries.xml "elec gen by gen tech":
      *[@type='sector' and (@name='electricity' or ...)]
      /*[@type='subsector']/*[@type='technology']
      /*[@type='output' and @name='electricity']/physical-output
    """
    print("  Extracting electricity generation...")
    raw = _basex_query("""
for $r in /scenario/world/region
let $rname := string($r/@name)
for $s in $r/*[@type='sector']
let $sname := string($s/@name)
where $sname = 'electricity' or $sname = 'elect_td_bld'
   or $sname = 'industrial energy use'
for $sub in $s/*[@type='subsector']
for $tech in $sub/*[@type='technology']
let $tname := string($tech/@name)
where not($tname = 'electricity' or $tname = 'elect_td_bld')
for $out in $tech/*[@type='output']
let $oname := string($out/@name)
where $oname = 'electricity' or $oname = 'elect_td_bld'
for $po in $out/physical-output
where number($po) > 0
return concat($rname, '|', $sname, '|', string($sub/@name), '|',
              $tname, '|', string($po/@vintage), '|', string($po))
""")
    df = _parse_pipe_delimited(
        raw, ["region", "sector", "subsector", "technology", "year", "generation_ej"],
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["generation_ej"] = pd.to_numeric(df["generation_ej"], errors="coerce")
    return df


def fetch_primary_energy() -> pd.DataFrame:
    """Primary energy production by resource type, region, year.

    Based on Main_queries.xml "resource production".
    """
    print("  Extracting primary energy...")
    raw = _basex_query("""
for $r in /scenario/world/region
let $rname := string($r/@name)
for $res in $r/resource
let $resname := string($res/@name)
where not(contains($resname, 'water'))
for $sub in $res/subresource
for $tech in $sub/technology
for $out in $tech/*/physical-output
where number($out) > 0
return concat($rname, '|', $resname, '|', string($sub/@name), '|',
              string($out/@vintage), '|', string($out))
""")
    df = _parse_pipe_delimited(
        raw, ["region", "resource", "subresource", "year", "production_ej"],
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["production_ej"] = pd.to_numeric(df["production_ej"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def _save(df: pd.DataFrame, name: str, output_dir: Path) -> None:
    """Save as both Parquet and CSV."""
    df.to_parquet(output_dir / f"{name}.parquet", index=False)
    df.to_csv(output_dir / f"{name}.csv", index=False)
    print(f"    {name}: {len(df):,} rows → {name}.parquet + .csv")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract GCAM Reference data from BaseX")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would extract to: {args.output}")
        print("Tables: population, national_accounts, final_energy, electricity_gen, primary_energy")
        return

    _ensure_dbpath()
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"Extracting GCAM Reference data → {args.output}\n")

    pop = fetch_population()
    _save(pop, "population", args.output)

    na = fetch_national_accounts()
    _save(na, "national_accounts", args.output)

    fe = fetch_final_energy_by_sector_fuel()
    _save(fe, "final_energy", args.output)

    elec = fetch_electricity_generation()
    _save(elec, "electricity_gen", args.output)

    pe = fetch_primary_energy()
    _save(pe, "primary_energy", args.output)

    print(f"\nDone. Files saved to {args.output}")


if __name__ == "__main__":
    main()
