"""Energy carrier enum and carbon-related constants.

Carrier is an identity-only enum: no state, no behavior.  Dynamic properties
(price, demand, supply) live in RegionState, not in the carrier itself.
Every module that needs carrier identity imports this single definition,
preventing typo-based silent bugs.
"""

from __future__ import annotations

from enum import Enum


class Carrier(str, Enum):
    """Energy carrier identifier."""

    ELECTRICITY = "electricity"
    GAS = "gas"
    COAL = "coal"
    LIQUIDS = "liquids"       # refined liquid fuels (post-refining)
    BIOMASS = "biomass"
    BIOFUEL = "biofuel"
    H2 = "h2"
    HEAT = "heat"             # district heat
    OIL = "oil"               # primary crude oil (pre-refining)
    URANIUM = "uranium"       # primary


# Commonly-used carrier groups
CARRIERS_7: list[Carrier] = [
    Carrier.ELECTRICITY, Carrier.GAS, Carrier.COAL, Carrier.LIQUIDS,
    Carrier.BIOMASS, Carrier.BIOFUEL, Carrier.H2,
]
CARRIERS_8: list[Carrier] = CARRIERS_7 + [Carrier.HEAT]

# ---------------------------------------------------------------------------
# Carbon coefficients: direct combustion at demand side (tC / GJ of fuel)
# Source: IPCC 2006 Guidelines, Vol. 2, Ch. 2
# ---------------------------------------------------------------------------
CARBON_COEFS: dict[Carrier, float] = {
    Carrier.COAL:        0.0257,   # ~94.6 kgCO2/GJ
    Carrier.GAS:         0.0153,   # ~56.1 kgCO2/GJ
    Carrier.LIQUIDS:     0.0200,   # ~73.3 kgCO2/GJ (combustion by end user)
    Carrier.OIL:         0.0,      # carbon stays in product until refined and burned
    Carrier.BIOMASS:     0.0,      # carbon-neutral (biogenic)
    Carrier.BIOFUEL:     0.0,      # carbon-neutral
    Carrier.ELECTRICITY: 0.0,      # indirect (counted at generation via SupplyTech)
    Carrier.H2:          0.0,      # indirect (counted at production via SupplyTech)
    Carrier.HEAT:        0.0,      # indirect (counted at generation via SupplyTech)
    Carrier.URANIUM:     0.0,
}

# ---------------------------------------------------------------------------
# Fugitive CH4 from fossil fuel production (tCH4 / EJ produced)
# Source: EDGAR v8.0
# ---------------------------------------------------------------------------
CH4_FUGITIVE: dict[Carrier, float] = {
    Carrier.COAL: 0.37e6,   # coal mining
    Carrier.OIL:  0.12e6,   # oil production + processing
    Carrier.GAS:  0.22e6,   # gas production + processing + T&D
}

# ---------------------------------------------------------------------------
# GWP100 values (AR6, Forster et al. 2021, Table 7.15)
# ---------------------------------------------------------------------------
GWP100: dict[str, float] = {
    "ch4": 27.9,
    "n2o": 273.0,
    "hfc": 1530.0,
}

# Stoichiometric conversion: tonnes carbon -> tonnes CO2
TC_TO_TCO2: float = 44.0 / 12.0

# ---------------------------------------------------------------------------
# LULUCF anthropogenic emissions (exogenous, Phase 1)
# Source: EDGAR 2025 GHG Booklet, LULUCF_countries sheet, 2021 values
#         Aggregated to GCAM R32 via iso_GCAM_regID.csv
#
# Positive = net emission (deforestation)
# Negative = net absorption (managed forest regrowth)
# Global net ~ -0.35 GtCO2 (anthropogenic LULUCF roughly balanced)
#
# IMPORTANT: Anthropogenic component only.  Does NOT include natural sinks
# (ocean absorption, CO2 fertilization).  Natural sinks are irrelevant for
# UNFCCC Net-Zero accounting.
# Phase 2+: replaced by AFOLU module (dynamic land-use change).
# ---------------------------------------------------------------------------
LULUCF_NET_CO2: dict[str, float] = {
    # GtCO2/yr, 2021, EDGAR v8.0
    "USA":                              -0.41,
    "Africa_Eastern":                    0.64,
    "Africa_Northern":                   0.04,
    "Africa_Southern":                   0.15,
    "Africa_Western":                   -0.27,
    "Australia_NZ":                     -0.04,
    "Brazil":                            0.42,
    "Canada":                           -0.15,
    "Central America and Caribbean":    -0.26,
    "Central Asia":                     -0.08,
    "China":                            -0.85,
    "EU-12":                            -0.04,
    "EU-15":                            -0.09,
    "Ukraine":                          -0.01,
    "Europe_Non_EU":                    -0.07,
    "European Free Trade Association":  -0.02,
    "India":                             0.74,
    "Indonesia":                         1.24,
    "Japan":                            -0.24,
    "Mexico":                           -0.23,
    "Middle East":                       0.00,
    "Pakistan":                          0.05,
    "Russia":                           -1.57,
    "South Africa":                      0.15,
    "South America_Northern":           -0.15,
    "South America_Southern":            0.05,
    "South Asia":                        0.25,
    "South Korea":                      -0.03,
    "Southeast Asia":                    0.59,
    "Taiwan":                           -0.01,
    "Argentina":                        -0.04,
    "Colombia":                         -0.11,
}
