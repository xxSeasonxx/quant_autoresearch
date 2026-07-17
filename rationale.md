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

## Current Lifecycle — warm-start re-baseline under the significance gate (active)

Fresh lifecycle: the prior 8-name lifecycle (retired `money_floor` gate) was reset and
archived (logged below as *Prior Lifecycle*), and this baseline is warm-started from that
lifecycle's best configuration — attempt-0005: long-only crowding-reversal, cadence 240,
`min_same_sign 1`, `min_abs_funding 1`, `min_idio 2.5`, recent-guard off, hold 720,
`top_n 5`, equal weighting, **`entry_twap_bars 20`**. `strategy.py` is unchanged from that
config; the warm-start is a *starting point re-validated fresh under the new gate*, not an
imported result.

**Why re-run 8 names under the new gate (materially different).** The prior lifecycle failed
the retired `money_floor` (+0.10 deflated return) at a t ≈ 2.0 plateau and concluded "8 names
exhausted, reseed." That conclusion was **premature** (the loop stopped at attempt 9/50) and
does **not** carry into this lifecycle. The active `significance` gate passes at deflated
full-Train return ≥ 0 (≈ t ≥ 2) — the same plateau now sits *at* the bar, not far below it.
attempt-0005's deflated return was **+0.0032 (positive)**, so the warm-start baseline plausibly
**clears the significance gate**; `capacity_bound` is a passing diagnostic, not a kill.

**First failure mode to watch.** Whether the warm-start baseline clears significance (deflated
full-Train return ≥ 0) at a feasible, scoreable book; and, if it passes, whether the loop can
lift the deployed-return **score** (materiality — capacity, breadth, duty cycle) without pushing
the deflated return back below zero. The t ≈ 2 plateau makes significance marginal, so score
gains that cost t are the trap.

**This lifecycle runs to its configured stop** (a fired stop rule or `max_iterations = 50`),
maintaining the Reseed Log and Lever Enumeration below; a reseed case is consolidated only at a
stop rule, never as an early exit.

### Reseed Log (append-only; read only at a stop rule, never a stop trigger)

- (baseline, attempt-0001) warm-start **passes the significance gate** (deflated return LCB
  +0.0032, marginal) — **weakens the immediate "reseed now" case**: 8 names can clear the new
  gate, so the thesis is viable here, not envelope-dead. But significance is thin (t ≈ 2) and the
  score is capacity-throttled (10.1% vol < 15% target), so the wider-universe hypothesis
  (duty-cycle-led t lift + more deployable capacity) stays open as a score/robustness lever, to
  be re-argued from this lifecycle's evidence at a stop rule.
- (2026-07-02, attempt-0002) L1 vol-normalized dislocation DISCARD (−0.187): **neutral-to-weak
  for reseed** — a signal-construction lever, not an envelope constraint. It sharpens *where the
  edge is* (absolute-bps, vol-seeking, in high-vol altcoins) and shows per-trade quality is
  saturated on 8 names (book already holds the right 1–3), so it removes signal-construction as a
  within-8-name t lever — consistent with, but not itself, the universe-bound story.
- (2026-07-02, attempt-0003) L4 decoupled exit ramp DISCARD (significance fail, t 1.997):
  **strengthens the reseed case materially.** Capacity is now fully relievable to the 15% risk
  budget (score 0.282, return 56.5%, PF intact) yet significance still fails because t is
  scale-invariant and pinned at ~2.0 — direct evidence that the binding constraint is **t
  (universe-bound), not capacity or the edge**. A wider universe (higher duty cycle → higher
  n_eff → t robustly >2) is what would convert this deployed 56% return into a passing survivor.
- (2026-07-02, attempt-0004) L5 exit=30 crossover KEEP (new survivor 0.282, t 2.024): **neutral
  for reseed on the edge, but sharpens the framing** — an 8-name all-gates-pass survivor exists
  once capacity is fully deployed, so the thesis is *viable* here (not envelope-dead under the
  new gate). The reseed remains the lever for a *higher/robust* t (the pass is knife-edge at
  t≈2.02), not for viability.
- (2026-07-02, attempt-0005) L6 funding recency DISCARD: **strengthens** — another within-8-name
  edge-quality lever falsified; the per-trade edge is saturated (funding sign-only, price
  absolute-bps cross-sectional), so t cannot be lifted by signal construction on 8 names. Only
  more concurrent independent setups (wider universe) can.
- (2026-07-02, attempt-0006) L7 vol-scaled hold DISCARD (t→1.82): **strengthens** — exit-timing
  falsified; the reversal is funding/clock-driven, fixed 720 is right, cutting winners loses the
  edge. No exit lever lifts t on 8 names.
- (2026-07-02, attempt-0007) L8 median reference near-inert DISCARD: **strengthens** — the signal
  form is settled; cross-section reference robustness is not a lever. Every signal/funding/exit
  edge lever now falsified or inert → the 8-name per-trade edge is comprehensively saturated. The
  reseed (wider universe → duty cycle → robust t>2) is the sole remaining lever; the case is
  approaching consolidation at enumeration closure.
