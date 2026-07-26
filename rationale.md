# Rationale — crypto_perp_tsmom_majors

Per-name time-series momentum (trend following) across the deepest crypto-perp majors
(**BTC-PERP, ETH-PERP, SOL-PERP**), aggregated into one book, sized by the engine's
volatility target. Train-only research; OOS, paper, and small-live review are downstream.

Same thesis identity as the preceding lifecycle, re-run on clean evidence. That lifecycle
produced a gate-clearing survivor but spent 18 of its 30 attempts carrying a stray
price-path stop that fails the gate on its own, so its lever verdicts are unusable. This
lifecycle re-tests the confounded levers with the price-path exits removed from the strategy
entirely. Its inherited evidence — what is clean, what is retracted, and the matched-control
method that salvages relative reads — is in `.autoresearch/lifecycle_archive/`, alongside
the 30-attempt ledger and per-attempt snapshots.

## Thesis (invariant identity)

**Mechanism.** Each crypto-perp major is retail-heavy, sentiment-driven, and weakly
arbitraged, so it under-reacts to information then delayed-over-reacts: each instrument's
own past price trend positively predicts the sign of its next-horizon return (time-series
momentum). The signal is applied independently per name from that name's own history (no
cross-section), and the book aggregates the per-name own-trend signals within one gross
budget.

**Observable.** Each symbol's own trailing price return over a formation window, from its
`close` history known at decision time (`available_at <= decision_time`). Realized 8h
funding is applied as financing on multi-day holds, never read as a signal.

**Falsifier.** Reject the thesis — rather than adding filters or per-name/per-window
exceptions — if net return after realistic costs and ADV/impact capacity is not positive
across the bounded lookbacks; or is not materially above a volatility-matched
buy-and-hold of the same basket; or all return concentrates in **one name** or one
mega-trend subwindow rather than being pervasive across names and regimes; or the
per-name trend-sign relationship is insignificant or flips after the cost floor.

**Horizon.** Weekly-to-quarterly trend persistence, per name.

## Universe

Three a-priori instruments: **BTC-PERP, ETH-PERP, SOL-PERP** — the deepest, longest-history
crypto-perp majors, chosen return-blind on eligibility (liquidity and history), never on
returns. The set is deliberately capped at three deep majors, not a broad basket: depth is
the mitigation for the thin-name capacity wall that killed a broader earlier lifecycle.

The **universe** (these three names) is protocol-frozen; changing it is a reseed. The
**active book** — how many of the three the signal actually holds at any time — is
strategy-owned and varies every attempt through the signal, the gate, and allocation
shape. Breadth is evidence to read (does it raise duty and diversify?), not a number to
optimize, and is never narrowed by naming names.

## Train window

**2021-03-03 → 2025-12-31 (~4.83 years).** Starts 2021-03-03, after BTC-PERP's only
unrepairable >45-min gap (2021-03-02); SOL-PERP data begins 2020-09-14 and ETH/BTC in
2020, so all three are clean from the start. Six regime-diverse subwindows span a full
bull-bear-bull cycle. The `train_strength` hurdle is `2/√4.83 ≈ 0.91` best-case annualized
Sharpe (a held/low-duty book needs more). The ~3.5-month tail to the data end is reserved
for downstream OOS.

## Signal Components

### Component: Per-name trend formation
For each symbol, the trailing return `r = close(formation_end) / close(formation_end −
lookback_days) − 1` sets the signed target (`trend_method="ma_cross"` instead compares the
close to its lookback-window mean daily close). `signal` reads it as `sign` (±1) or
`long_flat` (+1/0). With `blend` on, the vote is averaged over a fixed multi-timescale
lookback set {20,50,100,200}. `skip_days` optionally excludes the reversal-prone recent
move. `confirm_lookback_days > 0` gates the target by a slow regime trend over that horizon
(long only in a slow uptrend, short only in a slow downtrend, else flat) — the "trade with
the major trend" filter. `signal_band > 0` adds a no-trade band around the sign decision, so
a name holds its prior vote until the formation return clears the band. With `vol_scale` on,
each entry is scaled by `min(1, ref_vol / recent_vol)` (ex-ante vol scaling; fixed at entry).
This is one per-name trend edge; the gate, band, vol-scale, and estimator are filters and
sizing on it, not separate alphas.

**Book construction (not a separate alpha).** The book allocates across the per-name signals
by `weighting` — `equal` (`1/N` of NAV per name), `inverse_vol` (risk parity on each name's
recent realized vol), or `conviction` (vol-adjusted trend strength) — with `top_n` optionally
capping the active set. Every shape redistributes within the same active-set gross that equal
weighting would use, and weights recompute only on a vote change. `position_smoothing` steps
the emitted book fractionally toward each new target across that many rebalances, and
`execution_bars` ramps each step across that many one-minute bars; both change when turnover
lands in the capacity windows, not what the signal says. The operator-frozen volatility
target sets the overall book scale.

## Editable surface (levers)

Per-name formation & signal:
- `lookback_days` [20-180] — formation horizon. Coarse grid; do not fine-tune.
- `signal` {sign, long_flat} — two-sided, or long-only.
- `blend` {true, false} — single-horizon vote or multi-timescale sign blend.
- `skip_days` [0-15] — gap formation.
- `rebalance_days` [1-7] — rebalance cadence.
- `confirm_lookback_days` [0-200] — slow regime-agreement gate (0 = off). Coarse grid.
- `signal_band` [0-0.5] — no-trade band around the sign decision (0 = off).
- `trend_method` {return, ma_cross} — trend estimator.
- `vol_scale` {true,false} + `vol_lookback_days` [10-90] — ex-ante vol scaling.

Allocation and execution shape:
- `weighting` {equal, inverse_vol, conviction} + `top_n` [0-3] — cross-name allocation.
- `position_smoothing` [1-20] — spread one position change across that many rebalances.
- `execution_bars` [1-30] — ramp each step across that many one-minute bars.

Pinned: `decision_lag_minutes = 1` (causal). **There are no price-path exit levers.** A fixed
stop and a trailing stop were both falsified on clean evidence, and the stray trailing stop is
what confounded the preceding lifecycle, so they are out of the strategy rather than defaulted
off. Re-adding one is a deliberate decision, not a parameter flip.

## Assumptions

Bars are timezone-aware and ordered by causal availability through `available_at`. The
rebalance clock fires at UTC midnight every `rebalance_days` days; each decision fires at
the first real bar at or after the signal bar's `available_at` plus `decision_lag_minutes`.
Warmup happens inside the window. A multi-day hold pays or collects realized 8h funding via
the financed data kind.

## Inherited evidence (priors, not frozen results)

Carried from the preceding lifecycle. CLEAN means the deciding attempt had no stray stop;
everything else is a prior to re-test here, never a settled result.

- **CLEAN and load-bearing.** Two structural discoveries carried the thesis over the gate:
  risk-parity `inverse_vol` cross-name weighting, and dropping the slow regime gate. The
  gate-clearing configuration is 25d formation, `long_flat`, daily, `inverse_vol`, no gate,
  no exits, at t 2.42 (gap 0) and t 2.19 with a 13% higher score (gap 3), both pervasive
  across all six regime subwindows.
- **CLEAN rejections.** `conviction` weighting, `top_n=2`, a 60d formation horizon, two-sided
  `sign`, weekly cadence, `ma_cross`, and both price-path exits.
- **CLEAN capacity pin.** `capacity_bound = true` with `deployed_volatility ==
  max_feasible_volatility` on every clean attempt: 0.054-0.067 annualized vol against the
  0.15 target, so the book deploys 36-45% of its risk budget. The pin is real. Which lever
  can relieve it is the open question.
- **OPEN — the capacity/execution shape.** Held against a like-for-like control, a 0.05
  no-trade band and 5-rebalance position smoothing each *improved* the objective, and
  smoothing lifted `book_scale` 34%. Their recorded failures came from scoring them against a
  clean survivor while they carried the stop. They are candidates to beat the survivor.
- **OPEN — the gap choice.** The gap curve is a plateau over 0-3, not a spike, so which gap
  the survivor should carry is unresolved.
- **OPEN — the formation horizon.** A sharp peak at 25d survives the like-for-like control on
  both sides, so horizon sensitivity is real and is this thesis's main OOS risk. Whether the
  30d neighbour clears the gate is untested.
- **Falsified on the control, no re-test warranted.** `blend`, `equal` weighting, `top_n=1`.

## First failure mode to watch

**The baseline failing to reproduce its inherited score.** The baseline runs the inherited
gate-clearing configuration with the exit levers deleted, so it must reproduce that score. A
material miss means the reproduction is not clean — code drift, a data change, or
non-determinism — and every comparison in this lifecycle is unsafe until that is explained.
Check it before reading any lever result.

Second: **the capacity levers improving score while eroding the gate.** Smoothing raises
deployable scale but adds execution lag; the objective can rise while `train_strength` falls.
Read both, and prefer the configuration that clears the gate.

Third: **correlation limiting breadth.** BTC/ETH/SOL run ~0.7-0.9 correlated, so they trend
and whipsaw together. Watch effective symbol count and per-subwindow pervasiveness, and treat
concentration > 0.80 or effective symbol count < 1.5 as the breadth gates correctly failing.

## Lever Enumeration

Each distinct lever this thesis affords, with its status in **this** lifecycle. Inherited
priors are in Inherited evidence; this list tracks what has been run here. Every verdict is
stated with the base it was measured at, because five separate readings in this thesis turned
out to be base-specific (see Base dependence).

- **Formation horizon** (`lookback_days`) — RUN, closed on both sides at both candidates' bases, and
  the single most consequential axis. Long-only: 20 fails, 25 and 30 both pass 2.3% apart, 40 fails —
  a two-point plateau inside the a-priori 25-30d range. Two-sided: 25 passes at −10.7%, 30 is the
  survivor, **35 already fails**, 40 fails — effectively one point. Interacts with execution ramping
  (30d loses to 25d at ramping 10, wins at ramping 20) and with side logic (shorts are only pervasive
  at 30d). **Adding shorts converts a plateau into a knife edge.**
- **Gap** (`skip_days`) — RUN at three bases, axis closed. 0 wins everywhere. A one-day gap costs 2.4%
  at 25d long-only, 12.5% at 30d long-only, 14.2% at 30d two-sided: smooth at the short horizon,
  steep at the long one regardless of side logic, because a longer formation already excludes the
  recent move. Gap 2+ is untested and points the wrong way.
- **Rebalance cadence** (`rebalance_days`) — RUN. Daily wins: a 2-day clock buys the best per-trade
  economics in the ledger (PF 5.50, cost drag 0.021) and still loses 16.5% of score and 0.37 of t
  to slower exits. Response speed dominates cost drag by an order of magnitude, so turnover
  reduction is not a productive direction on this thesis.
- **Trend estimator** (`trend_method`) — RUN. `ma_cross` falsified decisively (t 1.36, the
  weakest row in the lifecycle); capacity relief does not rescue it.
- **Multi-timescale blend** (`blend`) — RUN. Falsified on three gates at once (t 0.77, 17 trades
  against a floor of 36, DD −0.289). Slow horizons convert the book to near-buy-and-hold.
- **Side logic** (`signal`) — RUN at both bases, and the verdict flipped. Two-sided lost 12% at the
  25d base; at the survivor's base it **wins on score** (+0.94%) because it is never flat, while
  every risk-adjusted measure falls (t 2.533 → 2.346, profit factor 4.96 → 1.92, cost drag doubles).
  A deployment gain, not an edge gain — but it carries 5× the closed trades and materially better
  dispersion across names and regimes. Treat as a fork, not a ranking.
