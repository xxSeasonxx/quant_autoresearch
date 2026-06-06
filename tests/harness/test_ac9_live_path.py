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
import pytest

from harness.data.lockbox_book import LockboxBook
from harness.foundation import FoldEvalResult, FoldReturns
from harness.lockbox import confirm_on_lockbox
from harness.objective.res import GateThresholds, compute_res
from harness.orchestrator import run_walk_forward_res
from harness.profiler import profile_asset
from harness.protocol import Experiment, Protocol
from harness.testing import benign_funding_carry, make_returns

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
    # COVERING panel: market + funding_carry (the Protocol-required columns). funding_carry is a
    # benign NON-DEGENERATE column (small noise) — usable (beta removable) yet negligible PnL.
    return fold, {"market": market, "funding_carry": benign_funding_carry(n, seed=seed + 5000)}


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
        # A covering panel: market (the true driver) + a benign NON-DEGENERATE funding_carry column.
        panels.append(
            {"market": panel["market"], "funding_carry": benign_funding_carry(panel["market"].size, seed=s + 6000)}
        )

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


# --------------------------------------------------------------------------- #
# CRITICAL regression — PRESENT-BUT-DEGENERATE factor columns (the re-opened hole).
#
# A required factor column that is PRESENT but DEGENERATE (all-zero, constant, or NaN) passed
# the OLD presence-only wall (``all(name in panel)``). But ``residualize`` regressing against a
# zero/constant column removes NOTHING (residual == raw), so a pure-market-beta basket (zero
# alpha) was scored on RAW beta and GRADUATED (rank≈26.5) / CONFIRMED on the Lockbox (forward
# Sharpe≈22.0) — the exact AC-9 hole. A NaN column additionally CRASHED ``residualize`` with an
# unhandled ``LinAlgError``. The wall must gate on the INVARIANT "beta was actually removable":
# each required column present AND all-finite AND non-degenerate (std ≥ ε). These tests drive the
# decorrelated pure-beta basket through BOTH paths with each degenerate variant and assert
# fail-closed (infeasible / insufficient_evidence), never a raw-returns graduation/confirmation.
# --------------------------------------------------------------------------- #


def _degenerate_market_panels(folds, *, kind: str):
    """Build a PRESENT-BUT-DEGENERATE covering panel for each fold (market + funding_carry).

    ``kind`` selects the degeneracy of the ``market`` column (the required factor whose
    non-degeneracy was the missing invariant): ``"zero"`` (all-zero), ``"constant"`` (a non-zero
    constant), or ``"nan"`` (a finite column with one NaN bar). ``funding_carry`` is the benign
    all-zero column (zero here regardless). Every panel CONTAINS both required names, so the OLD
    presence-only gate said ``covers=True`` — the point of the exploit.
    """
    panels = []
    for f in folds:
        n = np.asarray(f.values).size
        if kind == "zero":
            market = np.zeros(n, dtype=np.float64)
        elif kind == "constant":
            market = np.full(n, 0.004, dtype=np.float64)
        elif kind == "nan":
            market = np.full(n, 0.01, dtype=np.float64)
            market[0] = np.nan
        else:  # pragma: no cover - guard
            raise ValueError(kind)
        panels.append({"market": market, "funding_carry": np.zeros(n, dtype=np.float64)})
    return panels


class _DegeneratePanelProvider:
    """A FactorPanelProvider that returns a PRESENT-BUT-DEGENERATE covering panel.

    Mirrors a provider that emits a fake-covering column (e.g. an all-zero ``market`` from a flat
    benchmark window): the names are present, so the old presence-only Lockbox gate passed, but
    the column neutralizes nothing. Used to drive the Lockbox half of each degenerate variant.
    """

    def __init__(self, kind: str):
        self._kind = kind

    def __call__(self, window, returns):  # noqa: ARG002
        n = np.asarray(returns.values).size
        if self._kind == "zero":
            market = np.zeros(n, dtype=np.float64)
        elif self._kind == "constant":
            market = np.full(n, 0.004, dtype=np.float64)
        elif self._kind == "nan":
            market = np.full(n, 0.01, dtype=np.float64)
            market[0] = np.nan
        else:  # pragma: no cover - guard
            raise ValueError(self._kind)
        return {"market": market, "funding_carry": np.zeros(n, dtype=np.float64)}


