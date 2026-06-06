"""Stage-1 feasibility gates — hard, binary; fail any ⇒ RES infeasible (FR-C5).

The CHEAP gates that need no significance machinery (evidence/min-trade proxy,
concentration ceiling, correlation-aware effective-breadth floor) plus the four OOS gates
that need walk-forward folds / the real foundation:

- **Evidence sufficiency (proxy):** a minimum trade count (a fast proxy on ``run``).
- **PSR evidence sufficiency:** P(true Sharpe > benchmark) over the pooled residual clears
  the configured confidence — the honest evidence gate at ``evaluate``.
- **Concentration ceiling:** no single symbol may dominate PnL.
- **Effective-breadth floor (CORRELATION-AWARE):** the edge must come from several
  *independent* bets. A basket of co-moving symbols (ADA disguised as ADA/XRP/AVAX)
  collapses to an effective breadth of ~1 and FAILS — kills the "ADA-as-basket" trick.
- **Max-drawdown ceiling:** the residual equity curve's drawdown stays survivable.
- **Worst-fold floor + dispersion ceiling:** the edge holds in the weakest fold and is not
  carried by a single window. A fold whose residual Sharpe is undefined (degenerate
  near-zero variance — the ``_EPS`` carry) or non-finite is a FAILING fold, never silently
  skipped: an unmeasurable fold cannot clear the floor.
- **Cost-stress survival ratio:** the residual Sharpe under stressed costs holds a minimum
  fraction of the residual Sharpe under realistic costs.

All gates fail-closed when their statistic is undefined (insufficient evidence), never pass
by default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from harness.foundation import FoldReturns

_EPS = 1e-12


@dataclass(frozen=True)
class GateOutcome:
    """One gate's verdict (the shared type referenced by ``ResResult.gate_results``)."""

    name: str
    passed: bool
    value: float | None  # the measured statistic
    threshold: float | None  # the bar it was compared against
    detail: str = ""


def evidence_gate(trade_count: int, min_trades: int) -> GateOutcome:
    """Cheap evidence-sufficiency proxy: enough trades to measure anything.

    The PSR gate (skew/kurtosis-aware, given this candidate's own Sharpe) is the honest
    version and is DEFERRED to P2.
    """
    passed = trade_count >= min_trades
    return GateOutcome(
        name="evidence_sufficiency",
        passed=passed,
        value=float(trade_count),
        threshold=float(min_trades),
        detail="min-trade proxy; PSR gate deferred to P2",
    )


def factor_panel_gate(panels_cover: bool, n_required: int) -> GateOutcome:
    """Fail-closed factor-panel coverage gate (FR-C3, AC-9/G2, PRD Principle 6).

    The mechanical wall that makes "score raw beta as residual alpha" UNREPRESENTABLE on the live
    path: when the Protocol REQUIRES factor neutralization (``n_required > 0``) but the supplied
    panel does not COVER those columns (empty/identity — e.g. an unwired provider), the candidate
    is infeasible. ``passed`` is True only when every required column is present for every fold;
    otherwise it fails with ``factor_panel_unwired`` — never a silent raw-returns pass. Never
    passes by default (an unmeasurable requirement is a failing requirement)."""
    return GateOutcome(
        name="factor_panel",
        passed=panels_cover,
        value=1.0 if panels_cover else 0.0,
        threshold=1.0,
        detail=(
            f"required factor columns covered for every fold ({n_required} required)"
            if panels_cover
            else (
                "factor_panel_unwired: the Protocol requires neutralization of "
                f"{n_required} factor column(s) but the supplied panel does not cover them "
                "(empty/identity) — infeasible (fail-closed), NOT a raw-returns pass"
            )
        ),
    )


def _pnl_shares(by_symbol: Mapping[str, FoldReturns]) -> dict[str, float]:
    """Absolute-PnL share per symbol (compounded growth - 1, by |contribution|).

    Note: on near-zero-mean RESIDUAL legs the |PnL|-share basis is noisy at low SNR (the
    compounded growth of a mean-zero series is dominated by sampling fluctuation, not
    edge). In practice such candidates are already bounced upstream by a near-zero residual
    IR → rank None, so this gate need not be the one that bites there. If it ever must
    discriminate at low SNR, a variance- or |leg-mean|-based share would be a cleaner basis.
    """
    raw: dict[str, float] = {}
    for sym, fr in by_symbol.items():
        vals = np.asarray(fr.values, dtype=np.float64)
        # Compounded net PnL of the symbol leg over the fold.
        raw[sym] = float(np.prod(1.0 + vals) - 1.0) if vals.size else 0.0
    total_abs = sum(abs(v) for v in raw.values())
    if total_abs < _EPS:
        # No PnL anywhere — treat as fully concentrated (degenerate), let breadth/evidence catch it.
        return {sym: 0.0 for sym in by_symbol}
    return {sym: abs(v) / total_abs for sym, v in raw.items()}


