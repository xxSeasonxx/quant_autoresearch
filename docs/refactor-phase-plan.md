# Auto-Research Rebuild — Phase Plan (COMPLETE)

**Status:** ✅ shipped. All phases **P0–P5** were implemented, independently reviewed (statistics,
spec-compliance, test-honesty, and adversarial correctness lenses), and landed on branch
`refactor/auto-research-rebuild`. This document is retained as a historical map; the per-phase
implementation chronology lives in **git history** and the archived OpenSpec changes.

- **Requirements:** [PRD.md](./PRD.md) — FR-A..J, AC-1..AC-10.
- **Design rationale:** [auto-research-methodology.md](./auto-research-methodology.md).
- **As-built architecture / cross-phase contract:** [harness-architecture.md](./harness-architecture.md).
- **Operator must-knows before a live campaign:** the README's *"Before a live campaign"* section.

---

## What shipped

The judgment core was rebuilt **greenfield** in the `harness/` package. Every legacy judgment
module was retired — `scoring.py`, `promotion.py`, `experiment_config.py`, `runner.py`,
`artifact_policy.py`, `tools/`, and `results.tsv` are gone. **No legacy, fallback, or
compatibility code remains** (enforced by contract tests + a repo-wide grep).

| Phase | Delivered | Key modules | Acceptance |
|---|---|---|---|
| **P0** | Typed per-fold OOS return-series accessor on the evaluate result (cross-repo, `quant_strategies`) | `quant_strategies/evaluation/fold_returns.py` | AC-10 |
| **P1** | Immutable content-hashed **Protocol** + **Experiment** wall (no override path); **RES** objective — residual-alpha Sharpe over a factor panel, funding-as-carry, frozen sizing, undeflated per row; **stability gate** | `harness/protocol.py`, `harness/objective/*`, `harness/stability.py`, `harness/foundation.py` | AC-3, AC-4, AC-9 |
| **P2** | **Tiered Data Service** + forward-only **walk-forward** (purge/embargo); **RealFoundationGateway** adapter; remaining Stage-1 gates (PSR, max-DD, worst-fold, cost-stress); **Asset Profiler** + data-sufficiency | `harness/data/*`, `harness/foundation_real.py`, `harness/orchestrator.py`, `harness/profiler.py` | AC-1, AC-5, AC-10 |
| **P3** | Append-only **Trial Ledger** (full per-fold returns + fingerprints, atomic/fail-safe); global **Budget Manager** (MinBTL effective-N); signal-structure **Family** fingerprint; Selection controller | `harness/ledger.py`, `harness/budget.py`, `harness/family.py`, `harness/selection.py` | AC-2, AC-7, AC-8 |
| **P4** | **Graduation Auditor** — Romano-Wolf stepdown / PBO over the logged returns of all trials, HAC + data-driven block (serial-correlation-robust); power-aware **trichotomous Lockbox**; top-K rule | `harness/audit.py`, `harness/lockbox.py`, `harness/graduation.py`, `harness/bootstrap.py` | AC-6 |
| **P5** | **Escalation Controller** + naked-sweep routing + swing-big cadence; `run`/`evaluate`/`status` CLI (+ admin `graduate`); session shell; finalized one-page `program.md`; full legacy sweep + new-world `README`/`AGENTS`/`strategy.py` | `harness/escalation.py`, `harness/cli.py`, `harness/session.py` | AC-1 end-to-end |

**Dependency order as executed:** P0 ∥ P1 → P2 → P3 → P4 → P5. P0 (foundation) ran in parallel with
P1 (judgment skeleton); the judgment layer is decoupled from the engine behind a `FoundationGateway`
seam (only `harness/foundation_real.py` imports `quant_strategies`), so P1–P4 were built and
verified deterministically against a fake gateway before the real wiring landed.

## Verification

Every test names the acceptance criterion it covers; the suite runs under
`conda run -n quant python -m pytest`. AC-9 (factor neutrality) and AC-6 (audit FWER under serial
correlation) each went through multiple adversarial review→fix→re-verify cycles. The one standing
constraint is environmental: live `quant_data` is unreachable here, so real-data paths are
data-gated smokes (see [UPSTREAM_LIMITATIONS_TODO.md](../UPSTREAM_LIMITATIONS_TODO.md) and the
README). The judgment logic itself is fully verified in-process.
