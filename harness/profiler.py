"""Asset Profiler + data-sufficiency gate (FR-G1, FR-G2).

An asset only earns the conclusions its data can support (Principle 6). Before a campaign
the profiler measures, from the available history, the quantities that bound an honest
search, and DERIVES:

- the **budget upper bound** — the max number of Selection looks the asset's information
  content can honestly support (MinBTL-style, on the *effective* sample). Consumed by P3.
- the **window / fold / Lockbox sizing** (period counts at the bar cadence).
- the **significance bar** — the **Lockbox minimum detectable effect (MDE)** in annualized
  Sharpe units: the smallest edge the Lockbox block is powered to confirm.

The **data-sufficiency gate** refuses graduation (returns *insufficient evidence*) whenever
the Lockbox MDE exceeds the candidate's claimed edge, or the effective sample is below the
floor for an honest trial — it never lowers the bar to manufacture a verdict (FR-G2, AC-5).

Pure numpy/math: deterministic, no clock, no ``quant_strategies`` import. Operates on a
return-proxy series + cross-section legs the caller supplies (the harness owns data access);
this keeps the profiler unit-testable without a database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

import numpy as np

_EPS = 1e-12

# Confidence z for the significance bar / MinBTL noise threshold (95% one-sided).
_DEFAULT_CONFIDENCE_Z = 1.6448536269514722  # Phi^{-1}(0.95)
# Power z for the Lockbox MDE (80% power, one-sided): the effect must be detectable, not
# merely significant, so the MDE uses z_alpha + z_beta.
_DEFAULT_POWER_Z = 0.8416212335729143  # Phi^{-1}(0.80)

Verdict = Literal["admissible", "insufficient_evidence"]


@dataclass(frozen=True)
class AssetProfile:
    """What the profiler measures and derives for one asset/campaign."""

    # --- measured ---
    usable_periods: int  # raw bar count of usable history
    autocorrelation: float  # lag-1 autocorrelation of the return proxy
    effective_sample: float  # N_eff = N·(1-ρ)/(1+ρ) — serial-correlation-discounted
    effective_years: float  # N_eff / periods_per_year — the calendar scale of the evidence
    effective_regimes: int  # coarse count of distinct volatility regimes
    cross_section_breadth: float  # effective independent names (participation ratio)
    mean_pairwise_correlation: float  # mean off-diagonal correlation of the universe legs

    # --- derived ---
    budget_upper_bound: int  # max honest Selection looks (MinBTL on effective years) — P3 consumes
    train_periods: int
    test_periods: int
    lockbox_periods: int
    lockbox_mde: float  # significance bar: min detectable annualized Sharpe on the Lockbox


# --------------------------------------------------------------------------- #
# Measurement helpers (pure).
# --------------------------------------------------------------------------- #


def _lag1_autocorr(values: np.ndarray) -> float:
    """Lag-1 autocorrelation, clipped to [0, 0.999) for the effective-sample discount.

    Negative autocorrelation does not *reduce* effective independence below the raw count
    for the purpose of bounding search, so it is floored at 0 (a conservative N_eff ≤ N).
    """
    v = np.asarray(values, dtype=np.float64)
    if v.size < 3:
        return 0.0
    v = v[np.isfinite(v)]
    if v.size < 3 or float(np.std(v)) < _EPS:
        return 0.0
    a = v[:-1] - v[:-1].mean()
    b = v[1:] - v[1:].mean()
    denom = math.sqrt(float(np.sum(a**2)) * float(np.sum(b**2)))
    if denom < _EPS:
        return 0.0
    rho = float(np.sum(a * b) / denom)
    return float(min(max(rho, 0.0), 0.999))


def _effective_sample(n: int, rho: float) -> float:
    """Newey-West-style serial-correlation discount: N_eff = N·(1-ρ)/(1+ρ)."""
    if n <= 0:
        return 0.0
    return float(n * (1.0 - rho) / (1.0 + rho))


def _regime_count(values: np.ndarray, n_buckets: int = 0) -> int:
    """Coarse count of distinct volatility regimes over the span.

    Splits the series into contiguous blocks and counts how many *distinct* volatility
    levels appear (low / mid / high tertiles of block volatility). A single-regime history
    (all blocks similar vol) returns ~1; a history spanning calm and turbulent stretches
    returns more. This is the "≥3 regimes" check the methodology's fold table assumes.
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size < 6:
        return 1
    blocks = n_buckets or max(3, min(12, v.size // 50))
    chunk = max(2, v.size // blocks)
    vols = [
        float(np.std(v[i : i + chunk]))
        for i in range(0, v.size - chunk + 1, chunk)
    ]
    if len(vols) < 2:
        return 1
    vols_arr = np.array(vols)
    lo, hi = np.quantile(vols_arr, [1 / 3, 2 / 3])
    levels = set()
    for x in vols_arr:
        levels.add("low" if x <= lo else ("high" if x >= hi else "mid"))
    return max(1, len(levels))


def _cross_section_breadth(legs: Mapping[str, np.ndarray] | None) -> tuple[float, float]:
    """Effective independent names + mean pairwise correlation of the universe legs.

    Effective breadth is the participation ratio of the leg correlation matrix's eigenvalues
    (same correlation-aware measure as the breadth gate): co-moving names collapse toward 1.
    Returns ``(breadth, mean_pairwise_correlation)``.
    """
    if not legs:
        return 1.0, 1.0
    syms = list(legs)
    if len(syms) == 1:
        return 1.0, 1.0
    n = min(np.asarray(legs[s]).size for s in syms)
    if n < 2:
        return 1.0, 1.0
    matrix = np.column_stack([np.asarray(legs[s], dtype=np.float64)[:n] for s in syms])
    stds = matrix.std(axis=0, ddof=1)
    live = stds > _EPS
    if live.sum() < 2:
        return 1.0, 1.0
    matrix = matrix[:, live]
    corr = np.corrcoef(matrix, rowvar=False)
    corr = np.nan_to_num((corr + corr.T) / 2.0, nan=0.0)
    eigvals = np.clip(np.linalg.eigvalsh(corr), 0.0, None)
    denom = float(np.sum(eigvals**2))
    breadth = float(np.sum(eigvals) ** 2 / denom) if denom > _EPS else 1.0
    k = corr.shape[0]
    off = (float(np.sum(corr)) - k) / (k * (k - 1)) if k > 1 else 1.0
    return breadth, float(off)


# --------------------------------------------------------------------------- #
# MinBTL budget + Lockbox MDE.
# --------------------------------------------------------------------------- #


def _expected_max_standard_normal(k: int) -> float:
    """Expected maximum of ``k`` i.i.d. standard normals (BLPZ two-term approximation).

    ``E[max] ≈ (1-γ)·Φ⁻¹(1 - 1/k) + γ·Φ⁻¹(1 - 1/(k·e))`` with Euler–Mascheroni γ. This is the
    False-Strategy-Theorem expected-max-noise-Sharpe shape; it grows ~√(2 ln k), so the
    honest trial budget shrinks fast as history shortens.
    """
    if k <= 1:
        return 0.0
    gamma = 0.5772156649015329
    e = math.e
    return (1.0 - gamma) * _norm_ppf(1.0 - 1.0 / k) + gamma * _norm_ppf(1.0 - 1.0 / (k * e))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation; deterministic)."""
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _budget_upper_bound(
    effective_years: float,
    target_sharpe: float,
    *,
    max_budget: int = 64,
) -> int:
    """Max honest Selection looks: the largest K whose expected-max noise Sharpe stays below
    the target edge (MinBTL on the effective sample), all in ANNUALIZED Sharpe units.

    The annualized Sharpe estimator's standard error scales with **calendar time**, not bar
    count: ``SE(SR_ann) ≈ 1/sqrt(years)`` (the ``sqrt(ppy)`` of annualization cancels the
    ``sqrt(n)`` of the sample). So the per-trial noise std is ``1/sqrt(effective_years)`` and
    the expected maximum over K independent trials is ``E[max_K]/sqrt(effective_years)``
    (False Strategy Theorem). The honest budget is the largest K before that expected-max
    noise Sharpe meets/exceeds the ``target_sharpe`` we are searching for — i.e. before the
    best of K pure-luck trials would clear the target by chance. Short crypto history (few
    effective years) ⇒ a small single-digit budget; long equity/FX history ⇒ tens — exactly
    the MinBTL relationship (trials bounded by history, not compute).
    """
    if effective_years <= 0 or target_sharpe <= 0:
        return 1
    noise_std = 1.0 / math.sqrt(effective_years)
    k = 1
    while k < max_budget:
        nxt = k + 1
        if _expected_max_standard_normal(nxt) * noise_std >= target_sharpe:
            break
        k = nxt
    return max(1, k)


def _lockbox_mde(
    lockbox_years: float,
    *,
    confidence_z: float = _DEFAULT_CONFIDENCE_Z,
    power_z: float = _DEFAULT_POWER_Z,
) -> float:
    """Lockbox minimum detectable effect in ANNUALIZED Sharpe units.

    One-sample Sharpe power: the annualized Sharpe estimator's standard error scales with
    calendar time, ``SE(SR_ann) ≈ 1/sqrt(years)`` (not bar count — the ``sqrt(ppy)`` cancels
    the ``sqrt(n)``). So the smallest annualized Sharpe the Lockbox can confirm at the
    configured confidence AND power is ``MDE = (z_alpha + z_beta) / sqrt(lockbox_years)``. A
    thin (short calendar) Lockbox ⇒ a large MDE ⇒ only big edges are confirmable; everything
    smaller returns *insufficient evidence* (FR-G2). This is why a 2-month crypto Lockbox
    cannot confirm a Sharpe-1 edge with power, and the harness says so rather than pretending.
    """
    if lockbox_years <= 0:
        return float("inf")
    return (confidence_z + power_z) / math.sqrt(lockbox_years)


# --------------------------------------------------------------------------- #
# The profiler + the data-sufficiency gate.
# --------------------------------------------------------------------------- #


def profile_asset(
    return_proxy: np.ndarray | Sequence[float],
    *,
    cross_section_legs: Mapping[str, np.ndarray] | None = None,
    lockbox_periods: int,
    periods_per_year: float = 8760.0,
    train_test_ratio: float = 3.0,
    budget_target_sharpe: float = 1.0,
) -> AssetProfile:
    """Profile an asset from a return-proxy series (and optional cross-section legs).

    ``return_proxy`` is the asset's per-period return series over usable history (the harness
    sources it from ``quant_data``; here it is supplied so the profiler stays pure).
    ``lockbox_periods`` is the reserved forward-block length at the bar cadence.
    ``periods_per_year`` is the annualization cadence (matches the bar cadence) — Sharpe
    standard errors scale with calendar time, so period counts are converted to years.
    ``budget_target_sharpe`` is the annualized edge the search aims to detect; the budget is
    the MinBTL cap of trials before the expected-max pure-luck Sharpe would clear that target.
    The window/fold sizing is a ~``train_test_ratio``:1 split of the non-Lockbox history.
    """
    values = np.asarray(return_proxy, dtype=np.float64)
    # Fail closed on a degenerate cadence: an invalid periods_per_year would silently turn
    # bar counts into bogus calendar years (inflating the budget, shrinking the MDE). The
    # Protocol validates ppy>0, but the profiler does not trust its caller (defence in depth).
    if not math.isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError(f"periods_per_year must be a positive finite number, got {periods_per_year!r}")
    # Only FINITE bars are usable evidence. Counting NaN/inf bars as history would let an
    # all-NaN series claim a full effective sample, a finite MDE, and an admissible verdict —
    # a gate-gaming path. The downstream measurement helpers already drop non-finite bars; the
    # usable count must agree with them.
    usable = int(np.count_nonzero(np.isfinite(values)))
    rho = _lag1_autocorr(values)
    n_eff = _effective_sample(usable, rho)
    ppy = float(periods_per_year)
    effective_years = n_eff / ppy
    lockbox_years = lockbox_periods / ppy
    regimes = _regime_count(values)
    breadth, mean_corr = _cross_section_breadth(cross_section_legs)

    lockbox_mde = _lockbox_mde(lockbox_years)  # annualized Sharpe units
    budget = _budget_upper_bound(effective_years, budget_target_sharpe)

    # Window/fold sizing: split the non-Lockbox history ~train_test_ratio:1.
    non_lockbox = max(0, usable - lockbox_periods)
    test_periods = max(1, int(non_lockbox / (train_test_ratio + 1.0)))
    train_periods = max(1, int(non_lockbox - test_periods))

    return AssetProfile(
        usable_periods=usable,
        autocorrelation=rho,
        effective_sample=n_eff,
        effective_years=effective_years,
        effective_regimes=regimes,
        cross_section_breadth=breadth,
        mean_pairwise_correlation=mean_corr,
        budget_upper_bound=budget,
        train_periods=train_periods,
        test_periods=test_periods,
        lockbox_periods=int(lockbox_periods),
        lockbox_mde=lockbox_mde,
    )


@dataclass(frozen=True)
class SufficiencyVerdict:
    """The data-sufficiency gate's verdict (FR-G2)."""

    verdict: Verdict
    lockbox_mde: float
    claimed_edge: float
    effective_sample: float
    detail: str


def assess_sufficiency(
    profile: AssetProfile,
    claimed_edge: float,
    *,
    min_effective_sample: float = 30.0,
) -> SufficiencyVerdict:
    """Data-sufficiency gate (FR-G2, AC-5): refuse a verdict the data cannot power.

    Returns ``insufficient_evidence`` whenever the Lockbox MDE exceeds the candidate's
    claimed edge (the confirmation cannot distinguish the edge from zero), OR the effective
    sample is below the floor for an honest trial. NEVER lowers the bar to manufacture a
    verdict — an under-powered asset is reported as under-powered.
    """
    # Fail closed on a non-finite claimed edge: NaN would make every comparison false (and
    # slip through as admissible), and inf is not a real claim. An invalid claim is not a
    # confirmable claim.
    if not math.isfinite(claimed_edge):
        return SufficiencyVerdict(
            verdict="insufficient_evidence",
            lockbox_mde=profile.lockbox_mde,
            claimed_edge=claimed_edge,
            effective_sample=profile.effective_sample,
            detail=f"claimed edge {claimed_edge!r} is not a finite Sharpe — not a confirmable claim",
        )
    if profile.effective_sample < min_effective_sample:
        return SufficiencyVerdict(
            verdict="insufficient_evidence",
            lockbox_mde=profile.lockbox_mde,
            claimed_edge=claimed_edge,
            effective_sample=profile.effective_sample,
            detail=(
                f"effective sample {profile.effective_sample:.1f} < floor "
                f"{min_effective_sample} — too little independent history for an honest trial"
            ),
        )
    if not math.isfinite(profile.lockbox_mde) or profile.lockbox_mde > claimed_edge:
        return SufficiencyVerdict(
            verdict="insufficient_evidence",
            lockbox_mde=profile.lockbox_mde,
            claimed_edge=claimed_edge,
            effective_sample=profile.effective_sample,
            detail=(
                f"Lockbox MDE {profile.lockbox_mde:.3f} > claimed edge {claimed_edge:.3f} — "
                "the Lockbox cannot power this confirmation"
            ),
        )
    return SufficiencyVerdict(
        verdict="admissible",
        lockbox_mde=profile.lockbox_mde,
        claimed_edge=claimed_edge,
        effective_sample=profile.effective_sample,
        detail=(
            f"Lockbox MDE {profile.lockbox_mde:.3f} ≤ claimed edge {claimed_edge:.3f}; "
            f"effective sample {profile.effective_sample:.1f} clears the floor"
        ),
    )
