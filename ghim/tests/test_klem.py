"""Tests for CES-KLE macroeconomic driver."""

import pytest
import numpy as np

from ghim.econ.klem import KLEMDriver
from ghim.config import (
    BASE_YEAR, MODEL_YEARS, HISTORICAL_YEARS, FUTURE_YEARS,
    CAPITAL_OUTPUT_RATIO, CAPITAL_SHARE, SAVINGS_RATE,
    DEPRECIATION_RATE, TIMESTEP,
    SIGMA_KLE, REGIONAL_LFP, LABOR_FORCE_PARTICIPATION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0, region=""):
    return KLEMDriver(
        base_gdp=gdp,
        base_population=pop,
        base_energy_demand_ej=energy,
        base_energy_price=energy_price,
        region=region,
    )


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

    def test_labor_from_population_default(self):
        d = _make_driver(pop=200.0)
        assert d.labor == pytest.approx(200.0 * LABOR_FORCE_PARTICIPATION)

    def test_base_year_va_matches_gdp(self):
        """At base year, VA = A*K^α*L^(1-α) should reproduce base_gdp."""
        d = _make_driver(gdp=2000.0, pop=150.0)
        va = d.compute_value_added(population=150.0)
        assert va == pytest.approx(2000.0, rel=1e-6)

    def test_ces_calibration_reproduces_base(self):
        """CES(VA_base, E_base) should approximately reproduce base_gdp."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        # Y = CES(VA, E) ≈ base_gdp (calibrated at base year)
        assert y == pytest.approx(1000.0, rel=0.1)


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
# TestCESEnergyDemand
# ===========================================================================

class TestCESEnergyDemand:
    def test_energy_demand_decreases_with_price(self):
        """Higher P_E → lower E (CES substitution effect)."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        e_lo = d.compute_energy_demand(va, energy_price=3.0)
        e_hi = d.compute_energy_demand(va, energy_price=10.0)
        assert e_hi < e_lo, f"E(P=10)={e_hi:.2f} >= E(P=3)={e_lo:.2f}"

    def test_energy_demand_increases_with_va(self):
        """Higher VA → higher E demand."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        e_lo = d.compute_energy_demand(value_added=500.0, energy_price=5.0)
        e_hi = d.compute_energy_demand(value_added=2000.0, energy_price=5.0)
        assert e_hi > e_lo

    def test_base_energy_demand_reproduced(self):
        """At base-year VA and P_E, demand should reproduce base_energy."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        e = d.compute_energy_demand(va, energy_price=5.0)
        assert e == pytest.approx(10.0, rel=0.1)

    def test_price_floor_prevents_explosion(self):
        """Very low price should not produce infinite demand."""
        d = _make_driver()
        va = d.compute_value_added(100.0)
        e = d.compute_energy_demand(va, energy_price=0.001)
        assert np.isfinite(e)
        assert e > 0


# ===========================================================================
# TestCESGrossOutput
# ===========================================================================

class TestCESGrossOutput:
    def test_ces_gross_output_positive(self):
        d = _make_driver()
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        assert y > 0

    def test_gross_output_equals_va(self):
        """Y = VA in the two-level CES (energy via cost feedback)."""
        d = _make_driver()
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        assert y == pytest.approx(va)

    def test_ces_output_increases_with_va(self):
        """More VA → higher output."""
        d = _make_driver()
        y_lo = d.compute_gross_output(500.0, 10.0)
        y_hi = d.compute_gross_output(2000.0, 10.0)
        assert y_hi > y_lo


# ===========================================================================
# TestCompositeEnergyPrice
# ===========================================================================

class TestCompositeEnergyPrice:
    def test_expenditure_weighted(self):
        """Composite price should be expenditure-weighted, not simple average."""
        prices = {"coal": 2.0, "gas": 6.0}
        demands = {"coal": 1.0, "gas": 3.0}  # gas dominates
        composite = KLEMDriver.composite_energy_price(prices, demands)
        # Expected: (2*1 + 6*3) / (1+3) = 20/4 = 5.0
        assert composite == pytest.approx(5.0)

    def test_equal_demands_equals_simple_avg(self):
        """With equal demands, composite = simple average."""
        prices = {"a": 2.0, "b": 8.0}
        demands = {"a": 5.0, "b": 5.0}
        composite = KLEMDriver.composite_energy_price(prices, demands)
        assert composite == pytest.approx(5.0)

    def test_zero_demand_returns_default(self):
        composite = KLEMDriver.composite_energy_price({"a": 5.0}, {})
        assert composite == 5.0


# ===========================================================================
# TestRegionalLFP
# ===========================================================================

