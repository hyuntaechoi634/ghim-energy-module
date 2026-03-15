"""ElectricitySector — 17 SupplyTechs, LCOE logit, vintage stock turnover.

The most important transformation sector.  Uses SupplyTech.lcoe() with
explicit carbon pricing + CCS + BECCS.  Vintage-aware investment with
pipeline delay for nuclear/hydro.

Existing ghim.energy.electricity.ElectricitySector is kept unchanged.
This is the OOP replacement for Phase C+.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ghim.core.carrier import TC_TO_TCO2
from ghim.core.config import BASE_YEAR
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import SupplyTech
from ghim.core.vintage import PipelineAwareVintageTracker, NUCLEAR_PIPELINE_R10
from ghim.energy.logit import relative_pref_logit, preference_calibrate
from ghim.config import (
    ELEC_LOGIT_EXP,
    PREF_LOGIT_SCALE,
    PREF_DECAY_RATES,
    TECH_RETIREMENT_LIFETIMES,
    CONSTRUCTION_TIMES,
    DISCOUNT_RATE,
)
from ghim.sectors.abc import TransformationSector


# ===================================================================
# Default 17 electricity technologies
# ===================================================================

def default_electricity_supply_techs() -> list[SupplyTech]:
    """17 electricity generation SupplyTechs with gcamdata-sourced parameters.

    Sources (all values in $2020):
    - capex, fom, vom: NREL ATB 2022 central case, 2020 base year
      (input/gcamdata/inst/extdata/energy/NREL_ATB_*_2022.csv)
    - efficiency, capacity_factor: GCAM A23 globaltech files
      (input/gcamdata/inst/extdata/energy/A23.globaltech_eff.csv, _capacity_factor.csv)
    - ATB → GCAM mapping: energy/mappings/atb_gcam_mapping.csv
    - CCS/inferred techs: Muratori et al. (2017) cost ratios applied to ATB base techs

    Units: capex $/kW, fom $/kW/yr, vom $/GJ, carbon_coef tC/GJ.
    """
    return [
        # ---- Fossil ----
        # ATB: Coal, Coal (central 2020)
        SupplyTech("coal", "coal", "electricity",
                   efficiency=0.40, capex=2568, fom=74, vom=2.2,
                   capacity_factor=0.85, lifetime=45,
                   carbon_coef=0.0257, base_cumulative=2100.0, learning_rate=0.0),
        # ATB: Coal, Coal-90%-CCS; eff from A23 coal (conv pul CCS) 0.292
        SupplyTech("coal_ccs", "coal", "electricity",
                   efficiency=0.29, capex=4628, fom=125, vom=4.2,
                   capacity_factor=0.80, lifetime=40,
                   carbon_coef=0.0257, capture_rate=0.90,
                   base_cumulative=1.0, learning_rate=0.05),
        # ATB: Natural Gas, NG F-Frame CC; eff from A23 gas (CC) 0.565
        SupplyTech("gas_cc", "gas", "electricity",
                   efficiency=0.56, capex=947, fom=28, vom=0.6,
                   capacity_factor=0.85, lifetime=30,
                   carbon_coef=0.0153, base_cumulative=1800.0, learning_rate=0.0),
        # ATB: NG F-Frame CC 90% CCS; eff from A23 gas (CC CCS) 0.465
        SupplyTech("gas_cc_ccs", "gas", "electricity",
                   efficiency=0.47, capex=2399, fom=67, vom=1.7,
                   capacity_factor=0.80, lifetime=35,
                   carbon_coef=0.0153, capture_rate=0.90,
                   base_cumulative=1.0, learning_rate=0.05),
        # ATB: NG F-Frame CT (proxy for oil); eff from A23 refined liquids (steam/CT)
        SupplyTech("oil", "refined liquids", "electricity",
                   efficiency=0.36, capex=841, fom=21, vom=1.4,
                   capacity_factor=0.80, lifetime=30,
                   carbon_coef=0.0200, base_cumulative=500.0, learning_rate=0.0),
        # ---- Biomass ----
        # ATB: Biopower, Dedicated; eff from A23 biomass (conv) 0.266
        SupplyTech("biomass", "biomass", "electricity",
                   efficiency=0.27, capex=4083, fom=151, vom=1.6,
                   capacity_factor=0.85, lifetime=40,
                   biogenic_coef=0.0257, base_cumulative=150.0, learning_rate=0.05),
        # Muratori ratio: biomass_ccs/biomass ≈ 1.93; eff from A23 biomass (conv CCS) 0.196
        SupplyTech("biomass_ccs", "biomass", "electricity",
                   efficiency=0.20, capex=7860, fom=291, vom=3.1,
                   capacity_factor=0.85, lifetime=40,
                   biogenic_coef=0.0257, capture_rate=0.90,
                   base_cumulative=0.1, learning_rate=0.05),
        # ---- Nuclear ----
        # ATB: Nuclear - AP1000; eff from A23 Gen_III 0.333
        SupplyTech("nuclear", "uranium", "electricity",
                   efficiency=0.33, capex=6343, fom=146, vom=0.8,
                   capacity_factor=0.90, lifetime=60,
                   base_cumulative=440.0, learning_rate=0.03),
        # ---- Hydro ----
        # No ATB equivalent; site-specific (IEA range $1000-5000/kW)
        SupplyTech("hydro", "hydro", "electricity",
                   efficiency=1.0, capex=2500, fom=30, vom=0.1,
                   capacity_factor=0.45, lifetime=80,
                   base_cumulative=1300.0, learning_rate=0.0),
        # ---- Solar ----
        # ATB: Solar - Utility PV, Class 5; CF from A23 PV 0.20
        SupplyTech("solar", "solar", "electricity",
                   efficiency=1.0, capex=1303, fom=23, vom=0.0,
                   capacity_factor=0.20, lifetime=30,
                   base_cumulative=710.0, learning_rate=0.20),
        # ATB: Solar - CSP, Class 3 (w/o storage); CF from A23 CSP 0.25
        SupplyTech("solar_csp", "solar", "electricity",
                   efficiency=1.0, capex=6242, fom=66, vom=1.0,
                   capacity_factor=0.25, lifetime=30,
                   base_cumulative=6.0, learning_rate=0.15),
        # ---- Wind ----
        # ATB: Land-Based Wind, Class 5; CF from A23 wind 0.37
        SupplyTech("wind", "wind", "electricity",
                   efficiency=1.0, capex=1405, fom=43, vom=0.0,
                   capacity_factor=0.37, lifetime=25,
                   base_cumulative=740.0, learning_rate=0.12),
        # ATB: Offshore Wind, Class 4; CF from A23 (not avail, keep 0.40)
        SupplyTech("wind_offshore", "wind", "electricity",
                   efficiency=1.0, capex=2591, fom=113, vom=0.0,
                   capacity_factor=0.40, lifetime=25,
                   base_cumulative=35.0, learning_rate=0.15),
        # ---- Other renewables ----
        # ATB: Geothermal, Hydro/Flash; CF from A23 0.90
        SupplyTech("geothermal", "geothermal", "electricity",
                   efficiency=1.0, capex=4559, fom=107, vom=0.0,
                   capacity_factor=0.90, lifetime=30,
                   base_cumulative=15.0, learning_rate=0.05),
        # No ATB equivalent; nascent technology
        SupplyTech("ocean", "ocean", "electricity",
                   efficiency=1.0, capex=6000, fom=100, vom=0.0,
                   capacity_factor=0.30, lifetime=25,
                   base_cumulative=0.5, learning_rate=0.10),
        # ---- Hydrogen/Ammonia combustion ----
        SupplyTech("h2_turbine", "h2", "electricity",
                   efficiency=0.45, capex=700, fom=12, vom=0.3,
                   capacity_factor=0.30, lifetime=30,
                   base_cumulative=0.1, learning_rate=0.0),
        SupplyTech("ammonia", "h2", "electricity",
                   efficiency=0.35, capex=800, fom=15, vom=0.5,
                   capacity_factor=0.30, lifetime=30,
                   base_cumulative=0.1, learning_rate=0.0),
    ]


# Extended retirement lifetimes for new techs
_ELEC_LIFETIMES: dict[str, float] = {
    **TECH_RETIREMENT_LIFETIMES,
    "coal_ccs": 40.0, "gas_cc_ccs": 35.0, "biomass_ccs": 40.0,
    "solar_csp": 30.0, "wind_offshore": 25.0,
    "geothermal": 30.0, "ocean": 25.0,
    "h2_turbine": 30.0, "ammonia": 30.0,
}

# Hard-cutoff techs (deterministic lifetime, no S-curve)
_HARD_CUTOFF: set[str] = {
    "wind", "wind_offshore", "solar", "solar_csp", "ocean",
}


# ===================================================================
# ElectricitySector
# ===================================================================

class OOPElectricitySector(TransformationSector):
    """17-tech electricity sector with LCOE logit and vintage stock.

    One instance per region.  Uses SupplyTech.lcoe() with carbon pricing.
    """

    carrier_output: str = "electricity"

    def __init__(
        self,
        techs: list[SupplyTech] | None = None,
        region: str | None = None,
        logit_exp: float = ELEC_LOGIT_EXP,
        scale_k: float = PREF_LOGIT_SCALE,
    ) -> None:
        self.techs = techs or default_electricity_supply_techs()
        self.region = region
        self.logit_exp = logit_exp
        self.scale_k = scale_k

        self.pref_factors: np.ndarray | None = None
        self.base_pref_factors: np.ndarray | None = None
        self.last_shares: np.ndarray | None = None
        self.total_generation_ej: float = 0.0
        self.calibration_year: int = BASE_YEAR

        # Vintage stock (initialized in calibrate)
        self.vintage: PipelineAwareVintageTracker | None = None

    @property
    def tech_names(self) -> list[str]:
        return [t.name for t in self.techs]

    # ---- Calibration ----

    def calibrate(
        self,
        base_shares: dict[str, float],
        base_prices: dict[str, float],
        total_generation_ej: float = 0.0,
        gem_vintage_data: dict[str, dict[int, float]] | None = None,
    ) -> None:
        """Calibrate preference factors and initialize vintage stock.

        Parameters
        ----------
        base_shares : dict
            {tech_name: share} at base year.
        base_prices : dict
            Raw fuel prices $/GJ for LCOE computation.
        total_generation_ej : float
            Total electricity generation (EJ) at base year.
        gem_vintage_data : dict, optional
            {tech: {vintage_year: EJ}} from GEM preprocessing.
        """
        self.total_generation_ej = total_generation_ej

        shares_arr = np.array([
            base_shares.get(t.name, 1e-4) for t in self.techs
        ])
        shares_arr = np.maximum(shares_arr, 1e-6)
        shares_arr /= shares_arr.sum()

        # LCOE at base prices (no carbon price)
        costs_arr = np.array([
            t.lcoe(base_prices, carbon_price=0.0) for t in self.techs
        ])

        # Calibrate preference factors
        self.pref_factors = preference_calibrate(
            shares_arr, costs_arr, self.scale_k, logit_exp=self.logit_exp,
        )
        self.base_pref_factors = self.pref_factors.copy()
        self.last_shares = shares_arr.copy()

        # Initialize vintage stock
        names = self.tech_names
        lifetimes = {n: _ELEC_LIFETIMES.get(n, 40.0) for n in names}
        hard_cutoff = _HARD_CUTOFF & set(names)

        # Profit shutdown params from GCAM A23 (median_shutdown_point, steepness)
        _PROFIT_SHUTDOWN = {
            "coal": (-0.1, 6.0),
            "coal_ccs": (-0.1, 6.0),
            "gas_cc": (-0.1, 6.0),
            "gas_cc_ccs": (-0.1, 6.0),
            "oil": (-0.5, 6.0),
            "biomass": (-0.1, 6.0),
            "biomass_ccs": (-0.1, 6.0),
            "nuclear": (-0.1, 6.0),
            "geothermal": (-0.1, 6.0),
            "solar": (-0.1, 6.0),
            "solar_csp": (-0.1, 6.0),
            "wind": (-0.1, 6.0),
            "wind_offshore": (-0.1, 6.0),
            "hydro": (-0.1, 6.0),
            "h2_turbine": (-0.1, 6.0),
            "ammonia": (-0.1, 6.0),
        }
        ps_params = {n: _PROFIT_SHUTDOWN[n] for n in names if n in _PROFIT_SHUTDOWN}

        self.vintage = PipelineAwareVintageTracker(
            tech_names=names,
            lifetimes=lifetimes,
            hard_cutoff_techs=hard_cutoff,
            construction_times=dict(CONSTRUCTION_TIMES),
            profit_shutdown_params=ps_params,
        )

        if gem_vintage_data:
            self.vintage.initialize_from_gem(
                gem_vintage_data, shares_arr, total_generation_ej, BASE_YEAR,
            )
        else:
            self.vintage.initialize_uniform(
                shares_arr, total_generation_ej, BASE_YEAR,
            )

        # Nuclear pipeline from WNA data
        if self.region and self.region in NUCLEAR_PIPELINE_R10:
            uc_data = NUCLEAR_PIPELINE_R10[self.region]
            if uc_data:
                self.vintage.initialize_under_construction({"nuclear": uc_data})

    # ---- Supply computation ----

    def compute_supply(
        self,
        rs: RegionState,
        demand_ej: float,
        policy: Any = None,
    ) -> dict[str, float]:
        """Compute generation by tech.

        1. Compute LCOE (with carbon price from policy)
        2. Relative-pref logit → target shares
        3. Vintage gap-fill: surviving + new investment
        """
        carbon_price = getattr(rs, "carbon_price", 0.0)
        year = getattr(rs, "_year", None) or BASE_YEAR

        # Renewable subsidies from policy (reduce LCOE)
        subsidies = np.zeros(len(self.techs))
        if policy is not None and hasattr(policy, "renewable_subsidies"):
            for i, t in enumerate(self.techs):
                subsidies[i] = policy.renewable_subsidies.get_subsidy(t.name, year)

        # Compute LCOE for each tech
        lcoe = np.array([
            t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price)
            for t in self.techs
        ]) - subsidies
        lcoe = np.maximum(lcoe, 0.01)  # floor at near-zero

        # Preference factors with decay
        pf = self._compute_pref_factors(year)

        # Logit → target shares
        target_shares = relative_pref_logit(
            lcoe, pf, self.scale_k, self.logit_exp,
        )

        # Variable cost per tech (for profit shutdown):
        # fuel/eff + VOM + FOM/GJ + pref_cost (unobservable cost)
        # FOM is NOT sunk — real ongoing cost for keeping plant open.
        # Logit exponent: exp(β × C/k + P) → pref_cost = P×k/β ($/GJ)
        pref_cost_factor = self.scale_k / self.logit_exp if self.logit_exp != 0 else 0.0
        var_costs = np.array([
            (rs.raw_fuel_prices.get(t.fuel_input, 0.0) / t.efficiency
             if t.efficiency > 0 else 0.0)
            + t.vom
            + (t.fom / (t.capacity_factor * 8760 * 3.6e-3)
               if t.capacity_factor > 0 else 0.0)
            + (pf[i] * pref_cost_factor if pf is not None else 0.0)
            for i, t in enumerate(self.techs)
        ])
        var_costs = np.maximum(var_costs, 0.01)

        # Market price = share-weighted LCOE (current period)
        mkt_price = float(np.dot(target_shares, lcoe))

        # Vintage stock turnover (with profit shutdown)
        if self.vintage is not None:
            effective_shares = self.vintage.retire_and_invest(
                year, target_shares, demand_ej,
                tech_var_costs=var_costs,
                market_price=mkt_price,
            )
        else:
            effective_shares = target_shares

        self.last_shares = effective_shares
        self.total_generation_ej = demand_ej

        return {
            t.name: float(s * demand_ej)
            for t, s in zip(self.techs, effective_shares)
        }

    def compute_price(self, rs: RegionState) -> float:
        """Share-weighted LCOE ($/GJ), carbon-inclusive."""
        if self.last_shares is None:
            return 20.0  # fallback

        carbon_price = getattr(rs, "carbon_price", 0.0)
        lcoe = np.array([
            t.lcoe(rs.raw_fuel_prices, carbon_price=carbon_price)
            for t in self.techs
        ])
        return float(np.dot(self.last_shares, lcoe))

    def compute_emissions(
        self, generation: dict[str, float],
    ) -> EmissionResult:
        """Supply-side CO2 emissions from electricity generation."""
        tech_map = {t.name: t for t in self.techs}
        total_co2_mtc = 0.0
        for name, gen_ej in generation.items():
            tech = tech_map.get(name)
            if tech is None or gen_ej <= 0:
                continue
            # Fuel input = gen / efficiency
            fuel_ej = gen_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            total_co2_mtc += tech.annual_emissions_mtc(fuel_ej)
        # Convert MtC → MtCO2
        return EmissionResult(co2=total_co2_mtc * TC_TO_TCO2)

    def fuel_consumption(
        self, generation: dict[str, float],
    ) -> dict[str, float]:
        """Fuel input requirements by fuel type (EJ)."""
        tech_map = {t.name: t for t in self.techs}
        consumption: dict[str, float] = {}
        for name, gen_ej in generation.items():
            tech = tech_map.get(name)
            if tech is None or gen_ej <= 0:
                continue
            fuel_ej = gen_ej / tech.efficiency if tech.efficiency > 0 else 0.0
            consumption[tech.fuel_input] = (
                consumption.get(tech.fuel_input, 0.0) + fuel_ej
            )
        return consumption

    # ---- Internal helpers ----

    def _compute_pref_factors(self, year: int) -> np.ndarray:
        """Preference factors with per-tech decay."""
        if self.base_pref_factors is None:
            return np.zeros(len(self.techs))
        elapsed = max(year - self.calibration_year, 0)
        pf = np.empty(len(self.techs))
        for i, t in enumerate(self.techs):
            rate = PREF_DECAY_RATES.get(t.name, 0.0)
            pf[i] = self.base_pref_factors[i] * (1.0 - rate) ** elapsed
        return pf
