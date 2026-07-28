# Harness & Engine Constraint Review — is the loop killing profitable opportunities?

**Status:** point-in-time review, 2026-07-27. Evidence record and recommendation set, **not** an
active contract. Owning contracts stay in `program.md`, `protocol.toml`, `docs/score_research.md`,
and the module docstrings.

**Question reviewed (Season's):** research feels restricted along two axes — (i) engine setup
(capacity model, `risk_budget`), and (ii) the harness itself (gates, the thesis lock, needing to
edit the lock to keep iterating). Is that correct, and can it be simplified — or is the current
design right?

**Method:** source, frozen configs, and the 271-attempt ledger record across 7 offloaded theses are
primary evidence. Docs are claims audited against code. Upstream `quant_strategies` behavior is
taken from the consumer contract, not re-verified against upstream source.

**Lens disclosure:** the skill's four perspective lenses (onboarding, architecture, senior
engineering, adversarial) plus a quant-research lens were run **inline by the main reviewer, not as
fresh-context subagents**, per Season's standing instruction not to spawn agents unless asked. The
cost is less independence than parallel lenses would give; findings below are therefore backed by
ledger arithmetic rather than by cross-agent agreement.

**Location note:** placed alongside `docs/HARNESS_AND_DOCS_REVIEW.md` to keep review artifacts in
one directory rather than in a new `docs/reviews/` subfolder.

---

## 1. Executive verdict

