"""Lockbox Manager tests — AC-5 (the verdict layer) + the trichotomy + write-once (FR-F2).

AC-5: a candidate whose claimed edge < Lockbox MDE ⇒ ``insufficient_evidence``, never
``confirmed`` — the harness never manufactures a verdict the data cannot power (Principle 6).
A thin forward block ⇒ the block-bootstrap is the binding test.

Also covered: ``confirmed`` / ``rejected`` on a powered block; write-once-per-dataset
refusal; determinism (bit-for-bit). The forward block is fed through ``FakeFoundationGateway``
so the verdict is deterministic with synthetic returns (no live data, no engine call).
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from harness.data.lockbox_book import LockboxBook, LockboxSpentError
from harness.foundation import FoldEvalResult
from harness.lockbox import (
    LockboxError,
    _binding_test_for,
    _bootstrap_sharpe_lower_bound,
    _lockbox_seed,
    confirm_on_lockbox,
)
from harness.profiler import AssetProfile, profile_asset
from harness.protocol import Experiment, Protocol
from harness.testing import benign_funding_carry, make_returns

HOURLY = 8760.0


def _protocol() -> Protocol:
    return Protocol.model_validate(
        {
            "name": "lockbox-test",
            "cost_model": {"taker_bps": 5, "maker_bps": 1, "slippage_bps": 1},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-03-31"},
                "selection": {"start": "2024-04-01", "end": "2024-10-31"},
                "lockbox": {"start": "2024-11-01", "end": "2024-12-31"},
                "symbols": ["AAA-PERP", "BBB-PERP"],
                "source": {"kind": "crypto_perp_funding"},
            },
            "annualization": {"periods_per_year": HOURLY},
        }
    )


def _experiment() -> Experiment:
    return Experiment(strategy_path="strategy.py", params={"w": 0.1})


def _gateway_returning(values: np.ndarray):
    """A FoundationGateway whose single Lockbox evaluate returns the given return series.

    ``panel_for`` returns a COVERING panel of benign NON-DEGENERATE columns (market +
    funding_carry) aligned to the series: each column is present, finite, and genuinely varies
    (small noise) so it satisfies the Protocol's required-factor coverage (the factor wall requires
    columns be USABLE — actually removable — not merely present, AC-9/G2). The columns are small
    (sd≈1e-4) and INDEPENDENT of the synthetic return series, so their estimated beta is ≈0 and the
    residual ≈ the raw series — the confirmed/rejected assertions remain about the same return
    distribution. The driverless synthetic series has no real factor exposure, so an independent
    benign panel neutralizes ≈nothing while staying honest (no degenerate fake-covering column).
    Seeds are derived deterministically from the series so the verdict stays bit-for-bit
    reproducible (NFR-1)."""
    fr = make_returns(np.asarray(values, dtype=np.float64), periods_per_year=HOURLY)
    n = fr.values.shape[0]
    # Deterministic seed from the series (hashlib, not builtin hash — no PYTHONHASHSEED dependence)
    # so the verdict stays bit-for-bit reproducible across processes (NFR-1).
    seed = int.from_bytes(hashlib.sha256(fr.values.tobytes()).digest()[:4], "big")
    covering_panel = {
        "market": benign_funding_carry(n, seed=seed + 11),
        "funding_carry": benign_funding_carry(n, seed=seed + 22),
    }

    class _GW:
        def __init__(self):
            self.evaluate_calls = []

        def quick_run(self, *a, **k):  # pragma: no cover - unused
            raise NotImplementedError

        def evaluate(self, experiment, protocol, window):  # noqa: ARG002
            self.evaluate_calls.append(window)
            return FoldEvalResult(
                succeeded=True, causal_ok=True, returns=fr, sharpe=None, sortino=None,
                calmar=None, max_drawdown=-0.1, trade_count=200, worst_period_return=-0.03,
                provenance={"snapshot": "synthetic"}, failure_stage=None,
            )

        def panel_for(self, window, returns):  # noqa: ARG002
            return covering_panel

    return _GW()


def _profile_with_mde(mde: float, *, lockbox_periods: int = 1000) -> AssetProfile:
    """A hand-built profile with a chosen Lockbox MDE (the power bar), other fields plausible."""
    return AssetProfile(
        usable_periods=40000,
        autocorrelation=0.1,
        effective_sample=30000.0,
        effective_years=3.0,
        effective_regimes=3,
        cross_section_breadth=2.0,
        mean_pairwise_correlation=0.3,
        budget_upper_bound=8,
        train_periods=30000,
        test_periods=9000,
        lockbox_periods=lockbox_periods,
        lockbox_mde=mde,
    )


def _edged_series(n: int, seed: int, mean: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return mean + 0.01 * rng.standard_normal(n)


# --------------------------------------------------------------------------- #
# AC-5 — claimed edge < MDE ⇒ insufficient_evidence, never confirmed.
# --------------------------------------------------------------------------- #


def test_ac5_claimed_edge_below_mde_is_insufficient_evidence_not_confirmed():
    """The headline AC-5 assertion at the verdict layer: even with a strongly positive
    forward block, an UNPOWERED Lockbox (MDE > claimed edge) returns insufficient_evidence —
    the power gate runs BEFORE any confirmation logic, so confirmed is unrepresentable here."""
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=2.0)  # needs a Sharpe-2 edge to confirm
    # A genuinely strong forward block — would "look" confirmable — but the claim is below MDE.
    gw = _gateway_returning(_edged_series(1000, seed=1, mean=0.004))
    book = LockboxBook()

    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=1.0,  # 1.0 < MDE 2.0
        gateway=gw, book=book, trial_id="t1", spent_at="2025-01-01T00:00:00",
    )

    assert verdict.verdict == "insufficient_evidence"
    assert verdict.verdict != "confirmed"
    assert verdict.mde == 2.0 and verdict.claimed_edge == 1.0
    # The power gate ran BEFORE scoring: no evaluate, no Lockbox spend.
    assert gw.evaluate_calls == []
    assert book._spent == {}  # nothing reserved (the gate returned before the spend)


def test_ac5_non_finite_mde_is_insufficient_evidence():
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=float("inf"))  # an unpowered (thin) Lockbox
    gw = _gateway_returning(_edged_series(500, seed=2, mean=0.003))
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=1.5,
        gateway=gw, book=LockboxBook(), trial_id="t", spent_at="2025-01-01T00:00:00",
    )
    assert verdict.verdict == "insufficient_evidence"
    assert gw.evaluate_calls == []


def test_ac5_non_finite_or_nonpositive_claimed_edge_is_insufficient_evidence():
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.5)
    for bad in (float("nan"), 0.0, -1.0):
        gw = _gateway_returning(_edged_series(500, seed=3, mean=0.003))
        verdict = confirm_on_lockbox(
            exp, proto, profile, claimed_edge=bad,
            gateway=gw, book=LockboxBook(), trial_id="t", spent_at="2025-01-01T00:00:00",
        )
        assert verdict.verdict == "insufficient_evidence"
        assert gw.evaluate_calls == []  # never scored an unconfirmable claim


def test_ac5_thin_forward_block_makes_block_bootstrap_binding():
    """On a thin (short-calendar) Lockbox the binding test is the block-bootstrap CI, with the
    forward block as a sanity check (FR-F2). Use a real profiler-derived thin Lockbox."""
    # A thin Lockbox (1 month of hourly) ⇒ large MDE; pick a claimed edge above MDE-thickness
    # margin but the block is still not "comfortably" powered ⇒ bootstrap binding.
    prof = profile_asset(
        _edged_series(30000, seed=4, mean=0.0), lockbox_periods=int(1 / 12 * HOURLY),
        periods_per_year=HOURLY,
    )
    # claimed_edge just above MDE so the power gate passes, but mde > 0.5*claimed ⇒ thin.
    claimed = prof.lockbox_mde * 1.2
    assert _binding_test_for(prof, claimed) == "block_bootstrap"


def test_thick_forward_block_makes_forward_binding():
    """A comfortably-powered (thick) Lockbox makes the forward block binding."""
    prof = profile_asset(
        _edged_series(80000, seed=5, mean=0.0), lockbox_periods=int(2.0 * HOURLY),
        periods_per_year=HOURLY,
    )
    claimed = prof.lockbox_mde * 5.0  # well above the thickness margin
    assert _binding_test_for(prof, claimed) == "forward_block"


# --------------------------------------------------------------------------- #
# confirmed / rejected on a powered block.
# --------------------------------------------------------------------------- #


def test_confirmed_on_a_powered_block_with_a_real_edge():
    """A powered Lockbox (MDE below claimed edge) + a genuinely positive forward block whose
    bootstrap lower bound clears 0 ⇒ confirmed."""
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.3)  # powered for a Sharpe-1 claim
    # Strong, clean positive drift over a long block ⇒ lower CI bound > 0.
    gw = _gateway_returning(_edged_series(5000, seed=6, mean=0.0015))
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=1.0,
        gateway=gw, book=LockboxBook(), trial_id="t", spent_at="2025-01-01T00:00:00",
        factor_panel_provider=gw.panel_for,
    )
    assert verdict.verdict == "confirmed"
    assert verdict.lower_bound is not None and verdict.lower_bound > 0.0
    assert verdict.forward_sharpe is not None and verdict.forward_sharpe > 0.0
    assert len(gw.evaluate_calls) == 1  # scored exactly once (FR-J2)


def test_rejected_when_a_powered_block_comes_back_flat():
    """A powered Lockbox but a flat/zero-mean forward block ⇒ the lower CI bound cannot clear
    0 ⇒ rejected (NOT insufficient_evidence — the block WAS powered)."""
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.3)  # powered
    gw = _gateway_returning(_edged_series(5000, seed=7, mean=0.0))  # true zero edge
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=1.0,
        gateway=gw, book=LockboxBook(), trial_id="t", spent_at="2025-01-01T00:00:00",
        factor_panel_provider=gw.panel_for,
    )
    assert verdict.verdict == "rejected"
    assert verdict.lower_bound is not None and verdict.lower_bound <= 0.0


def test_rejected_when_a_powered_block_is_negative():
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.3)
    gw = _gateway_returning(_edged_series(5000, seed=8, mean=-0.001))  # negative drift
    verdict = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=1.0,
        gateway=gw, book=LockboxBook(), trial_id="t", spent_at="2025-01-01T00:00:00",
        factor_panel_provider=gw.panel_for,
    )
    assert verdict.verdict == "rejected"


# --------------------------------------------------------------------------- #
# Write-once per dataset (FR-B4).
# --------------------------------------------------------------------------- #


def test_write_once_a_second_graduation_on_the_same_dataset_is_refused():
    """A second confirmation on the SAME Lockbox dataset raises LockboxSpentError — the reserve
    is the gate, BEFORE scoring (FR-B4)."""
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.3)
    book = LockboxBook()

    gw1 = _gateway_returning(_edged_series(5000, seed=9, mean=0.0015))
    v1 = confirm_on_lockbox(
        exp, proto, profile, claimed_edge=1.0,
        gateway=gw1, book=book, trial_id="first", spent_at="2025-01-01T00:00:00",
        factor_panel_provider=gw1.panel_for,
    )
    assert v1.verdict in ("confirmed", "rejected")

    # A second graduation on the same dataset (same protocol/span/symbols) is refused.
    gw2 = _gateway_returning(_edged_series(5000, seed=10, mean=0.0015))
    with pytest.raises(LockboxSpentError):
        confirm_on_lockbox(
            exp, proto, profile, claimed_edge=1.0,
            gateway=gw2, book=book, trial_id="second", spent_at="2025-02-01T00:00:00",
            factor_panel_provider=gw2.panel_for,
        )
    assert gw2.evaluate_calls == []  # the refused second graduation never scored


def test_write_once_does_not_charge_an_insufficient_evidence_verdict():
    """An insufficient_evidence verdict returns BEFORE the reserve, so the block is NOT spent —
    a later powered graduation on the same block can still run."""
    proto, exp = _protocol(), _experiment()
    book = LockboxBook()
    # First: unpowered claim ⇒ insufficient_evidence, no spend.
    unpowered = _profile_with_mde(mde=2.0)
    gw1 = _gateway_returning(_edged_series(5000, seed=11, mean=0.0015))
    v1 = confirm_on_lockbox(
        exp, proto, unpowered, claimed_edge=1.0,
        gateway=gw1, book=book, trial_id="a", spent_at="2025-01-01T00:00:00",
    )
    assert v1.verdict == "insufficient_evidence"
    # The block was NOT spent (the power gate returned before reserve) ⇒ a real graduation runs.
    powered = _profile_with_mde(mde=0.3)
    gw2 = _gateway_returning(_edged_series(5000, seed=12, mean=0.0015))
    v2 = confirm_on_lockbox(
        exp, proto, powered, claimed_edge=1.0,
        gateway=gw2, book=book, trial_id="b", spent_at="2025-02-01T00:00:00",
        factor_panel_provider=gw2.panel_for,
    )
    assert v2.verdict in ("confirmed", "rejected")
    assert len(gw2.evaluate_calls) == 1


# --------------------------------------------------------------------------- #
# Determinism (NFR-1).
# --------------------------------------------------------------------------- #


def test_lockbox_verdict_is_deterministic_bit_for_bit():
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.3)
    series = _edged_series(4000, seed=20, mean=0.0008)

    def run():
        gw = _gateway_returning(series)
        return confirm_on_lockbox(
            exp, proto, profile, claimed_edge=1.0,
            gateway=gw, book=LockboxBook(),
            trial_id="t", spent_at="2025-01-01T00:00:00",
            factor_panel_provider=gw.panel_for,
        )

    a, b = run(), run()
    assert a.verdict == b.verdict
    assert a.lower_bound == b.lower_bound
    assert a.forward_sharpe == b.forward_sharpe


def test_lockbox_seed_is_a_pure_function_of_inputs():
    assert _lockbox_seed("ds1", "fp1") == _lockbox_seed("ds1", "fp1")
    assert _lockbox_seed("ds1", "fp1") != _lockbox_seed("ds2", "fp1")
    assert _lockbox_seed("ds1", "fp1") != _lockbox_seed("ds1", "fp2")


def test_lockbox_evaluate_failure_raises():
    """A Lockbox evaluate that did not produce a return series raises (cannot confirm)."""
    proto, exp = _protocol(), _experiment()
    profile = _profile_with_mde(mde=0.3)

    class _FailGW:
        def quick_run(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        def evaluate(self, *a, **k):
            return FoldEvalResult(
                succeeded=False, causal_ok=False, returns=None, sharpe=None, sortino=None,
                calmar=None, max_drawdown=None, trade_count=0, worst_period_return=None,
                provenance={}, failure_stage="contract",
            )

        def panel_for(self, window, returns):  # pragma: no cover - evaluate fails before this
            return {"market": np.zeros(0), "funding_carry": np.zeros(0)}

    with pytest.raises(LockboxError):
        confirm_on_lockbox(
            exp, proto, profile, claimed_edge=1.0,
            gateway=_FailGW(), book=LockboxBook(), trial_id="t", spent_at="2025-01-01T00:00:00",
            factor_panel_provider=_FailGW().panel_for,
        )


# --------------------------------------------------------------------------- #
# Serial-correlation false-confirm control (the binding-CI counterpart of AC-6's audit fix).
# --------------------------------------------------------------------------- #


def _ar1_zero_sharpe(n: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    """A TRUE-ZERO-Sharpe (mean-0) AR(1) return series — the Lockbox null under serial
    correlation (the regime where a too-short block under-widens the CI)."""
    eps = rng.standard_normal(n) * 0.01
    x = np.empty(n)
    x[0] = eps[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + eps[t]
    return x


@pytest.mark.parametrize("phi", [0.0, 0.3, 0.6, 0.8])
def test_lockbox_false_confirm_rate_controlled_under_serial_correlation(phi: float):
    """The Lockbox ``confirmed`` verdict turns on the block-bootstrap lower CI bound clearing 0
    AND a positive point estimate. Under a TRUE-ZERO Sharpe with AR(1) memory, the rate of that
    event (a false confirm — the FINAL wall passing noise) must stay ≤ the one-sided level
    ``1-confidence`` (+ MC slack). A fixed ``n**(1/3)`` block under-widened the CI and breached
    this (φ=0.6 ~0.07, φ=0.8 ~0.12); the Politis-White data-driven block restores control.

    Measured directly on the binding primitive ``_bootstrap_sharpe_lower_bound`` (the CI that
    decides ``confirmed``) over many deterministic seeds. Tolerance: with S=150 seeds the
    binomial SE at the 0.05 level is ~0.018; the 0.04 allowance (≈ 2.2 SE) is MC slack — the
    pre-fix φ=0.8 rate (~0.12) still blows through 0.09, so this fails loudly on the old block."""
    confidence = 0.95
    n, n_seeds, n_bootstrap = 500, 150, 250
    false_confirms = 0
    for seed in range(n_seeds):
        values = _ar1_zero_sharpe(n, phi, np.random.default_rng(seed * 13 + 1))
        boot_rng = np.random.default_rng(seed * 13 + 7)
        point, lower = _bootstrap_sharpe_lower_bound(
            values, HOURLY, boot_rng, confidence=confidence, n_bootstrap=n_bootstrap
        )
        if lower is not None and point is not None and lower > 0.0 and point > 0.0:
            false_confirms += 1
    rate = false_confirms / n_seeds
    one_sided_level = 1.0 - confidence
    assert rate <= one_sided_level + 0.04, (
        f"AR(1) φ={phi}: Lockbox false-confirm rate {rate:.3f} exceeds the one-sided level "
        f"{one_sided_level} + 0.04 (block-bootstrap CI under-widening under serial correlation)"
    )
