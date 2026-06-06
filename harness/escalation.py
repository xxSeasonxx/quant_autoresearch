"""Escalation Controller — the harness-enforced Train→Selection gate (FR-D1, FR-A4).

"Satisfice on Train, select on Selection." A candidate may consume a scarce, leaky Selection
look ONLY when it clears every condition of the escalation gate. The gate is a **filter**
(garbage is bounced to the free Train sandbox), not a ranking: above the in-sample floor,
candidates are **never** ranked for escalation by Train magnitude — preferring the higher
Train score actively selects for overfit (methodology "When to escalate"). The throttle is a
genuinely new *thesis* + remaining *budget* (the budget lives in P3, enforced at the CLI); the
gate's job is to keep invalid / dead / non-edge / thesis-free / single-symbol / knife-edge
candidates off Selection.

The six conditions (all binary; fail any ⇒ routed back to Train, FREE, never spends a look):

1. **valid** — passed causal replay + the decision contract (Tier-0's core job; from
   ``quick_run.valid``/``causal_ok``).
2. **alive** — enough trades to measure, not a degenerate artifact (``trade_count`` ≥ the
   Protocol's ``min_trades`` floor).
3. **in-sample-positive after costs** — a LOW floor ("the edge exists in-sample"), not a high
   one (``quick_run.in_sample_metric`` > 0). A negative/flat Train result is −EV to escalate
   because Train is optimistically biased.
4. **new thesis** — the candidate's computed **family fingerprint** (``harness.family`` over the
   strategy source) is NOT already in the trial ledger. A thesis-free nudge of a logged family
   (a param tweak, a relabeled docstring) collapses to the SAME family id and is routed to
   Train, FREE — it never spends a look (the naked-sweep detector, enforcement #4; AC-2/AC-8).
5. **cheap-robust** — the in-sample edge is not carried by a single symbol (from
   ``quick_run.slices['by_symbol']``). See the by_hour/by_month note below.
6. **robust-plateau** — not a knife-edge: the P1 stability gate (``harness.stability``) perturbs
   the params ±steps on Train and requires the in-sample metric to stay flat-and-positive
   (enforcement #10). Rewards *flatness, not height*, so it cannot be gamed by climbing.

**Swing-big cadence (FR-A4, enforcement #8).** Every ``M`` ideas the harness REQUIRES a
structurally new signal family. ``ideas_since_new_family`` is the count of IDEAS the agent has
explored — every ``run`` and ``evaluate`` is an idea — since the last ``evaluate`` that LOGGED a
structurally-new family; it is owned and persisted by the session (``harness.session``), not
derived from the ledger. (A ledger-derived count would be permanently zero: every logged look is
already a new family by the new-thesis condition, so it could never trigger. Counting ideas —
including the free Train runs the agent circles one family with — is what makes swing-big a real,
independent cadence.) Once it reaches ``M``, an old-family candidate is REFUSED (routed to Train)
until a structurally new family is proposed — breaking the cagy local-optima loop.

**The by_hour/by_month carry (resolved).** The real foundation
(``RealFoundationGateway._slices``) emits ``by_symbol`` / ``by_direction`` / ``by_exit_reason``
— there is **no** ``by_hour`` / ``by_month`` calendar axis in the engine (those were invented in
an earlier sketch). The cheap-robust "edge not carried by one symbol/window/hour" check is
therefore **scoped to the slices that exist**, with ``by_symbol`` the load-bearing one — it is
exactly the axis that bounces AC-1's ADA-disguised-as-basket campaign (one symbol carrying ~all
the PnL). ``FakeFoundationGateway`` defaults its slices to ``{"by_symbol": {}}`` to match, so
Fake-tested escalation matches reality. When a calendar concentration axis is wanted it can be
computed from the diagnostics ``sample_trades`` upstream; absent that, scoping to ``by_symbol``
is the honest, documented choice (it cannot silently pass a single-symbol bet).

Pure of ``quant_strategies``: depends only on the ``FoundationGateway`` seam (real adapter or
fake), the family fingerprint, the stability gate, and the ledger's logged family ids. No clock,
no RNG, no I/O here (the CLI shell injects the ledger view and the strategy source).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from harness.family import compute_family_id
from harness.foundation import FoundationGateway, QuickRunResult
from harness.protocol import Experiment, Protocol
from harness.stability import StabilityResult, evaluate_stability

# How many ideas may pass between two structurally-new families before the harness REQUIRES a
# swing-big (a new family) to escalate. Protocol-adjacent campaign cadence; default 5.
DEFAULT_SWING_BIG_EVERY = 5


@dataclass(frozen=True)
class GateCondition:
    """One escalation condition's outcome (observability, NFR-5)."""

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class EscalationDecision:
    """The escalation gate's verdict for one candidate.

    ``may_escalate`` True ⇒ the candidate cleared every condition and the swing-big cadence and
    MAY spend a Selection look (the CLI still checks the budget — the look is not *entitled*).
    False ⇒ routed back to Train (FREE); ``reason`` is the first failing condition.
    """

    may_escalate: bool
    family_id: str
    is_new_family: bool
    conditions: tuple[GateCondition, ...]
    stability: StabilityResult | None
    reason: str

    @property
    def routed_to_train(self) -> bool:
        """The complement of ``may_escalate`` — a routed candidate stays on the free Train
        sandbox and spends no look (the naked-sweep / swing-big redirect)."""
        return not self.may_escalate


