from __future__ import annotations

from scoring import build_score, classify_failure_source


def evidence(
    *,
    net_return: float = 0.03,
    gross_return: float = 0.04,
    cost_return: float = 0.01,
    trade_count: int = 25,
    passed: bool = True,
) -> dict[str, object]:
    return {
        "validation_report": {
            "passed": passed,
            "gates": [
                {"name": "valid_inputs", "passed": True, "detail": "screening completed"},
                {"name": "positive_net", "passed": passed, "detail": f"net_return={net_return}"},
            ],
            "screening_result": {
                "trade_count": trade_count,
                "net_return": net_return,
                "gross_return": gross_return,
                "cost_return": cost_return,
            },
        }
    }


def test_build_score_returns_guarded_score_when_trade_count_is_sufficient():
    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=evidence(net_return=0.03, trade_count=25),
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
    )

    assert score["status"] == "scored"
    assert score["score"] == 0.03
    assert score["raw_net_return"] == 0.03
    assert score["trade_count"] == 25
    assert score["passed_validation"] is True
    assert score["failed_gates"] == []
    assert score["notes"] == "Loop feedback only. Not market evidence."


def test_build_score_returns_null_score_for_insufficient_sample():
    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=evidence(net_return=0.50, trade_count=1),
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
    )

    assert score["status"] == "insufficient_sample"
    assert score["score"] is None
    assert score["raw_net_return"] == 0.50
    assert score["trade_count"] == 1


def test_build_score_preserves_numeric_feedback_for_failed_validation_with_enough_trades():
    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_failed"},
        evidence=evidence(net_return=-0.02, trade_count=30, passed=False),
        min_score_trades=20,
        window_id="holdout",
        failure_source=None,
    )

    assert score["status"] == "validation_failed"
    assert score["score"] == -0.02
    assert score["passed_validation"] is False
    assert score["failed_gates"] == ["positive_net"]


def test_build_score_classifies_runner_failure_without_evidence():
    score = build_score(
        summary={"stage": "data_load", "message": "strict data window failed"},
        evidence=None,
        min_score_trades=20,
        window_id="primary",
        failure_source="quant_data_error",
    )

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["failure_source"] == "quant_data_error"
    assert score["trade_count"] is None


def test_classify_failure_source_maps_runner_stages_and_messages():
    assert classify_failure_source("signal_generation", "strategy execution failed") == "strategy_error"
    assert classify_failure_source("request_build", "entry fill is outside available bars") == "strategy_error"
    assert classify_failure_source("data_load", "strict data window failed") == "quant_data_error"
    assert classify_failure_source("strategy_import", "strategy import failed") == "strategy_error"
    assert classify_failure_source("config", "invalid TOML") == "config_error"
    assert classify_failure_source("engine_evaluation", "engine evaluation failed") == "quant_strategies_error"
