from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

from experiment_config import ConfirmationScoringConfig, ExperimentConfig, PromotionConfig
from scoring import build_candidate_score


def scored_for_promotion(score: dict[str, Any]) -> bool:
    return score.get("status") == "scored" and _as_float_or_none(score.get("score")) is not None


def select_rotating_probe_window_id(config: PromotionConfig, state: Any) -> str:
    if not config.rotating_probe_window_ids:
        raise ValueError("promotion rotating probe windows are empty")
    index = int(getattr(state, "rotating_probe_index", 0))
    return config.rotating_probe_window_ids[index % len(config.rotating_probe_window_ids)]


def build_cost_stress_config(config: ExperimentConfig) -> ExperimentConfig:
    return replace(
        config,
        cost_model={
            **config.cost_model,
            "fee_bps_per_side": config.promotion.cost_fee_bps_per_side,
            "slippage_bps_per_side": config.promotion.cost_slippage_bps_per_side,
        },
    )


def build_promotion_score(
    *,
    recent_window_scores: list[dict[str, Any]],
    cost_stress_score: dict[str, Any],
    rotating_probe_score: dict[str, Any],
    confirmation_config: ConfirmationScoringConfig,
    promotion_config: PromotionConfig,
    commit: str | None,
    description: str,
    rotating_probe_window_id: str,
) -> dict[str, Any]:
    recent_score = build_candidate_score(
        window_scores=recent_window_scores,
        config=confirmation_config,
        commit=commit,
        description=description,
    )
    promotion_score = _as_float_or_none(recent_score.get("candidate_score"))
    recent_mean_score = _as_float_or_none(recent_score.get("recent_mean_score"))
    cost_value = _as_float_or_none(cost_stress_score.get("score"))
    probe_value = _as_float_or_none(rotating_probe_score.get("score"))
    failed_reasons: list[str] = []

    if recent_score.get("status") != "scored" or promotion_score is None:
        failed_reasons.append("recent_core_failed")
    if _failed_recent_core(recent_window_scores):
        failed_reasons.append("recent_core_weak_window")

    cost_stress_ratio = _cost_stress_ratio(cost_value, recent_mean_score)
    if cost_value is None:
        failed_reasons.append("cost_stress_failed")
    elif cost_stress_ratio is None:
        failed_reasons.append("cost_stress_ratio_unavailable")
    elif cost_stress_ratio < promotion_config.cost_stress_min_ratio:
        failed_reasons.append("cost_stress_ratio_below_minimum")

    if probe_value is None:
        failed_reasons.append("rotating_probe_failed")
    elif probe_value <= promotion_config.deep_probe_floor:
        failed_reasons.append("rotating_probe_below_floor")

    return {
        "status": "scored" if promotion_score is not None else "promotion_failed",
        "promotion_score": promotion_score,
        "metric": "promotion_recent_net_return_per_day",
        "commit": commit,
        "description": _single_line(description),
        "eligible_for_promotion": not failed_reasons,
        "failed_reasons": failed_reasons,
        "recent_candidate_score": recent_score,
        "recent_mean_score": recent_score.get("recent_mean_score"),
        "recent_median_score": recent_score.get("recent_median_score"),
        "worst_recent_score": recent_score.get("worst_recent_score"),
        "score_dispersion": recent_score.get("score_dispersion"),
        "near_equal_score_tolerance": promotion_config.near_equal_score_tolerance,
        "cost_stress_id": promotion_config.cost_stress_id,
        "cost_stress_score": cost_value,
        "cost_stress_ratio": cost_stress_ratio,
        "rotating_probe_window_id": rotating_probe_window_id,
        "rotating_probe_score": probe_value,
        "recent_window_scores": recent_window_scores,
        "cost_stress_window_score": cost_stress_score,
        "rotating_probe_window_score": rotating_probe_score,
        "notes": "Promotion screening only. Not final validation.",
    }


def decision_for_promotion(
    promotion_score: dict[str, Any],
    *,
    state: Any,
    simplification: bool,
) -> str:
    if promotion_score.get("eligible_for_promotion") is not True:
        return "reject"
    value = _as_float_or_none(promotion_score.get("promotion_score"))
    if value is None:
        return "reject"
    current = _as_float_or_none(getattr(state, "best_promoted_score", None))
    if current is None or value > current:
        return "promote"
    tolerance = _as_float_or_none(promotion_score.get("near_equal_score_tolerance")) or 0.0
    if simplification and value >= current - tolerance:
        return "promote"
    return "reject"


def _failed_recent_core(window_scores: list[dict[str, Any]]) -> bool:
    for score in window_scores:
        value = _as_float_or_none(score.get("score"))
        if score.get("status") != "scored" or value is None or value <= 0.0:
            return True
    return False


def _cost_stress_ratio(cost_value: float | None, recent_mean_score: float | None) -> float | None:
    if cost_value is None or recent_mean_score is None or recent_mean_score <= 0.0:
        return None
    return cost_value / recent_mean_score


def _as_float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _single_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")
