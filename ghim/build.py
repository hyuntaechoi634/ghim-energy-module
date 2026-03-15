"""Build GHIMModel from calibration data.

Constructs Region objects with OOP sectors (Phase C) and wires them into
a GHIMModel with DampedSolver for the recursive-dynamic run loop.

Uses GCAM R32 regions.  Energy calibration data (R10) is downscaled to R32
using GDP shares within each R10 group.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import numpy as np

from ghim.core.carrier import Carrier
from ghim.core.config import (
    BASE_YEAR, TIMESTEP, FUTURE_YEARS, MODEL_YEARS,
    TRADED_FUELS, TRADE_MAX_PRICE_CHANGE, TRADE_MAX_PROD_DECLINE,
)
from ghim.core.emissions import EmissionResult
from ghim.core.learning import TechChange, DEFAULT_RND_RATES
from ghim.core.region import Region
from ghim.core.state import PeriodState, RegionState
from ghim.econ.klem import KLEMDriver
from ghim.model import GHIMModel
from ghim.solver.damped import DampedSolver
from ghim.adapters.base import (
    DefaultClimateAdapter,
    DefaultWaterAdapter,
    DefaultAFOLUAdapter,
)

# OOP sectors
from ghim.sectors.industry import IndustrySector
from ghim.sectors.buildings import BuildingsSector
from ghim.sectors.transport import TransportSector
from ghim.sectors.agriculture import AgricultureSector
from ghim.sectors.electricity import OOPElectricitySector
from ghim.sectors.hydrogen import OOPHydrogenSector
from ghim.sectors.district_heat import DistrictHeatingSector
from ghim.sectors.biofuels import BiofuelsSector
from ghim.sectors.refining import RefinedOilSector
from ghim.sectors.bunkers import BunkersSector

from ghim.regions_r32 import R32_REGIONS, R32_TO_R10, r10_to_r32_members
from ghim.data.energy_cal import (
    DEFAULT_PRIMARY_ENERGY,
    DEFAULT_ELEC_SHARES,
    DEFAULT_ELEC_TOTAL_EJ,
    DEFAULT_FINAL_DEMAND,
)
from ghim.calibration import AR6Calibrator, Calibrator
from ghim.data.ar6_cal import R32_TO_R5, R5_TO_R32

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default fuel prices ($/GJ) — same as procedural code
# ---------------------------------------------------------------------------

def _default_fuel_prices() -> dict[str, float]:
    return {
        "coal": 2.5, "gas": 4.0, "oil": 8.0,
        "refined liquids": 12.0, "nuclear": 0.7,
        "hydro": 0.0, "wind": 0.0, "solar": 0.0,
        "biomass": 3.0, "geothermal": 0.0,
        "electricity": 20.0, "hydrogen": 15.0,
        "uranium": 0.5,
    }


def _default_carrier_prices() -> dict[str, float]:
    """Consumer-facing carrier prices (for demand sectors)."""
    return {
        "electricity": 20.0, "gas": 5.0, "coal": 3.0,
        "liquids": 12.0, "biomass": 3.0, "biofuel": 12.0,
        "h2": 15.0, "heat": 10.0, "oil": 8.0, "uranium": 0.5,
    }


# ---------------------------------------------------------------------------
# Default carrier splits for demand sectors
# ---------------------------------------------------------------------------

def _industry_carrier_demands(total_ej: float) -> dict[str, float]:
    splits = {
        "electricity": 0.25, "gas": 0.20, "coal": 0.25,
        "liquids": 0.15, "biomass": 0.10, "biofuel": 0.0, "h2": 0.05,
    }
    return {c: s * total_ej for c, s in splits.items()}


def _buildings_carrier_demands(total_ej: float) -> dict[str, float]:
    splits = {
        "electricity": 0.35, "gas": 0.25, "coal": 0.05,
        "liquids": 0.08, "biomass": 0.05, "biofuel": 0.0,
        "h2": 0.0, "heat": 0.12,
    }
    s = sum(splits.values())
    return {c: (f / s) * total_ej for c, f in splits.items()}


def _transport_carrier_demands(total_ej: float) -> dict[str, float]:
    splits = {
        "liquids": 0.85, "electricity": 0.03, "gas": 0.07,
        "h2": 0.0, "biofuel": 0.05, "biomass": 0.0,
    }
    return {c: s * total_ej for c, s in splits.items()}


# ---------------------------------------------------------------------------
# Fuel input → service demand: post-calibration fixup
# ---------------------------------------------------------------------------

def _fixup_base_demand(
    sector,
    calibrator: AR6Calibrator | Calibrator,
    carrier_prices: dict[str, float],
    sector_ar6: str,
    region_name: str,
) -> None:
    """Adjust base_demand so compute_demand returns correct fuel totals.

    After calibrate() is called with fuel-input demands, base_demand equals
    total fuel (EJ).  Demand sectors treat base_demand as *service* demand
    (carrier_demands divides by efficiency).  This fixup divides each
    subsector's base_demand by the demand multiplier Σ(share_i / eff_i),
    computed from AR6-calibrated tech shares, so the round-trip is exact:

        FE = base_demand × Σ(share_i / eff_i)  ←  matches original fuel total.
    """
    from ghim.calibration import _expand_carrier_shares_to_techs

    cshares = calibrator.get_sector_carrier_shares(
        BASE_YEAR, sector_ar6, region_name,
    )
    if cshares is None:
        return

    for sub in sector.subsectors:
        costs = np.array([
            t.lcot(carrier_prices.get(t.carrier, 5.0))
            if hasattr(t, "lcot")
            else t.levelized_cost(carrier_prices.get(t.carrier, 5.0))
            for t in sub.techs
        ])
        tech_shares = _expand_carrier_shares_to_techs(
            cshares, sub.techs, costs, sub.logit_scale,
        )
        effs = np.array([t.efficiency for t in sub.techs])
        demand_mult = float(np.sum(tech_shares / effs))

        if demand_mult > 0:
            sub.base_demand /= demand_mult

    sector.base_demand = sum(sub.base_demand for sub in sector.subsectors)

    # Update subsector fractions so compute_demand distributes correctly.
    # Without this, fixed _sub_fractions combined with varying demand_mult
    # causes FE = sector.base_demand × Σ(frac × mult) ≠ fuel_total.
    if hasattr(sector, "_sub_fractions") and sector.base_demand > 0:
        sector._sub_fractions = {
            sub.name: sub.base_demand / sector.base_demand
            for sub in sector.subsectors
        }

    # Also update pass/freight fractions for transport
    if hasattr(sector, "pass_fraction") and len(sector.subsectors) == 2:
        sector.pass_fraction = (
            sector.subsectors[0].base_demand / sector.base_demand
            if sector.base_demand > 0 else 0.6
        )
        sector.freight_fraction = 1.0 - sector.pass_fraction

    # Industry: update EU/FS fractions
    if hasattr(sector, "eu_fraction") and hasattr(sector, "fs_fraction"):
        if sector.base_demand > 0 and len(sector.subsectors) >= 2:
            sector.eu_fraction = sector.subsectors[0].base_demand / sector.base_demand
            sector.fs_fraction = 1.0 - sector.eu_fraction

    # Buildings: recalibrate energy_intensity to match the new base_demand
    if (
        hasattr(sector, "energy_intensity")
        and hasattr(sector, "use_floorspace")
        and sector.use_floorspace
        and getattr(sector, "base_population", 0) > 0
        and sector.base_gdp > 0
    ):
        gdp_per_cap_k = sector.base_gdp / sector.base_population
        floorspace_pc = sector.floorspace_per_capita(gdp_per_cap_k)
        total_floorspace = floorspace_pc * sector.base_population
        if total_floorspace > 0:
            sector.energy_intensity = sector.base_demand / (total_floorspace * 1e-3)

    # Recompute base_price with corrected base_demand weights
    sector.base_price = sector.sector_price_index(
        RegionState(carrier_prices=carrier_prices),
    )


# ---------------------------------------------------------------------------
# R10 → R32 energy data downscaling
# ---------------------------------------------------------------------------

def _compute_gdp_shares_within_r10(
    gdp_by_r32: dict[str, float],
) -> dict[str, float]:
    """Compute each R32 region's GDP share within its R10 group."""
    members = r10_to_r32_members()
    shares: dict[str, float] = {}
    for r10, r32_list in members.items():
        group_gdp = sum(gdp_by_r32.get(r, 0.0) for r in r32_list)
        for r32 in r32_list:
            shares[r32] = gdp_by_r32.get(r32, 0.0) / group_gdp if group_gdp > 0 else 1.0 / len(r32_list)
    return shares