**Season is right that research is being constrained — and wrong about where.** The restriction is
not the *volume* of rules. It is that **three or four numbers with enormous leverage over the result
were set by convention and never validated**, while the *visible* apparatus that feels restrictive
(nine gates, the lock, `program.md`'s prose) is largely inert and largely correct.

Three measured facts carry the verdict:

1. **The nine-gate apparatus is one gate wearing nine hats.** Across the 190 current-schema
  attempts, **every single-gate failure was `train_strength` — 83 of 83.** `breadth`,
   `complexity_cap`, `effective_symbol_count`, and `causality` never failed once; `path_risk` failed
   once, ever.
2. **That one binding gate's stringency was never chosen — it fell out of the Train window
  length.** `train_strength` (R − 2·SE ≥ 0) is algebraically identical to *in-sample annualized
   Sharpe ≥ 2/√Y*. Verified exactly against the ledger. So the real hurdle was **0.91** on the
   4.83-year thesis and **2.19** on the 0.84-year thesis. Nobody decided to demand Sharpe 2.19.
3. **Half of all attempts could not deploy the risk they were scored on.** `target_reached = false`
  in **95 of 190** attempts; deployed/max-feasible volatility sat pinned at **1.000 (median)** in
   four of six theses. One thesis ran at **0.010 vol against a 0.15 target** — a 15× shortfall.
   **But it also failed the scale-invariant strength gate in 29 of 30 scoreable attempts**, so
   capacity did not mask a proven edge there (§5.4).

So the honest answer splits:

- **On (i), engine setup: Season is right that there is a real problem, but it is a measurement gap,
not a demonstrated loss.** Nothing in this record shows the capacity model discarded a profitable
strategy — the clearest candidate for that claim failed a scale-free strength test as well. What is
established: `impact_coefficient_bps = 10.0`, `impact_exponent = 0.5`,
`max_average_bar_participation = 0.25`, `max_bar_participation = 0.50` are round-number defaults with no
calibration record; costs get a ×2.0 stress scenario and a dedicated retention gate while capacity
gets **none**; and the caps bind on **maximum** participation over the window — 0.500 against a
**mean of 0.0178** in attempt-0001 — with the near-maximum distribution unreported, so a
tail-driven limit cannot be told apart from a genuine liquidity envelope. That is enough to justify
measurement, not enough to justify loosening.
- **On (ii), the harness/lock: Season was right, and the root cause was smaller than the proposed
workaround.** Both blockers were the same mistake made twice — **a derived thing was frozen as if it
were a fact**. The implemented cutover hashes the research identity rather than file bytes, derives
stop state rather than persisting it in attempt rows, and records Season-authorized extensions in a
separate chained event log.
- **On "is the harness correct?": the spine is right and should be defended.** NAV-path scoring
rather than a per-trade bag, fail-closed exposure limits, per-attempt source snapshots, causality
micro-replay, the universe-vs-active-book distinction, the money-denominated score, the reseed
discipline. That is better evidence hygiene than most shops write down. **Do not trade it away for
throughput.**

**The one-line recommendation:** *validate the three constants* — that is where the missed profit
actually is — and simplify only the apparatus that is inert for **every** asset class, not merely for
this one. Generic loosening would trade the harness's only real strength for a gain that is not where
the loss is.

> **Scope caveat that governs how to read this review.** All 190 current-schema attempts are
> crypto-perpetual futures on **1-minute** bars, 3-14 correlated names, directional standing-position
> strategies. Several conclusions — above all "eight of nine gates are inert" — are artifacts of that
> frequency and universe shape, not properties of the harness. **§7a classifies every finding as
> universal, frequency-dependent, universe-dependent, asset-class-dependent, or style-dependent, and
> withdraws the recommendations that do not generalize.** Read §7a before acting on §5.2.

---

## 1a. Independent-challenge disposition

Every finding below was independently re-derived from the same ledgers and source by a second
reviewer (Codex). Recorded here so a reader knows which claims survived adversarial checking and
which were corrected.


| Finding                      | Outcome of independent challenge                                                                                                                                                                                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A — strength/window coupling | **Confirmed, sharpened.** Exact hurdle is `S_ann ≥ k·√(P/n_eff)`; `k/√Y` is the dense-sampling best case, so the tabulated hurdles *understate* stringency. Recommendation corrected: report the realized hurdle in the run card, never persist it in `protocol.toml`. |
| B — iteration blockers       | **Problem confirmed; first-draft remedy was unsafe and is replaced.** Excluding whole `[output]`/`[loop]` sections would have unfrozen gate-bearing and keeper-bearing fields. Exclusion is now three named fields, paired with a recorded `extend`.                   |
| C — plateau disabled         | **Mechanism confirmed; recommendation withdrawn.** Counterfactual arithmetic was wrong (16 attempts reclaimed, not 31; zero in two of three lifecycles). Reframed as an operator policy decision.                                                                      |
| D — capacity                 | **Calibration/observability gap confirmed; causal claim withdrawn.** The controlled-experiment framing was false (two params changed), and the clearest "capacity killed an edge" candidate also failed the scale-invariant strength gate.                             |
| E — target volatility        | **Observation confirmed, defect not established.** Headroom is not forgone profit.                                                                                                                                                                                     |
| F — `loop.py` size           | Confirmed as a maintenance smell only; do not split until a real change creates the seam.                                                                                                                                                                              |
| G — best-row anchor          | Confirmed low-priority ergonomics. The "capacity artifact" framing was wrong and is removed.                                                                                                                                                                           |


Net effect: the two structural conclusions — *one gate does all the filtering*, and *two derived
things are frozen as facts* — survived unchanged and got stronger. Three of the seven recommendations
did not survive in their original form. **No finding in this review establishes that the harness
discarded a profitable strategy.**

## 2. Scope and evidence inspected


| Evidence          | What was read                                                                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Harness source    | `loop.py` (1750 lines), `protocol.py`, `gates.py`, `objective.py`, `onboarding.py`, `results_log.py`                                                                                                            |
| Active contracts  | `program.md`, `protocol.toml`, `experiment.toml`, `AGENTS.md`                                                                                                                                                   |
| Backlog / history | `HARNESS_TODO.md`, `UPSTREAM_LIMITATIONS_TODO.md`, `docs/HARNESS_AND_DOCS_REVIEW.md`                                                                                                                            |
| Upstream contract | `quant_strategies/docs/consumer/{reference,integration,usage-guide}.md`                                                                                                                                         |
| Empirical record  | **271 attempts** across 7 offloaded theses in `~/Personal/researched_strategies`: full `results.tsv` ledgers, `protocol.train.toml` per lifecycle, `README.md` verdicts, `crypto_perp_tsmom_majors` diagnostics |
| Tests             | At review time, 107 collected: **106 passed, 1 failed** because the causality regression was thesis-coupled. The implemented cutover retires that test (§9, action 15).                                          |


**Not verified:** upstream capacity/impact implementation (contract-only); any OOS/paper/live outcome
for any candidate.

**Measured for this review, beyond the artifacts:** the autocorrelation function of the at-risk NAV
return series, on three candidates re-run from their offloaded snapshots (§5.6). This was the review's
one open measurement and it is now closed.

---

## 3. Intended foundation model (first principles, before judging the code)

Strip the repo away. To find a real tradeable edge with an autonomous agent you need exactly five
things, and nothing else is load-bearing:

1. **One comparable number** per attempt, denominated in the thing you actually want (money), held
  constant across attempts so the comparison is meaningful.
2. **A falsifiable identity** — mechanism + falsifier + evaluation conditions — frozen for the
  lifecycle, so 50 attempts are 50 tests of one hypothesis rather than 50 different questions.
3. **A minimum honesty bar** the agent cannot cross by cleverness: no lookahead, no same-bar fill,
  no hidden costs, no universe laundering, no OOS feedback.
4. **A bounded editable surface** wide enough that the mechanism can be expressed well, narrow
  enough that the agent cannot rewrite the question.
5. **A stop rule the agent does not own**, so "I think we're done" is never an outcome.

Everything else — gate count, artifact profiles, run cards, snapshot trees — is instrumentation. It
earns its place only if it changes a decision.

The single hardest design constraint, and the one this harness partly missed: **any threshold that
filters candidates must be expressed in units of the thing it means to constrain.** A threshold in
borrowed units (standard errors, minute samples) silently couples its real stringency to whatever
else determines those units — and then no one is deciding the research bar anymore.

---

## 4. Project ontology: concepts, contracts, boundaries, invariants

```
                    OPERATOR (Season)  ──── owns: thesis identity, protocol envelope, reseed
                            │
                            ▼
   ┌──────────────────────── LIFECYCLE ────────────────────────┐
   │  thesis_lock.json  (identity + protocol binding, frozen)  │
   │  results.tsv       (append-only ledger, one row/attempt)  │
   └───────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   EDITABLE SURFACE    PROTOCOL (frozen)   STOP RULES
   strategy.py         data/window          max_iterations
   experiment.toml     costs, fills         plateau_patience
   rationale.md        capacity_model       baseline_grace
                       leverage_budget
                       risk_budget
                       objective, gates
                            │
                            ▼
              ┌──── ENGINE (quant_strategies) ────┐
              │  target book → sizing → capacity  │
              │  → fills/costs → NAV path         │
              └───────────────────────────────────┘
                            │
                            ▼
                 FOUNDATION EVIDENCE (per attempt)
                  realistic_costs | cost_stress | sizing
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
         SCORE (scale-DEPENDENT)     GATES (scale-INVARIANT)
         full_window_total_return    train_strength = t ≥ 2
                            │
                            ▼
                keep / discard / crash → continuation
```

**Core invariants the design asserts** (all verified present in code):

- A target is a standing signed weight of NAV; re-emitting trades nothing. (`program.md` §Target Book)
- Gross/net over budget **fails closed, never clamps** (upstream `leverage_budget_breach`).
- The universe is protocol-frozen and return-blind; the *active book* is strategy-owned. Changing
the universe is a reseed, never a loop edit.
- Scores are never comparable across universes (unpriced multiple testing).
- Attempts are comparable **iff** identity + protocol are unchanged — this is what the lock exists
to guarantee.
- Derived stop state is a function of (ledger, protocol). *Asserted by `_stop_reason_after_attempt`
being pure — then violated by persisting its output. See Finding B.*

**The ontology error at the centre of this review:** the score is deliberately **scale-dependent**
("proportional to dollars earned at a fixed starting NAV") while the only binding gate is
**scale-invariant** (a t-statistic). Both choices are individually defensible. Together they mean a
capacity-capped book gets a mechanically crushed *score* while its *gate* is untouched. The ledger
does record enough to tell the two apart — `target_reached` plus `deployed`/`max_feasible` volatility
— but the loop never acts on it, which is Finding D.

---

## 5. The empirical record — what actually killed 271 attempts

### 5.1 Outcome distribution


| Thesis                                     | n   | keeps | keep% | window (y) | implied Sharpe hurdle | final stop       |
| ------------------------------------------ | --- | ----- | ----- | ---------- | --------------------- | ---------------- |
| `crypto_perp_tsmom_majors`                 | 50  | 12    | 24.0% | 4.83       | **0.91**              | max_iterations   |
| `crypto_perp_funding_carry_directional`    | 30  | 5     | 16.7% | 4.00       | 1.00                  | max_iterations   |
| `crypto_perp_tsmom_vol_target`             | 5   | 1     | 20.0% | 4.00       | 1.00                  | (manual offload) |
| `crypto_perp_funding_crowding_reversal`    | 45  | 2     | 4.4%  | **0.84**   | **2.19**              | max_iterations   |
| `crypto_perp_funding_xs_crowding_reversal` | 30  | 0     | 0%    | 4.00       | 1.00                  | baseline_failure |
| `crypto_perp_tsmom_btc_single_name`        | 30  | 0     | 0%    | 4.83       | 0.91                  | baseline_failure |
| `fx_session_activity_profile_rejection`    | 81  | 0     | 0%    | 0.84       | (superseded gate set) | (manual)         |


Totals: **247 discard, 20 keep, 4 crash.** 35.0 hours of compute; median attempt 276 s, mean 466 s.

### 5.2 Which gate does the filtering

**Population: the 190 current-schema attempts only.** The superseded 81-attempt FX lifecycle used a
different objective and gate set (`train_floor`, `cost_stress`, `subwindow_coverage`) and is excluded
here, consistent with §8.4 — it contributed a further 9 `trade_floor` and 1 `breadth` failures under
same-named but differently-configured gates, which must not be pooled.


| Gate                     | attempts where it failed       | attempts where it was the **sole** failure |
| ------------------------ | ------------------------------ | ------------------------------------------ |
| `train_strength`         | 110                            | **83**                                     |
| `cost_stress_retention`  | 18                             | 0                                          |
| `minimum_evidence`       | 7                              | 0                                          |
| `trade_floor`            | 5                              | 0                                          |
| `path_risk`              | 1                              | 0                                          |
| `breadth`                | **0**                          | 0                                          |
| `effective_symbol_count` | **0**                          | 0                                          |
| `complexity_cap`         | **0**                          | 0                                          |
| `causality`              | 0 (crashes handled separately) | 0                                          |


Four further attempts were sole-`run_config` failures. `run_config` is a crash class, not a gate, so
the single-gate population is 83, all `train_strength` — a stronger statement than a pooled count
gives.

`minimum_evidence` is calibrated in **minute** return samples (`min_return_sample_count = 100`,
`min_effective_sample_size = 50`). A multi-year minute window yields 10⁵–10⁶ at-risk samples, so on
*this data* the gate cannot bind except on a degenerate near-zero-duty book — which is what its 7
firings were. `complexity_cap` allows 50 params against 17 actually declared.

> **Read this table as evidence about crypto-perp minute-bar theses, not about the gate set.** The
> zero counts are frequency- and universe-dependent: `minimum_evidence` and `trade_floor` become
> binding on daily bars, and `breadth` / `effective_symbol_count` become binding on a wide
> cross-section. §7a quantifies this. The finding "one gate does the filtering" is solid **for this
> thesis family**; the corollary "therefore simplify the other eight away" does not generalize and is
> withdrawn.

### 5.3 The near-miss distribution — how the 83 died

t-statistic of the 83 sole-`train_strength` failures (gate needs t ≥ 2):


| range             | count  |
| ----------------- | ------ |
| t < 0             | 5      |
| 0 ≤ t < 1.0       | 10     |
| 1.0 ≤ t < 1.5     | 31     |
| **1.5 ≤ t < 2.0** | **37** |


median t = 1.43, p75 = 1.68, max = **1.97**. Closest calls: t = 1.97 with LCB −0.0030 (carry
directional attempt-0013, score 0.219) and t = 1.97 with LCB −0.0026 (majors attempt-0013, score
0.727). **37 attempts with positive returns died between 1.5 and 2.0 standard errors.**

### 5.4 Capacity binding


| Thesis                                     | target not reached | median deployed vol | median max-feasible vol | median utilization |
| ------------------------------------------ | -------------- | ------------------- | ----------------------- | ------------------ |
| `crypto_perp_tsmom_majors`                 | 11/50          | 0.150               | 0.254                   | 0.590              |
| `crypto_perp_funding_carry_directional`    | 9/30           | 0.200               | 0.219                   | 0.915              |
| `crypto_perp_tsmom_btc_single_name`        | 16/30          | 0.148               | 0.148                   | **1.000**          |
| `crypto_perp_funding_crowding_reversal`    | 28/45          | 0.149               | 0.149                   | **1.000**          |
| `crypto_perp_funding_xs_crowding_reversal` | 29/30          | **0.010**           | 0.010                   | **1.000**          |
| `crypto_perp_tsmom_vol_target`             | 2/5            | **0.001**           | 0.001                   | **1.000**          |


Within `crypto_perp_tsmom_majors`, capacity binding costs roughly two-thirds of the score: median
score 0.306 when `target_reached = false` versus **0.898** when true. `book_scale` across all
attempts: median 0.255, max 0.619.

`crypto_perp_funding_xs_crowding_reversal` ran 30 attempts at deployed volatility **0.010 against a
0.15 target**, median score 0.0025, zero keeps, stopped on `baseline_failure`.

**It is not a case of capacity masking an edge, and an earlier draft of this review wrongly implied
it was.** In 29 of its 30 scoreable attempts, `train_strength` failed **as well as** the book being
capacity-bound. `train_strength` is a t-statistic, first-order invariant to book scale — and if
anything *helped* by a smaller book, since impact is sublinear in participation so per-unit economics
improve as scale falls. Failing it at 1/15th of target risk is therefore evidence of a weak edge
independent of deployable scale. The honest reading is that this lifecycle showed **both** an
unproven edge and no deployable scale; capacity did not retire a proven edge.

The capacity findings in §6.D consequently rest on **calibration and observability**, not on a claim
that the harness discarded profitable strategies through capacity. No such case is established in
this record.

### 5.5 Budget allocation — new-best-survivor events


| Thesis                                  | last improvement                                                       | budget | attempts spent after final improvement |
| --------------------------------------- | ---------------------------------------------------------------------- | ------ | -------------------------------------- |
| `crypto_perp_tsmom_majors`              | iter **40** (scores 0.28→0.51→0.70→0.85→0.86→0.97→0.98→1.00→1.04→1.05) | 50     | 10                                     |
| `crypto_perp_funding_carry_directional` | iter 23                                                                | 30     | 7                                      |
| `crypto_perp_funding_crowding_reversal` | iter **14**                                                            | 45     | **31** (≈2.4 h)                        |


The budget was **too short where research was productive and too long where it was dead.** Majors
was still climbing when `max_iterations` cut it off; crowding reversal burned 31 attempts after its
last improvement. `plateau_patience == max_iterations` in *every* lifecycle, and `protocol.py:418`
enforces `plateau_patience <= max_iterations` — so the plateau rule is unreachable by construction.

**This is a deliberate Season decision**, recorded in `docs/HARNESS_AND_DOCS_REVIEW.md`: "a fixed
budget with no machine auto-stop, per Season", chosen to stop the agent rationalizing early exits.
The intent is right. The implementation conflates two different things — see Finding C.

### 5.6 Is `n_eff` honest? — measured

The strength gate is `t = Sharpe_period · √n_eff ≥ k`. Upstream derives `n_eff` from a **lag-1**
autocorrelation only: `n_eff = n·(1−ρ₁)/(1+ρ₁)`, clamped to `[1, n]`. The standing suspicion was that
overlapping multi-hour holds leave `n_eff ≈ n`, understating SE and overstating `t` — which would make
this gate a weaker instrument than it appears.

**Method.** Two independent estimators, on the real series.

1. **Every stored attempt (99 scored attempts, 6 theses).** Because `n_eff` is a closed form in `ρ₁`,
   each stored `n_eff/n` inverts to the *measured* lag-1 autocorrelation — no re-run needed.
2. **Direct measurement on three re-run candidates.** The at-risk return series was captured at the
   single upstream funnel that turns it into `(σ, n_eff, sharpe)`, and validated by requiring it to
   reproduce the stored `return_sample_count`, `mean_return` and `return_volatility` exactly. Its full
   autocorrelation function was then computed by FFT, and the variance-of-the-mean inflation
   `V = 1 + 2·Σ(1−k/n)·ρ_k` estimated by Newey-West/Bartlett across bandwidths and, independently, by
   non-overlapping batch means. `n_eff_honest = n/V`; `V = 1` means upstream is right.

Bandwidth discipline: only `L ≤ n/20` and batch counts `B ≥ 12` are reported. Wide-bandwidth HAC
values on these lengths have no independent blocks left, and the all-lags sum is degenerate (the
sample ACF sums identically to −½), so neither is evidence.

**Result — the three directly measured candidates.**


| series (`realistic_costs` full_train) | n         | median hold | ρ₁       | upstream `n_eff/n` | measured `V` | `t` upstream | `t` honest |
| ------------------------------------- | --------- | ----------- | -------- | ------------------ | ------------ | ------------ | ---------- |
| majors a0040 (the kept survivor)      | 2,498,274 | 4.0 d       | +0.00247 | 0.99506            | 0.86         | 2.346        | 2.53       |
| carry directional a0028               | 675,928   | 0.7 d       | +0.00053 | 0.99894            | 0.93         | 2.554        | 2.65       |
| crowding reversal a0018               | 143,437   | 0.5 d       | −0.03225 | 1.00000            | 0.84         | 2.414        | 2.64       |


**`n_eff` is honest, and errs conservative.** Measured `V` is **0.84–0.93** against the `V ≈ 1.00`
upstream assumes, so the true SE is **4–9% smaller** than the gate uses. Across all 99 stored
attempts, `ρ₁ ≤ 0.0132` and `n_eff/n ≥ 0.974` without exception: the worst-case SE understatement
attributable to the lag-1 form is **1.3%**.

**Why persistent positions do not make persistent returns.** The at-risk return is `r_t = w_{t−1}·x_t`.
Position `w` persists for days — but `x_t` is a martingale difference with respect to the information
that fixed `w_{t−1}`, so the *product* carries almost no serial correlation regardless of how long the
position is held. Holds of 4 days (and up to 111 days) with `ρ₁ = +0.0025` is exactly that. Position
autocorrelation was never the right thing to worry about; only return autocorrelation enters the
variance of a mean.

**Consequence for the 83 kills: they stand.** All 83 sole-`train_strength` failures had `t ≤ 1.97`,
median 1.43. Applying the measured range uniformly reclaims **5–9 of 83 (6–11%)**, and every reclaimed
attempt sits in `t ∈ [1.86, 1.97]`, moving to `t ∈ [2.03, 2.16]` — inside the band Finding A shows a
*no-edge* 50-attempt search reaches on its own. The SE is not what retired these candidates.

Two secondary hypotheses were tested and rejected: kurtosis does not bias the estimator (Monte Carlo
across kurtosis 3→400 shifts the null median by <0.05, and measured kurtosis correlates *positively*
with `V`, +0.41), and the 8-hourly funding schedule leaves a real but immaterial harmonic (mean `ρ` on
multiples of 480 minutes ≤ +0.0012 against ~0 off-beat).

---

## 6. Findings

### Finding A — The one binding gate's real stringency is set by window length, not by research judgement

- **Severity:** High. **Action class:** Refactor. **Root cause:** contract — a threshold expressed
in borrowed units.
- **Evidence:** `gates.py:176-183`, `objective.py:327-343`, `protocol.toml:77`, and the ledger.

`train_strength` requires `R − k·SE ≥ 0` with `k = 2`. Since `R = mean·P` and
`SE = vol·P/√n_eff`, the gate is exactly `t = Sharpe_period·√n_eff ≥ k`, and with dense sampling
(`n_eff ≈ n = P·Y`) that is:

> **exact:  S_ann ≥ k · √(P / n_eff)**    →    **dense-sampling case (n_eff ≈ n = P·Y):  S_ann ≥ k / √Y**

The `k/√Y` form used in the table below holds when the at-risk sample is dense and serially
uncorrelated. §5.6 measures both conditions directly and they hold: `n_eff/n ≥ 0.974` across all 99
scored attempts, and the long-run variance ratio is 0.84–0.93. The tabulated hurdles are therefore
accurate to within a few percent, and if anything **overstate** the bar by 4–9%.

Verified against the ledger with no residual: `crypto_perp_tsmom_majors` attempt-0040 shows
t = 2.346, implying Sharpe 1.07 over 4.83 years — matching the 1.07 full-window Sharpe its README
reports independently.

So the actual economic bar was:


| window | implied hurdle    | keep rate  |
| ------ | ----------------- | ---------- |
| 4.83 y | Sharpe ≥ 0.91     | 24.0%      |
| 4.00 y | Sharpe ≥ 1.00     | 16.7% / 0% |
| 0.84 y | **Sharpe ≥ 2.19** | 4.4%       |


**Why it matters.** On the 0.84-year thesis the only two survivors carried in-sample Sharpe **2.35
and 2.62** — the harness admitted *only the most extreme in-sample outliers, precisely where the
evidence was thinnest, after 45 attempts of search.* A constant-`t` rule equalizes nominal
statistical confidence, but it does **not** equalize candidate quality: it systematically selects
for extremity as the window shortens. The gate is doing something no one chose.

**The mitigation that exists, and why it did not fire.** `onboarding.py:410-464` already computes
this exact hurdle (`k/√Y`), prints it in the setup proposal's Feasibility table, and warns — but
only when the required Sharpe exceeds **4.0** (`onboarding.py:458`). A required Sharpe of 2.19 is
already outside the plausible range for a net-of-cost liquid-market strategy, so the guard was set
roughly 2× too loose to catch the one lifecycle it was built for. And the disclosure lives only in
the transient setup proposal — it is not carried into `protocol.toml`, the run card, or the ledger,
so across 45 attempts nothing reminded anyone the bar was 2.19.

**The countervailing argument, stated fairly.** At `max_iterations = 50`, the approximate expected
maximum t across N independent zero-edge tries is ≈ **2.06** (N=30 → 1.85; N=100 → 2.33). So an
undeflated t ≥ 2 is roughly the level a *no-edge* thesis reaches by search alone. (Nested variants
of one mechanism are not independent draws, so effective N is well below 50 — and both `gates.py`
and the majors README state explicitly that `train_strength` is *not* a multiple-testing
correction, pushing deflation downstream to OOS.) The gate is therefore **plausibly too harsh for a
modest real edge and simultaneously too soft against a searched-over best-of-N** — because one fixed
threshold is doing two incompatible jobs.

**Recommendation.** Do **not** simply lower `k`. Separate the two jobs:
(a) express the research bar in economic units — report the **realized** per-run hurdle
`k·√(P/n_eff)` in every run card, computed from that run's actual `n_eff`. Do **not** persist a
derived hurdle field in `protocol.toml`: that would freeze a computed value as if it were an input,
which is precisely the error Finding B identifies, and it would drift from the realized hurdle
whenever `n_eff` differs from the dense-sampling assumption;
(b) leave the setup warning threshold unchanged until an operator study justifies a replacement —
1.5 is another unvalidated constant, not a root fix;
(c) separately study a minimum-window / minimum-independent-observation condition so a 45-attempt search cannot
run against a 10-month window.

The `n_eff` precondition on touching `k` is now discharged: §5.6 shows the SE is honest to within 4–9%
and conservative in direction, so `k` can be reasoned about on research grounds. What still argues
against simply lowering it is the best-of-N problem above, not measurement uncertainty.

### Finding B — Two blockers to continuous iteration, one root cause: derived state frozen as fact

- **Severity:** High. **Action class:** Simplify. **Root cause:** boundary — freeze granularity.
- **Evidence:** `loop.py:231-232`, `loop.py:243-244`, `loop.py:946-962`, `HARNESS_TODO.md:32-67`.

At review time, two independent guards blocked raising `max_iterations` on a live thesis:

1. `_ensure_active_thesis_lock` compares the **whole-file SHA-256** of `protocol.toml`
  (`loop.py:231`). Any byte change — a comment, a stop-rule field — raises *"active thesis protocol
   changed; start a new thesis lifecycle."* The lock is meant to freeze **research identity**; it
   actually freezes **the file**.
2. `_ensure_can_attempt` refuses when the *persisted* `continuation == "terminal"`
  (`loop.py:243`). But `_stop_reason_after_attempt` (`loop.py:946-962`) is a **pure function** of
   `(rows, complexity gate outcome, loop_config)` — and the complexity outcome is itself already in
   the row's `gate_flags`. Its output is fully recomputable from the ledger plus the protocol, yet
   it is written into the ledger and read back as though it were a measurement.

`HARNESS_TODO.md` correctly diagnosed that `max_iterations` is a **stop rule, not a research
assumption**. The implemented correction fixes both over-broad freezes at their source:

- **Hash an identity projection, not the file — and enumerate it by field, not by section.** The
exclusion set is exactly three fields: `[loop].max_iterations`, `[loop].plateau_patience`,
`[loop].baseline_grace_iterations`. Everything else stays hashed. **Excluding whole sections would
be unsafe**, because these are *not* stop rules despite where they live:
  - `[loop].min_abs_improvement` / `min_rel_improvement` feed `is_improvement` (`objective.py:391`)
  and so decide which attempts become keepers — they change survivor history, not just stopping.
  - `[output].foundation_cost_stress_multiplier` drives the cost-stress scenario behind the
  `cost_stress_retention` gate.
  - `[output].causality_check` / `micro_probe_limit` / `micro_timeout_seconds` change whether
  causality violations are detected, and causality is a gate.
  - `[output].foundation_subwindows` must equal `objective.subwindows` and feeds `minimum_evidence`.
  Narrowed to those three fields, the projection is strictly tighter than the section-level version
  and strictly looser than today's whole-file hash, and it protects every gate-bearing and
  keeper-bearing field.
- **Derive stop state instead of mutating evidence.** New ledgers do not persist
  `continuation` or `stop_reason`; `status` and `climb` derive them from immutable rows and the
  authorized stop rules. Season records a monotonic stop-rule increase with `extend`, which appends
  a chained event to `.autoresearch/lifecycle_events.jsonl`. It does not rewrite the last attempt,
  rebind the lock, or teach the operator to edit generated evidence.

The cutover deliberately rejects old lock and ledger schemas rather than maintaining two lifecycle
models.

### Finding C — The plateau rule is right and is switched off; the fixed budget solves the wrong half of the problem

- **Severity:** Medium-High. **Action class:** Refactor. **Root cause:** contract — two concerns conflated.
- **Evidence:** `protocol.toml:57-62`, `protocol.py:418-422`, six current-schema
  `protocol.train.toml` files, §5.5. The superseded FX lifecycle used a larger fixed budget.

The fixed budget was chosen so the agent cannot rationalize an early exit. That concern is real and
`program.md`'s Continue Rule is the right answer to it. But **"the agent must not decide to stop" and
"the harness must not stop early" are different propositions**, and the current config collapses
them by setting `plateau_patience = max_iterations`.

A harness-enforced plateau stop is not agent discretion — it is a machine-checkable rule the agent
cannot invoke, argue with, or reach for when bored. Re-enabling it therefore does **not** reintroduce
the premature-stopping hazard the fixed budget was chosen to prevent. That part of the argument
stands.

**The counterfactual gain is much smaller than an earlier draft of this review claimed.** Patience
fires `plateau_patience` attempts *after* the last new best, so at patience 15:


| Thesis                                  | last new best | plateau fires at | budget | attempts actually reclaimed |
| --------------------------------------- | ------------- | ---------------- | ------ | --------------------------- |
| `crypto_perp_funding_crowding_reversal` | 14            | 29               | 45     | **16** (not 31)             |
| `crypto_perp_funding_carry_directional` | 23            | 38               | 30     | **0** — never fires         |
| `crypto_perp_tsmom_majors`              | 40            | 55               | 50     | 0 — never fires             |


So the measured saving across three lifecycles is 16 attempts (≈1.2 h), in one lifecycle, at one
arbitrary patience value.

**And the value 15 is itself unvalidated.** Choosing it by reading these same histories would install
another high-leverage constant fitted to the record it is meant to govern — which is the exact
failure mode this review's central argument objects to. Applying the argument consistently: this is an
**operator stop-policy decision requiring its own analysis**, not a demonstrated harness defect with
a known fix. The defensible finding is narrower: *the plateau mechanism is implemented and tested
(`loop.py:946`) but disabled by configuration in every lifecycle, so the loop has no early-exit path
on a dead thesis — and whether it should is an open policy question.*

### Finding D — Capacity constrains the score, and this repo's handling of that is thin

- **Severity:** Medium (local scope). **Action class:** Refactor. **Root cause:** research practice —
  a constraint the loop reads but does not interpret.
- **Evidence:** `loop.py:396-413`, `loop.py:544`, `protocol.toml:27-35`, §5.4.
- **Engine-side analysis is owned elsewhere.** The capacity denominator semantics, the frontier /
  target-reachability conflation, the missing binding-event diagnostic, static costs, and volume-unit
  semantics are engine findings recorded in
  `quant_strategies/review-capacity-instrument-consumer-evidence.md`. They are **not restated here.**
  This finding covers only what this repo owns.

**The local mechanic that matters.** `book_scale` is the minimum of what `risk_budget` wants and what
capacity allows. Score rises with deployed scale (first-order — impact and NAV compounding are
nonlinear), while `train_strength` is a scale-free t-statistic. So when capacity binds, the **score**
is cut and the **gate** is not. Measured: within `crypto_perp_tsmom_majors`, median score 0.306 when
`target_reached = false` versus 0.898 when true.

**What this repo does wrong with that.**

1. **The loop reads capacity but never interprets it.** `target_reached = false` fired in 95 of 190
   attempts and changed nothing in how the result was treated — no branch, no note, no
   different next move. A field that changes the score by ~3× and triggers no response is
   instrumentation nobody acts on.
2. **The emitted frontier is retained locally.** `_foundation_sizing` and the run card carry
   `max_feasible_book_scale`. The ledger already carries `book_scale`, `deployed_volatility`,
   `max_feasible_volatility`, and `target_reached`.
3. **The thresholds are inherited, not chosen.** `impact_coefficient_bps = 10.0`,
   `impact_exponent = 0.5`, `max_average_bar_participation = 0.25`, `max_bar_participation = 0.50`,
   `account.initial_notional = 1_000_000` are round numbers with no ADR and no local sensitivity run. The
   local notional sensitivity is recorded in `docs/capacity-sensitivity-study.md`; action 10 remains
   the ADR. Calibrating the engine's coefficient is not this repo's call.

**The relief lever is real, but the headline comparison is confounded.** `attempt-0006` shows max bar
participation 0.500 → 0.147, `max_feasible_book_scale` 0.097 → 0.982, deployed volatility
0.067 → 0.150, `target_reached` false → true, and net total return 0.281 → 0.857 (3.05×). **It changed
two params, not one:** `execution_bars` 1 → 10 **and** `position_smoothing` 1 → 3. The capacity release
is attributable to spreading; the return move is confounded, because `position_smoothing` changes the
held-position path independently of capacity. So 3.05× bounds the *combined* effect of two
turnover-shaping levers. `program.md`'s "relieving a feasibility constraint is itself an alpha move"
survives qualitatively; the point estimate does not.

**Withdrawn: the "volume-blind" claim.** An earlier draft asserted, following
`UPSTREAM_LIMITATIONS_TODO.md:16-38`, that strategies receive no traded volume and that every in-loop
relief lever is therefore volume-blind. **An engine source read contradicts this**: capacity-enabled
projection rows preserve the `volume` field and strategy code may use it causally. This inverts the
conclusion and is the one place in this review where something is genuinely being left on the table —
volume-aware execution shaping is **not blocked upstream, it is unbuilt** (action 17). The related
claim that capacity output is a *lower bound* on deployable scale is also withdrawn: it rested on
scheduling being inexpressible, which it is not.

### Finding D2 — account scale must match the real mandate

- **Severity:** High for the next lifecycle. **Action class:** Refactor. **Root cause:** ontology — a
  protocol constant set to a hypothetical rather than a fact.
- **Evidence:** `protocol.toml:29`, attempt-0001 vs attempt-0006 sizing, operator-stated capital.

The primary mandate is **$100,000**, expressed as
`[account].initial_notional`. Participation, minimum-order feasibility, and
normalized fixed costs all scale from this value.

The engine's own verdict on attempt-0001 is that this strategy, executed inside a single minute,
supports a gross book of **$96,853**. At a risk-budget-preferred `book_scale ≈ 0.30`, the operator
would deploy ~$3,000 (at $10k) or ~$30,000 (at $100k) — **3% and 31% of that ceiling**. Capacity
cannot bind. The crossover for this strategy is ≈ **$320k** with one-bar execution and ≈ **$3M** with
10-bar spreading. Impact cost at $10k is ~0.24 bps against `fee_bps_per_side = 5.0` — about 4% of
one-side friction.

**Why this is a research defect, not just a conservative setting.** Being pessimistic about size is
usually harmless. Here it was not:

1. Attempts were **scored** under a constraint that will not exist. attempt-0001's 0.281 reflects a
   book cut to a third of intended size; at the operator's real scale that cut never happens.
2. Attempts were **spent** discovering capacity-relief levers (`execution_bars`,
   `position_smoothing`) that solve a problem the operator will not have for years.
3. The frozen survivor's execution configuration (`execution_bars = 20`) is at least partly a capacity
   adaptation. At small scale, minimum order sizes and fixed per-order costs can
   dominate; the execution model now prices both and fails closed on undersized
   orders.

So the cost model is **optimistic in the dimension that binds at small size** (indivisibility, fixed
costs) and the capacity model is **pessimistic in a dimension that does not bind** (impact). The
envelope is calibrated for a large-account regime the operator is not in.

**Current action.** Keep the $100k mandate fixed. Select a lawfully accessible
venue and snapshot its current per-symbol terms before baseline; execution remains
deliberately unpriced until then. Treat higher-notional scalability as a separate,
non-gating diagnostic.

### Finding E — `target_volatility` is frozen at a level never tested, and the survivor shows 2.2× headroom

- **Severity:** Medium. **Action class:** Add. **Root cause:** ontology — an untested constant on the score's critical path.
- **Evidence:** `protocol.toml:41-44`, `crypto_perp_tsmom_majors/README.md`, `program.md:148`.

Score rises with deployed volatility — **first-order, not proportionally**, since impact, costs, and
NAV compounding are nonlinear in scale. The majors long-only candidate reached
`max_feasible_volatility = 0.338` against a frozen `target_volatility = 0.15` — roughly **2.2× of
feasible risk left unused**, and its own README states the reachable range "is extrapolated from one
deployed level, never measured."

**This is headroom, not forgone profit.** A higher target buys more gross return *and* more impact
cost and deeper drawdown, and the `path_risk` gate (max drawdown 0.25) would begin to bind. Nothing in
this record establishes that 0.15 is the wrong level — only that it was never tested, and that the
harness cannot see the cost of the choice because the target is constant across every attempt in a
lifecycle.

`program.md:148` says "Optimize shape, not magnitude: upstream sizes the book, so a global magnitude
knob is washed out." That is true *within* a lifecycle and is the right rule for the agent — but it
is easy to misread as *magnitude does not matter*. It matters enormously; it is simply pinned by the
operator, so its cost is invisible because it is constant across every attempt in the ledger. The
result is that the most score-relevant single number in the protocol is the one number the harness
never varies or reports headroom against.

This does **not** argue for letting the agent turn the knob — leverage-as-alpha is exactly the
self-deception the harness exists to prevent, and reseed-only is correct. It argues for a
**deliberate operator-run volatility-target sensitivity study as its own documented lifecycle**, so
0.15 becomes a measured choice rather than an inherited one.

### Finding F — `loop.py` carries six responsibilities in one 1750-line module

- **Severity:** Low-Medium. **Action class:** Refactor. **Root cause:** boundary.
- **Evidence:** ~60 module-level functions spanning thesis-lock lifecycle, provenance hashing,
upstream foundation adaptation (`_foundation_*`, lines 300-435), ledger row construction, run-card
and snapshot writing, stop-rule derivation, and the CLI.

It works and is tested, so this is a legibility cost rather than a defect — a new session must read
a 1750-line file to find any one concern. The natural first seam is the **upstream adapter**
(`_foundation_*`), because that is exactly where Finding D's dropped fields live: fixing D starts
the split for free. Do not undertake a broader reorganization as its own project.

### Finding G — `param_delta_vs_best` anchors on a score-best that can be a capacity artifact

- **Severity:** Low. **Action class:** Add. **Root cause:** data model — single-valued "best".
- **Evidence:** `loop.py:965-1002`, `HARNESS_TODO.md:13-30`, majors README "Two candidates, one decision."

`HARNESS_TODO` item 1 is real: maintaining a second candidate makes the delta line report an extra
delta by construction, and the proposed optional `--base <run_id>` is a sound, minimal fix. Two
observations sharpen it. First, `_best_row` is single-valued while the majors lifecycle ended with
**two** legitimate candidates differing in one flag, whose 0.94% score gap the README itself calls
noise — so "best" is a scoring rule the research had already outgrown. Second, an earlier draft called
capacity's contribution to score-best an "artifact"; that was wrong. **Deployable return is
deliberately the objective**, so an attempt that deploys more scale scoring higher is the objective
working as designed, not a distortion. Recording the declared base in the ledger row, as the TODO
suggests, is worth doing on ergonomics grounds alone.

---

## 7. Overbuilt, underbuilt, right-sized


|                 | Area                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Overbuilt**   | Nine-gate config and doc surface for one binding gate (§5.2). `minimum_evidence` in minute units — cannot bind. `complexity_cap` at 50 params against 17 declared. Three stop-rule knobs expressing one behaviour. Whole-file lock hash where an identity projection is both narrower and stronger.                                                                                                                                                                                                        |
| **Underbuilt**  | No capacity stress scenario against a ×2.0 cost stress. Feasibility warning at 4.0 — too loose to fire. No minimum-window condition. No ADR for the capacity constants or for `target_volatility = 0.15`. Plateau rule present but switched off.                                                                                                                                                                                                                         |
| **Right-sized** | NAV-path scoring over a per-trade bag. Fail-closed exposure. Per-attempt source snapshots and provenance rehashing. Causality micro-replay. Universe-vs-active-book separation and return-blind universe selection. Reseed discipline and the reseed log. `program.md`'s Continue Rule. The money-denominated score. The offloaded-package quality — `crypto_perp_tsmom_majors/README.md` is genuinely excellent research documentation, including its honest "expect Sharpe 0.4-0.7, not 1.07" deflation. |


---

## 7a. Generality across asset classes and strategy styles

**The evidence base is narrow and this section states what that costs.** All 190 current-schema
attempts are **crypto perpetual futures on 1-minute bars**, 3-14 names, trend or funding mechanisms.
The harness and engine are asset-class-agnostic by design (`bars`, `forex_with_quotes`,
`crypto_perp_funding`; `equity_daily`, `equity_1min`, `forex_daily`, `options_snapshot`), so a finding
that only holds at minute frequency on a narrow crypto universe is a finding about *this thesis
family*, not about the harness. Each finding is classified below.

### Universal — holds for any asset class, frequency, or strategy style

- **Finding B (lock and derived stop state).** Pure harness mechanics. No market data involved.
- **Finding C (plateau disabled).** Loop control only.
- **Finding A's mechanism.** `t = S_ann·√(n_eff/P)` is **frequency-invariant**: with `n_eff ≈ P·Y` the
  `P` cancels, so the hurdle is `k/√Y` whether bars are minutes or days. It depends only on **window
  years**. This makes Finding A stronger, not narrower — and it exposes a cross-asset inequity the
  harness never reconciles:

  | Dataset | Available span | Max window | Hurdle at `k = 2` |
  |---|---|---|---|
  | `forex_daily` | 2013-01-01 → 2026-04-13 | 13.3 y | **0.55** |
  | `equity_daily` / `equity_1min` | 2018-01-02 → 2026-04-15 | 8.3 y | **0.70** |
  | `forex_1min_with_quotes` | 2020-01-02 → 2026-04-13 | 6.3 y | 0.80 |
  | `crypto_perp_1min_with_funding` | 2020-03-01 → 2026-04-13 | 6.1 y | **0.81** |

  With one fixed `k`, a crypto thesis must clear roughly **1.5× the Sharpe** an FX-daily thesis must
  clear, purely because crypto history is shorter. Neither number was chosen. Any future asset class
  with a short history inherits a harsher bar automatically.

### Frequency-dependent — my "inert gates" conclusion is a minute-data artifact

**This is the correction that matters most, because acting on §5.2 as written would break daily-bar
research.** `minimum_evidence` (`min_return_sample_count = 100`,
`min_effective_sample_size = 50`, applied to the full window *and* each of 6 subwindows) is inert on
minute data only because a minute window is enormous:

| Data | Bars in window | Per subwindow (6) | Verdict on `min_return_sample_count = 100` |
|---|---|---|---|
| 1-min, 4.83 y | ~2,500,000 | ~420,000 | inert — cannot bind |
| **daily, 8.3 y** | ~2,085 | ~347 | **live** — binds below ~30% at-risk duty |
| **daily, 4 y** | ~1,008 | ~168 | **binding** — fails at 60% at-risk duty |

So on daily bars this gate is a real and possibly blocking constraint. The same applies to
`trade_floor` (`min_trades = 36`): trivial for a fast crypto book, genuinely binding for a
monthly-rebalanced daily strategy.

**Revised recommendation:** recalibrating `minimum_evidence` into frequency-invariant units
(independent observations, or effective years) is still right — 100 *minute* returns and 100 *daily*
returns are not comparable evidence, and only one number is configured for both. But **retiring it is
wrong** and that option is withdrawn from action 8.

### Universe-shape-dependent

`breadth` (max concentration 0.80) and `effective_symbol_count` (≥ 1.5) never fired — because these
theses held 3-14 highly correlated names. On a 100-name equity cross-section, both become live and
important gates. Their zero-failure count is evidence about the *universe*, not about the gates.

### Asset-class-dependent — one config block cannot serve all classes

- **`max_bar_participation = 0.50` means completely different things per frequency.** 50% of a
  *minute* is aggressive but survivable; 50% of a *day* would be an enormous position. One value
  cannot be correct for both `crypto_perp_1min` and `equity_daily`.
- **The max-statistic fragility in Finding D.1 scales with bar count.** A max drawn from 2.5 M minute
  bars is a far more extreme outlier than one drawn from ~2,000 daily bars. So the single-thin-bar
  problem is **severe at minute frequency and mild at daily** — Finding D is largely a
  high-frequency finding.
- **`impact_coefficient_bps = 10.0` is inherently per-asset-class.** Upstream already concedes this
  by failing closed on FX with `capacity_unsupported_volume_semantics` because FX `volume` is tick
  count. That fail-closed verdict *proves* capacity semantics are asset-class-specific — yet
  `[capacity_model]` provides exactly one global parameter set.
- **`entry_lag_bars = 1` is one minute here and one day on daily bars.** Same value, radically
  different fill realism.
- **`path_risk` (max drawdown 0.25)** never fired because volatility targeting on a diversified-ish
  crypto book keeps drawdown moderate. For jump-risk-exposed books (options, single-name event
  strategies) it would bind.

### Strategy-style-dependent

Every reviewed thesis is a **standing-position, directional** strategy. Untested by this record:
market-neutral long/short (where `max_net_exposure` and `effective_symbol_count` bind differently),
event-driven and low-duty-cycle strategies (where `minimum_evidence` and `trade_floor` bind hard),
and anything using `RiskRule` barriers as a primary mechanism.

### What to do about it

The generalizable ask is a **per-asset-class protocol profile**: the frequency- and class-sensitive
fields (`minimum_evidence` thresholds, `min_trades`, `max_bar_participation`, `entry_lag_bars`,
`impact_coefficient_bps`, `annualization_periods_per_year`) should be set from the data kind and bar
cadence rather than hand-copied from the last crypto lifecycle. `onboarding.py` already computes the
Sharpe hurdle from the window; extending that logic to derive frequency-appropriate evidence floors
is the natural home. **Until then, treat every threshold in `protocol.toml` as calibrated for
crypto-perp minute bars and re-derive it on the first non-crypto or non-minute thesis.**

---

## 8. Unknown unknowns and assumption risks

1. ~~**The `n_eff` question**~~ — **measured and closed; see §5.6.** The lag-1 form is accurate
  (`n_eff/n ≥ 0.974` across 99 attempts) and the long-run variance ratio is 0.84–0.93, so the gate's
   SE is honest and mildly **conservative** — the opposite of the suspected direction. The 83 kills
   stand. The caveat that defused this in the first place turned out to be the whole answer: only
   *return* autocorrelation enters the variance of a mean, and position persistence does not create it.
   Retained here because it was the highest-priority risk in this review and its resolution is what
   licenses reasoning about `k` at all.
2. **The upstream capacity model is contract-only evidence.** Whether
  `max_feasible_volatility = 0.010` on the xs-crowding thesis reflects genuine market impact or a
   model artifact is untested. That thesis also failed the scale-invariant strength gate in 29 of 30
   scoreable attempts (§5.4), so capacity was not what retired it — but the number itself remains
   unvalidated and would matter for any future high-turnover thesis.
3. **Selection deflation is entirely deferred to OOS**, and available holdout is thin — the majors
  README notes ~3.5 months yielding ~4 closed trades for the long-only candidate. The system's only
   defence against 50-attempt search may be too small to function.
4. `**fx_session_activity_profile_rejection` (81 attempts, 0 keeps) ran a superseded objective**
  (worst-subwindow) and gate set. It is evidence that the harness has already loosened once — the
   worst-subwindow objective was replaced by full-window total return — which is a point in the
   design's favour, but it means those 81 rows cannot be pooled with the rest.
5a. **Single-asset-class, single-frequency, single-style evidence base.** Every scored attempt is
   crypto perp, 1-minute, directional, 3-14 correlated names. Untested by this record: daily bars,
   equities, options, market-neutral books, wide cross-sections, low-duty-cycle event strategies, and
   `RiskRule`-driven mechanisms. §7a maps which findings survive the generalization and which do not.
   The largest single risk in this review is treating a crypto-minute artifact as a harness property —
   which the first draft did for the gate set.
6. **Sample size for this review's conclusions is 7 theses, 5 of them crypto perp, all one
  operator.** Keep-rate-versus-hurdle (§5.1) is suggestive, not established.

---

## 9. Missing decision records

`docs/adr/` holds exactly one ADR (`0001-curated-few-research-regime.md`). No decision record exists
for any of these load-bearing choices:

- the capacity-model constants (impact coefficient/exponent, ADV and bar participation caps, notional);
- `target_volatility = 0.15`;
- `train_strength_haircut_se = 2.0` and its window coupling;
- `plateau_patience == max_iterations` (recorded only as a line inside a review doc, which
`docs/HARNESS_AND_DOCS_REVIEW.md` itself declares is *not* an active contract — so the rationale
for a live behaviour currently lives in a document that disclaims authority over it);
- the gate thresholds, several of which cannot bind.

Also: `HARNESS_TODO.md:1` begins `and# Harness TODO` — a stray two-character prefix breaking the H1.

**The causality regression test was thesis-coupled and failing.** A synthetic fixture cannot prove
an arbitrary replaceable strategy causal, and requiring a replacement on every reseed creates a
second thesis setup surface that can become stale or vacuous. It was retired. Every Train attempt
already runs upstream micro replay on its actual rows, and this harness fails the causality gate when
that evidence is non-admissible. Complete replay remains a downstream validation/evaluation concern.

---

## 10. Action map

Status legend: `open` = not started. Priority: P0 highest.

**Ownership.** `HARNESS_TODO.md` owns changes to this repo's harness (`loop.py`, `protocol.py`,
`gates.py`, `objective.py`, `onboarding.py`, `results_log.py`) and operator ergonomics;
`UPSTREAM_LIMITATIONS_TODO.md` owns upstream data and engine limits. **Table 10a is local and
actionable here. Table 10b is not** — those rows are engine changes, and this review is not their
owning document; each points at the doc that is.

