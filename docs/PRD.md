# Auto-Research Harness — Product Requirements

**Status:** v1 requirements, derived first-principles from [`auto-research-methodology.md`](./auto-research-methodology.md). Implementation-agnostic — components are named by *responsibility*, not by any existing module. Where it depends on the foundation (`quant_strategies`) or data layer (`quant_data`), that is a deliberate ownership decision, not inherited structure.
**Date:** 2026-06-05

---

## 1. Problem & product definition

A backtest score is a **biased** estimator of future performance, and the bias **grows with the number of trials**. An autonomous searcher that "optimizes one number, keep/discard, loop" therefore converges on the *most overfit* strategy — whose edge collapses out-of-sample. LLM searchers compound this: they game whatever number they're shown and rationalize data-mined patterns with fluent theses.

**The product** is an autonomous research harness with two halves:

- a **thin agent loop** that proposes falsifiable, causal hypotheses and develops them, and
- an **immutable evaluator** that makes overfit and edge-less results *structurally impossible to graduate* — not merely discouraged.

**North star:** maximize the expected live, risk-adjusted, compounded profit of *graduated* strategies, while controlling the rate of false graduations. Rigor lives in the harness the agent cannot edit; simplicity lives in the agent's one-page contract.

---

## 2. Goals & non-goals

**Goals (each maps to acceptance criteria in §10):**

- **G1 — Trustworthy verdicts.** A "graduated" verdict means a real, out-of-sample, risk-adjusted edge at a stated confidence, or it is not issued.
- **G2 — Overfit can't score.** Leverage, turnover, single-symbol concentration, calendar curve-fitting, and factor/funding-carry beta cannot raise the score.
- **G3 — Search is honestly bounded by data.** The number of out-of-sample looks is capped by the asset's information content, not compute, and cannot be reset by the agent.
- **G4 — Reproducible & auditable.** Every decision is reconstructable from an append-only ledger.
- **G5 — Hypothesis-only agent surface.** The agent edits the strategy and its params; never how it is judged.
- **G6 — Fast inner loop.** Iterating ideas on in-sample data is free and quick; the expensive, honest evaluation runs only on candidates that earn it.

**Non-goals (v1):** live trading/execution; position sizing, leverage, and capacity/impact modeling (downstream of human promotion); multi-strategy portfolio construction; data materialization/refresh (owned by `quant_data`); being the *final* validation framework (graduation ≠ production sign-off).

---

## 3. Users

- **Human researcher / operator** — authors the immutable `Protocol`, launches campaigns, reads verdicts, and owns the one human gate (promotion above the Lockbox).
- **Autonomous LLM research agent** — proposes one hypothesis at a time, edits strategy + params, runs/evaluates within the harness, never touches judgment config or the Lockbox.
- **Downstream consumer** (out of scope) — the promotion/live pipeline that sizes and deploys a graduated, human-approved strategy.

---

## 4. Principles (product invariants)

1. **A backtest is biased; bias grows with trials** → defend in three complementary layers: prevent (budget), correct (audit over logged returns), confirm (one-shot wall). None substitutes for another.
2. **You are judged on what you did not optimize** → a hard data wall: optimize on Train, select on out-of-sample folds seen only in summary, confirm once on a Lockbox never iterated against.
3. **Leverage and *factor* beta are not alpha** → score scale-free residual alpha at fixed exposure; size downstream.
4. **Costs are part of the edge** → realistic costs in the primary objective; in crypto, funding is carry, not alpha.
5. **LLM searchers game the number** → the harness, not prose, enforces every judgment; the agent's editable surface is hypothesis-only.
6. **An asset only earns the conclusions its data can support** → asset-agnostic but data-driven: profile the asset, derive budget/Lockbox/significance, and return *insufficient evidence* when data can't support a verdict.

---

## 5. Functional requirements

### A. Research loop (agent contract)
- **FR-A1** The agent works one candidate at a time in an isolated workspace, in a never-early-stop session ended only by the harness or a human.
- **FR-A2** A candidate requires a **falsifiable, causal thesis** (effect, observable, falsifier) to consume any out-of-sample look. A param nudge with no thesis is not a candidate.
- **FR-A3** The agent's only editable surface is the strategy logic and its parameters. (G5)
- **FR-A4** Every M ideas the harness requires a structurally new signal family ("swing big") to break local-optima cagyness.