def _downscale_r10_to_r32(
    r10_data: dict[str, float],
    r32_name: str,
    gdp_share: float,
) -> float:
    """Downscale an R10 scalar to R32 using GDP share."""
    r10 = R32_TO_R10[r32_name]
    return r10_data.get(r10, 0.0) * gdp_share


def _downscale_r10_dict_to_r32(
    r10_data: dict[str, dict[str, float]],
    r32_name: str,
    gdp_share: float,
) -> dict[str, float]:
    """Downscale an R10 dict (fuel→value) to R32 using GDP share."""
    r10 = R32_TO_R10[r32_name]
    r10_values = r10_data.get(r10, {})
    return {k: v * gdp_share for k, v in r10_values.items()}


# ---------------------------------------------------------------------------
# Buildings subsector-level calibration (GCAM)
# ---------------------------------------------------------------------------

def _apply_subsector_calibration(
    buildings,
    calibrator,
    carrier_prices: dict[str, float],
    region_name: str,
) -> None:
    """Override buildings subsector fractions and carrier shares from GCAM data.

    GCAM provides per-subsector (heating/cooling/other × resid/comm) carrier
    detail.  This sets each subsector's base_demand, carrier shares, and
    preference factors to match GCAM, then recomputes _sub_fractions and
    energy_intensity.
    """
    from ghim.calibration import _expand_carrier_shares_to_techs

    bld_total = buildings.base_demand
    if bld_total <= 0:
        return

    any_subsector_found = False
    for sub in buildings.subsectors:
        sub_total = calibrator.get_subsector_total(BASE_YEAR, sub.name, region_name)
        sub_shares = calibrator.get_subsector_carrier_shares(BASE_YEAR, sub.name, region_name)
        if sub_total is None or sub_total <= 0 or sub_shares is None:
            continue

        any_subsector_found = True

        # Set subsector base_demand to GCAM subsector total (fuel EJ)
        sub.base_demand = sub_total

        # Carrier shares → per-tech shares
        shares = np.array([sub_shares.get(t.carrier, 1e-6) for t in sub.techs])
        shares = np.maximum(shares, 1e-6)
        shares /= shares.sum()

        # Re-calibrate preference factors with correct shares
        sub.calibrate(shares, carrier_prices)

        # Fixup: convert from fuel-input base_demand to service base_demand
        costs = np.array([
            t.lcot(carrier_prices.get(t.carrier, 5.0))
            if hasattr(t, "lcot")
            else t.levelized_cost(carrier_prices.get(t.carrier, 5.0))
            for t in sub.techs
        ])
        tech_shares = _expand_carrier_shares_to_techs(
            sub_shares, sub.techs, costs, sub.logit_scale,
        )
        effs = np.array([t.efficiency for t in sub.techs])
        demand_mult = float(np.sum(tech_shares / effs))
        if demand_mult > 0:
            sub.base_demand /= demand_mult

    if not any_subsector_found:
        return

    # Update sector totals and fractions
    buildings.base_demand = sum(sub.base_demand for sub in buildings.subsectors)
    if buildings.base_demand > 0:
        buildings._sub_fractions = {
            sub.name: sub.base_demand / buildings.base_demand
            for sub in buildings.subsectors
        }

    # Recalibrate energy_intensity for floorspace model
    if (hasattr(buildings, "energy_intensity")
            and hasattr(buildings, "use_floorspace")
            and buildings.use_floorspace
            and getattr(buildings, "base_population", 0) > 0
            and buildings.base_gdp > 0):
        gdp_per_cap_k = buildings.base_gdp / buildings.base_population
        floorspace_pc = buildings.floorspace_per_capita(gdp_per_cap_k)
        total_floorspace = floorspace_pc * buildings.base_population
        if total_floorspace > 0:
            buildings.energy_intensity = buildings.base_demand / (total_floorspace * 1e-3)

    # Recompute base_price
    buildings.base_price = buildings.sector_price_index(
        RegionState(carrier_prices=carrier_prices),
    )


# ---------------------------------------------------------------------------
# Build a single Region
# ---------------------------------------------------------------------------

