"""Nested CES (Constant Elasticity of Substitution) production function.

Implements:
    Y = A * [sum_i alpha_i * X_i^rho]^(1/rho)
    where rho = (sigma - 1) / sigma

Special cases:
    sigma = 1  -> Cobb-Douglas: Y = A * prod(X_i^alpha_i)
    sigma -> 0 -> Leontief: Y = A * min(X_i / alpha_i)
"""

from __future__ import annotations

import numpy as np


def _rho(sigma: float) -> float:
    """Convert elasticity of substitution to CES exponent."""
    return (sigma - 1.0) / sigma


def ces_output(
    inputs: np.ndarray,
    alphas: np.ndarray,
    sigma: float,
    scale: float = 1.0,
) -> float:
    """Compute CES aggregate output.

    Parameters
    ----------
    inputs : array of shape (n,)
        Quantities of each input factor.
    alphas : array of shape (n,)
        Share parameters (should sum to 1 for standard CES).
    sigma : float
        Elasticity of substitution. Must be > 0.
    scale : float
        Total factor productivity multiplier A.

    Returns
    -------
    float
        Aggregate output Y.
    """
    inputs = np.asarray(inputs, dtype=float)
    alphas = np.asarray(alphas, dtype=float)

    if sigma < 1e-6:
        # Leontief: Y = A * min(X_i / alpha_i)
        return scale * np.min(inputs / alphas)

    if abs(sigma - 1.0) < 1e-6:
        # Cobb-Douglas: Y = A * prod(X_i^alpha_i)
        return scale * np.prod(inputs ** alphas)

    rho = _rho(sigma)
    inner = np.sum(alphas * inputs ** rho)
    return scale * inner ** (1.0 / rho)


def ces_price(
    prices: np.ndarray,
    alphas: np.ndarray,
    sigma: float,
) -> float:
    """Compute the CES composite (dual) price.

    P = [sum_i alpha_i^sigma * p_i^(1 - sigma)]^(1/(1 - sigma))

    Parameters
    ----------
    prices : array of shape (n,)
        Prices of each input.
    alphas : array of shape (n,)
        Share parameters.
    sigma : float
        Elasticity of substitution.

    Returns
    -------
    float
        Composite price index.
    """
    prices = np.asarray(prices, dtype=float)
    alphas = np.asarray(alphas, dtype=float)

    if sigma < 1e-6:
        # Leontief: P = sum(alpha_i * p_i)
        return np.sum(alphas * prices)

    if abs(sigma - 1.0) < 1e-6:
        # Cobb-Douglas: P = prod((p_i / alpha_i)^alpha_i)
        return np.prod((prices / alphas) ** alphas)

    exp = 1.0 - sigma
    inner = np.sum(alphas ** sigma * prices ** exp)
    return inner ** (1.0 / exp)


def ces_demand(
    output: float,
    price_out: float,
    prices_in: np.ndarray,
    alphas: np.ndarray,
    sigma: float,
) -> np.ndarray:
    """Compute cost-minimizing input demands.

    X_i = alpha_i^sigma * (P / p_i)^sigma * Y

    Parameters
    ----------
    output : float
        Desired output level Y.
    price_out : float
        Composite output price P.
    prices_in : array of shape (n,)
        Input prices.
    alphas : array of shape (n,)
        Share parameters.
    sigma : float
        Elasticity of substitution.

    Returns
    -------
    ndarray of shape (n,)
        Optimal input quantities.
    """
    prices_in = np.asarray(prices_in, dtype=float)
    alphas = np.asarray(alphas, dtype=float)

    if sigma < 1e-6:
        # Leontief: X_i = alpha_i * Y
        return alphas * output

    if abs(sigma - 1.0) < 1e-6:
        # Cobb-Douglas: X_i = alpha_i * P * Y / p_i
        return alphas * price_out * output / prices_in

    return alphas ** sigma * (price_out / prices_in) ** sigma * output


def ces_calibrate(
    base_inputs: np.ndarray,
    base_prices: np.ndarray,
    sigma: float,
) -> np.ndarray:
    """Calibrate CES share parameters from base-year data.

    Given observed input quantities and prices, recover the alpha_i
    coefficients that reproduce the observed cost shares.

    Cost share: s_i = p_i * X_i / sum(p_j * X_j)
    For CES: alpha_i = s_i * (p_i)^(sigma - 1) / sum(s_j * p_j^(sigma-1))

    Parameters
    ----------
    base_inputs : array of shape (n,)
        Observed input quantities.
    base_prices : array of shape (n,)
        Observed input prices.
    sigma : float
        Elasticity of substitution (assumed known).

    Returns
    -------
    ndarray of shape (n,)
        Calibrated alpha parameters (normalized to sum to 1).
    """
    base_inputs = np.asarray(base_inputs, dtype=float)
    base_prices = np.asarray(base_prices, dtype=float)

    # Cost shares
    expenditures = base_prices * base_inputs
    shares = expenditures / expenditures.sum()

    if abs(sigma - 1.0) < 1e-6:
        # Cobb-Douglas: alphas = cost shares
        return shares

    # General CES
    raw = shares * base_prices ** (sigma - 1.0)
    return raw / raw.sum()