class TestRegionalLFP:
    def test_known_region_uses_regional_lfp(self):
        d = _make_driver(pop=100.0, region="Middle East")
        assert d.lfp == pytest.approx(0.51)
        assert d.labor == pytest.approx(100.0 * 0.51)

    def test_unknown_region_uses_global_default(self):
        d = _make_driver(pop=100.0, region="Atlantis")
        assert d.lfp == pytest.approx(LABOR_FORCE_PARTICIPATION)

    def test_empty_region_uses_global_default(self):
        d = _make_driver(pop=100.0, region="")
        assert d.lfp == pytest.approx(LABOR_FORCE_PARTICIPATION)


# ===========================================================================
# TestEnergyCostShareBounded
# ===========================================================================

class TestEnergyCostShareBounded:
    def test_cost_share_above_minimum(self):
        """base_energy_cost_share should be at least MIN_ENERGY_COST_SHARE."""
        from ghim.config import MIN_ENERGY_COST_SHARE
        d = _make_driver(gdp=1000.0, pop=100.0, energy=0.01, energy_price=0.1)
        assert d.base_energy_cost_share >= MIN_ENERGY_COST_SHARE

    def test_cost_share_reasonable(self):
        """Energy cost share at base year should be in [0, 1)."""
        d = _make_driver()
        assert 0 < d.base_energy_cost_share < 1.0


# ===========================================================================
# TestEdgeCases
# ===========================================================================

class TestEdgeCases:
    def test_missing_historical_gdp_uses_base(self):
        """If SSP dict is missing historical years, should fall back to base_gdp."""
        d = _make_driver(gdp=500.0, pop=50.0)
        sparse_gdp = {y: 500.0 + (y - BASE_YEAR) * 10 for y in FUTURE_YEARS}
        sparse_pop = {y: 50.0 for y in FUTURE_YEARS}
        d.init_tfp_trajectory(sparse_gdp, sparse_pop)
        for year in MODEL_YEARS:
            assert d._tfp_trajectory[year] > 0

    def test_future_tfp_uses_base_year_k(self):
        """TFP should not spike at the historical→future boundary.

        Regression test: a bug caused forward TFP calibration to use K(2000)
        instead of K(BASE_YEAR), producing inflated TFP that caused a GDP
        surge at the 2020→2025 transition.
        """
        d = _make_driver(gdp=5000.0, pop=500.0)
        gdp_path = _ssp_growing(start=3000.0, growth=0.02)
        pop_path = _ssp_growing(start=400.0, growth=0.005)
        d.init_tfp_trajectory(gdp_path, pop_path)
        tfp_2020 = d._tfp_trajectory[BASE_YEAR]
        tfp_2025 = d._tfp_trajectory[BASE_YEAR + TIMESTEP]
        assert tfp_2025 / tfp_2020 < 1.5, (
            f"TFP spike at boundary: TFP(2020)={tfp_2020:.4f}, "
            f"TFP(2025)={tfp_2025:.4f}, ratio={tfp_2025/tfp_2020:.2f}"
        )

    def test_zero_population_fallback(self):
        """Zero population should trigger TFP fallback, not crash."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        pop_with_zero = _ssp_constant(100.0)
        pop_with_zero[2050] = 0.0
        d.init_tfp_trajectory(_ssp_constant(1000.0), pop_with_zero)
        assert d._tfp_trajectory[2050] == pytest.approx(d.tfp)


# ===========================================================================
# TestSigmaSensitivity
# ===========================================================================

class TestSigmaSensitivity:
    def test_low_sigma_approaches_fixed_ratio(self):
        """With σ→0 (Leontief), E/VA ratio should be nearly fixed."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0,
                         region="")
        d_low = KLEMDriver(1000.0, 100.0, 10.0, 5.0, sigma_kle=0.05)
        va = d_low.compute_value_added(100.0)
        e1 = d_low.compute_energy_demand(va, energy_price=3.0)
        e2 = d_low.compute_energy_demand(va, energy_price=10.0)
        # With very low sigma, demand should barely change with price
        ratio = e1 / e2 if e2 > 0 else float("inf")
        assert ratio < 3.0  # much less responsive than high sigma

    def test_high_sigma_very_responsive(self):
        """With high σ, energy demand should be very responsive to price."""
        d_hi = KLEMDriver(1000.0, 100.0, 10.0, 5.0, sigma_kle=2.0)
        va = d_hi.compute_value_added(100.0)
        e_lo = d_hi.compute_energy_demand(va, energy_price=2.0)
        e_hi = d_hi.compute_energy_demand(va, energy_price=20.0)
        ratio = e_lo / e_hi
        assert ratio > 5.0  # very responsive