def build_region(
    region_name: str,
    base_gdp: float,
    base_pop: float,
    gdp_share: float = 1.0,
    calibrator: AR6Calibrator | Calibrator | None = None,
    gdp_share_r5: float | None = None,
) -> tuple[Region, RegionState]:
    """Build one Region with all OOP sectors + initial RegionState.

    Parameters
    ----------
    gdp_share : float
        This R32 region's GDP share within its R10 group.
        Used to downscale R10 energy calibration data.
    calibrator : AR6Calibrator | Calibrator, optional
        If provided, uses base-year sector totals and carrier shares.
    gdp_share_r5 : float, optional
        GDP share within R5 group (for AR6 sector total downscaling).
        Not needed when calibrator has native_r32=True.
    """
    fuel_prices = _default_fuel_prices()
    carrier_prices = _default_carrier_prices()

    r10 = R32_TO_R10.get(region_name, region_name)

    # Downscale R10 final demand to R32
    fd_r10 = DEFAULT_FINAL_DEMAND.get(
        r10, {"industry": 5.0, "buildings": 5.0, "transport": 5.0}
    )
    fd = {k: v * gdp_share for k, v in fd_r10.items()}

    # Override with calibrator base-year sector totals if available
    if calibrator is not None and calibrator.available:
        is_native_r32 = getattr(calibrator, 'native_r32', False)
        for sector_name in ["industry", "buildings", "transport"]:
            cal_total = calibrator.get_sector_total(BASE_YEAR, sector_name, region_name)
            if cal_total is not None and cal_total > 0:
                if is_native_r32:
                    fd[sector_name] = cal_total
                elif gdp_share_r5 is not None and gdp_share_r5 > 0:
                    fd[sector_name] = cal_total * gdp_share_r5

    total_final = max(sum(fd.values()), 0.1)

    # Economy
    base_energy_price = KLEMDriver.composite_energy_price(
        carrier_prices,
        {c: 1.0 for c in carrier_prices},
    )
    economy = KLEMDriver(
        base_gdp, base_pop, total_final,
        base_energy_price=base_energy_price,
        region=region_name,
    )

    # --- Demand sectors ---
    # Use AR6 carrier shares for initial calibration when available.
    # AR6 reports fuel input (EJ).  calibrate() sets base_demand = sum,
    # then _fixup_base_demand adjusts to correct service units.
    def _ar6_carrier_demands(sector_name: str, total_ej: float,
                              fallback_fn) -> dict[str, float]:
        if calibrator is not None and calibrator.available:
            shares = calibrator.get_sector_carrier_shares(
                BASE_YEAR, sector_name, region_name,
            )
            if shares:
                return {c: s * total_ej for c, s in shares.items()}
        return fallback_fn(total_ej)

    use_ar6 = calibrator is not None and calibrator.available

    industry = IndustrySector()
    ind_demands = _ar6_carrier_demands(
        "industry", fd.get("industry", 1.0), _industry_carrier_demands,
    )
    industry.calibrate(
        ind_demands, carrier_prices, base_gdp, base_population=base_pop,
    )
    if use_ar6:
        _fixup_base_demand(industry, calibrator, carrier_prices, "industry", region_name)

    buildings = BuildingsSector()
    bld_demands = _ar6_carrier_demands(
        "buildings", fd.get("buildings", 1.0), _buildings_carrier_demands,
    )
    buildings.calibrate(
        bld_demands, carrier_prices, base_gdp,
        hdd_base=1.0, cdd_base=1.0, base_population=base_pop,
    )
    if use_ar6:
        _fixup_base_demand(buildings, calibrator, carrier_prices, "buildings", region_name)

    # Subsector-level buildings calibration (GCAM provides heating/cooling/other detail)
    if (use_ar6
        and hasattr(calibrator, 'get_subsector_total')
        and hasattr(calibrator, 'get_subsector_carrier_shares')):
        _apply_subsector_calibration(buildings, calibrator, carrier_prices, region_name)

    transport = TransportSector()
    tr_demands = _ar6_carrier_demands(
        "transport", fd.get("transport", 1.0), _transport_carrier_demands,
    )
    transport.calibrate(tr_demands, carrier_prices, base_gdp)
    if use_ar6:
        _fixup_base_demand(transport, calibrator, carrier_prices, "transport", region_name)

    agriculture = AgricultureSector()
    ag_total = 1.0 * gdp_share
    ag_demands = {
        "electricity": 0.3 * ag_total, "liquids": 0.5 * ag_total,
        "gas": 0.1 * ag_total, "coal": 0.05 * ag_total,
        "biomass": 0.02 * ag_total, "biofuel": 0.01 * ag_total,
        "h2": 0.02 * ag_total,
    }
    agriculture.calibrate(ag_demands, carrier_prices, base_gdp)

    demand_sectors = [industry, buildings, transport, agriculture]

    # --- Transformation sectors ---
    # Electricity: base year shares and generation from calibrator
    elec = OOPElectricitySector(region=region_name)
    elec_shares = None
    elec_total = None
    if calibrator is not None and calibrator.available:
        if hasattr(calibrator, 'get_elec_target_shares'):
            elec_shares = calibrator.get_elec_target_shares(BASE_YEAR, region_name)
        if hasattr(calibrator, 'get_elec_generation'):
            elec_total = calibrator.get_elec_generation(BASE_YEAR, region_name)
    if not elec_shares or not elec_total or elec_total <= 0:
        # Fallback: load GCAM-v8.2 SSP2-Ref as default
        from ghim.data.gcam_cal import load_gcam_calibration as _load_default_cal
        _default = _load_default_cal()
        elec_shares = _default.elec_shares.get(region_name, {}).get(BASE_YEAR, {})
        elec_total = _default.elec_generation.get(region_name, {}).get(BASE_YEAR, 1.0)
    elec.calibrate(elec_shares, fuel_prices, total_generation_ej=max(elec_total, 0.1))

    hydrogen = OOPHydrogenSector()
    is_native_r32 = getattr(calibrator, 'native_r32', False) if calibrator else False
    h2_target = (
        calibrator.get_h2_production(BASE_YEAR, region_name)
        if is_native_r32 and hasattr(calibrator, 'get_h2_production')
        else None
    )
    hydrogen.calibrate(
        {"smr": 0.95, "electrolysis": 0.05},
        fuel_prices,
        total_production_ej=h2_target if h2_target and h2_target > 0 else max(0.5 * gdp_share, 0.01),
    )

    district_heat = DistrictHeatingSector()
    heat_target = (
        calibrator.get_heat_production(BASE_YEAR, region_name)
        if is_native_r32 and hasattr(calibrator, 'get_heat_production')
        else None
    )
    district_heat.calibrate(
        {"gas_boiler": 0.6, "electric_boiler": 0.1,
         "heat_pump": 0.2, "biomass_chp": 0.1},
        fuel_prices,
        total_production_ej=heat_target if heat_target and heat_target > 0 else 0.0,
    )

    biofuels = BiofuelsSector()
    biofuels.calibrate({"ethanol": 0.6, "biodiesel": 0.4}, fuel_prices)

    refining = RefinedOilSector()

    transformation = [elec, hydrogen, district_heat, biofuels, refining]

    # Build Region
    region = Region(
        name=region_name,
        economy=economy,
        demand_sectors=demand_sectors,
        transformation=transformation,
    )

    # Initial RegionState
    rs = RegionState(
        gdp=base_gdp,
        population=base_pop,
        capital_stock=economy.capital_stock,
        tfp=economy.tfp,
        raw_fuel_prices={
            Carrier.COAL: fuel_prices["coal"],
            Carrier.GAS: fuel_prices["gas"],
            Carrier.OIL: fuel_prices["oil"],
            Carrier.BIOMASS: fuel_prices["biomass"],
            Carrier.URANIUM: fuel_prices.get("uranium", 0.5),
        },
        carrier_prices={
            Carrier.ELECTRICITY: carrier_prices["electricity"],
            Carrier.GAS: carrier_prices["gas"],
            Carrier.COAL: carrier_prices["coal"],
            Carrier.LIQUIDS: carrier_prices["liquids"],
            Carrier.BIOMASS: carrier_prices["biomass"],
            Carrier.BIOFUEL: carrier_prices["biofuel"],
            Carrier.H2: carrier_prices["h2"],
            Carrier.HEAT: carrier_prices["heat"],
        },
        composite_energy_price=base_energy_price,
        hdd=1.0,
        cdd=1.0,
        base_gdp=base_gdp,
        base_energy_ej=total_final,
        base_energy_price=base_energy_price,
    )

    return region, rs


