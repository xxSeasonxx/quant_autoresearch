"""Serial-correlation-robust bootstrap primitives (shared by the audit + the Lockbox).

Both anti-overfit walls bootstrap a statistic of a per-period return series that has MEMORY
(serial correlation). Getting that memory into the resample — and into the variance scale of
the statistic — is what keeps their error rates controlled. Two failures hid here before:

- a fixed ``b ≈ n**(1/3)`` block is too short to carry within-trial serial correlation once the
  AR(1) coefficient φ ≥ 0.3, so the bootstrap null/CI under-widened and noise graduated /
  confirmed above the nominal level;
- an iid standard error (``std/sqrt(n)``) under-states the variance of a sample mean under
  dependence, so a studentized statistic built on it is not pivotal.

This module is the single, tested home for the corrections so the audit and the Lockbox share
one implementation (they must agree to share one statistical guarantee):

- ``politis_white_block`` — the data-driven circular-block length (grows with the dependence);
- ``newey_west_lrv`` / ``nw_lag`` — the HAC long-run variance and its automatic bandwidth, the
  serial-correlation-corrected variance of the sample mean;
- ``circular_block_indices`` — one circular-block index vector (the shared-index draw).

Pure numpy: no scipy, no RNG state of its own (the caller passes a seeded ``Generator``), no
clock. No ``quant_strategies`` import.
"""

from __future__ import annotations

import math

import numpy as np

_EPS = 1e-12


def nw_lag(n: int) -> int:
    """Automatic Newey-West truncation lag ``ceil(4·(n/100)**(2/9))`` (Newey & West 1994).

    The standard non-parametric bandwidth for a HAC long-run-variance estimator. Grows slowly
    with the sample so the Bartlett kernel spans enough autocovariances to capture the serial
    correlation while staying consistent. Clamped to ``[0, n-1]``.
    """
    if n < 2:
        return 0
    return int(min(max(0, math.ceil(4.0 * (n / 100.0) ** (2.0 / 9.0))), n - 1))


def newey_west_lrv(matrix: np.ndarray, lag: int) -> np.ndarray:
    """Per-column Newey-West long-run variance (HAC, Bartlett kernel) of ``matrix``.

    ``LRV_j = γ_0 + 2·Σ_{h=1}^{lag} (1 − h/(lag+1))·γ_h`` per column, where ``γ_h`` is the
    lag-``h`` autocovariance (1/n normalization). This is the serial-correlation-corrected
    variance of a single observation whose scaled version ``LRV/n`` is the variance of the
    sample MEAN under dependence — unlike the iid ``σ²/n`` it does not collapse under AR(p)
    memory. The Bartlett weights guarantee a non-negative estimate. Returns a length-K vector.
    """
    n = matrix.shape[0]
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    lrv = np.einsum("ij,ij->j", centered, centered) / n  # γ_0
    for h in range(1, lag + 1):
        weight = 1.0 - h / (lag + 1)
        gamma_h = np.einsum("ij,ij->j", centered[h:], centered[:-h]) / n
        lrv = lrv + 2.0 * weight * gamma_h
    return lrv


def politis_white_block(series: np.ndarray) -> int:
    """Politis & White (2004) automatic block length for the circular block bootstrap.

    Data-driven ``b̂`` from the series' own autocorrelation, replacing the fixed ``n**(1/3)``
    (too short to carry serial correlation once φ ≥ 0.3). The optimal circular-block length
    scales as ``(2·Ĝ² / D̂_CB)**(1/3)·n**(1/3)`` where ``Ĝ`` and ``D̂_CB`` are flat-top
    lag-window functionals of the autocorrelations; ``b̂`` therefore GROWS with the serial
    dependence (≈1 for white noise, tens of bars for strong AR(1)), so the block carries the
    memory the variance scale expects. Clamped to ``[1, n]``.
    """
    x = np.asarray(series, dtype=np.float64)
    n = x.size
    if n < 4:
        return 1
    xc = x - x.mean()
    gamma0 = float(np.dot(xc, xc) / n)
    if gamma0 <= _EPS:
        return 1
    # Correlogram cutoff: the largest lag with a "significant" autocorrelation, via the standard
    # flat-top rule (first run of K_n consecutive insignificant correlations).
    k_n = max(5, int(math.ceil(math.sqrt(math.log10(n)))))
    crit = 2.0 * math.sqrt(math.log10(n) / n)
    m_max = int(math.ceil(math.sqrt(n))) + k_n
    rho = np.zeros(m_max + 1, dtype=np.float64)
    for h in range(1, m_max + 1):
        rho[h] = float(np.dot(xc[h:], xc[:-h]) / n) / gamma0
    m_hat = m_max
    for m in range(1, m_max - k_n + 1):
        if np.all(np.abs(rho[m + 1 : m + 1 + k_n]) < crit):
            m_hat = m
            break
    big_m = max(1, min(2 * m_hat, m_max))
    lags = np.arange(1, big_m + 1)
    ratio = lags / big_m
    # Flat-top (trapezoidal) lag window: 1 for |t|≤1/2, tapering to 0 by |t|=1.
    lam = np.where(ratio <= 0.5, 1.0, np.where(ratio <= 1.0, 2.0 * (1.0 - ratio), 0.0))
    rk = rho[1 : big_m + 1]
    g_hat = 2.0 * float(np.sum(lam * lags * rk))
    d_cb = (4.0 / 3.0) * (1.0 + 2.0 * float(np.sum(lam * rk))) ** 2
    if d_cb <= _EPS:
        return 1
    b = ((2.0 * g_hat**2) / d_cb) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    return int(min(max(1, int(round(b))), n))


def circular_block_indices(rng: np.random.Generator, n: int, block: int) -> np.ndarray:
    """One circular-block index vector of length ``n`` for the (shared-index) block bootstrap.

    Draws ``ceil(n/block)`` random block starts in ``[0, n)`` and lays down contiguous blocks of
    length ``block`` with wrap-around (circular), then truncates to ``n``. Applying the SAME
    index vector to every column of a matrix is what preserves cross-column co-movement at each
    resampled time (the shared-index scheme).
    """
    if n <= 0:
        return np.empty(0, dtype=np.intp)
    block = max(1, int(block))
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=n_blocks)
    offsets = np.arange(block)
    idx = ((starts[:, None] + offsets[None, :]) % n).reshape(-1)[:n]
    return idx.astype(np.intp)
