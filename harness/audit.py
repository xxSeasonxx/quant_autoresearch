"""Graduation Auditor — the returns-based selection-bias correction (FR-F1, AC-6).

A backtest is a biased estimator and the bias grows with the number of trials (Principle 1):
the best of K configs is, by the False Strategy Theorem, almost guaranteed to *look* good even
when every true edge is zero. The budget (P3) BOUNDS how many looks a campaign may take; this
module CORRECTS the residual selection bias of the survivors by auditing over the logged
per-fold OOS returns of **every** trial — not just the finalists.

**Romano-Wolf stepdown is the PRIMARY correction and is binding for AC-6.** It controls the
family-wise error rate (FWER) over the K competing trials' OOS performance statistic using a
bootstrap that operates on the LOGGED RETURNS of all trials, so it absorbs cross-trial
correlation DIRECTLY — no ``N=K`` shortcut, no separate ``N_effective`` estimate.

How the correlation is absorbed (the key design choice)
--------------------------------------------------------
Each trial has a per-fold OOS return series. We align the K trials' pooled OOS tracks into a
common ``(T, K)`` matrix on their **shared timestamp index** — the INTERSECTION of the trials'
bar timestamps, so row ``t`` of every column is the same calendar bar (genuinely
contemporaneous). Non-finite bars are dropped on that intersection consistently across all
columns, so a missing bar in one trial never positionally shifts another. We then **resample
whole blocks on a SHARED index across all K columns at once**: a single set of circular
block-start indices is drawn per bootstrap replicate and applied to every column simultaneously,
so if trials co-move at time t that co-movement is carried into every replicate. The bootstrap
distribution of the *max* studentized statistic therefore widens exactly as much as the trials
are correlated — the correlation absorption FR-F1 demands. Per-column centering (subtract each
column's mean) imposes the joint null H0: every trial's true mean is zero.

Statistic
---------
Per trial, the one-sided studentized mean of its pooled OOS return track ``t_i = mean_i/SE_i``
with a **HAC (Newey-West) long-run-variance** SE — ``SE = sqrt(LRV/n)``, not the iid
``std/sqrt(n)``. The HAC scale is the serial-correlation-corrected variance of the sample mean,
so the statistic is asymptotically PIVOTAL under AR(p) within-trial memory: the same long-run
scale divides the observed mean and every bootstrap-null mean, so the null distribution matches
the observed sampling distribution and FWER is controlled even when a finite block length cannot
fully recover the autocorrelation (the iid SE under-states the mean's variance once φ≥0.3 and
let AR(1) noise graduate above α — the HAC SE is the root fix). Monotone in Sharpe for a fixed
sample; one-sided because only a *positive* edge is a graduation candidate. The block bootstrap
uses a **data-driven (Politis-White) block length** so it also carries the within-trial memory.
Together these make the procedure correlation- and heteroskedasticity-robust.

Determinism (NFR-1, AC-7-critical)
----------------------------------
The bootstrap RNG is ``np.random.default_rng(seed)`` where ``seed`` is a pure function of the
inputs — SHA-256 over the Protocol hash + the **sorted** trial fingerprints, folded to 64 bits
(``_audit_seed``). No clock, no unseeded RNG. Identical inputs ⇒ identical block draws ⇒
bit-identical critical values and verdict. Sorting the fingerprints makes the seed invariant to
ledger row order (the audit population is a *set*).

Complementary diagnostics
-------------------------
- **PBO (CSCV)** — the probability of backtest overfitting via combinatorially-symmetric
  cross-validation: over all ``C(S, S/2)`` time-block train/test partitions, how often the
  in-sample-best trial lands below the OOS median. A complementary diagnostic, NOT binding.
- **BHY** — Benjamini-Hochberg-Yekutieli step-up with the ``c(K)=Σ1/i`` arbitrary-dependence
  correction over per-trial bootstrap p-values. The documented simpler fallback, NOT binding.

Pure numpy: no scipy needed (the normal quantiles RES/profiler need live elsewhere; the audit
is bootstrap-based, so it needs only sampling + quantiles). No ``quant_strategies`` import.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Mapping, Sequence

import numpy as np

from harness.bootstrap import (
    circular_block_indices,
    newey_west_lrv,
    nw_lag,
    politis_white_block,
)
from harness.ledger import LedgerRow

_EPS = 1e-12

# Default family-wise error rate for the Romano-Wolf step-down (the audit's confidence level).
DEFAULT_ALPHA = 0.05
# Default bootstrap replicate count. Large enough for stable 95% quantiles; deterministic.
DEFAULT_N_BOOTSTRAP = 2000
# Default number of CSCV time blocks for PBO (must be even; S=16 → C(16,8)=12870 splits).
DEFAULT_PBO_BLOCKS = 16


# --------------------------------------------------------------------------- #
# Result type (the audit population verdict the graduation rule consumes).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TrialStat:
    """One trial's audit statistics (observability, NFR-5)."""

    trial_id: str
    n: int  # the aligned (common) track length used in the audit
    mean: float  # pooled OOS per-period mean return
    studentized: float  # the one-sided test statistic mean/SE (None-safe: 0.0 if degenerate)
    p_value: float  # bootstrap one-sided p-value (max-null adjusted is in `rejected`)
    romano_wolf_reject: bool  # rejected H0 at the configured FWER level (the BINDING verdict)
    bhy_reject: bool  # rejected by the BHY fallback (diagnostic)


