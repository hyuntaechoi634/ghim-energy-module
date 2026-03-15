"""Tests for GCAM calibration pipeline.

Tests data loading, unit conversion, share normalization,
CalibrationDataset construction, and Calibrator interface compliance.
"""

from __future__ import annotations

import pytest

from ghim.data.gcam_cal import (
    gcam_available,
    gcam_years,
    get_gcam_gdp,
    get_gcam_population,
    get_gcam_capital_stock,
    get_gcam_factor_shares,
    get_gcam_elec_shares,
    get_gcam_total_final_energy,
    get_gcam_sector_totals,
    get_gcam_fe_carrier_shares,
    get_gcam_sector_carrier_shares,
    load_gcam_calibration,
    GDP_1990_TO_2010,
    GCAM_FUEL_TO_GHIM,
    GCAM_ELEC_TECH_TO_GHIM,
    _classify_gcam_sector,
)
from ghim.calibration import CalibrationDataset, Calibrator
from ghim.regions_r32 import R32_REGIONS


pytestmark = pytest.mark.skipif(
    not gcam_available(),
    reason="GCAM reference parquet files not present",
)


# ---------------------------------------------------------------------------
# Data availability
# ---------------------------------------------------------------------------

class TestDataAvailability:
    def test_gcam_available(self):
        assert gcam_available()

    def test_gcam_years_nonempty(self):
        years = gcam_years()
        assert len(years) > 0
        assert 2005 in years
        assert 2050 in years
        assert 2100 in years

    def test_gcam_years_include_historical(self):
        years = gcam_years()
        assert 1975 in years
        assert 1990 in years

    def test_all_r32_regions_have_data(self):
        for region in R32_REGIONS:
            gdp = get_gcam_gdp(2021, region)
            assert gdp > 0, f"{region} has no GDP data at 2021"


# ---------------------------------------------------------------------------
# Mapping dicts
# ---------------------------------------------------------------------------

class TestMappings:
    def test_fuel_mapping_covers_common_fuels(self):
        ghim_carriers = set(GCAM_FUEL_TO_GHIM.values())
        for c in ("coal", "gas", "liquids", "electricity", "biomass", "h2", "heat"):
            assert c in ghim_carriers

    def test_elec_tech_mapping_covers_major_techs(self):
        ghim_techs = set(GCAM_ELEC_TECH_TO_GHIM.values())
        for t in ("coal", "gas_cc", "nuclear", "hydro", "solar", "wind"):
            assert t in ghim_techs

    def test_sector_classification(self):
        assert _classify_gcam_sector("resid heating modern_d1") == "buildings"
        assert _classify_gcam_sector("comm cooling") == "buildings"
        assert _classify_gcam_sector("trn_pass_road") == "transport"
        assert _classify_gcam_sector("iron and steel") == "industry"
        assert _classify_gcam_sector("cement") == "industry"
        assert _classify_gcam_sector("agricultural energy use") == "agriculture"
        assert _classify_gcam_sector("municipal water treatment") is None
        assert _classify_gcam_sector("desalinated water") is None


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

class TestUnitConversion:
    def test_gdp_conversion_factor(self):
        # BEA deflator: 89.632 / 59.305 ≈ 1.5114
        assert abs(GDP_1990_TO_2010 - 1.5114) < 0.001

    def test_gdp_is_billion_2010(self):
        """USA GDP should be ~15-20 trillion $2010 at 2021."""
        gdp = get_gcam_gdp(2021, "USA")
        # GCAM reports ~12.4M in million 1990$ → ~18.7T in 2010$
        assert 10_000 < gdp < 30_000  # billion $2010

    def test_population_is_million(self):
        pop = get_gcam_population(2021, "USA")
        assert 300 < pop < 400  # million


# ---------------------------------------------------------------------------
# Electricity shares
# ---------------------------------------------------------------------------

