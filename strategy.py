"""Strategy: fx_triangular_residual_reversion_harness_smoke

Thesis:
Use the external FX triangular residual reversion strategy as the active
strategy under the fixed quant_autoresearch harness.

Harness adaptation:
The current harness supplies one synthetic symbol with five bars. The source
strategy expects multi-symbol FX triangles and longer history. For this smoke
loop, adapt it to a single-symbol synthetic triangle so we can test whether the
autoresearch runner, engine, and artifact review loop work end to end.

Falsifier:
If this wrapper cannot produce a causal, fillable signal through the fixed
runner, the current harness is not yet ready to run imported strategy files.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import ModuleType


SOURCE_STRATEGY = Path("/Users/Season_Yang/Personal/quant_strategies/untested/fx_triangular_residual_reversion.py")


def generate_signals(bars: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> list[dict[str, object]]:
    if not bars:
        return []

    symbol = str(params.get("symbol", bars[0]["symbol"]))
    source = _load_source_strategy(SOURCE_STRATEGY)

    def triangles_for(triangle_set: str) -> tuple[tuple[str, str, int, str, int], ...]:
        if triangle_set == "harness_single_symbol":
            return ((symbol, symbol, 1, symbol, -1),)
        return source._original_triangles_for(triangle_set)  # type: ignore[attr-defined]

    if not hasattr(source, "_original_triangles_for"):
        source._original_triangles_for = source._triangles_for  # type: ignore[attr-defined]
    source._triangles_for = triangles_for  # type: ignore[attr-defined]

    raw_signals = source.generate_signals(bars, params)
    return _fillable_signals(raw_signals, bars, params)


def _load_source_strategy(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("fx_triangular_residual_reversion_source", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load strategy source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fillable_signals(
    signals: Sequence[Mapping[str, object]],
    bars: Sequence[Mapping[str, object]],
    params: Mapping[str, object],
) -> list[dict[str, object]]:
    bars_by_symbol = _bars_by_symbol(bars)
    entry_lag_bars = int(params.get("entry_lag_bars", 1))
    exit_lag_bars = int(params.get("exit_lag_bars", 0))
    decision_start = _optional_timestamp(params.get("decision_start"), "decision_start")
    decision_end = _optional_timestamp(params.get("decision_end"), "decision_end")

    result: list[dict[str, object]] = []
    for signal in signals:
        symbol = str(signal["symbol"])
        symbol_bars = bars_by_symbol.get(symbol, ())
        decision_time = _bar_timestamp(signal["decision_time"])
        if not _inside_decision_window(decision_time, decision_start, decision_end):
            continue

        decision_index = _decision_index(symbol_bars, decision_time)
        if decision_index is None:
            continue

        hold_bars = int(signal["hold_bars"])
        exit_index = decision_index + entry_lag_bars + hold_bars + exit_lag_bars
        if exit_index >= len(symbol_bars):
            continue

        result.append(
            {
                "symbol": symbol,
                "decision_time": decision_time,
                "side": str(signal["side"]),
                "weight": float(signal["weight"]),
                "hold_bars": hold_bars,
            }
        )
    return result


def _bars_by_symbol(bars: Sequence[Mapping[str, object]]) -> dict[str, tuple[Mapping[str, object], ...]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for bar in bars:
        grouped.setdefault(str(bar["symbol"]), []).append(bar)
    return {
        symbol: tuple(sorted(symbol_bars, key=lambda bar: _bar_timestamp(bar["timestamp"])))
        for symbol, symbol_bars in grouped.items()
    }


def _decision_index(bars: Sequence[Mapping[str, object]], decision_time: datetime) -> int | None:
    for index, bar in enumerate(bars):
        if _bar_timestamp(bar["timestamp"]) == decision_time:
            return index
    return None


def _optional_timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in {"", "none", "null"}:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise TypeError(f"{field_name} must be an ISO-8601 timestamp")
    return _require_timezone(parsed, field_name).astimezone(timezone.utc)


def _bar_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("bar timestamp must be a datetime")
    return _require_timezone(value, "bar timestamp").astimezone(timezone.utc)


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _inside_decision_window(
    decision_time: datetime,
    decision_start: datetime | None,
    decision_end: datetime | None,
) -> bool:
    if decision_start is not None and decision_time < decision_start:
        return False
    if decision_end is not None and decision_time >= decision_end:
        return False
    return True
