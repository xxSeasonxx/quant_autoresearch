from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import tomllib
from typing import Any


class ConfigError(ValueError):
    pass


MIN_RESEARCH_WINDOW_DAYS = 120
MAX_RESEARCH_WINDOW_DAYS = 180


@dataclass(frozen=True)
class WindowConfig:
    id: str
    start: str
    end: str

    @property
    def days(self) -> int:
        return _window_days(self.start, self.end, table=f"window {self.id}")


@dataclass(frozen=True)
class ScoringConfig:
    metric: str
    min_score_trades: int


@dataclass(frozen=True)
class ResearchConfig:
    mode: str
    primary_window_id: str
    confirmation_window_ids: tuple[str, ...]
    parallel_workers: int
    confirm_on_explore_keep: bool


@dataclass(frozen=True)
class ConfirmationScoringConfig:
    primary_metric: str
    dispersion_weight: float
    weak_window_floor: float
    weak_window_penalty: float
    min_trades_per_window: int
    low_trade_penalty: float
    min_symbol_count: int
    symbol_concentration_penalty: float


@dataclass(frozen=True)
class ArtifactConfig:
    profile: str
    keep_strategy_snapshot: bool
    keep_config: bool
    keep_summary: bool
    keep_evidence: bool
    keep_signals: bool
    keep_engine_request: bool
    keep_input_rows_csv: bool
    keep_input_rows_jsonl: bool
    compress_large_artifacts: bool
    large_artifact_max_mb: int


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
    research: ResearchConfig
    confirmation_scoring: ConfirmationScoringConfig
    artifacts: ArtifactConfig
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
    except OSError as exc:
        raise ConfigError(f"could not read {config_path}: {exc}") from exc
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
    selected_window_id = active_window_id or windows[0].id

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
    research = _parse_research(raw, window_ids, selected_window_id)
    confirmation_scoring = _parse_confirmation_scoring(raw)
    artifacts = _parse_artifacts(raw)
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
        research=research,
        confirmation_scoring=confirmation_scoring,
        artifacts=artifacts,
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
        days = _window_days(window.start, window.end, table=f"windows[{index}]")
        if not MIN_RESEARCH_WINDOW_DAYS <= days <= MAX_RESEARCH_WINDOW_DAYS:
            raise ConfigError(
                f"windows[{index}] must span {MIN_RESEARCH_WINDOW_DAYS} to "
                f"{MAX_RESEARCH_WINDOW_DAYS} days inclusive; got {days}"
            )
        if window.id in seen_ids:
            raise ConfigError(f"duplicate window id: {window.id}")
        seen_ids.add(window.id)
        windows.append(window)
    return tuple(windows)


def _window_days(start: str, end: str, *, table: str) -> int:
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError as exc:
        raise ConfigError(f"{table}.start and {table}.end must be YYYY-MM-DD dates") from exc

    days = (end_date - start_date).days + 1
    if days <= 0:
        raise ConfigError(f"{table}.end must be on or after {table}.start")
    return days


def _parse_scoring(raw_scoring: dict[str, Any]) -> ScoringConfig:
    metric = _required_str(raw_scoring, "metric", table="scoring")
    if metric != "net_return":
        raise ConfigError("scoring.metric must be net_return")
    min_score_trades = _required_positive_int(raw_scoring, "min_score_trades", table="scoring")
    return ScoringConfig(metric=metric, min_score_trades=min_score_trades)


def _parse_research(raw: dict[str, Any], window_ids: set[str], selected_window_id: str) -> ResearchConfig:
    table = raw.get("research")
    if table is None:
        return ResearchConfig(
            mode="explore",
            primary_window_id=selected_window_id,
            confirmation_window_ids=(selected_window_id,),
            parallel_workers=1,
            confirm_on_explore_keep=False,
        )
    if not isinstance(table, dict):
        raise ConfigError("research must be a table")

    mode = _required_str(table, "mode", table="research")
    if mode not in {"explore", "confirm"}:
        raise ConfigError("research.mode must be explore or confirm")

    primary_window_id = _required_str(table, "primary_window_id", table="research")
    if primary_window_id not in window_ids:
        raise ConfigError(f"research.primary_window_id does not match a configured window: {primary_window_id}")

    raw_confirmation_ids = table.get("confirmation_window_ids")
    if not isinstance(raw_confirmation_ids, list) or not raw_confirmation_ids:
        raise ConfigError("research.confirmation_window_ids must be a non-empty list")
    confirmation_window_ids = tuple(_list_item_str(raw_confirmation_ids, "research.confirmation_window_ids"))
    unknown = [window_id for window_id in confirmation_window_ids if window_id not in window_ids]
    if unknown:
        raise ConfigError(f"research.confirmation_window_ids contains unknown windows: {unknown}")
    if primary_window_id not in confirmation_window_ids:
        raise ConfigError("research.confirmation_window_ids must include research.primary_window_id")

    parallel_workers = _required_positive_int(table, "parallel_workers", table="research")
    if parallel_workers > 4:
        raise ConfigError("research.parallel_workers must be <= 4 for compact research runs")
    if parallel_workers > len(confirmation_window_ids):
        parallel_workers = len(confirmation_window_ids)
    confirm_on_explore_keep = _required_bool(table, "confirm_on_explore_keep", table="research")

    return ResearchConfig(
        mode=mode,
        primary_window_id=primary_window_id,
        confirmation_window_ids=confirmation_window_ids,
        parallel_workers=parallel_workers,
        confirm_on_explore_keep=confirm_on_explore_keep,
    )


