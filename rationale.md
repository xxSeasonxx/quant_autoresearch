# Rationale

## Thesis

Realized same-sign funding pressure and same-direction price extension can mark
crowded crypto perpetual positioning. The strategy trades the reversal after the
signal bar is observable and exits with explicit fixed-horizon flat targets.

## Observable

- Data: `crypto_perp_1min_with_funding`.
- Fields: `close`, `available_at`, `funding_timestamp`, `funding_rate`, and
  `has_funding_event`.
- Signal: the sum of the latest realized funding events, same-sign funding-event
  persistence, and price extension versus a completed prior close.
- Cross-section: rank candidates by combined funding pressure and idiosyncratic
  return extension versus the current eight-symbol universe.

## Universe

Eight liquid, established crypto-perp majors:
`BTC-PERP`, `ETH-PERP`, `SOL-PERP`, `XRP-PERP`, `BNB-PERP`, `DOGE-PERP`,
`ADA-PERP`, `LINK-PERP`.

Selection criterion is **return-blind**: the most liquid, longest-established
majors among the data-ready resolved universe, chosen for deployable notional
(adv_impact capacity) and full in-window minute coverage, never for realized
return. All eight are `research_ready` in the derived funding dataset with full
source/derived row parity and complete `2025-03-01..2025-12-31` coverage. Symbol
membership is protocol-frozen for this lifecycle.

Why at least eight, and never fewer: this is a cross-sectional reversal, and the
tradeable signal is relative — the idiosyncratic price extension is measured
against the cross-section mean over the candidates present at the signal bar. At
one name that deviation is identically zero, so the book cannot trade; at two or
three, the cross-section mean the ranking depends on is noise. Fewer names is
worse on every axis: it degrades the signal's own denominator, raises each name's
equal weight and economic concentration toward the breadth gate, and cuts closed
trades — widening the SE that the deflated money floor must overcome. The
eight-name edge is broadly cross-sectional (most names net positive, concentrated
in altcoins, not one-name beta), so if the money floor binds through a thin, lumpy
Sharpe rather than a weak per-trade edge, the honest reseed is *wider* — toward
the research-ready altcoins in the eligible twenty-five — never narrower. Read
`effective_symbol_count` and `max_symbol_concentration` each run to judge realized
breadth, and converge the active book with `top_n`, never by pruning the frozen
universe. Capacity reshaping (spreading entries across bars) is a strategy-side
lever, not a reason to change symbols.

## Signal Components

### Component: Funding pressure
Same-sign realized funding summed over the last `funding_lookback_events`
settlements, gated by `min_same_sign_funding_events` persistence and
`min_abs_funding_bps` / `min_latest_abs_funding_bps` magnitude. Crowded carry pays
one side; the book takes the other.

### Component: Idiosyncratic price extension
Signal-close return versus a completed prior close (`return_lookback_minutes`),
measured against the cross-section mean (`min_idiosyncratic_return_bps`), with a
recent-return guard (`max_recent_same_direction_return_bps`) against
still-accelerating moves. Same-direction extension marks the crowded move to
reverse.

## Falsifier

The thesis should die if micro-causal Train runs cannot produce enough closed
trades across subwindows, if returns collapse after costs and capacity impact, or
if the edge depends on one symbol or one time slice.

## Assumptions

- Funding fields are realized settlement events, not forecasts.
- A bar's close is used only after `available_at`.
- Target magnitude is shape-only: each active symbol receives an equal slice of
  gross book shape, and upstream risk-budget sizing owns deployed scale.

## Editable Params

- Funding pressure: `funding_lookback_events`, `min_abs_funding_bps`,
  `min_same_sign_funding_events`, `min_latest_abs_funding_bps`.
- Price extension: `return_lookback_minutes`, `min_abs_return_bps`,
  `recent_return_lookback_minutes`, `max_recent_same_direction_return_bps`,
  `min_idiosyncratic_return_bps`.
- Cross-section and sides: `top_n`, `min_cross_section`, `selection_score`,
  `include_negative_funding_longs`, `include_positive_funding_shorts`.
- Rebalance and horizon: `decision_interval_minutes`, `decision_lag_minutes`,
  `long_hold_minutes`, `short_hold_minutes`.

## Scoring Contract (current objective)

The `significance` gate deflates the **full-Train** annualized return at `k = 2.0` SE and
requires it to be **positive**: pass needs `full_train_return - 2.0 * SE >= 0`
(`k_accept = gates.score_haircut_se`) — i.e. the edge is statistically real after the best-of-N
multiple-testing correction (equivalently, the full-Train t-stat clears `k_accept`). It is the
sole binding gate here; the other seven pass with margin. **Materiality is not gated:** how much
money the edge deploys lives in the run score (`return - 1.0 * SE`, the deployed-return LCB the
loop ranks on) and is the operator's judgment, not a hard floor. A `significance` failure means
the edge is not distinguishable from best-of-N noise — not that it is merely small; and
`capacity_bound` is a passing diagnostic, not a failure.

Why the realized t sits at ~2 (verified against upstream, not an artifact): `t =
full_train_return / SE = Φ⁻¹(PSR) = annualized_Sharpe * sqrt(n_eff / P)`, which reduces to
`t = Sharpe * sqrt(duty_cycle * window_years)`. The book is at-risk only ~33% of the calendar
(n_eff = 145,168 at-risk minutes / P = 525,600 → n_eff/P ≈ 0.28, √ ≈ 0.53), so at Sharpe ~3.8 →
t ~2.0 and the deflated LCB sits right at zero. `n_eff` uses a Kish lag-1 factor and applies NO
discount here (minute returns near-white at lag 1); kurtosis (~65) folds into the Sharpe SE but
is negligible at this per-minute Sharpe — so t~2 is faithful, if slightly conservative. t is
**scale-invariant** (same at 1.6% and 10% vol), so capacity lifts deployed return (the score) but
not significance. The lever that raises t is a larger universe — **mainly by lifting duty cycle**
(more names firing → more at-risk calendar → higher n_eff); the diversification/Sharpe gain is
limited because crypto-perp crowding is one highly-correlated factor (ρ ≈ 0.6-0.8, which is why B2
risk-parity was inert and B3 density diluted). Neither shape nor scale on 8 names moves it.

## Prior-Universe Hypotheses To Re-Test On The Broad Cross-Section

These mechanistic findings come from the five-name lifecycle. They are carried
forward as **hypotheses to re-validate on eight names**, not as established facts —
the universe change can flip any of them.

1. **By-direction split (alpha vs beta).** On five names the longs (fade crowded
   shorts: negative funding + price down) paid (~+4.8 bps/trade net, hit ~0.60,
   strong PF) while the shorts (fade crowded longs) lost (~-1.2 bps/trade), so a
   long-only book was needed for profitability. Open question: is that real
   two-sided crowding alpha, or 2025 long beta (dip-buying a rising tape)? The
   broad universe is the clean test. The baseline runs **both sides** so the split
   is re-measured here before assuming long-only.
2. **Lumpy edge.** Per-trade profit factor was healthy (~1.7) but kurtosis ~90 — a
   few big winners drove the Sharpe, weakening its lower bound. More independent
   names should smooth this.
3. **Trade-starved subwindows.** One calendar slice (Aug-Sep) had a handful of
   trades on five names. More simultaneous candidates should populate every slice.
4. **Capacity throttles deployed vol.** All selected names entered in one decision
   minute, pinning peak bar participation at the 0.50 cap and capping the
   calibrate_vol scalar, leaving deployed vol far below the 15% target. This is
   real but secondary: money_floor = deployed_vol x Sharpe_LCB, so capacity relief
   only helps once the LCB is positive. Defer capacity reshaping (spreading entries
   across bars) until the LCB clears 0.

## Failure Modes To Watch

The money floor fails while the Sharpe lower bound is thin (lumpy edge, few
independent bets). On five names there was a tight<->broad tension: tight selection
gave a good LCB but failed subwindow coverage / breadth; broad selection passed
coverage but pushed the LCB negative. The eight-major universe is the lever meant
to break that tension — watch whether it does, or whether it reappears. A
micro-causality timeout is a compute limit, not thesis evidence.

## Baseline Plan

