from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
from math import isfinite
import time
from typing import Callable, Mapping, Sequence

from gates import GateSet, evaluate_gates, symbol_concentration
from objective import (
    FoundationEvidence,
    FoundationMetric,
    FoundationScenario,
    FoundationSizing,
    ObjectiveResult,
    TradeSample,
    is_improvement,
    score_foundation_cost_stress,
    score_objective,
)
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


def _sha256_path(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def _snapshot_source_hashes(root: Path, row: ResultRow) -> dict[str, str] | None:
    """Recompute an attempt's source hashes from its preserved snapshot files.

    Provenance is no longer carried inline in `results.tsv`; the per-attempt
    snapshot copies the actual strategy/params/protocol/rationale, so the repair
    check rehashes those to decide whether a crashed attempt's source changed.
    Returns None when the snapshot is incomplete.
    """

    paths = _snapshot_paths_for_attempt(root, row)
    if paths is None:
        return None
    return {
        "strategy_sha256": _sha256_path(Path(paths["strategy"])),
        "experiment_sha256": _sha256_path(Path(paths["experiment"])),
        "protocol_sha256": _sha256_path(Path(paths["protocol"])),
        "rationale_sha256": _sha256_path(Path(paths["rationale"])),
    }


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


def _ensure_can_attempt(
    rows: Sequence[ResultRow], snapshot: Mapping[str, str], *, root: Path
) -> None:
    if not rows:
        return
    latest = rows[-1]
    if latest.continuation == "terminal":
        raise ValueError(f"thesis already stopped: {latest.stop_reason}")
    if latest.continuation == "repair_required":
        prior = _snapshot_source_hashes(root, latest)
        if prior is not None and prior == dict(snapshot):
            raise ValueError(
                "previous crash requires a source, params, protocol, or rationale repair"
            )


def _default_runner(config_path, *, repo_root=None, event_sink=None):
    from quant_strategies.runner import run_config

    return run_config(config_path, repo_root=repo_root, event_sink=event_sink)


def _trades_from_result(
    result: object,
    *,
    required: bool = True,
) -> tuple[TradeSample, ...]:
    economics = getattr(result, "economics", None)
    if economics is None:
        if not required:
            return ()
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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"expected numeric foundation value, got {value!r}")
    return float(value)


