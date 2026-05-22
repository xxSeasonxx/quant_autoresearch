from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import tomllib
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class WindowConfig:
    id: str
    start: str
    end: str


@dataclass(frozen=True)
class ScoringConfig:
    metric: str
    min_score_trades: int


@dataclass(frozen=True)
class ExperimentConfig:
    strategy_id: str
    strategy_path: Path
    source_strategy_path: str | None
    max_attempts: int
    windows: tuple[WindowConfig, ...]
    active_window_id: str | None
    data: dict[str, Any]
    params: dict[str, Any]
    fill_model: dict[str, Any]
    cost_model: dict[str, Any]
    scoring: ScoringConfig
    output: dict[str, Any]

    @property
    def selected_window_id(self) -> str:
        if self.active_window_id is not None:
            return self.active_window_id
        if not self.windows:
            raise ConfigError("experiment config requires at least one window")
        return self.windows[0].id

    def window_by_id(self, window_id: str) -> WindowConfig:
        for window in self.windows:
            if window.id == window_id:
                return window
        raise ConfigError(f"unknown window_id: {window_id}")


def load_experiment_config(path: str | Path = "experiment.toml") -> ExperimentConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as file:
            raw = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    strategy_id = _required_str(raw, "strategy_id")
    strategy_path = Path(_required_str(raw, "strategy_path"))
    source_strategy_path = _optional_str(raw, "source_strategy_path")
    max_attempts = _required_positive_int(raw, "max_attempts")
    active_window_id = _optional_str(raw, "active_window_id")

    windows = _parse_windows(raw.get("windows"))
    window_ids = {window.id for window in windows}
    if active_window_id is not None and active_window_id not in window_ids:
        raise ConfigError(f"active_window_id does not match a configured window: {active_window_id}")

    data = _required_table(raw, "data")
    _required_str(data, "kind", table="data")
    params = _required_table(raw, "params")
    fill_model = _required_table(raw, "fill_model")
    _required_str(fill_model, "price", table="fill_model")
    _required_int(fill_model, "entry_lag_bars", table="fill_model")
    _required_int(fill_model, "exit_lag_bars", table="fill_model")
    cost_model = _required_table(raw, "cost_model")
    _required_number(cost_model, "fee_bps_per_side", table="cost_model")
    _required_number(cost_model, "slippage_bps_per_side", table="cost_model")
    scoring = _parse_scoring(_required_table(raw, "scoring"))
    output = _required_table(raw, "output")
    _required_str(output, "results_dir", table="output")
    output_mode = _required_str(output, "mode", table="output")
    if output_mode not in {"screen", "validate"}:
        raise ConfigError("output.mode must be screen or validate")

    for table_name, table in (
        ("data", data),
        ("params", params),
        ("fill_model", fill_model),
        ("cost_model", cost_model),
        ("output", output),
    ):
        _validate_finite_numbers(table_name, table)

    return ExperimentConfig(
        strategy_id=strategy_id,
        strategy_path=strategy_path,
        source_strategy_path=source_strategy_path,
        max_attempts=max_attempts,
        windows=windows,
        active_window_id=active_window_id,
        data=dict(data),
        params=dict(params),
        fill_model=dict(fill_model),
        cost_model=dict(cost_model),
        scoring=scoring,
        output=dict(output),
    )


def materialize_runner_toml(
    config: ExperimentConfig,
    path: str | Path,
    *,
    window_id: str,
    results_dir: Path,
) -> None:
    window = config.window_by_id(window_id)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    data = dict(config.data)
    data["start"] = window.start
    data["end"] = window.end

    output = dict(config.output)
    output["results_dir"] = str(results_dir)

    sections = [
        _format_key_value("strategy_path", str(config.strategy_path)),
        _format_key_value("strategy_id", config.strategy_id),
        "",
        _format_table("data", data),
        "",
        _format_table("params", config.params),
        "",
        _format_table("fill_model", config.fill_model),
        "",
        _format_table("cost_model", config.cost_model),
        "",
        _format_table("output", output),
    ]
    destination.write_text("\n".join(sections).rstrip() + "\n")


def _parse_windows(raw_windows: Any) -> tuple[WindowConfig, ...]:
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ConfigError("experiment config requires at least one window")

    windows: list[WindowConfig] = []
    seen_ids: set[str] = set()
    for index, raw_window in enumerate(raw_windows):
        if not isinstance(raw_window, dict):
            raise ConfigError(f"windows[{index}] must be a table")
        window = WindowConfig(
            id=_required_str(raw_window, "id", table=f"windows[{index}]"),
            start=_required_str(raw_window, "start", table=f"windows[{index}]"),
            end=_required_str(raw_window, "end", table=f"windows[{index}]"),
        )
        if window.id in seen_ids:
            raise ConfigError(f"duplicate window id: {window.id}")
        seen_ids.add(window.id)
        windows.append(window)
    return tuple(windows)


def _parse_scoring(raw_scoring: dict[str, Any]) -> ScoringConfig:
    metric = _required_str(raw_scoring, "metric", table="scoring")
    if metric != "net_return":
        raise ConfigError("scoring.metric must be net_return")
    min_score_trades = _required_int(raw_scoring, "min_score_trades", table="scoring")
    return ScoringConfig(metric=metric, min_score_trades=min_score_trades)


def _required_table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"missing required table: {key}")
    return value


def _required_str(raw: dict[str, Any], key: str, *, table: str | None = None) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value == "":
        raise ConfigError(f"missing required string field: {_field_name(key, table)}")
    return value


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if value is None:
        return None
    if not isinstance(value, str) or value == "":
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _required_positive_int(raw: dict[str, Any], key: str) -> int:
    value = _required_int(raw, key)
    if value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def _required_int(raw: dict[str, Any], key: str, *, table: str | None = None) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"missing required integer field: {_field_name(key, table)}")
    return value


def _required_number(raw: dict[str, Any], key: str, *, table: str | None = None) -> int | float:
    value = raw.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"missing required numeric field: {_field_name(key, table)}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigError(f"{_field_name(key, table)} must be finite")
    return value


def _field_name(key: str, table: str | None) -> str:
    if table is None:
        return key
    return f"{table}.{key}"


def _validate_finite_numbers(path: str, value: Any) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConfigError(f"{path} contains non-finite numeric value")
        return
    if isinstance(value, int):
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite_numbers(f"{path}.{key}", nested)
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_finite_numbers(f"{path}[{index}]", nested)


def _format_table(name: str, values: dict[str, Any]) -> str:
    lines = [f"[{name}]"]
    lines.extend(_format_key_value(key, value) for key, value in values.items())
    return "\n".join(lines)


def _format_key_value(key: str, value: Any) -> str:
    return f"{key} = {_toml_scalar(value)}"


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConfigError("TOML scalar floats must be finite")
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    raise ConfigError(f"unsupported TOML scalar type: {type(value).__name__}")