- **Allocation shape** (`weighting`) — RUN at two bases. `inverse_vol` beats `equal` by +0.11 score
  and +0.19 t at 25d, and the gain is breadth (effective symbol count 2.79 vs 2.33) rather than trade
  quality. `conviction` fails `train_strength` at both bases — leaning into per-name trend magnitude
  concentrates into extended positions (drawdown −0.201, the worst deployed row). Risk parity across
  the whole active book is the right shape everywhere measured. **Agreement across names carries
  information; magnitude within a name does not** — the breadth tilt pays and conviction does not.
- **Active-book cap** (`top_n`) — RUN at 1: fails `train_strength` **and** the thesis falsifier
  (88% of positive return from one subwindow). Hard-cutting the book to one name re-binds the
  capacity cap by construction, so relief cannot rescue this lever. `top_n` 2 untested.
- **Per-name regime gate** (`confirm_lookback_days`) — RUN at 90. **Falsified on pervasiveness:**
  worst-subwindow PSR collapses to 0.006 and one subwindow supplies 63% of positive return, so two
  nested uptrends turn a trend edge into a bull-regime bet. Buys the shallowest drawdown of any
  deployed row, which does not offset a failed gate.
- **Risk-parity estimator window** (`vol_lookback_days`) — RUN. Interior peak at the 30d
  formation: 30 → 1.003, **60 → 1.036**, 90 → 0.995. The survivor is not pinned to a bound.
- **Ex-ante vol scaling** (`vol_scale`) — inert under `inverse_vol` and `conviction`, which size from
  the same volatility estimate; it only applies under `equal` weighting. Never run here, and it
  cannot apply to any survivor this lifecycle has produced.
- **Across-day smoothing** (`position_smoothing`) — RUN. **2 is the peak at every base tested** —
  the one axis whose optimum did not move. 1 leaves the capacity cap binding at 30d (while
  carrying the best t in the thesis, 2.52), 3 gives back 8.8% of score and 0.28 of t, 5 breaks
  the trade floor.
- **Within-day ramping** (`execution_bars`) — RUN. A saturation curve: 10 is materially worse at
  the 30d formation, 20 and 30 are indistinguishable. Buys participation relief for free, holding
  trade count exactly constant, which is why it beat across-day smoothing as the capacity fix.
- **Hysteresis band** (`signal_band`) — RUN at two levels on two bases, axis closed. 0.05 on the 25d
  capacity-bound base failed the gate; 0.02 on the survivor costs 10.4% of score for a 0.7% cost
  saving. **The premise is wrong, not the sizing:** net per trade is identical with and without the
  band, so zero-crossing decisions are ordinary trades rather than filterable churn.
- **Breadth-conditional gross** (`gross_mode`) — RUN, axis resolved. How hard the book's gross
  leans on the fraction of the universe voting: flat loses 11.7% of score and 0.22 of t, while
  linear and quadratic are statistically indistinguishable (1.0359 vs 1.0371). **Breadth is
  informative** — flattening risk across it de-levers the strong-agreement periods that carry the
  return and raises cost drag by coupling the names — but the optimum is flat between linear and
  quadratic, so the survivor's mode is a coin-flip rather than a finding. **Inert under two-sided
  side logic**, where every name always votes and gross is always 1.0.
- **Exit structure** (`exit_lookback_days`; declared `RiskRule` via `stop_loss_pct`,
  `take_profit_pct`, `trailing_pct`) — **RUN, family closed, all four falsified with distinct
  failure modes.** Holding until the formation horizon turns beats every alternative: a
  faster-horizon exit (−27%) and a trailing barrier (−85%, gate fail) both sell into the reversals
  this edge is paid for holding through, a take-profit (−77%) truncates the continuing-trend tail
  that carries the return, and a fixed stop (−5%) changes drawdown by 0.0005 because portfolio
  path risk is a correlated cross-sectional move, not per-name losses from entry. Params removed
  after the block; evidence retained in the attempt log. See the exit-structure verdict.

**Untested and honestly open:** the regime gate at any base; `gross_mode` active; `signal_band`
under relieved capacity; `weighting` and `signal` re-tested at the 30d base; `top_n` 2; and
`position_smoothing` 1 paired with the 60d estimator (the evidence-quality candidate has not been
refreshed since the estimator moved).

## Iteration budget extensions

Season extended `max_iterations` twice — 10 → 30, then 30 → 50 — to continue this lifecycle
rather than start another, so every attempt stays in one continuous ledger. Only `[loop]` stop-rule
fields changed
(`max_iterations`, `plateau_patience`, `baseline_grace_iterations`); the window, costs, fills,
capacity model, leverage budget, risk budget, objective, and all nine gates are untouched, so
every attempt remains comparable and neither extension is a reseed. At the 30-attempt budget the
protocol was hash-identical to the one the first lifecycle ran under, confirming the budget is the
only field that has ever differed.

Two pieces of generated state have to be hand-edited each time, because the harness has no
supported extend path: `.autoresearch/thesis_lock.json`'s `protocol_sha256` is rebound to the
edited protocol, and the trailing row's `continuation` / `stop_reason` are recomputed from
`terminal` / `max_iterations` to `allowed` / empty. Those two ledger fields are **derived** from the
budget rather than measured, and they are recomputed by calling the harness's own
`_stop_reason_after_attempt` under the new budget, so they hold the value the harness would have
written at the time. No measured field is touched. The missing `loop extend` command is recorded in
`HARNESS_TODO.md`.

### What attempts 11-30 test, and why

**The premise:** a binding capacity cap inverts score ranking — it rewards whichever
configuration is cheapest to deploy over the one with the better edge. That is established here
(gap 3 outranked gap 0 for an entire lifecycle despite lower t). Every lever rejected while the
book was capacity-bound was therefore scored under a distorting constraint, and **score-based
rejection under a binding cap is not falsification.** The survivor now runs with capacity
relieved and 2× headroom, so score comparisons finally track edge quality.

**The cap's distortion is directional, so the suspect list is not uniform.** A binding
participation cap penalises turnover and concentration and *rewards* slowness. Therefore:

- **Genuinely suspect** — the cap worked against them: `top_n` 1 and 2 and `conviction`
  weighting (all concentrate weight into larger per-name positions, which is exactly what the
  ADV cap binds on), `equal` weighting (overweights the thin name), and `ma_cross` (over-trades).
- **Trustworthily rejected** — the cap worked *for* them and they lost anyway: weekly cadence,
  60d formation horizon, and the 60d regime gate all reduce turnover, so relief cannot rescue
  them. Low-value re-tests.
- **Resolved:** two-sided `sign` (attempt-0011).

**Then:** complete the untested-clean neighbourhood above, and combine whatever wins.

**Read every re-test on both axes.** A lever that lowers turnover can raise score purely by
deploying more, which is the same trap in a new guise. A score gain with flat-or-falling t is
deployment, not edge, and must be recorded as such.

### Outcome of attempts 11-30

**Phase A found nothing, and the gains came from interactions instead.** Seven levers rejected under
a binding cap were re-tested: three flipped from gate-failure to gate-pass and four were confirmed,
but **none beat the survivor and no ranking changed**. What did improve the survivor was pairing
levers: formation horizon 30 wins only at wider execution ramping, and the volatility estimator
wants 60 only at the longer horizon. Score 0.977 → **1.036**, t 2.40 → **2.511**.

**The durable methodological lesson: single-lever sweeps around one base mislabel local structure as
general.** Five separate "flat", "saturated", or "insensitive" readings in this thesis turned out to
be base-specific — execution ramping (saturated at 25d, worth +29% at 30d), the formation gap (flat
at 25d, −12.5% at 30d), the volatility estimator (insensitive at 25d, +3.3% at 30d), capacity
headroom as an edge proxy (bracketed by two counterexamples), and the horizon peak itself (25d at
narrow ramping, 30d at wide). Only the smoothing optimum generalised. This is the same class of
error that produced the predecessor's wrong conclusions, without contamination as the cause — so
**every single-lever verdict in this thesis should be read as conditional on its base**, and that
caveat belongs in any offload package.

### What attempts 31-50 test, and why

**The premise:** the book is no longer capacity-bound and the score is full-window total return, so
score now moves on exactly two things — edge quality per unit of risk taken, and how much of the
window carries risk at all. Polishing around the survivor is exhausted: both plateau axes are mapped
closed, and the estimator window is an interior peak. What remains is three classes of question, in
this order:

1. **Levers never run at any base here** — rebalance cadence and the per-name regime gate. An
   untested lever is not a confirmed one, and both change the signal's duty cycle directly.
2. **Duty-cycle and risk-profile levers**, including one new one. `gross_mode` asks whether the
   book's risk should keep scaling with how many names vote; `signal_band` asks whether holding
   through noise beats re-deciding daily, and its only verdict was measured on a capacity-bound
   base where it failed for a reason that no longer applies.
3. **Exit structure**, the one family this thesis has never explored. The book's only exit is the
   trend vote turning, so every position is held on the same horizon that opened it. Two exit
   kinds are available and each is distinct: a data exit (`exit_lookback_days`, an explicit flat
   when a shorter horizon disagrees) and three declared price-path barriers the engine enforces
   (`stop_loss_pct`, `take_profit_pct`, `trailing_pct`). Only two of these were ever tried, both on
   the predecessor's contaminated evidence — and the trailing stop was itself that contaminant, so
   neither verdict survives. `take_profit` has never been tested, and on a trend book it is a
   direct probe of the mechanism: if capping winners *helps*, the continuation claim is weak.
4. **Base-dependence re-tests at the 30d formation with the 60d estimator** — weighting, side
   logic, and the `position_smoothing` 1 evidence candidate, none of which has been measured since
   the base moved. Five of five single-lever verdicts in this thesis proved base-specific, so a
   verdict measured elsewhere is a hypothesis, not a result.

**Read every result on both axes, as before.** A score gain with flat-or-falling t is deployment,
not edge, and must be recorded as such.

## Attempt Log

Compact per-attempt record: lever, mechanism, falsifier, result. `t` = full-window
`train_strength` t-stat (gate needs `R − 2·SE ≥ 0`, i.e. t ≥ 2).

- **attempt-0001 (baseline)** — reproduce the inherited gate-clearing configuration (25d,
  gap 3, daily, `inverse_vol`, no gate, `long_flat`) with the price-path exits deleted.
  **Mechanism:** a determinism control — the same code and params on the same window must
  return the same number, or nothing else this lifecycle measures is trustworthy.
  **Falsifier:** any material deviation from the inherited score. **KEEP, all gates pass.**
  Score **0.28073**, t 2.19 (LCB +0.0074), PF 2.28, DD −0.053, 215 trades, effective symbol
  count 2.89, concentration 0.42, cost-stress retention 0.97. Reproduces the inherited
  configuration to every printed digit, which also proves the three execution-shape params
  are exactly neutral at their defaults and that deleting the exit levers changed nothing.
  Capacity binds as inherited: deployed vol 0.0669 == max feasible, against the 0.15 target.
  **This score is the reference bar for every re-test below.**