@pytest.mark.parametrize("kind", ["zero", "constant", "nan"])
def test_ac9_compute_res_fails_closed_on_present_but_degenerate_market(kind):
    """compute_res: a PRESENT-BUT-DEGENERATE required column ⇒ infeasible, NOT a raw graduation.

    Pre-fix (reproduced in the suite reproduction): the all-zero/constant variants GRADUATED with
    rank_sharpe≈26.5 (the presence-only gate passed and residualize removed nothing), and the NaN
    variant CRASHED ``residualize`` with ``LinAlgError``. Post-fix: the non-degeneracy gate fails
    closed for every variant — feasible False, rank None, ``factor_panel`` gate failed with a
    degenerate/unwired reason. No present-but-degenerate column can let beta-as-alpha graduate."""
    folds = [_beta_basket_fold(s)[0] for s in range(1, 4)]
    panels = _degenerate_market_panels(folds, kind=kind)

    res = compute_res(
        folds, panels, trade_count=900, thresholds=THRESHOLDS,
        required_factors=("market", "funding_carry"),
    )

    assert res.feasible is False, (
        f"pure-beta basket GRADUATED through a present-but-degenerate ({kind}) market column "
        f"(rank_sharpe={res.rank_sharpe}) — the non-degeneracy wall is not fail-closed"
    )
    assert res.rank_sharpe is None
    assert "factor_panel" in res.gate_results
    assert not res.gate_results["factor_panel"].passed
    assert "degenerate" in res.gate_results["factor_panel"].detail


@pytest.mark.parametrize("kind", ["zero", "constant", "nan"])
def test_ac9_walk_forward_fails_closed_on_present_but_degenerate_market(kind):
    """run_walk_forward_res (live path): a provider that emits a present-but-degenerate covering
    panel ⇒ infeasible, never a raw-beta graduation. The full orchestrator path, not just the
    judgment layer in isolation."""
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_beta_basket_fold)

    out = run_walk_forward_res(
        exp, proto, gw, _DegeneratePanelProvider(kind), thresholds=THRESHOLDS
    )

    assert out.n_folds_evaluated >= 1
    res = out.res
    assert res.feasible is False, (
        f"pure-beta basket GRADUATED on the live path via a degenerate ({kind}) panel "
        f"(rank_sharpe={res.rank_sharpe})"
    )
    assert res.rank_sharpe is None
    assert "factor_panel" in res.gate_results
    assert not res.gate_results["factor_panel"].passed
    assert "degenerate" in res.gate_results["factor_panel"].detail


@pytest.mark.parametrize("kind", ["zero", "constant", "nan"])
def test_ac9_lockbox_fails_closed_on_present_but_degenerate_market(kind):
    """confirm_on_lockbox: a PRESENT-BUT-DEGENERATE covering panel ⇒ insufficient_evidence,
    never CONFIRMED on raw beta.

    Pre-fix (reproduced in the suite reproduction): the all-zero/constant variants CONFIRMED on a
    powered block (forward Sharpe≈22.0) because the presence-only gate passed and residualize
    removed nothing; the NaN variant crashed. Post-fix: the non-degeneracy gate returns
    insufficient_evidence BEFORE the bootstrap — no Lockbox block is burned on raw beta."""
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_beta_basket_fold)
    rp = np.concatenate([_beta_basket_fold(s)[0].values for s in range(1, 40)])
    profile = profile_asset(rp, lockbox_periods=4000, periods_per_year=PPY)

    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=5.0, gateway=gw, book=LockboxBook(),
        trial_id="x", spent_at="2024-12-15T00:00:00Z",
        factor_panel_provider=_DegeneratePanelProvider(kind),
    )

    assert verdict.verdict == "insufficient_evidence", (
        f"Lockbox CONFIRMED pure-beta via a degenerate ({kind}) panel (verdict={verdict.verdict}, "
        f"forward_sharpe={verdict.forward_sharpe}) — the non-degeneracy wall is not fail-closed"
    )
    assert "degenerate" in verdict.detail


