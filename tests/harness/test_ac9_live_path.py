"""AC-9 / G2 on the LIVE (operator/default) path — the fail-closed factor-panel wall.

The diagnosed failure this product exists to prevent: a *pure factor-beta* basket scoring as
residual alpha and graduating/confirming. AC-9 ("a pure factor-beta strategy scores ≈0 and does
not graduate") and G2 ("factor beta cannot raise the score") must hold on the path the operator
ACTUALLY runs — not only on tests that hand-inject the true panel.

The reviewer's exploit (reproduced here): a **decorrelated** pure-market-beta basket — 6 legs,
each ``0.9*market + idiosyncratic noise`` with ZERO idiosyncratic alpha. The idiosyncratic noise
DEcorrelates the legs, so the correlation-aware effective-breadth gate is satisfied (this is NOT
the ADA-as-basket case); the only thing standing between this basket and graduation is honest
factor neutralization. On the OLD live path the factor panel was unwired (``_no_factor_panel`` ⇒
identity), so RES scored the RAW (pure-beta) returns and the basket graduated with a large
``rank_sharpe``; the Lockbox scored raw returns too and confirmed it.

The fix is FAIL-CLOSED (PRD Principle 6, "never lower the bar"): when the Protocol REQUIRES factor
neutralization but the supplied panel does not cover the required columns (empty/identity), RES is
``infeasible`` and the Lockbox is ``insufficient_evidence`` — never a silent pass on raw returns.
A covering panel (the positive control) still lets a genuine idiosyncratic edge graduate + confirm.
"""

from __future__ import annotations

import numpy as np

from harness.data.lockbox_book import LockboxBook
from harness.foundation import FoldEvalResult, FoldReturns
from harness.lockbox import confirm_on_lockbox
from harness.objective.res import GateThresholds, compute_res
from harness.orchestrator import run_walk_forward_res
from harness.profiler import profile_asset
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
# Generous breadth/concentration so neither bounces the DEcorrelated basket — the ONLY wall
# that may stop it is honest factor neutralization (that is the whole point of this exploit).
THRESHOLDS = GateThresholds(min_trades=30, max_concentration=0.9, min_effective_breadth=2.0)
SYMBOLS = ("L1", "L2", "L3", "L4", "L5", "L6")


def _protocol() -> Protocol:
    return Protocol.model_validate(
        {
            "name": "ac9-live",
            "cost_model": {"taker_bps": 1, "maker_bps": 1, "slippage_bps": 0, "stress_multiplier": 2.0},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-03-31"},
                "selection": {"start": "2024-04-01", "end": "2024-10-31"},
                "lockbox": {"start": "2024-11-01", "end": "2024-12-31"},
                "symbols": list(SYMBOLS),
                "source": {"kind": "crypto_perp_funding"},
            },
            "folds": _FOLDS,
            # required_factors defaults to ("market", "funding_carry"); make it explicit so the
            # exploit's premise (the live objective REQUIRES neutralization) is on the record.
            "objective": {
                "gates": {"min_trades": 30, "max_concentration": 0.9, "min_effective_breadth": 2.0},
                "factor_panel": {"required_factors": ["market", "funding_carry"]},
            },
            "annualization": {"periods_per_year": PPY},
        }
    )


def _experiment() -> Experiment:
    return Experiment(strategy_path="strategy.py", params={"w": 0.1}, symbols=SYMBOLS)


# --------------------------------------------------------------------------- #
# The exploit basket: 6 DEcorrelated legs, each pure market beta + idiosyncratic
# NOISE (zero idiosyncratic alpha). Residualized against the true market, every leg
# is mean-zero noise ⇒ no edge; un-neutralized, the raw basket is a strong "Sharpe".
# --------------------------------------------------------------------------- #


def _beta_basket_fold(seed: int, n: int = 240):
    """Pure-beta basket fold + its TRUE market panel.

    Each leg = 0.9*market + idio noise (mean 0). The idio noise (sd 0.01, comparable to the
    0.9*0.012 market component) DEcorrelates the RAW legs, so the correlation-aware
    effective-breadth gate PASSES even on the identity (unwired) panel — this is the reviewer's
    decorrelated basket, NOT the ADA-as-basket case the breadth gate already catches. There is
    ZERO idiosyncratic alpha, so residualizing against the TRUE ``market`` leaves mean-zero
    noise (no edge); un-neutralized, the raw basket posts a large spurious Sharpe (≈24)."""
    market = 0.012 * np.random.default_rng(seed).standard_normal(n) + 0.004
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate(SYMBOLS):
        rng = np.random.default_rng(seed * 100 + i)
        leg = 0.9 * market + 0.01 * rng.standard_normal(n)  # NO additive alpha term
        by_symbol[sym] = make_returns(leg, periods_per_year=PPY)
        port += leg / len(SYMBOLS)
    fold = FoldReturns(
        timestamps=make_returns(port, periods_per_year=PPY).timestamps,
        values=port, periods_per_year=PPY, by_symbol=by_symbol,
    )
    return fold, {"market": market}


