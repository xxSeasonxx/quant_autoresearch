from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


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
    gates_passed: bool
    gate_flags: str
    subwindow_trade_counts: tuple[int, ...]
    trade_count: int
    concentration: float | None
    cost_stress: float | None
    net_return_sum: float | None
    avg_trade_net: float | None
    win_rate: float | None
    profit_factor: float | None
    gross_return_sum: float | None
    cost_return_sum: float | None
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
            "gates_passed",
            "gate_flags",
            "subwindow_trade_counts",
            "trade_count",
            "concentration",
            "cost_stress",
            "net_return_sum",
            "avg_trade_net",
            "win_rate",
            "profit_factor",
            "gross_return_sum",
            "cost_return_sum",
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
            "gates_passed": "true" if self.gates_passed else "false",
            "gate_flags": self.gate_flags,
            "subwindow_trade_counts": ",".join(
                str(count) for count in self.subwindow_trade_counts
            ),
            "trade_count": str(self.trade_count),
            "concentration": "" if self.concentration is None else str(self.concentration),
            "cost_stress": "" if self.cost_stress is None else str(self.cost_stress),
            "net_return_sum": "" if self.net_return_sum is None else str(self.net_return_sum),
            "avg_trade_net": "" if self.avg_trade_net is None else str(self.avg_trade_net),
            "win_rate": "" if self.win_rate is None else str(self.win_rate),
            "profit_factor": "" if self.profit_factor is None else str(self.profit_factor),
            "gross_return_sum": "" if self.gross_return_sum is None else str(self.gross_return_sum),
            "cost_return_sum": "" if self.cost_return_sum is None else str(self.cost_return_sum),
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


def _parse_counts(value: str) -> tuple[int, ...]:
    if value == "":
        return ()
    return tuple(int(item) for item in value.split(","))


def _parse_row(row: dict[str, str]) -> ResultRow:
    missing = set(ResultRow.header()) - set(row)
    if missing:
        fields = ", ".join(sorted(missing))
        raise ValueError(f"results row is missing required fields: {fields}")
    return ResultRow(
        run_id=row["run_id"],
        commit=row["commit"],
        artifact_dir=row["artifact_dir"],
        worktree_dirty=row["worktree_dirty"] == "true",
        strategy_sha256=row["strategy_sha256"],
        experiment_sha256=row["experiment_sha256"],
        protocol_sha256=row["protocol_sha256"],
        rationale_sha256=row["rationale_sha256"],
        quick_config_sha256=row["quick_config_sha256"],
        iteration=int(row["iteration"]),
        score=_parse_float(row["score"]),
        gates_passed=row["gates_passed"] == "true",
        gate_flags=row["gate_flags"],
        subwindow_trade_counts=_parse_counts(row["subwindow_trade_counts"]),
        trade_count=int(row["trade_count"]),
        concentration=_parse_float(row["concentration"]),
        cost_stress=_parse_float(row["cost_stress"]),
        net_return_sum=_parse_float(row["net_return_sum"]),
        avg_trade_net=_parse_float(row["avg_trade_net"]),
        win_rate=_parse_float(row["win_rate"]),
        profit_factor=_parse_float(row["profit_factor"]),
        gross_return_sum=_parse_float(row["gross_return_sum"]),
        cost_return_sum=_parse_float(row["cost_return_sum"]),
        complexity_count=int(row["complexity_count"]),
        status=row["status"],
        best_status=row["best_status"],
        continuation=row["continuation"],
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
    kept_scores = [row.score for row in kept if row.score is not None]
    best = max(kept_scores, default=None)
    best_row = max(
        kept,
        key=lambda row: row.score if row.score is not None else float("-inf"),
        default=None,
    )
    stop_reason = next((row.stop_reason for row in reversed(rows) if row.stop_reason), "")
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
