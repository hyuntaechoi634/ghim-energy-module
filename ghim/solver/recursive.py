"""Recursive-dynamic solver.

Solves the energy model period-by-period (2000, 2005, ..., 2150).
Each period: endogenous GDP from DICE production function, KLEM
determines energy demand, energy sectors compete via preference
logit, prices iterate to market clearing.  Energy costs feed back
to net output and capital accumulation.
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
    gdp: float                          # net output (billion USD PPP)
    population: float                   # millions
    total_energy_demand_ej: float
    electricity_gen_ej: dict[str, float]  # tech -> EJ
    electricity_price: float            # $/GJ
    refined_liquids_ej: float
    hydrogen_ej: dict[str, float]       # tech -> EJ
    final_demand_ej: dict[str, dict[str, float]]  # sector -> carrier -> EJ
    fuel_prices: dict[str, float]       # carrier -> $/GJ
    emissions_mtco2: float              # total CO2 emissions (MtCO2)
    # New Phase 2 fields
    gross_output: float = 0.0           # Y = A*K^a*L^(1-a) (billion USD)
    net_output: float = 0.0             # Y - energy_cost (billion USD)
    capital_stock: float = 0.0          # K (billion USD)
    investment: float = 0.0             # I (billion USD/yr)
    energy_cost: float = 0.0            # total energy cost (billion USD)
    ssp_reference_gdp: float = 0.0     # SSP GDP for comparison (billion USD)
    tfp: float = 0.0                    # total factor productivity
    # Policy fields
    carbon_price_usd_tco2: float = 0.0  # active carbon price ($/tCO2)
    carbon_revenue_billion_usd: float = 0.0  # carbon revenue (billion USD)
    aeei_factor: float = 1.0            # cumulative efficiency factor
    # Trade fields
    world_prices: dict[str, float] = field(default_factory=dict)
    net_exports_ej: dict[str, float] = field(default_factory=dict)
    domestic_production_ej: dict[str, float] = field(default_factory=dict)
    calibration_rents: dict[str, float] = field(default_factory=dict)


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


_BASE_CARRIER_PRICES = None

def _get_base_carrier_prices() -> list[float]:
    """Cached base-year carrier prices for price index computation."""
    global _BASE_CARRIER_PRICES
    if _BASE_CARRIER_PRICES is None:
        defaults = _default_fuel_prices()
        _BASE_CARRIER_PRICES = [defaults.get(c, 5.0) for c in ENERGY_CARRIERS]
    return _BASE_CARRIER_PRICES


def solve_period(
    region_model: RegionModel,
    ssp_gdp: float,
    population: float,
    year: int,
    policy: "PolicyScenario | None" = None,
    trade_prices: dict[str, float] | None = None,
) -> PeriodResult:
    """Solve a single period for a single region.

    Uses endogenous GDP (DICE-style) with energy cost feedback.
    Iterates on energy prices until supply equals demand.

    Parameters
    ----------
    policy : PolicyScenario, optional
        Active policy scenario. None means no policy (default behavior).
    trade_prices : dict, optional
        Delivered fuel prices from trade module (fuel → $/GJ).
        Overrides primary fuel prices for coal, oil, gas.
    """
    from ghim.policy import PolicyScenario

    if policy is None:
        policy = PolicyScenario()

    rm = region_model
    prices = dict(rm.fuel_prices)
    years_from_base = max(year - BASE_YEAR, 0)

    # Apply trade-determined primary fuel prices
    if trade_prices:
        for fuel, price in trade_prices.items():
            prices[fuel] = price

    # --- Policy: carbon price adder on fuel prices ---
    carbon_price = policy.carbon_price.get_price(year)
    if carbon_price > 0:
        for fuel, coef in CARBON_COEFS.items():
            if coef > 0 and fuel in prices:
                prices[fuel] += coef * TC_TO_TCO2 * carbon_price

    # --- Policy: prepare subsidy and constraint dicts for supply sectors ---
    elec_subsidies: dict[str, float] | None = None
    h2_subsidies: dict[str, float] | None = None
    if policy.renewable_subsidies.subsidies:
        elec_subsidies = {}
        h2_subsidies = {}
        for tech in policy.renewable_subsidies.subsidies:
            sub = policy.renewable_subsidies.get_subsidy(tech, year)
            if sub > 0:
                elec_subsidies[tech] = sub
                h2_subsidies[tech] = sub
        if not elec_subsidies:
            elec_subsidies = None
        if not h2_subsidies:
            h2_subsidies = None

    elec_constraints = [tc for tc in policy.tech_constraints if tc.sector == "electricity"] or None
    h2_constraints = [tc for tc in policy.tech_constraints if tc.sector == "hydrogen"] or None

    # --- Policy: AEEI factor ---
    aeei_factor = policy.efficiency_standards.cumulative_factor("global", year, BASE_YEAR)

    # 1. Set TFP from pre-computed trajectory
    rm.klem.set_tfp_for_year(year)

    # 2. Compute gross output from current capital stock
    gross_output = rm.klem.compute_gross_output(population)

    # Use gross output for demand computation (replaces exogenous SSP GDP)
    gdp_for_demand = gross_output

    base_carrier_prices = _get_base_carrier_prices()

    # 3. Price iteration loop
    total_energy = 0.0
    final_demand = {}
    elec_gen = {}
    h2_gen = {}
    ref_result = {}

    for iteration in range(MAX_PRICE_ITER):
        # 3a. Energy price index (relative to base year)
        carrier_prices = [prices.get(c, 5.0) for c in ENERGY_CARRIERS]
        energy_price_index = np.mean(carrier_prices) / np.mean(base_carrier_prices)

        # 3b. Total energy demand from KLEM
        total_energy = rm.klem.compute_energy_demand(gdp_for_demand, energy_price_index)

        # Apply AEEI to total energy demand
        total_energy *= aeei_factor

        # 3c. Final demand by sector and carrier
        final_demand = {}
        total_by_carrier: dict[str, float] = {c: 0.0 for c in ENERGY_CARRIERS}
        for name, sector in rm.demand_sectors.items():
            carrier_demand = sector.compute_demand(gdp_for_demand, prices)
            # Apply per-sector AEEI
            sector_aeei = policy.efficiency_standards.cumulative_factor(name, year, BASE_YEAR)
            carrier_demand = {c: d * sector_aeei for c, d in carrier_demand.items()}
            final_demand[name] = carrier_demand
            for c, d in carrier_demand.items():
                total_by_carrier[c] = total_by_carrier.get(c, 0.0) + d

        # 3d. Electricity supply (with subsidies + constraints)
        elec_demand = total_by_carrier.get("electricity", 5.0)
        elec_gen = rm.electricity.compute_supply(
            prices, elec_demand, years_from_base,
            cost_adjustments=elec_subsidies,
            share_constraints=elec_constraints,
            year=year,
        )
        new_elec_price = rm.electricity.weighted_cost(prices)

        # 3e. Refined liquids supply
        liquids_demand = total_by_carrier.get("refined liquids", 5.0)
        ref_result = rm.refining.compute_supply(liquids_demand, prices.get("oil", 8.0))
        new_liquids_price = ref_result["cost_per_gj"]

        # 3f. Hydrogen supply (with subsidies + constraints)
        h2_demand = total_by_carrier.get("hydrogen", 0.1)
        h2_gen = rm.hydrogen.compute_supply(
            prices, max(h2_demand, 0.01), years_from_base,
            cost_adjustments=h2_subsidies,
            share_constraints=h2_constraints,
            year=year,
        )
        new_h2_price = rm.hydrogen.weighted_cost(prices)

        # 3g. Check price convergence and update
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

    # Store updated prices.
    # Reset traded fuel prices to defaults so next period's demand estimation
    # starts from reference prices rather than carrying forward trade-cleared
    # prices (which cause inter-period cobweb oscillation). The inter-period
    # price signal comes through resource depletion, not stored prices.
    rm.fuel_prices = dict(prices)
    defaults = _default_fuel_prices()
    for fuel in ["coal", "oil", "gas"]:
        rm.fuel_prices[fuel] = defaults[fuel]

    # 4. Compute energy cost and net output
    carrier_prices_arr = [prices.get(c, 5.0) for c in ENERGY_CARRIERS]
    avg_price = np.mean(carrier_prices_arr)
    energy_cost = KLEMDriver.compute_energy_cost(total_energy, avg_price)

    # 6. Compute emissions (before revenue recycling, which depends on emissions)
    elec_emissions = rm.electricity.emissions_mtc(elec_gen)
    ref_emissions = ref_result.get("emissions_mtc", 0.0)
    h2_emissions = rm.hydrogen.emissions_mtc(h2_gen)

    # Direct combustion emissions from final demand
    direct_emissions = 0.0
    for sector_demand in final_demand.values():
        for carrier, ej in sector_demand.items():
            cc = CARBON_COEFS.get(carrier, 0.0)
            direct_emissions += cc * ej * 1e9 / 1e6  # tC -> MtC

    total_emissions_mtc = elec_emissions + ref_emissions + h2_emissions + direct_emissions
    total_emissions_mtco2 = total_emissions_mtc * TC_TO_TCO2

    # --- Policy: revenue recycling ---
    carbon_revenue = 0.0
    if carbon_price > 0 and policy.revenue_recycling.fraction > 0:
        # Revenue = price * emissions (MtCO2) / 1000 (to GtCO2) * 1e9 (to $/billion)
        # Simplified: revenue_billion = carbon_price * total_emissions_mtco2 / 1000
        carbon_revenue = (
            carbon_price * total_emissions_mtco2 / 1000.0
            * policy.revenue_recycling.fraction
        )
        energy_cost = max(energy_cost - carbon_revenue, 0.0)

    net_output = KLEMDriver.compute_net_output(gross_output, energy_cost)

    # 5. Investment and capital update
    investment = rm.klem.compute_investment(net_output)
    rm.klem.update_capital(investment)

    return PeriodResult(
        year=year,
        region=rm.name,
        gdp=net_output,
        population=population,
        total_energy_demand_ej=total_energy,
        electricity_gen_ej=elec_gen,
        electricity_price=prices["electricity"],
        refined_liquids_ej=total_by_carrier.get("refined liquids", 0.0),
        hydrogen_ej=h2_gen,
        final_demand_ej=final_demand,
        fuel_prices=dict(prices),
        emissions_mtco2=total_emissions_mtco2,
        gross_output=gross_output,
        net_output=net_output,
        capital_stock=rm.klem.capital_stock,
        investment=investment,
        energy_cost=energy_cost,
        ssp_reference_gdp=ssp_gdp,
        tfp=rm.klem.tfp,
        carbon_price_usd_tco2=carbon_price,
        carbon_revenue_billion_usd=carbon_revenue,
        aeei_factor=aeei_factor,
    )


def compute_primary_fuel_demand(
    region_model: RegionModel,
    population: float,
    year: int,
    policy: "PolicyScenario | None" = None,
    price_overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    """Estimate primary fuel demand (coal, oil, gas) for one region.

    Used by trade module to estimate demands before market clearing.
    Runs one pass of demand computation without updating model state.

    Parameters
    ----------
    price_overrides : dict, optional
        Fuel prices to use instead of rm.fuel_prices for specified fuels.
        Used by the trade iteration loop to feed back cleared prices.
    """
    from ghim.policy import PolicyScenario
    if policy is None:
        policy = PolicyScenario()

    rm = region_model
    prices = dict(rm.fuel_prices)
    if price_overrides:
        prices.update(price_overrides)
        # Propagate oil price change to refined liquids price
        # (refining LCOE depends on oil input cost)
        if "oil" in price_overrides:
            prices["refined liquids"] = rm.refining.primary_tech.levelized_cost(
                prices["oil"]
            )

    # Compute gross output
    rm.klem.set_tfp_for_year(year)
    gross_output = rm.klem.compute_gross_output(population)

    base_carrier_prices = _get_base_carrier_prices()
    carrier_prices = [prices.get(c, 5.0) for c in ENERGY_CARRIERS]
    energy_price_index = np.mean(carrier_prices) / np.mean(base_carrier_prices)

    # Total energy from KLEM
    aeei_factor = policy.efficiency_standards.cumulative_factor("global", year, BASE_YEAR)
    total_energy = rm.klem.compute_energy_demand(gross_output, energy_price_index) * aeei_factor

    # Final demand by carrier
    total_by_carrier: dict[str, float] = {c: 0.0 for c in ENERGY_CARRIERS}
    for name, sector in rm.demand_sectors.items():
        carrier_demand = sector.compute_demand(gross_output, prices)
        sector_aeei = policy.efficiency_standards.cumulative_factor(name, year, BASE_YEAR)
        for c, d in carrier_demand.items():
            total_by_carrier[c] = total_by_carrier.get(c, 0.0) + d * sector_aeei

    # Electricity sector fuel consumption
    elec_demand = total_by_carrier.get("electricity", 5.0)
    # Use current shares to estimate fuel mix (don't update state)
    elec_fuel = {}
    if rm.electricity.current_shares is not None:
        for t, s in zip(rm.electricity.techs, rm.electricity.current_shares):
            if t.efficiency > 0:
                fuel_ej = (s * elec_demand) / t.efficiency
                elec_fuel[t.fuel_input] = elec_fuel.get(t.fuel_input, 0.0) + fuel_ej

    # Refining oil consumption
    liquids_demand = total_by_carrier.get("refined liquids", 5.0)
    oil_for_refining = liquids_demand / rm.refining.primary_tech.efficiency if rm.refining.primary_tech.efficiency > 0 else 0.0

    # Hydrogen fuel consumption
    h2_demand = total_by_carrier.get("hydrogen", 0.1)
    h2_fuel = {}
    if rm.hydrogen.current_shares is not None:
        for t, s in zip(rm.hydrogen.techs, rm.hydrogen.current_shares):
            if t.efficiency > 0:
                fuel_ej = (s * max(h2_demand, 0.01)) / t.efficiency
                h2_fuel[t.fuel_input] = h2_fuel.get(t.fuel_input, 0.0) + fuel_ej

    # Aggregate primary fuel demands
    primary: dict[str, float] = {"coal": 0.0, "oil": 0.0, "gas": 0.0}

    # Direct final demand
    primary["coal"] += total_by_carrier.get("coal", 0.0)
    primary["gas"] += total_by_carrier.get("gas", 0.0)
    # "refined liquids" → oil demand via refining
    primary["oil"] += oil_for_refining

    # Electricity fuel inputs
    primary["coal"] += elec_fuel.get("coal", 0.0)
    primary["gas"] += elec_fuel.get("gas", 0.0)
    primary["oil"] += elec_fuel.get("oil", 0.0)

    # Hydrogen fuel inputs
    primary["gas"] += h2_fuel.get("gas", 0.0)

    return primary


def _solve_regions_for_period(
    region_models: dict[str, RegionModel],
    gdp_df: "pd.DataFrame",
    pop_df: "pd.DataFrame",
    year: int,
    policy: "PolicyScenario",
    trade_module: "TradeModule | None" = None,
    prev_trade_prices: dict[str, dict[str, float]] | None = None,
) -> tuple[list["PeriodResult"], dict[str, dict[str, float]]]:
    """Solve all regions for one period, with optional trade clearing.

    Iterates demand estimation and trade clearing until prices converge,
    preventing cobweb oscillation when demand exceeds supply capacity.

    Parameters
    ----------
    prev_trade_prices : dict, optional
        Cleared trade prices from the previous period, used to warm-start
        the demand-trade iteration so it begins near the converged solution
        rather than from default fuel prices.

    Returns
    -------
    tuple of (list[PeriodResult], dict mapping region → fuel → price)
        The period results and the final cleared trade prices (empty dict
        if trade is disabled).
    """
    from ghim.config import (
        TRADED_FUELS,
        TRADE_DEMAND_MAX_ITER,
        TRADE_DEMAND_DAMP,
        TRADE_DEMAND_TOL,
        OBSERVED_FUEL_PRICES_2020,
        TRADE_MAX_PRICE_CHANGE,
        TRADE_MAX_PROD_DECLINE,
    )
    from ghim.energy.trade import TradeResult

    trade_results = None
    # Warm-start from previous period's cleared prices so the iteration
    # begins near the converged solution instead of from default prices.
    trade_prices_by_region: dict[str, dict[str, float]] = (
        {r: dict(p) for r, p in prev_trade_prices.items()}
        if prev_trade_prices else {}
    )

    if trade_module is not None and trade_module.enabled:
        if year <= BASE_YEAR:
            # Historical periods: use observed prices, skip market clearing.
            # This prevents artificially low supply-curve prices from
            # distorting GDP in early periods.
            for region in R10_REGIONS:
                trade_prices_by_region[region] = {}
                for fuel in TRADED_FUELS:
                    tc = trade_module.transport_costs.get(fuel, {}).get(region, 0.5)
                    trade_prices_by_region[region][fuel] = (
                        OBSERVED_FUEL_PRICES_2020[fuel] + tc
                    )

            # Synthetic trade results for metadata (production ≈ demand,
            # net exports ≈ 0, world prices = observed).
            trade_results = {}
            for fuel in TRADED_FUELS:
                regional_prod: dict[str, float] = {}
                regional_dem: dict[str, float] = {}
                for region in R10_REGIONS:
                    base_prod = DEFAULT_PRIMARY_ENERGY.get(region, {}).get(fuel, 0.0)
                    regional_prod[region] = base_prod
                    regional_dem[region] = base_prod
                trade_results[fuel] = TradeResult(
                    fuel=fuel,
                    world_price=OBSERVED_FUEL_PRICES_2020[fuel],
                    regional_production=regional_prod,
                    regional_demand=regional_dem,
                    net_exports={r: 0.0 for r in R10_REGIONS},
                )

            # Update depletion based on base-year production rates so that
            # by the first projection period the supply curves reflect
            # historical extraction.
            for region in R10_REGIONS:
                for fuel in TRADED_FUELS:
                    base_prod = DEFAULT_PRIMARY_ENERGY.get(region, {}).get(fuel, 0.0)
                    supply = trade_module.regional_supplies.get(region, {}).get(fuel)
                    if supply is not None:
                        supply.cumulative_extracted += base_prod * TIMESTEP

            # Seed prev_world_prices from observed so the first projection
            # period has a reference for price smoothing.
            if year == BASE_YEAR:
                trade_module.prev_world_prices = dict(OBSERVED_FUEL_PRICES_2020)
                # Seed prev_regional_production from base-year data so the
                # first projection period has a reference for production smoothing.
                for fuel in TRADED_FUELS:
                    trade_module.prev_regional_production[fuel] = {
                        r: DEFAULT_PRIMARY_ENERGY.get(r, {}).get(fuel, 0.0)
                        for r in R10_REGIONS
                    }
        else:
            # Projection periods: iterate demand estimation ↔ trade clearing.
            prev_world_prices: dict[str, float] = {}
            prev_demands: dict[str, dict[str, float]] | None = None
            converged = False

            # Bootstrap calibration rents at the first projection period:
            # run a preliminary clearing (with rent=0) to get extraction-cost
            # prices, then compute rents = observed − cleared.  All subsequent
            # solve_trade() calls automatically include the rents as adders.
            if not trade_module.calibration_rents:
                prelim_demands: dict[str, dict[str, float]] = {}
                for region in R10_REGIONS:
                    pop = float(pop_df.loc[region, year]) if year in pop_df.columns else 100.0
                    overrides = trade_prices_by_region.get(region)
                    prelim_demands[region] = compute_primary_fuel_demand(
                        region_models[region], pop, year, policy,
                        price_overrides=overrides,
                    )
                prelim_results = trade_module.solve_trade(prelim_demands)
                if prelim_results is not None:
                    trade_module.calibrate_rents(prelim_results, OBSERVED_FUEL_PRICES_2020)

            for trade_iter in range(TRADE_DEMAND_MAX_ITER):
                # Step 1: Estimate primary fuel demands per region
                regional_demands: dict[str, dict[str, float]] = {}
                for region in R10_REGIONS:
                    pop = float(pop_df.loc[region, year]) if year in pop_df.columns else 100.0
                    overrides = trade_prices_by_region.get(region)
                    demands = compute_primary_fuel_demand(
                        region_models[region], pop, year, policy,
                        price_overrides=overrides,
                    )
                    regional_demands[region] = demands

                # Step 2: Clear global markets → world prices
                trade_results = trade_module.solve_trade(regional_demands)

                # Step 3: Compute delivered prices per region
                new_prices_by_region: dict[str, dict[str, float]] = {}
                if trade_results is not None:
                    for region in R10_REGIONS:
                        new_prices_by_region[region] = trade_module.delivered_prices(
                            trade_results, region
                        )

                # Step 4: Check convergence
                if prev_world_prices and trade_results is not None:
                    max_change = 0.0
                    for fuel in TRADED_FUELS:
                        old_p = prev_world_prices.get(fuel, 0.0)
                        new_p = trade_results[fuel].world_price
                        if old_p > 0:
                            max_change = max(max_change, abs(new_p - old_p) / old_p)
                    if max_change < TRADE_DEMAND_TOL:
                        trade_prices_by_region = new_prices_by_region
                        converged = True
                        break

                # Step 5: Damped update of trade prices for next iteration
                if trade_prices_by_region and new_prices_by_region:
                    for region in R10_REGIONS:
                        for fuel in TRADED_FUELS:
                            old_p = trade_prices_by_region[region].get(fuel, 0.0)
                            new_p = new_prices_by_region[region].get(fuel, old_p)
                            trade_prices_by_region[region][fuel] = (
                                old_p + TRADE_DEMAND_DAMP * (new_p - old_p)
                            )
                else:
                    trade_prices_by_region = new_prices_by_region

                # Record for convergence check and oscillation averaging
                if trade_results is not None:
                    prev_world_prices = {
                        f: trade_results[f].world_price for f in TRADED_FUELS
                    }
                prev_demands = regional_demands

            # If iteration didn't converge (oscillating between grade boundaries),
            # average the last two demand estimates and do a final clearing.
            # This produces a smooth result between the two oscillating states.
            if not converged and prev_demands is not None:
                avg_demands: dict[str, dict[str, float]] = {}
                for region in R10_REGIONS:
                    avg_demands[region] = {}
                    for fuel in ["coal", "oil", "gas"]:
                        d1 = prev_demands[region].get(fuel, 0.0)
                        d2 = regional_demands[region].get(fuel, 0.0)
                        avg_demands[region][fuel] = (d1 + d2) / 2.0
                trade_results = trade_module.solve_trade(avg_demands)
                if trade_results is not None:
                    trade_prices_by_region = {}
                    for region in R10_REGIONS:
                        trade_prices_by_region[region] = trade_module.delivered_prices(
                            trade_results, region
                        )

    # --- Inter-period price smoothing ---
    # Rents are now incorporated directly into market clearing (via
    # price_adder in solve_trade), so world_price already includes rent.
    # We only need to clamp inter-period changes and record prices.
    if (trade_module is not None and trade_module.enabled
            and year > BASE_YEAR and trade_results is not None):
        # Clamp inter-period price changes
        trade_module.smooth_prices(trade_results, TRADE_MAX_PRICE_CHANGE)
        # Clamp per-region production declines
        trade_module.smooth_production(trade_results, TRADE_MAX_PROD_DECLINE)
        # Store for next period
        trade_module.record_world_prices(trade_results)
        trade_module.record_regional_production(trade_results)
        # Recompute delivered prices from smoothed world prices
        for region in R10_REGIONS:
            trade_prices_by_region[region] = trade_module.delivered_prices(
                trade_results, region
            )

    # Step 3/4: Solve each region with trade-determined (or default) prices
    period_results: list[PeriodResult] = []
    for region in R10_REGIONS:
        gdp = float(gdp_df.loc[region, year]) if year in gdp_df.columns else 1000.0
        pop = float(pop_df.loc[region, year]) if year in pop_df.columns else 100.0
        tp = trade_prices_by_region.get(region)
        result = solve_period(region_models[region], gdp, pop, year, policy, trade_prices=tp)

        # Attach trade metadata
        if trade_results is not None:
            result.world_prices = {f: trade_results[f].world_price for f in TRADED_FUELS}
            result.net_exports_ej = {f: trade_results[f].net_exports.get(region, 0.0) for f in TRADED_FUELS}
            result.domestic_production_ej = {f: trade_results[f].regional_production.get(region, 0.0) for f in TRADED_FUELS}
            if trade_module is not None:
                result.calibration_rents = dict(trade_module.calibration_rents)

        period_results.append(result)

    # Update resource depletion: increment cumulative extraction so
    # cheaper grades deplete over time, causing prices to rise.
    # (Historical periods handle depletion directly above, so skip here.)
    if trade_results is not None and trade_module is not None and year > BASE_YEAR:
        trade_module.update_depletion(trade_results, timestep=TIMESTEP)

    return period_results, trade_prices_by_region


def run_model(
    ssp_data: dict[str, "pd.DataFrame"],
    scenario: str = "SSP2",
    policy: "PolicyScenario | None" = None,
    trade_enabled: bool = True,
) -> list[PeriodResult]:
    """Run the full model for all regions and periods.

    Parameters
    ----------
    ssp_data : dict
        Output from ``load_ssp_data()`` with keys "population" and "gdp".
    policy : PolicyScenario, optional
        Policy scenario to apply. None = no policy.
    trade_enabled : bool
        If True (default), enable inter-regional trade for primary fuels.

    Returns
    -------
    list[PeriodResult]
        Results for every region x period combination.
    """
    import copy
    from ghim.policy import PolicyScenario, CarbonPricePolicy

    if policy is None:
        policy = PolicyScenario()

    pop_df = ssp_data["population"]
    gdp_df = ssp_data["gdp"]

    # Initialize region models with base year data
    region_models: dict[str, RegionModel] = {}
    for region in R10_REGIONS:
        base_gdp = float(gdp_df.loc[region, BASE_YEAR]) if BASE_YEAR in gdp_df.columns else 1000.0
        base_pop = float(pop_df.loc[region, BASE_YEAR]) if BASE_YEAR in pop_df.columns else 100.0
        rm = build_region_model(region, base_gdp, base_pop)

        # Initialize TFP trajectory from SSP GDP path
        ssp_gdp_series = {}
        pop_series = {}
        for year in MODEL_YEARS:
            if year in gdp_df.columns:
                ssp_gdp_series[year] = float(gdp_df.loc[region, year])
            if year in pop_df.columns:
                pop_series[year] = float(pop_df.loc[region, year])
        rm.klem.init_tfp_trajectory(ssp_gdp_series, pop_series)

        region_models[region] = rm

    # Initialize trade module
    trade_module = None
    if trade_enabled:
        try:
            from ghim.data.trade_cal import build_regional_supplies, default_transport_costs
            from ghim.energy.trade import TradeModule
            regional_supplies = build_regional_supplies()
            transport_costs = default_transport_costs()
            trade_module = TradeModule(regional_supplies, transport_costs, enabled=True)
        except Exception:
            trade_module = None

    # Solve period by period
    all_results: list[PeriodResult] = []
    prev_trade_prices: dict[str, dict[str, float]] | None = None
    for year in MODEL_YEARS:
        # Check if emissions cap requires bisection on carbon price
        cap_active = policy.emissions_cap.has_cap(year)
        global_cap = None
        if cap_active:
            global_cap = policy.emissions_cap.get_cap("global", year)

        if global_cap is not None and global_cap < float("inf"):
            # Bisection on carbon price to meet emissions cap
            saved_states = {r: copy.deepcopy(region_models[r]) for r in R10_REGIONS}
            saved_trade = copy.deepcopy(trade_module) if trade_module else None
            price_lo = 0.0
            price_hi = policy.emissions_cap.bisect_price_max

            best_results: list[PeriodResult] = []
            best_price = 0.0

            for bisect_iter in range(policy.emissions_cap.bisect_max_iter):
                price_mid = (price_lo + price_hi) / 2.0

                # Create modified policy with this carbon price
                cap_policy = copy.deepcopy(policy)
                cap_policy.carbon_price = CarbonPricePolicy(trajectory={year: price_mid})

                # Restore region model states
                trial_models = {r: copy.deepcopy(saved_states[r]) for r in R10_REGIONS}
                trial_trade = copy.deepcopy(saved_trade) if saved_trade else None

                trial_results, _ = _solve_regions_for_period(
                    trial_models, gdp_df, pop_df, year, cap_policy, trial_trade,
                    prev_trade_prices,
                )

                total_emissions = sum(r.emissions_mtco2 for r in trial_results)

                if abs(total_emissions - global_cap) / max(global_cap, 1.0) < policy.emissions_cap.bisect_tol:
                    best_results = trial_results
                    best_price = price_mid
                    break

                if total_emissions > global_cap:
                    price_lo = price_mid
                else:
                    price_hi = price_mid

                best_results = trial_results
                best_price = price_mid

            # Re-run with best price to get final state
            final_policy = copy.deepcopy(policy)
            final_policy.carbon_price = CarbonPricePolicy(trajectory={year: best_price})
            for region in R10_REGIONS:
                region_models[region] = copy.deepcopy(saved_states[region])
            if saved_trade:
                trade_module = copy.deepcopy(saved_trade)

            period_results, prev_trade_prices = _solve_regions_for_period(
                region_models, gdp_df, pop_df, year, final_policy, trade_module,
                prev_trade_prices,
            )
            all_results.extend(period_results)
        else:
            # Normal solve (with or without trade)
            period_results, prev_trade_prices = _solve_regions_for_period(
                region_models, gdp_df, pop_df, year, policy, trade_module,
                prev_trade_prices,
            )
            all_results.extend(period_results)

    return all_results
