"""Two-factor technology learning curves (LBD + RND) with spillovers.

Cost reduction:
  capex(t) = capex_0 × (Q_eff/Q_0)^(-λ_LBD) × (H_rd/H_0)^(-λ_RND)
  subject to: capex(t) ≥ floor

Where:
  Q_eff = Q_cum + Σ_j φ_ij × Q_cum_j   (effective cumulative with spillovers)
  H_rd  = Σ_τ (1-δ_H)^(t-τ) × RND_τ    (R&D knowledge stock)
  λ     = -ln(1-LR) / ln(2)              (learning exponent from rate)

Phase 1: global learning pool, exogenous RND (IEA when available).
Phase 2+: endogenous RND via Energy Services Nest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ghim.core.config import LearningConfig


# ===================================================================
# Per-tech data structures
# ===================================================================

@dataclass
class TechLearningParams:
    """Immutable per-technology learning parameters (set at registration)."""

    capex_0: float          # $/kW at base year
    cumulative_0: float     # GW (or EJ) at base year
    lbd_exponent: float     # λ_LBD (derived from learning rate)
    rnd_exponent: float     # λ_RND (derived from RND learning rate)
    floor: float            # $/kW minimum cost
    knowledge_0: float      # H_rd at base year (billion $, or index=1.0)


@dataclass
class TechLearningState:
    """Mutable per-technology learning state."""

    cumulative: float       # Q_cum(t) in GW (or EJ)
    knowledge_stock: float  # H_rd(t)
    current_capex: float    # $/kW after learning


def _lr_to_exponent(lr: float) -> float:
    """Convert learning rate (0-1) to CES exponent: λ = -ln(1-LR)/ln(2)."""
    if lr <= 0.0:
        return 0.0
    if lr >= 1.0:
        return 10.0  # practical cap
    return -math.log(1.0 - lr) / math.log(2.0)


# ===================================================================
# Default spillover matrix (Phase 1)
# ===================================================================

DEFAULT_SPILLOVERS: dict[str, dict[str, float]] = {
    # Solar family
    "solar": {"solar_csp": 0.2},
    "solar_csp": {"solar": 0.2},
    # Wind family
    "wind": {"wind_offshore": 0.5},
    "wind_offshore": {"wind": 0.5},
    # CCS family
    "coal_ccs": {"gas_ccs": 0.8, "biomass_ccs": 0.8},
    "gas_ccs": {"coal_ccs": 0.8, "biomass_ccs": 0.8},
    "biomass_ccs": {"coal_ccs": 0.8, "gas_ccs": 0.8},
    # Electrochemical family
    "electrolysis": {"fcev_fc": 0.3},
    "fcev_fc": {"electrolysis": 0.3},
}

# Default RND learning rates (WITCH values, §2.4)
DEFAULT_RND_RATES: dict[str, float] = {
    "solar": 0.15,
    "wind": 0.10,
    "nuclear": 0.08,
    "electrolysis": 0.12,
    "coal_ccs": 0.10,
    "gas_ccs": 0.10,
    "biomass_ccs": 0.10,
    "bev_battery": 0.12,
}

# Default floor fractions (§2.3)
DEFAULT_FLOOR_FRACTIONS: dict[str, float] = {
    "solar": 0.15,
    "wind": 0.25,
    "nuclear": 0.50,
    "electrolysis": 0.20,
    "coal_ccs": 0.30,
    "gas_ccs": 0.30,
    "biomass_ccs": 0.30,
    "geothermal": 0.40,
    "ocean": 0.30,
    "heat_pump": 0.25,
    "h2_dri": 0.30,
}


# ===================================================================
# TechChange — global learning manager
# ===================================================================

class TechChange:
    """Two-factor learning curve manager (global, cross-region).

    Tracks cumulative deployment and R&D knowledge stocks for all
    registered technologies.  Computes cost reduction via LBD + RND
    with cross-technology spillovers.

    One instance per model run (shared across regions).
    """

    def __init__(self, cfg: LearningConfig | None = None):
        cfg = cfg or LearningConfig()
        self.cost_floor_fraction = cfg.cost_floor_fraction
        self.knowledge_depreciation = cfg.knowledge_depreciation
        self.exogenous_rnd = cfg.exogenous_rnd

        self._params: dict[str, TechLearningParams] = {}
        self._state: dict[str, TechLearningState] = {}
        self._spillovers: dict[str, dict[str, float]] = {}

    # -- Registration ----------------------------------------------------

    def register(
        self,
        name: str,
        capex_0: float,
        cumulative_0: float,
        lbd_rate: float = 0.0,
        rnd_rate: float = 0.0,
        floor_fraction: float | None = None,
        knowledge_0: float = 1.0,
    ) -> None:
        """Register a technology for learning.

        Parameters
        ----------
        name : str
            Technology identifier (must be unique).
        capex_0 : float
            Base-year capital cost ($/kW).
        cumulative_0 : float
            Base-year cumulative deployment (GW).
        lbd_rate : float
            LBD learning rate (0-1).
        rnd_rate : float
            RND learning rate (0-1).  0 = no RND effect.
        floor_fraction : float or None
            Minimum cost as fraction of capex_0.
            None → use tech-specific default or global default.
        knowledge_0 : float
            Base-year knowledge stock (index, default 1.0).
        """
        if floor_fraction is None:
            floor_fraction = DEFAULT_FLOOR_FRACTIONS.get(
                name, self.cost_floor_fraction,
            )

        self._params[name] = TechLearningParams(
            capex_0=capex_0,
            cumulative_0=max(cumulative_0, 1e-6),
            lbd_exponent=_lr_to_exponent(lbd_rate),
            rnd_exponent=_lr_to_exponent(rnd_rate),
            floor=capex_0 * floor_fraction,
            knowledge_0=max(knowledge_0, 1e-6),
        )
        self._state[name] = TechLearningState(
            cumulative=max(cumulative_0, 1e-6),
            knowledge_stock=max(knowledge_0, 1e-6),
            current_capex=capex_0,
        )

    def set_spillover(
        self, from_tech: str, to_tech: str, phi: float,
    ) -> None:
        """Set spillover coefficient φ from from_tech to to_tech."""
        self._spillovers.setdefault(to_tech, {})[from_tech] = phi

    def load_default_spillovers(self) -> None:
        """Load the default cross-technology spillover matrix."""
        for tech, targets in DEFAULT_SPILLOVERS.items():
            for target, phi in targets.items():
                self.set_spillover(from_tech=tech, to_tech=target, phi=phi)

    @property
    def tech_names(self) -> list[str]:
        """List of registered technology names."""
        return list(self._params.keys())

    # -- Queries ---------------------------------------------------------

    def effective_cumulative(self, tech: str) -> float:
        """Cumulative deployment including spillover effects.

        Q_eff = Q_cum + Σ_j φ_ji × Q_cum_j
        """
        state = self._state.get(tech)
        if state is None:
            return 0.0
        q_eff = state.cumulative
        spillovers = self._spillovers.get(tech, {})
        for from_tech, phi in spillovers.items():
            from_state = self._state.get(from_tech)
            if from_state is not None:
                q_eff += phi * from_state.cumulative
        return q_eff

    def compute_capex(self, tech: str) -> float:
        """Current capex after LBD + RND learning.

        capex = capex_0 × (Q_eff/Q_0)^(-λ_LBD) × (H/H_0)^(-λ_RND)
        """
        params = self._params.get(tech)
        state = self._state.get(tech)
        if params is None or state is None:
            return 0.0

        capex = params.capex_0

        # LBD factor
        if params.lbd_exponent > 0:
            q_eff = self.effective_cumulative(tech)
            ratio = q_eff / params.cumulative_0
            if ratio > 1.0:
                capex *= ratio ** (-params.lbd_exponent)

        # RND factor
        if params.rnd_exponent > 0:
            h_ratio = state.knowledge_stock / params.knowledge_0
            if h_ratio > 1.0:
                capex *= h_ratio ** (-params.rnd_exponent)

        # Floor
        capex = max(capex, params.floor)

        state.current_capex = capex
        return capex

    def get_capex(self, tech: str) -> float:
        """Get last computed capex (without recomputing)."""
        state = self._state.get(tech)
        return state.current_capex if state is not None else 0.0

    def get_cumulative(self, tech: str) -> float:
        """Get current cumulative deployment."""
        state = self._state.get(tech)
        return state.cumulative if state is not None else 0.0

    def get_knowledge(self, tech: str) -> float:
        """Get current knowledge stock."""
        state = self._state.get(tech)
        return state.knowledge_stock if state is not None else 0.0

    # -- Updates (called between periods) --------------------------------

    def update_deployment(
        self, new_capacity: dict[str, float], timestep: int = 5,
    ) -> None:
        """Add new deployment to cumulative totals.

        Called after each period with global totals (sum across regions).
        new_capacity is in GW (or whatever unit matches cumulative_0).
        """
        for tech, new_cap in new_capacity.items():
            state = self._state.get(tech)
            if state is not None and new_cap > 0:
                state.cumulative += new_cap

    def update_knowledge(
        self, rnd_spending: dict[str, float],
    ) -> None:
        """Update R&D knowledge stocks.

        H(t+1) = (1 − δ_H) × H(t) + RND(t)

        rnd_spending is in billion $/period (or index units matching H_0).
        Called between periods.
        """
        decay = 1.0 - self.knowledge_depreciation
        for tech in self._state:
            state = self._state[tech]
            rnd = rnd_spending.get(tech, 0.0)
            state.knowledge_stock = decay * state.knowledge_stock + rnd

    def compute_all_capex(self) -> dict[str, float]:
        """Recompute and return capex for all registered techs."""
        return {tech: self.compute_capex(tech) for tech in self._params}

    # -- Bulk registration helper ----------------------------------------

    def register_from_technologies(
        self, techs: list, lbd_rates: dict[str, float] | None = None,
    ) -> None:
        """Register from a list of Technology objects (ghim.energy.technology).

        Reads name, capital_cost, base_cumulative, learning_rate from each.
        Optionally override learning rates via lbd_rates dict.
        """
        from ghim.config import LEARNING_RATES

        for t in techs:
            lr = (
                lbd_rates.get(t.name, 0.0)
                if lbd_rates is not None
                else getattr(t, "learning_rate", LEARNING_RATES.get(t.name, 0.0))
            )
            rnd_lr = DEFAULT_RND_RATES.get(t.name, 0.0)
            self.register(
                name=t.name,
                capex_0=t.capital_cost,
                cumulative_0=getattr(t, "base_cumulative", 1.0),
                lbd_rate=lr,
                rnd_rate=rnd_lr if not self.exogenous_rnd else 0.0,
                knowledge_0=1.0,
            )
