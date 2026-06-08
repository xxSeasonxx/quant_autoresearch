from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import hashlib
from typing import Any, cast

import pytest

from loop import (
    _ensure_can_attempt,
    climb_once,
    components_from_rationale,
    IterationOutcome,
    main,
    run_iteration,
    validate_thesis,
)
from gates import GateConfig
from objective import LoopConfig, ObjectiveConfig
from protocol import load_protocol
from results_log import ResultRow, append_result, read_results


@dataclass(frozen=True)
class _Trade:
    symbol: str
    decision_time: datetime
    net_return: float
    gross_return: float | None = None
    cost_return: float | None = None


@dataclass(frozen=True)
class _Economics:
    trades: tuple[_Trade, ...]
    trade_count: int


@dataclass(frozen=True)
class _Result:
    succeeded: bool
    economics: _Economics | None
    message: str = "ok"


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
        "score": 0.5,
        "gates_passed": True,
        "gate_flags": "all=pass",
        "subwindow_trade_counts": (4,),
        "trade_count": 4,
        "concentration": 0.5,
        "cost_stress": 0.1,
        "net_return_sum": 0.2,
        "avg_trade_net": 0.05,
        "win_rate": 1.0,
        "profit_factor": None,
        "gross_return_sum": 0.24,
        "cost_return_sum": 0.04,
        "complexity_count": 1,
        "status": "keep",
        "best_status": "updated",
        "continuation": "allowed",
        "stop_reason": "",
        "elapsed_seconds": 0.1,
        "note": "",
    }
    values.update(overrides)
    return ResultRow(**cast(Any, values))


