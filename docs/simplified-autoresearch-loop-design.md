# Simplified Auto-Research Loop — Design

**Status:** historical design / decision record (2026-06-06). Output of a
first-principles brainstorm. The simplified loop is now implemented and hardened;
use `README.md`, `program.md`, `protocol.toml`, and `openspec/specs/` as the
active operating sources. This document is retained as context, not the live implementation contract.

**Historical implementation sketch warning:** sections below may mention old or
unbuilt implementation details such as cache plumbing, `git revert`, `params.toml`,
or pre-archive OpenSpec tasks. Do not implement from this section. Treat it as
decision history only; active contracts live in the files named above.

This describes a **clean-slate rebuild** of `quant_autoresearch`. The existing
shipped 5-phase evaluator package and its docs are **retired** (§10), not
refactored. The sole template for the new world is **karpathy/autoresearch**; the
prior heavy approach is preserved in git history only and is intentionally not
referenced here, to avoid anchoring on it.

**Anchors:**
- The simplicity model we copy: **karpathy/autoresearch** (its `program.md` loop).
- Objective + first principles: `../../quant_strategies/RESEARCH_DIRECTION.md`.
- The engine we build on (kept as-is): `quant_strategies` public API
  (`runner.run_config`) + `quant_data` loaders.

---

## 1. Objective (the anchor)

I am a **personal trader**. The goal is not a publishable methodology or a
statistically perfect historical verdict:

> **A few uncorrelated strategies running live and making money** — reached by a
> path I can actually execute: develop → forward-test (paper) → small live → scale.

Auto-research's job is to **feed deployment**, not to certify edges from history
alone. Deployable beats pure; simple beats elaborate. We deliberately choose the
**curated-few** regime (hand-seeded, thesis-driven), which is what makes a simple
loop sound rather than naïve.

---

## 2. The core insight (why we cannot copy karpathy literally)

karpathy's agent climbs `val_bpb` and climbing it is **safe**: it edits the
training *recipe*, the model fits to *train* data, and validation merely *measures*
generalization. 100 experiments lowering val loss = 100 genuine improvements; there
is no "overfit the val set" because parameters are never fit *to* val.

In trading, "climb a backtest score" is the **opposite**. A backtest is a *biased
estimator*: `score = real edge + fitting-bias + noise`. Run keep-if-improved 100×
and you have built a machine that selects for noise. This is intrinsic to the
domain, not a flaw in the engine. **So the naïve karpathy port — one strategy,
climb one backtest number, never stop — is, for trading, an overfitting machine.**

The whole design is the resolution of the tension in the goal *"climb a score a
bit"* **and** *"don't overfit."* We resolve it by changing **what** is climbed,
**how far**, on **which data**, with a **narrow editable surface** — and by moving
the honest measure entirely out of the loop.

---

## 3. karpathy/autoresearch as the template

We keep his operational shape and change only what the trading domain forces.

| karpathy/autoresearch | This repo | Same? |
|---|---|---|
| `program.md` — one-page agent contract | `program.md` — one-page agent contract | **same idea** |
| `train.py` — the single agent-editable file | `strategy.py` — agent-editable signal logic + bounded params | **same idea** |
| `prepare.py` — read-only; agent can't touch data prep / eval | operator-owned read-only **protocol** (universe, window, costs, objective) | **same idea** |
| metric: `val_bpb` on held-out val | metric: a **robustness number on Train** (§6) | **changed** — a backtest number is biased; we climb robustness, not raw return |
| `results.tsv` — append-only experiment log | `results.tsv` — append-only experiment log | **same** |
| loop: edit → train 5 min → keep/discard → **never stop** | loop: edit → cached ~1s run → keep/revert → **stop on a rule** (§7) | **changed** — a bounded climb must terminate |
| validation is *in* the loop (you tune toward it) | OOS is **out** of the loop entirely (§9) — never tuned toward | **changed** — see §2 |

Everything outside that "changed" column is deliberately kept boring and identical
to karpathy.

---

## 4. Decisions (the resolved forks)

