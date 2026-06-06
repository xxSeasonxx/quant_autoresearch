"""Session shell (FR-A1, FR-E5) — never-early-stop, a quota, never a countdown.

The session ends only when the harness says so (the global budget is spent) or a human
interrupts; there is no attempt countdown. The session marker round-trips atomically.
"""

from __future__ import annotations

from harness.budget import BudgetManager
from harness.session import (
    SessionMarker,
    advance_idea,
    read_session_marker,
    session_status,
    write_session_marker,
)


class _Charged:
    def __init__(self, charged):
        self._charged = charged

    def charged_count(self):
        return self._charged


def test_session_active_while_budget_has_headroom():
    status = session_status(BudgetManager(8, _Charged(3)))
    assert status.state == "active"
    assert status.ended is False
    assert status.looks_remaining == 5
    assert status.looks_charged == 3
    assert status.cap == 8


def test_session_ends_only_when_budget_is_spent():
    status = session_status(BudgetManager(4, _Charged(4)))
    assert status.state == "budget_spent"
    assert status.ended is True
    assert status.looks_remaining == 0


def test_session_status_has_no_attempt_countdown_fields():
    """A quota state, never a countdown — the agent is never handed remaining_attempts."""
    status = session_status(BudgetManager(8, _Charged(0)))
    # The dataclass fields are quota-shaped (remaining looks), not attempt-shaped.
    fields = set(status.__dataclass_fields__)
    assert fields == {"state", "looks_remaining", "looks_charged", "cap"}
    assert "remaining_attempts" not in fields and "max_attempts" not in fields


def test_session_marker_round_trips_atomically(tmp_path):
    marker = SessionMarker(
        ledger_path="ledger.jsonl", book_path="lockbox.json", protocol_hash="abc123",
        ideas_since_new_family=4,
    )
    written = write_session_marker(tmp_path, marker)
    assert written.is_file()
    # No orphan temp file left behind.
    assert not (tmp_path / (written.name + ".tmp")).exists()
    back = read_session_marker(tmp_path)
    assert back == marker
    assert back.ideas_since_new_family == 4


def test_read_session_marker_missing_returns_none(tmp_path):
    assert read_session_marker(tmp_path) is None


def test_advance_idea_counts_ideas_and_resets_on_a_new_family_bet():
    """The swing-big cadence counts every idea (run/evaluate) and resets on a new-family bet."""
    m = SessionMarker(ledger_path="l", book_path="b", protocol_hash="h", ideas_since_new_family=0)
    # Three Train runs (or routed evaluates) — each an idea, none a new-family bet.
    for expected in (1, 2, 3):
        m = advance_idea(m, logged_new_family=False)
        assert m.ideas_since_new_family == expected
    # A logged NEW-family bet resets the cadence (the agent swung big).
    m = advance_idea(m, logged_new_family=True)
    assert m.ideas_since_new_family == 0


def test_read_session_marker_defaults_counter_when_absent_from_legacy_payload(tmp_path):
    """A marker written without the counter (e.g. a legacy/partial payload) reads as 0, not error."""
    import json

    (tmp_path / ".autoresearch_session.json").write_text(
        json.dumps({"ledger_path": "l", "book_path": "b", "protocol_hash": "h"}), encoding="utf-8"
    )
    back = read_session_marker(tmp_path)
    assert back is not None and back.ideas_since_new_family == 0