- **attempt-0002** — lever: `signal_band` 0 → 0.05 (no-trade band around the sign decision).
  **Mechanism:** whipsaw round-trips through zero collapse into holds, so turnover and its
  capacity participation fall without slowing the formation horizon. **Falsifier:** the band
  cuts at-risk duty faster than it cuts noise, so `train_strength` falls even as per-trade
  quality rises. **DISCARD (edge_unproven), falsifier confirmed.** Score 0.259, LCB −0.0085
  (baseline +0.0074), trades 215 → **83**. Per-trade quality improved sharply — PF 2.28 →
  2.97, avg trade net 0.0013 → 0.0031 — and `book_scale` rose 0.097 → 0.103, but the duty
  loss dominates: `train_strength` is a duty×Sharpe statistic, so a third of the trades
  cannot carry the same t. Hysteresis is a per-trade-quality lever, not a gate lever.
- **Method correction from attempt-0002.** The inherited matched-control read projected a gain
  here and was wrong, for a structural reason: the contaminant's damage is
  turnover-proportional. A 15% trailing stop fires on entries and forces re-entries, so any
  lever that cuts turnover also cuts stop firings and books that relief as apparent alpha.
  Matched-control comparisons are therefore unreliable for any lever that changes turnover.
  **Clean testing went on to discredit the method even for levers thought orthogonal to it** —
  the inherited read put the 30d formation horizon at −43% against its control, where the clean
  number is −10% and gate-clearing. Of the levers re-tested here, only `vol_lookback_days`
  matched its inherited read. The durable lesson is that a contaminant severe enough to fail the
  gate on its own corrupts nearly all inference drawn alongside it, including relative
  comparisons: re-running was the only sound response, and the salvage method should be treated
  as hypothesis generation for ordering re-tests, never as evidence.
- **attempt-0003** — lever: `position_smoothing` 1 → 5 (step 1/5 of the way to each new
  target per rebalance). **Mechanism:** one position change lands in five separate daily
  capacity windows, so the largest single flip no longer pins ADV participation and the book
  can scale toward its volatility target. **Falsifier:** the execution lag costs more edge
  than the added scale is worth. **DISCARD (trade_floor + edge_unproven) — but the mechanism
  works.** `capacity_bound` **true → false**: deployed vol 0.0669 → **0.14999** against the
  0.15 target with headroom above it (max feasible 0.180), `book_scale` 0.097 → **0.328**,
  score 0.281 → **0.802**. It fails because the evidence collapses, not because the edge
  does: trades 215 → **23** (floor 36), min-subwindow trades 1, DD −0.053 → **−0.156**, LCB
  −0.0023. Smoothing never fully flattens, so the book holds persistent partial positions and
  round-trips nearly disappear — PF 8.41 and 3.5% average trade net are that same fact.
  **The capacity pin is relievable from inside the protocol.** The open question is no longer
  whether scale can be deployed but whether it can be deployed on enough trades to prove an
  edge: smoothing buys deployable scale and spends closed-trade evidence, so the next
  attempts search that frontier for a value that clears both gates.
- **attempt-0004** — lever: `position_smoothing` 1 → 2 (the frontier attempt-0003 exposed, at
  the mild end). **Mechanism:** two capacity windows per position change should buy most of the
  participation relief at a fraction of the evidence cost. **Falsifier:** trades fall below the
  floor again, or the gate margin drops. **KEEP — new survivor, all nine gates pass.** Score
  0.281 → **0.510**, LCB +0.0074 → **+0.0095**, trades 70 (floor 36), min-subwindow trades 8,
  `book_scale` 0.097 → 0.179, deployed vol 0.0669 → 0.0974, PF 3.53, DD −0.053 → −0.093,
  worst-subwindow PSR 0.404 → 0.438.
  **Read this as scale, not edge.** Backing the t-stat out of both rows gives t = 2.19 for the
  baseline (R 0.08498, SE 0.03879) and t = 2.19 for this survivor (R 0.10795, SE 0.04923) —
  identical to three digits. Smoothing deploys ~1.85× more of the same edge; the score nearly
  doubles because the score measures total return, and drawdown scales for the same reason. The
  gate margin improved only because R grew slightly faster than its own standard error. No
  claim of a better signal is warranted, and none should reach the offload package.
  Still `capacity_bound = true`, so deployable headroom remains between here and smoothing 5.

- **attempt-0005** — lever: `position_smoothing` 2 → 3 (extend the frontier). **Mechanism:** a
  third capacity window should buy further participation relief while trades stay above the
  floor. **Falsifier:** trades fall through the floor, or the gate margin goes negative.
  **KEEP — new survivor, all nine gates pass.** Score 0.510 → **0.702**, LCB +0.0069, trades
  52, min-subwindow trades 5, `book_scale` 0.179 → 0.258, deployed vol 0.0974 → 0.128 against
  the 0.15 target, PF 3.65, DD −0.093 → −0.125, worst-subwindow PSR 0.438 → 0.465. Still
  `capacity_bound = true`, so full deployment needs either more smoothing or a lever that
  relieves participation without spending round-trips.

Frontier (`position_smoothing`, all else at the survivor base):

| smoothing | score | LCB | t | trades | `book_scale` | deployed vol | DD | capacity bound |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.281 | +0.0074 | 2.19 | 215 | 0.097 | 0.067 | −0.053 | yes |
| 2 | 0.510 | **+0.0095** | 2.19 | 70 | 0.179 | 0.097 | −0.093 | yes |
| 3 | **0.702** | +0.0069 | 2.11 | 52 | 0.258 | 0.128 | −0.125 | yes |
| 5 | 0.802 | −0.0023 | 1.97 | 23 | 0.328 | 0.150 | −0.156 | no |

**How to read the frontier.** Score rises with deployed scale and t falls monotonically past
smoothing 2 (2.19 → 2.19 → 2.11 → 1.97): the edge is not improving anywhere on this curve,
only the fraction of it that gets deployed, and drawdown scales with that fraction. Smoothing 4
would land on the trade floor (~35 against 36) at t ≈ 2.03, so extending the curve further
trades a near-zero gate margin for single-digit score gain — magnitude, not shape, and not
worth an attempt.

Smoothing alone forces a choice between scale and evidence. The within-day lever below removes
that trade-off, so the frontier above is a decomposition record, not a menu of candidates.

- **attempt-0006** — lever: `execution_bars` 1 → 10 (within-day TWAP) on the smoothing-3
  survivor. **Mechanism:** ramping each step across ten one-minute bars relieves per-bar
  participation without removing any flattening, so it should buy the remaining deployment
  without spending round-trips — the one thing smoothing cannot do. **Falsifier:** trades fall,
  or execution lag costs more than the added scale. **KEEP — new survivor, all nine gates pass,
  and the capacity constraint is released.** `capacity_bound` **true → false**, deployed vol
  0.128 → **0.15000** (the full target), `max_feasible_volatility` **0.484** — 3.2× headroom
  above the target. Score 0.702 → **0.850**, LCB +0.0069 → **+0.0081**, t 2.11, trades
  **52 → 52** (unchanged, as the mechanism predicts), PF 3.58, DD −0.125 → −0.146.
  **Capacity is no longer the binding constraint on this book.** What now limits deployment is
  the operator-frozen `target_volatility = 0.15`, with drawdown as the real ceiling: −0.146 at
  0.15 deployed vol implies the 0.25 drawdown gate binds near 0.25 vol. That is a protocol-owned
  risk-appetite question, not an in-loop one.
- **attempt-0007** — lever: `position_smoothing` 3 → 2, holding TWAP 10. **Mechanism:** if
  within-day ramping supplies the participation relief for free, the across-day smoothing that
  spends round-trips should be dialled back to its minimum, recovering evidence at equal scale.
  **Falsifier:** deployment falls back under the cap. **KEEP — survivor, all nine gates pass,
  and it dominates attempt-0006.** Score 0.850 → **0.865**, LCB +0.0081 → **+0.0155** (the best
  gate margin in either lifecycle), t **2.21**, trades 52 → **70**, DD −0.146 → **−0.141**,
  full-train PSR 0.9862, deployed vol **0.15000** with `max_feasible` 0.372 (2.5× headroom).
  Only worst-subwindow PSR is marginally lower (0.464 → 0.441).
  **The decomposition that matters:** across-day smoothing buys participation relief by spending
  round-trips, and within-day TWAP buys it for nothing. So use the minimum smoothing that helps
  and let TWAP carry the rest — smoothing 3 was doing work TWAP does better. Against the
  inherited survivor this is 3.1× the score with more than double the gate margin, while t is
  unchanged at ~2.2 throughout. Nothing here is a better signal.
- **attempt-0008** — lever: `lookback_days` 25 → 30 on the survivor base. **Mechanism:** the
  formation horizon is the thesis's main data-snooping surface, so the neighbour must be probed
  to know whether the survivor sits on a cliff or a plateau. **Falsifier:** the neighbour fails
  the gate, confirming a knife-edge fit. **DISCARD on score, but all nine gates pass.** Score
  0.779 (−10% vs survivor), LCB **+0.0051**, t 2.07, trades 64, full deployment, DD −0.147.
  **The horizon is a plateau, not a knife edge.** The inherited matched-control read put 30d at
  −43% against its control; clean it is −10% and gate-clearing, so that read overstated horizon
  sensitivity just as it overstated the turnover levers — the salvage method is weaker than
  first credited even for levers thought orthogonal to the contaminant. 25d still wins on both
  score and pervasiveness: worst-subwindow PSR 0.441 at 25d against **0.279** at 30d, which is
  the honest reason to prefer it, not the score gap alone.
  **Still open:** the 20d side of the peak is untested clean. The inherited read called it
  catastrophic (≈0.000), but that read is now twice-discredited, so the lower neighbour should
  not be described as falsified.
- **attempt-0009** — intended lever: `skip_days` 3 → 0. **Actually carried two changes:**
  `skip_days` 3 → 0 **and** `vol_lookback_days` 30 → 25, because the edit that restored
  `lookback_days` to 25 also matched `vol_lookback_days` as a substring. The attempt-start param
  delta reported both, so the confound is known and bounded rather than silent.
  **KEEP by score — best row in either lifecycle, all nine gates pass, attribution unresolved.**
  Score **0.969**, LCB **+0.0293**, **t 2.39**, trades 69, full-train PSR 0.9915, worst-subwindow
  PSR 0.464, DD −0.134, full deployment. This is a valid configuration with an invalid lever
  attribution: either change, or both, could be responsible. It is a survivor candidate, never
  evidence about the gap lever or the estimator window.
- **attempt-0010** — lever: `vol_lookback_days` 25 → 30, restoring the estimator window so the
  row differs from attempt-0007 by `skip_days` alone. **Mechanism:** resolve the previous
  attempt's confound and read the gap lever cleanly. **KEEP — final survivor, all nine gates
  pass.** Score **0.9769**, LCB **+0.0303**, **t 2.40**, trades 70, min-subwindow trades 8, DD
  **−0.133**, deployed vol 0.15000 with `max_feasible` 0.299 (2× headroom), full-train PSR
  **0.9918**, worst-subwindow PSR **0.469**, effective symbol count 2.79, concentration 0.463,
  cost-stress retention 0.973.
  **Both attributions resolved.** Against attempt-0007 this is a single lever, `skip_days` 3 → 0:
  score 0.865 → 0.977, LCB +0.0155 → +0.0303, t 2.21 → 2.40. The gap lever earned the entire
  gain. Against attempt-0009 it isolates the estimator window: 0.969 vs 0.977, so
  `vol_lookback_days` is insensitive across 25-30 and 30 is marginally better — the one inherited
  matched-control read that survives clean testing.
  **Why the inherited survivor choice was distorted.** Dropping the gap raises t in both
  lifecycles (2.42 vs 2.19 inherited; 2.40 vs 2.21 here), yet inherited scores ranked gap 3
  *above* gap 0 (0.281 vs 0.249) because gap 3's lower turnover bought more capacity
  (`book_scale` 0.097 vs 0.080) while the book was capacity-bound. **The binding capacity
  constraint was inverting the survivor ranking**, rewarding the weaker edge for being cheaper to
  deploy. Once capacity is relieved, the higher-t configuration also earns the higher return and
  the conflict disappears. The predecessor's preference for gap 0 was therefore right, for a
  reason it never identified, while its stated reason — an isolated overfit spike — was wrong.