# ---------------------------------------------------------------------------
# Calibration pass: run with exogenous GDP to record equilibrium energy
# ---------------------------------------------------------------------------

def _calibration_pass(
    model: GHIMModel,
    initial_state: PeriodState,
    ssp_data: dict[str, Any],
) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    """Run one full model pass to record equilibrium energy, GDP, and prices.

    Uses the same logic as oop_run_model (FE recalibration, inter-period
    updates for capital, learning, trade, vintage) to ensure calibration
    pass prices match the actual run.  A deep copy of the model is used
    so all state is restored afterward.

    Returns (ref_energy, ref_gdp, ref_price) where each is
    dict[region_name][year] = value.
    """
    # Deep copy model so calibration pass doesn't modify original state
    cal_model = deepcopy(model)

    pop_df = ssp_data["population"]
    ref_energy: dict[str, dict[int, float]] = {
        name: {} for name in cal_model.regions
    }
    ref_gdp: dict[str, dict[int, float]] = {
        name: {} for name in cal_model.regions
    }
    ref_price: dict[str, dict[int, float]] = {
        name: {} for name in cal_model.regions
    }

    state = deepcopy(initial_state)
    solver = DampedSolver(alpha=0.3, tol=5e-3, max_iter=150, skip_gdp=True)
    is_first_period = True

    # Seed trade module (same as main run loop)
    if cal_model.trade is not None and hasattr(cal_model.trade, "enabled") and cal_model.trade.enabled:
        try:
            from ghim.config import OBSERVED_FUEL_PRICES_2020
            cal_model.trade.prev_world_prices = dict(OBSERVED_FUEL_PRICES_2020)
            from ghim.data.energy_cal import DEFAULT_PRIMARY_ENERGY
            from ghim.regions import R10_REGIONS
            for fuel in TRADED_FUELS:
                cal_model.trade.prev_regional_production[fuel] = {
                    r: DEFAULT_PRIMARY_ENERGY.get(r, {}).get(fuel, 0.0)
                    for r in R10_REGIONS
                }
        except Exception:
            pass

    for period in FUTURE_YEARS:
        state.period = period
        for name, rs in state.regions.items():
            if period in pop_df.columns:
                rs.population = float(pop_df.loc[name, period])
            cal_model.regions[name].economy.set_tfp_for_year(period)

        # AR6 preference recalibration
        _apply_calibration(cal_model, state, period)

        # Warm-up first period
        if is_first_period:
            state = cal_model.F(state)
            state.period = period
            is_first_period = False

        # Solve with FE recalibration loop (matches oop_run_model)
        _FE_RECAL_ROUNDS_CAL = 3
        for _fe_round in range(_FE_RECAL_ROUNDS_CAL):
            state = solver.solve(cal_model, state)
            if _fe_round < _FE_RECAL_ROUNDS_CAL - 1:
                _apply_calibration(cal_model, state, period)
                state.period = period

        # Record equilibrium energy, GDP, and composite price for each region
        for name, rs in state.regions.items():
            ref_energy[name][period] = sum(rs.final_demand.values())
            ref_gdp[name][period] = rs.gdp
            ref_price[name][period] = getattr(rs, "composite_energy_price", 0.0)

        # Inter-period updates (same as oop_run_model)
        for name, region in cal_model.regions.items():
            rs = state.regions[name]
            region.economy.update_capital(rs.investment)
            rs.capital_stock = region.economy.capital_stock
            for sector in region.transformation:
                if hasattr(sector, "vintage") and sector.vintage is not None:
                    sector.vintage.prune_retired(period)

        # TechChange learning
        if cal_model.tech_change is not None:
            global_new_cap: dict[str, float] = {}
            for name, rs_snap in state.regions.items():
                for carrier, gen_dict in rs_snap.generation.items():
                    if isinstance(gen_dict, dict):
                        for tech, ej in gen_dict.items():
                            global_new_cap[tech] = global_new_cap.get(tech, 0.0) + ej
            cal_model.tech_change.update_deployment(global_new_cap, timestep=TIMESTEP)
            exogenous_rnd = {
                "solar": 2.0, "wind": 1.0, "nuclear": 0.5,
                "electrolysis": 0.5, "coal_ccs": 0.3, "gas_ccs": 0.3,
                "biomass_ccs": 0.2, "bev_battery": 1.0,
            }
            cal_model.tech_change.update_knowledge(exogenous_rnd)
            new_capex = cal_model.tech_change.compute_all_capex()
            for name, region in cal_model.regions.items():
                for sector in region.transformation:
                    if hasattr(sector, "techs"):
                        for t in sector.techs:
                            if t.name in new_capex:
                                t.capex = new_capex[t.name]

        # Trade inter-period smoothing
        if cal_model.trade is not None and hasattr(cal_model.trade, "enabled") and cal_model.trade.enabled:
            trade_results = getattr(cal_model, "_last_trade_results", None)
            if trade_results is not None:
                cal_model.trade.smooth_prices(trade_results, TRADE_MAX_PRICE_CHANGE)
                cal_model.trade.smooth_production(trade_results, TRADE_MAX_PROD_DECLINE)
                cal_model.trade.record_world_prices(trade_results)
                cal_model.trade.record_regional_production(trade_results)
                cal_model.trade.update_depletion(trade_results, timestep=TIMESTEP)

    # cal_model is discarded — original model state is untouched
    logger.info("Calibration pass complete — energy/GDP/price recorded for %d regions",
                len(ref_energy))
    return ref_energy, ref_gdp, ref_price


# ---------------------------------------------------------------------------
# Build full GHIMModel (R32)
# ---------------------------------------------------------------------------

