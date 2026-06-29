from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Any, Mapping
import tomllib

from gates import GateConfig
from objective import LoopConfig, ObjectiveConfig

ParamValue = int | float | bool | str


@dataclass(frozen=True)
class DataConfig:
    kind: str
    dataset: str | None
    symbols: tuple[str, ...]
    start: str
    end: str
    load_start: str | None = None
    load_end: str | None = None


@dataclass(frozen=True)
class FillModel:
    price: str
    entry_lag_bars: int


@dataclass(frozen=True)
class CostModel:
    fee_bps_per_side: float
    slippage_bps_per_side: float


@dataclass(frozen=True)
class CapacityModel:
    """Operator-frozen capacity envelope passed through to the runner.

    `mode = "off"` runs no capacity pricing; the upstream portfolio book treats a
    traded notional book with capacity off as non-scoreable, so a real thesis must
    set `mode = "adv_impact"` with the full impact parameter set before its book
    can score.
    """

    mode: str
    portfolio_notional: float | None = None
    adv_lookback_bars: int | None = None
    adv_min_observations: int | None = None
    max_bar_participation: float | None = None
    max_adv_participation: float | None = None
    impact_coefficient_bps: float | None = None
    impact_exponent: float | None = None


@dataclass(frozen=True)
class LeverageBudget:
    """Operator-frozen gross/net exposure ceiling passed through to the runner.

    Intended standing exposure beyond the ceiling is a fail-closed, non-scoreable
    feasibility verdict upstream; it is never clamped. Default is fully-invested
    `1.0/1.0`.
    """

    max_gross_exposure: float = 1.0
    max_net_exposure: float = 1.0


@dataclass(frozen=True)
class RiskBudgetConfig:
    """Operator-frozen conversion from target-book shape to executable book size.

    Upstream owns the sizing math; this is the operator-frozen config passed
    through. `calibrate_vol` sizes the book to `target_volatility`; `fixed_scale`
    applies `book_scale` to the normalized shape. `annualization_periods_per_year`
    must match the bar cadence and is the run-level `P` the money score reads back
    from the sizing report.
    """

    mode: str
    annualization_periods_per_year: int
    target_volatility: float | None = None
    book_scale: float | None = None


@dataclass(frozen=True)
class OutputConfig:
    results_dir: str
    artifact_profile: str = "summary"
    quick_checks: bool = True
    diagnostic_sample_trades: int = 0
    causality_check: str = "emitted"
    strict_probe_limit: int | None = None
    focused_probe_limit: int | None = None
    focused_timeout_seconds: float | None = None
    micro_probe_limit: int | None = None
    micro_timeout_seconds: float | None = None
    foundation_subwindows: int | None = None
    foundation_cost_stress_multiplier: float | None = None


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
    capacity_model: CapacityModel
    leverage_budget: LeverageBudget
    risk_budget: RiskBudgetConfig
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