### 10a. Local — this harness


| No. | Status | Priority | Action                                                                                                                                                                                                                                                                                                                                      | Class    | Finding | Scope                                                                  |
| --- | ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------- | ---------------------------------------------------------------------- |
| 1   | **done**   | **P0**   | ~~Measure realized multi-lag autocorrelation of the at-risk NAV return series; settle whether `n_eff` is honest.~~ **Done — §5.6.** Measured on 3 re-run candidates plus all 99 stored attempts: `n_eff` is honest and 4–9% conservative; the 83 sole-`train_strength` kills stand. No threshold change is warranted on SE grounds, and the upstream `n_eff` ask is closed as moot. | Add      | §5.6, §8.1, A | done |
| 2   | **done**   | **P0**   | The lock uses a canonical identity projection excluding **exactly three fields**: `[loop].max_iterations`, `plateau_patience`, `baseline_grace_iterations`. Everything else — including all of `[output]` and `[loop].min_abs_improvement`/`min_rel_improvement` — stays hashed. | Simplify | B       | `loop.py`, `onboarding.py`                                             |
| 3   | **done**   | **P0**   | `extend` authorizes only monotonic increases to the three stop rules and appends a chained lifecycle event. Stop state is derived; attempt rows are never rewritten. Old lock and ledger schemas are rejected. | Simplify | B       | `loop.py`, `results_log.py`                                       |
| 4   | **done** | P3       | Capture `max_feasible_book_scale` in the adapter, ledger, and run card. | Add | D.2 | `objective.py`, `loop.py`, `results_log.py` |
| 5   | **done**   | **P1**   | Run cards report the **realized** per-run hurdle `k·√(P/n_eff)`. No derived protocol field or unvalidated 1.5 blocking threshold was added. | Add      | A       | run card                                      |
| 6   | open   | P2       | Decide stop policy deliberately: whether a harness-enforced plateau should exist at all, and at what patience. **Reframed** — the measured gain from patience 15 is 16 attempts in one of three lifecycles, and picking 15 from these histories would install another unvalidated constant. Needs its own analysis, not a default.          | Refactor | C       | operator study; `protocol.toml`, `program.md` Stop                     |
| 7   | **done** | **P1**   | The frozen attempt-0040 survivor reaches its volatility target through $1.9m and misses it at $2.0m. See `docs/capacity-sensitivity-study.md`. | Add | D.3 | direct non-gating reruns |
| 8   | open   | **P2**   | Recalibrate `minimum_evidence` into **frequency-invariant** units (independent observations or effective years). **Retiring it is withdrawn** — it is inert only on minute data and becomes binding on daily bars (§7a). Document `complexity_cap` as a fail-safe.                                                                            | Refactor | §5.2, §7a | `protocol.toml`, `gates.py` docstring                                |
| 8b  | open   | **P1**   | Derive frequency- and asset-class-sensitive fields from the data kind and bar cadence instead of carrying crypto-minute values forward: `minimum_evidence` floors, `min_trades`, `max_bar_participation`, `entry_lag_bars`, `impact_coefficient_bps`, `annualization_periods_per_year`. Home is `onboarding.py`, which already derives the Sharpe hurdle from the window. | Add | §7a | `onboarding.py`; **required before the first non-crypto or non-minute thesis** |
| 9   | open   | **P2**   | Add a minimum-window / minimum-independent-observation condition so a 45-attempt search cannot run against a 10-month window.                                                                                                                                                                                                               | Add      | A       | `protocol.py` load guard                                               |
| 10  | open   | **P2**   | Write ADRs for the capacity constants, `target_volatility = 0.15`, `train_strength_haircut_se`, and the fixed-budget choice. Move the plateau rationale out of the non-authoritative review doc.                                                                                                                                            | Add      | §9      | `docs/adr/`                                                            |
| 11  | open   | **P2**   | Run an operator-owned volatility-target sensitivity study as its own documented lifecycle; publish headroom against `max_feasible_volatility`.                                                                                                                                                                                              | Add      | E       | one lifecycle; **not** an agent-editable knob                          |
| 12  | open   | **P3**   | Add optional `--base <run_id>` to `climb`; record the declared base in the ledger row.                                                                                                                                                                                                                                                      | Add      | G       | `HARNESS_TODO` item 1, as written                                      |
| 13  | open   | **P3**   | Extract the `_foundation_*` upstream adapter out of `loop.py` — naturally begun by item 4.                                                                                                                                                                                                                                                  | Refactor | F       | one seam only; no broader reorganization                               |
| 14  | **done**   | **P3**   | Fix the stray `and` prefix on `HARNESS_TODO.md:1`. | Retire   | §9      | 2 characters                                                           |
| 15  | **done**   | **P1**   | Retire the stale thesis-coupled causality test. Per-attempt micro replay on actual rows plus the fail-closed local gate owns Train causality; complete replay belongs downstream. | Retire | §9      | 1 test file                                                            |


