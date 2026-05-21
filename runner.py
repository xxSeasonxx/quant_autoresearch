from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import quant_strategies.runner.data_loader as runner_data_loader
from prepare import synthetic_bars
from quant_strategies.runner import RunResult, run_config
from quant_strategies.runner.data_loader import LoadedData


ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args(argv)

    experiment = load_experiment(ROOT / "experiment.yml")
    max_attempts = args.max_attempts or int(experiment.get("max_attempts", 1))
    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = ROOT / results_dir

    for attempt in range(1, max_attempts + 1):
        run_once(experiment, attempt=attempt, results_dir=results_dir)
    return 0


def load_experiment(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, raw_value = stripped.split(":", 1)
        values[key.strip()] = _parse_scalar(raw_value.strip())
    return values


def run_once(experiment: dict[str, Any], *, attempt: int, results_dir: Path) -> Path:
    del attempt
    results_dir = results_dir.resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    repo_root = _repo_root_for_results(results_dir)
    config_path = _write_run_config(experiment, repo_root=repo_root, results_dir=results_dir)
    rows = synthetic_bars(str(experiment["symbol"]))

    original_load_data = runner_data_loader.load_data
    runner_data_loader.load_data = lambda config: LoadedData(rows=[dict(row) for row in rows])
    original_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        result = run_config(config_path, repo_root=repo_root)
    finally:
        sys.dont_write_bytecode = original_dont_write_bytecode
        runner_data_loader.load_data = original_load_data

    if result.result_dir is not None:
        return result.result_dir
    return _write_config_failure(results_dir, result)


def _parse_scalar(value: str) -> str | int | float:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _attempt_dir(results_dir: Path, attempt: int) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S%fZ")
    return results_dir / f"{timestamp}_attempt_{attempt:04d}"


def _repo_root_for_results(results_dir: Path) -> Path:
    resolved_root = ROOT.resolve()
    try:
        results_dir.relative_to(resolved_root)
    except ValueError:
        return results_dir
    return resolved_root


def _write_run_config(experiment: dict[str, Any], *, repo_root: Path, results_dir: Path) -> Path:
    config_path = results_dir / ".autoresearch_run.toml"
    if repo_root == ROOT.resolve():
        strategy_path = _relative_to(ROOT / "strategy.py", repo_root)
        output_dir = _relative_to(results_dir, repo_root)
    else:
        shutil.copy2(ROOT / "strategy.py", repo_root / "strategy.py")
        strategy_path = "strategy.py"
        output_dir = "."

    config_path.write_text(_run_config_toml(experiment, strategy_path=strategy_path, output_dir=output_dir))
    return config_path


def _run_config_toml(experiment: dict[str, Any], *, strategy_path: str, output_dir: str) -> str:
    symbol = str(experiment["symbol"])
    start, end = _synthetic_window(symbol)
    params = "\n".join(
        f"{key} = {_toml_scalar(value)}"
        for key, value in sorted(experiment.items())
        if key
        not in {
            "fee_bps_per_side",
            "slippage_bps_per_side",
            "entry_lag_bars",
            "exit_lag_bars",
            "fill_price",
            "allow_same_bar_close_fill",
            "max_attempts",
        }
    )
    return f"""strategy_path = {_toml_scalar(strategy_path)}
strategy_id = {_toml_scalar(str(experiment["strategy_id"]))}

[data]
kind = "bars"
dataset = "synthetic_autoresearch"
symbols = [{_toml_scalar(symbol)}]
start = {_toml_scalar(start)}
end = {_toml_scalar(end)}
strict = true

[params]
{params}

[fill_model]
price = {_toml_scalar(str(experiment.get("fill_price", "close")))}
entry_lag_bars = {int(experiment.get("entry_lag_bars", 1))}
exit_lag_bars = {int(experiment.get("exit_lag_bars", 0))}
allow_same_bar_close_fill = {_toml_scalar(bool(experiment.get("allow_same_bar_close_fill", False)))}

[cost_model]
fee_bps_per_side = {float(experiment.get("fee_bps_per_side", 0.0))}
slippage_bps_per_side = {float(experiment.get("slippage_bps_per_side", 0.0))}

[output]
results_dir = {_toml_scalar(output_dir)}
mode = "validate"
"""


def _synthetic_window(symbol: str) -> tuple[str, str]:
    timestamps = [bar["timestamp"] for bar in synthetic_bars(symbol)]
    dates = [timestamp.date().isoformat() for timestamp in timestamps if isinstance(timestamp, datetime)]
    return min(dates), max(dates)


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value))


def _relative_to(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root).as_posix()


def _write_config_failure(results_dir: Path, result: RunResult) -> Path:
    attempt_dir = _attempt_dir(results_dir, 0)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    (attempt_dir / "notes.md").write_text(f"runner config failed\n\n{result.message}\n")
    return attempt_dir


if __name__ == "__main__":
    raise SystemExit(main())
