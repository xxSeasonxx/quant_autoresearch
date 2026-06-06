"""Lockbox Manager — the power-aware, one-shot confirmation verdict (FR-F2, AC-5).

The Lockbox is the third anti-overfit layer (Principle 1): after the budget BOUNDS search and
the audit CORRECTS the selection, the Lockbox CONFIRMS a survivor once on fresh forward data it
never touched. The verdict is **trichotomous** (harness-architecture §3):

- ``confirmed`` — a real, out-of-sample, risk-adjusted edge at the stated confidence;
- ``rejected`` — a powered look that came back flat or negative;
- ``insufficient_evidence`` — the data cannot support a verdict either way.

**Power first (AC-5, Principle 6).** Before trusting the forward block we ask whether it can
even detect the candidate's claimed edge. If the Lockbox minimum detectable effect
(``AssetProfile.lockbox_mde``, in annualized Sharpe units) exceeds the claimed edge — or the
MDE is non-finite, or the claimed edge is not a finite positive Sharpe — the verdict is
``insufficient_evidence``. A ``confirmed`` the data cannot power is **unrepresentable**: the
power gate runs before any confirmation logic, so an under-powered block can never yield
``confirmed``. This is the verdict-layer expression of "an asset only earns the conclusions its
data can support."

**Binding test (FR-F2).** With power, the binding test depends on the forward block's
thickness. A block thick enough for a powered one-shot forward test makes the **forward block**
binding (``binding_test=forward_block``), with a block-bootstrap CI as a sanity check. A thin
block (short crypto history) makes a **stationary/circular block-bootstrap CI** on the OOS
distribution binding (``binding_test=block_bootstrap``), with the forward point as the sanity
check. Either way the decision is: ``confirmed`` iff the binding test's lower confidence bound
on the annualized Sharpe clears zero AND the point estimate is positive; else ``rejected``.

**Write-once per dataset (FR-B4).** The manager reserves the Lockbox dataset on P2's
``LockboxBook`` BEFORE scoring; a second graduation on the same block raises ``LockboxSpentError``
— the reserve is the gate, so the second confirmation never runs.

**Determinism (NFR-1).** The bootstrap CI uses a seeded ``np.random.Generator`` whose seed is a
pure function of the inputs (the dataset id + the candidate fingerprint), so identical inputs ⇒
identical verdict, bit-for-bit. No clock, no unseeded RNG.

The harness EMITS this verdict; it never acts on it. Promotion above the Lockbox is a separate
human-only step (FR-F3). Pure numpy + the profiler/metrics helpers; no ``quant_strategies``
import (the foundation is reached only through the injected ``FoundationGateway`` seam).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from harness.bootstrap import circular_block_indices, politis_white_block
from harness.data.lockbox_book import LockboxBook, lockbox_dataset_id
from harness.foundation import FoundationGateway
from harness.objective import factors, metrics
from harness.orchestrator import FactorPanelProvider
from harness.profiler import AssetProfile
from harness.protocol import Experiment, Protocol

Verdict = Literal["confirmed", "rejected", "insufficient_evidence"]
BindingTest = Literal["forward_block", "block_bootstrap"]

# Default confidence for the one-sided lower bound on the annualized Sharpe (matches the
# profiler's significance Z — the bar the MDE is derived against).
_DEFAULT_CONFIDENCE = 0.95
# Default bootstrap replicate count for the OOS-distribution CI (deterministic, seeded).
_DEFAULT_N_BOOTSTRAP = 2000
# A forward block is "thick enough" for the forward test to be binding iff its calendar power
# can detect the claimed edge with margin: lockbox_mde ≤ thick_margin · claimed_edge. Below
# that the block-bootstrap CI is binding and the forward point is a sanity check. The margin
# (<1) reserves the forward test for blocks comfortably powered, not marginal ones.
_THICK_MARGIN = 0.5


@dataclass(frozen=True)
class LockboxVerdict:
    """The Lockbox confirmation verdict (harness-architecture §3).

    Adds the observability fields the CLI/ledger surface (the core trichotomy + the power
    inputs + the binding test are the contract; the rest is provenance).
    """

    verdict: Verdict
    mde: float | None  # Lockbox minimum detectable effect (annualized Sharpe)
    claimed_edge: float | None
    binding_test: BindingTest
    # --- observability (NFR-5) ---
    forward_sharpe: float | None = None  # annualized Sharpe on the forward block
    lower_bound: float | None = None  # binding test's lower CI bound on annualized Sharpe
    confidence: float = _DEFAULT_CONFIDENCE
    detail: str = ""


class LockboxError(RuntimeError):
    """Raised on a Lockbox scoring failure (e.g. the forward evaluate did not succeed)."""


# --------------------------------------------------------------------------- #
# Deterministic seeding (NFR-1).
# --------------------------------------------------------------------------- #


def _lockbox_seed(dataset_id: str, fingerprint: str) -> int:
    """A 64-bit bootstrap seed that is a pure function of the inputs (NFR-1).

    SHA-256 over the Lockbox dataset id + the candidate fingerprint, folded to 64 bits. No
    clock, no unseeded RNG: identical (dataset, candidate) ⇒ identical CI ⇒ identical verdict.
    """
    h = hashlib.sha256()
    h.update(b"lockbox-seed-v1\n")
    h.update(dataset_id.encode("utf-8"))
    h.update(b"\n")
    h.update(fingerprint.encode("utf-8"))
    return int.from_bytes(h.digest()[:8], "big", signed=False)


# --------------------------------------------------------------------------- #
# Block-bootstrap lower confidence bound on the annualized Sharpe.
# --------------------------------------------------------------------------- #


def _bootstrap_sharpe_lower_bound(
    values: np.ndarray,
    periods_per_year: float,
    rng: np.random.Generator,
    *,
    confidence: float,
    n_bootstrap: int,
) -> tuple[float | None, float | None]:
    """One-sided lower confidence bound on the ANNUALIZED Sharpe via a circular block bootstrap.

    Respects serial correlation (returns have memory) by resampling whole circular blocks with a
    **data-driven (Politis-White) block length** — the same root fix the audit uses. A fixed
    ``n**(1/3)`` block was too short to carry within-trial serial correlation once φ≥0.3, so the
    bootstrap CI under-widened and noise could spuriously ``confirm`` (false-confirm rate above
    the one-sided ``1-confidence`` level); the automatic block length grows with the dependence
    and restores control. The lower bound is the ``(1 - confidence)`` quantile of the bootstrap
    Sharpe distribution — the binding test for ``confirmed`` is whether this lower bound clears
    0. Returns ``(point_sharpe, lower_bound)``; ``(None, None)`` if the series cannot yield a
    Sharpe.
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    point = metrics.sharpe(v, periods_per_year=periods_per_year)
    if point is None or v.size < 2:
        return None, None
    n = v.size
    block = politis_white_block(v)
    boot = np.empty(n_bootstrap, dtype=np.float64)
    valid = 0
    for b in range(n_bootstrap):
        idx = circular_block_indices(rng, n, block)
        s = metrics.sharpe(v[idx], periods_per_year=periods_per_year)
        if s is not None:
            boot[valid] = s
            valid += 1
    if valid == 0:
        return point, None
    lower = float(np.quantile(boot[:valid], 1.0 - confidence))
    return point, lower


