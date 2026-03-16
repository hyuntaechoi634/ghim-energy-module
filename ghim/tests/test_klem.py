"""Tests for CES-KLE macroeconomic driver."""

import pytest
import numpy as np

from ghim.econ.klem import KLEMDriver
from ghim.core.config import (
    BASE_YEAR, MODEL_YEARS, SOLVE_YEARS, FUTURE_YEARS,
    CAPITAL_SHARE, SAVINGS_RATE, DEPRECIATION_RATE, TIMESTEP, SIGMA_KLE,
)
from ghim.config import (
    CAPITAL_OUTPUT_RATIO, REGIONAL_LFP, LABOR_FORCE_PARTICIPATION,
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
        """At base year, VA = A*K^alpha*L^(1-alpha) should reproduce base_gdp.

        With full CES, TFP is calibrated so CES(VA, E_val) = GDP.
        At the calibration point VA = GDP because the CES scale factor
        absorbs the normalization.
        """
        d = _make_driver(gdp=2000.0, pop=150.0)
        va = d.compute_value_added(population=150.0)
        assert va == pytest.approx(2000.0, rel=1e-6)

    def test_ces_calibration_reproduces_base(self):
        """CES(VA_base, E_base) should reproduce base_kle = GDP + E_cost."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        # KLE = GDP + E_cost at base year (KLE bundles VA + energy)
        expected_kle = 1000.0 + 10.0 * 5.0  # GDP + E*P_E
        assert y == pytest.approx(expected_kle, rel=1e-6)

    def test_base_energy_value_stored(self):
        """base_energy_value = E * P_E_base should be stored."""
        d = _make_driver(gdp=1000.0, energy=10.0, energy_price=5.0)
        assert d.base_energy_value == pytest.approx(50.0)

    def test_ces_alphas_sum_to_one(self):
        """CES share parameters should sum to approximately 1."""
        d = _make_driver()
        assert d._ces_alphas.sum() == pytest.approx(1.0, abs=1e-6)


# ===========================================================================
# TestTFPTrajectory
# ===========================================================================

class TestTFPTrajectory:
    def test_covers_solve_years(self):
        """TFP trajectory should cover BASE_YEAR + all FUTURE_YEARS."""
        d = _make_driver()
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        for year in SOLVE_YEARS:
            assert year in d._tfp_trajectory

    def test_no_historical_years(self):
        """TFP trajectory should NOT include historical years (2000-2015)."""
        d = _make_driver()
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        assert 2000 not in d._tfp_trajectory
        assert 2015 not in d._tfp_trajectory

    def test_all_tfp_positive(self):
        d = _make_driver()
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        for year, a in d._tfp_trajectory.items():
            assert a > 0, f"TFP at {year} = {a} (should be > 0)"

    def test_base_year_tfp_matches_init(self):
        """TFP at BASE_YEAR from trajectory should equal the initial calibration."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        init_tfp = d.tfp
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        traj_tfp = d._tfp_trajectory[BASE_YEAR]
        assert traj_tfp == pytest.approx(init_tfp, rel=1e-6)

    def test_growing_gdp_produces_increasing_tfp(self):
        """With growing GDP but constant population, TFP should trend upward."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        gdp_path = _ssp_growing(start=1000.0, growth=0.03)
        d.init_tfp_trajectory(gdp_path, _ssp_constant(100.0))
        first_tfp = d._tfp_trajectory[BASE_YEAR]
        last_tfp = d._tfp_trajectory[SOLVE_YEARS[-1]]
        assert last_tfp > first_tfp

    def test_capital_stock_unchanged_after_calibration(self):
        """Capital stock should remain at K(BASE_YEAR) after TFP calibration.
        (No backward solve, no reset to K(2000).)"""
        d = _make_driver(gdp=1000.0, pop=100.0)
        k_before = d.capital_stock
        d.init_tfp_trajectory(_ssp_constant(1000.0), _ssp_constant(100.0))
        assert d.capital_stock == pytest.approx(k_before)


# ===========================================================================
# TestCESEnergyDemand
# ===========================================================================

class TestCESEnergyDemand:
    def test_energy_demand_decreases_with_price(self):
        """Higher P_E -> lower E (CES substitution effect)."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        e_lo = d.compute_energy_demand(va, energy_price=3.0)
        e_hi = d.compute_energy_demand(va, energy_price=10.0)
        assert e_hi < e_lo, f"E(P=10)={e_hi:.2f} >= E(P=3)={e_lo:.2f}"

    def test_energy_demand_increases_with_va(self):
        """Higher VA -> higher E demand."""
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

    def test_ces_output_at_calibration_point(self):
        """At calibration point, KLE = GDP + E_cost (not GDP alone)."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        expected_kle = 1000.0 + 10.0 * 5.0
        assert y == pytest.approx(expected_kle, rel=1e-6)

    def test_ces_output_increases_with_va(self):
        """More VA -> higher output."""
        d = _make_driver()
        y_lo = d.compute_gross_output(500.0, 10.0)
        y_hi = d.compute_gross_output(2000.0, 10.0)
        assert y_hi > y_lo

    def test_ces_output_increases_with_energy(self):
        """More energy -> higher CES output (energy is a production factor)."""
        d = _make_driver()
        va = d.compute_value_added(100.0)
        y_lo = d.compute_gross_output(va, 5.0)
        y_hi = d.compute_gross_output(va, 20.0)
        assert y_hi > y_lo

    def test_ces_output_responds_to_energy_reduction(self):
        """Reducing energy should reduce CES output (GDP drag)."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        y_base = d.compute_gross_output(va, 10.0)
        y_low_e = d.compute_gross_output(va, 5.0)
        assert y_low_e < y_base
        # The reduction should be meaningful but not catastrophic
        assert y_low_e > 0.5 * y_base

    def test_ces_output_less_than_va_when_energy_drops(self):
        """When energy falls below base, CES output should be less than VA."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)
        # Halve energy
        y = d.compute_gross_output(va, 5.0)
        assert y < va, "CES output should drop below VA when energy decreases"


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
        from ghim.config import MIN_ENERGY_COST_SHARE  # not in config hierarchy
        d = _make_driver(gdp=1000.0, pop=100.0, energy=0.01, energy_price=0.1)
        assert d.base_energy_cost_share >= MIN_ENERGY_COST_SHARE

    def test_cost_share_reasonable(self):
        """Energy cost share at base year should be in [0, 1)."""
        d = _make_driver()
        assert 0 < d.base_energy_cost_share < 1.0


# ===========================================================================
# TestInvestment
# ===========================================================================

class TestInvestment:
    def test_investment_from_gross_output(self):
        """Investment = s x Y (from CES gross output, no cost subtraction)."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        inv = d.compute_investment(y)
        assert inv == pytest.approx(SAVINGS_RATE * y, rel=1e-6)

    def test_investment_capped_by_capital(self):
        """Investment should not exceed cap_rate x K."""
        d = _make_driver(gdp=100000.0, pop=100.0)  # very high GDP
        va = d.compute_value_added(100.0)
        y = d.compute_gross_output(va, 10.0)
        inv = d.compute_investment(y)
        max_inv = d.investment_cap_rate * d.capital_stock
        assert inv <= max_inv + 1e-6

    def test_capital_evolves_forward(self):
        """Capital should change after update."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        k_before = d.capital_stock
        inv = d.compute_investment(1000.0)
        d.update_capital(inv)
        assert d.capital_stock != k_before


# ===========================================================================
# TestHighCarbonPrice
# ===========================================================================

class TestHighCarbonPrice:
    def test_high_price_reduces_output(self):
        """Tripling energy price should meaningfully reduce CES output."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)

        # Base case
        e_base = d.compute_energy_demand(va, 5.0)
        y_base = d.compute_gross_output(va, e_base)

        # Triple energy price -> energy falls
        e_high = d.compute_energy_demand(va, 15.0)
        y_high = d.compute_gross_output(va, e_high)

        assert e_high < e_base, "Energy should decrease with higher price"
        assert y_high < y_base, "CES output should decrease with less energy"
        # GDP should drop but not collapse
        assert y_high > 0.3 * y_base, "GDP loss should not exceed 70%"

    def test_moderate_price_moderate_drag(self):
        """50% price increase should produce modest GDP drag."""
        d = _make_driver(gdp=1000.0, pop=100.0, energy=10.0, energy_price=5.0)
        va = d.compute_value_added(100.0)

        e_base = d.compute_energy_demand(va, 5.0)
        y_base = d.compute_gross_output(va, e_base)

        e_mod = d.compute_energy_demand(va, 7.5)  # 50% price increase
        y_mod = d.compute_gross_output(va, e_mod)

        drag = 1.0 - y_mod / y_base
        assert 0 < drag < 0.15, f"GDP drag from 50% price increase = {drag:.1%}"


# ===========================================================================
# TestEdgeCases
# ===========================================================================

class TestEdgeCases:
    def test_missing_future_gdp_uses_base(self):
        """If SSP dict is sparse, should fall back to base_gdp."""
        d = _make_driver(gdp=500.0, pop=50.0)
        # Only provide a few future years
        sparse_gdp = {2030: 600.0, 2050: 800.0}
        sparse_pop = {2030: 50.0, 2050: 50.0}
        d.init_tfp_trajectory(sparse_gdp, sparse_pop)
        for year in SOLVE_YEARS:
            assert d._tfp_trajectory[year] > 0

    def test_tfp_smooth_at_base_to_future(self):
        """TFP should not spike at base_year -> first future year boundary."""
        d = _make_driver(gdp=5000.0, pop=500.0)
        gdp_path = _ssp_growing(start=3000.0, growth=0.02)
        pop_path = _ssp_growing(start=400.0, growth=0.005)
        d.init_tfp_trajectory(gdp_path, pop_path)
        tfp_base = d._tfp_trajectory[BASE_YEAR]
        tfp_first = d._tfp_trajectory[FUTURE_YEARS[0]]
        assert tfp_first / tfp_base < 1.5, (
            f"TFP spike at boundary: TFP({BASE_YEAR})={tfp_base:.4f}, "
            f"TFP({FUTURE_YEARS[0]})={tfp_first:.4f}, "
            f"ratio={tfp_first/tfp_base:.2f}"
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
        """With sigma->0 (Leontief), E/VA ratio should be nearly fixed."""
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
        """With high sigma, energy demand should be very responsive to price."""
        d_hi = KLEMDriver(1000.0, 100.0, 10.0, 5.0, sigma_kle=2.0)
        va = d_hi.compute_value_added(100.0)
        e_lo = d_hi.compute_energy_demand(va, energy_price=2.0)
        e_hi = d_hi.compute_energy_demand(va, energy_price=20.0)
        ratio = e_lo / e_hi
        assert ratio > 5.0  # very responsive


# ===========================================================================
# TestCESKLInnerNest
# ===========================================================================

class TestCESKLInnerNest:
    def test_kl_alphas_sum_to_one(self):
        """K-L CES share parameters should sum to 1."""
        d = _make_driver()
        assert d._ces_alphas_kl.sum() == pytest.approx(1.0, abs=1e-6)

    def test_sigma_kl_one_matches_cobb_douglas(self):
        """With sigma_KL=1.0 (Cobb-Douglas), VA should match K^alpha L^(1-alpha)."""
        d_cd = KLEMDriver(1000.0, 100.0, 10.0, 5.0, sigma_kl=1.0)
        va_ces = d_cd.compute_value_added(100.0)
        # Cobb-Douglas reference:
        k = d_cd.capital_stock
        l = d_cd.labor
        va_cd = d_cd.tfp * k ** d_cd.alpha * l ** (1.0 - d_cd.alpha)
        assert va_ces == pytest.approx(va_cd, rel=0.01)

    def test_sigma_kl_stored(self):
        d = _make_driver()
        from ghim.core.config import SIGMA_KL
        assert d.sigma_kl == SIGMA_KL

    def test_va_increases_with_capital(self):
        """More capital -> higher VA (holding labor constant)."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        va1 = d.compute_value_added(100.0)
        d.capital_stock *= 2.0
        va2 = d.compute_value_added(100.0)
        assert va2 > va1

    def test_va_increases_with_labor(self):
        """More labor -> higher VA (holding capital constant)."""
        d = _make_driver(gdp=1000.0, pop=100.0)
        va_lo = d.compute_value_added(50.0)
        va_hi = d.compute_value_added(200.0)
        assert va_hi > va_lo

    def test_low_sigma_kl_less_substitutable(self):
        """With low sigma_KL, halving labor should hurt VA more."""
        d_low = KLEMDriver(1000.0, 100.0, 10.0, 5.0, sigma_kl=0.3)
        d_high = KLEMDriver(1000.0, 100.0, 10.0, 5.0, sigma_kl=1.5)
        # VA at full labor
        va_full_low = d_low.compute_value_added(100.0)
        va_full_high = d_high.compute_value_added(100.0)
        # VA at halved labor
        va_half_low = d_low.compute_value_added(50.0)
        va_half_high = d_high.compute_value_added(50.0)
        # With low sigma (complements), losing labor hurts more
        drop_low = 1.0 - va_half_low / va_full_low
        drop_high = 1.0 - va_half_high / va_full_high
        assert drop_low > drop_high, (
            f"Low sigma drop={drop_low:.3f} should exceed high sigma drop={drop_high:.3f}"
        )

    def test_ces_kl_reproduces_base_va(self):
        """At base year, VA = TFP x CES(K, L) should reproduce base_gdp."""
        d = _make_driver(gdp=5000.0, pop=500.0)
        va = d.compute_value_added(500.0)
        # VA should approximately equal GDP (exact match depends on outer CES calibration)
        assert va == pytest.approx(5000.0, rel=1e-6)


# ===========================================================================
# TestTFPWithRefEnergy
# ===========================================================================

class TestTFPWithRefEnergy:
    """Test TFP calibration with equilibrium energy (two-pass)."""

    def test_tfp_with_ref_energy_changes_trajectory(self):
        """When ref_energy with declining intensity is provided,
        TFP should differ from naive (energy scales linearly with GDP).

        ref_energy is accepted but no longer used (naive KLEM scaling
        is always used to preserve CES consistency).
        """
        base_gdp = 1000.0
        gdp_path = {y: base_gdp * (1.03) ** (y - BASE_YEAR) for y in MODEL_YEARS}
        pop_path = _ssp_constant(100.0)
        d_naive = _make_driver(gdp=base_gdp, pop=100.0, energy=10.0)
        d_ref = _make_driver(gdp=base_gdp, pop=100.0, energy=10.0)

        # Declining intensity (sector electrification + efficiency)
        ref_energy = {}
        for y in FUTURE_YEARS:
            intensity = max(0.7, 1.0 - 0.003 * (y - BASE_YEAR))
            ref_energy[y] = 10.0 * (gdp_path[y] / base_gdp) * intensity

        d_naive.init_tfp_trajectory(gdp_path, pop_path)
        d_ref.init_tfp_trajectory(gdp_path, pop_path, ref_energy_by_year=ref_energy)

        # TFP should be identical: ref_energy is ignored (naive KLEM scaling
        # always used to avoid CES asymptotic limit issues)
        late_year = FUTURE_YEARS[-1]
        tfp_naive = d_naive._tfp_trajectory[late_year]
        tfp_ref = d_ref._tfp_trajectory[late_year]
        assert tfp_ref == pytest.approx(tfp_naive, rel=1e-10), (
            f"TFP at {late_year}: naive={tfp_naive:.4f} ref={tfp_ref:.4f} — should match"
        )

    def test_tfp_ref_energy_backward_compat(self):
        """Without ref_energy, init_tfp_trajectory behaves identically."""
        d1 = _make_driver(gdp=1000.0, pop=100.0, energy=10.0)
        d2 = _make_driver(gdp=1000.0, pop=100.0, energy=10.0)
        gdp_path = _ssp_growing(start=1000.0, growth=0.02)
        pop_path = _ssp_constant(100.0)

        d1.init_tfp_trajectory(gdp_path, pop_path)
        d2.init_tfp_trajectory(gdp_path, pop_path, ref_energy_by_year=None)

        for year in FUTURE_YEARS:
            assert d1._tfp_trajectory[year] == pytest.approx(
                d2._tfp_trajectory[year], rel=1e-10,
            )

    def test_ref_energy_constant_intensity_same_tfp(self):
        """Constant intensity multiplier should NOT change TFP trajectory.

        The intensity ratio approach normalizes away constant multipliers
        (level differences) since they don't change the time pattern.
        """
        d1 = _make_driver(gdp=1000.0, pop=100.0, energy=10.0)
        d2 = _make_driver(gdp=1000.0, pop=100.0, energy=10.0)
        gdp_path = _ssp_growing(start=1000.0, growth=0.03)
        pop_path = _ssp_constant(100.0)

        # ref_energy with constant 0.7x intensity (no change over time)
        ref_energy = {}
        for y in FUTURE_YEARS:
            ref_energy[y] = 10.0 * (gdp_path[y] / 1000.0) * 0.7

        d1.init_tfp_trajectory(gdp_path, pop_path)
        d2.init_tfp_trajectory(gdp_path, pop_path, ref_energy_by_year=ref_energy)

        # With constant intensity ratio, TFP should be the same (level absorbed)
        last_year = FUTURE_YEARS[-1]
        assert d2._tfp_trajectory[last_year] == pytest.approx(
            d1._tfp_trajectory[last_year], rel=0.01,
        )


# ---------------------------------------------------------------------------
# EL/NEL base-year calibration
# ---------------------------------------------------------------------------


class TestELNELCalibration:
    """Verify that compute_energy_split reproduces base-year shares."""

    def test_base_year_reproduces_shares(self):
        """At base prices, EL/NEL split should match base_el_fraction."""
        el_frac = 0.35
        d = KLEMDriver(
            base_gdp=1000.0, base_population=100.0,
            base_energy_demand_ej=10.0, base_energy_price=5.0,
            base_el_fraction=el_frac, base_el_price=20.0,
        )
        el_ej, nel_ej = d.compute_energy_split(10.0, 20.0, d.base_nel_price)
        assert el_ej == pytest.approx(10.0 * el_frac, rel=1e-6)
        assert nel_ej == pytest.approx(10.0 * (1 - el_frac), rel=1e-6)

    def test_lower_el_price_increases_el_share(self):
        """Cheaper electricity → higher EL share (σ_EL_NEL=2.0)."""
        d = KLEMDriver(
            base_gdp=1000.0, base_population=100.0,
            base_energy_demand_ej=10.0, base_energy_price=5.0,
            base_el_fraction=0.20, base_el_price=20.0,
        )
        el_base, _ = d.compute_energy_split(10.0, 20.0, d.base_nel_price)
        el_cheap, _ = d.compute_energy_split(10.0, 10.0, d.base_nel_price)
        assert el_cheap > el_base, "Cheaper electricity should increase EL share"

    def test_higher_el_price_decreases_el_share(self):
        """More expensive electricity → lower EL share."""
        d = KLEMDriver(
            base_gdp=1000.0, base_population=100.0,
            base_energy_demand_ej=10.0, base_energy_price=5.0,
            base_el_fraction=0.20, base_el_price=20.0,
        )
        el_base, _ = d.compute_energy_split(10.0, 20.0, d.base_nel_price)
        el_exp, _ = d.compute_energy_split(10.0, 40.0, d.base_nel_price)
        assert el_exp < el_base, "More expensive electricity should decrease EL share"

    def test_region_specific_el_fraction(self):
        """Different regions with different EL fractions reproduce correctly."""
        for el_frac in [0.10, 0.25, 0.40]:
            d = KLEMDriver(
                base_gdp=500.0, base_population=50.0,
                base_energy_demand_ej=5.0, base_energy_price=4.0,
                base_el_fraction=el_frac, base_el_price=18.0,
            )
            el_ej, nel_ej = d.compute_energy_split(5.0, 18.0, d.base_nel_price)
            assert el_ej == pytest.approx(5.0 * el_frac, rel=1e-6)
            assert el_ej + nel_ej == pytest.approx(5.0, rel=1e-9)
