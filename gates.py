from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

from objective import FoundationScenario, TradeSample


@dataclass(frozen=True)
class GateConfig:
    min_trades: int
    min_trades_per_subwindow: int
    min_return_sample_count: int
    min_effective_sample_size: float
    max_symbol_concentration: float
    min_cost_stress_psr: float
    max_abs_drawdown: float
    min_total_return: float
    max_components: int
    max_params: int
    train_score_floor: float
    subwindows: int


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
    cost_stress_score: float | None,
    train_score: float | None,
    subwindow_trade_counts: Sequence[int],
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
    min_subwindow_count = min(subwindow_trade_counts, default=0)
    outcomes: list[GateOutcome] = [
        GateOutcome(
            name="trade_floor",
            passed=trade_count >= 0 and trade_count >= config.min_trades,
            value=float(trade_count),
            threshold=float(config.min_trades),
        ),
        GateOutcome(
            name="subwindow_coverage",
            passed=bool(subwindow_trade_counts)
            and len(subwindow_trade_counts) == config.subwindows
            and all(count >= 0 for count in subwindow_trade_counts)
            and all(
                count >= config.min_trades_per_subwindow
                for count in subwindow_trade_counts
            ),
            value=float(min_subwindow_count),
            threshold=float(config.min_trades_per_subwindow),
            detail=(
                "counts="
                + ",".join(str(count) for count in subwindow_trade_counts)
                + f", expected={config.subwindows}"
            ),
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
        total_return = foundation_scenario.full_train.total_return
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
        economic_return_passed = (
            total_return is not None
            and isfinite(total_return)
            and total_return >= config.min_total_return
        )
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
                    name="economic_return",
                    passed=economic_return_passed,
                    value=total_return,
                    threshold=config.min_total_return,
                ),
            ]
        )
    breadth_passed = (
        _probability(concentration)
        and concentration is not None
        and concentration <= config.max_symbol_concentration
    )
    cost_stress_passed = (
        _probability(cost_stress_score)
        and cost_stress_score is not None
        and cost_stress_score >= config.min_cost_stress_psr
    )
    train_floor_passed = (
        _probability(train_score)
        and train_score is not None
        and train_score >= config.train_score_floor
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
            name="cost_stress",
            passed=cost_stress_passed,
            value=cost_stress_score,
            threshold=config.min_cost_stress_psr,
        ),
        GateOutcome(
            name="complexity_cap",
            passed=component_count <= config.max_components
            and param_count <= config.max_params,
            value=float(complexity_value),
            threshold=float(max(config.max_components, config.max_params)),
            detail=f"components={component_count}, params={param_count}",
        ),
        GateOutcome(
            name="train_floor",
            passed=train_floor_passed,
            value=train_score,
            threshold=config.train_score_floor,
        ),
        ]
    )
    return GateSet(outcomes=tuple(outcomes))
