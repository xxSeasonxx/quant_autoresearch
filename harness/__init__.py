"""The immutable evaluator (the harness the agent cannot edit).

Rigor lives here; simplicity lives in the agent's one-page contract. The judgment
skeleton: the Protocol/Experiment wall, the Robust Edge Score (residual-alpha Sharpe at
frozen exposure), the Stage-1 feasibility gates (effective-breadth), the computed
stability gate, and the ``FoundationGateway`` testability seam (P1); the data tiers,
walk-forward, write-once Lockbox, and Asset Profiler (P2); and the append-only Trial
Ledger, computed Family Identifier, global MinBTL Budget Manager, and the Selection-look
controller that ties them together (P3) — making search honestly bounded and unforgeable.

The judgment layer depends ONLY on ``harness.foundation`` — never on ``quant_strategies``.
"""

from __future__ import annotations