### B. Data tiers & the wall
- **FR-B1** Three disjoint partitions per asset — **Train** (optimize freely), **Selection** (out-of-sample screen, summary-only to the agent), **Lockbox** (one-shot confirmation) — fixed in the Protocol, never agent-editable.
- **FR-B2** Selection is a **forward-only walk-forward**: each test fold sits strictly after its training window; the per-fold out-of-sample returns are the evidence.
- **FR-B3** Adjacent partitions/folds are separated by a **purge** gap sized to the holding/label horizon, plus a small **embargo** buffer on the following training block.
- **FR-B4** The **Lockbox is write-once per *dataset***: once any candidate is scored on a Lockbox block, that block is spent for the whole campaign; a new Lockbox requires fresh forward time. (Closes the cross-batch reuse leak.)

### C. Objective — Robust Edge Score (RES)
- **FR-C1** RES is computed on out-of-sample Selection folds at **fixed normalized exposure**. Sizing/leverage is frozen during search.
- **FR-C2** **Rank on Sharpe** (the statistic with a usable sampling distribution). Sortino, Calmar, and max-drawdown are **feasibility gates**, not the ranking number.
- **FR-C3** Score **residual alpha**: regress OOS returns on a tradeable factor panel (market/benchmark, cross-sectional momentum, funding-carry, size) and score the residual. Market beta *and* factor beta are not edge. In crypto, **funding is modeled as carry**, never additive PnL.
- **FR-C4** The unit of evidence is the **per-fold Sharpe set** (feeds gates and the audit's cross-trial variance). A pooled track is descriptive only.
- **FR-C5** Stage-1 feasibility gates (hard, binary; fail any ⇒ infeasible): evidence sufficiency (PSR / min-trade proxy), max-drawdown ceiling, worst-fold floor + dispersion ceiling, cost-stress survival, concentration ceiling + **effective-breadth** floor (correlation-aware, so co-moving baskets don't pass as diversified).
- **FR-C6** The per-row RES is **not** deflated — selection bias is handled outside the row (§F).

### D. Escalation & stability
- **FR-D1** "Satisfice on Train, select on Selection." A candidate may escalate to a Selection look **iff** it clears the escalation gate: *valid · alive · in-sample-positive after costs · new thesis · cheap-robust · on a robust plateau.* Above the floor, candidates are **not** ranked for escalation by Train magnitude.
- **FR-D2 — Stability gate (computed, not LLM-judged).** Before a Selection look, the harness perturbs each tunable param ±1/±2 natural steps on Train (one-at-a-time; steps owned by the Protocol, not the agent) and requires the in-sample metric to stay **flat-and-positive**: `min_N m(θ) ≥ ρ·m(θ*)` (ρ≈0.6) **and** ≥80% of neighbours positive after costs. Stability score `S = min_N m(θ)/m(θ*)`. A knife-edge fit is routed back to Train. Rewards *flatness, not height* — uncheatable by climbing the score.
- **FR-D3** The agent never hill-climbs an out-of-sample number: a Selection look is a **logged bet**, not a step in an improvement loop. There is no "keep if the score rose" on Selection.

### E. Trial budget & ledger
- **FR-E1 — Trial ledger** (harness-owned, append-only): every Selection look records the computed family id, full config, the **full per-fold OOS return series**, the thesis, timestamps, and the Protocol hash. (The audit is impossible without the returns of *every* trial.)
- **FR-E2 — Global budget.** The multiple-testing unit is each Selection look; the budget is **global to the campaign**, not reset per family.
- **FR-E3 — Budget sizing.** Derived from the **effective** sample (autocorrelation-discounted history) and **effective** independent trials (clustering correlated configs) — MinBTL's `N` is effective-N. Treated as an upper bound; computed per asset by the Asset Profiler (§G).
- **FR-E4 — Family identity is computed, not declared.** "Family" is a harness fingerprint of the **signal structure** (e.g., a hash of the signal-construction code excluding param values), so relabeling a thesis cannot mint fresh budget. (G3)
- **FR-E5** When the budget is spent, the harness stops issuing Selection looks (graduate the best, or retire); the agent is never handed a countdown.

### F. Graduation audit & verdict
- **FR-F1 — Correction.** At graduation, run a **Romano-Wolf stepdown / PBO** over the logged per-fold returns of *all* competing trials (not just finalists). Operating on the returns, it absorbs cross-trial correlation directly — no `N=K` shortcut, no separate `N_effective` estimate.
- **FR-F2 — Confirmation (power-aware Lockbox).** Re-evaluate survivors once on the fresh Lockbox. The verdict is **trichotomous**: *confirmed*, *rejected*, or **insufficient-evidence** — the last returned whenever the Lockbox's minimum detectable effect exceeds the candidate's claimed edge. Where the forward block is too thin for power, a stationary/block-bootstrap CI is the binding test and the forward block is a sanity check.
- **FR-F3** A candidate **graduates to the Lockbox** iff it clears the gates, ranks top-K by OOS Sharpe (PSR-gated), and survives the trial-population audit. "Promotion" (above the Lockbox) is a separate, human-only step.

### G. Asset profiling & data-sufficiency
- **FR-G1** Before a campaign, the Asset Profiler measures usable history, effective regime count, cross-section breadth/correlation, and autocorrelation, and **derives** the budget (§E3), the window/fold/Lockbox sizing, and the significance bar.
- **FR-G2** If the profile cannot support a powered confirmation, the harness refuses to run a graduation for that asset and reports *insufficient evidence* — it never lowers the bar to manufacture a verdict. (Principle 6)

### H. Config & ownership
- **FR-H1 — Two config surfaces.** *Experiment* (agent-editable): strategy reference + params (+ a bounded discovery symbol set if allowed). *Protocol* (harness-owned): data tiers, costs, fill model, fold/CPCV/regime config, objective metric + gates + thresholds, budget, perturbation steps, annualization.
- **FR-H2 — Mechanical wall.** The Protocol is loaded from outside the agent's writable surface, **content-hashed**, and the run **fails closed** on drift; its hash is recorded in every ledger row. (G5)
- **FR-H3 — No override path.** The layer that derives the foundation's per-call config lets params populate only strategy params; it can **never** override cost/fill/tiers (so a zero-cost model cannot be resurrected through a param key).

### I. Reproducibility & audit
- **FR-I1** Every ledger row carries a **measurement fingerprint** — hashes of strategy, params, and Protocol; the `quant_data` snapshot id; foundation and backend versions — sufficient to reproduce the metric.
- **FR-I2** A campaign pins one `quant_data` snapshot; ledger appends are atomic (a Selection touch is reserved before it runs and finalized after, failing safe toward "charged").

### J. Foundation & data dependencies
- **FR-J1** Honest per-fold metrics and the causal-replay/decision-contract integrity check (Tier-0) come from the foundation (`quant_strategies`); the harness orchestrates, it does not re-derive engine math.
- **FR-J2 — Required foundation additions (in scope):** a **typed per-fold return-series accessor** on the evaluate result (today only summary scalars + on-disk Parquet exist), and **one `evaluate` call per fold** (today multi-window evaluate pools with no embargo). PSR/DSR/PBO are **not** added to the foundation — significance is the harness's job.
- **FR-J3** Data access is through public `quant_data` loaders only; materialization/refresh/repair stay upstream.

---

## 6. Key objects & contracts

| Object | Owner | Contract / invariant |
|---|---|---|
| **Candidate** | agent | strategy + params; pure (no data loading / side effects) |
| **Family id** | harness | deterministic fingerprint of signal structure; stable under param changes; the budget key |
| **Protocol** | human | immutable per campaign; hashed; defines all judgment |
| **Ledger row** | harness | append-only; full per-fold OOS returns + thesis + fingerprint; never mutated |
| **RES** | harness | per-row, undeflated, reproducible from the fingerprint |
| **Verdict** | harness | confirmed / rejected / insufficient-evidence; Lockbox write-once per dataset |
| **Asset profile** | harness | derives budget, sizing, significance; gates data-sufficiency |

---

## 7. Core workflows

**Per-idea loop:** thesis → edit → `run` (Train, free) → develop to robust plateau → escalation gate → `evaluate` (Selection, spends 1 from global budget) → log the bet → next *distinct* thesis.
- *Invalid* (fails causal replay/contract): not a candidate; never reaches Selection.
- *Fails gate* (incl. knife-edge): stays on Train.
- *Budget spent*: harness stops Selection looks; graduate best or retire family.

**Graduation:** top-K by OOS Sharpe → returns-based audit (Romano-Wolf/PBO) → power-aware Lockbox → verdict → (human) promotion. Lockbox block then spent.

**Campaign lifecycle:** profile asset → derive budget/sizing/bar (or *insufficient evidence* → stop) → search under global budget → graduate → confirm → retire.

---

## 8. Interfaces

- **CLI (agent-facing):** `status` (best candidate + recent ledger), `run --desc` (Train: causal diagnostic + coarse plausibility band, free), `evaluate --desc` (Selection: RES + gates, costs one trial). Admin/human: `profile`, `graduate`, `lockbox`.
- **Agent contract (`program.md`):** one page — the loop in §7, the editable/read-only split, "satisfice on Train, select on Selection, never touch the Lockbox." (Draft: methodology Appendix A.)
- **Protocol schema:** declarative config for tiers, costs, fill, objective, gates, thresholds, budget, perturbation steps, annualization.

---

## 9. Non-functional requirements

- **NFR-1 Determinism:** identical (Protocol, params, data snapshot, versions) → identical metric.
- **NFR-2 Auditability:** any verdict reconstructable from the ledger alone.
- **NFR-3 Performance:** Train `run` is seconds and free; the heavy honest path runs only on escalated candidates.
- **NFR-4 Isolation/security:** the agent process cannot read or write the Protocol, the Lockbox, or the ledger except through harness-mediated, logged actions.
- **NFR-5 Observability:** budget consumed, family ledger, gate/stability outcomes, and verdict provenance are inspectable.
- **NFR-6 Failure-safe:** crashes during a Selection touch resolve toward "charged + logged," never a silent un-ledgered look.

---

## 10. Acceptance criteria (the "it works" tests)

- **AC-1 No overfit graduation.** Replaying the diagnosed campaign (ADA-only, short-only, excluded-hours, cranked sizing) yields *infeasible/rejected* — never graduated.
- **AC-2 Budget unforgeable.** Renaming a thesis or splitting a family does not increase the total Selection looks a campaign can run.
- **AC-3 Immutable judgment.** An agent-process edit to the Protocol fails the run closed; the ledger's Protocol hash detects drift.
- **AC-4 Knife-edge bounced.** A config whose in-sample metric collapses under ±step perturbation cannot be evaluated.
- **AC-5 Data-sufficiency honesty.** On an asset whose Lockbox MDE > claimed edge, the verdict is *insufficient-evidence*, never *confirmed*.
- **AC-6 Audit catches noise.** A batch of true-zero-Sharpe strategies routed to graduation is rejected at the configured level (Romano-Wolf over logged returns).
- **AC-7 Reproducible.** A ledger row regenerates its metric bit-for-bit from its fingerprint (pinned snapshot + versions).
- **AC-8 No hill-climb leak.** The agent cannot raise a candidate's graduation odds by re-evaluating tweaks on the same Selection data beyond the budget.
- **AC-9 Factor neutrality.** A pure factor-beta strategy (e.g., a BTC-beta basket, or a funding-carry collector) scores ≈0 residual alpha and does not graduate.
- **AC-10 Foundation boundary.** Per-fold OOS returns are obtained via a typed foundation API (no Parquet scraping); significance is computed in the harness.

---

## 11. Dependencies

- **`quant_strategies` (foundation):** per-fold honest metrics + causal-replay integrity; **requires** the two additions in FR-J2.
- **`quant_data`:** public loaders; point-in-time correctness, funding data for crypto carry modeling.

---

## 12. Out of scope / future

Position sizing & fractional-Kelly, capacity/market-impact modeling (downstream of promotion); multi-strategy portfolio FDR across campaigns; Thresholdout-style noised Selection feedback (budget is the v1 mitigation); combinatorial purged CV (optional, correlation-caveated); auto-generated factor panels.

---

## 13. Open decisions (tuning / risk-appetite)

Thresholds (PSR floor, max-DD ceiling, trade band, concentration/effective-breadth, audit significance, stability ρ and step sizes); the budget number per asset (expect single digits on short crypto history); Train-signal resolution (lean coarse); escalation ownership (lean: agent proposes, harness enforces gate + budget).

---

## Appendix — Build vs. Refactor (delivery decision)

*Separate from the spec above. The PRD is implementation-agnostic; this section maps it onto today's `quant_autoresearch` repo to decide how to deliver.*

### Gap map (PRD capability → legacy reality)

| Capability | Legacy state | Disposition |
|---|---|---|
| Objective / scoring (C) | `net_return/day` — rewards leverage; the diagnosed bug | **Replace** |
| Config ownership (H) | single agent-editable `experiment.toml` (incl. `cost_model=0/0`) | **Replace** (new immutable Protocol + mechanical wall) |
| Data tiers / walk-forward / purge-embargo (B) | absent (contiguous single-regime windows) | **New** |
| Trial ledger / global budget / family fingerprint (E) | absent | **New** |
| Graduation audit (Romano-Wolf/PBO), PSR (F) | absent (`promotion.py` is ad-hoc recent-window + cost-stress) | **New / replace** |
| Stability gate, escalation gate (D) | absent | **New** |
| Asset profiler / data-sufficiency (G) | absent | **New** |
| CLI surfaces `run`/`evaluate` (8) | `--explore`/`--promote` | **Replace** |
| Causal-replay + contract integrity (Tier-0, J1) | present (foundation; legacy invokes) | **Reuse** |
| Session / worktree / never-early-stop shell | present, but in a 51KB monolithic `runner.py` | **Partial reuse** (port deliberately) |
| Foundation integration plumbing | present; needs FR-J2 additions | **Reuse + extend** |

**Roughly 70–80% of the harness is new-or-replaced; the entire *judgment* layer — the product's reason to exist — is 100% new.** Reuse concentrates in the integration shell and the foundation-side integrity check.

### Recommendation: **rebuild the core greenfield, *in the same repo*, retiring legacy modules — not an in-place refactor, not a new repo.**

- **Not an in-place refactor of the legacy modules.** `scoring.py`, `promotion.py`, and the single-`experiment.toml` model *encode the exact anti-patterns* the methodology removes (return-per-day objective, agent-editable judgment, no data wall). Mutating them risks carrying hidden assumptions forward — the patch-on-patch failure the methodology explicitly warns against. There is little to refactor *into*; the target shares almost no abstractions with the source.
- **Not a new repo.** The two-repo boundary (foundation vs. loop) is already correct; a new repo would throw away the foundation wiring, env/CI, worktree/session tooling, and git history for no benefit, and duplicate the `quant_data` integration.
- **So: a fresh package layout inside `quant_autoresearch`**, with components matching §5 (Protocol, Tiered Data Service, Scorer, Stability Gate, Escalation Controller, Trial Ledger, Budget Manager, Family Identifier, Graduation Auditor, Lockbox Manager, Asset Profiler). Port only the thin reusable shell (session/worktree, foundation invocation, causal-replay wiring) deliberately; **delete** the legacy judgment modules wholesale rather than evolve them. Keep history.

**Sequence (matches the methodology's phasing, dependency-ordered):** foundation return-series accessor + per-fold evaluate (FR-J2) → Protocol + mechanical config wall (H) + frozen-sizing/costs-on objective (C1–C3) → ledger + global budget + family fingerprint (E) → walk-forward + asset profiler + data-sufficiency (B, G) → audit + power-aware Lockbox (F) → stability gate + escalation + swing-big (D).

**Reconsider only if** a closer audit shows `runner.py`'s session shell is genuinely clean and decoupled from the scoring/promotion model — in which case more of the shell is portable. Either way the judgment layer is new code, not refactored code.

**First buildable slice (highest leverage, smallest surface):** the Protocol + mechanical wall + the RES objective (Sharpe residual-alpha, frozen sizing, costs-on) + the stability gate — this alone makes the diagnosed overfit unscoreable (AC-1, AC-4, AC-9) without yet needing the full ledger/audit machinery.