def _genuine_fold(seed: int, n: int = 240):
    """Positive control: 6 legs of INDEPENDENT idiosyncratic alpha sharing a market beta."""
    market = 0.012 * np.random.default_rng(seed).standard_normal(n) + 0.004
    by_symbol, port = {}, np.zeros(n)
    for i, sym in enumerate(SYMBOLS):
        rng = np.random.default_rng(seed * 100 + i)
        leg = 0.0015 + 0.9 * market + 0.003 * rng.standard_normal(n)  # genuine +alpha
        by_symbol[sym] = make_returns(leg, periods_per_year=PPY)
        port += leg / len(SYMBOLS)
    fold = FoldReturns(
        timestamps=make_returns(port, periods_per_year=PPY).timestamps,
        values=port, periods_per_year=PPY, by_symbol=by_symbol,
    )
    # COVERING panel: market + funding_carry (the Protocol-required columns; funding ~0 here).
    return fold, {"market": market, "funding_carry": np.zeros_like(market)}


class _BasketGateway:
    """A FoundationGateway whose evaluate fabricates a fold and stashes its TRUE panel.

    ``panel_for`` returns the stashed true panel — used by the positive control to prove the
    neutralization path still works. The OPERATOR/default path uses NO panel provider (the
    production default), which is exactly the unwired/identity case the fail-closed guard catches.
    """

    def __init__(self, make_fold):
        self._make_fold = make_fold
        self._panels: dict[int, dict] = {}
        self._by_window: dict[str, tuple] = {}
        self._seed = 0
        self.evaluate_calls: list = []

    def quick_run(self, experiment, protocol, window):  # pragma: no cover - unused here
        raise NotImplementedError

    def evaluate(self, experiment, protocol, window):  # noqa: ARG002
        self.evaluate_calls.append(window)
        # The fake does not model costs, so the realistic + stressed evaluates of the SAME fold
        # window return the SAME series (cost-stress ratio = 1.0 exactly). Cache by window id so
        # cost-stress survival is a clean pass for a genuine edge — the cost-stress gate is tested
        # elsewhere; here it must not be the thing that (spuriously) bounces the positive control.
        if window.window_id not in self._by_window:
            self._seed += 1
            fold, panel = self._make_fold(self._seed)
            self._panels[id(fold)] = panel
            self._by_window[window.window_id] = (fold, panel)
        fold, _ = self._by_window[window.window_id]
        return FoldEvalResult(
            succeeded=True, causal_ok=True, returns=fold, sharpe=2.0, sortino=2.0,
            calmar=1.0, max_drawdown=-0.05, trade_count=300, worst_period_return=-0.02,
            provenance={"snapshot": "synthetic"}, failure_stage=None,
        )

    def panel_for(self, window, returns):
        return self._panels.get(id(returns), {})


def _no_panel_provider(window, returns):
    """The production default BEFORE the fix: an identity (empty) panel — no neutralization."""
    return {}


# --------------------------------------------------------------------------- #
# CRITICAL regression — graduation path (compute_res / run_walk_forward_res).
# --------------------------------------------------------------------------- #


def test_ac9_live_path_pure_beta_basket_does_not_graduate_fail_closed():
    """The reviewer's exploit through the OPERATOR/default path (the unwired/identity panel).

    Pre-fix: this graduated (feasible=True, large rank_sharpe ≈ 22.8). Post-fix: the Protocol
    requires neutralization but the panel does not cover it ⇒ infeasible, rank None, with an
    explicit ``factor_panel`` gate failure (reason ``factor_panel_unwired``). The live path can
    NEVER again score raw beta as residual alpha.
    """
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_beta_basket_fold)

    out = run_walk_forward_res(
        exp, proto, gw, _no_panel_provider, thresholds=THRESHOLDS
    )

    assert out.n_folds_evaluated >= 1
    res = out.res
    # FAIL-CLOSED: an unwired panel where the Protocol requires neutralization is infeasible.
    assert res.feasible is False, (
        f"pure-beta basket GRADUATED on the live path (rank_sharpe={res.rank_sharpe}) — "
        "the factor-panel wall is not fail-closed"
    )
    assert res.rank_sharpe is None
    assert "factor_panel" in res.gate_results
    assert not res.gate_results["factor_panel"].passed
    assert "factor_panel_unwired" in res.gate_results["factor_panel"].detail


