"""Forward-only walk-forward folds with purge + embargo (FR-B2, FR-B3).

Selection is a rolling (default) or anchored walk-forward: train on a window, score the
next (strictly later) window, roll forward. Every test fold sits **after** its training
window. Adjacent blocks are separated by:

- a **purge** gap of ``purge_periods`` immediately *before* each test window, removed from
  that fold's training window (no label/position straddles the boundary — sized to the
  holding/label horizon), and
- an **embargo** of ``embargo_periods`` immediately *after* a test window, removed from the
  *following* fold's training window (AFML: embargo applies to training data that follows a
  test window, mattering most under combinatorial folds).

Pure integer-period arithmetic: a fold is a set of ``[start, end)`` index ranges over a
span of ``n_periods`` bars. Mapping indices to calendar timestamps (for the foundation's
per-fold ``[[windows]]``) is the caller's job (it owns the bar cadence + span origin), which
keeps this module unit-testable with no data and no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from harness.protocol import FoldConfig

Scheme = Literal["rolling", "anchored"]


class WalkForwardError(ValueError):
    """Raised when the configured walk-forward cannot fit forward-only folds in the span."""


@dataclass(frozen=True)
class IndexRange:
    """A half-open ``[start, end)`` range of integer period indices."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise WalkForwardError(f"invalid index range [{self.start}, {self.end})")

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: "IndexRange") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold: a training range and a strictly-later test range.

    ``train`` is the *purged/embargoed* training window actually usable for this fold
    (the purge gap before the test window and any embargo from the prior test window are
    already removed). ``test`` is the OOS Selection window the foundation scores.
    """

    index: int
    train: IndexRange
    test: IndexRange

    def __post_init__(self) -> None:
        # Forward-only: the test window must begin at or after the (usable) training window
        # ends. With a purge gap it begins strictly after.
        if self.test.start < self.train.end:
            raise WalkForwardError(
                f"fold {self.index} test starts at {self.test.start} before train ends "
                f"at {self.train.end} (walk-forward must be forward-only, FR-B2)"
            )


def generate_folds(
    n_periods: int,
    config: FoldConfig,
) -> tuple[Fold, ...]:
    """Generate forward-only folds over ``n_periods`` bars from a ``FoldConfig``.

    Rolling (default): a fixed-length ``train_periods`` window immediately precedes each
    test window (minus the purge gap). Anchored: the training window expands from index 0
    (the fixed start) up to the purge gap before each test window.

    Spacing per fold ``i`` (test windows tile forward with an embargo between them):
      - ``test_start_i`` = ``train_periods + purge + i * (test_periods + embargo)``  (rolling)
        so the first test window sits after one full train block + purge, and each later
        test window is offset by its own length plus the embargo applied to the training
        data that follows the previous test window.
      - ``train_i`` ends at ``test_start_i - purge`` (purge gap before test). Rolling train
        starts at ``test_start_i - purge - train_periods``; anchored train starts at 0.

    Raises if not even one forward-only fold fits.
    """
    if n_periods <= 0:
        raise WalkForwardError("n_periods must be positive")
    train_p = config.train_periods
    test_p = config.test_periods
    purge = config.purge_periods
    embargo = config.embargo_periods
    scheme: Scheme = config.scheme  # type: ignore[assignment]
    if scheme not in ("rolling", "anchored"):
        raise WalkForwardError(f"unknown walk-forward scheme {scheme!r}")

    folds: list[Fold] = []
    for i in range(config.n_folds):
        test_start = train_p + purge + i * (test_p + embargo)
        test_end = test_start + test_p
        if test_end > n_periods:
            break  # no more room for a full test window — stop (forward-only, no partials)
        train_end = test_start - purge
        if scheme == "rolling":
            train_start = train_end - train_p
        else:  # anchored: expand from the fixed origin
            train_start = 0
        if train_start < 0:
            # Not enough history before this test window for a full training block.
            raise WalkForwardError(
                f"fold {i}: training window underflows the span "
                f"(need {train_p} train + {purge} purge before test at {test_start})"
            )
        folds.append(
            Fold(
                index=i,
                train=IndexRange(train_start, train_end),
                test=IndexRange(test_start, test_end),
            )
        )

    if not folds:
        raise WalkForwardError(
            f"no forward-only fold fits: n_periods={n_periods}, train={train_p}, "
            f"test={test_p}, purge={purge}, embargo={embargo}"
        )
    return tuple(folds)