def build_oop_model(
    ssp_data: dict[str, Any],
    scenario: str = "SSP2",
    policy: Any = None,
    calibrator_type: str = "ar6",
) -> tuple[GHIMModel, PeriodState, DampedSolver]:
    """Build GHIMModel with OOP sectors for all R32 regions.

    SSP data must be R32-aggregated (from load_ssp_data_r32).

    Parameters
    ----------
    calibrator_type : str
        "ar6" (default) or "gcam".  Determines calibration data source.

    Returns (model, initial_state, solver).
    """
    pop_df = ssp_data["population"]
    gdp_df = ssp_data["gdp"]

    def _ssp_at_base(df, region, fallback):
        if BASE_YEAR in df.columns:
            return float(df.loc[region, BASE_YEAR])
        available = sorted(
            y for y in df.columns
            if isinstance(y, (int, float)) and y <= BASE_YEAR
        )
        return float(df.loc[region, available[-1]]) if available else fallback

    # Calibrator
    calibrator: AR6Calibrator | Calibrator
    if calibrator_type == "gcam":
        from ghim.data.gcam_cal import load_gcam_calibration
        dataset = load_gcam_calibration(scenario=f"{scenario}-Ref")
        calibrator = Calibrator(dataset)
    else:
        calibrator = AR6Calibrator(ssp=scenario)

    # GDP source: GCAM GDP (MER, 2010$) when GCAM calibrator, else SSP (PPP, 2005$)
    use_gcam_gdp = calibrator_type == "gcam" and calibrator.available
    if use_gcam_gdp:
        gdp_by_r32 = {
            name: calibrator.get_gdp(BASE_YEAR, name) or 100.0
            for name in R32_REGIONS
        }
        logger.info("Using GCAM GDP (MER, billion US$2010)")
    else:
        gdp_by_r32 = {
            name: _ssp_at_base(gdp_df, name, 100.0)
            for name in R32_REGIONS
        }

    # Compute GDP shares for R10→R32 downscaling
    gdp_shares = _compute_gdp_shares_within_r10(gdp_by_r32)

    # Compute GDP shares within R5 groups (for AR6 sector total downscaling)
    gdp_shares_r5: dict[str, float] = {}
    for r5_name, r32_list in R5_TO_R32.items():
        group_gdp = sum(gdp_by_r32.get(r, 0.0) for r in r32_list)
        for r32 in r32_list:
            if group_gdp > 0:
                gdp_shares_r5[r32] = gdp_by_r32.get(r32, 0.0) / group_gdp
            else:
                gdp_shares_r5[r32] = 1.0 / len(r32_list)

    regions: dict[str, Region] = {}
    initial_state = PeriodState(period=BASE_YEAR, regions={})

    for region_name in R32_REGIONS:
        base_gdp = gdp_by_r32[region_name]
        base_pop = _ssp_at_base(pop_df, region_name, 10.0)
        share = gdp_shares.get(region_name, 0.1)
        share_r5 = gdp_shares_r5.get(region_name)

        region, rs = build_region(
            region_name, base_gdp, base_pop, gdp_share=share,
            calibrator=calibrator, gdp_share_r5=share_r5,
        )

        # Initialize TFP trajectory — use GCAM GDP if available
        gdp_target = {}
        pop_series = {}
        for year in MODEL_YEARS:
            if use_gcam_gdp:
                g = calibrator.get_gdp(year, region_name)
                if g is not None and g > 0:
                    gdp_target[year] = g
            elif year in gdp_df.columns:
                gdp_target[year] = float(gdp_df.loc[region_name, year])
            if year in pop_df.columns:
                pop_series[year] = float(pop_df.loc[region_name, year])
        region.economy.init_tfp_trajectory(gdp_target, pop_series)

        regions[region_name] = region
        initial_state.regions[region_name] = rs

    # Bunkers (global)
    bunkers = BunkersSector()
    world_gdp = sum(rs.gdp for rs in initial_state.regions.values())
    bunkers.calibrate(
        {"liquids": 8.0, "biofuel": 0.5, "gas": 1.0},
        _default_carrier_prices(),
        world_gdp,
    )

    # --- TechChange: global learning manager (gap #13) ---
    tech_change = TechChange()
    # Register electricity techs from the first region (all regions share same tech list)
    first_region = next(iter(regions.values()))
    for sector in first_region.transformation:
        if hasattr(sector, "techs"):
            for t in sector.techs:
                if t.name not in tech_change.tech_names:
                    rnd_rate = DEFAULT_RND_RATES.get(t.name, 0.0)
                    tech_change.register(
                        name=t.name,
                        capex_0=t.capex,
                        cumulative_0=max(t.base_cumulative, 1.0),
                        lbd_rate=t.learning_rate,
                        rnd_rate=rnd_rate,
                    )
                    t.floor_cost = tech_change._params[t.name].floor
    tech_change.load_default_spillovers()

    # --- Trade: R10-level market clearing (gap #1) ---
    trade_module = None
    try:
        from ghim.data.trade_cal import build_regional_supplies, default_transport_costs
        from ghim.energy.trade import TradeModule
        regional_supplies = build_regional_supplies()
        transport_costs = default_transport_costs()
        trade_module = TradeModule(regional_supplies, transport_costs, enabled=True)
    except Exception as e:
        logger.warning("Trade module init failed: %s — running without trade", e)

    # Calibrator logging
    if calibrator.available:
        n_years = (len(calibrator._ar6_years) if isinstance(calibrator, AR6Calibrator)
                   else len(calibrator.dataset.years))
        logger.info("Calibrator '%s' loaded (%d years)", calibrator.model_name, n_years)
    else:
        logger.warning("Calibrator unavailable — using default preferences")

    # Assemble model
    model = GHIMModel(
        regions=regions,
        trade=trade_module,
        tech_change=tech_change,
        policy=policy,
        climate=DefaultClimateAdapter(),
        water=DefaultWaterAdapter(),
        afolu=DefaultAFOLUAdapter(),
    )
    model.bunkers = bunkers
    model.calibrator = calibrator  # type: ignore[attr-defined]
    model.gdp_shares_r5 = gdp_shares_r5  # type: ignore[attr-defined]

    # Exogenous GDP trajectory per region
    # GCAM: MER billion US$2010 | AR6: PPP billion US$2005
    exogenous_gdp: dict[str, dict[int, float]] = {}
    gdp_target_series: dict[str, dict[int, float]] = {}
    ssp_pop_series: dict[str, dict[int, float]] = {}
    for region_name in R32_REGIONS:
        exogenous_gdp[region_name] = {}
        gdp_target_series[region_name] = {}
        ssp_pop_series[region_name] = {}
        for year in MODEL_YEARS:
            if use_gcam_gdp:
                g = calibrator.get_gdp(year, region_name)
                if g is not None and g > 0:
                    exogenous_gdp[region_name][year] = g
                    gdp_target_series[region_name][year] = g
            elif year in gdp_df.columns:
                exogenous_gdp[region_name][year] = float(gdp_df.loc[region_name, year])
                gdp_target_series[region_name][year] = float(gdp_df.loc[region_name, year])
            if year in pop_df.columns:
                ssp_pop_series[region_name][year] = float(pop_df.loc[region_name, year])
    model.exogenous_gdp = exogenous_gdp
    # GDP target: always available for calibration (even in endog mode)
    model.ssp_gdp_target = deepcopy(exogenous_gdp)  # type: ignore[attr-defined]

    # --- Iterative TFP calibration ---
    # GDP = Q − P_E·E − P_M·M creates a price-GDP feedback loop.
    # A single exogenous-GDP calibration pass records prices inconsistent
    # with endogenous equilibrium.  Iterate until convergence:
    #   Pass 1 (exogenous GDP): initial equilibrium prices
    #   Pass 2+ (endogenous GDP): re-equilibrate with CES-determined GDP
    from ghim.core.config import EconomyConfig
    want_endogenous = EconomyConfig().endogenous_gdp

    _N_CAL_PASSES = 4 if want_endogenous else 1
    for _cal_pass in range(_N_CAL_PASSES):
        ref_energy, ref_gdp, ref_price = _calibration_pass(
            model, deepcopy(initial_state), ssp_data,
        )
        for region_name, region in model.regions.items():
            region.economy.init_tfp_trajectory(
                gdp_target_series.get(region_name, {}),
                ssp_pop_series.get(region_name, {}),
                ref_energy_by_year=ref_energy.get(region_name),
                ref_price_by_year=ref_price.get(region_name),
            )

        if _cal_pass == 0 and want_endogenous:
            # Switch to endogenous GDP for subsequent calibration passes
            model.exogenous_gdp = None
            logger.info("Calibration pass 1 (exogenous) — switching to endogenous GDP")
        elif want_endogenous:
            # Check convergence: max GDP deviation across all regions/years
            max_dev = 0.0
            for rn in ref_gdp:
                for yr, gdp_val in ref_gdp[rn].items():
                    target = gdp_target_series.get(rn, {}).get(yr, 0)
                    if target > 0:
                        dev = abs(gdp_val - target) / target
                        max_dev = max(max_dev, dev)
            logger.info("Calibration pass %d (endogenous) — max GDP dev %.1f%%",
                         _cal_pass + 1, max_dev * 100)
            if max_dev < 0.02:
                break

    if want_endogenous:
        model.exogenous_gdp = None
        logger.info("Endogenous GDP enabled — CES determines GDP")

    # Solver — skip_gdp=True either way (GDP is derived, not iterated)
    solver = DampedSolver(
        alpha=0.3, tol=5e-3, max_iter=150,
        skip_gdp=True,
    )

    return model, initial_state, solver