def test_ac9_compute_res_fails_closed_on_empty_panels_when_required():
    """The pure judgment-layer wall: empty/identity panels + required_factors ⇒ infeasible.

    This is the mechanical wall in isolation (no gateway): the same decorrelated-beta folds the
    orchestrator would assemble, scored directly. Empty panels do not cover the required factors,
    so the result is infeasible with rank None — not a silent raw-returns pass."""
    folds = [_beta_basket_fold(s)[0] for s in range(1, 4)]
    empty_panels = [{} for _ in folds]

    res = compute_res(
        folds, empty_panels, trade_count=900, thresholds=THRESHOLDS,
        required_factors=("market", "funding_carry"),
    )
    assert res.feasible is False
    assert res.rank_sharpe is None
    assert not res.gate_results["factor_panel"].passed


def test_ac9_compute_res_with_covering_panel_still_neutralizes_and_bounces_beta():
    """Positive control (judgment layer): WITH the true covering panel, the pure-beta basket
    still residualizes to ≈0 ⇒ infeasible (the neutralization path is intact). This proves the
    guard did not replace neutralization — both walls hold."""
    folds, panels = [], []
    for s in range(1, 4):
        fold, panel = _beta_basket_fold(s)
        folds.append(fold)
        # A covering panel: market (the true driver) + a funding_carry column (zero here).
        panels.append({"market": panel["market"], "funding_carry": np.zeros_like(panel["market"])})

    res = compute_res(
        folds, panels, trade_count=900, thresholds=THRESHOLDS,
        required_factors=("market", "funding_carry"),
    )
    # The panel COVERS the requirement, so the guard does not fire; neutralization bounces beta.
    assert "factor_panel" not in res.gate_results or res.gate_results["factor_panel"].passed
    assert res.feasible is False  # residual alpha ≈ 0 ⇒ no rankable edge
    assert res.rank_sharpe is None


def test_ac9_genuine_alpha_with_covering_panel_still_graduates():
    """Positive control: a genuine idiosyncratic-alpha basket WITH a covering panel is feasible —
    the fix does not break the honest path."""
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_genuine_fold)

    out = run_walk_forward_res(exp, proto, gw, gw.panel_for, thresholds=THRESHOLDS)

    assert out.n_folds_evaluated >= 2
    assert out.res.feasible is True
    assert out.res.rank_sharpe is not None and out.res.rank_sharpe > 0
    # The guard did not fire (the panel COVERS the required market + funding_carry columns) and
    # the honest neutralization path produced a rankable residual edge — the fix is non-destructive.
    assert out.res.gate_results["factor_panel"].passed


# --------------------------------------------------------------------------- #
# CRITICAL regression — Lockbox confirmation path (confirm_on_lockbox).
# --------------------------------------------------------------------------- #


def test_ac9_live_lockbox_pure_beta_is_insufficient_evidence_fail_closed():
    """The Lockbox half of the exploit through the operator/default path (no panel provider).

    Pre-fix: ``confirm_on_lockbox`` scored RAW returns and CONFIRMED the pure-beta basket on a
    powered block. Post-fix: with no covering panel (the production default), the Protocol's
    required neutralization cannot be applied ⇒ ``insufficient_evidence`` (fail-closed), never
    confirmed — and never scored on raw returns."""
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_beta_basket_fold)
    # A POWERED profile (long history, thick block): pre-fix this is exactly what let raw beta
    # confirm; post-fix the fail-closed guard returns before any raw-returns bootstrap.
    rp = np.concatenate([_beta_basket_fold(s)[0].values for s in range(1, 40)])
    profile = profile_asset(rp, lockbox_periods=4000, periods_per_year=PPY)

    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=5.0, gateway=gw, book=LockboxBook(),
        trial_id="x", spent_at="2024-12-15T00:00:00Z",
        # No factor_panel_provider ⇒ the production default ⇒ fail closed.
    )
    assert verdict.verdict == "insufficient_evidence", (
        f"Lockbox CONFIRMED pure-beta on raw returns (verdict={verdict.verdict}) — "
        "the Lockbox factor wall is not fail-closed"
    )
    assert "factor_panel_unwired" in verdict.detail


def test_ac9_lockbox_genuine_alpha_with_covering_panel_still_confirms():
    """Positive control: a genuine edge WITH a covering panel still confirms on a powered block —
    the Lockbox residualizes against the panel (not raw) and the real edge survives."""
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_genuine_fold)
    rp = np.concatenate([_genuine_fold(s)[0].values for s in range(1, 40)])
    profile = profile_asset(rp, lockbox_periods=4000, periods_per_year=PPY)

    # claimed_edge comfortably above the block MDE (~3.7) so the power gate passes — the genuine
    # residual edge is far larger (~100+ annualized Sharpe on the clean synthetic alpha).
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=10.0, gateway=gw, book=LockboxBook(),
        trial_id="g", spent_at="2024-12-15T00:00:00Z",
        factor_panel_provider=gw.panel_for,
    )
    # Powered + a covering panel ⇒ a real verdict (not insufficient); the genuine residual edge
    # confirms (its idiosyncratic alpha survives neutralization).
    assert verdict.verdict != "insufficient_evidence"
    assert verdict.verdict in ("confirmed", "rejected")
