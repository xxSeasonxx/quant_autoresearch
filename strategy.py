"""Strategy: fx_triangular_residual_reversion

Source / provenance:
Internal residual-reversion hypothesis derived from FX triangular
arbitrage/law-of-one-price microstructure literature, especially Akram, Rime,
and Sarno (2008), "Arbitrage in the Foreign Exchange Market: Turning on the
Microscope", Journal of International Economics, DOI
10.1016/j.jinteco.2008.07.004. This file is not a direct paper replication.

Market rationale:
Large one-minute deviations between an FX cross and its USD-leg synthetic value
can mark short-lived pressure that mean-reverts.

Required observables:
Symbol, timestamp, and close price for one-minute FX bars covering each
triangle leg.

Signal rule:
Compute triangular log residuals from completed closes, score the current
residual against prior residuals only, attribute the recent residual move to
the largest aligned leg, and trade that leg toward residual mean reversion after
the residual's as-of bar can be observed.

Assumptions:
Close prices and quote fields are sufficiently aligned across triangle legs;
market data availability is represented by the runner's `available_at` field
when present, and the next-bar quote fill is the earliest causal execution used
by the runner config.

Falsifier:
If broad fixed-parameter residual signals do not produce positive gross return
before spread and slippage, reject this one-minute residual proxy before tuning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
import math
from statistics import fmean, pstdev
from typing import Any


__all__ = ["generate_signals"]

_Triangle = tuple[str, str, int, str, int]

_OUTSIDE_VIEW_8_TRIANGLES: tuple[_Triangle, ...] = (
    ("EURJPY", "EURUSD", 1, "USDJPY", 1),
    ("GBPJPY", "GBPUSD", 1, "USDJPY", 1),
    ("AUDJPY", "AUDUSD", 1, "USDJPY", 1),
    ("NZDJPY", "NZDUSD", 1, "USDJPY", 1),
    ("CADJPY", "USDJPY", 1, "USDCAD", -1),
    ("EURGBP", "EURUSD", 1, "GBPUSD", -1),
    ("EURAUD", "EURUSD", 1, "AUDUSD", -1),
    ("AUDNZD", "AUDUSD", 1, "NZDUSD", -1),
)
_ADDITIONAL_AVAILABLE_TRIANGLES: tuple[_Triangle, ...] = (
    ("EURCAD", "EURUSD", 1, "USDCAD", 1),
    ("EURCHF", "EURUSD", 1, "USDCHF", 1),
    ("GBPAUD", "GBPUSD", 1, "AUDUSD", -1),
)


def generate_signals(bars: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> list[dict[str, object]]:
    if not bars:
        return []

    residual_price_field = str(params.get("residual_price_field", "close"))
    if residual_price_field not in {"close", "mid"}:
        raise ValueError("residual_price_field must be 'close' or 'mid'")
    _require_fields(bars, {"symbol", "timestamp", residual_price_field})
    zscore_window_bars = _positive_int(
        params.get("zscore_window_bars", params.get("zscore_window_minutes", 240)),
        "zscore_window_bars",
    )
    min_zscore_observations = _positive_int(params.get("min_zscore_observations", 120), "min_zscore_observations")
    entry_zscore = _positive_float(params.get("entry_zscore", 2.5), "entry_zscore")
    min_abs_residual_bps = _non_negative_float(params.get("min_abs_residual_bps", 1.0), "min_abs_residual_bps")
    max_entry_spread_bps = _optional_positive_float(params.get("max_entry_spread_bps"), "max_entry_spread_bps")
    min_residual_spread_ratio = _optional_positive_float(
        params.get("min_residual_spread_ratio"),
        "min_residual_spread_ratio",
    )
    attribution_bars = _positive_int(
        params.get("attribution_bars", params.get("attribution_minutes", 5)),
        "attribution_bars",
    )
    min_attribution_score = _non_negative_float(params.get("min_attribution_score", 0.0), "min_attribution_score")
    decision_lag_minutes = _non_negative_int(params.get("decision_lag_minutes", 1), "decision_lag_minutes")
    symbol_cooldown_minutes = _non_negative_int(params.get("symbol_cooldown_minutes", 0), "symbol_cooldown_minutes")
    max_signals_per_symbol_per_day = _non_negative_int(
        params.get("max_signals_per_symbol_per_day", 0),
        "max_signals_per_symbol_per_day",
    )
    blocked_decision_hours_utc = _optional_hour_set(
        params.get("blocked_decision_hours_utc"),
        "blocked_decision_hours_utc",
    )
    allowed_decision_hours_utc = _optional_hour_set(
        params.get("allowed_decision_hours_utc"),
        "allowed_decision_hours_utc",
    )
    allowed_trade_symbols = _optional_string_set(params.get("allowed_trade_symbols"), "allowed_trade_symbols")
    if blocked_decision_hours_utc is not None and allowed_decision_hours_utc is not None:
        raise ValueError("blocked_decision_hours_utc and allowed_decision_hours_utc are mutually exclusive")
    leg_selection = str(params.get("leg_selection", "attribution"))
    if leg_selection not in {"attribution", "direct", "basket"}:
        raise ValueError("leg_selection must be 'attribution', 'direct', or 'basket'")
    residual_sign_filter = str(params.get("residual_sign_filter", "both"))
    if residual_sign_filter not in {"both", "positive", "negative"}:
        raise ValueError("residual_sign_filter must be 'both', 'positive', or 'negative'")
    crossing_only = bool(params.get("crossing_only", True))
    require_residual_reversal = bool(params.get("require_residual_reversal", False))
    min_residual_reversal_bps = _non_negative_float(
        params.get("min_residual_reversal_bps", 0.0),
        "min_residual_reversal_bps",
    )
    weight = float(params.get("weight", 1.0))
    max_hold_bars = _positive_int(
        params.get("max_hold_bars", params.get("hold_bars", params.get("hold_minutes", 30))),
        "max_hold_bars",
    )
    exit_controls = _exit_controls(params)

    close_by_key, timestamps, symbols = _close_table(bars, residual_price_field)
    use_spread_filter = max_entry_spread_bps is not None or min_residual_spread_ratio is not None
    spread_by_key = _spread_table(bars) if use_spread_filter else {}

    candidates: dict[tuple[str, datetime], list[dict[str, float | int]]] = {}
    for triangle in _triangles_for(str(params.get("triangle_set", "outside_view_8"))):
        if not set(_triangle_symbols(triangle)).issubset(symbols):
            continue
        points = _residual_points(triangle, timestamps, close_by_key)
        _collect_candidates(
            triangle,
            points,
            close_by_key,
            zscore_window_bars,
            min_zscore_observations,
            entry_zscore,
            min_abs_residual_bps,
            max_entry_spread_bps,
            min_residual_spread_ratio,
            attribution_bars,
            min_attribution_score,
            crossing_only,
            leg_selection,
            residual_sign_filter,
            require_residual_reversal,
            min_residual_reversal_bps,
            allowed_trade_symbols,
            spread_by_key,
            candidates,
        )

    signals: list[dict[str, object]] = []
    last_signal_time_by_symbol: dict[str, datetime] = {}
    signal_count_by_symbol_day: dict[tuple[str, date], int] = {}
    for symbol, as_of_time in sorted(candidates, key=lambda key: (key[1], key[0])):
        entries = candidates[(symbol, as_of_time)]
        score = sum(float(entry["signal"]) * float(entry["strength"]) for entry in entries)
        if abs(score) <= 1e-12:
            continue
        representative = max(entries, key=lambda entry: abs(float(entry["strength"])))
        decision_time = as_of_time + timedelta(minutes=decision_lag_minutes)
        if (symbol, decision_time) not in close_by_key:
            continue
        decision_hour = decision_time.hour
        if allowed_decision_hours_utc is not None and decision_hour not in allowed_decision_hours_utc:
            continue
        if blocked_decision_hours_utc is not None and decision_hour in blocked_decision_hours_utc:
            continue
        last_signal_time = last_signal_time_by_symbol.get(symbol)
        if (
            symbol_cooldown_minutes > 0
            and last_signal_time is not None
            and as_of_time - last_signal_time < timedelta(minutes=symbol_cooldown_minutes)
        ):
            continue
        day_key = (symbol, decision_time.date())
        if (
            max_signals_per_symbol_per_day > 0
            and signal_count_by_symbol_day.get(day_key, 0) >= max_signals_per_symbol_per_day
        ):
            continue
        payload: dict[str, object] = {
            "symbol": symbol,
            "decision_time": decision_time,
            "as_of_time": as_of_time,
            "side": "long" if score > 0.0 else "short",
            "weight": weight,
            "hold_bars": max_hold_bars,
            "max_hold_bars": max_hold_bars,
            "residual_zscore": representative["residual_zscore"],
            "residual_bps": representative["residual_bps"],
            "residual_reversal_bps": representative.get("residual_reversal_bps", 0.0),
            "entry_spread_bps": representative.get("entry_spread_bps"),
            "attribution_score": sum(float(entry["attribution_score"]) for entry in entries),
            "signal_family": "fx_triangular_residual_reversion",
            "leg_selection": leg_selection,
            "residual_price_field": residual_price_field,
            "residual_sign_filter": residual_sign_filter,
        }
        payload.update(exit_controls)
        signals.append(payload)
        last_signal_time_by_symbol[symbol] = as_of_time
        signal_count_by_symbol_day[day_key] = signal_count_by_symbol_day.get(day_key, 0) + 1
    return signals


def _require_fields(bars: Sequence[Mapping[str, object]], required: set[str]) -> None:
    for index, row in enumerate(bars):
        missing = required.difference(row.keys())
        if missing:
            raise ValueError(f"bar {index} missing required fields: {sorted(missing)}")


def _positive_int(value: object, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _non_negative_int(value: object, name: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _positive_float(value: object, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return parsed


def _non_negative_float(value: object, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return parsed


def _optional_positive_float(value: object, name: str) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return parsed


def _optional_hour_set(value: object, name: str) -> frozenset[int] | None:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of UTC hours")
    hours: set[int] = set()
    for raw_hour in value:
        hour = int(raw_hour)
        if hour < 0 or hour > 23:
            raise ValueError(f"{name} values must be UTC hours from 0 to 23")
        hours.add(hour)
    if not hours:
        raise ValueError(f"{name} must not be empty when provided")
    return frozenset(hours)


def _optional_string_set(value: object, name: str) -> frozenset[str] | None:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of strings")
    parsed = {str(item) for item in value}
    if not parsed:
        raise ValueError(f"{name} must not be empty when provided")
    return frozenset(parsed)


def _exit_controls(params: Mapping[str, object]) -> dict[str, object]:
    controls: dict[str, object] = {}
    for name in ("take_profit_bps", "stop_loss_bps", "trailing_stop_bps"):
        value = _optional_positive_float(params.get(name), name)
        if value is not None:
            controls[name] = value
    return controls


def _close_table(
    bars: Sequence[Mapping[str, object]],
    price_field: str = "close",
) -> tuple[dict[tuple[str, datetime], float], list[datetime], set[str]]:
    close_by_key: dict[tuple[str, datetime], float] = {}
    timestamps: set[datetime] = set()
    symbols: set[str] = set()

    for row in bars:
        symbol = str(row["symbol"])
        timestamp = _as_datetime(row["timestamp"])
        close = _positive_finite_float(row[price_field])
        if close is None:
            continue
        key = (symbol, timestamp)
        if key in close_by_key:
            raise ValueError(f"duplicate close row for {symbol} at {timestamp}")
        close_by_key[key] = close
        timestamps.add(timestamp)
        symbols.add(symbol)

    return close_by_key, sorted(timestamps), symbols


def _spread_table(bars: Sequence[Mapping[str, object]]) -> dict[tuple[str, datetime], float]:
    spread_by_key: dict[tuple[str, datetime], float] = {}
    for row in bars:
        if "bid" not in row or "ask" not in row:
            continue
        bid = _positive_finite_float(row["bid"])
        ask = _positive_finite_float(row["ask"])
        if bid is None or ask is None or ask < bid:
            continue
        midpoint = _positive_finite_float(row.get("mid"))
        if midpoint is None:
            midpoint = (bid + ask) / 2.0
        symbol = str(row["symbol"])
        timestamp = _as_datetime(row["timestamp"])
        spread_by_key[(symbol, timestamp)] = (ask - bid) / midpoint * 10_000.0
    return spread_by_key


def _collect_candidates(
    triangle: _Triangle,
    points: list[dict[str, Any]],
    close_by_key: dict[tuple[str, datetime], float],
    zscore_window_bars: int,
    min_zscore_observations: int,
    entry_zscore: float,
    min_abs_residual_bps: float,
    max_entry_spread_bps: float | None,
    min_residual_spread_ratio: float | None,
    attribution_bars: int,
    min_attribution_score: float,
    crossing_only: bool,
    leg_selection: str,
    residual_sign_filter: str,
    require_residual_reversal: bool,
    min_residual_reversal_bps: float,
    allowed_trade_symbols: frozenset[str] | None,
    spread_by_key: dict[tuple[str, datetime], float],
    candidates: dict[tuple[str, datetime], list[dict[str, float | int]]],
) -> None:
    prior_extreme_sign = 0
    residuals = [point["residual"] for point in points]
    for index, point in enumerate(points):
        history = residuals[max(0, index - zscore_window_bars) : index]
        if len(history) < min_zscore_observations:
            prior_extreme_sign = 0
            continue
        std = pstdev(history)
        if not math.isfinite(std) or std <= 0.0:
            prior_extreme_sign = 0
            continue

        history_mean = fmean(history)
        residual_z = (point["residual"] - history_mean) / std
        residual_bps = point["residual"] * 10_000.0
        extreme_sign = _extreme_sign(residual_z, residual_bps, entry_zscore, min_abs_residual_bps)
        if extreme_sign == 0:
            prior_extreme_sign = 0
            continue
        if residual_sign_filter == "positive" and extreme_sign < 0:
            prior_extreme_sign = 0
            continue
        if residual_sign_filter == "negative" and extreme_sign > 0:
            prior_extreme_sign = 0
            continue
        residual_reversal_bps = 0.0
        if require_residual_reversal:
            if index == 0:
                prior_extreme_sign = extreme_sign
                continue
            prior_gap = residuals[index - 1] - history_mean
            current_gap = point["residual"] - history_mean
            residual_reversal_bps = -extreme_sign * (current_gap - prior_gap) * 10_000.0
            if extreme_sign * prior_gap <= 0.0 or residual_reversal_bps <= min_residual_reversal_bps:
                prior_extreme_sign = extreme_sign
                continue

        if leg_selection == "basket":
            selected_entries = _basket_reversion_legs(triangle, extreme_sign, abs(float(residual_bps)))
        elif leg_selection == "direct":
            selected_entries = ((triangle[0], -extreme_sign, abs(float(residual_bps))),)
        else:
            selected = _select_reversion_leg(triangle, points, index, extreme_sign, attribution_bars)
            selected_entries = () if selected is None else (selected,)
        if not selected_entries:
            prior_extreme_sign = extreme_sign
            continue

        if crossing_only and prior_extreme_sign == extreme_sign:
            prior_extreme_sign = extreme_sign
            continue

        as_of_time = point["timestamp"]
        for symbol, signal, attribution_score in selected_entries:
            if attribution_score < min_attribution_score:
                continue
            if allowed_trade_symbols is not None and symbol not in allowed_trade_symbols:
                continue
            if (symbol, as_of_time) not in close_by_key:
                continue
            entry_spread_bps = spread_by_key.get((symbol, as_of_time))
            if max_entry_spread_bps is not None or min_residual_spread_ratio is not None:
                if entry_spread_bps is None:
                    continue
                if max_entry_spread_bps is not None and entry_spread_bps > max_entry_spread_bps:
                    continue
                if (
                    min_residual_spread_ratio is not None
                    and abs(float(residual_bps)) < entry_spread_bps * min_residual_spread_ratio
                ):
                    continue
            candidates.setdefault((symbol, as_of_time), []).append(
                {
                    "signal": signal,
                    "strength": abs(float(residual_z)),
                    "residual_zscore": float(residual_z),
                    "residual_bps": float(residual_bps),
                    "residual_reversal_bps": residual_reversal_bps,
                    "attribution_score": attribution_score,
                    "entry_spread_bps": entry_spread_bps,
                }
            )
        prior_extreme_sign = extreme_sign


def _residual_points(
    triangle: _Triangle,
    timestamps: list[datetime],
    close_by_key: dict[tuple[str, datetime], float],
) -> list[dict[str, Any]]:
    direct, leg_a, leg_a_sign, leg_b, leg_b_sign = triangle
    points: list[dict[str, Any]] = []
    for timestamp in timestamps:
        direct_close = close_by_key.get((direct, timestamp))
        leg_a_close = close_by_key.get((leg_a, timestamp))
        leg_b_close = close_by_key.get((leg_b, timestamp))
        if direct_close is None or leg_a_close is None or leg_b_close is None:
            continue
        logs = {
            direct: math.log(direct_close),
            leg_a: math.log(leg_a_close),
            leg_b: math.log(leg_b_close),
        }
        points.append(
            {
                "timestamp": timestamp,
                "logs": logs,
                "residual": logs[direct] - (leg_a_sign * logs[leg_a] + leg_b_sign * logs[leg_b]),
            }
        )
    return points


def _select_reversion_leg(
    triangle: _Triangle,
    points: list[dict[str, Any]],
    index: int,
    residual_sign: int,
    attribution_bars: int,
) -> tuple[str, int, float] | None:
    direct, leg_a, leg_a_sign, leg_b, leg_b_sign = triangle
    current = points[index]
    prior = points[max(0, index - attribution_bars)]
    current_logs = current["logs"]
    prior_logs = prior["logs"]
    contributions = (
        ("direct", direct, 1, current_logs[direct] - prior_logs[direct]),
        ("synthetic", leg_a, leg_a_sign, -leg_a_sign * (current_logs[leg_a] - prior_logs[leg_a])),
        ("synthetic", leg_b, leg_b_sign, -leg_b_sign * (current_logs[leg_b] - prior_logs[leg_b])),
    )
    aligned = [item for item in contributions if item[3] * residual_sign > 0.0]
    if not aligned:
        return None

    leg_type, symbol, synthetic_sign, contribution = max(aligned, key=lambda item: abs(item[3]))
    attribution_score = abs(float(contribution)) * 10_000.0
    if leg_type == "direct":
        return symbol, -residual_sign, attribution_score
    return symbol, residual_sign * synthetic_sign, attribution_score


def _basket_reversion_legs(
    triangle: _Triangle,
    residual_sign: int,
    attribution_score: float,
) -> tuple[tuple[str, int, float], ...]:
    direct, leg_a, leg_a_sign, leg_b, leg_b_sign = triangle
    return (
        (direct, -residual_sign, attribution_score),
        (leg_a, residual_sign * leg_a_sign, attribution_score),
        (leg_b, residual_sign * leg_b_sign, attribution_score),
    )


def _extreme_sign(
    residual_z: float,
    residual_bps: float,
    entry_zscore: float,
    min_abs_residual_bps: float,
) -> int:
    if abs(residual_z) < entry_zscore or abs(residual_bps) < min_abs_residual_bps:
        return 0
    return 1 if residual_z > 0.0 else -1


def _triangles_for(triangle_set: str) -> tuple[_Triangle, ...]:
    if triangle_set == "outside_view_8":
        return _OUTSIDE_VIEW_8_TRIANGLES
    if triangle_set == "all_available":
        return _OUTSIDE_VIEW_8_TRIANGLES + _ADDITIONAL_AVAILABLE_TRIANGLES
    raise ValueError("triangle_set must be 'outside_view_8' or 'all_available'")


def _triangle_symbols(triangle: _Triangle) -> tuple[str, str, str]:
    return triangle[0], triangle[1], triangle[3]


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime timestamp, got {type(value).__name__}")
    return value


def _positive_finite_float(value: object) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed
