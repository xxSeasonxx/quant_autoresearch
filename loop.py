from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time
from typing import Callable, Mapping, Sequence

from gates import GateSet, evaluate_gates, symbol_concentration
from objective import TradeSample, is_improvement, score_cost_stress, score_objective
from protocol import (
    ExperimentConfig,
    ProtocolConfig,
    load_experiment,
    load_protocol,
    write_quick_run_config,
)
from results_log import ResultRow, append_result, read_results, status_summary


Runner = Callable[..., object]


@dataclass(frozen=True)
class IterationOutcome:
    status: str
    score: float | None
    gates_passed: bool
    gates: GateSet | None
    row: ResultRow | None = None
    stop_reason: str = ""
    message: str = ""


@dataclass(frozen=True)
class AttemptProvenance:
    run_id: str
    artifact_dir: str
    worktree_dirty: bool
    strategy_sha256: str
    experiment_sha256: str
    protocol_sha256: str
    rationale_sha256: str
    quick_config_sha256: str


def validate_thesis(mechanism: str, falsifier: str) -> str | None:
    if not mechanism.strip():
        return "thesis mechanism is required"
    if not falsifier.strip():
        return "thesis falsifier is required"
    return None


def components_from_rationale(path: str | Path = "rationale.md") -> tuple[str, ...]:
    try:
        lines = Path(path).read_text().splitlines()
    except OSError as exc:
        raise ValueError(f"could not read rationale: {path}") from exc

    in_components = False
    components: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_components = stripped == "## Signal Components"
            continue
        if not in_components:
            continue
        if not stripped.startswith("### Component:"):
            continue
        name = stripped.removeprefix("### Component:").strip()
        if not name:
            raise ValueError("signal component heading must include a name")
        normalized = " ".join(name.lower().split())
        if normalized in seen:
            raise ValueError(f"duplicate signal component: {name}")
        seen.add(normalized)
        components.append(name)

    if not components:
        raise ValueError("rationale.md must declare at least one signal component")
    return tuple(components)