| # | Fork | Decision |
|---|---|---|
| D1 | What the loop iterates on | **Bounded climb on a robustness number** on Train. Not raw return; not generate-and-discard. |
| D2 | Autonomy | **Auto within a thesis; human-gated between theses.** Machine does the tedium; human owns thesis choice + irreversible promotion. |
| D3 | Overfit guard | **Narrow the agent's editable surface** — dangerous knobs live in read-only config the agent cannot reach. No logic-inspection, no ledger, no fingerprints. |
| D4 | Scope / home | **Clean-slate rebuild of `quant_autoresearch` on the karpathy template**, calling the kept `quant_strategies` engine. The shipped 5-phase evaluator is retired (§10). |
| D5 | The climbed number | **Pluggable objective** (build several, select one in read-only config), chosen **a-priori and frozen per thesis**; agent never chooses it. Default `worst_subwindow`. |
| D6 | Out-of-sample eval | **Removed from auto-research entirely.** The loop never sees OOS, never calls `evaluate`. The OOS gate is a separate downstream process (§9). |
| D7 | Loop constants | **`M`, `N`, and `K` are operator-configurable protocol settings**, frozen per thesis run and read-only to the agent. They are not hard-coded and not agent-tuned mid-run. |

Each maps to a first principle in `RESEARCH_DIRECTION.md`: D1/D5 ← P1–P3 (can't
tune your way to an edge; optimize on Train, *select* downstream); D3 ← P6
(structural/categorical search is the dangerous vector); D6 ← P2/P3/P4 (the honest
measure is scarce, non-renewable, and the real verdict is forward).

---

## 5. The loop (per thesis)

Auto-research is handed **Train-only data**. It never receives the OOS window or
the `evaluate` API.

```
YOU seed a thesis: mechanism (one sentence) + its falsifier.        # the only creative input
AGENT reads program.md + the seed, then loops until a stop-rule fires:
    edit strategy.py (signal logic) + propose bounded params         # within declared bounds
    if a signal component was added/changed:
        append its a-priori rationale + falsifier to rationale.md     # REQUIRED to keep the change
    run   = cached Train quick-run                                    # run_config on in-memory rows → ~1s
    score = objective(per-subwindow / per-cell after-cost returns)    # protocol-owned; agent cannot change
    gates = trade_floor AND breadth AND cost_stress AND complexity_cap# binary
    keep if (score improved AND all gates pass) else `git revert`
    append a row to results.tsv                                       # commit, score, gate flags, n_components, n_trades, note
  -> stop-rule fires  (plateau for M iters | complexity exhausted | budget N reached)
  -> Train floor gate: does the best candidate clear Train minimums?
        no  -> thesis dies on Train, nothing handed off
        yes -> freeze {strategy.py, params.toml, protocol.toml} + results.tsv + rationale.md
  -> STOP. Hand the frozen candidate to YOU.
YOU (between-thesis gate): read results.tsv + rationale.md; reseed / discard / send to the downstream OOS gate (§9).
```

**Deliberate departures from karpathy, each with a reason:**

- **~1s per iteration, not 5 min.** The data load (≈ half of wall-time per
  `RESEARCH_DIRECTION` §5) is paid **once per thesis** and cached in memory; we keep
  his "~100 experiments" throughput on Train.
- **Keep-if-improved is on the robustness number + gates**, not raw return — the
  climb resists noise instead of chasing it.
- **The loop stops** (he never does). A *bounded* climb must terminate; the human
  owns the between-thesis calls.
- **No `evaluate`, ever, inside auto-research** (D6). The honest measure is a
  separate downstream gate.

---

## 6. The editable surface — the entire overfit guard (D3)

The direct analog of karpathy's editable `train.py` vs read-only `prepare.py`. The
guard is *a narrow surface*, not a validator.