- **attempt-0011** — lever: `signal` `long_flat` → `sign` (two-sided). **Mechanism:** two-sided
  trend roughly doubles turnover, so a binding participation cap penalised it hardest; with the
  cap relieved the short side deserves a fair hearing. **Falsifier:** shorts add cost and
  turnover without adding edge. **DISCARD on score — but all nine gates pass.** Score 0.861
  (−12%), LCB **+0.0038**, t 2.06, trades 70 → **363**, full deployment, DD −0.133 → −0.166.
  **The short side is not falsified, and it is not competitive.** Capacity relief flipped the
  verdict from gate failure to gate pass without changing the ranking. What shorts cost is
  visible: PF 3.61 → **1.76**, win rate 0.486 → 0.344, cost drag 0.031 → **0.055**, and
  worst-subwindow PSR 0.469 → **0.091** — one regime subwindow becomes nearly worthless. Return
  spreads more evenly across names (effective symbol count 3.00, concentration 0.339,
  best-subwindow share 0.318), so the weakness is regime pervasiveness, not name concentration.
  Long-only stays correct for a sharper reason than a threshold: shorts dilute t and
  pervasiveness while nearly doubling costs.
- **attempt-0012** — lever: `top_n` 0 → 1 (hold only the strongest-trend name). **Mechanism:**
  concentration was penalised hardest by a binding participation cap, so relief should give it a
  fair hearing. **Falsifier:** breadth is load-bearing, so cutting the active book to one name
  destroys duty and pervasiveness. **DISCARD, `train_strength` fails. Falsifier confirmed, and
  the mechanism premise was wrong.** Score 0.465, LCB **−0.0291**, t 1.56, trades 62, DD −0.144.
  **Concentration does not merely get penalised by the cap — it causes the cap to re-bind.**
  `capacity_bound` returns to **true** with deployed vol 0.133 against the 0.15 target, because
  routing the whole book through one name at a time pushes that name's position back into the ADV
  limit. Relief is therefore irrelevant to this lever; `top_n` cannot escape the constraint.
  **And it fails the thesis falsifier, not just a gate:** `max_positive_subwindow_return_share`
  **0.880** — 88% of positive return from one subwindow — with symbol concentration 0.598 and
  effective symbol count 2.28. Breadth is load-bearing on undistorted evidence, so the inherited
  rejection of `top_n` < 3 stands for a real reason.
- **attempt-0013** — lever: `weighting` `inverse_vol` → `conviction` (tilt toward stronger
  trends). **Mechanism:** the softer form of concentration, which may escape what `top_n`'s hard
  cut could not. **Falsifier:** tilting concentrates return into fewer regimes and costs t.
  **DISCARD, `train_strength` fails. Inherited verdict confirmed.** Score 0.727, LCB **−0.0026**,
  t 1.97, trades 74, DD **−0.114**. Mild concentration does **not** re-bind capacity — deployed
  vol holds at 0.150 with `max_feasible` 0.197 — so the re-binding seen at `top_n` 1 is specific
  to hard-cutting the book. But conviction still loses on edge quality and pervasiveness:
  best-subwindow share 0.456 → **0.699**, effective symbol count 2.79 → 2.50, symbol
  concentration 0.463 → 0.543. It buys a shallower drawdown than the survivor, which does not
  offset a failed gate. Risk parity across the full book is the right allocation shape on
  undistorted evidence.
- **attempt-0014** — lever: `weighting` `inverse_vol` → `equal` (attribution baseline).
  **Mechanism:** quantify what risk parity actually buys once capacity no longer distorts the
  comparison. **DISCARD on score — all nine gates pass.** Score 0.865 (−11%), LCB **+0.0162**,
  t 2.21, trades 69, DD −0.138, full deployment. **Risk parity is worth +0.11 score and +0.19 t**,
  and most of that comes from breadth: effective symbol count 2.79 vs **2.33**, symbol
  concentration 0.463 vs **0.583**, best-subwindow share 0.456 vs 0.546. Equal weighting gives each
  name 1/N regardless of volatility, so the highest-vol name dominates the risk budget. It posts
  the best per-trade economics in the ledger (PF **4.43**, cost drag 0.019 against the survivor's
  0.031) and still loses, which is the cleanest available demonstration that this thesis is paid
  for breadth rather than trade quality.
- **attempt-0015** — lever: `trend_method` `return` → `ma_cross`. **Mechanism:** the estimator
  over-trades, so a binding participation cap punished it; two-sided trend showed 363 trades are
  affordable once relieved, so it deserves a fair hearing. **Falsifier:** a moving-average
  crossover lags the point-to-point return and dilutes the signal. **DISCARD, `train_strength`
  fails. Inherited verdict confirmed, decisively.** Score 0.306 (−69%), LCB **−0.0319**,
  **t 1.36** — the weakest in this lifecycle — PF 1.73, win rate 0.333, worst-subwindow PSR 0.112,
  DD −0.167. The estimator is not salvageable by capacity relief.

**Structural finding — capacity headroom is set by turnover lumpiness, not by edge quality.**
`max_feasible_volatility` is governed by the peak participation of the **largest single position
change**, so it reflects how concentrated a configuration's turnover is, not how good its signal is.

Within a fixed turnover profile, one real mechanism does link the two: a weaker signal realizes
lower book volatility, so the volatility target scales the book **up** to reach 0.15, and the
enlarged positions run into the ADV limit. That produces the apparent ordering t 2.40 → 0.299,
t 2.21 → 0.251, t 2.06 → 0.195, t 1.97 → 0.197, t 1.56 → 0.133, t 1.36 → 0.103.

**But headroom is not a proxy for edge quality, and two counterexamples bracket it.** `blend` has
the worst edge in the ledger (t 0.77) and the *largest* headroom (0.559), because 17 trades over
4.83 years generate almost no participation at any size. A 30d formation at smoothing 1 has the
*best* edge in the ledger (t 2.52) and yet re-binds the cap at 0.122, because a slower formation
concentrates turnover into fewer, larger flips. Read `capacity_bound` as a statement about
execution shape, and diagnose edge quality from t and the subwindow evidence instead.

- **attempt-0016** — lever: `blend` false → true (multi-timescale sign ensemble over
  {20,50,100,200}). **Mechanism:** averaging votes across horizons could stabilise the signal;
  this lever had never been tested outside contamination, so its verdict was unknown rather than
  distorted. **Falsifier:** slow horizons dominate the average and turn the fast edge negative.
  **DISCARD — fails `trade_floor`, `path_risk`, and `train_strength`. Falsified decisively.**
  Score 0.209, LCB **−0.0901**, **t 0.77**, trades **17** against the floor of 36, one subwindow
  with **zero** trades, DD **−0.289** breaching the 0.25 gate, worst-subwindow PSR 0.057, win rate
  0.235. Adding slow horizons converts a daily-response trend book into a near-buy-and-hold one
  that takes crash drawdowns without the trend edge. The inherited "falsified hard" verdict was
  reached on contaminated evidence but is correct.

### Phase A verdict — the lever map re-tested under relieved capacity

Seven levers re-tested. **Three verdicts flipped from fail to pass** (`lookback` 30, two-sided
`sign`, `equal` weighting) — capacity distortion had been inflating "worse" into "failed" — and
**four inherited rejections were confirmed** (`top_n` 1, `conviction`, `ma_cross`, `blend`).
**No lever was rescued into beating the survivor**, and no ranking changed. The survivor's
configuration is correct on every lever tested.

The distortion's practical signature is now precise: it corrupted **pass/fail labels** broadly
while inverting **rank order** in exactly one place — the formation gap, which the preceding
lifecycle already corrected. That is the honest claim for any offload package; "the earlier
lifecycles were wrong" would overstate it.

- **attempt-0017** — lever: `lookback_days` 25 → 20 (the untested lower shoulder of the horizon
  peak). **Mechanism:** the upper neighbour clears the gate, so the lower one may too, which would
  make the peak a genuine plateau. **Falsifier:** a shorter formation window trades noise.
  **DISCARD, `train_strength` fails.** Score 0.599, LCB **−0.0248**, t 1.66, trades 74, PF 2.07,
  worst-subwindow PSR 0.079, DD **−0.240** — within a whisker of the 0.25 gate.
  **The horizon peak is asymmetric, not a plateau:** 20 fails (t 1.66), 25 is the survivor
  (t 2.40), 30 passes at −10% score (t 2.07), and 40/60 failed on inherited evidence. This
  supersedes the plateau reading taken from the upper neighbour alone. The practical consequence
  for downstream review: if the true formation horizon drifts **longer** the edge degrades
  gracefully, and if it drifts **shorter** it breaks — and the short side also runs the drawdown
  gate to its limit. Horizon risk is real and one-sided.
- **attempt-0018** — lever: `skip_days` 0 → 1 (the untested near neighbour of the gap choice).
  **Mechanism:** map the gap curve immediately around the survivor. **DISCARD on score — all nine
  gates pass, and it is nearly indistinguishable.** Score 0.954 (−2.4%), LCB **+0.0274**, t 2.36,
  trades 70, DD −0.140, PF 3.52, full-train PSR 0.9909, worst-subwindow PSR 0.413.
  **The gap lever is a smooth plateau across 0-1**, in clear contrast to the horizon's one-sided
  cliff. A one-day gap costs 2.4% of score and 0.04 of t — inside noise for practical purposes.
  This is the strongest single piece of evidence that the survivor is not a fitted point: its
  nearest neighbour on the gap axis performs essentially identically.
- **attempt-0019** — lever: `position_smoothing` 2 → 1, holding TWAP 10. **Mechanism:** test
  whether across-day smoothing is necessary at all once within-day ramping is in place.
  **Falsifier (predicted):** ADV participation is measured over a daily window, so within-day
  spreading alone should leave the cap binding and deployment near 0.07-0.10.
  **DISCARD on score — all nine gates pass, the prediction was wrong, and this row wins on every
  evidence dimension.** Score 0.827 (−15%), but LCB **+0.0373** and **t 2.43** (both the best in
  this lifecycle), trades **215** (3× the survivor), DD **−0.123** (the shallowest of any fully
  deployed row), full-train PSR **0.9924**, effective symbol count **2.94**, symbol concentration
  **0.402**, and `capacity_bound` **false** with deployed vol 0.150.
  **Across-day smoothing is not required for capacity relief; within-day ramping alone releases
  the cap.** The inherited lesson that TWAP relieves only the per-bar cap and leaves ADV pinned
  came from a contaminated attempt whose stray trailing stop inflated turnover and therefore
  participation. Without the stop, TWAP 10 suffices by itself.
  **What smoothing 2 actually buys is at-risk duty, not capacity.** This row earns a *higher*
  annualized at-risk return (0.211 vs 0.167) while being invested a smaller fraction of the
  window, so the survivor wins total return — the objective — while this row wins return per unit
  of risk taken and carries three times the evidence.