def _int_value(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected integer foundation value for {name}, got {value!r}")
    if value < 0:
        raise ValueError(f"foundation count {name} must be >= 0")
    return value


def _foundation_float(
    raw: Mapping[str, object],
    name: str,
    *,
    required: bool = False,
    nonfinite_as_none: bool = False,
) -> float | None:
    value = raw.get(name)
    if value is None:
        if required:
            raise ValueError(f"missing foundation value: {name}")
        return None
    parsed = _optional_float(value)
    if parsed is None:
        raise ValueError(f"missing foundation value: {name}")
    if not isfinite(parsed):
        if nonfinite_as_none:
            return None
        raise ValueError(f"non-finite foundation value: {name}")
    return parsed


def _foundation_count(raw: Mapping[str, object], name: str) -> int:
    if name not in raw:
        raise ValueError(f"missing foundation count: {name}")
    return _int_value(raw[name], name=name)


def _validate_foundation_metric(metric: FoundationMetric) -> None:
    if metric.effective_sample_size is not None and metric.effective_sample_size < 0.0:
        raise ValueError("foundation effective_sample_size must be >= 0")
    if metric.return_volatility is not None and metric.return_volatility < 0.0:
        raise ValueError("foundation return_volatility must be >= 0")
    if metric.max_drawdown is not None and metric.max_drawdown > 0.0:
        raise ValueError("foundation max_drawdown must be <= 0")
    concentration = metric.max_symbol_concentration
    if concentration is not None and not 0.0 <= concentration <= 1.0:
        raise ValueError("foundation max_symbol_concentration must be in [0, 1]")


def _warnings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError("foundation warnings must be a list")
    return tuple(str(item) for item in value)


def _foundation_metric(raw: Mapping[str, object]) -> FoundationMetric:
    metric = FoundationMetric(
        window_id=str(raw["window_id"]),
        return_sample_count=_foundation_count(raw, "return_sample_count"),
        effective_sample_size=_foundation_float(
            raw, "effective_sample_size", nonfinite_as_none=True
        ),
        mean_return=_foundation_float(raw, "mean_return", nonfinite_as_none=True),
        return_volatility=_foundation_float(
            raw, "return_volatility", nonfinite_as_none=True
        ),
        sharpe=_foundation_float(raw, "sharpe", nonfinite_as_none=True),
        sharpe_standard_error=_foundation_float(
            raw, "sharpe_standard_error", nonfinite_as_none=True
        ),
        total_return=_foundation_float(raw, "total_return", nonfinite_as_none=True),
        max_drawdown=_foundation_float(raw, "max_drawdown"),
        closed_trade_count=_foundation_count(raw, "closed_trade_count"),
        max_symbol_concentration=_foundation_float(raw, "max_symbol_concentration"),
        warnings=_warnings(raw.get("warnings")),
        max_gross_utilization=_foundation_float(raw, "max_gross_utilization"),
        max_net_utilization=_foundation_float(raw, "max_net_utilization"),
    )
    _validate_foundation_metric(metric)
    return metric


def _foundation_scenario(raw: Mapping[str, object]) -> FoundationScenario:
    subwindows = raw.get("subwindows", ())
    if not isinstance(subwindows, list):
        raise ValueError("portfolio foundation scenario missing subwindows")
    capacity = raw.get("capacity")
    capacity_map = capacity if isinstance(capacity, Mapping) else {}
    return FoundationScenario(
        scenario_id=str(raw["scenario_id"]),
        full_train=_foundation_metric(raw["full_train"]),  # type: ignore[arg-type]
        subwindows=tuple(
            _foundation_metric(item)  # type: ignore[arg-type]
            for item in subwindows
        ),
        max_adv_participation=_foundation_float(capacity_map, "max_adv_participation"),
        max_bar_participation=_foundation_float(capacity_map, "max_bar_participation"),
    )


def _foundation_sizing(raw: object) -> FoundationSizing:
    if not isinstance(raw, Mapping):
        raise ValueError("portfolio foundation payload missing sizing_report")
    periods = raw.get("annualization_periods_per_year")
    if isinstance(periods, bool) or not isinstance(periods, int) or periods <= 0:
        raise ValueError(
            "sizing_report annualization_periods_per_year must be a positive integer"
        )
    capacity_bound = raw.get("capacity_bound")
    if capacity_bound is not None and not isinstance(capacity_bound, bool):
        raise ValueError("sizing_report capacity_bound must be a boolean")
    return FoundationSizing(
        annualization_periods_per_year=periods,
        book_scale=_foundation_float(raw, "book_scale"),
        deployed_volatility=_foundation_float(raw, "deployed_volatility"),
        max_feasible_volatility=_foundation_float(raw, "max_feasible_volatility"),
        capacity_bound=capacity_bound,
    )


def _foundation_from_result(result: object) -> FoundationEvidence:
    foundation = getattr(result, "foundation", None)
    if foundation is None:
        raise ValueError("run_config result missing portfolio foundation")
    matrix_payload = foundation.matrix_payload()
    scenarios = matrix_payload.get("scenarios")
    if not isinstance(scenarios, dict):
        raise ValueError("portfolio foundation payload missing scenarios")
    try:
        realistic = scenarios["realistic_costs"]
        cost_stress = scenarios["cost_stress"]
    except KeyError as exc:
        raise ValueError(f"portfolio foundation missing scenario: {exc.args[0]}") from exc
    return FoundationEvidence(
        realistic_costs=_foundation_scenario(realistic),
        cost_stress=_foundation_scenario(cost_stress),
        sizing=_foundation_sizing(matrix_payload.get("sizing_report")),
    )


def _failure_reason(result: object) -> str:
    """Short typed reason for a non-scoreable run, for the results.tsv column.

    Prefers the engine's feasibility reason (e.g. `capacity_limit_breach`), then
    the failure stage (e.g. `strategy_import`); empty when neither is set.
    """

    feasibility = getattr(result, "feasibility", None)
    reason = getattr(feasibility, "reason", None) if feasibility is not None else None
    if reason:
        return str(reason)
    failure_stage = getattr(getattr(result, "outcome", None), "failure_stage", None)
    return str(failure_stage) if failure_stage else ""


def _make_crash_row(
    *,
    provenance: AttemptProvenance,
    iteration: int,
    params: Mapping[str, object],
    components: Sequence[str],
    elapsed_seconds: float,
    note: str,
    failure_reason: str,
    stop_reason: str,
) -> ResultRow:
    return ResultRow(
        run_id=provenance.run_id,
        iteration=iteration,
        status="crash",
        score=None,
        worst_window_id="",
        deflated_money_floor=None,
        full_train_annualized_return=None,
        worst_window_annualized_return=None,
        cost_stress_return_retention=None,
        book_scale=None,
        deployed_volatility=None,
        max_feasible_volatility=None,
        capacity_bound=None,
        full_train_psr=None,
        worst_subwindow_psr=None,
        gates_passed=False,
        gate_flags="run_config=fail",
        trade_count=0,
        min_subwindow_trades=0,
        total_return=None,
        max_drawdown=None,
        max_symbol_concentration=None,
        win_rate=None,
        profit_factor=None,
        avg_trade_net=None,
        cost_return_sum=None,
        complexity_count=max(len(params), len(tuple(components))),
        failure_reason=failure_reason,
        best_status="unchanged",
        continuation="terminal" if stop_reason else "repair_required",
        stop_reason=stop_reason,
        elapsed_seconds=elapsed_seconds,
        artifact_dir=provenance.artifact_dir,
        note=note,
    )


def _gate_value(gates: GateSet, name: str) -> float | None:
    outcome = gates.by_name.get(name)
    return None if outcome is None else outcome.value


def _scored_result_row(
    *,
    provenance: AttemptProvenance,
    iteration: int,
    objective: ObjectiveResult,
    sizing: FoundationSizing | None,
    gates: GateSet,
    trades: Sequence[TradeSample],
    foundation_scenario: FoundationScenario | None,
    params: Mapping[str, object],
    components: Sequence[str],
    status: str,
    best_status: str,
    continuation: str,
    stop_reason: str,
    elapsed_seconds: float,
) -> ResultRow:
    full = None if foundation_scenario is None else foundation_scenario.full_train
    return ResultRow(
        run_id=provenance.run_id,
        iteration=iteration,
        status=status,
        score=objective.score,
        worst_window_id=objective.worst_window_id,
        deflated_money_floor=_gate_value(gates, "money_floor"),
        full_train_annualized_return=objective.full_train_return,
        worst_window_annualized_return=objective.worst_window_return,
        cost_stress_return_retention=_gate_value(gates, "cost_stress_retention"),
        book_scale=None if sizing is None else sizing.book_scale,
        deployed_volatility=None if sizing is None else sizing.deployed_volatility,
        max_feasible_volatility=(
            None if sizing is None else sizing.max_feasible_volatility
        ),
        capacity_bound=None if sizing is None else sizing.capacity_bound,
        full_train_psr=objective.full_train_psr,
        worst_subwindow_psr=objective.worst_subwindow_psr,
        gates_passed=gates.passed,
        gate_flags=gates.flags(),
        trade_count=_reported_trade_count(trades, foundation_scenario),
        min_subwindow_trades=_min_subwindow_trades(objective),
        total_return=None if full is None else full.total_return,
        max_drawdown=None if full is None else full.max_drawdown,
        max_symbol_concentration=(
            symbol_concentration(trades)
            if foundation_scenario is None and trades
            else (None if full is None else full.max_symbol_concentration)
        ),
        win_rate=(
            sum(1 for trade in trades if trade.net_return > 0.0) / len(trades)
            if trades
            else None
        ),
        profit_factor=_profit_factor(trades),
        avg_trade_net=(
            float(sum(trade.net_return for trade in trades) / len(trades))
            if trades
            else None
        ),
        cost_return_sum=_sum_optional(tuple(trade.cost_return for trade in trades)),
        complexity_count=max(len(params), len(tuple(components))),
        failure_reason="",
        best_status=best_status,
        continuation=continuation,
        stop_reason=stop_reason,
        elapsed_seconds=elapsed_seconds,
        artifact_dir=provenance.artifact_dir,
        note=objective.detail,
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


def _min_subwindow_trades(objective: ObjectiveResult) -> int:
    return min(objective.subwindow_trade_counts, default=0)


def _reported_trade_count(
    trades: Sequence[TradeSample],
    foundation_scenario: FoundationScenario | None,
) -> int:
    if foundation_scenario is not None:
        return foundation_scenario.full_train.closed_trade_count
    return len(trades)


def _gate_records(gates: GateSet | None) -> list[dict[str, object]]:
    if gates is None:
        return []
    return [
        {
            "name": outcome.name,
            "passed": outcome.passed,
            "value": outcome.value,
            "threshold": outcome.threshold,
            "detail": outcome.detail,
        }
        for outcome in gates.outcomes
    ]


def _metric_payload(metric: FoundationMetric) -> dict[str, object]:
    return {
        "window_id": metric.window_id,
        "return_sample_count": metric.return_sample_count,
        "effective_sample_size": metric.effective_sample_size,
        "mean_return": metric.mean_return,
        "return_volatility": metric.return_volatility,
        "sharpe": metric.sharpe,
        "sharpe_standard_error": metric.sharpe_standard_error,
        "total_return": metric.total_return,
        "max_drawdown": metric.max_drawdown,
        "closed_trade_count": metric.closed_trade_count,
        "max_symbol_concentration": metric.max_symbol_concentration,
        "max_gross_utilization": metric.max_gross_utilization,
        "max_net_utilization": metric.max_net_utilization,
        "warnings": list(metric.warnings),
    }


def _scenario_payload(scenario: FoundationScenario | None) -> dict[str, object] | None:
    if scenario is None:
        return None
    return {
        "scenario_id": scenario.scenario_id,
        "full_train": _metric_payload(scenario.full_train),
        "subwindows": [_metric_payload(metric) for metric in scenario.subwindows],
        "max_adv_participation": scenario.max_adv_participation,
        "max_bar_participation": scenario.max_bar_participation,
    }


def _sizing_payload(foundation: FoundationEvidence | None) -> dict[str, object] | None:
    if foundation is None:
        return None
    sizing = foundation.sizing
    return {
        "annualization_periods_per_year": sizing.annualization_periods_per_year,
        "book_scale": sizing.book_scale,
        "deployed_volatility": sizing.deployed_volatility,
        "max_feasible_volatility": sizing.max_feasible_volatility,
        "capacity_bound": sizing.capacity_bound,
    }


def _window_return_payload(objective: ObjectiveResult | None) -> list[dict[str, object]]:
    if objective is None:
        return []
    return [
        {
            "window_id": window_id,
            "annualized_return": annualized,
            "standard_error": standard_error,
        }
        for window_id, annualized, standard_error in zip(
            objective.window_ids,
            objective.window_returns,
            objective.window_return_ses,
        )
    ]


def _causality_admissible(result: object) -> bool | None:
    """Upstream causality admissibility verdict for Train scoring.

    Modern upstream quick runs expose `evidence.causality_admissible` separately
    from `evidence.causality.verified`: micro replay can be admissible for Train
    scoring while still not retention-verified. Older result objects fall back to
    the verification bit.
    """

    evidence = getattr(result, "evidence", None)
    admissible = getattr(evidence, "causality_admissible", None)
    if isinstance(admissible, bool):
        return admissible
    causality = getattr(evidence, "causality", None)
    if causality is None:
        return None
    verified = getattr(causality, "verified", None)
    return verified if isinstance(verified, bool) else None


def _causality_payload(result: object) -> dict[str, object]:
    evidence = getattr(result, "evidence", None)
    causality = getattr(evidence, "causality", None)
    if causality is None:
        return {}
    return {
        "causality_check": getattr(causality, "causality_check", None),
        "admissible": _causality_admissible(result),
        "verified": getattr(causality, "verified", None),
        "replay_warning": getattr(causality, "replay_warning", None),
        "timed_out": getattr(causality, "timed_out", None),
        "selected_probe_count": getattr(causality, "selected_probe_count", None),
    }


def _feasibility_note(result: object) -> str:
    """Summarize why a non-succeeded run is non-scoreable.

    An infeasible run is no score, not a low score. The upstream verdict is typed:
    `result.outcome.failure_stage` (e.g. "feasibility") plus, on an envelope breach,
    `result.feasibility.{reason, observed_gross, observed_net, detail}`. Surface those
    so the next edit responds to the reason (`capacity_unpriced` → price capacity,
    `leverage_budget_breach` → reduce intended gross) instead of only the message.
    """

    message = str(getattr(result, "message", "run failed"))
    outcome = getattr(result, "outcome", None)
    failure_stage = getattr(outcome, "failure_stage", None)
    feasibility = getattr(result, "feasibility", None)
    parts: list[str] = []
    if failure_stage:
        parts.append(f"failure_stage={failure_stage}")
    if feasibility is not None:
        reason = getattr(feasibility, "reason", None)
        if reason:
            parts.append(f"feasibility={reason}")
        for name in ("observed_gross", "observed_net"):
            value = getattr(feasibility, name, None)
            if value is not None:
                parts.append(f"{name}={value}")
        detail = getattr(feasibility, "detail", None)
        if detail:
            parts.append(str(detail))
    if not parts:
        return message
    return f"{message} :: {'; '.join(parts)}"


def _primary_failure_mode(
    gates: GateSet | None,
    objective: ObjectiveResult | None,
    *,
    error: str = "",
) -> str:
    if "portfolio foundation" in error:
        return "foundation_unavailable"
    if error and objective is None and gates is None:
        return "run_error"
    if objective is not None and objective.score is None:
        return "score_unavailable"
    if gates is None:
        return ""
    failed = [outcome.name for outcome in gates.outcomes if not outcome.passed]
    return failed[0] if failed else ""


def _write_run_card(
    root: Path,
    *,
    artifact_dir: str | Path,
    result: object | None,
    objective: ObjectiveResult | None,
    cost_stress: ObjectiveResult | None,
    gates: GateSet | None,
    foundation: FoundationEvidence | None,
    error: str = "",
) -> None:
    destination = root / artifact_dir / "run_card.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "score": None if objective is None else objective.score,
        "score_parts": {
            "worst_window_id": "" if objective is None else objective.worst_window_id,
            "full_train_annualized_return": None
            if objective is None
            else objective.full_train_return,
            "worst_window_annualized_return": None
            if objective is None
            else objective.worst_window_return,
            "deflated_money_floor": _gate_value(gates, "money_floor")
            if gates is not None
            else None,
            "cost_stress_return_retention": _gate_value(gates, "cost_stress_retention")
            if gates is not None
            else None,
            "windows": _window_return_payload(objective),
            "cost_stress_full_train_annualized_return": None
            if cost_stress is None
            else cost_stress.full_train_return,
            "diagnostics": {
                "full_train_psr": None if objective is None else objective.full_train_psr,
                "subwindow_psrs": []
                if objective is None
                else list(objective.subwindow_psrs),
                "worst_subwindow_psr": None
                if objective is None
                else objective.worst_subwindow_psr,
                "worst_subwindow_id": ""
                if objective is None
                else objective.worst_subwindow_id,
                "cost_stress_score": None if cost_stress is None else cost_stress.score,
            },
        },
        "sizing_report": _sizing_payload(foundation),
        "gates": _gate_records(gates),
        "foundation": {
            "realistic_costs": None
            if foundation is None
            else _scenario_payload(foundation.realistic_costs),
            "cost_stress": None
            if foundation is None
            else _scenario_payload(foundation.cost_stress),
        },
        "causality": {} if result is None else _causality_payload(result),
        "primary_failure_mode": _primary_failure_mode(gates, objective, error=error),
        "error": error,
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


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


def _finalize_crash(
    root: Path,
    *,
    results_path: str | Path,
    prior_rows: Sequence[ResultRow],
    loop_config,
    provenance: AttemptProvenance,
    iteration: int,
    params: Mapping[str, object],
    components: Sequence[str],
    elapsed_seconds: float,
    note: str,
    failure_reason: str,
    result: object | None,
    objective: ObjectiveResult | None,
    cost_stress: ObjectiveResult | None,
    gates: GateSet | None,
    foundation: FoundationEvidence | None,
    strategy_path: str | Path,
    protocol_path: str | Path,
    experiment_path: str | Path,
    rationale_path: str | Path,
) -> IterationOutcome:
    _write_run_card(
        root,
        artifact_dir=provenance.artifact_dir,
        result=result,
        objective=objective,
        cost_stress=cost_stress,
        gates=gates,
        foundation=foundation,
        error=note,
    )
    temp_row = _make_crash_row(
        provenance=provenance,
        iteration=iteration,
        params=params,
        components=components,
        elapsed_seconds=elapsed_seconds,
        note=note,
        failure_reason=failure_reason,
        stop_reason="",
    )
    stop_reason = _stop_reason_after_attempt(
        (*prior_rows, temp_row),
        gates=None,
        loop_config=loop_config,
    )
    crash_row = _make_crash_row(
        provenance=provenance,
        iteration=iteration,
        params=params,
        components=components,
        elapsed_seconds=elapsed_seconds,
        note=note,
        failure_reason=failure_reason,
        stop_reason=stop_reason,
    )
    _append_crash(results_path=results_path, row=crash_row)
    row = read_results(results_path)[-1]
    if row.stop_reason:
        _write_terminal_manifest(
            root,
            row=row,
            rows=(*prior_rows, row),
            strategy_path=strategy_path,
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
        message=note,
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
    _ensure_can_attempt(prior_rows, source_hashes, root=root)
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
    # The runner resolves the config's relative `strategy_path` against the config
    # file's own directory, so the strategy must sit beside the written quick config.
    _copy_if_present(root / protocol.strategy_path, config_path.parent / protocol.strategy_path)
    provenance = AttemptProvenance(
        run_id=run_id,
        artifact_dir=str(artifact_dir),
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
    try:
        result = run(config_path, repo_root=root)
    except Exception as exc:  # noqa: BLE001 - preserve attempted-iteration logging.
        elapsed = time.monotonic() - start
        return _finalize_crash(
            root,
            results_path=results_path,
            prior_rows=prior_rows,
            loop_config=protocol.loop,
            provenance=provenance,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
            failure_reason="",
            result=None,
            objective=None,
            cost_stress=None,
            gates=None,
            foundation=None,
            strategy_path=protocol.strategy_path,
            protocol_path=protocol_path,
            experiment_path=experiment_path,
            rationale_path=rationale_path,
        )
    elapsed = time.monotonic() - start

    if not getattr(result, "succeeded", False):
        return _finalize_crash(
            root,
            results_path=results_path,
            prior_rows=prior_rows,
            loop_config=protocol.loop,
            provenance=provenance,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=_feasibility_note(result),
            failure_reason=_failure_reason(result),
            result=result,
            objective=None,
            cost_stress=None,
            gates=None,
            foundation=None,
            strategy_path=protocol.strategy_path,
            protocol_path=protocol_path,
            experiment_path=experiment_path,
            rationale_path=rationale_path,
        )

    foundation: FoundationEvidence | None = None
    objective: ObjectiveResult | None = None
    stress: ObjectiveResult | None = None
    try:
        foundation = _foundation_from_result(result)
        trades = _trades_from_result(result, required=False)
        objective = score_objective(trades, protocol.objective, foundation=foundation)
        stress = score_foundation_cost_stress(foundation, protocol.objective)
    except Exception as exc:  # noqa: BLE001 - preserve attempted-iteration logging.
        return _finalize_crash(
            root,
            results_path=results_path,
            prior_rows=prior_rows,
            loop_config=protocol.loop,
            provenance=provenance,
            iteration=iteration,
            params=params,
            components=components,
            elapsed_seconds=elapsed,
            note=str(exc),
            failure_reason="",
            result=result,
            objective=objective,
            cost_stress=stress,
            gates=None,
            foundation=foundation,
            strategy_path=protocol.strategy_path,
            protocol_path=protocol_path,
            experiment_path=experiment_path,
            rationale_path=rationale_path,
        )
    foundation_scenario = None if foundation is None else foundation.realistic_costs
    sizing = None if foundation is None else foundation.sizing
    gates = evaluate_gates(
        trades,
        params=params,
        components=components,
        config=protocol.gates,
        objective=objective,
        cost_stress_full_train_return=stress.full_train_return,
        causality_admissible=_causality_admissible(result),
        foundation_scenario=foundation_scenario,
    )
    _write_run_card(
        root,
        artifact_dir=provenance.artifact_dir,
        result=result,
        objective=objective,
        cost_stress=stress,
        gates=gates,
        foundation=foundation,
    )
    keep = is_improvement(objective.score, best_score, gates.passed, protocol.loop)
    status = "keep" if keep else "discard"
    best_status = "updated" if keep else "unchanged"
    rows_for_stop = (
        *prior_rows,
        _scored_result_row(
            provenance=provenance,
            iteration=iteration,
            objective=objective,
            sizing=sizing,
            gates=gates,
            trades=trades,
            foundation_scenario=foundation_scenario,
            params=params,
            components=components,
            status=status,
            best_status=best_status,
            continuation="allowed",
            stop_reason="",
            elapsed_seconds=elapsed,
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
        _scored_result_row(
            provenance=provenance,
            iteration=iteration,
            objective=objective,
            sizing=sizing,
            gates=gates,
            trades=trades,
            foundation_scenario=foundation_scenario,
            params=params,
            components=components,
            status=status,
            best_status=best_status,
            continuation=continuation,
            stop_reason=stop_reason,
            elapsed_seconds=elapsed,
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
    _ensure_can_attempt(rows, snapshot, root=Path("."))
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
