from __future__ import annotations

import json
import csv
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


def write_experiment(root: Path, *, max_attempts: int = 2, results_dir: str = "results") -> None:
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
results_dir = "{results_dir}"
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


def fake_config_failure_run():
    def _run_config(config_path: Path, *, repo_root: Path):
        return FakeRunResult(False, None, None, "invalid TOML in generated config", run_completed=False)

    return _run_config


def fake_malformed_evidence_run(result_root: Path):
    def _run_config(config_path: Path, *, repo_root: Path):
        attempt_dir = result_root / "attempt_bad_evidence"
        attempt_dir.mkdir(parents=True)
        (attempt_dir / "summary.json").write_text(
            json.dumps({"stage": "completed", "assessment_status": "smoke_passed"}) + "\n"
        )
        (attempt_dir / "evidence.json").write_text("{invalid json\n")
        return FakeRunResult(False, attempt_dir, attempt_dir / "notes.md", "malformed evidence")

    return _run_config


def test_main_runs_one_attempt_writes_score_state_and_ledger(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
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
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
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
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))
    assert main(["--description", "baseline"]) == 0

    exit_code = main(["--description", "extra"])

    assert exit_code == 2
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert state["attempts_used"] == 1
    assert state["remaining_attempts"] == 0


def test_main_resolves_relative_paths_under_root_when_invoked_elsewhere(tmp_path: Path, monkeypatch):
    outside = tmp_path / "outside"
    workbench = tmp_path / "workbench"
    outside.mkdir()
    workbench.mkdir()
    write_experiment(workbench)
    monkeypatch.chdir(outside)
    monkeypatch.setattr(runner_module, "ROOT", workbench)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        assert config_path == workbench / "results" / ".generated" / "attempt_0001_primary.toml"
        assert repo_root == workbench
        return fake_success_run(workbench / "results", net_return=0.05)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--description", "outside cwd"]) == 0

    assert (workbench / "results" / ".generated" / "attempt_0001_primary.toml").exists()
    assert (workbench / "results" / "session_state.json").exists()
    assert (workbench / ".autoresearch_session.json").exists()
    assert (workbench / "results.tsv").exists()
    assert not (outside / "results").exists()
    assert not (outside / "results.tsv").exists()