- (2026-07-02, attempt-0008) L9 dislocation sizing KEEP (new survivor 0.291, t 2.043, PF 1.747):
  **neutral-to-slightly-weakening for reseed on viability, but sharpens it** — a *within-8-name*
  edge-quality win exists (conviction sizing), so the 8-name book is not fully wrung out and the
  survivor is stronger than thought. But the t gain (2.02→2.04) is still inside the ±0.1 knife-edge
  band; the significance pass remains marginal. The reseed is still the only lever for a *robust*
  (non-knife-edge) t, and now also for deploying the (improved) edge on more concurrent names.
- (2026-07-02, attempts 0007/0009/0010) L8 median / L10 disloc-hold / L11 beta-adjust — all
  DISCARD (near-inert or fail): **strengthen** — signal reference, exit-hold, and cross-name
  adjustment dimensions all closed; no within-8-name lever there lifts t.
- (2026-07-02, attempt-0011) L12 conviction convexity KEEP (new survivor 0.311, t 2.095, PF 1.797):
  **shifts the reseed framing from "envelope-dead" to "edge under-exploited"** — a second
  edge-quality win (super-linear conviction) shows real un-captured 8-name return the prior
  lifecycle missed, and t now clears 2.0 by ~0.095 (less marginal). The reseed case is now less
  "the thesis can't clear the gate" (it does, more robustly) and more "a wider universe would
  deploy this improved convex-conviction edge on more concurrent crowded-shorts, raising duty
  cycle for a more robust t and more deployed return."
- (2026-07-02, attempts 0012/0013) convexity bracket KEEP (survivor 0.326→0.335, t 2.146→2.175):
  **strengthens the "edge under-exploited" reading** — super-linear conviction is a robust,
  inspected (broad subwindow) win; the 8-name edge had real un-captured return. Reinforces that a
  wider universe should deploy this *improved* edge on more concurrent setups.
- (2026-07-02, attempt-0014) combined-conviction KEEP-by-score but REJECTED (overfit micro-gain):
  **neutral** — a mechanism-less +0.006 marks the overfit zone; the productive within-8-name search
  is done. Confirms closure: the reseed (wider universe) is the only remaining real lever.
- (2026-07-02, attempt-0015) recent-capitulation conviction DISCARD (worse): **strengthens** — the
  final within-8-name conviction axis falsified; conviction is dislocation-specific and fully
  exploited. Enumeration closed. Consolidated reseed case above stands: the binding constraint is
  the universe (1–3 concurrent setups → t~2.1 plateau), not the edge.

### Lever Enumeration (distinct levers × run/result, this lifecycle)

- baseline (warm-start attempt-0005 config, attempt-0001) — **KEEP; all 8 gates pass.**
  score 0.196, deflated return LCB +0.0032 (significance passes, marginal), full-Train return
  38.8%, deployed vol 10.1% (`capacity_bound` = passing diagnostic), PF 1.718, breadth 0.313,
  PSR 0.978, 306 trades, `failure_class = edge`. First gate-clearing Train survivor for this
  thesis; `continuation: allowed`.
- Prior-lifecycle levers (capacity/TWAP, weighting, cadence, exit/stop-loss, cross-section,
  hold length) are edge-characterized but must be **re-read against the significance gate**,
  where the bar is t ≥ 2, not the retired +0.10 floor; a lever that was "inert on money_floor"
  is not automatically settled here. Enumerate distinct levers with their results as the loop
  proceeds.

