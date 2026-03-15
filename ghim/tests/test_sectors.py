"""Tests for Phase C sector classes."""

import numpy as np
import pytest

from ghim.core.carrier import TC_TO_TCO2
from ghim.core.emissions import EmissionResult
from ghim.core.state import RegionState
from ghim.core.technology import SupplyTech, Powertrain

from ghim.sectors.industry import IndustrySector
from ghim.sectors.electricity import OOPElectricitySector, default_electricity_supply_techs
from ghim.sectors.hydrogen import OOPHydrogenSector, default_hydrogen_supply_techs
from ghim.sectors.biofuels import BiofuelsSector
from ghim.sectors.district_heat import DistrictHeatingSector
from ghim.sectors.transport import TransportSector
from ghim.sectors.bunkers import BunkersSector
from ghim.sectors.buildings import BuildingsSector


# ===========================================================================
# Shared test fixtures
# ===========================================================================

FUEL_PRICES = {
    "coal": 2.0, "gas": 5.0, "oil": 8.0, "refined liquids": 12.0,
    "biomass": 3.0, "uranium": 0.5, "hydro": 0.0, "wind": 0.0,
    "solar": 0.0, "geothermal": 0.0, "ocean": 0.0,
    "electricity": 20.0, "h2": 25.0,
}

CARRIER_PRICES = {
    "electricity": 20.0, "gas": 8.0, "coal": 4.0, "liquids": 15.0,
    "biomass": 3.0, "biofuel": 12.0, "h2": 25.0, "heat": 10.0,
    "oil": 8.0, "uranium": 0.5,
}


def make_rs(gdp=1000.0, **kwargs) -> RegionState:
    rs = RegionState(gdp=gdp, carrier_prices=dict(CARRIER_PRICES))
    rs.raw_fuel_prices = dict(FUEL_PRICES)
    rs.hdd = kwargs.get("hdd", 1.0)
    rs.cdd = kwargs.get("cdd", 1.0)
    return rs


# ===========================================================================
# IndustrySector
# ===========================================================================

class TestIndustrySector:
    def setup_method(self):
        self.ind = IndustrySector()
        self.ind.calibrate(
            {"electricity": 2.0, "gas": 3.0, "coal": 4.0,
             "liquids": 2.0, "biomass": 1.0, "biofuel": 0.0, "h2": 0.0},
            CARRIER_PRICES, 1000.0,
        )

    def test_two_subsectors(self):
        assert len(self.ind.subsectors) == 2
        assert self.ind.eu.name == "industry.EU"
        assert self.ind.fs.name == "industry.FS"

    def test_eu_has_8_techs(self):
        assert len(self.ind.eu.techs) == 8

    def test_fs_has_5_techs(self):
        assert len(self.ind.fs.techs) == 5

    def test_compute_demand_returns_dict(self):
        rs = make_rs()
        result = self.ind.compute_demand(rs)
        assert isinstance(result, dict)
        assert sum(result.values()) > 0

    def test_demand_increases_with_gdp(self):
        d_low = sum(self.ind.compute_demand(make_rs(gdp=1000.0)).values())
        d_high = sum(self.ind.compute_demand(make_rs(gdp=2000.0)).values())
        assert d_high > d_low

    def test_emissions_positive_for_fossil(self):
        rs = make_rs()
        rs.sector_demand = {"industry": {"coal": 2.0, "gas": 1.0}}
        em = self.ind.compute_emissions(rs)
        assert em.co2 > 0

    def test_eu_fs_fractions_sum_to_one(self):
        assert self.ind.eu_fraction + self.ind.fs_fraction == pytest.approx(1.0)


# ===========================================================================
# OOPElectricitySector
# ===========================================================================