def _first_failure(conditions: Sequence[GateCondition]) -> str:
    for c in conditions:
        if not c.passed:
            return f"{c.name}: {c.detail}"
    return ""


def _cheap_robust(
    slices: Any, max_concentration: float
) -> GateCondition:
    """Cheap-robust: the in-sample edge must not be carried by a single symbol (by_symbol slice).

    Uses the SAME correlation-free Herfindahl concentration measure the RES concentration gate
    uses, but on the cheap Train ``by_symbol`` summary (no return series here, just per-symbol
    scalar contributions). A single dominant symbol (share > ``max_concentration``) fails — this
    is the leg that bounces AC-1's ADA-only "basket" before it can spend a look. With <2 symbols
    there is nothing to diversify, so the check is N/A and passes (a single-symbol UNIVERSE is a
    deliberate Experiment choice, not a hidden concentration; the OOS concentration/breadth gates
    still bind on Selection).
    """
    by_symbol = {}
    if isinstance(slices, dict):
        raw = slices.get("by_symbol")
        if isinstance(raw, dict):
            by_symbol = raw
    if len(by_symbol) < 2:
        return GateCondition(
            name="cheap_robust",
            passed=True,
            detail=f"{len(by_symbol)} symbol slice(s); single-symbol concentration N/A on Train",
        )
    # Magnitude of each symbol's contribution; a symbol carrying > max_concentration of the
    # total |contribution| is a single-symbol-carried edge.
    contributions = {}
    for sym, v in by_symbol.items():
        val = _scalar(v)
        if val is not None:
            contributions[sym] = abs(val)
    total = sum(contributions.values())
    if total <= 0.0 or not contributions:
        # No measurable per-symbol contribution ⇒ nothing to attribute ⇒ cannot confirm breadth.
        return GateCondition(
            name="cheap_robust",
            passed=False,
            detail="no measurable per-symbol contribution; edge concentration cannot be confirmed",
        )
    top = max(contributions.values())
    share = top / total
    passed = share <= max_concentration
    return GateCondition(
        name="cheap_robust",
        passed=passed,
        detail=(
            f"top-symbol share {share:.2f} "
            f"({'≤' if passed else '>'} {max_concentration:.2f} ceiling)"
        ),
    )


def _scalar(value: Any) -> float | None:
    """Coerce a by_symbol slice value to a float contribution.

    The foundation's economic_slices map a symbol to either a scalar (its per-symbol economic
    figure, e.g. ``average_trade_net``/``net``) or a nested mapping of figures. Prefer an explicit
    net/contribution key; fall back to the first finite numeric value; ``None`` if none.
    """
    import math

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, dict):
        for key in ("net", "average_trade_net", "net_return", "contribution", "pnl"):
            v = value.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
                return float(v)
        for v in value.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
                return float(v)
    return None