**Two clean candidates, and the choice is not the harness's to make.** The protocol scores total
return, so attempt-0010 is correctly the frozen survivor. Attempt-0019 is simpler (one execution
lever instead of two), better on t, LCB, PSR, drawdown, breadth, and concentration, and has 3× the
closed trades — which is what an OOS test actually consumes. Both belong in any offload package
with this trade-off stated: **0010 maximises deployed money, 0019 maximises evidence quality and
minimises drawdown.** Do not silently promote one.

- **attempt-0020** — lever: `execution_bars` 10 → 20 on the survivor base. **Mechanism:** impact
  cost scales as participation^0.5, so wider within-day spreading should trim it. **KEEP by score,
  but a saturated lever rather than a gain.** Score 0.9769 → **0.9802** (+0.34%), LCB +0.0303 →
  +0.0307, t 2.401 → 2.407, trades 70 unchanged, DD −0.1326 → −0.1317, PF 3.64. Every field is
  within noise of the row it replaced. The mechanism is real but exhausted: ten minutes of
  ramping already captured the relief, and the twentieth minute adds a rounding error. Recorded
  as the lever's saturation point, not as an improvement — pushing it to 30 would be magnitude
  tuning, which the operating contract explicitly rejects.
- **attempt-0021** — lever: `position_smoothing` 2 → 1 at `execution_bars` 20 (the
  evidence-quality candidate, re-run at the wider ramping). **DISCARD on score — all nine gates
  pass, and this is the best evidence row in the ledger.** Score 0.834, LCB **+0.0384**,
  **t 2.442**, trades 215, DD **−0.123**, full-train PSR **0.9926**, effective symbol count 2.935,
  concentration 0.403, `max_feasible` 0.323. Ramping 20 reproduces the same saturation seen on the
  survivor base: a fraction of a percent over ramping 10.

### The smoothing trade-off at the 25d base, measured

Both rows sit at `execution_bars` 20 and differ **only** in `position_smoothing`, so the trade-off is
measured rather than inferred. Both are superseded as candidates — the surviving pair is stated in
*The two candidates* at the end of this log — but the trade-off itself is the cleanest measurement of
what across-day smoothing costs and buys:

| | attempt-0020 (smoothing 2) | attempt-0021 (smoothing 1) |
| --- | --- | --- |
| score (objective) | **0.980** | 0.834 |
| t | 2.407 | **2.442** |
| `train_strength` LCB | +0.0307 | **+0.0384** |
| closed trades | 70 | **215** |
| max drawdown | −0.132 | **−0.123** |
| full-train PSR | 0.9919 | **0.9926** |
| effective symbol count | 2.784 | **2.935** |
| deployed vol | 0.150 | 0.150 |

**Across-day smoothing 2 buys +17.6% total return and costs 0.035 of t, 145 closed trades, and
0.009 of drawdown** — the return-versus-evidence exchange rate on this axis, and the reason smoothing
2 is carried by both surviving candidates.

- **attempt-0022** — lever: `lookback_days` 25 → 30 on the evidence candidate (smoothing 1,
  ramping 20). **Mechanism:** horizon is the asymmetric-risk lever, so the second candidate needs
  its own horizon check rather than inheriting the survivor's. **DISCARD on score — all nine gates
  pass, and it posts the best risk-adjusted evidence in the ledger.** **t 2.522** (highest), LCB
  +0.0369, DD **−0.0858** (shallowest of any deployed row), full-train PSR **0.9941** (highest),
  worst-subwindow PSR 0.474, trades 192, PF 2.74. Score 0.675 (−19%) for one reason only:
  `capacity_bound` returns to **true** at deployed vol 0.122 against the 0.15 target, because a
  slower formation concentrates turnover into fewer, larger flips and raises peak participation.
  **The edge here is the best measured in this thesis and its only deficiency is deployment**,
  which across-day smoothing is already known to fix — so the combination is worth testing.
  Note the attempt-start delta reported two changes against the frozen survivor
  (`lookback_days` and `position_smoothing`). That is expected while a second candidate is being
  mapped: the guard anchors on the score-best row, so any exploration of the other candidate's
  neighbourhood shows an extra delta by construction.
- **attempt-0023** — lever: `position_smoothing` 1 → 2 at `lookback` 30, ramping 20 (the
  combination the previous attempt pointed at). **Mechanism:** that row carried the best edge
  quality in the thesis and failed only on deployment, and smoothing 2 is the lever proven to fix
  deployment; the question is whether both properties survive together. **KEEP — new survivor, and
  they do.** Score **1.0031** (the first above 1.0), LCB **+0.0350**, **t 2.459**, DD **−0.1164**,
  PF **4.99**, full-train PSR **0.9930**, `max_feasible` **0.370**, deployed vol 0.150, trades 64.
  Better than the row it replaced on score, gate margin, t, drawdown, per-trade economics, PSR, and
  headroom at once; only worst-subwindow PSR gives ground (0.466 → 0.414).
  **Two earlier readings need revising, and they are the same finding.** The horizon optimum
  *interacts with* execution ramping: at ramping 10, 30d loses to 25d (0.779 vs 0.865, t 2.07 vs
  2.21); at ramping 20, 30d wins (1.003 vs 0.980, t 2.459 vs 2.407). Consequently the "ramping is a
  saturated lever" conclusion was base-specific — worth +0.34% at 25d and **+29%** at 30d. These
  levers are not separable, and single-lever sweeps around one base cannot find the joint optimum.
  **Caution attached to this survivor:** it was reached by search rather than predicted, so its
  neighbourhood must be mapped before it is trusted. The snooping exposure is bounded — 30d is
  inside the a-priori 25-30d formation range, and ramping is an execution parameter rather than a
  signal one — but "found by combination search" is a materially weaker provenance than
  "a-priori config confirmed", and downstream review must be told which it is.
- **attempt-0024** — lever: `lookback_days` 30 → 40 on the new survivor base (the upper shoulder).
  **Mechanism:** map the horizon around a survivor found by combination search before trusting it.
  **DISCARD, `train_strength` fails.** Score 0.455, LCB **−0.0444**, t 1.426, trades 54, PF 2.26,
  worst-subwindow PSR 0.113, DD −0.203.
  **The horizon map at the survivor's execution regime is now closed on the upper side:** 25 passes
  (t 2.407), 30 is the survivor (t 2.459), 40 fails (t 1.426), and 20 failed at the narrower ramping
  (t 1.66). **The edge lives in the a-priori 25-30d window and breaks outside it on both sides.**
  The plateau is only two grid points wide, but it coincides exactly with the formation range
  specified before any searching — which is the opposite of a snooped peak, and the strongest
  provenance argument available for this survivor.
- **attempt-0025** — lever: `execution_bars` 20 → 30 on the survivor base. **Mechanism:** ramping
  20 beat ramping 10 by 29% at this horizon, so it must be shown to be a plateau point rather than
  a lucky one, or the survivor is an artifact of two interacting levers. **DISCARD on score by
  0.1% — all nine gates pass, and it is a near-exact match.** Score 1.0021 vs 1.0031, LCB +0.03483
  vs +0.03498, t 2.457 vs 2.459, trades 64 unchanged, DD −0.1156, PF 5.00, PSR 0.99293.
  **Ramping 20 is a plateau, not a spike.** The ramping axis steps between 10 and 20 and then runs
  flat from 20 to 30 — a saturation curve.

**The survivor sits on a two-dimensional plateau.** Formation horizon: 25 passes, 30 is the peak,
20 and 40 fail. Execution ramping: 20 and 30 are indistinguishable, 10 is materially worse at this
horizon. Both plateau points on the horizon axis fall inside the a-priori 25-30d range. That is the
robustness case for a survivor reached by combination search, and it is evidence rather than
assertion.

- **attempt-0026** — lever: `lookback_days` 30 → 20 at ramping 20 (close the horizon map at the
  survivor's own execution regime, since the 20d failure was measured at the narrower ramping and
  ramping is known to interact with horizon). **DISCARD, `train_strength` fails, and it fails
  identically to the ramping-10 version:** score 0.602 vs 0.599, LCB −0.0244 vs −0.0248, t 1.668 vs
  1.662, worst-subwindow PSR 0.080, DD −0.239. **Ramping does not rescue a short horizon** — the
  horizon-ramping interaction is specific to the 30d pair, where a slower formation needs wider
  ramping to deploy, and is not a general effect. Horizon map at the survivor's regime, closed on
  both sides: 20 → t 1.67 fail, 25 → t 2.407 pass, 30 → t 2.459 survivor, 40 → t 1.43 fail.
- **attempt-0027** — lever: `skip_days` 0 → 1 on the new survivor base. **DISCARD on score — all
  nine gates pass.** Score 0.878 (−12.5%), LCB +0.0187, t 2.246, trades 64, DD −0.136, PF 4.49,
  worst-subwindow PSR 0.300. **The gap lever's flatness is base-dependent:** at 25d a one-day gap
  cost 2.4% of score and 0.04 of t; at 30d it costs 12.5% and 0.21 of t. A longer formation already
  excludes recent noise, so adding a gap over-excludes. Gap 0 is confirmed at the new base, and the
  earlier "smooth plateau across 0-1" reading belongs to the 25d horizon specifically.
- **attempt-0028** — lever: `position_smoothing` 2 → 3 on the new survivor base. **DISCARD on score
  — all nine gates pass.** Score 0.915 (−8.8%), LCB +0.0168, t 2.230, trades 48, DD −0.136,
  PF 4.57, worst-subwindow PSR 0.352, `max_feasible` 0.488. **Smoothing 2 is still the peak at the
  longer horizon**, so this axis's optimum did not move with the formation window — the one "flat"
  reading in this lifecycle that generalises rather than being base-specific. Smoothing map at 30d
  and ramping 20: 1 is capacity-bound (0.675, though it carries the best t in the thesis at 2.52),
  2 is the survivor (1.003, t 2.46), 3 gives back scale and t (0.915, t 2.23).
- **attempt-0029** — lever: `vol_lookback_days` 30 → 60 on the new survivor base. **KEEP — new
  survivor.** Score 1.0031 → **1.0359** (+3.3%), LCB +0.0350 → **+0.0389**, **t 2.511**, full-train
  PSR 0.9930 → **0.9939**, PF 4.98, DD −0.117, trades 64, `max_feasible` 0.373, deployed 0.150.
  **The fifth base-dependent lever.** The estimator window was recorded as insensitive across 20-60
  from the 25d base, where 25 and 30 differed by 0.8%; at the 30d formation, 60 beats 30 by 3.3%.
  A longer formation window pairs with a longer volatility estimator. The reading was not wrong at
  the base where it was measured — it simply does not transfer.
- **attempt-0030** — lever: `vol_lookback_days` 60 → 90 (the top of the bounded range).
  **Mechanism:** the survivor had just moved to 60, so it must be shown to be an interior optimum
  rather than a configuration still climbing toward a boundary. **DISCARD on score — all nine gates
  pass.** Score 0.995 (−4%), LCB +0.0339, t 2.445, trades 64, DD −0.118, PF 4.89.
  **The estimator window is an interior peak:** 30 → 1.003, 60 → **1.036**, 90 → 0.995. The
  survivor is not pinned against a bound, so its optimum lies inside the searched range.
