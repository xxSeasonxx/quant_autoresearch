from __future__ import annotations

from pathlib import Path

import pytest

from experiment_config import ConfigError, load_experiment_config, materialize_runner_toml


VALID_TOML = """
strategy_id = "demo_strategy"
strategy_path = "strategy.py"
source_strategy_path = "/Users/Season_Yang/Personal/quant_strategies/untested/demo.py"
max_attempts = 3
active_window_id = "primary"

[[windows]]
id = "primary"
start = "2024-01-01"
end = "2024-01-31"

[[windows]]
id = "holdout"
start = "2024-02-01"
end = "2024-02-29"

[data]
kind = "bars"
dataset = "equity_1min"
symbols = ["SPY"]
strict = true

[params]
weight = 1.0
hold_bars = 2

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 1.0
slippage_bps_per_side = 2.0

[scoring]
metric = "net_return"
min_score_trades = 5

[output]
results_dir = "results"
mode = "validate"
"""


def write_config(tmp_path: Path, text: str = VALID_TOML) -> Path:
    path = tmp_path / "experiment.toml"
    path.write_text(text.strip() + "\n")
    return path


def test_load_experiment_config_parses_windows_and_scoring(tmp_path: Path):
    config = load_experiment_config(write_config(tmp_path))

    assert config.strategy_id == "demo_strategy"
    assert config.strategy_path == Path("strategy.py")
    assert config.max_attempts == 3
    assert [window.id for window in config.windows] == ["primary", "holdout"]
    assert config.active_window_id == "primary"
    assert config.scoring.metric == "net_return"
    assert config.scoring.min_score_trades == 5


def test_load_experiment_config_rejects_missing_windows(tmp_path: Path):
    bad = VALID_TOML.split("[[windows]]", 1)[0] + """
[data]
kind = "bars"
dataset = "equity_1min"
symbols = ["SPY"]
strict = true

[params]

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 0.0
slippage_bps_per_side = 0.0

[scoring]
metric = "net_return"
min_score_trades = 5

[output]
results_dir = "results"
mode = "validate"
"""

    with pytest.raises(ConfigError, match="at least one window"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_unknown_active_window(tmp_path: Path):
    bad = VALID_TOML.replace('active_window_id = "primary"', 'active_window_id = "missing"')

    with pytest.raises(ConfigError, match="active_window_id"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_non_net_return_metric(tmp_path: Path):
    bad = VALID_TOML.replace('metric = "net_return"', 'metric = "sharpe"')

    with pytest.raises(ConfigError, match="metric"):
        load_experiment_config(write_config(tmp_path, bad))


def test_materialize_runner_toml_uses_selected_window_dates(tmp_path: Path):
    config = load_experiment_config(write_config(tmp_path))
    generated = tmp_path / "results" / ".generated" / "attempt_0001_primary.toml"

    materialize_runner_toml(config, generated, window_id="holdout", results_dir=Path("results"))

    text = generated.read_text()
    assert 'strategy_path = "strategy.py"' in text
    assert 'strategy_id = "demo_strategy"' in text
    assert 'start = "2024-02-01"' in text
    assert 'end = "2024-02-29"' in text
    assert 'results_dir = "results"' in text
    assert 'dataset = "equity_1min"' in text
