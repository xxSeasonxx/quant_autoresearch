from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import subprocess
import time
from typing import Callable, Mapping, Sequence

from gates import GateSet, evaluate_gates, symbol_concentration
from objective import TradeSample, is_improvement, score_cost_stress, score_objective
from protocol import ProtocolConfig, load_params, load_protocol, write_quick_run_config
from results_log import ResultRow, append_result, read_results, status_summary


Runner = Callable[..., object]


@dataclass(frozen=True)
class IterationOutcome:
    status: str
    score: float | None
    gates_passed: bool
    gates: GateSet | None
    stop_reason: str = ""
    message: str = ""


def validate_thesis(mechanism: str, falsifier: str) -> str | None:
    if not mechanism.strip():
        return "thesis mechanism is required"
    if not falsifier.strip():
        return "thesis falsifier is required"
    return None


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


def _default_runner(config_path, *, repo_root=None, event_sink=None):
    from quant_strategies.runner import run_config

    return run_config(config_path, repo_root=repo_root, event_sink=event_sink)


def _trades_from_result(result: object) -> tuple[TradeSample, ...]:
    economics = getattr(result, "economics", None)
    if economics is None:
        return ()
    samples: list[TradeSample] = []
    for trade in getattr(economics, "trades", ()):
        samples.append(
            TradeSample(
                symbol=str(getattr(trade, "symbol")),
                decision_time=getattr(trade, "decision_time"),
                net_return=float(getattr(trade, "net_return")),
                weight=float(getattr(trade, "weight", 1.0)),
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


def _append_crash(
    *,
    results_path: str | Path,
    commit: str,
    iteration: int,
    params: Mapping[str, object],
    components: Sequence[str],
    elapsed_seconds: float,
    note: str,
) -> None:
    append_result(
        results_path,
        ResultRow(
            commit=commit,
            iteration=iteration,
            score=None,
            gates_passed=False,
            gate_flags="run_config=fail",
            trade_count=0,
            concentration=None,
            cost_stress=None,
            complexity_count=max(len(params), len(tuple(components))),
            status="crash",
            stop_reason="",
            elapsed_seconds=elapsed_seconds,
            note=note,
        ),
    )


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
) -> IterationOutcome:
    start = time.monotonic()
    root = Path(workdir)
    run_dir = root / ".autoresearch" / "quick"
    config_path = run_dir / f"iteration_{iteration}.toml"
    write_quick_run_config(
        protocol,
        params,
        config_path,
        results_dir=Path("results") / "autoresearch" / f"iteration_{iteration}",
    )

    run = runner or _default_runner
    commit = _current_commit(root)
    try:
        result = run(config_path, repo_root=root)
    except Exception as exc:  # noqa: BLE001 - preserve attempted-iteration logging.
        elapsed = time.monotonic() - start
        _append_crash(
            results_path=results_path,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
        )
        return IterationOutcome(
            status="crash",
            score=None,
            gates_passed=False,
            gates=None,
            message=str(exc),
        )
    elapsed = time.monotonic() - start

    if not getattr(result, "succeeded", False):
        _append_crash(
            results_path=results_path,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(getattr(result, "message", "run failed")),
        )
        return IterationOutcome(
            status="crash",
            score=None,
            gates_passed=False,
            gates=None,
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
        _append_crash(
            results_path=results_path,
            commit=commit,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
        )
        return IterationOutcome(
            status="crash",
            score=None,
            gates_passed=False,
            gates=None,
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
    )
    keep = is_improvement(objective.score, best_score, gates.passed, protocol.loop)
    status = "keep" if keep else "discard"
    append_result(
        results_path,
        ResultRow(
            commit=commit,
            iteration=iteration,
            score=objective.score,
            gates_passed=gates.passed,
            gate_flags=gates.flags(),
            trade_count=len(trades),
            concentration=symbol_concentration(trades) if trades else None,
            cost_stress=cost_stress_score,
            complexity_count=max(len(params), len(tuple(components))),
            status=status,
            stop_reason="",
            elapsed_seconds=elapsed,
            note=objective.detail,
        ),
    )
    return IterationOutcome(
        status=status,
        score=objective.score,
        gates_passed=gates.passed,
        gates=gates,
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
    components: Sequence[str] = ("baseline",),
    runner: Runner | None = None,
) -> IterationOutcome:
    thesis_error = validate_thesis(mechanism, falsifier)
    if thesis_error is not None:
        raise ValueError(thesis_error)
    cfg = load_protocol(protocol_path)
    rows = read_results(results_path)
    best_score = max(
        (row.score for row in rows if row.status == "keep" and row.score is not None),
        default=None,
    )
    return run_iteration(
        cfg,
        params=load_params(params_path),
        components=components,
        results_path=results_path,
        iteration=len(rows) + 1,
        best_score=best_score,
        runner=runner,
        workdir=Path("."),
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
        print(f"status: {outcome.status}")
        print(f"score: {outcome.score}")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
