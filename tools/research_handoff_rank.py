from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


METHOD_VERSION = "research_handoff_rank_v1"

FAMILY_PRIORITY = {
    "trailing_exit": 0,
    "price_threshold_exit": 1,
    "directional_subset": 2,
    "entry_filter": 3,
    "lookback_or_cadence": 4,
    "selection_or_breadth": 5,
    "time_only_exit": 6,
}
ENTRY_FILTER_KEYS = {
    "min_abs_funding_bps",
    "min_abs_return_bps",
    "min_same_sign_funding_events",
    "min_latest_abs_funding_bps",
    "min_idiosyncratic_return_bps",
    "min_long_idiosyncratic_return_bps",
    "min_tail_count",
    "balance_sides",
}
LOOKBACK_OR_CADENCE_KEYS = {
    "funding_lookback_events",
    "return_lookback_minutes",
    "decision_interval_minutes",
}
SELECTION_OR_BREADTH_KEYS = {"top_n", "selection_score"}
SIDE_INCLUDE_KEYS = {
    "include_positive_funding_shorts",
    "include_negative_funding_longs",
}

NON_FINITE_SCORE_PENALTY = 0.01
MISSING_RECENT_WINDOW_PENALTY = 0.002
LOW_TRADE_PENALTY = 0.005
COST_STRESS_GAP_WEIGHT = 1.0
DEFAULT_MIN_TRADES = 200


@dataclass(frozen=True)
class Attempt:
    attempt_id: int
    attempt_dir: Path
    metadata: dict[str, Any]
    score: dict[str, Any]
    params: dict[str, Any]
    strategy_source_sha: str

    @property
    def window_id(self) -> str:
        value = self.score.get("window_id") or self.metadata.get("window_id")
        return str(value) if value is not None else "unknown"


@dataclass
class Promotion:
    attempt_id: int
    promotion_dir: Path
    summary: dict[str, Any]
    promotion_score: float | None
    cost_stress_score: float | None


@dataclass
class Variant:
    variant_id: str
    params: dict[str, Any]
    strategy_source_sha: str
    attempts: list[Attempt] = field(default_factory=list)
    promotions: list[Promotion] = field(default_factory=list)

    @property
    def earliest_attempt_id(self) -> int:
        return min(attempt.attempt_id for attempt in self.attempts)


def build_handoff_ranking(campaign_dir: str | Path) -> dict[str, Any]:
    campaign_path = Path(campaign_dir).expanduser().resolve()
    attempts = _load_attempts(campaign_path)
    variants = _group_variants(attempts)
    promotions = _load_promotions(campaign_path)
    _attach_promotions(variants, promotions)

    baseline_params = _infer_baseline_params(list(variants.values()))
    expected_recent_windows = _expected_recent_windows(variants, promotions)
    ranked_variants = [
        _score_variant(variant, baseline_params, expected_recent_windows)
        for variant in variants.values()
    ]
    ranked_variants.sort(key=_variant_sort_key)

    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for variant in ranked_variants:
        families[variant["family"]].append(variant)

    selected_family_names = _select_family_names(families)
    selected_variants: list[dict[str, Any]] = []
    selected_families: list[dict[str, Any]] = []
    for family in selected_family_names:
        family_variants = families[family][:5]
        selected_families.append(
            {
                "family": family,
                "best_variant_id": family_variants[0]["variant_id"],
                "variant_count": len(family_variants),
            }
        )
        selected_variants.extend(family_variants)

    return {
        "method_version": METHOD_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "campaign_dir": str(campaign_path),
        "baseline_params": baseline_params,
        "selected_families": selected_families,
        "variants": selected_variants,
    }


