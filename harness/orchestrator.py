"""Walk-forward RES orchestration — the real out-of-sample path (FR-J2, AC-10, AC-1).

Ties the data wall to the objective: derive tiers, generate forward-only walk-forward folds
over the Selection span, call the foundation's ``evaluate`` ONCE per fold (FR-J2), assemble
the per-fold ``FoldReturns`` set (with per-symbol legs) + a stressed-cost set, build the
factor panel per fold, and feed ``compute_res``.

Pure of ``quant_strategies``: it depends only on the ``FoundationGateway`` seam (the real
adapter or the fake) and an injected factor-panel provider (the panel is built from
``quant_data`` outside this module, so the orchestrator stays testable with synthetic series
through ``FakeFoundationGateway``). The cost-stress evidence is a SECOND evaluate under a
stressed-cost Protocol — the seam stays single-series and unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Mapping, Sequence

import numpy as np

from harness.data.tiers import TierSpans, derive_tiers
from harness.data.walkforward import Fold, generate_folds
from harness.foundation import FoldEvalResult, FoldReturns, FoundationGateway
from harness.objective.res import GateThresholds, ResResult, compute_res
from harness.protocol import Experiment, Protocol

# A factor-panel provider maps one fold's window + its OOS returns to the factor-return
# columns for that fold (market/momentum/funding-carry/size), aligned to the return series.
# The harness builds this from quant_data outside this module; tests inject synthetic panels.
FactorPanelProvider = Callable[["FoldWindowSpan", FoldReturns], Mapping[str, np.ndarray]]


@dataclass(frozen=True)
class FoldWindowSpan:
    """A fold's calendar span + the foundation ``window_id`` (what ``evaluate`` is called with).

    Duck-types ``harness.foundation_real.FoldWindow`` (same ``window_id``/``start``/``end``
    fields) so the real adapter consumes it directly without importing this module.
    """

    window_id: str
    start: str  # ISO date
    end: str  # ISO date


@dataclass(frozen=True)
class WalkForwardRES:
    """The orchestrated result: the RES plus the per-fold provenance for the ledger (P3)."""

    res: ResResult
    fold_windows: tuple[FoldWindowSpan, ...]
    fold_results: tuple[FoldEvalResult, ...]
    n_folds_evaluated: int


def _bar_duration(periods_per_year: float) -> timedelta:
    """Calendar duration of one bar from the annualization cadence (e.g. hourly ⇒ 1h)."""
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    return timedelta(days=365.25 / periods_per_year)


def _fold_window(
    tier_start: date, fold: Fold, bar: timedelta
) -> FoldWindowSpan:
    """Map a fold's integer TEST index range to a calendar ``(start, end)`` window."""
    origin = datetime(tier_start.year, tier_start.month, tier_start.day)
    start = origin + fold.test.start * bar
    end = origin + fold.test.end * bar
    return FoldWindowSpan(
        window_id=f"fold_{fold.index}",
        start=start.date().isoformat(),
        end=end.date().isoformat(),
    )


def _selection_periods(tiers: TierSpans, bar: timedelta) -> int:
    """Number of bars in the Selection span at the bar cadence."""
    span_days = (tiers.selection.end - tiers.selection.start).days + 1
    bar_days = bar.total_seconds() / 86400.0
    return max(1, int(span_days / bar_days)) if bar_days > 0 else span_days


def _stressed_protocol(protocol: Protocol) -> Protocol:
    """A Protocol copy whose cost model is multiplied by its ``stress_multiplier``.

    Used to source the cost-stress *evidence* via a second evaluate. Costs still come solely
    from the Protocol (the wall holds); only the harness-owned stress factor scales them.
    """
    cost = protocol.cost_model
    m = cost.stress_multiplier
    stressed_cost = cost.model_copy(
        update={
            "taker_bps": cost.taker_bps * m,
            "maker_bps": cost.maker_bps * m,
            "slippage_bps": cost.slippage_bps * m,
        }
    )
    return protocol.model_copy(update={"cost_model": stressed_cost})


def run_walk_forward_res(
    experiment: Experiment,
    protocol: Protocol,
    gateway: FoundationGateway,
    factor_panel_provider: FactorPanelProvider,
    *,
    thresholds: GateThresholds | None = None,
    cost_stress: bool = True,
) -> WalkForwardRES:
    """Run the real OOS walk-forward path and compute RES.

    For each forward-only fold over the Selection span: call ``gateway.evaluate`` once
    (realistic costs), collect the typed ``FoldReturns`` (incl. ``by_symbol``) and the factor
    panel; when ``cost_stress`` is on, a second ``evaluate`` under the stressed-cost Protocol
    supplies the cost-stress evidence. Only folds whose evaluate SUCCEEDED with a return
    series contribute. RES is then computed over the assembled fold set + panels.
    """
    thresholds = thresholds or GateThresholds.from_protocol(protocol.objective.gates)
    tiers = derive_tiers(protocol)
    bar = _bar_duration(protocol.annualization.periods_per_year)
    n_periods = _selection_periods(tiers, bar)
    folds = generate_folds(n_periods, protocol.folds)

    fold_windows: list[FoldWindowSpan] = []
    fold_results: list[FoldEvalResult] = []
    realistic_folds: list[FoldReturns] = []
    panels: list[Mapping[str, np.ndarray]] = []
    stressed_folds: list[FoldReturns] = []
    stressed_panels: list[Mapping[str, np.ndarray]] = []

    stressed_proto = _stressed_protocol(protocol) if cost_stress else None

    for fold in folds:
        window = _fold_window(tiers.selection.start, fold, bar)
        fold_windows.append(window)
        result = gateway.evaluate(experiment, protocol, window)
        fold_results.append(result)
        if not result.succeeded or result.returns is None:
            continue
        panel = factor_panel_provider(window, result.returns)
        realistic_folds.append(result.returns)
        panels.append(panel)
        if stressed_proto is not None:
            s_result = gateway.evaluate(experiment, stressed_proto, window)
            if s_result.succeeded and s_result.returns is not None:
                stressed_folds.append(s_result.returns)
                stressed_panels.append(panel)

    # The factor columns the Protocol REQUIRES neutralized — the fail-closed contract passed
    # through to RES (AC-9/G2). An unwired/identity panel on this live path therefore yields an
    # infeasible RES, never a raw-returns pass scored as residual alpha.
    required_factors = protocol.objective.factor_panel.required_factors

    if not realistic_folds:
        # No usable fold ⇒ no evidence ⇒ infeasible RES (compute_res over an empty set yields
        # rank None / failing gates; we still return it so the caller sees the gate detail).
        res = compute_res([], [], trade_count=0, thresholds=thresholds, required_factors=required_factors)
        return WalkForwardRES(res=res, fold_windows=tuple(fold_windows),
                              fold_results=tuple(fold_results), n_folds_evaluated=0)

    trade_count = sum(r.trade_count for r in fold_results if r.succeeded)
    have_stress = cost_stress and len(stressed_folds) == len(realistic_folds)
    res = compute_res(
        realistic_folds,
        panels,
        trade_count=trade_count,
        thresholds=thresholds,
        required_factors=required_factors,
        stressed_folds=stressed_folds if have_stress else None,
        stressed_factor_panels=stressed_panels if have_stress else None,
    )
    return WalkForwardRES(
        res=res,
        fold_windows=tuple(fold_windows),
        fold_results=tuple(fold_results),
        n_folds_evaluated=len(realistic_folds),
    )
