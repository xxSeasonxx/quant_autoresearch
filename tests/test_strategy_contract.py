from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import strategy


def _funding_rows() -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    symbols = {
        "BTC-PERP": (100.0, 102.0, 0.0002),
        "ETH-PERP": (100.0, 98.0, -0.0002),
        "DOGE-PERP": (100.0, 100.5, 0.0001),
        "ADA-PERP": (100.0, 99.5, -0.0001),
        "LINK-PERP": (100.0, 100.2, 0.00005),
    }
    rows: list[dict[str, object]] = []
    for symbol, (base_close, signal_close, funding_rate) in symbols.items():
        for minute in range(7):
            timestamp = start + timedelta(minutes=minute)
            close = base_close
            if minute == 5:
                close = signal_close
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "available_at": timestamp + timedelta(minutes=1),
                    "close": close,
                    "funding_timestamp": timestamp if minute == 5 else None,
                    "funding_rate": funding_rate if minute == 5 else 0.0,
                    "has_funding_event": minute == 5,
                }
            )
    return rows


def _params(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "funding_lookback_events": 1,
        "return_lookback_minutes": 2,
        "decision_interval_minutes": 5,
        "decision_lag_minutes": 1,
        "top_n": 1,
        "min_cross_section": 4,
        "min_abs_funding_bps": 0.1,
        "min_abs_return_bps": 0.0,
        "min_same_sign_funding_events": 1,
        "weight": 0.2,
        "hold_bars": 2,
        "short_hold_bars": 2,
        "long_hold_bars": 2,
        "require_exit_horizon": False,
        "overlap_exit_buffer_bars": 0,
    }
    params.update(overrides)
    return params


def test_strategy_exports_pure_decision_contract():
    assert strategy.__all__ == ["validate_params", "generate_decisions"]
    assert callable(strategy.validate_params)
    assert callable(strategy.generate_decisions)


def test_validate_params_rejects_invalid_scalar_params():
    with pytest.raises(ValueError):
        strategy.validate_params({"funding_lookback_events": 0})
    with pytest.raises(ValueError):
        strategy.validate_params({"selection_score": "unsupported"})
    with pytest.raises(ValueError):
        strategy.validate_params({"require_exit_horizon": "true"})


def test_generate_decisions_emits_causal_funding_reversal_decisions():
    decisions = strategy.generate_decisions(_funding_rows(), _params())

    assert {decision.target.direction for decision in decisions} == {"long", "short"}
    for decision in decisions:
        assert decision.instrument.symbol.endswith("-PERP")
        assert decision.as_of_time < decision.decision_time
        assert decision.decision_time == decision.as_of_time + timedelta(minutes=1)
        assert decision.exit_policy.max_hold_bars == 2


def test_generate_decisions_suppresses_same_symbol_overlap():
    first_rows = _funding_rows()
    second_rows = []
    for row in first_rows:
        shifted = dict(row)
        shifted["timestamp"] = shifted["timestamp"] + timedelta(minutes=10)  # type: ignore[operator]
        if shifted["funding_timestamp"] is not None:
            shifted["funding_timestamp"] = shifted["funding_timestamp"] + timedelta(minutes=10)  # type: ignore[operator]
        shifted["available_at"] = shifted["available_at"] + timedelta(minutes=10)  # type: ignore[operator]
        second_rows.append(shifted)

    without_suppression = strategy.generate_decisions(
        [*first_rows, *second_rows],
        _params(state_mode="off"),
    )
    with_suppression = strategy.generate_decisions(
        [*first_rows, *second_rows],
        _params(state_mode="suppress_until_exit", hold_bars=20, short_hold_bars=20, long_hold_bars=20),
    )

    assert len(without_suppression) > len(with_suppression)


def test_rows_by_symbol_indexes_timestamps_for_exit_horizon_checks():
    rows = strategy._rows_by_symbol(_funding_rows())  # noqa: SLF001
    btc_rows = rows["BTC-PERP"]

    assert btc_rows.timestamp_to_index[btc_rows.timestamps[5]] == 5