# --------------------------------------------------------------------------- #
# The Lockbox Manager.
# --------------------------------------------------------------------------- #


def _claimed_edge_is_valid(claimed_edge: float) -> bool:
    """A confirmable claim is a finite POSITIVE Sharpe. NaN/inf/≤0 is not a real edge to power
    (NaN would slip every ``>`` comparison; ≤0 is not a graduation candidate)."""
    return math.isfinite(claimed_edge) and claimed_edge > 0.0


def confirm_on_lockbox(
    experiment: Experiment,
    protocol: Protocol,
    profile: AssetProfile,
    *,
    claimed_edge: float,
    gateway: FoundationGateway,
    book: LockboxBook,
    trial_id: str,
    spent_at: str,
    factor_panel_provider: FactorPanelProvider | None = None,
    confidence: float = _DEFAULT_CONFIDENCE,
    n_bootstrap: int = _DEFAULT_N_BOOTSTRAP,
) -> LockboxVerdict:
    """Confirm one survivor on the fresh Lockbox block — the trichotomous verdict (FR-F2).

    Order of operations (each makes an invalid state unrepresentable):

    1. **Power gate (AC-5).** If the Lockbox MDE exceeds the claimed edge (or the MDE is
       non-finite, or the claim is not a finite positive Sharpe), return
       ``insufficient_evidence`` — *before* reserving or scoring. A ``confirmed`` the block
       cannot power can never be produced.
    2. **Factor-panel wiring gate (AC-9/G2, FAIL-CLOSED).** If the Protocol REQUIRES factor
       neutralization but no ``factor_panel_provider`` is supplied (the production default with
       no provider), return ``insufficient_evidence`` (``factor_panel_unwired``) — *before*
       reserving or scoring. The Lockbox must NEVER score RAW returns as residual alpha; a
       pure factor-beta basket can never be ``confirmed`` on the live path.
    3. **Write-once reserve (FR-B4).** Reserve the Lockbox ``dataset_id`` on the ``LockboxBook``;
       a second graduation on the same block raises ``LockboxSpentError`` here, before scoring.
    4. **Score once.** One ``evaluate`` over the Lockbox window via the seam (FR-J2).
    5. **Residualize (FR-C3).** Build the factor panel for the Lockbox window and residualize the
       returns against it BEFORE scoring — the confirmation is on residual alpha, not raw return.
       If the provider does not produce a panel that COVERS the required factors,
       ``insufficient_evidence`` (``factor_panel_unwired``) — fail-closed, never a raw pass.
    6. **Binding test + decision.** Pick ``forward_block`` (thick block) or ``block_bootstrap``
       (thin block) as binding; ``confirmed`` iff the binding lower CI bound on the annualized
       Sharpe clears 0 AND the point estimate is positive; else ``rejected``.

    ``profile`` supplies ``lockbox_mde`` (the power bar). ``claimed_edge`` is the candidate's
    OOS edge in annualized Sharpe units (e.g. its Selection ``rank_sharpe``). ``spent_at`` is an
    injected ISO timestamp (never read from a clock here). ``factor_panel_provider`` is the same
    seam the Selection path uses; the real campaign wires it (built from quant_data) — tests inject
    a fake. With no required factors it is optional (identity is then a deliberate choice).
    """
    mde = profile.lockbox_mde
    required_factors = protocol.objective.factor_panel.required_factors

    # --- 1. Power gate FIRST (AC-5): never manufacture a confirm the data can't power. ---
    if not _claimed_edge_is_valid(claimed_edge):
        return LockboxVerdict(
            verdict="insufficient_evidence",
            mde=mde,
            claimed_edge=claimed_edge,
            binding_test=_binding_test_for(profile, claimed_edge),
            confidence=confidence,
            detail=f"claimed edge {claimed_edge!r} is not a finite positive Sharpe — not confirmable",
        )
    if not math.isfinite(mde) or mde > claimed_edge:
        return LockboxVerdict(
            verdict="insufficient_evidence",
            mde=mde,
            claimed_edge=claimed_edge,
            binding_test=_binding_test_for(profile, claimed_edge),
            confidence=confidence,
            detail=(
                f"Lockbox MDE {mde:.3f} > claimed edge {claimed_edge:.3f} — the block cannot "
                "power this confirmation (insufficient_evidence, not confirmed)"
            ),
        )

    # --- 2. Factor-panel wiring gate (AC-9/G2): fail closed BEFORE reserve/score when the
    # Protocol requires neutralization but no provider is wired. A confirm on RAW beta is
    # unrepresentable — and no Lockbox block is burned on the misconfiguration (mirrors the
    # power gate's pre-reserve return, so insufficient_evidence never spends the block). ---
    if required_factors and factor_panel_provider is None:
        return LockboxVerdict(
            verdict="insufficient_evidence",
            mde=mde,
            claimed_edge=claimed_edge,
            binding_test=_binding_test_for(profile, claimed_edge),
            confidence=confidence,
            detail=(
                "factor_panel_unwired: the Protocol requires neutralization of "
                f"{len(required_factors)} factor column(s) but no factor-panel provider is "
                "wired — the Lockbox refuses to score raw returns as residual alpha "
                "(insufficient_evidence, fail-closed)"
            ),
        )

    # --- 3. Write-once reserve (FR-B4): refuse a second graduation on the same block. ---
    dataset_id = lockbox_dataset_id(
        protocol_hash=protocol.content_hash,
        lockbox_start=protocol.data_tiers.lockbox.start,
        lockbox_end=protocol.data_tiers.lockbox.end,
        symbols=experiment.symbols if experiment.symbols is not None else protocol.data_tiers.symbols,
    )
    # reserve() raises LockboxSpentError if already spent — the gate, before any scoring.
    book.reserve(dataset_id, trial_id=trial_id, spent_at=spent_at)

    # --- 4. Score once on the Lockbox window (one evaluate, FR-J2). ---
    window = _lockbox_window(protocol)
    result = gateway.evaluate(experiment, protocol, window)
    if not result.succeeded or result.returns is None:
        raise LockboxError(
            f"Lockbox evaluate did not produce a return series (failure_stage="
            f"{result.failure_stage!r}); cannot confirm"
        )

    # --- 5. Residualize against the factor panel BEFORE scoring (FR-C3, AC-9/G2). The
    # confirmation is on RESIDUAL alpha — market/funding-carry beta is regressed out, never
    # scored as edge. If the provider cannot supply a panel covering the required factors, fail
    # closed (insufficient_evidence) rather than scoring raw returns. ---
    raw_returns = result.returns
    panel = factor_panel_provider(window, raw_returns) if factor_panel_provider is not None else {}
    if required_factors and not factors.panel_covers(panel, required_factors):
        return LockboxVerdict(
            verdict="insufficient_evidence",
            mde=mde,
            claimed_edge=claimed_edge,
            binding_test=_binding_test_for(profile, claimed_edge),
            confidence=confidence,
            detail=(
                "factor_panel_unwired: the Lockbox factor panel does not cover the "
                f"{len(required_factors)} required factor column(s) — refusing to score raw "
                "returns as residual alpha (insufficient_evidence, fail-closed)"
            ),
        )
    returns = factors.residual_fold_returns(raw_returns, panel)

    # --- 6. Binding test + decision. ---
    binding = _binding_test_for(profile, claimed_edge)
    seed = _lockbox_seed(dataset_id, f"{experiment.strategy_path}:{trial_id}")
    rng = np.random.default_rng(seed)
    point, lower = _bootstrap_sharpe_lower_bound(
        np.asarray(returns.values, dtype=np.float64),
        float(returns.periods_per_year),
        rng,
        confidence=confidence,
        n_bootstrap=n_bootstrap,
    )
    forward_sharpe = metrics.sharpe(returns)

    # The binding test's lower bound: for forward_block, the powered forward point's CI is the
    # bootstrap lower bound on the realized block (a one-shot forward look has no other CI to
    # draw on a single block); for block_bootstrap the bootstrap CI is explicitly binding. In
    # both cases the lower bound IS the bootstrap quantile; the label records which is the
    # decision-of-record vs the sanity check.
    if lower is None or point is None:
        return LockboxVerdict(
            verdict="insufficient_evidence",
            mde=mde,
            claimed_edge=claimed_edge,
            binding_test=binding,
            forward_sharpe=forward_sharpe,
            lower_bound=lower,
            confidence=confidence,
            detail="Lockbox return series has no usable Sharpe — cannot confirm or reject",
        )

    confirmed = lower > 0.0 and point > 0.0
    verdict: Verdict = "confirmed" if confirmed else "rejected"
    return LockboxVerdict(
        verdict=verdict,
        mde=mde,
        claimed_edge=claimed_edge,
        binding_test=binding,
        forward_sharpe=forward_sharpe,
        lower_bound=lower,
        confidence=confidence,
        detail=(
            f"binding={binding}: annualized Sharpe point={point:.3f}, "
            f"{confidence:.0%} lower bound={lower:.3f} ⇒ {verdict}"
        ),
    )


def _binding_test_for(profile: AssetProfile, claimed_edge: float) -> BindingTest:
    """Choose the binding test by the forward block's thickness (FR-F2).

    The forward block is binding only when it is comfortably powered for the claimed edge
    (``mde ≤ _THICK_MARGIN · claimed_edge``); otherwise the block-bootstrap CI is binding and
    the forward point is a sanity check. On short crypto history the block is thin, so the
    bootstrap is the binding test — which is the methodology's prescription.
    """
    mde = profile.lockbox_mde
    if not math.isfinite(mde) or not _claimed_edge_is_valid(claimed_edge):
        return "block_bootstrap"
    return "forward_block" if mde <= _THICK_MARGIN * claimed_edge else "block_bootstrap"


def _lockbox_window(protocol: Protocol):
    """The single Lockbox evaluate window (the most-recent forward block from the Protocol).

    Duck-types the orchestrator's ``FoldWindowSpan`` (``window_id``/``start``/``end``) so the
    same gateway seam consumes it. The Lockbox is one window — one ``evaluate`` (FR-J2).
    """
    from harness.orchestrator import FoldWindowSpan

    lb = protocol.data_tiers.lockbox
    return FoldWindowSpan(window_id="lockbox", start=lb.start, end=lb.end)
