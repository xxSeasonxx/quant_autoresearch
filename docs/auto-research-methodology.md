# Auto-Research Methodology

**Status:** brainstorm output for Season's review — not yet implemented.
**Scope:** how `quant_autoresearch` should iterate strategy candidates so the loop
converges on **real, out-of-sample, risk-adjusted profit** instead of overfit.
**Companion:** requirements are in [PRD.md](./PRD.md); the rebuild phasing is in [refactor-phase-plan.md](./refactor-phase-plan.md).

---

## TL;DR

1. **Karpathy's `autoresearch` loop is the right *shape* and the wrong *signal* for quant.**
  `val_bpb` on a held-out shard is a *low-bias, high-signal* estimate of generalization — forgiving, not immune — so
   "optimize one number, keep/discard, loop ~100×" climbs a largely real gradient. A backtest
   score is a *biased* estimate of the future, and the bias **grows with the number of
   attempts**. Port the loop naively and "loop forever optimizing the number" converges
   on the *most overfit* strategy — whose edge collapses out-of-sample, and turns *negative*
   when returns have memory (Bailey–Borwein–López de Prado–Zhu, 2014).
2. **Our current loop is, structurally, an overfitting machine.** It optimizes an
  in-sample, leverage-inflated, zero-cost, single-regime number with an unlimited trial
   budget. The 100-attempt campaign did exactly what it was built to do; the result
   (ADA-only, short-only, six excluded clock-hours, sizing cranked to 0.20) is a textbook
   overfit. See [Diagnosis](#diagnosis-the-current-loop).
3. **Trials are bounded by history, not compute.** Minimum Backtest Length ties the number
  of honest trials to how much history an asset has — tens for short-history assets like
   crypto, more for long-history ones like equities and FX. The budget is a hard cap set by
   the data, not a number you can buy back with compute.
4. **The fix is to change *what* is optimized and *how data is spent*, then let either
  trigger policy sit on top.** The two common iteration patterns differ only in *when* you
   escalate and *how* you batch; both share the latent bug of treating the in-sample
   number as the target. The redesign:
  - **Honest objective** — a clean, cost-aware, risk-adjusted, out-of-sample score (the
  *Robust Edge Score*), leverage/sizing removed. The per-row score is *not* deflated; selection
  bias is handled in three layers — a global trial budget (prevention), a returns-based audit
  (correction), and a power-aware one-shot lockbox (confirmation).
  - **Hard-walled data tiers** — Train (optimize freely) → Selection (out-of-sample screen, agent sees
  only a summary score) → Lockbox (one-shot, human-gated, never iterated against).
  - **An evidence ladder** with cheap→expensive gates that reconciles both common iteration patterns.
  - **A trial budget** treated as a first-class, ledgered resource.
  - **Rigor in the immutable harness, simplicity in `program.md`** — the agent stays a
  one-page loop; the evaluator stays honest.

---

## The core insight: why the analogy breaks

Karpathy's loop is *forgiving* — not because backtests and `val_bpb` obey different laws,
but because they sit at opposite ends of the *same* one. Selecting repeatedly against any
reused holdout leaks information into it: the Kaggle public-vs-private leaderboard gap is
exactly this effect, and the reusable-holdout literature exists to bound it. `val_bpb`
survives it *in practice* for three reasons — the target is dense and the effective sample
per eval is enormous, so the estimate's variance is tiny next to real effect sizes;
improvements that lower val loss (optimizer, architecture) tend to be *causal and
transferable*, not shard-specific; and the overnight loop spends only ~100 trials. Push any
of those the wrong way — sparse signal, few samples, idiosyncratic gains, thousands of
trials — and ML validation overfits too.

A backtest score pushes *all* of them the wrong way at once:

- **It is biased, and the bias compounds with search.** The *False Strategy Theorem*
(Bailey & López de Prado, 2014): the maximum Sharpe among `N` strategies with *true*
Sharpe of zero is right-unbounded in `N`. Try enough configs and *some* config posts a
great backtest by luck alone. "Loop forever" maximizes exactly this luck.
- **Financial data is one path, serially correlated, regime-dependent.** "More windows"
drawn from the same regime are not independent samples; surviving them is not evidence
of generalization.
- **The optimizer and the evaluator share data.** Once you tune against a window, that
window is in-sample, no matter what you call it.

**"Make money" decomposed.** Expected live profit ≈ `P(the edge is real) × magnitude of the edge`, net of costs and capacity. The whole job of the backtest is to estimate both
factors *honestly*:

- `P(edge is real)` collapses as you try more configs against the same data → must be
**protected by limiting trials and confirming out-of-sample**, not rescued by a score haircut.
- `magnitude` is *risk-adjusted compounded* return, not raw return → maximizing long-run
wealth means maximizing expected log-growth, which penalizes variance and drawdown
(this is why Sharpe/Sortino/Calmar, not net return, is the honest magnitude).
- raw leverage scales magnitude but not `P(real)` and not Sharpe → it must be a
*downstream sizing decision*, never a search reward.

So the objective writes itself: **a clean, risk-adjusted, cost-aware, out-of-sample score
with sizing factored out** — and selection bias handled by the data wall and a trial
budget, not by deflating the number. Everything below is the machinery to compute that
score honestly and to stop the agent from gaming it.

---

## Diagnosis: the current loop

The loop has Karpathy's discipline (immutable harness, one editable surface, keep/discard,
never-early-stop, a robustness screen) but four domain-fatal flaws. Each is visible in
`results.tsv`, `idea.md`, and `experiment.toml`.