def _numeric(value: object, *, name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not bool")
    if isinstance(value, int | float):
        if not isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
        return value
    raise ValueError(f"{name} must be numeric")


def _param_value(value: object, *, name: str) -> ParamValue:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        if not isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
        return value
    if isinstance(value, str):
        return value
    raise ValueError(f"{name} must be a numeric, boolean, or string scalar")


def _is_numeric_param(value: ParamValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _integer(value: object, *, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, not bool")
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _floating(value: object, *, name: str) -> float:
    return float(_numeric(value, name=name))


def _boolean(value: object, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _causality_check(value: object, *, name: str) -> str:
    parsed = str(value)
    if parsed not in {"off", "emitted", "strict", "focused", "micro"}:
        raise ValueError(f"{name} must be one of: off, emitted, strict, focused, micro")
    return parsed


def _positive_int(value: object, *, name: str) -> int:
    parsed = _integer(value, name=name)
    if parsed <= 0:
        raise ValueError(f"{name} must be > 0")
    return parsed


def _nonnegative_int(value: object, *, name: str) -> int:
    parsed = _integer(value, name=name)
    if parsed < 0:
        raise ValueError(f"{name} must be >= 0")
    return parsed


def _optional_nonnegative_int(value: object, *, name: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, name=name)


def _nonnegative_float(value: object, *, name: str) -> float:
    parsed = _floating(value, name=name)
    if parsed < 0.0:
        raise ValueError(f"{name} must be >= 0")
    return parsed


def _min_float(value: object, *, name: str, minimum: float) -> float:
    parsed = _floating(value, name=name)
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _positive_float(value: object, *, name: str) -> float:
    parsed = _floating(value, name=name)
    if parsed <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return parsed


def _fraction(value: object, *, name: str) -> float:
    parsed = _floating(value, name=name)
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return parsed


def _symbols(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("data.symbols must be a list of non-empty strings")
    symbols: list[str] = []
    for symbol in value:
        if not isinstance(symbol, str):
            raise ValueError("data.symbols must be a list of non-empty strings")
        normalized = symbol.strip()
        if not normalized:
            raise ValueError("data.symbols must include only non-empty strings")
        symbols.append(normalized)
    if not symbols:
        raise ValueError("data.symbols must include at least one symbol")
    return tuple(symbols)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _capacity_mode(value: object) -> str:
    parsed = str(value)
    if parsed not in {"off", "adv_impact"}:
        raise ValueError("capacity_model.mode must be one of: off, adv_impact")
    return parsed


def _load_capacity_model(raw: Mapping[str, Any]) -> CapacityModel:
    mode = _capacity_mode(_required(raw, "mode"))
    if mode == "off":
        return CapacityModel(mode="off")
    adv_lookback_bars = _positive_int(
        _required(raw, "adv_lookback_bars"), name="capacity_model.adv_lookback_bars"
    )
    adv_min_observations = _positive_int(
        _required(raw, "adv_min_observations"),
        name="capacity_model.adv_min_observations",
    )
    if adv_min_observations > adv_lookback_bars:
        raise ValueError(
            "capacity_model.adv_min_observations must be <= capacity_model.adv_lookback_bars"
        )
    return CapacityModel(
        mode=mode,
        portfolio_notional=_positive_float(
            _required(raw, "portfolio_notional"),
            name="capacity_model.portfolio_notional",
        ),
        adv_lookback_bars=adv_lookback_bars,
        adv_min_observations=adv_min_observations,
        max_bar_participation=_positive_float(
            _required(raw, "max_bar_participation"),
            name="capacity_model.max_bar_participation",
        ),
        max_adv_participation=_positive_float(
            _required(raw, "max_adv_participation"),
            name="capacity_model.max_adv_participation",
        ),
        impact_coefficient_bps=_nonnegative_float(
            _required(raw, "impact_coefficient_bps"),
            name="capacity_model.impact_coefficient_bps",
        ),
        impact_exponent=_positive_float(
            _required(raw, "impact_exponent"), name="capacity_model.impact_exponent"
        ),
    )


def _risk_budget_mode(value: object) -> str:
    parsed = str(value)
    if parsed not in {"calibrate_vol", "fixed_scale"}:
        raise ValueError("risk_budget.mode must be one of: calibrate_vol, fixed_scale")
    return parsed


def _load_risk_budget(raw: Mapping[str, Any]) -> RiskBudgetConfig:
    mode = _risk_budget_mode(_required(raw, "mode"))
    periods = _positive_int(
        _required(raw, "annualization_periods_per_year"),
        name="risk_budget.annualization_periods_per_year",
    )
    target_volatility: float | None = None
    book_scale: float | None = None
    if mode == "calibrate_vol":
        target_volatility = _positive_float(
            _required(raw, "target_volatility"),
            name="risk_budget.target_volatility",
        )
        if "book_scale" in raw:
            raise ValueError(
                "risk_budget.book_scale is only valid when mode = 'fixed_scale'"
            )
    else:
        book_scale = _positive_float(
            _required(raw, "book_scale"), name="risk_budget.book_scale"
        )
        if "target_volatility" in raw:
            raise ValueError(
                "risk_budget.target_volatility is only valid when mode = 'calibrate_vol'"
            )
    return RiskBudgetConfig(
        mode=mode,
        annualization_periods_per_year=periods,
        target_volatility=target_volatility,
        book_scale=book_scale,
    )


def _load_leverage_budget(raw: Mapping[str, Any]) -> LeverageBudget:
    return LeverageBudget(
        max_gross_exposure=_min_float(
            raw.get("max_gross_exposure", 1.0),
            name="leverage_budget.max_gross_exposure",
            minimum=1.0,
        ),
        max_net_exposure=_min_float(
            raw.get("max_net_exposure", 1.0),
            name="leverage_budget.max_net_exposure",
            minimum=1.0,
        ),
    )


def load_protocol(path: str | Path) -> ProtocolConfig:
    data = tomllib.loads(Path(path).read_text())
    raw_data = _required(data, "data")
    raw_fill = _required(data, "fill_model")
    raw_cost = _required(data, "cost_model")
    raw_capacity = _required(data, "capacity_model")
    raw_leverage = data.get("leverage_budget", {})
    if not isinstance(raw_leverage, Mapping):
        raise ValueError("leverage_budget must be a table")
    raw_risk_budget = _required(data, "risk_budget")
    if not isinstance(raw_risk_budget, Mapping):
        raise ValueError("risk_budget must be a table")
    raw_output = _required(data, "output")
    raw_loop = _required(data, "loop")
    raw_objective = _required(data, "objective")
    raw_gates = _required(data, "gates")
    symbols = _symbols(_required(raw_data, "symbols"))
    fill_price = str(_required(raw_fill, "price"))
    entry_lag_bars = _positive_int(
        _required(raw_fill, "entry_lag_bars"),
        name="fill_model.entry_lag_bars",
    )
    objective_kind = str(_required(raw_objective, "kind"))
    if objective_kind != "return_lcb_subwindow":
        raise ValueError(f"objective.kind unsupported: {objective_kind}")
    subwindows = _positive_int(
        _required(raw_objective, "subwindows"), name="objective.subwindows"
    )
    foundation_subwindows = _positive_int(
        raw_output.get("foundation_subwindows", subwindows),
        name="output.foundation_subwindows",
    )
    if foundation_subwindows != subwindows:
        raise ValueError("output.foundation_subwindows must equal objective.subwindows")
    foundation_cost_stress_multiplier = _min_float(
        raw_output.get("foundation_cost_stress_multiplier", 2.0),
        name="output.foundation_cost_stress_multiplier",
        minimum=1.0,
    )

    return ProtocolConfig(
        strategy_path=str(_required(data, "strategy_path")),
        strategy_id=str(_required(data, "strategy_id")),
        data=DataConfig(
            kind=str(_required(raw_data, "kind")),
            dataset=raw_data.get("dataset"),
            symbols=symbols,
            start=str(_required(raw_data, "start")),
            end=str(_required(raw_data, "end")),
            load_start=_optional_text(raw_data.get("load_start")),
            load_end=_optional_text(raw_data.get("load_end")),
        ),
        fill_model=FillModel(
            price=fill_price,
            entry_lag_bars=entry_lag_bars,
        ),
        cost_model=CostModel(
            fee_bps_per_side=_nonnegative_float(
                _required(raw_cost, "fee_bps_per_side"),
                name="cost_model.fee_bps_per_side",
            ),
            slippage_bps_per_side=_nonnegative_float(
                _required(raw_cost, "slippage_bps_per_side"),
                name="cost_model.slippage_bps_per_side",
            ),
        ),
        capacity_model=_load_capacity_model(raw_capacity),
        leverage_budget=_load_leverage_budget(raw_leverage),
        risk_budget=_load_risk_budget(raw_risk_budget),
        output=OutputConfig(
            results_dir=str(_required(raw_output, "results_dir")),
            artifact_profile=str(raw_output.get("artifact_profile", "summary")),
            quick_checks=_boolean(
                raw_output.get("quick_checks", True), name="output.quick_checks"
            ),
            diagnostic_sample_trades=_positive_int(
                raw_output.get("diagnostic_sample_trades", 5),
                name="output.diagnostic_sample_trades",
            ),
            causality_check=_causality_check(
                raw_output.get("causality_check", "emitted"),
                name="output.causality_check",
            ),
            strict_probe_limit=_optional_nonnegative_int(
                raw_output.get("strict_probe_limit"),
                name="output.strict_probe_limit",
            ),
            focused_probe_limit=_optional_nonnegative_int(
                raw_output.get("focused_probe_limit"),
                name="output.focused_probe_limit",
            ),
            focused_timeout_seconds=(
                None
                if raw_output.get("focused_timeout_seconds") is None
                else _nonnegative_float(
                    raw_output.get("focused_timeout_seconds"),
                    name="output.focused_timeout_seconds",
                )
            ),
            micro_probe_limit=(
                None
                if raw_output.get("micro_probe_limit") is None
                else _positive_int(
                    raw_output.get("micro_probe_limit"),
                    name="output.micro_probe_limit",
                )
            ),
            micro_timeout_seconds=(
                None
                if raw_output.get("micro_timeout_seconds") is None
                else _nonnegative_float(
                    raw_output.get("micro_timeout_seconds"),
                    name="output.micro_timeout_seconds",
                )
            ),
            foundation_subwindows=foundation_subwindows,
            foundation_cost_stress_multiplier=foundation_cost_stress_multiplier,
        ),
        loop=LoopConfig(
            plateau_patience=_positive_int(
                _required(raw_loop, "plateau_patience"),
                name="loop.plateau_patience",
            ),
            max_iterations=_positive_int(
                _required(raw_loop, "max_iterations"),
                name="loop.max_iterations",
            ),
            min_abs_improvement=_nonnegative_float(
                _required(raw_loop, "min_abs_improvement"),
                name="loop.min_abs_improvement",
            ),
            min_rel_improvement=_nonnegative_float(
                _required(raw_loop, "min_rel_improvement"),
                name="loop.min_rel_improvement",
            ),
            baseline_grace_iterations=_positive_int(
                raw_loop.get("baseline_grace_iterations", raw_loop["plateau_patience"]),
                name="loop.baseline_grace_iterations",
            ),
        ),
        objective=ObjectiveConfig(
            kind=objective_kind,
            subwindows=subwindows,
            psr_hurdle_sharpe=_floating(
                raw_objective.get("psr_hurdle_sharpe", 0.0),
                name="objective.psr_hurdle_sharpe",
            ),
        ),
        gates=GateConfig(
            min_trades=_nonnegative_int(
                _required(raw_gates, "min_trades"),
                name="gates.min_trades",
            ),
            min_return_sample_count=_nonnegative_int(
                _required(raw_gates, "min_return_sample_count"),
                name="gates.min_return_sample_count",
            ),
            min_effective_sample_size=_nonnegative_float(
                _required(raw_gates, "min_effective_sample_size"),
                name="gates.min_effective_sample_size",
            ),
            max_symbol_concentration=_fraction(
                _required(raw_gates, "max_symbol_concentration"),
                name="gates.max_symbol_concentration",
            ),
            min_cost_stress_return_retention=_fraction(
                _required(raw_gates, "min_cost_stress_return_retention"),
                name="gates.min_cost_stress_return_retention",
            ),
            max_abs_drawdown=_fraction(
                _required(raw_gates, "max_abs_drawdown"),
                name="gates.max_abs_drawdown",
            ),
            min_annualized_return=_floating(
                _required(raw_gates, "min_annualized_return"),
                name="gates.min_annualized_return",
            ),
            # Acceptance haircut k_accept for the deflated full-Train money floor —
            # the multiple-testing correction for the best-of-N search. It sits below
            # the best-of-N bound ~sqrt(2 * ln N) (~2.8 at N=50) but above the noise
            # floor. Explicit, not derived from loop.max_iterations.
            score_haircut_se=_positive_float(
                _required(raw_gates, "score_haircut_se"),
                name="gates.score_haircut_se",
            ),
            max_components=_positive_int(
                _required(raw_gates, "max_components"),
                name="gates.max_components",
            ),
            max_params=_nonnegative_int(
                _required(raw_gates, "max_params"), name="gates.max_params"
            ),
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
        str(key): _param_value(value, name=f"params.{key}")
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

    numeric_params = {key for key, value in params.items() if _is_numeric_param(value)}
    missing_bounds = numeric_params - set(bounds)
    if missing_bounds:
        raise ValueError(f"missing bounds for params: {sorted(missing_bounds)}")
    orphan_bounds = set(bounds) - set(params)
    if orphan_bounds:
        raise ValueError(f"bounds without params: {sorted(orphan_bounds)}")

    nonnumeric_bounds = set(bounds) - numeric_params
    if nonnumeric_bounds:
        raise ValueError(f"non-numeric params cannot have bounds: {sorted(nonnumeric_bounds)}")

    for key in numeric_params:
        value = params[key]
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
    if protocol.data.load_start is not None:
        data_block["load_start"] = protocol.data.load_start
    if protocol.data.load_end is not None:
        data_block["load_end"] = protocol.data.load_end
    output_block: dict[str, object] = {
        "results_dir": str(results_dir or protocol.output.results_dir),
        "artifact_profile": protocol.output.artifact_profile,
        "quick_checks": protocol.output.quick_checks,
        "diagnostic_sample_trades": max(1, protocol.output.diagnostic_sample_trades),
        "causality_check": protocol.output.causality_check,
        "foundation_subwindows": protocol.output.foundation_subwindows,
        "foundation_cost_stress_multiplier": protocol.output.foundation_cost_stress_multiplier,
    }
    if protocol.output.strict_probe_limit is not None:
        output_block["strict_probe_limit"] = protocol.output.strict_probe_limit
    if protocol.output.focused_probe_limit is not None:
        output_block["focused_probe_limit"] = protocol.output.focused_probe_limit
    if protocol.output.focused_timeout_seconds is not None:
        output_block["focused_timeout_seconds"] = protocol.output.focused_timeout_seconds
    if protocol.output.micro_probe_limit is not None:
        output_block["micro_probe_limit"] = protocol.output.micro_probe_limit
    if protocol.output.micro_timeout_seconds is not None:
        output_block["micro_timeout_seconds"] = protocol.output.micro_timeout_seconds
    capacity_block: dict[str, object] = {"mode": protocol.capacity_model.mode}
    for field_name in (
        "portfolio_notional",
        "adv_lookback_bars",
        "adv_min_observations",
        "max_bar_participation",
        "max_adv_participation",
        "impact_coefficient_bps",
        "impact_exponent",
    ):
        value = getattr(protocol.capacity_model, field_name)
        if value is not None:
            capacity_block[field_name] = value
    risk_budget_block: dict[str, object] = {
        "mode": protocol.risk_budget.mode,
        "annualization_periods_per_year": protocol.risk_budget.annualization_periods_per_year,
    }
    if protocol.risk_budget.target_volatility is not None:
        risk_budget_block["target_volatility"] = protocol.risk_budget.target_volatility
    if protocol.risk_budget.book_scale is not None:
        risk_budget_block["book_scale"] = protocol.risk_budget.book_scale
    return {
        "strategy_path": protocol.strategy_path,
        "strategy_id": protocol.strategy_id,
        "data": data_block,
        "params": dict(params),
        "fill_model": {
            "price": protocol.fill_model.price,
            "entry_lag_bars": protocol.fill_model.entry_lag_bars,
        },
        "cost_model": {
            "fee_bps_per_side": protocol.cost_model.fee_bps_per_side,
            "slippage_bps_per_side": protocol.cost_model.slippage_bps_per_side,
        },
        "capacity_model": capacity_block,
        "leverage_budget": {
            "max_gross_exposure": protocol.leverage_budget.max_gross_exposure,
            "max_net_exposure": protocol.leverage_budget.max_net_exposure,
        },
        "risk_budget": risk_budget_block,
        "envelope": {"operator_frozen": True},
        "output": output_block,
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
    for section in [
        "data",
        "params",
        "fill_model",
        "cost_model",
        "capacity_model",
        "leverage_budget",
        "risk_budget",
        "envelope",
        "output",
    ]:
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