@dataclass(frozen=True)
class AuditResult:
    """The trial-population audit verdict (FR-F1).

    ``survivors`` is the Romano-Wolf FWER-controlled set — the BINDING criterion for AC-6 and
    the set the graduation rule intersects with. PBO and BHY are reported alongside as
    diagnostics and are never the binding criterion.
    """

    survivors: tuple[str, ...]  # trial_ids that survive the BINDING (Romano-Wolf) audit
    trial_stats: Mapping[str, TrialStat]
    pbo: float  # probability of backtest overfitting (CSCV diagnostic), in [0, 1]
    bhy_survivors: tuple[str, ...]  # trial_ids the BHY fallback rejects-the-null for (diagnostic)
    alpha: float  # the configured FWER level
    binding_procedure: str  # always "romano_wolf" — the documented binding criterion
    n_trials: int
    n_bootstrap: int

    def survived(self, trial_id: str) -> bool:
        return trial_id in self.survivors


# --------------------------------------------------------------------------- #
# Deterministic seeding (NFR-1, AC-7-critical).
# --------------------------------------------------------------------------- #


def _audit_seed(protocol_hash: str, fingerprints: Sequence[str]) -> int:
    """A 64-bit bootstrap seed that is a pure function of the inputs.

    SHA-256 over the Protocol hash + the **sorted** trial fingerprints (so the seed is
    invariant to ledger row order — the audit population is a set), folded to 64 bits. No
    clock, no unseeded RNG: identical inputs ⇒ identical seed ⇒ identical verdict (NFR-1).
    """
    h = hashlib.sha256()
    h.update(b"audit-seed-v1\n")
    h.update(protocol_hash.encode("utf-8"))
    for fp in sorted(fingerprints):
        h.update(b"\n")
        h.update(fp.encode("utf-8"))
    # Fold the 256-bit digest to a 64-bit unsigned int (numpy seed domain).
    return int.from_bytes(h.digest()[:8], "big", signed=False)


def _trial_fingerprint(row: LedgerRow) -> str:
    """A stable per-trial fingerprint for seeding — the experiment hash + the trial id.

    The experiment hash pins the measured config; the trial id disambiguates two looks of the
    same config. Both are already in the ledger row, so the seed is reproducible from the
    persisted audit population alone (AC-7).
    """
    return f"{row.experiment_hash}:{row.trial_id}"


# --------------------------------------------------------------------------- #
# Track alignment — the (T, K) matrix the joint bootstrap resamples.
# --------------------------------------------------------------------------- #


