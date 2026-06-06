"""AC-1 (FULL) — the diagnosed campaign through the REAL OOS walk-forward + gates path.

The diagnosed overfit (ADA-only / short-only disguised as a basket, excluded clock-hours,
sizing cranked to 0.20) is reproduced as a HIGH-FIDELITY synthetic per-fold return profile
and run end-to-end through ``run_walk_forward_res`` with ``FakeFoundationGateway`` (live data
is unavailable in this environment; the seam makes this deterministic). It must come out
**infeasible / rejected** — never graduate. A genuine diversified-alpha campaign through the
SAME path is the positive control.

The factor panel is the TRUE market/funding driver per fold (in the real path it comes from
quant_data; here the synthetic gateway stashes the exact driver columns so residual alpha is
measured against the real factor, exactly as production would neutralize BTC beta + funding).
"""

from __future__ import annotations

import numpy as np

from harness.foundation import FoldEvalResult, FoldReturns
from harness.objective.res import GateThresholds
from harness.orchestrator import run_walk_forward_res
from harness.protocol import Experiment, Protocol
from harness.testing import make_returns

PPY = 8760.0
_FOLDS = {
    "scheme": "rolling",
    "n_folds": 3,
    "train_periods": 720,
    "test_periods": 240,
    "purge_periods": 24,
    "embargo_periods": 24,
}
THRESHOLDS = GateThresholds(min_trades=30, max_concentration=0.6, min_effective_breadth=2.0)


def _protocol(symbols) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "ac1-full",
            "cost_model": {"taker_bps": 5, "maker_bps": 1, "slippage_bps": 1, "stress_multiplier": 2.0},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-03-31"},
                "selection": {"start": "2024-04-01", "end": "2024-10-31"},
                "lockbox": {"start": "2024-11-01", "end": "2024-12-31"},
                "symbols": list(symbols),
                "source": {"kind": "crypto_perp_funding"},
            },
            "folds": _FOLDS,
            "annualization": {"periods_per_year": PPY},
        }
    )


def _experiment(symbols) -> Experiment:
    return Experiment(strategy_path="strategy.py", params={"weight": 0.20}, symbols=tuple(symbols))


class _SyntheticGateway:
    """A FoundationGateway whose evaluate fabricates a fold AND records the TRUE factor panel
    for that fold's return series, so the orchestrator's panel provider can return the exact
    market/funding driver (faithful to the real path, which neutralizes the real factor)."""

    def __init__(self, make_fold):
        self._make_fold = make_fold
        self._panels: dict[int, dict] = {}
        self._seed = 0
        self.evaluate_calls: list = []

    def quick_run(self, experiment, protocol, window):  # pragma: no cover - unused here
        raise NotImplementedError

    def evaluate(self, experiment, protocol, window):  # noqa: ARG002
        self.evaluate_calls.append(window)
        self._seed += 1
        fold, panel, sharpe = self._make_fold(self._seed)
        self._panels[id(fold)] = panel
        return FoldEvalResult(
            succeeded=True, causal_ok=True, returns=fold, sharpe=sharpe, sortino=sharpe,
            calmar=1.0, max_drawdown=-0.10, trade_count=300, worst_period_return=-0.04,
            provenance={"snapshot": "synthetic"}, failure_stage=None,
        )

    def panel_for(self, window, returns):
        return self._panels.get(id(returns), {})


def _diagnosed_fold(seed, n=240):
    """ADA dominates; XRP/AVAX co-move at tiny weight; PnL is pure market+funding beta."""
    rng = np.random.default_rng(seed)
    market = 0.012 * rng.standard_normal(n) + 0.004
    funding = 0.006 * rng.standard_normal(n) + 0.003
    ada = 1.3 * market + 1.0 * funding  # beta + carry, NO idiosyncratic alpha
    by_symbol = {
        "ADA-PERP": make_returns(0.95 * ada, periods_per_year=PPY),
        "XRP-PERP": make_returns(0.025 * (ada * 1.01), periods_per_year=PPY),
        "AVAX-PERP": make_returns(0.025 * (ada * 0.99), periods_per_year=PPY),
    }
    port = sum(fr.values for fr in by_symbol.values())
    fold = FoldReturns(
        timestamps=make_returns(port, periods_per_year=PPY).timestamps,
        values=port, periods_per_year=PPY, by_symbol=by_symbol,
    )
    return fold, {"market": market, "funding_carry": funding}, 2.0


