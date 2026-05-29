from __future__ import annotations

import pytest

from experiment_config import ConfirmationScoringConfig
from scoring import build_candidate_score, build_score, build_trade_attribution, classify_failure_source


def evidence(
    *,
    net_return: float = 0.03,
    gross_return: float = 0.04,
    funding_return: float = 0.002,
    cost_return: float = 0.01,
    trade_count: int = 25,
    passed: bool = True,
) -> dict[str, object]:
    screening_result = {
        "trade_count": trade_count,
        "smoke_score": {
            "sum_weighted_trade_net_return": net_return,
            "sum_weighted_trade_gross_return": gross_return,
            "sum_weighted_trade_funding_return": funding_return,
            "sum_weighted_trade_cost_return": cost_return,
        },
    }
    return {
        "schema_version": "quant_strategies.engine.evidence/v2",
        "mode": "validate",
        "strategy_id": "demo_strategy",
        "screening_result": screening_result,
        "validation_report": {
            "mode": "validate",
            "passed": passed,
            "gates": [
                {"name": "valid_inputs", "passed": True, "detail": "screening completed"},
                {"name": "positive_net", "passed": passed, "detail": f"net_return={net_return}"},
            ],
            "screening_result": screening_result,
        },
    }


def test_build_score_returns_guarded_score_when_trade_count_is_sufficient():
    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=evidence(net_return=0.03, trade_count=25),
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
        window_start="2024-01-01",
        window_end="2024-04-29",
        window_days=120,
        symbol_count=8,
    )

    assert score["status"] == "scored"
    assert score["score"] == pytest.approx(0.03 / 120)
    assert score["score_basis"] == "net_return_per_day"
    assert score["raw_net_return"] == 0.03
    assert score["gross_return"] == 0.04
    assert score["funding_return"] == 0.002
    assert score["cost_return"] == 0.01
    assert score["trade_count"] == 25
    assert score["window_start"] == "2024-01-01"
    assert score["window_end"] == "2024-04-29"
    assert score["window_days"] == 120
    assert score["symbol_count"] == 8
    assert score["passed_validation"] is True
    assert score["failed_gates"] == []
    assert score["failure_message"] is None
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


def test_build_score_returns_runner_failed_when_v2_smoke_score_is_missing_with_enough_trades():
    malformed_evidence = evidence(trade_count=25)
    del malformed_evidence["validation_report"]["screening_result"]["smoke_score"]
    malformed_evidence["screening_result"].pop("smoke_score", None)

    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=malformed_evidence,
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
    )

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["raw_net_return"] is None
    assert score["funding_return"] is None
    assert score["trade_count"] == 25
    assert score["failure_source"] == "quant_strategies_error"
    assert "smoke_score.sum_weighted_trade_net_return" in score["failure_message"]


def test_build_score_fails_closed_when_validation_passed_is_not_bool():
    malformed_evidence = evidence(net_return=0.03, trade_count=25)
    malformed_evidence["validation_report"]["passed"] = "false"

    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=malformed_evidence,
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
    )

    assert score["status"] == "validation_failed"
    assert score["score"] == 0.03
    assert score["passed_validation"] is False


def test_build_score_returns_runner_failed_when_net_return_is_non_finite():
    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=evidence(net_return=float("nan"), trade_count=25),
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
    )

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["raw_net_return"] is None
    assert score["trade_count"] == 25


def test_classify_failure_source_maps_runner_stages_and_messages():
    assert classify_failure_source("signal_generation", "strategy execution failed") == "strategy_error"
    assert classify_failure_source("request_build", "entry fill is outside available bars") == "strategy_error"
    assert classify_failure_source("param_validation", "param validation failed") == "strategy_error"
    assert classify_failure_source("decision_generation", "decision generation failed") == "strategy_error"
    assert classify_failure_source("data_load", "strict data window failed") == "quant_data_error"
    assert classify_failure_source("strategy_import", "strategy import failed") == "strategy_error"
    assert classify_failure_source("config", "invalid TOML") == "config_error"
    assert classify_failure_source("engine_evaluation", "engine evaluation failed") == "quant_strategies_error"
    assert classify_failure_source("config_load", "failed to load config") == "config_error"
    assert classify_failure_source("data_readiness", "insufficient data") == "quant_data_error"
    assert (
        classify_failure_source(
            "data_readiness",
            "emitted signal has as_of_time before the first available row",
        )
        == "strategy_error"
    )
    assert (
        classify_failure_source("data_readiness", "unavailable as-of row for emitted signal")
        == "strategy_error"
    )
    assert classify_failure_source("data_readiness", "strict missing data for ETH-PERP") == "quant_data_error"
    assert (
        classify_failure_source(
            "data_readiness",
            "strict data window outside available dataset range",
        )
        == "quant_data_error"
    )
    assert classify_failure_source("strategy_import", "No module named 'pandas'") == "environment_error"
    assert classify_failure_source("engine_evaluation", "conda environment failed") == "environment_error"
    assert classify_failure_source("unexpected_stage", "unknown runner failure") == "quant_strategies_error"
    assert classify_failure_source(None, None) is None


def confirmation_config() -> ConfirmationScoringConfig:
    return ConfirmationScoringConfig(
        primary_metric="net_return_per_day",
        dispersion_weight=0.5,
        weak_window_floor=0.0,
        weak_window_penalty=0.001,
        min_trades_per_window=200,
        low_trade_penalty=0.001,
        min_symbol_count=4,
        symbol_concentration_penalty=0.00025,
    )


