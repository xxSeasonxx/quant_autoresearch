from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from loop import run_iteration, validate_thesis
from objective import ObjectiveConfig
from protocol import load_protocol
from results_log import read_results


@dataclass(frozen=True)
class _Trade:
    symbol: str
    decision_time: datetime
    net_return: float


@dataclass(frozen=True)
class _Economics:
    trades: tuple[_Trade, ...]
    trade_count: int


@dataclass(frozen=True)
class _Result:
    succeeded: bool
    economics: _Economics | None
    message: str = "ok"


def test_validate_thesis_requires_mechanism_and_falsifier():
    assert "mechanism" in validate_thesis("", "flat if no edge").lower()
    assert "falsifier" in validate_thesis("momentum persists", "").lower()
    assert validate_thesis("momentum persists", "flat net after costs") is None


def test_run_iteration_uses_mocked_public_run_config_and_logs(tmp_path: Path):
    cfg = load_protocol(Path("protocol.toml"))
    cfg = cfg.with_output(results_dir=str(tmp_path / "artifacts"))
    results_path = tmp_path / "results.tsv"

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        assert Path(config_path).exists()
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

    assert outcome.status == "keep"
    assert outcome.gates_passed is True
    rows = read_results(results_path)
    assert len(rows) == 1
    assert rows[0].status == "keep"


def test_run_iteration_includes_entire_protocol_end_date(tmp_path: Path):
    cfg = replace(load_protocol(Path("protocol.toml")), objective=ObjectiveConfig(kind="worst_subwindow", subwindows=1))
    results_path = tmp_path / "results.tsv"

    def fake_run_config(config_path, *, repo_root=None, event_sink=None):
        return _Result(
            succeeded=True,
            economics=_Economics(
                trades=(
                    _Trade("BTC-PERP", datetime(2025, 2, 1, 12, tzinfo=timezone.utc), 0.10),
                    _Trade("ETH-PERP", datetime(2025, 2, 1, 13, tzinfo=timezone.utc), 0.10),
                    _Trade("BTC-PERP", datetime(2025, 2, 1, 14, tzinfo=timezone.utc), 0.10),
                    _Trade("ETH-PERP", datetime(2025, 2, 1, 15, tzinfo=timezone.utc), 0.10),
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
    assert "upstream unavailable" in rows[0].note
