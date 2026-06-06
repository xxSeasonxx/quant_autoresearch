"""No hill-climb (FR-D3, AC-8) — at the CLI/loop level.

Re-``evaluate``-ing tweaks of ONE idea spends budget each time and there is no "keep if the
score rose" path: every ``evaluate`` is a LOGGED bet (a new ledger row), never a conditional
keep/discard step in an improvement loop. The budget (P3) makes this mechanically true; this
asserts it at the CLI surface — the agent cannot raise graduation odds by re-evaluating tweaks
beyond the budget.
"""

from __future__ import annotations

import numpy as np

from harness.budget import BudgetManager
from harness.cli import EvaluateLogged, EvaluateRefused, HarnessCLI
from harness.foundation import FoldEvalResult, FoldReturns, QuickRunResult
from harness.ledger import TrialLedger
from harness.protocol import Experiment, Protocol
from harness.testing import make_returns

PPY = 8760.0

# One signal family; param tweaks of it all collapse to this family (FR-E4).
SRC = '''
def generate_decisions(rows, params):
    s = _alpha(rows)
    if s > 0:
        return [1]
    return []

def _alpha(rows):
    return sum(rows)
'''


def _protocol(symbols=("AAA", "BBB", "CCC"), looks=3) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "no-hill-climb",
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
                          "param_steps": {"threshold": 0.1}},
            "annualization": {"periods_per_year": PPY},
        }
    )


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
    return fold, {"market": market}


class _Gateway:
    def __init__(self, symbols):
        self._symbols = symbols
        self._panels = {}
        self._seed = 0

    def quick_run(self, e, p, w):  # noqa: ARG002
        n = len(self._symbols)
        share = round(1.0 / n, 4)
        return QuickRunResult(valid=True, causal_ok=True, in_sample_metric=1.0, trade_count=120,
                              slices={"by_symbol": {s: share for s in self._symbols}}, failure_stage=None)

    def evaluate(self, e, p, w):  # noqa: ARG002
        self._seed += 1
        fold, panel = _genuine_fold(self._seed, self._symbols)
        self._panels[id(fold)] = panel
        return FoldEvalResult(succeeded=True, causal_ok=True, returns=fold, sharpe=1.5, sortino=1.5,
                              calmar=1.0, max_drawdown=-0.08, trade_count=300, worst_period_return=-0.03,
                              provenance={"snapshot": "s"}, failure_stage=None)

    def panel_for(self, w, r):
        return self._panels.get(id(r), {})


def test_re_evaluating_tweaks_of_one_idea_each_spend_budget_until_spent():
    """The FIRST look of a new family is admitted; subsequent SAME-family tweaks are routed to
    Train by the new-thesis gate (free). The budget is only spent by genuinely new families —
    and re-evaluating to push a number up is impossible (no same-family second look, and across
    families the budget caps total looks)."""
    symbols = ("AAA", "BBB", "CCC")
    proto = _protocol(symbols, looks=3)
    ledger = TrialLedger()
    budget = BudgetManager(proto.budget.max_selection_looks, ledger)
    gw = _Gateway(symbols)
    cli = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                     factor_panel_provider=gw.panel_for, strategy_source_loader=lambda path: SRC)

    exp = Experiment(strategy_path="strategy.py", params={"threshold": 1.0}, symbols=symbols)
    # First look of the family — admitted, logged.
    first = cli.evaluate(exp, desc="idea v1", trial_id="t1", created_at="2024-06-01T00:00:00Z")
    assert isinstance(first, EvaluateLogged)
    assert budget.status().charged == 1

    # A param TWEAK of the SAME idea (same family). It does NOT get a second look — the new-thesis
    # gate routes it to Train (free). There is no "keep if the score rose" path; the tweak cannot
    # spend budget to chase a higher number.
    tweaked = exp.model_copy(update={"params": {"threshold": 1.5}})
    second = cli.evaluate(tweaked, desc="idea v2 (tweak)", trial_id="t2", created_at="2024-06-02T00:00:00Z")
    assert isinstance(second, EvaluateRefused)
    assert second.kind == "routed_to_train"
    assert second.reason.startswith("new_thesis:")
    # Budget unchanged — the tweak spent NOTHING. Only one row logged.
    assert budget.status().charged == 1
    assert len(ledger.rows()) == 1


def test_each_evaluate_is_a_logged_bet_not_a_conditional_keep():
    """Every admitted ``evaluate`` writes a ledger row unconditionally — there is no decision that
    discards a logged bet because the score did not rise (FR-D3)."""
    symbols = ("AAA", "BBB", "CCC")
    proto = _protocol(symbols, looks=8)
    ledger = TrialLedger()
    budget = BudgetManager(proto.budget.max_selection_looks, ledger)

    # Distinct families so each is admitted; each must LOG a row regardless of its score.
    sources = {
        "fam1": SRC,
        "fam2": SRC.replace("> 0", "< 0").replace("[1]", "[-1]"),
        "fam3": SRC.replace("sum(rows)", "rows[0] if rows else 0"),
    }
    logged_rows = 0
    for i, (tag, src) in enumerate(sources.items(), start=1):
        gw = _Gateway(symbols)
        cli = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                         factor_panel_provider=gw.panel_for, strategy_source_loader=lambda path, s=src: s)
        exp = Experiment(strategy_path="strategy.py", params={"threshold": float(i)}, symbols=symbols)
        out = cli.evaluate(exp, desc=f"{tag} | falsifier: x", trial_id=f"t{i}", created_at=f"2024-06-0{i}T00:00:00Z")
        assert isinstance(out, EvaluateLogged)
        logged_rows += 1
        # Every admitted evaluate spent exactly one look and logged exactly one row — no keep/discard.
        assert budget.status().charged == logged_rows
        assert len(ledger.rows()) == logged_rows
