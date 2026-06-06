"""FR-B2/B3 — forward-only walk-forward, purge before test, embargo on next train.

Pure integer-period arithmetic; the spacing math is verified directly.
"""

from __future__ import annotations

import pytest

from harness.data.walkforward import Fold, WalkForwardError, generate_folds
from harness.protocol import FoldConfig


def _cfg(**kw) -> FoldConfig:
    base = dict(
        scheme="rolling",
        n_folds=6,
        train_periods=100,
        test_periods=30,
        purge_periods=5,
        embargo_periods=4,
    )
    base.update(kw)
    return FoldConfig.model_validate(base)


def test_every_test_fold_is_after_its_training_window():
    folds = generate_folds(n_periods=1000, config=_cfg())
    assert len(folds) == 6
    for f in folds:
        # Forward-only: test starts at or after the usable train ends.
        assert f.test.start >= f.train.end
        # And with a purge gap it is strictly after.
        assert f.test.start > f.train.end


def test_purge_gap_precedes_each_test_window():
    cfg = _cfg(purge_periods=7)
    folds = generate_folds(n_periods=1000, config=cfg)
    for f in folds:
        # The purge gap is exactly the gap between usable-train end and test start.
        assert f.test.start - f.train.end == 7


def test_rolling_train_is_fixed_length():
    cfg = _cfg(scheme="rolling", train_periods=120)
    folds = generate_folds(n_periods=2000, config=cfg)
    for f in folds:
        assert f.train.length == 120


def test_anchored_train_expands_from_origin():
    cfg = _cfg(scheme="anchored", train_periods=100)
    folds = generate_folds(n_periods=2000, config=cfg)
    # All anchored trains start at the fixed origin 0 and grow.
    assert all(f.train.start == 0 for f in folds)
    lengths = [f.train.length for f in folds]
    assert lengths == sorted(lengths)  # non-decreasing
    assert lengths[-1] > lengths[0]


def test_embargo_offsets_consecutive_test_windows():
    # Consecutive test windows are offset by test_periods + embargo (the embargo is the
    # training data after a test window that the next fold must not train on).
    cfg = _cfg(test_periods=30, embargo_periods=4)
    folds = generate_folds(n_periods=2000, config=cfg)
    offsets = [folds[i + 1].test.start - folds[i].test.start for i in range(len(folds) - 1)]
    assert all(o == 30 + 4 for o in offsets)


def test_no_test_fold_overlaps_another():
    folds = generate_folds(n_periods=2000, config=_cfg())
    for i in range(len(folds)):
        for j in range(i + 1, len(folds)):
            assert not folds[i].test.overlaps(folds[j].test)


def test_folds_stop_when_span_exhausted():
    # A small span fits fewer than n_folds folds; generation stops cleanly (no partials).
    folds = generate_folds(n_periods=200, config=_cfg(n_folds=10))
    assert 0 < len(folds) < 10
    for f in folds:
        assert f.test.end <= 200


def test_no_room_for_any_fold_raises():
    with pytest.raises(WalkForwardError, match="no forward-only fold"):
        generate_folds(n_periods=50, config=_cfg(train_periods=100, test_periods=30))


def test_forward_only_invariant_enforced_on_fold_construction():
    # A hand-built fold whose test precedes train end is rejected at construction.
    from harness.data.walkforward import IndexRange

    with pytest.raises(WalkForwardError):
        Fold(index=0, train=IndexRange(0, 100), test=IndexRange(50, 80))
