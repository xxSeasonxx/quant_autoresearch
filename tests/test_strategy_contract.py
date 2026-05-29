from __future__ import annotations

import strategy


def test_strategy_exports_decision_contract_only():
    assert callable(strategy.generate_decisions)
    assert callable(strategy.validate_params)
    assert "generate_decisions" in strategy.__all__
    assert "validate_params" in strategy.__all__
    assert "generate_signals" not in strategy.__all__


def test_validate_params_returns_mapping_copy():
    source = {"weight": 0.1}
    validated = strategy.validate_params(source)

    assert validated == source
    assert validated is not source


def test_placeholder_strategy_emits_no_decisions():
    assert strategy.generate_decisions([], {}) == []
