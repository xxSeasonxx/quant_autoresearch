from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from experiment_config import ConfirmationScoringConfig


NOTES = "Loop feedback only. Not market evidence."
SMOKE_SCORE_FIELDS = {
    "raw_net_return": "sum_weighted_trade_net_return",
    "gross_return": "sum_weighted_trade_gross_return",
    "funding_return": "sum_weighted_trade_funding_return",
    "cost_return": "sum_weighted_trade_cost_return",
}


def load_json(path: str | Path) -> dict[str, Any] | None:
    json_path = Path(path)
    if not json_path.exists():
        return None

    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {json_path}")
    return data


def write_score(path: str | Path, payload: dict[str, Any]) -> None:
    score_path = Path(path)
    score_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _screening_result_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    validation_report = evidence.get("validation_report")
    if isinstance(validation_report, dict):
        screening_result = validation_report.get("screening_result")
        if isinstance(screening_result, dict):
            return screening_result
    screening_result = evidence.get("screening_result")
    return screening_result if isinstance(screening_result, dict) else {}


def _v2_returns_from_screening_result(
    screening_result: dict[str, Any],
) -> tuple[float | None, float | None, float | None, float | None, str | None]:
    smoke_score = screening_result.get("smoke_score")
    if not isinstance(smoke_score, dict):
        return None, None, None, None, "missing screening_result.smoke_score.sum_weighted_trade_net_return"

    values: dict[str, float | None] = {}
    for payload_key, field_name in SMOKE_SCORE_FIELDS.items():
        values[payload_key] = _as_float_or_none(smoke_score.get(field_name))
        if values[payload_key] is None:
            return None, None, None, None, f"missing screening_result.smoke_score.{field_name}"

    return (
        values["raw_net_return"],
        values["gross_return"],
        values["funding_return"],
        values["cost_return"],
        None,
    )


def classify_failure_source(stage: str | None, message: str | None) -> str | None:
    if not stage:
        return None

    normalized_stage = stage.strip().lower()
    normalized_message = (message or "").strip().lower()

    if "no module named" in normalized_message or "conda" in normalized_message:
        return "environment_error"
    if normalized_stage in {"config", "config_load"} or "invalid toml" in normalized_message:
        return "config_error"
    if normalized_stage in {"strategy_import", "signal_generation", "decision_generation", "param_validation", "request_build"}:
        return "strategy_error"
    if normalized_stage == "data_load":
        return "quant_data_error"
    if normalized_stage == "data_readiness":
        if _looks_strategy_caused_readiness_failure(normalized_message):
            return "strategy_error"
        return "quant_data_error"
    if normalized_stage == "engine_evaluation":
        return "quant_strategies_error"
    return "quant_strategies_error"


def build_score(
    summary: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    min_score_trades: int,
    window_id: str,
    failure_source: str | None,
    complexity_note: str = "",
    window_start: str | None = None,
    window_end: str | None = None,
    window_days: int | None = None,
    symbol_count: int | None = None,
) -> dict[str, Any]:
    if evidence is None:
        source = failure_source
        if source is None and summary is not None:
            source = classify_failure_source(
                _as_str_or_none(summary.get("stage")),
                _as_str_or_none(summary.get("message")),
            )
        return _payload(
            status="runner_failed" if summary is not None else "crash",
            score=None,
            raw_net_return=None,
            gross_return=None,
            funding_return=None,
            cost_return=None,
            trade_count=None,
            min_score_trades=min_score_trades,
            window_id=window_id,
            window_start=window_start,
            window_end=window_end,
            window_days=window_days,
            symbol_count=symbol_count,
            passed_validation=False,
            failed_gates=[],
            failure_source=source,
            failure_message=None,
            complexity_note=complexity_note,
        )

    validation_report = evidence.get("validation_report")
    if not isinstance(validation_report, dict):
        validation_report = {}

    screening_result = _screening_result_from_evidence(evidence)
    trade_count = _as_int_or_none(screening_result.get("trade_count"))
    raw_net_return, gross_return, funding_return, cost_return, smoke_score_error = _v2_returns_from_screening_result(
        screening_result
    )
    passed_validation = validation_report.get("passed") is True
    failed_gates = _failed_gate_names(validation_report.get("gates"))

    failure_message = None
    if smoke_score_error is not None:
        status = "runner_failed"
        score = None
        failure_source = failure_source or "quant_strategies_error"
        failure_message = smoke_score_error
    elif trade_count is None or trade_count < min_score_trades:
        status = "insufficient_sample"
        score = None
    elif not passed_validation:
        status = "validation_failed"
        score = _window_normalized_score(raw_net_return, window_days)
    else:
        status = "scored"
        score = _window_normalized_score(raw_net_return, window_days)

    return _payload(
        status=status,
        score=score,
        raw_net_return=raw_net_return,
        gross_return=gross_return,
        funding_return=funding_return,
        cost_return=cost_return,
        trade_count=trade_count,
        min_score_trades=min_score_trades,
        window_id=window_id,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        symbol_count=symbol_count,
        passed_validation=passed_validation,
        failed_gates=failed_gates,
        failure_source=failure_source,
        failure_message=failure_message,
        complexity_note=complexity_note,
    )


