"""AC-1 END-TO-END (the headline) — the diagnosed campaign through the FULL loop.

Replays the diagnosed overfit (ADA-only / short-only disguised as a basket, excluded clock-hours,
sizing cranked to 0.20) through ``run`` → escalation gate → ``evaluate`` → ``graduate`` →
``lockbox`` via the Fake gateway with the diagnosed synthetic profile, and asserts it does NOT
graduate — it is stopped at the appropriate stage (infeasible / routed / rejected /
insufficient-evidence). A genuine simple diversified edge is the positive control: it flows
through to a feasible logged bet, graduates, and confirms.

Deterministic — no live data; the seam (Fake gateway) makes the whole loop reproducible.
"""

from __future__ import annotations

import numpy as np

from harness.audit import run_graduation_audit
from harness.budget import BudgetManager
from harness.cli import EvaluateLogged, EvaluateRefused, HarnessCLI
from harness.data.lockbox_book import LockboxBook
from harness.foundation import FoldEvalResult, FoldReturns, QuickRunResult
from harness.graduation import select_graduates
from harness.ledger import TrialLedger
from harness.lockbox import confirm_on_lockbox
from harness.profiler import profile_asset
from harness.protocol import Experiment, Protocol
from harness.testing import benign_funding_carry, make_returns

PPY = 8760.0

# The diagnosed campaign's signal family (one structure); the genuine control is a different one.
SRC_DIAGNOSED = '''
def generate_decisions(rows, params):
    v = _votes(rows)
    if v >= 4:
        return [-1]
    return []

def _votes(rows):
    return sum(1 for r in rows if r > 0)
'''
SRC_GENUINE = '''
def generate_decisions(rows, params):
    z = _meanrev(rows)
    if z < 0:
        return [1]
    return []

def _meanrev(rows):
    return rows[-1] - sum(rows) / len(rows) if rows else 0
'''


def _protocol(symbols, looks=8) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "ac1-e2e",
            "cost_model": {"taker_bps": 5, "maker_bps": 1, "slippage_bps": 1, "stress_multiplier": 2.0},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-03-31"},
                "selection": {"start": "2024-05-01", "end": "2024-10-31"},
                "lockbox": {"start": "2024-12-01", "end": "2024-12-31"},
                "symbols": list(symbols),
            },
            "folds": {"scheme": "rolling", "n_folds": 3, "train_periods": 720,
                      "test_periods": 240, "purge_periods": 24, "embargo_periods": 24},
            "objective": {"gates": {"min_trades": 30, "max_concentration": 0.6, "min_effective_breadth": 2.0}},
            "budget": {"max_selection_looks": looks},
            "stability": {"rho": 0.6, "min_positive_fraction": 0.8, "step_multipliers": [1, 2],
                          "param_steps": {"base_position_pct": 0.02}},
            "annualization": {"periods_per_year": PPY},
        }
    )


# --------------------------------------------------------------------------- #
# The diagnosed campaign: ADA carries ~all PnL; pure market+funding beta; cranked sizing.
# --------------------------------------------------------------------------- #


def _diagnosed_fold(seed, n=240):
    """ADA dominates; XRP/AVAX co-move at tiny weight; PnL is pure market+funding beta (no alpha)."""
    rng = np.random.default_rng(seed)
    market = 0.012 * rng.standard_normal(n) + 0.004
    funding = 0.006 * rng.standard_normal(n) + 0.003
    ada = 1.3 * market + 1.0 * funding
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
    return fold, {"market": market, "funding_carry": funding}


class _DiagnosedGateway:
    """Fake gateway reproducing the diagnosed campaign on BOTH surfaces.

    quick_run: the Train slices show ADA carrying ~95% of the PnL (cheap-robust will bounce it);
    evaluate: pure market+funding beta with co-moving legs (RES infeasible: residual alpha ≈ 0,
    breadth ≈ 1). The TRUE market+funding panel is stashed so residual alpha is measured honestly.
    """

    def __init__(self):
        self._panels = {}
        self._seed = 0

    def quick_run(self, experiment, protocol, window):  # noqa: ARG002
        return QuickRunResult(
            valid=True, causal_ok=True, in_sample_metric=0.5, trade_count=300,
            slices={"by_symbol": {"ADA-PERP": 0.95, "XRP-PERP": 0.025, "AVAX-PERP": 0.025}},
            failure_stage=None,
        )

    def evaluate(self, experiment, protocol, window):  # noqa: ARG002
        self._seed += 1
        fold, panel = _diagnosed_fold(self._seed)
        self._panels[id(fold)] = panel
        return FoldEvalResult(
            succeeded=True, causal_ok=True, returns=fold, sharpe=2.0, sortino=2.0,
            calmar=1.0, max_drawdown=-0.10, trade_count=300, worst_period_return=-0.04,
            provenance={"snapshot": "synthetic"}, failure_stage=None,
        )

    def panel_for(self, window, returns):
        return self._panels.get(id(returns), {})