def _write_snapshot_files(root: Path) -> None:
    (root / "strategy.py").write_text("# strategy\n")
    (root / "experiment.toml").write_text(Path("experiment.toml").read_text())
    (root / "protocol.toml").write_text("# protocol\n")
    (root / "rationale.md").write_text(
        """
# Rationale

## Signal Components

### Component: baseline momentum
### Component: session filter
### Component: volatility gate
### Component: exit timing
"""
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_climb_protocol(root: Path) -> None:
    text = Path("protocol.toml").read_text()
    replacements = {
        "subwindows = 6": "subwindows = 1",
        "min_trades = 120": "min_trades = 4",
        "min_trades_per_subwindow = 12": "min_trades_per_subwindow = 1",
        "max_symbol_concentration = 0.70": "max_symbol_concentration = 1.0",
        "max_components = 3": "max_components = 4",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    (root / "protocol.toml").write_text(text)


def _successful_result() -> _Result:
    return _Result(
        succeeded=True,
        economics=_Economics(
            trades=(
                _Trade("BTC-PERP", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.10),
                _Trade("ETH-PERP", datetime(2025, 1, 2, tzinfo=timezone.utc), 0.08),
                _Trade("BTC-PERP", datetime(2025, 1, 3, tzinfo=timezone.utc), 0.06),
                _Trade("ETH-PERP", datetime(2025, 1, 4, tzinfo=timezone.utc), 0.04),
            ),
            trade_count=4,
        ),
    )


def _write_attempt_snapshot(root: Path, row: ResultRow, marker: str) -> None:
    snapshot = root / row.artifact_dir / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "strategy.py").write_text(f"# {marker} strategy\n")
    (snapshot / "experiment.toml").write_text(f"# {marker} experiment\n")
    (snapshot / "protocol.toml").write_text(f"# {marker} protocol\n")
    (snapshot / "rationale.md").write_text(f"# {marker} rationale\n")
    (snapshot / "quick_config.toml").write_text(f"# {marker} quick config\n")


def test_validate_thesis_requires_mechanism_and_falsifier():
    assert "mechanism" in validate_thesis("", "flat if no edge").lower()
    assert "falsifier" in validate_thesis("momentum persists", "").lower()
    assert validate_thesis("momentum persists", "flat net after costs") is None


def test_components_from_rationale_parses_signal_component_headings(tmp_path: Path):
    path = tmp_path / "rationale.md"
    path.write_text(
        """
# Rationale

## Signal Components

### Component: baseline momentum

### Component: session filter

## Variants Tried

### Variant: ignored
"""
    )

    assert components_from_rationale(path) == ("baseline momentum", "session filter")


def test_components_from_rationale_rejects_missing_and_duplicate_components(
    tmp_path: Path,
):
    missing = tmp_path / "missing.md"
    missing.write_text("# Rationale\n\n## Signal Components\n")
    duplicate = tmp_path / "duplicate.md"
    duplicate.write_text(
        """
# Rationale

## Signal Components

### Component: Baseline Momentum

### Component: baseline   momentum
"""
    )

    for path, message in [(missing, "at least one"), (duplicate, "duplicate")]:
        with pytest.raises(ValueError, match=message):
            components_from_rationale(path)


def test_run_iteration_uses_mocked_public_run_config_and_logs(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    cfg = load_protocol(Path("protocol.toml"))
    cfg = replace(
        cfg.with_output(results_dir=str(tmp_path / "artifacts")),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        assert Path(config_path).exists()
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade(
                        "BTC-PERP",
                        datetime(2025, 1, 1, tzinfo=timezone.utc),
                        0.10,
                        0.11,
                        0.01,
                    ),
                    _Trade(
                        "ETH-PERP",
                        datetime(2025, 1, 2, tzinfo=timezone.utc),
                        0.08,
                        0.09,
                        0.01,
                    ),
                    _Trade(
                        "BTC-PERP",
                        datetime(2025, 1, 3, tzinfo=timezone.utc),
                        0.06,
                        0.07,
                        0.01,
                    ),
                    _Trade(
                        "ETH-PERP",
                        datetime(2025, 1, 4, tzinfo=timezone.utc),
                        0.04,
                        0.05,
                        0.01,
                    ),
                ),
                trade_count=4,
            ),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=fake_run_config,
        workdir=tmp_path,
    )

    assert outcome.status == "keep"
    assert outcome.gates_passed is True
    rows = read_results(results_path)
    assert len(rows) == 1
    assert rows[0].status == "keep"
    assert rows[0].best_status == "updated"
    assert rows[0].continuation == "allowed"
    assert rows[0].artifact_dir == "results/autoresearch/attempt-0001"
    assert rows[0].strategy_sha256 == _sha256(tmp_path / "strategy.py")
    assert rows[0].experiment_sha256 == _sha256(tmp_path / "experiment.toml")
    assert rows[0].protocol_sha256 == _sha256(tmp_path / "protocol.toml")
    assert rows[0].rationale_sha256 == _sha256(tmp_path / "rationale.md")
    assert rows[0].subwindow_trade_counts == (4,)
    assert rows[0].net_return_sum == 0.28
    assert rows[0].avg_trade_net == 0.07
    assert rows[0].win_rate == 1.0
    assert rows[0].gross_return_sum == 0.32
    assert rows[0].cost_return_sum == 0.04


def test_run_iteration_includes_entire_protocol_end_date(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade(
                        "BTC-PERP", datetime(2025, 2, 1, 12, tzinfo=timezone.utc), 0.10
                    ),
                    _Trade(
                        "ETH-PERP", datetime(2025, 2, 1, 13, tzinfo=timezone.utc), 0.10
                    ),
                    _Trade(
                        "BTC-PERP", datetime(2025, 2, 1, 14, tzinfo=timezone.utc), 0.10
                    ),
                    _Trade(
                        "ETH-PERP", datetime(2025, 2, 1, 15, tzinfo=timezone.utc), 0.10
                    ),
                ),
                trade_count=4,
            ),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=fake_run_config,
        workdir=tmp_path,
    )

    assert outcome.status == "keep"
    assert outcome.score == 0.1
    assert read_results(results_path)[0].trade_count == 4
    assert read_results(results_path)[0].net_return_sum == 0.4


