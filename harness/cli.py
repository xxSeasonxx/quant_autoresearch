"""The agent + admin CLI — the composition root where rigor is MECHANICAL (§8).

Three agent-facing commands and three admin/human commands, each a thin shell over the
immutable judgment layer. The agent's contract (``program.md``) names exactly these:

- ``status``   — best logged candidate + recent ledger rows + the budget as a QUOTA state
                 (looks remaining, never a countdown; FR-E5).
- ``run``      — Train quick run: causal diagnostic + a coarse plausibility band. FREE, unlimited
                 (FR-A2/NFR-3). Never spends a look.
- ``evaluate`` — Selection: the harness applies the **escalation gate** + the **budget**, and
                 ONLY if the gate passes AND budget remains runs the walk-forward RES via
                 ``SelectionController.take_look`` and LOGS the bet. Refuses with a clear reason
                 if the gate fails (routed to Train) or the budget is spent (quota). This is
                 where rigor is MECHANICAL — the agent cannot bypass it (FR-D1/D3, AC-8).
- ``profile``  — Asset Profiler + data-sufficiency (admin; FR-G).
- ``graduate`` — returns-based audit + top-K graduation decision (admin; FR-F1/F3). EMITS a
                 verdict; never promotes.
- ``lockbox``  — power-aware one-shot Lockbox verdict (human-gated; FR-F2). EMITS a verdict;
                 the harness NEVER promotes.

**Boundary (the seam test must stay green).** This module must NOT ``import quant_strategies``.
It constructs the ``RealFoundationGateway`` LAZILY (inside ``_build_real_gateway`` →
``harness.foundation_real``, the single sanctioned importer) only when the real entry point runs,
so importing ``harness.cli`` does not pull in the engine. Tests inject the ``FakeFoundationGateway``
into ``HarnessCLI`` directly (no live data). The CLI core is pure orchestration over the seam.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from harness.budget import BudgetManager
from harness.escalation import (
    DEFAULT_SWING_BIG_EVERY,
    EscalationDecision,
    evaluate_escalation,
)
from harness.foundation import FoundationGateway
from harness.ledger import LedgerRow, TrialLedger
from harness.orchestrator import FactorPanelProvider, FoldWindowSpan
from harness.profiler import AssetProfile, SufficiencyVerdict, assess_sufficiency, profile_asset
from harness.protocol import Experiment, Protocol, load_protocol
from harness.selection import NoLookAvailable, SelectionController
from harness.stability import train_plausibility


def _no_factor_panel(window: FoldWindowSpan, returns) -> Mapping[str, np.ndarray]:
    """Default factor-panel provider: no neutralization (identity).

    The real campaign injects a ``quant_data``-backed panel (market/momentum/funding-carry/size)
    here — that is the seam where factor neutralization plugs in (harness-architecture §2, FR-C3).
    Absent a wired panel, RES scores the raw OOS residual (no factor columns to regress out); the
    breadth/concentration and OOS gates still bind. We do NOT fabricate a synthetic panel.
    """
    return {}


@dataclass(frozen=True)
class RunResult:
    """The ``run`` (Train quick run) outcome — a coarse band, FREE (never a look)."""

    valid: bool
    causal_ok: bool
    plausibility_band: str  # "positive" | "negative" | "flat" | "infeasible"
    trade_count: int
    family_id: str
    is_new_family: bool
    slices: Mapping[str, Mapping[str, float]]
    failure_stage: str | None


@dataclass(frozen=True)
class EvaluateRefused:
    """``evaluate`` refused: either the escalation gate routed to Train, or the budget is spent.

    Mechanical enforcement (FR-D1/E5): NO Selection look was spent and NO ledger row was written.
    ``kind`` distinguishes the two refusals; ``reason`` is the first failing gate condition or the
    quota message.
    """

    kind: str  # "routed_to_train" | "budget_spent"
    reason: str
    family_id: str
    escalation: EscalationDecision | None  # present for a gate refusal (observability)


@dataclass(frozen=True)
class EvaluateLogged:
    """``evaluate`` passed the gate + budget and LOGGED the bet (one Selection look spent).

    Carries the finalized ledger row (the logged bet — NOT a hill-climb step; FR-D3) and the
    escalation decision that admitted it.
    """

    row: LedgerRow
    family_id: str
    escalation: EscalationDecision
    looks_remaining: int


class HarnessCLI:
    """The composition root: ties the seam + ledger + budget + escalation + selection together.

    Constructed with an injected ``FoundationGateway`` (the real adapter in production, the Fake
    in tests), the campaign ``Protocol``, and the durable ``TrialLedger`` + ``BudgetManager``. The
    methods are the agent/admin commands; ``main`` builds this with the real gateway lazily.

    ``created_at`` / ``trial_id`` are injected per call (NFR-1 — no clock in the judgment path);
    the CLI shell supplies them from the wall clock / a counter, the only place that is allowed.
    """

    def __init__(
        self,
        *,
        gateway: FoundationGateway,
        protocol: Protocol,
        ledger: TrialLedger,
        budget: BudgetManager,
        factor_panel_provider: FactorPanelProvider = _no_factor_panel,
        swing_big_every: int = DEFAULT_SWING_BIG_EVERY,
        ideas_since_new_family: int = 0,
        train_window: Any = None,
        strategy_source_loader=None,
    ) -> None:
        self._gateway = gateway
        self._protocol = protocol
        self._ledger = ledger
        self._budget = budget
        self._panel_provider = factor_panel_provider
        self._swing_big_every = swing_big_every
        # The swing-big cadence counter (FR-A4) — IDEAS since the last new-family logged bet,
        # owned by the session (it counts free Train runs too, which the ledger cannot see). The
        # entry point reads it from the session marker; tests inject it directly.
        self._ideas_since_new_family = int(ideas_since_new_family)
        # The Train window the quick run / stability gate evaluate over (the Train tier).
        self._train_window = train_window or _train_window(protocol)
        self._load_source = strategy_source_loader or _read_source
        self._controller = SelectionController(
            ledger=ledger,
            budget=budget,
            gateway=gateway,
            factor_panel_provider=factor_panel_provider,
            strategy_source_loader=self._load_source,
        )

    # ------------------------------------------------------------------ #
    # status — best candidate + recent ledger + budget quota (agent-facing).
    # ------------------------------------------------------------------ #

    def status(self) -> dict[str, Any]:
        """Best logged candidate + recent ledger rows + the budget as a QUOTA (FR-E5).

        The budget is reported as ``looks_remaining`` (a quota), NEVER a countdown the agent
        should pause on. The "best" candidate is the feasible row with the highest OOS ``rank_sharpe``
        — a ranking over the ledger, not a hill-climb pointer.
        """
        rows = self._ledger.rows()
        budget = self._budget.status()
        feasible = [r for r in rows if r.res.feasible and r.res.rank_sharpe is not None]
        best = max(feasible, key=lambda r: float(r.res.rank_sharpe), default=None)  # type: ignore[arg-type]
        return {
            "best_candidate": None if best is None else _row_summary(best),
            "recent_ledger": [_row_summary(r) for r in rows[-5:]],
            "n_logged": len(rows),
            "budget": {
                "cap": budget.cap,
                "looks_charged": budget.charged,
                "looks_remaining": budget.remaining,
                "spent": budget.spent,
            },
            # A QUOTA state, never a countdown: the loop runs until the harness ends the session
            # (budget spent) or a human interrupts (FR-A1/E5).
            "session": "budget_spent" if budget.spent else "active",
        }

    # ------------------------------------------------------------------ #
    # run — Train quick run (FREE, unlimited; never a look).
    # ------------------------------------------------------------------ #

    def run(self, experiment: Experiment, *, desc: str) -> RunResult:
        """Train quick run: causal diagnostic + coarse plausibility band. FREE, unlimited.

        Returns the band (positive/negative/flat/infeasible) + validity + the computed family id
        (so the agent sees whether this idea is structurally new). Spends NO look and writes NO
        ledger row — Train is the free sandbox (enforcement #4). ``desc`` is the thesis (logged
        only if the idea later escalates).
        """
        band = train_plausibility(experiment, self._protocol, self._train_window, self._gateway)
        source = self._load_source(experiment.strategy_path)
        from harness.family import compute_family_id

        family_id = compute_family_id(source)
        is_new = family_id not in {r.family_id for r in self._ledger.rows()}
        return RunResult(
            valid=bool(band["valid"]),
            causal_ok=bool(band["causal_ok"]),
            plausibility_band=str(band["plausibility_band"]),
            trade_count=int(band["trade_count"]),
            family_id=family_id,
            is_new_family=is_new,
            slices=band["slices"],
            failure_stage=band["failure_stage"],
        )

    # ------------------------------------------------------------------ #
    # evaluate — Selection: the MECHANICAL gate + budget, then the logged bet.
    # ------------------------------------------------------------------ #

    def evaluate(
        self,
        experiment: Experiment,
        *,
        desc: str,
        trial_id: str,
        created_at: str,
        cost_stress: bool = True,
    ) -> EvaluateLogged | EvaluateRefused:
        """Apply the escalation gate + budget; ONLY if both pass, run RES and LOG the bet.

        Order (mechanical, so the contract holds by construction):

        1. Run the Train quick run; apply the **escalation gate** (``evaluate_escalation``). If it
           routes to Train (invalid / dead / negative / thesis-free-nudge / single-symbol /
           knife-edge / swing-big-required), REFUSE — no look, no row (FR-D1).
        2. Check the **budget**. If spent, REFUSE with the quota message — no look, no row (FR-E5).
        3. ``SelectionController.take_look`` — reserve → walk-forward RES → finalize the row. This
           is the logged bet; it is NEVER a "keep if the score rose" step (FR-D3, AC-8). Each
           ``evaluate`` of a tweak spends from the same global budget — re-evaluating to push a
           number up just burns the quota.

        ``desc`` is the thesis (effect | falsifier). ``trial_id``/``created_at`` are injected.
        """
        source = self._load_source(experiment.strategy_path)
        logged_families = [r.family_id for r in self._ledger.rows()]
        decision = evaluate_escalation(
            experiment,
            self._protocol,
            self._train_window,
            self._gateway,
            strategy_source=source,
            logged_family_ids=logged_families,
            # The cadence counter is the SESSION's idea count (it includes free Train runs), not a
            # ledger-derived count — every logged look is already a new family, so a ledger count
            # would be permanently 0 and swing-big would never bite (see SessionMarker).
            ideas_since_new_family=self._ideas_since_new_family,
            swing_big_every=self._swing_big_every,
        )

        # --- 1. The gate is MECHANICAL: a routed candidate never reaches Selection. ---
        if not decision.may_escalate:
            return EvaluateRefused(
                kind="routed_to_train",
                reason=decision.reason,
                family_id=decision.family_id,
                escalation=decision,
            )

        # --- 2. The budget is MECHANICAL: a passed gate does not ENTITLE a look (FR-E5). ---
        if not self._budget.can_reserve():
            return EvaluateRefused(
                kind="budget_spent",
                reason=(
                    f"global Selection budget spent ({self._budget.cap} looks charged) — "
                    "graduate the best or move on; this is a quota, not a rejection (FR-E5)"
                ),
                family_id=decision.family_id,
                escalation=decision,
            )

        # --- 3. Run RES and LOG the bet (one Selection look spent). ---
        look = self._controller.take_look(
            experiment,
            self._protocol,
            desc,
            trial_id=trial_id,
            created_at=created_at,
            cost_stress=cost_stress,
        )
        if isinstance(look, NoLookAvailable):
            # The budget was spent between the check and the reservation (a race the controller
            # also guards). Surface the quota state — still no row written for this trial.
            return EvaluateRefused(
                kind="budget_spent",
                reason=look.reason,
                family_id=look.family_id,
                escalation=decision,
            )
        return EvaluateLogged(
            row=look.row,
            family_id=look.family_id,
            escalation=decision,
            looks_remaining=self._budget.remaining(),
        )


# --------------------------------------------------------------------------- #
# Admin helpers (profile / graduate / lockbox) — pure compositions over the harness.
# --------------------------------------------------------------------------- #


def profile_campaign(
    return_proxy: np.ndarray,
    protocol: Protocol,
    *,
    claimed_edge: float,
    cross_section_legs: Mapping[str, np.ndarray] | None = None,
    lockbox_periods: int,
) -> tuple[AssetProfile, SufficiencyVerdict]:
    """``profile``: the Asset Profiler + the data-sufficiency gate (FR-G).

    Returns the derived ``AssetProfile`` (budget upper bound, sizing, Lockbox MDE) and the
    ``SufficiencyVerdict`` (admissible / insufficient_evidence) for a claimed edge. The harness
    never lowers the bar to manufacture a verdict (FR-G2, AC-5).
    """
    profile = profile_asset(
        return_proxy,
        cross_section_legs=cross_section_legs,
        lockbox_periods=lockbox_periods,
        periods_per_year=protocol.annualization.periods_per_year,
    )
    verdict = assess_sufficiency(profile, claimed_edge)
    return profile, verdict


def graduate_decision(ledger: TrialLedger, protocol: Protocol, *, top_k: int):
    """``graduate``: run the returns-based audit over ALL logged trials + the top-K rule (FR-F1/F3).

    Pure over the durable ledger (no live data): runs ``run_graduation_audit`` over every finalized
    row, then ``select_graduates`` (feasible ∧ PSR-passed ∧ top-K-by-Sharpe ∧ audit-survived). The
    harness EMITS the ``GraduationDecision`` — it never promotes; confirming a graduate on the
    Lockbox and promotion above it are separate (human-gated) steps.
    """
    from harness.audit import run_graduation_audit
    from harness.graduation import select_graduates

    rows = ledger.rows()
    audit = run_graduation_audit(rows, protocol.content_hash)
    return select_graduates(rows, audit, top_k=top_k)


# --------------------------------------------------------------------------- #
# Row / window helpers.
# --------------------------------------------------------------------------- #


def _row_summary(row: LedgerRow) -> dict[str, Any]:
    """A compact, agent-readable summary of one ledger row (status / observability)."""
    return {
        "trial_id": row.trial_id,
        "family_id": row.family_id[:12],
        "thesis": row.thesis,
        "feasible": row.res.feasible,
        "rank_sharpe": row.res.rank_sharpe,
        "created_at": row.created_at,
    }


def _train_window(protocol: Protocol) -> FoldWindowSpan:
    """The Train-tier window the quick run / stability gate evaluate over (the free sandbox).

    Duck-types ``FoldWindowSpan``/``FoldWindow`` (``window_id``/``start``/``end``) so the same
    gateway seam consumes it. Train is one window for the cheap diagnostic (not a walk-forward).
    """
    train = protocol.data_tiers.train
    return FoldWindowSpan(window_id="train", start=train.start, end=train.end)


def _read_source(strategy_path: str) -> str:
    p = Path(strategy_path)
    if not p.is_file():
        from harness.family import FamilyError

        raise FamilyError(f"strategy file not found: {p}")
    return p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The real entry point — constructs the RealFoundationGateway LAZILY (boundary).
# --------------------------------------------------------------------------- #


def _build_real_gateway(repo_root: str | Path):
    """Construct the RealFoundationGateway. Imported HERE (lazily) so importing ``harness.cli``
    never pulls in ``quant_strategies`` (the seam test asserts only ``foundation_real`` imports
    the engine). Tests never call this — they inject the Fake gateway into ``HarnessCLI``."""
    from harness.foundation_real import RealFoundationGateway

    return RealFoundationGateway(repo_root)


def _load_experiment(path: str | Path) -> Experiment:
    """Load the agent-editable Experiment surface from ``experiment.toml`` (strategy + params)."""
    import tomllib

    p = Path(path)
    with p.open("rb") as fh:
        payload = tomllib.load(fh)
    return Experiment.model_validate(payload)


def main(argv: list[str] | None = None) -> int:
    """Admin/agent CLI entry point. Constructs the real harness (lazy real gateway) and dispatches.

    Agent commands: ``status`` | ``run --desc`` | ``evaluate --desc``. Admin: ``profile`` |
    ``graduate`` | ``lockbox`` (these read the durable ledger/book; full wiring of profile/graduate/
    lockbox to live ``quant_data`` is the operator's campaign harness — here ``status``/``run``/
    ``evaluate`` are the mechanically-enforced agent loop).
    """
    import datetime as _dt
    import uuid as _uuid

    parser = argparse.ArgumentParser(prog="python -m harness.cli")
    parser.add_argument(
        "command",
        choices=("status", "run", "evaluate", "graduate"),
        help="agent: status|run|evaluate; admin: graduate (audit + top-K over the ledger)",
    )
    parser.add_argument("--desc", default="", help="the falsifiable causal thesis (| falsifier: …)")
    parser.add_argument("--protocol", default="protocol.toml")
    parser.add_argument("--experiment", default="experiment.toml")
    parser.add_argument("--ledger", default="ledger.jsonl")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--top-k", type=int, default=3, help="Lockbox ration for `graduate`")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    protocol = load_protocol(repo_root / args.protocol)
    ledger = TrialLedger(repo_root / args.ledger)

    budget = BudgetManager(protocol.budget.max_selection_looks, ledger)

    # Ledger-only admin/agent commands need no gateway (and so no engine import): status + graduate.
    if args.command == "graduate":
        decision = graduate_decision(ledger, protocol, top_k=args.top_k)
        print(json.dumps(_graduate_json(decision), indent=2, sort_keys=True, default=str))
        return 0

    # The swing-big cadence counter lives in the session marker (it counts free Train runs too).
    from harness.session import (
        SessionMarker,
        advance_idea,
        read_session_marker,
        write_session_marker,
    )

    marker = read_session_marker(repo_root) or SessionMarker(
        ledger_path=str(args.ledger), book_path="lockbox_book.json", protocol_hash=protocol.content_hash,
    )

    # status reads only the ledger/budget; build the CLI with the (lazy) real gateway uniformly so
    # run/evaluate share one construction. The gateway is constructed lazily so importing this
    # module never pulls in the engine; running it does.
    gateway = _build_real_gateway(repo_root)
    cli = HarnessCLI(
        gateway=gateway, protocol=protocol, ledger=ledger, budget=budget,
        ideas_since_new_family=marker.ideas_since_new_family,
    )

    if args.command == "status":
        print(json.dumps(cli.status(), indent=2, sort_keys=True, default=str))
        return 0

    experiment = _load_experiment(repo_root / args.experiment)
    if args.command == "run":
        out = cli.run(experiment, desc=args.desc)
        # A Train run is an idea — advance the swing-big cadence (never resets it).
        write_session_marker(repo_root, advance_idea(marker, logged_new_family=False))
        print(json.dumps(_runresult_json(out), indent=2, sort_keys=True, default=str))
        return 0

    # evaluate
    trial_id = _uuid.uuid4().hex
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    result = cli.evaluate(experiment, desc=args.desc, trial_id=trial_id, created_at=created_at)
    # A logged NEW-family bet resets the cadence (the agent swung); any other idea advances it.
    logged_new = isinstance(result, EvaluateLogged) and (result.escalation.is_new_family)
    write_session_marker(repo_root, advance_idea(marker, logged_new_family=logged_new))
    print(json.dumps(_evaluate_json(result), indent=2, sort_keys=True, default=str))
    # A refusal is not an error exit — it is a normal mechanical outcome (routed to Train / quota).
    return 0


def _graduate_json(decision) -> dict[str, Any]:
    return {
        "command": "graduate",
        "graduates": list(decision.graduates),
        "top_k": decision.top_k,
        "n_audited": decision.audit.n_trials,
        "audit_survivors": list(decision.audit.survivors),
        "note": "the harness EMITS this verdict; it never promotes (FR-F3).",
    }


def _runresult_json(out: RunResult) -> dict[str, Any]:
    return {
        "command": "run",
        "valid": out.valid,
        "causal_ok": out.causal_ok,
        "plausibility_band": out.plausibility_band,
        "trade_count": out.trade_count,
        "family_id": out.family_id[:12],
        "is_new_family": out.is_new_family,
        "note": "Train is FREE and unlimited; this spent no Selection look.",
    }


def _evaluate_json(result: EvaluateLogged | EvaluateRefused) -> dict[str, Any]:
    if isinstance(result, EvaluateRefused):
        return {
            "command": "evaluate",
            "outcome": "refused",
            "kind": result.kind,
            "reason": result.reason,
            "family_id": result.family_id[:12],
            "look_spent": False,
        }
    return {
        "command": "evaluate",
        "outcome": "logged",
        "trial_id": result.row.trial_id,
        "family_id": result.family_id[:12],
        "feasible": result.row.res.feasible,
        "rank_sharpe": result.row.res.rank_sharpe,
        "looks_remaining": result.looks_remaining,
        "note": "a LOGGED bet, not a hill-climb step (FR-D3); the budget is a quota.",
    }


if __name__ == "__main__":
    sys.exit(main())
