"""Train objective and loop-stop math for autonomous strategy research.

The Train objective scores the upstream netted-book NAV path, not aggregate PnL
and not a per-trade return bag. Aggregate PnL can look strong when one symbol, one
regime, one large position, or one lucky slice carries the run; the NAV path makes
the evidence about capital over time.

`return_lcb_subwindow` is the objective: the full-Train deployed-return lower
confidence bound. Subwindows are computed and reported as diagnostics (regime
stability), not scored — the score and gate bind on the full-Train window.

1. Read the upstream `realistic_costs` portfolio-foundation metrics and the
   run-level `annualization_periods_per_year` (`P`) from the sizing report.
2. For full Train and each configured subwindow, form the deployed annualized
   return `R_w = mean_return_w * P` and its standard error
   `SE_w = return_volatility_w * P / sqrt(effective_sample_size_w)`.
3. Use `min over windows of (R_w - k_rank * SE_w)` as the run score, `k_rank = 1`.

The score is denominated in money: scaling the deployed book's return moves it,
which a scale-invariant ratio (Sharpe, PSR, Calmar) cannot do. The `min(...)` shape
plus the SE haircut is a robustness filter across the whole Train window, not proof
of an edge. Binary gates elsewhere own viability constraints (trade count,
subwindow coverage, evidence, concentration, cost-stress return retention, path
risk, causality, the deflated money floor, and complexity). A high score with
failed gates is not a keepable candidate.

PSR/Sharpe/Calmar are retained only as diagnostics; they are neither the score nor
a gate. A window the upstream foundation cannot score for money (missing or
non-finite mean/volatility, non-positive effective sample size, or zero variance)
yields no lower bound, so the run is non-scoreable rather than assigned a finite
score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
from statistics import NormalDist
from typing import Sequence

# Ranking haircut: the per-window SE multiple folded into the run score. A code
# constant, not operator-tuned; the operator-owned acceptance haircut `k_accept`
# (`gates.score_haircut_se`) is a separate, stricter multiple used only by the
# money-floor gate.
_K_RANK = 1.0


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
    active value is `return_lcb_subwindow`; `subwindows` is the number of
    equal-duration slices used to test whether the strategy works across the
    Train window rather than only in one favorable regime. `psr_hurdle_sharpe`
    parameterizes the diagnostic PSR only; it is not the run score or a gate.
    """

    kind: str
    subwindows: int
    psr_hurdle_sharpe: float = 0.0


@dataclass(frozen=True)
class FoundationMetric:
    """Upstream-owned portfolio-return metric record used by local scoring.

    `mean_return` and `return_volatility` are the per-period deployed-return
    moments the money score annualizes; `effective_sample_size` is the
    autocorrelation-adjusted sample count behind the SE haircut.
    """

    window_id: str
    return_sample_count: int
    effective_sample_size: float | None
    mean_return: float | None
    return_volatility: float | None
    sharpe: float | None
    sharpe_standard_error: float | None
    total_return: float | None
    max_drawdown: float | None
    closed_trade_count: int
    max_symbol_concentration: float | None
    warnings: tuple[str, ...] = ()
    max_gross_utilization: float | None = None
    max_net_utilization: float | None = None
    effective_symbol_count: float | None = None


@dataclass(frozen=True)
class FoundationScenario:
    """One upstream portfolio-foundation scenario."""

    scenario_id: str
    full_train: FoundationMetric
    subwindows: tuple[FoundationMetric, ...]
    max_adv_participation: float | None = None
    max_bar_participation: float | None = None


@dataclass(frozen=True)
class FoundationSizing:
    """Run-level upstream sizing report; one record per quick run.

    `annualization_periods_per_year` (`P`) annualizes every window's per-period
    return moments in both scenarios. The remaining fields describe the deployed
    book scale and the capacity envelope for the ledger and run card.
    """

    annualization_periods_per_year: int
    book_scale: float | None = None
    deployed_volatility: float | None = None
    max_feasible_volatility: float | None = None
    capacity_bound: bool | None = None


