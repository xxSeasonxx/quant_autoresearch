# Auto-Research Rebuild — Phase Plan

**Status:** plan only — not started. This is the input to the OpenSpec / `/feature-workflow` implementation workflow (one change per phase).
**Decision:** rebuild the judgment core **greenfield, in this repo**, retiring legacy modules — not an in-place refactor, not a new repo (see [PRD.md](./PRD.md) §Appendix). Requirements: [PRD.md](./PRD.md). Design rationale: [auto-research-methodology.md](./auto-research-methodology.md). This plan **supersedes** the methodology doc's former "Refactor Plan" section.

---

## Approach

- **Greenfield core, same repo.** Stand up a fresh package layout whose modules match PRD §5 responsibilities (Protocol, Tiered Data Service, Scorer, Stability Gate, Escalation Controller, Trial Ledger, Budget Manager, Family Identifier, Graduation Auditor, Lockbox Manager, Asset Profiler). Keep git history, the two-repo boundary, env, and tooling.
- **Retire, don't mutate.** Legacy judgment modules (`scoring.py`, `promotion.py`, the single agent-editable `experiment.toml` model) encode the anti-patterns; delete them wholesale at the phase that replaces them rather than evolving them.
- **Port the shell deliberately.** Reuse only the thin, clean parts of the session/worktree shell and the foundation invocation; treat the rest of `runner.py` as reference.
- **Each phase is shippable and verifiable.** Every phase maps to a PRD acceptance criterion (AC-#) and becomes one OpenSpec change.

---

## Dependency order

```
P0 foundation accessor (quant_strategies)
        │
P1 judgment skeleton ──────────────┐         (Protocol wall + RES objective + stability gate; Train-side)
        │                          │
        ▼                          │
P2 data tiers + walk-forward ◄──── P0         (real OOS RES; asset profiler + data-sufficiency)
        │
        ▼
P3 ledger + global budget + family fingerprint
        │
        ▼
P4 graduation audit + power-aware Lockbox verdict
        │
        ▼
P5 escalation controller + search quality + agent contract  (closes the loop)
```

P0 and P1 can proceed in parallel (P0 is cross-repo). P2 needs both. P3→P5 are sequential.

---

## Phases

### P0 — Foundation enablement *(cross-repo: `quant_strategies`)*
- **Goal:** expose what the loop needs from the foundation.
- **Builds (PRD FR-J1/J2):** a **typed per-fold return-series accessor** on the evaluate result; **one `evaluate` call per fold** (no pooled multi-window with seams); confirm the causal-replay + decision-contract integrity check is callable per fold. PSR/DSR stay out of the foundation.
- **Retires:** the need to scrape `portfolio_path.parquet` across the repo line (preventive).
- **Depends on:** nothing.
- **Acceptance:** AC-10 — a fold returns its OOS return series in-process via a typed API; foundation tests green.
- **OpenSpec change:** `foundation-perfold-returns` (proposed/built in `quant_strategies`).

### P1 — Judgment skeleton: Protocol wall + RES objective + stability gate
- **Goal:** make overfit unscoreable and judgment immutable — *before* tiers exist. Highest leverage, smallest surface (the PRD's "first buildable slice").
- **Builds:** new package layout; **Protocol** (immutable, content-hashed, fail-closed) + **Experiment** split with no param-override path (FR-H1/H2/H3); frozen sizing + costs-on; the **RES objective** module — rank-on-Sharpe, **residual-alpha** over a factor panel, **funding-as-carry**, per-fold evidence unit (FR-C1–C4); the cheap Stage-1 gates incl. **effective-breadth** (FR-C5 subset); the coarse Train plausibility signal; the **stability gate** (perturb ±steps, flat-and-positive; FR-D2).
- **Retires:** `scoring.py` (net_return/day); the single agent-editable `experiment.toml` model.
- **Depends on:** nothing (uses Train data + existing foundation `run`).
- **Acceptance:** AC-3 (immutable judgment), AC-4 (knife-edge bounced), AC-9 (factor-neutral), partial AC-1 (overfit can't score on the feedback path).
- **OpenSpec change:** `judgment-core`.

### P2 — Data tiers + walk-forward + asset profiler
- **Goal:** the data wall and the *real* out-of-sample RES.
- **Builds:** **Tiered Data Service** (Train/Selection/Lockbox; FR-B1); **walk-forward** folds with **purge + embargo** (FR-B2/B3); per-dataset Lockbox bookkeeping (FR-B4); RES wired through the P0 accessor (full OOS RES + remaining Stage-1 gates: PSR, max-DD, worst-fold, cost-stress); **Asset Profiler** + **data-sufficiency** gate (FR-G1/G2).
- **Retires:** the contiguous single-regime window model.
- **Depends on:** P0 (accessor), P1 (objective).
- **Acceptance:** AC-1 (full — OOS overfit can't graduate), AC-5 (insufficient-evidence on thin data), AC-10 (boundary in use).
- **OpenSpec change:** `data-tiers-walkforward`.

### P3 — Trial ledger + global budget + family fingerprint
- **Goal:** make search honestly bounded and unforgeable.
- **Builds:** **Trial Ledger** (append-only; full per-fold returns; measurement fingerprint + Protocol hash; FR-E1, FR-I1); **Family Identifier** (signal-structure fingerprint; FR-E4); **Budget Manager** (global, effective-N, MinBTL upper bound; FR-E2/E3/E5); atomic, reproducible ledger writes (FR-I2); budget enforcement on Selection looks.
- **Retires:** `results.tsv` as system-of-record; ad-hoc trial accounting.
- **Depends on:** P2 (Selection must exist to budget).
- **Acceptance:** AC-2 (budget unforgeable by relabeling), AC-7 (reproducible row), AC-8 (no hill-climb leak).
- **OpenSpec change:** `ledger-budget`.

### P4 — Graduation audit + power-aware Lockbox verdict
- **Goal:** correct the residual selection bias, then confirm on fresh data.
- **Builds:** **Graduation Auditor** — Romano-Wolf stepdown / PBO over the logged trial returns (FR-F1); top-K graduation rule (FR-F3); **Lockbox Manager** with the **power-aware, trichotomous verdict** (confirmed / rejected / insufficient-evidence) + block-bootstrap fallback (FR-F2); the graduation module (reserve "promotion" for the human step).
- **Retires:** `promotion.py` (ad-hoc recent-window + cost-stress + rotating probe).
- **Depends on:** P3 (logged returns), P2 (Lockbox tier).
- **Acceptance:** AC-6 (audit rejects a batch of true-zero-Sharpe strategies).
- **OpenSpec change:** `graduation-audit`.

### P5 — Escalation controller + search quality + agent contract
- **Goal:** close the loop and finalize the agent's one-pager.
- **Builds:** **Escalation Controller** (agent proposes; harness enforces gate + budget; FR-D1); naked-sweep routing (thesis-free nudges → Train); swing-big cadence (FR-A4); the `run` / `evaluate` / `status` CLI (+ admin `profile`/`graduate`/`lockbox`); finalize `program.md` per methodology Appendix A.
- **Retires:** `--explore`/`--promote` CLI; the rest of the legacy `runner.py` orchestration (port the clean shell, delete the rest).
- **Depends on:** P1–P4.
- **Acceptance:** the full loop runs end-to-end; agent contract matches Appendix A; replaying the diagnosed campaign end-to-end yields no graduation (AC-1 end-to-end).
- **OpenSpec change:** `loop-and-contract`.

---

## Legacy retirement map

| Legacy artifact | Retired in | Replaced by |
|---|---|---|
| `scoring.py` (net_return/day) | P1 | RES objective module |
| single agent-editable `experiment.toml` | P1 | Protocol (immutable) + Experiment (hypothesis) |
| `experiment_config.py` (config model) | P1–P2 | Protocol/Experiment schema + tier config |
| contiguous-window evaluation | P2 | Tiered Data Service + walk-forward |
| `results.tsv` as record | P3 | Trial Ledger |
| `promotion.py` | P4 | Graduation Auditor + Lockbox Manager |
| `runner.py` `--explore`/`--promote` monolith | P5 | Escalation Controller + `run`/`evaluate`/`status` CLI (clean shell ported) |
| `strategy.py` (scratch strategy) | n/a | kept as the agent-editable surface; rewritten to the new contract as needed |

---

## Cross-cutting

- **Tests per phase** are written against the named AC-#, not just unit coverage.
- **Env:** all Python via `conda run -n quant`.
- **Git history** preserved; legacy modules deleted in their retiring phase (not left dead).
- **Foundation dependency:** P2+ are blocked on P0 landing in `quant_strategies`.

---

## Decisions *(moved from the methodology doc)*

**Resolved (encoded in the PRD + methodology):**

- **Ranking metric = Sharpe** (Sortino/Calmar/maxDD are gates) — the metric we can deflate.
- **Audit = Romano-Wolf / PBO over the logged trial returns** (not `N=K` DSR).
- **Budget is global to the campaign**, on the effective sample, keyed to a computed family fingerprint (relabeling can't reset it).
- **Asset-agnostic, data-driven** — campaign *order* is a deployment choice; the harness derives per-asset budget/Lockbox/bar and returns *insufficient evidence* when data can't support a verdict.
- **Foundation in scope** for a typed per-fold return-series accessor + one-`evaluate`-per-fold.
- **Edge enforcement = mechanical** (factor-neutral scoring + funding-as-carry); the human gate stays at Lockbox promotion.
- **Delivery = rebuild greenfield in this repo**, retire legacy modules.

**Still open (risk-appetite / tuning — resolve during the relevant phase):**

1. **Thresholds** (P1–P2) — PSR floor, max-DD ceiling, trade-count band, concentration / effective-breadth ceilings, audit significance level, stability ρ and perturbation steps. Defaults proposed at build time.
2. **Budget number** (P3) — derive the MinBTL effective-N cap per asset from real data; confirm appetite (expect single digits on short crypto history).
3. **Train-feedback resolution** (P1) — how coarse the free Train signal is. Lean coarse.
4. **Escalation ownership** (P5) — lean: agent proposes, harness enforces gate + budget.
5. **`runner.py` shell reuse** (P5) — confirm by audit how much of the session shell is clean enough to port vs. rewrite.

---

## Execution model (when ready — not now)

Each phase becomes **one OpenSpec change**, run through `/feature-workflow`: discovery → OpenSpec spec → parallel subagent build → parallel review → archive. This plan is the workflow's input; start with **P0 and P1** (parallelizable), since P1 alone makes the diagnosed overfit unscoreable.