- **attempt-0031** — lever: `rebalance_days` 1 → 2, a lever never run at any base in this
  lifecycle. **Mechanism:** a 30d formation barely changes day to day, so re-deciding every second
  day should halve decision events and their cost drag without slowing the formation horizon.
  **Falsifier:** a slower clock delays exits, so drawdown worsens and evidence thins.
  **DISCARD on score — all nine gates pass, and the falsifier is confirmed.** Score 0.865 (−16.5%),
  LCB +0.0105, t **2.143**, trades **39** against a floor of 36, min-subwindow trades 4,
  DD −0.117 → **−0.148**, worst-subwindow PSR 0.417 → 0.344, full-train PSR 0.9939 → 0.9839.
  **Daily is confirmed, and the result contains a structural read worth more than the verdict:
  this thesis is not cost-constrained.** The slower clock delivered exactly the economics it
  promised — profit factor 4.98 → **5.50**, net per trade 0.0163 → **0.0223**, cost drag 0.0281 →
  **0.0209** — and still lost 16.5% of score and 0.37 of t. Saving 0.007 of return in costs cost
  0.17 in return from timing. Response speed dominates cost drag by more than an order of
  magnitude here, so **further turnover reduction is not a productive direction** on this thesis,
  which also explains why the smoothing optimum sits at 2 rather than higher.
- **attempt-0032** — lever: `gross_mode` `universe` → `active`, a new lever. The book's gross has
  always scaled linearly with breadth (one of three names voting deploys a third of the budget,
  the rest sits in cash); `active` renormalizes across the voting names so gross holds at the full
  budget at any breadth. **Mechanism:** per-period risk currently varies for a reason unrelated to
  signal quality, and equalizing risk across time is the standard argument for a higher Sharpe.
  **Falsifier:** breadth is genuinely informative, so flattening risk across it moves capital into
  the weakest periods. **DISCARD on score — all nine gates pass, and the falsifier is confirmed.**
  Score 0.914 (−11.7%), LCB +0.0220, t **2.292**, trades 62, DD −0.125, full-train PSR 0.9890.
  **Breadth is informative, not a mechanical artifact, and breadth-neutrality is expensive twice
  over.** First, the global vol target scaled the book down 0.274 → **0.221** to absorb the extra
  risk taken in low-breadth periods, so the strong-agreement periods that carry the return were
  *de*-levered to pay for it. Second, cost drag rose 0.0281 → **0.0399** (+42%) on **fewer** trades
  (64 → 62): renormalizing couples the names, so every name entering or leaving resizes every
  standing position. Effective symbol count is unchanged (2.736), so this is not a concentration
  story — the natural idle sleeve is a feature. Worst-subwindow PSR did improve slightly
  (0.417 → 0.438), which is the one thing risk-flattening bought.
  **This is the first result that points at a lever rather than away from one:** if low-breadth
  periods are the weak ones, leaning risk further *toward* agreement should pay. Tested next.
- **attempt-0033** — lever: `gross_mode` `universe` → `tilted`, making gross quadratic in breadth
  rather than linear, so risk leans into cross-name agreement (one name voting deploys a ninth of
  the budget instead of a third). **Mechanism:** the previous attempt measured low-breadth periods
  as the weak ones, so treating breadth as conviction in a common trend should pay. **Falsifier:**
  the linear profile is already optimal and further tilt just concentrates into fewer periods.
  **KEEP — new survivor, and the thinnest one in the ledger.** Score 1.0359 → **1.0371** (+0.12%),
  LCB +0.0389 → **+0.0409**, t 2.511 → **2.533**, full-train PSR 0.9939 → **0.9942**, trades 66,
  DD −0.119, deployed 0.150.
  **Direction confirmed, magnitude immaterial — and the distinction matters.** The gain cleared the
  protocol's `min_abs_improvement` floor of 0.001 by 0.00025, so the harness correctly promoted it,
  but +0.12% of score is not a finding. **What is a finding is that the breadth axis is now
  resolved and its optimum is nearly flat on the tilt side:** flat costs 11.7%, linear and
  quadratic are statistically indistinguishable. Pushing to a cubic would be exponent-fitting with
  no new mechanism, so the axis is closed here. Downstream review should treat the survivor's
  breadth mode as a coin-flip between linear and quadratic, not as evidence for quadratic.
  Book scale rose 0.274 → **0.300** (backing out of weak periods lets the vol target lift the whole
  book) while headroom fell 0.373 → 0.338 (breadth changes now move positions further). The
  per-trade signature is consistent: win rate 0.531 → **0.455** with profit factor unchanged at
  4.96 — fewer winners, bigger ones, which is what leaning into strong trends should look like.

**Exit structure (attempts 0034-…).** The book's only exit had always been the trend vote turning,
so every position was held on the horizon that opened it. Two exit kinds exist: a data exit
(`exit_lookback_days`, an explicit flat while a shorter horizon disagrees) and three declared
price-path barriers the engine enforces intrabar against the entry mark (`stop_loss_pct`,
`take_profit_pct`, `trailing_pct`). Adding the surface moved `complexity_count` 16 → 20; if the whole
family fails, the params come back out, since carrying four dead levers is a real complexity cost.

- **attempt-0034** — lever: `exit_lookback_days` 0 → 10, a faster-horizon exit on the 30d formation
  (a 1/3 fast/slow ratio fixed a priori, not searched). **Mechanism:** trend following is
  conventionally paid for cutting losers before the slow signal concedes, so entry and exit need not
  share a horizon. **Falsifier:** inside a 30d uptrend, a negative 10d return is noise, so exiting on
  it sells into reversals and re-enters higher. **DISCARD on score — all nine gates pass, and the
  falsifier is confirmed decisively.** Score 0.756 (−27%), LCB +0.0101, t **2.127**, trades 66 → 81,
  DD −0.139, worst-subwindow PSR 0.408 → 0.317.
  **The fast exit cuts winners, not losers, and the per-trade tape is unambiguous:** profit factor
  4.96 → **2.78** (halved), net per trade 0.0158 → **0.0093** (−41%), cost drag 0.0268 → **0.0436**
  (+63%) on 23% more trades. Turnover up, quality down — the signature of selling into noise and
  buying back.
  **This is the mechanism's own prediction, and it now has direct evidence.** The thesis says these
  instruments under-react then over-react, so the edge *is* holding through short-horizon
  reversals; an exit that fires on any 10-day dip harvests the reversal instead of the trend. Read
  with attempt-0031 the pair is sharp: slowing the decision clock loses timing, and speeding up
  exits loses trend. The 30d holding period is not too long, and the surviving book's exit rule —
  wait for the formation horizon itself to turn — is load-bearing rather than incidental.
  **It does not pre-falsify the price-path barriers.** This lever fired on *any* negative 10d
  return; a stop or trailing barrier fires only on a large adverse move, so the two ask different
  questions and the barriers still deserve their own attempts.
- **attempt-0035** — lever: `trailing_pct` 0 → 0.15, a declared trailing barrier sized a priori at
  roughly 1.5× the 10-day noise of a 60%-vol crypto major. **Mechanism:** a ratcheting barrier
  should give back part of a trend rather than all of it, converting open profit into realized
  profit on a genuine break. **Falsifier:** a 15% retracement from a running peak is ordinary
  crypto behaviour, so the barrier fires inside live trends and latches the book flat.
  **DISCARD — `train_strength` fails, and this is the worst row in the lifecycle. Falsified
  decisively.** Score **0.157** (−85%), LCB **−0.0107**, t **1.578**, full-train PSR 0.9425.
  **It fails on two independent channels, and the trade tape shows both.** Edge first: trades 66 →
  **257** (3.9×) with net per trade collapsing 0.0158 → **0.00062** (−96%) and profit factor 4.96 →
  **1.76**. The barrier measures retracement from the peak *since entry*, so on a multi-week hold
  the peak ratchets up and an ordinary 15% pullback closes a position that the trend signal still
  likes. Capacity second: 257 trades pin the participation cap, so `capacity_bound` returns to
  **true** and deployed volatility collapses to **0.049** against the 0.15 target — the book can
  only put a third of its risk budget to work.
  **The apparent drawdown benefit is an artifact of not deploying, and this is the number that
  matters for the vol-target question.** Drawdown looks 57% shallower (−0.119 → −0.0518), but per
  unit of deployed volatility it is *worse*: 0.0518/0.049 = **1.06** against the survivor's
  0.119/0.150 = **0.79**. So a trailing barrier cannot buy drawdown headroom to spend on a higher
  `target_volatility`; it buys less return per unit of drawdown, not more.
- **attempt-0036** — lever: `stop_loss_pct` 0 → 0.15, a fixed barrier measured from the entry mark
  rather than from a ratcheting peak, so a position up 40% and retracing 20% survives it.
  **Mechanism:** isolate "cut bad entries" from "give back open profit" — the classic stop argument
  is about the former, and the trailing test could only speak to the latter. **Falsifier:** the
  drawdown this book takes is a portfolio-level correlated move, not an accumulation of per-name
  losses from entry, so a per-name stop will not touch it. **DISCARD on score — all nine gates
  pass, and the falsifier is confirmed in the cleanest possible form.** Score 0.984 (−5.1%),
  LCB +0.0345, t **2.449**, trades 66 → 101, deployed 0.150 with `capacity_bound` false.
  **Drawdown is unchanged to three decimal places: −0.1192 → −0.1197.** The stop fired 35 extra
  times, cost 5.1% of return and 38% of net per trade (0.0158 → 0.0098), and bought **zero**
  drawdown reduction. That is the whole finding: this book's path risk is a correlated
  cross-sectional move under a global volatility target, while a stop is a per-name device measured
  from each entry, so the two do not meet. Unlike the trailing barrier it is not destructive —
  capacity stays relieved, the book still deploys the full target, and all nine gates pass — it is
  simply an expense that buys nothing.
  **Together with attempt-0035 this closes the price-path family for the purpose it was tested
  for.** Neither barrier reduces drawdown per unit of deployed volatility, so **no in-protocol exit
  lever relaxes the drawdown ceiling on the `target_volatility` axis.** The reachable vol range is
  set by the raw path risk of the edge itself.
- **attempt-0037** — lever: `take_profit_pct` 0 → 0.30, capping each position at a 30% gain from
  entry. **Mechanism:** not a tuning knob but a probe of the thesis itself — crypto trends routinely
  run 50-100%, so if truncating them *helps*, the continuation claim this edge rests on is weaker
  than the ledger suggests. **Falsifier:** the return comes from a minority of large continuing
  trends, so capping them destroys the edge. **DISCARD on score — gates pass on a hairline
  (LCB +0.0011), and the falsifier is confirmed.** Score **0.235** (−77%), t **2.040**, trades 112.
  **The probe answers in the thesis's favour, which makes this a failure worth having.** Win rate
  *rose* 0.455 → **0.518** — capping gains converts more trades into winners — while profit factor
  collapsed 4.96 → **2.22** and net per trade fell 0.0158 → **0.0021** (−87%). More winners, far
  less money: the edge is concentrated in the tail of continuing trends, exactly as an
  under-react/over-react mechanism predicts. Continuation past +30% is load-bearing, not incidental.
  **And it exposes the interaction that explains three of these four failures.** A fired barrier
  latches the instrument flat until a different target is emitted, so the book sits out long
  stretches; realized volatility falls, the global vol target scales the surviving positions up to
  reach 0.15, and the enlarged positions hit the ADV limit. `capacity_bound` returns to **true** at
  deployed volatility **0.055**. **Any exit that lowers duty cycle is therefore capacity-penalized
  twice** — once in lost time at risk, once in the participation cap it re-binds.

### Exit structure verdict — the family is closed

Four exit devices, four falsifications, four *different* failure modes:

