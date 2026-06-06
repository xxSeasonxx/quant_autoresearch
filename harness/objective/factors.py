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
from typing import Mapping, Sequence

import numpy as np

from harness.foundation import FoldReturns

_EPS = 1e-12

# Non-degeneracy floor for a required factor column (AC-9/G2). A column is usable for
# neutralization only if its sample std clears a floor that is the LARGER of an absolute and a
# relative-to-scale term. The relative term (std vs the column's own |scale|) is the standard
# conditioning notion — a column whose variation is negligible relative to its level carries no
# information to regress against; the absolute term catches an all-zero column (scale 0). A
# regression against a zero/constant column removes NOTHING (residual == raw), so a present-but-
# degenerate required factor would let a pure-beta basket score as residual alpha — exactly the
# hole this floor closes. Both are deliberately tiny: a genuine market-return column (std≈1e-2)
# clears them by ~7 orders of magnitude, so the floor never over-fires on real data.
_STD_FLOOR_ABS = 1e-10  # absolute std floor (catches all-zero columns; scale-free baseline)
_STD_FLOOR_REL = 1e-8  # std floor relative to the column's |scale| (catches constant-at-level)

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


def column_is_usable(col: np.ndarray) -> bool:
    """Is this factor column USABLE for neutralization — i.e. is beta actually removable? (AC-9/G2).

    The invariant the factor wall must guarantee (not mere presence): a column is usable iff it is

    - all-finite (no NaN/inf — a non-finite design column makes the OLS undefined/crashing), AND
    - non-degenerate: its sample std clears ``max(_STD_FLOOR_ABS, _STD_FLOOR_REL · |scale|)`` where
      ``|scale|`` is the column's max-abs.

    A zero/constant column has std 0 ⇒ NOT usable: regressing returns on it removes nothing
    (``residual == raw``), so a pure-beta basket would be scored on RAW beta as if it were residual
    alpha. Requiring the column to actually VARY is the irreducible condition for "the beta was
    removed". A genuine factor-return column (std≈1e-2) clears the floor trivially.
    """
    arr = np.asarray(col, dtype=np.float64)
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        return False
    scale = float(np.max(np.abs(arr)))
    floor = max(_STD_FLOOR_ABS, _STD_FLOOR_REL * scale)
    return float(np.std(arr)) > floor


def panel_covers(
    factor_panel: Mapping[str, np.ndarray], required_factors: Sequence[str]
) -> bool:
    """Does this panel cover every required factor with a USABLE (removable) column? (FR-C3, AC-9/G2).

    The fail-closed test the judgment layer runs before trusting a residual. A panel covers the
    requirement iff every required factor is present AND ``column_is_usable`` — present, all-finite,
    and non-degenerate (the column actually varies, so beta is genuinely removable). Presence alone
    is NOT enough: a present-but-degenerate column (all-zero / constant / NaN) neutralizes nothing,
    so scoring against it would launder raw beta as residual alpha — the AC-9 hole. An
    empty/identity panel, or any panel with a degenerate/non-finite required column, covers nothing,
    so a Protocol that requires neutralization fails closed rather than scoring raw returns. With no
    required factors the requirement is vacuously met (identity is then a deliberate choice).
    """
    return all(
        name in factor_panel and column_is_usable(factor_panel[name])
        for name in required_factors
    )


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


def _infeasible_residual(n: int, names: Sequence[str]) -> ResidualResult:
    """The fail-closed sentinel for a design matrix that cannot neutralize (AC-9/G2).

    Returned when the factor design is degenerate / non-finite / rank-deficient — i.e. when beta is
    NOT actually removable. The residual is an all-NaN series so EVERY downstream statistic
    (Sharpe/Sortino/IR via ``metrics._all_finite``) resolves to ``None``: the candidate is
    unrankable, never scored on the RAW series as if neutralization had happened. This is what makes
    "cannot neutralize ⇒ score raw" unrepresentable even if the upstream coverage gate is bypassed.
    """
    return ResidualResult(
        residual=np.full(n, np.nan, dtype=np.float64),
        information_ratio=None,
        alpha=float("nan"),
        betas={name: float("nan") for name in names},
        r_squared=0.0,
    )


def _design_is_neutralizable(values: np.ndarray, x: np.ndarray) -> bool:
    """Can this ``[intercept | factors]`` design actually neutralize SOME beta? (fail-closed precond).

    Defense-in-depth precondition for ``residualize`` — distinct from the strict per-column coverage
    GATE (``panel_covers``/``column_is_usable``), which is the live-path wall. Here we guarantee only
    that ``residualize`` never (a) crashes or (b) returns ``residual == raw`` as if neutralization
    happened. Both require:

    - the returns and the WHOLE design to be FINITE (a NaN/inf design makes ``lstsq`` raise
      ``LinAlgError`` — we refuse it rather than crash), AND
    - the design to add at least ONE dimension beyond the intercept (``rank(x) ≥ 2``). If every
      factor column is degenerate (all-zero/constant), the design collapses to the constant column
      (rank 1) and the regression would remove NOTHING — ``residual == raw`` — which is exactly how
      raw beta is laundered as residual alpha. Requiring rank ≥ 2 makes "remove nothing, score raw"
      unrepresentable, while still allowing a benign extra all-zero column alongside a real one (a
      ``[real_market, zero_funding]`` panel is rank 2 and correctly neutralizes the market leg).
    """
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(x)):
        return False
    return int(np.linalg.matrix_rank(x)) >= 2


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

    **Fail-closed on a bad design (AC-9/G2, defense-in-depth).** If the factor design is degenerate
    (an all-zero/constant column), rank-deficient (collinear columns), or non-finite (a NaN/inf
    column), beta is NOT removable: ``residualize`` returns the all-NaN ``_infeasible_residual``
    sentinel (IR ``None``, every downstream Sharpe ``None``) rather than raising ``LinAlgError`` or
    returning the RAW series as if it had been neutralized. The coverage gate (``panel_covers``)
    catches this upstream; this guard makes the primitive robust regardless of caller.
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
    # Fail-closed BEFORE lstsq: a design that cannot neutralize ANY beta (all factor columns
    # degenerate ⇒ residual would == raw) or is non-finite (would crash lstsq) is refused —
    # never crash, never score raw as residual (see _infeasible_residual).
    if not _design_is_neutralizable(values, x):
        return _infeasible_residual(n, names)
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
