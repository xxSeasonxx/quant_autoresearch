from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.research_handoff_rank import build_handoff_ranking


BASE_PARAMS = {
    "funding_lookback_events": 5,
    "return_lookback_minutes": 120,
    "decision_interval_minutes": 240,
    "top_n": 5,
    "selection_score": "funding",
    "min_abs_funding_bps": 1.0,
    "min_abs_return_bps": 5.0,
    "min_same_sign_funding_events": 3,
    "min_latest_abs_funding_bps": 0.0,
    "min_idiosyncratic_return_bps": 2.5,
    "min_long_idiosyncratic_return_bps": 0.0,
    "min_tail_count": 1,
    "balance_sides": False,
    "include_positive_funding_shorts": True,
    "include_negative_funding_longs": True,
    "trailing_stop_bps": 0.0,
    "take_profit_bps": 0.0,
    "stop_loss_bps": 0.0,
    "hold_bars": 600,
}


def write_attempt(
    campaign: Path,
    attempt: int,
    params: dict[str, object],
    *,
    score: float | None = 0.010,
    trade_count: int = 250,
    window_id: str = "recent",
    status: str = "scored",
    strategy_source: str = "def generate_signals():\n    return []\n",
) -> Path:
    attempt_dir = campaign / f"2026-05-25T000{attempt:03d}Z-demo"
    attempt_dir.mkdir(parents=True)
    generated_dir = campaign / ".generated"
    generated_dir.mkdir(exist_ok=True)
    config_path = generated_dir / f"attempt_{attempt:04d}_{window_id}.toml"
    config_path.write_text(_toml(params))
    (attempt_dir / "strategy_snapshot.py").write_text(strategy_source)
    (attempt_dir / "attempt_metadata.json").write_text(
        json.dumps(
            {
                "attempt": attempt,
                "generated_config": str(config_path),
                "window_id": window_id,
                "description": f"attempt {attempt}",
            }
        )
        + "\n"
    )
    (attempt_dir / "score.json").write_text(
        json.dumps(
            {
                "status": status,
                "score": score,
                "trade_count": trade_count,
                "min_score_trades": 200,
                "window_id": window_id,
            },
            allow_nan=True,
        )
        + "\n"
    )
    return attempt_dir


def write_promotion(
    campaign: Path,
    attempt: int,
    *,
    promotion_score: float = 0.020,
    cost_stress_score: float | None = None,
    source_window_scores: dict[str, float] | None = None,
) -> Path:
    promotion_dir = campaign / f"promotion_{attempt:04d}_demo"
    cost_dir = promotion_dir / "cost_stress" / "realistic_costs" / "run"
    cost_dir.mkdir(parents=True)
    if cost_stress_score is not None:
        (cost_dir / "score.json").write_text(
            json.dumps({"status": "scored", "score": cost_stress_score, "trade_count": 250}) + "\n"
        )
    source_result_dirs: dict[str, str] = {}
    if source_window_scores is not None:
        for window_id, score in source_window_scores.items():
            result_dir = promotion_dir / "windows" / window_id / "run"
            result_dir.mkdir(parents=True)
            (result_dir / "score.json").write_text(
                json.dumps(
                    {
                        "status": "scored",
                        "score": score,
                        "trade_count": 250,
                        "min_score_trades": 200,
                        "window_id": window_id,
                    }
                )
                + "\n"
            )
            source_result_dirs[window_id] = str(result_dir.relative_to(promotion_dir))
    summary = {
        "attempt": attempt,
        "promotion_score": promotion_score,
        "recent_window_ids": list(source_window_scores) if source_window_scores is not None else ["recent"],
        "cost_stress_result_dir": str(cost_dir),
    }
    if source_result_dirs:
        summary["source_result_dirs"] = source_result_dirs
    (promotion_dir / "promotion_summary.json").write_text(json.dumps(summary) + "\n")
    return promotion_dir


def _toml(params: dict[str, object]) -> str:
    lines = ['strategy_path = "strategy.py"', 'strategy_id = "demo"', "", "[params]"]
    for key, value in params.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, str):
            rendered = json.dumps(value)
        else:
            rendered = str(value)
        lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


def params(**overrides: object) -> dict[str, object]:
    payload = dict(BASE_PARAMS)
    payload.update(overrides)
    return payload


def test_selects_exactly_three_families(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=0.030)
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020)
    write_attempt(campaign, 3, params(include_positive_funding_shorts=False), score=0.010)
    write_attempt(campaign, 4, params(min_abs_funding_bps=2.0), score=0.005)

    ranking = build_handoff_ranking(campaign)

    assert [family["family"] for family in ranking["selected_families"]] == [
        "trailing_exit",
        "price_threshold_exit",
        "directional_subset",
    ]
    assert len(ranking["selected_families"]) == 3


def test_fewer_than_three_families_raises(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=0.030)
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020)

    with pytest.raises(ValueError, match="expected at least three logic families"):
        build_handoff_ranking(campaign)


def test_nan_non_finite_score_penalty(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=float("nan"))
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020)
    write_attempt(campaign, 3, params(include_positive_funding_shorts=False), score=0.010)

    ranking = build_handoff_ranking(campaign)
    trailing = _family_variant(ranking, "trailing_exit")

    assert trailing["penalties"]["non_finite_scores"] > 0.0
    assert trailing["blended_score"] < trailing["base_score"]


def test_low_trade_penalty(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=0.030, trade_count=20)
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020)
    write_attempt(campaign, 3, params(include_positive_funding_shorts=False), score=0.010)

    ranking = build_handoff_ranking(campaign)
    trailing = _family_variant(ranking, "trailing_exit")

    assert trailing["penalties"]["low_trades"] > 0.0
    assert trailing["min_trade_count"] == 20


