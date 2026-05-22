from __future__ import annotations

import json
import csv
from dataclasses import dataclass
from pathlib import Path
import tomllib

import pytest

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


LEDGER_HEADER = "\t".join(runner_module.LEDGER_HEADER)
SCORED_NET_RETURN = 0.05
SCORED_DAILY_SCORE = SCORED_NET_RETURN / 120


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
end = "2024-04-29"

[[windows]]
id = "holdout"
start = "2024-05-01"
end = "2024-08-28"

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
        attempt_dir.mkdir(parents=True, exist_ok=True)
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
    assert state["best_score"] == pytest.approx(SCORED_DAILY_SCORE)
    assert state["last_decision"] == "keep"
    ledger = (tmp_path / "results.tsv").read_text()
    assert LEDGER_HEADER in ledger
    assert "baseline" in ledger
    rows = list(csv.DictReader(ledger.splitlines(), delimiter="\t"))
    assert rows[0]["window_id"] == "primary"
    assert rows[0]["window_start"] == "2024-01-01"
    assert rows[0]["window_end"] == "2024-04-29"
    assert rows[0]["window_days"] == "120"
    assert rows[0]["symbol_count"] == "1"
    score_files = list((tmp_path / "results").glob("attempt_0_05/score.json"))
    assert len(score_files) == 1
    score = json.loads(score_files[0].read_text())
    assert score["window_start"] == "2024-01-01"
    assert score["window_end"] == "2024-04-29"
    assert score["window_days"] == 120
    assert score["symbol_count"] == 1


def test_main_records_explicit_window_metadata(tmp_path: Path, monkeypatch, capsys):
    write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        generated = config_path.read_text()
        assert 'start = "2024-05-01"' in generated
        assert 'end = "2024-08-28"' in generated
        return fake_success_run(tmp_path / "results", net_return=0.05)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--window-id", "holdout", "--description", "holdout check"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["window_start"] == "2024-05-01"
    assert output["window_end"] == "2024-08-28"
    assert output["window_days"] == 120
    assert output["symbol_count"] == 1
    attempt_dir = tmp_path / "results" / "attempt_0_05"
    score = json.loads((attempt_dir / "score.json").read_text())
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    assert score["window_id"] == "holdout"
    assert score["window_start"] == "2024-05-01"
    assert score["window_end"] == "2024-08-28"
    assert score["window_days"] == 120
    assert score["symbol_count"] == 1
    assert metadata["window_id"] == "holdout"
    assert metadata["window_start"] == "2024-05-01"
    assert metadata["window_end"] == "2024-08-28"
    assert metadata["window_days"] == 120
    assert metadata["symbol_count"] == 1
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["window_id"] == "holdout"
    assert rows[0]["window_start"] == "2024-05-01"
    assert rows[0]["window_end"] == "2024-08-28"
    assert rows[0]["window_days"] == "120"
    assert rows[0]["symbol_count"] == "1"


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
    assert state["best_score"] == pytest.approx(SCORED_DAILY_SCORE)
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

    attempt_dir = tmp_path / "results" / "attempt_0001_primary_config_failed"
    score = json.loads((attempt_dir / "score.json").read_text())
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    ledger = (tmp_path / "results.tsv").read_text()

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["failure_source"] == "config_error"
    assert score["window_start"] == "2024-01-01"
    assert score["window_end"] == "2024-04-29"
    assert score["window_days"] == 120
    assert score["symbol_count"] == 1
    assert metadata["failure_source"] == "config_error"
    assert metadata["window_start"] == "2024-01-01"
    assert metadata["window_end"] == "2024-04-29"
    assert metadata["window_days"] == 120
    assert metadata["symbol_count"] == 1
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
    rows = list(csv.DictReader(ledger.splitlines(), delimiter="\t"))
    assert rows[0]["window_id"] == "config"
    assert rows[0]["window_start"] == ""
    assert rows[0]["window_end"] == ""
    assert rows[0]["window_days"] == ""
    assert rows[0]["symbol_count"] == ""
    assert rows[0]["status"] == "discard"
    assert rows[0]["description"] == "broken local config"


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
    assert output["window_start"] is None
    assert output["window_end"] is None
    assert output["window_days"] is None
    assert output["symbol_count"] is None


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
    assert state["best_score"] == pytest.approx(SCORED_DAILY_SCORE)
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
    assert state["best_score"] == pytest.approx(SCORED_DAILY_SCORE)
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