# ---------------------------------------------------------------------------
# AR6 per-period calibration (applied BEFORE solver at each period)
# ---------------------------------------------------------------------------

_SECTOR_AR6_NAME = {
    "IndustrySector": "industry",
    "BuildingsSector": "buildings",
    "TransportSector": "transport",
    "AgricultureSector": "agriculture",
}


def _subsector_adjusted_shares(
    sector_shares: dict[str, float],
    sub_carriers: set[str],
    other_carriers: set[str],
    sub_fraction: float,
) -> dict[str, float]:
    """Adjust sector-level carrier shares for a subsector's fraction of demand.

    When a demand sector has multiple subsectors (e.g. industry EU/FS), applying
    sector-level shares to each subsector dilutes carriers that exist in only one
    subsector.  This rescales so that ``sub_share × sub_fraction`` reproduces
    the correct sector-level share for carriers unique to this subsector.

    Parameters
    ----------
    sector_shares : sector-level carrier target shares (sum ≈ 1)
    sub_carriers : carriers present in this subsector's tech list
    other_carriers : carriers present in OTHER subsectors (not this one)
    sub_fraction : this subsector's demand fraction (e.g. 0.75 for EU)
    """
    if sub_fraction >= 1.0 or sub_fraction <= 0:
        return sector_shares

    # Carriers unique to this subsector (not in any other subsector)
    exclusive = sub_carriers - other_carriers

    adjusted: dict[str, float] = {}
    exclusive_sum_adjusted = 0.0
    for c in exclusive:
        s = sector_shares.get(c, 0.0)
        # Scale up: sector_share = sub_share × sub_frac → sub_share = sector_share / sub_frac
        adjusted[c] = s / sub_fraction
        exclusive_sum_adjusted += adjusted[c]

    # Remaining capacity for shared carriers within this subsector
    remaining = max(1.0 - exclusive_sum_adjusted, 0.0)
    shared_in_sub = {c: sector_shares.get(c, 0.0) for c in sub_carriers if c not in exclusive}
    shared_sum = sum(shared_in_sub.values())
    if shared_sum > 0 and remaining > 0:
        for c in shared_in_sub:
            adjusted[c] = shared_in_sub[c] / shared_sum * remaining
    elif shared_sum == 0:
        for c in shared_in_sub:
            adjusted[c] = 0.0

    # Renormalize
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {c: v / total for c, v in adjusted.items()}
    return adjusted