| lever | score | t | why it fails |
| --- | --- | --- | --- |
| `exit_lookback_days` 10 | 0.756 | 2.127 | sells into short-horizon reversals; PF halves |
| `trailing_pct` 0.15 | **0.157** | 1.578 | peak ratchets, fires inside live trends; capacity re-binds |
| `stop_loss_pct` 0.15 | 0.984 | 2.449 | costs 5%, buys **zero** drawdown reduction |
| `take_profit_pct` 0.30 | 0.235 | 2.040 | truncates the continuing-trend tail that carries the return |

**The surviving book's exit rule — hold until the formation horizon itself turns — beats every
alternative the surface affords, and now for stated reasons rather than by omission.** Two
generalizations fall out. First, this edge is paid for *holding through* adverse short-horizon price
action, so any device that reacts to price faster than the formation horizon harvests the reversal
instead of the trend. Second, drawdown here is a portfolio-level correlated move under a global
volatility target, so per-name entry-relative barriers cannot address it — the fixed stop
demonstrates this in isolation, changing drawdown by 0.0005 while costing 5% of return.

The four params were removed after this block: the executable strategy is byte-identical to the
survivor's snapshot again, and `complexity_count` returns 20 → 16. The evidence lives here and in
the attempt-0034 to attempt-0037 snapshots, so nothing is lost by not carrying dead levers.

- **attempt-0038** — lever: `confirm_lookback_days` 0 → 90, a per-name slow-regime gate, and the
  last lever that had never been run at any base in this lifecycle. **Mechanism:** a long is taken
  only in a 90d uptrend, so the book trades with the major trend and sits out whipsaw regimes.
  **Falsifier:** the gate concentrates return into sustained bull regimes, making the edge
  regime-conditional rather than pervasive. **DISCARD — `train_strength` fails, and the falsifier is
  confirmed on the axis that matters most for this thesis.** Score 0.507 (−51%), LCB **−0.0235**,
  t **1.733**, trades 48.
  **It fails on pervasiveness, not on return, and that is the damning part.** Worst-subwindow PSR
  collapses 0.408 → **0.0063** and one subwindow supplies **63%** of positive return (up from 45%) —
  moving toward the thesis's own falsifier, which rejects an edge whose return concentrates in a
  single mega-trend window. Requiring two nested uptrends restricts the book to bull regimes, so
  what survives is a bull-market bet rather than a trend edge. The inherited "gate off wins" verdict
  is now confirmed clean, and for a reason the predecessor never identified: it is a pervasiveness
  failure, not a return shortfall. It does buy the shallowest drawdown of any fully deployed row
  (−0.1117) and the highest headroom (`max_feasible` 0.395), neither of which offsets a failed gate.
  **This is the fifth independent confirmation of the same structural fact: duty cycle is what this
  book is paid for.** A slower clock (−16.5%), a faster exit (−27%), a take-profit (−77%), a
  trailing barrier (−85%), and now a regime gate (−51%) all reduce time at risk, and all lose. No
  lever that lowers duty has ever won here, while every winning lever preserved duty and improved
  shape. That is now a prior strong enough to rank the remaining candidates by.
- **attempt-0039** — lever: `signal_band` 0 → 0.02, a no-trade band around the zero crossing. Chosen
  light: at a 30d formation a typical absolute return is ~15%, so 2% touches only near-zero
  decisions. **Mechanism:** the one turnover-reducing device that should *raise* duty rather than
  lower it — inside the band a name holds its standing vote, so whipsaw round-trips through zero
  collapse into holds. **Falsifier:** near-zero crossings are ordinary trades, not noise, so removing
  them removes value. **DISCARD on score — all nine gates pass, and the falsifier is confirmed by an
  unusually clean decomposition.** Score 0.929 (−10.4%), LCB +0.0289, t **2.373**, trades 66 → 59.
  **The trades the band removes are worth exactly as much as the ones it keeps.** Net per trade is
  *identical* to the survivor's at **0.0158**, profit factor holds at 4.77 vs 4.96, and cost drag
  actually improves 27% (0.0268 → 0.0197) — yet score falls 10.4% while trade count falls 11%. Total
  return tracks trade count almost exactly, which is what it looks like when a filter removes
  average-value activity rather than junk. Pervasiveness even improves (worst-subwindow PSR 0.408 →
  **0.459**, the best of the recent rows) and drawdown worsens mildly (−0.119 → −0.131).
  **So the hysteresis premise is wrong for this thesis, not just mis-sized.** Zero-crossing decisions
  are not low-quality churn to be filtered; they are ordinary trades, and the band is a 10% tax for
  a cost saving worth 0.7%. Read with the 0.05 band tested on the 25d base, the axis now loses at two
  levels on two different bases, which closes it.
- **attempt-0040** — lever: `signal` `long_flat` → `sign` (two-sided), the only lever available that
  *raises* duty cycle: a two-sided book is invested at all times instead of standing flat whenever a
  name's trend is down. **Mechanism:** five levers had by then shown that this book is paid for time
  at risk, and this is the direct test of that prior. **Falsifier:** shorts add cost and turnover
  without adding edge — which is exactly what they did at the 25d base, losing 12% with
  worst-subwindow PSR at 0.091. **KEEP — new survivor, and the sixth base-dependent verdict.**
  Score 1.0371 → **1.0468** (+0.94%), ten times the improvement floor.
  **This is a deployment gain, not an edge gain, and the ledger's own rule requires saying so.**
  Every risk-adjusted measure moved the wrong way: t 2.533 → **2.346**, LCB +0.0409 → **+0.0239**,
  full-train PSR 0.9942 → 0.9905, worst-subwindow PSR 0.408 → 0.375, profit factor 4.96 → **1.92**,
  net per trade 0.0158 → **0.0029**, cost drag 0.0268 → **0.0524** (double), cost-stress retention
  0.978 → 0.959. The score rose because the book is never flat, not because the signal improved.
  **But the robustness profile improved substantially, and in ways an OOS test consumes directly:**
  trades 66 → **345**, min-subwindow trades 6 → **44**, effective symbol count 2.70 → **2.99**,
  symbol concentration 0.484 → **0.350**, and best-subwindow return share 0.455 → **0.334** — return
  is far more evenly spread across both names and regimes. Drawdown is unchanged (−0.120).
  **Two consequences for how the rest of this lifecycle is read.** First, `gross_mode` is now inert:
  under two-sided voting every name always votes ±1, so breadth is always the full universe, gross is
  always 1.0, and the tilt that won attempt-0033 does nothing here — the survivor no longer depends
  on that choice. Second, this is a genuine fork rather than a ranking: long-only maximizes edge
  quality per unit of risk taken, two-sided maximizes total return, evidence count, and dispersion.
  The protocol scores total return, so the harness is right to promote it, and downstream review must
  be handed both with the trade-off stated.
- **attempt-0041** — lever: `position_smoothing` 2 → 3 on the two-sided survivor. **Mechanism as
  predicted:** cost drag had just doubled to 0.052 on 345 trades, and a two-sided book was expected
  to hold full gross at any smoothing, making this the one case where cutting turnover costs no duty.
  **DISCARD on score — all nine gates pass, and the prediction was wrong.** Score 0.922 (−11.9%),
  LCB +0.0107, t **2.156**, trades 345 → 241, DD −0.120 → −0.137, worst-subwindow PSR 0.375 → 0.312.
  **The reasoning error is worth recording because it sharpens the duty rule.** Smoothing ramps each
  name *toward* its new target, so a +1 → −1 side flip passes gradually through zero: for three
  rebalances that name sits at partial or no exposure. Two-sided voting keeps a name always
  *wanting* full exposure, but smoothing still removes exposure exactly when a flip is underway, so
  duty falls after all. Cost drag did fall as predicted (0.0524 → 0.0442, −16%) and net per trade
  improved 25% — and the row still lost 11.9%, which is the same cost-versus-timing verdict
  attempt-0031 reached.
  **Smoothing 2 is now the peak at three separate bases** (25d long-only, 30d long-only, 30d
  two-sided). It remains the only axis in this thesis whose optimum has never moved with the base.
- **attempt-0042** — lever: `lookback_days` 30 → 25 on the two-sided survivor, starting the
  neighbourhood map a survivor reached by a lever change requires. **DISCARD on score — all nine
  gates pass.** Score 0.935 (−10.7%), LCB +0.0119, t **2.173**, trades 377, DD −0.120 → **−0.164**.
  **This row explains why two-sided flipped from losing to winning, and the answer is the horizon,
  not the base as a whole.** Worst-subwindow PSR collapses 0.375 → **0.097** at 25d — and the
  earlier 25d two-sided row measured 0.091 under a completely different secondary configuration
  (30d estimator, linear gross, ramping 10). Two independent measurements of 25d two-sided give
  ~0.09; 30d two-sided gives 0.375. **The short side needs the longer formation to be pervasive:**
  at 25d shorts concentrate their return into one regime, at 30d they do not. So the flip in the
  side-logic verdict is attributable to a single interacting lever rather than to the accumulated
  base, which is a stronger and more transferable statement.
  The horizon penalty is also much steeper two-sided than long-only: 25 costs 2.3% of score
  long-only and **10.7%** two-sided. Adding shorts makes the book more horizon-sensitive, which is
  a risk downstream review should carry — the two-sided candidate sits on a narrower plateau.
- **attempt-0043** — lever: `lookback_days` 30 → 40 on the two-sided survivor, closing the horizon
  map upward. **Mechanism, and a real hypothesis rather than grid completion:** if longer formations
  make shorts more pervasive, 40d should extend that, and it halves flip frequency, which attacks
  the cost drag that doubled when shorts came in. **DISCARD — `train_strength` fails, and the
  hypothesis is falsified.** Score **0.304** (−71%), LCB **−0.0524**, t **1.101**, profit factor
  **1.36**, net per trade **0.00095**, DD −0.178, full-train PSR 0.864, and `capacity_bound` returns
  to **true** at deployed 0.126 as fewer, larger flips concentrate participation.
  **Longer does not help the short side; it destroys the signal.** The pervasiveness gain from 25d →
  30d does not continue to 40d — worst-subwindow PSR is 0.278, and the edge itself is gone.

- **attempt-0044** — lever: `execution_bars` 20 → 30 on the two-sided survivor. **Mechanism:**
  ramping is the only lever that has ever bought participation relief for free, holding trade count
  exactly constant, and two-sided runs 5× the turnover with headroom cut from 0.338 to 0.233.
  **DISCARD on score by 0.6% — all nine gates pass, and it is a near-exact match.** Score 1.0407 vs
  1.0468, LCB +0.0233 vs +0.0239, t 2.337 vs 2.346, trades **345 unchanged** (as ramping always
  leaves them), DD −0.1200, profit factor 1.916. Ramping is saturated past 20 at this base too.
  **The reportable number is not the score but the headroom: `max_feasible_volatility` 0.233 →
  0.179.** Wider within-day spreading did not raise capacity here, which locates the binding
  constraint: at two-sided turnover the daily ADV cap binds, not the per-bar cap, so spreading
  *within* the day cannot relieve it and only reshuffles the daily profile. Ramping 20 stays correct.
  **This is the finding that decides the vol-target reseed between the two candidates**, and it is
  recorded in `reseed_log.md`: the two-sided survivor has only 1.19× capacity headroom above the
  0.15 target (max feasible 0.179 at ramping 30, 0.233 at ramping 20), while the long-only candidate
  has 2.25× (0.338). Since both carry the same drawdown (−0.12), the long-only book can be scaled to
  roughly 0.30 volatility before either limit binds and the two-sided book only to about 0.23. The
  score-leading candidate is therefore the *worse* base for the one reseed axis this thesis has
  earned.