def concentration_gate(
    by_symbol: Mapping[str, FoldReturns] | None,
    max_share: float,
) -> GateOutcome:
    """No single symbol may carry more than ``max_share`` of |PnL| (FR-C5).

    With no per-symbol decomposition the candidate is treated as fully concentrated
    (a single track) and FAILS — a single-symbol bet cannot masquerade as diversified
    by omitting its decomposition.
    """
    if not by_symbol:
        return GateOutcome(
            name="concentration",
            passed=False,
            value=1.0,
            threshold=max_share,
            detail="no per-symbol decomposition; treated as single-symbol",
        )
    shares = _pnl_shares(by_symbol)
    top = max(shares.values()) if shares else 1.0
    return GateOutcome(
        name="concentration",
        passed=top <= max_share,
        value=top,
        threshold=max_share,
        detail=f"top symbol |PnL| share over {len(by_symbol)} legs",
    )


def effective_breadth(by_symbol: Mapping[str, FoldReturns]) -> float:
    """Correlation-aware effective number of independent bets.

    Computed as the participation ratio of the eigenvalues of the per-symbol return
    *correlation* matrix:  ``N_eff = (Σλ)² / Σλ²``.

    - Perfectly co-moving legs → one eigenvalue ≈ k, rest ≈ 0 → ``N_eff ≈ 1``.
    - Perfectly independent legs → all eigenvalues = 1 → ``N_eff ≈ k``.

    So a basket whose symbols all track one underlying (ADA/XRP/AVAX all ~ ADA) scores
    ``N_eff ≈ 1`` and does NOT pass as diversified, regardless of how many tickers it lists.
    Degenerate (zero-variance) legs contribute no independent information.

    This measures the number of *independent* bets via the participation ratio of the
    correlation matrix — NOT a simple leg count. A perfectly hedged 2-leg pair (corr −1)
    is one independent bet, so it reads as ``N_eff ≈ 1`` (concentrated) and fails the
    floor: a legitimate pairs strategy therefore needs ≥3 independent legs, or a
    purpose-built pairs gate, rather than this breadth floor.
    """
    syms = list(by_symbol)
    k = len(syms)
    if k == 0:
        return 0.0
    if k == 1:
        return 1.0
    # Stack aligned per-symbol return columns.
    n = min(np.asarray(by_symbol[s].values).size for s in syms)
    if n < 2:
        return 1.0
    matrix = np.column_stack(
        [np.asarray(by_symbol[s].values, dtype=np.float64)[:n] for s in syms]
    )
    stds = matrix.std(axis=0, ddof=1)
    # Drop legs with no variance — they carry no independent signal.
    live = stds > _EPS
    if live.sum() < 2:
        return 1.0
    matrix = matrix[:, live]
    corr = np.corrcoef(matrix, rowvar=False)
    # Numerical guard: symmetrize and clip eigenvalues to non-negative.
    corr = np.nan_to_num((corr + corr.T) / 2.0, nan=0.0)
    eigvals = np.linalg.eigvalsh(corr)
    eigvals = np.clip(eigvals, 0.0, None)
    denom = float(np.sum(eigvals**2))
    if denom < _EPS:
        return 1.0
    return float(np.sum(eigvals) ** 2 / denom)


def effective_breadth_gate(
    by_symbol: Mapping[str, FoldReturns] | None,
    min_breadth: float,
) -> GateOutcome:
    """Effective-breadth floor (correlation-aware) — co-moving baskets fail (FR-C5)."""
    if not by_symbol:
        return GateOutcome(
            name="effective_breadth",
            passed=min_breadth <= 1.0,
            value=1.0,
            threshold=min_breadth,
            detail="no per-symbol decomposition; effective breadth = 1",
        )
    n_eff = effective_breadth(by_symbol)
    return GateOutcome(
        name="effective_breadth",
        passed=n_eff >= min_breadth,
        value=n_eff,
        threshold=min_breadth,
        detail=f"participation ratio of the {len(by_symbol)}-leg correlation matrix",
    )


# --------------------------------------------------------------------------- #
# The OOS gates (need walk-forward folds / the real foundation). Computed, not stubbed.
# Each fails CLOSED when its statistic is undefined — an unmeasurable edge is not a passing
# edge (insufficient evidence), never a silent pass.
# --------------------------------------------------------------------------- #


def psr_gate(psr: float | None, psr_floor: float) -> GateOutcome:
    """Evidence sufficiency: the Probabilistic Sharpe Ratio clears the confidence floor.

    PSR = P(true Sharpe > benchmark) given this candidate's own Sharpe, skew, and kurtosis
    over the pooled residual. ``None`` (degenerate / no-variance / too-small sample) means
    the evidence is insufficient to clear the bar ⇒ FAIL. A non-finite or out-of-[0,1] value
    is not a valid probability ⇒ FAIL (never pass on a malformed statistic).
    """
    valid = psr is not None and math.isfinite(psr) and 0.0 <= psr <= 1.0
    passed = valid and psr >= psr_floor
    return GateOutcome(
        name="psr",
        passed=passed,
        value=psr,
        threshold=psr_floor,
        detail="P(true Sharpe > benchmark) over the pooled residual; None/non-finite ⇒ insufficient",
    )


