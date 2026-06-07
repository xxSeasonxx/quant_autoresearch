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
    kind: str
    subwindows: int


@dataclass(frozen=True)
class TradeSample:
    symbol: str
    decision_time: datetime
    net_return: float
    weight: float = 1.0
    gross_return: float | None = None
    cost_return: float | None = None


@dataclass(frozen=True)
class ObjectiveResult:
    score: float | None
    feasible: bool
    subwindow_scores: tuple[float, ...]
    detail: str = ""


def _score_returns(values: Sequence[float]) -> float:
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
    ordered = sorted(trades, key=lambda trade: trade.decision_time)
    if not ordered:
        return ()
    start = window_start or ordered[0].decision_time
    end = window_end or ordered[-1].decision_time
    if end < start:
        raise ValueError("window_end must be >= window_start")
    if start == end:
        return (tuple(ordered),) + tuple(() for _ in range(subwindows - 1))

    total_seconds = (end - start).total_seconds()
    buckets: list[list[TradeSample]] = [[] for _ in range(subwindows)]
    for trade in ordered:
        if trade.decision_time < start or trade.decision_time >= end:
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
    if subwindows < 1:
        raise ValueError("subwindows must be >= 1")
    if not trades:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            detail="no trades",
        )

    scores: list[float] = []
    for chunk in _time_buckets(
        trades,
        subwindows=subwindows,
        window_start=window_start,
        window_end=window_end,
    ):
        values = [float(trade.net_return) for trade in chunk]
        if any(not isfinite(value) for value in values):
            return ObjectiveResult(
                score=None,
                feasible=False,
                subwindow_scores=tuple(scores),
                detail="non-finite trade return",
            )
        scores.append(_score_returns(values))

    if not scores:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            detail="no valid subwindows",
        )
    return ObjectiveResult(
        score=min(scores),
        feasible=True,
        subwindow_scores=tuple(scores),
    )


def score_objective(
    trades: Sequence[TradeSample],
    config: ObjectiveConfig,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> ObjectiveResult:
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
    return feasible_baseline and non_improving_since_best >= loop.plateau_patience


def max_iterations_reached(*, completed_iterations: int, loop: LoopConfig) -> bool:
    return completed_iterations >= loop.max_iterations
