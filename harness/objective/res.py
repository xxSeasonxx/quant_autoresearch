"""Robust Edge Score (RES) — the one honest number the agent ranks on.

RES is computed on OOS Selection folds at FIXED normalized exposure (sizing frozen,
FR-C1). It:

1. Neutralizes each fold against the factor panel (market/momentum/funding-carry/size)
   and scores the **residual** — market beta AND factor beta are not edge; funding is
   carry, regressed out (FR-C3). See ``factors``.
2. Computes the **per-fold Sharpe of the residual** series as the unit of evidence
   (FR-C4), and ranks on the pooled residual Sharpe (FR-C2).
3. Composes the Stage-1 feasibility gates (P1 subset: evidence proxy + concentration +
   correlation-aware effective-breadth). Fail any ⇒ infeasible (FR-C5).

The per-row RES is **NOT deflated** (FR-C6): selection-bias correction lives in the
budget (prevent, P3), the audit (correct, P4), and the Lockbox (confirm, P4) — never in
the row, so each row stays stable and reproducible.

Sizing is frozen *at the seam*: ``FoldReturns.values`` are returns at a fixed normalized
exposure, so any uniform leverage scaling leaves the (residual) Sharpe unchanged. RES
therefore cannot be raised by leverage (AC-1 partial).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from harness.foundation import FoldReturns
from harness.objective import factors, metrics
from harness.objective.gates import (
    GateOutcome,
    concentration_gate,
    effective_breadth_gate,
    evidence_gate,
)


@dataclass(frozen=True)
class ResResult:
    """The RES of one candidate (shared type, harness-architecture §3)."""

    feasible: bool  # all Stage-1 gates passed
    gate_results: Mapping[str, GateOutcome]  # name -> pass/fail + value + threshold
    rank_sharpe: float | None  # the ranking number: residual-alpha Sharpe, OOS, undeflated
    per_fold_sharpe: tuple[float, ...]  # the evidence unit (FR-C4)
    residual_info_ratio: float | None  # after factor-panel regression (FR-C3)
    psr: float | None  # PSR helper value (the PSR *gate* is P2); None in P1 by default


@dataclass(frozen=True)
class GateThresholds:
    """Protocol-owned Stage-1 thresholds (P1 subset)."""

    min_trades: int
    max_concentration: float
    min_effective_breadth: float


def _pool_residual_by_symbol(
    folds: Sequence[FoldReturns],
    factor_panels: Sequence[Mapping[str, np.ndarray]],
) -> dict[str, FoldReturns] | None:
    """Pool the **factor-neutralized** per-symbol legs across folds for the gates.

    The concentration and effective-breadth gates measure the breadth of the *edge*, not
    of raw market-correlated returns. In crypto every leg co-moves on BTC, so breadth on
    RAW returns would bounce even a genuinely diversified alpha basket. Computing breadth
    on the RESIDUAL (market/factor-neutralized) legs distinguishes independent alpha bets
    (high N_eff) from the same-coin "ADA-disguised-as-basket" trick (legs whose residuals
    are still identical ⇒ N_eff ≈ 1). Each leg is residualized against its own fold's panel
    before pooling.

    Returns ``None`` if no fold carries a per-symbol decomposition.
    """
    have = [f.by_symbol for f in folds if f.by_symbol]
    if not have:
        return None
    symbols: set[str] = set()
    for bs in have:
        symbols.update(bs.keys())
    pooled: dict[str, FoldReturns] = {}
    for sym in symbols:
        parts_v = []
        parts_t = []
        ppy = None
        for fold, panel in zip(folds, factor_panels):
            if fold.by_symbol and sym in fold.by_symbol:
                leg = fold.by_symbol[sym]
                resid_leg = factors.residual_fold_returns(leg, panel)
                parts_v.append(np.asarray(resid_leg.values, dtype=np.float64))
                parts_t.append(np.asarray(resid_leg.timestamps))
                ppy = leg.periods_per_year
        if parts_v:
            pooled[sym] = FoldReturns(
                timestamps=np.concatenate(parts_t),
                values=np.concatenate(parts_v),
                periods_per_year=float(ppy) if ppy is not None else 1.0,
            )
    return pooled


def compute_res(
    folds: Sequence[FoldReturns],
    factor_panels: Sequence[Mapping[str, np.ndarray]],
    trade_count: int,
    thresholds: GateThresholds,
    *,
    psr_benchmark: float = 0.0,
) -> ResResult:
    """Compute RES over a sequence of OOS folds and their aligned factor panels.

    ``factor_panels[i]`` is the panel for ``folds[i]`` (factor-return columns aligned to
    that fold). Pass empty mappings for an identity (no neutralization) — but the honest
    path always supplies the panel so beta/funding-carry are removed.
    """
    if len(folds) != len(factor_panels):
        raise ValueError("folds and factor_panels must be the same length")

    # --- Residualize each fold and compute the per-fold residual Sharpe (evidence unit) ---
    residual_folds: list[FoldReturns] = []
    per_fold_sharpe: list[float] = []
    for fold, panel in zip(folds, factor_panels):
        res_fold = factors.residual_fold_returns(fold, panel)
        residual_folds.append(res_fold)
        s = metrics.sharpe(res_fold)
        if s is not None:
            per_fold_sharpe.append(s)

    # Pool the residual series for the ranking Sharpe and the IR.
    pooled_residual = (
        np.concatenate([np.asarray(rf.values, dtype=np.float64) for rf in residual_folds])
        if residual_folds
        else np.empty(0)
    )
    ppy = residual_folds[0].periods_per_year if residual_folds else 1.0
    pooled_fr = FoldReturns(
        timestamps=np.concatenate([np.asarray(rf.timestamps) for rf in residual_folds])
        if residual_folds
        else np.empty(0, dtype="datetime64[ns]"),
        values=pooled_residual,
        periods_per_year=ppy,
    )
    rank_sharpe = metrics.sharpe(pooled_fr)
    residual_ir = factors._information_ratio(pooled_residual)
    psr = metrics.probabilistic_sharpe_ratio(pooled_fr, benchmark_sharpe=psr_benchmark)

    # --- Stage-1 feasibility gates (hard, binary) — measured on the RESIDUAL legs ---
    pooled_symbols = _pool_residual_by_symbol(folds, factor_panels)
    gate_list = [
        evidence_gate(trade_count, thresholds.min_trades),
        concentration_gate(pooled_symbols, thresholds.max_concentration),
        effective_breadth_gate(pooled_symbols, thresholds.min_effective_breadth),
    ]
    gate_results = {g.name: g for g in gate_list}
    feasible = all(g.passed for g in gate_list)

    # An infeasible candidate has no ranking number — it cannot be ranked or graduate.
    # A residual with no usable variance (pure factor beta) also has no rank.
    effective_rank = rank_sharpe if feasible else None

    return ResResult(
        feasible=feasible,
        gate_results=gate_results,
        rank_sharpe=effective_rank,
        per_fold_sharpe=tuple(per_fold_sharpe),
        residual_info_ratio=residual_ir,
        psr=psr,
    )
