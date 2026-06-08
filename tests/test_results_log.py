from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from results_log import ResultRow, append_result, read_results, status_summary


def _row(**overrides) -> ResultRow:
    values = {
        "run_id": "attempt-0001",
        "commit": "abcdef0",
        "artifact_dir": "results/autoresearch/attempt-0001",
        "worktree_dirty": False,
        "strategy_sha256": "s" * 64,
        "experiment_sha256": "e" * 64,
        "protocol_sha256": "p" * 64,
        "rationale_sha256": "r" * 64,
        "quick_config_sha256": "q" * 64,
        "iteration": 1,
        "score": 0.42,
        "gates_passed": True,
        "gate_flags": "trade_floor=pass",
        "subwindow_trade_counts": (4, 4, 4),
        "trade_count": 12,
        "concentration": 0.5,
        "cost_stress": 0.2,
        "net_return_sum": 0.20,
        "avg_trade_net": 0.10,
        "win_rate": 1.0,
        "profit_factor": None,
        "gross_return_sum": 0.25,
        "cost_return_sum": 0.05,
        "complexity_count": 2,
        "status": "keep",
        "best_status": "updated",
        "continuation": "allowed",
        "stop_reason": "",
        "elapsed_seconds": 1.5,
        "note": "baseline",
    }
    values.update(overrides)
    return ResultRow(**cast(Any, values))


def test_results_log_initializes_header_and_appends_one_row_per_attempt(tmp_path: Path):
    path = tmp_path / "results.tsv"
    row = _row()

    append_result(path, row)
    append_result(path, row)

    lines = path.read_text().splitlines()
    assert lines[0].split("\t") == ResultRow.header()
    assert len(lines) == 3
    assert len(read_results(path)) == 2


def test_status_summary_excludes_retired_harness_fields(tmp_path: Path):
    path = tmp_path / "results.tsv"
    append_result(path, _row(run_id="attempt-0001", commit="a", iteration=1, score=0.1))

    summary = status_summary(path, max_iterations=5, plateau_patience=2, subwindows=3)

    assert summary["best_score"] == 0.1
    assert summary["best_run_id"] == "attempt-0001"
    assert summary["attempts"] == 1
    assert summary["continuation"] == "allowed"
    assert summary["remaining_iterations"] == 4
    assert summary["plateau_patience"] == 2
    assert summary["subwindows"] == 3
    for retired in ["selection_budget", "family_id", "ledger", "graduation", "lockbox"]:
        assert retired not in summary


def test_result_rows_record_attempt_provenance_and_lifecycle(tmp_path: Path):
    path = tmp_path / "results.tsv"
    append_result(
        path,
        _row(
            worktree_dirty=True,
            status="discard",
            best_status="unchanged",
            continuation="allowed",
            subwindow_trade_counts=(10, 0, 2),
        ),
    )

    row = read_results(path)[0]

    assert row.worktree_dirty is True
    assert row.artifact_dir == "results/autoresearch/attempt-0001"
    assert row.strategy_sha256 == "s" * 64
    assert row.subwindow_trade_counts == (10, 0, 2)
    assert row.best_status == "unchanged"
    assert row.continuation == "allowed"


def test_legacy_results_rows_fail_with_clear_error(tmp_path: Path):
    path = tmp_path / "results.tsv"
    path.write_text("commit\titeration\nabc1234\t1\n")

    try:
        read_results(path)
    except ValueError as exc:
        assert "missing required fields" in str(exc)
    else:
        raise AssertionError("legacy row should fail with a clear error")
