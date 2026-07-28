from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence, cast
import hashlib
import json

from quant_data import catalog
from quant_data.catalog import DATASET_STATUS, DERIVED_DATASET_HEALTH
from quant_data.readiness import (
    ReadinessError,
    validate_dataset_window,
    validate_derived_symbol_window,
)


_DEFAULT_DATASETS: dict[str, str] = {
    "crypto_perp_funding": "crypto_perp_1min_with_funding",
}

_SYMBOL_CONSTANTS: dict[str, str] = {
    "crypto_perp_1min_with_funding": "CRYPTO_PERP_1MIN_WITH_FUNDING_SYMBOLS",
    "equity_1min": "EQUITY_1MIN_SYMBOLS",
    "equity_daily": "EQUITY_DAILY_SYMBOLS",
    "crypto_perp_1min": "CRYPTO_PERP_1MIN_SYMBOLS",
    "forex_1min": "FOREX_1MIN_SYMBOLS",
    "forex_daily": "FOREX_DAILY_SYMBOLS",
    "forex_1min_with_quotes": "FOREX_1MIN_WITH_QUOTES_SYMBOLS",
    "crypto_spot_perp_basis_1min": "CRYPTO_SPOT_PERP_BASIS_1MIN_SYMBOLS",
}

_BARS_DATASETS = frozenset(
    dataset
    for dataset in _SYMBOL_CONSTANTS
    if dataset != "crypto_perp_1min_with_funding"
)


@dataclass(frozen=True)
class UniverseArtifact:
    path: Path
    resolver_sha256: str
    resolved_symbols: tuple[str, ...]
    payload: Mapping[str, object]


