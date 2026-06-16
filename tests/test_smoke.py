from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from protocol import build_quick_run_config, load_experiment, load_protocol
import strategy


def _funding_bars() -> list[dict[str, object]]:
    """Two symbols, 70 one-minute bars each, with one funding event past the
    capacity-history floor: enough for the strategy to emit a held book."""

    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rates = {"AAA": 0.0002, "BBB": -0.0003}  # +2 bps -> short, -3 bps -> long
    bars: list[dict[str, object]] = []
    for symbol in ("AAA", "BBB"):
        for index in range(70):
            timestamp = base + timedelta(minutes=index)
            is_event = index == 65
            bars.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "close": 100.0,
                    "funding_timestamp": timestamp,
                    "funding_rate": rates[symbol] if is_event else 0.0,
                    "has_funding_event": is_event,
                    "available_at": timestamp,
                }
            )
    return bars


def test_harness_smoke_loads_active_config():
    protocol = load_protocol(Path("protocol.toml"))
    experiment = load_experiment(Path("experiment.toml"))
    quick = build_quick_run_config(protocol, experiment.params)

    assert protocol.strategy_path == "strategy.py"
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


def test_strategy_smoke_exports_contract():
    assert set(strategy.__all__) == {"validate_params", "generate_decisions"}
    assert callable(strategy.validate_params)
    assert callable(strategy.generate_decisions)


def test_strategy_scale_search_is_dead():
    # Upstream owns book scale, so the strategy has no magnitude knob: it emits
    # unit-magnitude targets, and a residual `weight` param cannot move them.
    bars = _funding_bars()
    params = {"top_n": 5, "min_abs_funding_bps": 1.0, "decision_lag_minutes": 1}

    decisions = strategy.generate_decisions(bars, params)
    assert decisions, "strategy should emit a held book for the fixture"
    assert all(abs(decision.target) in {0.5, 1.0} for decision in decisions)

    spurious = strategy.generate_decisions(bars, {**params, "weight": 999.0})
    shape = [(d.instrument.symbol, d.decision_time, d.target) for d in decisions]
    spurious_shape = [(d.instrument.symbol, d.decision_time, d.target) for d in spurious]
    assert shape == spurious_shape
