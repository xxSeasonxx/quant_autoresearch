from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import sqrt
import json
from pathlib import Path
from statistics import NormalDist
from typing import Mapping

import pytest

from gates import GateConfig, GateOutcome, GateSet, evaluate_gates
import loop
from loop import run_iteration
from objective import (
    FoundationEvidence,
    FoundationMetric,
    FoundationScenario,
    FoundationSizing,
    ObjectiveConfig,
    ObjectiveResult,
    TradeSample,
    deflated_window_floor,
    score_foundation_cost_stress,
    score_objective,
)
from protocol import build_quick_run_config, load_protocol
from results_log import ResultRow, append_result, read_results

# Run-level annualization used across the fixtures.
_P = 252


def _lcb(mean_return: float, return_volatility: float, n_eff: float, *, k: float) -> float:
    annualized = mean_return * _P
    standard_error = return_volatility * _P / sqrt(n_eff)
    return annualized - k * standard_error


def _metric(
    window_id: str,
    *,
    mean_return: float | None = 0.0012,
    return_volatility: float | None = 0.0010,
    effective_sample_size: float | None = 120.0,
    sharpe: float | None = None,
    sharpe_se: float | None = None,
    total_return: float = 0.05,
    max_drawdown: float = -0.03,
    closed_trade_count: int = 20,
    return_sample_count: int = 200,
    max_symbol_concentration: float = 0.4,
    warnings: tuple[str, ...] = (),
    max_gross_utilization: float = 0.02,
    max_net_utilization: float = 0.02,
    effective_symbol_count: float = 3.0,
) -> FoundationMetric:
    # Default the diagnostic Sharpe inputs to be consistent with the money moments
    # so the PSR cross-check identity holds: sharpe = mean/vol (per period),
    # sharpe_se = 1/sqrt(n_eff). Tests that probe SE-source independence override.
    if (
        sharpe is None
        and mean_return is not None
        and return_volatility is not None
        and return_volatility != 0.0
    ):
        sharpe = mean_return / return_volatility
    if (
        sharpe_se is None
        and effective_sample_size is not None
        and effective_sample_size != 0.0
    ):
        assert effective_sample_size is not None
        sharpe_se = 1.0 / sqrt(effective_sample_size)
    return FoundationMetric(
        window_id=window_id,
        return_sample_count=return_sample_count,
        effective_sample_size=effective_sample_size,
        mean_return=mean_return,
        return_volatility=return_volatility,
        sharpe=sharpe,
        sharpe_standard_error=sharpe_se,
        total_return=total_return,
        max_drawdown=max_drawdown,
        closed_trade_count=closed_trade_count,
        max_symbol_concentration=max_symbol_concentration,
        warnings=warnings,
        max_gross_utilization=max_gross_utilization,
        max_net_utilization=max_net_utilization,
        effective_symbol_count=effective_symbol_count,
    )


def _sizing(
    *,
    book_scale: float | None = 1.5,
    deployed_volatility: float | None = 0.18,
    max_feasible_volatility: float | None = 0.30,
    capacity_bound: bool | None = False,
) -> FoundationSizing:
    return FoundationSizing(
        annualization_periods_per_year=_P,
        book_scale=book_scale,
        deployed_volatility=deployed_volatility,
        max_feasible_volatility=max_feasible_volatility,
        capacity_bound=capacity_bound,
    )


def _foundation(
    *,
    full_train_mean: float = 0.0012,
    worst_subwindow_mean: float = 0.0009,
    cost_stress_full_mean: float = 0.0008,
    total_return: float = 0.05,
    max_drawdown: float = -0.03,
    warnings: tuple[str, ...] = (),
    sizing: FoundationSizing | None = None,
) -> FoundationEvidence:
    return FoundationEvidence(
        realistic_costs=FoundationScenario(
            scenario_id="realistic_costs",
            full_train=_metric(
                "full_train",
                mean_return=full_train_mean,
                total_return=total_return,
                max_drawdown=max_drawdown,
                warnings=warnings,
            ),
            subwindows=(
                _metric("train_1"),
                _metric("train_2", mean_return=worst_subwindow_mean, closed_trade_count=12),
                _metric("train_3"),
            ),
        ),
        cost_stress=FoundationScenario(
            scenario_id="cost_stress",
            full_train=_metric("full_train", mean_return=cost_stress_full_mean),
            subwindows=(
                _metric("train_1", mean_return=0.0007),
                _metric("train_2", mean_return=0.0005, closed_trade_count=12),
                _metric("train_3", mean_return=0.0007),
            ),
        ),
        sizing=sizing or _sizing(),
    )


