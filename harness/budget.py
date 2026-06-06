"""Budget Manager — the global, MinBTL-sized, effective-N Selection-look cap (FR-E2/E3/E5).

Trials are the scarce resource. The multiple-testing unit is **each Selection look**, and the
budget is **GLOBAL to the campaign** — not reset per family (FR-E2; the resolved decision in the
phase plan). Every Selection touch spends 1; the family fingerprint is the unforgeable key that
stops relabeling from minting budget (AC-2) and the clustering used for effective-N *sizing* —
it is NOT a per-family budget.

Two numbers, kept distinct (first principles):

1. **The cap** is an integer upper bound on the number of Selection looks the campaign may run.
   Its size comes from the Asset Profiler's ``budget_upper_bound`` — MinBTL on the **effective
   sample** (autocorrelation-discounted history; see ``profiler``). FR-E3's other half —
   **effective independent trials** (clustering correlated configs) — refines the cap downward:
   the cap is ``min(profile.budget_upper_bound, effective-trial bound)``. Because the cap is one
   global integer that does not grow with the number of families, no relabeling/splitting can
   raise it (AC-2).

2. **Consumption** is the count of looks already CHARGED — every reserved Selection touch
   (finalized or crashed; the ledger's ``charged_count``). A look may be reserved **iff**
   ``charged < cap``. When ``charged == cap`` the budget is **spent**: the harness STOPS issuing
   looks (FR-E5). The agent is never handed a countdown — "no more looks" is a quota state, not a
   per-call rejection the agent can probe around.

Effective-N (FR-E3, sizing): correlated configs do not count as independent evidence. Configs in
the **same family** are correlated; the number of **distinct families** is the count of effective
independent directions the search has explored. ``effective_independent_trials`` exposes this for
the cap refinement here and for P4's audit. (The audit itself operates on the logged *returns*,
which absorb residual correlation directly — FR-F1 — so this clustering is the search-time proxy,
not the final correction.)

Pure: no clock, no RNG, no I/O, no ``quant_strategies``. The manager reads consumption from the
ledger (injected) and never mutates it — reserving a look is the ledger's job, so a reserved look
is charged exactly once and the two states cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol as TypingProtocol


class _ChargedSource(TypingProtocol):
    """The slice of the ledger the budget reads: how many looks are already charged."""

    def charged_count(self) -> int: ...


def effective_independent_trials(family_ids: Iterable[str]) -> int:
    """Effective independent trials = the number of DISTINCT families among the looks.

    Configs sharing a family are correlated (same signal structure), so a family contributes one
    effective independent direction no matter how many param-tweaks it spawned. This is the
    search-time effective-N (FR-E3) used to size the cap and, in P4, to reason about top-K.
    """
    return len({f for f in family_ids})


def size_budget(
    profile_upper_bound: int,
    *,
    effective_trials_cap: int | None = None,
) -> int:
    """Compute the global cap as an upper bound (FR-E3).

    ``profile_upper_bound`` is the profiler's MinBTL-on-effective-sample cap (the primary bound).
    ``effective_trials_cap``, when supplied, is a tighter bound from the effective independent
    trials the campaign expects to run; the cap is the **minimum** of the two (a campaign can
    never run more looks than either bound allows). Always ≥ 1 so a campaign can take at least one
    honest look when the profile admits any.
    """
    cap = int(profile_upper_bound)
    if effective_trials_cap is not None:
        cap = min(cap, int(effective_trials_cap))
    return max(1, cap)


class BudgetExhaustedError(RuntimeError):
    """Raised if a look is reserved against a spent budget — a programming error, not an agent
    path. The agent-facing surface (``can_reserve`` / ``remaining``) reports the quota state so the
    controller never attempts a charge past the cap (FR-E5)."""


@dataclass(frozen=True)
class BudgetStatus:
    """A snapshot of the global budget (observability, NFR-5)."""

    cap: int
    charged: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.charged)

    @property
    def spent(self) -> bool:
        """True once the campaign has charged its full cap — the harness stops issuing looks."""
        return self.charged >= self.cap


class BudgetManager:
    """The global Selection-look budget, enforced against the ledger's charged count.

    ``cap`` is the global integer bound (from ``size_budget``). ``ledger`` is any object exposing
    ``charged_count()`` (the ``TrialLedger``); the manager never writes to it. Consumption is read
    live, so a crashed-but-reserved look (still charged in the ledger) correctly counts against the
    budget — the budget and the ledger cannot drift apart (FR-I2/NFR-6).
    """

    def __init__(self, cap: int, ledger: _ChargedSource) -> None:
        if cap < 1:
            raise ValueError(f"budget cap must be ≥ 1, got {cap}")
        self._cap = int(cap)
        self._ledger = ledger

    @property
    def cap(self) -> int:
        return self._cap

    def status(self) -> BudgetStatus:
        return BudgetStatus(cap=self._cap, charged=self._ledger.charged_count())

    def remaining(self) -> int:
        return self.status().remaining

    def can_reserve(self) -> bool:
        """Whether a Selection look may still be charged. False ⇒ budget spent ⇒ the harness
        stops issuing looks (FR-E5). This is the single enforcement predicate; it is keyed only to
        the global charged count, never to family — so relabeling cannot create headroom (AC-2)."""
        return not self.status().spent

    def check_can_reserve(self) -> None:
        """Raise ``BudgetExhaustedError`` if the budget is spent (a guard for the controller before
        it charges the ledger — turns a would-be over-charge into a hard failure, not a silent
        extra look)."""
        if not self.can_reserve():
            raise BudgetExhaustedError(
                f"global Selection budget spent: {self._cap} looks charged "
                "(harness stops issuing looks — graduate the best or retire; FR-E5)"
            )
