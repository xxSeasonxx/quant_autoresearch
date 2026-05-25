from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import strategy


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCSTRING_HEADINGS = (
    "Source / provenance:",
    "Market rationale:",
    "Required observables:",
    "Signal rule:",
    "Assumptions:",
    "Falsifier:",
)


def crypto_rows() -> list[dict[str, object]]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    symbols = ("BTC-PERP", "ETH-PERP", "SOL-PERP", "XRP-PERP")
    for symbol_index, symbol in enumerate(symbols):
        base = 100.0 + symbol_index
        for offset in range(0, 481):
            timestamp = start + timedelta(minutes=offset)
            funding_event = offset in {0, 240, 480}
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "open": base,
                    "high": base,
                    "low": base,
                    "close": base + offset * (0.01 if symbol_index < 2 else -0.01),
                    "funding_timestamp": timestamp if funding_event else None,
                    "funding_rate": (0.0002 if symbol_index < 2 else -0.0002) if funding_event else None,
                    "has_funding_event": funding_event,
                }
            )
    return rows


def test_strategy_docstring_matches_quant_strategies_shape():
    docstring = ast.get_docstring(ast.parse((ROOT / "strategy.py").read_text())) or ""

    for heading in REQUIRED_DOCSTRING_HEADINGS:
        assert heading in docstring


def test_strategy_exposes_generate_signals():
    assert callable(strategy.generate_signals)


def test_strategy_generates_quant_strategies_signal_shape():
    signals = strategy.generate_signals(
        crypto_rows(),
        {
            "funding_lookback_events": 2,
            "return_lookback_minutes": 240,
            "decision_interval_minutes": 480,
            "decision_lag_minutes": 1,
            "top_n": 1,
            "min_cross_section": 4,
            "min_abs_funding_bps": 0.1,
            "min_abs_return_bps": 1.0,
            "weight": 0.25,
            "hold_bars": 1,
        },
    )

    assert [(signal["symbol"], signal["side"]) for signal in signals] == [
        ("BTC-PERP", "short"),
        ("SOL-PERP", "long"),
    ]

    required_keys = {
        "symbol",
        "decision_time",
        "as_of_time",
        "side",
        "weight",
        "hold_bars",
        "max_hold_bars",
        "funding_pressure_bps",
        "entry_return_extension_bps",
        "signal_family",
    }
    for signal in signals:
        assert set(signal).issuperset(required_keys)
        assert signal["decision_time"] is not None
        assert signal["as_of_time"] is not None
        assert signal["side"] in {"long", "short"}
        assert signal["weight"] == 0.25
        assert signal["hold_bars"] == 1
        assert signal["max_hold_bars"] == 1
        assert signal["signal_family"] == "crypto_perp_funding_crowding_reversal"
        assert "take_profit_bps" not in signal
        assert "stop_loss_bps" not in signal
        assert "trailing_stop_bps" not in signal


def test_strategy_can_disable_positive_funding_shorts():
    signals = strategy.generate_signals(
        crypto_rows(),
        {
            "funding_lookback_events": 2,
            "return_lookback_minutes": 240,
            "decision_interval_minutes": 480,
            "decision_lag_minutes": 1,
            "top_n": 1,
            "min_cross_section": 4,
            "min_abs_funding_bps": 0.1,
            "min_abs_return_bps": 1.0,
            "include_positive_funding_shorts": False,
            "weight": 0.25,
            "hold_bars": 1,
        },
    )

    assert [(signal["symbol"], signal["side"]) for signal in signals] == [("SOL-PERP", "long")]


def test_strategy_filters_insufficient_same_sign_funding_events():
    signals = strategy.generate_signals(
        crypto_rows(),
        {
            "funding_lookback_events": 2,
            "return_lookback_minutes": 240,
            "decision_interval_minutes": 480,
            "decision_lag_minutes": 1,
            "top_n": 1,
            "min_cross_section": 4,
            "min_abs_funding_bps": 0.1,
            "min_abs_return_bps": 1.0,
            "min_same_sign_funding_events": 3,
            "weight": 0.25,
            "hold_bars": 1,
        },
    )

    assert signals == []


def test_strategy_emits_optional_exit_controls():
    signals = strategy.generate_signals(
        crypto_rows(),
        {
            "funding_lookback_events": 2,
            "return_lookback_minutes": 240,
            "decision_interval_minutes": 480,
            "decision_lag_minutes": 1,
            "top_n": 1,
            "min_cross_section": 4,
            "min_abs_funding_bps": 0.1,
            "min_abs_return_bps": 1.0,
            "weight": 0.25,
            "hold_bars": 3,
            "take_profit_bps": 150.0,
            "stop_loss_bps": 100.0,
            "trailing_stop_bps": 40.0,
        },
    )

    assert signals
    for signal in signals:
        assert signal["hold_bars"] == 3
        assert signal["max_hold_bars"] == 3
        assert signal["take_profit_bps"] == 150.0
        assert signal["stop_loss_bps"] == 100.0
        assert signal["trailing_stop_bps"] == 40.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("take_profit_bps", 0.0),
        ("stop_loss_bps", -1.0),
        ("trailing_stop_bps", float("inf")),
    ],
)
def test_strategy_rejects_invalid_exit_controls(field: str, value: float):
    params = {
        "funding_lookback_events": 2,
        "return_lookback_minutes": 240,
        "decision_interval_minutes": 480,
        "decision_lag_minutes": 1,
        "top_n": 1,
        "min_cross_section": 4,
        "min_abs_funding_bps": 0.1,
        "min_abs_return_bps": 1.0,
        "weight": 0.25,
        "hold_bars": 3,
        field: value,
    }

    with pytest.raises(ValueError, match=f"{field} must be finite and positive"):
        strategy.generate_signals(crypto_rows(), params)
