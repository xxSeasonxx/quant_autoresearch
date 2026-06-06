"""Graduation rule — the top-K composition that gates entry to the Lockbox (FR-F3).

A candidate **graduates to the Lockbox** iff it clears ALL THREE filters:

1. **Feasible** — it passed the Stage-1 gates (``ResResult.feasible``) AND carries a rankable
   number (``rank_sharpe is not None``). An infeasible or unrankable candidate is excluded from
   the pool entirely — a ``None`` rank is NEVER sorted as if it were a number (the P1/P2 carry).
2. **Top-K by OOS Sharpe (PSR-gated)** — among the feasible candidates, it ranks in the top K by
   ``rank_sharpe`` descending, with its PSR gate passed (evidence sufficiency).
3. **Survives the trial-population audit** — its ``trial_id`` is in the Romano-Wolf
   FWER-controlled survivor set from ``harness.audit`` (the BINDING criterion — the audit over
   the logged returns of ALL trials, not just these finalists).

Only the intersection graduates; clearing any subset does not. The three layers are
complementary (Principle 1): the gates kill overfit *shapes*, the top-K rations the scarce
Lockbox, and the audit corrects the *selection* over the whole trial population.

**The harness emits a verdict; it never promotes.** This module returns a ``GraduationDecision``
— the graduates, the audit result, and per-candidate reasons. It does NOT call the Lockbox and
does NOT act on a ``confirmed`` verdict. Confirming a graduate on the Lockbox is a separate call
(``harness.lockbox.confirm_on_lockbox``) the human/CLI orchestrates; **promotion above the
Lockbox is a human-only step** (FR-F3). No function in this module promotes.

Pure: composition over the ledger rows + the audit result; no clock, no RNG, no
``quant_strategies`` import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from harness.audit import AuditResult
from harness.ledger import LedgerRow

# The reason a candidate did or did not graduate (observability, NFR-5).
GraduationReason = str


@dataclass(frozen=True)
class CandidateRanking:
    """One candidate's standing against the three filters (per-candidate transparency)."""

    trial_id: str
    rank_sharpe: float | None
    feasible: bool  # passed Stage-1 gates AND has a rankable number
    psr_passed: bool
    in_top_k: bool
    audit_survived: bool
    graduates: bool
    reason: GraduationReason


@dataclass(frozen=True)
class GraduationDecision:
    """The graduation verdict over a trial population (FR-F3).

    ``graduates`` is the ordered (best-first by OOS Sharpe) tuple of trial_ids that clear ALL
    THREE filters and may be confirmed on the Lockbox. ``audit`` is the binding audit result
    the decision composed. The harness EMITS this; it does not promote.
    """

    graduates: tuple[str, ...]
    rankings: Mapping[str, CandidateRanking]
    audit: AuditResult
    top_k: int

    @property
    def promoted(self) -> None:
        """There is deliberately NO promotion here. Promotion above the Lockbox is a human-only
        step (FR-F3); the harness emits a verdict and never acts on it. This property exists to
        make the boundary explicit and greppable — it is always ``None``."""
        return None


def _psr_passed(row: LedgerRow) -> bool:
    """Whether the candidate's PSR (evidence-sufficiency) gate passed.

    Reads the gate the RES already computed (``psr`` gate in ``ResResult.gate_results``). If the
    PSR gate was not part of this row's gate set (a pure-logic RES with no OOS evidence), the
    evidence sufficiency was not established ⇒ fail closed (it cannot be top-K-eligible).
    """
    gate = row.res.gate_results.get("psr")
    return bool(gate is not None and gate.passed)


def select_graduates(
    rows: Sequence[LedgerRow],
    audit: AuditResult,
    *,
    top_k: int,
) -> GraduationDecision:
    """Compose the three filters into the graduation decision (FR-F3).

    ``rows`` is the finalized trial population (the same set the audit ran over). ``audit`` is
    the result of ``harness.audit.run_graduation_audit`` (Romano-Wolf survivors are binding).
    ``top_k`` is the Lockbox ration. A candidate graduates iff feasible ∧ PSR-passed ∧ top-K ∧
    audit-survived.

    Ranking handles ``None``/unrankable RES by EXCLUSION: only feasible candidates with a
    non-None ``rank_sharpe`` enter the ranking pool, so a ``None`` rank never participates in
    the sort. Ties break by trial_id for determinism.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be ≥ 1, got {top_k}")

    # --- Filter 1: feasible AND rankable. A None rank is EXCLUDED, never sorted. ---
    feasible_pool = [
        r for r in rows if r.res.feasible and r.res.rank_sharpe is not None
    ]

    # --- Filter 2: rank the feasible pool by OOS Sharpe desc; take top-K (PSR-gated). ---
    # Sort by (-rank_sharpe, trial_id): deterministic, best-first. PSR gate is required to be
    # top-K-eligible (evidence sufficiency); a feasible-but-PSR-failing row is not eligible.
    psr_eligible = [r for r in feasible_pool if _psr_passed(r)]
    ranked = sorted(
        psr_eligible,
        key=lambda r: (-float(r.res.rank_sharpe), r.trial_id),  # type: ignore[arg-type]
    )
    top_k_ids = {r.trial_id for r in ranked[:top_k]}

    # --- Filter 3: audit survival (the BINDING Romano-Wolf set). ---
    survivors = set(audit.survivors)

    # --- Compose: the intersection graduates, kept in best-first rank order. ---
    rankings: dict[str, CandidateRanking] = {}
    for r in rows:
        feasible = r.res.feasible and r.res.rank_sharpe is not None
        psr_ok = _psr_passed(r)
        in_top_k = r.trial_id in top_k_ids
        survived = r.trial_id in survivors
        graduates = feasible and psr_ok and in_top_k and survived
        rankings[r.trial_id] = CandidateRanking(
            trial_id=r.trial_id,
            rank_sharpe=r.res.rank_sharpe,
            feasible=feasible,
            psr_passed=psr_ok,
            in_top_k=in_top_k,
            audit_survived=survived,
            graduates=graduates,
            reason=_reason(feasible, psr_ok, in_top_k, survived),
        )

    graduates = tuple(r.trial_id for r in ranked if rankings[r.trial_id].graduates)
    return GraduationDecision(
        graduates=graduates,
        rankings=rankings,
        audit=audit,
        top_k=top_k,
    )


def _reason(feasible: bool, psr: bool, in_top_k: bool, survived: bool) -> GraduationReason:
    """A human-readable reason a candidate did or did not graduate (the first failing
    filter, in the composition order)."""
    if not feasible:
        return "excluded: infeasible or unrankable RES (None rank not sorted)"
    if not psr:
        return "excluded: PSR evidence-sufficiency gate not passed"
    if not in_top_k:
        return "not graduated: outside top-K by OOS Sharpe"
    if not survived:
        return "not graduated: did not survive the trial-population audit (Romano-Wolf)"
    return "graduated: feasible ∧ PSR-passed ∧ top-K ∧ audit-survived"
