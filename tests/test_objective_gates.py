from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gates import GateConfig, evaluate_gates
from objective import (
    LoopConfig,
    TradeSample,
    is_improvement,
    plateau_reached,
    score_cost_stress,
    score_worst_subwindow,
)


def _trade(symbol: str, i: int, net: float) -> TradeSample:
    return TradeSample(
        symbol=symbol,
        decision_time=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
        net_return=net,
    )


def test_worst_subwindow_uses_configured_k_and_lowest_slice():
    trades = [
        _trade("BTC", 0, 0.10),
        _trade("BTC", 1, 0.10),
        _trade("ETH", 2, -0.05),
        _trade("ETH", 3, -0.02),
        _trade("BTC", 4, 0.20),
        _trade("ETH", 5, 0.20),
    ]

    result = score_worst_subwindow(trades, subwindows=3)

    assert result.feasible is True
    assert len(result.subwindow_scores) == 3
    assert result.score == min(result.subwindow_scores)


def test_worst_subwindow_splits_by_time_not_trade_count():
    trades = [
        _trade("BTC", 0, 0.10),
        _trade("BTC", 1, 0.10),
        _trade("BTC", 2, 0.10),
        _trade("ETH", 120, -0.02),
    ]

    result = score_worst_subwindow(
        trades,
        subwindows=3,
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=180),
    )

    assert len(result.subwindow_scores) == 3
    assert result.subwindow_scores[1] == 0.0
    assert result.score == -0.02


def test_worst_subwindow_includes_idle_train_tail():
    trades = [_trade("BTC", 0, 0.10), _trade("BTC", 1, 0.10)]

    result = score_worst_subwindow(
        trades,
        subwindows=3,
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=180),
    )

    assert result.subwindow_scores == (0.1, 0.0, 0.0)
    assert result.score == 0.0


def test_cost_stress_subtracts_extra_round_trip_cost_by_position_weight():
    trades = (
        TradeSample(
            symbol="BTC",
            decision_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            net_return=0.010,
            weight=0.5,
        ),
    )

    stressed = score_cost_stress(trades, subwindows=1, extra_round_trip_bps=20.0)

    assert stressed.score == pytest.approx(0.009)


def test_plateau_improvement_uses_absolute_and_relative_thresholds():
    loop = LoopConfig(
        plateau_patience=3,
        max_iterations=10,
        min_abs_improvement=0.05,
        min_rel_improvement=0.10,
        baseline_grace_iterations=2,
    )

    assert not is_improvement(1.04, 1.0, True, loop)
    assert is_improvement(1.11, 1.0, True, loop)
    assert not is_improvement(2.15, 2.0, True, loop)
    assert is_improvement(2.21, 2.0, True, loop)
    assert not is_improvement(3.0, 1.0, False, loop)


def test_plateau_reached_after_m_non_improving_attempts():
    loop = LoopConfig(
        plateau_patience=3,
        max_iterations=10,
        min_abs_improvement=0.01,
        min_rel_improvement=0.0,
        baseline_grace_iterations=2,
    )

    assert not plateau_reached(non_improving_since_best=2, feasible_baseline=True, loop=loop)
    assert plateau_reached(non_improving_since_best=3, feasible_baseline=True, loop=loop)
    assert not plateau_reached(non_improving_since_best=3, feasible_baseline=False, loop=loop)


def test_gates_are_binary_and_separate_from_score():
    trades = [_trade("BTC", 0, 0.10), _trade("ETH", 1, 0.05), _trade("ETH", 2, 0.04)]
    cfg = GateConfig(
        min_trades=3,
        max_symbol_concentration=0.80,
        min_cost_stress_score=0.0,
        max_components=2,
        max_params=4,
        train_score_floor=0.0,
    )

    passed = evaluate_gates(
        trades,
        params={"lookback": 12, "weight": 0.1},
        components=("momentum",),
        config=cfg,
        cost_stress_score=0.01,
        train_score=0.2,
    )
    failed = evaluate_gates(
        trades,
        params={"lookback": 12, "weight": 0.1, "extra": 1, "extra2": 2, "extra3": 3},
        components=("a", "b", "c"),
        config=cfg,
        cost_stress_score=0.01,
        train_score=0.2,
    )

    assert passed.passed is True
    assert failed.passed is False
    assert failed.by_name["complexity_cap"].passed is False