def build_candidate_score(
    *,
    window_scores: list[dict[str, Any]],
    config: ConfirmationScoringConfig,
    commit: str | None,
    description: str,
) -> dict[str, Any]:
    numeric_scores: list[float] = []
    failed_windows: list[str] = []
    passed_windows: list[str] = []
    trade_counts: list[int] = []
    symbol_counts: list[int] = []

    for score in window_scores:
        window_id = _as_str_or_none(score.get("window_id")) or ""
        value = _as_float_or_none(score.get("score"))
        trade_count = _as_int_or_none(score.get("trade_count"))
        symbol_count = _as_int_or_none(score.get("symbol_count"))
        if trade_count is not None:
            trade_counts.append(trade_count)
        if symbol_count is not None:
            symbol_counts.append(symbol_count)
        if value is None:
            failed_windows.append(window_id)
            continue
        numeric_scores.append(value)
        if value <= config.weak_window_floor:
            failed_windows.append(window_id)
        else:
            passed_windows.append(window_id)

    if len(numeric_scores) != len(window_scores):
        return _candidate_payload(
            status="confirmation_failed",
            candidate_score=None,
            window_scores=window_scores,
            commit=commit,
            description=description,
            recent_mean_score=None,
            recent_median_score=None,
            worst_recent_score=None,
            score_dispersion=None,
            total_trade_count=sum(trade_counts),
            min_window_trade_count=min(trade_counts) if trade_counts else None,
            symbol_count=min(symbol_counts) if symbol_counts else None,
            passed_windows=passed_windows,
            failed_windows=failed_windows,
            penalties={
                "dispersion": None,
                "weak_windows": None,
                "low_trades": None,
                "symbol_concentration": None,
            },
        )

    recent_mean_score = statistics.fmean(numeric_scores)
    recent_median_score = statistics.median(numeric_scores)
    worst_recent_score = min(numeric_scores)
    score_dispersion = statistics.pstdev(numeric_scores) if len(numeric_scores) > 1 else 0.0
    min_window_trade_count = min(trade_counts) if trade_counts else None
    symbol_count = min(symbol_counts) if symbol_counts else None

    weak_window_count = sum(1 for value in numeric_scores if value <= config.weak_window_floor)
    low_trade_count = sum(1 for value in trade_counts if value < config.min_trades_per_window)
    symbol_concentration = (
        config.symbol_concentration_penalty
        if symbol_count is not None and symbol_count < config.min_symbol_count
        else 0.0
    )
    penalties = {
        "dispersion": score_dispersion * config.dispersion_weight,
        "weak_windows": weak_window_count * config.weak_window_penalty,
        "low_trades": low_trade_count * config.low_trade_penalty,
        "symbol_concentration": symbol_concentration,
    }
    candidate_score = recent_mean_score - sum(penalties.values())

    return _candidate_payload(
        status="scored",
        candidate_score=candidate_score,
        window_scores=window_scores,
        commit=commit,
        description=description,
        recent_mean_score=recent_mean_score,
        recent_median_score=recent_median_score,
        worst_recent_score=worst_recent_score,
        score_dispersion=score_dispersion,
        total_trade_count=sum(trade_counts),
        min_window_trade_count=min_window_trade_count,
        symbol_count=symbol_count,
        passed_windows=passed_windows,
        failed_windows=failed_windows,
        penalties=penalties,
    )


