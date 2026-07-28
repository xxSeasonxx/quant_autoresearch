from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv

_LEDGER_NOTE_MAX_CHARS = 2000
_LEDGER_NOTE_TRUNCATION = "\n...[truncated]"


def _compact_ledger_note(note: str) -> str:
    if len(note) <= _LEDGER_NOTE_MAX_CHARS:
        return note
    keep = _LEDGER_NOTE_MAX_CHARS - len(_LEDGER_NOTE_TRUNCATION)
    return note[:keep].rstrip() + _LEDGER_NOTE_TRUNCATION


@dataclass(frozen=True)
class ResultRow:
    run_id: str
    iteration: int
    status: str
    score: float | None
    train_strength_lcb: float | None
    full_train_at_risk_annualized_return: float | None
    cost_stress_return_retention: float | None
    book_scale: float | None
    deployed_volatility: float | None
    max_feasible_volatility: float | None
    target_reached: bool | None
    max_feasible_book_scale: float | None
    minimum_order_notional_ratio: float | None
    fixed_cost_share: float | None
    full_train_psr: float | None
    worst_subwindow_psr: float | None
    gates_passed: bool
    gate_flags: str
    trade_count: int
    min_subwindow_trades: int
    max_drawdown: float | None
    max_symbol_concentration: float | None
    effective_symbol_count: float | None
    max_positive_subwindow_return_share: float | None
    win_rate: float | None
    profit_factor: float | None
    avg_trade_net: float | None
    cost_return_sum: float | None
    complexity_count: int
    failure_class: str
    failure_reason: str
    best_status: str
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
            "train_strength_lcb",
            "full_train_at_risk_annualized_return",
            "cost_stress_return_retention",
            "book_scale",
            "deployed_volatility",
            "max_feasible_volatility",
            "target_reached",
            "max_feasible_book_scale",
            "minimum_order_notional_ratio",
            "fixed_cost_share",
            "full_train_psr",
            "worst_subwindow_psr",
            "gates_passed",
            "gate_flags",
            "trade_count",
            "min_subwindow_trades",
            "max_drawdown",
            "max_symbol_concentration",
            "effective_symbol_count",
            "max_positive_subwindow_return_share",
            "win_rate",
            "profit_factor",
            "avg_trade_net",
            "cost_return_sum",
            "complexity_count",
            "failure_class",
            "failure_reason",
            "best_status",
            "elapsed_seconds",
            "artifact_dir",
            "note",
        ]

    def as_record(self) -> dict[str, str]:
        def optional(value: float | None) -> str:
            return "" if value is None else str(value)

        def optional_bool(value: bool | None) -> str:
            return "" if value is None else ("true" if value else "false")

        return {
            "run_id": self.run_id,
            "iteration": str(self.iteration),
            "status": self.status,
            "score": optional(self.score),
            "train_strength_lcb": optional(self.train_strength_lcb),
            "full_train_at_risk_annualized_return": optional(
                self.full_train_at_risk_annualized_return
            ),
            "cost_stress_return_retention": optional(self.cost_stress_return_retention),
            "book_scale": optional(self.book_scale),
            "deployed_volatility": optional(self.deployed_volatility),
            "max_feasible_volatility": optional(self.max_feasible_volatility),
            "target_reached": optional_bool(self.target_reached),
            "max_feasible_book_scale": optional(self.max_feasible_book_scale),
            "minimum_order_notional_ratio": optional(self.minimum_order_notional_ratio),
            "fixed_cost_share": optional(self.fixed_cost_share),
            "full_train_psr": optional(self.full_train_psr),
            "worst_subwindow_psr": optional(self.worst_subwindow_psr),
            "gates_passed": "true" if self.gates_passed else "false",
            "gate_flags": self.gate_flags,
            "trade_count": str(self.trade_count),
            "min_subwindow_trades": str(self.min_subwindow_trades),
            "max_drawdown": optional(self.max_drawdown),
            "max_symbol_concentration": optional(self.max_symbol_concentration),
            "effective_symbol_count": optional(self.effective_symbol_count),
            "max_positive_subwindow_return_share": optional(
                self.max_positive_subwindow_return_share
            ),
            "win_rate": optional(self.win_rate),
            "profit_factor": optional(self.profit_factor),
            "avg_trade_net": optional(self.avg_trade_net),
            "cost_return_sum": optional(self.cost_return_sum),
            "complexity_count": str(self.complexity_count),
            "failure_class": self.failure_class,
            "failure_reason": self.failure_reason,
            "best_status": self.best_status,
            "elapsed_seconds": str(self.elapsed_seconds),
            "artifact_dir": self.artifact_dir,
            "note": _compact_ledger_note(self.note),
        }


