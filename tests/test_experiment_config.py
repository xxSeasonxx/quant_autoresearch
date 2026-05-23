from __future__ import annotations

from pathlib import Path
import tomllib

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
end = "2024-04-29"

[[windows]]
id = "holdout"
start = "2024-05-01"
end = "2024-10-27"

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
    assert config.window_by_id("primary").days == 120
    assert config.window_by_id("holdout").days == 180
    assert config.scoring.metric == "net_return"
    assert config.scoring.min_score_trades == 5
    assert config.research.mode == "explore"
    assert config.research.primary_window_id == "primary"
    assert config.research.confirmation_window_ids == ("primary",)
    assert config.research.parallel_workers == 1
    assert config.research.confirm_on_explore_keep is False
    assert config.confirmation_scoring.primary_metric == "net_return_per_day"
    assert config.artifacts.profile == "research"


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


def test_load_experiment_config_rejects_invalid_window_dates(tmp_path: Path):
    bad = VALID_TOML.replace('end = "2024-04-29"', 'end = "2023-12-31"', 1)

    with pytest.raises(ConfigError, match="on or after"):
        load_experiment_config(write_config(tmp_path, bad))


@pytest.mark.parametrize("end_date", ["2024-02-29", "2024-12-31"])
def test_load_experiment_config_rejects_windows_outside_research_length(
    tmp_path: Path,
    end_date: str,
):
    bad = VALID_TOML.replace('end = "2024-04-29"', f'end = "{end_date}"', 1)

    with pytest.raises(ConfigError, match="120 to 180"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_non_net_return_metric(tmp_path: Path):
    bad = VALID_TOML.replace('metric = "net_return"', 'metric = "sharpe"')

    with pytest.raises(ConfigError, match="metric"):
        load_experiment_config(write_config(tmp_path, bad))


@pytest.mark.parametrize("min_score_trades", [0, -1])
def test_load_experiment_config_rejects_non_positive_min_score_trades(
    tmp_path: Path,
    min_score_trades: int,
):
    bad = VALID_TOML.replace("min_score_trades = 5", f"min_score_trades = {min_score_trades}")

    with pytest.raises(ConfigError, match="min_score_trades|positive"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_non_finite_numbers(tmp_path: Path):
    bad = VALID_TOML.replace("weight = 1.0", "weight = nan")

    with pytest.raises(ConfigError, match="finite|non-finite"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_parses_research_confirmation_and_artifacts(tmp_path: Path):
    config_text = VALID_TOML + """

[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 4
confirm_on_explore_keep = true

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 200
low_trade_penalty = 0.001
min_symbol_count = 4
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

    config = load_experiment_config(write_config(tmp_path, config_text))

    assert config.research.mode == "explore"
    assert config.research.primary_window_id == "primary"
    assert config.research.confirmation_window_ids == ("primary", "holdout")
    assert config.research.parallel_workers == 2
    assert config.research.confirm_on_explore_keep is True
    assert config.confirmation_scoring.primary_metric == "net_return_per_day"
    assert config.confirmation_scoring.dispersion_weight == 0.5
    assert config.confirmation_scoring.weak_window_floor == 0.0
    assert config.confirmation_scoring.weak_window_penalty == 0.001
    assert config.confirmation_scoring.min_trades_per_window == 200
    assert config.confirmation_scoring.low_trade_penalty == 0.001
    assert config.confirmation_scoring.min_symbol_count == 4
    assert config.confirmation_scoring.symbol_concentration_penalty == 0.00025
    assert config.artifacts.profile == "research"
    assert config.artifacts.keep_input_rows_csv is False
    assert config.artifacts.keep_input_rows_jsonl is False
    assert config.artifacts.keep_signals is True
    assert config.artifacts.large_artifact_max_mb == 100


def test_load_experiment_config_defaults_promotion_disabled(tmp_path: Path):
    config = load_experiment_config(write_config(tmp_path))

    assert config.promotion.enabled is False
    assert config.promotion.screen_on_scored_explore is False
    assert config.promotion.recent_window_ids == ()
    assert config.promotion.rotating_probe_window_ids == ()
    assert config.promotion.deep_probe_floor == 0.0
    assert config.promotion.near_equal_score_tolerance == 0.0
    assert config.promotion.cost_stress_id == "cost_stress"
    assert config.promotion.cost_fee_bps_per_side == 0.0
    assert config.promotion.cost_slippage_bps_per_side == 0.0
    assert config.promotion.cost_stress_min_ratio == 0.0


def test_load_experiment_config_parses_promotion_section(tmp_path: Path):
    config_text = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""

    config = load_experiment_config(write_config(tmp_path, config_text))

    assert config.promotion.enabled is True
    assert config.promotion.screen_on_scored_explore is True
    assert config.promotion.recent_window_ids == ("primary", "holdout")
    assert config.promotion.rotating_probe_window_ids == ("holdout",)
    assert config.promotion.deep_probe_floor == pytest.approx(-0.001)
    assert config.promotion.near_equal_score_tolerance == pytest.approx(0.0001)
    assert config.promotion.cost_stress_id == "realistic_costs"
    assert config.promotion.cost_fee_bps_per_side == pytest.approx(0.5)
    assert config.promotion.cost_slippage_bps_per_side == pytest.approx(0.5)
    assert config.promotion.cost_stress_min_ratio == pytest.approx(0.5)


def test_load_experiment_config_rejects_unknown_promotion_window(tmp_path: Path):
    bad = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "missing"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""

    with pytest.raises(ConfigError, match="promotion.recent_window_ids"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_promotion_recent_without_primary_window(tmp_path: Path):
    bad = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""

    with pytest.raises(ConfigError, match="research.primary_window_id"):
        load_experiment_config(write_config(tmp_path, bad))


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_load_experiment_config_rejects_invalid_cost_stress_ratio(tmp_path: Path, ratio: float):
    bad = VALID_TOML + f"""

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = {ratio}
"""

    with pytest.raises(ConfigError, match="cost_stress_min_ratio"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_enabled_zero_cost_promotion(tmp_path: Path):
    bad = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.0
cost_slippage_bps_per_side = 0.0
cost_stress_min_ratio = 0.5
"""

    with pytest.raises(ConfigError, match="nonzero fee or slippage"):
        load_experiment_config(write_config(tmp_path, bad))


@pytest.mark.parametrize("mode", ["fast", "confirm-all", ""])
def test_load_experiment_config_rejects_invalid_research_mode(tmp_path: Path, mode: str):
    bad = VALID_TOML + f"""

[research]
mode = "{mode}"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 4
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="research.mode"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_unknown_confirmation_window(tmp_path: Path):
    bad = VALID_TOML + """

[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "missing"]
parallel_workers = 4
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="confirmation_window_ids"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_confirmation_bundle_without_primary_window(tmp_path: Path):
    bad = VALID_TOML + """

[research]
mode = "explore"
primary_window_id = "holdout"
confirmation_window_ids = ["primary"]
parallel_workers = 1
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="primary_window_id"):
        load_experiment_config(write_config(tmp_path, bad))


@pytest.mark.parametrize("parallel_workers", [0, 5])
def test_load_experiment_config_rejects_invalid_parallel_workers(
    tmp_path: Path,
    parallel_workers: int,
):
    bad = VALID_TOML + f"""

[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = {parallel_workers}
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="parallel_workers"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_invalid_artifact_profile(tmp_path: Path):
    bad = VALID_TOML + """

[artifacts]
profile = "everything"
"""

    with pytest.raises(ConfigError, match="artifacts.profile"):
        load_experiment_config(write_config(tmp_path, bad))


def test_materialize_runner_toml_uses_selected_window_dates(tmp_path: Path):
    config = load_experiment_config(write_config(tmp_path))
    generated = tmp_path / "results" / ".generated" / "attempt_0001_primary.toml"

    materialize_runner_toml(config, generated, window_id="holdout", results_dir=Path("results"))

    text = generated.read_text()
    parsed = tomllib.loads(text)

    assert 'strategy_path = "strategy.py"' in text
    assert 'strategy_id = "demo_strategy"' in text
    assert 'start = "2024-05-01"' in text
    assert 'end = "2024-10-27"' in text
    assert 'results_dir = "results"' in text
    assert 'dataset = "equity_1min"' in text
    assert parsed["strategy_path"] == "strategy.py"
    assert parsed["strategy_id"] == "demo_strategy"
    assert parsed["data"]["kind"] == "bars"
    assert parsed["data"]["dataset"] == "equity_1min"
    assert parsed["data"]["symbols"] == ["SPY"]
    assert parsed["data"]["strict"] is True
    assert parsed["data"]["start"] == "2024-05-01"
    assert parsed["data"]["end"] == "2024-10-27"
    assert parsed["params"]["weight"] == 1.0
    assert parsed["params"]["hold_bars"] == 2
    assert parsed["fill_model"]["price"] == "close"
    assert parsed["fill_model"]["entry_lag_bars"] == 1
    assert parsed["fill_model"]["exit_lag_bars"] == 0
    assert parsed["cost_model"]["fee_bps_per_side"] == 1.0
    assert parsed["cost_model"]["slippage_bps_per_side"] == 2.0
    assert parsed["output"]["results_dir"] == "results"
    assert parsed["output"]["mode"] == "validate"