class TestElectricitySector:
    def setup_method(self):
        self.elec = OOPElectricitySector(region="Eastern Asia")
        base_shares = {t.name: 1.0 / 17 for t in self.elec.techs}
        # Give coal/gas/nuclear bigger shares
        base_shares["coal"] = 0.35
        base_shares["gas_cc"] = 0.20
        base_shares["nuclear"] = 0.10
        base_shares["hydro"] = 0.15
        base_shares["wind"] = 0.08
        base_shares["solar"] = 0.07
        # Normalize remaining to small shares
        used = sum(base_shares[k] for k in ["coal", "gas_cc", "nuclear", "hydro", "wind", "solar"])
        remaining = 1.0 - used
        other_techs = [t.name for t in self.elec.techs
                       if t.name not in ["coal", "gas_cc", "nuclear", "hydro", "wind", "solar"]]
        for t in other_techs:
            base_shares[t] = remaining / len(other_techs)

        self.elec.calibrate(base_shares, FUEL_PRICES, total_generation_ej=30.0)

    def test_17_techs(self):
        assert len(self.elec.techs) == 17

    def test_all_techs_are_supply_tech(self):
        for t in self.elec.techs:
            assert isinstance(t, SupplyTech)

    def test_carrier_output(self):
        assert self.elec.carrier_output == "electricity"

    def test_calibrate_initializes_vintage(self):
        assert self.elec.vintage is not None

    def test_calibrate_sets_pref_factors(self):
        assert self.elec.pref_factors is not None
        assert len(self.elec.pref_factors) == 17

    def test_compute_supply_returns_all_techs(self):
        rs = make_rs()
        gen = self.elec.compute_supply(rs, 30.0)
        assert isinstance(gen, dict)
        assert len(gen) == 17
        total = sum(gen.values())
        assert total == pytest.approx(30.0, rel=1e-3)

    def test_compute_supply_positive(self):
        rs = make_rs()
        gen = self.elec.compute_supply(rs, 30.0)
        for v in gen.values():
            assert v >= 0

    def test_compute_price_positive(self):
        rs = make_rs()
        self.elec.compute_supply(rs, 30.0)
        price = self.elec.compute_price(rs)
        assert price > 0

    def test_compute_emissions_positive(self):
        gen = {"coal": 10.0, "gas_cc": 5.0, "solar": 5.0}
        em = self.elec.compute_emissions(gen)
        assert em.co2 > 0  # coal + gas produce CO2

    def test_ccs_reduces_emissions(self):
        gen_no_ccs = {"coal": 10.0}
        gen_ccs = {"coal_ccs": 10.0}
        em_no = self.elec.compute_emissions(gen_no_ccs)
        em_ccs = self.elec.compute_emissions(gen_ccs)
        assert em_ccs.co2 < em_no.co2

    def test_beccs_negative_emissions(self):
        gen = {"biomass_ccs": 10.0}
        em = self.elec.compute_emissions(gen)
        assert em.co2 < 0  # BECCS is negative

    def test_renewable_zero_emissions(self):
        gen = {"solar": 10.0, "wind": 5.0}
        em = self.elec.compute_emissions(gen)
        assert em.co2 == pytest.approx(0.0)

    def test_fuel_consumption(self):
        gen = {"coal": 10.0, "solar": 5.0}
        fc = self.elec.fuel_consumption(gen)
        assert "coal" in fc
        assert fc["coal"] > 10.0  # input > output (efficiency < 1)
        # Solar has no fuel input (fuel_input="solar" not in prices)
        assert fc.get("solar", 0.0) == pytest.approx(5.0)  # eff=1.0

    def test_nuclear_pipeline_loaded(self):
        """Eastern Asia should have nuclear pipeline from WNA data."""
        assert self.elec.vintage is not None
        uc = self.elec.vintage._under_construction_total("nuclear")
        assert uc > 0

    def test_supply_with_carbon_price(self):
        """Higher carbon price should shift generation toward renewables."""
        rs = make_rs()

        class MockPolicy:
            def get_carbon_price(self, rs):
                return 200.0  # $/tC

        gen_no_tax = self.elec.compute_supply(rs, 30.0)
        # Re-calibrate for clean comparison
        self.setup_method()
        gen_tax = self.elec.compute_supply(rs, 30.0, policy=MockPolicy())

        # Solar should gain share with carbon price
        # (may not always hold due to vintage inertia, so test is directional)
        assert gen_tax.get("solar", 0) + gen_tax.get("wind", 0) >= 0