def test_top_five_cap_within_family(tmp_path: Path):
    campaign = tmp_path / "campaign"
    for attempt in range(1, 8):
        write_attempt(
            campaign,
            attempt,
            params(
                min_abs_funding_bps=2.0 + attempt,
                hold_bars=600 + attempt,
            ),
            score=0.010 + attempt / 1000,
        )
    write_attempt(campaign, 20, params(take_profit_bps=150.0), score=0.020)
    write_attempt(campaign, 21, params(include_positive_funding_shorts=False), score=0.019)

    ranking = build_handoff_ranking(campaign)

    assert _selected_family(ranking, "entry_filter")["variant_count"] == 5
    assert len([variant for variant in ranking["variants"] if variant["family"] == "entry_filter"]) == 5


def test_promotion_matching_by_attempt(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=0.001)
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020)
    write_attempt(campaign, 3, params(include_positive_funding_shorts=False), score=0.010)
    promotion_dir = write_promotion(campaign, 1, promotion_score=0.050)

    ranking = build_handoff_ranking(campaign)
    trailing = _family_variant(ranking, "trailing_exit")

    assert trailing["promotion_score"] == pytest.approx(0.050)
    assert trailing["promotion_dir"] == str(promotion_dir)
    assert trailing["promotion_summary"]["attempt"] == 1


def test_optional_cost_stress_penalty(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=0.030)
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020)
    write_attempt(campaign, 3, params(include_positive_funding_shorts=False), score=0.010)
    write_promotion(campaign, 1, promotion_score=0.030, cost_stress_score=0.010)

    ranking = build_handoff_ranking(campaign)
    trailing = _family_variant(ranking, "trailing_exit")

    assert trailing["cost_stress_score"] == pytest.approx(0.010)
    assert trailing["penalties"]["cost_stress"] == pytest.approx(0.020)


def test_inferred_baseline_comparison_not_hard_coded_values(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(min_abs_funding_bps=3.0), score=0.005)
    write_attempt(campaign, 2, params(min_abs_funding_bps=3.0, trailing_stop_bps=50.0), score=0.030)
    write_attempt(campaign, 3, params(min_abs_funding_bps=3.0, take_profit_bps=150.0), score=0.020)
    write_attempt(
        campaign,
        4,
        params(min_abs_funding_bps=3.0, include_positive_funding_shorts=False),
        score=0.010,
    )

    ranking = build_handoff_ranking(campaign)

    assert ranking["baseline_params"]["min_abs_funding_bps"] == 3.0
    assert "entry_filter" not in {family["family"] for family in ranking["selected_families"]}


def test_exit_and_directional_families_require_baseline_difference(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(
        campaign,
        1,
        params(trailing_stop_bps=50.0, include_positive_funding_shorts=False),
        score=0.001,
    )
    write_attempt(
        campaign,
        2,
        params(
            trailing_stop_bps=50.0,
            include_positive_funding_shorts=False,
            min_abs_funding_bps=2.0,
        ),
        score=0.030,
    )
    write_attempt(
        campaign,
        3,
        params(trailing_stop_bps=75.0, include_positive_funding_shorts=False),
        score=0.020,
    )
    write_attempt(
        campaign,
        4,
        params(trailing_stop_bps=50.0, include_positive_funding_shorts=True),
        score=0.010,
    )

    ranking = build_handoff_ranking(campaign)
    variant = _variant_by_attempt(ranking, 2)

    assert ranking["baseline_params"]["trailing_stop_bps"] == 50.0
    assert ranking["baseline_params"]["include_positive_funding_shorts"] is False
    assert variant["family"] == "entry_filter"


def test_promotion_source_result_dirs_count_as_recent_window_evidence(tmp_path: Path):
    campaign = tmp_path / "campaign"
    write_attempt(campaign, 1, params(trailing_stop_bps=50.0), score=0.001, window_id="seed")
    write_attempt(campaign, 2, params(take_profit_bps=150.0), score=0.020, window_id="seed")
    write_attempt(
        campaign,
        3,
        params(include_positive_funding_shorts=False),
        score=0.010,
        window_id="seed",
    )
    promotion_dir = write_promotion(
        campaign,
        1,
        promotion_score=0.050,
        source_window_scores={"recent_a": 0.040, "recent_b": 0.030},
    )

    ranking = build_handoff_ranking(campaign)
    trailing = _family_variant(ranking, "trailing_exit")

    assert trailing["promotion_dir"] == str(promotion_dir)
    assert trailing["missing_recent_windows"] == []
    assert {score["window_id"] for score in trailing["recent_window_scores"]} >= {
        "recent_a",
        "recent_b",
    }
    assert {
        score["source"]
        for score in trailing["recent_window_scores"]
        if score["window_id"] in {"recent_a", "recent_b"}
    } == {"promotion_source_result_dir"}
    assert len(trailing["evidence_result_dirs"]) == 2


def _selected_family(ranking: dict[str, object], family: str) -> dict[str, object]:
    families = ranking["selected_families"]
    assert isinstance(families, list)
    for item in families:
        if item["family"] == family:
            return item
    raise AssertionError(f"missing family: {family}")


def _family_variant(ranking: dict[str, object], family: str) -> dict[str, object]:
    variants = ranking["variants"]
    assert isinstance(variants, list)
    for item in variants:
        if item["family"] == family:
            return item
    raise AssertionError(f"missing variant family: {family}")


def _variant_by_attempt(ranking: dict[str, object], attempt_id: int) -> dict[str, object]:
    variants = ranking["variants"]
    assert isinstance(variants, list)
    for item in variants:
        if item["attempt_ids"] == [attempt_id]:
            return item
    raise AssertionError(f"missing variant for attempt: {attempt_id}")