def evaluate_escalation(
    experiment: Experiment,
    protocol: Protocol,
    window: Any,
    gateway: FoundationGateway,
    *,
    strategy_source: str,
    logged_family_ids: Sequence[str],
    ideas_since_new_family: int,
    swing_big_every: int = DEFAULT_SWING_BIG_EVERY,
    quick_run: QuickRunResult | None = None,
) -> EscalationDecision:
    """Apply the escalation gate to one candidate (the harness-enforced Train→Selection filter).

    ``strategy_source`` is the candidate's strategy file source (the CLI reads it once); the
    family fingerprint is computed from it so a thesis-free nudge collapses to a logged family.
    ``logged_family_ids`` is the set/sequence of family ids already in the trial ledger.
    ``ideas_since_new_family`` is how many ideas have been explored since the last NEW family was
    logged (for the swing-big cadence). ``quick_run`` may be passed to reuse a Train run the CLI
    already executed; otherwise the gate runs one itself through the gateway.

    Returns an ``EscalationDecision``. ``may_escalate`` is True only if EVERY condition passed
    AND the swing-big cadence does not require a new family. The CLI still enforces the budget on
    top — passing the gate does not *entitle* a look.
    """
    family_id = compute_family_id(strategy_source)
    is_new_family = family_id not in set(logged_family_ids)

    run = quick_run if quick_run is not None else gateway.quick_run(experiment, protocol, window)

    min_trades = protocol.objective.gates.min_trades
    max_concentration = protocol.objective.gates.max_concentration

    # --- Conditions 1-3: validity, aliveness, in-sample positivity (cheap, from quick_run). ---
    valid = GateCondition(
        name="valid",
        passed=bool(run.valid and run.causal_ok),
        detail=(
            "passed causal replay + contract"
            if run.valid and run.causal_ok
            else f"invalid (failure_stage={run.failure_stage!r}, causal_ok={run.causal_ok})"
        ),
    )
    alive = GateCondition(
        name="alive",
        passed=run.trade_count >= min_trades,
        detail=f"{run.trade_count} trades ({'≥' if run.trade_count >= min_trades else '<'} {min_trades} floor)",
    )
    m = run.in_sample_metric
    in_sample_positive = GateCondition(
        name="in_sample_positive",
        passed=m is not None and m > 0.0,
        detail=(
            f"in-sample metric {m:.6g} after costs > 0"
            if (m is not None and m > 0.0)
            else f"in-sample metric {m!r} not positive after costs (−EV to escalate)"
        ),
    )

    # --- Condition 4: new thesis (the family fingerprint vs the ledger; naked-sweep routing). ---
    new_thesis = GateCondition(
        name="new_thesis",
        passed=is_new_family,
        detail=(
            f"family {family_id[:12]}… is structurally new"
            if is_new_family
            else f"family {family_id[:12]}… already in the ledger — a thesis-free nudge routes to Train (free)"
        ),
    )

    # --- Condition 5: cheap-robust (single-symbol-carried edge, scoped to by_symbol). ---
    cheap_robust = _cheap_robust(run.slices, max_concentration)

    # --- Condition 6: robust plateau (the computed stability gate). ---
    stability = evaluate_stability(experiment, protocol, window, gateway)
    plateau = GateCondition(
        name="robust_plateau",
        passed=stability.passed,
        detail=stability.detail or ("flat-and-positive plateau" if stability.passed else "knife-edge"),
    )

    gate_conditions = (valid, alive, in_sample_positive, new_thesis, cheap_robust, plateau)
    all_passed = all(c.passed for c in gate_conditions)

    # --- Swing-big cadence (FR-A4): after M ideas without a new family, a new family is REQUIRED. ---
    swing_big_required = (
        swing_big_every > 0 and ideas_since_new_family >= swing_big_every and not is_new_family
    )
    swing_big = GateCondition(
        name="swing_big",
        passed=not swing_big_required,
        detail=(
            f"swing-big required: {ideas_since_new_family} ideas since a new family "
            f"(≥ {swing_big_every}) — propose a structurally new signal family"
            if swing_big_required
            else f"{ideas_since_new_family} ideas since a new family (< {swing_big_every} cadence)"
        ),
    )
    conditions = gate_conditions + (swing_big,)

    may_escalate = all_passed and not swing_big_required
    reason = (
        "all conditions passed; may spend one Selection look (budget permitting)"
        if may_escalate
        else _first_failure(conditions)
    )
    return EscalationDecision(
        may_escalate=may_escalate,
        family_id=family_id,
        is_new_family=is_new_family,
        conditions=conditions,
        stability=stability,
        reason=reason,
    )
