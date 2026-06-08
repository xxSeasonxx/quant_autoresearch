from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Any, Mapping
import tomllib

from gates import GateConfig
from objective import LoopConfig, ObjectiveConfig

ParamValue = int | float


@dataclass(frozen=True)
class DataConfig:
    kind: str
    dataset: str | None
    symbols: tuple[str, ...]
    start: str
    end: str


@dataclass(frozen=True)
class FillModel:
    price: str
    entry_lag_bars: int
    exit_lag_bars: int


@dataclass(frozen=True)
class CostModel:
    fee_bps_per_side: float
    slippage_bps_per_side: float


@dataclass(frozen=True)
class OutputConfig:
    results_dir: str
    artifact_profile: str = "summary"
    quick_checks: bool = True
    diagnostic_sample_trades: int = 0


@dataclass(frozen=True)
class ParamBound:
    min: float
    max: float


@dataclass(frozen=True)
class ExperimentConfig:
    params: dict[str, ParamValue]
    bounds: dict[str, ParamBound]


@dataclass(frozen=True)
class ProtocolConfig:
    strategy_path: str
    strategy_id: str
    data: DataConfig
    fill_model: FillModel
    cost_model: CostModel
    output: OutputConfig
    loop: LoopConfig
    objective: ObjectiveConfig
    gates: GateConfig

    def with_output(self, *, results_dir: str) -> "ProtocolConfig":
        return replace(self, output=replace(self.output, results_dir=results_dir))


