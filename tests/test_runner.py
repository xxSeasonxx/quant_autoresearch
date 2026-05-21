from __future__ import annotations

import json
from pathlib import Path

import pytest
import runner as runner_module
from runner import main, run_once


LEGACY_DISTRIBUTION = "quant" + "-engine"


def test_run_once_writes_runner_managed_attempt_artifacts(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = write_harness_root(tmp_path, monkeypatch)
    experiment = {
        "strategy_id": "simple_momentum",
        "symbol": "DEMO",
        "weight": 1.0,
        "hold_bars": 1,
        "entry_lag_bars": 1,
        "fee_bps_per_side": 2.0,
        "slippage_bps_per_side": 1.0,
    }

    attempt_dir = run_once(experiment, attempt=1, results_dir=root / "results")

    expected = {
        "config.toml",
        "strategy_snapshot.py",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
        "signals.csv",
        "engine_request.json",
        "data_manifest.json",
        "run_manifest.json",
        "summary.json",
        "evidence.json",
        "notes.md",
    }
    assert expected.issubset({path.name for path in attempt_dir.iterdir()})
    summary = json.loads((attempt_dir / "summary.json").read_text())
    assert summary["success"] is True
    assert summary["status"] == "passed"
    assert summary["engine"] == {"passed": True, "trade_count": 1}
    assert LEGACY_DISTRIBUTION not in json.loads((attempt_dir / "run_manifest.json").read_text())["packages"]


def test_run_once_records_request_build_error_without_engine_artifacts(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = write_harness_root(tmp_path, monkeypatch)
    experiment = {
        "strategy_id": "simple_momentum",
        "symbol": "DEMO",
        "weight": 1.0,
        "hold_bars": 99,
        "entry_lag_bars": 1,
        "fee_bps_per_side": 2.0,
        "slippage_bps_per_side": 1.0,
    }

    attempt_dir = run_once(experiment, attempt=1, results_dir=root / "results")

    notes = (attempt_dir / "notes.md").read_text()
    assert "stage: request_build" in notes
    assert "outside available bars" in notes
    assert not (attempt_dir / "engine_request.json").exists()
    assert not (attempt_dir / "evidence.json").exists()


def test_run_once_records_failed_validation(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = write_harness_root(tmp_path, monkeypatch)
    experiment = {
        "strategy_id": "simple_momentum",
        "symbol": "DEMO",
        "weight": 1.0,
        "hold_bars": 1,
        "entry_lag_bars": 1,
        "fee_bps_per_side": 2000.0,
        "slippage_bps_per_side": 0.0,
    }

    attempt_dir = run_once(experiment, attempt=1, results_dir=root / "results")

    summary = json.loads((attempt_dir / "summary.json").read_text())
    evidence = json.loads((attempt_dir / "evidence.json").read_text())
    assert summary["success"] is False
    assert summary["status"] == "failed"
    assert evidence["validation_report"]["passed"] is False
    assert "failed validation gates" in (attempt_dir / "notes.md").read_text()


def test_main_respects_max_attempts_and_does_not_mutate_source_files(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = write_harness_root(tmp_path, monkeypatch)
    source_files = [root / "strategy.py", root / "experiment.yml", root / "prepare.py"]
    before = {path: path.read_text() for path in source_files}

    exit_code = main(["--max-attempts", "2", "--results-dir", str(root / "results")])

    assert exit_code == 0
    result_dirs = [
        path
        for path in (root / "results").iterdir()
        if path.is_dir() and not path.name.startswith("__")
    ]
    assert len(result_dirs) == 2
    assert {path: path.read_text() for path in source_files} == before


def write_harness_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(runner_module, "ROOT", root)
    (root / "prepare.py").write_text("from prepare import synthetic_bars\n")
    (root / "experiment.yml").write_text(
        "\n".join(
            [
                "strategy_id: simple_momentum",
                "symbol: DEMO",
                "max_attempts: 1",
                "weight: 1.0",
                "hold_bars: 1",
                "entry_lag_bars: 1",
                "fee_bps_per_side: 2.0",
                "slippage_bps_per_side: 1.0",
                "",
            ]
        )
    )
    (root / "strategy.py").write_text(
        '''
from __future__ import annotations


def generate_signals(bars, params):
    return [
        {
            "symbol": bars[1]["symbol"],
            "decision_time": bars[1]["timestamp"],
            "side": "long",
            "weight": float(params.get("weight", 1.0)),
            "hold_bars": int(params.get("hold_bars", 1)),
        }
    ]
'''.lstrip()
    )
    return root
