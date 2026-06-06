"""The Foundation seam — the linchpin that isolates judgment from the engine.

The judgment layer (objective, gates, stability) depends ONLY on the
``FoundationGateway`` protocol and the typed result objects below. It MUST NOT
import ``quant_strategies``. This is Dependency Inversion (FR-J1) and the literal
expression of AC-10 ("per-fold OOS returns via a typed foundation API, no Parquet
scraping"); it is what makes AC-1 / AC-6 / AC-9 / AC-4 deterministically testable
with synthetic returns through a ``FakeFoundationGateway`` (see ``harness.testing``).

numpy in the core, pandas only at the real adapter (``RealFoundationGateway``, P2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol as TypingProtocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class FoldReturns:
    """Per-fold OOS return series at FIXED normalized exposure (sizing frozen).

    The contract that ``values`` are returns at a fixed normalized exposure is what
    freezes sizing at the seam: any uniform leverage scaling multiplies numerator
    and denominator of Sharpe identically, so RES cannot be raised by leverage
    (FR-C1). The harness never asks the strategy to size; sizing is a downstream
    decision after a real edge is confirmed.
    """

    timestamps: np.ndarray  # datetime64[ns], strictly increasing
    values: np.ndarray  # float64 per-period returns (net of costs)
    periods_per_year: float  # annualization cadence (matches bar cadence)
    # Per-symbol decomposition for the concentration / effective-breadth gates.
    by_symbol: Mapping[str, "FoldReturns"] | None = None


@dataclass(frozen=True)
class QuickRunResult:
    """Train quick run (free, unlimited) — Tier-0 causal diagnostic + coarse band."""

    valid: bool  # passed causal replay + decision contract
    causal_ok: bool
    in_sample_metric: float | None  # coarse plausibility, AFTER costs (None if infeasible)
    trade_count: int
    # Cheap-robust slices keyed by the foundation's real diagnostic axes, e.g.
    # {"by_symbol": {...}, "by_direction": {...}, "by_exit_reason": {...}}; each axis maps a
    # group name to its scalar summary. by_symbol is the leg the breadth/concentration logic
    # reads. (The foundation emits no calendar by_month/by_hour axis.)
    slices: Mapping[str, Mapping[str, float]]
    failure_stage: str | None


@dataclass(frozen=True)
class FoldEvalResult:
    """One Selection fold or the Lockbox (the result of one ``evaluate`` call)."""

    succeeded: bool
    causal_ok: bool
    returns: FoldReturns | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float | None
    trade_count: int
    worst_period_return: float | None
    provenance: Mapping[str, str]  # snapshot id, foundation+backend versions (FR-I1)
    failure_stage: str | None


@runtime_checkable
class FoundationGateway(TypingProtocol):
    """The seam. Implementations:

    - ``RealFoundationGateway`` (P2): adapts ``quant_strategies.runner.run_config``
      (quick_run) and ``quant_strategies.evaluation.run_evaluation`` (evaluate),
      reading per-fold returns through the P0 typed accessor (never Parquet scraping).
    - ``FakeFoundationGateway`` (P1, ``harness.testing``): returns injected synthetic
      results. The entire judgment layer is tested through it.

    The harness owns fold orchestration; ``evaluate`` is called once per fold (FR-J2).
    ``window`` is a ``(start, end)`` span the harness derives from the Protocol tiers
    and the walk-forward schedule (P2).
    """

    def quick_run(self, experiment, protocol, window) -> QuickRunResult: ...

    def evaluate(self, experiment, protocol, window) -> FoldEvalResult: ...
