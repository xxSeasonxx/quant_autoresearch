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
common ``(T, K)`` matrix (truncated to the common length T — the tracks are the same
walk-forward Selection folds, so they share a time index) and **resample whole blocks on a
SHARED index across all K columns at once**. A single set of circular block-start indices is
drawn per bootstrap replicate and applied to every column simultaneously, so if trials co-move
at time t that co-movement is carried into every replicate. The bootstrap distribution of the
*max* studentized statistic therefore widens exactly as much as the trials are correlated —
which is the correlation absorption FR-F1 demands. Per-column centering (subtract each
column's mean) imposes the joint null H0: every trial's true mean is zero.

Statistic
---------
Per trial, the one-sided studentized mean of its pooled OOS return track ``t_i = mean_i/SE_i``
(SE = sample std / sqrt(n)). Monotone in Sharpe for a fixed sample; one-sided because only a
*positive* edge is a graduation candidate. The bootstrap supplies the joint null distribution
of the studentized stats, so the procedure is correlation- and heteroskedasticity-robust.

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


def _pooled_track(row: LedgerRow) -> np.ndarray:
    """One trial's pooled OOS return track: its per-fold series concatenated in fold order.

    The audit operates on the realized OOS returns the ledger logged (FR-E1). Concatenating
    the folds in order preserves each fold's internal serial correlation; the block bootstrap
    then respects that memory. Non-finite bars are dropped (an unmeasurable bar is not
    evidence) — consistent with the metrics layer's finite-only contract.
    """
    parts = [np.asarray(fr.values, dtype=np.float64) for fr in row.per_fold_returns]
    track = np.concatenate(parts) if parts else np.empty(0, dtype=np.float64)
    return track[np.isfinite(track)]


def _align_tracks(rows: Sequence[LedgerRow]) -> tuple[np.ndarray, tuple[str, ...]]:
    """Align the trials' pooled OOS tracks into a common ``(T, K)`` matrix.

    Truncates every track to the common length T = min track length (the tracks are the same
    walk-forward Selection folds, so they are near-equal; truncation is conservative — less
    data ⇒ a wider null ⇒ harder to graduate, never anti-conservative). Trials with an empty
    track are dropped (no evidence to audit). Returns the matrix and the aligned trial-id
    tuple in the SAME column order.

    Truncation takes the LAST T bars of each track (the most-recent, forward-most OOS), so the
    common index is a shared recent window across trials — the alignment that best preserves
    cross-trial co-movement (FR-F1).
    """
    tracks = [(row.trial_id, _pooled_track(row)) for row in rows]
    tracks = [(tid, tr) for tid, tr in tracks if tr.size > 0]
    if not tracks:
        return np.empty((0, 0), dtype=np.float64), ()
    common = min(tr.size for _, tr in tracks)
    ids = tuple(tid for tid, _ in tracks)
    matrix = np.column_stack([tr[-common:] for _, tr in tracks])
    return matrix, ids


# --------------------------------------------------------------------------- #
# Studentized statistic + circular block bootstrap (shared-index).
# --------------------------------------------------------------------------- #


def _studentized_means(matrix: np.ndarray) -> np.ndarray:
    """Per-column one-sided studentized mean ``mean/SE`` (SE = std/sqrt(n)).

    A degenerate (near-zero-variance) column has no usable statistic; it maps to 0.0 (the null
    value) so it can never reject — an unmeasurable edge is not a significant one (fail-closed,
    consistent with the gates).
    """
    n = matrix.shape[0]
    if n < 2:
        return np.zeros(matrix.shape[1], dtype=np.float64)
    means = matrix.mean(axis=0)
    sd = matrix.std(axis=0, ddof=1)
    se = sd / math.sqrt(n)
    out = np.zeros_like(means)
    live = se > _EPS
    out[live] = means[live] / se[live]
    return out


def _block_length(n: int) -> int:
    """Circular-block length ``b ≈ n**(1/3)`` (the standard stationary-bootstrap rule).

    Long enough to carry within-trial serial correlation into each resample, short enough to
    keep the bootstrap powered. Clamped to ``[1, n]``.
    """
    if n <= 1:
        return 1
    return int(min(max(1, round(n ** (1.0 / 3.0))), n))


def _shared_block_indices(rng: np.random.Generator, n: int, block: int) -> np.ndarray:
    """One circular-block index vector of length ``n`` (shared across all K columns).

    Draws ``ceil(n/block)`` random block starts in ``[0, n)`` and lays down contiguous blocks
    of length ``block`` with wrap-around (circular), then truncates to ``n``. Applying the SAME
    index vector to every column is what preserves the cross-trial co-movement at each
    resampled time (FR-F1).
    """
    if n <= 0:
        return np.empty(0, dtype=np.intp)
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=n_blocks)
    offsets = np.arange(block)
    idx = ((starts[:, None] + offsets[None, :]) % n).reshape(-1)[:n]
    return idx.astype(np.intp)


def _bootstrap_null_stats(
    centered: np.ndarray,
    rng: np.random.Generator,
    n_bootstrap: int,
    block: int,
) -> np.ndarray:
    """Bootstrap the joint null distribution of the per-column studentized stats.

    ``centered`` is the ``(T, K)`` matrix with each column demeaned (H0: true mean 0). Each
    replicate draws ONE shared circular-block index (so cross-trial correlation is preserved)
    and recomputes the K studentized means. Returns ``boot_stats`` of shape
    ``(n_bootstrap, K)`` — the per-column bootstrap studentized stats, from which the
    Romano-Wolf step-down takes the right-tail probability of the max over any surviving set
    (the shared-index draw is what makes those maxima carry the cross-trial dependence).
    """
    n, k = centered.shape
    boot_stats = np.empty((n_bootstrap, k), dtype=np.float64)
    for b in range(n_bootstrap):
        idx = _shared_block_indices(rng, n, block)
        sample = centered[idx, :]
        boot_stats[b, :] = _studentized_means(sample)
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
    - The studentized-mean statistic and the shared-index circular block bootstrap absorb
      cross-trial correlation and serial correlation directly (no ``N=K`` shortcut).
    - Under K true-zero-Sharpe trials, ``P(any false graduation) ≤ alpha`` (FWER control),
      validated empirically across seeds in the tests.
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
    observed = _studentized_means(matrix)
    centered = matrix - matrix.mean(axis=0, keepdims=True)  # impose H0 per column
    block = _block_length(n)
    boot_stats = _bootstrap_null_stats(centered, rng, n_bootstrap, block)

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
