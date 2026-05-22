from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiment_config import (
    ConfigError,
    ExperimentConfig,
    load_experiment_config,
    materialize_runner_toml,
)
from quant_strategies.runner import run_config
from scoring import build_score, classify_failure_source, load_json, write_score


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
LEDGER_HEADER = [
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


@dataclass(frozen=True)
class SessionState:
    max_attempts: int
    attempts_used: int
    best_score: float | None
    best_commit: str | None
    status: str
    last_decision: str | None = None

    @property
    def remaining_attempts(self) -> int:
        return max(0, self.max_attempts - self.attempts_used)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="experiment.toml")
    parser.add_argument("--description", default="")
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--window-id", default=None)
    parser.add_argument("--simplification", action="store_true")
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
    window_id = args.window_id or config.selected_window_id
    window_metadata = _window_metadata(config, window_id)
    commit = current_commit()
    generated_config = results_dir / ".generated" / f"attempt_{attempt:04d}_{window_id}.toml"
    materialize_runner_toml(config, generated_config, window_id=window_id, results_dir=results_dir)

    result = run_config(generated_config, repo_root=ROOT)
    result_dir = result.result_dir
    if result_dir is None:
        result_dir = results_dir / f"attempt_{attempt:04d}_config_failed"
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
        complexity_note="simplification" if args.simplification else "",
        **window_metadata,
    )

    write_score(result_dir / "score.json", score)
    write_attempt_metadata(
        result_dir / "attempt_metadata.json",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        description=args.description,
        generated_config=generated_config,
        failure_source=failure_source,
        **window_metadata,
    )

    return _finish_attempt(
        state_path=state_path,
        state=state,
        score=score,
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        window_metadata=window_metadata,
        result_dir=result_dir,
        description=args.description,
        simplification=args.simplification,
        ignored_max_attempts_override=ignored_max_attempts_override,
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
    window_metadata = _empty_window_metadata()
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
        **window_metadata,
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
        **window_metadata,
    )

    return _finish_attempt(
        state_path=state_path,
        state=state,
        score=score,
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        window_metadata=window_metadata,
        result_dir=result_dir,
        description=args.description,
        simplification=args.simplification,
        ignored_max_attempts_override=ignored_max_attempts_override,
    )


def _finish_attempt(
    *,
    state_path: Path,
    state: SessionState,
    score: dict[str, Any],
    attempt: int,
    commit: str | None,
    window_id: str,
    window_metadata: dict[str, str | int | None],
    result_dir: Path,
    description: str,
    simplification: bool,
    ignored_max_attempts_override: int | None,
) -> int:
    decision = decision_for_score(score, state=state, simplification=simplification)
    next_state = update_state(state, score=score, commit=commit, decision=decision)
    save_session_state(state_path, next_state)
    append_ledger(
        ROOT / "results.tsv",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        window_start=_optional_str(window_metadata["window_start"]),
        window_end=_optional_str(window_metadata["window_end"]),
        window_days=_optional_int(window_metadata["window_days"]),
        score=score,
        status=decision,
        description=description,
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
                "score": score["score"],
                "status": next_state.status,
                **window_metadata,
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
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    return SessionState(
        max_attempts=int(payload["max_attempts"]),
        attempts_used=int(payload["attempts_used"]),
        best_score=_optional_float(payload.get("best_score")),
        best_commit=_optional_str(payload.get("best_commit")),
        status=str(payload["status"]),
        last_decision=_optional_str(payload.get("last_decision")),
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
        "last_decision": state.last_decision,
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
        status="exhausted" if attempts_used >= state.max_attempts else "active",
        last_decision=decision,
    )


def append_ledger(
    path: Path,
    *,
    attempt: int,
    commit: str | None,
    window_id: str,
    window_start: str | None,
    window_end: str | None,
    window_days: int | None,
    score: dict[str, Any],
    status: str,
    description: str,
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
                "score": "" if score.get("score") is None else score["score"],
                "raw_net_return": "" if score.get("raw_net_return") is None else score["raw_net_return"],
                "trade_count": "" if score.get("trade_count") is None else score["trade_count"],
                "status": status,
                "description": _single_line(description),
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

    if fieldnames != OLD_LEDGER_HEADER:
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
    description: str,
    generated_config: Path,
    failure_source: str | None,
) -> None:
    payload = {
        "attempt": attempt,
        "commit": commit,
        "description": description,
        "failure_source": failure_source,
        "generated_config": str(generated_config),
        "window_id": window_id,
        "window_start": window_start,
        "window_end": window_end,
        "window_days": window_days,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _window_metadata(config: ExperimentConfig, window_id: str) -> dict[str, str | int | None]:
    window = config.window_by_id(window_id)
    return {
        "window_start": window.start,
        "window_end": window.end,
        "window_days": window.days,
    }


def _empty_window_metadata() -> dict[str, str | int | None]:
    return {
        "window_start": None,
        "window_end": None,
        "window_days": None,
    }


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