def _parse_date(value: str, *, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date") from exc


def _jsonable(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _payload_without_resolver_hash(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"created_at", "resolver_sha256"}
    }


def universe_payload_sha256(payload: Mapping[str, object]) -> str:
    return _canonical_sha256(_payload_without_resolver_hash(payload))


def _resolve_dataset(data_kind: str, dataset: str | None) -> str:
    if data_kind == "crypto_perp_funding":
        resolved = dataset or _DEFAULT_DATASETS[data_kind]
        if resolved != _DEFAULT_DATASETS[data_kind]:
            raise ValueError(
                "crypto_perp_funding supports only dataset "
                f"{_DEFAULT_DATASETS[data_kind]!r}"
            )
        return resolved
    if data_kind == "bars":
        if not dataset:
            raise ValueError("bars requires an explicit dataset")
        if dataset not in _BARS_DATASETS:
            supported = ", ".join(sorted(_BARS_DATASETS))
            raise ValueError(f"bars dataset must be one of: {supported}")
        return dataset
    raise ValueError("data_kind must be one of: bars, crypto_perp_funding")


def _candidate_symbols(dataset: str) -> tuple[str, ...]:
    constant = _SYMBOL_CONSTANTS[dataset]
    raw = getattr(catalog, constant)
    if not isinstance(raw, list) or not all(isinstance(symbol, str) for symbol in raw):
        raise ValueError(f"catalog constant {constant} must be a list of symbols")
    symbols = tuple(
        sorted(dict.fromkeys(symbol.strip() for symbol in raw if symbol.strip()))
    )
    if not symbols:
        raise ValueError(f"catalog constant {constant} has no symbols")
    return symbols


def _validate_capacity(dataset: str, capacity_model: str) -> None:
    if capacity_model not in {"off", "average_bar_impact"}:
        raise ValueError("capacity_model must be one of: off, average_bar_impact")
    semantics = catalog.DATASET_CONTRACTS[dataset]["volume_semantics"]
    if capacity_model == "average_bar_impact" and semantics not in {
        "base_units",
        "quote_notional",
    }:
        raise ValueError(
            f"dataset {dataset!r} volume_semantics={semantics!r} cannot price "
            "average_bar_impact capacity"
        )


def _derived_health_digest(dataset: str, symbols: Sequence[str]) -> dict[str, object]:
    if dataset not in DERIVED_DATASET_HEALTH:
        return {"sha256": None, "symbol_count": None}
    health = DERIVED_DATASET_HEALTH[dataset]
    relevant = {
        symbol: health[symbol] for symbol in sorted(symbols) if symbol in health
    }
    return {
        "sha256": _canonical_sha256(cast(Mapping[str, object], relevant)),
        "symbol_count": len(relevant),
    }


def _data_snapshot(dataset: str, symbols: Sequence[str]) -> dict[str, object]:
    try:
        dataset_status = DATASET_STATUS[dataset]
    except KeyError as exc:
        raise ValueError(f"dataset {dataset!r} is missing from DATASET_STATUS") from exc
    snapshot_without_hash: dict[str, object] = {
        "dataset": dataset,
        "dataset_status": cast(dict[str, object], _jsonable(dataset_status)),
        "derived_health": _derived_health_digest(dataset, symbols),
    }
    return {
        **snapshot_without_hash,
        "snapshot_sha256": _canonical_sha256(snapshot_without_hash),
    }


def _excluded(symbol: str, reason: str) -> dict[str, str]:
    return {"symbol": symbol, "reason": reason}


def resolve_universe_payload(
    *,
    data_kind: str,
    dataset: str | None,
    start: str,
    end: str,
    exclusions: Sequence[str] = (),
    max_lag_days: int | None = None,
    require_research_ready: bool = False,
    allowed_derived_statuses: Sequence[str] = ("research_ready",),
    capacity_model: str = "average_bar_impact",
    created_at: str | None = None,
) -> dict[str, object]:
    resolved_dataset = _resolve_dataset(data_kind, dataset)
    _validate_capacity(resolved_dataset, capacity_model)
    start_date = _parse_date(start, name="start")
    end_date = _parse_date(end, name="end")
    if end_date < start_date:
        raise ValueError("end must be on or after start")
    if max_lag_days is not None and max_lag_days < 0:
        raise ValueError("max_lag_days must be >= 0")
    allowed_statuses = tuple(
        status.strip() for status in allowed_derived_statuses if status.strip()
    )
    if not allowed_statuses:
        raise ValueError("allowed_derived_statuses must include at least one status")

    candidates = _candidate_symbols(resolved_dataset)
    try:
        validate_dataset_window(
            resolved_dataset,
            start_date,
            end_date,
            max_lag_days=max_lag_days,
            require_research_ready=require_research_ready,
        )
    except ReadinessError as exc:
        raise ValueError(str(exc)) from exc

    exclusions_set = {symbol.strip() for symbol in exclusions if symbol.strip()}
    excluded: list[dict[str, str]] = []
    resolved: list[str] = []

    for symbol in candidates:
        if symbol in exclusions_set:
            excluded.append(_excluded(symbol, "explicit_exclusion"))
            continue
        if resolved_dataset in DERIVED_DATASET_HEALTH:
            try:
                validate_derived_symbol_window(
                    resolved_dataset,
                    symbol,
                    start_date,
                    end_date,
                    max_lag_days=max_lag_days,
                    allowed_statuses=allowed_statuses,
                )
            except ReadinessError as exc:
                excluded.append(_excluded(symbol, f"derived_readiness: {exc}"))
                continue
        resolved.append(symbol)

    for symbol in sorted(exclusions_set - set(candidates)):
        excluded.append(_excluded(symbol, "explicit_exclusion_not_in_candidates"))

    if not resolved:
        raise ValueError(
            "resolved universe is empty after readiness checks and exclusions"
        )

    payload: dict[str, object] = {
        "schema_version": 1,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "rule": {
            "data_kind": data_kind,
            "dataset": resolved_dataset,
            "start": start,
            "end": end,
            "exclusions": sorted(exclusions_set),
            "readiness_options": {
                "max_lag_days": max_lag_days,
                "require_research_ready": require_research_ready,
                "allowed_derived_statuses": list(allowed_statuses),
                "capacity_model": capacity_model,
            },
        },
        "resolved_symbols": resolved,
        "excluded_symbols": sorted(excluded, key=lambda item: item["symbol"]),
        "data_snapshot": _data_snapshot(resolved_dataset, candidates),
        "resolver_sha256": "",
    }
    payload["resolver_sha256"] = universe_payload_sha256(payload)
    return payload


def write_universe_artifact(
    *,
    out_path: str | Path,
    data_kind: str,
    dataset: str | None,
    start: str,
    end: str,
    exclusions: Sequence[str] = (),
    max_lag_days: int | None = None,
    require_research_ready: bool = False,
    allowed_derived_statuses: Sequence[str] = ("research_ready",),
    capacity_model: str = "average_bar_impact",
) -> dict[str, object]:
    payload = resolve_universe_payload(
        data_kind=data_kind,
        dataset=dataset,
        start=start,
        end=end,
        exclusions=exclusions,
        max_lag_days=max_lag_days,
        require_research_ready=require_research_ready,
        allowed_derived_statuses=allowed_derived_statuses,
        capacity_model=capacity_model,
    )
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def load_universe_artifact(path: str | Path) -> UniverseArtifact:
    source = Path(path)
    try:
        payload = json.loads(source.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"universe artifact is unreadable: {source}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("universe artifact must be a JSON object")
    if payload.get("schema_version") != 1:
        raise ValueError("universe artifact schema_version must be 1")
    created_at = payload.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise ValueError("universe artifact missing created_at")
    resolver_sha = payload.get("resolver_sha256")
    if not isinstance(resolver_sha, str) or not resolver_sha:
        raise ValueError("universe artifact missing resolver_sha256")
    if resolver_sha != universe_payload_sha256(payload):
        raise ValueError("universe artifact resolver_sha256 mismatch")
    if not isinstance(payload.get("rule"), Mapping):
        raise ValueError("universe artifact missing rule")
    if not isinstance(payload.get("data_snapshot"), Mapping):
        raise ValueError("universe artifact missing data_snapshot")
    excluded = payload.get("excluded_symbols")
    if not isinstance(excluded, list):
        raise ValueError("universe artifact excluded_symbols must be a list")
    symbols = payload.get("resolved_symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("universe artifact resolved_symbols must be a non-empty list")
    resolved: list[str] = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(
                "universe artifact resolved_symbols must contain non-empty strings"
            )
        resolved.append(symbol)
    return UniverseArtifact(
        path=source,
        resolver_sha256=resolver_sha,
        resolved_symbols=tuple(resolved),
        payload=payload,
    )
