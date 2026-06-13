from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import NormalDist
from typing import Mapping

from gates import GateConfig, evaluate_gates
from loop import run_iteration
from objective import (
    FoundationEvidence,
    FoundationMetric,
    FoundationScenario,
    ObjectiveConfig,
    TradeSample,
    score_foundation_cost_stress,
    score_objective,
)
from protocol import build_quick_run_config, load_protocol
from results_log import ResultRow, append_result, read_results


def _metric(
    window_id: str,
    *,
    sharpe: float | None,
    sharpe_se: float | None = 0.2,
    total_return: float = 0.05,
    max_drawdown: float = -0.03,
    closed_trade_count: int = 20,
    return_sample_count: int = 200,
    effective_sample_size: float = 120.0,
    max_symbol_concentration: float = 0.4,
    warnings: tuple[str, ...] = (),
) -> FoundationMetric:
    return FoundationMetric(
        window_id=window_id,
        return_sample_count=return_sample_count,
        effective_sample_size=effective_sample_size,
        sharpe=sharpe,
        sharpe_standard_error=sharpe_se,
        total_return=total_return,
        max_drawdown=max_drawdown,
        closed_trade_count=closed_trade_count,
        max_symbol_concentration=max_symbol_concentration,
        warnings=warnings,
    )


def _foundation(
    *,
    full_train_sharpe: float | None = 0.4,
    train_2_sharpe: float | None = 0.1,
    cost_stress_train_2_sharpe: float | None = 0.05,
    total_return: float = 0.05,
    max_drawdown: float = -0.03,
    warnings: tuple[str, ...] = (),
) -> FoundationEvidence:
    return FoundationEvidence(
        realistic_costs=FoundationScenario(
            scenario_id="realistic_costs",
            full_train=_metric(
                "full_train",
                sharpe=full_train_sharpe,
                total_return=total_return,
                max_drawdown=max_drawdown,
                warnings=warnings,
            ),
            subwindows=(
                _metric("train_1", sharpe=0.35),
                _metric("train_2", sharpe=train_2_sharpe, closed_trade_count=12),
                _metric("train_3", sharpe=0.3),
            ),
        ),
        cost_stress=FoundationScenario(
            scenario_id="cost_stress",
            full_train=_metric("full_train", sharpe=0.25),
            subwindows=(
                _metric("train_1", sharpe=0.2),
                _metric(
                    "train_2",
                    sharpe=cost_stress_train_2_sharpe,
                    closed_trade_count=12,
                ),
                _metric("train_3", sharpe=0.1),
            ),
        ),
    )


def _foundation_payload(foundation: FoundationEvidence | None = None) -> dict[str, object]:
    def metric_payload(metric: FoundationMetric) -> dict[str, object]:
        return {
            "window_id": metric.window_id,
            "return_sample_count": metric.return_sample_count,
            "effective_sample_size": metric.effective_sample_size,
            "sharpe": metric.sharpe,
            "sharpe_standard_error": metric.sharpe_standard_error,
            "total_return": metric.total_return,
            "max_drawdown": metric.max_drawdown,
            "closed_trade_count": metric.closed_trade_count,
            "max_symbol_concentration": metric.max_symbol_concentration,
            "warnings": list(metric.warnings),
        }

    foundation = foundation or _foundation()
    return {
        "scenarios": {
            "realistic_costs": {
                "scenario_id": "realistic_costs",
                "full_train": metric_payload(foundation.realistic_costs.full_train),
                "subwindows": [
                    metric_payload(metric)
                    for metric in foundation.realistic_costs.subwindows
                ],
            },
            "cost_stress": {
                "scenario_id": "cost_stress",
                "full_train": metric_payload(foundation.cost_stress.full_train),
                "subwindows": [
                    metric_payload(metric)
                    for metric in foundation.cost_stress.subwindows
                ],
            },
        }
    }


class RawFoundation:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def matrix_payload(self) -> dict[str, object]:
        return self._payload


@dataclass(frozen=True)
class FakeTrade:
    symbol: str
    decision_time: datetime
    net_return: float
    weight: float = 1.0
    gross_return: float | None = None
    cost_return: float | None = None


@dataclass(frozen=True)
class FakeEconomics:
    trades: tuple[FakeTrade, ...]


class FakeFoundation:
    def __init__(self, foundation: FoundationEvidence | None = None) -> None:
        self._foundation = foundation

    def matrix_payload(self) -> dict[str, object]:
        return _foundation_payload(self._foundation)


