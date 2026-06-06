"""Budget Manager — global cap, effective-N sizing, fail-safe consumption (FR-E2/E3/E5).

Unit-level guarantees:
- the cap is a global integer upper bound sized on effective-N (sizing math);
- consumption reads the ledger's CHARGED count, so a crashed-but-reserved look still counts;
- when charged == cap the budget is spent and no more looks may be reserved (FR-E5).
The campaign-level AC-2/AC-8 assertions live in ``test_selection_budget.py``.
"""

from __future__ import annotations

import pytest

from harness.budget import (
    BudgetExhaustedError,
    BudgetManager,
    effective_independent_trials,
    size_budget,
)


class _FakeLedger:
    """A ledger stub exposing only the budget's read seam."""

    def __init__(self, charged: int = 0) -> None:
        self._charged = charged

    def charged_count(self) -> int:
        return self._charged

    def charge(self) -> None:
        self._charged += 1


def test_effective_independent_trials_clusters_by_family():
    # Five looks across two families ⇒ two effective independent directions (FR-E3).
    fams = ["F1", "F1", "F1", "F2", "F2"]
    assert effective_independent_trials(fams) == 2
    assert effective_independent_trials([]) == 0
    assert effective_independent_trials(["F1"]) == 1


def test_size_budget_is_an_upper_bound_min_of_the_two_bounds():
    # The profiler's MinBTL-on-effective-sample bound is the primary cap.
    assert size_budget(8) == 8
    # An effective-trials bound tightens it downward (never up).
    assert size_budget(8, effective_trials_cap=3) == 3
    assert size_budget(3, effective_trials_cap=8) == 3
    # Always at least one honest look.
    assert size_budget(0) == 1
    assert size_budget(5, effective_trials_cap=0) == 1


def test_remaining_decrements_as_looks_are_charged():
    led = _FakeLedger(0)
    bm = BudgetManager(cap=3, ledger=led)
    assert bm.remaining() == 3 and bm.can_reserve()
    led.charge()
    assert bm.remaining() == 2 and bm.can_reserve()
    led.charge(); led.charge()
    assert bm.remaining() == 0 and not bm.can_reserve()  # spent (FR-E5)


def test_budget_spent_stops_issuing_looks():
    bm = BudgetManager(cap=2, ledger=_FakeLedger(2))
    assert bm.status().spent
    assert not bm.can_reserve()
    with pytest.raises(BudgetExhaustedError):
        bm.check_can_reserve()


def test_charged_count_includes_crashed_reservations():
    """The budget reads CHARGED looks (the ledger counts reserved-but-crashed ones), so a crash
    cannot create free headroom — consumption and the ledger cannot drift (FR-I2/NFR-6)."""
    # 3 charged out of cap 3 — even if some never finalized, the budget is spent.
    bm = BudgetManager(cap=3, ledger=_FakeLedger(3))
    assert bm.remaining() == 0
    assert not bm.can_reserve()


def test_cap_must_be_positive():
    with pytest.raises(ValueError):
        BudgetManager(cap=0, ledger=_FakeLedger())
