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
        "strategy_sha256": "a" * 64,
        "experiment_sha256": "b" * 64,
        "protocol_sha256": "c" * 64,
        "rationale_sha256": "d" * 64,
        "quick_config_sha256": "e" * 64,
        "iteration": 1,
        "score": 0.42,
        "gates_passed": True,
        "gate_flags": "trade_floor=pass",
        "subwindow_trade_counts": (4, 4, 4),
        "trade_count": 12,
        "net_return_contribution_concentration": 0.5,
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
    first = _row(run_id="attempt-0001", iteration=1)
    second = _row(
        run_id="attempt-0002",
        commit="abcdef1",
        iteration=2,
        status="discard",
        best_status="unchanged",
        score=0.1,
    )

    append_result(path, first)
    append_result(path, second)

    lines = path.read_text().splitlines()
    assert lines[0].split("\t") == ResultRow.header()
    assert "net_return_contribution_concentration" in ResultRow.header()
    assert "concentration" not in ResultRow.header()
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
    assert row.strategy_sha256 == "a" * 64
    assert row.subwindow_trade_counts == (10, 0, 2)
    assert row.net_return_contribution_concentration == 0.5
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


def test_result_rows_reject_invalid_enums_booleans_and_hashes(tmp_path: Path):
    cases = [
        (_row(status="winner"), "status"),
        (_row(best_status="changed"), "best_status"),
        (_row(continuation="maybe"), "continuation"),
        (_row(strategy_sha256="not-a-hash"), "strategy_sha256"),
    ]
    for row, message in cases:
        path = tmp_path / f"{message}.tsv"
        append_result(path, row)
        try:
            read_results(path)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"{message} should fail")

    path = tmp_path / "boolean.tsv"
    append_result(path, _row())
    text = path.read_text().replace("\ttrue\t", "\tTRUE\t", 1)
    path.write_text(text)
    try:
        read_results(path)
    except ValueError as exc:
        assert "gates_passed" in str(exc) or "worktree_dirty" in str(exc)
    else:
        raise AssertionError("invalid boolean should fail")


def test_result_chain_rejects_duplicate_non_contiguous_and_terminal_middle_rows(
    tmp_path: Path,
):
    duplicate = tmp_path / "duplicate.tsv"
    append_result(duplicate, _row(run_id="attempt-0001", iteration=1))
    append_result(
        duplicate,
        _row(
            run_id="attempt-0001",
            iteration=1,
            status="discard",
            best_status="unchanged",
        ),
    )
    try:
        read_results(duplicate)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate attempts should fail")

    gap = tmp_path / "gap.tsv"
    append_result(gap, _row(run_id="attempt-0001", iteration=1))
    append_result(
        gap,
        _row(
            run_id="attempt-0003",
            iteration=3,
            status="discard",
            best_status="unchanged",
        ),
    )
    try:
        read_results(gap)
    except ValueError as exc:
        assert "contiguous" in str(exc)
    else:
        raise AssertionError("non-contiguous attempts should fail")

    terminal_middle = tmp_path / "terminal_middle.tsv"
    append_result(
        terminal_middle,
        _row(
            run_id="attempt-0001",
            iteration=1,
            continuation="terminal",
            stop_reason="plateau",
        ),
    )
    append_result(
        terminal_middle,
        _row(
            run_id="attempt-0002",
            iteration=2,
            status="discard",
            best_status="unchanged",
        ),
    )
    try:
        read_results(terminal_middle)
    except ValueError as exc:
        assert "terminal" in str(exc)
    else:
        raise AssertionError("terminal row before final row should fail")
