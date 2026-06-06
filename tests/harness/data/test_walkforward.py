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


def test_embargo_is_the_gap_between_consecutive_test_windows():
    # The embargo's REAL, mechanically-enforced effect is the gap separating consecutive OOS
    # test windows: no two test windows are adjacent — exactly `embargo_periods` of untested
    # bars sit between one test's end and the next test's start. (Asserted directly on the
    # inter-test GAP, not merely the stride, so the guarantee is pinned, not inferred.)
    cfg = _cfg(test_periods=30, embargo_periods=4)
    folds = generate_folds(n_periods=2000, config=cfg)
    gaps = [folds[i + 1].test.start - folds[i].test.end for i in range(len(folds) - 1)]
    assert all(g == 4 for g in gaps)


def test_embargo_does_not_carve_the_per_fold_train():
    """The honest `Fold.train` contract: a purged pre-fold-test window, NOT embargo-carved.

    With the forward-chaining test schedule (consecutive tests separated only by the embargo),
    there is no clean per-fold training window left to carve an embargo out of — a genuine
    embargo-carve would leave every fold after the first with an empty train. So the embargo's
    effect lives on the TEST schedule (the inter-test gap, asserted above), and `train` stays
    the full `train_periods` window ending exactly `purge` before its own test. Nothing in the
    harness fits per-fold (the orchestrator uses only `fold.test`); this pins that real
    guarantee. It FAILS the old docstring's false claim that the prior test's embargo is
    "already removed" from this fold's train (a carve would shorten the train below
    train_periods or move its end off the purge boundary).
    """
    train_p, purge, embargo = 100, 5, 4
    folds = generate_folds(
        n_periods=2000, config=_cfg(train_periods=train_p, purge_periods=purge, embargo_periods=embargo)
    )
    for f in folds:
        # train is purged from its OWN test: end sits exactly `purge` before the test start.
        assert f.test.start - f.train.end == purge
        # rolling train is the full train_periods window — the embargo did NOT carve it.
        assert f.train.length == train_p

    # Changing ONLY the embargo widens the inter-test gap but leaves the train window length
    # untouched (the embargo is not carved out of train).
    more_embargo = generate_folds(
        n_periods=2000, config=_cfg(train_periods=train_p, purge_periods=purge, embargo_periods=embargo + 10)
    )
    for f in more_embargo:
        assert f.train.length == train_p  # still uncarved despite a larger embargo
    gaps = [more_embargo[i + 1].test.start - more_embargo[i].test.end for i in range(len(more_embargo) - 1)]
    assert all(g == embargo + 10 for g in gaps)


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