def window_score(
    window_id: str,
    score: float | None,
    *,
    raw_net_return: float | None = None,
    trade_count: int | None = 250,
    symbol_count: int | None = 5,
    status: str = "scored",
) -> dict[str, object]:
    return {
        "window_id": window_id,
        "window_start": "2025-01-01",
        "window_end": "2025-06-29",
        "window_days": 180,
        "score": score,
        "raw_net_return": raw_net_return if raw_net_return is not None else (score * 180 if score is not None else None),
        "trade_count": trade_count,
        "symbol_count": symbol_count,
        "status": status,
        "failed_gates": [],
        "failure_source": None,
    }


def test_build_candidate_score_rewards_recent_mean_and_records_components():
    payload = build_candidate_score(
        window_scores=[
            window_score("validation_2025_h1", 0.0010),
            window_score("validation_2025_h2", 0.0020),
            window_score("locked_recent_2026", 0.0030),
        ],
        config=confirmation_config(),
        commit="abc1234",
        description="candidate",
    )

    assert payload["status"] == "scored"
    assert payload["commit"] == "abc1234"
    assert payload["description"] == "candidate"
    assert payload["recent_mean_score"] == pytest.approx(0.0020)
    assert payload["recent_median_score"] == pytest.approx(0.0020)
    assert payload["worst_recent_score"] == pytest.approx(0.0010)
    assert payload["total_trade_count"] == 750
    assert payload["min_window_trade_count"] == 250
    assert payload["symbol_count"] == 5
    assert payload["passed_windows"] == ["validation_2025_h1", "validation_2025_h2", "locked_recent_2026"]
    assert payload["failed_windows"] == []
    assert payload["candidate_score"] < payload["recent_mean_score"]
    assert payload["penalties"]["dispersion"] > 0.0
    assert payload["penalties"]["weak_windows"] == 0.0
    assert payload["penalties"]["low_trades"] == 0.0
    assert payload["penalties"]["symbol_concentration"] == 0.0


def test_build_candidate_score_penalizes_weak_low_trade_and_narrow_universe():
    payload = build_candidate_score(
        window_scores=[
            window_score("validation_2025_h1", 0.0010, trade_count=250, symbol_count=3),
            window_score("validation_2025_h2", -0.0005, trade_count=100, symbol_count=3),
            window_score("locked_recent_2026", 0.0020, trade_count=250, symbol_count=3),
        ],
        config=confirmation_config(),
        commit="abc1234",
        description="candidate",
    )

    assert payload["status"] == "scored"
    assert payload["failed_windows"] == ["validation_2025_h2"]
    assert payload["min_window_trade_count"] == 100
    assert payload["symbol_count"] == 3
    assert payload["penalties"]["weak_windows"] == pytest.approx(0.001)
    assert payload["penalties"]["low_trades"] == pytest.approx(0.001)
    assert payload["penalties"]["symbol_concentration"] == pytest.approx(0.00025)


def test_build_candidate_score_invalidates_missing_numeric_window_score():
    payload = build_candidate_score(
        window_scores=[
            window_score("validation_2025_h1", 0.0010),
            window_score("validation_2025_h2", None, status="runner_failed"),
            window_score("locked_recent_2026", 0.0020),
        ],
        config=confirmation_config(),
        commit="abc1234",
        description="candidate",
    )

    assert payload["status"] == "confirmation_failed"
    assert payload["candidate_score"] is None
    assert payload["failed_windows"] == ["validation_2025_h2"]


def trade(symbol: str, side: str, decision_time: str, net: float, gross: float, funding: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "side": side,
        "decision_time": decision_time,
        "exit_time": decision_time,
        "gross_return": gross,
        "funding_return": funding,
        "cost_return": 0.0,
        "net_return": net,
    }


def test_build_trade_attribution_groups_trade_evidence():
    evidence_by_window = {
        "validation_2025_h1": {
            "schema_version": "quant_strategies.engine.evidence/v2",
            "screening_result": {
                "trades": [
                    trade("ETH-PERP", "short", "2025-01-02T08:01:00Z", 0.01, 0.009, 0.001),
                    trade("ETH-PERP", "long", "2025-01-02T12:01:00Z", -0.02, -0.019, -0.001),
                ]
            }
        },
        "locked_recent_2026": {
            "schema_version": "quant_strategies.engine.evidence/v2",
            "screening_result": {
                "trades": [
                    trade("ADA-PERP", "short", "2026-01-02T08:01:00Z", 0.03, 0.029, 0.001),
                ]
            }
        },
    }

    attribution = build_trade_attribution(evidence_by_window)

    assert attribution["total_trade_count"] == 3
    assert attribution["by_window"]["validation_2025_h1"]["trade_count"] == 2
    assert attribution["by_window"]["validation_2025_h1"]["net_return"] == pytest.approx(-0.01)
    assert attribution["by_symbol"]["ETH-PERP"]["trade_count"] == 2
    assert attribution["by_side"]["short"]["net_return"] == pytest.approx(0.04)
    assert attribution["by_decision_hour"]["08"]["trade_count"] == 2
    assert attribution["by_month"]["2025-01"]["net_return"] == pytest.approx(-0.01)
    assert attribution["by_symbol_side"]["ETH-PERP|long"]["net_return"] == pytest.approx(-0.02)
    assert attribution["by_window_side"]["locked_recent_2026|short"]["net_return"] == pytest.approx(0.03)
    assert attribution["by_window_hour"]["validation_2025_h1|12"]["net_return"] == pytest.approx(-0.02)