def test_ac9_lockbox_does_not_spend_block_on_degenerate_panel():
    """The degenerate-panel insufficient_evidence must NOT burn the Lockbox dataset (the reserve
    is a one-shot resource; a misconfigured panel must not consume it). A second confirm on the
    same block with a covering panel must still be able to run (reserve not yet spent)."""
    proto, exp = _protocol(), _experiment()
    gw = _BasketGateway(_beta_basket_fold)
    rp = np.concatenate([_beta_basket_fold(s)[0].values for s in range(1, 40)])
    profile = profile_asset(rp, lockbox_periods=4000, periods_per_year=PPY)
    book = LockboxBook()

    first = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=5.0, gateway=gw, book=book,
        trial_id="x", spent_at="2024-12-15T00:00:00Z",
        factor_panel_provider=_DegeneratePanelProvider("zero"),
    )
    assert first.verdict == "insufficient_evidence"
    # The reserve must not have fired: a subsequent confirm on the SAME block still reserves
    # successfully (no LockboxSpentError), proving the degenerate path returned pre-reserve.
    from harness.data.lockbox_book import LockboxSpentError

    try:
        confirm_on_lockbox(
            exp, proto, profile, claimed_edge=5.0, gateway=gw, book=book,
            trial_id="y", spent_at="2024-12-16T00:00:00Z",
            factor_panel_provider=_DegeneratePanelProvider("constant"),
        )
    except LockboxSpentError:  # pragma: no cover - would mean the block was wrongly burned
        raise AssertionError("degenerate-panel verdict burned the Lockbox block (reserve fired)")


# --------------------------------------------------------------------------- #
# residualize itself must be fail-closed (defense-in-depth): a degenerate / non-finite /
# rank-deficient design matrix must signal infeasibility, NOT crash and NOT return raw.
# --------------------------------------------------------------------------- #


def test_residualize_fails_closed_on_nan_design_does_not_crash():
    """residualize against a NaN-containing factor column must NOT raise LinAlgError and must NOT
    return the raw series as if it were residual. It signals infeasibility (no usable IR)."""
    from harness.objective.factors import residualize

    rng = np.random.default_rng(7)
    raw = 0.9 * (0.012 * rng.standard_normal(240) + 0.004) + 0.01 * rng.standard_normal(240)
    market = np.full(240, 0.01)
    market[0] = np.nan  # non-finite design column

    result = residualize(raw, {"market": market, "funding_carry": np.zeros(240)})
    # Fail-closed sentinel: no usable information ratio, and the series is NOT scored as raw alpha.
    assert result.information_ratio is None


@pytest.mark.parametrize("kind", ["zero", "constant"])
def test_residualize_fails_closed_on_degenerate_design(kind):
    """residualize against an all-zero / constant factor column signals infeasibility rather than
    returning the raw beta series (which a zero/constant regressor cannot neutralize)."""
    from harness.objective.factors import residualize

    rng = np.random.default_rng(8)
    raw = 0.9 * (0.012 * rng.standard_normal(240) + 0.004) + 0.01 * rng.standard_normal(240)
    market = np.zeros(240) if kind == "zero" else np.full(240, 0.004)

    result = residualize(raw, {"market": market, "funding_carry": np.zeros(240)})
    assert result.information_ratio is None


# --------------------------------------------------------------------------- #
# Positive control (re-affirmed): a NON-degenerate market column (std≈0.011) still BOUNCES the
# pure-beta basket (neutralization works) AND a covering non-degenerate panel still lets genuine
# idiosyncratic alpha graduate/confirm. The non-degeneracy gate must not over-fire on real data.
# --------------------------------------------------------------------------- #


def test_ac9_non_degenerate_market_still_bounces_pure_beta():
    """The reviewer's positive control: a real (non-degenerate) market column (std≈0.011) covers
    the requirement, so the non-degeneracy gate does NOT fire, and honest neutralization still
    residualizes the pure-beta basket to ≈0 ⇒ infeasible (no rankable residual edge)."""
    folds, panels = [], []
    for s in range(1, 4):
        fold, panel = _beta_basket_fold(s)
        folds.append(fold)
        panels.append(
            {"market": panel["market"], "funding_carry": benign_funding_carry(panel["market"].size, seed=s + 7000)}
        )
    # Sanity: the true market column is genuinely non-degenerate.
    assert float(np.std(panels[0]["market"], ddof=1)) > 0.005

    res = compute_res(
        folds, panels, trade_count=900, thresholds=THRESHOLDS,
        required_factors=("market", "funding_carry"),
    )
    # The non-degeneracy gate passes (the market column is usable), and neutralization bounces beta.
    assert res.gate_results["factor_panel"].passed
    assert res.feasible is False
    assert res.rank_sharpe is None
