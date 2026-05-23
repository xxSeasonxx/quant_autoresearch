from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from artifact_policy import apply_artifact_policy
from experiment_config import (
    ArtifactConfig,
    ConfigError,
    ExperimentConfig,
    load_experiment_config,
    materialize_runner_toml,
)
from promotion import (
    build_cost_stress_config,
    build_promotion_score,
    decision_for_promotion,
    scored_for_promotion,
    select_rotating_probe_window_id,
)
from quant_strategies.runner import run_config
from scoring import (
    build_candidate_score,
    build_score,
    build_trade_attribution,
    classify_failure_source,
    load_json,
    write_score,
)


ROOT = Path(__file__).resolve().parent
SESSION_POINTER_NAME = ".autoresearch_session.json"
CONFIG_FAILURE_MAX_ATTEMPTS = 1
CONFIG_FAILURE_MIN_SCORE_TRADES = 1
CONFIG_FAILURE_WINDOW_ID = "config"
OLD_LEDGER_HEADER = [
    "attempt",
    "commit",
    "window_id",
    "score",
    "raw_net_return",
    "trade_count",
    "status",
    "description",
]
WINDOW_LEDGER_HEADER = [
    "attempt",
    "commit",
    "window_id",
    "window_start",
    "window_end",
    "window_days",
    "score",
    "raw_net_return",
    "trade_count",
    "status",
    "description",
]
SYMBOL_LEDGER_HEADER = [
    "attempt",
    "commit",
    "window_id",
    "window_start",
    "window_end",
    "window_days",
    "symbol_count",
    "score",
    "raw_net_return",
    "trade_count",
    "status",
    "description",
]
LEDGER_HEADER = [
    *SYMBOL_LEDGER_HEADER,
    "run_kind",
    "candidate_score",
    "recent_mean_score",
    "worst_recent_score",
    "passed_window_count",
    "failed_window_count",
]
CANDIDATE_LEDGER_HEADER = LEDGER_HEADER
LEDGER_HEADER = [
    *CANDIDATE_LEDGER_HEADER,
    "promotion_decision",
    "promotion_score",
    "score_dispersion",
    "cost_stress_score",
    "cost_stress_ratio",
    "rotating_probe_window_id",
    "rotating_probe_score",
    "promoted_commit",
]


@dataclass(frozen=True)
class SessionState:
    max_attempts: int
    attempts_used: int
    best_score: float | None
    best_commit: str | None
    status: str
    last_decision: str | None = None
    best_primary_window_score: float | None = None
    best_confirmed_candidate_score: float | None = None
    best_confirmed_commit: str | None = None
    best_promoted_score: float | None = None
    best_promoted_commit: str | None = None
    rotating_probe_index: int = 0
    last_promotion_decision: str | None = None

    @property
    def remaining_attempts(self) -> int:
        return max(0, self.max_attempts - self.attempts_used)