def test_ledger_upgrades_old_header_when_appending(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    (tmp_path / "results.tsv").write_text(
        "attempt\tcommit\twindow_id\tscore\traw_net_return\ttrade_count\tstatus\tdescription\n"
        "0\told123\tprimary\t0.01\t0.01\t3\tkeep\tlegacy row\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--description", "new row"]) == 0

    ledger_text = (tmp_path / "results.tsv").read_text()
    assert ledger_text.splitlines()[0] == LEDGER_HEADER
    rows = list(csv.DictReader(ledger_text.splitlines(), delimiter="\t"))
    assert rows[0]["description"] == "legacy row"
    assert rows[0]["window_start"] == ""
    assert rows[0]["window_end"] == ""
    assert rows[0]["window_days"] == ""
    assert rows[0]["symbol_count"] == ""
    assert rows[1]["description"] == "new row"
    assert rows[1]["window_start"] == "2024-01-01"
    assert rows[1]["window_end"] == "2024-04-29"
    assert rows[1]["window_days"] == "120"
    assert rows[1]["symbol_count"] == "1"


def test_ledger_upgrades_window_header_when_appending_symbol_count(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    (tmp_path / "results.tsv").write_text(
        "attempt\tcommit\twindow_id\twindow_start\twindow_end\twindow_days\t"
        "score\traw_net_return\ttrade_count\tstatus\tdescription\n"
        "0\told123\tprimary\t2024-01-01\t2024-04-29\t120\t0.01\t0.01\t3\tkeep\tlegacy row\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--description", "new row"]) == 0

    ledger_text = (tmp_path / "results.tsv").read_text()
    assert ledger_text.splitlines()[0] == LEDGER_HEADER
    rows = list(csv.DictReader(ledger_text.splitlines(), delimiter="\t"))
    assert rows[0]["description"] == "legacy row"
    assert rows[0]["window_start"] == "2024-01-01"
    assert rows[0]["window_days"] == "120"
    assert rows[0]["symbol_count"] == ""
    assert rows[1]["description"] == "new row"
    assert rows[1]["window_start"] == "2024-01-01"
    assert rows[1]["window_days"] == "120"
    assert rows[1]["symbol_count"] == "1"


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
    assert score["score"] == pytest.approx(0.02 / 120)


def test_session_state_tracks_best_confirmed_candidate(tmp_path: Path):
    state = runner_module.SessionState(
        max_attempts=3,
        attempts_used=0,
        best_score=0.01,
        best_commit="old",
        status="active",
        best_primary_window_score=0.0015,
        best_confirmed_candidate_score=0.002,
        best_confirmed_commit="confirmed_old",
    )

    payload_path = tmp_path / "session_state.json"
    runner_module.save_session_state(payload_path, state)
    loaded = runner_module.load_session_state(
        payload_path,
        config=None,
        max_attempts_override=None,
        fallback_max_attempts=3,
    )

    assert loaded.best_score == 0.01
    assert loaded.best_commit == "old"
    assert loaded.best_primary_window_score == 0.0015
    assert loaded.best_confirmed_candidate_score == 0.002
    assert loaded.best_confirmed_commit == "confirmed_old"


def test_append_ledger_writes_candidate_columns(tmp_path: Path):
    score = {
        "score": 0.001,
        "raw_net_return": 0.12,
        "trade_count": 250,
    }
    candidate_score = {
        "candidate_score": 0.0008,
        "recent_mean_score": 0.0012,
        "worst_recent_score": 0.0004,
        "passed_windows": ["validation_2025_h1", "locked_recent_2026"],
        "failed_windows": ["validation_2025_h2"],
    }

    runner_module.append_ledger(
        tmp_path / "results.tsv",
        attempt=1,
        commit="abc1234",
        window_id="locked_recent_2026",
        window_start="2025-10-16",
        window_end="2026-04-13",
        window_days=180,
        symbol_count=4,
        score=score,
        status="discard",
        description="confirm",
        run_kind="confirm",
        candidate_score=candidate_score,
    )

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["run_kind"] == "confirm"
    assert rows[0]["candidate_score"] == "0.0008"
    assert rows[0]["recent_mean_score"] == "0.0012"
    assert rows[0]["worst_recent_score"] == "0.0004"
    assert rows[0]["passed_window_count"] == "2"
    assert rows[0]["failed_window_count"] == "1"