def _config() -> ObjectiveConfig:
    return ObjectiveConfig(kind="return_lcb_subwindow", subwindows=3, psr_hurdle_sharpe=0.0)


def _foundation_payload(foundation: FoundationEvidence | None = None) -> dict[str, object]:
    def metric_payload(metric: FoundationMetric) -> dict[str, object]:
        return {
            "window_id": metric.window_id,
            "return_sample_count": metric.return_sample_count,
            "effective_sample_size": metric.effective_sample_size,
            "mean_return": metric.mean_return,
            "return_volatility": metric.return_volatility,
            "sharpe": metric.sharpe,
            "sharpe_standard_error": metric.sharpe_standard_error,
            "total_return": metric.total_return,
            "max_drawdown": metric.max_drawdown,
            "closed_trade_count": metric.closed_trade_count,
            "max_symbol_concentration": metric.max_symbol_concentration,
            "effective_symbol_count": metric.effective_symbol_count,
            "max_gross_utilization": metric.max_gross_utilization,
            "max_net_utilization": metric.max_net_utilization,
            "warnings": list(metric.warnings),
        }

    def scenario_payload(scenario: FoundationScenario) -> dict[str, object]:
        return {
            "scenario_id": scenario.scenario_id,
            "capacity": {"max_adv_participation": 0.05, "max_bar_participation": 0.1},
            "full_train": metric_payload(scenario.full_train),
            "subwindows": [metric_payload(metric) for metric in scenario.subwindows],
        }

    foundation = foundation or _foundation()
    sizing = foundation.sizing
    return {
        "sizing_report": {
            "annualization_periods_per_year": sizing.annualization_periods_per_year,
            "book_scale": sizing.book_scale,
            "deployed_volatility": sizing.deployed_volatility,
            "max_feasible_volatility": sizing.max_feasible_volatility,
            "capacity_bound": sizing.capacity_bound,
        },
        "scenarios": {
            "realistic_costs": scenario_payload(foundation.realistic_costs),
            "cost_stress": scenario_payload(foundation.cost_stress),
        },
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
    causality_admissible: bool = True


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
        min_return_sample_count=100,
        min_effective_sample_size=50.0,
        max_symbol_concentration=0.75,
        min_cost_stress_return_retention=0.5,
        max_abs_drawdown=0.2,
        min_annualized_return=0.10,
        score_haircut_se=2.8,
        max_components=3,
        max_params=10,
    )


def _evaluate(
    foundation: FoundationEvidence,
    *,
    trades: tuple[TradeSample, ...] = (),
    causality_admissible: bool | None = True,
    config: GateConfig | None = None,
):
    objective = score_objective((), _config(), foundation=foundation)
    cost_stress = score_foundation_cost_stress(foundation, _config())
    gates = evaluate_gates(
        trades,
        params={},
        components=("signal",),
        config=config or _gate_config(),
        objective=objective,
        cost_stress_full_train_return=cost_stress.full_train_return,
        causality_admissible=causality_admissible,
        foundation_scenario=foundation.realistic_costs,
    )
    return objective, cost_stress, gates


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

[risk_budget]
mode = "calibrate_vol"
annualization_periods_per_year = 525600
target_volatility = 0.15

[output]
results_dir = "results"
artifact_profile = "diagnostic"
quick_checks = true
causality_check = "micro"
micro_probe_limit = 40
micro_timeout_seconds = 600.0
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
kind = "return_lcb_subwindow"
subwindows = 3
psr_hurdle_sharpe = 0.0

