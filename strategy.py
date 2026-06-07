"""Strategy: simple_causal_momentum

Source / provenance:
Internal baseline example for the clean-slate autoresearch loop, grounded in the
generic time-series momentum anomaly documented by Moskowitz, Ooi, and Pedersen
(2012), "Time Series Momentum", Journal of Financial Economics, DOI
10.1016/j.jfineco.2011.11.003. This is not a paper replication.

Market rationale:
Recent returns can persist over short horizons when flows, slow information
diffusion, or positioning pressure continue after the first move.

Required observables:
symbol, timestamp, available_at, close.

Decision rule:
For each symbol, compare the latest close with the close `lookback_bars` earlier.
If the return exceeds `threshold_bps`, emit one long target after the latest row
is available.

Assumptions:
Signals are evaluated after data is available. Fills are controlled by the
read-only protocol, not by strategy code.

Falsifier:
If the rule cannot clear Train trade floor and after-cost robustness gates before
parameter tuning, reject this baseline thesis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from quant_strategies.decisions import (
    ExitPolicy,
    InstrumentRef,
    ObservationRef,
    PositionTarget,
    StrategyDecision,
)

__all__ = ["validate_params", "generate_decisions"]

_DEFAULTS = {
    "lookback_bars": 3,
    "threshold_bps": 50.0,
    "weight": 0.10,
    "max_hold_bars": 4,
}


def validate_params(params: Mapping[str, object]) -> dict[str, object]:
    unknown = set(params) - set(_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params: {sorted(unknown)}")

    out = dict(_DEFAULTS)
    out.update(params)

    lookback_bars = int(out["lookback_bars"])
    threshold_bps = float(out["threshold_bps"])
    weight = float(out["weight"])
    max_hold_bars = int(out["max_hold_bars"])

    if lookback_bars < 2:
        raise ValueError("lookback_bars must be >= 2")
    if not isfinite(threshold_bps) or threshold_bps <= 0.0:
        raise ValueError("threshold_bps must be finite and positive")
    if not isfinite(weight) or not (0.0 < weight <= 1.0):
        raise ValueError("weight must be in (0, 1]")
    if max_hold_bars < 1:
        raise ValueError("max_hold_bars must be >= 1")

    return {
        "lookback_bars": lookback_bars,
        "threshold_bps": threshold_bps,
        "weight": weight,
        "max_hold_bars": max_hold_bars,
    }


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"expected datetime-compatible value, got {type(value)!r}")


def _instrument(symbol: str) -> InstrumentRef:
    kind = "crypto_perp" if symbol.endswith("-PERP") else "equity_or_etf"
    return InstrumentRef(kind=kind, symbol=symbol)


def generate_decisions(
    rows: Sequence[Mapping[str, object]],
    params: Mapping[str, object],
) -> list[StrategyDecision]:
    cfg = validate_params(params)
    lookback = int(cfg["lookback_bars"])
    threshold = float(cfg["threshold_bps"]) / 10_000.0
    weight = float(cfg["weight"])
    max_hold_bars = int(cfg["max_hold_bars"])

    by_symbol: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        by_symbol.setdefault(str(row["symbol"]), []).append(row)

    decisions: list[StrategyDecision] = []
    for symbol, symbol_rows in sorted(by_symbol.items()):
        ordered = sorted(symbol_rows, key=lambda row: _as_datetime(row["timestamp"]))
        if len(ordered) <= lookback:
            continue
        active_until_index = -1
        for index in range(lookback, len(ordered)):
            if index <= active_until_index:
                continue
            current = ordered[index]
            prior = ordered[index - lookback]
            current_close = float(current["close"])
            prior_close = float(prior["close"])
            if prior_close <= 0.0:
                continue
            ret = current_close / prior_close - 1.0
            if ret <= threshold:
                continue

            as_of_time = _as_datetime(current.get("available_at", current["timestamp"]))
            decision_time = as_of_time + timedelta(microseconds=1)
            decisions.append(
                StrategyDecision(
                    strategy_id="strategy",
                    instrument=_instrument(symbol),
                    decision_time=decision_time,
                    as_of_time=as_of_time,
                    target=PositionTarget(direction="long", size=weight),
                    exit_policy=ExitPolicy(max_hold_bars=max_hold_bars),
                    observations=(
                        ObservationRef(
                            symbol=symbol,
                            timestamp=_as_datetime(prior["timestamp"]),
                            field="close",
                        ),
                        ObservationRef(
                            symbol=symbol,
                            timestamp=_as_datetime(current["timestamp"]),
                            field="close",
                        ),
                    ),
                )
            )
            active_until_index = index + max_hold_bars
    return decisions
