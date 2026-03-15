"""EmissionsCapWrapper — bisection on carbon price to hit an emissions cap.

Wraps any Solver.  Outside F(x), outside the fixed-point loop.
Finds the carbon price τ such that global_emissions(τ) ≤ cap.

Design principle (§3): Solve Less — bisection on a monotonic function.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from ghim.core.state import PeriodState
from ghim.policy import CarbonPricePolicy, PolicyScenario

logger = logging.getLogger(__name__)


class EmissionsCapWrapper:
    """Bisection wrapper: find carbon price that achieves an emissions cap.

    Parameters
    ----------
    solver : Solver
        Inner solver (e.g. DampedSolver).
    tol : float
        Relative tolerance for cap matching (default 2%).
    max_iter : int
        Maximum bisection iterations.
    price_floor : float
        Lower bound for carbon price search ($/tCO2).
    price_ceiling : float
        Upper bound for carbon price search ($/tCO2).
    """

    def __init__(
        self,
        solver: Any,
        tol: float = 0.02,
        max_iter: int = 20,
        price_floor: float = 0.0,
        price_ceiling: float = 2000.0,
    ) -> None:
        self.solver = solver
        self.tol = tol
        self.max_iter = max_iter
        self.price_floor = price_floor
        self.price_ceiling = price_ceiling

    def solve(
        self,
        model: Any,
        state: PeriodState,
        cap_gtco2eq: float,
    ) -> PeriodState:
        """Solve with bisection to find carbon price meeting emissions cap.

        Parameters
        ----------
        model : GHIMModel
        state : PeriodState
            Initial state for this period.
        cap_gtco2eq : float
            Emissions cap in GtCO2eq.

        Returns
        -------
        PeriodState with emissions ≤ cap (within tolerance).
        """
        period = state.period

        # Ensure model has a PolicyScenario
        if model.policy is None:
            model.policy = PolicyScenario()

        def emissions_at_price(price: float) -> tuple[float, PeriodState]:
            """Run model at given carbon price, return (emissions_gt, solved_state)."""
            model.policy.carbon_price = CarbonPricePolicy(
                trajectory={period: price}
            )
            solved = self.solver.solve(model, deepcopy(state))
            return solved.global_emissions, solved

        # Check if cap is already met at zero price
        em_floor, result_floor = emissions_at_price(self.price_floor)
        if em_floor <= cap_gtco2eq:
            logger.info(
                "Period %d: emissions %.2f Gt ≤ cap %.2f Gt at price $%.0f",
                period, em_floor, cap_gtco2eq, self.price_floor,
            )
            return result_floor

        # Check if ceiling is sufficient
        em_ceil, result_ceil = emissions_at_price(self.price_ceiling)
        if em_ceil > cap_gtco2eq:
            logger.warning(
                "Period %d: emissions %.2f Gt > cap %.2f Gt even at $%.0f/tCO2",
                period, em_ceil, cap_gtco2eq, self.price_ceiling,
            )
            return result_ceil

        # Bisection
        lo, hi = self.price_floor, self.price_ceiling
        best_result = result_ceil

        for i in range(self.max_iter):
            mid = (lo + hi) / 2.0
            em_mid, result_mid = emissions_at_price(mid)

            logger.debug(
                "Bisection iter %d: price=$%.1f, emissions=%.3f Gt (cap=%.3f)",
                i, mid, em_mid, cap_gtco2eq,
            )

            if em_mid > cap_gtco2eq:
                lo = mid
            else:
                hi = mid
                best_result = result_mid

            # Check convergence
            if abs(em_mid - cap_gtco2eq) / max(cap_gtco2eq, 0.01) < self.tol:
                logger.info(
                    "Period %d: cap bisection converged at $%.1f/tCO2 "
                    "(emissions=%.3f Gt, cap=%.3f Gt, iter=%d)",
                    period, mid, em_mid, cap_gtco2eq, i + 1,
                )
                return result_mid

        logger.warning(
            "Period %d: cap bisection did not converge after %d iterations "
            "(price=$%.1f, emissions=%.3f Gt, cap=%.3f Gt)",
            period, self.max_iter, (lo + hi) / 2, best_result.global_emissions,
            cap_gtco2eq,
        )
        return best_result
