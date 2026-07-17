from __future__ import annotations

from pathlib import Path
import json
import re

import pytest

from quant_data.catalog import CRYPTO_PERP_1MIN_WITH_FUNDING_SYMBOLS
from universe_resolver import (
    load_universe_artifact,
    resolve_universe_payload,
    write_universe_artifact,
)


def test_resolver_excludes_user_symbols_and_sorts_deterministically():
    first = resolve_universe_payload(
        data_kind="crypto_perp_funding",
        dataset="crypto_perp_1min_with_funding",
        start="2025-03-01",
        end="2025-12-31",
        exclusions=("MATIC-PERP",),
    )
    second = resolve_universe_payload(
        data_kind="crypto_perp_funding",
        dataset="crypto_perp_1min_with_funding",
        start="2025-03-01",
        end="2025-12-31",
        exclusions=("MATIC-PERP",),
    )

    symbols = first["resolved_symbols"]
    assert isinstance(symbols, list)
    assert symbols == sorted(symbols)
    assert "MATIC-PERP" not in symbols
    assert {"symbol": "MATIC-PERP", "reason": "explicit_exclusion"} in first[
        "excluded_symbols"
    ]
    assert first["resolver_sha256"] == second["resolver_sha256"]


def test_derived_health_dataset_excludes_not_ready_symbols():
    payload = resolve_universe_payload(
        data_kind="bars",
        dataset="crypto_spot_perp_basis_1min",
        start="2025-03-01",
        end="2025-12-31",
    )

    assert "APT-PERP" not in payload["resolved_symbols"]
    excluded = {
        item["symbol"]: item["reason"]
        for item in payload["excluded_symbols"]
    }
    assert "status=not_research_ready" in excluded["APT-PERP"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "data_kind": "bars",
                "dataset": None,
                "start": "2025-01-01",
                "end": "2025-02-01",
            },
            "bars requires an explicit dataset",
        ),
        (
            {
                "data_kind": "unknown",
                "dataset": None,
                "start": "2025-01-01",
                "end": "2025-02-01",
            },
            "data_kind must be one of",
        ),
        (
            {
                "data_kind": "bars",
                "dataset": "forex_1min",
                "start": "2025-01-01",
                "end": "2025-02-01",
            },
            "not supported for adv_impact capacity",
        ),
    ],
)
def test_resolver_rejects_unsupported_rules(kwargs: dict[str, object], message: str):
    with pytest.raises(ValueError, match=re.escape(message)):
        resolve_universe_payload(**kwargs)  # type: ignore[arg-type]


def test_resolver_fails_when_all_candidates_are_excluded():
    with pytest.raises(ValueError, match="resolved universe is empty"):
        resolve_universe_payload(
            data_kind="crypto_perp_funding",
            dataset="crypto_perp_1min_with_funding",
            start="2025-03-01",
            end="2025-12-31",
            exclusions=CRYPTO_PERP_1MIN_WITH_FUNDING_SYMBOLS,
        )


def test_universe_artifact_round_trips_and_hash_rejects_tampering(tmp_path: Path):
    out = tmp_path / ".autoresearch" / "universe" / "latest.json"
    payload = write_universe_artifact(
        out_path=out,
        data_kind="crypto_perp_funding",
        dataset="crypto_perp_1min_with_funding",
        start="2025-03-01",
        end="2025-12-31",
        exclusions=("MATIC-PERP",),
    )

    loaded = load_universe_artifact(out)
    symbols = payload["resolved_symbols"]
    assert isinstance(symbols, list)

    assert loaded.resolver_sha256 == payload["resolver_sha256"]
    assert loaded.resolved_symbols == tuple(symbols)

    tampered = json.loads(out.read_text())
    tampered["resolved_symbols"] = ["BTC-PERP"]
    out.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="resolver_sha256 mismatch"):
        load_universe_artifact(out)


def test_resolver_has_no_train_artifact_dependencies():
    source = Path("universe_resolver.py").read_text()
    forbidden = (
        "results.tsv",
        "objective.py",
        "gates.py",
        "run_card",
        "run_config",
        "ResultRow",
        "profit_factor",
        "win_rate",
        "sharpe",
        "calmar",
    )
    assert not any(term in source for term in forbidden)