@dataclass(frozen=True)
class WindowAttemptResult:
    window_id: str
    result_dir: Path
    score: dict[str, Any]
    summary: dict[str, Any] | None
    evidence: dict[str, Any] | None
    run_metadata: dict[str, str | int | None]
    failure_source: str | None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="experiment.toml")
    parser.add_argument("--description", default="")
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--simplification", action="store_true")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--window-id", default=None)
    mode_group.add_argument("--explore", action="store_true")
    mode_group.add_argument("--confirm", action="store_true")
    parser.add_argument("--artifact-profile", choices=("research", "debug"), default=None)
    args = parser.parse_args(argv)

    try:
        config = load_experiment_config(_rooted_path(args.config))
    except ConfigError as exc:
        return _record_config_load_failure(args, exc)

    results_dir = _results_dir(config)
    _write_results_dir_pointer(results_dir)
    state_path = results_dir / "session_state.json"
    state = load_session_state(
        state_path,
        config=config,
        max_attempts_override=args.max_attempts,
    )
    ignored_max_attempts_override = _ignored_max_attempts_override(
        state_path,
        state=state,
        max_attempts_override=args.max_attempts,
    )
    if state.remaining_attempts <= 0:
        print("session exhausted")
        return 2

    attempt = state.attempts_used + 1
    commit = current_commit()
    run_kind = _run_kind(args, config)

    if run_kind == "confirm":
        candidate_dir, candidate_score, window_results = run_confirmation_attempt(
            config=config,
            attempt=attempt,
            results_dir=results_dir,
            description=args.description,
            commit=commit,
            simplification=args.simplification,
            artifact_profile=args.artifact_profile,
        )
        return _finish_confirmation_attempt(
            state_path=state_path,
            state=state,
            candidate_dir=candidate_dir,
            candidate_score=candidate_score,
            window_results=window_results,
            attempt=attempt,
            commit=commit,
            description=args.description,
            ignored_max_attempts_override=ignored_max_attempts_override,
            auto_confirmed_from_explore=False,
            simplification=args.simplification,
            primary_window_id=config.research.primary_window_id,
        )

    window_id = _selected_single_window(args, config, run_kind)
    window_result = run_single_window_attempt(
        config=config,
        attempt=attempt,
        window_id=window_id,
        results_dir=results_dir,
        description=args.description,
        commit=commit,
        simplification=args.simplification,
        artifact_profile=args.artifact_profile,
    )

    if (
        run_kind == "explore"
        and config.promotion.enabled
        and config.promotion.screen_on_scored_explore
        and scored_for_promotion(window_result.score)
    ):
        promotion_dir, promotion_score, recent_results = run_promotion_screen(
            config=config,
            state=state,
            attempt=attempt,
            results_dir=results_dir,
            description=args.description,
            commit=commit,
            simplification=args.simplification,
            artifact_profile=args.artifact_profile,
            explore_result=window_result,
        )
        return _finish_promotion_attempt(
            state_path=state_path,
            state=state,
            promotion_dir=promotion_dir,
            promotion_score=promotion_score,
            recent_results=recent_results,
            attempt=attempt,
            commit=commit,
            description=args.description,
            ignored_max_attempts_override=ignored_max_attempts_override,
            simplification=args.simplification,
            primary_window_id=config.research.primary_window_id,
        )

    if run_kind == "explore" and config.research.confirm_on_explore_keep:
        state_with_primary = update_primary_window_reference(state, score=window_result.score)
        if state_with_primary.best_primary_window_score != state.best_primary_window_score:
            candidate_dir, candidate_score, window_results = run_confirmation_attempt(
                config=config,
                attempt=attempt,
                results_dir=results_dir,
                description=args.description,
                commit=commit,
                simplification=args.simplification,
                artifact_profile=args.artifact_profile,
            )
            return _finish_confirmation_attempt(
                state_path=state_path,
                state=state_with_primary,
                candidate_dir=candidate_dir,
                candidate_score=candidate_score,
                window_results=window_results,
                attempt=attempt,
                commit=commit,
                description=args.description,
                ignored_max_attempts_override=ignored_max_attempts_override,
                auto_confirmed_from_explore=True,
                simplification=args.simplification,
                primary_window_id=config.research.primary_window_id,
            )

    return _finish_attempt(
        state_path=state_path,
        state=state,
        score=window_result.score,
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        run_metadata=window_result.run_metadata,
        result_dir=window_result.result_dir,
        description=args.description,
        simplification=args.simplification,
        ignored_max_attempts_override=ignored_max_attempts_override,
        run_kind=run_kind,
    )


