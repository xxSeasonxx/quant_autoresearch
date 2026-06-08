from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

from quant_strategies.runner.config import load_config as load_runner_config

from protocol import (
    build_quick_run_config,
    load_experiment,
    load_params,
    load_protocol,
    write_quick_run_config,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def _protocol_text(**replacements: str) -> str:
    text = Path("protocol.toml").read_text()
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def test_protocol_loads_train_only_loop_constants(tmp_path: Path):
    protocol_path = _write(
        tmp_path / "protocol.toml",
        """
strategy_path = "strategy.py"
strategy_id = "strategy"

[data]
kind = "bars"
dataset = "crypto_perp_1min"
symbols = ["BTC-PERP", "ETH-PERP"]
start = "2025-01-01"
end = "2025-02-01"

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 5.0
slippage_bps_per_side = 1.0

[output]
results_dir = "results"
artifact_profile = "summary"

[loop]
plateau_patience = 4
max_iterations = 25
min_abs_improvement = 0.02
min_rel_improvement = 0.01
baseline_grace_iterations = 3

[objective]
kind = "worst_subwindow"
subwindows = 5

[gates]
min_trades = 12
min_trades_per_subwindow = 2
max_symbol_concentration = 0.6
min_cost_stress_score = 0.0
max_components = 3
max_params = 8
train_score_floor = 0.1
""",
    )

    cfg = load_protocol(protocol_path)

    assert cfg.data.symbols == ("BTC-PERP", "ETH-PERP")
    assert cfg.loop.plateau_patience == 4
    assert cfg.loop.max_iterations == 25
    assert cfg.loop.min_abs_improvement == 0.02
    assert cfg.loop.min_rel_improvement == 0.01
    assert cfg.objective.subwindows == 5
    assert cfg.gates.min_trades_per_subwindow == 2
    assert not hasattr(cfg.data, "oos")


def test_protocol_documents_default_symbol_window_and_subwindow_rationale():
    text = Path("protocol.toml").read_text().lower()

    assert "symbol universe rationale" in text
    assert "train window rationale" in text
    assert "subwindow rationale" in text
    assert "btc-perp" in text
    assert "eth-perp" in text


def test_protocol_rejects_invalid_numeric_ranges(tmp_path: Path):
    cases = [
        ("entry_lag_bars = 1", "entry_lag_bars = 0", "entry_lag_bars"),
        ("exit_lag_bars = 0", "exit_lag_bars = -1", "exit_lag_bars"),
        ("fee_bps_per_side = 5.0", "fee_bps_per_side = -1.0", "fee_bps_per_side"),
        ("plateau_patience = 4", "plateau_patience = 0", "plateau_patience"),
        ("max_iterations = 80", "max_iterations = 0", "max_iterations"),
        (
            "min_abs_improvement = 0.01",
            "min_abs_improvement = -0.01",
            "min_abs_improvement",
        ),
        ("subwindows = 6", "subwindows = 0", "subwindows"),
        ("min_trades = 120", "min_trades = -1", "min_trades"),
        ("max_components = 3", "max_components = 0", "max_components"),
    ]
    for old, new, message in cases:
        path = _write(tmp_path / f"{message}.toml", _protocol_text(**{old: new}))
        try:
            load_protocol(path)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"{message} should fail")


def test_protocol_rejects_invalid_concentration_symbols_and_booleans(tmp_path: Path):
    cases = [
        (
            "max_symbol_concentration = 0.70",
            "max_symbol_concentration = 1.50",
            "max_symbol_concentration",
        ),
        ('symbols = ["BTC-PERP", "ETH-PERP"]', "symbols = []", "symbols"),
        ('symbols = ["BTC-PERP", "ETH-PERP"]', 'symbols = "BTC-PERP"', "symbols"),
        ('symbols = ["BTC-PERP", "ETH-PERP"]', 'symbols = [""]', "symbols"),
        (
            'symbols = ["BTC-PERP", "ETH-PERP"]',
            'symbols = ["BTC-PERP", 123]',
            "symbols",
        ),
        ("quick_checks = true", 'quick_checks = "false"', "quick_checks"),
    ]
    for old, new, message in cases:
        path = _write(tmp_path / f"{message}.toml", _protocol_text(**{old: new}))
        try:
            load_protocol(path)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"{message} should fail")


