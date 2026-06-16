"""Strategy: crypto_perp_funding_anchor_carry

Source / provenance:
Ackerer, Hugonnier, and Jermann (2024), "Perpetual Futures Pricing", model
funding as the cashflow that anchors a perpetual future to spot. The paper's
mechanical implication is directional and simple: when the perp is rich, longs
pay shorts and the short side is made more attractive; when the perp is cheap,
longs receive funding and the long side is made more attractive.

This file implements that mechanism directly. It is not a price-extension or
crowding strategy. It treats the observed funding rate sign as the tradable proxy
for the premium term because this bench does not expose a separate perp/spot
basis series.

Signal rule:
At each funding-event observation, rank symbols by the absolute latest funding
rate. Short positive funding and long negative funding, holding the target until
the next funding-event rebalance changes it. Emit explicit flat targets for
symbols that no longer qualify. The strategy uses only funding rows whose
`available_at` is no later than the emitted decision time. This variant requires
at least two eligible funding-sign targets before holding the book.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import math
from typing import Any, cast

from quant_strategies.decisions import InstrumentRef, ObservationRef, TargetDecision

__all__ = ["generate_decisions", "validate_params"]

_STRATEGY_ID = "crypto_perp_funding_crowding_reversal_stateful_rebalance"
_REQUIRED_FIELDS = {
    "symbol",
    "timestamp",
    "close",
    "funding_timestamp",
    "funding_rate",
    "has_funding_event",
    "available_at",
}
_MIN_CAPACITY_HISTORY_BARS = 60
_REQUIRE_PRICE_EXTENSION = False
_PRICE_EXTENSION_LOOKBACK_MINUTES = 120
_MIN_PRICE_EXTENSION_BPS = 10.0
_PRIMARY_MIN_ABS_FUNDING_BPS = 1.0
_FALLBACK_MIN_ABS_FUNDING_BPS = 0.75
_FALLBACK_WEIGHT_MULTIPLIER = 0.5
_MIN_SELECTED_SYMBOLS = 2


class _FundingEvent:
    __slots__ = ("available_at", "funding_rate", "funding_time", "observed_at", "symbol")

    def __init__(
        self,
        *,
        symbol: str,
        observed_at: datetime,
        funding_time: datetime,
        available_at: datetime,
        funding_rate: float,
    ) -> None:
        self.symbol = symbol
        self.observed_at = observed_at
        self.funding_time = funding_time
        self.available_at = available_at
        self.funding_rate = funding_rate

    @property
    def funding_bps(self) -> float:
        return self.funding_rate * 10_000.0


def validate_params(params: Mapping[str, object]) -> dict[str, object]:
    validated = dict(params)
    _positive_int(validated.get("top_n", 1), "top_n")
    _non_negative_float(validated.get("min_abs_funding_bps", 0.0), "min_abs_funding_bps")
    _non_negative_int(validated.get("decision_lag_minutes", 1), "decision_lag_minutes")
    return validated


def generate_decisions(
    bars: Sequence[Mapping[str, object]], params: Mapping[str, object]
) -> list[TargetDecision]:
    if not bars:
        return []
    _require_fields(bars, _REQUIRED_FIELDS)
    cfg = validate_params(params)

    top_n = _positive_int(cfg.get("top_n", 1), "top_n")
    min_abs_funding_bps = _non_negative_float(
        cfg.get("min_abs_funding_bps", 0.0), "min_abs_funding_bps"
    )
    decision_lag = timedelta(
        minutes=_non_negative_int(cfg.get("decision_lag_minutes", 1), "decision_lag_minutes")
    )

    all_symbols = tuple(sorted({str(row["symbol"]) for row in bars}))
    symbols = _complete_mark_symbols(bars, symbols=all_symbols)
    if not symbols:
        return []

    events_by_time = _funding_events_by_time(bars, symbols=symbols)
    valid_decision_times = _valid_common_decision_times(bars, symbols=symbols)
    close_index = _close_index(bars, symbols=symbols)
    latest_by_symbol: dict[str, _FundingEvent] = {}
    standing_targets: dict[str, float] = {symbol: 0.0 for symbol in symbols}
    emitted: set[tuple[str, datetime]] = set()
    decisions: list[TargetDecision] = []

    for as_of_time in sorted(events_by_time):
        for event in events_by_time[as_of_time]:
            latest_by_symbol[event.symbol] = event

        decision_time = _first_bar_at_or_after(valid_decision_times, as_of_time + decision_lag)
        if decision_time is None:
            continue
        tradable = [
            event
            for event in latest_by_symbol.values()
            if event.available_at <= decision_time and event.funding_time <= as_of_time
        ]

        targets = _funding_targets(
            tradable,
            symbols=symbols,
            close_index=close_index,
            decision_time=decision_time,
            top_n=top_n,
            min_abs_funding_bps=min_abs_funding_bps,
        )
        observations = {
            event.symbol: (
                ObservationRef(
                    symbol=event.symbol,
                    timestamp=event.observed_at,
                    field="funding_rate",
                    source="quant_data",
                ),
            )
            for event in tradable
        }
        for symbol in symbols:
            target = targets.get(symbol, 0.0)
            if math.isclose(target, standing_targets[symbol], rel_tol=0.0, abs_tol=1e-15):
                continue
            latest_event = latest_by_symbol.get(symbol)
            key = (symbol, decision_time)
            if key in emitted:
                continue
            decisions.append(
                TargetDecision(
                    strategy_id=_STRATEGY_ID,
                    instrument=InstrumentRef(kind="crypto_perp", symbol=symbol),
                    decision_time=decision_time,
                    as_of_time=as_of_time,
                    target=target,
                    risk_rule=None,
                    observations=observations.get(symbol, ()),
                    metadata={
                        "signal_family": "funding_anchor_carry",
                        "funding_bps": None
                        if latest_event is None else latest_event.funding_bps,
                    },
                )
            )
            emitted.add(key)
            standing_targets[symbol] = target

    return decisions


def _funding_targets(
    events: Sequence[_FundingEvent],
    *,
    symbols: Sequence[str],
    close_index: Mapping[str, Mapping[datetime, tuple[float, datetime]]],
    decision_time: datetime,
    top_n: int,
    min_abs_funding_bps: float,
) -> dict[str, float]:
    # Emit a unit base weight: upstream owns book scale (risk-budget sizing
    # normalizes the shape), so a global magnitude knob would be washed out and is
    # not a degree of freedom the loop searches over. Only the relative shape
    # matters, including the conviction-scaled fallback below.
    primary_floor = max(min_abs_funding_bps, _PRIMARY_MIN_ABS_FUNDING_BPS)
    selected = _selected_events(
        events,
        close_index=close_index,
        decision_time=decision_time,
        min_abs_funding_bps=primary_floor,
        top_n=top_n,
    )
    target_weight = 1.0
    if len(selected) < _MIN_SELECTED_SYMBOLS:
        selected = _selected_events(
            events,
            close_index=close_index,
            decision_time=decision_time,
            min_abs_funding_bps=_FALLBACK_MIN_ABS_FUNDING_BPS,
            top_n=top_n,
        )
        target_weight = _FALLBACK_WEIGHT_MULTIPLIER
    targets = {symbol: 0.0 for symbol in symbols}
    if len(selected) < _MIN_SELECTED_SYMBOLS:
        return targets
    for event in selected:
        targets[event.symbol] = -target_weight if event.funding_bps > 0.0 else target_weight
    return targets


def _selected_events(
    events: Sequence[_FundingEvent],
    *,
    close_index: Mapping[str, Mapping[datetime, tuple[float, datetime]]],
    decision_time: datetime,
    min_abs_funding_bps: float,
    top_n: int,
) -> list[_FundingEvent]:
    return sorted(
        (
            event
            for event in events
            if event.funding_bps != 0.0
            and abs(event.funding_bps) >= min_abs_funding_bps
            and _passes_price_extension(event, close_index, decision_time)
        ),
        key=lambda event: (-abs(event.funding_bps), event.symbol),
    )[:top_n]


def _passes_price_extension(
    event: _FundingEvent,
    close_index: Mapping[str, Mapping[datetime, tuple[float, datetime]]],
    decision_time: datetime,
) -> bool:
    if not _REQUIRE_PRICE_EXTENSION:
        return True
    extension = _return_extension_bps(
        event,
        close_index,
        decision_time,
        lookback=timedelta(minutes=_PRICE_EXTENSION_LOOKBACK_MINUTES),
    )
    if extension is None:
        return False
    if event.funding_bps > 0.0:
        return extension >= _MIN_PRICE_EXTENSION_BPS
    return extension <= -_MIN_PRICE_EXTENSION_BPS


def _return_extension_bps(
    event: _FundingEvent,
    close_index: Mapping[str, Mapping[datetime, tuple[float, datetime]]],
    decision_time: datetime,
    *,
    lookback: timedelta,
) -> float | None:
    symbol_closes = close_index.get(event.symbol, {})
    current = symbol_closes.get(event.observed_at)
    base = symbol_closes.get(event.observed_at - lookback)
    if current is None or base is None:
        return None
    current_close, current_available_at = current
    base_close, base_available_at = base
    if current_available_at > decision_time or base_available_at > decision_time:
        return None
    if current_close <= 0.0 or base_close <= 0.0:
        return None
    return (current_close / base_close - 1.0) * 10_000.0


def _funding_events_by_time(
    bars: Sequence[Mapping[str, object]],
    *,
    symbols: Sequence[str],
) -> dict[datetime, list[_FundingEvent]]:
    events: dict[datetime, list[_FundingEvent]] = {}
    eligible = set(symbols)
    seen: set[tuple[str, datetime]] = set()
    rows_seen_by_symbol: dict[str, int] = {}
    for row in sorted(bars, key=lambda item: (_as_datetime(item["timestamp"]), str(item["symbol"]))):
        symbol = str(row["symbol"])
        rows_seen = rows_seen_by_symbol.get(symbol, 0)
        rows_seen_by_symbol[symbol] = rows_seen + 1
        if symbol not in eligible:
            continue
        if not bool(row["has_funding_event"]):
            continue
        if rows_seen < _MIN_CAPACITY_HISTORY_BARS:
            continue
        funding_time = _as_datetime(row["funding_timestamp"])
        key = (symbol, funding_time)
        if key in seen:
            continue
        seen.add(key)
        funding_rate = _finite_float(row["funding_rate"])
        if funding_rate is None:
            continue
        observed_at = _as_datetime(row["timestamp"])
        events.setdefault(observed_at, []).append(
            _FundingEvent(
                symbol=symbol,
                observed_at=observed_at,
                funding_time=funding_time,
                available_at=_as_datetime(row["available_at"]),
                funding_rate=funding_rate,
            )
        )
    return events


def _finite_bar_times_by_symbol(
    bars: Sequence[Mapping[str, object]],
) -> dict[str, tuple[datetime, ...]]:
    times: dict[str, set[datetime]] = {}
    for row in bars:
        if _finite_float(row["close"]) is None:
            continue
        times.setdefault(str(row["symbol"]), set()).add(_as_datetime(row["timestamp"]))
    return {symbol: tuple(sorted(values)) for symbol, values in times.items()}


def _close_index(
    bars: Sequence[Mapping[str, object]],
    *,
    symbols: Sequence[str],
) -> dict[str, dict[datetime, tuple[float, datetime]]]:
    eligible = set(symbols)
    indexed: dict[str, dict[datetime, tuple[float, datetime]]] = {}
    for row in bars:
        symbol = str(row["symbol"])
        if symbol not in eligible:
            continue
        close = _finite_float(row["close"])
        if close is None:
            continue
        timestamp = _as_datetime(row["timestamp"])
        available_at = _as_datetime(row["available_at"])
        indexed.setdefault(symbol, {})[timestamp] = (close, available_at)
    return indexed


def _complete_mark_symbols(
    bars: Sequence[Mapping[str, object]],
    *,
    symbols: Sequence[str],
) -> tuple[str, ...]:
    times_by_symbol = _finite_bar_times_by_symbol(bars)
    global_times: set[datetime] = set()
    for values in times_by_symbol.values():
        global_times.update(values)
    if not global_times:
        return ()
    return tuple(
        symbol
        for symbol in symbols
        if set(times_by_symbol.get(symbol, ())) == global_times
    )


def _valid_common_decision_times(
    bars: Sequence[Mapping[str, object]],
    *,
    symbols: Sequence[str],
) -> tuple[datetime, ...]:
    times_by_symbol = _finite_bar_times_by_symbol(bars)
    symbol_sets = [set(times_by_symbol.get(symbol, ())) for symbol in symbols]
    if not symbol_sets:
        return ()
    common = set.intersection(*symbol_sets)
    next_bar_safe = {timestamp - timedelta(minutes=1) for timestamp in common}
    return tuple(sorted(common & next_bar_safe))


def _first_bar_at_or_after(bar_times: Sequence[datetime], target: datetime) -> datetime | None:
    position = bisect_left(bar_times, target)
    if position >= len(bar_times):
        return None
    return bar_times[position]


def _require_fields(bars: Sequence[Mapping[str, object]], required: set[str]) -> None:
    for index, row in enumerate(bars):
        missing = required.difference(row.keys())
        if missing:
            raise ValueError(f"bar {index} missing required fields: {sorted(missing)}")


def _positive_int(value: object, name: str) -> int:
    parsed = int(cast(Any, value))
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _non_negative_int(value: object, name: str) -> int:
    parsed = int(cast(Any, value))
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _non_negative_float(value: object, name: str) -> float:
    parsed = float(cast(Any, value))
    if not math.isfinite(parsed) or parsed < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return parsed


def _finite_float(value: object) -> float | None:
    parsed = float(cast(Any, value))
    if not math.isfinite(parsed):
        return None
    return parsed


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime timestamp, got {type(value).__name__}")
    return value
