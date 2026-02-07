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
    # Policy arguments
    parser.add_argument(
        "--policy", default=None,
        help="Path to JSON policy scenario file",
    )
    parser.add_argument(
        "--carbon-price", type=float, default=0.0,
        help="Constant carbon price in $/tCO2 (default: 0)",
    )
    parser.add_argument(
        "--efficiency-rate", type=float, default=0.0,
        help="Annual energy efficiency improvement rate (e.g. 0.01 for 1%%)",
    )
    parser.add_argument(
        "--recycling-fraction", type=float, default=0.0,
        help="Fraction of carbon revenue recycled (0-1, default: 0)",
    )
    parser.add_argument(
        "--no-trade", action="store_true",
        help="Disable inter-regional primary energy trade",
    )
    args = parser.parse_args()

    # Build policy scenario
    from ghim.policy import load_policy, policy_from_cli, PolicyScenario
    policy: PolicyScenario | None = None
    if args.policy:
        policy = load_policy(args.policy)
        print(f"Loaded policy: {policy.name}")
    elif args.carbon_price > 0 or args.efficiency_rate > 0 or args.recycling_fraction > 0:
        policy = policy_from_cli(
            carbon_price=args.carbon_price,
            efficiency_rate=args.efficiency_rate,
            recycling_fraction=args.recycling_fraction,
        )
        print(f"Policy: carbon_price=${args.carbon_price}/tCO2, "
              f"efficiency={args.efficiency_rate}, recycling={args.recycling_fraction}")

    print(f"Loading SSP data for scenario {args.scenario}...")
    from ghim.data.ssp import load_ssp_data
    ssp_data = load_ssp_data(args.scenario)

    print(f"Running model for {len(ssp_data['population'])} regions...")
    from ghim.solver.recursive import run_model
    trade_enabled = not args.no_trade
    if not trade_enabled:
        print("Trade disabled (--no-trade)")
    results = run_model(ssp_data, args.scenario, policy=policy, trade_enabled=trade_enabled)

    from ghim.output.reporting import print_summary, export_csv
    print_summary(results)

    if not args.no_csv:
        output_dir = Path(args.output_dir)
        export_csv(results, output_dir)
        print(f"\nResults exported to {output_dir}/")


if __name__ == "__main__":
    main()