def test_run_iteration_logs_crash_when_runner_raises(tmp_path: Path):
    cfg = load_protocol(Path("protocol.toml"))
    results_path = tmp_path / "results.tsv"

    def raising_runner(*args, **kwargs):
        raise RuntimeError("upstream unavailable")

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=raising_runner,
        workdir=Path.cwd(),
    )

    rows = read_results(results_path)
    assert outcome.status == "crash"
    assert len(rows) == 1
    assert rows[0].status == "crash"
    assert rows[0].continuation == "repair_required"
    assert "upstream unavailable" in rows[0].note


def test_run_iteration_discard_leaves_best_unchanged_and_allows_continuation(
    tmp_path: Path,
):
    _write_snapshot_files(tmp_path)
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"
    prior_rows = (_row(iteration=1, score=1.0),)
    for prior_row in prior_rows:
        append_result(results_path, prior_row)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade("BTC-PERP", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.01),
                    _Trade("ETH-PERP", datetime(2025, 1, 2, tzinfo=timezone.utc), 0.01),
                    _Trade("BTC-PERP", datetime(2025, 1, 3, tzinfo=timezone.utc), 0.01),
                    _Trade("ETH-PERP", datetime(2025, 1, 4, tzinfo=timezone.utc), 0.01),
                ),
                trade_count=4,
            ),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=2,
        best_score=1.0,
        runner=fake_run_config,
        workdir=tmp_path,
        prior_rows=prior_rows,
    )

    row = read_results(results_path)[-1]
    assert outcome.status == "discard"
    assert row.best_status == "unchanged"
    assert row.continuation == "allowed"
    assert row.stop_reason == ""


def test_plateau_terminal_attempt_writes_survivor_manifest(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        loop=LoopConfig(
            plateau_patience=2,
            max_iterations=10,
            min_abs_improvement=0.01,
            min_rel_improvement=0.0,
            baseline_grace_iterations=3,
        ),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"
    prior_rows = (
        _row(iteration=1, status="keep", score=1.0),
        _row(
            run_id="attempt-0002",
            iteration=2,
            status="discard",
            score=0.5,
            best_status="unchanged",
        ),
    )
    for prior_row in prior_rows:
        append_result(results_path, prior_row)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade("BTC-PERP", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.01),
                    _Trade("ETH-PERP", datetime(2025, 1, 2, tzinfo=timezone.utc), 0.01),
                    _Trade("BTC-PERP", datetime(2025, 1, 3, tzinfo=timezone.utc), 0.01),
                    _Trade("ETH-PERP", datetime(2025, 1, 4, tzinfo=timezone.utc), 0.01),
                ),
                trade_count=4,
            ),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=3,
        best_score=1.0,
        runner=fake_run_config,
        workdir=tmp_path,
        prior_rows=prior_rows,
    )

    row = read_results(results_path)[-1]
    manifest = tmp_path / row.artifact_dir / "terminal_manifest.json"
    assert outcome.stop_reason == "plateau"
    assert row.continuation == "terminal"
    assert manifest.exists()
    payload = json.loads(manifest.read_text())
    assert payload["status"] == "train_survivor"
    assert (
        tmp_path / payload["snapshot_paths"]["strategy"]
    ).read_text() == "# strategy\n"
    assert (tmp_path / payload["snapshot_paths"]["experiment"]).exists()
    assert (tmp_path / payload["snapshot_paths"]["protocol"]).exists()
    assert (tmp_path / payload["snapshot_paths"]["rationale"]).exists()
    assert (tmp_path / payload["snapshot_paths"]["quick_config"]).exists()
    assert payload["snapshot_paths"]["best_quick_config"] is None
    assert "not OOS, paper, live" in payload["disclaimer"]


