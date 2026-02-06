"""Stock turnover model for gradual fleet/capacity transition.

Technology shares don't switch instantly — existing stock decays at
sector-specific rates.  New investment follows logit-determined target
shares, blending with existing stock.

    NewStock_i = OldStock_i + (TargetShare_i - OldStock_i) * (dt / tau)
"""

from __future__ import annotations

import numpy as np

from ghim.config import TIMESTEP


def apply_stock_turnover(
    current_shares: np.ndarray,
    target_shares: np.ndarray,
    dt: int = TIMESTEP,
    turnover_time: float = 30.0,
) -> np.ndarray:
    """Blend current stock shares toward logit-determined target shares.

    Parameters
    ----------
    current_shares : array of shape (n,)
        Stock/fleet shares from previous period (should sum to 1).
    target_shares : array of shape (n,)
        Ideal shares from logit for new investment (should sum to 1).
    dt : int
        Timestep in years.
    turnover_time : float
        Characteristic replacement time in years for this sector.

    Returns
    -------
    ndarray of shape (n,)
        Blended shares, renormalized to sum to 1.
    """
    current_shares = np.asarray(current_shares, dtype=float)
    target_shares = np.asarray(target_shares, dtype=float)

    blend_rate = min(float(dt) / turnover_time, 1.0)
    new_shares = current_shares + blend_rate * (target_shares - current_shares)

    # Ensure non-negative and renormalize
    new_shares = np.maximum(new_shares, 0.0)
    total = new_shares.sum()
    if total > 0:
        new_shares /= total
    return new_shares
