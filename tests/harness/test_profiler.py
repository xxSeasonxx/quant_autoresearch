"""FR-G1/G2 + AC-5 — Asset Profiler derivations and the data-sufficiency gate.

The profiler derives the budget upper bound (MinBTL on effective-N), window/fold/Lockbox
sizing, and the significance bar (Lockbox MDE). The data-sufficiency gate returns
*insufficient evidence* when the Lockbox cannot power a confirmation — never lowers the bar.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness.profiler import assess_sufficiency, profile_asset


def _series(n, mean=0.0, sd=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return mean + sd * rng.standard_normal(n)


# --------------------------------------------------------------------------- #
# FR-G1 — derivations.
# --------------------------------------------------------------------------- #


HOURLY = 8760.0


def test_effective_sample_discounts_autocorrelation():
    # An AR(1)-ish series has positive lag-1 autocorrelation ⇒ N_eff < N.
    rng = np.random.default_rng(1)
    n = 2000
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.6 * x[i - 1] + rng.standard_normal()  # ρ ≈ 0.6
    prof = profile_asset(x, lockbox_periods=200, periods_per_year=HOURLY)
    assert prof.usable_periods == n
    assert prof.autocorrelation > 0.4
    assert prof.effective_sample < n  # discounted
    assert prof.effective_sample > 0
    assert prof.effective_years == prof.effective_sample / HOURLY


def test_iid_series_has_near_full_effective_sample():
    x = _series(2000, seed=2)
    prof = profile_asset(x, lockbox_periods=200, periods_per_year=HOURLY)
    assert prof.autocorrelation < 0.1
    # Near full (no serial-correlation discount) — within a tolerance band.
    assert prof.effective_sample > 0.8 * prof.usable_periods


def test_budget_upper_bound_is_small_on_short_crypto_history():
    # ~1.5 yr of HOURLY crypto bars ⇒ a small single-digit honest budget (MinBTL).
    x = _series(int(1.5 * HOURLY), seed=3)  # ~13140 hourly bars
    prof = profile_asset(x, lockbox_periods=int(2 / 12 * HOURLY), periods_per_year=HOURLY)
    assert 1 <= prof.budget_upper_bound <= 9


def test_budget_grows_with_more_effective_history():
    # Short crypto (1.5 yr hourly) vs long equity-scale (10 yr daily) ⇒ budget grows.
    short = profile_asset(_series(int(1.5 * HOURLY), seed=4), lockbox_periods=1000, periods_per_year=HOURLY)
    long = profile_asset(_series(10 * 252, seed=4), lockbox_periods=252, periods_per_year=252.0)
    assert long.budget_upper_bound > short.budget_upper_bound


def test_lockbox_mde_shrinks_with_a_longer_lockbox():
    # Both hourly; a longer (more calendar) Lockbox ⇒ smaller MDE.
    thin = profile_asset(_series(30000, seed=5), lockbox_periods=int(1 / 12 * HOURLY), periods_per_year=HOURLY)
    thick = profile_asset(_series(60000, seed=5), lockbox_periods=int(1.5 * HOURLY), periods_per_year=HOURLY)
    assert thin.lockbox_mde > thick.lockbox_mde
    assert math.isfinite(thick.lockbox_mde)


def test_window_sizing_splits_non_lockbox_history():
    prof = profile_asset(_series(4000, seed=6), lockbox_periods=1000, train_test_ratio=3.0)
    # ~3:1 train:test over the 3000 non-lockbox periods.
    assert prof.lockbox_periods == 1000
    assert prof.train_periods > prof.test_periods
    assert abs((prof.train_periods + prof.test_periods) - 3000) <= 2


def test_regime_count_distinguishes_single_from_multi_regime():
    # Single-regime: constant volatility.
    single = profile_asset(_series(3000, sd=0.01, seed=7), lockbox_periods=200)
    # Multi-regime: a calm half and a turbulent half.
    rng = np.random.default_rng(8)
    multi_vals = np.concatenate(
        [0.003 * rng.standard_normal(1500), 0.05 * rng.standard_normal(1500)]
    )
    multi = profile_asset(multi_vals, lockbox_periods=200)
    assert multi.effective_regimes >= single.effective_regimes


def test_cross_section_breadth_collapses_for_comoving_legs():
    n = 1000
    base = _series(n, seed=9)
    comoving = {s: base + 1e-6 * _series(n, seed=100 + i) for i, s in enumerate("ABC")}
    prof_co = profile_asset(base, cross_section_legs=comoving, lockbox_periods=120)
    assert prof_co.cross_section_breadth < 1.5
    assert prof_co.mean_pairwise_correlation > 0.9
    independent = {s: _series(n, seed=200 + i) for i, s in enumerate("ABC")}
    prof_ind = profile_asset(base, cross_section_legs=independent, lockbox_periods=120)
    assert prof_ind.cross_section_breadth > 2.0


# --------------------------------------------------------------------------- #
# FR-G2 / AC-5 — data-sufficiency gate.
# --------------------------------------------------------------------------- #


def test_ac5_lockbox_mde_above_claimed_edge_is_insufficient_evidence():
    """AC-5: an asset whose Lockbox MDE exceeds the claimed edge ⇒ insufficient-evidence.

    A 1-month hourly Lockbox cannot power a Sharpe-~1 confirmation; a candidate claiming an
    edge below that MDE is reported insufficient, never confirmed.
    """
    prof = profile_asset(
        _series(30000, seed=11), lockbox_periods=int(1 / 12 * HOURLY), periods_per_year=HOURLY
    )
    assert prof.lockbox_mde > 1.0  # a thin Lockbox needs a big edge to confirm
    verdict = assess_sufficiency(prof, claimed_edge=prof.lockbox_mde * 0.5)
    assert verdict.verdict == "insufficient_evidence"
    assert "cannot power" in verdict.detail


def test_ac5_powered_asset_is_admissible():
    # A thick (calendar-long) Lockbox ⇒ small MDE ⇒ a modest claimed edge is confirmable.
    prof = profile_asset(
        _series(80000, seed=12), lockbox_periods=int(2.0 * HOURLY), periods_per_year=HOURLY
    )
    verdict = assess_sufficiency(prof, claimed_edge=prof.lockbox_mde * 2.0)
    assert verdict.verdict == "admissible"


def test_insufficient_when_effective_sample_below_floor():
    # Tiny history ⇒ effective sample below the honest-trial floor regardless of MDE.
    prof = profile_asset(_series(20, seed=13), lockbox_periods=5, periods_per_year=HOURLY)
    verdict = assess_sufficiency(prof, claimed_edge=10.0, min_effective_sample=30.0)
    assert verdict.verdict == "insufficient_evidence"
    assert "effective sample" in verdict.detail


def test_sufficiency_gate_never_lowers_the_bar():
    # Even with a huge claimed edge, a below-floor effective sample stays insufficient
    # (the gate reports under-power; it does not manufacture a verdict).
    prof = profile_asset(_series(15, seed=14), lockbox_periods=4, periods_per_year=HOURLY)
    v = assess_sufficiency(prof, claimed_edge=100.0)
    assert v.verdict == "insufficient_evidence"


# --------------------------------------------------------------------------- #
# Fail-closed hardening (no gate-gaming via degenerate inputs).
# --------------------------------------------------------------------------- #


def test_non_finite_bars_are_not_counted_as_usable_evidence():
    # An all-NaN series carries NO usable history ⇒ effective sample 0 ⇒ insufficient.
    nan_series = np.full(int(5 * HOURLY), np.nan)
    prof = profile_asset(nan_series, lockbox_periods=int(HOURLY), periods_per_year=HOURLY)
    assert prof.usable_periods == 0
    assert prof.effective_sample == 0.0
    v = assess_sufficiency(prof, claimed_edge=100.0)
    assert v.verdict == "insufficient_evidence"


def test_partial_nan_series_counts_only_finite_bars():
    x = _series(2000, seed=15)
    x[::3] = np.nan  # a third of the bars are non-finite
    prof = profile_asset(x, lockbox_periods=100, periods_per_year=HOURLY)
    assert prof.usable_periods == int(np.count_nonzero(np.isfinite(x)))
    assert prof.usable_periods < 2000


def test_invalid_periods_per_year_fails_closed():
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="periods_per_year"):
            profile_asset(_series(1000, seed=16), lockbox_periods=100, periods_per_year=bad)


def test_non_finite_claimed_edge_is_insufficient_evidence():
    prof = profile_asset(_series(80000, seed=17), lockbox_periods=int(2.0 * HOURLY), periods_per_year=HOURLY)
    # A powered asset (small MDE) still refuses a non-finite claim — fail closed.
    for bad in (float("nan"), float("inf")):
        v = assess_sufficiency(prof, claimed_edge=bad)
        assert v.verdict == "insufficient_evidence"
