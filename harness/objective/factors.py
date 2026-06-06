"""Factor-panel residual alpha (FR-C3).

RES scores *residual alpha*, not raw return: regress the OOS returns on a tradeable
factor panel and score the residual. **Market beta AND factor beta are not edge.**

In crypto, **funding is carry, never additive alpha** — so funding enters as a *column
of the factor panel* (a return stream the strategy is exposed to). Any PnL explained by
funding is regressed OUT; it is never added back. A short-only bet that is largely
funding collection therefore residualizes to ~0 alpha (AC-9).

The panel is supplied to the harness (auto-derived panels are out of scope per PRD §12);
P1 takes it as numpy factor-return columns. The contract fixed here — regress and score
the residual, funding-as-carry — does not change when P2 builds the real panel from
``quant_data``.

Pure numpy (lstsq); deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from harness.foundation import FoldReturns

_EPS = 1e-12

# The canonical factor panel axes (FR-C3). Funding is carry — listed as a panel column,
# regressed out, never additive. A panel need not supply every axis; whatever columns
# are present are neutralized.
PANEL_AXES = ("market", "momentum", "funding_carry", "size")


@dataclass(frozen=True)
class ResidualResult:
    """Residual-alpha regression output.

    ``residual`` is the **alpha-bearing** residual series: returns with the factor *beta*
    exposure removed but the alpha *intercept retained* (``residual = alpha + ε``, where
    ``ε`` is the mean-zero OLS residual). This is the correct definition of residual alpha
    — a pure factor-beta strategy has alpha ≈ 0 AND ε ≈ 0, so the series is ≈ 0 (AC-9),
    while a genuine idiosyncratic edge keeps its positive-mean alpha. RES ranks on the
    Sharpe of THIS series (FR-C2/C3). Subtracting the intercept too would zero every
    series by construction (OLS residuals are mean-zero) and destroy the signal.
    """

    residual: np.ndarray  # alpha-bearing residual: values - Σ beta_k·f_k (beta removed, alpha kept)
    information_ratio: float | None  # mean(residual) / std(residual) ≈ alpha / tracking error
    alpha: float  # regression intercept (the average residual alpha per period)
    betas: Mapping[str, float]  # factor name -> loading (the beta that IS removed)
    r_squared: float  # fraction of return variance explained by factor BETAS (not the intercept)


def _panel_matrix(
    factor_panel: Mapping[str, np.ndarray], n: int
) -> tuple[np.ndarray, tuple[str, ...]]:
    """Build the [n, k] design matrix of factor columns (no intercept here).

    Columns are ordered by ``PANEL_AXES`` first (stable, canonical), then any extra
    factor names sorted, so the regression is deterministic regardless of dict order.
    """
    names: list[str] = [a for a in PANEL_AXES if a in factor_panel]
    names += sorted(k for k in factor_panel if k not in PANEL_AXES)
    if not names:
        return np.empty((n, 0), dtype=np.float64), ()
    cols = []
    for name in names:
        col = np.asarray(factor_panel[name], dtype=np.float64)
        if col.shape[0] != n:
            raise ValueError(
                f"factor column {name!r} has length {col.shape[0]}, expected {n}"
            )
        cols.append(col)
    return np.column_stack(cols), tuple(names)


def residualize(
    returns: FoldReturns | np.ndarray,
    factor_panel: Mapping[str, np.ndarray],
) -> ResidualResult:
    """Regress returns on the factor panel; return the residual series + info ratio.

    Model: ``r_t = alpha + Σ_k beta_k * f_{k,t} + residual_t`` (OLS via lstsq).
    The residual is the scale-free edge after market/factor/funding-carry neutralization.

    An empty panel is the identity: the residual is the returns themselves (nothing to
    neutralize). With a panel, the intercept captures the average residual; the residual
    *series* is what RES ranks on.
    """
    values = (
        np.asarray(returns.values, dtype=np.float64)
        if isinstance(returns, FoldReturns)
        else np.asarray(returns, dtype=np.float64)
    )
    n = values.size

    design, names = _panel_matrix(factor_panel, n)
    if design.shape[1] == 0:
        # No factors to neutralize — residual is the raw series, no beta, no explained var.
        ir = _information_ratio(values)
        return ResidualResult(
            residual=values.copy(),
            information_ratio=ir,
            alpha=float(np.mean(values)) if n else 0.0,
            betas={},
            r_squared=0.0,
        )

    # Regress on the factor columns WITH an intercept (so beta is estimated unbiased by the
    # mean), but score the alpha-bearing residual = intercept + ε = values - factor·beta.
    x = np.column_stack([np.ones(n, dtype=np.float64), design])
    coef, *_ = np.linalg.lstsq(x, values, rcond=None)

    alpha = float(coef[0])
    beta_vec = coef[1:]
    betas = {name: float(c) for name, c in zip(names, beta_vec)}

    # Remove only the factor-beta contribution; KEEP the alpha intercept in the series.
    factor_contribution = design @ beta_vec
    residual_alpha = values - factor_contribution  # == alpha + ε (mean ≈ alpha)

    # R² here measures variance explained by the factor BETAS (the exposure we strip), so a
    # pure-beta series reports ~1.0 and a pure-alpha series ~0.0.
    total_var = float(np.var(values))
    eps = values - (x @ coef)  # the mean-zero OLS residual, for the explained-variance ratio
    r_squared = 0.0 if total_var < _EPS else max(0.0, 1.0 - float(np.var(eps)) / total_var)

    return ResidualResult(
        residual=residual_alpha,
        information_ratio=_information_ratio(residual_alpha),
        alpha=alpha,
        betas=betas,
        r_squared=r_squared,
    )


def _information_ratio(residual: np.ndarray) -> float | None:
    """Per-period information ratio of the residual: mean / std.

    Returns ``None`` for a degenerate (near-zero-variance) residual — a pure
    factor-beta strategy residualizes to ~0 with no usable IR.
    """
    if residual.size < 2:
        return None
    # A non-finite bar would make the ratio NaN; an unrankable NaN must not propagate
    # as if it were an alpha magnitude (see metrics._all_finite).
    if not np.all(np.isfinite(residual)):
        return None
    sd = float(np.std(residual, ddof=1))
    if sd < _EPS:
        return None
    result = float(np.mean(residual)) / sd
    return result if np.isfinite(result) else None


def residual_fold_returns(
    fold: FoldReturns,
    factor_panel: Mapping[str, np.ndarray],
) -> FoldReturns:
    """Return a ``FoldReturns`` whose ``values`` are the residual series.

    Used by RES so the per-fold Sharpe is computed on the *residual* alpha at the same
    frozen exposure and annualization cadence as the input fold.
    """
    result = residualize(fold, factor_panel)
    return FoldReturns(
        timestamps=fold.timestamps,
        values=result.residual,
        periods_per_year=fold.periods_per_year,
        by_symbol=fold.by_symbol,
    )