def test_plateau_after_discard_manifest_snapshots_best_kept_attempt(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    (tmp_path / "strategy.py").write_text("# terminal strategy\n")
    (tmp_path / "experiment.toml").write_text("# terminal experiment\n")
    (tmp_path / "protocol.toml").write_text("# terminal protocol\n")
    (tmp_path / "rationale.md").write_text("# terminal rationale\n")
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        loop=LoopConfig(
            plateau_patience=2,
            max_iterations=10,
            min_abs_improvement=0.01,
            min_rel_improvement=0.0,
            baseline_grace_iterations=3,
        ),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    best_row = _row(
        iteration=1,
        run_id="attempt-0001",
        status="keep",
        score=1.0,
        strategy_sha256=hashlib.sha256(b"# best strategy\n").hexdigest(),
        experiment_sha256=hashlib.sha256(b"# best experiment\n").hexdigest(),
        protocol_sha256=hashlib.sha256(b"# best protocol\n").hexdigest(),
        rationale_sha256=hashlib.sha256(b"# best rationale\n").hexdigest(),
        quick_config_sha256=hashlib.sha256(b"# best quick config\n").hexdigest(),
    )
    _write_attempt_snapshot(tmp_path, best_row, "best")
    prior_rows = (
        best_row,
        _row(
            run_id="attempt-0002",
            iteration=2,
            status="discard",
            score=0.5,
            best_status="unchanged",
        ),
    )
    results_path = tmp_path / "results.tsv"
    for prior_row in prior_rows:
        append_result(results_path, prior_row)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade("BTC-PERP", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.01),
                    _Trade("ETH-PERP", datetime(2025, 1, 2, tzinfo=timezone.utc), 0.01),
                    _Trade("BTC-PERP", datetime(2025, 1, 3, tzinfo=timezone.utc), 0.01),
                    _Trade("ETH-PERP", datetime(2025, 1, 4, tzinfo=timezone.utc), 0.01),
                ),
                trade_count=4,
            ),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=3,
        best_score=1.0,
        runner=fake_run_config,
        workdir=tmp_path,
        prior_rows=prior_rows,
    )

    row = read_results(results_path)[-1]
    manifest = tmp_path / row.artifact_dir / "terminal_manifest.json"
    payload = json.loads(manifest.read_text())
    best_snapshot = payload["best_survivor_snapshot"]
    terminal_snapshot = payload["terminal_attempt_snapshot"]

    assert outcome.stop_reason == "plateau"
    assert payload["best_attempt"]["run_id"] == "attempt-0001"
    assert (tmp_path / best_snapshot["strategy"]).read_text() == "# best strategy\n"
    assert (
        tmp_path / terminal_snapshot["strategy"]
    ).read_text() == "# terminal strategy\n"
    assert _sha256(tmp_path / best_snapshot["strategy"]) == best_row.strategy_sha256


def test_baseline_failure_writes_train_failure_manifest(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        loop=LoopConfig(
            plateau_patience=2,
            max_iterations=10,
            min_abs_improvement=0.01,
            min_rel_improvement=0.0,
            baseline_grace_iterations=1,
        ),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"

    def no_trade_runner(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(trades=(), trade_count=0),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=no_trade_runner,
        workdir=tmp_path,
    )

    row = read_results(results_path)[0]
    manifest = tmp_path / row.artifact_dir / "terminal_manifest.json"
    payload = json.loads(manifest.read_text())
    assert outcome.stop_reason == "baseline_failure"
    assert row.continuation == "terminal"
    assert payload["status"] == "train_failure"
    assert payload["best_attempt"] is None
    assert payload["best_survivor_snapshot"] is None
    assert (tmp_path / payload["snapshot_paths"]["strategy"]).exists()
    assert (tmp_path / payload["snapshot_paths"]["quick_config"]).exists()


def test_max_iterations_writes_terminal_manifest(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        loop=LoopConfig(
            plateau_patience=2,
            max_iterations=1,
            min_abs_improvement=0.01,
            min_rel_improvement=0.0,
            baseline_grace_iterations=3,
        ),
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=3,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade("BTC-PERP", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.10),
                    _Trade("ETH-PERP", datetime(2025, 1, 2, tzinfo=timezone.utc), 0.08),
                    _Trade("BTC-PERP", datetime(2025, 1, 3, tzinfo=timezone.utc), 0.06),
                    _Trade("ETH-PERP", datetime(2025, 1, 4, tzinfo=timezone.utc), 0.04),
                ),
                trade_count=4,
            ),
        )

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=fake_run_config,
        workdir=tmp_path,
    )

    row = read_results(results_path)[0]
    manifest = tmp_path / row.artifact_dir / "terminal_manifest.json"
    assert outcome.status == "keep"
    assert outcome.stop_reason == "max_iterations"
    assert row.continuation == "terminal"
    assert manifest.exists()