def _parse_confirmation_scoring(raw: dict[str, Any]) -> ConfirmationScoringConfig:
    table = raw.get("confirmation_scoring")
    if table is None:
        return ConfirmationScoringConfig(
            primary_metric="net_return_per_day",
            dispersion_weight=0.5,
            weak_window_floor=0.0,
            weak_window_penalty=0.001,
            min_trades_per_window=200,
            low_trade_penalty=0.001,
            min_symbol_count=4,
            symbol_concentration_penalty=0.00025,
        )
    if not isinstance(table, dict):
        raise ConfigError("confirmation_scoring must be a table")

    primary_metric = _required_str(table, "primary_metric", table="confirmation_scoring")
    if primary_metric != "net_return_per_day":
        raise ConfigError("confirmation_scoring.primary_metric must be net_return_per_day")

    return ConfirmationScoringConfig(
        primary_metric=primary_metric,
        dispersion_weight=_required_non_negative_float(table, "dispersion_weight", table="confirmation_scoring"),
        weak_window_floor=float(_required_number(table, "weak_window_floor", table="confirmation_scoring")),
        weak_window_penalty=_required_non_negative_float(table, "weak_window_penalty", table="confirmation_scoring"),
        min_trades_per_window=_required_positive_int(table, "min_trades_per_window", table="confirmation_scoring"),
        low_trade_penalty=_required_non_negative_float(table, "low_trade_penalty", table="confirmation_scoring"),
        min_symbol_count=_required_positive_int(table, "min_symbol_count", table="confirmation_scoring"),
        symbol_concentration_penalty=_required_non_negative_float(
            table,
            "symbol_concentration_penalty",
            table="confirmation_scoring",
        ),
    )


def _parse_artifacts(raw: dict[str, Any]) -> ArtifactConfig:
    table = raw.get("artifacts")
    if table is None:
        return ArtifactConfig(
            profile="research",
            keep_strategy_snapshot=True,
            keep_config=True,
            keep_summary=True,
            keep_evidence=True,
            keep_signals=True,
            keep_engine_request=False,
            keep_input_rows_csv=False,
            keep_input_rows_jsonl=False,
            compress_large_artifacts=False,
            large_artifact_max_mb=100,
        )
    if not isinstance(table, dict):
        raise ConfigError("artifacts must be a table")

    profile = _required_str(table, "profile", table="artifacts")
    if profile not in {"research", "debug"}:
        raise ConfigError("artifacts.profile must be research or debug")

    return ArtifactConfig(
        profile=profile,
        keep_strategy_snapshot=_required_bool(table, "keep_strategy_snapshot", table="artifacts"),
        keep_config=_required_bool(table, "keep_config", table="artifacts"),
        keep_summary=_required_bool(table, "keep_summary", table="artifacts"),
        keep_evidence=_required_bool(table, "keep_evidence", table="artifacts"),
        keep_signals=_required_bool(table, "keep_signals", table="artifacts"),
        keep_engine_request=_required_bool(table, "keep_engine_request", table="artifacts"),
        keep_input_rows_csv=_required_bool(table, "keep_input_rows_csv", table="artifacts"),
        keep_input_rows_jsonl=_required_bool(table, "keep_input_rows_jsonl", table="artifacts"),
        compress_large_artifacts=_required_bool(table, "compress_large_artifacts", table="artifacts"),
        large_artifact_max_mb=_required_positive_int(table, "large_artifact_max_mb", table="artifacts"),
    )


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


def _required_bool(raw: dict[str, Any], key: str, *, table: str | None = None) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"missing required boolean field: {_field_name(key, table)}")
    return value


def _required_positive_int(raw: dict[str, Any], key: str, *, table: str | None = None) -> int:
    value = _required_int(raw, key, table=table)
    if value <= 0:
        raise ConfigError(f"{_field_name(key, table)} must be a positive integer")
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


def _required_non_negative_float(raw: dict[str, Any], key: str, *, table: str | None = None) -> float:
    value = _required_number(raw, key, table=table)
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise ConfigError(f"{_field_name(key, table)} must be finite and non-negative")
    return parsed


def _list_item_str(values: list[Any], field_name: str) -> list[str]:
    parsed: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or value == "":
            raise ConfigError(f"{field_name}[{index}] must be a non-empty string")
        parsed.append(value)
    return parsed


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
