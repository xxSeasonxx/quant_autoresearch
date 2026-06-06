# Harness Architecture Contract

**Status:** durable cross-phase contract for the greenfield rebuild in
[refactor-phase-plan.md](./refactor-phase-plan.md). Requirements: [PRD.md](./PRD.md).
Rationale: [auto-research-methodology.md](./auto-research-methodology.md).

This document pins the decisions that cross phase boundaries so each phase's
sub-agents build a **coherent, composable** system. Within-phase implementation
detail is the building sub-agent's to design; anything in this file is fixed
unless a later phase explicitly amends it here.

First principles for the rebuild (from the PRD): rigor lives in the immutable
**harness** the agent cannot edit; simplicity lives in the agent's one-page
contract. **No legacy, no fallback, no compatibility shims** — legacy judgment
modules are deleted in their retiring phase, not evolved.

---

## 1. Package layout

A fresh package `harness/` (the immutable evaluator). Top-level legacy modules
(`scoring.py`, `promotion.py`, `experiment_config.py`, `runner.py`) are **not
imported by** `harness/` and are deleted in their retiring phase (§6).

```
harness/
  __init__.py
  protocol.py        # Protocol (immutable, content-hashed) + Experiment split        [P1] FR-H
  foundation.py      # FoundationGateway seam + result types (the testability seam)    [P1 iface / P2 real]  FR-J
  foundation_real.py # RealFoundationGateway adapter — the ONLY quant_strategies importer [P2] FR-J
  orchestrator.py    # walk-forward RES orchestration (evaluate once per fold → RES)   [P2] FR-J2
  objective/
    __init__.py
    res.py           # Robust Edge Score: rank-on-Sharpe, per-fold evidence unit       [P1] FR-C1,C2,C4,C6
    factors.py       # factor panel + residual-alpha (funding-as-carry)                [P1] FR-C3
    gates.py         # Stage-1 feasibility gates (incl. effective-breadth)             [P1/P2] FR-C5
    metrics.py       # Sharpe / Sortino / Calmar / maxDD / PSR over FoldReturns        [P1/P2]
  stability.py       # stability gate (perturb +/- steps, flat-and-positive)           [P1] FR-D2
  data/
    __init__.py
    tiers.py         # Tiered Data Service: Train / Selection / Lockbox partitions     [P2] FR-B1
    walkforward.py   # forward-only folds + purge + embargo                            [P2] FR-B2,B3
    lockbox_book.py  # write-once-per-dataset Lockbox bookkeeping                      [P2] FR-B4
  profiler.py        # Asset Profiler + data-sufficiency gate                          [P2] FR-G
  ledger.py          # Trial Ledger (append-only; full per-fold returns + fingerprint) [P3] FR-E1,I1,I2
  family.py          # Family Identifier (signal-structure fingerprint)                [P3] FR-E4
  budget.py          # Budget Manager (global, effective-N, MinBTL upper bound)        [P3] FR-E2,E3,E5
  audit.py           # Graduation Auditor (Romano-Wolf stepdown / PBO)                 [P4] FR-F1
  lockbox.py         # Lockbox Manager (power-aware trichotomous verdict)              [P4] FR-F2,F3
  escalation.py      # Escalation Controller + naked-sweep + swing-big cadence         [P5] FR-A,D1,D3
  cli.py             # run / evaluate / status (+ admin profile/graduate/lockbox)      [P5] §8
  session.py         # session/worktree/never-early-stop shell (ported clean)          [P5]
```

`strategy.py` stays the agent-editable surface (rewritten to the new contract in
P5). `experiment.toml` becomes the **Experiment** surface only (params); the
**Protocol** lives in a separate harness-owned file (§4).

Tests live in `tests/` mirroring the package; every test names the AC-# it covers.

---

## 2. The Foundation seam (the linchpin — pin exactly)

The judgment layer **must not** import `quant_strategies` directly. It depends on
the abstraction below (Dependency Inversion). This is what makes AC-1/AC-6/AC-9
deterministically testable with synthetic returns, and it is the literal
expression of FR-J1 ("harness orchestrates, does not re-derive engine math") and
AC-10 ("per-fold OOS returns via a typed foundation API, no Parquet scraping").

> **Single sanctioned boundary crosser (P2):** `harness/foundation_real.py`
> (`RealFoundationGateway`) is the **only** module under `harness/` permitted to import
> `quant_strategies`. Every other harness module — objective/, gates, metrics, factors,
> stability, protocol, data/, profiler, orchestrator, and the P3–P5 judgment modules — stays
> pure. The boundary test (`tests/harness/test_foundation_seam.py`) asserts both directions:
> no judgment module imports the engine, and the adapter *is* the importer.