# --------------------------------------------------------------------------- #
# The genuine control: diversified INDEPENDENT idiosyncratic alpha sharing a market beta.
# --------------------------------------------------------------------------- #


def _genuine_fold(seed, symbols, n=240):
    market = 0.012 * np.random.default_rng(seed).standard_normal(n) + 0.004
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate(symbols):
        rng = np.random.default_rng(seed * 10 + i)
        leg = 0.0015 + 0.9 * market + 0.003 * rng.standard_normal(n)
        by_symbol[sym] = make_returns(leg, periods_per_year=PPY)
        port += leg / len(symbols)
    fold = FoldReturns(
        timestamps=make_returns(port, periods_per_year=PPY).timestamps,
        values=port, periods_per_year=PPY, by_symbol=by_symbol,
    )
    # COVERING panel (market + funding_carry, the Protocol-required columns). funding_carry is a
    # benign NON-DEGENERATE column (usable for neutralization — beta removable — yet negligible
    # PnL), as the real provider supplies a genuinely-varying funding rate. Alpha survives.
    return fold, {"market": market, "funding_carry": benign_funding_carry(n, seed=seed + 5000)}


class _GenuineGateway:
    def __init__(self, symbols):
        self._symbols = symbols
        self._panels = {}
        self._seed = 0

    def quick_run(self, experiment, protocol, window):  # noqa: ARG002
        n = len(self._symbols)
        share = round(1.0 / n, 4)
        return QuickRunResult(
            valid=True, causal_ok=True, in_sample_metric=1.0, trade_count=150,
            slices={"by_symbol": {s: share for s in self._symbols}}, failure_stage=None,
        )

    def evaluate(self, experiment, protocol, window):  # noqa: ARG002
        self._seed += 1
        fold, panel = _genuine_fold(self._seed, self._symbols)
        self._panels[id(fold)] = panel
        return FoldEvalResult(
            succeeded=True, causal_ok=True, returns=fold, sharpe=1.5, sortino=1.5,
            calmar=1.0, max_drawdown=-0.08, trade_count=300, worst_period_return=-0.03,
            provenance={"snapshot": "synthetic"}, failure_stage=None,
        )

    def panel_for(self, window, returns):
        return self._panels.get(id(returns), {})


# --------------------------------------------------------------------------- #
# AC-1: the diagnosed campaign does NOT graduate ANYWHERE in the loop.
# --------------------------------------------------------------------------- #


def test_ac1_diagnosed_campaign_is_routed_at_the_escalation_gate_and_spends_no_look():
    """Stage 1 stop: the escalation gate bounces the ADA-only 'basket' (cheap-robust) — no look."""
    symbols = ("ADA-PERP", "XRP-PERP", "AVAX-PERP")
    proto = _protocol(symbols)
    ledger = TrialLedger()
    budget = BudgetManager(proto.budget.max_selection_looks, ledger)
    gw = _DiagnosedGateway()
    cli = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                     factor_panel_provider=gw.panel_for, strategy_source_loader=lambda p: SRC_DIAGNOSED)

    exp = Experiment(strategy_path="strategy.py", params={"base_position_pct": 0.20}, symbols=symbols)
    out = cli.evaluate(exp, desc="diagnosed | falsifier: x", trial_id="d1", created_at="2024-06-01T00:00:00Z")

    assert isinstance(out, EvaluateRefused)
    assert out.kind == "routed_to_train"
    assert out.reason.startswith("cheap_robust:")
    # NO look spent, NO row — the diagnosed campaign never reaches Selection.
    assert budget.status().charged == 0
    assert len(ledger.rows()) == 0


