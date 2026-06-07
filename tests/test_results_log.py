from __future__ import annotations

from pathlib import Path

from results_log import ResultRow, append_result, read_results, status_summary


def test_results_log_initializes_header_and_appends_one_row_per_attempt(tmp_path: Path):
    path = tmp_path / "results.tsv"
    row = ResultRow(
        commit="abcdef0",
        iteration=1,
        score=0.42,
        gates_passed=True,
        gate_flags="trade_floor=pass",
        trade_count=12,
        concentration=0.5,
        cost_stress=0.2,
        complexity_count=2,
        status="keep",
        stop_reason="",
        elapsed_seconds=1.5,
        note="baseline",
    )

    append_result(path, row)
    append_result(path, row)

    lines = path.read_text().splitlines()
    assert lines[0].split("\t") == ResultRow.header()
    assert len(lines) == 3
    assert len(read_results(path)) == 2


def test_status_summary_excludes_retired_harness_fields(tmp_path: Path):
    path = tmp_path / "results.tsv"
    append_result(
        path,
        ResultRow(
            commit="a",
            iteration=1,
            score=0.1,
            gates_passed=True,
            gate_flags="all=pass",
            trade_count=3,
            concentration=0.4,
            cost_stress=0.0,
            complexity_count=1,
            status="keep",
            stop_reason="",
            elapsed_seconds=0.1,
            note="",
        ),
    )

    summary = status_summary(path, max_iterations=5, plateau_patience=2, subwindows=3)

    assert summary["best_score"] == 0.1
    assert summary["attempts"] == 1
    assert summary["remaining_iterations"] == 4
    assert summary["plateau_patience"] == 2
    assert summary["subwindows"] == 3
    for retired in ["selection_budget", "family_id", "ledger", "graduation", "lockbox"]:
        assert retired not in summary