Both sides on, `decision_interval = 120`, `top_n = 5` of 8, `min_cross_section = 4`,
`min_same_sign = 3`, `min_idio = 2.5`, holds 720/720. The baseline establishes a
feasible, causal anchor on the broad universe and yields a fresh by-direction
decomposition. First failure mode to watch: whether eight names are enough to clear
the breadth gate (concentration < 0.70) and populate all six subwindows; if so, the
next lever is the Sharpe lower bound (selectivity and side logic), not trade count.

## Breadth Is Economic, Not Structural (supersedes the earlier peak-concentration finding)

The `breadth` gate reads `max_symbol_concentration`, now the **largest single
symbol's share of the window's realized PnL** (economic concentration, computed
upstream from the round-trip ledger). A book whose PnL is spread across names
scores low even when it holds one name at a time; a genuine single-name book
scores 1.0; a window with no realized PnL scores 0.0.

The earlier conclusion — that breadth is a structural 1.0 wall incompatible with
this thesis's sparsity — was an artifact of the prior metric (peak instantaneous
single-symbol share of gross notional, which read 1.0 whenever the book held one
name at any bar) and no longer holds. Breadth under the corrected metric is
unmeasured here and must be re-established with a fresh baseline. The `0.70`
threshold is retained as a recall-oriented economic-dependence ceiling: one name
may carry up to 70% of realized PnL. The dated entries below record breadth as
observed under the prior metric.

## Current Lifecycle — Corrected Harness (active)

Fresh lifecycle re-baselined on the corrected harness (attempt-0001). Same 8-major
universe and mechanism as the archived log below; the harness changed:

- `breadth` now reads **economic** concentration (largest symbol's share of realized
  PnL), not peak gross notional. It PASSES (0.305 << 0.70). The archived "breadth is a
  structural 1.0 wall" lesson is **obsolete** — an artifact of the old metric.
- `subwindow_coverage` is **removed** as a gate; `subwindow_consistency` is now a
  diagnostic. Per-window sufficiency lives only in `minimum_evidence` (return samples +
  effective sample size). Archived "coverage fails / 3-of-6 windows negative" no longer gate.
- `effective_symbol_count` (inverse-HHI of PnL shares) is a reported breadth diagnostic;
  `failure_class` names the binding constraint semantically.

What transfers (edge statistics unchanged): the edge is **one-directional** (fade
crowded-short capitulations, go long; shorts have no gross edge); the minimal sufficient
core is **negative funding ≥ 1 bp + price-down + idiosyncratically-down-vs-peers ≥ 2.5 bp**
(persistence and falling-knife guards removable, funding-magnitude and cross-section floors
load-bearing); cadence **240** is the edge peak; every magnitude/timing tightening removes
good trades. The t-stat ceiling on 8 names was ~2.07, capped by setup sparsity (1-3
concurrent crowded-shorts).

**B0 baseline (attempt-0001) = archived best config** (cadence 240, long-only,
min_same_sign 1, min_abs_funding 1, min_idio 2.5, recent-guard off, hold 720, top_n 5,
fixed-horizon, entry_twap_bars 1): discard, score +0.0335, **failure_class capacity_bound**.
Only `money_floor` fails (deflated +0.0023, needs +0.10); the other 7 gates pass (breadth
0.305, causality pass, cost-stress 0.83, PF 1.686, PSR 0.981, full-train t ~2.07, 306 trades,
effective_symbol_count 5.16). Real, broadly cross-sectional, cost-robust edge deployed at only
**1.6% vol** (book_scale 0.052, max_feasible_vol == deployed_vol == 0.0163) vs 15% target, so
6.5% return misses the 10% floor. **Binding constraint = capacity → deployed vol.** money_floor
= deployed_vol × (Sharpe − 2·Sharpe_SE); with t~2 the deflation factor (1 − 2/t) ≈ 0.03 is tiny,
so approaching +0.10 needs BOTH capacity relief AND a materially higher t-stat.

- **B1 (entry_twap_bars 1 → 10; capacity relief):** Mechanism — selected names enter/exit
  in one decision minute, pinning that bar at the 0.50 bar-participation cap and throttling
  book_scale to 0.052. Ramping each name in over 10 consecutive 1-min bars (equal deltas) and
  out over 10 bars drops per-bar participation ~10×, shifting the binding cap from
  bar-participation toward the ADV ceiling (~0.25 vs current ~0.09). Observable —
  max_feasible_vol / book_scale / deployed_vol. Falsifier — deployed vol does not rise (bar
  participation was not binding, or per-symbol ADV already binds), or the edge degrades (a
  10-min spread over a 720-min hold should be negligible). Now causally admissible
  (multi-decision-per-signal ramp no longer false-flagged as suppression). Even on full
  success, ~2-3× capacity relief lifts money_floor to ~0.006 (still < +0.10) — this measures
  the true capacity ceiling, not a pass.