Core return type — **numpy in the core, pandas only at the real adapter**:

```python
# harness/foundation.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Protocol as TypingProtocol
import numpy as np

@dataclass(frozen=True)
class FoldReturns:
    """Per-fold OOS return series at FIXED normalized exposure (sizing frozen)."""
    timestamps: np.ndarray        # datetime64[ns], strictly increasing
    values: np.ndarray            # float64 per-period returns (net of costs)
    periods_per_year: float       # annualization cadence (matches bar cadence)
    by_symbol: Mapping[str, "FoldReturns"] | None = None  # for concentration/breadth gates

@dataclass(frozen=True)
class QuickRunResult:               # Train quick run (free, unlimited)
    valid: bool                     # passed causal replay + decision contract
    causal_ok: bool
    in_sample_metric: float | None  # coarse plausibility, AFTER costs (None if infeasible)
    trade_count: int
    slices: Mapping[str, Mapping[str, float]]  # {"by_symbol":{...},"by_month":{...},"by_hour":{...}}
    failure_stage: str | None

@dataclass(frozen=True)
class FoldEvalResult:               # one Selection fold or the Lockbox (one evaluate call)
    succeeded: bool
    causal_ok: bool
    returns: FoldReturns | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float | None
    trade_count: int
    worst_period_return: float | None
    provenance: Mapping[str, str]   # snapshot id, foundation+backend versions (FR-I1)
    failure_stage: str | None

class FoundationGateway(TypingProtocol):
    def quick_run(self, experiment, protocol, window) -> QuickRunResult: ...
    def evaluate(self, experiment, protocol, window) -> FoldEvalResult: ...
```

- `window` is a `(start, end)` span the harness derives from the Protocol's tiers
  and the walk-forward schedule. **The harness owns fold orchestration**; it calls
  `evaluate` **once per fold** (FR-J2 "one evaluate call per fold").
- Implementations:
  - `RealFoundationGateway` (P2) — adapts `quant_strategies.runner.run_config`
    (quick_run) and `quant_strategies.evaluation.run_evaluation` (evaluate) to the
    types above, reading per-fold returns through the **P0 typed accessor** (never
    Parquet scraping).
  - `FakeFoundationGateway` (P1, `tests/`) — returns injected synthetic
    `FoldReturns`/results. The entire judgment layer is tested through this.

**P0's job (in `quant_strategies`)** is to make `RealFoundationGateway`
implementable without scraping: expose a **typed per-fold OOS return-series
accessor** on the evaluate result and support **one evaluate per fold**. The exact
foundation-side API is P0's to design against the foundation's real types; it must
be sufficient to populate `FoldEvalResult.returns` (and per-symbol returns) and the
provenance fields. PSR/DSR/PBO are **not** added to the foundation — significance
is the harness's job.

---

## 3. Shared judgment types (stable across phases)

```python
# harness/objective/res.py
@dataclass(frozen=True)
class ResResult:
    feasible: bool                 # all Stage-1 gates passed
    gate_results: Mapping[str, "GateOutcome"]   # name -> pass/fail + value + threshold
    rank_sharpe: float | None      # the ranking number: residual-alpha Sharpe, OOS, undeflated (FR-C6)
    per_fold_sharpe: tuple[float, ...]          # the evidence unit (FR-C4)
    residual_info_ratio: float | None           # after factor-panel regression (FR-C3)
    psr: float | None
```

- **RES is per-row undeflated** (FR-C6). Selection-bias correction lives in the
  budget (prevent), the audit (correct), and the Lockbox (confirm) — never in the row.
- **Rank on Sharpe** (FR-C2). Sortino/Calmar/maxDD/worst-fold/dispersion/cost-stress/
  concentration/effective-breadth are **gates**, not the ranking number.

```python
# harness/lockbox.py
Verdict = Literal["confirmed", "rejected", "insufficient_evidence"]
@dataclass(frozen=True)
class LockboxVerdict:
    verdict: Verdict
    mde: float | None              # Lockbox minimum detectable effect
    claimed_edge: float | None
    binding_test: Literal["forward_block", "block_bootstrap"]
```

```python
# harness/ledger.py — append-only row (FR-E1, I1)
@dataclass(frozen=True)
class LedgerRow:
    trial_id: str
    family_id: str                 # computed fingerprint (FR-E4), NOT the free-text thesis
    experiment_hash: str           # strategy ref + params
    protocol_hash: str             # content hash of the Protocol (FR-H2)
    thesis: str                    # effect / observable / falsifier
    per_fold_returns: tuple[FoldReturns, ...]   # FULL series of EVERY trial — the audit needs these
    res: ResResult
    provenance: Mapping[str, str]  # snapshot id + versions (reproducible — AC-7)
    created_at: str                # ISO; injected, never read from a clock inside pure code
```