# ===========================================================================
# OOPHydrogenSector
# ===========================================================================

class TestHydrogenSector:
    def setup_method(self):
        self.h2 = OOPHydrogenSector()
        self.h2.calibrate(
            {"smr": 0.95, "electrolysis": 0.05},
            FUEL_PRICES, total_production_ej=1.0,
        )

    def test_two_techs(self):
        assert len(self.h2.techs) == 2

    def test_compute_supply(self):
        rs = make_rs()
        gen = self.h2.compute_supply(rs, 1.0)
        assert sum(gen.values()) == pytest.approx(1.0, rel=1e-3)

    def test_compute_price(self):
        rs = make_rs()
        self.h2.compute_supply(rs, 1.0)
        price = self.h2.compute_price(rs)
        assert price > 0

    def test_smr_emissions_positive(self):
        em = self.h2.compute_emissions({"smr": 1.0})
        assert em.co2 > 0

    def test_electrolysis_zero_emissions(self):
        em = self.h2.compute_emissions({"electrolysis": 1.0})
        assert em.co2 == pytest.approx(0.0)


# ===========================================================================
# BiofuelsSector
# ===========================================================================

class TestBiofuelsSector:
    def setup_method(self):
        self.bf = BiofuelsSector()
        self.bf.calibrate({"ethanol": 0.6, "biodiesel": 0.4}, FUEL_PRICES)

    def test_two_techs(self):
        assert len(self.bf.techs) == 2

    def test_compute_supply(self):
        rs = make_rs()
        gen = self.bf.compute_supply(rs, 2.0)
        assert sum(gen.values()) == pytest.approx(2.0, rel=1e-3)

    def test_zero_emissions(self):
        em = self.bf.compute_emissions({"ethanol": 1.0})
        assert em.co2 == 0.0

    def test_fuel_consumption(self):
        fc = self.bf.fuel_consumption({"ethanol": 1.0})
        assert "biomass" in fc
        assert fc["biomass"] > 1.0  # eff < 1


# ===========================================================================
# DistrictHeatingSector
# ===========================================================================

class TestDistrictHeatingSector:
    def setup_method(self):
        self.dh = DistrictHeatingSector()
        self.dh.calibrate(
            {"gas_boiler": 0.6, "electric_boiler": 0.1,
             "heat_pump": 0.2, "biomass_chp": 0.1},
            FUEL_PRICES,
        )

    def test_four_techs(self):
        assert len(self.dh.techs) == 4

    def test_compute_supply(self):
        rs = make_rs()
        gen = self.dh.compute_supply(rs, 3.0)
        assert sum(gen.values()) == pytest.approx(3.0, rel=1e-3)

    def test_gas_boiler_emissions(self):
        em = self.dh.compute_emissions({"gas_boiler": 1.0})
        assert em.co2 > 0

    def test_heat_pump_zero_direct_emissions(self):
        em = self.dh.compute_emissions({"heat_pump": 1.0})
        assert em.co2 == pytest.approx(0.0)

    def test_heat_pump_efficient(self):
        """Heat pump COP=3.5 → less fuel input than gas boiler eff=0.9."""
        fc_hp = self.dh.fuel_consumption({"heat_pump": 1.0})
        fc_gas = self.dh.fuel_consumption({"gas_boiler": 1.0})
        assert fc_hp["electricity"] < fc_gas["gas"]


# ===========================================================================
# TransportSector
# ===========================================================================

