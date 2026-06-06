"""FR-B4 — write-once-per-dataset Lockbox bookkeeping.

Once any candidate scores on a Lockbox block, that block is spent for the whole campaign;
a new Lockbox needs fresh forward time. Keyed to the dataset, not the candidate.
"""

from __future__ import annotations

import pytest

from harness.data.lockbox_book import (
    LockboxBook,
    LockboxSpentError,
    lockbox_dataset_id,
)


def _did(start="2025-03-01", end="2025-05-31", symbols=("ADA-PERP",), phash="abc123") -> str:
    return lockbox_dataset_id(
        protocol_hash=phash, lockbox_start=start, lockbox_end=end, symbols=symbols
    )


def test_first_scoring_succeeds_and_marks_spent():
    book = LockboxBook()
    did = _did()
    assert not book.is_spent(did)
    book.reserve(did, trial_id="t1", spent_at="2026-06-05T00:00:00Z")
    assert book.is_spent(did)


def test_second_scoring_on_same_dataset_is_refused_even_for_a_different_candidate():
    book = LockboxBook()
    did = _did()
    book.reserve(did, trial_id="t1", spent_at="2026-06-05T00:00:00Z")
    # A DIFFERENT candidate (t2) on the SAME Lockbox block is refused (per-dataset, not
    # per-candidate — closes the cross-batch reuse leak).
    with pytest.raises(LockboxSpentError, match="already spent"):
        book.reserve(did, trial_id="t2", spent_at="2026-06-05T01:00:00Z")


def test_fresh_lockbox_dataset_is_a_new_key():
    # A freshly cut forward block (different span) is a different dataset, scorable once.
    book = LockboxBook()
    did_old = _did(start="2025-03-01", end="2025-05-31")
    did_new = _did(start="2025-06-01", end="2025-08-31")
    assert did_old != did_new
    book.reserve(did_old, trial_id="t1", spent_at="2026-06-05T00:00:00Z")
    assert not book.is_spent(did_new)
    book.reserve(did_new, trial_id="t2", spent_at="2026-09-05T00:00:00Z")
    assert book.is_spent(did_new)


def test_dataset_id_is_candidate_independent_but_span_sensitive():
    # Same span+symbols+protocol ⇒ same dataset id regardless of which candidate scores it.
    a = _did(symbols=("ADA-PERP", "BTC-PERP"))
    b = _did(symbols=("BTC-PERP", "ADA-PERP"))  # order-independent
    assert a == b
    c = _did(phash="different-protocol")
    assert a != c  # a different judgment config is a different dataset


def test_spent_flag_persists_across_book_instances(tmp_path):
    path = tmp_path / "lockbox_book.json"
    did = _did()
    book1 = LockboxBook(path=path)
    book1.reserve(did, trial_id="t1", spent_at="2026-06-05T00:00:00Z")
    # A fresh process/instance reads the persisted spent-flag and still refuses.
    book2 = LockboxBook(path=path)
    assert book2.is_spent(did)
    with pytest.raises(LockboxSpentError):
        book2.reserve(did, trial_id="t2", spent_at="2026-06-05T02:00:00Z")
