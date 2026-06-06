"""The agent + admin CLI (§8) — mechanical gate + budget enforcement on ``evaluate``.

status / run / evaluate produce correct outputs; the harness REFUSES an ``evaluate`` that fails
the escalation gate or exceeds the budget (mechanical, FR-D1/E5). ``evaluate`` is a logged bet,
never a hill-climb step (FR-D3). All via the Fake gateway — no live data. The boundary (cli.py
does not import quant_strategies) is asserted in test_foundation_seam-style fashion here too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

import harness.cli as cli_mod
from harness.budget import BudgetManager
from harness.cli import EvaluateLogged, EvaluateRefused, HarnessCLI
from harness.foundation import FoldEvalResult, FoldReturns, QuickRunResult
from harness.ledger import TrialLedger
from harness.protocol import Experiment, Protocol
from harness.testing import FakeFoundationGateway, benign_funding_carry, make_returns

PPY = 8760.0

# A genuine diversified edge source vs a structurally different one (distinct families).
SRC_EDGE = '''
def generate_decisions(rows, params):
    s = _alpha(rows)
    if s > 0:
        return [1]
    return []

def _alpha(rows):
    return sum(rows)
'''
SRC_OTHER = '''
def generate_decisions(rows, params):
    t = _carry(rows)
    if t < 0:
        return [-1]
    return []

def _carry(rows):
    return rows[0] if rows else 0
'''


def _protocol(symbols=("AAA", "BBB", "CCC"), looks=8) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "cli-test",
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


def _experiment(symbols=("AAA", "BBB", "CCC")) -> Experiment:
    return Experiment(strategy_path="strategy.py", params={"threshold": 1.0}, symbols=tuple(symbols))


def _balanced_slices():
    return {"by_symbol": {"AAA": 0.34, "BBB": 0.33, "CCC": 0.33}}


def _genuine_fold(seed, symbols, n=240):
    """Diversified independent idiosyncratic alpha sharing a (neutralized) market beta."""
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
    # COVERING panel (market + funding_carry, the Protocol-required columns). funding_carry is a
    # benign NON-DEGENERATE column (usable for neutralization; negligible PnL), as the real
    # provider supplies a genuinely-varying funding rate. The genuine alpha survives.
    return fold, {"market": market, "funding_carry": benign_funding_carry(n, seed=seed + 5000)}


class _EdgeGateway:
    """Fake gateway: a plateau Train quick run + genuine diversified evaluate folds + panel.

    Drives BOTH the escalation gate (quick_run: valid/alive/positive/plateau/cheap-robust) and
    the walk-forward RES (evaluate: a feasible diversified edge), with the TRUE market panel so
    residual alpha survives.
    """

    def __init__(self, symbols):
        self._symbols = symbols
        self._panels = {}
        self._seed = 0

    def quick_run(self, experiment, protocol, window):  # noqa: ARG002
        return QuickRunResult(
            valid=True, causal_ok=True, in_sample_metric=1.0, trade_count=120,
            slices=_balanced_slices(), failure_stage=None,
        )

    def evaluate(self, experiment, protocol, window):  # noqa: ARG002
        self._seed += 1
        fold, panel = _genuine_fold(self._seed, self._symbols)
        self._panels[id(fold)] = panel
        return FoldEvalResult(
            succeeded=True, causal_ok=True, returns=fold, sharpe=1.5, sortino=1.5,
            calmar=1.0, max_drawdown=-0.1, trade_count=300, worst_period_return=-0.03,
            provenance={"snapshot": "synthetic", "foundation": "vfake"}, failure_stage=None,
        )

    def panel_for(self, window, returns):
        return self._panels.get(id(returns), {})


def _cli(symbols=("AAA", "BBB", "CCC"), looks=8, swing=5):
    proto = _protocol(symbols, looks=looks)
    ledger = TrialLedger()
    budget = BudgetManager(proto.budget.max_selection_looks, ledger)
    gw = _EdgeGateway(symbols)
    cli = HarnessCLI(
        gateway=gw, protocol=proto, ledger=ledger, budget=budget,
        factor_panel_provider=gw.panel_for, swing_big_every=swing,
        strategy_source_loader=lambda path: SRC_EDGE,
    )
    return cli, ledger, budget, gw


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #


def test_status_reports_quota_not_countdown_on_empty_ledger():
    cli, ledger, budget, gw = _cli(looks=8)
    s = cli.status()
    assert s["best_candidate"] is None
    assert s["n_logged"] == 0
    assert s["budget"] == {"cap": 8, "looks_charged": 0, "looks_remaining": 8, "spent": False}
    assert s["session"] == "active"
    # No countdown vocabulary leaks into the agent-facing surface.
    assert "remaining_attempts" not in s and "max_attempts" not in s


# --------------------------------------------------------------------------- #
# run — FREE, never a look
# --------------------------------------------------------------------------- #


def test_run_is_free_and_writes_no_ledger_row():
    cli, ledger, budget, gw = _cli()
    out = cli.run(_experiment(), desc="thesis: diversified alpha")
    assert out.valid and out.causal_ok
    assert out.plausibility_band == "positive"
    assert out.is_new_family is True
    # FREE: no look charged, no row written.
    assert budget.status().charged == 0
    assert len(ledger.rows()) == 0


# --------------------------------------------------------------------------- #
# evaluate — the MECHANICAL gate + budget, then the logged bet
# --------------------------------------------------------------------------- #


def test_evaluate_logs_a_bet_when_gate_and_budget_pass():
    cli, ledger, budget, gw = _cli()
    out = cli.evaluate(_experiment(), desc="thesis | falsifier: x", trial_id="t1", created_at="2024-06-01T00:00:00Z")
    assert isinstance(out, EvaluateLogged)
    assert out.row.res.feasible is True
    assert out.row.res.rank_sharpe is not None and out.row.res.rank_sharpe > 0
    # Exactly one look charged, exactly one row logged (the bet).
    assert budget.status().charged == 1
    assert len(ledger.rows()) == 1
    assert out.looks_remaining == 7


def test_evaluate_refuses_and_spends_nothing_when_gate_routes_to_train():
    """A dead candidate (too few trades) is routed to Train — no look, no row (FR-D1)."""
    proto = _protocol()
    ledger = TrialLedger()
    budget = BudgetManager(8, ledger)

    class DeadGW(_EdgeGateway):
        def quick_run(self, e, p, w):  # noqa: ARG002
            return QuickRunResult(valid=True, causal_ok=True, in_sample_metric=1.0,
                                  trade_count=3, slices=_balanced_slices(), failure_stage=None)

    gw = DeadGW(("AAA", "BBB", "CCC"))
    cli = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                     factor_panel_provider=gw.panel_for, strategy_source_loader=lambda path: SRC_EDGE)
    out = cli.evaluate(_experiment(), desc="t", trial_id="t1", created_at="2024-06-01T00:00:00Z")
    assert isinstance(out, EvaluateRefused)
    assert out.kind == "routed_to_train"
    assert out.reason.startswith("alive:")
    # MECHANICAL: nothing charged, nothing logged.
    assert budget.status().charged == 0
    assert len(ledger.rows()) == 0


def test_evaluate_refuses_when_budget_spent_even_if_gate_would_pass():
    """A passed gate does NOT entitle a look — a spent budget refuses with the quota (FR-E5)."""
    cli, ledger, budget, gw = _cli(looks=1)
    # Spend the single look on a NEW family.
    first = cli.evaluate(_experiment(), desc="first", trial_id="t1", created_at="2024-06-01T00:00:00Z")
    assert isinstance(first, EvaluateLogged)
    assert budget.status().spent is True

    # A genuinely NEW family idea now — gate would pass, but the budget is spent.
    cli2 = HarnessCLI(gateway=gw, protocol=cli._protocol, ledger=ledger, budget=budget,
                      factor_panel_provider=gw.panel_for, strategy_source_loader=lambda path: SRC_OTHER)
    out = cli2.evaluate(_experiment(), desc="second new family", trial_id="t2", created_at="2024-06-02T00:00:00Z")
    assert isinstance(out, EvaluateRefused)
    assert out.kind == "budget_spent"
    # No second row; still exactly one logged.
    assert len(ledger.rows()) == 1


def test_evaluate_refuses_old_family_at_the_swing_big_cadence():
    """At the swing-big cadence (M ideas since a new family), an old-family idea is routed to Train
    even with budget remaining — until a structurally new family is proposed (FR-A4)."""
    proto = _protocol(looks=8)
    ledger = TrialLedger()
    budget = BudgetManager(8, ledger)
    gw = _EdgeGateway(("AAA", "BBB", "CCC"))
    # Log one bet of family SRC_EDGE, then build a CLI whose session cadence is AT the limit.
    cli0 = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                      factor_panel_provider=gw.panel_for, strategy_source_loader=lambda p: SRC_EDGE,
                      swing_big_every=5)
    cli0.evaluate(_experiment(), desc="first", trial_id="t1", created_at="2024-06-01T00:00:00Z")

    cli = HarnessCLI(gateway=gw, protocol=proto, ledger=ledger, budget=budget,
                     factor_panel_provider=gw.panel_for, strategy_source_loader=lambda p: SRC_EDGE,
                     swing_big_every=5, ideas_since_new_family=5)
    out = cli.evaluate(_experiment(), desc="same family at cadence", trial_id="t2", created_at="2024-06-02T00:00:00Z")
    assert isinstance(out, EvaluateRefused)
    assert out.kind == "routed_to_train"
    # The swing-big condition is the (or a) reason; no second look spent.
    assert out.escalation is not None
    assert any(c.name == "swing_big" and not c.passed for c in out.escalation.conditions)
    assert budget.status().charged == 1


def test_status_surfaces_best_candidate_after_a_logged_bet():
    cli, ledger, budget, gw = _cli()
    cli.evaluate(_experiment(), desc="t | falsifier: x", trial_id="t1", created_at="2024-06-01T00:00:00Z")
    s = cli.status()
    assert s["best_candidate"] is not None
    assert s["best_candidate"]["trial_id"] == "t1"
    assert s["n_logged"] == 1
    assert s["budget"]["looks_remaining"] == 7


# --------------------------------------------------------------------------- #
# Boundary: cli.py does not import quant_strategies (the seam stays clean).
# --------------------------------------------------------------------------- #


def test_cli_module_does_not_import_quant_strategies():
    """The composition root must NOT import the engine at module scope (only foundation_real does).

    It constructs the RealFoundationGateway lazily inside ``_build_real_gateway``. AST-parse the
    cli.py source: no top-level ``import quant_strategies`` / ``from quant_strategies …``.
    """
    src = Path(cli_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name.split(".")[0] != "quant_strategies" for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "quant_strategies"


def test_graduate_decision_emits_a_verdict_over_the_ledger_and_never_promotes():
    """graduate: audit + top-K over the logged trials; the harness EMITS, never promotes (FR-F3)."""
    cli, ledger, budget, gw = _cli()
    cli.evaluate(_experiment(), desc="g | falsifier: x", trial_id="g1", created_at="2024-06-01T00:00:00Z")
    decision = cli_mod.graduate_decision(ledger, cli._protocol, top_k=3)
    # A GraduationDecision is emitted; there is NO promotion side effect (promoted is always None).
    assert hasattr(decision, "graduates")
    assert decision.promoted is None


def test_profile_campaign_emits_sufficiency_verdict():
    """profile: Asset Profiler + data-sufficiency gate (admin; FR-G/AC-5)."""
    proto = _protocol()
    # A thin Lockbox (few periods) ⇒ a large MDE ⇒ a small claimed edge is insufficient_evidence.
    rp = np.concatenate([0.001 + 0.01 * np.random.default_rng(0).standard_normal(2000)])
    profile, verdict = cli_mod.profile_campaign(
        rp, proto, claimed_edge=0.05, lockbox_periods=200,
    )
    assert verdict.verdict in ("admissible", "insufficient_evidence")
    # The MDE is the power bar; a tiny claimed edge against a thin block is insufficient.
    assert profile.lockbox_mde > 0