| Flaw                                   | Evidence                                                                                                                                                                             | Consequence                                                                                                 |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| **Metric rewards leverage, not skill** | `scoring.py:_window_normalized_score = raw_net_return / window_days`. Scores scaled *exactly proportionally* with `base_position_pct` (0.12→0.000336, 0.16→0.000448, 0.20→0.000561). | The biggest "gains" were just more exposure.                                                                |
| **Metric rewards data-snooping**       | Promoted config excludes decision hours `[1,2,3,4,14,20]`; no economic thesis.                                                                                                       | Calendar curve-fitting promoted because the number rose.                                                    |
| **Metric rewards concentration**       | Universe collapsed to ADA 0.95 / XRP 0.025 / AVAX 0.025; `idea.md` admits it "disguises an ADA-only bet."                                                                            | A single-asset directional bet dressed as a basket.                                                         |
| **"Robustness" is single-regime**      | `experiment.toml` windows are all 2025-01 → 2026-04, contiguous, no embargo, no true holdout. Primary `cost_model` is `0/0` bps.                                                     | Surviving H1/H2/recent ≠ surviving a regime change; zero-cost primary rewards turnover.                     |
| **No tax on the search**               | 100 attempts vs one target; no deflation, no trial ledger.                                                                                                                           | Per MinBTL, the expected-max *noise* Sharpe on 16 months ≫ 1; the 50× climb is consistent with pure mining. |


And the decisive lesson: `program.md` **explicitly told** the agent not to cherry-pick
windows and not to chase the number — and it did both anyway. **Rigor that lives in prose
gets ignored. Rigor has to live in the harness the agent cannot edit.**

---

## Design principles

Six hard truths, each producing a non-negotiable design rule.

1. **A backtest is a biased estimator; bias grows with trials.**
  → Three complementary defenses, not substitutes: *cap* trials with a small global budget
   (MinBTL-bounded) — prevention; *correct* the surviving selection with an audit over the
   logged trial returns (Romano-Wolf / PBO) — correction; *confirm* once on a one-shot wall —
   confirmation. A budget bounds the bias; it does not remove it.
2. **You must be judged on what you did not optimize.**
  → A hard data wall: optimize on Train, *select* on out-of-sample folds the agent sees only
   in summary, *confirm* once on a Lockbox that can never be iterated against.
3. **Leverage and *factor* beta are not alpha.**
  → Search a *scale-free* edge at fixed normalized exposure, scored as **residual alpha** after
   a factor panel (market/benchmark, momentum, funding-carry, size) — not just benchmark-relative;
   decide sizing (fractional Kelly) downstream, never inside the loop.
4. **Costs and capacity are part of the edge.**
  → Realistic costs in the *primary* objective, not a late stress; turnover, concentration,
   and breadth gated.
5. **LLM searchers get "cagy" and nudge parameters** (observed first-hand in the diagnosed campaign).
  → The harness does not count naked parameter sweeps as candidates, requires a falsifiable
   causal thesis to spend a trial, and schedules forced "swing-big" exploration.
6. **An asset only earns the conclusions its data can support.**
  → The method is asset-agnostic but *data-driven*: profile each asset's usable history,
   cross-section breadth/correlation, effective regime count, and autocorrelation, then
   *derive* the trial budget, the Lockbox mode (forward block vs. bootstrap), and the
   significance bar from that profile. When the data cannot support a powered confirmation,
   the harness returns **insufficient evidence** — never a graduation.

