from __future__ import annotations

from strategy import generate_signals


def test_placeholder_strategy_returns_no_signals():
    assert generate_signals([], {}) == []
