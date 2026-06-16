# Harness Diagnosis & Objective Redesign — Discussion Record

**Type:** point-in-time design-discussion / decision record — the *rationale* behind
the redesign. The **active plan to execute is `docs/harness-objective-roadmap.md`**
(self-contained; read that to implement). Not an active contract: the live contracts
stay in `protocol.toml`, `objective.py`, `gates.py`, `loop.py`, `program.md`, and
`docs/score_research.md`; when these decisions land, those docs get updated. The
durable "why" — rejected alternatives, migration rationale, chronology — then belongs
in `HISTORY.md`; fold this file into `HISTORY.md` at that point rather than keeping a
second source of truth for the upstream contract.
**Date:** 2026-06-15

This record captures one working conversation: first questioning *why the current
Train survivor makes such a low return*, then deciding *what to change in the
harness, process, and objective*. The upstream (`quant_strategies`) risk-budget
sizing piece has since **shipped** (2026-06-16); the upstream section records the
landed contract. The consumer-side pieces (guided operator mandate, money-first
objective/gates, return-blind universe rule, and ledger fields) remain to build
in `quant_autoresearch`.

---

## Operating principle (read first)

Be practical: **make real money, robustly.** This is the decision rule for every
harness, objective, process, and universe choice below. Three requirements that
must hold *jointly* — a candidate failing any one is not a survivor, however well
it scores on the others:

1. **Make money, uncertainty-adjusted.** The objective is realized economic return
   at the deployed book size, haircut for the statistical uncertainty of its own
   estimate. A scale-invariant ratio (Sharpe, PSR, Calmar) is wrong *as the
   objective*: it cannot tell a 0.2%-return book from a 20%-return book of the same
   shape. Statistical significance is not a separate side constraint to bolt on — it
   is internalized as the uncertainty haircut inside the money score. If the score
   does not move when deployed return moves, the score is wrong.
2. **Don't overfit.** A survivor must generalize beyond this Train window, not
   memorize it. Enforce robustness in the score's *shape* (weakest subwindow +
   uncertainty haircut + cost stress), a deflated acceptance bar for the
   best-of-many search, a rule-based frozen universe with no symbol cherry-picking,
   and hard simplicity caps. On a tie, keep the simpler candidate.
3. **Stay practical.** Price costs, slippage, capacity, and position size exactly
  as live trading will, so a passing survivor is deployable to paper then live as
   is. Surface real ceilings (capacity, universe breadth); never hide a limit to
   make a number look better.

The failure this rule prevents is today's survivor: maximally "not overfit" and
consistent, yet it makes no money — the objective never asked it to, and its costs
were priced at a size no one would deploy. Optimize for the opposite: **the most
money obtainable that is also robust and deployable.** Encode this as the North
Star in `program.md`.

---

## Part 1 — Diagnosis: why the survivor returns almost nothing

The felt problem: the current survivor is unattractive — a very low return. The
question was first-principles: is it the upstream harness, the project setup /
`protocol.toml`, the `program.md` operating instructions, or just a bad strategy?

### The survivor's actual numbers (attempt-12, re-confirmed at attempt-50)

- `total_return ≈ 0.00224` over ~~10 months (**~~0.27%/yr**); max drawdown **0.11%**.
- `max_gross_utilization ≈ 0.0111` — the book deploys **~1.1% of a 100% budget**;
~99% sits in cash.
- Capacity is **not** binding: bar participation 8.7% (cap 50%), ADV
participation 2.4% (cap 25%) → ~5–10× headroom before any cap binds.
- Per-observation `sharpe ≈ 0.0068`, `sharpe_se ≈ 0.0040` → full-train PSR **0.95**
(annualized Sharpe **≈ 1.5–2**).
- Per-trade edge is real: net ≈ `1.0e-5` of NAV per trade (~29 bps on position
notional at weight 0.0035), after ~10 bps cost; profit factor 1.64; win rate
0.55; all three symbols profitable.

**Read: the shape is good (Sharpe ~~1.8), the scale is nothing (~~1% gross). The low
return is a scale artifact, not an edge artifact.**

### Root cause: the scored objective is magnitude-blind (and mildly prefers shrinking)

```text
score = min( PSR(full_train), min_k PSR(subwindow_k) )
PSR   = NormalCDF( (sharpe - hurdle) / sharpe_se )     # objective.py:144, hurdle = 0
```