def _parse_float(value: str) -> float | None:
    return None if value == "" else float(value)


def _parse_bool(value: str, *, name: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{name} must be true or false")


def _parse_optional_bool(value: str, *, name: str) -> bool | None:
    if value == "":
        return None
    return _parse_bool(value, name=name)


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
        train_strength_lcb=_parse_float(row["train_strength_lcb"]),
        full_train_at_risk_annualized_return=_parse_float(
            row["full_train_at_risk_annualized_return"]
        ),
        cost_stress_return_retention=_parse_float(row["cost_stress_return_retention"]),
        book_scale=_parse_float(row["book_scale"]),
        deployed_volatility=_parse_float(row["deployed_volatility"]),
        max_feasible_volatility=_parse_float(row["max_feasible_volatility"]),
        target_reached=_parse_optional_bool(
            row["target_reached"], name="target_reached"
        ),
        max_feasible_book_scale=_parse_float(row["max_feasible_book_scale"]),
        minimum_order_notional_ratio=_parse_float(row["minimum_order_notional_ratio"]),
        fixed_cost_share=_parse_float(row["fixed_cost_share"]),
        full_train_psr=_parse_float(row["full_train_psr"]),
        worst_subwindow_psr=_parse_float(row["worst_subwindow_psr"]),
        gates_passed=_parse_bool(row["gates_passed"], name="gates_passed"),
        gate_flags=row["gate_flags"],
        trade_count=int(row["trade_count"]),
        min_subwindow_trades=int(row["min_subwindow_trades"]),
        max_drawdown=_parse_float(row["max_drawdown"]),
        max_symbol_concentration=_parse_float(row["max_symbol_concentration"]),
        effective_symbol_count=_parse_float(row["effective_symbol_count"]),
        max_positive_subwindow_return_share=_parse_float(
            row["max_positive_subwindow_return_share"]
        ),
        win_rate=_parse_float(row["win_rate"]),
        profit_factor=_parse_float(row["profit_factor"]),
        avg_trade_net=_parse_float(row["avg_trade_net"]),
        cost_return_sum=_parse_float(row["cost_return_sum"]),
        complexity_count=int(row["complexity_count"]),
        failure_class=row["failure_class"],
        failure_reason=row["failure_reason"],
        best_status=_parse_enum(
            row["best_status"],
            name="best_status",
            allowed={"updated", "unchanged"},
        ),
        elapsed_seconds=float(row["elapsed_seconds"]),
        artifact_dir=row["artifact_dir"],
        note=row["note"],
    )


def _validate_result_chain(rows: list[ResultRow]) -> None:
    seen_run_ids: set[str] = set()
    seen_iterations: set[int] = set()
    for row in rows:
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
    expected_iterations = list(range(1, len(rows) + 1))
    actual_iterations = [row.iteration for row in rows]
    if actual_iterations != expected_iterations:
        raise ValueError("result iterations must be contiguous from 1")


def _existing_header(path: Path) -> list[str]:
    with path.open(newline="") as handle:
        reader = csv.reader(handle, dialect="excel-tab")
        try:
            return next(reader)
        except StopIteration:
            return []


def _ensure_writable_schema(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return True
    if _existing_header(path) == ResultRow.header():
        return False
    raise ValueError("legacy results.tsv schema; start a new thesis lifecycle")


def append_result(path: str | Path, row: ResultRow) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    needs_header = _ensure_writable_schema(destination)
    if not needs_header:
        with destination.open("rb+") as handle:
            handle.seek(-1, 2)
            if handle.read(1) not in {b"\n", b"\r"}:
                handle.write(b"\n")
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
    if source.stat().st_size == 0:
        return []
    # Crash rows can carry verbose multi-line notes (e.g. an observation-audit
    # failure listing every missing row) that exceed Python's default 128 KB CSV
    # field cap; raise it so a large note never wedges the reader.
    csv.field_size_limit(10 * 1024 * 1024)
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle, dialect="excel-tab")
        raw_rows = list(reader)
    if reader.fieldnames != ResultRow.header():
        raise ValueError("legacy results.tsv schema; start a new thesis lifecycle")
    rows = [_parse_row(row) for row in raw_rows]
    _validate_result_chain(rows)
    return rows
