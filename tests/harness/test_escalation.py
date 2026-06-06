"""Escalation gate (FR-D1, FR-A4, enforcement #4/#8/#10) — the harness Train→Selection filter.

Each failing condition routes the candidate back to Train (FREE, no look) and a valid new
robust thesis passes. Swing-big: after M ideas without a new family, escalation is REFUSED
until a new family is proposed. All deterministic through the Fake gateway (no live data).
"""

from __future__ import annotations

import numpy as np

from harness.escalation import evaluate_escalation
from harness.family import compute_family_id
from harness.foundation import FoldReturns, QuickRunResult
from harness.protocol import Experiment, Protocol
from harness.testing import FakeFoundationGateway

PPY = 8760.0

# Two structurally-DISTINCT strategy sources (different signal closures ⇒ different family ids).
SRC_A = '''
def generate_decisions(rows, params):
    x = _signal(rows)
    if x > 0:
        return [1]
    return []

def _signal(rows):
    return sum(rows)
'''

SRC_B = '''
def generate_decisions(rows, params):
    y = _trend(rows)
    if y < 0:
        return [-1]
    return []

def _trend(rows):
    return rows[0] - rows[-1] if rows else 0
'''

# A literal-value + docstring-only nudge of SRC_A — same control-flow STRUCTURE, so it MUST
# collapse to A's family (FR-E4): only the constant `0`→`2` and a prose docstring change, which
# the fingerprint normalizes out. (A change to the comparison or call graph would be a real new
# family — correctly NOT a nudge.)
SRC_A_NUDGED = '''
def generate_decisions(rows, params):
    """A different thesis in prose, identical signal structure."""
    x = _signal(rows)
    if x > 2:
        return [1]
    return []

def _signal(rows):
    return sum(rows)
'''


def _protocol(symbols=("AAA", "BBB", "CCC")) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "esc-test",
            "cost_model": {"taker_bps": 5, "maker_bps": 1, "slippage_bps": 1},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-03-31"},
                "selection": {"start": "2024-05-01", "end": "2024-10-31"},
                "lockbox": {"start": "2024-12-01", "end": "2024-12-31"},
                "symbols": list(symbols),
            },
            "objective": {"gates": {"min_trades": 30, "max_concentration": 0.5}},
            "stability": {
                "rho": 0.6,
                "min_positive_fraction": 0.8,
                "step_multipliers": [1, 2],
                "param_steps": {"threshold": 0.1},
            },
            "annualization": {"periods_per_year": PPY},
        }
    )


def _experiment() -> Experiment:
    return Experiment(strategy_path="strategy.py", params={"threshold": 1.0}, symbols=("AAA", "BBB", "CCC"))


def _balanced_slices() -> dict:
    """A by_symbol slice with no single dominant symbol (cheap-robust passes)."""
    return {"by_symbol": {"AAA": 0.34, "BBB": 0.33, "CCC": 0.33}}


def _plateau_gateway(*, valid=True, causal_ok=True, trade_count=100, metric=1.0, slices=None):
    """A Fake gateway whose Train metric is a flat-and-positive plateau (stability passes)."""
    return FakeFoundationGateway(
        quick_metric_fn=lambda e: metric,  # flat across perturbations ⇒ plateau
        valid=valid,
        causal_ok=causal_ok,
        trade_count=trade_count,
        slices=slices or _balanced_slices(),
    )


# --------------------------------------------------------------------------- #
# The happy path: a valid, alive, positive, NEW, cheap-robust, plateau candidate passes.
# --------------------------------------------------------------------------- #


def test_valid_new_robust_thesis_may_escalate():
    gw = _plateau_gateway()
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    assert d.may_escalate is True
    assert d.is_new_family is True
    assert all(c.passed for c in d.conditions)


# --------------------------------------------------------------------------- #
# Each failing condition routes to Train and does NOT pass (FR-D1).
# --------------------------------------------------------------------------- #


def test_invalid_candidate_routes_to_train():
    gw = _plateau_gateway(valid=False, causal_ok=False)
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    assert d.may_escalate is False
    assert d.routed_to_train is True
    assert d.reason.startswith("valid:")


def test_dead_candidate_too_few_trades_routes_to_train():
    gw = _plateau_gateway(trade_count=5)  # < 30 floor
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    assert d.may_escalate is False
    assert d.reason.startswith("alive:")