def max_drawdown_gate(max_drawdown: float | None, ceiling: float) -> GateOutcome:
    """Survival: the residual equity curve's max drawdown magnitude stays under the ceiling.

    ``max_drawdown`` is the (negative-fraction) drawdown of the residual curve. ``None``
    (empty / non-finite) fails — an unmeasurable drawdown is not a survivable one.
    """
    passed = max_drawdown is not None and abs(max_drawdown) <= ceiling
    return GateOutcome(
        name="max_drawdown",
        passed=passed,
        value=None if max_drawdown is None else abs(max_drawdown),
        threshold=ceiling,
        detail="|max drawdown| of the residual equity curve; None ⇒ fail",
    )


def worst_fold_gate(
    per_fold_sharpe: Sequence[float | None],
    worst_fold_floor: float,
    dispersion_ceiling: float,
) -> GateOutcome:
    """Worst-fold floor + dispersion ceiling over the per-fold residual Sharpe set (FR-C5).

    The edge must hold in the weakest fold (``min ≥ worst_fold_floor``) and not be carried
    by a single window (dispersion ``std/|mean|`` of the per-fold Sharpes ``≤ ceiling``).

    **Degenerate/None folds are gate-relevant** (the ``_EPS`` carry): a fold whose residual
    Sharpe is ``None`` (near-zero variance) or non-finite is treated as a FAILING fold — its
    edge is unmeasurable, so it cannot clear the floor. This prevents a near-zero-variance
    fold from laundering a spurious "all folds positive" pass. With no folds at all the gate
    fails (no evidence). With a single measurable fold the floor still applies; dispersion is
    not applicable (cannot disperse one point) and does not by itself fail the gate.
    """
    if len(per_fold_sharpe) == 0:
        return GateOutcome(
            name="worst_fold",
            passed=False,
            value=None,
            threshold=worst_fold_floor,
            detail="no folds — no evidence",
        )
    # A None/non-finite fold is unmeasurable ⇒ it cannot clear the floor ⇒ the gate fails.
    has_unmeasurable = any(
        s is None or not math.isfinite(s) for s in per_fold_sharpe
    )
    finite = [float(s) for s in per_fold_sharpe if s is not None and math.isfinite(s)]
    worst = min(finite) if finite else None
    if has_unmeasurable:
        return GateOutcome(
            name="worst_fold",
            passed=False,
            value=worst,
            threshold=worst_fold_floor,
            detail="a fold has undefined/non-finite residual Sharpe (degenerate) — "
            "treated as a failing fold, not skipped",
        )
    assert worst is not None  # all folds measurable here
    floor_ok = worst >= worst_fold_floor
    # Dispersion: coefficient-of-variation-style spread of the per-fold Sharpes. Only
    # applicable with ≥2 folds (a single point has no dispersion).
    dispersion = None
    dispersion_ok = True
    if len(finite) >= 2:
        mean = float(np.mean(finite))
        sd = float(np.std(finite, ddof=1))
        dispersion = sd / abs(mean) if abs(mean) > _EPS else float("inf")
        dispersion_ok = dispersion <= dispersion_ceiling
    passed = bool(floor_ok and dispersion_ok)
    return GateOutcome(
        name="worst_fold",
        passed=passed,
        value=worst,
        threshold=worst_fold_floor,
        detail=(
            f"worst fold Sharpe={worst:.3f} (floor {worst_fold_floor}); "
            + (
                f"dispersion={dispersion:.3f} (ceiling {dispersion_ceiling})"
                if dispersion is not None
                else "single fold — dispersion N/A"
            )
        ),
    )


def cost_stress_gate(
    realistic_sharpe: float | None,
    stressed_sharpe: float | None,
    survival_ratio: float,
) -> GateOutcome:
    """Cost-stress survival: stressed-cost residual Sharpe holds a fraction of realistic.

    Pass iff ``realistic_sharpe > 0`` and ``stressed_sharpe / realistic_sharpe ≥
    survival_ratio``. A non-positive, ``None``, or non-finite realistic Sharpe is not a
    positive edge to stress ⇒ FAIL. A ``None`` / non-finite stressed Sharpe is UNDEFINED
    evidence ⇒ FAIL outright (it is not mapped to 0, which could otherwise slip through a
    ``survival_ratio = 0`` Protocol — fail closed on missing evidence).
    """
    if realistic_sharpe is None or not math.isfinite(realistic_sharpe) or realistic_sharpe <= 0.0:
        return GateOutcome(
            name="cost_stress",
            passed=False,
            value=None,
            threshold=survival_ratio,
            detail="no positive realistic-cost edge to stress",
        )
    if stressed_sharpe is None or not math.isfinite(stressed_sharpe):
        return GateOutcome(
            name="cost_stress",
            passed=False,
            value=None,
            threshold=survival_ratio,
            detail="stressed-cost residual Sharpe undefined — insufficient evidence under stress",
        )
    ratio = stressed_sharpe / realistic_sharpe
    return GateOutcome(
        name="cost_stress",
        passed=ratio >= survival_ratio,
        value=ratio,
        threshold=survival_ratio,
        detail=f"stressed/realistic residual Sharpe = {ratio:.3f}",
    )
