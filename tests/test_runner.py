from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import runner as runner_module
from runner import main


@dataclass(frozen=True)
class FakeRunResult:
    success: bool
    result_dir: Path | None
    notes_path: Path | None
    message: str
    run_completed: bool = True
    assessment_status: str = "smoke_passed"
    promotion_eligible: bool = False


def write_experiment(root: Path, *, max_attempts: int = 2) -> None:
    (root / "experiment.toml").write_text(
        f'''
strategy_id = "demo"
strategy_path = "strategy.py"
max_attempts = {max_attempts}
active_window_id = "primary"

[[windows]]
id = "primary"
start = "2024-01-01"
end = "2024-01-31"

[data]
kind = "bars"
dataset = "equity_1min"
symbols = ["SPY"]
strict = true

[params]
weight = 1.0
hold_bars = 1

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 0.0
slippage_bps_per_side = 0.0

[scoring]
metric = "net_return"
min_score_trades = 2

[output]
results_dir = "results"
mode = "validate"
'''.lstrip()
    )
    (root / "strategy.py").write_text("def generate_signals(bars, params):\n    return []\n")


def fake_success_run(result_root: Path, *, net_return: float, trade_count: int = 3):
    def _run_config(config_path: Path, *, repo_root: Path):
        attempt_dir = result_root / f"attempt_{net_return}".replace(".", "_")
        attempt_dir.mkdir(parents=True)
        (attempt_dir / "summary.json").write_text(
            json.dumps({"stage": "completed", "assessment_status": "smoke_passed"}) + "\n"
        )
        (attempt_dir / "evidence.json").write_text(
            json.dumps(
                {
                    "validation_report": {
                        "passed": True,
                        "gates": [],
                        "screening_result": {
                            "trade_count": trade_count,
                            "net_return": net_return,
                            "gross_return": net_return,
                            "cost_return": 0.0,
                        },
                    }
                }
            )
            + "\n"
        )
        return FakeRunResult(True, attempt_dir, attempt_dir / "notes.md", "ok")

    return _run_config


def test_main_runs_one_attempt_writes_score_state_and_ledger(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    exit_code = main(["--description", "baseline"])

    assert exit_code == 0
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert state["attempts_used"] == 1
    assert state["remaining_attempts"] == 1
    assert state["best_score"] == 0.05
    assert state["last_decision"] == "keep"
    ledger = (tmp_path / "results.tsv").read_text()
    assert "attempt\tcommit\twindow_id\tscore\traw_net_return\ttrade_count\tstatus\tdescription" in ledger
    assert "baseline" in ledger
    score_files = list((tmp_path / "results").glob("attempt_0_05/score.json"))
    assert len(score_files) == 1


def test_main_marks_non_improving_attempt_discard_but_consumes_budget(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=2)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))
    assert main(["--description", "baseline"]) == 0

    monkeypatch.setattr(runner_module, "current_commit", lambda: "def5678")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.01))
    assert main(["--description", "worse"]) == 0

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert state["attempts_used"] == 2
    assert state["remaining_attempts"] == 0
    assert state["status"] == "exhausted"
    assert state["best_score"] == 0.05
    assert state["best_commit"] == "abc1234"
    assert state["last_decision"] == "discard"
    assert "worse" in (tmp_path / "results.tsv").read_text()


def test_main_refuses_to_run_after_budget_exhausted(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=1)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))
    assert main(["--description", "baseline"]) == 0

    exit_code = main(["--description", "extra"])

    assert exit_code == 2
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert state["attempts_used"] == 1
    assert state["remaining_attempts"] == 0
