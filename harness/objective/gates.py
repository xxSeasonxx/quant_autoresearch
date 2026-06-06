"""Stage-1 feasibility gates — hard, binary; fail any ⇒ RES infeasible (FR-C5).

P1 implements the CHEAP gates that need no significance machinery:

- **Evidence sufficiency (proxy):** a minimum trade count. The PSR gate is the honest
  version at ``evaluate`` and is DEFERRED to P2 (extension point below).
- **Concentration ceiling:** no single symbol may dominate PnL.
- **Effective-breadth floor (CORRELATION-AWARE):** the edge must come from several
  *independent* bets. A basket of co-moving symbols (ADA disguised as ADA/XRP/AVAX)
  collapses to an effective breadth of ~1 and FAILS — this is what kills the
  "ADA-as-basket" trick (AC-1 partial).

DEFERRED to P2 (FR-C5, left as marked extension points, NOT fallbacks): the PSR gate,
the max-drawdown ceiling, the worst-fold floor + dispersion ceiling, and the cost-stress
survival ratio. They are real OOS gates that need walk-forward folds / the real
foundation (P2), so they are intentionally absent here, not stubbed to "pass".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

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


def _pnl_shares(by_symbol: Mapping[str, FoldReturns]) -> dict[str, float]:
    """Absolute-PnL share per symbol (compounded growth - 1, by |contribution|)."""
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