def _required(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ValueError(f"missing required protocol key: {key}")
    return mapping[key]


def _numeric(value: object, *, name: str) -> ParamValue:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not bool")
    if isinstance(value, int | float):
        if not isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
        return value
    raise ValueError(f"{name} must be numeric")


def load_protocol(path: str | Path) -> ProtocolConfig:
    data = tomllib.loads(Path(path).read_text())
    raw_data = _required(data, "data")
    raw_fill = _required(data, "fill_model")
    raw_cost = _required(data, "cost_model")
    raw_output = _required(data, "output")
    raw_loop = _required(data, "loop")
    raw_objective = _required(data, "objective")
    raw_gates = _required(data, "gates")

    return ProtocolConfig(
        strategy_path=str(_required(data, "strategy_path")),
        strategy_id=str(_required(data, "strategy_id")),
        data=DataConfig(
            kind=str(_required(raw_data, "kind")),
            dataset=raw_data.get("dataset"),
            symbols=tuple(str(symbol) for symbol in _required(raw_data, "symbols")),
            start=str(_required(raw_data, "start")),
            end=str(_required(raw_data, "end")),
        ),
        fill_model=FillModel(
            price=str(_required(raw_fill, "price")),
            entry_lag_bars=int(_required(raw_fill, "entry_lag_bars")),
            exit_lag_bars=int(_required(raw_fill, "exit_lag_bars")),
        ),
        cost_model=CostModel(
            fee_bps_per_side=float(_required(raw_cost, "fee_bps_per_side")),
            slippage_bps_per_side=float(_required(raw_cost, "slippage_bps_per_side")),
        ),
        output=OutputConfig(
            results_dir=str(_required(raw_output, "results_dir")),
            artifact_profile=str(raw_output.get("artifact_profile", "summary")),
            quick_checks=bool(raw_output.get("quick_checks", True)),
            diagnostic_sample_trades=int(raw_output.get("diagnostic_sample_trades", 5)),
        ),
        loop=LoopConfig(
            plateau_patience=int(_required(raw_loop, "plateau_patience")),
            max_iterations=int(_required(raw_loop, "max_iterations")),
            min_abs_improvement=float(_required(raw_loop, "min_abs_improvement")),
            min_rel_improvement=float(_required(raw_loop, "min_rel_improvement")),
            baseline_grace_iterations=int(
                raw_loop.get("baseline_grace_iterations", raw_loop["plateau_patience"])
            ),
        ),
        objective=ObjectiveConfig(
            kind=str(_required(raw_objective, "kind")),
            subwindows=int(_required(raw_objective, "subwindows")),
        ),
        gates=GateConfig(
            min_trades=int(_required(raw_gates, "min_trades")),
            min_trades_per_subwindow=int(
                _required(raw_gates, "min_trades_per_subwindow")
            ),
            max_symbol_concentration=float(
                _required(raw_gates, "max_symbol_concentration")
            ),
            min_cost_stress_score=float(_required(raw_gates, "min_cost_stress_score")),
            max_components=int(_required(raw_gates, "max_components")),
            max_params=int(_required(raw_gates, "max_params")),
            train_score_floor=float(_required(raw_gates, "train_score_floor")),
            subwindows=int(_required(raw_objective, "subwindows")),
        ),
    )


def load_experiment(path: str | Path) -> ExperimentConfig:
    data = tomllib.loads(Path(path).read_text())
    raw_params = data.get("params", {})
    if not isinstance(raw_params, dict):
        raise ValueError("experiment [params] must be a table")

    raw_bounds = data.get("bounds", {})
    if not isinstance(raw_bounds, dict):
        raise ValueError("experiment [bounds] must be a table")

    params = {
        str(key): _numeric(value, name=f"params.{key}")
        for key, value in raw_params.items()
    }
    bounds: dict[str, ParamBound] = {}
    for key, raw_bound in raw_bounds.items():
        if not isinstance(raw_bound, dict):
            raise ValueError(f"bounds.{key} must be a table")
        lower = float(_numeric(_required(raw_bound, "min"), name=f"bounds.{key}.min"))
        upper = float(_numeric(_required(raw_bound, "max"), name=f"bounds.{key}.max"))
        if lower > upper:
            raise ValueError(f"bounds.{key}.min must be <= bounds.{key}.max")
        bounds[str(key)] = ParamBound(min=lower, max=upper)

    missing_bounds = set(params) - set(bounds)
    if missing_bounds:
        raise ValueError(f"missing bounds for params: {sorted(missing_bounds)}")
    orphan_bounds = set(bounds) - set(params)
    if orphan_bounds:
        raise ValueError(f"bounds without params: {sorted(orphan_bounds)}")

    for key, value in params.items():
        bound = bounds[key]
        numeric_value = float(value)
        if numeric_value < bound.min or numeric_value > bound.max:
            raise ValueError(
                f"params.{key}={value} outside bounds [{bound.min}, {bound.max}]"
            )

    return ExperimentConfig(params=params, bounds=bounds)


def load_params(path: str | Path) -> dict[str, ParamValue]:
    return load_experiment(path).params


def build_quick_run_config(
    protocol: ProtocolConfig,
    params: Mapping[str, object],
    *,
    results_dir: str | Path | None = None,
) -> dict[str, object]:
    data_block: dict[str, object] = {
        "kind": protocol.data.kind,
        "symbols": list(protocol.data.symbols),
        "start": protocol.data.start,
        "end": protocol.data.end,
    }
    if protocol.data.dataset is not None:
        data_block["dataset"] = protocol.data.dataset
    return {
        "strategy_path": protocol.strategy_path,
        "strategy_id": protocol.strategy_id,
        "data": data_block,
        "params": dict(params),
        "fill_model": {
            "price": protocol.fill_model.price,
            "entry_lag_bars": protocol.fill_model.entry_lag_bars,
            "exit_lag_bars": protocol.fill_model.exit_lag_bars,
        },
        "cost_model": {
            "fee_bps_per_side": protocol.cost_model.fee_bps_per_side,
            "slippage_bps_per_side": protocol.cost_model.slippage_bps_per_side,
        },
        "output": {
            "results_dir": str(results_dir or protocol.output.results_dir),
            "artifact_profile": protocol.output.artifact_profile,
            "quick_checks": protocol.output.quick_checks,
            "diagnostic_sample_trades": max(1, protocol.output.diagnostic_sample_trades),
        },
    }


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {value!r}")


def _write_block(lines: list[str], name: str, values: Mapping[str, object]) -> None:
    lines.append("")
    lines.append(f"[{name}]")
    for key, value in values.items():
        lines.append(f"{key} = {_toml_value(value)}")


def dumps_quick_run_config(config: Mapping[str, object]) -> str:
    lines = [
        f"strategy_path = {_toml_value(config['strategy_path'])}",
        f"strategy_id = {_toml_value(config['strategy_id'])}",
    ]
    for section in ["data", "params", "fill_model", "cost_model", "output"]:
        _write_block(lines, section, config[section])  # type: ignore[arg-type]
    return "\n".join(lines) + "\n"


def write_quick_run_config(
    protocol: ProtocolConfig,
    params: Mapping[str, object],
    path: str | Path,
    *,
    results_dir: str | Path | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = build_quick_run_config(protocol, params, results_dir=results_dir)
    destination.write_text(dumps_quick_run_config(config))
    return destination
