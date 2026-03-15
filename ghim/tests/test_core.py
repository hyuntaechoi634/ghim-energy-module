"""Tests for ghim.core foundation: Carrier, Config, EmissionResult, State."""

import pytest
from dataclasses import replace


# ===================================================================
# Carrier
# ===================================================================

class TestCarrier:
    def test_enum_values(self):
        from ghim.core.carrier import Carrier
        assert Carrier.ELECTRICITY.value == "electricity"
        assert Carrier.COAL.value == "coal"
        assert Carrier.H2.value == "h2"
        assert Carrier.HEAT.value == "heat"

    def test_str_comparison(self):
        """Carrier(str, Enum) should compare equal to its string value."""
        from ghim.core.carrier import Carrier
        assert Carrier.COAL == "coal"
        assert Carrier.GAS == "gas"

    def test_carriers_7_and_8(self):
        from ghim.core.carrier import CARRIERS_7, CARRIERS_8, Carrier
        assert len(CARRIERS_7) == 7
        assert len(CARRIERS_8) == 8
        assert Carrier.HEAT not in CARRIERS_7
        assert Carrier.HEAT in CARRIERS_8

    def test_carbon_coefs_keys(self):
        from ghim.core.carrier import CARBON_COEFS, Carrier
        # Every carrier should have a coefficient
        for c in Carrier:
            assert c in CARBON_COEFS, f"Missing CARBON_COEFS for {c}"

    def test_carbon_coefs_values(self):
        from ghim.core.carrier import CARBON_COEFS, Carrier
        # Fossil fuels have positive coefficients
        assert CARBON_COEFS[Carrier.COAL] > 0
        assert CARBON_COEFS[Carrier.GAS] > 0
        assert CARBON_COEFS[Carrier.LIQUIDS] > 0
        # Non-carbon carriers are zero
        assert CARBON_COEFS[Carrier.ELECTRICITY] == 0.0
        assert CARBON_COEFS[Carrier.H2] == 0.0
        assert CARBON_COEFS[Carrier.BIOMASS] == 0.0

    def test_carbon_coefs_string_key_lookup(self):
        """Dict lookup with plain string should work via str enum."""
        from ghim.core.carrier import CARBON_COEFS
        assert CARBON_COEFS["coal"] > 0

    def test_ch4_fugitive(self):
        from ghim.core.carrier import CH4_FUGITIVE, Carrier
        assert len(CH4_FUGITIVE) == 3
        assert CH4_FUGITIVE[Carrier.COAL] > 0

    def test_gwp100(self):
        from ghim.core.carrier import GWP100
        assert GWP100["ch4"] == pytest.approx(27.9)
        assert GWP100["n2o"] == pytest.approx(273.0)
        assert GWP100["hfc"] == pytest.approx(1530.0)

    def test_tc_to_tco2(self):
        from ghim.core.carrier import TC_TO_TCO2
        assert TC_TO_TCO2 == pytest.approx(44.0 / 12.0)

    def test_lulucf_net_co2(self):
        from ghim.core.carrier import LULUCF_NET_CO2
        assert len(LULUCF_NET_CO2) == 32  # GCAM R32 regions (minus Taiwan = 31, but we have 32)
        # Global sum should be roughly -0.35 GtCO2
        total = sum(LULUCF_NET_CO2.values())
        assert -1.0 < total < 0.5


# ===================================================================
# EmissionResult
# ===================================================================

class TestEmissionResult:
    def test_defaults_zero(self):
        from ghim.core.emissions import EmissionResult
        e = EmissionResult()
        assert e.co2 == 0.0
        assert e.ch4 == 0.0
        assert e.co2eq == 0.0

    def test_co2eq_calculation(self):
        from ghim.core.emissions import EmissionResult
        from ghim.core.carrier import GWP100
        e = EmissionResult(co2=100.0, ch4=1.0, n2o=0.1)
        expected = 100.0 + 1.0 * GWP100["ch4"] + 0.1 * GWP100["n2o"]
        assert e.co2eq == pytest.approx(expected)

    def test_co2eq_excl_lulucf(self):
        from ghim.core.emissions import EmissionResult
        e = EmissionResult(co2=100.0, lulucf=-50.0)
        assert e.co2eq == pytest.approx(50.0)
        assert e.co2eq_excl_lulucf == pytest.approx(100.0)

    def test_addition(self):
        from ghim.core.emissions import EmissionResult
        a = EmissionResult(co2=10.0, ch4=1.0)
        b = EmissionResult(co2=20.0, n2o=0.5)
        c = a + b
        assert c.co2 == pytest.approx(30.0)
        assert c.ch4 == pytest.approx(1.0)
        assert c.n2o == pytest.approx(0.5)

    def test_sum_builtin(self):
        """sum() should work via __radd__ with initial 0."""
        from ghim.core.emissions import EmissionResult
        items = [EmissionResult(co2=10.0), EmissionResult(co2=20.0)]
        total = sum(items)
        assert total.co2 == pytest.approx(30.0)

    def test_negative_beccs(self):
        from ghim.core.emissions import EmissionResult
        e = EmissionResult(co2=-5.0)  # BECCS removes CO2
        assert e.co2eq < 0


# ===================================================================
# Config
# ===================================================================