def test_negative_in_sample_routes_to_train():
    gw = _plateau_gateway(metric=-0.5)  # negative after costs
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    assert d.may_escalate is False
    assert d.reason.startswith("in_sample_positive:")


def test_thesis_free_nudge_of_logged_family_routes_to_train_and_spends_no_look():
    """A param/docstring nudge of a logged family collapses to the same family id ⇒ Train (free)."""
    logged = [compute_family_id(SRC_A)]
    gw = _plateau_gateway()
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A_NUDGED, logged_family_ids=logged, ideas_since_new_family=0,
    )
    assert d.is_new_family is False
    assert d.may_escalate is False
    assert d.reason.startswith("new_thesis:")
    # The nudge's family id IS the logged family id (the AC-2/AC-8 linchpin).
    assert d.family_id == compute_family_id(SRC_A)


def test_single_symbol_carried_edge_routes_to_train():
    """AC-1 leg: an ADA-only 'basket' (one symbol carries ~all PnL) fails cheap-robust."""
    concentrated = {"by_symbol": {"ADA": 0.95, "XRP": 0.025, "AVAX": 0.025}}
    gw = _plateau_gateway(slices=concentrated)
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    assert d.may_escalate is False
    assert d.reason.startswith("cheap_robust:")


def test_knife_edge_routes_to_train():
    """A non-plateau (knife-edge) Train metric fails the stability gate."""
    # Center high, neighbours collapse to ~0 ⇒ worst/center << rho ⇒ knife-edge.
    def spiky(experiment):
        return 1.0 if abs(experiment.params["threshold"] - 1.0) < 1e-9 else 0.0

    gw = FakeFoundationGateway(
        quick_metric_fn=spiky, valid=True, causal_ok=True, trade_count=100,
        slices=_balanced_slices(),
    )
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    assert d.may_escalate is False
    assert d.reason.startswith("robust_plateau:")
    assert d.stability is not None and d.stability.routed_back_to_train is True


# --------------------------------------------------------------------------- #
# Swing-big cadence (FR-A4, enforcement #8).
# --------------------------------------------------------------------------- #


def test_swing_big_refuses_old_family_after_M_ideas():
    """After M ideas without a new family, an old-family candidate is REFUSED until a new one."""
    logged = [compute_family_id(SRC_A)]
    gw = _plateau_gateway()
    # A NEW idea in the SAME family A, with the cadence already at the limit.
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=logged, ideas_since_new_family=5,
        swing_big_every=5,
    )
    assert d.may_escalate is False
    # new_thesis fails first for an old family; the swing-big condition is also present.
    assert any(c.name == "swing_big" and not c.passed for c in d.conditions)


def test_swing_big_satisfied_by_a_new_family():
    """Proposing a structurally NEW family at the cadence limit clears swing-big and may escalate."""
    logged = [compute_family_id(SRC_A)]
    gw = _plateau_gateway()
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_B, logged_family_ids=logged, ideas_since_new_family=5,
        swing_big_every=5,
    )
    assert d.is_new_family is True
    assert d.may_escalate is True
    assert all(c.passed for c in d.conditions)


def test_cheap_robust_na_for_single_symbol_universe():
    """A single-symbol slice is N/A for concentration (the OOS gates still bind on Selection)."""
    gw = _plateau_gateway(slices={"by_symbol": {"AAA": 1.0}})
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
    )
    cr = next(c for c in d.conditions if c.name == "cheap_robust")
    assert cr.passed is True


def test_reuses_injected_quick_run_without_re_running():
    """The CLI may pass an already-computed quick_run; the gate reuses it (one fewer Train run)."""
    gw = _plateau_gateway()
    qr = QuickRunResult(
        valid=True, causal_ok=True, in_sample_metric=2.0, trade_count=80,
        slices=_balanced_slices(), failure_stage=None,
    )
    d = evaluate_escalation(
        _experiment(), _protocol(), ("w",), gw,
        strategy_source=SRC_A, logged_family_ids=[], ideas_since_new_family=0,
        quick_run=qr,
    )
    # The injected quick_run drove conditions 1-3 (its trade_count 80 and metric 2.0).
    alive = next(c for c in d.conditions if c.name == "alive")
    assert "80 trades" in alive.detail
