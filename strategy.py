"""Strategy: time-series momentum (the agent-editable surface).

This is the ONE file (with ``experiment.toml`` ``[params]``) the agent edits. It expresses a
single, simple, falsifiable, causal hypothesis. The harness (``harness/``) judges it; this file
never decides how it is judged.

Provenance:
A clean greenfield example written for the rebuilt harness — NOT the diagnosed legacy ensemble
(that overfit story now lives in ``docs/``). It is deliberately minimal so it is easy to audit
and so the agent has a clear, honest starting point to develop from.

Market rationale (the hypothesis):
Liquid crypto perpetuals exhibit short-horizon TREND PERSISTENCE: an instrument whose price rose
over the recent lookback window is, on average, slightly more likely to keep rising over the next
bar than to reverse. This is a real, widely-documented cross-asset effect (time-series momentum),
not a calendar artifact or a single-name bet. We take a fixed normalized long position in each
instrument whose lookback return clears a small positive threshold, and stay flat otherwise.
Sizing is a FIXED normalized weight — the harness freezes leverage during search, so size is not
part of the edge.

Required observables:
Per row: ``symbol``, a timezone-aware ``timestamp``, and ``close`` (``open``/``high``/``low`` are
read when present but only ``close`` drives the signal). Hourly crypto-perp bars by default.

Decision rule (point-in-time causal):
For each symbol, at each bar we observe the close AT ``as_of_time`` and the close ``lookback_bars``
earlier; if the lookback return exceeds ``entry_threshold`` we emit a LONG target-weight decision,
flat otherwise. The decision is stamped ``decision_time = as_of_time + decision_lag_minutes`` so it
is emitted strictly AFTER the as-of bar is observable (no hidden lookahead). The position is held
``max_hold_bars`` bars; re-entry is suppressed until the hold window elapses.

Assumptions:
Rows are causally ordered (the runner's ``available_at`` when present); bars are evenly spaced
enough to treat ``lookback_bars`` as a fixed bar count; one position per symbol at a time.

Falsifier:
If the lookback-up instruments do not, out-of-sample and after costs, earn a positive risk-adjusted
residual return — i.e. the edge is pure market/funding beta, is carried by a single symbol, or
collapses under the stability perturbation — this hypothesis is wrong and the harness will not
graduate it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from quant_strategies.decisions import (
    ExitPolicy,
    InstrumentRef,
    ObservationRef,
    PositionTarget,
    StrategyDecision,
)

__all__ = ["generate_decisions", "validate_params"]

# Defaults are conservative and live here so the file runs as-is; the agent tunes them in
# ``experiment.toml`` ``[params]`` (the harness freezes sizing and perturbs the rest).
_DEFAULTS: dict[str, object] = {
    "lookback_bars": 24,        # bars over which the trend is measured (e.g. ~1 day hourly)
    "entry_threshold": 0.01,    # min lookback return to go long (after-cost edge must clear costs)
    "base_position_pct": 0.05,  # FIXED normalized target weight per instrument (sizing frozen)
    "max_hold_bars": 24,        # bars to hold a position before it may re-enter
    "decision_lag_minutes": 60, # decision emitted strictly after the as-of bar (no lookahead)
    "strategy_id": "ts_momentum",
}

_REQUIRED_FIELDS = ("symbol", "timestamp", "close")


def validate_params(params: Mapping[str, object]) -> dict[str, object]:
    """Validate + normalize the agent's params, returning a defensive copy.

    Raises ``ValueError``/``TypeError`` on an invalid param so a malformed Experiment fails loudly
    rather than silently mis-trading. ``decision_lag_minutes`` must be > 0 (a decision may never be
    emitted on the same instant as the bar it observes — that would be hidden lookahead).
    """
    out = dict(_DEFAULTS)
    out.update(params)

    out["lookback_bars"] = _positive_int(out["lookback_bars"], "lookback_bars")
    out["entry_threshold"] = _finite_float(out["entry_threshold"], "entry_threshold")
    out["base_position_pct"] = _positive_float(out["base_position_pct"], "base_position_pct")
    out["max_hold_bars"] = _positive_int(out["max_hold_bars"], "max_hold_bars")
    lag = _non_negative_int(out["decision_lag_minutes"], "decision_lag_minutes")
    if lag <= 0:
        raise ValueError("decision_lag_minutes must be > 0 (decisions follow the observed bar)")
    out["decision_lag_minutes"] = lag
    out["strategy_id"] = str(out["strategy_id"])
    return out


def generate_decisions(
    bars: Sequence[Mapping[str, object]],
    params: Mapping[str, object],
) -> list[StrategyDecision]:
    """Emit long/flat target-weight decisions from short-horizon trend persistence (the signal).

    Pure: reads only the supplied ``bars`` (no data loading, no I/O, no clock). For each symbol,
    scans its causally-ordered bars; when the ``lookback_bars`` return clears ``entry_threshold``
    it emits a LONG decision held ``max_hold_bars`` bars. Returns decisions sorted by
    ``(decision_time, symbol)`` for determinism.
    """
    if not bars:
        return []
    p = validate_params(params)
    rows_by_symbol = _rows_by_symbol(bars)
    lookback = p["lookback_bars"]
    threshold = p["entry_threshold"]
    weight = p["base_position_pct"]
    max_hold = p["max_hold_bars"]
    lag = timedelta(minutes=p["decision_lag_minutes"])
    strategy_id = p["strategy_id"]

    decisions: list[StrategyDecision] = []
    for symbol, rows in rows_by_symbol.items():
        if len(rows) <= lookback:
            continue
        next_allowed = lookback
        for i in range(lookback, len(rows)):
            if i < next_allowed:
                continue
            as_of_close = rows[i]["close"]
            past_close = rows[i - lookback]["close"]
            if past_close <= 0.0:
                continue
            lookback_return = as_of_close / past_close - 1.0
            if lookback_return <= threshold:
                continue  # not enough up-trend to clear the entry floor → stay flat

            as_of_time = rows[i]["timestamp"]
            decisions.append(
                StrategyDecision(
                    strategy_id=strategy_id,
                    instrument=InstrumentRef(kind="crypto_perp", symbol=symbol),
                    decision_time=as_of_time + lag,  # strictly after the observed bar (causal)
                    as_of_time=as_of_time,
                    target=PositionTarget(direction="long", sizing_kind="target_weight", size=weight),
                    exit_policy=ExitPolicy(max_hold_bars=max_hold),
                    observations=(ObservationRef(symbol=symbol, timestamp=as_of_time, field="close"),),
                    metadata={"lookback_return": float(lookback_return)},
                )
            )
            next_allowed = i + max_hold + 1  # suppress re-entry until the hold window elapses
    return sorted(decisions, key=lambda d: (d.decision_time, d.instrument.symbol))


# --------------------------------------------------------------------------- #
# Helpers (pure).
# --------------------------------------------------------------------------- #


def _rows_by_symbol(
    bars: Sequence[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Group bars by symbol, validate the required fields, and sort each group by timestamp.

    Sorting by the tz-aware timestamp gives a causal order even if the input is interleaved; the
    runner's ``available_at`` ordering is respected when the input is already so ordered.
    """
    grouped: dict[str, list[dict[str, object]]] = {}
    for raw in bars:
        for field in _REQUIRED_FIELDS:
            if field not in raw:
                raise ValueError(f"bar is missing required field {field!r}")
        symbol = str(raw["symbol"])
        timestamp = _as_datetime(raw["timestamp"])
        close = _positive_float(raw["close"], "close")
        grouped.setdefault(symbol, []).append({"symbol": symbol, "timestamp": timestamp, "close": close})
    for rows in grouped.values():
        rows.sort(key=lambda r: r["timestamp"])
    return grouped


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime timestamp, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


def _positive_int(value: object, name: str) -> int:
    parsed = int(value)  # type: ignore[arg-type]
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _non_negative_int(value: object, name: str) -> int:
    parsed = int(value)  # type: ignore[arg-type]
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed


def _finite_float(value: object, name: str) -> float:
    parsed = float(value)  # type: ignore[arg-type]
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _positive_float(value: object, name: str) -> float:
    parsed = _finite_float(value, name)
    if parsed <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return parsed
