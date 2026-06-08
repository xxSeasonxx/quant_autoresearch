from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from objective import TradeSample


@dataclass(frozen=True)
class GateConfig:
    min_trades: int
    min_trades_per_subwindow: int
    max_symbol_concentration: float
    min_cost_stress_score: float
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


def evaluate_gates(
    trades: Sequence[TradeSample],
    *,
    params: Mapping[str, object],
    components: Sequence[str],
    config: GateConfig,
    cost_stress_score: float | None,
    train_score: float | None,
    subwindow_trade_counts: Sequence[int],
) -> GateSet:
    concentration = symbol_concentration(trades)
    component_count = len(tuple(components))
    param_count = len(dict(params))
    complexity_value = max(component_count, param_count)
    min_subwindow_count = min(subwindow_trade_counts, default=0)
    outcomes = (
        GateOutcome(
            name="trade_floor",
            passed=len(trades) >= config.min_trades,
            value=float(len(trades)),
            threshold=float(config.min_trades),
        ),
        GateOutcome(
            name="subwindow_coverage",
            passed=bool(subwindow_trade_counts)
            and len(subwindow_trade_counts) == config.subwindows
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
        GateOutcome(
            name="breadth",
            passed=concentration <= config.max_symbol_concentration,
            value=concentration,
            threshold=config.max_symbol_concentration,
        ),
        GateOutcome(
            name="cost_stress",
            passed=cost_stress_score is not None
            and cost_stress_score >= config.min_cost_stress_score,
            value=cost_stress_score,
            threshold=config.min_cost_stress_score,
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
            passed=train_score is not None and train_score >= config.train_score_floor,
            value=train_score,
            threshold=config.train_score_floor,
        ),
    )
    return GateSet(outcomes=outcomes)