| 18  | open | **P1** | Calibrate `min_cost_stress_return_retention` for the $100k mandate and selected venue terms. Capacity is unlikely to bind at this scale, while proportional and fixed execution costs may become the binding economic gate. | Add | D2, §9 | `protocol.toml`, `docs/adr/` |

### 10b. Upstream asks — owned elsewhere, not restated here

Engine-side asks motivated by this review are **not listed in this document**, to keep one owner per
item:

| Ask | Owning document |
| --- | --- |
| Discrete lot, quantity-step, price-tick, and contract-multiplier semantics | `UPSTREAM_LIMITATIONS_TODO.md` |

**Reciprocal cleanup owed.** The upstream working note's finding 7 — the provisional `0.50`
`cost_stress_retention` threshold — is a **harness** item, not an engine one. It is owned here as
action 18 and should be dropped from that note.

**Sequencing.** Items 1–5, 7, and 15 are complete. Venue selection and a current
execution-terms snapshot are required before the next Train attempt. The remaining
actions retain their listed priorities.

---

## 11. Preservation constraints — do not trade these for throughput

These are right-sized and should stay stable even under pressure to move faster:

- **NAV-path scoring, not a per-trade bag.** The single best decision in the design.
- **Fail-closed exposure limits, never clamped.** Clamping would silently rewrite the experiment.
- **Universe frozen and return-blind; the active book strategy-owned.** The clearest defence against
the survivorship bias that inflates most published crypto results.
- **No score comparison across universes.** Correctly identified as unpriced multiple testing.
- **The evidence boundary: no OOS feedback into a Train lifecycle.** Non-negotiable.
- **Per-attempt source snapshots plus provenance rehashing**, and an append-only ledger no operator
edits. Items 2 and 3 exist partly to stop the current workaround from eroding this.
- `**program.md`'s Continue Rule** — the agent never owns the stop. Item 6 changes who *else* can
stop the loop, never this.
- **Reseed discipline:** universe, notional, leverage budget, risk budget, objective, and gates stay
reseed-only. Item 11 respects this by running the volatility study as its own lifecycle.

