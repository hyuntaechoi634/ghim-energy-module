"""Tests for KLEM macroeconomic driver."""

import pytest

from ghim.econ.klem import KLEMDriver
from ghim.config import (
    BASE_YEAR, MODEL_YEARS, HISTORICAL_YEARS, FUTURE_YEARS,
    CAPITAL_OUTPUT_RATIO, CAPITAL_SHARE, SAVINGS_RATE,
    LABOR_FORCE_PARTICIPATION, DEPRECIATION_RATE, TIMESTEP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver(gdp=1000.0, pop=100.0, energy=10.0):
    return KLEMDriver(base_gdp=gdp, base_population=pop, base_energy_demand_ej=energy)


def _ssp_constant(value=1000.0):
    """Return constant GDP/pop dicts for all MODEL_YEARS."""
    return {y: value for y in MODEL_YEARS}


def _ssp_growing(start=1000.0, growth=0.02):
    """Return growing GDP path (compound growth from HISTORY_START)."""
    gdp = {}
    for y in MODEL_YEARS:
        gdp[y] = start * (1 + growth) ** (y - MODEL_YEARS[0])
    return gdp


# ===========================================================================
# TestKLEMInit
# ===========================================================================

class TestKLEMInit:
    def test_capital_stock_uses_config_ratio(self):
        d = _make_driver(gdp=5000.0)
        assert d.capital_stock == pytest.approx(5000.0 * CAPITAL_OUTPUT_RATIO)

    def test_tfp_positive(self):
        d = _make_driver()
        assert d.tfp > 0

    def test_labor_from_population(self):
        d = _make_driver(pop=200.0)
        assert d.labor == pytest.approx(200.0 * LABOR_FORCE_PARTICIPATION)

    def test_base_year_production_matches_gdp(self):
        """At base year, Y = A*K^α*L^(1-α) should reproduce base_gdp."""
        d = _make_driver(gdp=2000.0, pop=150.0)
        y = d.compute_gross_output(population=150.0)
        assert y == pytest.approx(2000.0, rel=1e-6)


# ===========================================================================
# TestTFPTrajectory
# ===========================================================================

class TestTFPTrajectory:
    def test_covers_all_years(self):
        d = _make_driver()
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        for year in MODEL_YEARS:
            assert year in d._tfp_trajectory

    def test_all_tfp_positive(self):
        d = _make_driver()
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        for year, a in d._tfp_trajectory.items():
            assert a > 0, f"TFP at {year} = {a} (should be > 0)"

    def test_base_year_tfp_matches_init(self):
        """TFP at BASE_YEAR from trajectory should be close to the initial calibration."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        init_tfp = d.tfp
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        traj_tfp = d._tfp_trajectory[BASE_YEAR]
        assert traj_tfp == pytest.approx(init_tfp, rel=0.05)

    def test_growing_gdp_produces_increasing_tfp(self):
        """With growing GDP but constant population, TFP should trend upward."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        gdp_path = _ssp_growing(start=1000.0, growth=0.03)
        d.init_tfp_trajectory(gdp_path, _ssp_constant(100.0))
        # Compare first vs last TFP
        first_tfp = d._tfp_trajectory[MODEL_YEARS[0]]
        last_tfp = d._tfp_trajectory[MODEL_YEARS[-1]]
        assert last_tfp > first_tfp


# ===========================================================================
# TestHistoricalKBackSolve
# ===========================================================================

class TestHistoricalKBackSolve:
    def test_k2000_less_than_k2020(self):
        """With constant GDP, backward-solved K(2000) should be < K(2020)
        because capital accumulated over 2000-2020."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        # TFP at 2000 should be higher than at 2020 (smaller K → need higher A to match same GDP)
        tfp_2000 = d._tfp_trajectory[2000]
        tfp_2020 = d._tfp_trajectory[BASE_YEAR]
        assert tfp_2000 > tfp_2020, (
            f"TFP(2000)={tfp_2000:.4f} should be > TFP(2020)={tfp_2020:.4f} "
            "because K(2000) < K(2020)"
        )

    def test_historical_tfp_higher_than_base(self):
        """All historical TFP values should be >= base-year TFP
        (smaller K with same GDP requires higher A)."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        base_tfp = d._tfp_trajectory[BASE_YEAR]
        for year in HISTORICAL_YEARS:
            assert d._tfp_trajectory[year] >= base_tfp * 0.99, (
                f"TFP({year})={d._tfp_trajectory[year]:.4f} should be >= {base_tfp:.4f}"
            )


# ===========================================================================
# TestEdgeCases
# ===========================================================================

class TestEdgeCases:
    def test_missing_historical_gdp_uses_base(self):
        """If SSP dict is missing historical years, should fall back to base_gdp."""
        d = _make_driver(gdp=500.0, pop=50.0)
        # Only provide future years
        sparse_gdp = {y: 500.0 + (y - BASE_YEAR) * 10 for y in FUTURE_YEARS}
        sparse_pop = {y: 50.0 for y in FUTURE_YEARS}
        d.init_tfp_trajectory(sparse_gdp, sparse_pop)
        # Should still produce valid TFP for all years
        for year in MODEL_YEARS:
            assert d._tfp_trajectory[year] > 0

    def test_zero_population_fallback(self):
        """Zero population should trigger TFP fallback, not crash."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        pop_with_zero = _ssp_constant(100.0)
        pop_with_zero[2050] = 0.0
        d.init_tfp_trajectory(_ssp_constant(1000.0), pop_with_zero)
        # TFP at 2050 should be the fallback value (init TFP)
        assert d._tfp_trajectory[2050] == pytest.approx(d.tfp)