def _load_attempts(campaign_dir: Path) -> list[Attempt]:
    if not campaign_dir.exists():
        raise ValueError(f"campaign_dir does not exist: {campaign_dir}")

    attempts: list[Attempt] = []
    for attempt_dir in sorted(path for path in campaign_dir.iterdir() if path.is_dir()):
        if attempt_dir.name.startswith("promotion_"):
            continue
        metadata_path = attempt_dir / "attempt_metadata.json"
        score_path = attempt_dir / "score.json"
        if not metadata_path.exists() or not score_path.exists():
            continue

        metadata = _read_json(metadata_path)
        score = _read_json(score_path)
        params = _read_params(_resolve_generated_config(metadata, campaign_dir))
        strategy_source_sha = _strategy_source_sha(attempt_dir)
        attempt_id = _attempt_id(metadata, attempt_dir.name)
        attempts.append(
            Attempt(
                attempt_id=attempt_id,
                attempt_dir=attempt_dir,
                metadata=metadata,
                score=score,
                params=params,
                strategy_source_sha=strategy_source_sha,
            )
        )

    if not attempts:
        raise ValueError(f"no scored attempt directories found in {campaign_dir}")
    return sorted(attempts, key=lambda attempt: (attempt.attempt_id, str(attempt.attempt_dir)))


def _read_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _resolve_generated_config(metadata: dict[str, Any], campaign_dir: Path) -> Path:
    raw_path = metadata.get("generated_config")
    if raw_path is None:
        raise ValueError(f"attempt metadata missing generated_config under {campaign_dir}")
    config_path = Path(str(raw_path)).expanduser()
    if config_path.is_absolute():
        return config_path
    return (campaign_dir / config_path).resolve()


def _read_params(config_path: Path) -> dict[str, Any]:
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    params = config.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"expected [params] table in {config_path}")
    return {str(key): _jsonable(value) for key, value in params.items()}


def _strategy_source_sha(attempt_dir: Path) -> str:
    snapshot_path = attempt_dir / "strategy_snapshot.py"
    if snapshot_path.exists():
        return _file_sha256(snapshot_path)
    strategy_path = Path("strategy.py")
    if strategy_path.exists():
        return _file_sha256(strategy_path)
    return "missing"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attempt_id(metadata: dict[str, Any], fallback: str) -> int:
    raw_attempt = metadata.get("attempt")
    if isinstance(raw_attempt, int) and not isinstance(raw_attempt, bool):
        return raw_attempt
    digits = "".join(character for character in fallback if character.isdigit())
    return int(digits) if digits else 0


def _group_variants(attempts: list[Attempt]) -> dict[str, Variant]:
    variants: dict[str, Variant] = {}
    for attempt in attempts:
        canonical = _canonical_json(
            {
                "params": attempt.params,
                "strategy_source_sha": attempt.strategy_source_sha,
            }
        )
        variant_id = hashlib.sha256(canonical.encode()).hexdigest()
        if variant_id not in variants:
            variants[variant_id] = Variant(
                variant_id=variant_id,
                params=attempt.params,
                strategy_source_sha=attempt.strategy_source_sha,
            )
        variants[variant_id].attempts.append(attempt)
    return variants


def _load_promotions(campaign_dir: Path) -> dict[int, Promotion]:
    promotions: dict[int, Promotion] = {}
    for summary_path in sorted(campaign_dir.glob("promotion_*/promotion_summary.json")):
        summary = _read_json(summary_path)
        attempt_id = _attempt_id(summary, summary_path.parent.name)
        promotion_score = _finite_float(summary.get("promotion_score"))
        cost_stress_score = _score_from_referenced_result(summary.get("cost_stress_result_dir"))
        promotion = Promotion(
            attempt_id=attempt_id,
            promotion_dir=summary_path.parent,
            summary=summary,
            promotion_score=promotion_score,
            cost_stress_score=cost_stress_score,
        )
        existing = promotions.get(attempt_id)
        if existing is None or _promotion_sort_key(promotion) < _promotion_sort_key(existing):
            promotions[attempt_id] = promotion
    return promotions