def _apply_calibration(
    model: GHIMModel,
    state: PeriodState,
    period: int,
) -> None:
    """Recalibrate electricity + demand-sector preferences from target data.

    Called BEFORE solver.solve() at each model period. Updates preference
    factors on sectors/subsectors so the logit reproduces target shares.
    Works with both AR6Calibrator (R5, needs downscaling) and Calibrator
    (native R32, no downscaling).
    """
    calibrator: AR6Calibrator | Calibrator | None = getattr(model, "calibrator", None)
    if calibrator is None or not calibrator.available:
        return

    is_native_r32 = getattr(calibrator, 'native_r32', False)

    for region_name, region in model.regions.items():
        rs = state.regions[region_name]

        # --- Electricity sector ---
        for sector in region.transformation:
            if isinstance(sector, OOPElectricitySector):
                prefs = calibrator.electricity_prefs(
                    period, sector.techs, rs.raw_fuel_prices,
                    region_r32=region_name,
                    carbon_price=getattr(rs, "carbon_price", 0.0),
                )
                if prefs is not None:
                    sector.base_pref_factors = prefs
                    sector.pref_factors = prefs
                    sector.calibration_year = period
                    # Cache target shares for inline recalibration in F()
                    target_shares = calibrator.get_elec_target_shares(
                        period, region_name,
                    )
                    if target_shares is not None:
                        sector._target_tech_shares = np.array([
                            target_shares.get(t.name, 1e-6)
                            for t in sector.techs
                        ])
                        sector._target_tech_shares = np.maximum(
                            sector._target_tech_shares, 1e-6,
                        )
                        sector._target_tech_shares /= sector._target_tech_shares.sum()

                # Generation scaling: GCAM gen includes T&D losses + own-use
                if is_native_r32 and hasattr(calibrator, 'get_elec_generation'):
                    target_gen = calibrator.get_elec_generation(period, region_name)
                    if target_gen is not None and target_gen > 0:
                        sector._generation_target = target_gen

            # --- Hydrogen sector ---
            if isinstance(sector, OOPHydrogenSector):
                if is_native_r32 and hasattr(calibrator, 'get_h2_production'):
                    target = calibrator.get_h2_production(period, region_name)
                    if target is not None and target > 0:
                        sector._generation_target = target

            # --- District heat sector ---
            if isinstance(sector, DistrictHeatingSector):
                if is_native_r32 and hasattr(calibrator, 'get_heat_production'):
                    target = calibrator.get_heat_production(period, region_name)
                    if target is not None and target > 0:
                        sector._generation_target = target

        # --- Demand sectors ---
        for sector in region.demand_sectors:
            sector_ar6 = _SECTOR_AR6_NAME.get(
                type(sector).__name__,
            )
            if sector_ar6 is None:
                continue

            # --- Carrier share recalibration ---
            # For buildings with subsector data: use per-subsector shares
            has_subsector = (
                sector_ar6 == "buildings"
                and is_native_r32
                and hasattr(calibrator, 'get_subsector_carrier_shares')
            )

            # Update buildings independent subsector demands from GCAM
            if has_subsector and hasattr(sector, 'calibrate_subsector_demands'):
                sub_totals: dict[str, float] = {}
                for sub in sector.subsectors:
                    st = calibrator.get_subsector_total(
                        period, sub.name, region_name,
                    )
                    if st is not None and st > 0:
                        sub_totals[sub.name] = st
                if sub_totals:
                    sector.calibrate_subsector_demands(sub_totals, rs=rs)

            # For multi-subsector sectors (industry EU/FS, transport pass/freight):
            # sector-level carrier shares must be adjusted per subsector so that
            # sub_share × sub_frac sums to the target sector-level share.
            _needs_sub_adjust = (
                len(sector.subsectors) > 1
                and sector_ar6 in ("industry", "transport")
            )
            _sector_target = None
            _sub_carrier_sets: dict[str, set[str]] = {}
            _sub_fracs: dict[str, float] = {}
            if _needs_sub_adjust:
                _sector_target = calibrator.get_sector_carrier_shares(
                    period, sector_ar6, region_name,
                )
                if _sector_target is not None:
                    for s in sector.subsectors:
                        _sub_carrier_sets[s.name] = {t.carrier for t in s.techs}
                    # Determine fractions
                    if isinstance(sector, IndustrySector):
                        _sub_fracs = {
                            sector.eu.name: sector.eu_fraction,
                            sector.fs.name: sector.fs_fraction,
                        }
                    elif isinstance(sector, TransportSector):
                        _sub_fracs = {
                            sector.passenger.name: sector.pass_fraction,
                            sector.freight.name: sector.freight_fraction,
                        }

            for sub in sector.subsectors:
                if has_subsector:
                    # Use subsector-specific carrier shares (e.g. residential.heating)
                    sub_target = calibrator.get_subsector_carrier_shares(
                        period, sub.name, region_name,
                    )
                    if sub_target is not None:
                        # Override with subsector-level target
                        if len(sub.techs) > 1:
                            from ghim.energy.logit import preference_calibrate
                            from ghim.calibration import _expand_carrier_shares_to_techs
                            from ghim.core.technology import Powertrain
                            costs = np.array([
                                t.lcot(rs.carrier_prices.get(t.carrier, 5.0))
                                if isinstance(t, Powertrain)
                                else t.levelized_cost(rs.carrier_prices.get(t.carrier, 5.0))
                                for t in sub.techs
                            ])
                            tech_shares = _expand_carrier_shares_to_techs(
                                sub_target, sub.techs, costs, sub.logit_scale,
                            )
                            prefs = preference_calibrate(
                                tech_shares, costs, sub.logit_scale,
                            )
                            sub.pref_factors = prefs
                            sub._target_svc_shares = tech_shares  # cache (bld eff=1.0)
                            sub.calibration_year = period
                        continue

                # Multi-subsector adjusted shares
                if _needs_sub_adjust and _sector_target is not None and len(sub.techs) > 1:
                    sub_frac = _sub_fracs.get(sub.name, 1.0 / len(sector.subsectors))
                    sub_carriers = _sub_carrier_sets.get(sub.name, {t.carrier for t in sub.techs})
                    other_carriers = set()
                    for other_name, other_cs in _sub_carrier_sets.items():
                        if other_name != sub.name:
                            other_carriers |= other_cs
                    adjusted = _subsector_adjusted_shares(
                        _sector_target, sub_carriers, other_carriers, sub_frac,
                    )
                    from ghim.energy.logit import preference_calibrate
                    from ghim.calibration import _expand_carrier_shares_to_techs
                    from ghim.core.technology import Powertrain
                    costs = np.array([
                        t.lcot(rs.carrier_prices.get(t.carrier, 5.0))
                        if isinstance(t, Powertrain)
                        else t.levelized_cost(rs.carrier_prices.get(t.carrier, 5.0))
                        for t in sub.techs
                    ])
                    tech_shares = _expand_carrier_shares_to_techs(
                        adjusted, sub.techs, costs, sub.logit_scale,
                    )
                    # Efficiency correction: convert FE shares to service
                    # shares so carrier_demands(share/eff) recovers FE target.
                    effs = np.array([t.efficiency for t in sub.techs])
                    svc_shares = tech_shares * effs
                    svc_shares = np.maximum(svc_shares, 1e-6)
                    svc_shares /= svc_shares.sum()
                    prefs = preference_calibrate(
                        svc_shares, costs, sub.logit_scale,
                    )
                    sub.pref_factors = prefs
                    sub._target_svc_shares = svc_shares  # cache for F() re-cal
                    sub.calibration_year = period
                    continue

                prefs = calibrator.demand_carrier_prefs(
                    period, sub, rs.carrier_prices,
                    sector_ar6, region_r32=region_name,
                )
                if prefs is not None:
                    sub.pref_factors = prefs
                    sub.calibration_year = period

            # --- Sector total: sector_pref_weight via price channel ---
            # Replace _demand_scale with a preference weight on the sector
            # price index.  Inverse solve:
            #   target = base × (GDP/GDP₀)^α × ((P+w)/P₀)^γ
            #   w = P × ((target/model_at_w0)^(1/γ) − 1)
            target_fe: float | None = None
            cal_total = calibrator.get_sector_total(
                period, sector_ar6, region_name,
            )

            if is_native_r32:
                if cal_total is not None and cal_total > 0:
                    target_fe = cal_total
            else:
                gdp_shares_r5 = getattr(model, "gdp_shares_r5", None)
                if gdp_shares_r5 is not None:
                    share_r5 = gdp_shares_r5.get(region_name, 0.0)
                    if cal_total is not None and cal_total > 0 and share_r5 > 0:
                        target_fe = cal_total * share_r5

            if target_fe is not None and target_fe > 0:
                orig_gdp = rs.gdp
                ssp_target = getattr(model, "ssp_gdp_target", None)
                exog = getattr(model, "exogenous_gdp", None)
                if ssp_target is not None:
                    ssp_val = ssp_target.get(region_name, {}).get(period)
                    if ssp_val is not None:
                        rs.gdp = ssp_val
                elif exog is not None:
                    exog_val = exog.get(region_name, {}).get(period)
                    if exog_val is not None:
                        rs.gdp = exog_val

                # Compute model FE with pref_weight = 0
                sector.sector_pref_weight = 0.0
                model_fe_dict = sector.compute_demand(rs, model.policy)
                model_fe = sum(model_fe_dict.values())

                if model_fe > 0:
                    gamma = sector.price_elasticity
                    P = sector.sector_price_index(rs)  # w=0 here
                    ratio = target_fe / model_fe
                    if abs(gamma) > 1e-6 and P > 0:
                        # w = P × (ratio^(1/γ) − 1)
                        sector.sector_pref_weight = P * (
                            ratio ** (1.0 / gamma) - 1.0
                        )
                    else:
                        sector._demand_scale = ratio

                rs.gdp = orig_gdp


