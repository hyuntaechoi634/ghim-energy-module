"""Logit-based discrete choice for technology competition.

Implements two variants following GCAM's approach:

1. Relative Cost Logit:
    share_i = alpha_i * P_i^beta / sum_j(alpha_j * P_j^beta)

2. Absolute Cost Logit:
    share_i = alpha_i * exp(beta * P_i / P_0) / sum_j(alpha_j * exp(beta * P_j / P_0))

All computations use log-space for numerical stability.
"""

from __future__ import annotations

import numpy as np


def relative_cost_logit(
    costs: np.ndarray,
    share_weights: np.ndarray,
    logit_exp: float,
) -> np.ndarray:
    """Compute market shares using the relative cost logit.

    Parameters
    ----------
    costs : array of shape (n,)
        Cost/price of each option.  Must be positive.
    share_weights : array of shape (n,)
        Calibrated share weights (alpha_i).  Must be positive.
    logit_exp : float
        Logit exponent (beta).  Typically negative (e.g. -3).

    Returns
    -------
    ndarray of shape (n,)
        Market shares (sum to 1).
    """
    costs = np.asarray(costs, dtype=float)
    share_weights = np.asarray(share_weights, dtype=float)

    # Ensure costs and weights are strictly positive for log-space computation
    costs = np.maximum(costs, 1e-10)
    share_weights = np.maximum(share_weights, 1e-10)

    # Log-space: log(unnorm_share_i) = log(alpha_i) + beta * log(P_i)
    log_unnorm = np.log(share_weights) + logit_exp * np.log(costs)
    # Subtract max for numerical stability
    log_unnorm -= log_unnorm.max()
    unnorm = np.exp(log_unnorm)
    return unnorm / unnorm.sum()


def absolute_cost_logit(
    costs: np.ndarray,
    share_weights: np.ndarray,
    logit_exp: float,
    base_value: float = 1.0,
) -> np.ndarray:
    """Compute market shares using the absolute cost logit.

    Parameters
    ----------
    costs : array of shape (n,)
        Cost/price of each option.
    share_weights : array of shape (n,)
        Calibrated share weights (alpha_i).
    logit_exp : float
        Logit exponent (beta). Typically negative.
    base_value : float
        Normalization scale P_0.

    Returns
    -------
    ndarray of shape (n,)
        Market shares (sum to 1).
    """
    costs = np.asarray(costs, dtype=float)
    share_weights = np.asarray(share_weights, dtype=float)

    # Log-space: log(unnorm_i) = log(alpha_i) + beta * P_i / P_0
    log_unnorm = np.log(share_weights) + logit_exp * costs / base_value
    log_unnorm -= log_unnorm.max()
    unnorm = np.exp(log_unnorm)
    return unnorm / unnorm.sum()


def logit_shares(
    costs: np.ndarray,
    share_weights: np.ndarray = None,
    logit_exp: float = None,
    mode: str = "relative",
    base_value: float = 1.0,
    pref_factors: np.ndarray = None,
    scale_k: float = None,
    alpha: np.ndarray | None = None,
) -> np.ndarray:
    """Unified interface for logit share computation.

    Parameters
    ----------
    costs : array of shape (n,)
    share_weights : array (required for relative/absolute modes)
    logit_exp : float (required for relative/absolute/relative_pref modes)
    mode : {"relative", "absolute", "preference", "relative_pref"}
    base_value : float (absolute mode only)
    pref_factors : array (preference and relative_pref modes)
    scale_k : float (preference and relative_pref modes)
    alpha : array (relative_pref mode only)

    Returns
    -------
    ndarray of shape (n,)
        Market shares.
    """
    if mode == "preference":
        return preference_logit(costs, pref_factors, scale_k)
    elif mode == "relative":
        return relative_cost_logit(costs, share_weights, logit_exp)
    elif mode == "absolute":
        return absolute_cost_logit(costs, share_weights, logit_exp, base_value)
    elif mode == "relative_pref":
        return relative_pref_logit(costs, pref_factors, scale_k, logit_exp, alpha)
    else:
        raise ValueError(f"Unknown logit mode: {mode!r}")


