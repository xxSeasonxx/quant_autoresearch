"""Graduation rule tests — the top-K composition + the harness/human boundary (FR-F3).

A candidate graduates to the Lockbox iff it (a) clears the Stage-1 gates (RES feasible), (b)
ranks top-K by OOS Sharpe (PSR-gated), AND (c) survives the trial-population audit. All three
are required; None-rank RES is excluded from the ranking (never sorted as a number). The
harness EMITS a verdict and NEVER promotes — that boundary is asserted explicitly.

The audit is stubbed with a hand-built ``AuditResult`` so the composition logic is tested in
isolation from the bootstrap (the bootstrap itself is covered in ``test_audit.py``).
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.audit import AuditResult, TrialStat
from harness.foundation import FoldReturns
from harness.graduation import GraduationDecision, select_graduates
from harness.objective.gates import GateOutcome
from harness.ledger import LedgerRow
from harness.objective.res import ResResult

PPY = 8760.0


def _res(rank: float | None, *, feasible: bool | None = None, psr_pass: bool = True) -> ResResult:
    """A ResResult with a chosen rank + PSR gate outcome. feasible defaults to (rank is not None)."""
    feas = (rank is not None) if feasible is None else feasible
    psr_gate = GateOutcome(name="psr", passed=psr_pass, value=0.99 if psr_pass else 0.5, threshold=0.95)
    return ResResult(
        feasible=feas,
        gate_results={"psr": psr_gate},
        rank_sharpe=rank,
        per_fold_sharpe=(),
        residual_info_ratio=rank,
        psr=0.99 if psr_pass else 0.5,
    )


def _row(trial_id: str, rank: float | None, *, feasible: bool | None = None, psr_pass: bool = True) -> LedgerRow:
    fr = FoldReturns(
        timestamps=np.array(["2025-01-01"], dtype="datetime64[ns]"),
        values=np.array([0.001]),
        periods_per_year=PPY,
    )
    return LedgerRow(
        trial_id=trial_id,
        family_id=f"fam-{trial_id}",
        experiment_hash=f"exp-{trial_id}",
        protocol_hash="ph",
        thesis="t",
        per_fold_returns=(fr,),
        res=_res(rank, feasible=feasible, psr_pass=psr_pass),
        provenance={"snapshot": "s"},
        created_at="2025-01-01T00:00:00",
    )


def _audit(survivors: tuple[str, ...], all_ids: tuple[str, ...]) -> AuditResult:
    stats = {
        tid: TrialStat(
            trial_id=tid, n=100, mean=0.001, studentized=2.0 if tid in survivors else 0.1,
            p_value=0.01 if tid in survivors else 0.6,
            romano_wolf_reject=tid in survivors, bhy_reject=tid in survivors,
        )
        for tid in all_ids
    }
    return AuditResult(
        survivors=survivors, trial_stats=stats, pbo=0.1, bhy_survivors=survivors,
        alpha=0.05, binding_procedure="romano_wolf", n_trials=len(all_ids), n_bootstrap=1000,
    )


# --------------------------------------------------------------------------- #
# All three filters required.
# --------------------------------------------------------------------------- #


def test_graduates_only_when_all_three_filters_pass():
    rows = [_row("a", 2.0), _row("b", 1.5), _row("c", 1.0)]
    audit = _audit(survivors=("a", "b", "c"), all_ids=("a", "b", "c"))
    decision = select_graduates(rows, audit, top_k=3)
    assert decision.graduates == ("a", "b", "c")  # best-first by Sharpe


def test_feasible_and_top_k_but_audit_fails_does_not_graduate():
    """Clears gates + ranks top-K but the audit rejects it ⇒ no graduation (audit is binding)."""
    rows = [_row("a", 2.0), _row("b", 1.5)]
    audit = _audit(survivors=("a",), all_ids=("a", "b"))  # b rejected by the audit
    decision = select_graduates(rows, audit, top_k=5)
    assert decision.graduates == ("a",)
    assert not decision.rankings["b"].graduates
    assert decision.rankings["b"].audit_survived is False
    assert "audit" in decision.rankings["b"].reason


def test_audit_survivor_but_infeasible_does_not_graduate():
    """Survives the audit but failed the Stage-1 gates ⇒ no graduation (gates required)."""
    rows = [_row("a", 2.0), _row("b", None, feasible=False)]  # b infeasible, no rank
    audit = _audit(survivors=("a", "b"), all_ids=("a", "b"))
    decision = select_graduates(rows, audit, top_k=5)
    assert decision.graduates == ("a",)
    assert not decision.rankings["b"].graduates
    assert decision.rankings["b"].feasible is False


def test_audit_survivor_feasible_but_below_top_k_does_not_graduate():
    """Feasible + audit-survived but ranks below K ⇒ no graduation (top-K rations the Lockbox)."""
    rows = [_row("a", 3.0), _row("b", 2.0), _row("c", 1.0)]
    audit = _audit(survivors=("a", "b", "c"), all_ids=("a", "b", "c"))
    decision = select_graduates(rows, audit, top_k=2)  # only top-2 eligible
    assert decision.graduates == ("a", "b")
    assert not decision.rankings["c"].in_top_k
    assert "top-K" in decision.rankings["c"].reason


def test_feasible_top_k_audit_survived_but_psr_failed_does_not_graduate():
    """PSR (evidence-sufficiency) gate is required to be top-K-eligible (FR-F3 PSR-gated)."""
    rows = [_row("a", 2.0, psr_pass=True), _row("b", 1.5, psr_pass=False)]
    audit = _audit(survivors=("a", "b"), all_ids=("a", "b"))
    decision = select_graduates(rows, audit, top_k=5)
    assert decision.graduates == ("a",)
    assert not decision.rankings["b"].graduates
    assert decision.rankings["b"].psr_passed is False
    assert "PSR" in decision.rankings["b"].reason


# --------------------------------------------------------------------------- #
# None-rank is excluded from the ranking, never sorted as a number.
# --------------------------------------------------------------------------- #


def test_none_rank_is_excluded_from_top_k_not_sorted_as_number():
    """An unrankable RES (None rank) is excluded from the candidate pool — it must NOT sort as
    if it were a numeric rank (the P1/P2 carry). With None mixed among real ranks the sort
    must not raise and the None must not occupy a top-K slot."""
    rows = [
        _row("a", 2.0),
        _row("none1", None, feasible=False),  # infeasible/unrankable
        _row("b", 1.0),
        _row("none2", None, feasible=True),   # feasible flag True but rank None ⇒ still excluded
    ]
    audit = _audit(survivors=("a", "b", "none1", "none2"), all_ids=("a", "b", "none1", "none2"))
    decision = select_graduates(rows, audit, top_k=4)
    # Only the two rankable candidates graduate; neither None occupies a slot.
    assert decision.graduates == ("a", "b")
    assert not decision.rankings["none1"].feasible
    assert not decision.rankings["none2"].feasible  # rank None ⇒ excluded even if gate flag set
    assert decision.rankings["none1"].in_top_k is False
    assert decision.rankings["none2"].in_top_k is False


def test_none_rank_with_a_full_top_k_does_not_displace_real_candidates():
    rows = [_row("a", 5.0), _row("b", 4.0), _row("x", None, feasible=False)]
    audit = _audit(survivors=("a", "b", "x"), all_ids=("a", "b", "x"))
    decision = select_graduates(rows, audit, top_k=2)
    assert decision.graduates == ("a", "b")
    assert "x" not in decision.graduates


# --------------------------------------------------------------------------- #
# The harness emits a verdict and NEVER promotes.
# --------------------------------------------------------------------------- #


def test_harness_emits_verdict_but_never_promotes():
    """FR-F3 boundary: the decision is a verdict; there is no promotion action and no code path
    that acts on a graduated/confirmed candidate. The `promoted` property is always None."""
    rows = [_row("a", 2.0)]
    audit = _audit(survivors=("a",), all_ids=("a",))
    decision = select_graduates(rows, audit, top_k=1)
    assert isinstance(decision, GraduationDecision)
    assert decision.graduates == ("a",)
    # The boundary marker: the harness never promotes.
    assert decision.promoted is None
    # The module exposes no promote function (greppable boundary).
    import harness.graduation as grad_mod
    assert not any(name.startswith("promote") for name in dir(grad_mod))


def test_audit_result_is_carried_in_the_decision():
    rows = [_row("a", 2.0), _row("b", 1.0)]
    audit = _audit(survivors=("a",), all_ids=("a", "b"))
    decision = select_graduates(rows, audit, top_k=2)
    assert decision.audit is audit
    assert decision.audit.binding_procedure == "romano_wolf"


# --------------------------------------------------------------------------- #
# Edge cases.
# --------------------------------------------------------------------------- #


def test_empty_population_graduates_nothing():
    audit = _audit(survivors=(), all_ids=())
    decision = select_graduates([], audit, top_k=3)
    assert decision.graduates == ()


def test_top_k_must_be_positive():
    with pytest.raises(ValueError):
        select_graduates([_row("a", 1.0)], _audit(("a",), ("a",)), top_k=0)


def test_ranking_is_deterministic_by_sharpe_then_trial_id():
    """Ties in Sharpe break by trial_id for a deterministic order."""
    rows = [_row("z", 1.0), _row("a", 1.0), _row("m", 1.0)]  # identical Sharpe
    audit = _audit(survivors=("z", "a", "m"), all_ids=("z", "a", "m"))
    decision = select_graduates(rows, audit, top_k=3)
    assert decision.graduates == ("a", "m", "z")  # tie-break by trial_id ascending
