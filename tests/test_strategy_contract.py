from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import strategy


def _bars(symbol: str, closes: list[float]):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "symbol": symbol,
            "timestamp": start + timedelta(minutes=i),
            "available_at": start + timedelta(minutes=i + 1),
            "close": close,
        }
        for i, close in enumerate(closes)
    ]


def test_strategy_exports_pure_decision_contract():
    assert strategy.__all__ == ["validate_params", "generate_decisions"]
    assert callable(strategy.validate_params)
    assert callable(strategy.generate_decisions)


def test_validate_params_rejects_unknown_and_out_of_bounds_params():
    with pytest.raises(ValueError):
        strategy.validate_params({"unknown": 1})
    with pytest.raises(ValueError):
        strategy.validate_params({"lookback_bars": 1})
    with pytest.raises(ValueError):
        strategy.validate_params({"weight": 2.0})


def test_generate_decisions_emits_causal_long_decision():
    decisions = strategy.generate_decisions(
        _bars("BTC-PERP", [100, 101, 102, 104, 105]),
        {"lookback_bars": 3, "threshold_bps": 50, "weight": 0.1, "max_hold_bars": 2},
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.instrument.symbol == "BTC-PERP"
    assert decision.target.direction == "long"
    assert decision.as_of_time < decision.decision_time
    assert decision.decision_time == decision.as_of_time + timedelta(minutes=1)


def test_generate_decisions_scans_history_and_suppresses_overlap():
    rows = _bars("BTC-PERP", [100, 102, 104, 106, 108, 110, 112, 114, 116, 118])

    decisions = strategy.generate_decisions(
        rows,
        {"lookback_bars": 2, "threshold_bps": 50, "weight": 0.1, "max_hold_bars": 2},
    )

    assert len(decisions) >= 2
    assert decisions[1].decision_time > decisions[0].decision_time