- `sharpe = mean/std` is **scale-invariant**: multiply every target weight by `k`
and both mean and std scale by `k`, so the score is unchanged. The score cannot
tell a 0.2%-return book from a 20%-return book of the same shape.
- Impact cost is `10bps × adv_participation^0.5` (`portfolio_foundation.py:1254`)
— super-linear, so a *bigger* book has a slightly *worse* Sharpe. The score
therefore mildly **rewards shrinking toward zero size**.
- The only return constraint is the gate `min_total_return = 0.0` (just "be
positive"). Nothing in the score or gates rewards return magnitude or using the
leverage budget.
- Confirmation already in `results.tsv`: attempt-35 scaled +10% → return rose,
score moved **−0.00002**; attempt-34 scaled −10% → score essentially unchanged.
Size moves return ~linearly and the score not at all.

The loop did exactly what it was told — maximize worst-window PSR — and PSR does
not value money. 50 attempts converged on a tiny, ultra-safe, consistent book.

### Scoring the four hypotheses honestly

- **Setup / protocol — the main problem.** Objective is magnitude-blind by config;
`min_total_return = 0` is toothless; the 3-symbol universe + capacity model on
1-minute bars caps deployable gross at ~6–7% (so `leverage_budget = 1.0` is
largely illusory); ~31 of 35 `experiment.toml` params are dead (strategy reads
~4).
- **Harness — mostly sound.** Accounting, causality, cost/fill, and foundation
NAV-path stats are reasonable and faithfully computed a small return for a small
book. Real critiques: (1) the only objective offered is magnitude-blind; (2) PSR
multiplicity-blindness across 50 × 6 windows; (3) the causality micro-replay
timed out (`verified: false`) in the survivor card.
- **program.md — a goal/metric split.** North Star says "strongest real, tradeable
economic return," but the loop maximizes worst-window PSR (consistency). "Size is
not alpha" + a scale-invariant score = the doc actively reinforces
under-deployment.
- **Just a bad strategy — no.** Real per-trade edge, good shape, all names
profitable. Honest caveat: funding-sign carry on three majors is intrinsically a
small-capacity sleeve; even fully deployed under current capacity it tops out
~1.5–3%/yr. It is a legitimate diversifying carry sleeve that needs breadth +
leverage to matter.

### The Karpathy anchor

`karpathy/autoresearch`'s "one file, one metric" works because its metric
(`val_bpb`) **directly measures the deliverable** (model quality). This project
copied the structure (one metric, keep-or-discard) but chose a metric
(worst-window PSR) that measures statistical consistency, not money. The pattern
is right; the scalar is wrong.

---

## Part 2 — What to do next: decisions reached

Goal restated: a strategy that actually makes money, so it can go to paper then
live; keep overfit resistance; keep it simple; be able to iterate strategies
easily and rerun this one anytime; get the foundation right.

### Decision 0 — Guided operator mandate (elicited and frozen first)

Everything below optimizes *against your goals*, so your goals must be an explicit,
recorded input — not numbers the agent invents and you rubber-stamp. Before a run,
the agent runs a small **operator mandate** brief in plain language with defaults
and explanations. You are not expected to know quant terms; the LLM's job is to
guide, translate, and recommend. The mandate is then frozen in
`protocol.toml [mandate]`. The sizing target, return hurdle, drawdown limit, and
universe threshold below all **derive from this**, not from the mechanism or from
Train results.

Ownership:

- **Season owns preferences:** capital, acceptable loss, desired return,
  paper/live intent, markets to avoid, and hard limits.
- **LLM owns guidance:** explain tradeoffs, recommend defaults, translate
  plain-language answers into candidate protocol values, and state assumptions.
- **Protocol owns enforcement:** approved values become mechanical fields and are
  frozen for the lifecycle.
- **Train loop owns research only:** it cannot revise mandate values because
  results are inconvenient.

The mandate (set once, reused — a stable profile, not a per-run questionnaire):

- **Capital** — money in this book (`portfolio_notional`).
- **Risk appetite → target volatility** — "calm / normal / aggressive" mapped to a
vol number with a default; becomes Decision 3's `target_volatility`.
- **Drawdown stop** — the loss that would make you switch it off; this *is* the
`max_abs_drawdown` path-risk gate, chosen by you, not a default.
- **Return hurdle** — the return that makes this worth doing; sets the real money
gate (Decision 5), honestly.
- **Deployment intent** — paper first, time to live, any holding-horizon preference.
- **Hard limits** — leverage allowed, instruments to avoid, liquidity floor.

Why first, and why frozen: (1) the knobs that encode risk must be elicited with
defaults and explanations rather than assumed; (2) committing the risk / return /
acceptance bar *before* the search is itself anti-overfit — it stops the goalposts
from moving to flatter whatever the loop produces. A desk quant could set
`protocol.toml` directly and skip the brief; the elicitation step exists to serve a
non-expert operator and to make intent explicit.

Implementation shape: move new-thesis setup out of `program.md` into a top-level
setup contract such as `new-strategy.md`. That document owns the operator brief,
mandate translation, protocol fit, universe rule, lifecycle reset, and approval
checklist. `program.md` stays the active Train-loop runbook after the setup is
approved.

Build order: the load-bearing, build-first piece is the frozen `[mandate]` fields,
their derivation into `[risk_budget]` and the gate thresholds, and the
anti-goalpost-moving freeze. The LLM-guided elicitation brief and `new-strategy.md`
are usability polish for a non-expert operator; they must not block the money-first
objective and gates (Decisions 2 and 5), which are the load-bearing consumer changes
and can land against mandate fields set directly in `protocol.toml`.

### Decision 1 — Approach B refined: one money-first objective + real risk-budget sizing

Chosen over (A) a cheap magnitude fix that still misprices cost at the tiny scale,
and (C) a two-stage screen-then-deploy split. **B is the only option where the
number the loop chases *is* the deployable-money number** — so a passing survivor
means "ready to paper-trade," not "ready if the costs don't bite."

Refinement after decision review: keep protocol-level support for alternate
objective kinds, but do not make the menu an ordinary convenience. A permissive
objective menu lets the operator or agent choose the friendliest scalar. The
default active objective should be one money-first scalar; alternatives require
explicit pre-loop protocol fit and Season approval.

### Decision 2 — Default score: weakest-window deployed return, uncertainty-haircut

The default `objective.kind` is `return_lcb_subwindow`. The run score is the
weakest-window lower bound on deployed annualized return — the deployed-book
annualized return haircut by one standard error of its own estimate:

```text
score   = min over windows of [ annualized_return_w - k_rank * SE(annualized_return_w) ]
SE(annualized_return_w) = return_volatility_w * P / sqrt(effective_sample_size_w)
k_rank  = 1     # ranking haircut; the heavier multiplicity haircut is the
                # acceptance gate in Decision 5
```

windows = full Train plus each configured subwindow. The SE is the textbook standard
error of a mean (`σ/√n`), computed directly from per-window fields the foundation
already emits: `return_volatility_w` and `effective_sample_size_w` from its
`ReturnStatistics`, and `P = annualization_periods_per_year` from the
`PortfolioSizingReport`. These are per-period, so `annualized_return_w =
mean_return_w × P`. No proxy: do not approximate the SE as `sharpe_standard_error ×
vol` — that mixes the per-period Sharpe SE with annualized vol and understates the
true SE by ≈√P. As an intuition / cross-check, the identity `SE = annualized_return_w
/ t_w` holds with `t_w = sharpe_w / sharpe_se_w = Φ⁻¹(PSR_w)` — the same t-stat the
current PSR score computes — so the lower bound equals `annualized_return_w · (1 −
k_rank / t_w)`. `n_eff` already discounts lag-1 autocorrelation; the SE does not model
higher-order autocorrelation or within-window non-stationarity.

Why a lower bound, not raw return. Once the foundation owns scale (Decision 3), the
loop controls only *shape*. At a fixed vol target, raw worst-window return and
worst-window Sharpe rank candidates almost identically, so a raw-return score is not
the money lever its name implies — its one real effect over Sharpe/PSR is that it
drops the uncertainty penalty, which is the worst thing to drop in a best-of-many
in-sample search. The lower bound keeps money as the unit and folds the penalty back
in. It factors as `(uncertainty-deflated Sharpe) × (deployed volatility)`: the first
factor resists overfit, the second is the capacity/money lever that rewards shapes
able to carry more size. Raw return drops the first factor; a ratio drops the second.

Where the money actually grows: deployed scale and capacity — Decision 3 plus the
mandate vol target plus universe breadth — not the choice of scalar. The objective
change makes the score money-*denominated*, gateable, and overfit-braked; it does not
by itself make the loop hunt for more money. Do not credit the scalar swap with the
scale fix.

The objective registry can still include alternatives, but their roles are narrow:

| kind | role |
| --- | --- |
| `return_lcb_subwindow` | default primary score; deployed money, uncertainty-haircut |
| `return_subwindow` | undeflated diagnostic only (point-estimate deployed return) |
| `calmar_subwindow` | gate, finalist diagnostic, or explicit protocol-fit alternative |
| `sharpe_subwindow` | risk-adjusted diagnostic or explicit protocol-fit alternative |
| `psr_subwindow` | diagnostic / legacy comparison |

The SE haircut now lives inside the primary score, so PSR is no longer a separate
robustness screen; Calmar, Sharpe, and PSR are diagnostics or tie-breakers. The
score must move when deployed return moves and must penalize windows whose return is
statistically thin.

### Decision 3 — Size the book to a risk budget (the money + honesty fix)

First-principles point that drove this: **Calmar = return ÷ drawdown is *also*
scale-invariant**, so changing the ratio alone will not make money appear. We fix
the *scale*, not the ratio.

**Status: shipped upstream** as the `[risk_budget]` contract (see the upstream
section). What landed:

- `TargetDecision.target` is now **base target shape**, not a deployable weight.
The foundation normalizes the shape by maximum intended raw gross exposure, applies
`[risk_budget]`, and scores the final executable book. Global scale is owned by the
foundation, not the strategy.
- `[risk_budget]` is **required** on every surface. Train quick-run uses
`mode = "calibrate_vol"` with `target_volatility` (the budget you set); validation
and evaluation use `mode = "fixed_scale"` with the `book_scale` the Train run
recorded — the same deployed size carried OOS, no recalibration.
- Ownership split (first principles, and what landed): **sizing belongs in the
foundation** — only it knows volatility, how each capacity limit binds, and impact;
the loop must not re-derive capacity math. A target above what the universe can
carry is **information, not an error**: the foundation sizes to the **max feasible
vol**, records `capacity_bound`, and still scores; only genuine infeasibility fails
closed. `FOUNDATION_LOCK` was refined accordingly.

Sizing precedence (must be explicit in the owning doc): vol-target sizing clamps to
the leverage budget first, then to the capacity frontier (recorded as
`capacity_bound`). Reaching the leverage cap or the capacity frontier before hitting
the vol target is **information**, not failure. Only a strategy's *raw intended
shape* that already implies exposure over the leverage / risk budget fails closed.

Consumer rule: remove the strategy's global `weight` parameter absolutely. Relative
allocation shape is valid; deployable scale is not. If a strategy needs conviction
or cross-sectional allocation, it can emit relative base shapes. It must not carry a
single knob whose purpose is to search final economic size.

### Decision 4 — Universe as a frozen rule, expandable at reseed

- Replace the hand-picked 3-symbol list with `[universe] rule`: an objective filter
(data kind + min ADV/liquidity + data-readiness + complete marks over the
window). The harness resolves it to a concrete list at run start, then **freezes
and records** both the rule and the resolved list.
- More money = loosen **one threshold** at reseed when capacity, mandate, and data
readiness justify it (more symbols → more capacity + diversification). The agent
may **propose** expansion with capacity evidence; it must **never** pick individual
symbols from Train P&L — that is the overfit trap. An explicit list stays valid (a
trivial rule) for replay.
- The resolver must be return-blind. It can use data availability, mark
completeness, liquidity, volume, capacity support, instrument eligibility, and
operator exclusions. It must not use realized return, per-symbol PnL, Sharpe,
Calmar, win rate, or any Train performance statistic.

### Decision 5 — Gates, protocol, params, program.md

- Money floor = deflated acceptance gate. Replace the toothless
`min_total_return ≥ 0` and the now-redundant `train_score_floor` with one
money-denominated floor: the weakest-window deployed-return lower bound, taken at the
*deflated* haircut, must clear the mandate hurdle.

```text
min over windows of [ annualized_return_w - k_accept * SE(annualized_return_w) ] >= min_annualized_return
SE(annualized_return_w) = return_volatility_w * P / sqrt(effective_sample_size_w)     # same SE as Decision 2
k_accept ≈ sqrt(2 * ln N_attempts)     # ≈ 2.8 at a 50-attempt budget
```

This is where the multiple-testing correction for a best-of-N search lives; the score
itself (Decision 2) uses the lighter `k_rank = 1`. Same SE, same per-window fields —
only `k` differs. Make `k_accept` an explicit
protocol field (e.g. `gates.score_haircut_se`), not auto-derived from
`max_iterations`, so changing the loop budget does not silently move the bar;
document the `sqrt(2 ln N)` guidance. The drawdown gate now binds because it is
deployment-scaled.
- Replace PSR-only cost stress with money-aware cost-stress gates, such as
`min_cost_stress_annualized_return` and/or `min_cost_stress_return_retention`.
Cost stress should answer "does this still make enough money under worse costs?",
not only "is the tiny stressed book statistically consistent?"
- Add a mandate-capacity verdict. Capacity-bound calibration is not mechanical
failure when the frontier-sized book is feasible, but if `max_feasible_volatility`
or feasible annualized return falls materially below the operator mandate, the run
must be labeled as capacity-bound or fail the mandate-capacity gate. Otherwise the
loop can keep finding tidy tiny sleeves.
- Sample size is now load-bearing for the score, not only validity. The SE haircut
lets the thinnest subwindow drive the score, so set `min_effective_sample_size` and
`min_trades_per_subwindow` so a sparse slice cannot dominate the score through
sampling noise alone.
- Causality is a deployability gate. A survivor whose causality replay did not verify
(`verified: false`, e.g. the micro-replay timing out) is not deployable money and
must not count as a survivor. Raise the replay budget or shrink the probe so
causality verifies, or fail the run.
- `protocol.toml`: add `[mandate]` (Decision 0) and `[risk_budget]`, make
`[objective] kind` protocol-owned, add `[universe] rule`, the money floor and
`k_accept`, and the money-aware cost / capacity gate fields.
- Prune the ~31 dead `experiment.toml` params and drop global `weight`. Smaller
surface = less overfit + easier iteration; the complexity gate becomes meaningful.
- Split docs by ownership. `new-strategy.md` owns the Operator Brief and
pre-lifecycle protocol setup. `program.md` owns active Train iteration after the
protocol is approved. The North Star must say what the loop now optimizes:
deployed annualized return, uncertainty-haircut, subject to robustness and
practicality gates.

### Expected first outcome — state it, do not be surprised by it

Under the deflated money floor, the current three-symbol funding sleeve almost
certainly fails: its weakest subwindow sits only ~0.23 SE above zero (PSR 0.59 →
`Φ⁻¹(0.59) ≈ 0.23`), so any real `k_accept` drives the floor negative. That is the
designed result — the harness returns the verdict *reseed with more breadth and/or
leverage*, not a deployable survivor. A run that ends with no survivor on this
universe is the score working, not breaking.

### Decision 6 — Reproducibility & migration

- Record the **config** `(objective.kind, risk_budget mode + target_volatility,
universe rule + resolved list)` in the thesis lock; record the foundation's
**`PortfolioSizingReport`** (`book_scale`, deployed & `max_feasible_volatility`,
`capacity_bound`, `max_feasible_book_scale`) plus `annualized_return`, stressed
annualized return, return retention, Calmar, Sharpe, and PSR in the run card +
ledger.
- Reproducibility (as landed): a Train run reproduces by re-running the same
`calibrate_vol` config (calibration is deterministic → same `book_scale`);
downstream replays it via `fixed_scale` + the recorded `book_scale`. There is **no
emitted-weights compatibility mode** — old Train artifacts were regenerated against
the shape-plus-risk-budget contract, not replayed.
- Migration should be a hard cutover. Do not carry a compatibility mode that treats
old target magnitudes as final deployable weights. Regenerate configs, fixtures,
artifacts, and docs against shape-plus-risk-budget semantics.

### Testing intent (consumer side)

- Objective correctness: default `return_lcb_subwindow` scores the weakest-window
deployed-return lower bound at `k_rank = 1`; raw `return_subwindow` remains an
undeflated diagnostic; unknown kind rejected; unscoreable window → non-scoreable run.
- Deflated acceptance gate: the money floor uses `k_accept` from `sqrt(2 ln
N_attempts)`; a candidate whose weakest-window deflated lower bound is below the
mandate hurdle fails, even with a positive point-estimate return.
- Guardrail metrics: Calmar/Sharpe/PSR are emitted and can gate/tie-break without
becoming the default objective.
- Cost-stress gates: stressed annualized return and/or return retention bind a
book that is statistically consistent but economically tiny.
- The "strategy scale-search is dead" invariant: global target magnitude does not
change deployed final weights after foundation shape normalization + risk budget.
- Mandate → config wiring: the operator mandate deterministically populates
`[risk_budget]`, `max_abs_drawdown`, the return hurdle, `k_accept`, the universe
threshold, and capacity-mandate verdict thresholds.
- Deterministic, return-blind universe resolution; threshold change moves the list
as expected while ignoring Train performance.
- Reproducibility: a Train `calibrate_vol` run re-runs to the same `book_scale`;
downstream `fixed_scale` replays it. (Foundation-side sizing tests live upstream —
see below.)

---

## Upstream (`quant_strategies`) changes — shipped

Status: **landed 2026-06-16** (`HISTORY.md` "Risk-budget sizing contract";
`FOUNDATION_LOCK.md` "Risk-budget sizing"). It addresses the Decision 3 feedback —
recorded here as the current contract, with the specifics that actually shipped.

### Shape + risk budget

- `TargetDecision.target` is a **standing signed base target shape**, not a final
weight. The foundation **normalizes the shape by maximum intended raw gross
exposure**, applies `[risk_budget]`, and folds the final executable weights into
the one netted NAV book it scores. This closed the scale-search loophole — a
strategy can no longer encode economic size in target magnitudes.
- `[risk_budget]` is **required** on quick-run, validation, and evaluation, with an
explicit `annualization_periods_per_year`:
  - Train quick-run — `mode = "calibrate_vol"` + `target_volatility`: the
  foundation calibrates `book_scale` to hit the target vol, subject to capacity.
  - Validation / evaluation — `mode = "fixed_scale"` + the positive `book_scale`
  recorded by the Train `PortfolioSizingReport`; they **reject** `calibrate_vol`
  and never recalibrate per window, so the Train-deployed size is carried OOS
  unchanged.

### Capacity frontier (the lock refinement, landed)

Capacity-bound calibration sizes the book to the **feasible frontier** and is
**recorded on the sizing report, not a feasibility failure**, when the
frontier-sized book is feasible. Genuine infeasibility still fails closed (unpriced
/ unsupported / missing capacity evidence, a participation-limit breach with no
feasible book, zero-cost / zero-slippage, unfinanced leverage, degenerate sample,
or intended exposure over the risk / leverage budget). This is exactly the
"information, not an error" split Decision 3 asked for.

### `PortfolioSizingReport` (the new evidence)

Carries the shape-normalization scalar, `annualization_periods_per_year`,
`book_scale`, deployed and `max_feasible_volatility`, `capacity_bound`, and
`max_feasible_book_scale`. Exposed on quick-run output and on the evaluation fold
accessor (`FoldScenarioMetrics.sizing_report`). `return_volatility` and the
annualization cadence are now first-class, so the earlier "confirm
`periods_per_year`" question is **resolved**.

### What the consumer (`quant_autoresearch`) still owns

- The objective registry + score (`return_lcb_subwindow` default, optional Calmar /
Sharpe / PSR protocol alternatives, weakest-window `min`, the `k_rank` ranking
haircut and `k_accept` deflated acceptance gate) — the lock's score-policy boundary
is unchanged.
- Capturing the SE inputs the foundation already emits. The per-window payload carries
`mean_return`, `return_volatility`, and `effective_sample_size` (upstream
`ReturnStatistics`), but the consumer parser (`loop.py` → `FoundationMetric`) today
only keeps `sharpe` / `sharpe_standard_error` / `effective_sample_size`. Start
capturing `mean_return` (the deployed-return value) and `return_volatility` (the SE),
and read `P = annualization_periods_per_year` from the `PortfolioSizingReport`. No
upstream change is needed — the data is already there.
- Setting `[risk_budget]` (`calibrate_vol` + `target_volatility` on Train) from the
operator mandate, and recording the `PortfolioSizingReport` in the ledger / lock.
- Money-aware gates for annualized return, stressed annualized return or return
retention, and mandate-capacity fit.

### Differences from the original proposal

The intent landed intact (foundation owns sizing; capacity-bound is information;
strategy emits shape), but naming and mechanics shifted: modes are `calibrate_vol`
/ `fixed_scale`, not `vol_target` / `as_emitted`; scale comes from **max-gross
shape normalization + risk budget**, not a raw `book_scale` multiplier on
`signed_weight`; `[risk_budget]` is **required**, not opt-in; and there is **no
emitted-weights replay mode** — Train artifacts were regenerated rather than
replayed.