@dataclass(frozen=True)
class FoundationEvidence:
    """Portfolio-foundation scenarios and sizing report emitted by quick run."""

    realistic_costs: FoundationScenario
    cost_stress: FoundationScenario
    sizing: FoundationSizing


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

    `score` is the full-Train deployed-return lower bound at `k_rank`, `None`
    when any window cannot yield a lower bound (the run is non-scoreable).
    `feasible` only means the objective math produced a score; it does not mean
    all strategy gates passed. `window_returns`/`window_return_ses` are the
    per-window `R_w`/`SE_w` (full Train first, then each subwindow); the score and
    the significance gate bind on the full-Train window (index 0), and the subwindow
    entries are reported as diagnostics. PSR fields are diagnostics only.
    """

    score: float | None
    feasible: bool
    subwindow_trade_counts: tuple[int, ...] = ()
    window_ids: tuple[str, ...] = ()
    window_returns: tuple[float, ...] = ()
    window_return_ses: tuple[float, ...] = ()
    full_train_return: float | None = None
    full_train_return_se: float | None = None
    detail: str = ""
    full_train_psr: float | None = None
    subwindow_psrs: tuple[float, ...] = ()
    worst_subwindow_psr: float | None = None
    worst_subwindow_id: str = ""


def _psr(metric: FoundationMetric, *, hurdle: float) -> float | None:
    """Diagnostic probabilistic Sharpe ratio; `None` when inputs are unusable."""

    sharpe = metric.sharpe
    sharpe_se = metric.sharpe_standard_error
    if sharpe is None or sharpe_se is None:
        return None
    if not isfinite(float(sharpe)):
        return None
    if not isfinite(float(sharpe_se)) or float(sharpe_se) <= 0.0:
        return None
    return NormalDist().cdf((float(sharpe) - hurdle) / float(sharpe_se))


def _diagnostic_psrs(
    scenario: FoundationScenario, config: ObjectiveConfig
) -> tuple[float | None, tuple[float, ...], float | None, str]:
    """Full-Train and per-subwindow diagnostic PSRs (present values only)."""

    full = _psr(scenario.full_train, hurdle=config.psr_hurdle_sharpe)
    present: list[tuple[str, float]] = []
    for metric in scenario.subwindows:
        value = _psr(metric, hurdle=config.psr_hurdle_sharpe)
        if value is not None:
            present.append((metric.window_id, value))
    if not present:
        return full, (), None, ""
    worst_id, worst = min(present, key=lambda item: item[1])
    return full, tuple(value for _, value in present), worst, worst_id


def _window_return_se(
    metric: FoundationMetric, *, periods_per_year: int
) -> tuple[float, float] | None:
    """Deployed annualized return `R_w` and its standard error `SE_w`.

    Returns `None` when the window yields no lower bound: missing or non-finite
    mean/volatility/effective-sample-size, non-positive effective sample size, or
    zero variance (a zero-variance window gets no free pass).
    """

    mean_return = metric.mean_return
    volatility = metric.return_volatility
    n_eff = metric.effective_sample_size
    if mean_return is None or volatility is None or n_eff is None:
        return None
    if not (isfinite(mean_return) and isfinite(volatility) and isfinite(n_eff)):
        return None
    if n_eff <= 0.0 or volatility <= 0.0:
        return None
    annualized_return = mean_return * periods_per_year
    standard_error = volatility * periods_per_year / sqrt(n_eff)
    return annualized_return, standard_error


def _score_foundation_scenario(
    scenario: FoundationScenario,
    config: ObjectiveConfig,
    *,
    periods_per_year: int,
) -> ObjectiveResult:
    counts = tuple(metric.closed_trade_count for metric in scenario.subwindows)
    full_psr, subwindow_psrs, worst_subwindow_psr, worst_subwindow_id = _diagnostic_psrs(
        scenario, config
    )
    if len(scenario.subwindows) != config.subwindows:
        return ObjectiveResult(
            score=None,
            feasible=False,
            subwindow_trade_counts=counts,
            detail=(
                f"foundation subwindow count {len(scenario.subwindows)} "
                f"!= configured {config.subwindows}"
            ),
            full_train_psr=full_psr,
            subwindow_psrs=subwindow_psrs,
            worst_subwindow_psr=worst_subwindow_psr,
            worst_subwindow_id=worst_subwindow_id,
        )

    full_parts = _window_return_se(scenario.full_train, periods_per_year=periods_per_year)
    full_train_return = None if full_parts is None else full_parts[0]
    full_train_return_se = None if full_parts is None else full_parts[1]

    window_ids: list[str] = []
    window_returns: list[float] = []
    window_return_ses: list[float] = []
    for metric in (scenario.full_train, *scenario.subwindows):
        parts = _window_return_se(metric, periods_per_year=periods_per_year)
        if parts is None:
            return ObjectiveResult(
                score=None,
                feasible=False,
                subwindow_trade_counts=counts,
                full_train_return=full_train_return,
                detail=f"{metric.window_id} non-scoreable window",
                full_train_psr=full_psr,
                subwindow_psrs=subwindow_psrs,
                worst_subwindow_psr=worst_subwindow_psr,
                worst_subwindow_id=worst_subwindow_id,
            )
        window_ids.append(metric.window_id)
        window_returns.append(parts[0])
        window_return_ses.append(parts[1])

    # Full-Train deployed-return lower bound is the run score and the significance-gate
    # input (full_train is index 0). It is the binding in-sample robustness
    # instrument; per-subwindow returns are reported diagnostics, not gated, so
    # neither the score nor the floor binds on the noisiest short subwindow.
    score = window_returns[0] - _K_RANK * window_return_ses[0]
    return ObjectiveResult(
        score=score,
        feasible=True,
        subwindow_trade_counts=counts,
        window_ids=tuple(window_ids),
        window_returns=tuple(window_returns),
        window_return_ses=tuple(window_return_ses),
        full_train_return=full_train_return,
        full_train_return_se=full_train_return_se,
        full_train_psr=full_psr,
        subwindow_psrs=subwindow_psrs,
        worst_subwindow_psr=worst_subwindow_psr,
        worst_subwindow_id=worst_subwindow_id,
    )


def deflated_window_floor(
    objective: ObjectiveResult, *, k_accept: float
) -> float | None:
    """Full-Train deployed-return lower bound at the acceptance haircut.

    Reuses the objective's full-Train `R`/`SE`; only the haircut multiple differs
    from the run score. `None` when the run is non-scoreable. This deflated
    full-Train floor is the binding in-sample robustness gate; per-subwindow
    returns are reported diagnostics, not gated.
    """

    if objective.full_train_return is None or objective.full_train_return_se is None:
        return None
    if not (
        isfinite(objective.full_train_return)
        and isfinite(objective.full_train_return_se)
    ):
        return None
    return objective.full_train_return - k_accept * objective.full_train_return_se


def score_foundation_cost_stress(
    foundation: FoundationEvidence,
    config: ObjectiveConfig,
) -> ObjectiveResult:
    """Score the upstream cost-stress scenario with the money-LCB rule.

    Used for the cost-stress return-retention gate (via `full_train_return`) and
    as a run-card diagnostic; it is not a gated run score on its own.
    """

    return _score_foundation_scenario(
        foundation.cost_stress,
        config,
        periods_per_year=foundation.sizing.annualization_periods_per_year,
    )


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

    if config.kind != "return_lcb_subwindow":
        raise ValueError(f"unsupported objective kind: {config.kind}")
    if foundation is None:
        return ObjectiveResult(
            score=None,
            feasible=False,
            detail="portfolio foundation unavailable",
        )
    return _score_foundation_scenario(
        foundation.realistic_costs,
        config,
        periods_per_year=foundation.sizing.annualization_periods_per_year,
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