def _pooled_track(row: LedgerRow) -> tuple[np.ndarray, np.ndarray]:
    """One trial's pooled OOS track as ``(timestamps, values)``, folds concatenated in order.

    The audit operates on the realized OOS returns the ledger logged (FR-E1). Concatenating the
    folds preserves each fold's internal serial correlation; the block bootstrap then respects
    that memory. The TIMESTAMPS are carried alongside the values so alignment can intersect
    trials on their genuinely contemporaneous bars (not positionally) — a NaN dropped in one
    trial must not positionally shift it relative to the others. Bars are NOT dropped here;
    non-finite bars are dropped on the shared index in ``_align_tracks`` (consistently across
    columns). Duplicate timestamps within a trial keep the first occurrence (walk-forward folds
    are non-overlapping, so this is a no-op in practice but guards a malformed ledger).
    """
    if not row.per_fold_returns:
        return (
            np.empty(0, dtype="datetime64[ns]"),
            np.empty(0, dtype=np.float64),
        )
    ts_parts = [np.asarray(fr.timestamps, dtype="datetime64[ns]") for fr in row.per_fold_returns]
    val_parts = [np.asarray(fr.values, dtype=np.float64) for fr in row.per_fold_returns]
    timestamps = np.concatenate(ts_parts)
    values = np.concatenate(val_parts)
    # Unique, SORTED-by-timestamp index keeping the first value at each timestamp. ``np.unique``
    # returns the sorted unique timestamps and the first-occurrence positions; selecting values at
    # those positions yields a strictly-increasing, unique track — so ``_align_tracks`` can
    # intersect and ``searchsorted`` is always valid regardless of fold order on disk.
    unique_ts, first_idx = np.unique(timestamps, return_index=True)
    return unique_ts, values[first_idx]


def _align_tracks(rows: Sequence[LedgerRow]) -> tuple[np.ndarray, tuple[str, ...]]:
    """Align the trials' pooled OOS tracks into a common ``(T, K)`` matrix on a SHARED timestamp
    index — the contemporaneous bars the shared-index bootstrap requires (FR-F1).

    Each trial contributes a ``(timestamps, values)`` track. The common index is the
    INTERSECTION of the trials' timestamps (genuinely contemporaneous bars), then any timestamp
    where ANY trial's value is non-finite is dropped CONSISTENTLY across all columns — so a NaN
    in one trial removes that bar everywhere rather than positionally shifting one trial against
    the others (the latent misalignment bug). The matrix rows are the surviving timestamps in
    increasing order, so column ``j`` and column ``j'`` at row ``t`` are the SAME calendar bar —
    which is what lets one shared block-index draw carry the true cross-trial co-movement.

    Intersecting is conservative in the methodology's sense: it can only DROP bars (never invent
    co-movement), so the null is never narrowed by misalignment. Trials with an empty track are
    dropped (no evidence to audit). Returns the matrix and the aligned trial-id tuple in the
    SAME column order.
    """
    tracks = [(row.trial_id, *_pooled_track(row)) for row in rows]
    tracks = [(tid, ts, val) for tid, ts, val in tracks if ts.size > 0]
    if not tracks:
        return np.empty((0, 0), dtype=np.float64), ()

    # Common calendar index = intersection of every trial's timestamps.
    common_ts = tracks[0][1]
    for _, ts, _ in tracks[1:]:
        common_ts = np.intersect1d(common_ts, ts, assume_unique=True)
    if common_ts.size == 0:
        return np.empty((0, 0), dtype=np.float64), ()

    # Gather each trial's values on the common index (searchsorted: tracks are sorted unique).
    columns = []
    ids = []
    for tid, ts, val in tracks:
        pos = np.searchsorted(ts, common_ts)
        columns.append(val[pos])
        ids.append(tid)
    matrix = np.column_stack(columns)

    # Drop any common-index bar that is non-finite in ANY column — consistently, no positional
    # shift (the alignment-correctness fix). Keeps the matrix genuinely contemporaneous.
    finite_rows = np.all(np.isfinite(matrix), axis=1)
    matrix = matrix[finite_rows]
    if matrix.shape[0] == 0:
        return np.empty((0, 0), dtype=np.float64), ()
    return matrix, tuple(ids)