- **B1 result (attempt-0002): capacity relief CONFIRMED; t-stat is the residual wall.**
  book_scale 0.052 → **0.171**, deployed_vol 1.63% → **5.36%** (3.3×), full-train return
  6.5% → **19.8%**, score 0.0335 → **0.0955 (new best)**. Edge untouched: PF 1.686 → 1.679,
  306 trades (identical), concentration 0.308, cost-stress 0.77 pass. Still `capacity_bound`
  (5.4% == max_feasible_vol → now at/near the ADV ceiling, ~3.3× vs A30's ~2.8× estimate).
  BUT full-train t 2.07 → **1.93** (staggered fills reshaped the return-series
  autocorrelation), so deflated money_floor +0.0023 → **−0.0068** and `failure_class`
  flipped capacity_bound → no_edge. KEY STRUCTURE: money_floor = deployed_vol × Sharpe ×
  (1 − 2/t) flips sign at **t = 2**; B0 was just above, B1 just below. Capacity is now
  largely captured; the sole remaining lever to +0.10 is the **t-stat** (need ~3-4; at 5.4%
  vol and Sharpe ~3.7, t=4 → floor ~0.099). Kept TWAP-10 as the deployable base; the t-stat
  is universe-independence-bound, so the next moves attack portfolio-return SE directly.
- **B2 (inverse-volatility weighting; TWAP-10 base):** Replace equal 1/N weights with a
  risk-parity book shape — each selected name weighted ∝ 1/realized_vol (vol estimated
  causally from 1-min returns over `vol_lookback_minutes` ending at the signal bar), gross
  per decision preserved. Mechanism — equalizing per-name risk contribution stops the
  high-vol altcoins from dominating portfolio variance, lowering portfolio-return SE for the
  same mean → higher Sharpe/t-stat (classic risk-parity gain), pushing the deflated floor
  back above zero and toward +0.10. This is the top untested signal-construction lever.
  Falsifier — t-stat flat or worse: the edge is genuinely concentrated in the high-vol
  altcoins (A11/A16: DOGE/XRP/SOL/ADA carry it, BTC/ETH rarely fire), so down-weighting them
  loses more return than variance. Either outcome is decisive about where the edge lives.
- **B2 result (attempt-0003): inverse-vol is INERT.** score 0.0955 → 0.0965, deflated
  −0.0068 → −0.0054, t ~1.93 → ~1.95, PF 1.679 → 1.681 — every metric moved ~0.001. Neither
  hurt (edge is not fragile to down-weighting altcoins) nor helped t. Reason: you cannot
  risk-balance a book that holds only 1-3 names at a time — weighting cannot manufacture
  independence the universe does not supply. THIRD confirmation of the t~2 ceiling from
  concurrent-setup sparsity (archived top_n 8 ≡ 5; B1 capacity relieved 3.3× but t flat; B2
  risk-parity inert). Capacity ceiling is likewise the per-name ADV cap (bar-cap had 10×
  headroom at N=10, vol rose only 3.3×) — also a few-names artifact. Both walls trace to the
  universe. Kept inverse_vol as the marginal-best base (candidate for later simplification).
- **B3 (decision_interval 240 → 120; TWAP-10, inverse_vol base):** The archived lifecycle
  converged to a tight, sparse, cadence-240 book partly because the now-removed breadth
  (gross-notional) and subwindow_coverage gates punished density; and faster cadence
  previously CRASHED on capacity (A3, pre-TWAP). Both blockers are gone. Mechanism — 2×
  decision points create more overlapping cohorts → more concurrent names held → higher
  effective sample size / lower portfolio-return SE → higher money-floor t-stat, now that
  TWAP prevents the synchronized-entry capacity collapse. Observable — t-stat / n_eff /
  concurrent breadth / deployed vol / PF. Falsifier — PF dilutes (faster cadence re-enters
  the same names at lower-quality points, as A3 showed 1.33→1.19) and t does not rise →
  cadence 240 stays the peak and faster cadence hurts the edge regardless of capacity.
- **B3 result (attempt-0004): FALSIFIED — faster cadence is decisively worse.** cadence 120:
  score 0.0965 → 0.0331, return 19.8% → 10.4% (halved), PF 1.681 → 1.385 (diluted), t ~1.95
  → ~1.47, deployed vol 5.34% → 4.19% (lower — more turnover tightens the per-name ADV cap).
  436 trades but worse: the extra entries are autocorrelated re-samples of the same crowded
  names, NOT independent bets, so n_eff did not rise. This REFUTES "the old lifecycle
  over-tightened due to now-removed gates" — the tight, sparse cadence-240 book is genuinely
  optimal under the corrected harness too, not a gate artifact. Reverted to cadence 240.
- **Trade-tape inspection (B1 diagnostics) rules out a stop-loss.** All 306 exits are
  fixed-horizon; avg_win +7.7 bps / avg_loss −6.2 bps (near-symmetric), PF 1.68; the largest
  losers are only ~−0.3% NAV and exit at the horizon — there is NO fat left tail to cut. A
  stop-loss would whipsaw (cut mid-hold dips that recover over the slow reversal), consistent
  with A6/A7/A18 (every exit-timing edit hurt). Not tested — evidence argues against it.
- **B4 (entry_twap_bars 10 → 20; equal weighting; cadence-240 base):** Two consolidations.
  (1) Simplification — revert inverse_vol → equal (B2 proved it inert, +0.001, but +2 params);
  the simpler book is the base. (2) Capacity-ceiling characterization — vs B1 (TWAP-10, equal,
  5.36% vol) this isolates whether deployable vol is maxed at the per-name ADV cap. Prediction
  — INERT: at N=10 the bar-participation cap has ~10× headroom yet vol rose only 3.3×, so the
  ADV cap (unaffected by more intraday spreading) already binds; N=20 should hold ~5.4% vol.
  Falsifier — vol rises materially → bar-participation was still binding and more capacity is
  free. Either way this fixes the true 8-name capacity ceiling for the handoff/reseed case.

- **B4 result (attempt-0005): PREDICTION OVERTURNED — capacity is NOT maxed; new best by 2×.**
  N=20 (equal): score 0.0955 → **0.1957** (~5.8× baseline), deployed vol 5.4% → **10.1%**
  (doubled again toward the 15% target), return 19.8% → **38.8%**, deflated money_floor −0.0068
  → **+0.0032 (positive)**, t 1.93 → **2.02** (recovered above 2 — TWAP does NOT systematically
  hurt t), PF 1.679 → **1.718**, 306 trades (identical), failure_class no_edge → capacity_bound.
  The bar-participation cap was STILL binding at N=10; N=20 relieved it further. Still
  `capacity_bound` at 10.1% → more headroom below 15% target likely remains. Equal weighting
  adopted (inverse_vol dropped — inert, +2 params). TWO durable facts: (1) capacity is the
  dominant profitability lever and is not exhausted — deployable return climbs strongly with N;
  (2) money_floor = return × (1 − 2/t), so at t≈2 the deflation factor ≈ 0 and even full 15% vol
  leaves the floor near zero — clearing +0.10 needs t ≈ 3-4 (e.g. return ~30% at t=3 → floor
  0.13). t is scale-invariant (B4 at 10% vol has the same t≈2 as B0 at 1.6%), so it stays
  universe-bound; capacity lifts deployable return, not significance.
- **B5 (entry_twap_bars 20 → 30, bound max 30 → 60; equal, cadence-240 base):** Push capacity
  to the 15% risk-budget target. Mechanism — the bar-participation cap still binds at N=20
  (vol 10.1% < 15% target, capacity_bound true); spreading each entry/exit over 30 bars lowers
  per-bar participation further. Observable — deployed vol / book_scale / capacity_bound flag.
  Success — deployed vol → ~15% (capacity_bound flips FALSE = risk budget, not liquidity, is
  the limit), return → ~55%, score → ~0.29. Falsifier — vol plateaus below 15% (a per-name ADV
  cap, unaffected by more intraday spreading, is the true ceiling) → that plateau IS the honest
  8-name capacity ceiling. Either way maximizes deployable return and fixes the ceiling.

- **B5 result (attempt-0006): capacity is NON-MONOTONIC in N; peak ≈ N=20.** N=30: deployed
  vol 10.1% → **4.9%** (dropped, ≈ N=10 level), book_scale 0.326 → 0.160, return 38.8% →
  19.6%, score 0.196 → 0.103. deployed_vol/book_scale ≈ 0.31 across ALL N, so this is a pure
  capacity-sizing effect: the model allowed 2× higher book_scale at N=20 than N=30. Mechanism
  — spreading over more bars cuts per-bar size but touches MORE bars, raising the chance of
  hitting a thin-liquidity minute the per-bar participation cap binds on; so deployable vol
  peaks (~N=20) rather than rising monotonically to the 15% target. The true 8-name capacity
  ceiling is ~10% vol, not 15%. (N=30's deflated floor +0.0097 > N=20's +0.0032 is only t-noise
  2.10 vs 2.02; both far from +0.10.) Vol trajectory by N: 1→1.6%, 10→5.4%, 20→10.1%, 30→4.9%.
- **B6 (entry_twap_bars 30 → 25; equal, cadence-240 base):** Confirm the deployed-vol peak is
  broad (robust optimum) vs a sharp spike at exactly N=20 (execution-noise artifact). Success —
  N=25 vol ≈ 8-10% (broad peak → N≈20-25 is a stable deployable optimum). Falsifier — N=25 vol
  ≈ 5% (sharp spike at 20 → the peak is a fragile capacity-model artifact, treat frontier as
  ~5-10% noisy). Either way fixes the deployable optimum for the survivor/reseed handoff.

- **B6 result (attempt-0007): N=20 is a SHARP SPIKE, not a broad peak.** N=25: deployed vol
  **4.1%** (≈ N=10/25/30 cluster of 4-5.4%), score 0.085, return 16.3%. So by-N vol is
  1→1.6%, 10→5.4%, 20→**10.1%**, 25→4.1%, 30→4.9% — only N=20 doubled. deployed_vol/book_scale
  ≈ 0.31 throughout, so N=20 got 2× book_scale purely because that ramp offset avoided the
  thin-liquidity minutes the per-bar cap binds on for the least-liquid name — a fragile,
  Train-window-specific capacity artifact, not to be banked (North Star: no number the Train
  window merely liked). Robust deployable frontier ≈ 5% vol (score ~0.10, ~3× baseline) — a
  real, defensible TWAP capacity gain. money_floor still universe-bound (t ~2).
- **B7 (entry_twap_bars 25 → 18; equal, cadence-240 base):** One decisive test of the N=20
  spike width, because ~10% vs ~5% vol is a 2× profitability difference for the handoff.
  Success — N=18 vol ≈ 9-10% (peak is broad 18-20, ~10% is robust and bankable). Falsifier —
  N=18 vol ≈ 5% (razor spike at exactly 20, discount it; robust frontier stays ~5%). Stop
  tuning N after this regardless of outcome — further N search would be overfitting the
  capacity model to specific liquid minutes.

- **B7 result (attempt-0008): ~10% vol is an N=18-20 PLATEAU, not a razor spike.** N=18:
  deployed vol **9.2%**, score **0.173**, return 34.8%, PF 1.705, t ~1.99 (deflated −0.0023).
  Updated by-N vol: 10→5.4%, 18→9.2%, 20→10.1%, 25→4.1%, 30→4.9%. So ~10% is reachable across
  N≈18-20 with a sharp cliff above ~22 back to the ~5% floor. More robust than a spike but the
  nearby cliff keeps the exact level execution-timing-sensitive. Deployable frontier: ~5%
  robust floor, up to ~10% at N=18-20. Even at the ~10% peak the deflated floor is ~0 (t≈2) —
  the survivor gate is capacity-independent and universe-bound. Stopped tuning N (committed).

- **B8 result (attempt-0009): the edge is CROSS-SECTIONAL — min_idio is load-bearing.** min_idio
  2.5 → 0 (N=18 base): PF 1.705 → 1.636, t 1.99 → 1.89, score 0.173 → 0.153, +12 trades. Removing
  the idiosyncratically-down-vs-peers screen admits names down absolutely but not relative to the
  cross-section → lower quality → PF/t drop (matches archived A16). Reverted to 2.5. The tradeable
  edge is genuinely relative-value, so a LARGER cross-section improves signal quality (cleaner
  relative ranking, more simultaneous idiosyncratic-deviation candidates) — a third, independent
  reason the reseed lever is a bigger universe.

## Current Lifecycle — Convergence Summary (attempt 9)

Nine attempts on the corrected harness fully characterize the thesis:

- **Win (real, robust):** entry-TWAP capacity relief lifts deployable volatility from the
  1.6% baseline to a ~5% robust floor and a ~9-10% N=18-20 plateau — a 3-6× gain in deployable
  return (score 0.033 → ~0.10 robust, ~0.17-0.20 at the plateau) with the edge intact (PF ~1.7,
  causality pass, cost-stress ~0.78, breadth ~0.31). This is the first time this thesis has
  deployed materially — the archived lifecycle was capacity-throttled to 1.6% and its TWAP
  probe was bug-blocked.
- **Wall (confirmed 5 ways):** the money_floor at +0.10 needs a full-Train t-stat ≈ 3-4;
  it sits at ~2.0 (±0.1 noise) and is scale-invariant (same t at 1.6% and 10% vol) and
  universe-bound. Unbroken by capacity (B1/B4), risk-parity weighting (B2, inert — too few
  concurrent names to balance), density/faster cadence (B3, dilutes edge), and the trade tape
  rules out a stop-loss (no fat left tail). Archived top_n 8 ≡ 5 confirms 1-3 concurrent setups.
- **Both walls trace to one fact:** 8 names supply only 1-3 concurrent crowded-short setups,
  which caps the t-stat (independence) AND the per-name ADV capacity. The single lever that
  breaks both is a materially larger universe (~25 names) — a reseed, Season's call.

The entire editable surface is now mapped (this lifecycle: capacity/TWAP N=1-30, weighting,
cadence, exit/stop-loss, cross-section; archived and edge-invariant: funding/return/horizon/
selection params). No untested distinct lever remains — further runs would be redundant
re-confirmation (edge statistics unchanged) or N-polishing (overfitting the capacity model to
specific liquid minutes). Search stopped at convergence rather than run redundant slots to 50.

## Frozen Survivor-Candidate (this lifecycle) — NOT a Train survivor

No config clears the Train gates (money_floor unreachable on 8 names). The best robust
deployable candidate for Season's downstream OOS/paper/small-live review is **attempt-0008**
(current `experiment.toml`): long-only crowding-reversal, cadence 240, min_same_sign 1,
min_abs_funding 1, min_idio 2.5, recent-guard off, hold 720, top_n 5, equal weighting,
**entry_twap_bars 18**. Score 0.173, deployed vol 9.2%, full-Train return 34.8%, PF 1.705,
PSR 0.977, t ~1.99, breadth 0.31, causality pass, cost-stress 0.78. Peak-score point is
attempt-0005 (N=20, score 0.196, vol 10.1%) but it sits at the capacity cliff (N>22 halves
vol) so it is less robust; the ~5% floor (N=10/25/30) is the conservative deployable level.
This is a candidate-quality edge, not a promotion signal.

## Reseed Case (for Season; not executed) — larger universe

The thesis is envelope-bound, not edge-bound. Both binding walls share one root cause and one fix.

- **Root cause:** 8 majors supply only 1-3 concurrent crowded-short setups (top_n 8 ≡ top_n 5;
  min_cross_section inert). This simultaneously (a) caps statistical independence → full-Train
  t-stat ~2.0, so the deflated money_floor = return × (1 − 2/t) stays ~0 and the +0.10 gate is
  unreachable regardless of deployed scale; and (b) concentrates capacity into few names →
  per-name ADV participation caps deployable vol at ~5-10%.
- **The edge is cross-sectional** (B8: min_idio load-bearing) and **broadly diversified**
  (archived: 6-7 of 8 names net positive; breadth 0.31), so it is not a one-name artifact — a
  wider cross-section should deepen it, not dilute it.
- **Recommendation:** reseed the same long-only funding-crowding-reversal mechanism on the full
  data-ready crypto-perp universe (~25 names), selected return-blind on eligibility (liquidity,
  readiness), keeping the frozen mechanism, cadence 240, TWAP entry, and the minimal filter core.
  Expected to raise t **mainly via duty cycle** — more names firing means the book is at-risk a
  larger fraction of the calendar (n_eff rises). The diversification/Sharpe gain from more
  concurrent names is **limited**: crypto-perp crowding is a single highly-correlated factor
  (cross-perp ρ ≈ 0.6-0.8), so effective independent bets grow slowly with N — which is exactly
  why B2 risk-parity was inert and B3 density diluted. Under the current **significance** gate
  (deflated full-Train return > 0, ≈ t > 2), the reseed needs only to lift the realized t
  comfortably above 2 — a lower, more reachable bar than the retired +0.10 materiality floor —
  which a wider universe should do by raising duty cycle (at-risk fraction ~33% → ~45-55%) even
  with limited diversification gain; it also lowers per-name ADV participation → more deployable
  capacity. Materiality (how much money) is then read off the run score and Season's judgment,
  not gated.
- **Secondary lever** (Season's protocol call, not within-lifecycle): a higher leverage/notional
  budget would raise deployable scale (the run score), independent of the significance gate.

This is Season's decision; it changes neither the protocol nor this run. A reseed is a new
lifecycle with a return-blind universe chosen on eligibility, never by dropping names that lost.

- **B9 (long_hold_minutes 720 → 480; N=18 live base):** The one lever an adversarial review
  found unclosed — hold length isolated on the live cadence-240/TWAP base and scored on
  t/floor (A7 tested 480 on the stale cadence-120 base, judged on PF). Mechanism — `t = Sharpe
  × √(duty_cycle × window_years)`; the book is at-risk only ~33% of the calendar. A shorter
  hold frees capital sooner (the `active_until` lock releases earlier), so if freed capital
  re-enters OTHER crowded-shorts it raises duty cycle / independent-bet count → higher n_eff →
  higher t, the direct path to the +0.10 floor. Falsifier — t/floor flat or worse: the shorter
  hold captures less of the slow reversal (lower per-minute Sharpe) more than the extra
  re-entries add n_eff (A7 halved return on the old base), OR freed capital finds no other
  crowded-short to enter (1-3 concurrent cap). P(clears +0.10) ~0.15 — decisive either way:
  it closes the last within-8-name lever and confirms/refutes the plateau.

- **B9 result (attempt-0010): FALSIFIED — the last within-8-name lever is closed; hold 720
  optimal.** hold 480: deployed vol 9.2% → **11.7%** (highest of the lifecycle) and return 34.8%
  → **39.6%** (highest raw), trades 306 → 352 — so duty cycle DID rise, as the review's mechanism
  predicted. But edge quality collapsed: PF 1.705 → 1.481, win 56.5% → 50.9%, so Sharpe fell
  faster than n_eff rose and **t dropped 1.99 → 1.61**, deflated floor −0.002 → **−0.096**. In
  `t = Sharpe × √(duty × years)` the duty gain was swamped by the Sharpe loss — the reversal
  needs the full ~720-min window. Reverted to 720. Every within-8-name lever is now exhausted:
  capacity/TWAP (lifts vol not t), weighting (inert), cadence (dilutes), stop-loss (no left tail),
  cross-section filter (load-bearing), hold length (dilutes). **Plateau confirmed on 8 names — no
  strategy edit reaches the t ≈ 2.7 the +0.10 floor needs.** The reseed (larger universe → higher
  duty cycle AND more concurrent bets → higher t) is the only remaining lever.

## Iteration Log (archived prior lifecycle — edge-lessons durable, gate-lessons obsolete)

Retained for its mechanism findings; its breadth/subwindow-gate conclusions are superseded
by the corrected harness (see Current Lifecycle above). Prior five-name attempts are archived
and do not seed this ledger.

- **A0 baseline (both sides, cadence 120, top_n 5 of 8, holds 720):** discard,
  score -0.025. 2332 trades, 343+/subwindow so `subwindow_coverage` now PASSES
  (the five-name starvation is gone). But the loose both-sides book is unprofitable:
  PF 0.93, full-Train return -1.0%, avg net ~0. `money_floor` fail (deflated -0.040),
  `subwindow_consistency` fail (3/6 windows negative: train_2,3,4 = mid-2025),
  `breadth` fail (1.0). by_direction REPLICATES the five-name split: longs
  (fade crowded shorts) 368 trades, +0.80% gross / **+0.55% net**; shorts
  (fade crowded longs) 1964 trades, **-0.10% gross / -1.41% net** — no short-side
  gross alpha, then buried by costs. Shorts are 84% of trades and pure drag.
  Lesson: the broad universe fixed coverage; edge quality (the losing short side)
  is the binding problem, exactly as on five names.
- **A1 (long-only: shorts off):** Hypothesis - removing the demonstrated-losing
  short side (negative gross, 1964 trades) leaves the +0.55%-net long book; PF
  should jump well above 1, full-Train return turn positive, `money_floor` improve,
  and `subwindow_consistency` ease (fewer negative windows). The broad universe
  roughly doubled long trades vs five names (368 vs ~186), so density should hold
  (>=120, >=12/subwindow). Falsifier - PF stays near 1 (the loose long edge is
  noise too) or trades crater below the floor. Watch breadth: long-only is sparser,
  so concentration may stay 1.0 (the structural breadth problem), and watch whether
  the long edge is cross-sectional alpha or 2025 long beta in the by_symbol split.
- **A1 result:** discard, score +0.006 (positive). PF 0.93->1.26, full-Train
  return -1.0%->**+6.4%**, deployed vol 1.3%->3.2%, PSR 0.87, `subwindow_consistency`
  now PASS, `cost_stress_retention` 0.66 PASS. But `money_floor` still fail
  (deflated -0.051): return +6.4% with SE ~5.7% -> **t-stat ~1.1**, the long edge
  is real but lumpy. `subwindow_coverage` now FAIL (min 9 < 12: long-only is
  sparser, the mid-2025 window thins). `breadth` 1.0 (structural). ALPHA-vs-BETA:
  by_symbol net positive for 6 of 8 names (DOGE +0.83%, XRP +0.72%, SOL, ADA, ETH,
  BTC > 0; LINK, BNB slightly negative) - broadly cross-sectional, not one-name
  beta. BTC/ETH rarely fire as longs (6-8 trades): crowded-short setups are mostly
  an altcoin phenomenon. Lesson: long-only is the right edge; the binding wall is
  the thin Sharpe LCB (t ~1.1) plus the structural breadth gate. Kept long-only.
- **A2 (min_same_sign_funding_events 3 -> 2; long-only):** Hypothesis - the thin
  mid-2025 window is setup-scarce; requiring 3 same-sign funding events over-filters
  regimes where crowding is present but less persistent. Relaxing to 2 admits more
  long setups across all windows (especially the thin one), lifting
  `subwindow_coverage` past 12 and raising the money-floor t-stat via more
  similar-quality trades (prior five-name evidence: this relaxation kept PF ~1.7,
  unlike dropping magnitude gates which tanked PF). Falsifier - PF drops materially
  (relaxed longs are noise) or the thin window stays < 12 (genuine regime scarcity).
- **A2 result:** discard, score +0.020 (best yet). PF 1.26->**1.33** (relaxation
  improved the edge, did not dilute it), return 6.4%->7.1%, PSR 0.87->0.92,
  `money_floor` deflated -0.051->-0.030 (t-stat ~1.1->~1.4), deployed vol 2.9%,
  427 trades. But `min_subwindow_trades` STILL 9 - the thin mid-2025 window did NOT
  populate, so it is genuinely **setup-scarce** (that regime lacks crowded-short
  setups), not filter-limited. `subwindow_coverage` and `breadth` (1.0) still fail.
  Kept min_same_sign 2. KEY REFRAME: money_floor deflates `return - 2*SE`, still
  negative, so scaling deployed vol cannot help until t-stat > 2 - and the t-stat is
  low precisely because the book is concentrated (1 name at many bars -> high
  idiosyncratic portfolio vol -> low Sharpe). Breadth and money_floor are the SAME
  problem: more independent names held CONCURRENTLY diversifies the portfolio return
  series (higher Sharpe t-stat) and lowers peak concentration. Concurrency is the target.
- **A3 (decision_interval 120 -> 60; long-only):** Hypothesis - 2x decision points
  double cohort overlap, so more names are held simultaneously: this diversifies the
  portfolio return series (lower SE -> higher money-floor t-stat), lowers peak symbol
  concentration toward the breadth threshold, and adds closed trades per window.
  Falsifier - breadth stays 1.0 and t-stat flat (scarce periods with no setups
  dominate the peak-concentration metric -> a continuous-hold restructure is
  required), or deployed vol drops from peak-gross normalization with no t-stat gain.
- **A3 result: FALSIFIED cohort overlap.** Cadence 60 CRASHED deployed vol
  2.9%->0.64% (frequent synchronized cohort entries pin peak bar-participation at
  the 0.50 cap, collapsing the calibrate_vol scalar), diluted PF 1.33->1.19, return
  ->0.9%, `cost_stress_retention` fail, and `breadth` STILL 1.0. Score went negative.
  Confirms discrete cohort entries cannot fix breadth/t-stat/vol: scarce periods
  still give single-name bars, and synchronized entries pin capacity. Reverted to
  the A2 base (cadence 120). The structural restructure is now justified.
- **A4 (BOLD: continuous standing top-N book; long-only, cadence 120):** Replace
  fixed-horizon cohort exits with a standing book that holds the crowded top-N
  continuously and rotates a name to flat only when it leaves the top-N. Only the
  rotation delta trades each rebalance. Hypothesis - (1) `breadth` improves: the
  book holds >=2 names continuously wherever the universe supplies >=2 crowded
  candidates, dropping peak concentration below 1.0; (2) money-floor t-stat rises:
  a diversified portfolio return series has lower SE; (3) deployed vol rises:
  staggered deltas spread participation, relieving the peak-bar-participation
  capacity cap that A3 showed pins vol. Falsifier - breadth stays ~1.0 and t-stat
  /vol flat (scarce single-name periods dominate the peak metric -> the gates are
  structurally outside the frozen envelope for this sparse event-driven thesis,
  reseed evidence), PF collapses (continuously holding a decaying reversal bleeds
  the edge), or closed-trade rotation is too slow to clear the per-subwindow floor.
- **A4 result: FALSIFIED continuous holding.** It DID fix `subwindow_coverage`
  (760 trades, min 19) - rotation supplies closed trades. But PF dropped 1.33->0.98
  (below 1): holding a name until it leaves the top-N holds through and past the
  reversal, giving back the snapback the fixed-horizon exit captures. And `breadth`
  STILL 1.0 even continuously held - confirming the metric is intrinsically 1.0 for
  this edge. `cost_stress_retention` failed badly (-0.85). Two durable lessons: the
  fixed-horizon exit is essential (the reversal is captured in a ~12h window), and
  breadth is a structural envelope wall. Reverted to the A2 fixed-horizon base.
- **A5 (min_abs_funding_bps 1.0 -> 3.0; long-only, fixed-horizon):** Hypothesis -
  the primary gate is `money_floor` (t ~1.4, needs > 2); the lever is per-trade edge
  quality. Requiring stronger summed funding crowding (1->3 bps) concentrates on the
  most extremely-positioned names, where the reversal should be cleaner -> higher
  per-trade net and Sharpe -> higher money-floor t-stat. Falsifier - PF/t-stat do
  not improve (funding magnitude does not predict reversal strength, echoing the
  price-extension-magnitude null) or trades crater below the 120 floor. Expect
  coverage/breadth to stay failed (sparser book) - acceptable, both look structural.
- **A5 result: FALSIFIED crowding-magnitude selectivity.** min_abs_funding 1->3 cut
  PF 1.33->1.21, return 7.1%->2.3%, halved trades (427->173, min_subwindow 3),
  worsened the t-stat. Stronger summed funding does NOT predict cleaner reversals.
  With the earlier price-extension-magnitude null, MAGNITUDE thresholds are a
  confirmed dead lever: the edge is in the presence of persistent crowding +
  idiosyncratic dislocation, not its extremity. Reverted min_abs_funding to 1.0.
- **A6 (max_recent_same_direction_return_bps 250 -> 100; long-only, A2 base):**
  Hypothesis - the long side fades crowded shorts whose price has already fallen;
  entering a name still free-falling (recent 60-min return very negative) is a
  falling knife that loses before reverting. Tightening the guard to reject names
  that fell > 100 bps in the last hour enters only after the crash decelerates ->
  better reversal timing -> higher per-trade net and Sharpe -> higher money-floor
  t-stat. Falsifier - PF/t-stat do not improve (entry timing is not the issue) or
  the guard cuts so many entries that the book falls below the trade floor.
- **A6 result: FALSIFIED the entry-timing guard.** max_recent 250->100 slightly hurt
  (PF 1.33->1.26, return 7.1%->5.6%, t-stat worse, 402 trades). Rejecting hard-fallen
  names removed good reversals - the larger the crowded-short capitulation, the better
  the bounce, so the looser 250 guard is better. Reverted to 250. PATTERN (A3-A6):
  the A2 config is robust; every tightening (cadence, magnitude, entry-timing,
  continuous-hold) removes good trades or bleeds the edge. The per-trade edge sits at
  its natural operating point (PF ~1.33, t ~1.4).
- **A7 (long_hold_minutes 720 -> 480; long-only, A2 base):** Hypothesis - the
  reversal horizon shapes per-trade Sharpe. If the crowded-short snapback is largely
  captured within ~8h, exiting at 480 locks it in before post-reversal mean-reversion
  noise erodes it -> higher per-trade Sharpe / lower variance -> higher money-floor
  t-stat, and faster capital recycling. (closed-trade count is setup-limited, so
  coverage is unchanged by hold length.) Falsifier - PF/t-stat drop (the reversal is
  slow and needs the full ~12h, echoing the five-name horizon scan where 240 was too
  short); then test the longer side (1080).
- **A7 result: FALSIFIED faster capture; reversal is slow.** hold 480 cut PF
  1.33->1.15 and worsened the t-stat (return 3.6%, deflated -0.042) - 480 captures
  too little of the slow snapback. Side effect: shorter holds let names re-enter
  sooner -> 529 trades, min_subwindow 13, so `subwindow_coverage` incidentally
  PASSED, but at a diluted edge. 720 beats 480; horizon optimum is >= 720.
- **A8 (long_hold_minutes 720 -> 1440; long-only, A2 base):** Hypothesis - the
  money_floor needs t > 2, and t is scale-invariant, so deployed-vol/capacity relief
  cannot help while return - 2*SE < 0. The one remaining t-stat lever is
  DIVERSIFICATION: holding more independent names concurrently lowers the portfolio
  return SE for the same per-trade edge. Longer holds maximize cohort overlap -> more
  concurrent names -> lower SE -> higher money-floor t-stat, and may lower peak
  concentration (breadth). Watch the t-stat/SE, not PF. Falsifier - t-stat stays
  ~1.4 (over-holding erodes the per-trade edge enough to cancel the diversification
  gain, as the five-name 1440 scan hinted) -> the t-stat ceiling is firmly < 2 and
  money_floor is outside the frozen envelope.
- **A8 result: FALSIFIED diversification-via-longer-holds.** hold 1440 made the
  t-stat WORSE (deflated -0.062 vs A2 -0.030): longer holds raised deployed vol to
  3.4% but produced overlapping, autocorrelated 24h returns -> low effective sample
  size -> higher SE, and cut closed trades to 291 (min_subwindow 7). PF ~flat (1.30).
  720 is the horizon optimum. VERDICT FORMING: every t-stat lever (selectivity A5,
  timing A6, cadence A3, continuous A4, shorter A7, longer A8) is worse than A2; the
  edge's t-stat ceiling is ~1.4, below the money_floor's effective t>2. Remaining
  untested levers are signal CONSTRUCTION (dislocation window, crowding window,
  per-symbol vol normalization), not thresholds.
- **A9 (return_lookback_minutes 120 -> 240; long-only, A2 base):** Hypothesis -
  crowded positioning builds over a price dislocation; measuring idiosyncratic
  extension over 4h instead of 2h may identify genuinely crowded names more cleanly
  (less micro-noise in the dislocation), sharpening per-trade edge and the t-stat.
  Falsifier - PF/t-stat flat or worse (the 2h window already captures the
  dislocation, or a longer window stales the signal).
- **A9 result: FALSIFIED the longer dislocation window.** return_lookback 240 worse
  (PF 1.33->1.25, return 5.4%, deflated -0.046). The 2h dislocation window is better;
  a 4h window stales the signal. Reverted to 120.
- **A10 (funding_lookback_events 5 -> 3; long-only, A2 base):** Hypothesis - summing
  5 funding settlements (~40h) mixes fresh and stale crowding; the most recent 3
  (~24h) may capture currently-actionable crowding more cleanly -> better reversal
  timing and t-stat. Falsifier - PF/t-stat flat or worse (5 events already define
  crowding well, or 3 is too noisy a crowding estimate).
- **A10 result:** discard, score +0.004. funding_lookback 3 PASSED subwindow_coverage
  (368 trades, min 14) and tied the money_floor (deflated -0.029 vs A2 -0.030), but
  lower return (3.6%) and score. No real money_floor progress - the t-stat stays ~1.4
  regardless of signal window. Reverted funding_lookback to 5 (A2 best by score).
  Parameter space is now well-mapped; A2 is a robust local optimum.
- **A11 (min_idiosyncratic_return_bps 2.5 -> 0; long-only, A2 base):** Component
  isolation, not tuning. The long condition requires a name to be idiosyncratically
  down versus the cross-section mean (`market - extension >= min_idio`). Removing it
  (min_idio 0) keeps only funding crowding + absolute price-down. Hypothesis - if PF
  holds, the cross-section requirement is unnecessary complexity (simplify); if PF
  drops, the edge is genuinely CROSS-SECTIONAL (supporting the alpha read, since a
  relative-value requirement matters). Falsifier for "edge is cross-sectional" - PF
  is unchanged with min_idio 0.
- **A11 result:** discard, score +0.0176 (~tie with A2 +0.020). min_idio 0 left PF
  ~unchanged (1.33->1.31), return 6.8%, money_floor -0.033 (~A2). The 2.5 bps
  cross-section filter is nearly INERT - the edge is funding-crowding + absolute
  price-down, not the relative-value requirement. Implication: universe REDUCTION
  would likely hurt (the binding lever is the t-stat, helped by diversification; the
  cross-section mean is robust to dropping the low-firing majors BTC/ETH, ~3% of
  trades). Stay at 8 names (top of the 2-8 band). Reverted min_idio to 2.5 (best score).
- **A12 (top_n 5 -> 8; long-only, A2 base):** Hypothesis - the binding gate is
  money_floor (t ~1.4) and the one un-exhausted t-stat lever is diversification.
  Taking ALL qualifying longs each decision (up to 8, vs capping at 5) holds more
  independent names concurrently -> lower portfolio return SE -> higher t-stat.
  Falsifier - t-stat flat (fewer than 5 longs usually qualify, so the cap rarely
  binds) or lower (the 6th-8th-ranked longs are weaker and dilute).
- **A12 result: IDENTICAL to A2** (score +0.0205, PF 1.332, every metric byte-equal).
  top_n 8 = top_n 5 exactly -> the cap never binds, so FEWER THAN 5 longs qualify per
  decision. KEY STRUCTURAL FINDING: simultaneous crowded-short setups across 8 majors
  are sparse (usually 1-3 concurrent). This single fact caps diversification (-> t-stat
  ceiling ~1.4) AND forces single-name bars (-> breadth 1.0) - the two failing gates
  share one root cause: setup sparsity. The lever to relieve it is MORE simultaneous
  setups = a LARGER universe (15-25 names), not fewer; that exceeds the operator's 2-8
  cap, so it is a reseed recommendation, not a within-lifecycle move. top_n and
  selection_score are inert (rarely bind) and not worth testing. Reverted top_n to 5.
- **A13 (min_same_sign_funding_events 2 -> 1; long-only, A2 base):** Ablation of the
  crowding-persistence requirement. Hypothesis - requiring 2 same-sign funding events
  filters for persistent (not one-off) crowding; dropping to 1 admits any single
  same-sign event. If PF holds, persistence is unnecessary (simplify); if PF drops,
  persistent crowding is the real signal. Falsifier for "persistence matters" - PF
  unchanged at min_same_sign 1.
- **A13 result: NEW BEST + simplification.** min_same_sign 1 marginally beats A2 on
  every metric: score +0.0225 (>+0.0205), PF 1.341, return 7.25%, money_floor -0.027
  (best yet), PSR 0.927. Crowding persistence was mild over-filtering; a single
  same-sign event suffices and is simpler. Adopted as the base (call it A13-base).
  t-stat ~1.45 - still far below the money_floor's effective t > 2. Gates failing:
  money_floor, subwindow_coverage (min 9), breadth (1.0).
- **A14 (max_recent_same_direction_return_bps 250 -> off; A13-base):** Ablation of
  the falling-knife guard. A6 showed tightening it to 100 hurt; does removing it
  entirely (admit names that fell > 250 bps recently) help or stay neutral? If
  neutral-or-better, the guard is removable complexity (simplify). Falsifier for
  "guard matters" - PF drops when the guard is off (the hardest free-falls do need
  excluding).
- **A14 result: SIMPLIFICATION improves the binding gate.** max_recent off gives the
  best money_floor of the lifecycle (deflated -0.0199 vs -0.027), best PF (1.370),
  best PSR (0.936), t-stat ~1.52 - admitting hard-fallen names helps (biggest
  crowded-short capitulations bounce best). Score +0.0216 (~tie, marginally below
  A13's +0.0225) but the binding money_floor and PF/PSR all improve, and it is
  simpler. Adopted (recent guard off). Narrative: the edge gets CLEANER by removing
  filters - the original guard/persistence filters were fitting noise; the simple
  "fade crowded-short dips" core is best. money_floor still -0.0199, far from +0.10.
- **A15 (min_abs_funding_bps 1 -> 0; A14-base):** Ablation of the funding-magnitude
  floor. funding_pressure is the summed funding over 5 events; the floor requires
  |sum| >= 1 bp. Setting 0 keeps only the SIGN (negative funding = crowded short).
  Hypothesis - consistent with the simplification trend, the sign is the signal and
  the magnitude floor screens out little; removing it admits more crowded-short names
  at equal/better edge. Falsifier - PF drops (the 1 bp floor was screening genuine
  non-crowding noise).
- **A15 result: FALSIFIED sign-only; funding floor is load-bearing.** min_abs_funding
  0 dropped PF 1.37->1.18, return ->3.0%, money_floor -0.028, but added trades (717,
  min_subwindow 24 so coverage passes). Admitting near-zero-funding names dilutes the
  edge - the 1 bp funding floor is the real crowding screen and must stay. Reverted to
  1.0. Minimal sufficient core: negative funding >= 1 bp + price-down (persistence and
  the falling-knife guard are removable; the funding-magnitude floor is not).
- **A16 (min_idiosyncratic_return_bps 2.5 -> 0; A14-base, recent-guard-off):** Final
  simplification check - A11 showed the cross-section filter inert on the
  min_same_sign-2 base; re-test on the simplest base. Hypothesis - min_idio 0 leaves
  PF ~unchanged (filter inert) -> the minimal strategy is just "negative funding
  >= 1 bp + price-down," dropping the cross-section requirement. Falsifier - PF drops
  (the relative-value screen does work once the other filters are off).
- **A16 result:** discard, score +0.0191. min_idio 0 slightly WORSE (PF 1.370->1.349,
  money_floor -0.0199->-0.022): once the noise filters are off, the cross-section
  screen does a little real work. min_idio 2.5 stays. A14-base confirmed as the
  optimum (PF 1.37, money_floor -0.0199, t ~1.52). Minimal sufficient strategy:
  negative funding >= 1 bp + price-down + idiosyncratically-down-vs-peers >= 2.5 bp;
  persistence and the falling-knife guard removed.
- **A17 (refined two-sided: shorts ON, A14-base filters):** The baseline both-sides
  book was LOOSE; this re-tests two-sidedness with the REFINED filters. Decisive
  alpha-vs-beta test: mirror the optimized long logic to shorts (positive funding +
  price-up + idiosyncratically-up >= min_idio). Hypothesis - if selective shorts pay
  (short-side PF > 1), the edge is genuine two-sided crowding-reversal alpha AND the
  extra concurrent names diversify the portfolio return series -> lower SE -> higher
  money-floor t-stat (the binding lever). Falsifier - shorts still lose net even
  selectively (short-side gross <= 0), confirming the edge is one-directional
  (long-only, with a long-beta component) and two-sided adds only cost + drag.
- **A17 result: DECISIVE - the edge is one-directional.** Refined two-sided: longs
  +0.96% gross / +0.66% net (432 trades), shorts -0.20% GROSS / -1.54% net (1999
  trades). Even with identical optimized filters, the short side has no gross edge.
  Score -0.025, PF 0.93. Mechanism: in crypto, positive funding (longs pay) is the
  NORMAL regime (structural long premium), so "positive funding + price-up" is not a
  reliable crowding signal and shorting it fights the drift; negative funding (shorts
  pay) is a genuine short-capitulation stress signal, and fading it (long) catches
  the bounce. The tradeable edge is specifically "fade crowded-short capitulations,
  go long" - real, broadly cross-sectional (6/8 names), one-directional, with a
  long-beta tailwind. Reverted to long-only (A14-base).
- **A18 (take_profit_frac 0.05 via price-path RiskRule; long-only, A14-base):**
  Risk-shape lever for the t-stat. The Sharpe LCB is weak because the per-trade
  return distribution is fat-tailed (a few big winners drive the mean). A take-profit
  at +5% caps the right tail -> lower kurtosis -> tighter Sharpe SE -> higher
  money-floor t-stat, accepting a slightly lower mean. New param `take_profit_frac`
  attached as a RiskRule on the long entry; the fixed-horizon flat target remains the
  primary exit and the barrier fires earlier when price reaches +5%. Falsifier - PF
  /return fall more than the SE tightens (the edge needs the big winners) -> t-stat
  flat or worse, meaning the lumpiness is intrinsic and not trimmable without killing
  the edge.
- **A18 result: FALSIFIED risk-shape.** take_profit 5% dropped PF 1.37->1.32, return
  ->5.5%, money_floor -0.022. Capping the right tail loses the bigger bounces - the
  big winners ARE the edge; the lumpiness is intrinsic. Reverted take_profit to 0.
  A14-base confirmed as the global optimum across every lever tested.

## Stop Verdict (40 experiments; no feasible baseline, envelope-bound)

The thesis did NOT clear the Train gates, but the binding constraints are the
protocol ENVELOPE, not the edge. The edge is real and survives extensive search.

**Best Train config (frozen, = attempt-0028/0031; reproducible):** long-only
crowding-reversal on the 8 majors, cadence 240, `min_same_sign=1`,
`min_abs_funding=1`, `min_idio=2.5`, recent-guard off, hold 720, `top_n=5`,
fixed-horizon exit. Score +0.0335, PF **1.69**, full-Train return **+6.5%**,
full-Train **t-stat +2.07**, PSR **0.98**, all 6 subwindows positive (+2.6% to
+13.1%), 7/8 symbols positive, cost-stress retention pass.

**Gates failed (3 of 10):**
- `money_floor` (deflated +0.0023, needs +0.10): the Sharpe lower bound clears 2,
  so this is NOT edge-limited. Deployed vol is capacity-throttled to 1.6% (vs 15%
  target; bar-participation pinned at 0.50). At t~2 and feasible vol, the deflated
  return is ~+0.002; even full capacity relief to target vol reaches only ~+0.02 -
  still far below +0.10. The 0.10 deflated-return gate is outside the $1M /
  adv_impact / leverage-1.0 envelope for an edge of this Sharpe and deployable scale.
- `breadth` (1.0, structural): peak single-symbol share of the marked book is 1.0
  whenever the book holds one name at any bar, which a sparse event-driven
  crowding book does constantly. Confirmed 1.0 across every config, both
  structures, sparse and dense books. Incompatible with this thesis's sparsity
  unless diluted with non-crowded filler (which bleeds the edge).
- `subwindow_coverage` (min 7 < 12): the best-edge cadence (240) thins the trade
  count; faster cadence populates coverage but fails money_floor and breadth harder.

**Root cause (one fact):** simultaneous crowded-short setups across 8 majors are
sparse (usually 1-3 concurrent; `top_n`/`selection_score`/`min_cross_section` never
bind). That single fact caps diversification (Sharpe), forces single-name bars
(breadth 1.0), and thins per-window coverage. The lever that relieves all three is
MORE simultaneous setups = a materially LARGER universe (15-25 names) - which the
operator-set 2-8 cap excludes. Within the cap, 8 (the maximum) is optimal;
reducing would worsen the t-stat.

**Reseed recommendation (for Season; not executed):** re-run this same long-only
crowding-reversal mechanism on the full data-ready universe (~25 names). Expected
to relieve breadth (more concurrent names < 0.70 concentration), populate every
subwindow, and raise the Sharpe lower bound via diversification - directly
attacking all three failed gates at their shared root cause. Secondary lever:
relax the capacity/leverage envelope or add a probe-compatible entry-TWAP
(see UPSTREAM_LIMITATIONS_TODO.md) so the significant edge can deploy more notional.

A Train survivor was not produced; this is a candidate-quality edge blocked by the
frozen envelope, recommended for a larger-universe reseed - Season's decision.

## BREAKTHROUGH: Slower Cadence (cadence 240)

The robustness sweep surfaced a major result that overturns the "edge tops out at
t~1.5" reading. **cadence 240** (4h rebalance, vs the 120 base) gives score +0.0335
(new best), PF **1.69**, and the **first POSITIVE deflated money_floor (+0.0023,
t-stat ~2.07)** - the Sharpe lower bound finally clears 2. The edge is robust: all
6 subwindows positive (+2.6% to +13.1% annualized), 7/8 symbols positive. Fewer,
higher-quality entries at 4h marks plus less cohort overlap tighten the SE.

The binding constraint has FLIPPED. With t > 2, the money_floor is no longer
edge-limited; deployed vol is throttled to 1.6% (capacity_bound, max_feasible_vol
1.6% vs 15% target), so the deflated money (+0.0023) is small purely because the
$1M / adv_impact / leverage-1.0 envelope will not let the book deploy more. CAPACITY
is now the binding lever. Per the contract, relieving it (spread entries across bars,
slower rebalance, longer holds) is the alpha work, not a wall to route around.

Open directions from here: (1) even slower cadence (300-480); (2) capacity reshaping
to lift max_feasible_vol toward target. NOTE: this is a live, climbing direction, so
iteration continues past the 40-experiment marker toward the configured stop.

### Cadence/capacity exploration

- **cadence 360 (A29):** WORSE - PF 1.69->1.37, money_floor back to -0.035. cadence
  240 is a sharp, real peak. Mechanism: 4h decision points (00,04,08,12,16,20 UTC)
  hit the 8h funding-settlement times (00,08,16) plus midpoints; 6h (360) misses
  settlements. Reverted to 240 (the breakthrough base = attempt-0028).
- **entry TWAP (A30, entry_twap_bars 4):** Capacity reshaping - ramp each name's full
  target in over 4 consecutive 1-min bars (engine trades the per-step delta) so no
  single bar pins the 0.50 bar-participation cap that throttles deployed vol to 1.6%.
  Hypothesis - max_feasible_vol rises toward the ADV-participation ceiling (~0.25 vs
  current 0.09, so ~2-3x headroom), lifting the deflated money_floor from +0.002
  proportionally while the edge is unchanged (a few-bar entry spread is negligible
  over a 12h hold). Falsifier - vol does not rise (bar participation is not the binding
  cap, or per-symbol participation is unchanged by spreading one name across bars).
  Even on success, money_floor is expected to stay well below +0.10 - confirming the
  envelope (not the t-stat) binds.
- **A30 result: CRASH (causality).** The entry-TWAP ramp triggered the micro-causality
  probe's `hidden_lookahead_suppression_detected`. The ramp uses only signal-time data
  (every step's as_of = the signal bar; no future dependence), so this is a probe
  limitation on multi-decision-per-signal patterns, not real lookahead. Capacity
  reshaping via intra-symbol TWAP is therefore not admissible under `causality_check =
  micro`; recorded in UPSTREAM_LIMITATIONS_TODO.md. Reverted the TWAP code; restored
  the cadence-240 breakthrough config (= attempt-0028) as the survivor base.
- **A31 (repair + confirm):** Re-run the restored cadence-240 config to repair the
  crash and confirm the breakthrough result reproduces (expect score ~+0.0335, PF
  ~1.69, deflated money_floor ~+0.002, all subwindows positive).
- **A31 result: CONFIRMED + repaired.** Reproduced attempt-0028 exactly: score
  +0.0335, deflated money_floor +0.0023, return 6.5%, PF 1.686, PSR 0.981, all
  subwindows positive, deployed vol 1.6% (capacity_bound). continuation allowed
  (crash cleared). This is the frozen best config (see Stop Verdict). 40 experiments
  reached; productive within-envelope directions exhausted (cadence peaked at 240,
  capacity relief probe-blocked, larger universe operator-capped). Stop.

## Robustness Sensitivity Sweep (A19-A27, on the cadence-120 base)

Superseded as the base by the cadence-240 breakthrough, but the sweep confirmed the
cadence-120 optimum was single-peaked on every other axis.

With the optimum (A14-base) confirmed and the verdict essentially settled, the
remaining runs map both sides of each key parameter to confirm the optimum is a
stable peak rather than an overfit knife-edge. Tracked against A14-base
(PF 1.37, money_floor -0.0199, score +0.0216). Each entry: param, result, keep/revert.

- **hold 600 (A19):** score +0.004, PF 1.25, deflated -0.0147 (least-negative, but a
  low-vol artifact: return only 2.2%). Revert. 720 > 600 by score.
- **hold 960 (A20):** score +0.006, PF 1.34, deflated -0.033. Revert. Hold peak = 720
  (480, 600, 960, 1440 all lower by score).
- **cadence 180 (A21):** score +0.005, PF 1.36, deflated -0.0045 (least-negative of
  the whole lifecycle, again a low-vol artifact: return 1.4%). Revert. Cadence peak
  = 120.
- **return_lookback 60 (A22):** score -0.007, PF 1.16. Revert. With 240 (A9) also
  worse, dislocation-window peak = 120.
- KEY: the deflated money_floor is least-negative (~-0.0045) at LOW-deployment configs
  (slow cadence / short hold) but NEVER approaches +0.10 in any direction. The gate is
  unreachable across the entire vol/deployment tradeoff - the binding limit is the
  t-stat (~1.5 ceiling), not deployment.
- **funding_lookback 8 (A23):** score -0.018, PF 1.08. Revert. Peak = 5 (3 and 8 lower).
- **min_idio 5 (A24):** score +0.018, PF 1.35. Revert. Shallow peak near 2.5 (0 and 5 lower).
- **min_cross_section 6 (A25):** byte-identical to base - inert (>=6 candidates almost
  always present across 8 majors), like top_n. Revert to 4.
- **min_abs_funding 2 (A26):** score +0.002, PF 1.30. Revert. Funding-floor curve peaks
  at 1 bp (0->PF1.18, 1->1.37, 2->1.30, 3->1.21): low but nonzero is the sweet spot.
- SWEEP VERDICT: A14-base is a stable score-peak on every axis (smooth, single-peaked,
  not a knife-edge). Score-best of the whole lifecycle is attempt-0014 (min_same_sign 1,
  recent-guard at 250) +0.02254; money_floor-best is the guard-off variant -0.0199. No
  config clears money_floor (best deflated ~-0.0045 via low-vol, ~-0.0199 at full
  deployment) or breadth (1.0 everywhere).