def test_ac1_diagnosed_campaign_is_infeasible_even_if_it_reached_selection():
    """Stage 2 backstop: even bypassing the gate, the RES is infeasible (residual alpha ≈ 0,
    breadth ≈ 1) so it can never be feasible/top-K/graduate."""
    from harness.orchestrator import run_walk_forward_res
    from harness.objective.res import GateThresholds

    symbols = ("ADA-PERP", "XRP-PERP", "AVAX-PERP")
    proto = _protocol(symbols)
    gw = _DiagnosedGateway()
    exp = Experiment(strategy_path="strategy.py", params={"base_position_pct": 0.20}, symbols=symbols)
    out = run_walk_forward_res(
        exp, proto, gw, gw.panel_for,
        thresholds=GateThresholds(min_trades=30, max_concentration=0.6, min_effective_breadth=2.0),
    )
    assert out.res.feasible is False
    assert out.res.rank_sharpe is None
    assert not out.res.gate_results["effective_breadth"].passed

    # ...and a graduation over an (empty/infeasible) ledger yields NO graduates.
    ledger = TrialLedger()  # the diagnosed look never logged a feasible row
    audit = run_graduation_audit(ledger.rows(), proto.content_hash)
    decision = select_graduates(ledger.rows(), audit, top_k=3)
    assert decision.graduates == ()


def test_ac1_diagnosed_thin_lockbox_returns_insufficient_evidence_never_confirmed():
    """Stage 4 backstop: a thin diagnosed Lockbox cannot power even a claimed edge ⇒
    insufficient_evidence, never confirmed (AC-5 inside the AC-1 story)."""
    symbols = ("ADA-PERP", "XRP-PERP", "AVAX-PERP")
    proto = _protocol(symbols)
    gw = _DiagnosedGateway()
    # Diagnosed profile: short, autocorrelated, thin Lockbox ⇒ a large MDE.
    rp = _diagnosed_fold(1)[0].values
    profile = profile_asset(rp, lockbox_periods=120, periods_per_year=PPY)
    exp = Experiment(strategy_path="strategy.py", params={"base_position_pct": 0.20}, symbols=symbols)
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=0.5, gateway=gw, book=LockboxBook(),
        trial_id="d1", spent_at="2024-12-15T00:00:00Z",
    )
    assert verdict.verdict == "insufficient_evidence"


# --------------------------------------------------------------------------- #
# Positive control: a genuine simple edge flows through to graduate + confirmed.
# --------------------------------------------------------------------------- #


def test_ac1_positive_control_genuine_edge_logs_graduates_and_confirms():
    symbols = ("AAA-PERP", "BBB-PERP", "CCC-PERP")
    proto = _protocol(symbols)
    ledger = TrialLedger()
    budget = BudgetManager(proto.budget.max_selection_looks, ledger)
    gw = _GenuineGateway(symbols)
    cli = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                     factor_panel_provider=gw.panel_for, strategy_source_loader=lambda p: SRC_GENUINE)
    exp = Experiment(strategy_path="strategy.py", params={"base_position_pct": 0.05}, symbols=symbols)

    # run (FREE) — positive band, structurally new.
    band = cli.run(exp, desc="genuine diversified alpha")
    assert band.plausibility_band == "positive" and band.is_new_family

    # evaluate — passes the gate + budget; logs a feasible bet.
    logged = cli.evaluate(exp, desc="genuine | falsifier: x", trial_id="g1", created_at="2024-06-01T00:00:00Z")
    assert isinstance(logged, EvaluateLogged)
    assert logged.row.res.feasible is True
    assert logged.row.res.rank_sharpe is not None and logged.row.res.rank_sharpe > 0

    # graduate — the single feasible PSR-passed row survives the audit and is top-K.
    rows = ledger.rows()
    audit = run_graduation_audit(rows, proto.content_hash)
    decision = select_graduates(rows, audit, top_k=3)
    assert "g1" in decision.graduates

    # lockbox — a POWERED profile (long history, thick block) confirms the genuine edge.
    rp = np.concatenate([_genuine_fold(s, symbols)[0].values for s in range(1, 40)])
    profile = profile_asset(rp, lockbox_periods=4000, periods_per_year=PPY)
    claimed = logged.row.res.rank_sharpe
    # Only assert confirmability is possible (powered): MDE ≤ claimed edge ⇒ not auto-insufficient.
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=float(claimed), gateway=gw, book=LockboxBook(),
        trial_id="g1", spent_at="2024-12-15T00:00:00Z", factor_panel_provider=gw.panel_for,
    )
    assert verdict.verdict in ("confirmed", "rejected")  # powered ⇒ a real verdict, not insufficient
    assert verdict.verdict != "insufficient_evidence"