# --------------------------------------------------------------------------- #
# Studentized statistic + circular block bootstrap (shared-index).
# --------------------------------------------------------------------------- #


def _studentized_means(matrix: np.ndarray, lag: int | None = None) -> np.ndarray:
    """Per-column one-sided studentized mean ``mean/SE`` with a HAC (Newey-West) SE.

    ``SE = sqrt(LRV/n)`` where ``LRV`` is the Newey-West long-run variance (NOT the iid
    ``std/sqrt(n)``). Using the serial-correlation-corrected scale makes the statistic
    **asymptotically pivotal** under AR(p) dependence: the same long-run scale divides both the
    observed mean and every bootstrap-null mean, so observed and null share one
    serial-correlation-robust scale and the bootstrap quantiles match the observed sampling
    distribution regardless of how much within-trial memory the finite block length recovers.
    The iid SE under-states the mean's variance when φ>0 (the defect that let AR(1) noise
    graduate above α); the HAC SE does not.

    ``lag`` is the Bartlett truncation lag; ``None`` ⇒ the automatic ``nw_lag(n)``. The SAME
    ``lag`` is passed to the observed and the bootstrap statistics so the studentization is
    consistent on both sides. A degenerate (near-zero-LRV) column has no usable statistic; it
    maps to 0.0 (the null value) so it can never reject — fail-closed, consistent with the gates.
    """
    n = matrix.shape[0]
    if n < 2:
        return np.zeros(matrix.shape[1], dtype=np.float64)
    if lag is None:
        lag = nw_lag(n)
    means = matrix.mean(axis=0)
    lrv = newey_west_lrv(matrix, lag)
    se = np.sqrt(np.maximum(lrv, 0.0) / n)
    out = np.zeros_like(means)
    live = se > _EPS
    out[live] = means[live] / se[live]
    return out


def _block_length(matrix: np.ndarray) -> int:
    """Data-driven circular-block length for the shared-index bootstrap of a ``(T, K)`` matrix.

    The shared-index scheme draws ONE block-start vector applied to every column, so it needs a
    SINGLE scalar block length. Take the Politis-White automatic length (``politis_white_block``)
    per column and use the MAX across columns: the longest within-trial memory governs, so the
    block is long enough to carry the most serially-correlated trial's autocorrelation into every
    resample (conservative — a too-short block is the failure that under-widened the null).
    Clamped to ``[1, T]``.
    """
    n = matrix.shape[0]
    if n <= 1:
        return 1
    k = matrix.shape[1]
    if k == 0:
        return 1
    block = max(politis_white_block(matrix[:, j]) for j in range(k))
    return int(min(max(1, block), n))


def _bootstrap_null_stats(
    centered: np.ndarray,
    rng: np.random.Generator,
    n_bootstrap: int,
    block: int,
    lag: int,
) -> np.ndarray:
    """Bootstrap the joint null distribution of the per-column studentized stats.

    ``centered`` is the ``(T, K)`` matrix with each column demeaned (H0: true mean 0). Each
    replicate draws ONE shared circular-block index (so cross-trial correlation is preserved)
    and recomputes the K HAC-studentized means with the SAME ``lag`` used for the observed
    statistic — so observed and null share the serial-correlation-corrected scale and the
    statistic is asymptotically pivotal. Returns ``boot_stats`` of shape ``(n_bootstrap, K)``,
    from which the Romano-Wolf step-down takes the right-tail probability of the max over any
    surviving set (the shared-index draw is what makes those maxima carry the cross-trial
    dependence).
    """
    n, k = centered.shape
    boot_stats = np.empty((n_bootstrap, k), dtype=np.float64)
    for b in range(n_bootstrap):
        idx = circular_block_indices(rng, n, block)
        sample = centered[idx, :]
        boot_stats[b, :] = _studentized_means(sample, lag)
    return boot_stats


