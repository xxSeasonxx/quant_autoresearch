from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare import synthetic_bars
from strategy import generate_signals


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()

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
    attempt_dir = _attempt_dir(results_dir, attempt)
    attempt_dir.mkdir(parents=True)
    _write_experiment(attempt_dir / "experiment.yml", experiment)
    shutil.copy2(ROOT / "strategy.py", attempt_dir / "strategy_snapshot.py")

    try:
        bars = synthetic_bars(str(experiment["symbol"]))
        signals = generate_signals(bars, experiment)
        _write_bars_csv(attempt_dir / "bars.csv", bars)
        _write_signals_csv(attempt_dir / "signals.csv", signals)
        _write_request(attempt_dir / "request.json", experiment)

        screen = _run_engine("screen", attempt_dir / "request.json", summary=True)
        (attempt_dir / "screen_summary.json").write_text(screen.stdout)
        if screen.returncode != 0:
            (attempt_dir / "notes.md").write_text(f"screen failed\n\n```json\n{screen.stderr}```\n")
            return attempt_dir

        validate = _run_engine("validate", attempt_dir / "request.json", summary=True)
        (attempt_dir / "validate_summary.json").write_text(validate.stdout)
        if validate.returncode != 0:
            (attempt_dir / "notes.md").write_text(f"validate failed\n\n```json\n{validate.stderr}```\n")
            return attempt_dir

        evidence = _run_engine("validate", attempt_dir / "request.json", summary=False)
        (attempt_dir / "evidence.json").write_text(evidence.stdout)
        if evidence.returncode != 0:
            (attempt_dir / "notes.md").write_text(f"evidence failed\n\n```json\n{evidence.stderr}```\n")
            return attempt_dir

        (attempt_dir / "notes.md").write_text("completed\n")
        return attempt_dir
    except Exception as exc:
        (attempt_dir / "notes.md").write_text(f"request build failed\n\n{exc}\n")
        return attempt_dir


def _parse_scalar(value: str) -> str | int | float:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _attempt_dir(results_dir: Path, attempt: int) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return results_dir / f"{timestamp}_attempt_{attempt:04d}"


def _write_experiment(path: Path, experiment: dict[str, Any]) -> None:
    lines = [f"{key}: {value}" for key, value in experiment.items()]
    path.write_text("\n".join(lines) + "\n")


def _write_bars_csv(path: Path, bars: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("symbol", "timestamp", "open", "high", "low", "close"))
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "symbol": bar["symbol"],
                    "timestamp": bar["timestamp"].isoformat().replace("+00:00", "Z"),
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                }
            )


def _write_signals_csv(path: Path, signals: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("symbol", "decision_time", "side", "weight", "hold_bars"))
        writer.writeheader()
        for signal in signals:
            writer.writerow(
                {
                    "symbol": signal["symbol"],
                    "decision_time": signal["decision_time"].isoformat().replace("+00:00", "Z"),
                    "side": signal["side"],
                    "weight": signal["weight"],
                    "hold_bars": signal["hold_bars"],
                }
            )


def _write_request(path: Path, experiment: dict[str, Any]) -> None:
    payload = {
        "spec": {"strategy_id": experiment["strategy_id"]},
        "bars_csv": "bars.csv",
        "signals_csv": "signals.csv",
        "fill_model": {"price": "close", "entry_lag_bars": experiment["entry_lag_bars"]},
        "cost_model": {
            "fee_bps_per_side": experiment["fee_bps_per_side"],
            "slippage_bps_per_side": experiment["slippage_bps_per_side"],
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _run_engine(mode: str, request_file: Path, *, summary: bool) -> subprocess.CompletedProcess[str]:
    command = ["quant-engine", mode, "--request-file", str(request_file)]
    if summary:
        command.append("--summary")
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