| Agent-editable | Harness-owned (read-only to the agent) |
|---|---|
| signal logic in `generate_decisions` (pure fn; already lint-enforced by the engine) | **which symbols** (fixed universe) → kills symbol cherry-picking |
| a few **bounded** numeric params (bounds declared in `validate_params`) | **time window; no agent hour/date exclusions** → kills exclusion games |
| | `cost_model`, `fill_model` → cannot be zeroed |
| | the **Train window** handed in (OOS physically not present) |
| | the **objective + gate thresholds** |

The diagnosed ADA overfit needed exactly two moves — *pick the symbol* and *exclude
the hours*. Both are now read-only config the agent cannot reach, so we get the
protection with **zero logic-inspection**.

The only count the loop enforces is a **complexity cap** (max N declared signal
components / params); a component without a `rationale.md` entry cannot be kept.

> **Honest limitation.** A determined agent could under-declare a component it
> actually codes. Caught only when you read `rationale.md` against `strategy.py` at
> the gate — procedural, not mechanical. Acceptable for curated-few.

---

## 7. The climbed number (D5) + the gates

**Principle (from `RESEARCH_DIRECTION`): rank on ONE number; everything else is a
gate, not part of the number.**

### Pluggable objective

One interface, several implementations, selected by `[objective] kind` in the
read-only protocol (Open/Closed seam — add a fourth without touching the loop or
gates):

- `worst_subwindow` *(default)* — split Train into `K` contiguous subwindows; the
  number is the minimum after-cost trade-unit robustness score across them. The
  edge must show up even in the worst slice. Simplest, interpretable,
  asset-agnostic.
- `breadth_median` — median after-cost Sharpe across **symbol × subwindow** cells,
  penalized by dispersion. Rewards an edge that generalizes across the universe.
  Use for real cross-sections; degenerates for single-instrument strategies.
- `cv_mean` — purged/embargoed K-fold CV mean within Train. Familiar from ML;
  heaviest; thin on short serially-correlated history.

### The guardrail that makes "easily choose" safe

> The objective is **operator-owned and chosen a-priori, frozen per thesis.** It is
> selected in the read-only protocol **before the climb starts**. The **agent never
> chooses its own objective** (that would become "pick the metric that flatters this
> candidate"), and you **do not swap objectives after seeing a downstream verdict**
> (meta-level tuning against the holdout — a P2 violation). "Easily choose" means
> *configure up front per thesis*, never *retry after the verdict*. This discipline
> is **procedural, not mechanically enforced** — a recorded residual risk.

### Gates (binary; not part of the climbed number)

- **trade_floor** — minimum trade count (reject degenerate / too-few-trades fits).
- **breadth** — not concentrated in a single symbol (applies when universe > 1).
- **cost_stress** — edge survives a cost / slippage bump.
- **complexity_cap** — declared components / params within the cap (the simplicity
  tax, mechanical).

---

## 8. Stopping rule + Train floor gate

`M`, `N`, and `K` are explicit config values in the read-only protocol:

```toml
[loop]
plateau_patience = M        # stop after this many non-improving completed attempts
max_iterations = N          # hard ceiling per thesis
min_abs_improvement = eps   # absolute score delta that counts as real
min_rel_improvement = rho   # optional relative score delta

[objective]
kind = "worst_subwindow"
subwindows = K
```

They are **operator-configurable before a thesis starts** and frozen for that run.
The agent can read them but cannot change them while climbing.

### Plateau definition

Let `s_t` be the score from completed iteration `t`, and let `b_t` be the best
kept feasible score before `t`. A completed iteration is an **improvement** iff:

```
all_gates_pass(t) AND s_t > b_t + max(eps, rho * max(1, abs(b_t)))
```

where `eps = loop.min_abs_improvement` and `rho = loop.min_rel_improvement`.
Otherwise it is a non-improving attempt. The thesis is on a **plateau** when
there have been `M` consecutive completed attempts since the last improvement.
Crashes, invalid strategies, and gate failures count toward `N`; once a feasible
baseline exists, they also count as non-improving attempts for plateau. If no
feasible baseline is found within an initial grace window, the thesis dies on
Train rather than looping forever on broken code.

**Stop the thesis** on the first of: **plateau** as defined above; **complexity
exhausted** (at the cap with no improvement); **budget** (hard ceiling `N`, e.g.
~60).

**Train floor gate** then decides whether the thesis produces a handoff at all: the
best candidate must clear Train minimums (worst-subwindow floor, trade floor, all
gates green). If not, **the thesis dies on Train and produces no candidate** — we
never pass junk downstream. (`M`, `N`, `K`, the cap, and the floors are per-asset
protocol settings, not hard-coded constants.)

---

## 9. The downstream OOS gate (relocated, mandatory, NOT auto-research) (D6)

The honest out-of-sample measure lives **outside** auto-research, where the
irreversible human gate already is. The funnel is unchanged — only *ownership*
moved:

```
Train climb (auto-research)  ->  downstream OOS gate  ->  paper  ->  small live  ->  scale
```

- **One look.** A single `quant-strategies evaluate` on the **frozen candidate**
  (its `strategy.py` + `params.toml` + `protocol.toml`) against the **reserved OOS
  window**, using the candidate's own costs/fills. Binary go/no-go (after-cost
  risk-adjusted > floor, maxDD ≤ ceiling, trades ≥ floor, not concentrated, survives
  cost-stress). **Logged once; never tuned against.**
