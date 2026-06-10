from __future__ import annotations

from pathlib import Path

from protocol import build_quick_run_config, load_experiment, load_protocol
import strategy


def test_harness_smoke_loads_active_config():
    protocol = load_protocol(Path("protocol.toml"))
    experiment = load_experiment(Path("experiment.toml"))
    quick = build_quick_run_config(protocol, experiment.params)

    assert protocol.strategy_path == "strategy.py"
    assert protocol.output.causality_check == "micro"
    assert protocol.output.foundation_enabled is True
    assert quick["strategy_id"] == protocol.strategy_id
    assert quick["params"] == experiment.params
    assert quick["output"]["causality_check"] == "micro"
    assert quick["output"]["foundation_enabled"] is True
    assert quick["output"]["foundation_subwindows"] == protocol.objective.subwindows


def test_strategy_smoke_exports_contract():
    assert strategy.__all__ == ["validate_params", "generate_decisions"]
    assert callable(strategy.validate_params)
    assert callable(strategy.generate_decisions)
