from __future__ import annotations

from datetime import datetime, timedelta, timezone


def synthetic_bars(symbol: str) -> list[dict[str, object]]:
    start = datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc)
    closes = [100.0, 101.0, 102.0, 105.0, 100.0]
    return [
        {
            "symbol": symbol,
            "timestamp": start + timedelta(minutes=index),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
        }
        for index, close in enumerate(closes)
    ]