@dataclass(frozen=True)
class FakeCausality:
    causality_check: str = "micro"
    verified: bool = False
    replay_warning: str | None = None
    timed_out: bool = False
    selected_probe_count: int = 3


@dataclass(frozen=True)
class FakeEvidence:
    causality: FakeCausality


@dataclass(frozen=True)
class FakeRunResult:
    succeeded: bool
    economics: FakeEconomics | None
    foundation: FakeFoundation | RawFoundation | None
    evidence: FakeEvidence
    message: str = "ok"


def _gate_config() -> GateConfig:
    return GateConfig(
        min_trades=10,
        min_trades_per_subwindow=3,
        min_return_sample_count=100,
        min_effective_sample_size=50.0,
        max_symbol_concentration=0.75,
        min_cost_stress_psr=0.5,
        max_abs_drawdown=0.2,
        min_total_return=0.0,
        max_components=3,
        max_params=10,
        train_score_floor=0.5,
        subwindows=3,
    )


def _protocol_text() -> str:
    return """
strategy_path = "strategy.py"
strategy_id = "example"

[data]
kind = "bars"
dataset = "equity_1min"
symbols = ["SPY"]
start = "2025-01-01"
end = "2025-01-31"

[fill_model]
price = "close"
entry_lag_bars = 1

[cost_model]
fee_bps_per_side = 1.0
slippage_bps_per_side = 1.0

[capacity_model]
mode = "off"

[leverage_budget]
max_gross_exposure = 1.0
max_net_exposure = 1.0

[output]
results_dir = "results"
artifact_profile = "diagnostic"
quick_checks = true
causality_check = "micro"
diagnostic_sample_trades = 5
foundation_subwindows = 3
foundation_cost_stress_multiplier = 2.0

[loop]
plateau_patience = 5
max_iterations = 10
min_abs_improvement = 0.001
min_rel_improvement = 0.0
baseline_grace_iterations = 3

[objective]
kind = "portfolio_psr_subwindow"
subwindows = 3
psr_hurdle_sharpe = 0.0

[gates]
min_trades = 10
min_trades_per_subwindow = 3
min_return_sample_count = 100
min_effective_sample_size = 50.0
max_symbol_concentration = 0.75
min_cost_stress_psr = 0.5
max_abs_drawdown = 0.2
min_total_return = 0.0
max_components = 3
max_params = 10
train_score_floor = 0.5
""".strip() + "\n"


def test_protocol_materializes_foundation_and_micro(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())

    protocol = load_protocol(protocol_path)
    quick = build_quick_run_config(protocol, {"lookback": 3})
    output = quick["output"]
    assert isinstance(output, Mapping)

    assert protocol.output.causality_check == "micro"
    assert protocol.objective.kind == "portfolio_psr_subwindow"
    assert protocol.objective.psr_hurdle_sharpe == 0.0
    assert protocol.capacity_model.mode == "off"
    assert output["causality_check"] == "micro"
    assert output["foundation_subwindows"] == 3
    assert output["foundation_cost_stress_multiplier"] == 2.0
    assert quick["capacity_model"]["mode"] == "off"
    assert quick["leverage_budget"]["max_net_exposure"] == 1.0
    assert quick["envelope"]["operator_frozen"] is True


