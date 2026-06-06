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
    cost_stress_gate,
    effective_breadth_gate,
    evidence_gate,
    max_drawdown_gate,
    psr_gate,
    worst_fold_gate,
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
    """Protocol-owned Stage-1 thresholds.

    The first three (the cheap P1 gates) are required positionally; the four OOS-gate
    thresholds default to values that pass a genuine positive-drift residual edge and bounce
    their respective failure modes, so the existing 3-field positional construction is
    unchanged while the real path supplies all seven.
    """

    min_trades: int
    max_concentration: float
    min_effective_breadth: float
    psr_floor: float = 0.95
    max_drawdown_ceiling: float = 0.35
    worst_fold_floor: float = 0.0
    dispersion_ceiling: float = 3.0
    cost_stress_ratio: float = 0.5

    @classmethod
    def from_protocol(cls, spec) -> "GateThresholds":
        """Build from a Protocol ``GateThresholdSpec`` so all seven thresholds come from the
        harness-owned Protocol (never agent-editable)."""
        return cls(
            min_trades=spec.min_trades,
            max_concentration=spec.max_concentration,
            min_effective_breadth=spec.min_effective_breadth,
            psr_floor=spec.psr_floor,
            max_drawdown_ceiling=spec.max_drawdown_ceiling,
            worst_fold_floor=spec.worst_fold_floor,
            dispersion_ceiling=spec.dispersion_ceiling,
            cost_stress_ratio=spec.cost_stress_ratio,
        )


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


def _pooled_residual_fr(
    folds: Sequence[FoldReturns],
    factor_panels: Sequence[Mapping[str, np.ndarray]],
) -> tuple[FoldReturns, list[float | None]]:
    """Residualize each fold; return the pooled residual series + the per-fold Sharpe list.

    The per-fold Sharpe list is **aligned to folds** and carries ``None`` for a degenerate
    (near-zero-variance / non-finite) fold, so the worst-fold gate can treat such a fold as
    a failing fold rather than silently dropping it (the ``_EPS`` carry, FR-C5).
    """
    residual_folds: list[FoldReturns] = []
    per_fold_aligned: list[float | None] = []
    for fold, panel in zip(folds, factor_panels):
        res_fold = factors.residual_fold_returns(fold, panel)
        residual_folds.append(res_fold)
        per_fold_aligned.append(metrics.sharpe(res_fold))
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
    return pooled_fr, per_fold_aligned


def compute_res(
    folds: Sequence[FoldReturns],
    factor_panels: Sequence[Mapping[str, np.ndarray]],
    trade_count: int,
    thresholds: GateThresholds,
    *,
    psr_benchmark: float = 0.0,
    stressed_folds: Sequence[FoldReturns] | None = None,
    stressed_factor_panels: Sequence[Mapping[str, np.ndarray]] | None = None,
) -> ResResult:
    """Compute RES over a sequence of OOS folds and their aligned factor panels.

    ``factor_panels[i]`` is the panel for ``folds[i]`` (factor-return columns aligned to
    that fold). Pass empty mappings for an identity (no neutralization) — but the honest
    path always supplies the panel so beta/funding-carry are removed.

    ``stressed_folds`` (optional) is the same folds re-evaluated under STRESSED costs — the
    evidence for the cost-stress survival gate. When supplied, the cost-stress gate is part
    of the Stage-1 set; when absent (a pure-logic call with no stressed evidence) the
    cost-stress question was not asked, so that single gate is omitted from the list (it is
    not silently passed). The real orchestrator ALWAYS supplies it. ``stressed_factor_panels``
    defaults to ``factor_panels`` (the same panel, since residual alpha is what survives
    costs).
    """
    if len(folds) != len(factor_panels):
        raise ValueError("folds and factor_panels must be the same length")

    pooled_fr, per_fold_aligned = _pooled_residual_fr(folds, factor_panels)
    per_fold_sharpe = [s for s in per_fold_aligned if s is not None]  # measurable evidence unit
    rank_sharpe = metrics.sharpe(pooled_fr)
    residual_ir = factors._information_ratio(np.asarray(pooled_fr.values, dtype=np.float64))
    psr = metrics.probabilistic_sharpe_ratio(pooled_fr, benchmark_sharpe=psr_benchmark)
    residual_max_dd = metrics.max_drawdown(pooled_fr)

    # --- Stage-1 feasibility gates (hard, binary) — measured on the RESIDUAL legs ---
    pooled_symbols = _pool_residual_by_symbol(folds, factor_panels)
    gate_list = [
        evidence_gate(trade_count, thresholds.min_trades),
        psr_gate(psr, thresholds.psr_floor),
        concentration_gate(pooled_symbols, thresholds.max_concentration),
        effective_breadth_gate(pooled_symbols, thresholds.min_effective_breadth),
        max_drawdown_gate(residual_max_dd, thresholds.max_drawdown_ceiling),
        worst_fold_gate(
            per_fold_aligned, thresholds.worst_fold_floor, thresholds.dispersion_ceiling
        ),
    ]
    if stressed_folds is not None:
        s_panels = stressed_factor_panels if stressed_factor_panels is not None else factor_panels
        stressed_pooled, _ = _pooled_residual_fr(stressed_folds, s_panels)
        stressed_rank = metrics.sharpe(stressed_pooled)
        gate_list.append(
            cost_stress_gate(rank_sharpe, stressed_rank, thresholds.cost_stress_ratio)
        )
    gate_results = {g.name: g for g in gate_list}

    # A candidate must clear every Stage-1 gate AND carry a usable ranking number to be
    # feasible. ``rank_sharpe is None`` (no usable residual variance — pure factor beta —
    # or a non-finite bar, see metrics) means there is nothing to rank, so the candidate
    # is unrankable: feasible=False with rank_sharpe=None, never feasible with a missing
    # or NaN rank. ResResult.rank_sharpe is therefore strictly float | None.
    feasible = all(g.passed for g in gate_list) and rank_sharpe is not None
    effective_rank = rank_sharpe if feasible else None

    return ResResult(
        feasible=feasible,
        gate_results=gate_results,
        rank_sharpe=effective_rank,
        per_fold_sharpe=tuple(per_fold_sharpe),
        residual_info_ratio=residual_ir,
        psr=psr,
    )