- **Why it is a *stronger* wall than bundling it in.** Auto-research never holds the
  OOS window or the `evaluate` API — no path to leak, peek, or wire it back. A
  *physical* wall, not a *promised* one. It also fits how `quant_strategies` already
  treats `evaluate`: the **stateless, frozen-candidate** surface, designed to run
  downstream on a frozen artifact.
- **A Train-survivor is not a promotion signal.** Passing the OOS gate earns a
  **paper** test (the real confirmation surface), nothing more.

For now this gate is simply a documented `evaluate` invocation on the frozen
candidate. A thicker forward/paper/live process is a later, separate project.

---

## 10. Clean-slate retirement (D4)

The existing `quant_autoresearch` is a **shipped** 5-phase evaluator. This rebuild
**retires it wholesale** rather than refactoring it — to stay simple and unanchored
from the heavy approach.

**Retired (deleted in the rebuild change):**
- the entire old evaluator package and its statistical confirmation, bookkeeping,
  budget, family-tracking, orchestration, data-tier, session, and CLI modules;
- the heavy `program.md`, `strategy.py`, `protocol.toml`, `experiment.toml`, the
  generated quick-run artifacts, and `results/`;
- the four methodology docs (`auto-research-methodology.md`, the old architecture doc,
  `refactor-phase-plan.md`, `PRD.md`). Their reasoning is preserved in git history;
  the durable distillation already lives in `RESEARCH_DIRECTION.md`.

**Kept:**
- the `quant_strategies` engine (public `run` API) + `quant_data` loaders — unchanged;
- `quant_strategies/evaluation/fold_returns.py` (the P0 per-fold OOS accessor) — it
  lives in the *engine* repo and is a legitimate `evaluate` capability the downstream
  OOS gate (§9) can use. **Open question for the plan: keep vs. remove** (§13).

**Execution discipline (so `main` never breaks):** the wipe and the rebuild land in
**one change on a branch** — old code/docs deleted and the new thin loop added
together — never a commit where `main` has neither a working old system nor a
working new one. No deletion happens before the implementation plan is approved.

---

## 11. What gets built (fresh, on the karpathy template)

All new; nothing harvested from the retired evaluator. The only reuse is the
`quant_strategies` engine and `quant_data`.