[gates]
min_trades = 10
min_return_sample_count = 100
min_effective_sample_size = 50.0
max_symbol_concentration = 0.75
min_cost_stress_return_retention = 0.5
max_abs_drawdown = 0.2
min_annualized_return = 0.10
score_haircut_se = 2.8
max_components = 3
max_params = 10
""".strip() + "\n"


# --- protocol wiring -------------------------------------------------------


def test_protocol_materializes_money_objective_and_micro(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())

    protocol = load_protocol(protocol_path)
    quick = build_quick_run_config(protocol, {"lookback": 3})
    output = quick["output"]
    assert isinstance(output, Mapping)

    assert protocol.output.causality_check == "micro"
    assert protocol.objective.kind == "return_lcb_subwindow"
    assert protocol.gates.min_annualized_return == 0.10
    assert protocol.gates.score_haircut_se == 2.8
    assert protocol.gates.min_cost_stress_return_retention == 0.5
    assert output["causality_check"] == "micro"
    assert output["micro_probe_limit"] == 40
    assert output["micro_timeout_seconds"] == 600.0

    assert protocol.risk_budget.mode == "calibrate_vol"
    assert protocol.risk_budget.annualization_periods_per_year == 525600
    assert protocol.risk_budget.target_volatility == 0.15
    risk_budget = quick["risk_budget"]
    assert isinstance(risk_budget, Mapping)
    assert risk_budget["mode"] == "calibrate_vol"
    assert risk_budget["annualization_periods_per_year"] == 525600
    assert risk_budget["target_volatility"] == 0.15


def test_protocol_rejects_unknown_objective_kind(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(
        _protocol_text().replace(
            'kind = "return_lcb_subwindow"', 'kind = "portfolio_psr_subwindow"'
        )
    )
    try:
        load_protocol(protocol_path)
    except ValueError as exc:
        assert "objective.kind unsupported" in str(exc)
    else:
        raise AssertionError("expected unknown objective kind to fail")


def test_protocol_rejects_invalid_acceptance_haircut(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(
        _protocol_text().replace("score_haircut_se = 2.8", "score_haircut_se = 0.0")
    )
    try:
        load_protocol(protocol_path)
    except ValueError as exc:
        assert "score_haircut_se must be > 0" in str(exc)
    else:
        raise AssertionError("expected non-positive acceptance haircut to fail")


def test_acceptance_haircut_is_independent_of_max_iterations(tmp_path: Path):
    base = tmp_path / "base.toml"
    base.write_text(_protocol_text())
    bigger = tmp_path / "bigger.toml"
    bigger.write_text(_protocol_text().replace("max_iterations = 10", "max_iterations = 500"))

    assert load_protocol(base).gates.score_haircut_se == load_protocol(bigger).gates.score_haircut_se


# --- money score -----------------------------------------------------------


def test_score_is_full_train_lcb_at_k_rank_one():
    result = score_objective((), _config(), foundation=_foundation())

    expected = _lcb(0.0012, 0.0010, 120.0, k=1.0)  # full_train binds the score
    assert result.score == expected
    assert result.worst_window_id == "full_train"
    assert result.full_train_return == 0.0012 * _P
    assert result.worst_window_return == 0.0012 * _P
    assert result.subwindow_trade_counts == (20, 12, 20)


def test_score_binds_on_full_train_not_a_subwindow():
    high_variance_window = _metric(
        "train_2",
        mean_return=0.0020,
        return_volatility=0.0200,
        closed_trade_count=12,
    )
    low_point_return_window = _metric(
        "train_1",
        mean_return=0.0010,
        return_volatility=0.0001,
    )
    foundation = FoundationEvidence(
        realistic_costs=FoundationScenario(
            scenario_id="realistic_costs",
            full_train=_metric("full_train", mean_return=0.0030),
            subwindows=(
                low_point_return_window,
                high_variance_window,
                _metric("train_3", mean_return=0.0015, return_volatility=0.0001),
            ),
        ),
        cost_stress=_foundation().cost_stress,
        sizing=_sizing(),
    )

    result = score_objective((), _config(), foundation=foundation)

    assert result.worst_window_id == "full_train"
    assert result.worst_window_return == 0.0030 * _P
    assert result.score == _lcb(0.0030, 0.0010, 120.0, k=1.0)
    assert min(result.window_returns) == 0.0010 * _P


def test_scaling_deployed_return_moves_the_score():
    base = score_objective((), _config(), foundation=_foundation()).score
    bigger = score_objective(
        (),
        _config(),
        foundation=_foundation(
            full_train_mean=0.0024,
            worst_subwindow_mean=0.0018,
        ),
    ).score
    smaller = score_objective(
        (),
        _config(),
        foundation=_foundation(
            full_train_mean=0.0006,
            worst_subwindow_mean=0.00045,
        ),
    ).score

    assert base is not None and bigger is not None and smaller is not None
    assert bigger > base > smaller


def test_se_comes_directly_from_per_window_fields_not_a_proxy():
    # A Sharpe SE deliberately inconsistent with the money moments: the score must
    # use return_volatility * P / sqrt(n_eff), not sharpe_se * volatility.
    metric = _metric("full_train", sharpe=0.4, sharpe_se=9.0)
    foundation = FoundationEvidence(
        realistic_costs=FoundationScenario(
            scenario_id="realistic_costs",
            full_train=metric,
            subwindows=(_metric("train_1"), _metric("train_2"), _metric("train_3")),
        ),
        cost_stress=_foundation().cost_stress,
        sizing=_sizing(),
    )
    result = score_objective((), _config(), foundation=foundation)

    direct = _lcb(0.0012, 0.0010, 120.0, k=1.0)
    proxy = 0.0012 * _P - 9.0 * 0.0010
    assert result.score == direct
    assert result.score != proxy


def test_lcb_cross_check_matches_psr_t_stat():
    # With sharpe = mean/vol and sharpe_se = 1/sqrt(n_eff), t = sharpe/sharpe_se
    # equals R_w / SE_w, so LCB_w = R_w * (1 - k_rank / t) with t = Phi^-1(PSR).
    # Modest moments keep the t-stat (~2) inside (0, 1) PSR territory.
    def window(window_id: str) -> FoundationMetric:
        return _metric(
            window_id,
            mean_return=0.02,
            return_volatility=0.10,
            effective_sample_size=100.0,
        )

    uniform = FoundationScenario(
        scenario_id="realistic_costs",
        full_train=window("full_train"),
        subwindows=(window("train_1"), window("train_2"), window("train_3")),
    )
    foundation = FoundationEvidence(
        realistic_costs=uniform,
        cost_stress=_foundation().cost_stress,
        sizing=_sizing(),
    )
    result = score_objective((), _config(), foundation=foundation)

    assert result.full_train_psr is not None
    t_stat = NormalDist().inv_cdf(result.full_train_psr)
    annualized = 0.02 * _P
    expected = annualized * (1.0 - 1.0 / t_stat)
    assert result.score is not None
    assert abs(result.score - expected) < 1e-9


def test_unscoreable_window_makes_run_non_scoreable():
    base = _foundation()
    mutations = (
        replace(base.realistic_costs.subwindows[1], mean_return=None),
        replace(base.realistic_costs.subwindows[1], return_volatility=None),
        replace(base.realistic_costs.subwindows[1], return_volatility=0.0),
        replace(base.realistic_costs.subwindows[1], effective_sample_size=0.0),
        replace(base.realistic_costs.subwindows[1], mean_return=float("nan")),
    )
    for mutated in mutations:
        foundation = replace(
            base,
            realistic_costs=replace(
                base.realistic_costs,
                subwindows=(
                    base.realistic_costs.subwindows[0],
                    mutated,
                    base.realistic_costs.subwindows[2],
                ),
            ),
        )
        result = score_objective((), _config(), foundation=foundation)
        assert result.score is None
        assert "non-scoreable window" in result.detail


def test_unknown_objective_kind_is_rejected():
    try:
        score_objective((), ObjectiveConfig(kind="psr", subwindows=3), foundation=_foundation())
    except ValueError as exc:
        assert "unsupported objective kind" in str(exc)
    else:
        raise AssertionError("expected unknown objective kind to raise")


# --- gates -----------------------------------------------------------------


def test_default_foundation_passes_all_gates():
    _, _, gates = _evaluate(_foundation())
    assert gates.passed
    assert gates.by_name["money_floor"].passed
    assert gates.by_name["cost_stress_retention"].passed
    assert gates.by_name["causality"].passed


def test_money_floor_fails_when_deflated_lcb_below_hurdle():
    # Positive point estimate, but the deflated lower bound falls under the hurdle.
    foundation = _foundation(full_train_mean=0.00045, worst_subwindow_mean=0.00045)
    objective, _, gates = _evaluate(foundation)

    money_floor = deflated_window_floor(objective, k_accept=2.8)
    assert objective.worst_window_return is not None and objective.worst_window_return > 0.0
    assert money_floor is not None and money_floor < 0.10
    assert not gates.by_name["money_floor"].passed
    # The failed gate does not change the base score.
    assert objective.score == _lcb(0.00045, 0.0010, 120.0, k=1.0)


def test_cost_stress_retention_fails_when_weak():
    foundation = _foundation(cost_stress_full_mean=0.0002)  # retention ~0.167
    _, _, gates = _evaluate(foundation)
    assert not gates.by_name["cost_stress_retention"].passed


def test_cost_stress_retention_non_binding_when_realistic_nonpositive():
    foundation = _foundation(
        full_train_mean=-0.0009,
        worst_subwindow_mean=-0.0012,
        cost_stress_full_mean=-0.002,
    )
    objective, _, gates = _evaluate(foundation)
    assert objective.full_train_return is not None and objective.full_train_return <= 0.0
    assert gates.by_name["cost_stress_retention"].passed  # non-binding
    assert not gates.by_name["money_floor"].passed  # money floor is the kill


def test_causality_gate_fails_when_not_admissible():
    _, _, gates = _evaluate(_foundation(), causality_admissible=False)
    assert not gates.by_name["causality"].passed
    assert gates.by_name["causality"].detail == "not_admissible"
    _, _, gates_none = _evaluate(_foundation(), causality_admissible=None)
    assert not gates_none.by_name["causality"].passed


def test_sample_size_gate_binds_for_thin_evidence():
    base = _foundation()
    thin = replace(
        base,
        realistic_costs=replace(
            base.realistic_costs,
            subwindows=(
                base.realistic_costs.subwindows[0],
                replace(base.realistic_costs.subwindows[1], effective_sample_size=10.0),
                base.realistic_costs.subwindows[2],
            ),
        ),
    )
    _, _, gates = _evaluate(thin)
    assert not gates.by_name["minimum_evidence"].passed


def test_failed_gate_does_not_change_score():
    foundation = _foundation()
    objective, _, gates = _evaluate(foundation, causality_admissible=False)
    assert not gates.passed
    assert objective.score == _lcb(0.0012, 0.0010, 120.0, k=1.0)


def test_breadth_gate_fails_when_foundation_concentration_missing():
    base = _foundation()
    foundation = replace(
        base,
        realistic_costs=replace(
            base.realistic_costs,
            full_train=replace(
                base.realistic_costs.full_train, max_symbol_concentration=None
            ),
        ),
    )
    _, _, gates = _evaluate(foundation)
    assert not gates.by_name["breadth"].passed
    assert gates.by_name["breadth"].value is None
    assert "missing foundation" in gates.by_name["breadth"].detail


# --- ledger ----------------------------------------------------------------


def _row() -> ResultRow:
    return ResultRow(
        run_id="attempt-0001",
        iteration=1,
        status="keep",
        score=0.2037,
        worst_window_id="train_2",
        deflated_money_floor=0.162,
        full_train_annualized_return=0.3024,
        worst_window_annualized_return=0.2268,
        cost_stress_return_retention=0.667,
        book_scale=1.5,
        deployed_volatility=0.18,
        max_feasible_volatility=0.30,
        capacity_bound=False,
        full_train_psr=0.98,
        worst_subwindow_psr=0.91,
        gates_passed=True,
        gate_flags="money_floor=pass",
        trade_count=52,
        min_subwindow_trades=12,
        total_return=0.04,
        max_drawdown=-0.03,
        max_symbol_concentration=0.4,
        win_rate=0.55,
        profit_factor=1.4,
        avg_trade_net=0.001,
        cost_return_sum=0.02,
        complexity_count=1,
        failure_class="edge",
        failure_reason="",
        best_status="updated",
        continuation="allowed",
        stop_reason="",
        elapsed_seconds=1.25,
        artifact_dir="results/autoresearch/attempt-0001",
        note="",
    )


def test_result_log_round_trips_and_replaces_empty_legacy_header(tmp_path: Path):
    row = _row()
    header_only = tmp_path / "header_only.tsv"
    header_only.write_text("old\tcolumns\n")
    assert read_results(header_only) == []
    append_result(header_only, row)
    header = header_only.read_text().splitlines()[0].split("\t")
    assert header == ResultRow.header()
    assert "deflated_money_floor" in header
    assert "book_scale" in header
    assert "capacity_bound" in header
    assert "cost_stress_psr" not in header
    assert "max_gross_utilization" not in header
    assert read_results(header_only)[0] == row


def test_result_log_rejects_nonempty_legacy(tmp_path: Path):
    nonempty = tmp_path / "nonempty.tsv"
    nonempty.write_text("old\tcolumns\n1\t2\n")
    try:
        append_result(nonempty, _row())
    except ValueError as exc:
        assert "legacy results.tsv schema" in str(exc)
    else:
        raise AssertionError("expected legacy non-empty result log to fail")


# --- run_iteration end to end ----------------------------------------------


def _write_workspace(tmp_path: Path) -> None:
    (tmp_path / "protocol.toml").write_text(_protocol_text())
    (tmp_path / "experiment.toml").write_text("[params]\n[bounds]\n")
    (tmp_path / "strategy.py").write_text("__all__ = []\n")
    (tmp_path / "rationale.md").write_text("## Signal Components\n\n### Component: signal\n")


def test_climb_once_warns_and_runs_when_rationale_components_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _write_workspace(tmp_path)
    (tmp_path / "rationale.md").write_text("# Rationale\n\n## Thesis\nNo components yet.\n")
    result = FakeRunResult(
        succeeded=True,
        economics=None,
        foundation=FakeFoundation(),
        evidence=FakeEvidence(causality=FakeCausality()),
    )
    monkeypatch.chdir(tmp_path)

    outcome = loop.climb_once(
        mechanism="Funding pressure mean reverts.",
        falsifier="No post-cost robustness.",
        runner=lambda *args, **kwargs: result,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    run_card = json.loads(
        (tmp_path / "results/autoresearch/attempt-0001/run_card.json").read_text()
    )
    assert outcome.status == "keep"
    assert row.complexity_count == 0
    assert run_card["warnings"] == [
        "rationale.md has no Signal Components section; assuming zero declared components"
    ]


def test_rationale_components_empty_section_is_empty_metadata(tmp_path: Path):
    rationale = tmp_path / "rationale.md"
    rationale.write_text("# Rationale\n\n## Signal Components\n\n## Variant Log\n")

    assert loop.components_from_rationale(rationale) == ()


def test_rationale_components_reject_blank_or_duplicate_headings(tmp_path: Path):
    blank = tmp_path / "blank.md"
    blank.write_text("## Signal Components\n\n### Component:\n")
    duplicate = tmp_path / "duplicate.md"
    duplicate.write_text(
        "## Signal Components\n\n"
        "### Component: signal\n\n"
        "### Component:  Signal \n"
    )

    with pytest.raises(ValueError, match="must include a name"):
        loop.components_from_rationale(blank)
    with pytest.raises(ValueError, match="duplicate signal component"):
        loop.components_from_rationale(duplicate)


def test_run_iteration_writes_compact_row_and_run_card(tmp_path: Path):
    _write_workspace(tmp_path)
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

    assert outcome.status == "keep"
    assert rows[0].score == _lcb(0.0012, 0.0010, 120.0, k=1.0)
    assert rows[0].worst_window_id == "full_train"
    assert rows[0].deflated_money_floor == _lcb(0.0012, 0.0010, 120.0, k=2.8)
    assert rows[0].full_train_annualized_return == 0.0012 * _P
    assert rows[0].worst_window_annualized_return == 0.0012 * _P
    assert rows[0].book_scale == 1.5
    assert rows[0].capacity_bound is False
    assert rows[0].full_train_psr is not None
    assert rows[0].trade_count == 20
    assert rows[0].win_rate == 0.5
    assert rows[0].cost_return_sum == 0.004

    payload = json.loads(run_card.read_text())
    assert payload["score_parts"]["worst_window_id"] == "full_train"
    assert len(payload["score_parts"]["windows"]) == 4
    assert payload["score_parts"]["windows"][0]["t_stat"] is not None
    assert "money_floor_gap" not in payload["score_parts"]["windows"][0]
    assert payload["sizing_report"]["annualization_periods_per_year"] == _P
    realistic = payload["foundation"]["realistic_costs"]
    assert realistic["full_train"]["mean_return"] == 0.0012
    assert realistic["full_train"]["return_volatility"] == 0.0010
    assert realistic["full_train"]["effective_symbol_count"] == 3.0
    assert payload["causality"]["causality_check"] == "micro"
    assert payload["causality"]["admissible"] is True
    assert payload["causality"]["verified"] is False
    assert payload["failure_class"] == "edge"


def test_run_iteration_scores_foundation_when_diagnostic_economics_missing(tmp_path: Path):
    _write_workspace(tmp_path)
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
    assert row.score == _lcb(0.0012, 0.0010, 120.0, k=1.0)
    assert row.trade_count == 20
    assert row.win_rate is None


def test_run_iteration_discards_when_causality_not_admissible(tmp_path: Path):
    _write_workspace(tmp_path)
    protocol = load_protocol(tmp_path / "protocol.toml")
    result = FakeRunResult(
        succeeded=True,
        economics=FakeEconomics(trades=()),
        foundation=FakeFoundation(),
        evidence=FakeEvidence(
            causality=FakeCausality(verified=False),
            causality_admissible=False,
        ),
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
    assert "causality=fail" in row.gate_flags
    assert row.score == _lcb(0.0012, 0.0010, 120.0, k=1.0)
    assert run_card["causality"]["admissible"] is False
    assert run_card["causality"]["verified"] is False
    assert run_card["failure_class"] == "causality"


def test_run_iteration_discards_when_money_floor_fails(tmp_path: Path):
    _write_workspace(tmp_path)
    protocol = load_protocol(tmp_path / "protocol.toml")
    result = FakeRunResult(
        succeeded=True,
        economics=FakeEconomics(trades=()),
        foundation=FakeFoundation(
            _foundation(full_train_mean=0.00045, worst_subwindow_mean=0.00045)
        ),
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
    assert "money_floor=fail" in row.gate_flags
    assert run_card["failure_class"] == "no_edge"


def test_run_iteration_discards_nonfinite_score_input_without_crash(tmp_path: Path):
    _write_workspace(tmp_path)
    protocol = load_protocol(tmp_path / "protocol.toml")
    payload = _foundation_payload()
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, dict)
    realistic = scenarios["realistic_costs"]
    assert isinstance(realistic, dict)
    full_train = realistic["full_train"]
    assert isinstance(full_train, dict)
    full_train["mean_return"] = float("inf")
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
    assert outcome.status == "discard"
    assert row.status == "discard"
    assert row.score is None
    assert "non-scoreable window" in row.note
    assert run_card["failure_class"] == "score_unavailable"


def test_run_iteration_crashes_on_malformed_foundation_payload(tmp_path: Path):
    _write_workspace(tmp_path)
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
    assert outcome.status == "crash"
    assert "non-finite foundation value: max_drawdown" in row.note


def test_run_iteration_truncates_crash_ledger_note_and_preserves_run_card_error(
    tmp_path: Path,
):
    _write_workspace(tmp_path)
    protocol = load_protocol(tmp_path / "protocol.toml")
    long_error = "portfolio_foundation_failed: " + "missing_mark:DOGE-PERP;" * 180

    outcome = run_iteration(
        protocol,
        params={},
        components=("signal",),
        results_path=tmp_path / "results.tsv",
        iteration=1,
        best_score=None,
        runner=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(long_error)),
        workdir=tmp_path,
    )

    row = read_results(tmp_path / "results.tsv")[0]
    run_card = json.loads(
        (tmp_path / "results/autoresearch/attempt-0001/run_card.json").read_text()
    )
    assert outcome.status == "crash"
    assert outcome.message == long_error
    assert len(row.note) <= 2000
    assert row.note != long_error
    assert "truncated" in row.note
    assert run_card["error"] == long_error


def test_run_iteration_crashes_when_foundation_missing(tmp_path: Path):
    _write_workspace(tmp_path)
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
    assert run_card["failure_class"] == "foundation_unavailable"


def _gates_with(
    *,
    failed: frozenset[str] = frozenset(),
    money_floor_value: float | None = 0.2,
) -> GateSet:
    names = (
        "trade_floor",
        "minimum_evidence",
        "path_risk",
        "money_floor",
        "cost_stress_retention",
        "breadth",
        "causality",
        "complexity_cap",
    )
    return GateSet(
        outcomes=tuple(
            GateOutcome(
                name=name,
                passed=name not in failed,
                value=money_floor_value if name == "money_floor" else None,
                threshold=None,
            )
            for name in names
        )
    )


def test_failure_class_edge_when_all_gates_pass():
    assert loop._failure_class(_gates_with(), None, _sizing()) == "edge"


def test_failure_class_capacity_bound_when_money_floor_throttled_with_real_edge():
    # money_floor fails but the deflated floor is >= 0 (a significant edge after the
    # k_accept haircut) and the book is capacity-bound: real edge, throttled scale.
    gates = _gates_with(failed=frozenset({"money_floor"}), money_floor_value=0.05)
    sizing = _sizing(capacity_bound=True, deployed_volatility=0.02, max_feasible_volatility=0.02)
    assert loop._failure_class(gates, None, sizing) == "capacity_bound"


def test_failure_class_no_edge_when_deflated_floor_negative():
    gates = _gates_with(failed=frozenset({"money_floor"}), money_floor_value=-0.5)
    assert loop._failure_class(gates, None, _sizing(capacity_bound=True)) == "no_edge"


def test_failure_class_no_edge_when_money_floor_fails_without_capacity_bound():
    # Significant edge (floor >= 0) but not capacity-throttled: scaling won't help.
    gates = _gates_with(failed=frozenset({"money_floor"}), money_floor_value=0.05)
    assert loop._failure_class(gates, None, _sizing(capacity_bound=False)) == "no_edge"


def test_failure_class_breadth_evidence_and_gate_fallback():
    assert (
        loop._failure_class(_gates_with(failed=frozenset({"breadth"})), None, _sizing())
        == "breadth_bound"
    )
    assert (
        loop._failure_class(_gates_with(failed=frozenset({"minimum_evidence"})), None, _sizing())
        == "evidence_thin"
    )
    assert (
        loop._failure_class(_gates_with(failed=frozenset({"path_risk"})), None, _sizing())
        == "path_risk"
    )


def test_failure_class_causality_takes_precedence_over_money_floor():
    gates = _gates_with(failed=frozenset({"causality", "money_floor"}), money_floor_value=-0.5)
    assert loop._failure_class(gates, None, _sizing()) == "causality"


def test_failure_class_error_states():
    assert (
        loop._failure_class(None, None, None, error="portfolio foundation unavailable")
        == "foundation_unavailable"
    )
    assert loop._failure_class(None, None, None, error="boom") == "run_error"
    assert (
        loop._failure_class(None, ObjectiveResult(score=None, feasible=False), None)
        == "score_unavailable"
    )
