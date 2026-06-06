"""AC-9 (factor neutrality) + unit tests for residual-alpha regression (FR-C3).

A pure factor-beta strategy and a pure funding-carry collector residualize to ≈0 alpha.
Funding is carry — a panel column regressed out, never additive PnL.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.objective import factors
from harness.testing import (
    beta_exposed_series,
    factor_series,
    funding_carry_series,
    make_returns,
    noisy_alpha_series,
)


def test_ac9_pure_market_beta_residualizes_to_zero():
    market = factor_series(n=500, sd=0.02, seed=1)
    returns = beta_exposed_series(market, beta=1.3, seed=2)
    result = factors.residualize(returns, {"market": market})
    # Almost all variance explained; residual ≈ 0.
    assert result.r_squared > 0.999
    assert np.allclose(result.residual, 0.0, atol=1e-6)
    # The beta is recovered (~1.3), and there is no usable information ratio.
    assert result.betas["market"] == pytest.approx(1.3, abs=1e-3)


def test_ac9_pure_funding_carry_residualizes_to_zero():
    """Funding is carry: a funding-carry collector has ≈0 residual alpha."""
    funding = factor_series(n=500, sd=0.005, seed=7)
    returns = funding_carry_series(funding, loading=1.0, seed=8)
    result = factors.residualize(returns, {"funding_carry": funding})
    assert result.r_squared > 0.999
    assert np.allclose(result.residual, 0.0, atol=1e-6)


def test_ac9_funding_pnl_is_not_added_back_as_alpha():
    """A strategy that is market beta + funding carry keeps NEITHER as edge."""
    market = factor_series(n=500, sd=0.02, seed=1)
    funding = factor_series(n=500, sd=0.005, seed=7)
    returns = 0.8 * market + 1.0 * funding  # purely explainable by the panel
    panel = {"market": market, "funding_carry": funding}
    result = factors.residualize(returns, panel)
    assert result.r_squared > 0.999
    assert np.allclose(result.residual, 0.0, atol=1e-6)
    # IR of a fully-explained residual is None/degenerate — no edge to rank.
    assert result.information_ratio is None or abs(result.information_ratio) < 1e-3


def test_genuine_residual_alpha_survives_neutralization():
    """A real idiosyncratic edge survives the factor regression with a positive IR."""
    market = factor_series(n=600, sd=0.02, seed=1)
    alpha = noisy_alpha_series(n=600, mean=0.0008, sd=0.004, seed=42)
    returns = 0.9 * market + alpha  # beta PLUS genuine alpha
    result = factors.residualize(returns, {"market": market})
    assert result.information_ratio is not None
    assert result.information_ratio > 0
    # Residual mean is close to the injected alpha mean (beta removed, alpha kept).
    assert float(np.mean(result.residual)) == pytest.approx(0.0008, abs=3e-4)


def test_empty_panel_is_identity():
    returns = noisy_alpha_series(n=100, seed=3)
    result = factors.residualize(returns, {})
    assert np.array_equal(result.residual, returns)
    assert result.r_squared == 0.0


def test_residual_fold_returns_preserves_cadence():
    market = factor_series(n=300, seed=1)
    fold = make_returns(beta_exposed_series(market, beta=1.0, seed=2), periods_per_year=8760.0)
    rf = factors.residual_fold_returns(fold, {"market": market})
    assert rf.periods_per_year == 8760.0
    assert rf.values.shape == fold.values.shape


def test_panel_column_length_mismatch_raises():
    returns = noisy_alpha_series(n=100, seed=3)
    with pytest.raises(ValueError):
        factors.residualize(returns, {"market": np.zeros(50)})
