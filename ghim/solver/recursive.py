"""Recursive-dynamic solver.

Solves the energy model period-by-period (2020, 2025, ..., 2100).
Each period: KLEM determines energy demand, energy sectors compete
via logit, prices iterate to market clearing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ghim.config import (
    MODEL_YEARS, BASE_YEAR, TIMESTEP,
    PRICE_TOL, MAX_PRICE_ITER, PRICE_DAMP,
    TC_TO_TCO2, CARBON_COEFS,
)
from ghim.regions import R10_REGIONS
from ghim.data.energy_cal import (
    DEFAULT_PRIMARY_ENERGY,
    DEFAULT_ELEC_SHARES,
    DEFAULT_ELEC_TOTAL_EJ,
    DEFAULT_FINAL_DEMAND,
)
from ghim.econ.klem import KLEMDriver
from ghim.energy.electricity import ElectricitySector
from ghim.energy.refining import RefiningSector
from ghim.energy.hydrogen import HydrogenSector
from ghim.energy.demand import FinalDemand, ENERGY_CARRIERS
from ghim.energy.supply import default_resource_supplies


@dataclass
class PeriodResult:
    """Results for one region in one period."""
    year: int
    region: str
    gdp: float                          # billion USD PPP
    population: float                   # millions
    total_energy_demand_ej: float
    electricity_gen_ej: dict[str, float]  # tech → EJ
    electricity_price: float            # $/GJ
    refined_liquids_ej: float
    hydrogen_ej: dict[str, float]       # tech → EJ
    final_demand_ej: dict[str, dict[str, float]]  # sector → carrier → EJ
    fuel_prices: dict[str, float]       # carrier → $/GJ
    emissions_mtco2: float              # total CO2 emissions (MtCO2)


@dataclass
class RegionModel:
    """All model components for a single region."""
    name: str
    klem: KLEMDriver
    electricity: ElectricitySector
    refining: RefiningSector
    hydrogen: HydrogenSector
    demand_sectors: dict[str, FinalDemand]
    fuel_prices: dict[str, float] = field(default_factory=dict)

    def calibrate(self, gdp: float) -> None:
        """Calibrate all sectors to base-year data."""
        self.electricity.calibrate(
            DEFAULT_ELEC_SHARES.get(self.name, {}),
            self.fuel_prices,
        )
        self.hydrogen.calibrate(
            {"smr": 0.95, "electrolysis": 0.05},
            self.fuel_prices,
        )
        for sector in self.demand_sectors.values():
            sector.calibrate(self.fuel_prices, gdp)


def _default_fuel_prices() -> dict[str, float]:
    """Default fuel prices in $/GJ."""
    return {
        "coal": 2.5,
        "gas": 4.0,
        "oil": 8.0,
        "refined liquids": 12.0,
        "nuclear": 0.7,
        "hydro": 0.0,
        "wind": 0.0,
        "solar": 0.0,
        "biomass": 3.0,
        "geothermal": 0.0,
        "electricity": 20.0,
        "hydrogen": 15.0,
    }


def build_region_model(
    region: str,
    base_gdp: float,
    base_pop: float,
) -> RegionModel:
    """Initialize a RegionModel with base-year calibration data."""
    # Base-year total final demand
    fd = DEFAULT_FINAL_DEMAND.get(region, {"industry": 5.0, "buildings": 5.0, "transport": 5.0})
    total_final = sum(fd.values())

    # Build demand sectors
    demand_sectors = {}
    for sector_name, base_ej in fd.items():
        demand_sectors[sector_name] = FinalDemand(sector_name, base_ej)

    # KLEM driver
    klem = KLEMDriver(base_gdp, base_pop, total_final)

    # Electricity sector
    elec = ElectricitySector()
    elec.total_generation_ej = DEFAULT_ELEC_TOTAL_EJ.get(region, 5.0)

    # Transformation sectors
    refining = RefiningSector()
    hydrogen = HydrogenSector()

    fuel_prices = _default_fuel_prices()

    model = RegionModel(
        name=region,
        klem=klem,
        electricity=elec,
        refining=refining,
        hydrogen=hydrogen,
        demand_sectors=demand_sectors,
        fuel_prices=fuel_prices,
    )

    # Calibrate
    model.calibrate(base_gdp)
    return model


def solve_period(
    region_model: RegionModel,
    gdp: float,
    population: float,
    year: int,
) -> PeriodResult:
    """Solve a single period for a single region.

    Iterates on energy prices until supply equals demand.
    """
    rm = region_model
    prices = dict(rm.fuel_prices)

    for iteration in range(MAX_PRICE_ITER):
        # 1. Compute composite energy price (GDP-weighted average of carrier prices)
        carrier_prices = [prices.get(c, 5.0) for c in ENERGY_CARRIERS]
        energy_price_index = np.mean(carrier_prices) / np.mean(
            [_default_fuel_prices().get(c, 5.0) for c in ENERGY_CARRIERS]
        )

        # 2. KLEM: total energy demand
        total_energy = rm.klem.compute_energy_demand(gdp, population, energy_price_index)

        # 3. Final demand by sector and carrier
        final_demand = {}
        total_by_carrier: dict[str, float] = {c: 0.0 for c in ENERGY_CARRIERS}
        for name, sector in rm.demand_sectors.items():
            carrier_demand = sector.compute_demand(gdp, prices)
            final_demand[name] = carrier_demand
            for c, d in carrier_demand.items():
                total_by_carrier[c] = total_by_carrier.get(c, 0.0) + d

        # 4. Electricity supply
        elec_demand = total_by_carrier.get("electricity", 5.0)
        elec_gen = rm.electricity.compute_supply(prices, elec_demand)
        new_elec_price = rm.electricity.weighted_cost(prices)

        # 5. Refined liquids supply
        liquids_demand = total_by_carrier.get("refined liquids", 5.0)
        ref_result = rm.refining.compute_supply(liquids_demand, prices.get("oil", 8.0))
        new_liquids_price = ref_result["cost_per_gj"]

        # 6. Hydrogen supply
        h2_demand = total_by_carrier.get("hydrogen", 0.1)
        h2_gen = rm.hydrogen.compute_supply(prices, max(h2_demand, 0.01))
        new_h2_price = rm.hydrogen.weighted_cost(prices)

        # 7. Check price convergence and update
        new_prices = dict(prices)
        new_prices["electricity"] = new_elec_price
        new_prices["refined liquids"] = new_liquids_price
        new_prices["hydrogen"] = new_h2_price

        # Damped update
        max_change = 0.0
        for key in ["electricity", "refined liquids", "hydrogen"]:
            old_p = prices.get(key, 1.0)
            new_p = new_prices[key]
            if old_p > 0:
                change = abs(new_p - old_p) / old_p
                max_change = max(max_change, change)
            prices[key] = old_p + PRICE_DAMP * (new_p - old_p)

        if max_change < PRICE_TOL:
            break

    # Store updated prices
    rm.fuel_prices = dict(prices)

    # Compute emissions
    elec_emissions = rm.electricity.emissions_mtc(elec_gen)
    ref_emissions = ref_result["emissions_mtc"]
    h2_emissions = rm.hydrogen.emissions_mtc(h2_gen)

    # Direct combustion emissions from final demand (non-electric, non-hydrogen)
    direct_emissions = 0.0
    for sector_demand in final_demand.values():
        for carrier, ej in sector_demand.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            direct_emissions += cc * ej * 1e9 / 1e6  # tC → MtC

    total_emissions_mtc = elec_emissions + ref_emissions + h2_emissions + direct_emissions
    total_emissions_mtco2 = total_emissions_mtc * TC_TO_TCO2

    return PeriodResult(
        year=year,
        region=rm.name,
        gdp=gdp,
        population=population,
        total_energy_demand_ej=total_energy,
        electricity_gen_ej=elec_gen,
        electricity_price=prices["electricity"],
        refined_liquids_ej=liquids_demand,
        hydrogen_ej=h2_gen,
        final_demand_ej=final_demand,
        fuel_prices=dict(prices),
        emissions_mtco2=total_emissions_mtco2,
    )


def run_model(
    ssp_data: dict[str, "pd.DataFrame"],
    scenario: str = "SSP2",
) -> list[PeriodResult]:
    """Run the full model for all regions and periods.

    Parameters
    ----------
    ssp_data : dict
        Output from ``load_ssp_data()`` with keys "population" and "gdp".

    Returns
    -------
    list[PeriodResult]
        Results for every region × period combination.
    """
    pop_df = ssp_data["population"]
    gdp_df = ssp_data["gdp"]

    # Initialize region models with base year data
    region_models: dict[str, RegionModel] = {}
    for region in R10_REGIONS:
        base_gdp = float(gdp_df.loc[region, BASE_YEAR]) if BASE_YEAR in gdp_df.columns else 1000.0
        base_pop = float(pop_df.loc[region, BASE_YEAR]) if BASE_YEAR in pop_df.columns else 100.0
        region_models[region] = build_region_model(region, base_gdp, base_pop)

    # Solve period by period
    all_results: list[PeriodResult] = []
    for year in MODEL_YEARS:
        for region in R10_REGIONS:
            gdp = float(gdp_df.loc[region, year]) if year in gdp_df.columns else 1000.0
            pop = float(pop_df.loc[region, year]) if year in pop_df.columns else 100.0
            result = solve_period(region_models[region], gdp, pop, year)
            all_results.append(result)

    return all_results