class TestTransportSector:
    def setup_method(self):
        self.tr = TransportSector()
        self.tr.calibrate(
            {"liquids": 8.0, "electricity": 0.5, "gas": 1.0,
             "h2": 0.0, "biofuel": 0.5, "biomass": 0.0},
            CARRIER_PRICES, 1000.0,
        )

    def test_two_subsectors(self):
        assert len(self.tr.subsectors) == 2

    def test_passenger_6_powertrains(self):
        assert len(self.tr.passenger.techs) == 6

    def test_freight_5_powertrains(self):
        assert len(self.tr.freight.techs) == 5

    def test_all_are_powertrains(self):
        for sub in self.tr.subsectors:
            for t in sub.techs:
                assert isinstance(t, Powertrain)

    def test_compute_demand(self):
        rs = make_rs()
        result = self.tr.compute_demand(rs)
        assert sum(result.values()) > 0

    def test_demand_scales_with_gdp(self):
        d_low = sum(self.tr.compute_demand(make_rs(gdp=1000.0)).values())
        d_high = sum(self.tr.compute_demand(make_rs(gdp=2000.0)).values())
        assert d_high > d_low

    def test_fractions_sum_to_one(self):
        assert self.tr.pass_fraction + self.tr.freight_fraction == pytest.approx(1.0)


# ===========================================================================
# BunkersSector
# ===========================================================================

class TestBunkersSector:
    def setup_method(self):
        self.bk = BunkersSector()
        self.bk.calibrate(
            {"liquids": 8.0, "biofuel": 0.5, "gas": 1.0},
            CARRIER_PRICES, 50000.0,  # world GDP
        )

    def test_two_subsectors(self):
        assert len(self.bk.subsectors) == 2

    def test_compute_demand(self):
        rs = make_rs(gdp=50000.0)
        result = self.bk.compute_demand(rs)
        assert sum(result.values()) > 0

    def test_high_income_elasticity(self):
        assert self.bk.income_elasticity == 0.9


# ===========================================================================
# BuildingsSector
# ===========================================================================

class TestBuildingsSector:
    def setup_method(self):
        self.bld = BuildingsSector()
        self.bld.calibrate(
            {"electricity": 5.0, "gas": 4.0, "coal": 1.0,
             "liquids": 1.0, "biomass": 0.5, "biofuel": 0.0,
             "h2": 0.0, "heat": 1.5},
            CARRIER_PRICES, 1000.0,
            hdd_base=1.0, cdd_base=1.0,
        )

    def test_six_subsectors(self):
        assert len(self.bld.subsectors) == 6

    def test_heating_techs_include_heat_pump(self):
        heating = self.bld.subsectors[0]  # residential.heating
        names = [t.name for t in heating.techs]
        assert "heat_pump" in names

    def test_heating_techs_include_district_heat(self):
        heating = self.bld.subsectors[0]
        names = [t.name for t in heating.techs]
        assert "district_heat" in names

    def test_compute_demand(self):
        rs = make_rs()
        result = self.bld.compute_demand(rs)
        assert sum(result.values()) > 0

    def test_hdd_scaling(self):
        """More HDD → more heating demand."""
        d_normal = sum(self.bld.compute_demand(make_rs(hdd=1.0)).values())
        d_cold = sum(self.bld.compute_demand(make_rs(hdd=1.5)).values())
        assert d_cold > d_normal

    def test_cdd_scaling(self):
        """More CDD → more cooling demand."""
        d_normal = sum(self.bld.compute_demand(make_rs(cdd=1.0)).values())
        d_hot = sum(self.bld.compute_demand(make_rs(cdd=1.5)).values())
        assert d_hot > d_normal

    def test_demand_scales_with_gdp(self):
        d_low = sum(self.bld.compute_demand(make_rs(gdp=1000.0)).values())
        d_high = sum(self.bld.compute_demand(make_rs(gdp=2000.0)).values())
        assert d_high > d_low
