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
    share_weights: np.ndarray,
    logit_exp: float,
    mode: str = "relative",
    base_value: float = 1.0,
) -> np.ndarray:
    """Unified interface for logit share computation.

    Parameters
    ----------
    costs, share_weights, logit_exp : see above
    mode : {"relative", "absolute"}
    base_value : float
        Only used when mode="absolute".

    Returns
    -------
    ndarray of shape (n,)
        Market shares.
    """
    if mode == "relative":
        return relative_cost_logit(costs, share_weights, logit_exp)
    elif mode == "absolute":
        return absolute_cost_logit(costs, share_weights, logit_exp, base_value)
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