def test_terminal_and_repair_required_state_block_new_attempts():
    snapshot = {
        "strategy_sha256": "a" * 64,
        "experiment_sha256": "b" * 64,
        "protocol_sha256": "c" * 64,
        "rationale_sha256": "d" * 64,
    }

    with pytest.raises(ValueError, match="already stopped"):
        _ensure_can_attempt(
            (_row(continuation="terminal", stop_reason="plateau"),),
            snapshot,
        )

    with pytest.raises(ValueError, match="requires"):
        _ensure_can_attempt(
            (_row(status="crash", continuation="repair_required"),),
            snapshot,
        )

    changed = dict(snapshot)
    changed["strategy_sha256"] = "f" * 64
    _ensure_can_attempt(
        (_row(status="crash", continuation="repair_required"),),
        changed,
    )


def test_climb_once_blocks_terminal_state_before_runner(tmp_path: Path, monkeypatch):
    _write_snapshot_files(tmp_path)
    protocol_text = Path("protocol.toml").read_text()
    (tmp_path / "protocol.toml").write_text(protocol_text)
    (tmp_path / "results.tsv").write_text(
        "\t".join(ResultRow.header())
        + "\n"
        + "\t".join(
            _row(
                continuation="terminal",
                stop_reason="plateau",
                strategy_sha256=_sha256(tmp_path / "strategy.py"),
                experiment_sha256=_sha256(tmp_path / "experiment.toml"),
                protocol_sha256=_sha256(tmp_path / "protocol.toml"),
                rationale_sha256=_sha256(tmp_path / "rationale.md"),
            )
            .as_record()
            .values()
        )
        + "\n"
    )
    monkeypatch.chdir(tmp_path)
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    with pytest.raises(ValueError, match="already stopped"):
        climb_once(
            mechanism="momentum persists",
            falsifier="flat after costs",
            runner=runner,
        )
    assert called is False


def test_climb_once_rejects_out_of_bound_params_before_runner(
    tmp_path: Path, monkeypatch
):
    _write_snapshot_files(tmp_path)
    (tmp_path / "protocol.toml").write_text(Path("protocol.toml").read_text())
    (tmp_path / "experiment.toml").write_text(
        """
[params]
weight = 0.75

[bounds.weight]
min = 0.01
max = 0.50
"""
    )
    monkeypatch.chdir(tmp_path)
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    with pytest.raises(ValueError, match="outside bounds"):
        climb_once(
            mechanism="momentum persists",
            falsifier="flat after costs",
            runner=runner,
        )
    assert called is False


