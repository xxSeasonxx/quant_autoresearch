from __future__ import annotations

from pathlib import Path

from protocol import build_quick_run_config, load_experiment, load_protocol
import strategy


def test_harness_smoke_loads_process_config():
    protocol = load_protocol(Path("protocol.toml"))
    experiment = load_experiment(Path("experiment.toml"))
    quick = build_quick_run_config(protocol, experiment.params)

    assert protocol.strategy_path == "strategy.py"
    assert Path(protocol.strategy_path).exists()
    assert protocol.strategy_id.strip()
    assert protocol.output.causality_check == "micro"
    assert protocol.capacity_model.mode in {"off", "adv_impact"}
    assert quick["strategy_id"] == protocol.strategy_id
    assert quick["params"] == experiment.params
    assert quick["output"]["causality_check"] == "micro"
    assert quick["output"]["foundation_subwindows"] == protocol.objective.subwindows
    assert quick["capacity_model"]["mode"] == protocol.capacity_model.mode
    assert (
        quick["leverage_budget"]["max_gross_exposure"]
        == protocol.leverage_budget.max_gross_exposure
    )
    assert quick["envelope"]["operator_frozen"] is True
    for name, value in experiment.params.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        bound = experiment.bounds[name]
        assert bound.min <= float(value) <= bound.max


def test_strategy_smoke_exports_contract():
    assert set(strategy.__all__) == {"validate_params", "generate_decisions"}
    assert callable(strategy.validate_params)
    assert callable(strategy.generate_decisions)