---

## The objective: Robust Edge Score (RES)

One number, "higher is better" (Karpathy's clarity) — but an *honest* number that cannot
be gamed by leverage, concentration, turnover, or trying more configs.

RES is computed on the **out-of-sample Selection paths** (see [Data tiers](#data-tiers)) at
a **fixed normalized exposure**, in two stages. (Candidates here have already passed the
Tier-0 causal diagnostic — contract + hidden-lookahead replay — so RES never runs on a
causally-invalid strategy.)

### Stage 1 — Feasibility gates (hard, binary; fail any ⇒ RES = infeasible)

- **Evidence sufficiency (PSR)** — the Probabilistic Sharpe Ratio clears the confidence
level (e.g. 95%): enough trades *given this candidate's own Sharpe, skew, and kurtosis*. A
crude minimum trade count is a fast proxy on `run`; PSR is the gate at `evaluate`.
- **Max drawdown ≤ ceiling** — survival; risk-adjusted ratios alone understate crash and
tail risk.
- **Worst-fold floor and dispersion ceiling** — the edge holds in the weakest regime/fold and is not carried by a single window.
- **Cost-stress ratio ≥ threshold** — the edge survives realistic *and* stressed costs.
- **Concentration ≤ ceiling and breadth ≥ floor** — no single symbol dominates PnL, and the
edge is confirmed on held-out symbols.

### Stage 2 — Score (continuous; only for feasible candidates)

The score is a **clean out-of-sample risk-adjusted magnitude**, computed at fixed exposure.
Three specifics make it score *skill*, not exposure or luck:

- **Rank on Sharpe** (Sortino / Calmar / maxDD become Stage-1 gates, not the ranking number).
Sharpe is the one statistic with a usable sampling distribution (PSR/DSR), so ranking on what
we can deflate keeps the score and the audit measuring the same thing.
- **Score residual alpha, not raw return.** Where tradeable factors exist, regress the OOS
returns on a factor panel (market/benchmark, cross-sectional momentum, **funding-carry**,
size…) and score the *residual* (information ratio). Market beta **and** factor beta are not
edge. In crypto, **funding is carry** — a path-dependent factor/cost, never additive alpha
(the diagnosed short-only bet was largely funding collection).
- **The evidence unit is the per-fold Sharpe set**, not one pooled track: it feeds the
worst-fold / dispersion gates and the audit's cross-trial variance directly. A pooled,
trade-weighted track is a descriptive headline only.

That is the number the agent ranks on; per row it is **not** deflated — selection bias is
handled outside the row (below), so each row stays stable and reproducible.

**Selection bias is handled outside the score, in three complementary layers** — each
addresses a different leak, none substitutes for another:

- **Prevention — a global trial budget** (MinBTL-derived; see [Search budget](#search-budget--the-multiple-testing-ledger)).
Bounds how many Selection looks the whole campaign may take, so the best-of-N inflation stays
small. It bounds the bias; it does not remove it.
- **Correction — an audit over the *logged trial returns***. At graduation, run a
**Romano-Wolf stepdown / PBO** over the recorded OOS return series of *all* competing trials,
not just the K finalists. Operating on the actual returns, it absorbs the correlation among
trials directly — no `N_effective` to guess, no Sharpe-only `N=K` shortcut. (This replaces the
earlier "batch DSR with `N=K`", which under-counted the search and mis-estimated the
cross-trial variance.)
- **Confirmation — a power-aware Lockbox**. Re-evaluate survivors once on fresh data they never
touched. The Lockbox **reports its own power**: if its minimum detectable effect exceeds the
candidate's claimed edge, it returns **insufficient evidence**, never "confirmed." Where the
forward block is too thin for power (short histories), a stationary/block-bootstrap CI on the
OOS distribution is the binding test and the forward block is a sanity check.

**Decision rule:**

- A candidate **graduates to the Lockbox** if it clears the gates, ranks top-K by OOS Sharpe
(PSR-gated), and survives the trial-population audit.
- The **graduation verdict** is the Lockbox result *with its power stated*: confirmed,
rejected, or insufficient-evidence. *Magnitude answers "how much?"; the audit + powered Lockbox
answer "is it real?"*

### Sizing is decoupled (this is where "as profitable as possible" lives)

The search optimizes a scale-free edge; it never sees leverage. Once an edge is *real*
(passed Lockbox), size it by **fractional Kelly** on its out-of-sample return
distribution, capped by drawdown tolerance. Leverage applied to a *real* edge makes
money; leverage baked into the search just inflates noise. `base_position_pct` is
**frozen** during search.

> **Why keep the per-row score clean (undeflated)?** Because deflation belongs at the
> *decision*, not on every row. The row is a stable, reproducible property of one candidate;
> the selection bias lives in the *max over rows*, and that is corrected once — at graduation,
> by the audit over the logged trial returns — prevented by the global budget, and confirmed on
> the wall. Prevention, correction, and confirmation are *complementary*, not substitutes.
> Effective-N is not wished away: it is estimated transparently where it belongs (sizing the
> budget, and implicitly in the returns-based audit), never as a fragile `N=K` shortcut.

---

## Data tiers

Every candidate is developed, selected, and confirmed on three disjoint partitions, fixed
in `protocol.toml` and never edited by the agent. Each partition is separated by a **purge**
gap sized to the holding/label horizon (so no position straddles a boundary), plus a small
**embargo** buffer on the training block that *follows* a test window (per AFML: embargo ≈ a
small fraction of the sample, and it matters mainly under combinatorial folds).


| Tier          | Data                                           | Who optimizes            | What the agent sees                                               | Trial cost          |
| ------------- | ---------------------------------------------- | ------------------------ | ----------------------------------------------------------------- | ------------------- |
| **Train**     | rolling or anchored train window               | agent, freely & fast     | everything: causal + contract diagnostics, trade metrics          | none                |
| **Selection** | rolling walk-forward folds + embargo           | nobody tunes; it *ranks* | only the RES summary (scalar + pass/fail), never per-trade detail | **1 trial** per run |
| **Lockbox**   | most-recent forward block (+ held-out symbols) | nobody                   | one-shot result, human-gated                                      | burns a graduation  |


**Walk-forward, forward-only.** Selection is a rolling walk-forward: train on a window,
score the next (later) window, roll forward; the concatenated out-of-sample folds are the
evidence. Every test window sits after its training data. Rolling (fixed-length recent
train) is the default; anchored (expanding train from a fixed start) suits slow,
long-horizon strategies. The most-recent block is reserved, untouched, as the Lockbox.

**Two robustness axes.** A candidate must hold across **time and regime** — folds spanning
trending, range-bound, and high-volatility periods — and across the **cross-section** —
confirmation on held-out symbols it was not developed on. Cross-sectional confirmation is
decisive where the cross-section is broad and lightly correlated (equities) and weaker where
it is thin and co-moving (FX majors, crypto against BTC), which lean correspondingly more on
time and regime folds.

**Window profile.** Windows are set per asset in `protocol.toml` and calibrated against
baseline runs; the PSR gate enforces evidence sufficiency. Windows are frozen for a campaign
and re-cut forward between campaigns.

**Data sufficiency is a gate, and the Lockbox is consumed per dataset.** The method is
asset-agnostic but data-driven (Design principle 6): the harness profiles usable history,
effective regimes, and cross-section correlation per asset, *derives* the budget, Lockbox mode,
and significance bar — and refuses a graduation when the data can't support a powered
confirmation. The Lockbox is **write-once per *dataset*, not per candidate**: once any candidate
is scored on a Lockbox block, that block is spent for the whole campaign and a new Lockbox needs
fresh forward time. (This closes the leak where a reused forward block silently becomes a second
Selection set across graduation batches.)


|                                      | Crypto perp (hourly) | Equities (daily) | FX (daily)    |
| ------------------------------------ | -------------------- | ---------------- | ------------- |
| `run` train window                   | ~4–6 mo              | ~2–3 yr          | ~2–3 yr       |
| `evaluate` fold (train / test, ≈3:1) | 6mo / 2mo            | 2yr / 8mo        | 2yr / 8mo     |
| folds (≥3 regimes)                   | ~6–8                 | ~8–12            | ~8–12         |
| Lockbox (forward)                    | ~2–3 mo              | ~1–2 yr          | ~1–2 yr       |
| minimum history                      | ~1.5–2 yr            | ~8–10 yr         | ~8–10 yr      |
| primary robustness axis              | time / regime        | cross-section    | time / regime |


---

## The evidence ladder

Cheap → expensive gates that escalate *evidence strength*, not authority. Vocabulary:
`feedback → graduate → lockbox → human promotion`. "Promotion" is reserved for the human
authority step above the lockbox (per the foundation contract); the loop only ever
*graduates* a candidate up the ladder. Both common iteration patterns reduce to this structure; they differ only in the Tier-1→Tier-2 batching cadence.

The ladder also separates three questions the old loop blurred into one number:

- **Is it causally valid?** — the Tier-0 quick-run diagnostic (decision contract +
hidden-lookahead replay). A failure here *disqualifies* a strategy; it never enters the
ladder, however good its backtest looks.
- **Is it a real, robust edge?** — Selection's out-of-sample gates and risk-adjusted score.
- **Did we fool ourselves by searching?** — the trial budget + graduation batch audit.

Causal integrity is a *precondition*, not a score. The quick run owns it.

- **Tier 0 — Quick run (Train): the causal diagnostic.** `quant-strategies run` is first an
*integrity* check, not a score — it validates the decision contract and **replays for hidden
lookahead** (strict point-in-time causality), then emits trade-level `economic_metrics`
(`replayability` / `row-contract` / `causality` / `warnings` in `result.evidence`). A
strategy that fails causal replay or the contract is **not a candidate**: it never reaches
Selection, however good its number. Runs on every idea in seconds at no trial cost; the
feedback score is a byproduct. The fast Karpathy cadence.
- **Tier 1 — Out-of-sample selection screen (Selection).** Triggered when Tier-0 clears a
plausibility bar **and** the idea carries a *new falsifiable thesis* (not a param nudge).
Computes the RES (clean OOS risk-adjusted score) over the walk-forward folds plus held-out
symbols; **costs one trial**; appends to the trial ledger. Built on `quant-strategies evaluate`, with fold orchestration in `quant_autoresearch`.
- **Tier 2 — Lockbox confirmation (Lockbox).** Batched over the top-K Tier-1 survivors,
human-gated, one-shot. Batching makes the multiple-testing audit clean — the batch DSR uses
`N = K` — and rations the precious Lockbox.

**Reconciling the two iteration patterns:**

- *Workflow 1 (score-gated escalation)* = per-candidate triggers up the ladder.
- *Workflow 2 (continuous quick-runs, periodic multi-window, top-K evaluation)* = the
batched variant.
- **Recommendation: a hybrid** — continuous Tier-0; escalate-on-thesis to Tier-1; batch
the top-K to Tier-2 on a periodic cadence. You get Workflow 2's statistical cleanliness
(the batch audit uses `N = K`) and Workflow 1's responsiveness, from one architecture.

---

## When to escalate: satisfice on Train, select on Selection

The most under-specified decision in the ladder is the Tier-0 → Tier-1 trigger — what
"promising" means. The answer follows from the *epistemic status* of each tier's number,
not from its magnitude.

|                      | Train (quick run)             | Selection (evaluate)                       |
| -------------------- | ----------------------------- | ------------------------------------------ |
| Estimator of edge    | **biased high** (in-sample)   | ~**unbiased** (OOS folds)                  |
| Cost to look         | free, unlimited               | scarce (budget) **and** leaky (reused holdout) |
| Honest use           | *plausibility* — real-shaped? | *rank* — how real is it?                    |

The Train number is the very thing an unlimited free optimizer overfits, so its magnitude
above a floor is mostly overfit, not edge. The rule that falls out:

> **Satisfice on Train. Maximize on Selection. Confirm on Lockbox.** Never hill-climb a
> biased free signal; never hill-climb a leaky holdout.

### "Promising" is a gate, not a high number

Escalate to Tier-1 iff a candidate clears **all** of (binary):

1. **Valid** — passes causal replay + decision contract (Tier-0's core job).
2. **Alive** — enough trades to measure; not a degenerate single-symbol / single-hour
  artifact; sizing frozen.
3. **In-sample-positive after real costs** — a *low* floor ("the edge exists in-sample"),
  not a high one.
4. **New thesis** — a structurally new falsifiable hypothesis, not a param-neighbor of a
  logged trial.
5. **Cheap-robust** — the in-sample edge isn't carried by one symbol / window / hour (free
  from the engine's `by_symbol` / `by_month` / `by_hour` slices).
6. **On a robust plateau** — not a knife-edge: the harness perturbs the params on Train and
  requires the in-sample metric to stay flat-and-positive (the **stability gate**, computed —
  enforcement #10). Rewards *flatness, not height*, so it cannot be gamed by climbing the score.

A **negative or flat Train result ⇒ don't escalate**: Train is optimistically biased, so
expected OOS is ≤ that and the trial is −EV. And above the floor, **do not rank escalation
candidates by Train magnitude** — rank by thesis conviction, novelty, and cheap robustness.
Preferring the higher Train score actively selects for overfit.

### The gate is a filter; the throttle is thesis + budget

As the agent improves, garbage disappears and the gate stops filtering — *by design*.
Escalation does **not** collapse to "evaluate every run," because passing the gate does not
*entitle* a trial. A trial requires a genuinely new thesis **and** remaining budget —
neither weakens as the agent improves.

- **thesis-free nudge** → Train only, free, unlimited; never evaluates (the naked-sweep
  detector's job).
- **thesis-justified change** → may spend **one** trial; counts against budget.
- **budget** (MinBTL-derived) caps total OOS questions, including a few refinement variants.

**Throttle hierarchy:** filter = gate (garbage) → throttle = thesis (a real new question) →
hard cap = budget → confirm = lockbox.

### Where the score improves — and the one place it must not

1. ✅ **On Train, toward a robust plateau** — refine freely, but target stability across
  params/symbols/windows and economic soundness, **not** the peak number. A plateau
  generalizes; a sharp peak is overfit. Unlimited, but it is *development*, not *evidence*.
2. ✅ **Across the ledger** — the best-of-K OOS score rises as *theses* get better (informed
  by what survived OOS before). This is the real improvement curve.
3. ❌ **Grinding one idea's OOS score by re-evaluating tweaks** — the overfitting machine;
  the budget exists to forbid it (False Strategy Theorem: re-question one holdout enough and
  the rising number is guaranteed to be luck).

The reason is structural: **parameter tuning has no free lunch.** Tune on Train → in-sample
overfit; tune by re-evaluating on Selection → holdout overfit. No tier makes "push the number
up" trustworthy, so the loop sources improvement from better hypotheses + robust-plateau
development, and caps OOS questions with the budget.

Consequently **keep/discard differs by tier**: on Train, iterate and discard freely (free,
in-sample); on Selection, do **not** "keep if the score rose" — each eval is a logged bet,
and graduation is top-K over the ledger. *(The shipped `program.md` and Appendix A both reflect
this; the agent contract no longer hill-climbs — the harness enforces it mechanically.)*

### The loop

Per idea:

1. Write one falsifiable causal thesis (effect, observable, falsifier).
2. Edit `strategy.py` / `[params]`.
3. `run` on **Train** (free) — causal check + a coarse plausibility band.
4. Refine on **Train** toward a robust plateau (free; development, not evidence).
5. Apply the **escalation gate** — refinements / nudges fail "new thesis" and stay on Train.
6. `evaluate` on **Selection** (spends 1 trial; harness enforces gate + budget).
7. **Log the bet** (config, thesis, full OOS return series, RES) — *not* "keep if score rose."
8. Move to a **distinct** thesis; every M ideas, swing big.

When a family's budget is spent:

9. Graduate **top-K** by OOS rank (gates + PSR) to the Lockbox.
10. **Lockbox** is one-shot, human-gated, batch-audited — then retire the family.

---

## Search budget & the multiple-testing ledger

Trials are the scarce resource, so make them first-class.

- **Trial register** (harness-owned, append-only): every Tier-1 run records the strategy
family, the config, the **full OOS return series**, and the thesis. You cannot compute
DSR/FDR without the returns of *every* trial — recording them is mandatory, not optional.
- **A global, hard budget — prevention, not the whole story.** The multiple-testing unit is
each query against Selection data; every Tier-1 touch spends one from a small, MinBTL-derived
budget that is **global to the campaign**, not reset per family. (Family is a harness-computed
fingerprint of the signal structure — see enforcement #7 — so relabeling a thesis cannot mint
fresh budget.) Train iterations are free. Capping trials *bounds* the selection bias; it does
not *remove* it.
- **Sizing the budget (MinBTL), on the *effective* sample.** The cap is derived from
*effective* history (discounting serial correlation) and *effective* independent trials
(clustering correlated configs) — MinBTL's `N` is effective-N. On short, autocorrelated,
single-regime histories the honest cap is small (single digits, not "tens"); the harness
computes it per asset and treats it as an upper bound. This is where effective-N is estimated,
transparently.
- **Correction — audit over the logged returns.** At graduation, a **Romano-Wolf stepdown /
PBO** over the recorded OOS return series of *all* trials (the register makes this possible)
removes the residual selection bias. Operating on the returns, it is correlation-robust — no
`N=K` shortcut, no separate `N_effective` guess. Benjamini–Hochberg–Yekutieli over the
graduated candidates' p-values is the simpler fallback (Harvey–Liu 2015: the haircut is
non-linear — strong edges barely penalized, marginal ones heavily).

---

## Anti-overfit enforcement (in the harness, not prose)

1. **Sizing frozen** during search (`base_position_pct` fixed) — leverage can't score.
2. **Realistic costs in the primary** objective — turnover can't hide.
3. **Concentration & breadth gates + cross-asset holdout** — single-asset bets fail.
4. **Every Selection query counts; Train is the free sandbox.** Sensitivity sweeps belong
  on Train, where looking is genuinely free. *Any* touch of Selection data is logged and
   spends budget — there is no "probe" loophole, because a result the agent can see has
   already conditioned the search. Every Selection touch spends from the budget; the budget
   is the cap and the lockbox is the check. The naked-sweep detector's job is to push nudges
   back to Train (free) and keep thesis-free tweaks off Selection — not to grant
   free looks.
5. **Thesis + falsifier required** to spend a Tier-1 trial — structured, logged, checked.
6. **Lockbox is write-once per *dataset*** — once any candidate is scored on a Lockbox block it
  is spent for the whole campaign; a new Lockbox needs fresh forward time. (Per-candidate
  write-once leaks: a reused block becomes a second Selection set across batches.)
7. **The trial budget is a global, hard cap, keyed to a computed family id** — the budget is
  global to the campaign, not reset per family; "family" is a harness-computed fingerprint of
  the signal structure (not the agent's free-text thesis), so relabeling cannot mint budget.
  The harness stops issuing evaluations when the cap is spent; the agent is never handed a
  countdown, and the session ends only when the harness says so.
8. **Forced exploration cadence** — every M iterations the agent must propose a
  structurally new signal family, to break the cagy local-optima loop.
9. **The measurement config is read-only — by mechanism, not request.** `protocol.toml` (costs,
  fill, tiers, objective metric, gates, thresholds, budget, annualization) is loaded from
  outside the agent's writable surface, content-hashed, and the run **fails closed** on any
  drift; its hash is recorded in every ledger row. The config-derivation layer lets `params`
  populate only strategy `[params]` — it can **never** override cost/fill/tiers, so
  `cost_model = 0/0` cannot be resurrected through a param key.
10. **Stability gate (robust plateau, computed — not LLM-judged).** Before a candidate may
  `evaluate`, the harness perturbs each tunable param ±1/±2 natural steps on Train (free,
  one-at-a-time; steps live in `protocol.toml`, not agent-set) and requires the in-sample
  metric to stay **flat-and-positive**: worst neighbour ≥ ρ·center (ρ≈0.6) **and** ≥80% of
  neighbours positive after costs. Stability score `S = min_N m(θ)/m(θ*)`. A knife-edge fit
  (low/negative `S`) is routed back to Train. It rewards *flatness, not height*, so it cannot
  be gamed by climbing the score. The agent only proposes θ* and which params matter; the
  harness measures. (In-sample pre-filter only — Selection/Lockbox still confirm.)

---

## The simplicity contract

Karpathy's real genius: `program.md` is a one-page "skill," and the *immutable evaluator*
enforces everything that matters. We keep that split. All the statistics (DSR, CPCV,
purge/embargo, FDR, sizing decoupling, gates) live in the harness the agent cannot edit.
The agent's instructions stay a short loop:

> Read the candidate. Form one falsifiable, causal thesis. `run` it on Train. If it clears the
> gate, `evaluate` it — that spends one trial. Log the bet; don't hill-climb the score. Never
> touch the Lockbox. Every M ideas, swing big.

A draft of the rewritten `program.md` is in [Appendix A](#appendix-a-draft-programmd).

---

## Config surfaces: split by ownership

The agent edits the *hypothesis*, never the *judgment*:

- `**experiment.toml` — agent-editable.** `strategy_path` + `[params]` (plus a bounded
discovery symbol set, if universe choice is allowed). The same params feed both the quick
run and the evaluation, so there is only ever one editable param set — not a run set and an
eval set.
- `**protocol.toml` — harness-owned, read-only** (in the agent's do-not-touch list beside
`scoring.py`). Everything that defines how a candidate is measured and judged: the data
tiers (Train/Selection/Lockbox), `cost_model`, `fill_model`, CPCV/regime config, the
objective metric + gates + thresholds, the trial budget, annualization/backend. Quick-run
and evaluation settings live here *together* — they share tiers, symbols, and costs, so one
source of truth keeps the feedback number and the ranking number measuring the same world
(no `cost_model = 0/0` in one place and `0.5` in another).

The `quant_autoresearch` runner *derives* the foundation's per-surface calls (`run_config`
for the quick run, `run_evaluation` for Selection/Lockbox) from `protocol.toml` + `params`;
the agent never hand-writes the foundation's run/validate/evaluate TOMLs. Net editable
surface: `strategy.py` + the params in `experiment.toml` — Karpathy-minimal. The wall is
**mechanical, not advisory**: `protocol.toml` lives outside the agent's writable surface and
is content-hashed (fail-closed on drift), and the derivation layer treats cost/fill/tiers as
protocol-only — `params` cannot override them (enforcement #9).

---

## How this maps onto the two repos

The ownership boundary already declared in `quant_strategies` is exactly right and we keep
it:

- `**quant_strategies` (foundation, stateless evidence):** owns the honest per-fold numbers.
`evaluate` already computes NAV-based `sharpe`, `sortino`, `calmar`, `max_drawdown`,
`trade_count`, `profit_factor`, `worst_period_return` with proper annualization-cadence guards.
**Two additions are in scope:** a **typed per-fold return-series accessor** on the result
(today `EvaluationRunResult` returns dir + status only, and the OOS returns the audit needs
live in `portfolio_path.parquet`), and **one `evaluate` call per fold** (today multi-window
`evaluate` pools windows into one path with no embargo). PSR/DSR do **not** belong here —
significance is the loop's job.
- `**quant_autoresearch` (the search loop):** owns candidate generation, the out-of-sample
selection orchestration (CPCV / cross-asset / regime), path stitching, the trial register and
global budget, the graduation audit (Romano-Wolf / PBO over the logged trial returns), PSR/DSR,
ranking, and stopping rules — i.e., everything the foundation README explicitly says lives
"outside this repo."

The boundary holds; the foundation exposes the summary scalars today and gains a typed
return-series accessor so the loop never scrapes Parquet across the repo line.

---

## Implementation phasing

The rebuild phase plan — greenfield core in this repo, legacy judgment modules retired —
lives in **[refactor-phase-plan.md](./refactor-phase-plan.md)**, executed one OpenSpec
change at a time via `/feature-workflow`. Requirements are in **[PRD.md](./PRD.md)**.

---

## Appendix A — the agent contract

The one-page agent loop is the shipped **[`program.md`](../program.md)** (canonical). It is
enforced **mechanically** by the `harness/` package — the escalation gate, the global budget,
the stability check, naked-sweep routing, and the swing-big cadence all live in the harness the
agent cannot edit, exactly as this methodology argues ("rigor in the harness, simplicity in the
contract").

The earlier *draft* of this appendix — which still used the pre-rebuild `runner.py
--explore/--promote` commands and a per-family budget, and predated the `run`/`evaluate`/`status`
CLI — has been superseded by the shipped `program.md` and lives in git history.

---

## References

- Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J. (2014). *Pseudo-Mathematics
and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample
Performance.* Notices of the AMS. — MinBTL; overfitting collapses OOS edge (negative only under serial dependence).
[SSRN 2308659](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659) ·
[PDF](https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf)
- Bailey, D. H., & López de Prado, M. (2014). *The Deflated Sharpe Ratio: Correcting for
Selection Bias, Backtest Overfitting and Non-Normality.* J. Portfolio Management. — DSR/PSR;
False Strategy Theorem.
[SSRN 2460551](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) ·
[PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) ·
[Wikipedia](https://en.wikipedia.org/wiki/Deflated_sharpe_ratio)
- Bailey, D. H., & López de Prado, M. *The Probability of Backtest Overfitting* (CSCV/PBO).
[PDF](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- Harvey, C. R., & Liu, Y. (2015). *Backtesting.* J. Portfolio Management. — haircut Sharpe;
Bonferroni/Holm/BHY multiple-testing.
[PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF)
- Harvey, C. R., Liu, Y., & Zhu, H. (2016). *…and the Cross-Section of Expected Returns.* RFS.
[PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF)
- López de Prado, M. (2018). *Advances in Financial Machine Learning*, ch. 7 (purged/embargoed
CV) & ch. 12 (CPCV). [Purged CV — Wikipedia](https://en.wikipedia.org/wiki/Purged_cross-validation)
- Karpathy, A. (2026). *autoresearch.* [github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch)
— the loop shape, the three-file contract, "one GPU, one file, one metric."