def _current_commit(workdir: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=workdir,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _sha256_path(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def _tracked_worktree_dirty(workdir: Path) -> bool:
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=workdir,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(output.strip())


def _same_source_snapshot(row: ResultRow, snapshot: Mapping[str, str]) -> bool:
    return (
        row.strategy_sha256 == snapshot["strategy_sha256"]
        and row.experiment_sha256 == snapshot["experiment_sha256"]
        and row.protocol_sha256 == snapshot["protocol_sha256"]
        and row.rationale_sha256 == snapshot["rationale_sha256"]
    )


def _source_snapshot(
    root: Path,
    *,
    strategy_path: str | Path,
    experiment_path: str | Path,
    protocol_path: str | Path,
    rationale_path: str | Path,
) -> dict[str, str]:
    return {
        "strategy_sha256": _sha256_path(root / strategy_path),
        "experiment_sha256": _sha256_path(root / experiment_path),
        "protocol_sha256": _sha256_path(root / protocol_path),
        "rationale_sha256": _sha256_path(root / rationale_path),
    }


def _normalize_thesis_text(value: str) -> str:
    return " ".join(value.split())


def _bounds_sha256(experiment: ExperimentConfig) -> str:
    payload = {
        name: {"min": bound.min, "max": bound.max}
        for name, bound in sorted(experiment.bounds.items())
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _lock_path(root: Path) -> Path:
    return root / ".autoresearch" / "thesis_lock.json"


def _normalize_lock_path(root: Path, path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(root.resolve()).as_posix()
        except ValueError:
            return candidate.resolve().as_posix()
    return candidate.as_posix().removeprefix("./")


def _ensure_active_thesis_lock(
    root: Path,
    *,
    rows: Sequence[ResultRow],
    mechanism: str,
    falsifier: str,
    protocol_sha256: str,
    bounds_sha256: str,
    results_path: str | Path,
) -> None:
    lock_path = _lock_path(root)
    normalized_mechanism = _normalize_thesis_text(mechanism)
    normalized_falsifier = _normalize_thesis_text(falsifier)
    result_path_text = _normalize_lock_path(root, results_path)
    if not lock_path.exists():
        if rows:
            raise ValueError(
                "active thesis lock missing for existing results; start a new thesis lifecycle"
            )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "mechanism": normalized_mechanism,
            "falsifier": normalized_falsifier,
            "protocol_sha256": protocol_sha256,
            "bounds_sha256": bounds_sha256,
            "results_path": result_path_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return

    try:
        payload = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("active thesis lock is unreadable; start a new thesis lifecycle") from exc

    if payload.get("mechanism") != normalized_mechanism or payload.get("falsifier") != normalized_falsifier:
        raise ValueError("active thesis identity changed; start a new thesis lifecycle")
    if payload.get("protocol_sha256") != protocol_sha256:
        raise ValueError("active thesis protocol changed; start a new thesis lifecycle")
    if payload.get("bounds_sha256") != bounds_sha256:
        raise ValueError("active thesis bounds changed; start a new thesis lifecycle")
    if payload.get("results_path") != result_path_text:
        raise ValueError("active thesis results path changed; start a new thesis lifecycle")


def _ensure_can_attempt(rows: Sequence[ResultRow], snapshot: Mapping[str, str]) -> None:
    if not rows:
        return
    latest = rows[-1]
    if latest.continuation == "terminal":
        raise ValueError(f"thesis already stopped: {latest.stop_reason}")
    if latest.continuation == "repair_required" and _same_source_snapshot(latest, snapshot):
        raise ValueError("previous crash requires a source, params, protocol, or rationale repair")


def _default_runner(config_path, *, repo_root=None, event_sink=None):
    from quant_strategies.runner import run_config

    return run_config(config_path, repo_root=repo_root, event_sink=event_sink)


def _trades_from_result(result: object) -> tuple[TradeSample, ...]:
    economics = getattr(result, "economics", None)
    if economics is None:
        raise ValueError("run_config result missing economics")
    samples: list[TradeSample] = []
    for trade in getattr(economics, "trades", ()):
        samples.append(
            TradeSample(
                symbol=str(getattr(trade, "symbol")),
                decision_time=getattr(trade, "decision_time"),
                net_return=float(getattr(trade, "net_return")),
                weight=float(getattr(trade, "weight", 1.0)),
                gross_return=getattr(trade, "gross_return", None),
                cost_return=getattr(trade, "cost_return", None),
            )
        )
    return tuple(samples)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_window_end(value: str) -> datetime:
    parsed = _parse_time(value)
    if "T" not in value and " " not in value:
        return parsed + timedelta(days=1)
    return parsed


def _make_crash_row(
    *,
    provenance: AttemptProvenance,
    commit: str,
    iteration: int,
    params: Mapping[str, object],
    components: Sequence[str],
    elapsed_seconds: float,
    note: str,
    stop_reason: str,
) -> ResultRow:
    return ResultRow(
        run_id=provenance.run_id,
        commit=commit,
        artifact_dir=provenance.artifact_dir,
        worktree_dirty=provenance.worktree_dirty,
        strategy_sha256=provenance.strategy_sha256,
        experiment_sha256=provenance.experiment_sha256,
        protocol_sha256=provenance.protocol_sha256,
        rationale_sha256=provenance.rationale_sha256,
        quick_config_sha256=provenance.quick_config_sha256,
        iteration=iteration,
        score=None,
        gates_passed=False,
        gate_flags="run_config=fail",
        subwindow_trade_counts=(),
        trade_count=0,
        concentration=None,
        cost_stress=None,
        net_return_sum=None,
        avg_trade_net=None,
        win_rate=None,
        profit_factor=None,
        gross_return_sum=None,
        cost_return_sum=None,
        complexity_count=max(len(params), len(tuple(components))),
        status="crash",
        best_status="unchanged",
        continuation="terminal" if stop_reason else "repair_required",
        stop_reason=stop_reason,
        elapsed_seconds=elapsed_seconds,
        note=note,
    )


def _append_crash(*, results_path: str | Path, row: ResultRow) -> None:
    append_result(results_path, row)


def _profit_factor(trades: Sequence[TradeSample]) -> float | None:
    wins = sum(trade.net_return for trade in trades if trade.net_return > 0.0)
    losses = -sum(trade.net_return for trade in trades if trade.net_return < 0.0)
    if wins <= 0.0 and losses <= 0.0:
        return None
    if losses <= 0.0:
        return None
    return wins / losses


def _sum_optional(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))


def _non_improving_since_best(rows: Sequence[ResultRow]) -> int:
    kept_iterations = [row.iteration for row in rows if row.status == "keep"]
    if not kept_iterations:
        return 0
    last_keep = max(kept_iterations)
    return sum(1 for row in rows if row.iteration > last_keep)


def _stop_reason_after_attempt(
    rows: Sequence[ResultRow],
    *,
    gates: GateSet | None,
    loop_config,
) -> str:
    completed = len(rows)
    if gates is not None and not gates.by_name["complexity_cap"].passed:
        return "complexity_exhausted"
    has_keep = any(row.status == "keep" for row in rows)
    if not has_keep and completed >= loop_config.baseline_grace_iterations:
        return "baseline_failure"
    if has_keep and _non_improving_since_best(rows) >= loop_config.plateau_patience:
        return "plateau"
    if completed >= loop_config.max_iterations:
        return "max_iterations"
    return ""


def _best_row(rows: Sequence[ResultRow]) -> ResultRow | None:
    kept = [row for row in rows if row.status == "keep" and row.score is not None]
    if not kept:
        return None
    return max(kept, key=lambda row: row.score if row.score is not None else float("-inf"))


def _copy_if_present(source: Path, destination: Path) -> str | None:
    try:
        content = source.read_bytes()
    except OSError:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return str(destination)


def _attempt_snapshot_dir(root: Path, artifact_dir: str | Path) -> Path:
    return root / artifact_dir / "snapshot"


def _snapshot_paths_for_attempt(root: Path, row: ResultRow) -> dict[str, str] | None:
    snapshot_dir = _attempt_snapshot_dir(root, row.artifact_dir)
    paths = {
        "strategy": snapshot_dir / "strategy.py",
        "experiment": snapshot_dir / "experiment.toml",
        "protocol": snapshot_dir / "protocol.toml",
        "rationale": snapshot_dir / "rationale.md",
        "quick_config": snapshot_dir / "quick_config.toml",
    }
    if not all(path.exists() for path in paths.values()):
        return None
    return {name: str(path) for name, path in paths.items()}


def _write_attempt_snapshot(
    root: Path,
    *,
    run_id: str,
    artifact_dir: str | Path,
    strategy_path: str | Path = "strategy.py",
    protocol_path: str | Path = "protocol.toml",
    experiment_path: str | Path = "experiment.toml",
    rationale_path: str | Path = "rationale.md",
) -> dict[str, str]:
    snapshot_dir = _attempt_snapshot_dir(root, artifact_dir)
    paths = {
        "strategy": _copy_if_present(root / strategy_path, snapshot_dir / "strategy.py"),
        "experiment": _copy_if_present(root / experiment_path, snapshot_dir / "experiment.toml"),
        "protocol": _copy_if_present(root / protocol_path, snapshot_dir / "protocol.toml"),
        "rationale": _copy_if_present(root / rationale_path, snapshot_dir / "rationale.md"),
        "quick_config": _copy_if_present(
            root / ".autoresearch" / "quick" / f"{run_id}.toml",
            snapshot_dir / "quick_config.toml",
        ),
    }
    return {name: path for name, path in paths.items() if path is not None}


def _write_terminal_manifest(
    root: Path,
    *,
    row: ResultRow,
    rows: Sequence[ResultRow],
    strategy_path: str | Path = "strategy.py",
    protocol_path: str | Path = "protocol.toml",
    experiment_path: str | Path = "experiment.toml",
    rationale_path: str | Path = "rationale.md",
) -> None:
    best = _best_row(rows)
    status = "train_survivor" if best is not None else "train_failure"
    manifest_dir = root / row.artifact_dir
    terminal_snapshot = _snapshot_paths_for_attempt(root, row)
    if terminal_snapshot is None:
        terminal_snapshot = _write_attempt_snapshot(
            root,
            run_id=row.run_id,
            artifact_dir=row.artifact_dir,
            strategy_path=strategy_path,
            protocol_path=protocol_path,
            experiment_path=experiment_path,
            rationale_path=rationale_path,
        )
    best_snapshot = None if best is None else _snapshot_paths_for_attempt(root, best)
    snapshot_paths: dict[str, str | None] = dict(terminal_snapshot)
    if best is not None:
        snapshot_paths["best_quick_config"] = (
            None if best_snapshot is None else best_snapshot["quick_config"]
        )
        if snapshot_paths["best_quick_config"] is None:
            snapshot_paths["best_quick_config"] = _copy_if_present(
                root / ".autoresearch" / "quick" / f"{best.run_id}.toml",
                manifest_dir / "snapshot" / "best_quick_config.toml",
            )
    else:
        snapshot_paths["best_quick_config"] = None
    results_snapshot = _copy_if_present(
        root / "results.tsv",
        manifest_dir / "snapshot" / "results.tsv",
    )
    if best_snapshot is not None:
        best_snapshot = dict(best_snapshot)
    terminal_snapshot = dict(terminal_snapshot)
    if results_snapshot is not None:
        terminal_snapshot["results_tsv"] = results_snapshot
    if best_snapshot is not None and results_snapshot is not None:
        best_snapshot["results_tsv"] = results_snapshot
    destination = manifest_dir / "terminal_manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "stop_reason": row.stop_reason,
        "run_id": row.run_id,
        "attempt": row.as_record(),
        "best_attempt": None if best is None else best.as_record(),
        "snapshot_paths": snapshot_paths,
        "terminal_attempt_snapshot": terminal_snapshot,
        "best_survivor_snapshot": best_snapshot,
        "results_tsv": "results.tsv",
        "disclaimer": "Train evidence only; not OOS, paper, live, or deployability evidence.",
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run_iteration(
    protocol: ProtocolConfig,
    *,
    params: Mapping[str, object],
    components: Sequence[str],
    results_path: str | Path,
    iteration: int,
    best_score: float | None,
    runner: Runner | None = None,
    workdir: str | Path = ".",
    prior_rows: Sequence[ResultRow] = (),
    protocol_path: str | Path = "protocol.toml",
    experiment_path: str | Path = "experiment.toml",
    rationale_path: str | Path = "rationale.md",
) -> IterationOutcome:
    start = time.monotonic()
    root = Path(workdir)
    source_hashes = _source_snapshot(
        root,
        strategy_path=protocol.strategy_path,
        experiment_path=experiment_path,
        protocol_path=protocol_path,
        rationale_path=rationale_path,
    )
    _ensure_can_attempt(prior_rows, source_hashes)
    run_id = f"attempt-{iteration:04d}"
    run_dir = root / ".autoresearch" / "quick"
    config_path = run_dir / f"{run_id}.toml"
    artifact_dir = Path("results") / "autoresearch" / run_id
    write_quick_run_config(
        protocol,
        params,
        config_path,
        results_dir=artifact_dir,
    )
    provenance = AttemptProvenance(
        run_id=run_id,
        artifact_dir=str(artifact_dir),
        worktree_dirty=_tracked_worktree_dirty(root),
        quick_config_sha256=_sha256_path(config_path),
        **source_hashes,
    )
    _write_attempt_snapshot(
        root,
        run_id=provenance.run_id,
        artifact_dir=provenance.artifact_dir,
        strategy_path=protocol.strategy_path,
        protocol_path=protocol_path,
        experiment_path=experiment_path,
        rationale_path=rationale_path,
    )

    run = runner or _default_runner
    commit = _current_commit(root)
    try:
        result = run(config_path, repo_root=root)
    except Exception as exc:  # noqa: BLE001 - preserve attempted-iteration logging.
        elapsed = time.monotonic() - start
        stop_reason = _stop_reason_after_attempt(
            (
                *prior_rows,
                _make_crash_row(
                    provenance=provenance,
                    commit=commit,
                    iteration=iteration,
                    params=params,
                    components=components,
                    elapsed_seconds=elapsed,
                    note=str(exc),
                    stop_reason="",
                ),
            ),
            gates=None,
            loop_config=protocol.loop,
        )
        crash_row = _make_crash_row(
            provenance=provenance,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
            stop_reason=stop_reason,
        )
        _append_crash(
            results_path=results_path,
            row=crash_row,
        )
        row = read_results(results_path)[-1]
        if row.stop_reason:
            _write_terminal_manifest(
                root,
                row=row,
                rows=(*prior_rows, row),
                strategy_path=protocol.strategy_path,
                protocol_path=protocol_path,
                experiment_path=experiment_path,
                rationale_path=rationale_path,
            )
        return IterationOutcome(
            status="crash",
            score=None,
            gates_passed=False,
            gates=None,
            row=row,
            stop_reason=stop_reason,
            message=str(exc),
        )
    elapsed = time.monotonic() - start

    if not getattr(result, "succeeded", False):
        temp_row = _make_crash_row(
            provenance=provenance,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(getattr(result, "message", "run failed")),
            stop_reason="",
        )
        stop_reason = _stop_reason_after_attempt(
            (*prior_rows, temp_row),
            gates=None,
            loop_config=protocol.loop,
        )
        crash_row = _make_crash_row(
            provenance=provenance,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(getattr(result, "message", "run failed")),
            stop_reason=stop_reason,
        )
        _append_crash(
            results_path=results_path,
            row=crash_row,
        )
        row = read_results(results_path)[-1]
        if row.stop_reason:
            _write_terminal_manifest(
                root,
                row=row,
                rows=(*prior_rows, row),
                strategy_path=protocol.strategy_path,
                protocol_path=protocol_path,
                experiment_path=experiment_path,
                rationale_path=rationale_path,
            )
        return IterationOutcome(
            status="crash",
            score=None,
            gates_passed=False,
            gates=None,
            row=row,
            stop_reason=stop_reason,
            message=str(getattr(result, "message", "run failed")),
        )

    try:
        trades = _trades_from_result(result)
        window_start = _parse_time(protocol.data.start)
        window_end = _parse_window_end(protocol.data.end)
        objective = score_objective(
            trades,
            protocol.objective,
            window_start=window_start,
            window_end=window_end,
        )
        stress = score_cost_stress(
            trades,
            subwindows=protocol.objective.subwindows,
            extra_round_trip_bps=2.0
            * (
                protocol.cost_model.fee_bps_per_side
                + protocol.cost_model.slippage_bps_per_side
            ),
            window_start=window_start,
            window_end=window_end,
        )
    except Exception as exc:  # noqa: BLE001 - preserve attempted-iteration logging.
        temp_row = _make_crash_row(
            provenance=provenance,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
            stop_reason="",
        )
        stop_reason = _stop_reason_after_attempt(
            (*prior_rows, temp_row),
            gates=None,
            loop_config=protocol.loop,
        )
        crash_row = _make_crash_row(
            provenance=provenance,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
            stop_reason=stop_reason,
        )
        _append_crash(
            results_path=results_path,
            row=crash_row,
        )
        row = read_results(results_path)[-1]
        if row.stop_reason:
            _write_terminal_manifest(
                root,
                row=row,
                rows=(*prior_rows, row),
                strategy_path=protocol.strategy_path,
                protocol_path=protocol_path,
                experiment_path=experiment_path,
                rationale_path=rationale_path,
            )
        return IterationOutcome(
            status="crash",
            score=None,
            gates_passed=False,
            gates=None,
            row=row,
            stop_reason=stop_reason,
            message=str(exc),
        )
    cost_stress_score = stress.score
    gates = evaluate_gates(
        trades,
        params=params,
        components=components,
        config=protocol.gates,
        cost_stress_score=cost_stress_score,
        train_score=objective.score,
        subwindow_trade_counts=objective.subwindow_trade_counts,
    )
    keep = is_improvement(objective.score, best_score, gates.passed, protocol.loop)
    status = "keep" if keep else "discard"
    best_status = "updated" if keep else "unchanged"
    rows_for_stop = (
        *prior_rows,
        ResultRow(
            run_id=provenance.run_id,
            commit=commit,
            artifact_dir=provenance.artifact_dir,
            worktree_dirty=provenance.worktree_dirty,
            strategy_sha256=provenance.strategy_sha256,
            experiment_sha256=provenance.experiment_sha256,
            protocol_sha256=provenance.protocol_sha256,
            rationale_sha256=provenance.rationale_sha256,
            quick_config_sha256=provenance.quick_config_sha256,
            iteration=iteration,
            score=objective.score,
            gates_passed=gates.passed,
            gate_flags=gates.flags(),
            subwindow_trade_counts=objective.subwindow_trade_counts,
            trade_count=len(trades),
            concentration=symbol_concentration(trades) if trades else None,
            cost_stress=cost_stress_score,
            net_return_sum=float(sum(trade.net_return for trade in trades)) if trades else None,
            avg_trade_net=(
                float(sum(trade.net_return for trade in trades) / len(trades))
                if trades
                else None
            ),
            win_rate=(
                sum(1 for trade in trades if trade.net_return > 0.0) / len(trades)
                if trades
                else None
            ),
            profit_factor=_profit_factor(trades),
            gross_return_sum=_sum_optional(tuple(trade.gross_return for trade in trades)),
            cost_return_sum=_sum_optional(tuple(trade.cost_return for trade in trades)),
            complexity_count=max(len(params), len(tuple(components))),
            status=status,
            best_status=best_status,
            continuation="allowed",
            stop_reason="",
            elapsed_seconds=elapsed,
            note=objective.detail,
        ),
    )
    stop_reason = _stop_reason_after_attempt(
        rows_for_stop,
        gates=gates,
        loop_config=protocol.loop,
    )
    continuation = "terminal" if stop_reason else "allowed"
    append_result(
        results_path,
        ResultRow(
            run_id=provenance.run_id,
            commit=commit,
            artifact_dir=provenance.artifact_dir,
            worktree_dirty=provenance.worktree_dirty,
            strategy_sha256=provenance.strategy_sha256,
            experiment_sha256=provenance.experiment_sha256,
            protocol_sha256=provenance.protocol_sha256,
            rationale_sha256=provenance.rationale_sha256,
            quick_config_sha256=provenance.quick_config_sha256,
            iteration=iteration,
            score=objective.score,
            gates_passed=gates.passed,
            gate_flags=gates.flags(),
            subwindow_trade_counts=objective.subwindow_trade_counts,
            trade_count=len(trades),
            concentration=symbol_concentration(trades) if trades else None,
            cost_stress=cost_stress_score,
            net_return_sum=float(sum(trade.net_return for trade in trades)) if trades else None,
            avg_trade_net=(
                float(sum(trade.net_return for trade in trades) / len(trades))
                if trades
                else None
            ),
            win_rate=(
                sum(1 for trade in trades if trade.net_return > 0.0) / len(trades)
                if trades
                else None
            ),
            profit_factor=_profit_factor(trades),
            gross_return_sum=_sum_optional(tuple(trade.gross_return for trade in trades)),
            cost_return_sum=_sum_optional(tuple(trade.cost_return for trade in trades)),
            complexity_count=max(len(params), len(tuple(components))),
            status=status,
            best_status=best_status,
            continuation=continuation,
            stop_reason=stop_reason,
            elapsed_seconds=elapsed,
            note=objective.detail,
        ),
    )
    row = read_results(results_path)[-1]
    if row.stop_reason:
        _write_terminal_manifest(
            root,
            row=row,
            rows=(*prior_rows, row),
            strategy_path=protocol.strategy_path,
            protocol_path=protocol_path,
            experiment_path=experiment_path,
            rationale_path=rationale_path,
        )
    return IterationOutcome(
        status=status,
        score=objective.score,
        gates_passed=gates.passed,
        gates=gates,
        row=row,
        stop_reason=stop_reason,
    )


def run_status(
    *,
    protocol_path: str | Path = "protocol.toml",
    results_path: str | Path = "results.tsv",
) -> dict[str, object]:
    cfg = load_protocol(protocol_path)
    return status_summary(
        results_path,
        max_iterations=cfg.loop.max_iterations,
        plateau_patience=cfg.loop.plateau_patience,
        subwindows=cfg.objective.subwindows,
    )


def climb_once(
    *,
    protocol_path: str | Path = "protocol.toml",
    params_path: str | Path = "experiment.toml",
    results_path: str | Path = "results.tsv",
    mechanism: str,
    falsifier: str,
    components: Sequence[str] | None = None,
    runner: Runner | None = None,
) -> IterationOutcome:
    thesis_error = validate_thesis(mechanism, falsifier)
    if thesis_error is not None:
        raise ValueError(thesis_error)
    cfg = load_protocol(protocol_path)
    rows = read_results(results_path)
    snapshot = _source_snapshot(
        Path("."),
        strategy_path=cfg.strategy_path,
        experiment_path=params_path,
        protocol_path=protocol_path,
        rationale_path="rationale.md",
    )
    _ensure_can_attempt(rows, snapshot)
    experiment = load_experiment(params_path)
    declared_components = (
        tuple(components)
        if components is not None
        else components_from_rationale("rationale.md")
    )
    _ensure_active_thesis_lock(
        Path("."),
        rows=rows,
        mechanism=mechanism,
        falsifier=falsifier,
        protocol_sha256=snapshot["protocol_sha256"],
        bounds_sha256=_bounds_sha256(experiment),
        results_path=results_path,
    )
    params = experiment.params
    best_score = max(
        (row.score for row in rows if row.status == "keep" and row.score is not None),
        default=None,
    )
    return run_iteration(
        cfg,
        params=params,
        components=declared_components,
        results_path=results_path,
        iteration=len(rows) + 1,
        best_score=best_score,
        runner=runner,
        workdir=Path("."),
        prior_rows=rows,
        protocol_path=protocol_path,
        experiment_path=params_path,
        rationale_path="rationale.md",
    )


def _print_status(summary: Mapping[str, object]) -> None:
    for key, value in summary.items():
        print(f"{key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-autoresearch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    climb = subparsers.add_parser("climb")
    climb.add_argument("--mechanism", required=True)
    climb.add_argument("--falsifier", required=True)
    args = parser.parse_args(argv)

    if args.command == "status":
        _print_status(run_status())
        return 0
    if args.command == "climb":
        outcome = climb_once(mechanism=args.mechanism, falsifier=args.falsifier)
        if outcome.row is None:
            print(f"status: {outcome.status}")
            print(f"score: {outcome.score}")
        else:
            for key, value in outcome.row.as_record().items():
                print(f"{key}: {value}")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