def test_run_single_window_attempt_returns_score_and_artifacts(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    config = runner_module.load_experiment_config(tmp_path / "experiment.toml")
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        runner_module,
        "run_config",
        fake_success_run(tmp_path / "results", net_return=0.05),
    )

    result = runner_module.run_single_window_attempt(
        config=config,
        attempt=1,
        window_id="primary",
        results_dir=tmp_path / "results",
        description="helper run",
        commit="abc1234",
        simplification=False,
        artifact_profile=None,
    )

    assert result.window_id == "primary"
    assert result.score["score"] == pytest.approx(0.05 / 120)
    assert result.evidence is not None
    assert (result.result_dir / "score.json").exists()
    assert (result.result_dir / "attempt_metadata.json").exists()


def test_window_id_run_is_diagnostic_and_does_not_update_best_confirmed(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=2)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--window-id", "holdout", "--description", "manual"]) == 0

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert state["best_confirmed_candidate_score"] is None
    assert rows[0]["run_kind"] == "diagnostic"


def test_explore_run_uses_primary_research_window(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=2)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "holdout"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 2
confirm_on_explore_keep = false
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--explore", "--description", "explore"]) == 0

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["window_id"] == "holdout"
    assert rows[0]["run_kind"] == "explore"


@pytest.mark.parametrize(
    "argv",
    [
        ["--confirm", "--window-id", "holdout", "--description", "ambiguous"],
        ["--explore", "--window-id", "holdout", "--description", "ambiguous"],
    ],
)
def test_main_rejects_window_id_combined_with_research_modes(
    tmp_path: Path,
    monkeypatch,
    argv: list[str],
):
    write_experiment(tmp_path, max_attempts=1)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(argv)

    assert exc.value.code == 2
    assert not (tmp_path / "results" / "session_state.json").exists()


def test_explore_auto_confirms_when_primary_reference_improves(tmp_path: Path, monkeypatch, capsys):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 1
confirm_on_explore_keep = true

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 2
low_trade_penalty = 0.001
min_symbol_count = 1
symbol_concentration_penalty = 0.00025

[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        text = config_path.read_text()
        net = 0.12 if 'start = "2024-01-01"' in text else 0.24
        output_dir = Path(tomllib.loads(text)["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=net, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--description", "auto confirm"]) == 0

    output = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))

    assert output["run_kind"] == "confirm"
    assert output["auto_confirmed_from_explore"] is True
    assert state["best_primary_window_score"] == pytest.approx(0.12 / 120)
    assert state["best_confirmed_candidate_score"] == pytest.approx(output["candidate_score"])
    assert rows[0]["run_kind"] == "confirm"


def test_explore_does_not_auto_confirm_when_primary_reference_does_not_improve(
    tmp_path: Path,
    monkeypatch,
):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 1
confirm_on_explore_keep = true
"""
        )
    state_path = tmp_path / "results" / "session_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "attempts_used": 0,
                "best_commit": None,
                "best_score": None,
                "best_primary_window_score": 0.12 / 120,
                "best_confirmed_candidate_score": None,
                "best_confirmed_commit": None,
                "last_decision": None,
                "max_attempts": 1,
                "remaining_attempts": 1,
                "status": "active",
            }
        )
        + "\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.06))

    assert main(["--explore", "--description", "stale explore"]) == 0

    state = json.loads(state_path.read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert state["best_primary_window_score"] == pytest.approx(0.12 / 120)
    assert state["best_confirmed_candidate_score"] is None
    assert rows[0]["run_kind"] == "explore"


def test_confirm_runs_all_confirmation_windows_and_writes_candidate_score(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 2
confirm_on_explore_keep = true

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 2
low_trade_penalty = 0.001
min_symbol_count = 1
symbol_concentration_penalty = 0.00025

[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        text = config_path.read_text()
        net = 0.12 if 'start = "2024-01-01"' in text else 0.24
        output_dir = Path(tomllib.loads(text)["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=net, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--confirm", "--description", "confirm candidate"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["run_kind"] == "confirm"
    assert output["candidate_score"] is not None
    candidate_dir = Path(output["result_dir"])
    assert (candidate_dir / "candidate_score.json").exists()
    assert (candidate_dir / "candidate_summary.json").exists()
    assert (candidate_dir / "trade_attribution.json").exists()
    for window_id in ("primary", "holdout"):
        window_root = candidate_dir / "windows" / window_id
        assert window_root.is_dir()
        window_attempts = [path for path in window_root.iterdir() if path.name.startswith("attempt_")]
        assert len(window_attempts) == 1
        assert (window_attempts[0] / "score.json").exists()
        assert (window_attempts[0] / "summary.json").exists()
        assert (window_attempts[0] / "evidence.json").exists()

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert state["best_confirmed_candidate_score"] == pytest.approx(output["candidate_score"])
    assert state["best_confirmed_commit"] == "abc1234"

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["run_kind"] == "confirm"
    assert rows[0]["candidate_score"] != ""
    assert rows[0]["passed_window_count"] == "2"


def test_confirm_ledger_uses_primary_window_even_when_not_first(
    tmp_path: Path,
    monkeypatch,
):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "holdout"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 1
confirm_on_explore_keep = false

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 2
low_trade_penalty = 0.001
min_symbol_count = 1
symbol_concentration_penalty = 0.00025
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        text = config_path.read_text()
        output_dir = Path(tomllib.loads(text)["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=0.12, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--confirm", "--description", "primary second"]) == 0

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["window_id"] == "holdout"
    assert rows[0]["window_start"] == "2024-05-01"
    assert rows[0]["window_end"] == "2024-08-28"


def test_confirm_simplification_keeps_equal_candidate_score(tmp_path: Path, monkeypatch, capsys):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 1
confirm_on_explore_keep = false

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 2
low_trade_penalty = 0.001
min_symbol_count = 1
symbol_concentration_penalty = 0.00025
"""
        )
    state_path = tmp_path / "results" / "session_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "attempts_used": 0,
                "best_commit": None,
                "best_score": None,
                "best_primary_window_score": None,
                "best_confirmed_candidate_score": 0.12 / 120,
                "best_confirmed_commit": "old123",
                "last_decision": None,
                "max_attempts": 1,
                "remaining_attempts": 1,
                "status": "active",
            }
        )
        + "\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "new456")

    def _run_config(config_path: Path, *, repo_root: Path):
        output_dir = Path(tomllib.loads(config_path.read_text())["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=0.12, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--confirm", "--simplification", "--description", "simpler tie"]) == 0

    output = json.loads(capsys.readouterr().out)
    state = json.loads(state_path.read_text())
    assert output["decision"] == "keep"
    assert state["best_confirmed_candidate_score"] == pytest.approx(0.12 / 120)
    assert state["best_confirmed_commit"] == "new456"


