from __future__ import annotations

import json
from pathlib import Path

from runner import run_once


def test_run_once_writes_complete_attempt_artifacts(tmp_path):
    experiment = {
        "strategy_id": "simple_momentum",
        "symbol": "DEMO",
        "weight": 1.0,
        "hold_bars": 1,
        "entry_lag_bars": 1,
        "fee_bps_per_side": 2.0,
        "slippage_bps_per_side": 1.0,
    }

    attempt_dir = run_once(experiment, attempt=1, results_dir=tmp_path)

    expected = {
        "experiment.yml",
        "strategy_snapshot.py",
        "bars.csv",
        "signals.csv",
        "request.json",
        "screen_summary.json",
        "validate_summary.json",
        "evidence.json",
        "notes.md",
    }
    assert expected.issubset({path.name for path in attempt_dir.iterdir()})
    assert json.loads((attempt_dir / "screen_summary.json").read_text())["strategy_id"] == "simple_momentum"
    assert json.loads((attempt_dir / "validate_summary.json").read_text())["passed"] is True


def test_run_once_records_error_without_engine_artifacts(tmp_path):
    experiment = {
        "strategy_id": "simple_momentum",
        "symbol": "DEMO",
        "weight": 1.0,
        "hold_bars": 99,
        "entry_lag_bars": 1,
        "fee_bps_per_side": 2.0,
        "slippage_bps_per_side": 1.0,
    }

    attempt_dir = run_once(experiment, attempt=1, results_dir=tmp_path)

    notes = (attempt_dir / "notes.md").read_text()
    assert "screen failed" in notes
    assert not (attempt_dir / "validate_summary.json").exists()
