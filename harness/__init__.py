"""The immutable evaluator (the harness the agent cannot edit).

Rigor lives here; simplicity lives in the agent's one-page contract. The judgment
skeleton: the Protocol/Experiment wall, the Robust Edge Score (residual-alpha Sharpe at
frozen exposure), the Stage-1 feasibility gates (effective-breadth), the computed
stability gate, and the ``FoundationGateway`` testability seam (P1); the data tiers,
walk-forward, write-once Lockbox, and Asset Profiler (P2); the append-only Trial Ledger,
computed Family Identifier, global MinBTL Budget Manager, and the Selection-look controller
that ties them together (P3); the returns-based Graduation Auditor + power-aware Lockbox +
top-K graduation rule (P4); and the harness-enforced Escalation Controller, the agent + admin
CLI, and the never-early-stop session shell (P5) — closing the loop so search is honestly
bounded, unforgeable, and the agent contract stays a one-page loop.

The judgment layer depends ONLY on ``harness.foundation`` — never on ``quant_strategies``;
the single sanctioned boundary crosser is ``harness.foundation_real`` (the real adapter).
"""

from __future__ import annotations