---

## 12. NOT in scope

- Upstream `quant_strategies` / `quant_data` implementation changes. Items 4 and 7 may become
upstream asks; this review does not design them.
- Any OOS, paper, or live evaluation of any candidate, including the two open majors candidates.
- The `crypto_perp_tsmom_majors` long-only-versus-two-sided decision, which its package
deliberately leaves open.
- `strategy.py` research content, and the `new-thesis-setup` / offload skills.
- Restructuring the offloaded `researched_strategies` store.
- Any code or config change: this review is a decision artifact only.

---

## 13. What was verified, what was not, residual risk

**Verified from source or ledger arithmetic:** the gate-failure distribution and sole-failure counts
(§5.2); the `t = Sharpe·√Y` identity, reconciled independently against the majors README's reported
Sharpe (§6.A); the implied-hurdle-versus-keep-rate table (§5.1); capacity binding rates, deployed
and max-feasible volatilities, and the score gap between capacity-bound and unbound attempts (§5.4);
new-best-survivor trajectories (§5.5); that, at review time, `_stop_reason_after_attempt` was pure
while its output was persisted and the lock compared a whole-file hash (§6.B); that
`max_feasible_book_scale` is emitted upstream and now retained locally (§6.D); that
`_feasibility_warning` fires only above 4.0 (§6.A); that `plateau_patience == max_iterations` in all
seven lifecycles (§5.5); and that the initial suite failure was the thesis-coupled
causality test retired by action 15 (§9).