def test_confirm_records_one_window_exception_as_failed_evidence(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 2
confirm_on_explore_keep = false

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 2
low_trade_penalty = 0.001
min_symbol_count = 1
symbol_concentration_penalty = 0.00025
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        text = config_path.read_text()
        if 'start = "2024-05-01"' in text:
            raise RuntimeError("simulated window crash")
        output_dir = Path(tomllib.loads(text)["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=0.12, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--confirm", "--description", "partial failure"]) == 0

    candidate_score = json.loads(
        (tmp_path / "results" / "candidate_0001_demo" / "candidate_score.json").read_text()
    )
    assert candidate_score["status"] == "confirmation_failed"
    assert candidate_score["candidate_score"] is None
    assert candidate_score["failed_windows"] == ["holdout"]


def test_runner_applies_research_artifact_policy(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        result = fake_success_run(tmp_path / "results", net_return=0.05)(config_path, repo_root=repo_root)
        assert result.result_dir is not None
        (result.result_dir / "strategy_input_rows.csv").write_text("big csv\n")
        (result.result_dir / "strategy_input_rows.jsonl").write_text("big jsonl\n")
        (result.result_dir / "engine_request.json").write_text("{}\n")
        return result

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--description", "compact artifacts"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0_05"
    assert not (attempt_dir / "strategy_input_rows.csv").exists()
    assert not (attempt_dir / "strategy_input_rows.jsonl").exists()
    assert not (attempt_dir / "engine_request.json").exists()
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    assert metadata["removed_artifacts"] == [
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ]


def test_artifact_profile_cli_research_overrides_debug_config(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[artifacts]
profile = "debug"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = true
keep_input_rows_csv = true
keep_input_rows_jsonl = true
compress_large_artifacts = false
large_artifact_max_mb = 100
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        result = fake_success_run(tmp_path / "results", net_return=0.05)(config_path, repo_root=repo_root)
        assert result.result_dir is not None
        (result.result_dir / "strategy_input_rows.csv").write_text("big csv\n")
        (result.result_dir / "strategy_input_rows.jsonl").write_text("big jsonl\n")
        (result.result_dir / "engine_request.json").write_text("{}\n")
        return result

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--artifact-profile", "research", "--description", "force compact"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0_05"
    assert not (attempt_dir / "strategy_input_rows.csv").exists()
    assert not (attempt_dir / "strategy_input_rows.jsonl").exists()
    assert not (attempt_dir / "engine_request.json").exists()
