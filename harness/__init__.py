"""The immutable evaluator (the harness the agent cannot edit).

Rigor lives here; simplicity lives in the agent's one-page contract. P1 ships the
judgment skeleton: the Protocol/Experiment wall, the Robust Edge Score (residual-alpha
Sharpe at frozen exposure), the Stage-1 feasibility gates (effective-breadth), the
computed stability gate, and the ``FoundationGateway`` testability seam.

The judgment layer depends ONLY on ``harness.foundation`` — never on ``quant_strategies``.
"""

from __future__ import annotations
