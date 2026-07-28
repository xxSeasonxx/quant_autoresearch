"""Train objective and loop-stop math for autonomous strategy research.

The Train objective scores the upstream netted-book NAV path, not aggregate PnL
and not a per-trade return bag. Aggregate PnL can look strong when one symbol, one
regime, one large position, or one lucky slice carries the run; the NAV path makes
the evidence about capital over time.

`full_window_total_return` is the objective: realistic-cost total return over the
full Train window. Subwindows are required diagnostics and minimum-evidence
inputs, not ranking inputs.

1. Read the upstream `realistic_costs` portfolio-foundation metrics and the
   run-level `annualization_periods_per_year` (`P`) from the sizing report.
2. Use `realistic_costs.full_train.total_return` as the run score.
3. For full Train and each configured subwindow, retain the at-risk annualized
   return `R_w = mean_return_w * P` and standard error
   `SE_w = return_volatility_w * P / sqrt(effective_sample_size_w)` for the fixed
   Train strength hurdle and diagnostics.

The score is economic return, proportional to dollars earned at a fixed starting
NAV. Scaling the deployed book's return or changing its duty cycle moves it, which
a scale-invariant ratio (Sharpe, PSR, Calmar) cannot do. Binary gates elsewhere
own viability constraints (trade count, subwindow
coverage, evidence, concentration, cost-stress return retention, path risk,
causality, Train strength, and complexity). A high score with failed gates is not a
keepable candidate.

PSR/Sharpe/Calmar are retained only as diagnostics; they are neither the score nor
a gate. A missing or non-finite full-window total return is non-scoreable. A window
with missing or non-finite at-risk return inputs, non-positive effective sample
size, or zero variance is also non-scoreable because the strength and evidence
diagnostics cannot be evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
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
    active value is `full_window_total_return`; `subwindows` is the number of
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

    `mean_return` and `return_volatility` are the per-period at-risk return
    moments used by the annualized Train-strength diagnostics;
    `effective_sample_size` is the autocorrelation-adjusted sample count behind
    the standard error.
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
    max_average_bar_participation: float | None = None
    max_bar_participation: float | None = None
    minimum_order_notional_ratio: float | None = None
    fixed_cost_share: float | None = None


@dataclass(frozen=True)
class FoundationSizing:
    """Run-level upstream sizing report; one record per quick run.

    `annualization_periods_per_year` (`P`) annualizes every window's per-period
    return moments in both scenarios. The remaining fields describe the deployed
    book scale and the capacity envelope for the ledger and run card.
    """

    annualization_periods_per_year: int
    book_scale: float | None = None
    max_feasible_book_scale: float | None = None
    deployed_volatility: float | None = None
    max_feasible_volatility: float | None = None
    target_reached: bool | None = None


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

    `score` is realistic-cost full-window total return, `None` when the total
    return or required at-risk return diagnostics are non-scoreable.
    `feasible` only means the objective math produced a score; it does not mean
    all strategy gates passed. The window vectors are the per-window at-risk
    annualized `R_w`/`SE_w` values (full Train first, then each subwindow); only the
    Train strength gate binds on the full-Train pair. PSR fields are diagnostics.
    """

    score: float | None
    feasible: bool
    subwindow_trade_counts: tuple[int, ...] = ()
    window_ids: tuple[str, ...] = ()
    window_at_risk_annualized_returns: tuple[float, ...] = ()
    window_at_risk_annualized_standard_errors: tuple[float, ...] = ()
    full_window_total_return: float | None = None
    full_train_at_risk_annualized_return: float | None = None
    full_train_at_risk_annualized_standard_error: float | None = None
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
    full_psr, subwindow_psrs, worst_subwindow_psr, worst_subwindow_id = (
        _diagnostic_psrs(scenario, config)
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

    full_window_total_return = scenario.full_train.total_return
    full_parts = _window_return_se(
        scenario.full_train, periods_per_year=periods_per_year
    )
    full_train_at_risk_annualized_return = None if full_parts is None else full_parts[0]
    full_train_at_risk_annualized_standard_error = (
        None if full_parts is None else full_parts[1]
    )

    window_ids: list[str] = []
    window_at_risk_annualized_returns: list[float] = []
    window_at_risk_annualized_standard_errors: list[float] = []
    for metric in (scenario.full_train, *scenario.subwindows):
        parts = _window_return_se(metric, periods_per_year=periods_per_year)
        if parts is None:
            return ObjectiveResult(
                score=None,
                feasible=False,
                subwindow_trade_counts=counts,
                full_window_total_return=full_window_total_return,
                full_train_at_risk_annualized_return=(
                    full_train_at_risk_annualized_return
                ),
                full_train_at_risk_annualized_standard_error=(
                    full_train_at_risk_annualized_standard_error
                ),
                detail=f"{metric.window_id} non-scoreable window",
                full_train_psr=full_psr,
                subwindow_psrs=subwindow_psrs,
                worst_subwindow_psr=worst_subwindow_psr,
                worst_subwindow_id=worst_subwindow_id,
            )
        window_ids.append(metric.window_id)
        window_at_risk_annualized_returns.append(parts[0])
        window_at_risk_annualized_standard_errors.append(parts[1])

    score = (
        float(full_window_total_return)
        if full_window_total_return is not None and isfinite(full_window_total_return)
        else None
    )

    return ObjectiveResult(
        score=score,
        feasible=score is not None,
        subwindow_trade_counts=counts,
        window_ids=tuple(window_ids),
        window_at_risk_annualized_returns=tuple(window_at_risk_annualized_returns),
        window_at_risk_annualized_standard_errors=tuple(
            window_at_risk_annualized_standard_errors
        ),
        full_window_total_return=score,
        full_train_at_risk_annualized_return=(full_train_at_risk_annualized_return),
        full_train_at_risk_annualized_standard_error=(
            full_train_at_risk_annualized_standard_error
        ),
        detail=("" if score is not None else "full_train non-scoreable total_return"),
        full_train_psr=full_psr,
        subwindow_psrs=subwindow_psrs,
        worst_subwindow_psr=worst_subwindow_psr,
        worst_subwindow_id=worst_subwindow_id,
    )


def train_strength_floor(
    objective: ObjectiveResult, *, haircut_se: float
) -> float | None:
    """Full-Train at-risk annualized return lower bound for Train strength.

    Applies the fixed Train strength hurdle to the objective's full-Train `R`/`SE`.
    This is a development filter, not statistical proof or a best-of-N correction.
    Per-subwindow values are diagnostics, not gated.
    """

    annualized_return = objective.full_train_at_risk_annualized_return
    standard_error = objective.full_train_at_risk_annualized_standard_error
    if annualized_return is None or standard_error is None:
        return None
    if not (isfinite(annualized_return) and isfinite(standard_error)):
        return None
    return annualized_return - haircut_se * standard_error


def score_foundation_cost_stress(
    foundation: FoundationEvidence,
    config: ObjectiveConfig,
) -> ObjectiveResult:
    """Compute the cost-stress scenario metrics used by the retention gate.

    Used for the cost-stress return-retention gate (via the full-Train at-risk
    annualized return) and as a run-card diagnostic; it is not a gated run score.
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

    if config.kind != "full_window_total_return":
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
