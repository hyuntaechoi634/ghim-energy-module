"""GHIMModel — top-level orchestrator.

F(x) is a single model pass: External -> Economy -> Demand -> Transformation
-> Trade -> Price -> GDP -> Emissions.  The solver calls F(x) repeatedly
until convergence.

Price channels (critical for carbon tax correctness):
  raw_fuel_prices  = world_price + transport_cost  (no carbon tax)
  carrier_prices   = consumer-facing prices         (carbon-inclusive)

Carbon tax enters at TWO points, each exactly once per emission:
  1. SupplyTech.lcoe(raw_prices, tau) -> carbon_cost in LCOE (CCS-aware)
  2. Direct-use fuels: raw + CARBON_COEFS * TC_TO_TCO2 * tau
No double-counting: CARBON_COEFS[ELECTRICITY/H2/HEAT] = 0.

Policy instruments (8 total, all wired via PolicyScenario):
  - Carbon price: Steps 4 (LCOE) + 6a (carrier adder)
  - Efficiency standards: Step 3 (demand × AEEI factor)
  - Renewable subsidies: Step 4 (LCOE reduction)
  - Tech constraints: Step 4 (post-logit share clamping)
  - Tech availability: Steps 3-4 (via sector logit)
  - Pref overrides: Steps 3-4 (via sector logit)
  - Revenue recycling: Step 8 (diagnostic tracking)
  - Emissions cap: Outside F — bisection wrapper (EmissionsCapWrapper)
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import numpy as np

from ghim.core.carrier import (
    Carrier,
    CARBON_COEFS,
    CH4_FUGITIVE,
    GWP100,
    LULUCF_NET_CO2,
    TC_TO_TCO2,
)
from ghim.core.config import BASE_YEAR
from ghim.core.emissions import EmissionResult
from ghim.core.region import Region
from ghim.core.state import PeriodState, RegionState
from ghim.core.technology import Powertrain
from ghim.adapters.base import ExternalInterface
from ghim.energy.logit import preference_calibrate

logger = logging.getLogger(__name__)

# Waste CH4 per capita baseline (MtCH4 per million people, empirical)
WASTE_CH4_PER_CAPITA = 0.0015  # ~1.5 ktCH4 per million at base income


class GHIMModel:
    """Top-level model: regions, trade, learning, policy, external adapters."""

    def __init__(
        self,
        regions: dict[str, Region],
        trade: Any = None,
        tech_change: Any = None,
        policy: Any = None,
        climate: ExternalInterface | None = None,
        water: ExternalInterface | None = None,
        afolu: ExternalInterface | None = None,
    ) -> None:
        self.regions = regions
        self.trade = trade
        self.tech_change = tech_change
        self.policy = policy
        self.climate = climate
        self.water = water
        self.afolu = afolu
        self.bunkers: Any = None  # global, not per-region

        # Exogenous GDP: if set, overrides CES output with SSP trajectory.
        # Dict mapping region_name → {year → GDP_billion_USD}.
        self.exogenous_gdp: dict[str, dict[int, float]] | None = None

    # ------------------------------------------------------------------
    # F(x): one full model pass
    # ------------------------------------------------------------------

    def F(self, state: PeriodState) -> PeriodState:
        """One full model pass.  Returns updated state.

        8 steps following design/implementation.md §7.
        No inner iteration loops — the outer solver handles convergence.
        """
        new = deepcopy(state)
        period = new.period
        carbon_price = self._get_carbon_price(period)

        # Store carbon price on state for sectors and reporting
        new.policy_carbon_price = carbon_price

        # Step 1: External modules
        if self.climate is not None:
            self.climate.update(new)
        if self.water is not None:
            self.water.update(new)
        if self.afolu is not None:
            self.afolu.update(new)

        # Steps 2-4: Per-region economy, demand, transformation
        for name, region in self.regions.items():
            rs = new.regions[name]
            rs.carbon_price = carbon_price
            rs._year = period  # for sectors that need year

            # Step 2: Economy -> VA, total energy demand
            va = region.economy.compute_value_added(rs.population)
            rs.value_added = va
            total_e = region.economy.compute_energy_demand(
                va, rs.composite_energy_price
            )

            # Step 3: Demand sectors -> carrier demands
            # 3a. AEEI: efficiency standards reduce demand
            aeei = self._get_aeei_factor(period)
            rs.aeei_factor = aeei
            total_e *= aeei

            # 3b. Re-calibrate subsector preferences at current prices.
            # _target_svc_shares (cached by _apply_calibration) are the
            # service-level shares that reproduce GCAM FE targets after
            # efficiency conversion.  Re-solving the inverse logit at
            # current carrier prices keeps shares on-target even as the
            # solver iterates and prices change.
            for sector in region.demand_sectors:
                for sub in sector.subsectors:
                    tgt = getattr(sub, '_target_svc_shares', None)
                    if tgt is None or len(sub.techs) <= 1:
                        continue
                    costs = np.array([
                        t.lcot(rs.carrier_prices.get(t.carrier, 5.0))
                        if isinstance(t, Powertrain)
                        else t.levelized_cost(rs.carrier_prices.get(t.carrier, 5.0))
                        for t in sub.techs
                    ])
                    sub.pref_factors = preference_calibrate(
                        tgt, costs, sub.logit_scale,
                    )
                    sub.calibration_year = period  # prevent decay

            raw_demands: dict[str, float] = {}
            _sector_names = {
                "IndustrySector": "industry",
                "BuildingsSector": "buildings",
                "TransportSector": "transport",
                "AgricultureSector": "agriculture",
            }
            for sector in region.demand_sectors:
                d = sector.compute_demand(rs, self.policy)
                # Store per-sector demands for emissions and reporting
                sn = _sector_names.get(type(sector).__name__)
                if sn:
                    rs.sector_demand[sn] = d
                for c, v in d.items():
                    raw_demands[c] = raw_demands.get(c, 0.0) + v

            # Add water energy demand to electricity
            raw_demands["electricity"] = (
                raw_demands.get("electricity", 0.0) + rs.water_energy_demand
            )

            # Scale sector demands to CES total energy.
            # When calibration is active, sector demands are already
            # calibrated via sector_pref_weight and preference factors —
            # use them directly. EL/NEL electrification signal is injected
            # as a cost bias into the logit (soft coupling, not hard scaling).
            raw_sum = sum(raw_demands.values())
            calibrator = getattr(self, "calibrator", None)
            has_calibrator = (
                calibrator is not None
                and getattr(calibrator, "available", False)
            )

            if has_calibrator:
                # Calibrated path: sector demands drive energy total.
                # EL/NEL split is determined by sector logit calibration,
                # not by KLEM CES. KLEM EL/NEL nest only affects GDP via
                # the production function (compute_energy_demand → compute_gdp).
                rs.final_demand = dict(raw_demands)
                total_e = raw_sum
            else:
                # No calibrator: uniform scaling to CES total
                scale = total_e / raw_sum if raw_sum > 0 else 1.0
                rs.final_demand = {c: v * scale for c, v in raw_demands.items()}

            # Step 4: Transformation sectors -> generation, prices
            # 4pre. Re-calibrate electricity pref factors at current prices
            for sector in region.transformation:
                tgt_shares = getattr(sector, '_target_tech_shares', None)
                if tgt_shares is not None and hasattr(sector, 'techs'):
                    carbon_price_val = getattr(rs, 'carbon_price', 0.0)
                    lcoe = np.array([
                        t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price_val)
                        for t in sector.techs
                    ])
                    lcoe = np.maximum(lcoe, 0.01)
                    prefs = preference_calibrate(
                        tgt_shares, lcoe,
                        getattr(sector, 'scale_k', 0.3),
                        logit_exp=getattr(sector, 'logit_exp', -4.0),
                    )
                    sector.base_pref_factors = prefs
                    sector.pref_factors = prefs

            # Sectors read carbon_price from rs, subsidies from policy
            for sector in region.transformation:
                demand = rs.final_demand.get(sector.carrier_output, 0.0)
                # Electricity: add T&D + ownuse losses
                td_loss = getattr(sector, '_td_loss_rate', 0.0)
                if td_loss > 0 and demand > 0:
                    demand = demand / (1.0 - td_loss)
                gen = sector.compute_supply(rs, demand, self.policy)

                # 4a. Tech constraints: post-logit share clamping
                gen = self._apply_tech_constraints(
                    gen, sector, period,
                )

                price = sector.compute_price(rs)
                rs.carrier_prices[sector.carrier_output] = price
                rs.generation[sector.carrier_output] = gen

        # Step 5: Trade clearing (global)
        if self.trade is not None:
            self._clear_trade(new)

        # Step 6: Build consumer-facing carrier prices (carbon-inclusive)
        cp_policy = self._get_carbon_price_policy()
        for name, region in self.regions.items():
            rs = new.regions[name]

            # 6a. Direct-use fuels: raw price + CO2 carbon tax + fugitive CH4
            for fuel in [Carrier.COAL, Carrier.GAS, Carrier.LIQUIDS,
                         Carrier.BIOMASS, Carrier.BIOFUEL]:
                raw = rs.raw_fuel_prices.get(
                    fuel, rs.carrier_prices.get(fuel, 0.0)
                )
                # CO2 adder (only if cover_co2 is True)
                co2_adder = 0.0
                if cp_policy is None or cp_policy.cover_co2:
                    co2_adder = CARBON_COEFS.get(fuel, 0.0) * TC_TO_TCO2 * carbon_price

                # Fugitive CH4 adder (only if cover_fugitive_ch4 is True)
                ch4_adder = 0.0
                if cp_policy is not None and cp_policy.cover_fugitive_ch4:
                    # CH4_FUGITIVE is tCH4/EJ; convert to $/GJ:
                    # intensity × GWP100 × τ / 1e9 (EJ→GJ)
                    ch4_intensity = CH4_FUGITIVE.get(fuel, 0.0)
                    if ch4_intensity > 0:
                        ch4_adder = (
                            ch4_intensity * GWP100["ch4"] * carbon_price / 1e9
                        )

                rs.carrier_prices[fuel] = raw + co2_adder + ch4_adder

            # 6a-ag. Agriculture non-energy GHG cost (if priced)
            if cp_policy is not None and cp_policy.cover_agriculture_ghg:
                for sector in region.demand_sectors:
                    if hasattr(sector, "base_ch4"):
                        co2eq_mt = (
                            sector.base_ch4 * GWP100["ch4"]
                            + getattr(sector, "base_n2o", 0.0) * GWP100["n2o"]
                        )
                        base_e = sector.base_demand
                        if base_e > 0 and co2eq_mt > 0:
                            # $/GJ = MtCO2eq × $/tCO2 / (EJ × 1e3)
                            rs.ag_ghg_cost_per_gj = (
                                co2eq_mt * carbon_price / (base_e * 1e3)
                            )

            # 6b. Sector price indices
            for sector in region.demand_sectors:
                rs.sector_prices[type(sector).__name__] = (
                    sector.sector_price_index(rs)
                )

            # 6c. Composite energy price (for CES FOC)
            from ghim.econ.klem import KLEMDriver
            rs.composite_energy_price = KLEMDriver.composite_energy_price(
                rs.carrier_prices, rs.final_demand
            )

        # Step 7: GDP = Q − P_E·E − P_M·M  (net output)
        # Use actual composite energy price so energy price feedback
        # affects GDP: higher P_E → lower E demand → lower Q → lower GDP.
        for name, region in self.regions.items():
            rs = new.regions[name]
            p_e = rs.composite_energy_price
            e_klem = region.economy.compute_energy_demand(rs.value_added, p_e)
            rs.gdp = region.economy.compute_gdp(rs.value_added, e_klem, p_e)

            # Exogenous GDP override: use SSP trajectory instead of CES output
            if self.exogenous_gdp is not None:
                exog = self.exogenous_gdp.get(name, {})
                if new.period in exog:
                    rs.gdp = exog[new.period]

            inv = region.economy.compute_investment(rs.gdp)
            rs.investment = inv

        # Step 8: Emissions (multi-gas) + policy tracking
        total_global = EmissionResult()
        for name, region in self.regions.items():
            rs = new.regions[name]
            region_em = EmissionResult()

            # 8a. Transformation sectors
            for sector in region.transformation:
                gen = rs.generation.get(sector.carrier_output, {})
                region_em = region_em + sector.compute_emissions(gen)

            # 8b. Demand sectors
            for sector in region.demand_sectors:
                region_em = region_em + sector.compute_emissions(rs)

            # 8c. Fugitive CH4 from fossil production
            for fuel in [Carrier.COAL, Carrier.OIL, Carrier.GAS]:
                prod = rs.regional_production.get(fuel, 0.0)
                ch4_factor = CH4_FUGITIVE.get(fuel, 0.0)
                region_em.ch4 += prod * ch4_factor

            # 8d. Waste CH4 (population + income scaled)
            if rs.population > 0:
                gdp_per_cap = rs.gdp / rs.population
                region_em.ch4 += (
                    rs.population * WASTE_CH4_PER_CAPITA
                    * max(gdp_per_cap, 0.01) ** 0.3
                )

            # 8e. F-Gases: placeholder (Phase 1: scaled by region GDP)

            # 8f. LULUCF (exogenous, Phase 1)
            lulucf_gt = LULUCF_NET_CO2.get(name, 0.0)
            region_em.lulucf = lulucf_gt * 1000.0  # GtCO2 -> MtCO2

            rs.emissions_detail = region_em
            rs.emissions = region_em.co2eq

            # 8g. Carbon revenue tracking (diagnostic)
            # revenue = τ ($/tCO2) × CO2 emissions (MtCO2) × 1e-3 (Mt→Gt) × 1e3 (G$→B$)
            # = τ × CO2_mt × 1e-3 (billion$, since τ is $/t and CO2 is Mt)
            rs.carbon_revenue = carbon_price * region_em.co2 * 1e-3

            total_global = total_global + region_em

        # Bunkers emissions (global, not per-region)
        if self.bunkers is not None:
            bunker_rs = RegionState(
                gdp=sum(rs.gdp for rs in new.regions.values()),
                carrier_prices=dict(
                    next(iter(new.regions.values())).carrier_prices
                ) if new.regions else {},
            )
            bunker_d = self.bunkers.compute_demand(bunker_rs, self.policy)
            bunker_rs.sector_demand["bunkers"] = bunker_d
            bunker_em = self.bunkers.compute_emissions(bunker_rs)
            total_global = total_global + bunker_em

        new.global_emissions = total_global.co2eq / 1000.0  # Mt -> Gt
        new.global_emissions_detail = total_global

        return new

    # ------------------------------------------------------------------
    # Policy helpers
    # ------------------------------------------------------------------

    def _get_carbon_price(self, period: int) -> float:
        """Get carbon price from policy ($/tCO2). Returns 0 if no policy."""
        if self.policy is None:
            return 0.0
        if hasattr(self.policy, "get_carbon_price"):
            return self.policy.get_carbon_price(period)
        if hasattr(self.policy, "carbon_price"):
            cp = self.policy.carbon_price
            if callable(cp):
                return cp(period)
            if hasattr(cp, "get_price"):
                return cp.get_price(period)
            if isinstance(cp, (int, float)):
                return float(cp)
        return 0.0

    def _get_carbon_price_policy(self):
        """Get the CarbonPricePolicy object (for coverage toggles). Returns None if absent."""
        if self.policy is None:
            return None
        if hasattr(self.policy, "carbon_price"):
            cp = self.policy.carbon_price
            if hasattr(cp, "cover_co2"):
                return cp
        return None

    def _get_aeei_factor(self, period: int) -> float:
        """Get cumulative AEEI factor from policy. Returns 1.0 if no policy."""
        if self.policy is None:
            return 1.0
        if not hasattr(self.policy, "efficiency_standards"):
            return 1.0
        es = self.policy.efficiency_standards
        if not hasattr(es, "cumulative_factor"):
            return 1.0
        return es.cumulative_factor("global", period, BASE_YEAR)

    def _apply_tech_constraints(
        self,
        generation: dict[str, float],
        sector: Any,
        period: int,
    ) -> dict[str, float]:
        """Apply min/max share constraints from policy, redistribute excess."""
        if self.policy is None:
            return generation
        if not hasattr(self.policy, "tech_constraints"):
            return generation
        constraints = self.policy.tech_constraints
        if not constraints:
            return generation

        import numpy as np
        from ghim.policy import apply_share_constraints

        sector_name = getattr(sector, "carrier_output", type(sector).__name__)
        tech_names = list(generation.keys())
        total = sum(generation.values())
        if total <= 0:
            return generation

        shares = np.array([generation[t] / total for t in tech_names])
        adjusted = apply_share_constraints(
            shares, tech_names, constraints, period, sector_name,
        )
        return {t: float(s * total) for t, s in zip(tech_names, adjusted)}

    # ------------------------------------------------------------------
    # Trade
    # ------------------------------------------------------------------

    def _clear_trade(self, state: PeriodState) -> None:
        """Clear global fossil fuel markets (R32 demands → R10 clearing → R32 prices).

        1. Compute primary fuel demands per R32 (direct use + transformation input)
        2. Aggregate R32 → R10
        3. Call TradeModule.solve_trade() at R10 level
        4. Distribute delivered prices back to R32 regions
        """
        from ghim.regions_r32 import R32_TO_R10
        from ghim.core.config import TRADED_FUELS

        if self.trade is None or not hasattr(self.trade, "solve_trade"):
            return
        if not getattr(self.trade, "enabled", True):
            return

        # Carrier → trade fuel name mapping
        _CARRIER_TO_FUEL = {
            Carrier.COAL: "coal", Carrier.OIL: "oil", Carrier.GAS: "gas",
        }
        _FUEL_TO_CARRIER = {
            "coal": Carrier.COAL, "oil": Carrier.OIL, "gas": Carrier.GAS,
        }

        # Step 1: Compute R32 primary fuel demands
        r32_fuel_demands: dict[str, dict[str, float]] = {}
        for r32_name in state.regions:
            rs = state.regions[r32_name]
            demands: dict[str, float] = {}

            # Direct-use fuel demands
            for carrier, fuel in _CARRIER_TO_FUEL.items():
                demands[fuel] = demands.get(fuel, 0.0) + rs.final_demand.get(
                    fuel, rs.final_demand.get(carrier.value, 0.0)
                )

            # Transformation sector fuel consumption
            region = self.regions.get(r32_name)
            if region is not None:
                for sector in region.transformation:
                    if hasattr(sector, "fuel_consumption"):
                        gen = rs.generation.get(sector.carrier_output, {})
                        fc = sector.fuel_consumption(gen)
                        for fuel_input, ej in fc.items():
                            # Map fuel_input name to traded fuel
                            if fuel_input in ("coal",):
                                demands["coal"] = demands.get("coal", 0.0) + ej
                            elif fuel_input in ("gas",):
                                demands["gas"] = demands.get("gas", 0.0) + ej
                            elif fuel_input in ("oil", "refined liquids"):
                                demands["oil"] = demands.get("oil", 0.0) + ej

            r32_fuel_demands[r32_name] = demands

        # Step 2: Aggregate R32 → R10
        from ghim.regions import R10_REGIONS
        r10_demands: dict[str, dict[str, float]] = {
            r10: {f: 0.0 for f in TRADED_FUELS} for r10 in R10_REGIONS
        }
        for r32_name, demands in r32_fuel_demands.items():
            r10 = R32_TO_R10.get(r32_name)
            if r10 is None:
                continue
            for fuel, ej in demands.items():
                if fuel in TRADED_FUELS and r10 in r10_demands:
                    r10_demands[r10][fuel] = r10_demands[r10].get(fuel, 0.0) + ej

        # Step 3: Clear markets at R10
        trade_results = self.trade.solve_trade(r10_demands)
        if trade_results is None:
            return

        # Store for inter-period updates
        self._last_trade_results = trade_results

        # Step 4: Update world prices on state
        for fuel in TRADED_FUELS:
            carrier = _FUEL_TO_CARRIER.get(fuel)
            if carrier is not None:
                state.world_prices[carrier] = trade_results[fuel].world_price

        # Step 5: Distribute delivered prices to R32 regions
        for r32_name in state.regions:
            rs = state.regions[r32_name]
            r10 = R32_TO_R10.get(r32_name)
            if r10 is None:
                continue
            delivered = self.trade.delivered_prices(trade_results, r10)
            for fuel, price in delivered.items():
                carrier = _FUEL_TO_CARRIER.get(fuel)
                if carrier is not None:
                    rs.raw_fuel_prices[carrier] = price

            # Update net exports and production (proportional to R32 demand share)
            for fuel in TRADED_FUELS:
                carrier = _FUEL_TO_CARRIER.get(fuel)
                if carrier is None:
                    continue
                r10_total_demand = sum(
                    r32_fuel_demands.get(r, {}).get(fuel, 0.0)
                    for r, r10_check in R32_TO_R10.items()
                    if r10_check == r10 and r in state.regions
                )
                r32_demand = r32_fuel_demands.get(r32_name, {}).get(fuel, 0.0)
                share = r32_demand / r10_total_demand if r10_total_demand > 0 else 0.0

                r10_net_exp = trade_results[fuel].net_exports.get(r10, 0.0)
                r10_prod = trade_results[fuel].regional_production.get(r10, 0.0)
                rs.net_exports[carrier] = r10_net_exp * share
                rs.regional_production[carrier] = r10_prod * share