def test_protocol_rejects_missing_capacity_and_low_cost_stress_multiplier(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"

    protocol_path.write_text(
        _protocol_text().replace('[capacity_model]\nmode = "off"\n', "")
    )
    try:
        load_protocol(protocol_path)
    except ValueError as exc:
        assert "capacity_model" in str(exc)
    else:
        raise AssertionError("expected missing capacity_model to fail")

    protocol_path.write_text(
        _protocol_text().replace("foundation_cost_stress_multiplier = 2.0", "foundation_cost_stress_multiplier = 0.5")
    )
    try:
        load_protocol(protocol_path)
    except ValueError as exc:
        assert "foundation_cost_stress_multiplier must be >= 1.0" in str(exc)
    else:
        raise AssertionError("expected low cost-stress multiplier to fail")


def test_portfolio_psr_score_uses_full_train_and_worst_subwindow():
    config = ObjectiveConfig(
        kind="portfolio_psr_subwindow",
        subwindows=3,
        psr_hurdle_sharpe=0.0,
    )
    result = score_objective((), config, foundation=_foundation())

    expected_full = NormalDist().cdf(0.4 / 0.2)
    expected_worst = NormalDist().cdf(0.1 / 0.2)

    assert result.score == expected_worst
    assert result.full_train_psr == expected_full
    assert result.worst_subwindow_id == "train_2"
    assert result.subwindow_trade_counts == (20, 12, 20)


def test_portfolio_psr_score_can_be_full_train_binding_and_hurdled():
    config = ObjectiveConfig(
        kind="portfolio_psr_subwindow",
        subwindows=3,
        psr_hurdle_sharpe=0.1,
    )
    result = score_objective(
        (),
        config,
        foundation=_foundation(full_train_sharpe=0.05, train_2_sharpe=0.4),
    )

    assert result.score == NormalDist().cdf((0.05 - 0.1) / 0.2)
    assert result.worst_subwindow_id == "train_3"


def test_portfolio_psr_score_rejects_invalid_sharpe_inputs():
    config = ObjectiveConfig(
        kind="portfolio_psr_subwindow",
        subwindows=3,
        psr_hurdle_sharpe=0.0,
    )
    invalid_cases = (
        (
            FoundationEvidence(
                realistic_costs=FoundationScenario(
                    scenario_id="realistic_costs",
                    full_train=_metric("full_train", sharpe=None),
                    subwindows=(_metric("train_1", sharpe=0.2),) * 3,
                ),
                cost_stress=_foundation().cost_stress,
            ),
            "missing sharpe",
        ),
        (
            FoundationEvidence(
                realistic_costs=FoundationScenario(
                    scenario_id="realistic_costs",
                    full_train=_metric("full_train", sharpe=float("nan")),
                    subwindows=(_metric("train_1", sharpe=0.2),) * 3,
                ),
                cost_stress=_foundation().cost_stress,
            ),
            "non-finite sharpe",
        ),
        (
            FoundationEvidence(
                realistic_costs=FoundationScenario(
                    scenario_id="realistic_costs",
                    full_train=_metric("full_train", sharpe=0.2, sharpe_se=0.0),
                    subwindows=(_metric("train_1", sharpe=0.2),) * 3,
                ),
                cost_stress=_foundation().cost_stress,
            ),
            "invalid sharpe_standard_error",
        ),
    )

    for foundation, expected_detail in invalid_cases:
        result = score_objective((), config, foundation=foundation)
        assert result.score is None
        assert expected_detail in result.detail


def test_foundation_gates_use_portfolio_metrics_not_trade_bag_concentration():
    foundation = _foundation()
    objective = score_objective(
        (),
        ObjectiveConfig(
            kind="portfolio_psr_subwindow",
            subwindows=3,
            psr_hurdle_sharpe=0.0,
        ),
        foundation=foundation,
    )
    cost_stress = score_foundation_cost_stress(
        foundation,
        ObjectiveConfig(
            kind="portfolio_psr_subwindow",
            subwindows=3,
            psr_hurdle_sharpe=0.0,
        ),
    )

    gates = evaluate_gates(
        (
            TradeSample(
                symbol="SPY",
                decision_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                net_return=0.01,
            ),
        ),
        params={},
        components=("signal",),
        config=_gate_config(),
        cost_stress_score=cost_stress.score,
        train_score=objective.score,
        subwindow_trade_counts=objective.subwindow_trade_counts,
        foundation_scenario=foundation.realistic_costs,
    )

    assert gates.passed
    assert gates.by_name["minimum_evidence"].passed
    assert gates.by_name["trade_floor"].passed
    assert gates.by_name["subwindow_coverage"].passed
    assert gates.by_name["breadth"].value == 0.4
    assert gates.by_name["path_risk"].passed
    assert gates.by_name["economic_return"].passed


def test_foundation_breadth_gate_fails_when_foundation_concentration_missing():
    base = _foundation()
    foundation = replace(
        base,
        realistic_costs=replace(
            base.realistic_costs,
            full_train=replace(
                base.realistic_costs.full_train,
                max_symbol_concentration=None,
            ),
        ),
    )
    objective = score_objective(
        (),
        ObjectiveConfig(
            kind="portfolio_psr_subwindow",
            subwindows=3,
            psr_hurdle_sharpe=0.0,
        ),
        foundation=foundation,
    )
    cost_stress = score_foundation_cost_stress(
        foundation,
        ObjectiveConfig(
            kind="portfolio_psr_subwindow",
            subwindows=3,
            psr_hurdle_sharpe=0.0,
        ),
    )

    gates = evaluate_gates(
        (
            TradeSample(
                symbol="A",
                decision_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                net_return=0.01,
            ),
            TradeSample(
                symbol="B",
                decision_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                net_return=0.01,
            ),
        ),
        params={},
        components=("signal",),
        config=_gate_config(),
        cost_stress_score=cost_stress.score,
        train_score=objective.score,
        subwindow_trade_counts=objective.subwindow_trade_counts,
        foundation_scenario=foundation.realistic_costs,
    )

    assert not gates.by_name["breadth"].passed
    assert gates.by_name["breadth"].value is None
    assert "missing foundation" in gates.by_name["breadth"].detail


def test_foundation_gates_reject_invalid_metric_ranges():
    base = _foundation()
    config = ObjectiveConfig(
        kind="portfolio_psr_subwindow",
        subwindows=3,
        psr_hurdle_sharpe=0.0,
    )
    invalid_foundations = (
        (
            replace(
                base,
                realistic_costs=replace(
                    base.realistic_costs,
                    full_train=replace(base.realistic_costs.full_train, max_drawdown=0.4),
                ),
            ),
            "path_risk",
        ),
        (
            replace(
                base,
                realistic_costs=replace(
                    base.realistic_costs,
                    full_train=replace(
                        base.realistic_costs.full_train,
                        max_symbol_concentration=-0.1,
                    ),
                ),
            ),
            "breadth",
        ),
        (
            replace(
                base,
                realistic_costs=replace(
                    base.realistic_costs,
                    full_train=replace(
                        base.realistic_costs.full_train,
                        effective_sample_size=float("nan"),
                    ),
                ),
            ),
            "minimum_evidence",
        ),
    )

    for foundation, failed_gate in invalid_foundations:
        objective = score_objective((), config, foundation=foundation)
        cost_stress = score_foundation_cost_stress(foundation, config)
        gates = evaluate_gates(
            (),
            params={},
            components=("signal",),
            config=_gate_config(),
            cost_stress_score=cost_stress.score,
            train_score=objective.score,
            subwindow_trade_counts=objective.subwindow_trade_counts,
            foundation_scenario=foundation.realistic_costs,
        )

        assert not gates.by_name[failed_gate].passed


def test_run_iteration_crashes_on_malformed_foundation_payload(tmp_path: Path):
    (tmp_path / "protocol.toml").write_text(_protocol_text())
    (tmp_path / "experiment.toml").write_text("[params]\n[bounds]\n")
    (tmp_path / "strategy.py").write_text("__all__ = []\n")
    (tmp_path / "rationale.md").write_text(
        "## Signal Components\n\n### Component: signal\n"
    )
    protocol = load_protocol(tmp_path / "protocol.toml")
    payload = _foundation_payload()
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, dict)
    realistic = scenarios["realistic_costs"]
    assert isinstance(realistic, dict)
    full_train = realistic["full_train"]
    assert isinstance(full_train, dict)
    full_train["max_drawdown"] = float("inf")
    result = FakeRunResult(
        succeeded=True,
        economics=None,
        foundation=RawFoundation(payload),
        evidence=FakeEvidence(causality=FakeCausality()),
    )

    outcome = run_iteration(
        protocol,
        params={},
        components=("signal",),
        results_path=tmp_path / "results.tsv",
        iteration=1,
        best_score=None,
        runner=lambda *args, **kwargs: result,
        workdir=tmp_path,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    run_card = json.loads(
        (tmp_path / "results/autoresearch/attempt-0001/run_card.json").read_text()
    )
    assert outcome.status == "crash"
    assert "non-finite foundation value: max_drawdown" in row.note
    assert "non-finite foundation value: max_drawdown" in run_card["error"]


def test_cost_stress_gate_failure_does_not_change_base_score():
    foundation = _foundation(cost_stress_train_2_sharpe=-0.5)
    config = ObjectiveConfig(
        kind="portfolio_psr_subwindow",
        subwindows=3,
        psr_hurdle_sharpe=0.0,
    )
    objective = score_objective((), config, foundation=foundation)
    cost_stress = score_foundation_cost_stress(foundation, config)
    gates = evaluate_gates(
        (),
        params={},
        components=("signal",),
        config=_gate_config(),
        cost_stress_score=cost_stress.score,
        train_score=objective.score,
        subwindow_trade_counts=objective.subwindow_trade_counts,
        foundation_scenario=foundation.realistic_costs,
    )

    assert objective.score == NormalDist().cdf(0.1 / 0.2)
    assert cost_stress.score is not None and cost_stress.score < 0.5
    assert not gates.passed
    assert not gates.by_name["cost_stress"].passed


def test_result_log_replaces_empty_legacy_header_and_rejects_nonempty_legacy(tmp_path: Path):
    row = ResultRow(
        run_id="attempt-0001",
        commit="abcdef0",
        artifact_dir="results/autoresearch/attempt-0001",
        worktree_dirty=False,
        strategy_sha256="a" * 64,
        experiment_sha256="b" * 64,
        protocol_sha256="c" * 64,
        rationale_sha256="d" * 64,
        quick_config_sha256="e" * 64,
        iteration=1,
        score=0.6914624612740131,
        full_train_psr=0.9772498680518208,
        worst_subwindow_psr=0.6914624612740131,
        worst_subwindow_id="train_2",
        cost_stress_psr=0.5987063256829237,
        gates_passed=True,
        gate_flags="train_floor=pass",
        trade_count=52,
        min_subwindow_trades=12,
        total_return=0.04,
        max_drawdown=-0.03,
        win_rate=0.55,
        profit_factor=1.4,
        avg_trade_net=0.001,
        cost_return_sum=0.02,
        max_symbol_concentration=0.4,
        complexity_count=1,
        status="keep",
        best_status="updated",
        continuation="allowed",
        stop_reason="",
        elapsed_seconds=1.25,
        note="",
    )

    header_only = tmp_path / "header_only.tsv"
    header_only.write_text("old\tcolumns\n")
    assert read_results(header_only) == []
    append_result(header_only, row)
    header = header_only.read_text().splitlines()[0].split("\t")
    assert header == ResultRow.header()
    assert "subwindow_trade_counts" not in header
    assert "cost_stress" not in header
    assert "gross_return_sum" not in header
    assert read_results(header_only)[0] == row

    nonempty = tmp_path / "nonempty.tsv"
    nonempty.write_text("old\tcolumns\n1\t2\n")
    try:
        append_result(nonempty, row)
    except ValueError as exc:
        assert "legacy results.tsv schema" in str(exc)
    else:
        raise AssertionError("expected legacy non-empty result log to fail")
    try:
        read_results(nonempty)
    except ValueError as exc:
        assert "legacy results.tsv schema" in str(exc)
    else:
        raise AssertionError("expected legacy non-empty result log read to fail")


def test_run_iteration_writes_compact_row_and_run_card(tmp_path: Path):
    (tmp_path / "protocol.toml").write_text(_protocol_text())
    (tmp_path / "experiment.toml").write_text("[params]\n[bounds]\n")
    (tmp_path / "strategy.py").write_text("__all__ = []\n")
    (tmp_path / "rationale.md").write_text(
        "## Signal Components\n\n### Component: signal\n"
    )
    protocol = load_protocol(tmp_path / "protocol.toml")
    result = FakeRunResult(
        succeeded=True,
        economics=FakeEconomics(
            trades=(
                FakeTrade(
                    symbol="SPY",
                    decision_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    net_return=0.01,
                    gross_return=0.012,
                    cost_return=0.002,
                ),
                FakeTrade(
                    symbol="SPY",
                    decision_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                    net_return=-0.002,
                    gross_return=0.0,
                    cost_return=0.002,
                ),
            )
        ),
        foundation=FakeFoundation(_foundation(warnings=("sample_warning",))),
        evidence=FakeEvidence(causality=FakeCausality()),
    )

    outcome = run_iteration(
        protocol,
        params={},
        components=("signal",),
        results_path=tmp_path / "results.tsv",
        iteration=1,
        best_score=None,
        runner=lambda *args, **kwargs: result,
        workdir=tmp_path,
    )

    rows = read_results(tmp_path / "results.tsv")
    run_card = tmp_path / "results/autoresearch/attempt-0001/run_card.json"
    quick_config = tmp_path / ".autoresearch/quick/attempt-0001.toml"

    assert outcome.status == "keep"
    assert rows[0].full_train_psr == NormalDist().cdf(0.4 / 0.2)
    assert rows[0].worst_subwindow_id == "train_2"
    assert rows[0].trade_count == 20
    assert rows[0].total_return == 0.05
    assert rows[0].win_rate == 0.5
    assert rows[0].cost_return_sum == 0.004
    run_card_payload = json.loads(run_card.read_text())
    assert run_card_payload["score_parts"]["full_train_psr"] == NormalDist().cdf(0.4 / 0.2)
    assert run_card_payload["score_parts"]["worst_subwindow_id"] == "train_2"
    assert run_card_payload["score_parts"]["cost_stress_psr"] == NormalDist().cdf(0.05 / 0.2)
    assert run_card_payload["gates"][0]["name"] == "trade_floor"
    assert run_card_payload["foundation"]["realistic_costs"]["full_train"]["warnings"] == [
        "sample_warning"
    ]
    assert run_card_payload["causality"]["causality_check"] == "micro"
    assert run_card_payload["primary_failure_mode"] == ""
    quick_config_text = quick_config.read_text()
    assert "[capacity_model]" in quick_config_text
    assert 'mode = "off"' in quick_config_text
    assert "[leverage_budget]" in quick_config_text


def test_run_iteration_scores_foundation_when_diagnostic_economics_missing(tmp_path: Path):
    (tmp_path / "protocol.toml").write_text(_protocol_text())
    (tmp_path / "experiment.toml").write_text("[params]\n[bounds]\n")
    (tmp_path / "strategy.py").write_text("__all__ = []\n")
    (tmp_path / "rationale.md").write_text(
        "## Signal Components\n\n### Component: signal\n"
    )
    protocol = load_protocol(tmp_path / "protocol.toml")
    result = FakeRunResult(
        succeeded=True,
        economics=None,
        foundation=FakeFoundation(),
        evidence=FakeEvidence(causality=FakeCausality()),
    )

    outcome = run_iteration(
        protocol,
        params={},
        components=("signal",),
        results_path=tmp_path / "results.tsv",
        iteration=1,
        best_score=None,
        runner=lambda *args, **kwargs: result,
        workdir=tmp_path,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    assert outcome.status == "keep"
    assert row.score == NormalDist().cdf(0.1 / 0.2)
    assert row.trade_count == 20
    assert row.win_rate is None
    assert row.avg_trade_net is None


def test_run_iteration_discards_when_cost_stress_gate_fails(tmp_path: Path):
    (tmp_path / "protocol.toml").write_text(_protocol_text())
    (tmp_path / "experiment.toml").write_text("[params]\n[bounds]\n")
    (tmp_path / "strategy.py").write_text("__all__ = []\n")
    (tmp_path / "rationale.md").write_text(
        "## Signal Components\n\n### Component: signal\n"
    )
    protocol = load_protocol(tmp_path / "protocol.toml")
    result = FakeRunResult(
        succeeded=True,
        economics=FakeEconomics(trades=()),
        foundation=FakeFoundation(_foundation(cost_stress_train_2_sharpe=-0.5)),
        evidence=FakeEvidence(causality=FakeCausality()),
    )

    outcome = run_iteration(
        protocol,
        params={},
        components=("signal",),
        results_path=tmp_path / "results.tsv",
        iteration=1,
        best_score=None,
        runner=lambda *args, **kwargs: result,
        workdir=tmp_path,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    run_card = json.loads(
        (tmp_path / "results/autoresearch/attempt-0001/run_card.json").read_text()
    )
    assert outcome.status == "discard"
    assert row.best_status == "unchanged"
    assert row.score == NormalDist().cdf(0.1 / 0.2)
    assert row.cost_stress_psr is not None and row.cost_stress_psr < 0.5
    assert "cost_stress=fail" in row.gate_flags
    assert run_card["primary_failure_mode"] == "cost_stress"


def test_run_iteration_crashes_when_foundation_missing(tmp_path: Path):
    (tmp_path / "protocol.toml").write_text(_protocol_text())
    (tmp_path / "experiment.toml").write_text("[params]\n[bounds]\n")
    (tmp_path / "strategy.py").write_text("__all__ = []\n")
    (tmp_path / "rationale.md").write_text(
        "## Signal Components\n\n### Component: signal\n"
    )
    protocol = load_protocol(tmp_path / "protocol.toml")
    result = FakeRunResult(
        succeeded=True,
        economics=FakeEconomics(trades=()),
        foundation=None,
        evidence=FakeEvidence(causality=FakeCausality()),
    )

    outcome = run_iteration(
        protocol,
        params={},
        components=("signal",),
        results_path=tmp_path / "results.tsv",
        iteration=1,
        best_score=None,
        runner=lambda *args, **kwargs: result,
        workdir=tmp_path,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    run_card = json.loads(
        (tmp_path / "results/autoresearch/attempt-0001/run_card.json").read_text()
    )
    assert outcome.status == "crash"
    assert row.continuation == "repair_required"
    assert "missing portfolio foundation" in row.note
    assert "missing portfolio foundation" in run_card["error"]
    assert run_card["primary_failure_mode"] == "foundation_unavailable"
