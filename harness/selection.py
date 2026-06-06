"""Selection-look controller — where budget + ledger + family compose (FR-E1/E2/E5, I1/I2).

A Selection look is the campaign's scarce, logged bet. This controller is the single path that
ties the three P3 pieces together so the contract holds *by construction*:

1. compute the **family id** from the strategy source (FR-E4) — the unforgeable budget key;
2. check the **global budget** (FR-E2/E5): if spent, return ``NoLookAvailable`` and issue nothing
   (the agent is never handed a countdown — "no more looks" is a quota state);
3. **reserve** the look in the ledger BEFORE running (FR-I2/NFR-6) — from here it is charged, so a
   crash mid-run cannot yield a silent un-ledgered look;
4. run the P2 **walk-forward RES** (one ``evaluate`` per fold);
5. **finalize** the append-only ledger row with the full per-fold returns + ``ResResult`` +
   measurement fingerprint (FR-E1/I1) — reproducible bit-for-bit (AC-7).

Because the family id is computed from code (not the thesis) and the budget is keyed only to the
global charged count, relabeling a thesis or splitting one signal by param-tweaks cannot raise the
number of looks a campaign can run (AC-2), and re-evaluating tweaks each spends from the same
global budget until it is spent (AC-8).

Pure of ``quant_strategies``: depends on the ``FoundationGateway`` seam (real adapter or fake),
the ledger, the budget, and the family/experiment hashers. ``trial_id`` and ``created_at`` are
INJECTED by the caller (the harness shell), never read from a clock here (NFR-1).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from harness.budget import BudgetManager
from harness.family import compute_family_id
from harness.foundation import FoundationGateway
from harness.ledger import LedgerRow, TrialLedger
from harness.objective.res import GateThresholds
from harness.orchestrator import (
    FactorPanelProvider,
    WalkForwardRES,
    run_walk_forward_res,
)
from harness.protocol import Experiment, Protocol


def experiment_hash(experiment: Experiment, *, strategy_source: str) -> str:
    """Deterministic hash of the Experiment: the strategy SOURCE + the params + symbols (FR-I1).

    Hashing the source (not just the path) makes the fingerprint reproduce the *exact* code that
    was measured (AC-7), and makes two different strategy files distinguishable even at the same
    path. Params/symbols are canonicalized (sorted keys) so equal experiments hash equally.
    """
    canonical = json.dumps(
        {
            "strategy_path": experiment.strategy_path,
            "strategy_source_sha256": hashlib.sha256(strategy_source.encode("utf-8")).hexdigest(),
            "params": experiment.params,
            "symbols": list(experiment.symbols) if experiment.symbols is not None else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NoLookAvailable:
    """Returned when the global budget is spent — the harness issues no look (FR-E5).

    Not an error and not a per-call rejection the agent can probe around: it is the quota state.
    The campaign graduates the best logged candidate or retires; it never gets more looks by
    relabeling (the cap is global) — see ``BudgetStatus`` for the numbers (operator-facing).
    """

    family_id: str
    reason: str = "global Selection budget spent (FR-E5)"


@dataclass(frozen=True)
class LookResult:
    """A completed Selection look: the logged row + the orchestrated RES + the family id."""

    row: LedgerRow
    walk_forward: WalkForwardRES
    family_id: str


class SelectionController:
    """Drives one Selection look end-to-end, enforcing budget + ledger + family.

    ``strategy_source_loader`` reads a strategy file's source given its path (defaults to reading
    from disk); injecting it keeps the controller unit-testable without a real file. The budget is
    enforced against the same ledger the controller writes, so consumption can never disagree with
    what was logged.
    """

    def __init__(
        self,
        *,
        ledger: TrialLedger,
        budget: BudgetManager,
        gateway: FoundationGateway,
        factor_panel_provider: FactorPanelProvider,
        strategy_source_loader=None,
    ) -> None:
        self._ledger = ledger
        self._budget = budget
        self._gateway = gateway
        self._panel_provider = factor_panel_provider
        self._load_source = strategy_source_loader or _read_source

    def take_look(
        self,
        experiment: Experiment,
        protocol: Protocol,
        thesis: str,
        *,
        trial_id: str,
        created_at: str,
        reserved_at: str | None = None,
        dataset_id: str | None = None,
        thresholds: GateThresholds | None = None,
        cost_stress: bool = True,
    ) -> LookResult | NoLookAvailable:
        """Take one Selection look (or report the budget is spent).

        Steps (in order, so the invariants hold by construction): compute family id → check budget
        → reserve (charge) → run walk-forward RES → finalize the row. ``trial_id``/``created_at``
        are injected; ``reserved_at`` defaults to ``created_at`` (the reservation timestamp).
        """
        source = self._load_source(experiment.strategy_path)
        family_id = compute_family_id(source)

        # FR-E5: the budget is keyed only to the global charged count, never to family — so a fresh
        # label cannot create headroom (AC-2). If spent, issue nothing.
        if not self._budget.can_reserve():
            return NoLookAvailable(family_id=family_id)

        exp_hash = experiment_hash(experiment, strategy_source=source)
        proto_hash = protocol.content_hash

        # Reserve BEFORE running: from here the look is charged. A crash in run_walk_forward_res
        # leaves the reservation durable (the look counts), never a silent un-ledgered look.
        reservation = self._ledger.reserve(
            trial_id=trial_id,
            family_id=family_id,
            experiment_hash=exp_hash,
            protocol_hash=proto_hash,
            thesis=thesis,
            reserved_at=reserved_at or created_at,
            dataset_id=dataset_id,
        )

        walk_forward = run_walk_forward_res(
            experiment,
            protocol,
            self._gateway,
            self._panel_provider,
            thresholds=thresholds,
            cost_stress=cost_stress,
        )

        # The per-fold OOS returns of EVERY trial are logged (FR-E1) — the audit (P4) needs them.
        per_fold_returns = [
            r.returns for r in walk_forward.fold_results if r.succeeded and r.returns is not None
        ]
        provenance = _merge_provenance(walk_forward)

        row = self._ledger.finalize(
            reservation,
            per_fold_returns=per_fold_returns,
            res=walk_forward.res,
            provenance=provenance,
            created_at=created_at,
        )
        return LookResult(row=row, walk_forward=walk_forward, family_id=family_id)


def _read_source(strategy_path: str) -> str:
    p = Path(strategy_path)
    if not p.is_file():
        from harness.family import FamilyError

        raise FamilyError(f"strategy file not found for family fingerprint: {p}")
    return p.read_text(encoding="utf-8")


def _merge_provenance(walk_forward: WalkForwardRES) -> dict[str, str]:
    """The measurement fingerprint for the row (FR-I1).

    All folds in one look share a campaign-pinned snapshot + foundation/backend versions (FR-I2),
    so the per-fold provenance is identical; we take the first succeeded fold's. If no fold
    succeeded, the row still records an empty provenance (the look ran and is logged either way).
    """
    for r in walk_forward.fold_results:
        if r.succeeded and r.provenance:
            return dict(r.provenance)
    return {}
