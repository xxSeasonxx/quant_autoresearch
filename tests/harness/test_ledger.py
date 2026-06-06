"""Trial Ledger — append-only, lossless round-trip, fail-safe (FR-E1, I1, I2, NFR-6).

Unit-level guarantees the campaign and the P4 audit depend on:
- a persisted row reconstructs its per-fold arrays + ResResult bit-for-bit (the storage half
  of AC-7; metric *re-derivation* from the fingerprint is in ``test_selection_budget.py``);
- the ledger is append-only and a reserved-but-crashed look stays charged (FR-I2/NFR-6);
- the read API P4 consumes (full per-fold returns of every trial, grouped by family).
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.ledger import LedgerError, Reservation, TrialLedger
from harness.objective.gates import GateOutcome
from harness.objective.res import ResResult
from harness.testing import make_returns

PPY = 8760.0


def _res(rank: float | None = 1.4, feasible: bool = True) -> ResResult:
    gate = GateOutcome(name="evidence", passed=True, value=120.0, threshold=30.0, detail="ok")
    return ResResult(
        feasible=feasible,
        gate_results={"evidence": gate},
        rank_sharpe=rank,
        per_fold_sharpe=(1.1, 1.5, 1.6),
        residual_info_ratio=0.02,
        psr=0.97,
    )


def _folds() -> list:
    rng = np.random.default_rng(7)
    f1 = make_returns(0.0005 + 0.01 * rng.standard_normal(240), periods_per_year=PPY)
    by_symbol = {
        "AAA": make_returns(0.0004 + 0.01 * rng.standard_normal(240), periods_per_year=PPY),
        "BBB": make_returns(0.0006 + 0.01 * rng.standard_normal(240), periods_per_year=PPY),
    }
    f2 = make_returns(0.0006 + 0.012 * rng.standard_normal(240), periods_per_year=PPY, by_symbol=by_symbol)
    return [f1, f2]


def _reserve_and_finalize(ledger: TrialLedger, trial_id: str = "t1"):
    res = ledger.reserve(
        trial_id=trial_id,
        family_id="fam-abc",
        experiment_hash="exp-123",
        protocol_hash="proto-xyz",
        thesis="effect/observable/falsifier",
        reserved_at="2026-06-05T00:00:00Z",
        dataset_id="ds-1",
    )
    return ledger.finalize(
        res,
        per_fold_returns=_folds(),
        res=_res(),
        provenance={"snapshot": "snap-1", "foundation_version": "1.2", "backend_version": "3.4"},
        created_at="2026-06-05T00:01:00Z",
    )


def test_row_round_trips_bit_for_bit_from_disk(tmp_path):
    """AC-7 (storage): a persisted row reconstructs its per-fold arrays + ResResult exactly."""
    path = tmp_path / "ledger.jsonl"
    written = _reserve_and_finalize(TrialLedger(path))

    reread = TrialLedger(path).rows()
    assert len(reread) == 1
    row = reread[0]

    assert row.trial_id == written.trial_id
    assert row.family_id == "fam-abc"
    assert row.experiment_hash == "exp-123"
    assert row.protocol_hash == "proto-xyz"
    assert row.dataset_id == "ds-1"
    assert row.provenance["snapshot"] == "snap-1"
    assert row.created_at == "2026-06-05T00:01:00Z"

    # Per-fold arrays are bit-exact (raw-byte base64, not float-string).
    for got, exp in zip(row.per_fold_returns, written.per_fold_returns):
        assert np.array_equal(got.values, exp.values)
        assert got.values.dtype == exp.values.dtype
        assert np.array_equal(got.timestamps.astype("datetime64[ns]"), exp.timestamps.astype("datetime64[ns]"))
        assert got.periods_per_year == exp.periods_per_year
    # by_symbol legs round-trip too.
    leg = row.per_fold_returns[1].by_symbol
    assert leg is not None and set(leg) == {"AAA", "BBB"}
    assert np.array_equal(leg["AAA"].values, written.per_fold_returns[1].by_symbol["AAA"].values)

    # ResResult round-trips (incl. gate outcomes and the per-fold Sharpe evidence unit).
    assert row.res.feasible is True
    assert row.res.rank_sharpe == pytest.approx(1.4)
    assert row.res.per_fold_sharpe == (1.1, 1.5, 1.6)
    assert row.res.gate_results["evidence"].passed is True
    assert row.res.gate_results["evidence"].value == pytest.approx(120.0)


def test_extreme_float_values_round_trip_exactly(tmp_path):
    """Inf / -inf / tiny / huge values survive the raw-byte encoding (no precision loss)."""
    path = tmp_path / "led.jsonl"
    led = TrialLedger(path)
    vals = np.array([1e-300, -1e300, np.inf, -np.inf, 0.1, 1.0 / 3.0], dtype=np.float64)
    fold = make_returns(vals, periods_per_year=PPY)
    r = led.reserve(
        trial_id="x", family_id="f", experiment_hash="e", protocol_hash="p",
        thesis="t", reserved_at="2026-06-05T00:00:00Z",
    )
    led.finalize(r, per_fold_returns=[fold], res=_res(rank=None, feasible=False),
                 provenance={"snapshot": "s"}, created_at="2026-06-05T00:00:01Z")
    got = TrialLedger(path).rows()[0].per_fold_returns[0].values
    # NaN-free here, so exact equality including the infinities.
    assert np.array_equal(got, vals)
    assert got.tobytes() == vals.tobytes()


def test_ledger_is_append_only_no_reuse_no_rewrite(tmp_path):
    led = TrialLedger(tmp_path / "l.jsonl")
    _reserve_and_finalize(led)
    # Re-finalizing the same reservation must fail (rows are never rewritten).
    dup = Reservation(
        trial_id="t1", family_id="fam-abc", experiment_hash="exp-123",
        protocol_hash="proto-xyz", thesis="t", reserved_at="2026-06-05T00:00:00Z",
    )
    with pytest.raises(LedgerError):
        led.finalize(
            dup, per_fold_returns=_folds(), res=_res(),
            provenance={"snapshot": "s"}, created_at="2026-06-05T00:02:00Z",
        )
    # Reusing a trial_id for a new reservation must fail.
    with pytest.raises(LedgerError):
        led.reserve(
            trial_id="t1", family_id="f", experiment_hash="e", protocol_hash="p",
            thesis="t", reserved_at="2026-06-05T00:03:00Z",
        )


def test_crash_between_reserve_and_finalize_keeps_the_look_charged(tmp_path):
    """FR-I2 / NFR-6: a reserved-but-never-finalized look is still charged (never lost) and the
    ledger stays consistent. We simulate the crash by reserving, then opening a FRESH ledger from
    the same file WITHOUT finalizing (as a crashed process would see it)."""
    path = tmp_path / "crash.jsonl"
    led = TrialLedger(path)
    led.reserve(
        trial_id="t-crash", family_id="f", experiment_hash="e", protocol_hash="p",
        thesis="t", reserved_at="2026-06-05T00:00:00Z",
    )
    # --- crash here: no finalize ---
    recovered = TrialLedger(path)
    assert recovered.charged_count() == 1  # the look counts: budget was spent
    assert "t-crash" in recovered.charged_trial_ids()
    assert recovered.pending_reservations() == ["t-crash"]  # visible as charged-but-no-row
    assert recovered.rows() == []  # no finalized row (the look produced no evidence)
    assert len(recovered) == 0  # __len__ counts finalized rows


def test_charged_count_counts_reservations_not_just_rows(tmp_path):
    led = TrialLedger(tmp_path / "c.jsonl")
    _reserve_and_finalize(led, "t1")
    led.reserve(trial_id="t2", family_id="f", experiment_hash="e", protocol_hash="p",
                thesis="t", reserved_at="2026-06-05T00:05:00Z")  # reserved, crashed
    assert led.charged_count() == 2  # both spent budget
    assert len(led.rows()) == 1  # only one finalized


def test_rows_by_family_groups_for_the_audit(tmp_path):
    led = TrialLedger(tmp_path / "g.jsonl")
    for tid, fam in [("a", "F1"), ("b", "F1"), ("c", "F2")]:
        r = led.reserve(trial_id=tid, family_id=fam, experiment_hash="e", protocol_hash="p",
                        thesis="t", reserved_at="2026-06-05T00:00:00Z")
        led.finalize(r, per_fold_returns=_folds(), res=_res(),
                     provenance={"snapshot": "s"}, created_at="2026-06-05T00:00:01Z")
    grouped = led.rows_by_family()
    assert set(grouped) == {"F1", "F2"}
    assert {row.trial_id for row in grouped["F1"]} == {"a", "b"}
    # Every grouped row carries its FULL per-fold returns (the audit needs them).
    assert all(len(row.per_fold_returns) == 2 for rows in grouped.values() for row in rows)


def test_finalize_unknown_reservation_raises(tmp_path):
    from harness.ledger import Reservation

    led = TrialLedger(tmp_path / "u.jsonl")
    with pytest.raises(LedgerError):
        led.finalize(
            Reservation(trial_id="ghost", family_id="f", experiment_hash="e",
                        protocol_hash="p", thesis="t", reserved_at="2026-06-05T00:00:00Z"),
            per_fold_returns=_folds(), res=_res(),
            provenance={"snapshot": "s"}, created_at="2026-06-05T00:00:01Z",
        )
