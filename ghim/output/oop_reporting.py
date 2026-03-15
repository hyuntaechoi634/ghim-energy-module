"""OOP model reporting — PeriodState → DataFrame and IAMC format.

Principle 4: IAMC-Native Reporting — direct readout, not post-hoc mapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ghim.core.state import PeriodState, RegionState


# ===================================================================
# Wide DataFrame (one row per region per period)
# ===================================================================

def oop_to_dataframe(results: list[PeriodState]) -> pd.DataFrame:
    """Convert OOP model results to a flat DataFrame.

    One row per region per period.  Columns match IAMC variable space
    where possible.
    """
    rows = []
    for ps in results:
        for name, rs in ps.regions.items():
            row: dict[str, Any] = {
                "year": ps.period,
                "region": name,
                # Economy
                "gdp_billion_usd": rs.gdp,
                "population_million": rs.population,
                "capital_stock_billion_usd": rs.capital_stock,
                "investment_billion_usd": rs.investment,
                "value_added_billion_usd": rs.value_added,
                "tfp": rs.tfp,
                # Energy
                "total_energy_ej": sum(rs.final_demand.values()),
                "composite_energy_price_usd_gj": rs.composite_energy_price,
                # Emissions
                "emissions_co2_mt": rs.emissions_detail.co2,
                "emissions_ch4_mt": rs.emissions_detail.ch4,
                "emissions_n2o_mt": rs.emissions_detail.n2o,
                "emissions_fgas_mtco2eq": rs.emissions_detail.f_gases,
                "emissions_lulucf_mtco2": rs.emissions_detail.lulucf,
                "emissions_co2eq_mt": rs.emissions_detail.co2eq,
                # Policy tracking
                "carbon_price_usd_tco2": rs.carbon_price,
                "aeei_factor": rs.aeei_factor,
                "carbon_revenue_billion_usd": rs.carbon_revenue,
            }

            # Per-carrier demands
            for carrier, ej in rs.final_demand.items():
                row[f"demand_{carrier}_ej"] = ej

            # Per-carrier prices
            for carrier, price in rs.carrier_prices.items():
                key = carrier.value if hasattr(carrier, "value") else str(carrier)
                row[f"price_{key}_usd_gj"] = price

            # Sector price indices
            for sector_name, price in rs.sector_prices.items():
                row[f"sector_price_{sector_name}_usd_gj"] = price

            # Generation by tech (per transformation output)
            for output_carrier, gen_dict in rs.generation.items():
                if isinstance(gen_dict, dict):
                    for tech, ej in gen_dict.items():
                        row[f"gen_{output_carrier}_{tech}_ej"] = ej

            # Trade
            for fuel, val in rs.net_exports.items():
                key = fuel.value if hasattr(fuel, "value") else str(fuel)
                row[f"net_exports_{key}_ej"] = val
            for fuel, val in rs.regional_production.items():
                key = fuel.value if hasattr(fuel, "value") else str(fuel)
                row[f"production_{key}_ej"] = val

            rows.append(row)

    return pd.DataFrame(rows)


# ===================================================================
# IAMC long format
# ===================================================================

# IAMC variable mapping: (variable_name, unit, extractor_function)
_IAMC_VARIABLES: list[tuple[str, str, Any]] = [
    ("GDP|PPP", "billion US$2017/yr",
     lambda rs, ps: rs.gdp),
    ("Population", "million",
     lambda rs, ps: rs.population),
    ("Capital Stock", "billion US$2017",
     lambda rs, ps: rs.capital_stock),
    ("Investment", "billion US$2017/yr",
     lambda rs, ps: rs.investment),
    ("Final Energy", "EJ/yr",
     lambda rs, ps: sum(rs.final_demand.values())),
    ("Final Energy|Electricity", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("electricity", 0.0)),
    ("Final Energy|Gases", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("gas", 0.0)),
    ("Final Energy|Liquids", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("liquids", 0.0)),
    ("Final Energy|Solids|Coal", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("coal", 0.0)),
    ("Final Energy|Solids|Biomass", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("biomass", 0.0)),
    ("Final Energy|Hydrogen", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("h2", 0.0)),
    ("Final Energy|Heat", "EJ/yr",
     lambda rs, ps: rs.final_demand.get("heat", 0.0)),
    ("Emissions|CO2", "Mt CO2/yr",
     lambda rs, ps: rs.emissions_detail.co2),
    ("Emissions|CO2|Energy and Industrial Processes", "Mt CO2/yr",
     lambda rs, ps: rs.emissions_detail.co2),
    ("Emissions|CH4", "Mt CH4/yr",
     lambda rs, ps: rs.emissions_detail.ch4),
    ("Emissions|CO2|AFOLU", "Mt CO2/yr",
     lambda rs, ps: rs.emissions_detail.lulucf),
    ("Emissions|Kyoto Gases", "Mt CO2-equiv/yr",
     lambda rs, ps: rs.emissions_detail.co2eq),
    ("Price|Carbon", "US$2017/t CO2",
     lambda rs, ps: rs.carbon_price),
    ("Energy Efficiency|AEEI Factor", "dimensionless",
     lambda rs, ps: rs.aeei_factor),
    ("Price|Final Energy", "US$2017/GJ",
     lambda rs, ps: rs.composite_energy_price),
]


def oop_to_iamc(
    results: list[PeriodState],
    model_name: str = "GHIM",
    scenario_name: str = "SSP2",
) -> pd.DataFrame:
    """Convert OOP results to IAMC long format.

    Columns: model, scenario, region, variable, unit, <year columns>.
    """
    rows = []
    for ps in results:
        year = ps.period
        for region_name, rs in ps.regions.items():
            for var_name, unit, extractor in _IAMC_VARIABLES:
                value = extractor(rs, ps)
                rows.append({
                    "model": model_name,
                    "scenario": scenario_name,
                    "region": region_name,
                    "variable": var_name,
                    "unit": unit,
                    "year": year,
                    "value": value,
                })

    df = pd.DataFrame(rows)

    # Pivot to wide format (year columns) per IAMC convention
    wide = df.pivot_table(
        index=["model", "scenario", "region", "variable", "unit"],
        columns="year",
        values="value",
        aggfunc="first",
    ).reset_index()

    return wide


# ===================================================================
# Export and print
# ===================================================================

def oop_export(
    results: list[PeriodState],
    output_dir: Path,
    scenario: str = "SSP2",
    formats: tuple[str, ...] = ("parquet", "csv"),
) -> None:
    """Export OOP results to Parquet and/or CSV.

    Parameters
    ----------
    formats : tuple of str
        Which formats to write. Default ("parquet", "csv") writes both.
        Parquet is ~10x smaller and faster for analysis; CSV for inspection.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    df = oop_to_dataframe(results)
    iamc = oop_to_iamc(results, scenario_name=scenario)

    if "parquet" in formats:
        df.to_parquet(output_dir / "model_results.parquet", index=False)
        iamc.to_parquet(output_dir / "iamc_results.parquet", index=False)

    if "csv" in formats:
        df.to_csv(output_dir / "model_results.csv", index=False)
        iamc.to_csv(output_dir / "iamc_results.csv", index=False)