Also verified from the `crypto_perp_tsmom_majors` diagnostics artifacts: the attempt-0001 /
attempt-0006 capacity figures, the 28× max-to-mean participation ratio, and the 3.05× score move
from the combined execution-spreading and position-smoothing change (§6.D).

**Verified by direct notional reruns:** the frozen attempt-0040 survivor reaches the 15% volatility
target at $1.9m and misses it at $2.0m under the configured capacity model. The seven-run study,
input hashes, and capacity tails are recorded in `docs/capacity-sensitivity-study.md`.

**Verified by direct measurement on re-run candidates (§5.6):** the autocorrelation function of the
at-risk NAV return series for three candidates spanning the range of behaviour, and the resulting
long-run variance ratio (0.84–0.93 against upstream's implicit 1.00). The captured series was gated on
reproducing the stored `return_sample_count` / `mean_return` / `return_volatility` exactly, so it is
the series upstream actually scored rather than a reconstruction. Lag-1 autocorrelation was
additionally recovered in closed form for all 99 stored attempts.

**Not verified:** upstream capacity/impact behaviour beyond the consumer contract; **the unit
`volume` is denominated in for `crypto_perp_1min*`** — the `quant_data` contract annotates forex
volume as "tick count, not notional" but leaves crypto perp "dataset-dependent", so the denominator
of every participation ratio above is unstated (worth one clarifying question upstream); whether the
0.84–0.93 variance ratio of §5.6 holds on daily bars or a wide cross-section — it is measured on three
crypto-perp minute candidates only, and the mechanism generalizes but the magnitude is not
established; whether volume is reachable by strategies
(`UPSTREAM_LIMITATIONS_TODO` records this as unchecked); any claim about how these candidates would
perform out of sample; that narrowing the lock hash (Item 2) has no consequence I have not
considered — it needs a test that a genuine identity change still hard-stops.

**Residual risk.** The central conclusion — *the apparatus is over-built and inert while three or
four constants are under-validated and decisive* — rests on 271 attempts from 7 theses, 5 of them
crypto perp, all one operator. The direction is well supported; the magnitudes are not established.

The review's one open measurement is now closed, and closing it removed a suspected defect rather than
confirming one: the strength gate's standard error is honest and slightly conservative (§5.6). That
shifts the residual risk. What remains under-validated is no longer the *statistic* but the
*constants* chosen around it — `train_strength_haircut_se = 2.0` against a best-of-N search that
reaches t ≈ 2 unaided, `target_volatility = 0.15`, and
`min_cost_stress_return_retention = 0.50`. None of those is a measurement problem;
each is a decision nobody has recorded (§9, action 10).

The single largest remaining exposure is generalization: every measured number here comes from
crypto-perp minute bars. §7a marks which findings survive a change of asset class or bar cadence and
which are artifacts of this data, and action 8b is the guard that must land before the first
non-crypto or non-minute thesis.