def logit_calibrate(
    base_shares: np.ndarray,
    base_costs: np.ndarray,
    logit_exp: float,
    mode: str = "relative",
    base_value: float = 1.0,
) -> np.ndarray:
    """Calibrate share weights to reproduce observed base-year shares.

    For relative cost logit:
        alpha_i = S_i / P_i^beta  (then normalized so max = 1)

    For absolute cost logit:
        alpha_i = S_i / exp(beta * P_i / P_0)

    Parameters
    ----------
    base_shares : array of shape (n,)
        Observed market shares in base year (must sum to 1).
    base_costs : array of shape (n,)
        Observed costs in base year.
    logit_exp : float
        Logit exponent.
    mode : {"relative", "absolute"}
    base_value : float
        Normalization scale (absolute mode only).

    Returns
    -------
    ndarray of shape (n,)
        Calibrated share weights, normalized so the largest is 1.0.
    """
    base_shares = np.asarray(base_shares, dtype=float)
    base_costs = np.asarray(base_costs, dtype=float)

    if mode == "relative":
        raw = base_shares / (base_costs ** logit_exp)
    elif mode == "absolute":
        raw = base_shares / np.exp(logit_exp * base_costs / base_value)
    else:
        raise ValueError(f"Unknown logit mode: {mode!r}")

    # Normalize so the largest weight = 1 (GCAM convention)
    return raw / raw.max()


# ---------------------------------------------------------------------------
# MERGE-style preference factor logit
# ---------------------------------------------------------------------------

def preference_logit(
    costs: np.ndarray,
    pref_factors: np.ndarray,
    scale_k: float,
) -> np.ndarray:
    """Compute market shares using MERGE-style preference factor logit.

    Share_i = exp(-k * (Cost_i + Pref_i)) / sum_j exp(-k * (Cost_j + Pref_j))

    Parameters
    ----------
    costs : array of shape (n,)
        Levelized cost of each option ($/GJ).
    pref_factors : array of shape (n,)
        Preference adder for each option ($/GJ equivalent).
        Positive = penalty (disliked), negative = bonus (preferred).
    scale_k : float
        Sensitivity parameter k > 0.  Larger k = more cost-sensitive.

    Returns
    -------
    ndarray of shape (n,)
        Market shares (sum to 1).
    """
    costs = np.asarray(costs, dtype=float)
    pref_factors = np.asarray(pref_factors, dtype=float)

    log_unnorm = -scale_k * (costs + pref_factors)
    log_unnorm -= log_unnorm.max()  # numerical stability
    unnorm = np.exp(log_unnorm)
    return unnorm / unnorm.sum()


def preference_calibrate(
    base_shares: np.ndarray,
    base_costs: np.ndarray,
    scale_k: float,
    logit_exp: float | None = None,
) -> np.ndarray:
    """Calibrate preference factors from base-year shares (inverse logit).

    When *logit_exp* is ``None`` (default), calibrates for the absolute
    preference logit (MERGE-style):

        ln(S_i / S_r) = -k * ((C_i + P_i) - (C_r + 0))
        P_i = (C_r - C_i) - ln(S_i / S_r) / k

    When *logit_exp* is given (e.g. -4.0), calibrates for the relative
    preference logit:

        ln(S_i / S_r) = β·(ln C_i − ln C_r) − k·(P_i − P_r)
        P_i = -(β/k)·(ln C_i − ln C_r) − ln(S_i / S_r) / k

    Parameters
    ----------
    base_shares : array of shape (n,)
        Observed market shares (must sum to 1, all > 0).
    base_costs : array of shape (n,)
        Observed costs in base year.
    scale_k : float
        Sensitivity parameter k > 0.
    logit_exp : float, optional
        If provided, calibrate for ``relative_pref_logit`` with this β.

    Returns
    -------
    ndarray of shape (n,)
        Calibrated preference factors ($/GJ equivalent).
        Reference technology has Pref = 0.
    """
    base_shares = np.asarray(base_shares, dtype=float)
    base_costs = np.asarray(base_costs, dtype=float)

    # Ensure positive shares for log
    base_shares = np.maximum(base_shares, 1e-10)
    base_shares = base_shares / base_shares.sum()

    ref = int(np.argmax(base_shares))
    log_ratio = np.log(base_shares / base_shares[ref])

    if logit_exp is not None:
        # Relative preference logit calibration
        # From: ln(S_i/S_r) = -k*(P_i - P_r) + β*(ln C_i - ln C_r)
        # With P_r = 0: P_i = (β/k)*(ln C_i - ln C_r) - (1/k)*ln(S_i/S_r)
        base_costs = np.maximum(base_costs, 1e-10)
        log_cost_diff = np.log(base_costs) - np.log(base_costs[ref])
        pref = (logit_exp / scale_k) * log_cost_diff - log_ratio / scale_k
    else:
        # Absolute preference logit calibration (original MERGE-style)
        pref = (base_costs[ref] - base_costs) - log_ratio / scale_k

    pref -= pref[ref]  # ensure reference = 0
    return pref