| File | Job |
|---|---|
| `program.md` | the one-page agent contract, intentionally mirroring `karpathy/autoresearch`'s structure while translating the content to this repo's trading-specific usage |
| `loop.py` | per-thesis loop: edit → cached run → score → keep/revert → log → stop |
| `objective.py` | the pluggable robustness objectives behind one interface + selector |
| `gates.py` | the binary gates (trade-floor, breadth, cost-stress, complexity cap) |
| `protocol.py` | operator-owned read-only config + the params-only merge-back |
| `cache.py` | in-memory Train-window cache — **the one new piece of plumbing** |
| `results.tsv` | the climb log (karpathy's exact artifact) |
| thin CLI | `climb` (run a thesis) · `status`. **No `screen`/`evaluate`.** |
| `strategy.py` | a small example agent-editable strategy (fresh, not the 37KB one) |

**The one engine-adjacent risk — the cache.** Try a loop-side memoizing wrapper
first (no `quant_strategies` change): load the Train window once via `quant_data`,
hold normalized rows in memory, feed repeated `run_config` calls. If `run_config`
re-loads data unavoidably, the clean fix is a small public "pass pre-loaded rows"
parameter upstream (`RESEARCH_DIRECTION` flags caching as the #1 lever).

**v1 proves on crypto perp** (data ready; the prior `funding_crowding` thesis is a
known mechanism to re-seed), then FX, then equity/options. The loop and pluggable
objective are asset-agnostic by construction.

### `program.md` shape

The new `program.md` should be deliberately close to the reference repo's
structure, so an agent can recognize the same operating model:

1. **Setup** — agree on a thesis/run tag, create/use the branch, read the small
   in-scope file set, verify data access, initialize `results.tsv`, and confirm
   before the climb starts.
2. **Experimentation** — describe exactly what is editable (`strategy.py` and
   bounded params) and what is fixed/read-only (`protocol.toml`, objective,
   gates, symbols, Train window, costs/fills, OOS/evaluate).
3. **Output format** — define the run summary fields the agent must parse:
   score, gate flags, trade count, breadth, cost-stress result, complexity count,
   elapsed time, and result status.
4. **Logging results** — require a tab-separated `results.tsv` with stable
   columns and one row per attempted iteration; keep it as the loop's lightweight
   memory, matching the reference repo's style.
5. **The experiment loop** — edit, commit, run, parse, keep/revert, log, repeat
   until the configured stop rule fires.
6. **Trading-specific differences** — no `evaluate` inside auto-research, no OOS
   tuning, no symbol/hour cherry-picking, rationale required for each signal
   component, and stop on the configured plateau instead of running forever.

---

## 12. Honest limitations (recorded, not hidden)

- **Robust-on-Train ≠ generalization.** The climb still optimizes an in-sample
  number (even if robustified). It *reduces* overfit; it does not eliminate it. The
  downstream OOS gate and forward testing remain the real filters.
- **Short, single-regime history** limits how much even worst-subwindow robustness
  means — the reason forward is the verdict.
- **The complexity cap** partly relies on honest component declaration (§6).
- **Objective pluggability** carries a residual meta-overfit risk if the a-priori /
  frozen / no-swap discipline (§7) is not followed; it is procedural.
- **Clean-slate cost.** We discard working, reviewed code (incl. a Protocol wall and
  a quick-train surface that overlap this design). Accepted deliberately for
  simplicity and to avoid anchoring; the cost is rebuild effort.

---

## 13. Open questions for the implementation plan

1. Default numeric values per asset: Train floors/ceilings, gate thresholds,
   `M` (plateau patience), `N` (max iterations), `K` (subwindows), `eps`/`rho`
   (plateau improvement thresholds), the complexity cap, and the initial
   feasible-baseline grace window.
2. Cache feasibility: loop-side wrapper vs. a small `run_config` "pre-loaded rows"
   parameter — verify against the real `quant_strategies` API.
3. Protocol mechanics: where the read-only `protocol.toml` lives so the agent's
   workspace cannot write it, and the exact params-only merge-back.
4. `rationale.md` format: the minimal logged schema per signal component
   (mechanism, observable, falsifier).
5. Thesis-family tracking at the human gate: the lightest running list to keep the
   live set uncorrelated (not a fingerprint algorithm).
6. Fate of `quant_strategies/evaluation/fold_returns.py` (keep for the downstream
   gate vs. remove).
7. The branch + single-change wipe-and-rebuild sequence (§10), incl. retiring
   `openspec/` artifacts and `AGENTS.md`/`README.md` references to the old world.
