"""Tests for DampedSolver and Solver ABC."""

import pytest

from ghim.core.carrier import Carrier
from ghim.core.state import PeriodState, RegionState
from ghim.solver.damped import Solver, DampedSolver, SOLVED_CARRIERS


# ===========================================================================
# Solver ABC
# ===========================================================================

class TestSolverABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            Solver()


# ===========================================================================
# DampedSolver
# ===========================================================================

def _make_state(gdp=1000.0, elec_price=20.0, h2_price=15.0, heat_price=10.0,
                world_coal=3.0, world_oil=8.0, world_gas=5.0):
    """Create a simple single-region PeriodState for testing."""
    rs = RegionState(
        gdp=gdp,
        population=100.0,
        carrier_prices={
            Carrier.ELECTRICITY: elec_price,
            Carrier.H2: h2_price,
            Carrier.HEAT: heat_price,
        },
    )
    return PeriodState(
        period=2025,
        regions={"TestRegion": rs},
        world_prices={
            "coal": world_coal,
            "oil": world_oil,
            "gas": world_gas,
        },
    )


class TestDampedSolver:
    def test_init_defaults(self):
        solver = DampedSolver()
        assert solver.alpha == 0.4
        assert solver.tol == 1e-3
        assert solver.max_iter == 50

    def test_custom_params(self):
        solver = DampedSolver(alpha=0.3, tol=1e-4, max_iter=100)
        assert solver.alpha == 0.3
        assert solver.tol == 1e-4
        assert solver.max_iter == 100

    def test_residual_zero_for_identical(self):
        solver = DampedSolver()
        s1 = _make_state()
        s2 = _make_state()
        carrier, world = solver._residual(s1, s2)
        assert carrier == 0.0
        assert world == 0.0

    def test_residual_detects_gdp_change(self):
        solver = DampedSolver()
        s1 = _make_state(gdp=1000.0)
        s2 = _make_state(gdp=1100.0)
        carrier, world = solver._residual(s1, s2)
        assert carrier == pytest.approx(0.1)

    def test_residual_detects_price_change(self):
        solver = DampedSolver()
        s1 = _make_state(elec_price=20.0)
        s2 = _make_state(elec_price=25.0)
        carrier, world = solver._residual(s1, s2)
        assert carrier == pytest.approx(0.25)

    def test_residual_detects_world_price_change(self):
        solver = DampedSolver()
        s1 = _make_state(world_oil=8.0)
        s2 = _make_state(world_oil=10.0)
        carrier, world = solver._residual(s1, s2)
        assert world == pytest.approx(0.25)

    def test_damp_interpolates_gdp(self):
        solver = DampedSolver(alpha=0.5)
        s_old = _make_state(gdp=1000.0)
        s_new = _make_state(gdp=1200.0)
        result = solver._damp(s_old, s_new)
        assert result.regions["TestRegion"].gdp == pytest.approx(1100.0)

    def test_damp_interpolates_prices(self):
        solver = DampedSolver(alpha=0.4)
        s_old = _make_state(elec_price=20.0)
        s_new = _make_state(elec_price=30.0)
        result = solver._damp(s_old, s_new)
        expected = 0.4 * 30.0 + 0.6 * 20.0  # = 24.0
        assert result.regions["TestRegion"].carrier_prices[Carrier.ELECTRICITY] == pytest.approx(expected)

    def test_damp_interpolates_world_prices(self):
        # world_price_alpha defaults to alpha * 0.15 = 0.075
        solver = DampedSolver(alpha=0.5)
        s_old = _make_state(world_coal=3.0)
        s_new = _make_state(world_coal=5.0)
        result = solver._damp(s_old, s_new)
        # a_world = min(0.075, 0.5) = 0.075
        expected = 0.075 * 5.0 + 0.925 * 3.0  # = 3.15
        assert result.world_prices["coal"] == pytest.approx(expected)

    def test_damp_world_prices_explicit_alpha(self):
        solver = DampedSolver(alpha=0.5, world_price_alpha=0.5)
        s_old = _make_state(world_coal=3.0)
        s_new = _make_state(world_coal=5.0)
        result = solver._damp(s_old, s_new)
        assert result.world_prices["coal"] == pytest.approx(4.0)

    def test_converges_on_identity_model(self):
        """If F(x) = x (identity), solver converges in 1 iteration."""
        solver = DampedSolver(alpha=0.5, tol=1e-6, max_iter=10)

        class IdentityModel:
            def F(self, state):
                from copy import deepcopy
                return deepcopy(state)

        state = _make_state()
        result = solver.solve(IdentityModel(), state)
        assert result.regions["TestRegion"].gdp == pytest.approx(1000.0)

    def test_converges_on_contractive_model(self):
        """If F(x) contracts toward a fixed point, solver should converge."""
        solver = DampedSolver(alpha=0.5, tol=1e-3, max_iter=100)

        class ContractiveModel:
            """F moves GDP toward 500."""
            def F(self, state):
                from copy import deepcopy
                new = deepcopy(state)
                for rs in new.regions.values():
                    rs.gdp = 0.5 * rs.gdp + 0.5 * 500.0
                return new

        state = _make_state(gdp=1000.0)
        result = solver.solve(ContractiveModel(), state)
        assert result.regions["TestRegion"].gdp == pytest.approx(500.0, rel=1e-2)

    def test_max_iterations_honored(self):
        """Solver should stop at max_iter even if not converged."""
        call_count = 0

        class DivergentModel:
            def F(self, state):
                nonlocal call_count
                call_count += 1
                from copy import deepcopy
                new = deepcopy(state)
                for rs in new.regions.values():
                    rs.gdp *= 1.1  # diverges
                return new

        solver = DampedSolver(alpha=0.5, tol=1e-6, max_iter=5)
        state = _make_state(gdp=100.0)
        solver.solve(DivergentModel(), state)
        assert call_count == 5

    def test_multiple_regions(self):
        """Solver handles multiple regions."""
        solver = DampedSolver(alpha=0.5, tol=1e-6, max_iter=5)

        state = PeriodState(
            period=2025,
            regions={
                "USA": RegionState(gdp=5000.0, carrier_prices={
                    Carrier.ELECTRICITY: 20.0,
                    Carrier.H2: 15.0,
                    Carrier.HEAT: 10.0,
                }),
                "China": RegionState(gdp=8000.0, carrier_prices={
                    Carrier.ELECTRICITY: 18.0,
                    Carrier.H2: 12.0,
                    Carrier.HEAT: 8.0,
                }),
            },
            world_prices={"coal": 3.0, "oil": 8.0, "gas": 5.0},
        )

        class IdentityModel:
            def F(self, state):
                from copy import deepcopy
                return deepcopy(state)

        result = solver.solve(IdentityModel(), state)
        assert result.regions["USA"].gdp == pytest.approx(5000.0)
        assert result.regions["China"].gdp == pytest.approx(8000.0)
