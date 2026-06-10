from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re


@dataclass(frozen=True)
class ResultRow:
    run_id: str
    commit: str
    artifact_dir: str
    worktree_dirty: bool
    strategy_sha256: str
    experiment_sha256: str
    protocol_sha256: str
    rationale_sha256: str
    quick_config_sha256: str
    iteration: int
    score: float | None
    full_train_psr: float | None
    worst_subwindow_psr: float | None
    worst_subwindow_id: str
    cost_stress_psr: float | None
    gates_passed: bool
    gate_flags: str
    trade_count: int
    min_subwindow_trades: int
    total_return: float | None
    max_drawdown: float | None
    win_rate: float | None
    profit_factor: float | None
    avg_trade_net: float | None
    cost_return_sum: float | None
    max_symbol_concentration: float | None
    complexity_count: int
    status: str
    best_status: str
    continuation: str
    stop_reason: str
    elapsed_seconds: float
    note: str

    @staticmethod
    def header() -> list[str]:
        return [
            "run_id",
            "commit",
            "artifact_dir",
            "worktree_dirty",
            "strategy_sha256",
            "experiment_sha256",
            "protocol_sha256",
            "rationale_sha256",
            "quick_config_sha256",
            "iteration",
            "score",
            "full_train_psr",
            "worst_subwindow_psr",
            "worst_subwindow_id",
            "cost_stress_psr",
            "gates_passed",
            "gate_flags",
            "trade_count",
            "min_subwindow_trades",
            "total_return",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "avg_trade_net",
            "cost_return_sum",
            "max_symbol_concentration",
            "complexity_count",
            "status",
            "best_status",
            "continuation",
            "stop_reason",
            "elapsed_seconds",
            "note",
        ]

    def as_record(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "commit": self.commit,
            "artifact_dir": self.artifact_dir,
            "worktree_dirty": "true" if self.worktree_dirty else "false",
            "strategy_sha256": self.strategy_sha256,
            "experiment_sha256": self.experiment_sha256,
            "protocol_sha256": self.protocol_sha256,
            "rationale_sha256": self.rationale_sha256,
            "quick_config_sha256": self.quick_config_sha256,
            "iteration": str(self.iteration),
            "score": "" if self.score is None else str(self.score),
            "full_train_psr": ""
            if self.full_train_psr is None
            else str(self.full_train_psr),
            "worst_subwindow_psr": ""
            if self.worst_subwindow_psr is None
            else str(self.worst_subwindow_psr),
            "worst_subwindow_id": self.worst_subwindow_id,
            "cost_stress_psr": ""
            if self.cost_stress_psr is None
            else str(self.cost_stress_psr),
            "gates_passed": "true" if self.gates_passed else "false",
            "gate_flags": self.gate_flags,
            "trade_count": str(self.trade_count),
            "min_subwindow_trades": str(self.min_subwindow_trades),
            "total_return": ""
            if self.total_return is None
            else str(self.total_return),
            "max_drawdown": ""
            if self.max_drawdown is None
            else str(self.max_drawdown),
            "win_rate": "" if self.win_rate is None else str(self.win_rate),
            "profit_factor": ""
            if self.profit_factor is None
            else str(self.profit_factor),
            "avg_trade_net": ""
            if self.avg_trade_net is None
            else str(self.avg_trade_net),
            "cost_return_sum": ""
            if self.cost_return_sum is None
            else str(self.cost_return_sum),
            "max_symbol_concentration": ""
            if self.max_symbol_concentration is None
            else str(self.max_symbol_concentration),
            "complexity_count": str(self.complexity_count),
            "status": self.status,
            "best_status": self.best_status,
            "continuation": self.continuation,
            "stop_reason": self.stop_reason,
            "elapsed_seconds": str(self.elapsed_seconds),
            "note": self.note,
        }


def _parse_float(value: str) -> float | None:
    return None if value == "" else float(value)