class TestConfig:
    def test_default_config_runs(self):
        """GHIMConfig() should produce a valid config with no arguments."""
        from ghim.core.config import GHIMConfig
        cfg = GHIMConfig()
        assert cfg.economy.sigma_kl == pytest.approx(0.80)
        assert cfg.time.base_year == 2021
        assert cfg.solver.damping == pytest.approx(0.4)

    def test_frozen(self):
        """Config dataclasses should be immutable."""
        from ghim.core.config import GHIMConfig
        cfg = GHIMConfig()
        with pytest.raises(AttributeError):
            cfg.economy = None

    def test_replace_creates_new(self):
        from ghim.core.config import GHIMConfig
        cfg = GHIMConfig()
        cfg2 = replace(cfg, economy=replace(cfg.economy, sigma_kle=0.5))
        assert cfg.economy.sigma_kle == pytest.approx(0.40)
        assert cfg2.economy.sigma_kle == pytest.approx(0.50)

    def test_time_config_properties(self):
        from ghim.core.config import TimeConfig
        t = TimeConfig()
        assert t.historical_years[0] == 2000
        assert t.historical_years[-1] == 2020
        assert t.future_years[0] == 2025
        assert t.future_years[-1] == 2150
        assert t.solve_years[0] == 2021  # base_year
        assert t.solve_years[1] == 2025  # first projection year
        assert t.model_years == t.historical_years + t.future_years

    def test_time_config_custom(self):
        from ghim.core.config import TimeConfig
        t = TimeConfig(base_year=2020, projection_start=2025, end_year=2100)
        assert t.solve_years[0] == 2020
        assert t.future_years[-1] == 2100

    def test_module_level_aliases(self):
        from ghim.core.config import (
            BASE_YEAR, TIMESTEP, SIGMA_KL, SAVINGS_RATE,
            DEPRECIATION_RATE, PRICE_TOL,
        )
        assert BASE_YEAR == 2021
        assert TIMESTEP == 5
        assert SIGMA_KL == pytest.approx(0.80)
        assert SAVINGS_RATE == pytest.approx(0.22)
        assert DEPRECIATION_RATE == pytest.approx(0.05)
        assert PRICE_TOL == pytest.approx(1e-3)

    def test_load_config_defaults(self):
        from ghim.core.config import load_config
        cfg = load_config()
        assert cfg.economy.sigma_kl == pytest.approx(0.80)

    def test_load_config_yaml(self, tmp_path):
        from ghim.core.config import load_config
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(
            "economy:\n  sigma_kle: 0.5\nsolver:\n  tolerance: 0.0001\n"
        )
        cfg = load_config(str(yaml_file))
        assert cfg.economy.sigma_kle == pytest.approx(0.5)
        assert cfg.economy.sigma_kl == pytest.approx(0.80)  # unchanged
        assert cfg.solver.tolerance == pytest.approx(1e-4)

    def test_load_config_ignores_unknown_keys(self, tmp_path):
        from ghim.core.config import load_config
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("economy:\n  bogus_param: 999\n")
        cfg = load_config(str(yaml_file))
        assert cfg.economy.sigma_kl == pytest.approx(0.80)  # not affected


# ===================================================================
# State
# ===================================================================

class TestState:
    def test_region_state_defaults(self):
        from ghim.core.state import RegionState
        rs = RegionState()
        assert rs.gdp == 0.0
        assert rs.capital_stock == 0.0
        assert rs.emissions == 0.0
        assert rs.composite_energy_price == 5.0

    def test_region_state_mutable(self):
        from ghim.core.state import RegionState
        rs = RegionState()
        rs.gdp = 5000.0
        assert rs.gdp == 5000.0

    def test_region_state_emissions_detail(self):
        from ghim.core.state import RegionState
        from ghim.core.emissions import EmissionResult
        rs = RegionState()
        assert isinstance(rs.emissions_detail, EmissionResult)
        rs.emissions_detail.co2 = 100.0
        assert rs.emissions_detail.co2 == 100.0

    def test_period_state(self):
        from ghim.core.state import PeriodState, RegionState
        ps = PeriodState(period=2025)
        ps.regions["USA"] = RegionState(gdp=20000.0)
        assert ps.regions["USA"].gdp == 20000.0

    def test_period_state_global_emissions(self):
        from ghim.core.state import PeriodState
        from ghim.core.emissions import EmissionResult
        ps = PeriodState(period=2025)
        assert isinstance(ps.global_emissions_detail, EmissionResult)

    def test_carrier_typed_dicts(self):
        from ghim.core.state import RegionState
        from ghim.core.carrier import Carrier
        rs = RegionState()
        rs.carrier_prices[Carrier.ELECTRICITY] = 20.0
        rs.raw_fuel_prices[Carrier.GAS] = 3.85
        assert rs.carrier_prices[Carrier.ELECTRICITY] == 20.0


# ===================================================================
# Backward compatibility
# ===================================================================

class TestBackwardCompat:
    def test_config_reexports(self):
        """ghim.config should re-export moved constants."""
        from ghim.config import (
            BASE_YEAR, TIMESTEP, SIGMA_KL, CARBON_COEFS, TC_TO_TCO2,
        )
        assert BASE_YEAR == 2021
        assert SIGMA_KL == pytest.approx(0.80)
        assert TC_TO_TCO2 == pytest.approx(44.0 / 12.0)

    def test_carbon_coefs_compat(self):
        """Old string-keyed CARBON_COEFS should still work."""
        from ghim.config import CARBON_COEFS
        assert CARBON_COEFS["coal"] > 0
        assert CARBON_COEFS["electricity"] == 0.0