# ---------------------------------------------------------------------------
# OOP run loop (§9 from design doc)
# ---------------------------------------------------------------------------

def oop_run_model(
    ssp_data: dict[str, Any],
    scenario: str = "SSP2",
    policy: Any = None,
    calibrator_type: str = "ar6",
) -> list[PeriodState]:
    """Run the OOP model for all R32 regions, all periods.

    SSP data should be R32-aggregated (from load_ssp_data_r32).
    Returns a list of PeriodState (one per period).
    """
    model, state, solver = build_oop_model(ssp_data, scenario, policy,
                                            calibrator_type=calibrator_type)

    pop_df = ssp_data["population"]
    gdp_df = ssp_data["gdp"]

    # Seed trade module with observed base-year prices for smoothing
    if model.trade is not None and hasattr(model.trade, "enabled") and model.trade.enabled:
        from ghim.config import OBSERVED_FUEL_PRICES_2020
        model.trade.prev_world_prices = dict(OBSERVED_FUEL_PRICES_2020)
        # Seed base-year regional production for production smoothing
        from ghim.data.energy_cal import DEFAULT_PRIMARY_ENERGY
        from ghim.regions import R10_REGIONS
        for fuel in TRADED_FUELS:
            model.trade.prev_regional_production[fuel] = {
                r: DEFAULT_PRIMARY_ENERGY.get(r, {}).get(fuel, 0.0)
                for r in R10_REGIONS
            }

    results: list[PeriodState] = []
    is_first_period = True

    for period in FUTURE_YEARS:
        state.period = period
        for name, rs in state.regions.items():
            if period in pop_df.columns:
                rs.population = float(pop_df.loc[name, period])
            model.regions[name].economy.set_tfp_for_year(period)

        # AR6 preference recalibration (BEFORE solver)
        _apply_calibration(model, state, period)

        # Warm-up: seed first period with one F(x) pass so initial
        # carrier/world prices are self-consistent before solving
        if is_first_period:
            state = model.F(state)
            state.period = period
            is_first_period = False

        # Solve with FE recalibration loop: _demand_scale computed at
        # pre-solver prices may be wrong after convergence (price
        # elasticity shifts demand).  Re-calibrate and re-solve until
        # FE matches AR6 targets within tolerance.
        _FE_RECAL_ROUNDS = 3
        _FE_RECAL_TOL = 0.02  # 2%
        for _fe_round in range(_FE_RECAL_ROUNDS):
            # Emissions cap: bisection wrapper if policy has a cap for this period
            if (policy is not None
                    and hasattr(policy, "emissions_cap")
                    and policy.emissions_cap.has_cap(period)):
                from ghim.solver.emissions_cap import EmissionsCapWrapper
                cap_gt = policy.emissions_cap.get_cap("global", period) / 1000.0  # Mt→Gt
                cap_solver = EmissionsCapWrapper(
                    solver,
                    tol=policy.emissions_cap.bisect_tol,
                    max_iter=policy.emissions_cap.bisect_max_iter,
                    price_ceiling=policy.emissions_cap.bisect_price_max,
                )
                state = cap_solver.solve(model, state, cap_gt)
            else:
                state = solver.solve(model, state)

            # Re-calibrate _demand_scale at converged prices
            if _fe_round < _FE_RECAL_ROUNDS - 1:
                _apply_calibration(model, state, period)
                state.period = period  # restore after recal

        # GDP tracking diagnostic (endogenous mode)
        if model.exogenous_gdp is None:
            gdp_target = getattr(model, "ssp_gdp_target", None) or {}
            for name, rs in state.regions.items():
                target = gdp_target.get(name, {}).get(period)
                if target is not None and target > 0:
                    dev = (rs.gdp - target) / target
                    if abs(dev) > 0.02:
                        logger.warning(
                            "Period %d %s: GDP dev %.1f%% (model=%.0f, target=%.0f)",
                            period, name, dev * 100, rs.gdp, target,
                        )

        # Inter-period updates (NOT part of F)
        for name, region in model.regions.items():
            rs = state.regions[name]

            # Capital accumulation
            region.economy.update_capital(rs.investment)
            rs.capital_stock = region.economy.capital_stock

            # Vintage pruning (memory optimization)
            for sector in region.transformation:
                if hasattr(sector, "vintage") and sector.vintage is not None:
                    sector.vintage.prune_retired(period)

            # Demand sector: carry forward converged demand for next period
            for sector in region.demand_sectors:
                if hasattr(sector, '_last_demand_ej'):
                    sd = rs.sector_demand.get(
                        _SECTOR_AR6_NAME.get(type(sector).__name__), {},
                    )
                    if sd:
                        sector._last_demand_ej = sum(sd.values())

        # --- TechChange: learning curve updates (gap #2) ---
        if model.tech_change is not None:
            # Aggregate global deployment by tech from generation
            global_new_cap: dict[str, float] = {}
            for name, rs_snap in state.regions.items():
                for carrier, gen_dict in rs_snap.generation.items():
                    if isinstance(gen_dict, dict):
                        for tech, ej in gen_dict.items():
                            global_new_cap[tech] = global_new_cap.get(tech, 0.0) + ej

            model.tech_change.update_deployment(global_new_cap, timestep=TIMESTEP)

            # Exogenous RND spending (Phase 1: fixed defaults, billion $/period)
            exogenous_rnd = {
                "solar": 2.0, "wind": 1.0, "nuclear": 0.5,
                "electrolysis": 0.5, "coal_ccs": 0.3, "gas_ccs": 0.3,
                "biomass_ccs": 0.2, "bev_battery": 1.0,
            }
            model.tech_change.update_knowledge(exogenous_rnd)

            # Recompute capex and push to all regions' SupplyTechs
            new_capex = model.tech_change.compute_all_capex()
            for name, region in model.regions.items():
                for sector in region.transformation:
                    if hasattr(sector, "techs"):
                        for t in sector.techs:
                            if t.name in new_capex:
                                t.capex = new_capex[t.name]

        # --- Trade: inter-period updates (gap #1) ---
        if model.trade is not None and hasattr(model.trade, "enabled") and model.trade.enabled:
            # Get trade results from the last F() call (stored on model)
            trade_results = getattr(model, "_last_trade_results", None)
            if trade_results is not None:
                model.trade.smooth_prices(trade_results, TRADE_MAX_PRICE_CHANGE)
                model.trade.smooth_production(trade_results, TRADE_MAX_PROD_DECLINE)
                model.trade.record_world_prices(trade_results)
                model.trade.record_regional_production(trade_results)
                model.trade.update_depletion(trade_results, timestep=TIMESTEP)

        results.append(deepcopy(state))
        logger.info(
            "Period %d done: global GDP=%.0f, emissions=%.2f GtCO2eq",
            period,
            sum(rs.gdp for rs in state.regions.values()),
            state.global_emissions,
        )

    return results
