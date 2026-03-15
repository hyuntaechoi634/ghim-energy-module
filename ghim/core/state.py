"""Shared mutable state objects for the GHIM solver loop.

PeriodState holds all model state for one period.
RegionState holds all per-region state within that period.

These replace the scattered dicts that were previously passed between
functions.  The solver writes to these objects; sectors read from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ghim.core.carrier import Carrier
from ghim.core.emissions import EmissionResult


@dataclass
class RegionState:
    """Per-region model state for one period.

    Economy fields are set by the Economy class.
    Demand/supply/emissions fields are set by sector classes.
    Price fields are updated by the solver during iteration.
    """

    # ---- Economy ----
    gdp: float = 0.0                        # billion USD PPP
    population: float = 0.0                  # millions
    value_added: float = 0.0                 # VA (billion USD)
    capital_stock: float = 0.0               # K (billion USD)
    investment: float = 0.0                  # I (billion USD/yr)
    tfp: float = 1.0

    # ---- Prices ----
    # Two channels: raw for supply, consumer for demand
    raw_fuel_prices: dict[Carrier, float] = field(default_factory=dict)
    carrier_prices: dict[Carrier, float] = field(default_factory=dict)
    sector_prices: dict[str, float] = field(default_factory=dict)
    composite_energy_price: float = 5.0      # expenditure-weighted $/GJ

    # ---- Demands ----
    final_demand: dict[str, float] = field(default_factory=dict)
    sector_demand: dict[str, dict[str, float]] = field(default_factory=dict)

    # ---- Supply ----
    generation: dict[str, dict[str, float]] = field(default_factory=dict)

    # ---- Trade ----
    net_exports: dict[str, float] = field(default_factory=dict)
    regional_production: dict[str, float] = field(default_factory=dict)

    # ---- Emissions ----
    emissions: float = 0.0                   # MtCO2eq (total)
    emissions_detail: EmissionResult = field(default_factory=EmissionResult)

    # ---- External module outputs ----
    temperature_anomaly: float = 0.0
    precip_anomaly: float = 0.0
    hdd: float = 0.0
    cdd: float = 0.0
    cooling_water_avail: float = float("inf")
    hydro_water_fraction: float = 1.0
    water_energy_demand: float = 0.0
    biomass_supply: list[float] = field(default_factory=list)
    ag_output: float = 0.0

    # ---- Policy tracking (set by F(), read by sectors and reporting) ----
    carbon_price: float = 0.0                # $/tCO2 (current period)
    aeei_factor: float = 1.0                 # cumulative AEEI multiplier
    carbon_revenue: float = 0.0              # billion USD (τ × emissions)
    ag_ghg_cost_per_gj: float = 0.0          # $/GJ surcharge from non-CO₂ GHG pricing

    # ---- Base-year reference values (set at calibration, read-only after) ----
    base_gdp: float = 0.0
    base_energy_ej: float = 0.0
    base_energy_price: float = 5.0
    base_cooling_ej: float = 0.0


@dataclass
class PeriodState:
    """Full model state for one period."""

    period: int = 0
    regions: dict[str, RegionState] = field(default_factory=dict)

    # Global
    world_prices: dict[Carrier, float] = field(default_factory=dict)
    global_emissions: float = 0.0              # GtCO2eq
    global_emissions_detail: EmissionResult = field(default_factory=EmissionResult)

    # Policy (set by F(), read by reporting)
    policy_carbon_price: float = 0.0           # $/tCO2 for this period

    # ------------------------------------------------------------------
    # State vector serialization for Phase 2 Anderson/Newton-Krylov
    #
    # Layout: [per_region × n_regions] + [global]
    #   Per-region (4): gdp, P_electricity, P_gas, P_liquids
    #   Global (5): world_price_coal, world_price_oil, world_price_gas,
    #               global_emissions, policy_carbon_price
    #   Total: 4 × n_regions + 5
    # ------------------------------------------------------------------

    def to_vector(self) -> np.ndarray:
        """Pack solver state into a flat numpy vector."""
        names = sorted(self.regions.keys())
        n = len(names)
        vec = np.empty(4 * n + 5)

        for i, name in enumerate(names):
            rs = self.regions[name]
            base = i * 4
            vec[base] = rs.gdp
            vec[base + 1] = rs.carrier_prices.get(Carrier.ELECTRICITY, 20.0)
            vec[base + 2] = rs.carrier_prices.get(Carrier.GAS, 5.0)
            vec[base + 3] = rs.carrier_prices.get(Carrier.LIQUIDS, 12.0)

        g = 4 * n
        vec[g] = self.world_prices.get(Carrier.COAL, 2.5)
        vec[g + 1] = self.world_prices.get(Carrier.OIL, 8.0)
        vec[g + 2] = self.world_prices.get(Carrier.GAS, 4.0)
        vec[g + 3] = self.global_emissions
        vec[g + 4] = self.policy_carbon_price
        return vec

    def from_vector(self, vec: np.ndarray) -> None:
        """Unpack solver state from a flat numpy vector (in-place)."""
        names = sorted(self.regions.keys())
        n = len(names)

        for i, name in enumerate(names):
            rs = self.regions[name]
            base = i * 4
            rs.gdp = float(vec[base])
            rs.carrier_prices[Carrier.ELECTRICITY] = float(vec[base + 1])
            rs.carrier_prices[Carrier.GAS] = float(vec[base + 2])
            rs.carrier_prices[Carrier.LIQUIDS] = float(vec[base + 3])

        g = 4 * n
        self.world_prices[Carrier.COAL] = float(vec[g])
        self.world_prices[Carrier.OIL] = float(vec[g + 1])
        self.world_prices[Carrier.GAS] = float(vec[g + 2])
        self.global_emissions = float(vec[g + 3])
        self.policy_carbon_price = float(vec[g + 4])

    @property
    def state_dim(self) -> int:
        """Dimensionality of the solver state vector."""
        return 4 * len(self.regions) + 5
