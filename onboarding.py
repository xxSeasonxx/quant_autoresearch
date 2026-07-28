from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from math import isfinite, sqrt
from pathlib import Path
from typing import Any, Mapping, cast
import hashlib
import json
import tomllib

from protocol import ProtocolConfig, load_protocol
from universe_resolver import UniverseArtifact, load_universe_artifact


def protocol_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


STOP_RULE_FIELDS = (
    "max_iterations",
    "plateau_patience",
    "baseline_grace_iterations",
)


def protocol_identity_sha256(protocol: ProtocolConfig) -> str:
    """Hash the frozen research contract, excluding operator-owned stop rules."""

    payload = asdict(protocol)
    loop = payload["loop"]
    for field in STOP_RULE_FIELDS:
        del loop[field]
    return _canonical_sha256(payload)


def stop_rule_values(protocol: ProtocolConfig) -> dict[str, int]:
    return {field: int(getattr(protocol.loop, field)) for field in STOP_RULE_FIELDS}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _toml_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    in_block = False
    active_is_toml = False
    current: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_block:
                if active_is_toml:
                    blocks.append("\n".join(current))
                in_block = False
                active_is_toml = False
                current = []
                continue
            info = stripped.removeprefix("```").strip().lower()
            in_block = True
            active_is_toml = "toml" in info
            current = []
            continue
        if in_block and active_is_toml:
            current.append(line)
    return blocks


def _load_brief_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    text = source.read_text()
    blocks = _toml_blocks(text)
    candidates = blocks or [text]
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = tomllib.loads(candidate)
        except tomllib.TOMLDecodeError as exc:
            last_error = exc
            continue
        if {"mechanism", "observable", "falsifier"} & set(parsed):
            return parsed
    if last_error is not None:
        raise ValueError(
            f"could not parse setup brief TOML: {last_error}"
        ) from last_error
    raise ValueError(
        "setup brief must contain a TOML block with mechanism, observable, and falsifier"
    )


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return " ".join(value.split())


def _optional_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return " ".join(value.split())


