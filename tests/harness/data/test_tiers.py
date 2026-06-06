"""FR-B1 — disjoint Train/Selection/Lockbox tiers, Lockbox = most-recent block.

Pure span derivation from the harness-owned Protocol; no data, no agent edit path.
"""

from __future__ import annotations

from datetime import date

import pytest

from harness.data.tiers import TierError, derive_tiers
from harness.protocol import Protocol


def _protocol(train, selection, lockbox, symbols=("ADA-PERP", "BTC-PERP")) -> Protocol:
    return Protocol.model_validate(
        {
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
    )


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