class TestElecShares:
    def test_shares_sum_to_one(self):
        shares = get_gcam_elec_shares(2021, "USA")
        assert shares
        total = sum(shares.values())
        assert abs(total - 1.0) < 1e-6

    def test_no_negative_shares(self):
        for region in ["USA", "China", "India"]:
            shares = get_gcam_elec_shares(2021, region)
            for tech, share in shares.items():
                assert share >= 0, f"{region} {tech} has negative share"

    def test_usa_has_gas_coal_nuclear(self):
        shares = get_gcam_elec_shares(2021, "USA")
        assert shares.get("gas_cc", 0) > 0.1
        assert shares.get("coal", 0) > 0.01
        assert shares.get("nuclear", 0) > 0.01

    def test_no_1975_electricity(self):
        """1975 has no electricity data — should return empty."""
        shares = get_gcam_elec_shares(1975, "USA")
        assert shares == {}


# ---------------------------------------------------------------------------
# Final energy
# ---------------------------------------------------------------------------

class TestFinalEnergy:
    def test_total_fe_positive(self):
        fe = get_gcam_total_final_energy(2021, "USA")
        assert fe > 10  # EJ

    def test_sector_totals_reasonable(self):
        totals = get_gcam_sector_totals(2021, "USA")
        assert "industry" in totals
        assert "buildings" in totals
        assert "transport" in totals
        for sector, val in totals.items():
            assert val >= 0

    def test_sector_totals_sum_near_fe_total(self):
        totals = get_gcam_sector_totals(2021, "USA")
        fe = get_gcam_total_final_energy(2021, "USA")
        sector_sum = sum(totals.values())
        # Should be close (agriculture is small)
        assert abs(sector_sum - fe) / fe < 0.05

    def test_carrier_shares_sum_to_one(self):
        shares = get_gcam_fe_carrier_shares(2021, "USA")
        assert shares
        assert abs(sum(shares.values()) - 1.0) < 1e-6

    def test_sector_carrier_shares_sum_to_one(self):
        for sector in ("industry", "buildings", "transport"):
            shares = get_gcam_sector_carrier_shares(2021, sector, "USA")
            if shares:
                assert abs(sum(shares.values()) - 1.0) < 1e-6, \
                    f"{sector} carrier shares don't sum to 1"


# ---------------------------------------------------------------------------
# National accounts
# ---------------------------------------------------------------------------

class TestNationalAccounts:
    def test_capital_stock_positive(self):
        k = get_gcam_capital_stock(2021, "USA")
        assert k > 0

    def test_factor_shares_sum_to_one(self):
        fs = get_gcam_factor_shares(2021, "USA")
        total = sum(fs.values())
        assert abs(total - 1.0) < 0.05  # ~1.0 (may not be exact)

    def test_labor_share_dominant(self):
        fs = get_gcam_factor_shares(2021, "USA")
        assert fs["labor"] > 0.4


# ---------------------------------------------------------------------------
# CalibrationDataset
# ---------------------------------------------------------------------------

class TestCalibrationDataset:
    @pytest.fixture
    def dataset(self):
        return load_gcam_calibration()

    def test_model_name(self, dataset):
        assert "GHIM" in dataset.model_name
        assert "GCAM" in dataset.model_name

    def test_has_all_years(self, dataset):
        assert 2005 in dataset.years
        assert 2050 in dataset.years
        assert 2100 in dataset.years

    def test_has_r32_regions(self, dataset):
        assert "USA" in dataset.regions
        assert "China" in dataset.regions
        assert len(dataset.regions) == len(R32_REGIONS)

    def test_gdp_populated(self, dataset):
        assert "USA" in dataset.gdp
        assert len(dataset.gdp["USA"]) > 5

    def test_elec_shares_populated(self, dataset):
        assert "USA" in dataset.elec_shares
        # 1975 has no electricity → starts from 1990
        assert 1990 in dataset.elec_shares.get("USA", {}) or \
               2005 in dataset.elec_shares.get("USA", {})

    def test_sector_carrier_shares_all_sectors(self, dataset):
        usa_2021 = dataset.sector_carrier_shares.get("USA", {}).get(2021, {})
        assert "industry" in usa_2021
        assert "buildings" in usa_2021
        assert "transport" in usa_2021

    def test_no_r5_references(self, dataset):
        """CalibrationDataset should have R32 regions, not R5."""
        for region in dataset.regions:
            assert region in R32_REGIONS


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------