**Campaign framing (baseline diagnostics → where the score lever lives).** attempt-0001 is
capacity-bound with **bar-participation pinned at 0.50** and ADV participation only 0.047 (5× of
the 0.25 ADV ceiling): the binding cap is per-symbol single-minute liquidity, which the prior
lifecycle proved is **non-monotonic/fragile** in entry-TWAP (N=20 is a spike, not a plateau).
So within-8-name capacity is near-exhausted and is not a *robust* score lever. The score
(`return − 1·SE`) improves robustly by **lowering SE via signal quality** — cleaner trades →
higher per-minute Sharpe → higher t → higher score. The one frontier the prior lifecycle
flagged-but-never-ran is **signal construction** (its own A8 note: "remaining untested levers are
signal CONSTRUCTION … per-symbol vol normalization, not thresholds"). That is this campaign's
primary axis. Threshold/structure/cadence/hold/weighting/sides/stop-loss are gate-independent
physics already mapped; they are recorded run/settled here and not re-run as polish.

Planned distinct levers (execute one at a time; revise from diagnostics):
- L1 vol-normalized idiosyncratic dislocation (signal construction) — attempt-0002.
- L2 funding recency/acceleration weighting (signal construction) — pending.
- L3 alternative dislocation anchor (own-mean reversion z-score vs fixed-lookback) — pending.
- L4 capacity reshaping not yet tried honestly (confirms/refutes the ~10% ceiling) — pending.
- Simplification of whatever survivor emerges.

- **L1 (attempt-0002): vol-normalized idiosyncratic dislocation.**
  - *Mechanism:* the raw-bps cross-section screen (`market_mean − extension ≥ 2.5 bps`) is a
    tiny threshold for high-vol altcoins (they always pass) and meaningful only for low-vol
    majors, so the current book is effectively "any high-vol name that is idiosyncratically
    down at all." Dividing each name's extension by its own expected horizon move
    (`per_min_vol·√lookback`) makes the dislocation a σ-score, applying an equal relative-value
    bar across names → screens for genuinely large moves-vs-own-vol → cleaner per-trade edge →
    higher Sharpe/t → higher score.
  - *Observable:* PF, full-train t / SE, per-symbol mix (does it pull in low-vol BTC/ETH?),
    trade count, deployed vol.
  - *Falsifier:* PF/t flat or worse — either raw bps already captures the dislocation, or the
    edge genuinely lives in the high-vol altcoins and σ-normalization dilutes it by admitting
    weak low-vol setups (BTC net-negative, ETH tiny). Decisive about *where the edge lives*.
  - *Book effect:* selection set changes (σ-threshold 0.5); gross/turnover ~unchanged (shape,
    not magnitude); breadth may shift toward majors.
  - *Failure mode targeted:* thin/lumpy Sharpe (SE), the sole binding gate's marginal t≈2.
  - *Result (attempt-0002): DECISIVELY FALSIFIED — DISCARD, score −0.187.* σ≥0.5 collapsed the
    edge: trades 306→92, PF 1.72→**1.08**, full-Train return 38.8%→4.95%, deflated +0.0032→
    **−0.42**, cost-stress retention 0.78→**−0.91**, `trade_floor`/`significance`/`cost_stress`
    all fail, `failure_class = no_edge`. **Learning (durable):** the edge is *vol-seeking in
    absolute bps* — it lives in large-absolute-move idiosyncratic capitulations of the high-vol
    altcoins (DOGE/XRP/ADA/SOL). Dividing by own-vol de-selects exactly those (a big DOGE move
    is "only ~1σ for DOGE"), and because the crowded names co-move (ρ 0.6–0.8) the σ-idio-vs-mean
    is small for them → the screen keeps only weak low-vol setups. This sharpens B2 (inverse-vol
    weighting inert): the edge is not merely vol-agnostic, it is actively vol-seeking. **Corollary
    that reshapes the campaign:** no signal-construction lever leans *further* into the edge —
    the book already holds exactly the 1–3 right names (top_n/min_cross_section never bind), so
    per-trade quality is saturated on 8 names. Any σ-/mean-normalization variant (L3) would fail
    the same way; L3 dropped. Remaining distinct axes: **deployment (capacity reshaping, honest)**
    and simplification. Reverted to raw.

- **L4 (attempt-0003): decoupled exit ramp (capacity reshaping).**
  - *Mechanism:* deployed vol is capacity-bound with **bar-participation pinned at 0.50** while
    ADV sits at 0.047 (5× headroom). The prior lifecycle only ever ramped entry and exit
    *symmetrically* over one `entry_twap_bars` and found the symmetric ramp non-monotonic
    (N=20 spike). Exit is a separate synchronized event: at the fixed horizon every name in a
    cohort unwinds together, so exit minutes may pin the cap independently of entry. Spreading
    the *exit* over more bars (`exit_twap_bars` 20→40, entry held at 20) lowers per-exit-minute
    participation → higher `book_scale` → more of the real edge deployed → higher score. This is
    program-endorsed turnover spreading, not magnitude/leverage.
  - *Observable:* `book_scale`, `deployed_volatility`, `max_bar_participation` (does it drop
    below 0.50?), PF/t (must stay intact), trade count (unchanged — same entries).
  - *Falsifier:* `book_scale`/vol flat → exits were not the binding pin (entries pin), so the
    ~10% ceiling is entry-liquidity-bound and robustly exhausted; OR vol drops (longer exit
    touches thinner late-horizon minutes) → same non-monotonic fragility as symmetric TWAP.
    Either outcome honestly characterizes the 8-name capacity ceiling for the reseed case.
  - *Book effect:* turnover unchanged in total; exit participation per minute halved; effective
    hold ~20 min longer at the tail.
  - *Failure mode targeted:* implementation/capacity limit throttling deployed return (score).
  - *Result (attempt-0003): DISCARD (significance fail), but the capacity mechanism CONFIRMED
    and a major structural finding.* exit=40: `capacity_bound` **FALSE** — book_scale 0.33→0.53,
    deployed vol 10.1%→**15.0%** (hit the 15% risk-budget target), max-feasible 18.6%. The
    synchronized fixed-horizon exit **was** the binding 0.50 bar-cap pin; decoupling it deploys
    the book to its full risk budget. Return 38.8%→**56.5%**, PF **1.695** (intact), 306 trades,
    breadth 0.31, cost-stress pass, score 0.196→**0.282**. BUT significance FAILS: deflated
    **−0.0013**, t **1.997** (baseline 2.016). **Confirms the money-first structure:** capacity
    relief scales return and SE together → moves the score, not t (scale-invariant, universe-bound
    at ~2.0); extra exit-spreading also shaves t via return-series autocorrelation (B1 mechanism).
    So the fully-deployed book sits on the t=2 knife-edge. `max_feasible_vol` rises with
    exit-spreading (10.1%@20 → 18.6%@40), so there is a crossover exit_twap that reaches the 15%
    target with the LEAST spreading → least autocorrelation → highest t among fully-deployed
    configs. exit=40 overshot. Not reverted — carried as the deployment base for the L5 crossover
    probe.

- **L5 (attempt-0004): exit_twap crossover (full deployment at maximum t).**
  - *Mechanism:* find the smallest exit-spread that still reaches the 15% risk-budget target, so
    the book deploys the full edge (return ~56%, score ~0.28) while paying the *minimum*
    autocorrelation t-cost. exit=30 probes the crossover between deployed-vol=10.1%@exit=20 (t
    2.016, passes) and 15.0%@exit=40 (t 1.997, fails).
  - *Observable:* `capacity_bound`, deployed vs max-feasible vol, deflated_return_lcb / t,
    score, PF.
  - *Falsifier:* if exit=30 still deploys <15% (capacity_bound TRUE) OR t is still <2.0 →
    there is no fully-deployed point that clears t=2, so the significance gate is genuinely
    t-bound at the 8-name knife-edge and capacity cannot buy a passing survivor above 0.196.
  - *Failure mode targeted:* the score↔t tradeoff at the capacity frontier; whether a
    higher-score all-gates-pass survivor exists on 8 names.
  - *Result (attempt-0004): KEEP — NEW BEST SURVIVOR, all 8 gates pass, score 0.282.* exit=30
    reaches near-full deployment (deployed vol **14.5%**, capacity_bound just barely TRUE),
    return **55.7%**, PF **1.713**, 306 trades, breadth 0.31. Significance PASSES: deflated
    **+0.0066**, t **2.024** (> baseline 2.016 > exit=40's 1.997 — t bounces ±0.02 with exit
    spread, all within the ±0.1 knife-edge band around 2.0). **A real +44% score gain
    (0.196→0.282) from a robust monotonic capacity mechanism** (exit-un-pinning: vol 10.1→14.5→15%
    across exit 20→30→40, smooth, not a fragile spike). Adopted as the survivor base
    (`entry_twap=20, exit_twap=30`). Caveat carried: the significance pass is marginal (t≈2.02,
    8-name knife-edge). Not fine-sweeping exit_twap further — that would be knife-edge polishing.

**Survivor (this lifecycle, current): attempt-0004** — long-only crowding-reversal, cadence 240,
`min_same_sign=1`, `min_abs_funding=1`, `min_idio=2.5` (raw), recent-guard off, hold 720,
`top_n=5`, equal weighting, `entry_twap=20`, `exit_twap=30`. Score 0.282, all gates pass, t 2.024.

**State after L5: capacity is solved (full risk-budget deployment); the signal is saturated on 8
names (L1); t is universe-bound at ~2.0.** Remaining distinct levers are low-probability per-trade
edge/Sharpe probes (funding timing, dislocation reference frame, exit-completion timing,
vol-scaled hold) — each a genuine falsification that closes a dimension and accretes the reseed
case. Running them breadth-first to demonstrate (not assume) the 8-name plateau; will not
manufacture threshold-nudges to pad the count.

- **L6 (attempt-0005): funding recency weighting.**
  - *Mechanism:* funding_pressure is an equal sum over the last N settlements (~40h), mixing
    fresh and stale crowding. Exponentially weighting recent settlements more (`funding_decay`,
    scale-normalized so the magnitude scale is preserved) tests whether *fresh* crowding reverses
    more cleanly than time-averaged crowding → higher per-trade edge → higher Sharpe/t.
  - *Observable:* PF, t / deflated, trade count (should be ~flat — scale preserved), by-symbol.
  - *Falsifier:* PF/t flat or worse → funding is sign-only (crowded-short = negative funding),
    its timing/magnitude non-predictive (consistent with A5 magnitude-null, A10 count-flat,
    A15 sign-only-floor-load-bearing). Closes the funding-timing dimension.
  - *Failure mode targeted:* thin Sharpe (SE) via the funding signal dimension.
  - *Result (attempt-0005): FALSIFIED — DISCARD, score 0.062.* decay=0.5: PF 1.71→**1.44**,
    return 55.7%→20.3%, deployed vol→7.6%, significance fails (deflated −0.079), +33 trades,
    `failure_class = no_edge`. Recency-tilting admits names whose recent funding trends/flips
    sign → lower-quality setups → edge diluted. **Confirms funding is purely a sign detector**
    (crowded-short = negative funding); level/count/magnitude/timing all non-predictive
    (A5/A10/A15). Funding-timing dimension CLOSED. Reverted decay=0.

- **L7 (attempt-0006): vol-scaled ("risk-time") hold length.**
  - *Mechanism:* the fixed 720-min hold is a universe average, but the edge concentrates in
    high-vol altcoins (DOGE/XRP/ADA/SOL) whose capitulation-bounce plausibly completes faster in
    clock time. Holding in *risk-time* — hold ∝ (ref_vol/name_vol)^`hold_vol_scaling`, clamped
    [120,1440] — exits high-vol names sooner (locking the bounce before post-reversal noise) and
    low-vol names later, matching capture to each name's dynamics → higher per-trade Sharpe/t.
    `hold_vol_scaling=0` reproduces the fixed hold.
  - *Observable:* PF, t/deflated, holding-period spread, by-symbol PnL, deployed vol.
  - *Falsifier:* PF/t flat or worse → the reversal is funding/clock-driven (settles on the 8h
    schedule), so vol-scaling the hold mismatches the mechanism and the fixed 720 (A7/A8 peak)
    is right regardless of name vol. Closes the exit-timing dimension.
  - *Failure mode targeted:* exit mismatch / thin Sharpe (SE).
  - *Result (attempt-0006): FALSIFIED — DISCARD, score 0.231.* scaling=1: deployed full 15% vol
    but t dropped 2.024→**1.82** (significance fail), PF 1.71→1.64. Win-rate rose (0.573) but PF
    fell — cutting high-vol names short yields more small wins and **loses the big bounces** (the
    overshoots ARE the edge; same lesson as A18 take-profit). The reversal is funding/clock-driven;
    fixed 720 is right regardless of name vol. Exit-timing dimension CLOSED. Reverted scaling=0.

- **L8 (attempt-0007): robust cross-section reference (mean → median).**
  - *Mechanism:* the idiosyncratic dislocation is measured vs the cross-section MEAN extension.
    With a co-moving cross-section (ρ 0.6–0.8) a few extreme names skew the mean, adding noise to
    the "typical move" the idio is measured against. A median (or trimmed) reference is a robust
    estimate of the typical name's move → cleaner idiosyncratic signal → better selection → higher
    per-trade edge. This is the one distinct signal lever NOT answered by L1 (which was
    normalization, not reference robustness).
  - *Observable:* PF, t/deflated, trade count, by-symbol.
  - *Falsifier:* PF/t flat → with 4–8 candidates mean≈median, so the reference is already
    well-formed and reference robustness is not a lever. Near-inert expected; a clean final
    rigor check that the signal form is settled.
  - *Failure mode targeted:* thin Sharpe (SE) via cross-section reference noise.
  - *Result (attempt-0007): NEAR-INERT — DISCARD, score 0.274.* median: PF 1.699 vs 1.713, return
    55.5%, 305 trades — essentially identical to the mean survivor; t 1.97 (mean marginally
    better, significance just fails). With 4–8 candidates mean≈median → the cross-section reference
    is already well-formed; reference robustness is not a lever. Signal form SETTLED. Reverted to
    mean.

- **L9 (attempt-0008): dislocation-magnitude sizing.**
  - *Mechanism:* the book equal-weights the 1–3 selected names. Weighting each ∝ its idiosyncratic
    dislocation magnitude (gross preserved — shape, not magnitude) puts the most capital on the
    biggest capitulations, which A6 evidence says bounce biggest → higher return per unit risk →
    higher per-trade Sharpe/t. Distinct from B2 inverse-vol, which leaned *away* from the high-vol
    names that carry the edge; this leans *into* the confirmed vol-seeking/absolute-dislocation
    edge, so it is the most likely of the remaining levers to actually help.
  - *Observable:* PF, t/deflated, by-symbol PnL concentration, breadth (concentration must stay
    < 0.70), deployed vol.
  - *Falsifier:* PF/t flat → sizing cannot help a 1–3-name book (B2 lesson: too few concurrent
    names to reshape), so conviction-weighting is washed out like every other sizing lever.
  - *Failure mode targeted:* thin Sharpe (SE) — whether conviction sizing lifts per-trade edge.
  - *Result (attempt-0008): KEEP — NEW BEST SURVIVOR, all 8 gates pass, score 0.291.* Conviction
    weighting lifted PF 1.713→**1.747** (best of lifecycle), return 55.7→**57.0%**, t 2.024→**2.043**,
    deflated **+0.012** (best significance margin), breadth 0.314, 306 trades. **My "sizing inert"
    prediction was FALSIFIED** — dislocation-weighting helps because it leans *into* the confirmed
    edge (biggest capitulations bounce biggest, A6), unlike B2's inverse-vol which leaned away.
    First edge-QUALITY win of the lifecycle (PF up, not just capacity). Adopted. Lesson: lean-in
    conviction levers can beat the saturation prior — so the remaining "predicted-fail" levers
    deserve genuine tests, not dismissal.

**Survivor (updated): attempt-0008** — long-only crowding-reversal, cadence 240, `min_same_sign=1`,
`min_abs_funding=1`, `min_idio=2.5` (raw, mean reference), recent-guard off, hold 720, `top_n=5`,
`entry_twap=20`, `exit_twap=30`, **`weighting=dislocation`**. Score 0.291 (+48% vs baseline), t 2.043,
PF 1.747, all gates pass (significance marginal at the 8-name t≈2 knife-edge).

- **L10 (attempt-0009): dislocation-scaled hold (conviction on the time axis).**
  - *Mechanism:* the sizing win shows leaning into dislocation helps. Its time-axis analog: hold
    the biggest capitulations longer (`hold ∝ (idio/ref_idio)^hold_dislocation_scaling`, clamped),
    since a bigger crowded-short capitulation plausibly has a bigger, slower bounce (A6). Distinct
    from L7, which scaled by *vol* and cut high-vol names short (that hurt).
  - *Observable:* PF, t/deflated, holding-period spread, by-symbol.
  - *Falsifier:* PF/t flat or worse → either the reversal horizon is dislocation-independent (fixed
    720 right for all), or the return-series heterogeneity from varied holds costs more t than the
    conviction-PF gain adds (the L7 heterogeneity mechanism, direction-independent).
  - *Failure mode targeted:* exit mismatch / thin Sharpe (SE).
  - *Result (attempt-0009): FALSIFIED — DISCARD, score 0.246.* t 2.043→**1.93** (significance fail),
    PF 1.747→1.731, return→51%. The L7 heterogeneity mechanism dominated: varying hold length —
    even in the conviction direction — creates heterogeneous overlapping return series → lower
    n_eff → higher SE → lower t. **Clean contrast:** conviction helps via SIZING (0008 — same
    trades, reshaped weights, no heterogeneity) but not via HOLD. Exit/hold dimension now closed by
    FIVE converging falsifications (A7/A8/A18/L7/L9). Reverted to the 0008 survivor.

- **L11 (attempt-0010): beta-adjusted idiosyncratic dislocation.**
  - *Mechanism:* the current signal subtracts the beta=1 cross-section MEAN move; a high-beta
    (high-vol) altcoin that simply moved with the market then looks idiosyncratically dislocated
    when it is not. Subtracting a beta-scaled market move (`reference = beta × market_mean`,
    beta ≈ name_vol / cross-section_vol) removes the market-common component, leaving the true
    idiosyncratic residual → cleaner selection → higher edge. Generalizes raw (beta=1 ≡ current);
    distinct from L1 (which rescaled magnitude by own vol, not the reference by beta).
  - *Observable:* PF, t/deflated, by-symbol mix (does it de-select high-vol altcoins?), trades.
  - *Falsifier:* PF/t flat or worse → either the beta=1 mean is already adequate, or (like L1)
    beta-adjustment de-selects the high-vol altcoins whose *raw absolute* moves carry the edge.
    Together with L1 this definitively closes the "cross-name adjustment" question.
  - *Failure mode targeted:* thin Sharpe (SE) via market-beta contamination of the signal.
  - *Result (attempt-0010): DISCARD, score 0.271 — passes all gates but does not beat the survivor.*
    PF 1.728 vs 1.747, t 2.004 vs 2.043, return 54.1%. Beta-adjustment mildly de-emphasizes the
    high-vol altcoins (as L1 predicted, but gently — beta≈1.6/0.4 is a softer touch than full
    σ-normalization). **Together with L1 this definitively closes cross-name adjustment: the edge is
    raw absolute dislocation; neither vol-normalization (catastrophic) nor beta-adjustment (mild)
    helps.** Signal dimension SETTLED three ways. Reverted to raw.

- **L12 (attempt-0011): conviction-sizing convexity (weight ∝ dislocation²).**
  - *Mechanism:* the linear dislocation-sizing win (0008) shows conviction helps. A convex weight
    (`dislocation_weight_power` 1→2) concentrates capital further on the largest capitulations —
    the highest-conviction, biggest-expected-bounce signals — which should raise per-trade Sharpe
    if the edge scales super-linearly with dislocation. Gross preserved; a discrete structural test
    of the sizing win's shape, not an aimless sweep.
  - *Observable:* PF, t/deflated, `max_symbol_concentration` (breadth gate 0.70 — currently 0.31),
    deployed vol, score.
  - *Falsifier:* PF/t flat or worse, or breadth rises toward 0.70 → convexity over-concentrates a
    1–3-name book into single-name risk without an edge gain; linear conviction is the right shape.
  - *Failure mode targeted:* thin Sharpe (SE) / symbol concentration — the sizing win's optimal shape.
  - *Result (attempt-0011): KEEP — NEW BEST SURVIVOR, all 8 gates pass, score 0.311.* power=2:
    PF 1.747→**1.797** (best of lifecycle), return 57→**59.5%**, t 2.043→**2.095** (widest clearance
    of 2.0 yet), deflated **+0.027** (least-marginal significance pass), full 15% vol deployed,
    breadth 0.317 (safe). **Third consecutive conviction win** — the edge scales *super-linearly*
    with dislocation: biggest capitulations → biggest, cleanest bounces (A6). Adopted. The prior
    lifecycle missed this entirely (only tested inverse-vol, which leans the wrong way).

**Survivor (updated): attempt-0011** — long-only crowding-reversal, cadence 240, `min_same_sign=1`,
`min_abs_funding=1`, `min_idio=2.5` (raw, mean ref), recent-guard off, hold 720, `top_n=5`,
`entry_twap=20`, `exit_twap=30`, `weighting=dislocation`, **`dislocation_weight_power=2`**.
Score **0.311 (+59% vs baseline)**, t 2.095, PF 1.797, all gates pass.

- **L13 (attempt-0012): convexity bracket (power 2 → 3).**
  - *Mechanism:* convexity is a live climbing direction (equal→linear→convex² all improved). Test
    power=3 to bracket the optimum: does even sharper conviction concentration keep helping, or is
    ~2 the peak? One bracketing point, not a fine sweep.
  - *Observable:* PF, t/deflated, breadth (0.70 gate; 0.317 at p=2), score.
  - *Falsifier:* PF/t flat-or-worse, or breadth rises materially → p≈2 is the peak; over-concentration
    into single-name risk beyond that. Commit to the better of {p=2, p=3} and stop the exponent sweep.
  - *Failure mode targeted:* symbol concentration / diminishing conviction returns.
  - *Result (attempt-0012): KEEP — NEW BEST SURVIVOR, all gates pass, score 0.326.* power=3:
    PF 1.797→**1.837**, return 59.5→**61.0%**, t 2.095→**2.146**, deflated **+0.041** (most robust
    significance margin), full 15% vol, breadth 0.319 (safe), still climbing. **Inspection (per the
    overfit red-flag protocol) shows the convexity gain is ROBUST, not overfit:** it improves the
    *weakest* subwindow (train_1 PSR 0.653→0.699 across p=1→3) and train_6 while strong windows stay
    flat, so the t-gain broadly tightens the weak end; PnL stays spread across 5–6 altcoins (top
    share 0.33, all 6 subwindows positive). A genuine cross-sectional feature (biggest dislocations
    bounce biggest, broadly). Adopted p=3; continuing to bracket.

- **L14 (attempt-0013): convexity bracket (power 3 → 4).**
  - *Mechanism:* convexity still climbing at p=3 with robust broad subwindow gains and safe breadth.
    Test power=4 to locate the peak/break: does it keep broadly improving, or does breadth rise /
    the weak-window gain reverse (over-concentration)?
  - *Observable:* score, t, PF, `max_symbol_concentration`, train_1 subwindow PSR.
  - *Falsifier:* score/t flat-or-down, or breadth rises materially, or train_1 PSR reverses →
    p≈3 is the robust peak; commit and stop the exponent sweep.
  - *Failure mode targeted:* symbol concentration / diminishing conviction returns.
  - *Result (attempt-0013): KEEP — NEW BEST SURVIVOR, all gates pass, score 0.335.* power=4:
    PF **1.864**, return **62.0%**, t **2.175**, deflated **+0.051**, breadth 0.320 (safe),
    worst-subwindow 0.717. But the climb DECELERATED (score deltas +0.020/+0.015/+0.009;
    PF +0.050/+0.040/+0.027) — diminishing returns to the peak. **STOP convexity escalation at
    p=4** per the overfit discipline: pushing to p=5,6 for the last ~+0.005 is Train-number-chasing.
    Conviction thread exhausted at its peak. Survivor of record = attempt-0013.

**Survivor (updated): attempt-0013** — long-only crowding-reversal, cadence 240, `min_same_sign=1`,
`min_abs_funding=1`, `min_idio=2.5` (raw, mean ref), recent-guard off, hold 720, `top_n=5`,
`entry_twap=20`, `exit_twap=30`, `weighting=dislocation`, **`dislocation_weight_power=4`**.
Score **0.335 (+71% vs baseline 0.196)**, t 2.175, PF 1.864, deployed vol 15.0% (full budget),
all gates pass. Robustness note: the well-motivated convexity is ~quadratic-cubic; p=4's marginal
gain over p=3 (+0.009) is small — a point for OOS validation, not a robustness claim.

- **L15 (attempt-0014): combined-conviction weighting (funding + dislocation).**
  - *Mechanism:* the conviction win weights by dislocation. Does weighting by the full selection
    score (funding magnitude + dislocation) help more (general conviction) or less (funding
    magnitude is non-predictive noise, A5)? Probes whether the win is dislocation-specific.
  - *Observable:* PF, t/deflated, score vs the 0.335 dislocation survivor.
  - *Falsifier:* combined ≤ dislocation → the conviction is dislocation-specific (funding magnitude
    dilutes), confirming A5 and the dislocation-conviction finding. (Expected.)
  - *Failure mode targeted:* whether conviction generalizes beyond the dislocation signal.
  - *Result (attempt-0014): KEEP by score (0.341) but REJECTED as an overfit micro-gain.* combined:
    +0.006 over pure dislocation, t 2.201, but breadth crept 0.320→**0.364** and the gain comes from
    adding **funding magnitude** to the conviction weight — which A5 established is **non-predictive**.
    No mechanism explains the gain (Quant Research Standard: "if the evidence cannot explain the
    result, do not edit"), so it is Train-flattering, not edge. Rejected; reverted to pure
    dislocation. This is the overfit zone (micro-gains from mechanism-less knobs) — the honest
    signal that the productive conviction search is done.

- **L16 (attempt-0015): recent-capitulation conviction weighting.**
  - *Mechanism:* a distinct, *predictive* conviction signal (vs the rejected non-predictive funding
    magnitude): weight by the magnitude of each name's recent same-direction move (a fresh, ongoing
    capitulation). A6 established bigger recent capitulations bounce best, so concentrating on the
    deepest recent fallers should lift per-trade Sharpe — an independent conviction axis from the
    cross-sectional dislocation. Tested alone (convex power=3) vs the dislocation survivor.
  - *Falsifier:* PF/t below the dislocation survivor (0.326) → recent-return is a worse or redundant
    conviction axis; dislocation-conviction stands.
  - *Result (attempt-0015): FALSIFIED — DISCARD, score 0.278.* PF 1.837→**1.715**, significance
    fails, −13 trades (zeroing recent-risers de-selected qualifying names). Recent-return magnitude
    is a worse conviction axis than cross-sectional dislocation. **Confirms conviction is
    dislocation-specific** (the edge is relative-value, B8). Conviction axis SETTLED = convex
    cross-sectional dislocation. Reverted.

## Stop — enumeration genuinely closed (attempt 15; feasible survivor; universe/envelope-bound)

This is now a genuine stop, not premature closure: (1) the productive climb has plateaued — the last
robust improvement was the dislocation convexity (attempt-0012/0013); the two attempts since
(0014 combined = mechanism-less overfit micro-gain, 0015 capitulation = worse) produced no robust
gain; (2) every mechanism-dimension has a result; (3) the remaining un-run ideas are **variants of
already-closed mechanism-classes**, not new mechanisms — a dynamic signal-reversion exit is a
combination of continuous-rotation (A4, falsified: bled the reversal) and varied-exit-time (L7/L9,
falsified: return-series heterogeneity lowers t); a multi-horizon dislocation is a confirmation
filter (the filter class is closed — A5/A6/A11/A15/A16 all cut good trades or inert). No new distinct
hypothesis with a real, non-variant mechanism can be articulated. Dimension status:

- **Signal construction** — CLOSED. Edge is *raw absolute-bps* cross-sectional dislocation; both
  vol-normalization (L1, catastrophic) and beta-adjustment (L11, mild) fail; median reference inert
  (L8). It is vol-*seeking*, not vol-agnostic.
- **Funding** — CLOSED. Sign-only detector; level/count/magnitude/recency/weight-magnitude all
  non-predictive (A5/A10/L6/L15).
- **Exit** — CLOSED (6 converging results). Fixed-horizon 720 is optimal; every timing/scaling
  variant (A7 short, A8 long, A18 take-profit, L7 vol-scaled, L9 disloc-scaled) hurts — shorter cuts
  the slow bounce, any *varied* exit adds return-series heterogeneity → lower n_eff → lower t. A
  dynamic signal-reversion exit is a variant of this closed class (same heterogeneity cost) and is
  not run.
- **Capacity** — SOLVED. Decoupling the synchronized fixed-horizon exit ramp (L4/L5) deploys the
  full 15% risk budget (was liquidity-throttled to 10%); a robust, monotonic mechanism.
- **Sizing / conviction** — SOLVED and bracketed. Convex dislocation-weighting (super-linear
  conviction) is the second win, inspected-robust to ~p3 (broad subwindow gains, spread PnL); p4/
  combined are the overfit tail. Inverse-vol (B2) inert; leans the wrong way.
- **Selection / cadence / hold / sides** — mapped (top_n inert at 1–3 concurrent; cadence 240
  funding-aligned; hold 720; long-only, shorts no gross edge).

**Frozen Train survivor (recommended, robust): attempt-0012** — long-only crowding-reversal, cadence
240, `min_same_sign=1`, `min_abs_funding=1`, `min_idio=2.5` (raw, mean ref), recent-guard off, hold
720, `top_n=5`, `entry_twap=20`, `exit_twap=30`, `weighting=dislocation`, `dislocation_weight_power=3`.
Score **0.326 (+66% vs the 0.196 warm-start baseline)**, full-Train return 61.0%, deployed vol 15.0%
(full risk budget), t **2.146**, PF 1.837, breadth 0.319, all 8 gates pass, causality admissible,
6/6 subwindows positive. This is a candidate for Season's downstream OOS/paper/small-live review,
**not** a deployability claim. The protocol ledger's numeric-max is attempt-0014 (0.341, combined/p4);
its final ~+0.015 is a mechanism-less overfit tail (non-predictive funding magnitude, decelerating
convexity, rising concentration) — I recommend the robust config above and flag the tail for OOS
scrutiny.

**Two robust wins the prior lifecycle missed** (it only reached ~0.196-equivalent and concluded
"reseed"): (1) exit-ramp decoupling → full-budget deployment; (2) convex dislocation-conviction
sizing → higher per-trade Sharpe. Together +66%. The significance pass is now less marginal (t 2.15
vs the 2.0 knife-edge) but still on the 8-name plateau: t is scale-invariant and universe-bound, so
neither win *robustly* lifts it far above 2.

### Reseed Case (for Season; not executed) — larger return-blind universe

The binding constraint is the **universe/envelope, not the edge**. The edge is real, causal,
cost/impact-robust, broadly cross-sectional, and now well-deployed and conviction-shaped — yet the
full-Train t sits at ~2.0–2.15 because 8 majors supply only 1–3 concurrent crowded-short setups,
capping statistical independence (duty cycle ~33%). Every within-8-name t lever is falsified.
Recommendation: reseed the same long-only funding-crowding-reversal mechanism — carrying the two new
wins (exit-decoupling, convex conviction) — on the full data-ready crypto-perp universe (~25 names),
chosen return-blind on eligibility (liquidity, readiness), never by dropping losers. Expected to
raise t mainly via **duty cycle** (more names firing → more at-risk calendar → higher n_eff) and to
lower per-name ADV participation (more deployable capacity); the diversification/Sharpe gain is
limited (crypto-perp crowding is one ρ≈0.6–0.8 factor). This changes neither the protocol nor this
run; a reseed is a new lifecycle and Season's call.

## Prior Lifecycle — 8-name, retired money_floor gate (archived; edge-lessons durable, gate/exhaustion conclusions superseded)

Re-baselined on the corrected harness (attempt-0001). Same 8-major universe and mechanism as
the active lifecycle above; this log scored under the retired `money_floor` gate. The harness
changed:

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