def _record_config_load_failure(args: argparse.Namespace, error: ConfigError) -> int:
    results_dir = _config_failure_results_dir()
    state_path = results_dir / "session_state.json"
    state = load_session_state(
        state_path,
        config=None,
        max_attempts_override=None,
        fallback_max_attempts=CONFIG_FAILURE_MAX_ATTEMPTS,
    )
    ignored_max_attempts_override = _ignored_max_attempts_override(
        state_path,
        state=state,
        max_attempts_override=args.max_attempts,
    )
    if state.remaining_attempts <= 0:
        print("session exhausted")
        return 2

    attempt = state.attempts_used + 1
    window_id = args.window_id or CONFIG_FAILURE_WINDOW_ID
    run_metadata = _empty_run_metadata()
    commit = current_commit()
    result_dir = results_dir / f"attempt_{attempt:04d}_config_failed"
    result_dir.mkdir(parents=True, exist_ok=True)

    summary = {"stage": "config_load", "message": str(error)}
    (result_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failure_source = classify_failure_source("config_load", str(error))
    score = build_score(
        summary=summary,
        evidence=None,
        min_score_trades=CONFIG_FAILURE_MIN_SCORE_TRADES,
        window_id=window_id,
        failure_source=failure_source,
        complexity_note="simplification" if args.simplification else "",
        **run_metadata,
    )

    write_score(result_dir / "score.json", score)
    write_attempt_metadata(
        result_dir / "attempt_metadata.json",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        description=args.description,
        generated_config=_rooted_path(args.config),
        failure_source=failure_source,
        **run_metadata,
    )

    return _finish_attempt(
        state_path=state_path,
        state=state,
        score=score,
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        run_metadata=run_metadata,
        result_dir=result_dir,
        description=args.description,
        simplification=args.simplification,
        ignored_max_attempts_override=ignored_max_attempts_override,
        run_kind="diagnostic" if args.window_id else "explore",
    )


def run_single_window_attempt(
    *,
    config: ExperimentConfig,
    attempt: int,
    window_id: str,
    results_dir: Path,
    description: str,
    commit: str | None,
    simplification: bool,
    artifact_profile: str | None,
) -> WindowAttemptResult:
    run_metadata = _run_metadata(config, window_id)
    generated_config = results_dir / ".generated" / f"attempt_{attempt:04d}_{window_id}.toml"
    materialize_runner_toml(config, generated_config, window_id=window_id, results_dir=results_dir)

    result = run_config(generated_config, repo_root=ROOT)
    result_dir = result.result_dir
    if result_dir is None:
        result_dir = results_dir / f"attempt_{attempt:04d}_{window_id}_config_failed"
        result_dir.mkdir(parents=True, exist_ok=True)
    summary, evidence = _load_artifacts(result_dir, result_message=getattr(result, "message", None))
    if result.result_dir is None:
        summary = {"stage": "config", "message": getattr(result, "message", None)}
    failure_source = _failure_source(summary, evidence, getattr(result, "message", None))
    score = build_score(
        summary=summary,
        evidence=evidence,
        min_score_trades=config.scoring.min_score_trades,
        window_id=window_id,
        failure_source=failure_source,
        complexity_note="simplification" if simplification else "",
        **run_metadata,
    )

    write_score(result_dir / "score.json", score)
    artifact_config = config.artifacts
    if artifact_profile is not None and artifact_profile != artifact_config.profile:
        artifact_config = _artifact_config_with_profile(artifact_config, artifact_profile)
    removed_artifacts = apply_artifact_policy(result_dir, artifact_config)
    write_attempt_metadata(
        result_dir / "attempt_metadata.json",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        description=description,
        generated_config=generated_config,
        failure_source=failure_source,
        removed_artifacts=removed_artifacts,
        **run_metadata,
    )

    return WindowAttemptResult(
        window_id=window_id,
        result_dir=result_dir,
        score=score,
        summary=summary,
        evidence=evidence,
        run_metadata=run_metadata,
        failure_source=failure_source,
    )


def run_confirmation_attempt(
    *,
    config: ExperimentConfig,
    attempt: int,
    results_dir: Path,
    description: str,
    commit: str | None,
    simplification: bool,
    artifact_profile: str | None,
) -> tuple[Path, dict[str, Any], list[WindowAttemptResult]]:
    candidate_dir = results_dir / f"candidate_{attempt:04d}_{config.strategy_id}"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    def _run(window_id: str) -> WindowAttemptResult:
        window_results_dir = candidate_dir / "windows" / window_id
        try:
            return run_single_window_attempt(
                config=config,
                attempt=attempt,
                window_id=window_id,
                results_dir=window_results_dir,
                description=description,
                commit=commit,
                simplification=simplification,
                artifact_profile=artifact_profile,
            )
        except Exception as exc:
            return failed_window_attempt_result(
                config=config,
                attempt=attempt,
                window_id=window_id,
                result_dir=window_results_dir / f"attempt_{attempt:04d}_{window_id}_failed",
                description=description,
                commit=commit,
                message=f"confirmation window failed: {exc}",
            )

    workers = max(1, min(config.research.parallel_workers, len(config.research.confirmation_window_ids)))
    if workers == 1:
        window_results = [_run(window_id) for window_id in config.research.confirmation_window_ids]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            window_results = list(executor.map(_run, config.research.confirmation_window_ids))

    candidate_score = build_candidate_score(
        window_scores=[result.score for result in window_results],
        config=config.confirmation_scoring,
        commit=commit,
        description=description,
    )
    write_score(candidate_dir / "candidate_score.json", candidate_score)
    (candidate_dir / "candidate_summary.json").write_text(
        json.dumps(
            {
                "attempt": attempt,
                "commit": commit,
                "description": description,
                "window_ids": list(config.research.confirmation_window_ids),
                "candidate_score": candidate_score["candidate_score"],
                "status": candidate_score["status"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    attribution = build_trade_attribution({result.window_id: result.evidence for result in window_results})
    (candidate_dir / "trade_attribution.json").write_text(
        json.dumps(attribution, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate_dir, candidate_score, window_results


def run_promotion_screen(
    *,
    config: ExperimentConfig,
    state: SessionState,
    attempt: int,
    results_dir: Path,
    description: str,
    commit: str | None,
    simplification: bool,
    artifact_profile: str | None,
    explore_result: WindowAttemptResult,
) -> tuple[Path, dict[str, Any], list[WindowAttemptResult]]:
    promotion_dir = results_dir / f"promotion_{attempt:04d}_{config.strategy_id}"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    def _run(
        *,
        target_config: ExperimentConfig,
        window_id: str,
        result_dir: Path,
        stage: str,
    ) -> WindowAttemptResult:
        try:
            return run_single_window_attempt(
                config=target_config,
                attempt=attempt,
                window_id=window_id,
                results_dir=result_dir,
                description=description,
                commit=commit,
                simplification=simplification,
                artifact_profile=artifact_profile,
            )
        except Exception as exc:
            return failed_window_attempt_result(
                config=target_config,
                attempt=attempt,
                window_id=window_id,
                result_dir=result_dir / f"attempt_{attempt:04d}_{window_id}_failed",
                description=description,
                commit=commit,
                message=f"{stage} failed: {exc}",
            )

    recent_results: list[WindowAttemptResult] = []
    for window_id in config.promotion.recent_window_ids:
        if window_id == explore_result.window_id:
            recent_results.append(explore_result)
            continue
        recent_results.append(
            _run(
                target_config=config,
                window_id=window_id,
                result_dir=promotion_dir / "windows" / window_id,
                stage="promotion recent window",
            )
        )

    cost_config = build_cost_stress_config(config)
    cost_result = _run(
        target_config=cost_config,
        window_id=config.research.primary_window_id,
        result_dir=promotion_dir / "cost_stress" / config.promotion.cost_stress_id,
        stage="promotion cost stress",
    )

    probe_window_id = select_rotating_probe_window_id(config.promotion, state)
    probe_result = _run(
        target_config=config,
        window_id=probe_window_id,
        result_dir=promotion_dir / "rotating_probe" / probe_window_id,
        stage="promotion rotating probe",
    )

    promotion_score = build_promotion_score(
        recent_window_scores=[result.score for result in recent_results],
        cost_stress_score=cost_result.score,
        rotating_probe_score=probe_result.score,
        confirmation_config=config.confirmation_scoring,
        promotion_config=config.promotion,
        commit=commit,
        description=description,
        rotating_probe_window_id=probe_window_id,
    )
    write_score(promotion_dir / "promotion_score.json", promotion_score)
    (promotion_dir / "promotion_summary.json").write_text(
        json.dumps(
            {
                "attempt": attempt,
                "commit": commit,
                "description": description,
                "promotion_score": promotion_score["promotion_score"],
                "eligible_for_promotion": promotion_score["eligible_for_promotion"],
                "failed_reasons": promotion_score["failed_reasons"],
                "recent_window_ids": list(config.promotion.recent_window_ids),
                "source_result_dirs": {result.window_id: str(result.result_dir) for result in recent_results},
                "cost_stress_result_dir": str(cost_result.result_dir),
                "cost_stress_id": config.promotion.cost_stress_id,
                "rotating_probe_window_id": probe_window_id,
                "rotating_probe_result_dir": str(probe_result.result_dir),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    evidence_by_window = {result.window_id: result.evidence for result in recent_results}
    evidence_by_window[f"cost_stress:{config.promotion.cost_stress_id}"] = cost_result.evidence
    evidence_by_window[f"rotating_probe:{probe_window_id}"] = probe_result.evidence
    (promotion_dir / "trade_attribution.json").write_text(
        json.dumps(build_trade_attribution(evidence_by_window), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return promotion_dir, promotion_score, recent_results


def failed_window_attempt_result(
    *,
    config: ExperimentConfig,
    attempt: int,
    window_id: str,
    result_dir: Path,
    description: str,
    commit: str | None,
    message: str,
) -> WindowAttemptResult:
    result_dir.mkdir(parents=True, exist_ok=True)
    run_metadata = _run_metadata(config, window_id)
    summary = {"stage": "confirmation_window", "message": message}
    (result_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failure_source = "environment_error"
    score = build_score(
        summary=summary,
        evidence=None,
        min_score_trades=config.scoring.min_score_trades,
        window_id=window_id,
        failure_source=failure_source,
        **run_metadata,
    )
    write_score(result_dir / "score.json", score)
    write_attempt_metadata(
        result_dir / "attempt_metadata.json",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        description=description,
        generated_config=result_dir / "unavailable.toml",
        failure_source=failure_source,
        **run_metadata,
    )
    return WindowAttemptResult(
        window_id=window_id,
        result_dir=result_dir,
        score=score,
        summary=summary,
        evidence=None,
        run_metadata=run_metadata,
        failure_source=failure_source,
    )


def _finish_attempt(
    *,
    state_path: Path,
    state: SessionState,
    score: dict[str, Any],
    attempt: int,
    commit: str | None,
    window_id: str,
    run_metadata: dict[str, str | int | None],
    result_dir: Path,
    description: str,
    simplification: bool,
    ignored_max_attempts_override: int | None,
    run_kind: str,
) -> int:
    decision = decision_for_score(score, state=state, simplification=simplification)
    next_state = update_state(state, score=score, commit=commit, decision=decision)
    save_session_state(state_path, next_state)
    append_ledger(
        ROOT / "results.tsv",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        window_start=_optional_str(run_metadata["window_start"]),
        window_end=_optional_str(run_metadata["window_end"]),
        window_days=_optional_int(run_metadata["window_days"]),
        symbol_count=_optional_int(run_metadata["symbol_count"]),
        score=score,
        status=decision,
        description=description,
        run_kind=run_kind,
    )
    print(
        json.dumps(
            {
                "attempt": attempt,
                "decision": decision,
                "ignored_max_attempts_override": ignored_max_attempts_override,
                "max_attempts": next_state.max_attempts,
                "remaining_attempts": next_state.remaining_attempts,
                "result_dir": str(result_dir),
                "run_kind": run_kind,
                "score": score["score"],
                "status": next_state.status,
                **run_metadata,
            },
            sort_keys=True,
        )
    )
    return 0


def _finish_confirmation_attempt(
    *,
    state_path: Path,
    state: SessionState,
    candidate_dir: Path,
    candidate_score: dict[str, Any],
    window_results: list[WindowAttemptResult],
    attempt: int,
    commit: str | None,
    description: str,
    ignored_max_attempts_override: int | None,
    auto_confirmed_from_explore: bool,
    simplification: bool,
    primary_window_id: str,
) -> int:
    decision = decision_for_candidate_score(candidate_score, state=state, simplification=simplification)
    next_state = update_state_for_candidate(state, candidate_score=candidate_score, commit=commit, decision=decision)
    save_session_state(state_path, next_state)

    primary_result = _primary_window_result(window_results, primary_window_id=primary_window_id)
    append_ledger(
        ROOT / "results.tsv",
        attempt=attempt,
        commit=commit,
        window_id=primary_result.window_id,
        window_start=_optional_str(primary_result.run_metadata["window_start"]),
        window_end=_optional_str(primary_result.run_metadata["window_end"]),
        window_days=_optional_int(primary_result.run_metadata["window_days"]),
        symbol_count=_optional_int(primary_result.run_metadata["symbol_count"]),
        score=primary_result.score,
        status=decision,
        description=description,
        run_kind="confirm",
        candidate_score=candidate_score,
    )
    print(
        json.dumps(
            {
                "attempt": attempt,
                "auto_confirmed_from_explore": auto_confirmed_from_explore,
                "candidate_score": candidate_score["candidate_score"],
                "decision": decision,
                "ignored_max_attempts_override": ignored_max_attempts_override,
                "max_attempts": next_state.max_attempts,
                "remaining_attempts": next_state.remaining_attempts,
                "result_dir": str(candidate_dir),
                "run_kind": "confirm",
                "status": next_state.status,
            },
            sort_keys=True,
        )
    )
    return 0


def _finish_promotion_attempt(
    *,
    state_path: Path,
    state: SessionState,
    promotion_dir: Path,
    promotion_score: dict[str, Any],
    recent_results: list[WindowAttemptResult],
    attempt: int,
    commit: str | None,
    description: str,
    ignored_max_attempts_override: int | None,
    simplification: bool,
    primary_window_id: str,
) -> int:
    decision = decision_for_promotion(promotion_score, state=state, simplification=simplification)
    next_score = {
        **promotion_score,
        "promotion_decision": decision,
        "promoted_commit": commit if decision == "promote" else None,
    }
    write_score(promotion_dir / "promotion_score.json", next_score)
    next_state = update_state_for_promotion(
        state,
        promotion_score=promotion_score,
        commit=commit,
        decision=decision,
    )
    save_session_state(state_path, next_state)
    primary_result = _primary_window_result(recent_results, primary_window_id=primary_window_id)
    append_ledger(
        ROOT / "results.tsv",
        attempt=attempt,
        commit=commit,
        window_id=primary_result.window_id,
        window_start=_optional_str(primary_result.run_metadata["window_start"]),
        window_end=_optional_str(primary_result.run_metadata["window_end"]),
        window_days=_optional_int(primary_result.run_metadata["window_days"]),
        symbol_count=_optional_int(primary_result.run_metadata["symbol_count"]),
        score=primary_result.score,
        status=decision,
        description=description,
        run_kind="promotion",
        promotion_score=next_score,
    )
    print(
        json.dumps(
            {
                "attempt": attempt,
                "decision": decision,
                "ignored_max_attempts_override": ignored_max_attempts_override,
                "max_attempts": next_state.max_attempts,
                "promotion_score": promotion_score["promotion_score"],
                "remaining_attempts": next_state.remaining_attempts,
                "result_dir": str(promotion_dir),
                "run_kind": "promotion",
                "status": next_state.status,
            },
            sort_keys=True,
        )
    )
    return 0


def load_session_state(
    path: Path,
    *,
    config: ExperimentConfig | None,
    max_attempts_override: int | None,
    fallback_max_attempts: int | None = None,
) -> SessionState:
    if not path.exists():
        if max_attempts_override is not None:
            max_attempts = max_attempts_override
        elif config is not None:
            max_attempts = config.max_attempts
        elif fallback_max_attempts is not None:
            max_attempts = fallback_max_attempts
        else:
            raise ValueError("missing max attempts source for new session")
        return SessionState(
            max_attempts=max_attempts,
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

    payload = json.loads(path.read_text(encoding="utf-8"))
    return SessionState(
        max_attempts=int(payload["max_attempts"]),
        attempts_used=int(payload["attempts_used"]),
        best_score=_optional_float(payload.get("best_score")),
        best_commit=_optional_str(payload.get("best_commit")),
        status=str(payload["status"]),
        last_decision=_optional_str(payload.get("last_decision")),
        best_primary_window_score=_optional_float(payload.get("best_primary_window_score")),
        best_confirmed_candidate_score=_optional_float(payload.get("best_confirmed_candidate_score")),
        best_confirmed_commit=_optional_str(payload.get("best_confirmed_commit")),
        best_promoted_score=_optional_float(payload.get("best_promoted_score")),
        best_promoted_commit=_optional_str(payload.get("best_promoted_commit")),
        rotating_probe_index=_optional_int(payload.get("rotating_probe_index")) or 0,
        last_promotion_decision=_optional_str(payload.get("last_promotion_decision")),
    )


def _ignored_max_attempts_override(
    path: Path,
    *,
    state: SessionState,
    max_attempts_override: int | None,
) -> int | None:
    if (
        path.exists()
        and max_attempts_override is not None
        and max_attempts_override != state.max_attempts
    ):
        return max_attempts_override
    return None


def save_session_state(path: Path, state: SessionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "attempts_used": state.attempts_used,
        "best_commit": state.best_commit,
        "best_score": state.best_score,
        "best_primary_window_score": state.best_primary_window_score,
        "last_decision": state.last_decision,
        "best_confirmed_candidate_score": state.best_confirmed_candidate_score,
        "best_confirmed_commit": state.best_confirmed_commit,
        "best_promoted_score": state.best_promoted_score,
        "best_promoted_commit": state.best_promoted_commit,
        "rotating_probe_index": state.rotating_probe_index,
        "last_promotion_decision": state.last_promotion_decision,
        "max_attempts": state.max_attempts,
        "remaining_attempts": state.remaining_attempts,
        "status": state.status,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def decision_for_score(score: dict[str, Any], *, state: SessionState, simplification: bool) -> str:
    value = _numeric_score(score.get("score"))
    if value is None:
        return "discard"
    if state.best_score is None:
        return "keep"
    if value > state.best_score:
        return "keep"
    if value == state.best_score and simplification:
        return "keep"
    return "discard"


def update_state(
    state: SessionState,
    *,
    score: dict[str, Any],
    commit: str | None,
    decision: str,
) -> SessionState:
    attempts_used = state.attempts_used + 1
    best_score = state.best_score
    best_commit = state.best_commit
    value = _numeric_score(score.get("score"))
    if decision == "keep" and value is not None:
        best_score = value
        best_commit = commit

    return SessionState(
        max_attempts=state.max_attempts,
        attempts_used=attempts_used,
        best_score=best_score,
        best_commit=best_commit,
        best_primary_window_score=state.best_primary_window_score,
        best_confirmed_candidate_score=state.best_confirmed_candidate_score,
        best_confirmed_commit=state.best_confirmed_commit,
        best_promoted_score=state.best_promoted_score,
        best_promoted_commit=state.best_promoted_commit,
        rotating_probe_index=state.rotating_probe_index,
        last_promotion_decision=state.last_promotion_decision,
        status="exhausted" if attempts_used >= state.max_attempts else "active",
        last_decision=decision,
    )


def decision_for_candidate_score(
    candidate_score: dict[str, Any],
    *,
    state: SessionState,
    simplification: bool,
) -> str:
    value = _numeric_score(candidate_score.get("candidate_score"))
    if value is None:
        return "discard"
    if state.best_confirmed_candidate_score is None:
        return "keep"
    if value > state.best_confirmed_candidate_score:
        return "keep"
    if value == state.best_confirmed_candidate_score and simplification:
        return "keep"
    return "discard"


def update_state_for_candidate(
    state: SessionState,
    *,
    candidate_score: dict[str, Any],
    commit: str | None,
    decision: str,
) -> SessionState:
    attempts_used = state.attempts_used + 1
    best_confirmed_candidate_score = state.best_confirmed_candidate_score
    best_confirmed_commit = state.best_confirmed_commit
    value = _numeric_score(candidate_score.get("candidate_score"))
    if decision == "keep" and value is not None:
        best_confirmed_candidate_score = value
        best_confirmed_commit = commit
    return SessionState(
        max_attempts=state.max_attempts,
        attempts_used=attempts_used,
        best_score=state.best_score,
        best_commit=state.best_commit,
        best_primary_window_score=state.best_primary_window_score,
        best_confirmed_candidate_score=best_confirmed_candidate_score,
        best_confirmed_commit=best_confirmed_commit,
        best_promoted_score=state.best_promoted_score,
        best_promoted_commit=state.best_promoted_commit,
        rotating_probe_index=state.rotating_probe_index,
        last_promotion_decision=state.last_promotion_decision,
        status="exhausted" if attempts_used >= state.max_attempts else "active",
        last_decision=decision,
    )


def update_state_for_promotion(
    state: SessionState,
    *,
    promotion_score: dict[str, Any],
    commit: str | None,
    decision: str,
) -> SessionState:
    attempts_used = state.attempts_used + 1
    best_promoted_score = state.best_promoted_score
    best_promoted_commit = state.best_promoted_commit
    value = _numeric_score(promotion_score.get("promotion_score"))
    if decision == "promote" and value is not None:
        best_promoted_score = value
        best_promoted_commit = commit
    return SessionState(
        max_attempts=state.max_attempts,
        attempts_used=attempts_used,
        best_score=state.best_score,
        best_commit=state.best_commit,
        best_primary_window_score=state.best_primary_window_score,
        best_confirmed_candidate_score=state.best_confirmed_candidate_score,
        best_confirmed_commit=state.best_confirmed_commit,
        best_promoted_score=best_promoted_score,
        best_promoted_commit=best_promoted_commit,
        rotating_probe_index=state.rotating_probe_index + 1,
        last_promotion_decision=decision,
        status="exhausted" if attempts_used >= state.max_attempts else "active",
        last_decision=decision,
    )


def update_primary_window_reference(state: SessionState, *, score: dict[str, Any]) -> SessionState:
    value = _numeric_score(score.get("score"))
    if value is None:
        return state
    if state.best_primary_window_score is not None and value <= state.best_primary_window_score:
        return state
    return replace(state, best_primary_window_score=value)


def append_ledger(
    path: Path,
    *,
    attempt: int,
    commit: str | None,
    window_id: str,
    window_start: str | None,
    window_end: str | None,
    window_days: int | None,
    symbol_count: int | None,
    score: dict[str, Any],
    status: str,
    description: str,
    run_kind: str = "explore",
    candidate_score: dict[str, Any] | None = None,
    promotion_score: dict[str, Any] | None = None,
) -> None:
    exists = _ensure_ledger_schema(path)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_HEADER, delimiter="\t", lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "attempt": attempt,
                "commit": commit or "",
                "window_id": window_id,
                "window_start": window_start or "",
                "window_end": window_end or "",
                "window_days": "" if window_days is None else window_days,
                "symbol_count": "" if symbol_count is None else symbol_count,
                "score": "" if score.get("score") is None else score["score"],
                "raw_net_return": "" if score.get("raw_net_return") is None else score["raw_net_return"],
                "trade_count": "" if score.get("trade_count") is None else score["trade_count"],
                "status": status,
                "description": _single_line(description),
                "run_kind": run_kind,
                "candidate_score": _candidate_field(candidate_score, "candidate_score"),
                "recent_mean_score": _candidate_field(candidate_score, "recent_mean_score"),
                "worst_recent_score": _candidate_field(candidate_score, "worst_recent_score"),
                "passed_window_count": _candidate_count(candidate_score, "passed_windows"),
                "failed_window_count": _candidate_count(candidate_score, "failed_windows"),
                "promotion_decision": _promotion_field(promotion_score, "promotion_decision"),
                "promotion_score": _promotion_field(promotion_score, "promotion_score"),
                "score_dispersion": _promotion_field(promotion_score, "score_dispersion"),
                "cost_stress_score": _promotion_field(promotion_score, "cost_stress_score"),
                "cost_stress_ratio": _promotion_field(promotion_score, "cost_stress_ratio"),
                "rotating_probe_window_id": _promotion_field(promotion_score, "rotating_probe_window_id"),
                "rotating_probe_score": _promotion_field(promotion_score, "rotating_probe_score"),
                "promoted_commit": _promotion_field(promotion_score, "promoted_commit"),
            }
        )


def _ensure_ledger_schema(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        if fieldnames == LEDGER_HEADER:
            return True
        rows = list(reader)

    if fieldnames not in (OLD_LEDGER_HEADER, WINDOW_LEDGER_HEADER, SYMBOL_LEDGER_HEADER, CANDIDATE_LEDGER_HEADER):
        raise ValueError(f"unexpected results.tsv header: {fieldnames}")

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_HEADER, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") or "" for field in LEDGER_HEADER})
    return True


def write_attempt_metadata(
    path: Path,
    *,
    attempt: int,
    commit: str | None,
    window_id: str,
    window_start: str | None,
    window_end: str | None,
    window_days: int | None,
    symbol_count: int | None,
    description: str,
    generated_config: Path,
    failure_source: str | None,
    removed_artifacts: list[str] | None = None,
) -> None:
    payload = {
        "attempt": attempt,
        "commit": commit,
        "description": description,
        "failure_source": failure_source,
        "generated_config": str(generated_config),
        "removed_artifacts": removed_artifacts or [],
        "window_id": window_id,
        "window_start": window_start,
        "window_end": window_end,
        "window_days": window_days,
        "symbol_count": symbol_count,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_kind(args: argparse.Namespace, config: ExperimentConfig) -> str:
    if args.confirm:
        return "confirm"
    if args.explore:
        return "explore"
    if args.window_id is not None:
        return "diagnostic"
    return config.research.mode


def _selected_single_window(args: argparse.Namespace, config: ExperimentConfig, run_kind: str) -> str:
    if args.window_id is not None:
        return args.window_id
    if run_kind == "explore":
        return config.research.primary_window_id
    return config.selected_window_id


def _primary_window_result(
    window_results: list[WindowAttemptResult],
    *,
    primary_window_id: str,
) -> WindowAttemptResult:
    if not window_results:
        raise ValueError("confirmation produced no window results")
    for result in window_results:
        if result.window_id == primary_window_id:
            return result
    raise ValueError(f"confirmation did not produce primary window result: {primary_window_id}")


def _artifact_config_with_profile(config: ArtifactConfig, profile: str) -> ArtifactConfig:
    if profile == "debug":
        return ArtifactConfig(
            profile="debug",
            keep_strategy_snapshot=True,
            keep_config=True,
            keep_summary=True,
            keep_evidence=True,
            keep_signals=True,
            keep_engine_request=True,
            keep_input_rows_csv=True,
            keep_input_rows_jsonl=True,
            compress_large_artifacts=config.compress_large_artifacts,
            large_artifact_max_mb=config.large_artifact_max_mb,
        )
    return ArtifactConfig(
        profile="research",
        keep_strategy_snapshot=True,
        keep_config=True,
        keep_summary=True,
        keep_evidence=True,
        keep_signals=True,
        keep_engine_request=False,
        keep_input_rows_csv=False,
        keep_input_rows_jsonl=False,
        compress_large_artifacts=config.compress_large_artifacts,
        large_artifact_max_mb=config.large_artifact_max_mb,
    )


def _candidate_field(candidate_score: dict[str, Any] | None, key: str) -> str:
    if candidate_score is None:
        return ""
    value = candidate_score.get(key)
    return "" if value is None else str(value)


def _candidate_count(candidate_score: dict[str, Any] | None, key: str) -> str:
    if candidate_score is None:
        return ""
    value = candidate_score.get(key)
    if not isinstance(value, list):
        return ""
    return str(len(value))


def _promotion_field(promotion_score: dict[str, Any] | None, key: str) -> str:
    if promotion_score is None:
        return ""
    value = promotion_score.get(key)
    return "" if value is None else str(value)


def current_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    commit = result.stdout.strip()
    return commit or None


def _results_dir(config: ExperimentConfig) -> Path:
    configured = Path(str(config.output["results_dir"]))
    if configured.is_absolute():
        return configured
    return ROOT / configured


def _run_metadata(config: ExperimentConfig, window_id: str) -> dict[str, str | int | None]:
    window = config.window_by_id(window_id)
    return {
        "window_start": window.start,
        "window_end": window.end,
        "window_days": window.days,
        "symbol_count": _symbol_count(config),
    }


def _empty_run_metadata() -> dict[str, str | int | None]:
    return {
        "window_start": None,
        "window_end": None,
        "window_days": None,
        "symbol_count": None,
    }


def _symbol_count(config: ExperimentConfig) -> int | None:
    symbols = config.data.get("symbols")
    if not isinstance(symbols, list):
        return None
    return len(symbols)


def _config_failure_results_dir() -> Path:
    previous_results_dir = _read_results_dir_pointer()
    if previous_results_dir is not None and (previous_results_dir / "session_state.json").exists():
        return previous_results_dir
    return ROOT / "results"


def _write_results_dir_pointer(results_dir: Path) -> None:
    payload = {"results_dir": str(results_dir)}
    _session_pointer_path().write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_results_dir_pointer() -> Path | None:
    path = _session_pointer_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    raw_results_dir = payload.get("results_dir")
    if not isinstance(raw_results_dir, str) or raw_results_dir == "":
        return None

    results_dir = Path(raw_results_dir)
    if results_dir.is_absolute():
        return results_dir
    return ROOT / results_dir


def _session_pointer_path() -> Path:
    return ROOT / SESSION_POINTER_NAME


def _rooted_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def _failure_source(
    summary: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    result_message: str | None,
) -> str | None:
    if evidence is not None:
        return None
    stage = _optional_str(summary.get("stage")) if summary is not None else None
    message = _optional_str(summary.get("message")) if summary is not None else None
    return classify_failure_source(stage, message or result_message)


def _load_artifacts(
    result_dir: Path,
    *,
    result_message: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        summary = load_json(result_dir / "summary.json")
    except ValueError as exc:
        return _artifact_failure_summary("summary.json", exc, result_message), None

    try:
        evidence = load_json(result_dir / "evidence.json")
    except ValueError as exc:
        if summary is None:
            summary = _artifact_failure_summary("evidence.json", exc, result_message)
        else:
            summary = dict(summary)
            summary["message"] = _artifact_failure_message("evidence.json", exc, result_message)
        return summary, None

    return summary, evidence


def _artifact_failure_summary(
    artifact_name: str,
    error: ValueError,
    result_message: str | None,
) -> dict[str, str]:
    return {
        "stage": "engine_evaluation",
        "message": _artifact_failure_message(artifact_name, error, result_message),
    }


def _artifact_failure_message(
    artifact_name: str,
    error: ValueError,
    result_message: str | None,
) -> str:
    message = f"malformed {artifact_name}: {error}"
    if result_message:
        return f"{message}; {result_message}"
    return message


def _numeric_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _single_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