def test_climb_once_uses_rationale_components_for_complexity(
    tmp_path: Path, monkeypatch
):
    _write_snapshot_files(tmp_path)
    (tmp_path / "protocol.toml").write_text(Path("protocol.toml").read_text())
    monkeypatch.chdir(tmp_path)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade("BTC-PERP", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.10),
                    _Trade("ETH-PERP", datetime(2025, 5, 1, tzinfo=timezone.utc), 0.08),
                    _Trade("BTC-PERP", datetime(2025, 9, 1, tzinfo=timezone.utc), 0.06),
                    _Trade(
                        "ETH-PERP", datetime(2025, 12, 1, tzinfo=timezone.utc), 0.04
                    ),
                ),
                trade_count=4,
            ),
        )

    outcome = climb_once(
        mechanism="momentum persists",
        falsifier="flat after costs",
        runner=fake_run_config,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    assert outcome.row is not None
    assert row.complexity_count == 4
    assert "complexity_cap=fail" in row.gate_flags


def test_climb_once_rejects_missing_rationale_components_before_runner(
    tmp_path: Path,
    monkeypatch,
):
    _write_snapshot_files(tmp_path)
    (tmp_path / "protocol.toml").write_text(Path("protocol.toml").read_text())
    (tmp_path / "rationale.md").write_text("# Rationale\n\n## Signal Components\n")
    monkeypatch.chdir(tmp_path)
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    with pytest.raises(ValueError, match="at least one"):
        climb_once(
            mechanism="momentum persists",
            falsifier="flat after costs",
            runner=runner,
        )
    assert called is False
    assert not (tmp_path / ".autoresearch" / "thesis_lock.json").exists()


def test_run_iteration_snapshots_configured_strategy_path(tmp_path: Path):
    _write_snapshot_files(tmp_path)
    (tmp_path / "alt_strategy.py").write_text("# alternate strategy\n")
    cfg = replace(
        load_protocol(Path("protocol.toml")),
        strategy_path="alt_strategy.py",
        objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1),
        gates=GateConfig(
            min_trades=4,
            min_trades_per_subwindow=1,
            max_symbol_concentration=0.8,
            min_cost_stress_score=0.0,
            max_components=4,
            max_params=8,
            train_score_floor=0.0,
            subwindows=1,
        ),
    )
    results_path = tmp_path / "results.tsv"

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _successful_result()

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=fake_run_config,
        workdir=tmp_path,
    )

    assert outcome.row is not None
    snapshot_strategy = tmp_path / outcome.row.artifact_dir / "snapshot" / "strategy.py"
    assert snapshot_strategy.read_text() == "# alternate strategy\n"
    assert _sha256(snapshot_strategy) == outcome.row.strategy_sha256


