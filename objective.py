"""Train objective and loop-stop math for autonomous strategy research.

The Train objective scores the upstream netted-book NAV path, not aggregate PnL
and not a per-trade return bag. Aggregate PnL can look strong when one symbol, one
regime, one large position, or one lucky slice carries the run; the NAV path makes
the evidence about capital over time.

`portfolio_psr_subwindow` is the objective:

1. Read the upstream `realistic_costs` portfolio-foundation metrics.
2. Compute PSR for full Train and each configured Train subwindow.
3. Use `min(full_train_psr, min(subwindow_psrs))` as the run score.

PSR puts the score on a probability scale and adjusts for Sharpe uncertainty via
the upstream Sharpe standard error. The `min(...)` shape is a development filter
for consistency across the whole Train window, not proof of an edge. Binary gates
elsewhere own viability constraints (trade count, subwindow coverage, evidence,
concentration, cost stress, path risk, economic magnitude, complexity, and the
Train score floor). A high score with failed gates is not a keepable candidate.

A subwindow the upstream foundation cannot score (too few at-risk-bar return
samples) yields no PSR, so the run is non-scoreable rather than assigned a finite
Sharpe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import NormalDist
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

    `kind` is intentionally narrow for active protocol loading. The supported
    active value is `portfolio_psr_subwindow`; `subwindows` is the number of
    equal-duration slices used to test whether the strategy works across the
    Train window rather than only in one favorable regime.
    """

    kind: str
    subwindows: int
    psr_hurdle_sharpe: float = 0.0


@dataclass(frozen=True)
class FoundationMetric:
    """Upstream-owned portfolio-return metric record used by local scoring."""

    window_id: str
    return_sample_count: int
    effective_sample_size: float | None
    sharpe: float | None
    sharpe_standard_error: float | None
    total_return: float | None
    max_drawdown: float | None
    closed_trade_count: int
    max_symbol_concentration: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoundationScenario:
    """One upstream portfolio-foundation scenario."""

    scenario_id: str
    full_train: FoundationMetric
    subwindows: tuple[FoundationMetric, ...]


@dataclass(frozen=True)
class FoundationEvidence:
    """Portfolio-foundation scenarios emitted by quick run."""

    realistic_costs: FoundationScenario
    cost_stress: FoundationScenario


@dataclass(frozen=True)
class TradeSample:
    """Completed trade from the upstream per-trade attribution ledger.

    The per-trade tape is a derived attribution view of the one NAV book; it feeds
    diagnostics (win rate, profit factor, average net) and the trade-bag fallback
    for symbol concentration, but it is not scored. `net_return` is already after
    protocol-owned costs/fills; `weight` is the emitted position weight.
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
    full_train_psr: float | None = None
    subwindow_psrs: tuple[float, ...] = ()
    worst_subwindow_id: str = ""


def _psr(metric: FoundationMetric, *, hurdle: float) -> tuple[float | None, str]:
    sharpe = metric.sharpe
    sharpe_se = metric.sharpe_standard_error
    if sharpe is None:
        return None, f"{metric.window_id} missing sharpe"
    if sharpe_se is None:
        return None, f"{metric.window_id} missing sharpe_standard_error"
    if not isfinite(float(sharpe)):
        return None, f"{metric.window_id} non-finite sharpe"
    if not isfinite(float(sharpe_se)) or float(sharpe_se) <= 0.0:
        return None, f"{metric.window_id} invalid sharpe_standard_error"
    value = NormalDist().cdf((float(sharpe) - hurdle) / float(sharpe_se))
    return value, ""


def _score_foundation_scenario(
    scenario: FoundationScenario,
    config: ObjectiveConfig,
) -> ObjectiveResult:
    if len(scenario.subwindows) != config.subwindows:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            subwindow_trade_counts=tuple(
                metric.closed_trade_count for metric in scenario.subwindows
            ),
            detail=(
                f"foundation subwindow count {len(scenario.subwindows)} "
                f"!= configured {config.subwindows}"
            ),
        )

    full_psr, detail = _psr(
        scenario.full_train,
        hurdle=config.psr_hurdle_sharpe,
    )
    if full_psr is None:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            subwindow_trade_counts=tuple(
                metric.closed_trade_count for metric in scenario.subwindows
            ),
            detail=detail,
        )

    subwindow_psrs: list[float] = []
    counts: list[int] = []
    for metric in scenario.subwindows:
        counts.append(metric.closed_trade_count)
        value, detail = _psr(metric, hurdle=config.psr_hurdle_sharpe)
        if value is None:
            return ObjectiveResult(
                score=None,
                feasible=False,
                subwindow_scores=tuple(subwindow_psrs),
                subwindow_trade_counts=tuple(counts),
                detail=detail,
                full_train_psr=full_psr,
                subwindow_psrs=tuple(subwindow_psrs),
            )
        subwindow_psrs.append(value)

    worst_index, worst_psr = min(
        enumerate(subwindow_psrs),
        key=lambda item: item[1],
    )
    score = min(full_psr, worst_psr)
    worst_subwindow_id = scenario.subwindows[worst_index].window_id
    return ObjectiveResult(
        score=score,
        feasible=True,
        subwindow_scores=tuple(subwindow_psrs),
        subwindow_trade_counts=tuple(counts),
        full_train_psr=full_psr,
        subwindow_psrs=tuple(subwindow_psrs),
        worst_subwindow_id=worst_subwindow_id,
    )


def score_foundation_cost_stress(
    foundation: FoundationEvidence,
    config: ObjectiveConfig,
) -> ObjectiveResult:
    """Score upstream cost-stress portfolio foundation with the live PSR rule."""

    return _score_foundation_scenario(foundation.cost_stress, config)


def score_objective(
    trades: Sequence[TradeSample],
    config: ObjectiveConfig,
    *,
    foundation: FoundationEvidence | None = None,
) -> ObjectiveResult:
    """Score the run from the upstream portfolio foundation.

    `trades` are accepted for call symmetry with the loop's diagnostics path but
    are not scored: the scored unit is the netted-book NAV path, read from the
    foundation's realistic-costs scenario.
    """

    if config.kind != "portfolio_psr_subwindow":
        raise ValueError(f"unsupported objective kind: {config.kind}")
    if foundation is None:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_scores=(),
            subwindow_trade_counts=(),
            detail="portfolio foundation unavailable",
        )
    return _score_foundation_scenario(foundation.realistic_costs, config)


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
