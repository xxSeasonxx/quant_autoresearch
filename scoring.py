from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


NOTES = "Loop feedback only. Not market evidence."


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


def classify_failure_source(stage: str | None, message: str | None) -> str | None:
    if not stage:
        return None

    normalized_stage = stage.strip().lower()
    normalized_message = (message or "").strip().lower()

    if "no module named" in normalized_message or "conda" in normalized_message:
        return "environment_error"
    if normalized_stage in {"config", "config_load"} or "invalid toml" in normalized_message:
        return "config_error"
    if normalized_stage in {"strategy_import", "signal_generation", "request_build"}:
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
            complexity_note=complexity_note,
        )

    validation_report = evidence.get("validation_report")
    if not isinstance(validation_report, dict):
        validation_report = {}

    screening_result = validation_report.get("screening_result")
    if not isinstance(screening_result, dict):
        screening_result = evidence.get("screening_result")
    if not isinstance(screening_result, dict):
        screening_result = {}

    trade_count = _as_int_or_none(screening_result.get("trade_count"))
    raw_net_return = _as_float_or_none(screening_result.get("net_return"))
    gross_return = _as_float_or_none(screening_result.get("gross_return"))
    cost_return = _as_float_or_none(screening_result.get("cost_return"))
    passed_validation = validation_report.get("passed") is True
    failed_gates = _failed_gate_names(validation_report.get("gates"))

    if trade_count is None or trade_count < min_score_trades:
        status = "insufficient_sample"
        score = None
    elif raw_net_return is None:
        status = "runner_failed"
        score = None
    elif not passed_validation:
        status = "validation_failed"
        score = raw_net_return
    else:
        status = "scored"
        score = raw_net_return

    return _payload(
        status=status,
        score=score,
        raw_net_return=raw_net_return,
        gross_return=gross_return,
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
        complexity_note=complexity_note,
    )


def _payload(
    *,
    status: str,
    score: float | None,
    raw_net_return: float | None,
    gross_return: float | None,
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
    complexity_note: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "score": score,
        "metric": "net_return",
        "raw_net_return": raw_net_return,
        "gross_return": gross_return,
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
        "complexity_note": complexity_note,
        "notes": NOTES,
    }


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