def test_materialized_quick_run_ignores_param_collisions(tmp_path: Path):
    cfg = load_protocol(
        _write(tmp_path / "protocol.toml", (Path("protocol.toml").read_text()))
    )
    params = {
        "lookback_bars": 12,
        "symbols": ["DOGE-PERP"],
        "fee_bps_per_side": 0.0,
        "min_trades_per_subwindow": 999,
        "plateau_patience": 999,
    }

    materialized = build_quick_run_config(cfg, params, results_dir=tmp_path / "runs")
    data = cast(dict[str, Any], materialized["data"])
    cost_model = cast(dict[str, Any], materialized["cost_model"])

    assert data["symbols"] == list(cfg.data.symbols)
    assert cost_model["fee_bps_per_side"] == cfg.cost_model.fee_bps_per_side
    assert cfg.gates.min_trades_per_subwindow != params["min_trades_per_subwindow"]
    assert materialized["params"] == params
    assert "loop" not in materialized
    assert "objective" not in materialized


def test_write_quick_run_config_uses_public_runner_sections(tmp_path: Path):
    cfg = load_protocol(Path("protocol.toml"))
    out = write_quick_run_config(
        cfg,
        load_params(Path("experiment.toml")),
        tmp_path / "quick.toml",
        results_dir="results/autoresearch-test",
    )
    parsed = tomllib.loads(out.read_text())

    assert set(parsed) == {
        "strategy_path",
        "strategy_id",
        "data",
        "params",
        "fill_model",
        "cost_model",
        "output",
    }
    assert parsed["data"]["start"] == cfg.data.start
    assert parsed["output"]["artifact_profile"] == cfg.output.artifact_profile
    assert parsed["output"]["diagnostic_sample_trades"] >= 1
    loaded = load_runner_config(out, repo_root=Path.cwd())
    assert loaded.output.results_dir.name == "autoresearch-test"


def test_experiment_loads_params_and_bounds():
    experiment = load_experiment(Path("experiment.toml"))

    assert experiment.params["lookback_bars"] == 3
    assert experiment.bounds["weight"].min == 0.01
    assert experiment.bounds["weight"].max == 0.50
    assert load_params(Path("experiment.toml")) == experiment.params


def test_experiment_rejects_out_of_bound_params(tmp_path: Path):
    path = _write(
        tmp_path / "experiment.toml",
        """
[params]
weight = 0.75

[bounds.weight]
min = 0.01
max = 0.50
""",
    )

    try:
        load_experiment(path)
    except ValueError as exc:
        assert "outside bounds" in str(exc)
    else:
        raise AssertionError("out-of-bound param should fail")


def test_experiment_rejects_missing_and_orphan_bounds(tmp_path: Path):
    missing = _write(
        tmp_path / "missing.toml",
        """
[params]
weight = 0.10
""",
    )
    orphan = _write(
        tmp_path / "orphan.toml",
        """
[params]
weight = 0.10

[bounds.weight]
min = 0.01
max = 0.50

[bounds.lookback_bars]
min = 2
max = 240
""",
    )

    for path, message in [
        (missing, "missing bounds"),
        (orphan, "bounds without params"),
    ]:
        try:
            load_experiment(path)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"{path.name} should fail")


def test_experiment_rejects_non_finite_params_and_bounds(tmp_path: Path):
    non_finite_param = _write(
        tmp_path / "non_finite_param.toml",
        """
[params]
weight = nan

[bounds.weight]
min = 0.01
max = 0.50
""",
    )
    non_finite_bound = _write(
        tmp_path / "non_finite_bound.toml",
        """
[params]
weight = 0.10

[bounds.weight]
min = nan
max = 0.50
""",
    )

    for path in [non_finite_param, non_finite_bound]:
        try:
            load_experiment(path)
        except ValueError as exc:
            assert "finite" in str(exc)
        else:
            raise AssertionError(f"{path.name} should fail")
