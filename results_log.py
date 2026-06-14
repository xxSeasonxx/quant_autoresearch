from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


@dataclass(frozen=True)
class ResultRow:
    run_id: str
    iteration: int
    status: str
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
    max_symbol_concentration: float | None
    max_gross_utilization: float | None
    max_net_utilization: float | None
    max_adv_participation: float | None
    max_bar_participation: float | None
    win_rate: float | None
    profit_factor: float | None
    avg_trade_net: float | None
    cost_return_sum: float | None
    complexity_count: int
    failure_reason: str
    best_status: str
    continuation: str
    stop_reason: str
    elapsed_seconds: float
    artifact_dir: str
    note: str

    @staticmethod
    def header() -> list[str]:
        return [
            "run_id",
            "iteration",
            "status",
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
            "max_symbol_concentration",
            "max_gross_utilization",
            "max_net_utilization",
            "max_adv_participation",
            "max_bar_participation",
            "win_rate",
            "profit_factor",
            "avg_trade_net",
            "cost_return_sum",
            "complexity_count",
            "failure_reason",
            "best_status",
            "continuation",
            "stop_reason",
            "elapsed_seconds",
            "artifact_dir",
            "note",
        ]

    def as_record(self) -> dict[str, str]:
        def optional(value: float | None) -> str:
            return "" if value is None else str(value)

        return {
            "run_id": self.run_id,
            "iteration": str(self.iteration),
            "status": self.status,
            "score": optional(self.score),
            "full_train_psr": optional(self.full_train_psr),
            "worst_subwindow_psr": optional(self.worst_subwindow_psr),
            "worst_subwindow_id": self.worst_subwindow_id,
            "cost_stress_psr": optional(self.cost_stress_psr),
            "gates_passed": "true" if self.gates_passed else "false",
            "gate_flags": self.gate_flags,
            "trade_count": str(self.trade_count),
            "min_subwindow_trades": str(self.min_subwindow_trades),
            "total_return": optional(self.total_return),
            "max_drawdown": optional(self.max_drawdown),
            "max_symbol_concentration": optional(self.max_symbol_concentration),
            "max_gross_utilization": optional(self.max_gross_utilization),
            "max_net_utilization": optional(self.max_net_utilization),
            "max_adv_participation": optional(self.max_adv_participation),
            "max_bar_participation": optional(self.max_bar_participation),
            "win_rate": optional(self.win_rate),
            "profit_factor": optional(self.profit_factor),
            "avg_trade_net": optional(self.avg_trade_net),
            "cost_return_sum": optional(self.cost_return_sum),
            "complexity_count": str(self.complexity_count),
            "failure_reason": self.failure_reason,
            "best_status": self.best_status,
            "continuation": self.continuation,
            "stop_reason": self.stop_reason,
            "elapsed_seconds": str(self.elapsed_seconds),
            "artifact_dir": self.artifact_dir,
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


def _parse_row(row: dict[str, str]) -> ResultRow:
    missing = set(ResultRow.header()) - set(row)
    if missing:
        fields = ", ".join(sorted(missing))
        raise ValueError(f"results row is missing required fields: {fields}")
    return ResultRow(
        run_id=row["run_id"],
        iteration=int(row["iteration"]),
        status=_parse_enum(
            row["status"], name="status", allowed={"keep", "discard", "crash"}
        ),
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
        max_symbol_concentration=_parse_float(row["max_symbol_concentration"]),
        max_gross_utilization=_parse_float(row["max_gross_utilization"]),
        max_net_utilization=_parse_float(row["max_net_utilization"]),
        max_adv_participation=_parse_float(row["max_adv_participation"]),
        max_bar_participation=_parse_float(row["max_bar_participation"]),
        win_rate=_parse_float(row["win_rate"]),
        profit_factor=_parse_float(row["profit_factor"]),
        avg_trade_net=_parse_float(row["avg_trade_net"]),
        cost_return_sum=_parse_float(row["cost_return_sum"]),
        complexity_count=int(row["complexity_count"]),
        failure_reason=row["failure_reason"],
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
        artifact_dir=row["artifact_dir"],
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