- **attempt-0048** — lever: `lookback_days` 30 → 35 on the two-sided survivor. **Purpose stated
  before the run:** not to hunt a better peak but to measure how wide the cliff between 30 (survivor)
  and 40 (outright failure) is, because the two-sided candidate sat on a single grid point and its
  horizon risk needed bounding. **DISCARD — `train_strength` fails.** Score 0.654 (−38%),
  LCB **−0.0206**, t **1.702**, profit factor 1.64, DD **−0.160**, worst-subwindow PSR 0.202.
  **The cliff starts between 30 and 35, so the two-sided survivor is genuinely knife-edge on the
  axis that matters most.** A five-day drift in the true formation horizon breaks it, and drift is
  exactly what a downstream OOS window can deliver.

**The horizon maps, side by side, and this is the sharpest difference between the two candidates.**

| `lookback_days` | long-only | two-sided |
| --- | --- | --- |
| 20 | fail (t 1.67) | not run |
| 25 | 0.980 pass (t 2.41) | 0.935 pass (t 2.17) |
| 30 | **1.037 (t 2.53)** | **1.047 (t 2.35)** |
| 35 | not run | **fail** (t 1.70) |
| 40 | fail (t 1.43) | fail (t 1.10) |

Long-only has a two-point plateau whose members sit 2.3% apart, and both fall inside the a-priori
25-30d range. Two-sided has a single passing point with a gate failure five days above it. The
score-leading candidate is therefore the more fragile one on the thesis's most consequential
parameter, and that belongs in front of any promotion decision.

- **attempt-0045** — lever: `weighting` `inverse_vol` → `conviction` on the two-sided survivor.
  **Mechanism:** the breadth tilt won by leaning into cross-name agreement, and conviction is the
  within-breadth analogue — lean into whichever name trends hardest per unit of volatility.
  **Falsifier:** the hardest-trending name is also the most extended, so tilting toward it
  concentrates into reversal-prone positions. **DISCARD — `train_strength` fails, confirming this
  lever at a second base.** Score 0.593 (−43%), LCB **−0.0285**, t **1.586**, DD **−0.201** (the worst
  of any deployed row in the lifecycle), symbol concentration 0.350 → **0.512**, effective symbol
  count 2.99 → 2.62, best-subwindow return share 0.331 → 0.484.
  **The distinction it draws is the useful part, and it is not obvious.** Leaning into cross-name
  *agreement* pays slightly (the breadth tilt, +0.12%); leaning into per-name trend *magnitude* fails
  hard at both bases tested. **What carries information here is how many names agree, not how
  strongly any one of them trends** — conviction is not a principle that transfers from one level to
  the other, and risk parity across the whole active book stays the right allocation shape at every
  base measured.
  Setting this attempt up exposed a defect worth recording. The conviction metric floored
  vol-adjusted trend strength at zero, which silently zeroed every short and would have made this
  row a mislabeled long-only variant rather than a test of the lever. It now uses the magnitude,
  matching the metric `top_n` already ranks on, and was verified to leave long-only output unchanged
  so every earlier row stays comparable.

- **attempt-0046** — lever: `vol_lookback_days` 60 → 30 on the two-sided survivor. **Mechanism:** the
  estimator window was one of the base-dependent verdicts — insensitive across 20-60 at the 25d
  formation, worth +3.3% at 30d — so a side-logic change warrants re-measuring it. **DISCARD on score
  — all nine gates pass.** Score 1.0272 (−1.9%), LCB +0.0220, t **2.318**, trades 337, DD −0.121,
  worst-subwindow PSR 0.375 → 0.355, `max_feasible` 0.233 → 0.209.
  **This is the first lever verdict that transferred across the side-logic change.** A 60d estimator
  beats a 30d one at both bases with a 30d formation (+3.3% long-only, +1.9% two-sided), so the
  pairing of a longer formation with a longer volatility estimate is a property of the horizon rather
  than of the side logic. Given how much of this thesis turned out to be base-specific, a verdict
  that holds across a base change is worth flagging as the more transferable kind.
- **attempt-0049** — lever: `vol_lookback_days` 60 → 90 on the two-sided survivor, closing the
  estimator axis at this base. **DISCARD on score — all nine gates pass.** Score 1.0104 (−3.5%),
  LCB +0.0202, t **2.292**, trades 345, DD −0.124.
  **The estimator is an interior peak at the two-sided base as well:** 30 → 1.027, **60 → 1.047**,
  90 → 1.010. Both candidates therefore sit at an interior optimum on this axis rather than pinned
  against a bound, which is the check that distinguishes a found optimum from a configuration still
  climbing toward the edge of its range.
- **attempt-0050** — lever: `skip_days` 0 → 1 on the two-sided survivor, closing the gap axis at this
  base and exhausting the iteration budget. **DISCARD on score — all nine gates pass.** Score 0.898
  (−14.2%), LCB +0.0083, t **2.120**, trades 345 unchanged, DD −0.120 → **−0.161**, worst-subwindow
  PSR 0.375 → 0.350.
  **Gap 0 is confirmed at every base tested, and the penalty is now side-independent:** a one-day gap
  costs 2.4% at the 25d long-only base, 12.5% at 30d long-only, and 14.2% at 30d two-sided. The
  earlier reading that the gap axis is flat belongs to the short horizon alone; at a 30d formation the
  recent move is already excluded by the horizon itself, so adding a gap over-excludes regardless of
  side logic.

### The two candidates

Fifty attempts leave two configurations that a skeptical reviewer should see together. They differ in
**one lever** — side logic — and everything else is identical: 30d formation, no gap, daily,
`inverse_vol` on a 60d estimator, no regime gate, no exits, `position_smoothing` 2, `execution_bars`
20, quadratic breadth tilt (inert for the two-sided row).

| | attempt-0033 long-only | attempt-0040 two-sided |
| --- | --- | --- |
| score (objective) | 1.0371 | **1.0468** |
| `train_strength` t | **2.533** | 2.346 |
| `train_strength` LCB | **+0.0409** | +0.0239 |
| full-train PSR | **0.9942** | 0.9905 |
| worst-subwindow PSR | **0.408** | 0.375 |
| closed trades | 66 | **345** |
| min-subwindow trades | 6 | **44** |
| profit factor | **4.96** | 1.92 |
| net per trade | **0.0158** | 0.0029 |
| cost drag | **0.0268** | 0.0524 |
| cost-stress retention | **0.978** | 0.959 |
| max drawdown | −0.119 | −0.120 |
| effective symbol count | 2.70 | **2.99** |
| symbol concentration | 0.484 | **0.350** |
| best-subwindow return share | 0.455 | **0.334** |
| `max_feasible_volatility` | **0.338** (2.25×) | 0.233 (1.55×) |
| horizon robustness | 25 **and** 30 pass, 2.3% apart | 30 only; 35 fails |
| gates | 9/9 | 9/9 |

**Two-sided wins the objective by 0.94% and loses almost everything else.** It is never flat, which is
why it earns more total return, and the score is the protocol's ranking rule, so the harness is
correct to freeze it. But it is worse on every risk-adjusted measure, roughly half as cost-robust,
holds only 1.55× capacity headroom against 2.25×, and sits on a single horizon grid point with a gate
failure five days above it. What it genuinely buys is **evidence**: 5× the closed trades, seven times
the thinnest-subwindow trade count, and return spread far more evenly across names and regimes.

**The choice is not a research question and must not be settled by reading the survivor row.**
Long-only is the more trustworthy edge and the only viable base if the `target_volatility` axis is
ever taken (see `reseed_log.md`). Two-sided is the higher-return book at the frozen target and the
one that gives a downstream OOS test more to work with. Both belong in any offload package with this
table intact.

### Outcome of attempts 31-50

**Two keeps in twenty attempts, and the survivor advanced 1.0359 → 1.0468 (+1.05%).** Both keeps were
marginal by design of the improvement floor rather than by strength: the breadth tilt cleared it by
0.00025 and side logic by ten times the floor. Neither is an edge improvement — the tilt is within
noise and two-sided is a deployment gain with falling t.

**The block's real product is one structural rule with seven independent confirmations: this book is
paid for duty cycle.** Every lever that reduced time at risk lost — a slower clock (−16.5%), a faster
exit (−27%), a regime gate (−51%), a take-profit (−77%), a trailing barrier (−85%), a hysteresis band
(−10.4%), and heavier across-day smoothing (−11.9%) — while the one lever that raised duty took the
score lead. Four of those rows *improved* per-trade economics and cost drag while losing materially on
total return, so **cost is not this thesis's binding constraint and turnover reduction is not a
productive direction.** The mirror image also holds: any exit that latches the book flat is penalized
twice, once in lost time at risk and once in the participation cap it re-binds when the volatility
target scales the survivors up.

**The exit family is closed** — four devices, four distinct falsifications, and the surviving rule
(hold until the formation horizon turns) beats them all for stated reasons rather than by omission.
Two of those failures constrain the reseed decision: no price-path barrier improves drawdown per unit
of deployed volatility, so nothing relaxes the drawdown ceiling on the `target_volatility` axis.

**Base dependence continued to dominate lever verdicts.** Side logic flipped from −12% to +0.94%, and
attempt-0042 attributed the flip to a single interacting lever rather than to the accumulated base:
shorts are only pervasive at a 30d formation (worst-subwindow PSR ~0.09 at 25d in two independent
measurements, 0.375 at 30d). Against that, the estimator verdict *transferred* across the change,
which makes it the more durable kind of finding. The one axis whose optimum has never moved at any
base is `position_smoothing` 2.

**What did not work is as informative as what did.** Breadth is informative but its tilt is nearly
flat (flat gross −11.7%, linear and quadratic indistinguishable); agreement across names carries
information while trend magnitude within a name does not (conviction fails at both bases); and risk
parity turns out to be doing double duty in this universe, aligning risk *and* keeping the thinnest
name inside its ADV limit, because the highest-volatility name is also the least liquid.
- **attempt-0047** — lever: `weighting` `inverse_vol` → `equal` on the two-sided survivor, the
  attribution baseline that completes the weighting map at this base. **DISCARD on score — all nine
  gates pass.** Score 0.743 (−29%), LCB +0.0115, t **2.204**, trades 342, DD −0.113.
  **Risk parity is doing two jobs at once here, and equal weighting breaks both.** Allocation first:
  symbol concentration 0.350 → **0.471** and effective symbol count 3.00 → 2.76, because equal shares
  hand the highest-volatility name the same NAV as the steadiest one and let it dominate the risk
  budget. Capacity second, and this is the part that is specific to this universe:
  `capacity_bound` returns to **true** at deployed volatility **0.123**, only 82% of the target.
  **In this universe the highest-volatility name is also the least liquid, so risk parity is
  incidentally liquidity-aligned** — sizing by inverse volatility keeps the thin name small enough to
  stay inside its ADV limit, and equal weighting pushes it back through. So roughly two-thirds of the
  29% loss is deployment and one-third is allocation quality.
  Per-trade economics again move the other way — profit factor 1.92 → **2.02** and cost drag 0.0524 →
  **0.0280**, nearly halved — and the row still loses 29%. That is the fourth time cheaper trading
  has come with materially worse total return.
  **Risk parity's value grew when shorts came in:** worth +11% at the 25d long-only base and +29%
  here. It is the allocation shape at every base measured, now for a liquidity reason as well as a
  risk one.