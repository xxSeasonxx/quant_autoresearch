"""The Robust Edge Score (RES) objective and its Stage-1 feasibility gates.

- ``metrics``: Sharpe / Sortino / Calmar / max-drawdown (+ PSR helper) over ``FoldReturns``.
- ``factors``: factor-panel residual alpha (funding-as-carry).
- ``gates``: Stage-1 feasibility gates (P1 subset: evidence proxy + concentration +
  correlation-aware effective-breadth).
- ``res``: composes the above into a ``ResResult`` (rank-on-Sharpe of the residual, undeflated).
"""

from __future__ import annotations
