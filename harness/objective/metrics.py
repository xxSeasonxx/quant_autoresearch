"""Risk-adjusted metrics over a per-period return series (numpy core).

All metrics take net-of-cost per-period returns and an annualization cadence
(``periods_per_year``), matching the bar cadence. Sharpe is the statistic with a
usable sampling distribution (PSR/DSR), so RES ranks on it (FR-C2); Sortino, Calmar,
and max-drawdown are feasibility gates, not the ranking number.

Pure functions, no RNG, no clock — deterministic (NFR-1).
"""

from __future__ import annotations

import math

import numpy as np

from harness.foundation import FoldReturns

# Smallest denominator we treat as "no variance" — avoids div-by-zero blowups while
# keeping a degenerate (flat) series from posting an infinite ratio.
_EPS = 1e-12


def _as_returns(returns: FoldReturns | np.ndarray) -> tuple[np.ndarray, float]:
    """Normalize input to (values, periods_per_year)."""
    if isinstance(returns, FoldReturns):
        values = np.asarray(returns.values, dtype=np.float64)
        return values, float(returns.periods_per_year)
    return np.asarray(returns, dtype=np.float64), math.nan


def sharpe(returns: FoldReturns | np.ndarray, periods_per_year: float | None = None) -> float | None:
    """Annualized Sharpe ratio (risk-free assumed 0; sizing frozen upstream).

    Returns ``None`` when there is no usable sample (fewer than 2 points) or the
    series has no variance.
    """
    values, ppy = _as_returns(returns)
    if periods_per_year is not None:
        ppy = float(periods_per_year)
    if values.size < 2 or not math.isfinite(ppy) or ppy <= 0:
        return None
    sd = float(np.std(values, ddof=1))
    if sd < _EPS:
        return None
    mean = float(np.mean(values))
    return mean / sd * math.sqrt(ppy)


def sortino(returns: FoldReturns | np.ndarray, periods_per_year: float | None = None) -> float | None:
    """Annualized Sortino ratio — downside deviation about a 0 target.

    Returns ``None`` when there is no usable sample or no downside deviation.
    """
    values, ppy = _as_returns(returns)
    if periods_per_year is not None:
        ppy = float(periods_per_year)
    if values.size < 2 or not math.isfinite(ppy) or ppy <= 0:
        return None
    downside = np.minimum(values, 0.0)
    # Mean squared downside about the target, normalized by the full sample count
    # (the conventional Sortino denominator), then annualized.
    downside_var = float(np.mean(downside**2))
    dd = math.sqrt(downside_var)
    if dd < _EPS:
        return None
    mean = float(np.mean(values))
    return mean / dd * math.sqrt(ppy)


def max_drawdown(returns: FoldReturns | np.ndarray) -> float | None:
    """Maximum drawdown of the compounded equity curve, as a negative fraction.

    A flat or rising curve returns 0.0. Returns ``None`` for an empty series.
    """
    values, _ = _as_returns(returns)
    if values.size == 0:
        return None
    equity = np.cumprod(1.0 + values)
    running_max = np.maximum.accumulate(equity)
    drawdowns = equity / running_max - 1.0
    return float(np.min(drawdowns))


def calmar(returns: FoldReturns | np.ndarray, periods_per_year: float | None = None) -> float | None:
    """Calmar ratio — annualized (geometric) return over absolute max drawdown.

    Returns ``None`` when there is no usable sample or drawdown is ~0 (no downside
    to normalize against).
    """
    values, ppy = _as_returns(returns)
    if periods_per_year is not None:
        ppy = float(periods_per_year)
    if values.size < 1 or not math.isfinite(ppy) or ppy <= 0:
        return None
    mdd = max_drawdown(values)
    if mdd is None or abs(mdd) < _EPS:
        return None
    # Geometric (compounded) annualized return.
    total_growth = float(np.prod(1.0 + values))
    if total_growth <= 0:
        return None
    ann_return = total_growth ** (ppy / values.size) - 1.0
    return ann_return / abs(mdd)


def probabilistic_sharpe_ratio(
    returns: FoldReturns | np.ndarray,
    benchmark_sharpe: float = 0.0,
    periods_per_year: float | None = None,
) -> float | None:
    """Probabilistic Sharpe Ratio (PSR) — P(true Sharpe > benchmark_sharpe).

    HELPER ONLY. The PSR *gate* is P2 (FR-C5); this lives here so P2 can wire it
    behind the evidence-sufficiency gate. Skew/kurtosis-adjusted per Bailey & López
    de Prado. Sharpe here is the per-period (non-annualized) ratio; PSR scales by
    sqrt(n-1) over the per-period estimate, so we de-annualize before applying it.

    Returns ``None`` when the sample is too small or has no variance.
    """
    values, ppy = _as_returns(returns)
    if periods_per_year is not None:
        ppy = float(periods_per_year)
    n = values.size
    if n < 3:
        return None
    sd = float(np.std(values, ddof=1))
    if sd < _EPS:
        return None
    mean = float(np.mean(values))
    sr = mean / sd  # per-period Sharpe
    # Per-period benchmark Sharpe (de-annualize the supplied annualized benchmark).
    if math.isfinite(ppy) and ppy > 0:
        sr_star = benchmark_sharpe / math.sqrt(ppy)
    else:
        sr_star = benchmark_sharpe
    # Moments for the skew/kurtosis correction.
    skew = float(_sample_skew(values, mean, sd))
    kurt = float(_sample_kurtosis(values, mean, sd))  # non-excess (normal == 3)
    denom = math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2, _EPS))
    z = (sr - sr_star) * math.sqrt(n - 1) / denom
    return float(_normal_cdf(z))


def _sample_skew(values: np.ndarray, mean: float, sd: float) -> float:
    if sd < _EPS:
        return 0.0
    return float(np.mean(((values - mean) / sd) ** 3))


def _sample_kurtosis(values: np.ndarray, mean: float, sd: float) -> float:
    if sd < _EPS:
        return 3.0
    return float(np.mean(((values - mean) / sd) ** 4))


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