def _text_list(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    if key not in data or data.get(key) is None:
        return ()
    value = data[key]
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        items = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{key} must contain only text values")
            items.append(item.strip())
    else:
        raise ValueError(f"{key} must be a list of text values")
    return tuple(item for item in items if item)


def _explicit_symbols(data: Mapping[str, Any]) -> tuple[str, ...]:
    if "symbols" in data:
        source = {"symbols": data["symbols"]}
    elif "target_universe" in data:
        source = {"symbols": data["target_universe"]}
    else:
        return ()
    return _text_list(source, "symbols")


def _resolve_universe_artifact(path_text: str) -> UniverseArtifact:
    return load_universe_artifact(Path(path_text))


def _artifact_rule(artifact: UniverseArtifact) -> Mapping[str, object]:
    rule = artifact.payload.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError("universe artifact missing rule")
    return rule


def _validate_universe_artifact_rule(
    artifact: UniverseArtifact,
    data: Mapping[str, Any],
) -> None:
    rule = _artifact_rule(artifact)
    expected_pairs = {
        "data_kind": data.get("data_kind"),
        "dataset": data.get("dataset"),
        "start": data.get("train_start"),
        "end": data.get("train_end"),
    }
    for key, expected in expected_pairs.items():
        if expected in (None, ""):
            continue
        if rule.get(key) != expected:
            brief_key = (
                "train_start"
                if key == "start"
                else "train_end"
                if key == "end"
                else key
            )
            raise ValueError(f"universe_artifact rule.{key} must match {brief_key}")

    rule_exclusions = rule.get("exclusions")
    expected_exclusions = sorted(_text_list(data, "exclusions"))
    if rule_exclusions != expected_exclusions:
        raise ValueError("universe_artifact rule.exclusions must match exclusions")


def _brief_symbols(data: Mapping[str, Any]) -> tuple[tuple[str, ...], str, str | None]:
    explicit = _explicit_symbols(data)
    artifact_path = _optional_text(data, "universe_artifact")
    artifact: UniverseArtifact | None = None
    if artifact_path:
        artifact = _resolve_universe_artifact(artifact_path)
        _validate_universe_artifact_rule(artifact, data)
    has_explicit_key = "symbols" in data or "target_universe" in data
    if has_explicit_key and not explicit and artifact is None:
        raise ValueError("symbols must include at least one symbol")
    if explicit and artifact is not None and explicit != artifact.resolved_symbols:
        raise ValueError(
            "symbols must exactly match universe_artifact resolved_symbols"
        )
    if artifact is not None:
        return artifact.resolved_symbols, artifact_path, artifact.resolver_sha256
    if explicit:
        return explicit, "", None
    raise ValueError(
        "either symbols or universe_artifact must include at least one symbol"
    )


def _finite_float(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{key} must be finite")
    return parsed


def _positive_float(data: Mapping[str, Any], key: str) -> float:
    parsed = _finite_float(data, key)
    if parsed <= 0.0:
        raise ValueError(f"{key} must be > 0")
    return parsed


def _fraction(data: Mapping[str, Any], key: str) -> float:
    parsed = _finite_float(data, key)
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError(f"{key} must be in [0, 1]")
    return parsed


def _nonnegative_float(data: Mapping[str, Any], key: str) -> float:
    parsed = _finite_float(data, key)
    if parsed < 0.0:
        raise ValueError(f"{key} must be >= 0")
    return parsed


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _positive_int(data: Mapping[str, Any], key: str) -> int:
    value = _integer(data, key)
    if value <= 0:
        raise ValueError(f"{key} must be > 0")
    return value


def _nonnegative_int(data: Mapping[str, Any], key: str) -> int:
    value = _integer(data, key)
    if value < 0:
        raise ValueError(f"{key} must be >= 0")
    return value


def _iterations(data: Mapping[str, Any]) -> int:
    value = data.get("max_iterations")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_iterations must be an integer")
    if value < 2:
        raise ValueError("max_iterations must be >= 2")
    return value


def _risk_budget_mode(data: Mapping[str, Any]) -> str:
    value = _required_text(data, "risk_budget_mode")
    if value not in {"calibrate_vol", "fixed_scale"}:
        raise ValueError("risk_budget_mode must be one of: calibrate_vol, fixed_scale")
    return value


def _execution_terms(
    data: Mapping[str, Any],
    *,
    symbols: tuple[str, ...],
) -> tuple[str, str, str, dict[str, dict[str, float]]]:
    venue = _required_text(data, "execution_venue")
    terms_as_of = _required_text(data, "execution_terms_as_of")
    source = _required_text(data, "execution_source")
    try:
        parsed_terms_as_of = date.fromisoformat(terms_as_of)
    except ValueError as exc:
        raise ValueError("execution_terms_as_of must be an ISO date") from exc
    if parsed_terms_as_of > date.today():
        raise ValueError("execution_terms_as_of cannot be in the future")
    raw_instruments = data.get("execution_instruments")
    if not isinstance(raw_instruments, Mapping):
        raise ValueError("execution_instruments must be a table")
    expected = set(symbols)
    actual = {str(symbol) for symbol in raw_instruments}
    if actual != expected:
        raise ValueError(
            "execution_instruments must exactly cover symbols: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    instruments: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        raw_terms = raw_instruments[symbol]
        if not isinstance(raw_terms, Mapping):
            raise ValueError(f"execution_instruments.{symbol} must be a table")
        if set(raw_terms) != {"min_order_notional", "fixed_cost_per_order"}:
            raise ValueError(
                f"execution_instruments.{symbol} requires min_order_notional "
                "and fixed_cost_per_order"
            )
        instruments[symbol] = {
            "min_order_notional": _nonnegative_float(raw_terms, "min_order_notional"),
            "fixed_cost_per_order": _nonnegative_float(
                raw_terms, "fixed_cost_per_order"
            ),
        }
    return venue, terms_as_of, source, instruments


@dataclass(frozen=True)
class StrategyBrief:
    mechanism: str
    observable: str
    falsifier: str
    horizon: str
    decision_cadence: str
    data_needs: tuple[str, ...]
    data_kind: str
    dataset: str
    train_start: str
    train_end: str
    load_start: str
    load_end: str
    bar_cadence: str
    annualization_periods_per_year: int
    symbols: tuple[str, ...]
    universe_artifact: str
    universe_resolver_sha256: str | None
    initial_notional: float
    execution_venue: str
    execution_terms_as_of: str
    execution_source: str
    execution_instruments: dict[str, dict[str, float]]
    average_bar_lookback_bars: int
    average_bar_min_observations: int
    max_bar_participation: float
    max_average_bar_participation: float
    impact_coefficient_bps: float
    impact_exponent: float
    max_gross_exposure: float
    max_net_exposure: float
    risk_budget_mode: str
    target_volatility: float
    max_abs_drawdown: float
    objective_subwindows: int
    min_trades: int
    min_return_sample_count: int
    min_effective_sample_size: float
    max_symbol_concentration: float
    min_cost_stress_return_retention: float
    max_iterations: int
    baseline_grace_iterations: int
    plateau_patience: int
    min_abs_improvement: float
    min_rel_improvement: float
    max_components: int
    max_params: int
    exclusions: tuple[str, ...]
    editable_params: tuple[str, ...]
    baseline_expectations: str


def load_strategy_brief(path: str | Path) -> StrategyBrief:
    data = _load_brief_mapping(path)
    symbols, universe_artifact, universe_resolver_sha256 = _brief_symbols(data)
    execution_venue, execution_terms_as_of, execution_source, execution_instruments = (
        _execution_terms(data, symbols=symbols)
    )
    average_bar_lookback_bars = _positive_int(data, "average_bar_lookback_bars")
    average_bar_min_observations = _positive_int(data, "average_bar_min_observations")
    if average_bar_min_observations > average_bar_lookback_bars:
        raise ValueError(
            "average_bar_min_observations must be <= average_bar_lookback_bars"
        )
    max_iterations = _iterations(data)
    baseline_grace_iterations = _positive_int(data, "baseline_grace_iterations")
    plateau_patience = _positive_int(data, "plateau_patience")
    if plateau_patience > max_iterations:
        raise ValueError("plateau_patience must be <= max_iterations")
    if baseline_grace_iterations > max_iterations:
        raise ValueError("baseline_grace_iterations must be <= max_iterations")
    return StrategyBrief(
        mechanism=_required_text(data, "mechanism"),
        observable=_required_text(data, "observable"),
        falsifier=_required_text(data, "falsifier"),
        horizon=_optional_text(data, "horizon"),
        decision_cadence=_optional_text(data, "decision_cadence"),
        data_needs=_text_list(data, "data_needs"),
        data_kind=_required_text(data, "data_kind"),
        dataset=_optional_text(data, "dataset"),
        train_start=_required_text(data, "train_start"),
        train_end=_required_text(data, "train_end"),
        load_start=_optional_text(data, "load_start"),
        load_end=_optional_text(data, "load_end"),
        bar_cadence=_required_text(data, "bar_cadence"),
        annualization_periods_per_year=_positive_int(
            data, "annualization_periods_per_year"
        ),
        symbols=symbols,
        universe_artifact=universe_artifact,
        universe_resolver_sha256=universe_resolver_sha256,
        initial_notional=_positive_float(data, "initial_notional"),
        execution_venue=execution_venue,
        execution_terms_as_of=execution_terms_as_of,
        execution_source=execution_source,
        execution_instruments=execution_instruments,
        average_bar_lookback_bars=average_bar_lookback_bars,
        average_bar_min_observations=average_bar_min_observations,
        max_bar_participation=_fraction(data, "max_bar_participation"),
        max_average_bar_participation=_fraction(data, "max_average_bar_participation"),
        impact_coefficient_bps=_nonnegative_float(data, "impact_coefficient_bps"),
        impact_exponent=_positive_float(data, "impact_exponent"),
        max_gross_exposure=_positive_float(data, "max_gross_exposure"),
        max_net_exposure=_positive_float(data, "max_net_exposure"),
        risk_budget_mode=_risk_budget_mode(data),
        target_volatility=_positive_float(data, "target_volatility"),
        max_abs_drawdown=_fraction(data, "max_abs_drawdown"),
        objective_subwindows=_positive_int(data, "objective_subwindows"),
        min_trades=_nonnegative_int(data, "min_trades"),
        min_return_sample_count=_nonnegative_int(data, "min_return_sample_count"),
        min_effective_sample_size=_nonnegative_float(data, "min_effective_sample_size"),
        max_symbol_concentration=_fraction(data, "max_symbol_concentration"),
        min_cost_stress_return_retention=_fraction(
            data, "min_cost_stress_return_retention"
        ),
        max_iterations=max_iterations,
        baseline_grace_iterations=baseline_grace_iterations,
        plateau_patience=plateau_patience,
        min_abs_improvement=_nonnegative_float(data, "min_abs_improvement"),
        min_rel_improvement=_nonnegative_float(data, "min_rel_improvement"),
        max_components=_positive_int(data, "max_components"),
        max_params=_nonnegative_int(data, "max_params"),
        exclusions=_text_list(data, "exclusions"),
        editable_params=_text_list(data, "editable_params"),
        baseline_expectations=_optional_text(data, "baseline_expectations"),
    )


@dataclass(frozen=True)
class ProtocolProposal:
    schema_version: int
    created_at: str
    brief_sha256: str
    protocol_sha256: str
    proposal_sha256: str
    thesis: dict[str, object]
    current_protocol: dict[str, dict[str, object]]
    recommended_protocol: dict[str, dict[str, object]]
    rationale: dict[str, str]
    warnings: list[str]
    approval: dict[str, object]

    def as_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "brief_sha256": self.brief_sha256,
            "protocol_sha256": self.protocol_sha256,
            "proposal_sha256": self.proposal_sha256,
            "thesis": self.thesis,
            "current_protocol": self.current_protocol,
            "recommended_protocol": self.recommended_protocol,
            "rationale": self.rationale,
            "warnings": self.warnings,
            "approval": self.approval,
        }


def _approval_checklist() -> list[str]:
    return [
        "Season approved the recommendation table before any baseline run.",
        "protocol.toml was reviewed and edited intentionally; the helper did not auto-apply it.",
        "Edited protocol-owned values were compared against the approved recommendation table; any deltas were shown to Season.",
        "rationale.md records the mechanism, observable, falsifier, assumptions, first failure mode, and the universe population with its mechanism-driven, return-blind sizing rationale.",
        "results.tsv is header-only or absent, and .autoresearch/thesis_lock.json is absent.",
        "The selected venue is lawfully accessible to the account, and current per-symbol execution terms and provenance were reviewed.",
        "approval.protocol_sha256 equals the SHA-256 of the approved protocol.toml.",
    ]


def _train_years(start: object, end: object) -> float | None:
    if not (isinstance(start, str) and isinstance(end, str)):
        return None
    try:
        d0 = datetime.fromisoformat(start)
        d1 = datetime.fromisoformat(end)
    except ValueError:
        return None
    days = (d1 - d0).days
    return days / 365.25 if days > 0 else None


def _feasibility_rows(recommended: Mapping[str, Any]) -> list[dict[str, object]]:
    """Annualized Sharpe implied by the fixed full-Train strength hurdle.

    The `train_strength` gate requires `R - k*SE >= 0`. With best-case dense
    sampling (effective years ~= calendar years) this is `S_ann >= k/sqrt(Y)`.
    The full-Train row is active; the per-subwindow row is informational. A held
    or low-duty-cycle book needs a higher Sharpe than the table shows.
    """

    gates = recommended.get("gates", {})
    objective = recommended.get("objective", {})
    data = recommended.get("data", {})
    k = gates.get("train_strength_haircut_se")
    subwindows = objective.get("subwindows")
    years = _train_years(data.get("start"), data.get("end"))
    if not (
        isinstance(k, (int, float))
        and isinstance(subwindows, int)
        and years is not None
        and subwindows > 0
    ):
        return []
    rows: list[dict[str, object]] = []
    full = k / sqrt(years)
    rows.append(
        {
            "window": "train_strength (full_train, active)",
            "years": round(years, 3),
            "required_sharpe": round(full, 2),
        }
    )
    sub_years = years / subwindows
    per_sub = k / sqrt(sub_years)
    rows.append(
        {
            "window": "per-subwindow strength reference (not used)",
            "years": round(sub_years, 3),
            "required_sharpe": round(per_sub, 2),
        }
    )
    return rows


def _feasibility_warning(rows: list[dict[str, object]]) -> str | None:
    active = next((row for row in rows if "active" in str(row["window"])), None)
    if active is None:
        return None
    required = active["required_sharpe"]
    if isinstance(required, (int, float)) and required > 4.0:
        return (
            f"Feasibility: the Train strength hurdle needs annualized Sharpe ~{required} "
            "(best-case dense sampling; a held / low-duty book needs more). "
            "That is implausibly high — lengthen the Train window or expect no survivor."
        )
    return None


def _proposal_payload_without_hash(
    *,
    created_at: str,
    brief_hash: str,
    current_protocol_hash: str,
    brief: StrategyBrief,
    current: ProtocolConfig,
) -> dict[str, object]:
    train_strength_haircut = 2.0
    # Universe-bounded: a floor above the eligible name count can never pass, so a
    # single-instrument thesis gets 1.0 and a cross-section gets the 2.0 default.
    min_effective_symbol_count = 1.0 if len(brief.symbols) <= 1 else 2.0
    current_execution: dict[str, object] = {"mode": current.execution_model.mode}
    if current.execution_model.mode == "minimum_notional":
        assert current.execution_model.instruments is not None
        current_execution.update(
            {
                "venue": current.execution_model.venue,
                "terms_as_of": current.execution_model.terms_as_of,
                "source": current.execution_model.source,
                "instruments": {
                    symbol: {
                        "min_order_notional": terms.min_order_notional,
                        "fixed_cost_per_order": terms.fixed_cost_per_order,
                    }
                    for symbol, terms in current.execution_model.instruments.items()
                },
            }
        )
    current_protocol: dict[str, dict[str, object]] = {
        "data": {
            "kind": current.data.kind,
            "dataset": current.data.dataset,
            "symbols": list(current.data.symbols),
            "start": current.data.start,
            "end": current.data.end,
            "load_start": current.data.load_start,
            "load_end": current.data.load_end,
            "universe_resolver_sha256": current.data.universe_resolver_sha256,
        },
        "account": {
            "initial_notional": current.account.initial_notional,
        },
        "execution_model": current_execution,
        "capacity_model": {
            "mode": current.capacity_model.mode,
            "average_bar_lookback_bars": current.capacity_model.average_bar_lookback_bars,
            "average_bar_min_observations": current.capacity_model.average_bar_min_observations,
            "max_bar_participation": current.capacity_model.max_bar_participation,
            "max_average_bar_participation": current.capacity_model.max_average_bar_participation,
            "impact_coefficient_bps": current.capacity_model.impact_coefficient_bps,
            "impact_exponent": current.capacity_model.impact_exponent,
        },
        "leverage_budget": {
            "max_gross_exposure": current.leverage_budget.max_gross_exposure,
            "max_net_exposure": current.leverage_budget.max_net_exposure,
        },
        "risk_budget": {
            "mode": current.risk_budget.mode,
            "annualization_periods_per_year": current.risk_budget.annualization_periods_per_year,
            "target_volatility": current.risk_budget.target_volatility,
        },
        "output": {"causality_check": current.output.causality_check},
        "objective": {
            "kind": current.objective.kind,
            "subwindows": current.objective.subwindows,
        },
        "loop": {
            "max_iterations": current.loop.max_iterations,
            "baseline_grace_iterations": current.loop.baseline_grace_iterations,
            "plateau_patience": current.loop.plateau_patience,
            "min_abs_improvement": current.loop.min_abs_improvement,
            "min_rel_improvement": current.loop.min_rel_improvement,
        },
        "gates": {
            "min_trades": current.gates.min_trades,
            "min_return_sample_count": current.gates.min_return_sample_count,
            "min_effective_sample_size": current.gates.min_effective_sample_size,
            "max_symbol_concentration": current.gates.max_symbol_concentration,
            "min_effective_symbol_count": current.gates.min_effective_symbol_count,
            "min_cost_stress_return_retention": current.gates.min_cost_stress_return_retention,
            "max_abs_drawdown": current.gates.max_abs_drawdown,
            "train_strength_haircut_se": (current.gates.train_strength_haircut_se),
            "max_components": current.gates.max_components,
            "max_params": current.gates.max_params,
        },
    }
    recommended_protocol: dict[str, dict[str, object]] = {
        "data": {
            "kind": brief.data_kind,
            "dataset": brief.dataset or None,
            "symbols": list(brief.symbols),
            "start": brief.train_start,
            "end": brief.train_end,
            "load_start": brief.load_start or None,
            "load_end": brief.load_end or None,
            "universe_resolver_sha256": brief.universe_resolver_sha256,
        },
        "account": {
            "initial_notional": brief.initial_notional,
        },
        "execution_model": {
            "mode": "minimum_notional",
            "venue": brief.execution_venue,
            "terms_as_of": brief.execution_terms_as_of,
            "source": brief.execution_source,
            "instruments": brief.execution_instruments,
        },
        "capacity_model": {
            "mode": "average_bar_impact",
            "average_bar_lookback_bars": brief.average_bar_lookback_bars,
            "average_bar_min_observations": brief.average_bar_min_observations,
            "max_bar_participation": brief.max_bar_participation,
            "max_average_bar_participation": brief.max_average_bar_participation,
            "impact_coefficient_bps": brief.impact_coefficient_bps,
            "impact_exponent": brief.impact_exponent,
        },
        "leverage_budget": {
            "max_gross_exposure": brief.max_gross_exposure,
            "max_net_exposure": brief.max_net_exposure,
        },
        "risk_budget": {
            "mode": brief.risk_budget_mode,
            "annualization_periods_per_year": brief.annualization_periods_per_year,
            "target_volatility": brief.target_volatility,
        },
        "output": {"causality_check": "micro"},
        "objective": {
            "kind": "full_window_total_return",
            "subwindows": brief.objective_subwindows,
        },
        "loop": {
            "max_iterations": brief.max_iterations,
            "baseline_grace_iterations": brief.baseline_grace_iterations,
            "plateau_patience": brief.plateau_patience,
            "min_abs_improvement": brief.min_abs_improvement,
            "min_rel_improvement": brief.min_rel_improvement,
        },
        "gates": {
            "min_trades": brief.min_trades,
            "min_return_sample_count": brief.min_return_sample_count,
            "min_effective_sample_size": brief.min_effective_sample_size,
            "max_symbol_concentration": brief.max_symbol_concentration,
            "min_effective_symbol_count": min_effective_symbol_count,
            "min_cost_stress_return_retention": brief.min_cost_stress_return_retention,
            "max_abs_drawdown": brief.max_abs_drawdown,
            "train_strength_haircut_se": train_strength_haircut,
            "max_components": brief.max_components,
            "max_params": brief.max_params,
        },
    }
    warnings = [
        "Train micro causality is a bounded score-admissibility check, not retention, paper, live, or deployability proof.",
    ]
    if brief.universe_resolver_sha256 is None:
        warnings.append(
            "Symbols are explicit Season-approved inputs; no resolver artifact was used."
        )
    else:
        warnings.append(
            "Resolved symbols are eligibility-based from the resolver artifact, not return-ranked or Train-result-ranked."
        )
    if current.output.causality_check != "micro":
        warnings.append(
            "Current protocol causality is not micro; the proposal keeps Train causality bounded on micro."
        )
    feasibility_warning = _feasibility_warning(_feasibility_rows(recommended_protocol))
    if feasibility_warning is not None:
        warnings.append(feasibility_warning)
    return {
        "schema_version": 1,
        "created_at": created_at,
        "brief_sha256": brief_hash,
        "protocol_sha256": current_protocol_hash,
        "proposal_sha256": "",
        "thesis": {
            "mechanism": brief.mechanism,
            "observable": brief.observable,
            "falsifier": brief.falsifier,
            "horizon": brief.horizon,
            "decision_cadence": brief.decision_cadence,
            "bar_cadence": brief.bar_cadence,
            "data_needs": list(brief.data_needs),
            "universe_artifact": brief.universe_artifact,
            "universe_resolver_sha256": brief.universe_resolver_sha256,
            "exclusions": list(brief.exclusions),
            "editable_params": list(brief.editable_params),
            "baseline_expectations": brief.baseline_expectations,
        },
        "current_protocol": current_protocol,
        "recommended_protocol": recommended_protocol,
        "rationale": {
            "data.kind": "Match the data source to the observable and fields needed at decision time.",
            "data.dataset": "Use the dataset that provides the required causal fields and readiness coverage.",
            "data.symbols": (
                "Use the resolver artifact's eligibility-filtered symbols."
                if brief.universe_resolver_sha256 is not None
                else "Use only the explicit universe Season approved for this setup pass."
            ),
            "data.start": "Set the Train start before any result is inspected; do not tune it to outcomes.",
            "data.end": "Set the Train end before any result is inspected; OOS remains outside the loop.",
            "data.load_start": "Use only as an execution/data-readiness buffer, not as scored Train evidence.",
            "data.load_end": "Use only as an execution/data-readiness buffer, not as scored Train evidence.",
            "data.universe_resolver_sha256": "Bind the return-blind resolver artifact hash; leave empty only for a Season-approved explicit symbol list.",
            "account.initial_notional": "Set the real mandate account scale used for execution feasibility and normalized costs.",
            "execution_model.venue": "Use only a lawfully accessible execution venue.",
            "execution_model.terms_as_of": "Snapshot current execution terms before baseline.",
            "execution_model.source": "Record the authoritative source for the venue terms.",
            "execution_model.instruments": "Cover every configured symbol with minimum-order and fixed-order-cost terms.",
            "capacity_model.average_bar_lookback_bars": "Use the approved liquidity-history window for average-bar capacity checks.",
            "capacity_model.average_bar_min_observations": "Require enough liquidity observations before capacity is trusted.",
            "capacity_model.max_bar_participation": "Cap per-bar participation from the mandate and liquidity standard.",
            "capacity_model.max_average_bar_participation": "Cap average-bar participation from the mandate and liquidity standard.",
            "capacity_model.impact_coefficient_bps": "Use the approved impact-cost assumption for capacity pricing.",
            "capacity_model.impact_exponent": "Use the approved market-impact curve shape.",
            "leverage_budget.max_gross_exposure": "Map the allowed gross target-book exposure ceiling directly.",
            "leverage_budget.max_net_exposure": "Map the allowed net target-book exposure ceiling directly.",
            "risk_budget.mode": "Choose the sizing mode before Train results exist.",
            "risk_budget.annualization_periods_per_year": "Derive from bar cadence and market calendar; do not tune from returns.",
            "risk_budget.target_volatility": "Map target volatility directly into upstream risk-budget sizing.",
            "output.causality_check": "Keep Train causality on bounded micro replay.",
            "objective.kind": "Rank gate-passing candidates by realistic-cost full-window total return.",
            "objective.subwindows": "Set robustness slices from Train window length and thesis horizon.",
            "loop.max_iterations": "Use the approved attempt budget as the hard Train iteration cap.",
            "loop.baseline_grace_iterations": "Use the approved first-baseline grace before declaring Train death.",
            "loop.plateau_patience": "Use the approved non-improvement patience after a feasible baseline exists.",
            "loop.min_abs_improvement": "Set the minimum meaningful absolute score improvement before results exist.",
            "loop.min_rel_improvement": "Set the minimum meaningful relative score improvement before results exist.",
            "gates.min_trades": "Set the aggregate closed-trade evidence floor for the claim.",
            "gates.min_return_sample_count": "Require enough portfolio-return observations in each scored window.",
            "gates.min_effective_sample_size": "Require enough autocorrelation-adjusted evidence in each scored window.",
            "gates.max_symbol_concentration": "Set the maximum allowed one-symbol dependence for the claim.",
            "gates.min_effective_symbol_count": "Set the minimum effective number of names carrying PnL (inverse-HHI); use 1.0 for a single-instrument thesis, 2-3 for a cross-sectional book.",
            "gates.min_cost_stress_return_retention": "Set the minimum cost-stress robustness requirement.",
            "gates.max_abs_drawdown": "Map the maximum tolerable drawdown directly into the path-risk gate.",
            "gates.train_strength_haircut_se": "Use a fixed 2-SE Train strength hurdle; it is not statistical proof or a best-of-N correction.",
            "gates.max_components": "Set the maximum signal-component complexity allowed in rationale.md.",
            "gates.max_params": "Set the maximum bounded-parameter complexity allowed in experiment.toml.",
        },
        "warnings": warnings,
        "approval": {
            "approved": False,
            "approved_by": "",
            "approved_at": "",
            "protocol_sha256": None,
            "checklist": _approval_checklist(),
        },
    }


def build_protocol_proposal(
    brief_path: str | Path,
    *,
    protocol_path: str | Path = "protocol.toml",
) -> ProtocolProposal:
    brief_source = Path(brief_path).read_text()
    brief = load_strategy_brief(brief_path)
    current = load_protocol(protocol_path)
    created_at = datetime.now(timezone.utc).isoformat()
    current_hash = protocol_sha256(protocol_path)
    payload = _proposal_payload_without_hash(
        created_at=created_at,
        brief_hash=_sha256_text(brief_source),
        current_protocol_hash=current_hash,
        brief=brief,
        current=current,
    )
    payload["proposal_sha256"] = _canonical_sha256(
        {key: value for key, value in payload.items() if key != "proposal_sha256"}
    )
    return ProtocolProposal(
        schema_version=payload["schema_version"],  # type: ignore[arg-type]
        created_at=payload["created_at"],  # type: ignore[arg-type]
        brief_sha256=payload["brief_sha256"],  # type: ignore[arg-type]
        protocol_sha256=payload["protocol_sha256"],  # type: ignore[arg-type]
        proposal_sha256=payload["proposal_sha256"],  # type: ignore[arg-type]
        thesis=payload["thesis"],  # type: ignore[arg-type]
        current_protocol=payload["current_protocol"],  # type: ignore[arg-type]
        recommended_protocol=payload["recommended_protocol"],  # type: ignore[arg-type]
        rationale=payload["rationale"],  # type: ignore[arg-type]
        warnings=payload["warnings"],  # type: ignore[arg-type]
        approval=payload["approval"],  # type: ignore[arg-type]
    )


def _proposal_markdown(proposal: ProtocolProposal) -> str:
    current = proposal.current_protocol
    recommended = proposal.recommended_protocol
    rationale = proposal.rationale
    rows: list[str] = []
    for section, values in recommended.items():
        for field, value in values.items():
            key = f"{section}.{field}"
            current_value = current.get(section, {}).get(field)
            current_rendered = json.dumps(current_value, sort_keys=True)
            rendered = json.dumps(value, sort_keys=True)
            rows.append(
                f"| `{key}` | `{current_rendered}` | `{rendered}` | {rationale.get(key, '')} |"
            )
    checklist_items = cast(list[str], proposal.approval["checklist"])
    checklist = "\n".join(f"- [ ] {item}" for item in checklist_items)
    warnings = "\n".join(f"- {item}" for item in proposal.warnings)
    feasibility_rows = _feasibility_rows(recommended)
    feasibility_section = ""
    if feasibility_rows:
        feasibility_lines = "\n".join(
            f"| {row['window']} | {row['years']} | {row['required_sharpe']} |"
            for row in feasibility_rows
        )
        feasibility_section = (
            "\n## Feasibility\n\n"
            "Annualized Sharpe implied by the Train strength hurdle (best-case dense "
            "sampling; a held book needs more). The full_train row is the active "
            "gate; the per-subwindow row is diagnostic only.\n\n"
            "| Window | Years | Required Sharpe |\n"
            "| --- | --- | --- |\n"
            f"{feasibility_lines}\n"
        )
    thesis = proposal.thesis
    universe_hash = thesis.get("universe_resolver_sha256")
    universe_section = ""
    if isinstance(universe_hash, str) and universe_hash:
        universe_section = f"""
## Universe Resolver

- Artifact: `{thesis["universe_artifact"]}`
- Resolver SHA-256: `{universe_hash}`
- Symbol list: eligibility-based, not return-ranked or Train-result-ranked.
"""
    return f"""# Protocol Proposal

## Thesis

- Mechanism: {thesis["mechanism"]}
- Observable: {thesis["observable"]}
- Falsifier: {thesis["falsifier"]}
- Horizon: {thesis["horizon"]}
{universe_section}

## Recommendation Table

| Protocol field | Current value | Recommended value | Reason |
| --- | --- | --- | --- |
{chr(10).join(rows)}
{feasibility_section}
## Warnings

{warnings}

## Approval Checklist

{checklist}

Set `approval.approved = true` and `approval.protocol_sha256` to the SHA-256 of the approved `protocol.toml` before running `baseline`.
"""


def write_protocol_proposal(
    brief_path: str | Path,
    out_path: str | Path,
    *,
    protocol_path: str | Path = "protocol.toml",
) -> ProtocolProposal:
    proposal = build_protocol_proposal(brief_path, protocol_path=protocol_path)
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(proposal.as_payload(), indent=2, sort_keys=True) + "\n"
    )
    destination.with_suffix(".md").write_text(_proposal_markdown(proposal))
    return proposal
