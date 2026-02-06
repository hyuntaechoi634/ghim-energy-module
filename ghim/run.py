"""CLI entry point for the GHIM Energy Model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GHIM Energy Module - Recursive-dynamic energy model"
    )
    parser.add_argument(
        "--scenario", default="SSP2",
        choices=["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"],
        help="SSP scenario to run (default: SSP2)",
    )
    parser.add_argument(
        "--output-dir", default="ghim_output",
        help="Directory for output CSV files (default: ghim_output)",
    )
    parser.add_argument(
        "--no-csv", action="store_true",
        help="Skip CSV export, only print summary",
    )
    args = parser.parse_args()

    print(f"Loading SSP data for scenario {args.scenario}...")
    from ghim.data.ssp import load_ssp_data
    ssp_data = load_ssp_data(args.scenario)

    print(f"Running model for {len(ssp_data['population'])} regions...")
    from ghim.solver.recursive import run_model
    results = run_model(ssp_data, args.scenario)

    from ghim.output.reporting import print_summary, export_csv
    print_summary(results)

    if not args.no_csv:
        output_dir = Path(args.output_dir)
        export_csv(results, output_dir)
        print(f"\nResults exported to {output_dir}/")


if __name__ == "__main__":
    main()
