"""RES semantics — AC-9 (factor neutrality) and AC-1 partial (overfit can't score).

Covers:
- AC-9: pure factor-beta / funding-carry ⇒ ≈0 residual alpha (information ratio) ⇒ no
  real edge to rank. The information ratio is the methodology's named residual-alpha
  magnitude; a near-zero IR means there is nothing for the audit/Lockbox to confirm.
- AC-1 (partial): leverage-inflated returns do NOT raise RES (frozen sizing); the
  ADA-disguised-as-basket fails the correlation-aware breadth/concentration gates ⇒ infeasible.
- FR-C4: per-fold Sharpe is the evidence unit. FR-C6: the row is undeflated.

Gates measure the breadth of the EDGE: per-symbol legs are factor-neutralized before the
concentration/breadth gates, so a genuinely diversified alpha basket (legs co-moving on
market beta but independent in alpha) passes, while the same-coin disguise fails.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.objective import factors, metrics
from harness.objective.res import GateThresholds, compute_res
from harness.testing import (
    factor_series,
    make_returns,
)

THRESHOLDS = GateThresholds(min_trades=30, max_concentration=0.6, min_effective_breadth=2.0)


def _alpha_basket(n, market, seed_base, alpha=0.0007, beta=0.9, idio_sd=0.004):
    """Diversified ALPHA basket: shared market beta, INDEPENDENT idiosyncratic alpha.

    Legs co-move on market beta (as all crypto does) but carry independent alpha, so they
    are diversified in residual (edge) space.
    """
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate("ABC"):
        rng = np.random.default_rng(seed_base + i)
        leg = alpha + beta * market + idio_sd * rng.standard_normal(n)
        by_symbol[sym] = make_returns(leg)
        port += leg / 3.0
    return by_symbol, port


# --------------------------------------------------------------------------- #
# AC-9: factor / funding beta is not edge.
# --------------------------------------------------------------------------- #


def test_ac9_pure_market_beta_has_zero_residual_alpha():
    """A pure market-beta basket (no alpha) has ≈0 residual information ratio."""
    n = 600
    market = factor_series(n=n, sd=0.02, seed=1)
    # alpha=0: pure beta + realistic idio noise (NOT a degenerate near-zero series).
    by_symbol, port = _alpha_basket(n, market, seed_base=10, alpha=0.0, idio_sd=0.004)
    fold = make_returns(port, by_symbol=by_symbol)

    res = compute_res([fold], [{"market": market}], trade_count=200, thresholds=THRESHOLDS)
    # The residual-alpha magnitude (IR) is ≈ 0 — there is no edge to confirm.
    assert res.residual_info_ratio is not None
    assert abs(res.residual_info_ratio) < 0.05  # within finite-sample noise band of zero


def test_ac9_pure_funding_carry_has_zero_residual_alpha():
    """Funding is carry: a funding-carry collector has ≈0 residual information ratio."""
    n = 600
    funding = factor_series(n=n, sd=0.006, seed=21)
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate("ABC"):
        rng = np.random.default_rng(40 + i)
        # PnL = funding carry (loading ~1) + idio noise; NO alpha.
        leg = 1.0 * funding + 0.003 * rng.standard_normal(n)
        by_symbol[sym] = make_returns(leg)
        port += leg / 3.0
    fold = make_returns(port, by_symbol=by_symbol)

    res = compute_res([fold], [{"funding_carry": funding}], trade_count=200, thresholds=THRESHOLDS)
    assert res.residual_info_ratio is not None
    assert abs(res.residual_info_ratio) < 0.05  # within finite-sample noise band of zero


def test_ac9_funding_pnl_is_neutralized_not_added_back():
    """Market beta + funding carry, no alpha ⇒ residual IR ≈ 0 (neither kept as edge)."""
    n = 600
    market = factor_series(n=n, sd=0.02, seed=1)
    funding = factor_series(n=n, sd=0.006, seed=21)
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate("ABC"):
        rng = np.random.default_rng(60 + i)
        leg = 0.8 * market + 1.0 * funding + 0.003 * rng.standard_normal(n)
        by_symbol[sym] = make_returns(leg)
        port += leg / 3.0
    fold = make_returns(port, by_symbol=by_symbol)
    panel = {"market": market, "funding_carry": funding}
    res = compute_res([fold], [panel], trade_count=200, thresholds=THRESHOLDS)
    assert res.residual_info_ratio is not None
    assert abs(res.residual_info_ratio) < 0.05  # within finite-sample noise band of zero


def test_genuine_residual_alpha_ranks_positive_and_feasible():
    """A real, diversified, idiosyncratic edge is feasible and ranks positive."""
    n = 800
    market = factor_series(n=n, sd=0.02, seed=1)
    by_symbol, port = _alpha_basket(n, market, seed_base=50, alpha=0.0009, idio_sd=0.003)
    fold = make_returns(port, by_symbol=by_symbol)
    res = compute_res([fold], [{"market": market}], trade_count=200, thresholds=THRESHOLDS)
    assert res.feasible  # diversified in residual (alpha) space ⇒ breadth passes
    assert res.rank_sharpe is not None and res.rank_sharpe > 0
    assert res.residual_info_ratio is not None and res.residual_info_ratio > 0


# --------------------------------------------------------------------------- #
# AC-1 (partial): the diagnosed overfit's signature cannot raise RES.
# --------------------------------------------------------------------------- #


def test_ac1_leverage_does_not_raise_res():
    """Sizing is frozen at the seam: uniformly scaling returns leaves RES unchanged."""
    n = 800
    market = factor_series(n=n, sd=0.02, seed=1)
    by_symbol_1x, port_1x = _alpha_basket(n, market, seed_base=70, alpha=0.0009, idio_sd=0.003)
    fold_1x = make_returns(port_1x, by_symbol=by_symbol_1x)

    # "Crank sizing to 0.20": multiply every return leg (and the factor exposure) by k.
    lev = 4.0
    by_symbol_lev = {s: make_returns(fr.values * lev) for s, fr in by_symbol_1x.items()}
    fold_lev = make_returns(port_1x * lev, by_symbol=by_symbol_lev)

    res_1x = compute_res([fold_1x], [{"market": market}], 200, THRESHOLDS)
    res_lev = compute_res([fold_lev], [{"market": market * lev}], 200, THRESHOLDS)
    assert res_1x.rank_sharpe is not None and res_lev.rank_sharpe is not None
    # Residual Sharpe is scale-free ⇒ leverage cannot raise the rank number.
    assert res_1x.rank_sharpe == pytest.approx(res_lev.rank_sharpe, rel=1e-6)


def test_ac1_ada_disguised_as_basket_is_infeasible():
    """ADA 0.95 / XRP / AVAX co-moving single-asset bet ⇒ correlation-aware gates fire.

    The per-symbol legs are the position-weighted contributions, so ADA dominates PnL
    (concentration) AND all legs are the same coin (residuals identical ⇒ breadth ≈ 1).
    """
    n = 500
    market = factor_series(n=n, sd=0.02, seed=1)
    rng = np.random.default_rng(99)
    ada = 0.0008 + 0.01 * rng.standard_normal(n)  # the real directional bet
    # Position-weighted contributions: the disguise lives in the weights.
    by_symbol = {
        "ADA": make_returns(0.95 * ada),
        "XRP": make_returns(0.025 * (ada * 1.01)),  # co-moves with ADA, tiny weight
        "AVAX": make_returns(0.025 * (ada * 0.99)),
    }
    port = sum(fr.values for fr in by_symbol.values())
    fold = make_returns(port, by_symbol=by_symbol)

    res = compute_res([fold], [{"market": market}], trade_count=200, thresholds=THRESHOLDS)
    assert not res.feasible
    assert res.rank_sharpe is None
    # The correlation-aware breadth gate bounces the same-coin disguise.
    assert not res.gate_results["effective_breadth"].passed
    # And concentration catches ADA dominating the weighted PnL.
    assert not res.gate_results["concentration"].passed


def test_ac1_thin_trade_count_is_infeasible():
    """A degenerate single-hour artifact with too few trades fails the evidence proxy."""
    n = 400
    market = factor_series(n=n, sd=0.02, seed=1)
    by_symbol, port = _alpha_basket(n, market, seed_base=120, alpha=0.0009)
    fold = make_returns(port, by_symbol=by_symbol)
    res = compute_res([fold], [{"market": market}], trade_count=5, thresholds=THRESHOLDS)
    assert not res.feasible
    assert not res.gate_results["evidence_sufficiency"].passed


# --------------------------------------------------------------------------- #
# FR-C4 / FR-C6 semantics.
# --------------------------------------------------------------------------- #


def test_per_fold_sharpe_is_the_evidence_unit():
    n = 300
    market = factor_series(n=n, sd=0.02, seed=1)
    folds, panels = [], []
    for f in range(4):
        by_symbol, port = _alpha_basket(n, market, seed_base=200 + 10 * f, alpha=0.0009)
        folds.append(make_returns(port, by_symbol=by_symbol))
        panels.append({"market": market})
    res = compute_res(folds, panels, trade_count=200, thresholds=THRESHOLDS)
    assert len(res.per_fold_sharpe) == 4  # one Sharpe per fold


def test_row_is_undeflated_rank_equals_raw_residual_sharpe():
    """FR-C6: the rank number is the raw residual Sharpe — no per-row deflation applied."""
    n = 800
    market = factor_series(n=n, sd=0.02, seed=1)
    by_symbol, port = _alpha_basket(n, market, seed_base=300, alpha=0.0009, idio_sd=0.003)
    fold = make_returns(port, by_symbol=by_symbol)
    res = compute_res([fold], [{"market": market}], trade_count=200, thresholds=THRESHOLDS)
    # The rank Sharpe equals the undeflated Sharpe of the residual-alpha series itself
    # (PSR is reported as a helper but NOT folded into the rank).
    residual_alpha = factors.residual_fold_returns(fold, {"market": market})
    assert res.rank_sharpe == pytest.approx(metrics.sharpe(residual_alpha))
    assert res.psr is not None  # reported, not applied to the row
