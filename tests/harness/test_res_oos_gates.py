"""FR-C5 — the four OOS gates wired into compute_res, each bouncing within the pipeline.

Uses the same diversified-alpha basket as test_res so the cheap gates (concentration/breadth)
pass and the new OOS gate under test is the one that bites.
"""

from __future__ import annotations

import numpy as np

from harness.objective.res import GateThresholds, compute_res
from harness.testing import factor_series, make_returns

THRESHOLDS = GateThresholds(min_trades=30, max_concentration=0.6, min_effective_breadth=2.0)


def _alpha_basket(n, market, seed_base, alpha=0.0009, beta=0.9, idio_sd=0.003):
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate("ABC"):
        rng = np.random.default_rng(seed_base + i)
        leg = alpha + beta * market + idio_sd * rng.standard_normal(n)
        by_symbol[sym] = make_returns(leg)
        port += leg / 3.0
    return by_symbol, port


def _genuine_fold(n=400, seed_base=10, **kw):
    market = factor_series(n=n, sd=0.02, seed=1)
    by_symbol, port = _alpha_basket(n, market, seed_base, **kw)
    return make_returns(port, by_symbol=by_symbol), {"market": market}


def test_genuine_edge_passes_all_oos_gates():
    fold, panel = _genuine_fold()
    res = compute_res([fold], [panel], trade_count=200, thresholds=THRESHOLDS)
    assert res.feasible
    assert res.gate_results["psr"].passed
    assert res.gate_results["max_drawdown"].passed
    assert res.gate_results["worst_fold"].passed


def test_psr_gate_bounces_a_high_floor():
    # A near-zero-drift residual yields low PSR; a 0.99 floor bounces it.
    n = 400
    market = factor_series(n=n, sd=0.02, seed=1)
    by_symbol, port = _alpha_basket(n, market, 30, alpha=0.00002, idio_sd=0.01)
    fold = make_returns(port, by_symbol=by_symbol)
    thr = GateThresholds(30, 0.6, 2.0, psr_floor=0.99)
    res = compute_res([fold], [{"market": market}], trade_count=200, thresholds=thr)
    assert not res.gate_results["psr"].passed
    assert not res.feasible


def test_max_drawdown_gate_bounces_a_tight_ceiling():
    fold, panel = _genuine_fold()
    thr = GateThresholds(30, 0.6, 2.0, max_drawdown_ceiling=1e-6)  # absurdly tight
    res = compute_res([fold], [panel], trade_count=200, thresholds=thr)
    assert not res.gate_results["max_drawdown"].passed
    assert not res.feasible


def test_worst_fold_gate_bounces_a_negative_fold():
    # Three good folds + one genuinely negative-edge fold ⇒ worst-fold floor fires.
    market = factor_series(n=400, sd=0.02, seed=1)
    folds, panels = [], []
    for f in range(3):
        bs, port = _alpha_basket(400, market, 50 + 10 * f, alpha=0.0009, idio_sd=0.003)
        folds.append(make_returns(port, by_symbol=bs))
        panels.append({"market": market})
    # A negative-alpha fold.
    bs_bad, port_bad = _alpha_basket(400, market, 900, alpha=-0.0012, idio_sd=0.003)
    folds.append(make_returns(port_bad, by_symbol=bs_bad))
    panels.append({"market": market})
    res = compute_res(folds, panels, trade_count=200, thresholds=THRESHOLDS)
    assert not res.gate_results["worst_fold"].passed
    assert not res.feasible


def test_cost_stress_gate_runs_when_stressed_folds_supplied_and_bounces_collapse():
    # Realistic edge is real; the stressed version collapses to ~flat ⇒ cost-stress fails.
    n = 400
    market = factor_series(n=n, sd=0.02, seed=1)
    bs, port = _alpha_basket(n, market, 70, alpha=0.0009, idio_sd=0.003)
    fold = make_returns(port, by_symbol=bs)
    # Stressed: same beta exposure, alpha eaten away by costs (near zero drift).
    bs_s, port_s = _alpha_basket(n, market, 70, alpha=0.00001, idio_sd=0.003)
    stressed = make_returns(port_s, by_symbol=bs_s)
    res = compute_res(
        [fold], [{"market": market}], trade_count=200, thresholds=THRESHOLDS,
        stressed_folds=[stressed], stressed_factor_panels=[{"market": market}],
    )
    assert "cost_stress" in res.gate_results
    assert not res.gate_results["cost_stress"].passed
    assert not res.feasible


def test_cost_stress_gate_omitted_when_no_stressed_evidence():
    # No stressed folds supplied ⇒ the cost-stress question was not asked ⇒ gate omitted
    # (not silently passed). The candidate can still be feasible on the other gates.
    fold, panel = _genuine_fold()
    res = compute_res([fold], [panel], trade_count=200, thresholds=THRESHOLDS)
    assert "cost_stress" not in res.gate_results
    assert res.feasible


def test_cost_stress_gate_passes_when_edge_survives_stress():
    n = 400
    market = factor_series(n=n, sd=0.02, seed=1)
    bs, port = _alpha_basket(n, market, 70, alpha=0.0009, idio_sd=0.003)
    fold = make_returns(port, by_symbol=bs)
    # Stressed edge retains most of its drift.
    bs_s, port_s = _alpha_basket(n, market, 70, alpha=0.0008, idio_sd=0.003)
    stressed = make_returns(port_s, by_symbol=bs_s)
    res = compute_res(
        [fold], [{"market": market}], trade_count=200, thresholds=THRESHOLDS,
        stressed_folds=[stressed], stressed_factor_panels=[{"market": market}],
    )
    assert res.gate_results["cost_stress"].passed
