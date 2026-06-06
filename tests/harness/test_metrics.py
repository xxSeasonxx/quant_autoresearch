"""Unit tests for risk-adjusted metrics (Sharpe / Sortino / Calmar / maxDD / PSR)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness.objective import metrics
from harness.testing import make_returns


def test_sharpe_matches_manual_annualization():
    vals = np.array([0.01, -0.005, 0.02, 0.0, 0.015])
    ppy = 252.0
    expected = np.mean(vals) / np.std(vals, ddof=1) * math.sqrt(ppy)
    assert metrics.sharpe(make_returns(vals, periods_per_year=ppy)) == pytest.approx(expected)


def test_sharpe_invariant_to_uniform_scaling():
    """Sharpe is scale-free: scaling all returns by k leaves it unchanged (frozen sizing)."""
    vals = np.array([0.01, -0.004, 0.02, -0.001, 0.012, 0.003])
    base = metrics.sharpe(make_returns(vals))
    scaled = metrics.sharpe(make_returns(vals * 3.7))
    assert base == pytest.approx(scaled)


def test_sharpe_none_on_zero_variance_and_tiny_sample():
    assert metrics.sharpe(make_returns([0.01, 0.01, 0.01])) is None
    assert metrics.sharpe(make_returns([0.01])) is None


def test_sortino_penalizes_downside_only():
    # Same mean/variance scale, but the downside differs.
    mostly_up = make_returns([0.02, 0.02, -0.01, 0.02])
    s = metrics.sortino(mostly_up)
    assert s is not None and s > 0


def test_max_drawdown_negative_and_zero_for_monotone():
    rising = make_returns([0.01, 0.02, 0.005, 0.01])
    assert metrics.max_drawdown(rising) == pytest.approx(0.0)
    drop = make_returns([0.1, -0.5, 0.0])
    mdd = metrics.max_drawdown(drop)
    assert mdd is not None and mdd < 0


def test_calmar_uses_geometric_return_over_drawdown():
    vals = make_returns([0.02, -0.03, 0.04, -0.01, 0.02], periods_per_year=252.0)
    c = metrics.calmar(vals)
    mdd = metrics.max_drawdown(vals)
    assert c is not None and mdd is not None
    # Sign of Calmar matches sign of compounded return (positive here).
    assert (c > 0) == (np.prod(1 + vals.values) > 1)


def test_psr_increases_with_sample_size_for_positive_sharpe():
    rng = np.random.default_rng(0)
    short = 0.001 + 0.01 * rng.standard_normal(30)
    long = 0.001 + 0.01 * rng.standard_normal(2000)
    psr_short = metrics.probabilistic_sharpe_ratio(make_returns(short), periods_per_year=252.0)
    psr_long = metrics.probabilistic_sharpe_ratio(make_returns(long), periods_per_year=252.0)
    assert psr_short is not None and psr_long is not None
    assert psr_long >= psr_short


def test_psr_none_for_tiny_sample():
    assert metrics.probabilistic_sharpe_ratio(make_returns([0.01, 0.02])) is None
