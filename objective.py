"""Train objective and loop-stop math for autonomous strategy research.

The core Train objective is intentionally not aggregate PnL. Aggregate PnL can
look strong when one symbol, one regime, one large position, or one lucky time
slice carries the run. This module instead scores trade-unit robustness:

Selectable objective kinds today:

- `worst_subwindow`: the only supported `objective.kind`. It scores every
  configured Train time slice and uses the weakest slice as the run score.

Not selectable as objective kinds today:

- aggregate net return, average trade return, win rate, profit factor, gross
  return, or cost-stressed score. Those are diagnostics or gates. They can help
  explain why a candidate worked or failed, but they do not decide the primary
  keep/discard score.

`worst_subwindow` is calculated as:

1. Split the configured Train window into contiguous time subwindows.
2. For each subwindow, score the completed trade net returns as mean / sigma.
3. Use the minimum subwindow score as the run score.

That makes the score a development filter for consistency, not a proof of an
edge. Binary gates elsewhere still own basic viability constraints such as
minimum trade count, subwindow coverage, concentration, cost stress, complexity,
and Train score floor. A high score with failed gates is not a keepable
candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import fmean, pstdev
from typing import Sequence


@dataclass(frozen=True)
class LoopConfig:
    plateau_patience: int
    max_iterations: int
    min_abs_improvement: float
    min_rel_improvement: float
    baseline_grace_iterations: int


@dataclass(frozen=True)
class ObjectiveConfig:
    """Configured Train objective.

    `kind` is intentionally narrow today. The only accepted value is
    `worst_subwindow`; protocol loading and `score_objective` reject any other
    objective kind. `subwindows` is the number of equal-duration slices used to
    test whether the strategy works across the Train window rather than only in
    one favorable regime.
    """

    kind: str
    subwindows: int


@dataclass(frozen=True)
class TradeSample:
    """Completed trade input used by the objective.

    `net_return` is already after protocol-owned costs/fills. The base objective
    scores these net returns as trade units; it does not multiply returns by
    notional or optimize aggregate capital usage. `weight` is kept for cost
    stress so larger emitted positions pay a larger extra round-trip penalty.
    """

    symbol: str
    decision_time: datetime
    net_return: float
    weight: float = 1.0
    gross_return: float | None = None
    cost_return: float | None = None


@dataclass(frozen=True)
class ObjectiveResult:
    """Result of objective scoring.

    `score` is `None` when the run cannot be scored at all, for example no
    trades or non-finite returns. `feasible` only means the objective math
    produced a score; it does not mean all strategy gates passed.
    """

    score: float | None
    feasible: bool
    subwindow_scores: tuple[float, ...]
    subwindow_trade_counts: tuple[int, ...]
    detail: str = ""


def _score_returns(values: Sequence[float]) -> float:
    """Score one subwindow's trade returns as mean / population stddev.

    Positive mean and low dispersion produce a higher score. Negative mean or
    noisy trade outcomes pull the score down. For one trade, or for a flat set
    of identical returns, there is no dispersion estimate to divide by, so the
    mean is returned directly.
    """

    if not values:
        return 0.0
    mean = fmean(values)
    if len(values) == 1:
        return mean
    sigma = pstdev(values)
    if sigma == 0.0:
        return mean
    return mean / sigma


def _time_buckets(
    trades: Sequence[TradeSample],
    *,
    subwindows: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[tuple[TradeSample, ...], ...]:
    """Assign trades to contiguous time buckets over the Train window.

    When `window_start` and `window_end` are provided by the protocol, empty
    subwindows stay visible instead of shrinking the objective around emitted
    trades. That is important: a strategy that only trades during favorable
    parts of Train should show sparse or empty slices rather than receive a
    friendlier window.
    """

    ordered = sorted(trades, key=lambda trade: trade.decision_time)
    if not ordered:
        return ()
    start = window_start or ordered[0].decision_time
    include_end = window_end is None
    end = window_end or ordered[-1].decision_time
    if end < start:
        raise ValueError("window_end must be >= window_start")
    if start == end:
        return (tuple(ordered),) + tuple(() for _ in range(subwindows - 1))

    total_seconds = (end - start).total_seconds()
    buckets: list[list[TradeSample]] = [[] for _ in range(subwindows)]
    for trade in ordered:
        if trade.decision_time < start:
            continue
        if include_end:
            if trade.decision_time > end:
                continue
        elif trade.decision_time >= end:
            continue
        offset = (trade.decision_time - start).total_seconds()
        index = min(subwindows - 1, int(offset / total_seconds * subwindows))
        buckets[index].append(trade)
    return tuple(tuple(bucket) for bucket in buckets)


def score_worst_subwindow(
    trades: Sequence[TradeSample],
    *,
    subwindows: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> ObjectiveResult:
    """Score Train robustness as the weakest time slice.

    Each subwindow receives a trade-unit score from `_score_returns`. The final
    score is `min(subwindow_scores)`, so a candidate must be reasonably robust
    across the full Train window instead of relying on one strong period.

    Subwindow coverage is intentionally not enforced here. The objective reports
    counts, while gates decide whether sparse buckets are acceptable.
    """

    if subwindows < 1:
        raise ValueError("subwindows must be >= 1")
    if not trades:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            subwindow_trade_counts=(),
            detail="no trades",
        )

    scores: list[float] = []
    counts: list[int] = []
    for chunk in _time_buckets(
        trades,
        subwindows=subwindows,
        window_start=window_start,
        window_end=window_end,
    ):
        values = [float(trade.net_return) for trade in chunk]
        counts.append(len(values))
        if any(not isfinite(value) for value in values):
            return ObjectiveResult(
                score=None,
                feasible=False,
                subwindow_scores=tuple(scores),
                subwindow_trade_counts=tuple(counts),
                detail="non-finite trade return",
            )
        scores.append(_score_returns(values))

    if not scores:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            subwindow_trade_counts=(),
            detail="no valid subwindows",
        )
    return ObjectiveResult(
        score=min(scores),
        feasible=True,
        subwindow_scores=tuple(scores),
        subwindow_trade_counts=tuple(counts),
    )


def score_objective(
    trades: Sequence[TradeSample],
    config: ObjectiveConfig,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> ObjectiveResult:
    """Dispatch to the configured Train objective."""

    if config.kind == "worst_subwindow":
        return score_worst_subwindow(
            trades,
            subwindows=config.subwindows,
            window_start=window_start,
            window_end=window_end,
        )
    raise ValueError(f"unsupported objective kind: {config.kind}")


def score_cost_stress(
    trades: Sequence[TradeSample],
    *,
    subwindows: int,
    extra_round_trip_bps: float,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> ObjectiveResult:
    """Re-score after adding an extra round-trip cost penalty.

    Cost stress asks whether the same trade distribution survives a harsher cost
    assumption. The penalty is proportional to `abs(weight)` because larger
    emitted positions should be more sensitive to extra costs.
    """

    stressed = tuple(
        TradeSample(
            symbol=trade.symbol,
            decision_time=trade.decision_time,
            net_return=trade.net_return - abs(trade.weight) * extra_round_trip_bps / 10_000.0,
            weight=trade.weight,
        )
        for trade in trades
    )
    return score_worst_subwindow(
        stressed,
        subwindows=subwindows,
        window_start=window_start,
        window_end=window_end,
    )


def is_improvement(
    score: float | None,
    best_score: float | None,
    gates_passed: bool,
    loop: LoopConfig,
) -> bool:
    """Return whether a scored attempt updates the best Train survivor.

    Gates must pass before score improvement matters. The threshold combines an
    absolute floor and a relative floor so tiny numerical moves do not reset
    plateau patience or create a new survivor.
    """

    if score is None or not gates_passed:
        return False
    if best_score is None:
        return True
    threshold = max(
        loop.min_abs_improvement,
        loop.min_rel_improvement * max(1.0, abs(best_score)),
    )
    return score > best_score + threshold


def plateau_reached(
    *,
    non_improving_since_best: int,
    feasible_baseline: bool,
    loop: LoopConfig,
) -> bool:
    """Return whether non-improving attempts have exhausted patience."""

    return feasible_baseline and non_improving_since_best >= loop.plateau_patience


def max_iterations_reached(*, completed_iterations: int, loop: LoopConfig) -> bool:
    """Return whether the configured hard iteration cap has been reached."""

    return completed_iterations >= loop.max_iterations
