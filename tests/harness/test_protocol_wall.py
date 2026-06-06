"""AC-3 — Immutable judgment: the mechanical config wall (FR-H2, FR-H3).

An agent-process edit to the Protocol fails the run closed; the recorded hash detects
drift. There is no code path by which `params` overrides cost/fill/tiers — asserted
STRUCTURALLY (the absence of a path), not by catching a guard.
"""

from __future__ import annotations

import textwrap

import pytest
from pydantic import ValidationError

from harness.protocol import (
    CostModel,
    Experiment,
    FoundationCallConfig,
    Protocol,
    ProtocolDriftError,
    derive_foundation_config,
    load_protocol,
)

VALID_PROTOCOL_TOML = textwrap.dedent(
    """
    name = "test-asset-v1"

    [cost_model]
    taker_bps = 5.0
    maker_bps = 1.0
    slippage_bps = 1.0

    [fill_model]
    fill = "next_bar_open"

    [data_tiers]
    symbols = ["BTCUSDT", "ETHUSDT"]
    [data_tiers.train]
    start = "2024-01-01"
    end = "2024-09-30"
    [data_tiers.selection]
    start = "2024-10-01"
    end = "2025-04-30"
    [data_tiers.lockbox]
    start = "2025-05-01"
    end = "2025-07-31"

    [stability.param_steps]
    lookback = 4
    """
)


def _write(tmp_path, content: str):
    path = tmp_path / "protocol.toml"
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# AC-3: drift fails closed.
# --------------------------------------------------------------------------- #


def test_ac3_tampered_protocol_after_hashing_fails_closed(tmp_path):
    """Hash a Protocol, tamper its file, reload with the recorded hash ⇒ ProtocolDriftError."""
    path = _write(tmp_path, VALID_PROTOCOL_TOML)
    original = load_protocol(path)
    recorded_hash = original.content_hash

    # Agent tampers the cost model in the file (resurrect cheap costs).
    tampered = VALID_PROTOCOL_TOML.replace("taker_bps = 5.0", "taker_bps = 0.0")
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(ProtocolDriftError):
        load_protocol(path, expected_hash=recorded_hash)


def test_ac3_loader_points_at_drifted_file_fails_closed(tmp_path):
    """A loader pointed at a file whose hash differs from the recorded one fails closed."""
    path_a = _write(tmp_path, VALID_PROTOCOL_TOML)
    recorded_hash = load_protocol(path_a).content_hash

    drifted = VALID_PROTOCOL_TOML.replace("maker_bps = 1.0", "maker_bps = 0.0")
    path_b = tmp_path / "drifted.toml"
    path_b.write_text(drifted, encoding="utf-8")

    with pytest.raises(ProtocolDriftError):
        load_protocol(path_b, expected_hash=recorded_hash)


def test_ac3_matching_hash_loads(tmp_path):
    path = _write(tmp_path, VALID_PROTOCOL_TOML)
    proto = load_protocol(path)
    # Reloading with the genuine hash succeeds — drift detection is exact, not paranoid.
    again = load_protocol(path, expected_hash=proto.content_hash)
    assert again.content_hash == proto.content_hash


def test_content_hash_is_stable_and_order_independent(tmp_path):
    """The hash is a stable function of content, independent of TOML key order."""
    path1 = _write(tmp_path, VALID_PROTOCOL_TOML)
    h1 = load_protocol(path1).content_hash

    # Reorder top-level sections; semantically identical Protocol.
    reordered = textwrap.dedent(
        """
        name = "test-asset-v1"

        [fill_model]
        fill = "next_bar_open"

        [cost_model]
        slippage_bps = 1.0
        maker_bps = 1.0
        taker_bps = 5.0

        [data_tiers]
        symbols = ["BTCUSDT", "ETHUSDT"]
        [data_tiers.selection]
        start = "2024-10-01"
        end = "2025-04-30"
        [data_tiers.train]
        start = "2024-01-01"
        end = "2024-09-30"
        [data_tiers.lockbox]
        start = "2025-05-01"
        end = "2025-07-31"

        [stability.param_steps]
        lookback = 4
        """
    )
    path2 = tmp_path / "reordered.toml"
    path2.write_text(reordered, encoding="utf-8")
    h2 = load_protocol(path2).content_hash
    assert h1 == h2


def test_unknown_protocol_key_rejected_at_parse(tmp_path):
    """extra='forbid': a sneaked unknown TOP-LEVEL key (a fake override) fails at parse."""
    # Insert the key at the top level (before any table) so it binds to the Protocol root,
    # not to a trailing nested table.
    sneaky = "zero_cost_backdoor = true\n" + VALID_PROTOCOL_TOML
    path = _write(tmp_path, sneaky)
    with pytest.raises(ValidationError):
        load_protocol(path)


# --------------------------------------------------------------------------- #
# AC-3: no param-override path (FR-H3) — asserted structurally.
# --------------------------------------------------------------------------- #


def test_ac3_params_cannot_override_cost_fill_tiers_structurally(tmp_path):
    """Params that COLLIDE with cost/fill/tier names do not reach the derived cost/fill/tiers.

    This asserts the *absence of a code path*: the derived config's cost/fill/tiers come
    solely from the Protocol; the colliding params land only under strategy_params.
    """
    path = _write(tmp_path, VALID_PROTOCOL_TOML)
    proto = load_protocol(path)

    malicious = Experiment(
        strategy_path="strategy.py",
        params={
            "taker_bps": 0.0,  # try to resurrect a zero-cost model
            "maker_bps": 0.0,
            "fill": "perfect",
            "cost_model": {"taker_bps": 0.0},
            "lookback": 20,
        },
    )
    cfg = derive_foundation_config(proto, malicious)

    # Cost/fill/tiers are EXACTLY the Protocol's, untouched by params.
    assert cfg.cost_model == proto.cost_model
    assert cfg.cost_model.taker_bps == 5.0
    assert cfg.fill_model == proto.fill_model
    assert cfg.data_tiers == proto.data_tiers
    # The colliding params are quarantined under strategy_params only.
    assert cfg.strategy_params["taker_bps"] == 0.0
    assert "taker_bps" not in cfg.model_fields_set or cfg.cost_model.taker_bps == 5.0


def test_ac3_no_attribute_merges_params_into_cost():
    """Structural: FoundationCallConfig has no field that fuses params with cost/fill/tiers.

    cost_model / fill_model / data_tiers are typed sub-models; strategy_params is a
    SEPARATE dict. There is no shared namespace into which a param could be merged.
    """
    fields = set(FoundationCallConfig.model_fields)
    assert "cost_model" in fields
    assert "fill_model" in fields
    assert "data_tiers" in fields
    assert "strategy_params" in fields
    # cost_model is a CostModel, not a free dict that params could be **-spread into.
    assert FoundationCallConfig.model_fields["cost_model"].annotation is CostModel


def test_experiment_is_frozen_extra_forbid():
    exp = Experiment(strategy_path="strategy.py", params={"x": 1})
    with pytest.raises(ValidationError):
        Experiment(strategy_path="s", params={}, unknown_field=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        exp.strategy_path = "other"  # frozen


def test_protocol_is_frozen():
    proto = Protocol.model_validate(
        {
            "name": "x",
            "cost_model": {"taker_bps": 5, "maker_bps": 1},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-06-01"},
                "selection": {"start": "2024-06-02", "end": "2024-10-01"},
                "lockbox": {"start": "2024-10-02", "end": "2024-12-01"},
            },
        }
    )
    with pytest.raises(Exception):
        proto.name = "y"  # frozen
