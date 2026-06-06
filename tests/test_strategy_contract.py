"""The agent-editable strategy surface contract (the new world).

``strategy.py`` exposes the foundation's pure decision contract (``generate_decisions`` /
``validate_params``) and expresses ONE simple causal hypothesis (time-series momentum). It is
pure (no data loading / I/O), validates its params, and emits causally-stamped decisions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import strategy


def test_strategy_exports_decision_contract_only():
    assert callable(strategy.generate_decisions)
    assert callable(strategy.validate_params)
    assert "generate_decisions" in strategy.__all__
    assert "validate_params" in strategy.__all__
    assert "generate_signals" not in strategy.__all__


def test_validate_params_returns_defensive_copy_with_defaults():
    source = {"lookback_bars": 12}
    validated = strategy.validate_params(source)
    assert validated is not source
    assert validated["lookback_bars"] == 12
    # Defaults fill the rest.
    assert validated["base_position_pct"] == 0.05
    assert validated["decision_lag_minutes"] == 60


def test_validate_params_rejects_zero_decision_lag():
    """A zero decision lag is hidden lookahead — must be rejected (causal contract)."""
    with pytest.raises(ValueError):
        strategy.validate_params({"decision_lag_minutes": 0})


def test_generate_decisions_empty_bars_is_empty():
    assert strategy.generate_decisions([], {}) == []


def _bars(symbol, closes, start="2024-01-01T00:00:00+00:00"):
    t0 = datetime.fromisoformat(start)
    return [
        {"symbol": symbol, "timestamp": t0 + timedelta(hours=i), "close": c}
        for i, c in enumerate(closes)
    ]


def test_emits_long_on_up_trend_with_causal_decision_time():
    """A clear up-trend over the lookback window emits a LONG decision stamped strictly after
    the as-of bar (no lookahead)."""
    closes = [100.0] * 24 + [130.0]  # +30% over the 24-bar lookback at the last bar
    params = {"lookback_bars": 24, "entry_threshold": 0.01, "decision_lag_minutes": 60, "max_hold_bars": 24}
    decisions = strategy.generate_decisions(_bars("BTCUSDT", closes), params)
    assert len(decisions) == 1
    d = decisions[0]
    assert d.target.direction == "long"
    assert d.target.sizing_kind == "target_weight"
    assert d.instrument.symbol == "BTCUSDT"
    # decision_time is strictly after as_of_time (the lag) — causal.
    assert d.decision_time == d.as_of_time + timedelta(minutes=60)


def test_no_decision_when_trend_below_threshold():
    """A flat series never clears the entry threshold ⇒ no long, no decision (stays flat)."""
    closes = [100.0] * 30
    params = {"lookback_bars": 24, "entry_threshold": 0.01}
    assert strategy.generate_decisions(_bars("ETHUSDT", closes), params) == []
