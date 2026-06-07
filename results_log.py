from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


@dataclass(frozen=True)
class ResultRow:
    commit: str
    iteration: int
    score: float | None
    gates_passed: bool
    gate_flags: str
    trade_count: int
    concentration: float | None
    cost_stress: float | None
    complexity_count: int
    status: str
    stop_reason: str
    elapsed_seconds: float
    note: str

    @staticmethod
    def header() -> list[str]:
        return [
            "commit",
            "iteration",
            "score",
            "gates_passed",
            "gate_flags",
            "trade_count",
            "concentration",
            "cost_stress",
            "complexity_count",
            "status",
            "stop_reason",
            "elapsed_seconds",
            "note",
        ]

    def as_record(self) -> dict[str, str]:
        return {
            "commit": self.commit,
            "iteration": str(self.iteration),
            "score": "" if self.score is None else str(self.score),
            "gates_passed": "true" if self.gates_passed else "false",
            "gate_flags": self.gate_flags,
            "trade_count": str(self.trade_count),
            "concentration": "" if self.concentration is None else str(self.concentration),
            "cost_stress": "" if self.cost_stress is None else str(self.cost_stress),
            "complexity_count": str(self.complexity_count),
            "status": self.status,
            "stop_reason": self.stop_reason,
            "elapsed_seconds": str(self.elapsed_seconds),
            "note": self.note,
        }


def _parse_float(value: str) -> float | None:
    return None if value == "" else float(value)


def _parse_row(row: dict[str, str]) -> ResultRow:
    return ResultRow(
        commit=row["commit"],
        iteration=int(row["iteration"]),
        score=_parse_float(row["score"]),
        gates_passed=row["gates_passed"] == "true",
        gate_flags=row["gate_flags"],
        trade_count=int(row["trade_count"]),
        concentration=_parse_float(row["concentration"]),
        cost_stress=_parse_float(row["cost_stress"]),
        complexity_count=int(row["complexity_count"]),
        status=row["status"],
        stop_reason=row["stop_reason"],
        elapsed_seconds=float(row["elapsed_seconds"]),
        note=row["note"],
    )


def append_result(path: str | Path, row: ResultRow) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not destination.exists() or destination.stat().st_size == 0
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
        return [_parse_row(row) for row in csv.DictReader(handle, dialect="excel-tab")]


def status_summary(
    path: str | Path,
    *,
    max_iterations: int,
    plateau_patience: int,
    subwindows: int,
) -> dict[str, object]:
    rows = read_results(path)
    kept = [row for row in rows if row.status == "keep" and row.score is not None]
    best = max((row.score for row in kept), default=None)
    stop_reason = next((row.stop_reason for row in reversed(rows) if row.stop_reason), "")
    return {
        "attempts": len(rows),
        "best_score": best,
        "last_status": rows[-1].status if rows else "not_started",
        "stop_reason": stop_reason,
        "max_iterations": max_iterations,
        "remaining_iterations": max(0, max_iterations - len(rows)),
        "plateau_patience": plateau_patience,
        "subwindows": subwindows,
    }

