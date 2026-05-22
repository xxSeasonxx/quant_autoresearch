from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import strategy


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
    docstring = ast.get_docstring(ast.parse(Path("strategy.py").read_text())) or ""

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

    assert signals
    first = signals[0]
    assert set(first).issuperset({"symbol", "decision_time", "as_of_time", "side", "weight", "hold_bars"})
    assert first["side"] in {"long", "short"}
    assert first["weight"] == 0.25
    assert first["hold_bars"] == 1
