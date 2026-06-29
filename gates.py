"""Binary viability gates for a scored Train attempt.

Gates are separate from the run score: a high score with a failed gate is not a
keepable candidate, and a failed gate never changes the score. The money-first
gates are:

- ``money_floor``: the weakest-window deployed-return lower bound at the
  acceptance haircut ``k_accept`` (``gates.score_haircut_se``) must clear
  ``min_annualized_return``. ``k_accept`` is the multiple-testing correction for
  the best-of-N search and is stricter than the score's ranking haircut.
- ``cost_stress_retention``: the cost-stress full-Train annualized return must
  retain at least ``min_cost_stress_return_retention`` of the realistic
  full-Train return, evaluated only when the realistic return is positive (a
  non-positive realistic return is the money floor's kill, so retention is then
  non-binding).
- ``causality``: upstream replay evidence must be score-admissible. A bounded
  micro replay can be admissible for Train scoring without being retention-
  verified for downstream deployment review.

The remaining gates (trade floor, minimum evidence, path risk, breadth,
complexity cap) constrain the evidence behind the score.

Per-subwindow trade counts and per-slice returns are reported diagnostics, not
gates: per-window sample sufficiency is owned by ``minimum_evidence`` (return
samples and effective sample size, the latter autocorrelation-adjusted), and the
binding in-sample robustness gate is the full-Train deflated ``money_floor``.
Per-slice return sign on contiguous, autocorrelated calendar slices is not gated
— it cannot test regime independence (the firewalled OOS stage does that) and
double-counts the full-Train deflation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

from objective import (
    FoundationScenario,
    ObjectiveResult,
    TradeSample,
    deflated_window_floor,
)


@dataclass(frozen=True)
class GateConfig:
    min_trades: int
    min_return_sample_count: int
    min_effective_sample_size: float
    max_symbol_concentration: float
    min_cost_stress_return_retention: float
    max_abs_drawdown: float
    min_annualized_return: float
    score_haircut_se: float
    max_components: int
    max_params: int


@dataclass(frozen=True)
class GateOutcome:
    name: str
    passed: bool
    value: float | None
    threshold: float | None
    detail: str = ""


@dataclass(frozen=True)
class GateSet:
    outcomes: tuple[GateOutcome, ...]

    @property
    def passed(self) -> bool:
        return all(outcome.passed for outcome in self.outcomes)

    @property
    def by_name(self) -> dict[str, GateOutcome]:
        return {outcome.name: outcome for outcome in self.outcomes}

    def flags(self) -> str:
        return ",".join(
            f"{outcome.name}={'pass' if outcome.passed else 'fail'}"
            for outcome in self.outcomes
        )


def symbol_concentration(trades: Sequence[TradeSample]) -> float:
    totals: dict[str, float] = {}
    for trade in trades:
        totals[trade.symbol] = totals.get(trade.symbol, 0.0) + abs(float(trade.net_return))
    total_abs = sum(totals.values())
    if total_abs <= 0.0:
        return 1.0
    return max(totals.values()) / total_abs


def _finite(value: float | None) -> bool:
    return value is not None and isfinite(value)


def _finite_nonnegative(value: float | None) -> bool:
    return value is not None and isfinite(value) and value >= 0.0


def _probability(value: float | None) -> bool:
    return value is not None and isfinite(value) and 0.0 <= value <= 1.0


def evaluate_gates(
    trades: Sequence[TradeSample],
    *,
    params: Mapping[str, object],
    components: Sequence[str],
    config: GateConfig,
    objective: ObjectiveResult,
    cost_stress_full_train_return: float | None,
    causality_admissible: bool | None,
    foundation_scenario: FoundationScenario | None = None,
) -> GateSet:
    concentration = (
        foundation_scenario.full_train.max_symbol_concentration
        if foundation_scenario is not None
        else symbol_concentration(trades)
    )
    trade_count = (
        foundation_scenario.full_train.closed_trade_count
        if foundation_scenario is not None
        else len(trades)
    )
    component_count = len(tuple(components))
    param_count = len(dict(params))
    complexity_value = max(component_count, param_count)
    outcomes: list[GateOutcome] = [
        GateOutcome(
            name="trade_floor",
            passed=trade_count >= 0 and trade_count >= config.min_trades,
            value=float(trade_count),
            threshold=float(config.min_trades),
        ),
    ]
    if foundation_scenario is not None:
        metrics = (foundation_scenario.full_train, *foundation_scenario.subwindows)
        min_return_sample_count = min(
            (metric.return_sample_count for metric in metrics),
            default=0,
        )
        effective_values = [
            metric.effective_sample_size
            for metric in metrics
        ]
        valid_effective_values: list[float] = []
        for value in effective_values:
            if _finite_nonnegative(value) and value is not None:
                valid_effective_values.append(value)
        min_effective_sample_size = min(valid_effective_values, default=0.0)
        max_drawdown = foundation_scenario.full_train.max_drawdown
        minimum_evidence_passed = (
            all(metric.return_sample_count >= 0 for metric in metrics)
            and min_return_sample_count >= config.min_return_sample_count
            and len(valid_effective_values) == len(metrics)
            and min_effective_sample_size >= config.min_effective_sample_size
        )
        path_risk_passed = (
            max_drawdown is not None
            and isfinite(max_drawdown)
            and max_drawdown <= 0.0
            and max_drawdown >= -config.max_abs_drawdown
        )
        money_floor_value = deflated_window_floor(
            objective, k_accept=config.score_haircut_se
        )
        money_floor_passed = (
            money_floor_value is not None
            and isfinite(money_floor_value)
            and money_floor_value >= config.min_annualized_return
        )
        realistic_full_return = objective.full_train_return
        retention_binding = (
            realistic_full_return is not None
            and isfinite(realistic_full_return)
            and realistic_full_return > 0.0
        )
        if retention_binding:
            assert realistic_full_return is not None  # narrowed by retention_binding
            if (
                cost_stress_full_train_return is None
                or not isfinite(cost_stress_full_train_return)
            ):
                retention_value: float | None = None
                retention_passed = False
            else:
                retention_value = cost_stress_full_train_return / realistic_full_return
                retention_passed = (
                    retention_value >= config.min_cost_stress_return_retention
                )
        else:
            # Non-binding: a non-positive realistic full-Train return is the money
            # floor's economic kill, and the retention ratio's sign is ambiguous.
            retention_value = None
            retention_passed = True
        outcomes.extend(
            [
                GateOutcome(
                    name="minimum_evidence",
                    passed=minimum_evidence_passed,
                    value=float(min_effective_sample_size),
                    threshold=float(config.min_effective_sample_size),
                    detail=(
                        f"min_return_sample_count={min_return_sample_count}, "
                        f"return_sample_threshold={config.min_return_sample_count}"
                    ),
                ),
                GateOutcome(
                    name="path_risk",
                    passed=path_risk_passed,
                    value=max_drawdown,
                    threshold=-config.max_abs_drawdown,
                ),
                GateOutcome(
                    name="money_floor",
                    passed=money_floor_passed,
                    value=money_floor_value,
                    threshold=config.min_annualized_return,
                    detail=f"k_accept={config.score_haircut_se}, full_train",
                ),
                GateOutcome(
                    name="cost_stress_retention",
                    passed=retention_passed,
                    value=retention_value,
                    threshold=config.min_cost_stress_return_retention,
                    detail=(
                        "non-binding: realistic full-Train return <= 0"
                        if not retention_binding
                        else ""
                    ),
                ),
            ]
        )
    breadth_passed = (
        _probability(concentration)
        and concentration is not None
        and concentration <= config.max_symbol_concentration
    )
    outcomes.extend(
        [
        GateOutcome(
            name="breadth",
            passed=breadth_passed,
            value=concentration,
            threshold=config.max_symbol_concentration,
            detail=(
                "missing foundation max_symbol_concentration"
                if foundation_scenario is not None and concentration is None
                else ""
            ),
        ),
        GateOutcome(
            name="causality",
            passed=causality_admissible is True,
            value=None,
            threshold=None,
            detail="admissible" if causality_admissible is True else "not_admissible",
        ),
        GateOutcome(
            name="complexity_cap",
            passed=component_count <= config.max_components
            and param_count <= config.max_params,
            value=float(complexity_value),
            threshold=float(max(config.max_components, config.max_params)),
            detail=f"components={component_count}, params={param_count}",
        ),
        ]
    )
    return GateSet(outcomes=tuple(outcomes))
