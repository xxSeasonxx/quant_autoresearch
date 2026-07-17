from __future__ import annotations

from datetime import datetime, timedelta, timezone

import strategy


def _bar(
    symbol: str,
    timestamp: datetime,
    *,
    close: float,
    funding_rate: float,
    has_funding_event: bool,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "available_at": timestamp,
        "close": close,
        "volume": 1_000.0,
        "funding_timestamp": timestamp,
        "funding_rate": funding_rate,
        "has_funding_event": has_funding_event,
    }


def test_decisions_before_cutoff_do_not_depend_on_future_rows() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal_time = start + timedelta(minutes=120)
    params = {
        "funding_lookback_events": 1,
        "return_lookback_minutes": 120,
        "recent_return_lookback_minutes": 0,
        "decision_interval_minutes": 120,
        "decision_lag_minutes": 1,
        "entry_twap_bars": 2,
        "exit_twap_bars": 2,
        "long_hold_minutes": 120,
        "short_hold_minutes": 120,
        "top_n": 2,
        "min_cross_section": 2,
        "min_abs_funding_bps": 0.1,
        "min_abs_return_bps": 0.0,
        "min_same_sign_funding_events": 1,
        "min_idiosyncratic_return_bps": 0.0,
        "cross_section_reference": "mean",
        "weighting": "equal",
    }
    prefix = [
        _bar(
            "LONG-PERP",
            start,
            close=100.0,
            funding_rate=-0.0002,
            has_funding_event=True,
        ),
        _bar(
            "SHORT-PERP",
            start,
            close=100.0,
            funding_rate=0.0002,
            has_funding_event=True,
        ),
        _bar(
            "LONG-PERP",
            signal_time,
            close=99.0,
            funding_rate=0.0,
            has_funding_event=False,
        ),
        _bar(
            "SHORT-PERP",
            signal_time,
            close=101.0,
            funding_rate=0.0,
            has_funding_event=False,
        ),
    ]
    future = [
        _bar(
            symbol,
            start + timedelta(minutes=offset),
            close=close,
            funding_rate=0.0,
            has_funding_event=False,
        )
        for symbol, close in (("LONG-PERP", 99.0), ("SHORT-PERP", 101.0))
        for offset in (121, 125, 241, 250)
    ]

    prefix_decisions = strategy.generate_decisions(prefix, params)
    full_decisions = strategy.generate_decisions([*prefix, *future], params)

    assert prefix_decisions
    assert prefix_decisions == full_decisions
    assert {decision.decision_time for decision in prefix_decisions} == {
        start + timedelta(minutes=121),
        start + timedelta(minutes=122),
        start + timedelta(minutes=241),
        start + timedelta(minutes=242),
    }