def _parse_bool(value: str, *, name: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{name} must be true or false")


def _parse_enum(value: str, *, name: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}")
    return value


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _parse_hash(value: str, *, name: str) -> str:
    if value == "missing" or _HASH_RE.fullmatch(value):
        return value
    raise ValueError(f"{name} must be a 64-character lowercase hex hash or missing")


def _parse_row(row: dict[str, str]) -> ResultRow:
    missing = set(ResultRow.header()) - set(row)
    if missing:
        fields = ", ".join(sorted(missing))
        raise ValueError(f"results row is missing required fields: {fields}")
    return ResultRow(
        run_id=row["run_id"],
        commit=row["commit"],
        artifact_dir=row["artifact_dir"],
        worktree_dirty=_parse_bool(row["worktree_dirty"], name="worktree_dirty"),
        strategy_sha256=_parse_hash(row["strategy_sha256"], name="strategy_sha256"),
        experiment_sha256=_parse_hash(
            row["experiment_sha256"], name="experiment_sha256"
        ),
        protocol_sha256=_parse_hash(row["protocol_sha256"], name="protocol_sha256"),
        rationale_sha256=_parse_hash(row["rationale_sha256"], name="rationale_sha256"),
        quick_config_sha256=_parse_hash(
            row["quick_config_sha256"], name="quick_config_sha256"
        ),
        iteration=int(row["iteration"]),
        score=_parse_float(row["score"]),
        full_train_psr=_parse_float(row["full_train_psr"]),
        worst_subwindow_psr=_parse_float(row["worst_subwindow_psr"]),
        worst_subwindow_id=row["worst_subwindow_id"],
        cost_stress_psr=_parse_float(row["cost_stress_psr"]),
        gates_passed=_parse_bool(row["gates_passed"], name="gates_passed"),
        gate_flags=row["gate_flags"],
        trade_count=int(row["trade_count"]),
        min_subwindow_trades=int(row["min_subwindow_trades"]),
        total_return=_parse_float(row["total_return"]),
        max_drawdown=_parse_float(row["max_drawdown"]),
        win_rate=_parse_float(row["win_rate"]),
        profit_factor=_parse_float(row["profit_factor"]),
        avg_trade_net=_parse_float(row["avg_trade_net"]),
        cost_return_sum=_parse_float(row["cost_return_sum"]),
        max_symbol_concentration=_parse_float(row["max_symbol_concentration"]),
        complexity_count=int(row["complexity_count"]),
        status=_parse_enum(
            row["status"], name="status", allowed={"keep", "discard", "crash"}
        ),
        best_status=_parse_enum(
            row["best_status"],
            name="best_status",
            allowed={"updated", "unchanged"},
        ),
        continuation=_parse_enum(
            row["continuation"],
            name="continuation",
            allowed={"allowed", "repair_required", "terminal"},
        ),
        stop_reason=row["stop_reason"],
        elapsed_seconds=float(row["elapsed_seconds"]),
        note=row["note"],
    )


def _validate_result_chain(rows: list[ResultRow]) -> None:
    seen_run_ids: set[str] = set()
    seen_iterations: set[int] = set()
    for index, row in enumerate(rows):
        if row.iteration <= 0:
            raise ValueError("iteration must be > 0")
        if row.run_id in seen_run_ids:
            raise ValueError(f"duplicate run_id: {row.run_id}")
        if row.iteration in seen_iterations:
            raise ValueError(f"duplicate iteration: {row.iteration}")
        seen_run_ids.add(row.run_id)
        seen_iterations.add(row.iteration)
        expected_run_id = f"attempt-{row.iteration:04d}"
        if row.run_id != expected_run_id:
            raise ValueError(f"run_id must match iteration: expected {expected_run_id}")
        if row.continuation == "terminal" and index != len(rows) - 1:
            raise ValueError("terminal continuation row must be last")

    expected_iterations = list(range(1, len(rows) + 1))
    actual_iterations = [row.iteration for row in rows]
    if actual_iterations != expected_iterations:
        raise ValueError("result iterations must be contiguous from 1")


def _existing_header_and_has_rows(path: Path) -> tuple[list[str], bool]:
    with path.open(newline="") as handle:
        reader = csv.reader(handle, dialect="excel-tab")
        try:
            header = next(reader)
        except StopIteration:
            return [], False
        return header, any(any(cell != "" for cell in row) for row in reader)


def _ensure_writable_schema(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return True
    header, has_rows = _existing_header_and_has_rows(path)
    if header == ResultRow.header():
        return False
    if has_rows:
        raise ValueError(
            "legacy results.tsv schema with existing rows; start a new thesis lifecycle"
        )
    path.write_text("")
    return True


def append_result(path: str | Path, row: ResultRow) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    needs_header = _ensure_writable_schema(destination)
    with destination.open("a", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ResultRow.header(),
            dialect="excel-tab",
            lineterminator="\n",
        )
        if needs_header:
            writer.writeheader()
        writer.writerow(row.as_record())


def read_results(path: str | Path) -> list[ResultRow]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle, dialect="excel-tab")
        raw_rows = list(reader)
    if reader.fieldnames != ResultRow.header():
        if not raw_rows:
            return []
        raise ValueError(
            "legacy results.tsv schema with existing rows; start a new thesis lifecycle"
        )
    rows = [_parse_row(row) for row in raw_rows]
    _validate_result_chain(rows)
    return rows


def status_summary(
    path: str | Path,
    *,
    max_iterations: int,
    plateau_patience: int,
    subwindows: int,
) -> dict[str, object]:
    rows = read_results(path)
    kept = [row for row in rows if row.status == "keep" and row.score is not None]
    kept_scores = [row.score for row in kept if row.score is not None]
    best = max(kept_scores, default=None)
    best_row = max(
        kept,
        key=lambda row: row.score if row.score is not None else float("-inf"),
        default=None,
    )
    stop_reason = next(
        (row.stop_reason for row in reversed(rows) if row.stop_reason), ""
    )
    continuation = rows[-1].continuation if rows else "allowed"
    return {
        "attempts": len(rows),
        "best_score": best,
        "best_run_id": None if best_row is None else best_row.run_id,
        "last_status": rows[-1].status if rows else "not_started",
        "continuation": continuation,
        "stop_reason": stop_reason,
        "max_iterations": max_iterations,
        "remaining_iterations": max(0, max_iterations - len(rows)),
        "plateau_patience": plateau_patience,
        "subwindows": subwindows,
    }
