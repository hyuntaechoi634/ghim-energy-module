"""Enhanced technology classes for OOP model architecture.

Two classes replace the single ghim.energy.technology.Technology:

  SupplyTech  — transformation-side (electricity, hydrogen, heat, biofuel, refining).
                LCOE-based competition.  Explicit carbon costing + CCS + BECCS.
  EndUseTech  — demand-side technology within a Subsector.
                Simple levelized cost from carrier price.  Optional vintage.

Powertrain subclass of EndUseTech adds LCOT for transport.

The original Technology class in ghim.energy.technology is kept unchanged;
existing code continues to use it.  Phase C+ sectors will adopt these classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ghim.core.carrier import TC_TO_TCO2
from ghim.config import (
    capital_recovery_factor,
    HOURS_PER_YEAR,
    GJ_PER_KWH,
    DISCOUNT_RATE,
)


# ===================================================================
# EndUseTech — demand-side
# ===================================================================

@dataclass
class EndUseTech:
    """Demand-side technology choice within a Subsector.

    1:1 carrier mapping.  Phase 1 degenerate case: capex=0, eff=1.0
    makes levelized_cost = carrier_price (equivalent to carrier-level logit).

    Parameters
    ----------
    carrier : str
        Energy carrier consumed (e.g. "electricity", "gas", "h2").
    efficiency : float
        Service output / GJ input.
    capex : float
        Annualized capital cost ($/GJ-capacity/yr).
    lifetime : int
        Equipment lifetime in years.
    fom : float
        Fixed O&M ($/GJ-service/yr).
    name : str
        Technology name.  Defaults to carrier string.
    """

    carrier: str
    efficiency: float = 1.0
    capex: float = 0.0
    lifetime: int = 25
    fom: float = 0.0
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.carrier

    def levelized_cost(self, carrier_price: float) -> float:
        """Cost per GJ of service ($/GJ)."""
        return self.capex + carrier_price / self.efficiency + self.fom


# ===================================================================
# SupplyTech — transformation-side
# ===================================================================

@dataclass
class SupplyTech:
    """Supply-side technology (electricity, hydrogen, heat, biofuel, refining).

    LCOE computed from raw fuel prices + explicit carbon pricing.
    Supports CCS (capture_rate) and BECCS (biogenic_coef).

    Parameters
    ----------
    name : str
        Technology identifier.
    fuel_input : str
        Primary fuel consumed (e.g. "coal", "gas", "wind", "solar").
        Renewables with no fuel input use string keys not in the price
        dict, yielding fuel_cost = 0.
    carrier_output : str
        Energy carrier produced (e.g. "electricity", "h2", "heat").
    efficiency : float
        Output / input ratio.
    capex : float
        Capital cost ($/kW).
    fom : float
        Fixed O&M ($/kW/yr).
    vom : float
        Variable O&M ($/GJ output).
    capacity_factor : float
        Annual average capacity factor (0-1).
    lifetime : int
        Asset lifetime in years.
    carbon_coef : float
        Fossil carbon coefficient (tC/GJ fuel input).
    biogenic_coef : float
        Biogenic carbon coefficient (tC/GJ fuel input, for BECCS).
    capture_rate : float
        CCS capture fraction (0.0-0.95).
    learning_rate : float
        LBD learning rate (0-1).
    base_cumulative : float
        Base-year cumulative deployment (GW).
    """

    name: str
    fuel_input: str
    carrier_output: str
    efficiency: float
    capex: float
    fom: float = 0.0
    vom: float = 0.0
    capacity_factor: float = 1.0
    lifetime: int = 30
    carbon_coef: float = 0.0
    biogenic_coef: float = 0.0
    capture_rate: float = 0.0
    learning_rate: float = 0.0
    base_cumulative: float = 0.0
    floor_cost: float = 0.0         # $/kW minimum capex (set by TechChange)

    def lcoe(
        self,
        raw_fuel_prices: dict[str, float],
        carbon_price: float = 0.0,
        discount_rate: float = DISCOUNT_RATE,
    ) -> float:
        """Levelized cost of energy ($/GJ output).

        Takes *raw* fuel prices (from trade clearing, no carbon tax).
        Carbon cost added explicitly via carbon_coef — CCS capture_rate
        reduces carbon cost.  BECCS credit when biogenic_coef > 0.

        Parameters
        ----------
        raw_fuel_prices : dict
            Fuel prices in $/GJ, keyed by fuel name.
        carbon_price : float
            Carbon price in $/tC.
        discount_rate : float
            Discount rate for capital recovery.
        """
        crf = capital_recovery_factor(discount_rate, self.lifetime)
        annual_output_gj = (
            self.capacity_factor * HOURS_PER_YEAR * GJ_PER_KWH
        )  # GJ/kW/yr

        if annual_output_gj < 1e-10:
            return 1e6  # zero-output technology

        capital_component = self.capex * crf / annual_output_gj
        fom_component = self.fom / annual_output_gj

        fuel_cost = (
            raw_fuel_prices.get(self.fuel_input, 0.0) / self.efficiency
            if self.efficiency > 0 else 0.0
        )

        # Fossil carbon cost (reduced by CCS capture)
        carbon_cost = (
            self.carbon_coef * TC_TO_TCO2
            * (1.0 - self.capture_rate) * carbon_price
            / self.efficiency
        ) if self.efficiency > 0 and self.carbon_coef > 0 else 0.0

        # BECCS credit: captured biogenic carbon → negative emission → revenue
        beccs_credit = (
            self.biogenic_coef * TC_TO_TCO2
            * self.capture_rate * carbon_price
            / self.efficiency
        ) if self.efficiency > 0 and self.biogenic_coef > 0 else 0.0

        return (
            capital_component + fom_component + fuel_cost
            + carbon_cost - beccs_credit + self.vom
        )

    def annual_emissions_mtc(self, fuel_input_ej: float) -> float:
        """Net CO2 emissions in MtC given fuel input in EJ.

        fossil_net  = carbon_coef × (1 − capture_rate) × fuel  (≥ 0)
        biogenic_net = −biogenic_coef × capture_rate × fuel     (≤ 0)
        total = fossil_net + biogenic_net

        Examples (1 EJ fuel input):
          Coal:      0.0257 × 1.0 × 1e3 = 25.7 MtC
          Coal CCS:  0.0257 × 0.1 × 1e3 = 2.57 MtC
          BECCS:     0 − 0.0257 × 0.9 × 1e3 = −23.1 MtC (negative!)
          Biomass:   0 − 0 = 0 (carbon-neutral, no CCS)
        """
        fossil_net = self.carbon_coef * (1.0 - self.capture_rate) * fuel_input_ej
        biogenic_net = -self.biogenic_coef * self.capture_rate * fuel_input_ej
        # tC/GJ × EJ × (1e9 GJ/EJ) / (1e6 tC/MtC) = × 1e3
        return (fossil_net + biogenic_net) * 1e3


# ===================================================================
# Powertrain — transport-specific EndUseTech
# ===================================================================

@dataclass
class Powertrain(EndUseTech):
    """Transport powertrain.  Extends EndUseTech with vehicle-km cost.

    Parameters
    ----------
    annual_service : float
        km driven per year.
    capex_vehicle : float
        Vehicle purchase price ($).
    energy_intensity : float
        Energy consumption (GJ/km).
    """

    annual_service: float = 15000.0
    capex_vehicle: float = 0.0
    energy_intensity: float = 0.002  # GJ/km, ~2 MJ/km (typical BEV)

    def lcot(self, carrier_price: float) -> float:
        """Levelized cost of transport ($/km).

        Parameters
        ----------
        carrier_price : float
            Price of energy carrier ($/GJ).
        """
        fuel_per_gj = (
            carrier_price / self.efficiency if self.efficiency > 0 else 0.0
        )
        fuel_per_km = fuel_per_gj * self.energy_intensity
        capital_per_km = (
            self.capex_vehicle / (self.annual_service * self.lifetime)
            if self.annual_service > 0 and self.lifetime > 0 else 0.0
        )
        fom_per_km = (
            self.fom / self.annual_service if self.annual_service > 0 else 0.0
        )
        return capital_per_km + fuel_per_km + fom_per_km
