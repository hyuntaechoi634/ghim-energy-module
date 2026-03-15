"""Fixed-point solvers for the GHIM model.

Solver ABC defines the interface: solve(model, state) -> PeriodState.

DampedSolver (Phase 1):  x_{n+1} = alpha * F(x) + (1-alpha) * x
  - Guaranteed convergence when alpha < 1/L (L = Lipschitz constant).
  - Typical alpha = 0.3-0.5.

The solver iterates on a state vector subset:
  - rs.gdp per region
  - rs.carrier_prices[ELECTRICITY, H2, HEAT] per region
  - state.world_prices[fuel] global
  Total: 4 * N_regions + N_traded_fuels dimensions.

Everything else is derived inside F(x).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import TYPE_CHECKING

from ghim.core.carrier import Carrier
from ghim.core.config import TRADED_FUELS
from ghim.core.state import PeriodState

if TYPE_CHECKING:
    from ghim.model import GHIMModel

logger = logging.getLogger(__name__)

# Carriers whose prices are solved (secondary energy carriers)
SOLVED_CARRIERS = [Carrier.ELECTRICITY, Carrier.H2, Carrier.HEAT]

# Trade-driven carriers: damped more conservatively to break feedback loop
# (trade → raw_fuel_prices → carrier_prices → demands → trade)
TRADE_CARRIERS = [Carrier.COAL, Carrier.OIL, Carrier.GAS]
TRADE_DEMAND_CARRIERS = [Carrier.COAL, Carrier.GAS, Carrier.LIQUIDS]


class Solver(ABC):
    """Abstract solver: find fixed point F(x*) = x*."""

    @abstractmethod
    def solve(self, model: GHIMModel, state: PeriodState) -> PeriodState:
        ...


class DampedSolver(Solver):
    """Damped fixed-point iteration: x_{n+1} = alpha * F(x) + (1-alpha) * x.

    Damps only the state vector components (GDP, secondary prices, world prices).
    Derived fields (demands, generation, emissions) come from the latest F(x).

    World prices use a separate (lower) damping factor to handle trade supply
    curve discontinuities at grade boundaries.  Convergence is declared when
    carrier prices (the economically meaningful variables) stabilize; world
    price residual is logged but does not block convergence.
    """

    def __init__(
        self,
        alpha: float = 0.4,
        tol: float = 1e-3,
        max_iter: int = 50,
        skip_gdp: bool = False,
        world_price_alpha: float | None = None,
    ) -> None:
        self.alpha = alpha
        self.tol = tol
        self.max_iter = max_iter
        self.skip_gdp = skip_gdp
        # World prices damped more conservatively (supply curve grade jumps)
        self.world_price_alpha = world_price_alpha if world_price_alpha is not None else alpha * 0.15

    def solve(self, model: GHIMModel, state: PeriodState) -> PeriodState:
        x = state
        prev_carrier_resid = float("inf")
        effective_alpha = self.alpha
        # Track best state (lowest carrier residual) for fallback
        best_x: PeriodState | None = None
        best_carrier = float("inf")
        for n in range(self.max_iter):
            x_new = model.F(x)
            carrier_resid, world_resid = self._residual(x, x_new)
            logger.debug(
                "Period %d iter %d: carrier=%.6f world=%.6f alpha=%.3f",
                x.period, n, carrier_resid, world_resid, effective_alpha,
            )
            # Track best state from second half of iterations
            if n >= self.max_iter // 2 and carrier_resid < best_carrier:
                best_carrier = carrier_resid
                best_x = x_new
            # Converge on carrier prices (primary economic variables)
            if carrier_resid < self.tol:
                if world_resid > 0.05:
                    logger.debug(
                        "Period %d carrier converged but world_resid=%.4f",
                        x.period, world_resid,
                    )
                logger.info(
                    "Period %d converged in %d iterations (carrier=%.6f, world=%.6f)",
                    x.period, n + 1, carrier_resid, world_resid,
                )
                return x_new
            # Adaptive alpha: reduce when oscillating, recover when improving
            if n > 0 and carrier_resid > prev_carrier_resid * 0.95:
                effective_alpha = max(effective_alpha * 0.7, 0.05)
            elif n > 0 and carrier_resid < prev_carrier_resid * 0.5:
                effective_alpha = min(effective_alpha * 1.1, self.alpha)
            x = self._damp(x, x_new, effective_alpha)
            prev_carrier_resid = carrier_resid
        logger.warning(
            "Period %d did NOT converge after %d iterations (carrier=%.6f, world=%.6f)",
            x.period, self.max_iter, carrier_resid, world_resid,
        )
        # Return best state from second half if better than last
        if best_x is not None and best_carrier < carrier_resid:
            return best_x
        return x

    def _residual(self, old: PeriodState, new: PeriodState) -> tuple[float, float]:
        """Max relative change for carrier prices and world prices (separate).

        Returns (carrier_residual, world_residual).
        """
        carrier_change = 0.0
        for name in old.regions:
            o, n = old.regions[name], new.regions[name]
            # GDP (skip when exogenous — it's set externally, not solved)
            if not self.skip_gdp and o.gdp > 0:
                carrier_change = max(carrier_change, abs(n.gdp - o.gdp) / o.gdp)
            # Secondary carrier prices
            for c in SOLVED_CARRIERS:
                p0 = o.carrier_prices.get(c, 1.0)
                p1 = n.carrier_prices.get(c, p0)
                if p0 > 0:
                    carrier_change = max(carrier_change, abs(p1 - p0) / p0)
        # World prices (separate)
        world_change = 0.0
        for fuel in TRADED_FUELS:
            p0 = old.world_prices.get(fuel, 1.0)
            p1 = new.world_prices.get(fuel, p0)
            if p0 > 0:
                world_change = max(world_change, abs(p1 - p0) / p0)
        return carrier_change, world_change

    def _damp(self, old: PeriodState, new: PeriodState, alpha: float | None = None) -> PeriodState:
        """Damp state vector components. Derived fields come from new."""
        result = deepcopy(new)
        a = alpha if alpha is not None else self.alpha
        a_world = min(self.world_price_alpha, a)
        for name in old.regions:
            o = old.regions[name]
            r = result.regions[name]
            # GDP: keep F(x) output directly when exogenous
            if not self.skip_gdp:
                r.gdp = a * r.gdp + (1 - a) * o.gdp
            # Secondary carrier prices
            for c in SOLVED_CARRIERS:
                r.carrier_prices[c] = (
                    a * r.carrier_prices.get(c, 0.0)
                    + (1 - a) * o.carrier_prices.get(c, 0.0)
                )
            # Trade-driven raw_fuel_prices (Step 4 reads these for LCOE)
            for c in TRADE_CARRIERS:
                old_raw = o.raw_fuel_prices.get(c, 0.0)
                new_raw = r.raw_fuel_prices.get(c, old_raw)
                if old_raw > 0:
                    r.raw_fuel_prices[c] = (
                        a_world * new_raw + (1 - a_world) * old_raw
                    )
            # Trade-driven carrier_prices (Step 3 reads these for demands)
            for c in TRADE_DEMAND_CARRIERS:
                old_cp = o.carrier_prices.get(c, 0.0)
                new_cp = r.carrier_prices.get(c, old_cp)
                if old_cp > 0:
                    r.carrier_prices[c] = (
                        a_world * new_cp + (1 - a_world) * old_cp
                    )
        # World prices (more conservative damping)
        for fuel in TRADED_FUELS:
            result.world_prices[fuel] = (
                a_world * result.world_prices.get(fuel, 0.0)
                + (1 - a_world) * old.world_prices.get(fuel, 0.0)
            )
        return result