def _score_from_referenced_result(raw_path: object) -> float | None:
    if raw_path is None:
        return None
    result_path = Path(str(raw_path)).expanduser()
    if result_path.is_file():
        score_path = result_path
    else:
        direct_score = result_path / "score.json"
        if direct_score.exists():
            score_path = direct_score
        else:
            matches = sorted(result_path.glob("**/score.json"))
            if not matches:
                return None
            score_path = matches[0]
    try:
        score = _read_json(score_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return _finite_float(score.get("score"))


def _promotion_sort_key(promotion: Promotion) -> tuple[float, str]:
    score = promotion.promotion_score if promotion.promotion_score is not None else -math.inf
    return (-score, str(promotion.promotion_dir))


def _attach_promotions(variants: dict[str, Variant], promotions: dict[int, Promotion]) -> None:
    by_attempt_id: dict[int, Variant] = {}
    for variant in variants.values():
        for attempt in variant.attempts:
            by_attempt_id[attempt.attempt_id] = variant
    for attempt_id, promotion in promotions.items():
        variant = by_attempt_id.get(attempt_id)
        if variant is not None:
            variant.promotions.append(promotion)


def _infer_baseline_params(variants: list[Variant]) -> dict[str, Any]:
    values_by_key: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for variant in variants:
        for key, value in variant.params.items():
            canonical = _canonical_json(value)
            record = values_by_key[key].setdefault(
                canonical,
                {
                    "value": value,
                    "count": 0,
                    "earliest_attempt_id": variant.earliest_attempt_id,
                },
            )
            record["count"] += 1
            record["earliest_attempt_id"] = min(
                record["earliest_attempt_id"],
                variant.earliest_attempt_id,
            )

    baseline: dict[str, Any] = {}
    for key in sorted(values_by_key):
        records = values_by_key[key].values()
        selected = min(
            records,
            key=lambda record: (-record["count"], record["earliest_attempt_id"], _canonical_json(record["value"])),
        )
        baseline[key] = selected["value"]
    return baseline


def _expected_recent_windows(
    variants: dict[str, Variant],
    promotions: dict[int, Promotion],
) -> set[str]:
    promoted_recent_windows: set[str] = set()
    for promotion in promotions.values():
        recent_window_ids = promotion.summary.get("recent_window_ids", [])
        if isinstance(recent_window_ids, list):
            promoted_recent_windows.update(str(window_id) for window_id in recent_window_ids)
    if promoted_recent_windows:
        return promoted_recent_windows

    observed = {
        attempt.window_id
        for variant in variants.values()
        for attempt in variant.attempts
        if attempt.window_id != "unknown"
    }
    return observed


def _score_variant(
    variant: Variant,
    baseline_params: dict[str, Any],
    expected_recent_windows: set[str],
) -> dict[str, Any]:
    best_promotion = _best_promotion(variant.promotions)
    finite_recent_scores = [
        score
        for score in (_finite_float(attempt.score.get("score")) for attempt in variant.attempts)
        if score is not None
    ]
    promotion_score = best_promotion.promotion_score if best_promotion is not None else None
    base_score = promotion_score
    if base_score is None:
        base_score = statistics.fmean(finite_recent_scores) if finite_recent_scores else 0.0

    recent_score_stdev = (
        statistics.pstdev(finite_recent_scores) if len(finite_recent_scores) >= 2 else 0.0
    )
    non_finite_score_count = len(variant.attempts) - len(finite_recent_scores)
    observed_recent_windows = {attempt.window_id for attempt in variant.attempts}
    missing_recent_windows = sorted(expected_recent_windows - observed_recent_windows)
    min_trade_count = _min_trade_count(variant)
    required_min_trades = _required_min_trades(variant)
    low_trade_ratio = 0.0
    if min_trade_count is None:
        low_trade_ratio = 1.0
    elif min_trade_count < required_min_trades:
        low_trade_ratio = (required_min_trades - min_trade_count) / required_min_trades

    cost_stress_score = best_promotion.cost_stress_score if best_promotion is not None else None
    cost_stress_gap = 0.0
    if cost_stress_score is not None and cost_stress_score < base_score:
        cost_stress_gap = base_score - cost_stress_score

    penalties = {
        "non_finite_scores": non_finite_score_count * NON_FINITE_SCORE_PENALTY,
        "missing_recent_windows": len(missing_recent_windows) * MISSING_RECENT_WINDOW_PENALTY,
        "low_trades": low_trade_ratio * LOW_TRADE_PENALTY,
        "cost_stress": cost_stress_gap * COST_STRESS_GAP_WEIGHT,
    }
    blended_score = base_score - 0.50 * recent_score_stdev - sum(penalties.values())
    family = _classify_family(variant.params, baseline_params)

    payload = {
        "variant_id": variant.variant_id,
        "family": family,
        "params": variant.params,
        "strategy_source_sha": variant.strategy_source_sha,
        "attempt_ids": [attempt.attempt_id for attempt in sorted(variant.attempts, key=lambda item: item.attempt_id)],
        "attempt_dirs": [str(attempt.attempt_dir) for attempt in sorted(variant.attempts, key=lambda item: item.attempt_id)],
        "recent_window_scores": [
            {
                "attempt_id": attempt.attempt_id,
                "window_id": attempt.window_id,
                "score": _finite_float(attempt.score.get("score")),
                "status": attempt.score.get("status"),
                "trade_count": _int_or_none(attempt.score.get("trade_count")),
            }
            for attempt in sorted(variant.attempts, key=lambda item: (item.window_id, item.attempt_id))
        ],
        "missing_recent_windows": missing_recent_windows,
        "base_score": base_score,
        "promotion_score": promotion_score,
        "recent_window_score_stdev": recent_score_stdev,
        "trade_count": sum(
            count
            for count in (_int_or_none(attempt.score.get("trade_count")) for attempt in variant.attempts)
            if count is not None
        ),
        "min_trade_count": min_trade_count,
        "required_min_trades": required_min_trades,
        "penalties": penalties,
        "blended_score": blended_score,
        "promotion_dir": str(best_promotion.promotion_dir) if best_promotion is not None else None,
        "promotion_summary": best_promotion.summary if best_promotion is not None else None,
        "cost_stress_score": cost_stress_score,
    }
    return _jsonable(payload)


def _best_promotion(promotions: list[Promotion]) -> Promotion | None:
    if not promotions:
        return None
    return min(promotions, key=_promotion_sort_key)


def _min_trade_count(variant: Variant) -> int | None:
    trade_counts = [
        trade_count
        for trade_count in (_int_or_none(attempt.score.get("trade_count")) for attempt in variant.attempts)
        if trade_count is not None
    ]
    return min(trade_counts) if trade_counts else None


def _required_min_trades(variant: Variant) -> int:
    requirements = [
        min_trades
        for min_trades in (_int_or_none(attempt.score.get("min_score_trades")) for attempt in variant.attempts)
        if min_trades is not None and min_trades > 0
    ]
    return max(requirements) if requirements else DEFAULT_MIN_TRADES


def _classify_family(params: dict[str, Any], baseline_params: dict[str, Any]) -> str:
    if _positive_param(params, baseline_params, "trailing_stop_bps"):
        return "trailing_exit"
    if _positive_param(params, baseline_params, "take_profit_bps") or _positive_param(
        params,
        baseline_params,
        "stop_loss_bps",
    ):
        return "price_threshold_exit"
    if any(key in baseline_params and params.get(key) is False for key in SIDE_INCLUDE_KEYS):
        return "directional_subset"
    if _any_baseline_difference(params, baseline_params, ENTRY_FILTER_KEYS):
        return "entry_filter"
    if _any_baseline_difference(params, baseline_params, LOOKBACK_OR_CADENCE_KEYS):
        return "lookback_or_cadence"
    if _any_baseline_difference(params, baseline_params, SELECTION_OR_BREADTH_KEYS):
        return "selection_or_breadth"
    return "time_only_exit"


def _positive_param(params: dict[str, Any], baseline_params: dict[str, Any], key: str) -> bool:
    if key not in baseline_params or key not in params:
        return False
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(float(value)) and float(value) > 0.0


def _any_baseline_difference(
    params: dict[str, Any],
    baseline_params: dict[str, Any],
    keys: set[str],
) -> bool:
    for key in keys:
        if key in baseline_params and key in params and params[key] != baseline_params[key]:
            return True
    return False


def _variant_sort_key(variant: dict[str, Any]) -> tuple[float, float, float, int, int, str]:
    promotion_score = variant.get("promotion_score")
    return (
        -float(variant["blended_score"]),
        -(float(promotion_score) if promotion_score is not None else -math.inf),
        float(variant["recent_window_score_stdev"]),
        -int(variant["trade_count"]),
        FAMILY_PRIORITY[str(variant["family"])],
        str(variant["variant_id"]),
    )


def _select_family_names(families: dict[str, list[dict[str, Any]]]) -> list[str]:
    if len(families) < 3:
        raise ValueError("expected at least three logic families")
    ranked_families = sorted(
        families,
        key=lambda family: _variant_sort_key(families[family][0]),
    )
    return ranked_families[:3]


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    ranking = build_handoff_ranking(args.campaign_dir)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ranking, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