# --------------------------------------------------------------------------- #
# Romano-Wolf stepdown (PRIMARY — binding for AC-6).
# --------------------------------------------------------------------------- #


def _romano_wolf(
    observed: np.ndarray,
    boot_stats: np.ndarray,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Romano-Wolf step-down multiple test controlling FWER at ``alpha``.

    ``observed`` is the length-K vector of observed studentized stats; ``boot_stats`` is the
    ``(n_bootstrap, K)`` matrix of centered-null bootstrap stats (shared-index, so it carries
    the cross-trial dependence). One-sided (reject for large positive stats).

    Step-down: order hypotheses by ``observed`` descending. At each step the step-down-adjusted
    p-value of the leading hypothesis is the bootstrap right-tail probability of the **max over
    the still-surviving (not-yet-rejected) hypotheses** — ``P(null max over survivors ≥
    observed)`` — using the empirical dependence among exactly those columns. **The adjusted
    p-value is the single source of truth: reject iff it is ≤ ``alpha``.** On a rejection, drop
    the hypothesis and recompute over the remainder; stop at the first non-rejection (all
    less-significant hypotheses are then retained, monotonicity enforced). Deriving the reject
    decision from the same empirical tail probability that defines the adjusted p-value makes
    ``reject ⇔ adj_p ≤ alpha`` hold *by construction* — there is no separate interpolated
    quantile that could disagree with the reported p-value at the boundary. This is uniformly
    more powerful than single-step Bonferroni/Holm because the reference distribution shrinks as
    significant hypotheses are removed and it uses the bootstrap's joint distribution rather
    than a worst-case dependence bound (Romano & Wolf 2005, 2016).

    Returns ``(reject, adj_p)``: a boolean reject vector and step-down-adjusted one-sided
    p-values, both aligned to the input column order and mutually consistent
    (``reject[j] == (adj_p[j] <= alpha)``).
    """
    k = observed.size
    reject = np.zeros(k, dtype=bool)
    adj_p = np.ones(k, dtype=float)
    if k == 0:
        return reject, adj_p

    order = np.argsort(-observed)  # most significant first
    remaining = list(order)
    prev_p = 0.0
    while remaining:
        lead = remaining[0]
        # Right-tail probability of the bootstrap max over the SURVIVING columns only (the
        # step-down's shrinking reference distribution). This empirical tail probability is BOTH
        # the adjusted p-value AND the reject criterion, so the two cannot disagree.
        surviving_max = boot_stats[:, remaining].max(axis=1)
        p_lead = float(np.mean(surviving_max >= observed[lead]))
        # Enforce monotone (non-decreasing) adjusted p-values down the step-down order.
        p_lead = max(p_lead, prev_p)
        adj_p[lead] = p_lead
        prev_p = p_lead
        if p_lead <= alpha:  # reject ⇔ adjusted p ≤ alpha (single source of truth)
            reject[lead] = True
            remaining.pop(0)
            continue
        # First non-rejection: every less-significant hypothesis is also retained, with its
        # adjusted p-value floored at the leading (monotone) value.
        for idx in remaining:
            adj_p[idx] = max(p_lead, prev_p)
        break
    return reject, adj_p


# --------------------------------------------------------------------------- #
# PBO (CSCV) — complementary diagnostic.
# --------------------------------------------------------------------------- #


def _pbo(matrix: np.ndarray, n_blocks: int) -> float:
    """Probability of backtest overfitting via CSCV (Bailey & López de Prado).

    Partition the ``(T, K)`` matrix into ``S`` contiguous time blocks. Over every
    ``C(S, S/2)`` split of the blocks into a train half and a complementary test half:
    pick the trial with the best in-sample (train) mean, find its **relative rank** ``ω`` in
    ``(0, 1)`` among all trials' test (OOS) means, and form the logit ``λ = ln(ω/(1-ω))``. PBO
    is the fraction of splits with ``λ ≤ 0`` (the in-sample winner lands at or below the OOS
    median) — i.e. how often selecting the in-sample best is no better than a coin flip OOS.

    A clearly-overfit set (the in-sample winner is random OOS) → PBO ≈ 0.5; a robust set (the
    same trial wins both halves) → PBO ≈ 0. Diagnostic only — never the binding criterion.
    Returns ``nan`` only if the matrix has fewer than 2 trials or too few blocks to split.
    """
    n, k = matrix.shape
    if k < 2 or n_blocks < 2:
        return float("nan")
    s = n_blocks - (n_blocks % 2)  # force even
    if s < 2 or n < s:
        return float("nan")
    # Even contiguous blocks (last block absorbs the remainder).
    bounds = [int(round(i * n / s)) for i in range(s + 1)]
    blocks = [np.arange(bounds[i], bounds[i + 1]) for i in range(s)]
    half = s // 2

    overfit = 0
    total = 0
    for train_set in combinations(range(s), half):
        train_idx = np.concatenate([blocks[i] for i in train_set])
        test_set = [i for i in range(s) if i not in train_set]
        test_idx = np.concatenate([blocks[i] for i in test_set])
        is_perf = matrix[train_idx, :].mean(axis=0)  # in-sample performance per trial
        oos_perf = matrix[test_idx, :].mean(axis=0)  # OOS performance per trial
        best = int(np.argmax(is_perf))
        # Relative rank of the IS-best trial among OOS performances, in (0, 1).
        # rank = #{trials with strictly lower OOS} ; ω = (rank + 1) / (k + 1) avoids 0/1.
        rank = int(np.sum(oos_perf < oos_perf[best]))
        omega = (rank + 1) / (k + 1)
        lam = math.log(omega / (1.0 - omega))
        if lam <= 0.0:
            overfit += 1
        total += 1
    return overfit / total if total else float("nan")


# --------------------------------------------------------------------------- #
# BHY (Benjamini-Hochberg-Yekutieli) — documented simpler fallback.
# --------------------------------------------------------------------------- #


def _bhy_reject(p_values: np.ndarray, alpha: float) -> np.ndarray:
    """BHY step-up controlling FDR under ARBITRARY dependence (Benjamini-Yekutieli 2001).

    Order p-values ascending; with the dependence correction ``c(K) = Σ_{i=1}^K 1/i``, the
    largest ``i`` with ``p_(i) ≤ (i / (K·c(K)))·alpha`` sets the threshold; reject all
    hypotheses with that or smaller p-values. The ``c(K)`` factor is what makes it valid for
    correlated tests (Harvey-Liu 2015's recommended multiple-testing fallback). Diagnostic /
    fallback only — Romano-Wolf is binding.
    """
    k = p_values.size
    reject = np.zeros(k, dtype=bool)
    if k == 0:
        return reject
    c_k = float(np.sum(1.0 / np.arange(1, k + 1)))
    order = np.argsort(p_values)
    ranked = p_values[order]
    thresh = (np.arange(1, k + 1) / (k * c_k)) * alpha
    below = np.where(ranked <= thresh)[0]
    if below.size:
        cutoff = below.max()
        reject[order[: cutoff + 1]] = True
    return reject


# --------------------------------------------------------------------------- #
# The public audit entry point.
# --------------------------------------------------------------------------- #


def run_graduation_audit(
    rows: Sequence[LedgerRow],
    protocol_hash: str,
    *,
    alpha: float = DEFAULT_ALPHA,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    pbo_blocks: int = DEFAULT_PBO_BLOCKS,
) -> AuditResult:
    """Run the returns-based graduation audit over the logged returns of ALL trials (FR-F1).

    ``rows`` is the audit population — ALL finalized ledger rows (``TrialLedger.rows()``), not
    just the finalists. ``protocol_hash`` + the trials' fingerprints seed the bootstrap
    deterministically (NFR-1). Returns an ``AuditResult`` whose ``survivors`` is the
    Romano-Wolf FWER-controlled set (the BINDING criterion for AC-6), with PBO and BHY reported
    as diagnostics.

    Statistical contract:
    - The HAC-studentized-mean statistic and the shared-index circular block bootstrap absorb
      cross-trial correlation and within-trial serial correlation directly (no ``N=K`` shortcut):
      a Newey-West long-run-variance SE makes the statistic asymptotically pivotal under AR(p)
      memory, and a data-driven (Politis-White) block length carries that memory into the null.
    - Under K true-zero-Sharpe trials, ``P(any false graduation) ≤ alpha`` (FWER control). The
      tests measure empirical FWER over many deterministic seeds and confirm control (within a
      Monte-Carlo tolerance) across AR(1) serial correlation φ∈{0,0.2,0.3,0.6,0.8} and a heavy
      tail (t(3)), and across cross-sectional correlation up to ρ=0.9 at φ=0 (perfectly
      correlated nulls incur no spurious multiplicity penalty — the shared-index scheme). The
      asymptotics weaken at very small samples combined with near-unit-root persistence, where a
      small residual size distortion remains (it shrinks as the sample grows).
    """
    matrix, ids = _align_tracks(rows)
    fingerprints = [_trial_fingerprint(r) for r in rows]
    seed = _audit_seed(protocol_hash, fingerprints)
    rng = np.random.default_rng(seed)

    k = matrix.shape[1]
    if k == 0:
        # No auditable evidence ⇒ nothing graduates (fail-closed).
        return AuditResult(
            survivors=(),
            trial_stats={},
            pbo=float("nan"),
            bhy_survivors=(),
            alpha=alpha,
            binding_procedure="romano_wolf",
            n_trials=0,
            n_bootstrap=n_bootstrap,
        )

    n = matrix.shape[0]
    lag = nw_lag(n)  # HAC truncation lag — shared by observed and bootstrap (pivotal scale)
    observed = _studentized_means(matrix, lag)
    centered = matrix - matrix.mean(axis=0, keepdims=True)  # impose H0 per column
    block = _block_length(matrix)  # data-driven (Politis-White) circular-block length
    boot_stats = _bootstrap_null_stats(centered, rng, n_bootstrap, block, lag)

    # PRIMARY: Romano-Wolf step-down (FWER-controlled survivors — binding for AC-6).
    rw_reject, rw_adj_p = _romano_wolf(observed, boot_stats, alpha)

    # Per-trial RAW one-sided bootstrap p-values (for BHY + observability): P(own null ≥ obs).
    raw_p = np.array(
        [float(np.mean(boot_stats[:, j] >= observed[j])) for j in range(k)],
        dtype=np.float64,
    )
    # FALLBACK diagnostic: BHY over the raw per-trial p-values.
    bhy_reject = _bhy_reject(raw_p, alpha)

    # DIAGNOSTIC: PBO via CSCV.
    pbo = _pbo(matrix, pbo_blocks)

    trial_stats = {
        ids[j]: TrialStat(
            trial_id=ids[j],
            n=n,
            mean=float(matrix[:, j].mean()),
            studentized=float(observed[j]),
            p_value=float(rw_adj_p[j]),
            romano_wolf_reject=bool(rw_reject[j]),
            bhy_reject=bool(bhy_reject[j]),
        )
        for j in range(k)
    }
    survivors = tuple(ids[j] for j in range(k) if rw_reject[j])
    bhy_survivors = tuple(ids[j] for j in range(k) if bhy_reject[j])

    return AuditResult(
        survivors=survivors,
        trial_stats=trial_stats,
        pbo=pbo,
        bhy_survivors=bhy_survivors,
        alpha=alpha,
        binding_procedure="romano_wolf",
        n_trials=k,
        n_bootstrap=n_bootstrap,
    )