# Keep old name for backward compatibility
def oop_export_csv(
    results: list[PeriodState],
    output_dir: Path,
    scenario: str = "SSP2",
) -> None:
    """Export OOP results to CSV files (legacy wrapper)."""
    oop_export(results, output_dir, scenario, formats=("csv",))


def oop_print_summary(results: list[PeriodState]) -> None:
    """Print a quick summary of OOP model results."""
    print(f"\n{'='*78}")
    print(f"  GHIM OOP Model — {len(results)} periods solved, "
          f"{len(results[0].regions)} regions")
    print(f"{'='*78}")
    print(f"  {'Year':>4}  {'GDP (T$)':>10}  {'Pop (B)':>8}  "
          f"{'Energy (EJ)':>11}  {'CO2eq (Gt)':>10}  {'τ ($/tCO2)':>10}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*8}  {'-'*11}  {'-'*10}  {'-'*10}")
    for ps in results:
        total_gdp = sum(rs.gdp for rs in ps.regions.values())
        total_pop = sum(rs.population for rs in ps.regions.values())
        total_energy = sum(
            sum(rs.final_demand.values()) for rs in ps.regions.values()
        )
        carbon_price = ps.policy_carbon_price
        print(
            f"  {ps.period:4d}  {total_gdp / 1000:10.1f}  "
            f"{total_pop / 1000:8.2f}  {total_energy:11.1f}  "
            f"{ps.global_emissions:10.2f}  {carbon_price:10.1f}"
        )
    print(f"{'='*78}")

    # Electricity mix for first and last period
    first, last = results[0], results[-1]
    for ps, label in [(first, "First"), (last, "Last")]:
        elec_gen: dict[str, float] = {}
        for rs in ps.regions.values():
            gen = rs.generation.get("electricity", {})
            if isinstance(gen, dict):
                for tech, ej in gen.items():
                    elec_gen[tech] = elec_gen.get(tech, 0.0) + ej
        total = sum(elec_gen.values())
        if total > 0:
            print(f"\n  {label} period ({ps.period}) — Global electricity mix:")
            for tech in sorted(elec_gen, key=lambda t: -elec_gen[t]):
                share = elec_gen[tech] / total * 100
                print(f"    {tech:>16}: {elec_gen[tech]:>7.1f} EJ ({share:>5.1f}%)")