def relative_pref_logit(
    costs: np.ndarray,
    pref_factors: np.ndarray,
    scale_k: float,
    logit_exp: float,
    alpha: np.ndarray | None = None,
) -> np.ndarray:
    """Compute market shares using relative cost logit with preference factors.

    Combines GCAM-style relative cost competition with MERGE-style
    preference adders and binary availability switches:

        s_i = α_i · exp(-k·P_i) · C_i^β  /  Σ_j α_j · exp(-k·P_j) · C_j^β

    In log-space:

        log_unnorm_i = log(α_i) + (-k · P_i) + β · log(C_i)

    where ``log(0) = -inf`` naturally zeroes out technologies with α=0.

    Parameters
    ----------
    costs : array of shape (n,)
        Levelized cost of each option ($/GJ).  Must be positive.
    pref_factors : array of shape (n,)
        Preference adder P_i for each option ($/GJ).
        Positive = penalty (increases effective cost),
        negative = bonus (decreases effective cost).
    scale_k : float
        Sensitivity parameter k > 0 for preference factors.
    logit_exp : float
        Relative cost exponent β.  Typically negative (e.g. -4.0).
    alpha : array of shape (n,) or None
        Binary availability switches {0, 1}.  None = all available.

    Returns
    -------
    ndarray of shape (n,)
        Market shares (sum to 1).
    """
    costs = np.asarray(costs, dtype=float)
    pref_factors = np.asarray(pref_factors, dtype=float)
    costs = np.maximum(costs, 1e-10)

    if alpha is not None:
        alpha = np.asarray(alpha, dtype=float)
    else:
        alpha = np.ones_like(costs)

    # Log-space computation
    # log(0) = -inf which naturally zeroes out disabled techs
    with np.errstate(divide="ignore"):
        log_alpha = np.where(alpha > 0, np.log(alpha), -np.inf)

    log_unnorm = log_alpha + (-scale_k * pref_factors) + logit_exp * np.log(costs)

    # Check if all -inf (all techs disabled)
    finite_mask = np.isfinite(log_unnorm)
    if not finite_mask.any():
        # All technologies disabled — return uniform (degenerate case)
        return np.ones_like(costs) / len(costs)

    # Subtract max of finite values for numerical stability
    log_unnorm -= log_unnorm[finite_mask].max()
    unnorm = np.exp(log_unnorm)
    total = unnorm.sum()
    if total > 0:
        return unnorm / total
    return np.ones_like(costs) / len(costs)


def preference_decay(
    pref_factors: np.ndarray,
    years_elapsed: int,
    decay_rate: float,
) -> np.ndarray:
    """Decay preference factors toward zero over time.

    Pref_i(t) = Pref_i(base) * (1 - decay_rate)^years_elapsed

    As preferences decay, pure cost competition dominates.
    """
    factor = (1.0 - decay_rate) ** years_elapsed
    return np.asarray(pref_factors, dtype=float) * factor


def logit_average_cost(
    costs: np.ndarray,
    share_weights: np.ndarray,
    logit_exp: float,
    mode: str = "relative",
    base_value: float = 1.0,
) -> float:
    """Compute the share-weighted average cost (sector composite cost).

    Parameters
    ----------
    costs, share_weights, logit_exp, mode, base_value : see above

    Returns
    -------
    float
        Weighted average cost of the sector.
    """
    shares = logit_shares(costs, share_weights, logit_exp, mode, base_value)
    return float(np.dot(shares, costs))