---

## 4. Config ownership & the mechanical wall (FR-H)

Two surfaces, split by ownership:

- **Experiment** (`experiment.toml`, agent-editable): `strategy_path` + `[params]`
  (+ optional bounded discovery symbol set). Nothing about how it is judged.
- **Protocol** (harness-owned, read-only to the agent; e.g. `protocol.toml` loaded
  from outside the agent's writable surface): data tiers, costs, fill model,
  fold/walk-forward/embargo config, objective metric + gates + thresholds, factor
  panel, budget, perturbation steps, annualization.

Rules (mechanical, not advisory):
- Protocol is **content-hashed**; the run **fails closed** on drift; the hash is
  recorded in every ledger row (FR-H2, AC-3).
- The layer that derives the foundation's per-call config lets `params` populate
  **only** strategy params — it can **never** override cost/fill/tiers (FR-H3): a
  zero-cost model cannot be resurrected through a param key.
- Protocol & Experiment are Pydantic models, `frozen`, `extra="forbid"`.

---

## 5. Conventions

- **Env:** all Python via `conda run -n quant`. Tests: `conda run -n quant python -m pytest`.
- **Determinism (NFR-1):** identical (Protocol, params, snapshot, versions) → identical
  metric. No `datetime.now()`/RNG inside judgment math; timestamps/ids are injected.
- **Types:** Pydantic at external/config boundaries; frozen dataclasses for internal
  value objects; numpy for return-series math.
- **Append-only ledger; atomic writes** (FR-I2, NFR-6): a Selection touch is reserved
  before it runs and finalized after, failing safe toward "charged + logged."
- **Pure strategy contract** is the foundation's (`generate_decisions`/`validate_params`);
  the harness never asks the strategy to load data.
- Each phase = one OpenSpec change (`openspec/changes/<name>/`), archived on completion.
  `openspec/` is gitignored (local working-spec home); durable specs/docs live in `docs/`.

---

## 6. Legacy retirement map (no code left behind)

| Legacy artifact | Retired in | Replaced by |
|---|---|---|
| `scoring.py` (net_return/day) | P1 | `harness/objective/` (RES) |
| single agent-editable `experiment.toml` model | P1 | Protocol (immutable) + Experiment (hypothesis) |
| `experiment_config.py` | P1–P2 | `harness/protocol.py` + `harness/data/` config |
| contiguous-window evaluation | P2 | `harness/data/` tiers + walk-forward |
| `results.tsv` as system-of-record | P3 | `harness/ledger.py` |
| `promotion.py` | P4 | `harness/audit.py` + `harness/lockbox.py` |
| `runner.py` `--explore`/`--promote` monolith | P5 | `harness/escalation.py` + `harness/cli.py` (clean shell ported to `harness/session.py`) |
| `tools/research_handoff_*.py` + their tests | P5 | retired (replaced by ledger/graduation surfaces) |
| `strategy.py` | n/a | kept; rewritten to the new contract in P5 |

By the end of P5: no top-level legacy judgment module remains; `program.md`,
`AGENTS.md`, `README.md` describe only the new world; no `--explore`/`--promote`,
no `net_return/day`, no agent-editable judgment.

---

## 7. Acceptance-criteria → phase map (what "correct" means)

| AC | Meaning | Verified in |
|---|---|---|
| AC-1 | Replaying the diagnosed campaign (ADA-only, short-only, excluded-hours, cranked sizing) ⇒ infeasible/rejected | partial P1, full P2, end-to-end P5 |
| AC-2 | Renaming/splitting a family does not increase total Selection looks | P3 |
| AC-3 | Agent edit to Protocol fails the run closed; ledger hash detects drift | P1 |
| AC-4 | Knife-edge (collapses under ±step) cannot be evaluated | P1 |
| AC-5 | Lockbox MDE > claimed edge ⇒ insufficient-evidence, never confirmed | P2/P4 |
| AC-6 | Batch of true-zero-Sharpe strategies ⇒ rejected by the audit | P4 |
| AC-7 | A ledger row regenerates its metric from its fingerprint | P3 |
| AC-8 | Agent cannot raise graduation odds by re-evaluating tweaks beyond budget | P3 |
| AC-9 | Pure factor-beta / funding-carry strategy ⇒ ≈0 residual alpha, no graduation | P1 |
| AC-10 | Per-fold OOS returns via typed foundation API; significance in harness | P0 + P2 |

Tests are written against the named AC-#, not just unit coverage.
