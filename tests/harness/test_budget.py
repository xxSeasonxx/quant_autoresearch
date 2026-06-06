"""Budget Manager — global cap, fail-safe consumption (FR-E2/E3/E5).

Unit-level guarantees:
- the cap is a global integer upper bound sized on the effective SAMPLE (family-count-independent);
- consumption reads the ledger's CHARGED count, so a crashed-but-reserved look still counts;
- when charged == cap the budget is spent and no more looks may be reserved (FR-E5).
The campaign-level AC-2/AC-8 assertions live in ``test_selection_budget.py``.
"""

from __future__ import annotations

import pytest

from harness.budget import BudgetExhaustedError, BudgetManager


class _FakeLedger:
    """A ledger stub exposing only the budget's read seam."""

    def __init__(self, charged: int = 0) -> None:
        self._charged = charged

    def charged_count(self) -> int:
        return self._charged

    def charge(self) -> None:
        self._charged += 1


class _FamilyCountingLedger:
    """A ledger stub whose charged-count equals the number of DISTINCT families charged.

    This is the surface a future change might (wrongly) try to use to size the cap upward as more
    families appear — exactly the AC-2 loosening the budget must never allow.
    """

    def __init__(self) -> None:
        self._families: set[str] = set()

    def charge_family(self, family_id: str) -> None:
        self._families.add(family_id)

    def charged_count(self) -> int:
        return len(self._families)


def test_cap_cannot_be_raised_by_adding_families():
    """AC-2: the budget cap is a fixed global integer; nothing about how many DISTINCT families
    have been charged can raise it. A campaign that has explored 1 family and one that has
    explored 100 share the identical cap — so relabeling/splitting cannot mint headroom (FR-E2).

    This fails if anyone later wires family count into the cap (e.g. ``cap = base * n_families``).
    """
    ledger = _FamilyCountingLedger()
    bm = BudgetManager(cap=3, ledger=ledger)
    cap_with_zero_families = bm.cap

    for i in range(100):
        ledger.charge_family(f"F{i}")
        # The cap is immutable regardless of how many families have been seen.
        assert bm.cap == cap_with_zero_families == 3
    # And once charges (here, distinct families) reach the cap, the budget is spent — the family
    # explosion consumes the cap, it never enlarges it.
    assert bm.status().spent and not bm.can_reserve()


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
