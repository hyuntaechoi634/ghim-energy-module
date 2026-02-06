"""Results collection and export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ghim.solver.recursive import PeriodResult


def results_to_dataframe(results: list[PeriodResult]) -> pd.DataFrame:
    """Convert a list of PeriodResults to a flat DataFrame."""
    rows = []
    for r in results:
        base = {
            "year": r.year,
            "region": r.region,
            "gdp_billion_usd": r.gdp,
            "population_million": r.population,
            "total_energy_ej": r.total_energy_demand_ej,
            "electricity_price_usd_gj": r.electricity_price,
            "refined_liquids_ej": r.refined_liquids_ej,
            "emissions_mtco2": r.emissions_mtco2,
        }
        # Electricity generation by tech
        for tech, ej in r.electricity_gen_ej.items():
            base[f"elec_{tech}_ej"] = ej
        rows.append(base)
    return pd.DataFrame(rows)


def export_csv(results: list[PeriodResult], output_dir: Path) -> None:
    """Export results to CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    df = results_to_dataframe(results)
    df.to_csv(output_dir / "model_results.csv", index=False)

    # Summary: emissions by region and year
    emissions = df.pivot_table(
        values="emissions_mtco2", index="region", columns="year", aggfunc="sum"
    )
    emissions.to_csv(output_dir / "emissions_by_region.csv")

    # Summary: total energy by region and year
    energy = df.pivot_table(
        values="total_energy_ej", index="region", columns="year", aggfunc="sum"
    )
    energy.to_csv(output_dir / "energy_by_region.csv")


def print_summary(results: list[PeriodResult]) -> None:
    """Print a quick summary of model results to console."""
    df = results_to_dataframe(results)

    print("\n=== GHIM Energy Model Results ===\n")

    # Global totals by year
    global_by_year = df.groupby("year").agg({
        "emissions_mtco2": "sum",
        "total_energy_ej": "sum",
        "gdp_billion_usd": "sum",
        "population_million": "sum",
    })

    print("Global Totals:")
    print(f"{'Year':>6} {'CO2 (GtCO2)':>12} {'Energy (EJ)':>12} {'GDP (T$)':>10} {'Pop (B)':>8}")
    print("-" * 52)
    for year, row in global_by_year.iterrows():
        print(
            f"{year:>6} "
            f"{row['emissions_mtco2'] / 1000:>12.1f} "
            f"{row['total_energy_ej']:>12.1f} "
            f"{row['gdp_billion_usd'] / 1000:>10.1f} "
            f"{row['population_million'] / 1000:>8.2f}"
        )

    # Electricity mix in base and end year
    elec_cols = [c for c in df.columns if c.startswith("elec_") and c.endswith("_ej")]
    if elec_cols:
        for yr in [df["year"].min(), df["year"].max()]:
            yr_data = df[df["year"] == yr][elec_cols].sum()
            total = yr_data.sum()
            print(f"\nGlobal Electricity Mix ({yr}):")
            for col in sorted(elec_cols, key=lambda c: -yr_data[c]):
                tech = col.replace("elec_", "").replace("_ej", "")
                share = yr_data[col] / total * 100 if total > 0 else 0
                print(f"  {tech:>12}: {yr_data[col]:>6.1f} EJ ({share:>5.1f}%)")
