"""FR-C5 — the four OOS Stage-1 gates: PSR, max-drawdown, worst-fold+dispersion, cost-stress.

Each gate bounces its own failure mode and fails closed when its statistic is undefined.
The degenerate/None-fold carry (the metrics ``_EPS`` floor) is gate-relevant for worst-fold.
"""

from __future__ import annotations

import numpy as np

from harness.objective import gates


# --------------------------------------------------------------------------- #
# PSR gate.
# --------------------------------------------------------------------------- #


def test_psr_gate_passes_above_floor():
    assert gates.psr_gate(0.97, 0.95).passed


def test_psr_gate_fails_below_floor():
    assert not gates.psr_gate(0.80, 0.95).passed


def test_psr_gate_fails_closed_on_none():
    # Undefined PSR (degenerate / too-small sample) is insufficient evidence ⇒ fail.
    out = gates.psr_gate(None, 0.95)
    assert not out.passed
    assert out.value is None


# --------------------------------------------------------------------------- #
# Max-drawdown ceiling.
# --------------------------------------------------------------------------- #


def test_max_drawdown_gate_passes_under_ceiling():
    assert gates.max_drawdown_gate(-0.10, 0.35).passed


def test_max_drawdown_gate_fails_over_ceiling():
    assert not gates.max_drawdown_gate(-0.50, 0.35).passed


def test_max_drawdown_gate_fails_closed_on_none():
    assert not gates.max_drawdown_gate(None, 0.35).passed


# --------------------------------------------------------------------------- #
# Worst-fold floor + dispersion ceiling (degenerate-fold carry).
# --------------------------------------------------------------------------- #


def test_worst_fold_gate_passes_tight_positive_set():
    # All folds positive, low dispersion.
    assert gates.worst_fold_gate([1.0, 1.1, 0.9, 1.05], 0.0, 3.0).passed


def test_worst_fold_gate_fails_negative_worst_fold():
    assert not gates.worst_fold_gate([1.0, 1.2, -0.3, 0.9], 0.0, 3.0).passed


def test_worst_fold_gate_fails_high_dispersion():
    # Mean small, spread large ⇒ the edge is carried by one window.
    out = gates.worst_fold_gate([0.05, 0.05, 3.0, 0.05], 0.0, 1.0)
    assert not out.passed


def test_degenerate_none_fold_is_a_failing_fold_not_skipped():
    """A near-zero-variance fold (Sharpe None — the _EPS carry) cannot launder a pass.

    Without this guard, dropping the None fold would leave [1.0, 1.1, 0.9] (all positive) and
    spuriously PASS. Treating None as a failing fold bounces it.
    """
    out = gates.worst_fold_gate([1.0, None, 1.1, 0.9], 0.0, 3.0)
    assert not out.passed
    assert "degenerate" in out.detail


def test_worst_fold_gate_fails_on_empty_set():
    assert not gates.worst_fold_gate([], 0.0, 3.0).passed


def test_worst_fold_single_fold_applies_floor_only():
    # One measurable positive fold: floor applies, dispersion N/A ⇒ passes.
    assert gates.worst_fold_gate([0.8], 0.0, 3.0).passed
    # One measurable negative fold fails the floor.
    assert not gates.worst_fold_gate([-0.2], 0.0, 3.0).passed


# --------------------------------------------------------------------------- #
# Cost-stress survival ratio.
# --------------------------------------------------------------------------- #


def test_cost_stress_gate_passes_when_edge_survives():
    # Stressed Sharpe is 70% of realistic ⇒ above a 0.5 floor.
    assert gates.cost_stress_gate(1.0, 0.7, 0.5).passed


def test_cost_stress_gate_fails_when_edge_evaporates():
    # Stressed Sharpe collapses to 20% of realistic.
    assert not gates.cost_stress_gate(1.0, 0.2, 0.5).passed


def test_cost_stress_gate_fails_on_nonpositive_realistic_edge():
    assert not gates.cost_stress_gate(-0.1, -0.05, 0.5).passed
    assert not gates.cost_stress_gate(None, 0.5, 0.5).passed


def test_cost_stress_gate_fails_closed_on_undefined_stressed_even_with_zero_ratio():
    # Fail-closed: a None/non-finite stressed Sharpe is UNDEFINED evidence and must fail even
    # if the survival ratio is 0.0 (it must NOT be mapped to 0 and slip through).
    assert not gates.cost_stress_gate(1.0, None, 0.0).passed
    assert not gates.cost_stress_gate(1.0, float("nan"), 0.0).passed
    assert not gates.cost_stress_gate(float("inf"), 0.5, 0.5).passed


def test_psr_gate_fails_closed_on_non_finite_or_out_of_range():
    # PSR must be a finite probability in [0,1]; a malformed value never passes.
    assert not gates.psr_gate(float("inf"), 0.95).passed
    assert not gates.psr_gate(float("nan"), 0.95).passed
    assert not gates.psr_gate(1.5, 0.95).passed  # >1 is not a probability
    assert not gates.psr_gate(-0.1, 0.0).passed
