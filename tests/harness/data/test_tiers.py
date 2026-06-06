"""FR-B1 — disjoint Train/Selection/Lockbox tiers, Lockbox = most-recent block.

Pure span derivation from the harness-owned Protocol; no data, no agent edit path.
"""

from __future__ import annotations

from datetime import date

import pytest

from harness.data.tiers import TierError, derive_tiers
from harness.protocol import Protocol


def _protocol(
    train,
    selection,
    lockbox,
    symbols=("ADA-PERP", "BTC-PERP"),
    *,
    purge_periods=None,
    periods_per_year=None,
) -> Protocol:
    payload = {
        "name": "tier-test",
        "cost_model": {"taker_bps": 5, "maker_bps": 1},
        "fill_model": {"fill": "close"},
        "data_tiers": {
            "train": {"start": train[0], "end": train[1]},
            "selection": {"start": selection[0], "end": selection[1]},
            "lockbox": {"start": lockbox[0], "end": lockbox[1]},
            "symbols": list(symbols),
        },
    }
    if purge_periods is not None:
        payload["folds"] = {"purge_periods": purge_periods}
    if periods_per_year is not None:
        payload["annualization"] = {"periods_per_year": periods_per_year}
    return Protocol.model_validate(payload)


def test_derive_tiers_disjoint_and_forward_ordered():
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2024-07-01", "2025-02-28"),
        ("2025-03-01", "2025-05-31"),
    )
    tiers = derive_tiers(proto)
    # Disjoint, pairwise.
    assert not tiers.train.overlaps(tiers.selection)
    assert not tiers.selection.overlaps(tiers.lockbox)
    assert not tiers.train.overlaps(tiers.lockbox)
    # Forward-ordered.
    assert tiers.train.end < tiers.selection.start
    assert tiers.selection.end < tiers.lockbox.start
    assert tiers.symbols == ("ADA-PERP", "BTC-PERP")


def test_lockbox_is_most_recent_block():
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2024-07-01", "2025-02-28"),
        ("2025-03-01", "2025-05-31"),
    )
    tiers = derive_tiers(proto)
    latest = max(s.end for s in tiers.all_spans)
    assert tiers.lockbox.end == latest == date(2025, 5, 31)
    assert tiers.lockbox.start > tiers.train.end
    assert tiers.lockbox.start > tiers.selection.end


def test_overlapping_tiers_rejected():
    # Selection overlaps Train by a day.
    proto = _protocol(
        ("2024-01-01", "2024-07-01"),
        ("2024-07-01", "2025-02-28"),
        ("2025-03-01", "2025-05-31"),
    )
    with pytest.raises(TierError, match="overlap"):
        derive_tiers(proto)


def test_lockbox_not_latest_rejected():
    # Lockbox sits BEFORE selection — not the most-recent block.
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2025-01-01", "2025-06-30"),
        ("2024-07-01", "2024-12-31"),
    )
    with pytest.raises(TierError):
        derive_tiers(proto)


# --------------------------------------------------------------------------- #
# FR-B3 — adjacent partitions separated by at least the purge horizon.
#
# The purge horizon is purge_periods bars; converted to whole calendar days via the
# annualization cadence (and floored at 1 day) it is the minimum gap each adjacent tier
# boundary must clear. Fail closed when a boundary is too tight for the configured purge.
# --------------------------------------------------------------------------- #


def test_gap_below_purge_horizon_rejected():
    # 1-day boundary gaps, but a purge horizon that needs >=2 calendar days
    # (36 hourly bars ≈ 1.50 days → 2). Both boundaries are too tight ⇒ reject.
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2024-07-01", "2025-02-28"),  # train->selection gap = 1 day
        ("2025-03-01", "2025-05-31"),  # selection->lockbox gap = 1 day
        purge_periods=36,
        periods_per_year=8760,
    )
    with pytest.raises(TierError, match="purge horizon"):
        derive_tiers(proto)


def test_selection_to_lockbox_gap_below_purge_horizon_rejected():
    # Train->Selection gap is generous (>1 month) but Selection->Lockbox is 1 day, under a
    # 2-day purge horizon ⇒ the second boundary fails closed.
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2024-08-01", "2025-02-28"),  # train->selection gap ≈ 1 month (fine)
        ("2025-03-01", "2025-05-31"),  # selection->lockbox gap = 1 day (too small)
        purge_periods=36,
        periods_per_year=8760,
    )
    with pytest.raises(TierError, match="purge horizon"):
        derive_tiers(proto)


def test_gap_at_or_above_purge_horizon_passes():
    # The default purge horizon (24 hourly bars ≈ 1 day, floored at 1) is satisfied by the
    # 1-day boundary gaps the other tests use — derivation succeeds.
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2024-07-01", "2025-02-28"),
        ("2025-03-01", "2025-05-31"),
        purge_periods=24,
        periods_per_year=8760,
    )
    tiers = derive_tiers(proto)
    assert tiers.train.end < tiers.selection.start
    assert tiers.selection.end < tiers.lockbox.start


def test_larger_purge_horizon_requires_larger_gap_and_passes():
    # A 2-day purge horizon is met by 3-day boundary gaps.
    proto = _protocol(
        ("2024-01-01", "2024-06-30"),
        ("2024-07-03", "2025-02-25"),  # gap = 3 days
        ("2025-02-28", "2025-05-31"),  # gap = 3 days
        purge_periods=36,
        periods_per_year=8760,
    )
    tiers = derive_tiers(proto)
    assert tiers.selection.start.isoformat() == "2024-07-03"