class TestCalibrator:
    @pytest.fixture
    def calibrator(self):
        dataset = load_gcam_calibration()
        return Calibrator(dataset)

    def test_available(self, calibrator):
        assert calibrator.available

    def test_native_r32(self, calibrator):
        assert calibrator.native_r32 is True

    def test_model_name(self, calibrator):
        assert "GHIM" in calibrator.model_name

    def test_get_elec_target_shares(self, calibrator):
        shares = calibrator.get_elec_target_shares(2025, "USA")
        assert shares is not None
        assert abs(sum(shares.values()) - 1.0) < 1e-6

    def test_get_sector_total(self, calibrator):
        val = calibrator.get_sector_total(2025, "industry", "USA")
        assert val is not None
        assert val > 0

    def test_get_fe_total(self, calibrator):
        val = calibrator.get_fe_total(2025, "USA")
        assert val is not None
        assert val > 0

    def test_get_gdp(self, calibrator):
        val = calibrator.get_gdp(2025, "USA")
        assert val is not None
        assert val > 10_000  # billion $2010

    def test_get_population(self, calibrator):
        val = calibrator.get_population(2025, "USA")
        assert val is not None
        assert 300 < val < 400

    def test_get_sector_carrier_shares(self, calibrator):
        shares = calibrator.get_sector_carrier_shares(2025, "industry", "USA")
        assert shares is not None
        assert abs(sum(shares.values()) - 1.0) < 1e-6

    def test_get_factor_shares(self, calibrator):
        fs = calibrator.get_factor_shares(2025, "USA")
        assert fs is not None
        assert "capital" in fs
        assert "labor" in fs

    def test_get_capital_stock(self, calibrator):
        k = calibrator.get_capital_stock(2025, "USA")
        assert k is not None
        assert k > 0

    def test_interpolation_at_2020(self, calibrator):
        """2020 is between GCAM years 2015 and 2021 — should interpolate."""
        gdp = calibrator.get_gdp(2020, "USA")
        assert gdp is not None
        gdp_2015 = calibrator.get_gdp(2015, "USA")
        gdp_2021 = calibrator.get_gdp(2021, "USA")
        assert gdp_2015 < gdp < gdp_2021

    def test_summary(self, calibrator):
        s = calibrator.summary("USA", years=[2021, 2050])
        assert "USA" in s
        assert "2021" in s

    def test_electricity_prefs_shape(self, calibrator):
        """electricity_prefs returns array matching tech count."""
        from ghim.sectors.electricity import OOPElectricitySector
        import numpy as np
        elec = OOPElectricitySector()
        fuel_prices = {"coal": 2.5, "gas": 4.0, "oil": 8.0, "nuclear": 0.7,
                       "biomass": 3.0, "uranium": 0.5}
        prefs = calibrator.electricity_prefs(2025, elec.techs, fuel_prices, "USA")
        assert prefs is not None
        assert len(prefs) == len(elec.techs)
        assert not np.any(np.isnan(prefs))


# ---------------------------------------------------------------------------
# Protocol compliance: Calibrator has same interface as AR6Calibrator
# ---------------------------------------------------------------------------

class TestProtocolCompliance:
    """Both AR6Calibrator and Calibrator must expose the same methods."""

    REQUIRED_METHODS = [
        "available",
        "model_name",
        "get_elec_target_shares",
        "get_fe_target_shares",
        "get_sector_total",
        "get_fe_total",
        "get_gdp",
        "get_population",
        "get_sector_carrier_shares",
        "electricity_prefs",
        "demand_carrier_prefs",
    ]

    def test_calibrator_has_all_methods(self):
        dataset = load_gcam_calibration()
        cal = Calibrator(dataset)
        for method in self.REQUIRED_METHODS:
            assert hasattr(cal, method), f"Calibrator missing {method}"

    def test_ar6_has_all_methods(self):
        from ghim.calibration import AR6Calibrator
        # Don't load data, just check methods exist on class
        for method in self.REQUIRED_METHODS:
            assert hasattr(AR6Calibrator, method) or \
                   any(method in cls.__dict__ for cls in AR6Calibrator.__mro__), \
                   f"AR6Calibrator missing {method}"
