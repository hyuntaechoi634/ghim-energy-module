"""Tests for data loading modules."""

import pytest
import pandas as pd

from ghim.regions import R10_REGIONS, build_iso_to_r10, load_region_mapping
from ghim.data.ssp import load_ssp_data


class TestRegionMapping:
    def test_mapping_loads(self):
        df = load_region_mapping()
        assert len(df) > 200
        assert "ISO" in df.columns
        assert "region_ar6_10" in df.columns

    def test_iso_to_r10_coverage(self):
        mapping = build_iso_to_r10()
        assert "USA" in mapping
        assert "CHN" in mapping
        assert mapping["USA"] == "North America"
        assert mapping["CHN"] == "Eastern Asia"

    def test_all_r10_regions_present(self):
        mapping = build_iso_to_r10()
        regions_in_mapping = set(mapping.values())
        for r in R10_REGIONS:
            assert r in regions_in_mapping, f"R10 region {r} not in mapping"


class TestSSPData:
    def test_ssp2_loads(self):
        data = load_ssp_data("SSP2")
        assert "population" in data
        assert "gdp" in data

    def test_population_shape(self):
        data = load_ssp_data("SSP2")
        pop = data["population"]
        assert len(pop) == len(R10_REGIONS)
        assert 2020 in pop.columns

    def test_global_population_2020(self):
        """Global population in 2020 should be ~7.8 billion."""
        data = load_ssp_data("SSP2")
        global_pop = data["population"][2020].sum()
        assert 7000 < global_pop < 8500, f"Global pop {global_pop} out of range"

    def test_global_gdp_2020(self):
        """Global GDP PPP in 2020 should be ~120-140 trillion USD."""
        data = load_ssp_data("SSP2")
        global_gdp = data["gdp"][2020].sum()
        assert 100000 < global_gdp < 200000, f"Global GDP {global_gdp} out of range"