def _genuine_fold(seed, symbols, n=240):
    """Diversified INDEPENDENT idiosyncratic alpha sharing a market beta."""
    market = 0.012 * np.random.default_rng(seed).standard_normal(n) + 0.004
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate(symbols):
        rng = np.random.default_rng(seed * 10 + i)
        leg = 0.0012 + 0.9 * market + 0.003 * rng.standard_normal(n)
        by_symbol[sym] = make_returns(leg, periods_per_year=PPY)
        port += leg / len(symbols)
    fold = FoldReturns(
        timestamps=make_returns(port, periods_per_year=PPY).timestamps,
        values=port, periods_per_year=PPY, by_symbol=by_symbol,
    )
    # A COVERING panel (market + funding_carry) — the columns the Protocol requires neutralized
    # (funding is ~0 in this synthetic fold, but the column is present, as the real provider
    # supplies it). The genuine idiosyncratic alpha survives neutralization.
    return fold, {"market": market, "funding_carry": np.zeros_like(market)}, 1.5


def test_ac1_full_diagnosed_campaign_is_infeasible_through_the_walk_forward_path():
    symbols = ("ADA-PERP", "XRP-PERP", "AVAX-PERP")
    proto, exp = _protocol(symbols), _experiment(symbols)
    gw = _SyntheticGateway(_diagnosed_fold)

    out = run_walk_forward_res(exp, proto, gw, gw.panel_for, thresholds=THRESHOLDS)

    assert out.n_folds_evaluated >= 1
    res = out.res
    # The diagnosed overfit does NOT graduate: infeasible, no rankable residual edge.
    # (Pure market+funding beta ⇒ residual alpha ≈ 0 ⇒ rank_sharpe None; AND the co-moving
    # legs collapse the correlation-aware breadth gate to ≈1.)
    assert res.feasible is False
    assert res.rank_sharpe is None
    # The residual IR is ≈ 0 — there is no idiosyncratic edge to confirm (AC-9 mechanism).
    assert res.residual_info_ratio is None or abs(res.residual_info_ratio) < 0.1
    # The correlation-aware breadth gate bounces the same-coin "basket".
    assert not res.gate_results["effective_breadth"].passed


def test_ac1_full_genuine_diversified_edge_is_feasible_through_the_same_path():
    """Positive control: a genuinely diversified idiosyncratic-alpha campaign IS feasible."""
    symbols = ("AAA-PERP", "BBB-PERP", "CCC-PERP")
    proto, exp = _protocol(symbols), _experiment(symbols)
    gw = _SyntheticGateway(lambda seed: _genuine_fold(seed, symbols))

    out = run_walk_forward_res(exp, proto, gw, gw.panel_for, thresholds=THRESHOLDS)

    assert out.n_folds_evaluated >= 2
    assert out.res.feasible
    assert out.res.rank_sharpe is not None and out.res.rank_sharpe > 0
    # Cost-stress evidence was sourced (a second evaluate under the stressed Protocol ran).
    assert "cost_stress" in out.res.gate_results


def test_orchestrator_calls_evaluate_once_per_fold_per_cost_scenario():
    """FR-J2: one evaluate per fold (×2 here: realistic + stressed cost-stress evidence)."""
    symbols = ("AAA-PERP", "BBB-PERP", "CCC-PERP")
    proto, exp = _protocol(symbols), _experiment(symbols)
    gw = _SyntheticGateway(lambda seed: _genuine_fold(seed, symbols))
    out = run_walk_forward_res(exp, proto, gw, gw.panel_for, thresholds=THRESHOLDS)
    # 3 folds, realistic + stressed ⇒ 6 evaluate calls.
    assert len(gw.evaluate_calls) == 2 * out.n_folds_evaluated
    # Each fold window is strictly forward (test windows tile forward across the Selection span).
    starts = [w.start for w in out.fold_windows]
    assert starts == sorted(starts)


def test_orchestrator_no_cost_stress_omits_the_gate():
    symbols = ("AAA-PERP", "BBB-PERP", "CCC-PERP")
    proto, exp = _protocol(symbols), _experiment(symbols)
    gw = _SyntheticGateway(lambda seed: _genuine_fold(seed, symbols))
    out = run_walk_forward_res(exp, proto, gw, gw.panel_for, thresholds=THRESHOLDS, cost_stress=False)
    assert "cost_stress" not in out.res.gate_results
    # Only the realistic evaluate ran per fold.
    assert len(gw.evaluate_calls) == out.n_folds_evaluated
