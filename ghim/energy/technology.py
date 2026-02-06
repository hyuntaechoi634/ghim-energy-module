"""Technology definitions for the energy sector model."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ghim.config import (
    capital_recovery_factor, HOURS_PER_YEAR, DISCOUNT_RATE,
    LEARNING_RATES, COST_FLOOR_FRACTION,
)


@dataclass
class Technology:
    """A single energy conversion technology.

    Costs are in $/GJ-output unless otherwise noted.
    """

    name: str
    sector: str              # "electricity", "refining", "hydrogen"
    fuel_input: str          # primary fuel consumed (e.g. "coal", "gas", "wind")
    efficiency: float        # output / input ratio (0-1 for thermal, >1 possible for renewables using convention)
    capital_cost: float      # $/kW capacity
    om_fixed: float          # $/kW/yr
    om_variable: float       # $/GJ output
    capacity_factor: float   # 0-1, annual average
    lifetime: int            # years
    share_weight: float = 1.0  # calibrated logit weight (legacy, kept for compat)
    carbon_coef: float = 0.0   # tC/GJ of fuel input

    # Learning-by-doing fields
    base_capital_cost: float = 0.0      # initial capital cost (frozen at model init)
    base_cumulative: float = 1.0        # initial cumulative capacity (GW or EJ)
    cumulative_capacity: float = 0.0    # current cumulative deployed capacity
    learning_rate: float = 0.0          # 0-1, fraction cost reduction per doubling
    cost_floor: float = 0.0             # minimum capital cost ($/kW)

    def __post_init__(self):
        # Initialize learning fields if not set
        if self.base_capital_cost == 0.0:
            self.base_capital_cost = self.capital_cost
        if self.learning_rate == 0.0:
            self.learning_rate = LEARNING_RATES.get(self.name, 0.0)
        if self.cost_floor == 0.0:
            self.cost_floor = self.base_capital_cost * COST_FLOOR_FRACTION

    def levelized_cost(self, fuel_price: float, discount_rate: float = DISCOUNT_RATE) -> float:
        """Compute levelized cost of energy in $/GJ output.

        LCOE = (capex * CRF) / (CF * 8760 * 3.6e-6) + OM_fixed/(CF*8760*3.6e-6)
               + fuel_price/efficiency + OM_variable

        Note: Capital and fixed OM are in $/kW, output is in GJ.
        1 kW * 8760 h/yr * 3600 s/h * 1e-9 GJ/J = 0.031536 GJ/yr per kW at CF=1.
        """
        crf = capital_recovery_factor(discount_rate, self.lifetime)
        annual_output_gj_per_kw = self.capacity_factor * HOURS_PER_YEAR * 3.6e-3  # GJ/yr per kW

        if annual_output_gj_per_kw < 1e-10:
            return 1e6  # infinite cost for zero-output technology

        capital_component = self.capital_cost * crf / annual_output_gj_per_kw
        fixed_om_component = self.om_fixed / annual_output_gj_per_kw
        fuel_component = fuel_price / self.efficiency if self.efficiency > 0 else 0.0

        return capital_component + fixed_om_component + fuel_component + self.om_variable

    def annual_emissions_tc(self, output_ej: float) -> float:
        """Compute annual CO2 emissions in MtC given output in EJ."""
        # input = output / efficiency (in EJ)
        if self.efficiency <= 0:
            return 0.0
        input_ej = output_ej / self.efficiency
        # carbon_coef is tC/GJ, input_ej * 1e9 = GJ
        return self.carbon_coef * input_ej * 1e9 / 1e6  # MtC

    def update_learning(self, new_capacity: float) -> None:
        """Update cumulative deployment and reduce capital cost via learning curve.

        Cost(t) = Cost_0 * (Q_cum / Q_0)^(-learn_exp)
        learn_exp = ln(1 - LR) / ln(2)
        """
        if self.learning_rate <= 0 or self.base_cumulative <= 0:
            return
        self.cumulative_capacity += new_capacity
        if self.cumulative_capacity <= self.base_cumulative:
            return
        learn_exp = math.log(1.0 - self.learning_rate) / math.log(2.0)
        ratio = self.cumulative_capacity / self.base_cumulative
        self.capital_cost = max(
            self.base_capital_cost * ratio ** learn_exp,
            self.cost_floor,
        )


# ---------------------------------------------------------------------------
# Default technology parameters
# Sources: NREL ATB 2023, IEA WEO 2023, GCAM defaults
# ---------------------------------------------------------------------------

def default_electricity_techs() -> list[Technology]:
    """Return default electricity generation technologies."""
    return [
        Technology("coal", "electricity", "coal",
                   efficiency=0.39, capital_cost=1500, om_fixed=40,
                   om_variable=0.5, capacity_factor=0.75, lifetime=40,
                   carbon_coef=0.0257,
                   base_cumulative=2100.0),  # ~2100 GW global
        Technology("gas_cc", "electricity", "gas",
                   efficiency=0.55, capital_cost=900, om_fixed=12,
                   om_variable=0.3, capacity_factor=0.60, lifetime=30,
                   carbon_coef=0.0153,
                   base_cumulative=1800.0),
        Technology("nuclear", "electricity", "nuclear",
                   efficiency=0.33, capital_cost=5500, om_fixed=100,
                   om_variable=0.5, capacity_factor=0.90, lifetime=60,
                   carbon_coef=0.0,
                   base_cumulative=440.0),
        Technology("hydro", "electricity", "hydro",
                   efficiency=1.0, capital_cost=2500, om_fixed=30,
                   om_variable=0.1, capacity_factor=0.45, lifetime=80,
                   carbon_coef=0.0,
                   base_cumulative=1300.0),
        Technology("wind", "electricity", "wind",
                   efficiency=1.0, capital_cost=1200, om_fixed=25,
                   om_variable=0.0, capacity_factor=0.35, lifetime=25,
                   carbon_coef=0.0,
                   base_cumulative=740.0),   # ~740 GW global 2020
        Technology("solar", "electricity", "solar",
                   efficiency=1.0, capital_cost=900, om_fixed=12,
                   om_variable=0.0, capacity_factor=0.22, lifetime=30,
                   carbon_coef=0.0,
                   base_cumulative=710.0),   # ~710 GW global 2020
        Technology("biomass", "electricity", "biomass",
                   efficiency=0.35, capital_cost=2500, om_fixed=50,
                   om_variable=0.5, capacity_factor=0.70, lifetime=30,
                   carbon_coef=0.0,
                   base_cumulative=150.0),
        Technology("oil", "electricity", "refined liquids",
                   efficiency=0.37, capital_cost=800, om_fixed=15,
                   om_variable=0.8, capacity_factor=0.30, lifetime=30,
                   carbon_coef=0.0200,
                   base_cumulative=500.0),
    ]


def default_refining_techs() -> list[Technology]:
    """Return default refining technologies."""
    return [
        Technology("oil_refining", "refining", "oil",
                   efficiency=0.90, capital_cost=500, om_fixed=15,
                   om_variable=0.2, capacity_factor=0.85, lifetime=40,
                   carbon_coef=0.0200),
    ]


def default_hydrogen_techs() -> list[Technology]:
    """Return default hydrogen production technologies."""
    return [
        Technology("smr", "hydrogen", "gas",
                   efficiency=0.72, capital_cost=600, om_fixed=20,
                   om_variable=0.3, capacity_factor=0.90, lifetime=25,
                   carbon_coef=0.0153,
                   base_cumulative=100.0),
        Technology("electrolysis", "hydrogen", "electricity",
                   efficiency=0.70, capital_cost=1000, om_fixed=25,
                   om_variable=0.1, capacity_factor=0.50, lifetime=20,
                   carbon_coef=0.0,
                   base_cumulative=1.0),  # very small base → fast learning
    ]
