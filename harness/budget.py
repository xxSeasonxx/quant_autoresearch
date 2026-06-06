"""Budget Manager — the global, MinBTL-sized Selection-look cap (FR-E2/E3/E5).

Trials are the scarce resource. The multiple-testing unit is **each Selection look**, and the
budget is **GLOBAL to the campaign** — not reset per family (FR-E2; the resolved decision in the
phase plan). Every Selection touch spends 1.

The budget is one of three complementary anti-gaming layers; it is precisely the **first**:

1. **The budget** (here) is a hard cap on the number of *raw* Selection looks. Its size is a pure
   function of the **effective SAMPLE** — MinBTL on the autocorrelation-discounted history (the
   Asset Profiler's ``budget_upper_bound``; FR-E3). It is deliberately **family-count-INDEPENDENT**:
   the cap is one global integer that does not grow with the number of distinct families, so no
   amount of relabeling/splitting a config into "new" families can mint additional looks (AC-2).
2. **Trial CORRELATION** is not the budget's job. Correlated looks are corrected by P4's
   graduation audit (Romano-Wolf / PBO over the logged per-fold *returns*, which absorb residual
   correlation directly — FR-F1), NOT by loosening this cap. The budget never tries to "discount"
   itself for correlation; doing so would be the loosening AC-2 forbids.
3. The family **fingerprint** (``harness.family``) is the unforgeable key the audit groups by; it
   is structure-derived, not agent-chosen.

So the budget caps raw looks from the effective sample; correlation is handled downstream. Keeping
the cap family-independent is what makes AC-2 hold: tightening from clustering would be safe (it
can only ``min`` the cap down), but the live cap takes no family input at all, so the property is
unconditional.

Two numbers, kept distinct (first principles):

1. **The cap** is an integer upper bound on the number of Selection looks the campaign may run,
   constructed directly from ``profile.budget_upper_bound`` (a pure function of effective YEARS).
   Because it does not grow with the number of families, no relabeling/splitting can raise it.

2. **Consumption** is the count of looks already CHARGED — every reserved Selection touch
   (finalized or crashed; the ledger's ``charged_count``). A look may be reserved **iff**
   ``charged < cap``. When ``charged == cap`` the budget is **spent**: the harness STOPS issuing
   looks (FR-E5). The agent is never handed a countdown — "no more looks" is a quota state, not a
   per-call rejection the agent can probe around.

Pure: no clock, no RNG, no I/O, no ``quant_strategies``. The manager reads consumption from the
ledger (injected) and never mutates it — reserving a look is the ledger's job, so a reserved look
is charged exactly once and the two states cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol as TypingProtocol


class _ChargedSource(TypingProtocol):
    """The slice of the ledger the budget reads: how many looks are already charged."""

    def charged_count(self) -> int: ...


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

    ``cap`` is the global integer bound (from ``profile.budget_upper_bound`` — MinBTL on the
    effective sample, family-count-independent). ``ledger`` is any object exposing
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