def build_trade_attribution(evidence_by_window: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    groups: dict[str, dict[str, dict[str, float | int]]] = {
        "by_window": {},
        "by_symbol": {},
        "by_side": {},
        "by_decision_hour": {},
        "by_month": {},
        "by_symbol_side": {},
        "by_window_side": {},
        "by_window_hour": {},
    }
    total_trade_count = 0

    for window_id, evidence in evidence_by_window.items():
        for trade in _trades_from_evidence(evidence):
            total_trade_count += 1
            symbol = str(trade.get("symbol", ""))
            side = str(trade.get("side", ""))
            decision_time = str(trade.get("decision_time", ""))
            hour = _iso_hour(decision_time)
            month = _iso_month(decision_time)

            keys = {
                "by_window": window_id,
                "by_symbol": symbol,
                "by_side": side,
                "by_decision_hour": hour,
                "by_month": month,
                "by_symbol_side": f"{symbol}|{side}",
                "by_window_side": f"{window_id}|{side}",
                "by_window_hour": f"{window_id}|{hour}",
            }
            for group_name, group_key in keys.items():
                _add_trade_to_group(groups[group_name], group_key, trade)

    return {
        "total_trade_count": total_trade_count,
        **groups,
    }


def _payload(
    *,
    status: str,
    score: float | None,
    raw_net_return: float | None,
    gross_return: float | None,
    funding_return: float | None,
    cost_return: float | None,
    trade_count: int | None,
    min_score_trades: int,
    window_id: str,
    window_start: str | None,
    window_end: str | None,
    window_days: int | None,
    symbol_count: int | None,
    passed_validation: bool,
    failed_gates: list[str],
    failure_source: str | None,
    failure_message: str | None,
    complexity_note: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "score": score,
        "metric": "net_return",
        "score_basis": "net_return_per_day" if _has_positive_window_days(window_days) else "net_return",
        "raw_net_return": raw_net_return,
        "gross_return": gross_return,
        "funding_return": funding_return,
        "cost_return": cost_return,
        "trade_count": trade_count,
        "min_score_trades": min_score_trades,
        "window_id": window_id,
        "window_start": window_start,
        "window_end": window_end,
        "window_days": window_days,
        "symbol_count": symbol_count,
        "passed_validation": passed_validation,
        "failed_gates": failed_gates,
        "failure_source": failure_source,
        "failure_message": failure_message,
        "complexity_note": complexity_note,
        "notes": NOTES,
    }


def _candidate_payload(
    *,
    status: str,
    candidate_score: float | None,
    window_scores: list[dict[str, Any]],
    commit: str | None,
    description: str,
    recent_mean_score: float | None,
    recent_median_score: float | None,
    worst_recent_score: float | None,
    score_dispersion: float | None,
    total_trade_count: int,
    min_window_trade_count: int | None,
    symbol_count: int | None,
    passed_windows: list[str],
    failed_windows: list[str],
    penalties: dict[str, float | None],
) -> dict[str, Any]:
    return {
        "status": status,
        "candidate_score": candidate_score,
        "metric": "balanced_recent_net_return_per_day",
        "commit": commit,
        "description": _single_line(description),
        "recent_mean_score": recent_mean_score,
        "recent_median_score": recent_median_score,
        "worst_recent_score": worst_recent_score,
        "score_dispersion": score_dispersion,
        "total_trade_count": total_trade_count,
        "min_window_trade_count": min_window_trade_count,
        "symbol_count": symbol_count,
        "passed_windows": passed_windows,
        "failed_windows": failed_windows,
        "penalties": penalties,
        "window_scores": window_scores,
        "notes": NOTES,
    }


def _trades_from_evidence(evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    if evidence is None:
        return []
    screening_result = _screening_result_from_evidence(evidence)
    trades = screening_result.get("trades")
    if not isinstance(trades, list):
        return []
    return [trade for trade in trades if isinstance(trade, dict)]


def _add_trade_to_group(group: dict[str, dict[str, float | int]], key: str, trade: dict[str, Any]) -> None:
    row = group.setdefault(
        key,
        {
            "trade_count": 0,
            "gross_return": 0.0,
            "funding_return": 0.0,
            "cost_return": 0.0,
            "net_return": 0.0,
            "average_net_per_trade": 0.0,
            "score_contribution": 0.0,
        },
    )
    row["trade_count"] = int(row["trade_count"]) + 1
    row["gross_return"] = float(row["gross_return"]) + _trade_float(trade.get("gross_return"))
    row["funding_return"] = float(row["funding_return"]) + _trade_float(trade.get("funding_return"))
    row["cost_return"] = float(row["cost_return"]) + _trade_float(trade.get("cost_return"))
    row["net_return"] = float(row["net_return"]) + _trade_float(trade.get("net_return"))
    row["average_net_per_trade"] = float(row["net_return"]) / int(row["trade_count"])
    row["score_contribution"] = float(row["net_return"])


def _failed_gate_names(gates: object) -> list[str]:
    if not isinstance(gates, list):
        return []

    names: list[str] = []
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("passed") is not False:
            continue
        name = gate.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def _window_normalized_score(raw_net_return: float, window_days: int | None) -> float:
    if not _has_positive_window_days(window_days):
        return raw_net_return
    return raw_net_return / float(window_days)


def _has_positive_window_days(window_days: int | None) -> bool:
    return isinstance(window_days, int) and not isinstance(window_days, bool) and window_days > 0


def _trade_float(value: object) -> float:
    parsed = _as_float_or_none(value)
    return 0.0 if parsed is None else parsed


def _iso_hour(value: str) -> str:
    return value[11:13] if len(value) >= 13 else ""


def _iso_month(value: str) -> str:
    return value[:7] if len(value) >= 7 else ""


def _as_float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _as_int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _as_str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _single_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


def _looks_strategy_caused_readiness_failure(message: str) -> bool:
    strategy_markers = (
        "emitted signal",
        "signal timing",
        "as_of_time",
        "as-of row",
        "as_of row",
        "decision time",
        "decision timestamp",
    )
    if any(marker in message for marker in strategy_markers):
        return True
    if "outside available" not in message:
        return False
    return any(
        context in message
        for context in ("signal", "fill", "decision", "as_of", "as-of", "entry", "exit")
    )
