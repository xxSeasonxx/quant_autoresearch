"""Strategy: autoresearch_template

Source / provenance:
Internal neutral starting template for quant_autoresearch. It is not a researched
edge and not an external paper; it exists to express the target-book contract end
to end so a new thesis can replace the decision rule with its own mechanism.

Market rationale:
None claimed. A long-while-rising placeholder gives the harness a standing target
book with enough at-risk bars to score. It is a starting shape, not an alpha
source.

Required observables:
Symbol, timestamp, close, and available_at for ordered bars.

Decision rule:
Per symbol, hold a long `weight`-of-NAV target while the latest available close
exceeds the close `lookback_bars` bars earlier, and flatten (target 0) otherwise.
Targets are standing and idempotent: a decision is emitted only when the desired
target changes for that symbol, so re-confirming the current target trades
nothing and same-symbol exposure nets by construction.

Assumptions:
Signals gate on each bar's available_at, never its own timestamp. A target
becomes actionable on the first bar at or after the signal bar's available_at, so
decision_time lands on an already-available bar and the configured fill model
enters on the following bar.

Falsifier:
This is a placeholder, not a thesis. As a neutral momentum toy it should show no
durable edge; a real thesis replaces the decision rule before any tuning.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from quant_strategies.decisions import InstrumentRef, ObservationRef, TargetDecision

__all__ = ["validate_params", "generate_decisions"]

_STRATEGY_ID = "autoresearch_template"
_INSTRUMENT_KIND = "crypto_perp"


def validate_params(params: Mapping[str, object]) -> dict[str, object]:
    weight = float(params.get("weight", 0.25))
    if not math.isfinite(weight) or not 0.0 < weight <= 1.0:
        raise ValueError("weight must be finite and in (0, 1]")
    lookback_bars = int(params.get("lookback_bars", 60))
    if lookback_bars < 1:
        raise ValueError("lookback_bars must be >= 1")
    return {"weight": weight, "lookback_bars": lookback_bars}


def generate_decisions(
    rows: Sequence[Mapping[str, object]],
    params: Mapping[str, object],
) -> list[TargetDecision]:
    validated = validate_params(params)
    weight = float(validated["weight"])
    lookback_bars = int(validated["lookback_bars"])

    decisions: list[TargetDecision] = []
    for symbol, bars in _rows_by_symbol(rows).items():
        current_target = 0.0
        for index in range(lookback_bars, len(bars)):
            prior_close = float(bars[index - lookback_bars]["close"])
            latest_close = float(bars[index]["close"])
            desired_target = weight if latest_close > prior_close else 0.0
            if desired_target == current_target:
                continue
            entry_index = _first_bar_at_or_after(
                bars, index + 1, bars[index]["available_at"]
            )
            if entry_index is None:
                break
            decisions.append(
                TargetDecision(
                    strategy_id=_STRATEGY_ID,
                    instrument=InstrumentRef(kind=_INSTRUMENT_KIND, symbol=symbol),
                    decision_time=bars[entry_index]["timestamp"],
                    as_of_time=bars[index]["timestamp"],
                    target=desired_target,
                    observations=(
                        ObservationRef(
                            symbol=symbol,
                            timestamp=bars[index - lookback_bars]["timestamp"],
                            field="close",
                            source="strategy_input",
                        ),
                        ObservationRef(
                            symbol=symbol,
                            timestamp=bars[index]["timestamp"],
                            field="close",
                            source="strategy_input",
                        ),
                    ),
                )
            )
            current_target = desired_target
    return decisions


def _rows_by_symbol(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, list[Mapping[str, object]]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["symbol"]), []).append(row)
    for bars in grouped.values():
        bars.sort(key=lambda bar: bar["timestamp"])
    return grouped


def _first_bar_at_or_after(
    bars: Sequence[Mapping[str, object]],
    start: int,
    available_at: object,
) -> int | None:
    for index in range(start, len(bars)):
        if bars[index]["timestamp"] >= available_at:
            return index
    return None
