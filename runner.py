from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiment_config import ExperimentConfig, load_experiment_config, materialize_runner_toml
from quant_strategies.runner import run_config
from scoring import build_score, classify_failure_source, load_json, write_score


ROOT = Path(__file__).resolve().parent
LEDGER_HEADER = [
    "attempt",
    "commit",
    "window_id",
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

    config = load_experiment_config(args.config)
    results_dir = _results_dir(config)
    state_path = results_dir / "session_state.json"
    state = load_session_state(state_path, config=config, max_attempts_override=args.max_attempts)
    if state.remaining_attempts <= 0:
        print("session exhausted")
        return 2

    attempt = state.attempts_used + 1
    window_id = args.window_id or config.selected_window_id
    commit = current_commit()
    generated_config = results_dir / ".generated" / f"attempt_{attempt:04d}_{window_id}.toml"
    materialize_runner_toml(config, generated_config, window_id=window_id, results_dir=results_dir)

    result = run_config(generated_config, repo_root=ROOT)
    result_dir = result.result_dir
    summary = load_json(result_dir / "summary.json") if result_dir is not None else None
    evidence = load_json(result_dir / "evidence.json") if result_dir is not None else None
    failure_source = _failure_source(summary, evidence, getattr(result, "message", None))
    score = build_score(
        summary=summary,
        evidence=evidence,
        min_score_trades=config.scoring.min_score_trades,
        window_id=window_id,
        failure_source=failure_source,
        complexity_note="simplification" if args.simplification else "",
    )

    if result_dir is not None:
        write_score(result_dir / "score.json", score)
        write_attempt_metadata(
            result_dir / "attempt_metadata.json",
            attempt=attempt,
            commit=commit,
            window_id=window_id,
            description=args.description,
            generated_config=generated_config,
            failure_source=failure_source,
        )

    decision = decision_for_score(score, state=state, simplification=args.simplification)
    next_state = update_state(state, score=score, commit=commit, decision=decision)
    save_session_state(state_path, next_state)
    append_ledger(
        Path("results.tsv"),
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        score=score,
        status=decision,
        description=args.description,
    )
    print(
        json.dumps(
            {
                "attempt": attempt,
                "decision": decision,
                "remaining_attempts": next_state.remaining_attempts,
                "result_dir": str(result_dir) if result_dir is not None else None,
                "score": score["score"],
                "status": next_state.status,
            },
            sort_keys=True,
        )
    )
    return 0


def load_session_state(
    path: Path,
    *,
    config: ExperimentConfig,
    max_attempts_override: int | None,
) -> SessionState:
    if not path.exists():
        max_attempts = config.max_attempts if max_attempts_override is None else max_attempts_override
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
    score: dict[str, Any],
    status: str,
    description: str,
) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_HEADER, delimiter="\t", lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "attempt": attempt,
                "commit": commit or "",
                "window_id": window_id,
                "score": "" if score.get("score") is None else score["score"],
                "raw_net_return": "" if score.get("raw_net_return") is None else score["raw_net_return"],
                "trade_count": "" if score.get("trade_count") is None else score["trade_count"],
                "status": status,
                "description": description,
            }
        )


def write_attempt_metadata(
    path: Path,
    *,
    attempt: int,
    commit: str | None,
    window_id: str,
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
    return Path.cwd() / configured


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


def _numeric_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


if __name__ == "__main__":
    raise SystemExit(main())