def test_climb_once_rejects_active_thesis_identity_drift(tmp_path: Path, monkeypatch):
    _write_snapshot_files(tmp_path)
    _write_climb_protocol(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _successful_result()

    first = climb_once(
        mechanism="momentum persists",
        falsifier="flat after costs",
        runner=fake_run_config,
    )
    assert first.status == "keep"
    assert (tmp_path / ".autoresearch" / "thesis_lock.json").exists()

    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    with pytest.raises(ValueError, match="new thesis lifecycle"):
        climb_once(
            mechanism="mean reversion after overreaction",
            falsifier="flat after costs",
            runner=runner,
        )
    assert called is False
    assert not (tmp_path / ".autoresearch" / "quick" / "attempt-0002.toml").exists()


def test_climb_once_rejects_protocol_drift_before_runner(tmp_path: Path, monkeypatch):
    _write_snapshot_files(tmp_path)
    _write_climb_protocol(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _successful_result()

    first = climb_once(
        mechanism="momentum persists",
        falsifier="flat after costs",
        runner=fake_run_config,
    )
    assert first.status == "keep"

    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    protocol_text = (tmp_path / "protocol.toml").read_text()
    (tmp_path / "protocol.toml").write_text(
        protocol_text.replace("min_trades = 4", "min_trades = 5")
    )
    with pytest.raises(ValueError, match="protocol"):
        climb_once(
            mechanism="momentum persists",
            falsifier="flat after costs",
            runner=runner,
        )
    assert called is False
    assert not (tmp_path / ".autoresearch" / "quick" / "attempt-0002.toml").exists()


def test_climb_once_rejects_bounds_drift_before_runner(tmp_path: Path, monkeypatch):
    _write_snapshot_files(tmp_path)
    _write_climb_protocol(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _successful_result()

    first = climb_once(
        mechanism="momentum persists",
        falsifier="flat after costs",
        runner=fake_run_config,
    )
    assert first.status == "keep"

    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    experiment_text = (tmp_path / "experiment.toml").read_text()
    (tmp_path / "experiment.toml").write_text(
        experiment_text.replace("max = 0.50", "max = 0.75")
    )
    with pytest.raises(ValueError, match="bounds"):
        climb_once(
            mechanism="momentum persists",
            falsifier="flat after costs",
            runner=runner,
        )
    assert called is False


def test_climb_once_allows_param_value_change_with_unchanged_bounds(
    tmp_path: Path,
    monkeypatch,
):
    _write_snapshot_files(tmp_path)
    _write_climb_protocol(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _successful_result()

    first = climb_once(
        mechanism="momentum persists",
        falsifier="flat after costs",
        runner=fake_run_config,
    )
    assert first.status == "keep"
    lock_payload = json.loads(
        (tmp_path / ".autoresearch" / "thesis_lock.json").read_text()
    )
    assert lock_payload["mechanism"] == "momentum persists"

    experiment_text = (tmp_path / "experiment.toml").read_text()
    (tmp_path / "experiment.toml").write_text(
        experiment_text.replace("weight = 0.10", "weight = 0.20")
    )
    second = climb_once(
        mechanism="  momentum   persists ",
        falsifier="flat after costs",
        runner=fake_run_config,
    )

    assert second.row is not None
    assert second.row.iteration == 2
    assert (tmp_path / ".autoresearch" / "quick" / "attempt-0002.toml").exists()


def test_run_iteration_blocks_repair_required_state_before_writing_config(
    tmp_path: Path,
):
    _write_snapshot_files(tmp_path)
    cfg = load_protocol(Path("protocol.toml"))
    prior = (
        _row(
            status="crash",
            continuation="repair_required",
            strategy_sha256=_sha256(tmp_path / "strategy.py"),
            experiment_sha256=_sha256(tmp_path / "experiment.toml"),
            protocol_sha256=_sha256(tmp_path / "protocol.toml"),
            rationale_sha256=_sha256(tmp_path / "rationale.md"),
        ),
    )

    with pytest.raises(ValueError, match="requires"):
        run_iteration(
            cfg,
            params={"lookback_bars": 12, "weight": 0.1},
            components=("momentum",),
            results_path=tmp_path / "results.tsv",
            iteration=2,
            best_score=None,
            runner=lambda *args, **kwargs: None,
            workdir=tmp_path,
            prior_rows=prior,
        )

    assert not (tmp_path / ".autoresearch" / "quick" / "attempt-0002.toml").exists()


def test_missing_successful_economics_is_logged_as_crash(tmp_path: Path):
    cfg = load_protocol(Path("protocol.toml"))
    results_path = tmp_path / "results.tsv"

    def missing_economics_runner(*args, **kwargs):
        return _Result(succeeded=True, economics=None)

    outcome = run_iteration(
        cfg,
        params={"lookback_bars": 12, "weight": 0.1},
        components=("momentum",),
        results_path=results_path,
        iteration=1,
        best_score=None,
        runner=missing_economics_runner,
        workdir=tmp_path,
    )

    row = read_results(results_path)[0]
    assert outcome.status == "crash"
    assert row.continuation == "repair_required"
    assert "missing economics" in row.note


def test_climb_cli_outputs_full_result_row(monkeypatch, capsys):
    row = _row(run_id="attempt-0099", gate_flags="trade_floor=pass")

    def fake_climb_once(**kwargs):
        return IterationOutcome(
            status=row.status,
            score=row.score,
            gates_passed=row.gates_passed,
            gates=None,
            row=row,
        )

    monkeypatch.setattr("loop.climb_once", fake_climb_once)

    assert (
        main(
            [
                "climb",
                "--mechanism",
                "momentum persists",
                "--falsifier",
                "flat after costs",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    assert len(lines) == len(ResultRow.header())
    for field in ResultRow.header():
        assert f"{field}: " in output
    assert "run_id: attempt-0099" in output
    assert "gate_flags: trade_floor=pass" in output
