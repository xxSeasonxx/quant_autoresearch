from __future__ import annotations

from dataclasses import replace

import pytest

from experiment_config import ConfirmationScoringConfig, PromotionConfig
from promotion import (
    build_cost_stress_config,
    build_promotion_score,
    decision_for_promotion,
    scored_for_promotion,
    select_rotating_probe_window_id,
)
from runner import SessionState


def confirmation_config() -> ConfirmationScoringConfig:
    return ConfirmationScoringConfig(
        primary_metric="net_return_per_day",
        dispersion_weight=0.0,
        weak_window_floor=0.0,
        weak_window_penalty=0.0,
        min_trades_per_window=2,
        low_trade_penalty=0.0,
        min_symbol_count=1,
        symbol_concentration_penalty=0.0,
    )


def promotion_config() -> PromotionConfig:
    return PromotionConfig(
        enabled=True,
        screen_on_scored_explore=True,
        recent_window_ids=("primary", "holdout"),
        rotating_probe_window_ids=("stress_a", "stress_b"),
        deep_probe_floor=-0.001,
        near_equal_score_tolerance=0.0001,
        cost_stress_id="realistic_costs",
        cost_fee_bps_per_side=0.5,
        cost_slippage_bps_per_side=0.5,
        cost_stress_min_ratio=0.5,
    )


def window_score(window_id: str, score: float | None, *, status: str = "scored") -> dict[str, object]:
    return {
        "window_id": window_id,
        "score": score,
        "raw_net_return": score * 120 if score is not None else None,
        "trade_count": 3,
        "symbol_count": 2,
        "status": status,
        "failed_gates": [],
        "failure_source": None,
    }


def state(**overrides: object) -> SessionState:
    base = SessionState(
        max_attempts=3,
        attempts_used=0,
        best_score=None,
        best_commit=None,
        status="active",
        best_primary_window_score=None,
        best_confirmed_candidate_score=None,
        best_confirmed_commit=None,
        best_promoted_score=None,
        best_promoted_commit=None,
        rotating_probe_index=0,
        last_promotion_decision=None,
    )
    return replace(base, **overrides)


def test_scored_for_promotion_accepts_only_scored_numeric_scores():
    assert scored_for_promotion(window_score("primary", 0.01)) is True
    assert scored_for_promotion(window_score("primary", None, status="insufficient_sample")) is False
    assert scored_for_promotion(window_score("primary", 0.01, status="validation_failed")) is False


def test_select_rotating_probe_window_id_uses_session_index_modulo_probe_count():
    assert select_rotating_probe_window_id(promotion_config(), state(rotating_probe_index=0)) == "stress_a"
    assert select_rotating_probe_window_id(promotion_config(), state(rotating_probe_index=1)) == "stress_b"
    assert select_rotating_probe_window_id(promotion_config(), state(rotating_probe_index=2)) == "stress_a"


def test_build_cost_stress_config_overrides_only_cost_model(tmp_path):
    from experiment_config import load_experiment_config
    from tests.test_experiment_config import VALID_TOML, write_config

    text = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""
    config = load_experiment_config(write_config(tmp_path, text))

    stressed = build_cost_stress_config(config)

    assert stressed.cost_model["fee_bps_per_side"] == 0.5
    assert stressed.cost_model["slippage_bps_per_side"] == 0.5
    assert config.cost_model["fee_bps_per_side"] == 1.0
    assert config.cost_model["slippage_bps_per_side"] == 2.0
    assert stressed.strategy_id == config.strategy_id


def test_build_promotion_score_records_recent_cost_and_probe_evidence():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is True
    assert payload["promotion_score"] == pytest.approx(0.0019)
    assert payload["recent_mean_score"] == pytest.approx(0.0019)
    assert payload["cost_stress_ratio"] == pytest.approx(0.0012 / 0.0019)
    assert payload["rotating_probe_window_id"] == "stress_a"
    assert payload["failed_reasons"] == []


def test_build_promotion_score_rejects_cost_stress_edge_destruction():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0002),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is False
    assert "cost_stress_ratio_below_minimum" in payload["failed_reasons"]


def test_build_promotion_score_rejects_validation_failed_cost_stress():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012, status="validation_failed"),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is False
    assert "cost_stress_failed" in payload["failed_reasons"]
    assert payload["cost_stress_score"] is None


def test_build_promotion_score_rejects_deep_negative_probe():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", -0.0020),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is False
    assert "rotating_probe_below_floor" in payload["failed_reasons"]


def test_build_promotion_score_rejects_validation_failed_rotating_probe():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", 0.0001, status="validation_failed"),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is False
    assert "rotating_probe_failed" in payload["failed_reasons"]
    assert payload["rotating_probe_score"] is None


def test_decision_for_promotion_respects_best_score_and_simplification_tolerance():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert decision_for_promotion(payload, state=state(), simplification=False) == "promote"
    current = state(best_promoted_score=payload["promotion_score"] + 0.00005)
    assert decision_for_promotion(payload, state=current, simplification=False) == "reject"
    assert decision_for_promotion(payload, state=current, simplification=True) == "promote"