def test_main_writes_failure_artifacts_when_run_config_has_no_result_dir(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_config_failure_run())

    assert main(["--description", "bad config"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0001_config_failed"
    score = json.loads((attempt_dir / "score.json").read_text())
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    ledger = (tmp_path / "results.tsv").read_text()

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["failure_source"] == "config_error"
    assert metadata["failure_source"] == "config_error"
    assert state["attempts_used"] == 1
    assert state["last_decision"] == "discard"
    assert "\tdiscard\tbad config" in ledger


def test_main_writes_failure_artifacts_for_invalid_local_config(tmp_path: Path, monkeypatch):
    (tmp_path / "experiment.toml").write_text("max_attempts = \n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    assert main(["--description", "broken local config"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0001_config_failed"
    score = json.loads((attempt_dir / "score.json").read_text())
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    ledger = (tmp_path / "results.tsv").read_text()

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["failure_source"] == "config_error"
    assert metadata["failure_source"] == "config_error"
    assert state["attempts_used"] == 1
    assert state["remaining_attempts"] == 0
    assert state["status"] == "exhausted"
    assert state["last_decision"] == "discard"
    assert "\tconfig\t\t\t\tdiscard\tbroken local config" in ledger


def test_new_invalid_local_config_session_ignores_max_attempts_override(
    tmp_path: Path, monkeypatch, capsys
):
    (tmp_path / "experiment.toml").write_text("max_attempts = \n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    assert main(["--description", "broken local config", "--max-attempts", "3"]) == 0

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    output = json.loads(capsys.readouterr().out)
    assert state["max_attempts"] == 1
    assert state["attempts_used"] == 1
    assert state["remaining_attempts"] == 0
    assert state["status"] == "exhausted"
    assert output["max_attempts"] == 1
    assert output["remaining_attempts"] == 0


def test_main_writes_failure_artifacts_for_unreadable_local_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    assert main(["--config", "missing.toml", "--description", "missing local config"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0001_config_failed"
    score = json.loads((attempt_dir / "score.json").read_text())
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    ledger = (tmp_path / "results.tsv").read_text()

    assert score["status"] == "runner_failed"
    assert score["failure_source"] == "config_error"
    assert metadata["failure_source"] == "config_error"
    assert state["attempts_used"] == 1
    assert state["last_decision"] == "discard"
    assert "\tdiscard\tmissing local config" in ledger


def test_invalid_local_config_consumes_existing_session_capacity(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=3)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))
    assert main(["--description", "baseline"]) == 0

    (tmp_path / "experiment.toml").write_text("max_attempts = \n")
    monkeypatch.setattr(runner_module, "current_commit", lambda: "def5678")

    assert main(["--description", "broken local config"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0002_config_failed"
    score = json.loads((attempt_dir / "score.json").read_text())
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())

    assert score["failure_source"] == "config_error"
    assert state["attempts_used"] == 2
    assert state["remaining_attempts"] == 1
    assert state["best_score"] == 0.05
    assert state["best_commit"] == "abc1234"
    assert state["last_decision"] == "discard"


def test_invalid_local_config_consumes_custom_results_session_capacity(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=3, results_dir="custom_results")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(
        runner_module,
        "run_config",
        fake_success_run(tmp_path / "custom_results", net_return=0.05),
    )
    assert main(["--description", "baseline"]) == 0

    (tmp_path / "experiment.toml").write_text("max_attempts = \n")
    monkeypatch.setattr(runner_module, "current_commit", lambda: "def5678")

    assert main(["--description", "broken local config"]) == 0

    attempt_dir = tmp_path / "custom_results" / "attempt_0002_config_failed"
    score = json.loads((attempt_dir / "score.json").read_text())
    state = json.loads((tmp_path / "custom_results" / "session_state.json").read_text())

    assert score["failure_source"] == "config_error"
    assert state["attempts_used"] == 2
    assert state["remaining_attempts"] == 1
    assert state["best_score"] == 0.05
    assert state["best_commit"] == "abc1234"
    assert state["last_decision"] == "discard"
    assert not (tmp_path / "results" / "session_state.json").exists()


def test_main_writes_failure_artifacts_for_malformed_evidence_json(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(
        runner_module,
        "run_config",
        fake_malformed_evidence_run(tmp_path / "results"),
    )

    assert main(["--description", "bad evidence"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_bad_evidence"
    score = json.loads((attempt_dir / "score.json").read_text())
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    ledger = (tmp_path / "results.tsv").read_text()

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["failure_source"] == "quant_strategies_error"
    assert metadata["failure_source"] == "quant_strategies_error"
    assert state["attempts_used"] == 1
    assert state["last_decision"] == "discard"
    assert "\tdiscard\tbad evidence" in ledger


def test_existing_session_preserves_max_attempts_when_override_differs(
    tmp_path: Path, monkeypatch, capsys
):
    write_experiment(tmp_path, max_attempts=2)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))
    assert main(["--description", "baseline"]) == 0
    capsys.readouterr()

    monkeypatch.setattr(runner_module, "current_commit", lambda: "def5678")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.06))
    assert main(["--description", "second", "--max-attempts", "10"]) == 0

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    output = json.loads(capsys.readouterr().out)
    assert state["max_attempts"] == 2
    assert state["remaining_attempts"] == 0
    assert output["max_attempts"] == 2
    assert output["ignored_max_attempts_override"] == 10


def test_ledger_sanitizes_newlines_in_description(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--description", "line one\nline two\rline three"]) == 0

    ledger_path = tmp_path / "results.tsv"
    ledger_text = ledger_path.read_text()
    rows = list(csv.DictReader(ledger_text.splitlines(), delimiter="\t"))
    assert len(ledger_text.splitlines()) == 2
    assert rows[0]["description"] == "line one line two line three"


def test_smoke_attempt_uses_real_default_strategy_file_without_live_quant_data(
    tmp_path: Path, monkeypatch
):
    import importlib.util
    import tomllib
    from datetime import datetime, timedelta, timezone

    def _crypto_rows() -> list[dict[str, object]]:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        rows: list[dict[str, object]] = []
        symbols = ("BTC-PERP", "ETH-PERP", "SOL-PERP", "XRP-PERP")
        for symbol_index, symbol in enumerate(symbols):
            base = 100.0 + symbol_index
            for offset in range(0, 481):
                timestamp = start + timedelta(minutes=offset)
                funding_event = offset in {0, 240, 480}
                rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": timestamp,
                        "open": base,
                        "high": base,
                        "low": base,
                        "close": base + offset * (0.01 if symbol_index < 2 else -0.01),
                        "funding_timestamp": timestamp if funding_event else None,
                        "funding_rate": (0.0002 if symbol_index < 2 else -0.0002)
                        if funding_event
                        else None,
                        "has_funding_event": funding_event,
                    }
                )
        return rows

    def _run_config(config_path: Path, *, repo_root: Path):
        generated_config = tomllib.loads(config_path.read_text())
        strategy_path = Path(generated_config["strategy_path"])
        if not strategy_path.is_absolute():
            strategy_path = repo_root / strategy_path
        assert strategy_path == tmp_path / "strategy.py"

        spec = importlib.util.spec_from_file_location("scratch_strategy_smoke", strategy_path)
        assert spec is not None
        assert spec.loader is not None
        strategy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(strategy_module)

        generate_signals = getattr(strategy_module, "generate_signals", None)
        assert callable(generate_signals)
        signals = generate_signals(_crypto_rows(), generated_config["params"])
        assert [(signal["symbol"], signal["side"]) for signal in signals] == [
            ("BTC-PERP", "short"),
            ("SOL-PERP", "long"),
        ]

        return fake_success_run(tmp_path / "results", net_return=0.02, trade_count=5)(
            config_path, repo_root=repo_root
        )

    write_experiment(tmp_path, max_attempts=1)
    source_strategy = Path(__file__).resolve().parents[1] / "strategy.py"
    (tmp_path / "strategy.py").write_text(source_strategy.read_text())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", _run_config)

    exit_code = main(["--description", "strategy compatibility smoke"])

    assert exit_code == 0
    score_path = next((tmp_path / "results").glob("attempt_0_02/score.json"))
    score = json.loads(score_path.read_text())
    assert score["status"] == "scored"
    assert score["score"] == 0.02
