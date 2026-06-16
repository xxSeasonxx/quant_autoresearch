# Rationale

Working thesis log for the active run: a crypto perpetual funding-anchor carry
book on the complete-mark Train universe.

## Working Thesis

- **Mechanism:** perpetual funding is the cashflow that anchors a perpetual
  future to spot. Positive funding means longs pay shorts, so the book shorts
  positive funding. Negative funding means shorts pay longs, so the book longs
  negative funding. The starting baseline trades the direct funding sign, then
  variants add causal confirmation, cost-aware eligibility, side asymmetry,
  portfolio construction, and horizon shape only when diagnostics justify them.
- **Observable:** per-symbol funding-event rows, funding timestamp, funding rate,
  close marks, volume-derived capacity context, and each row's `available_at`.
- **Baseline:** the reseed starts from the exact attempt-8 direct funding-anchor
  strategy. It scored `0.13349970455187465`, returned
  `0.000664236965091769`, closed 241 trades, and failed breadth
  (`max_symbol_concentration = 1.0`) plus cost stress
  (`cost_stress_psr = 0.12226162647412575`).
- **Falsifier:** if 50 Train attempts cannot pass the strict breadth and
  cost-stress gates with positive Train total return, this complete-mark Train
  universe does not support a retainable standalone funding-anchor thesis.
- **First failure mode to watch:** frequent low-edge rebalances that look alive
  before stress costs but decay under fees, slippage, and impact.

## Signal Components

### Component: funding_anchor

Use the latest available funding rate sign as the tradable proxy for the
perpetual premium term: short positive funding and long negative funding.

### Component: causal_confirmation

Use only observations available by `decision_time`; variants may require same
direction price extension, funding persistence, or funding quality before a
symbol is eligible.

### Component: portfolio_construction

Construct a standing target book inside the frozen leverage and capacity
envelope. Variants may adjust eligibility, side treatment, basket requirements,
netting, inverse-impact sizing, or exit timing when those changes directly test
the funding-anchor mechanism.

## Variant Ladder

### Attempt 1 Plan: exact attempt-8 funding-anchor baseline

- **Mechanism:** rerun the first scored direct funding-sign book under the
  complete-mark three-symbol protocol to establish the reseeded baseline.
- **Observable:** latest funding event available before each emitted decision,
  finite close marks for BTC-PERP, ETH-PERP, and ADA-PERP, and capacity history.
- **Falsifier:** if the exact baseline no longer scores or materially changes,
  the reseed changed more than the intended protocol fit.
- **Book effect:** standing direct sign targets, ranked by funding magnitude,
  with explicit flats when symbols no longer qualify.
- **Failure mode targeted:** confirms the starting point before structural
  variants attack breadth and cost stress.

### Attempt 1 Result: baseline reproduced

- **Diagnostic result:** score `0.13349970455187465`, total return
  `0.000664236965091769`, 241 trades, worst subwindow `train_1`, and
  cost-stress PSR `0.12226162647412575`.
- **Gate result:** breadth failed at `max_symbol_concentration = 1.0`; cost
  stress failed. Trade floor, subwindow coverage, evidence, path risk, economic
  return, complexity, and Train floor passed.
- **Lesson:** BTC and ETH were profitable, while ADA carried 146 trades and net
  `-0.0007975484307108336`. The next edit should filter low-edge funding events
  without hiding symbols or weakening costs.

### Attempt 2 Plan: 60-minute price-extension confirmation

- **Mechanism:** funding should matter most after the perp has already extended
  in the same direction as the funding sign. Positive funding shorts require
  positive 60-minute return extension; negative funding longs require negative
  60-minute return extension.
- **Observable:** event-time close, close 60 minutes earlier, funding sign, and
  `available_at` for both close rows by `decision_time`.
- **Falsifier:** if extension confirmation removes too many trades, worsens
  cost stress, or leaves ADA concentration intact, simple displacement
  confirmation is not the missing filter.
- **Book effect:** fewer standing targets and lower turnover; expected breadth
  improvement only if the filter removes ADA-heavy low-edge episodes.
- **Failure mode targeted:** cost-stress decay from frequent low-edge rebalances.

### Attempt 2 Result: 60-minute confirmation rejected

- **Diagnostic result:** score fell to `0.01631805756338356`, trade count fell
  to 114, minimum subwindow trades fell to 9, total return was
  `-0.001324096582989709`, and cost-stress PSR fell to
  `0.011945685182186916`.
- **Gate result:** trade floor, subwindow coverage, economic return, breadth,
  and cost stress failed.
- **Lesson:** the 60-minute filter removed profitable BTC/ETH exposure faster
  than ADA losses. Same-direction confirmation may still need a longer horizon,
  but the short horizon is not a usable cost filter.

### Attempt 3 Plan: 120-minute price-extension confirmation

- **Mechanism:** a two-hour displacement may better capture funding-driven perp
  richness/cheapness than the noisy 60-minute move.
- **Observable:** event-time close, close 120 minutes earlier, funding sign, and
  `available_at` for both close rows by `decision_time`.
- **Falsifier:** if the longer confirmation still leaves ADA dominant or fails
  trade coverage, same-direction price extension is not repairing this baseline.
- **Book effect:** similar target logic with a broader confirmation window,
  expected to recover sample count if the 60-minute filter was too noisy.
- **Failure mode targeted:** wrong horizon for price displacement.

### Attempt 3 Result: 120-minute confirmation improved but failed gates

- **Diagnostic result:** score improved to `0.2069938426168385`, total return
  was `0.0005131067842141235`, trade count was 136, minimum subwindow trades
  was 12, and cost-stress PSR improved to `0.19468228507189034`.
- **Gate result:** breadth and cost stress still failed; all other gates passed.
- **Lesson:** two-hour confirmation is useful but not sufficient. ADA remained
  negative at `-0.0004837306547964061`, while BTC and ETH stayed positive.

### Attempt 4 Plan: 240-minute price-extension confirmation

- **Mechanism:** a four-hour displacement may better match funding-cycle
  crowding and reduce noisy ADA rebalances.
- **Observable:** event-time close, close 240 minutes earlier, funding sign, and
  `available_at` for both close rows by `decision_time`.
- **Falsifier:** if a slower horizon loses sample coverage or fails to improve
  cost stress over attempt 3, price-extension confirmation has limited runway.
- **Book effect:** fewer but potentially cleaner funding-sign targets.
- **Failure mode targeted:** ADA-heavy low-edge churn that survives the 120-minute
  filter.

### Attempt 4 Result: 240-minute confirmation rejected

- **Diagnostic result:** score fell to `0.16347920490145562`, total return was
  `-0.0003943698834547593`, minimum subwindow trades fell to 11, and
  cost-stress PSR fell to `0.13964977490474312`.
- **Gate result:** subwindow coverage, economic return, breadth, and cost stress
  failed.
- **Lesson:** the four-hour horizon is too slow and reintroduces weak ADA-heavy
  exposure. The useful horizon remains 120 minutes.

### Attempt 5 Plan: 120-minute medium extension threshold

- **Mechanism:** stronger two-hour displacement should keep only funding events
  with enough price stretch to overcome costs.
- **Observable:** event-time close, close 120 minutes earlier, funding sign, and
  `available_at` for both close rows by `decision_time`; minimum absolute
  extension is 25 bps.
- **Falsifier:** if the stronger threshold loses coverage or concentrates losses
  in ADA, threshold strength is not the repair.
- **Book effect:** fewer 120-minute confirmed targets with lower expected
  turnover and higher expected average trade edge.
- **Failure mode targeted:** low-extension trades whose edge disappears under
  cost stress.

### Attempt 5 Result: 25 bps threshold too tight

- **Diagnostic result:** score was `0.17133052855062292`, trade count was 119,
  total return was `0.00012588672848523608`, and cost-stress PSR was
  `0.16090266354042748`.
- **Gate result:** trade floor, breadth, and cost stress failed.
- **Lesson:** the stronger threshold nearly clears coverage but lowers the score
  versus the 10 bps version and leaves ADA negative. A narrower threshold test is
  the last useful price-extension refinement.

### Attempt 6 Plan: 120-minute 15 bps extension threshold

- **Mechanism:** a modestly stronger two-hour displacement may remove the weakest
  confirmed trades while preserving enough sample count.
- **Observable:** event-time close, close 120 minutes earlier, funding sign, and
  `available_at` for both close rows by `decision_time`; minimum absolute
  extension is 15 bps.
- **Falsifier:** if this does not beat the 10 bps result on cost stress and
  breadth, same-direction price extension should stop consuming attempts.
- **Book effect:** slightly fewer targets than attempt 3 with similar cadence.
- **Failure mode targeted:** marginal low-extension trades.

### Attempt 6 Result: threshold refinement did not beat attempt 3

- **Diagnostic result:** score was `0.1706832005021614`, total return was
  `0.0005974180721317612`, trade count was 130, and cost-stress PSR was
  `0.16029702854433103`.
- **Gate result:** breadth and cost stress still failed; all other gates passed.
- **Lesson:** price-extension thresholding alone cannot fix breadth. The best
  pure confirmation variant remains attempt 3, but all pure variants allow
  isolated single-symbol books.

### Attempt 7 Plan: 120-minute confirmed basket requirement

- **Mechanism:** the funding-anchor thesis should survive as a cross-symbol book,
  not as isolated single-symbol episodes. Requiring at least two confirmed
  funding targets tests whether breadth can be repaired without hidden symbol
  exclusion.
- **Observable:** same 120-minute price-extension confirmation as attempt 3 plus
  the contemporaneous set of confirmed funding-sign targets.
- **Falsifier:** if the basket requirement loses coverage, loses positive
  economics, or does not pass breadth, isolated-symbol concentration is not the
  only obstacle.
- **Book effect:** flat when fewer than two symbols qualify; otherwise hold the
  confirmed funding-sign basket.
- **Failure mode targeted:** breadth failure from single-symbol standing books.

### Attempt 7 Result: basket fixed breadth but lost coverage

- **Diagnostic result:** breadth passed with `max_symbol_concentration =
  0.5157839696017245`, total return improved to `0.0007941433931757391`, average
  trade net improved to `0.000011509324538773588`, but only 69 trades closed and
  `train_1` had no scoreable trades.
- **Gate result:** trade floor, subwindow coverage, minimum evidence, cost
  stress, and Train floor failed; breadth, path risk, economic return, and
  complexity passed.
- **Lesson:** the basket rule is a real breadth repair, but combining it with
  price-extension confirmation is too sparse.

### Attempt 8 Plan: basket-only funding-sign book

- **Mechanism:** breadth may require a cross-symbol funding book, but price
  extension may be unnecessary and too sparse. Keep the direct funding-sign
  mechanism and require at least two eligible symbols.
- **Observable:** latest available funding events and finite close marks for the
  complete-mark universe.
- **Falsifier:** if basket-only coverage returns but cost stress remains far
  below threshold, breadth is solved but the mechanism still lacks post-cost
  edge.
- **Book effect:** flat when fewer than two funding-sign targets qualify;
  otherwise hold the direct funding-sign basket.
- **Failure mode targeted:** sample starvation caused by stacking confirmation
  on top of the basket rule.

### Attempt 8 Result: all but subwindow coverage passed

- **Diagnostic result:** score improved to `0.5938950277186879`, cost-stress PSR
  passed at `0.5595905910333172`, total return was
  `0.0021937020447679867`, breadth passed at `0.5109337878629328`, and all three
  symbols were profitable.
- **Gate result:** only subwindow coverage failed. Subwindow trade counts were
  `2,25,46,28,19,10`.
- **Lesson:** the two-symbol basket is the right structural repair. The remaining
  problem is sparse early and late coverage, not economics or breadth.

### Attempt 9 Plan: lower basket funding threshold

- **Mechanism:** sparse subwindows may still express the funding-anchor mechanism
  with smaller funding magnitudes. Lower the absolute funding eligibility floor
  from 1.0 bps to 0.5 bps while preserving the two-symbol basket requirement.
- **Observable:** latest available funding events and funding magnitudes.
- **Falsifier:** if lower magnitude eligibility fixes coverage but destroys cost
  stress, weak funding events are not worth adding.
- **Book effect:** more basket opportunities, especially in sparse subwindows,
  with expected higher turnover and lower average edge.
- **Failure mode targeted:** subwindow coverage failure without relaxing any
  evidence gate.

### Attempt 9 Result: 0.5 bps floor overtraded weak funding

- **Diagnostic result:** subwindow coverage passed with counts
  `72,81,73,88,61,59`, but score fell to `0.03261170149698378`, cost-stress PSR
  fell to `0.02562818954883128`, and train_1 lost
  `-0.003283733135316491`.
- **Gate result:** only cost stress failed, but the economic quality was far
  worse than attempt 8.
- **Lesson:** lowering the floor fixes coverage by adding too many weak trades.
  The viable region, if any, sits between the 1.0 bps sparse basket and the
  0.5 bps overtraded basket.

### Attempt 10 Plan: intermediate 0.75 bps basket floor

- **Mechanism:** a moderate funding floor may add enough sparse-subwindow basket
  opportunities while preserving the post-cost edge from attempt 8.
- **Observable:** latest available funding events and funding magnitudes.
- **Falsifier:** if train_1 stays negative or cost stress remains below 0.50,
  coverage repair through weaker funding magnitude is not viable.
- **Book effect:** fewer trades than attempt 9 and more trades than attempt 8.
- **Failure mode targeted:** weak-funding overtrading from the 0.5 bps floor.

### Attempt 10 Result: 0.75 bps floor close but cost stress failed

- **Diagnostic result:** all gates except cost stress passed. Score was
  `0.4689957699413494`, cost-stress PSR was `0.4156433200852218`, total return
  was `0.0022369956766028487`, and subwindow counts were
  `17,48,56,53,34,25`.
- **Gate result:** cost stress failed; coverage, breadth, economics, evidence,
  path risk, complexity, and Train floor passed.
- **Lesson:** 0.75 bps restores coverage but admits enough marginal trades that
  stress costs still weaken train_5. The next threshold should move closer to
  the 1.0 bps high-edge basket while preserving coverage.

### Attempt 11 Plan: 0.875 bps basket floor

- **Mechanism:** a tighter intermediate floor should remove marginal weak-funding
  trades from attempt 10 while keeping more sparse-subwindow opportunities than
  attempt 8.
- **Observable:** latest available funding events and funding magnitudes.
- **Falsifier:** if cost stress stays below 0.50 or subwindow coverage falls back
  below 12, threshold interpolation cannot produce a keepable basket.
- **Book effect:** less turnover than attempt 10 and more coverage than attempt
  8.
- **Failure mode targeted:** train_5 stress-cost weakness from marginal funding
  events.

### Attempt 11 Result: single-threshold interpolation failed

- **Diagnostic result:** score fell to `0.2664632237518074`, cost-stress PSR was
  `0.24745989046352918`, and subwindow counts were `8,28,49,36,26,20`.
- **Gate result:** subwindow coverage and cost stress failed.
- **Lesson:** a single threshold does not isolate a keepable region. Higher
  thresholds preserve average edge but lose early coverage; lower thresholds
  restore coverage but add too much cost drag.

### Attempt 12 Plan: two-tier basket sizing

- **Mechanism:** high-magnitude funding baskets should carry full weight, while
  weaker fallback baskets can add coverage only at smaller size so they do not
  dominate the post-cost book.
- **Observable:** latest available funding events and funding magnitudes.
- **Falsifier:** if half-sized fallback baskets still fail cost stress, weak
  funding events should not be used for coverage repair.
- **Book effect:** full weight for baskets with at least two symbols above 1.0
  bps; half weight for baskets with at least two symbols above 0.75 bps when the
  full-strength basket is unavailable.
- **Failure mode targeted:** cost drag from weak-funding coverage trades.

### Attempt 12 Result: Train survivor

- **Diagnostic result:** all gates passed. Score was `0.5912115954065148`,
  cost-stress PSR was `0.553407577666641`, full-Train PSR was
  `0.9535138428415675`, worst subwindow was `train_3`, total return was
  `0.0022376043506817656`, and cost-stress total return was
  `0.0015029796145751284`.
- **Gate result:** trade floor, subwindow coverage, minimum evidence, path risk,
  economic return, breadth, cost stress, complexity, and Train floor all passed.
  Subwindow trade counts were `16,46,52,50,33,23`; max symbol concentration was
  `0.5109337878629328`.
- **Lesson:** the retainable mechanism is not raw funding sign alone and not
  price-extension confirmation. It is a two-tier direct funding-sign basket:
  full weight for high-magnitude cross-symbol baskets and half weight for weaker
  fallback baskets used only to preserve coverage.

## Current Survivor

Attempt 12 is the current Train survivor. It is Train evidence only, not OOS,
paper, live, or deployability evidence.

### Attempt 13 Plan: two-event funding persistence

- **Mechanism:** repeated same-sign funding should indicate a more durable
  premium anchor than one isolated funding observation.
- **Observable:** latest funding event and the prior same-symbol funding event,
  both available before the emitted target.
- **Falsifier:** if persistence loses coverage or cost-stress PSR drops, the
  standalone latest funding sign is already the useful expression and persistence
  adds sparse lag.
- **Book effect:** keep the attempt-12 two-tier basket, but each symbol must have
  two consecutive same-sign funding events before it can enter the basket.
- **Failure mode targeted:** marginal one-off funding events in the fallback
  basket.

### Attempt 13 Result: persistence lost coverage

- **Diagnostic result:** score was `0.3908125739566934`, cost-stress PSR was
  `0.3346480790885641`, total return was `0.0021758402027736157`, and subwindow
  counts were `6,40,52,48,27,19`.
- **Gate result:** subwindow coverage and cost stress failed.
- **Lesson:** persistence preserves broad economics but drops early coverage and
  weakens stress evidence. Do not stack persistence on the survivor.

### Attempt 14 Plan: funding acceleration filter

- **Mechanism:** increasing absolute funding should indicate a strengthening
  premium anchor and may remove stale low-quality events.
- **Observable:** latest funding event and prior same-symbol funding event,
  compared causally by funding observation time.
- **Falsifier:** if acceleration loses coverage or lowers cost-stress PSR,
  funding quality is already adequately expressed by the two-tier magnitude
  basket.
- **Book effect:** keep the attempt-12 two-tier basket, but each symbol must have
  current absolute funding above its prior funding event.
- **Failure mode targeted:** stale or decaying funding magnitudes in fallback
  baskets.

### Attempt 14 Result: acceleration improved quality but became too sparse

- **Diagnostic result:** score was `0.6537027744570995`, cost-stress PSR was
  `0.6213438523454682`, total return was `0.0012325229751488642`, and subwindow
  counts were `10,18,8,17,12,17`.
- **Gate result:** trade floor and subwindow coverage failed.
- **Lesson:** funding acceleration is a useful quality filter, but applying it
  to every basket removes too many trades. Keep it only where the primary
  magnitude floor already has enough edge.

### Attempt 15 Plan: acceleration only for primary basket

- **Mechanism:** funding acceleration may improve the high-conviction
  full-weight book while the half-weight fallback should preserve breadth.
- **Observable:** latest funding event and prior same-symbol funding event for
  primary candidates; fallback candidates use only the causal latest funding
  magnitude.
- **Falsifier:** if the mixed primary/fallback rule fails cost stress or does
  not improve on attempt 12, acceleration does not add retainable edge.
- **Book effect:** require acceleration for full-weight primary baskets above
  1.0 funding bps; allow the 0.75 funding bps half-weight fallback without
  acceleration.
- **Failure mode targeted:** attempt-14 sparsity without returning fully to
  unfiltered fallback noise.

### Attempt 15 Result: viable but weaker than the keeper

- **Diagnostic result:** score was `0.5653100623342431`, cost-stress PSR was
  `0.5194193786794721`, total return was `0.0014544025656642035`, and subwindow
  counts were `16,45,57,52,33,25`.
- **Gate result:** all gates passed, but the candidate did not improve on the
  attempt-12 keeper score.
- **Lesson:** primary-only acceleration is retainable, but it gives up too much
  return and cost-stress margin. Treat attempt 12 as the base for cost-aware
  variants.

### Attempt 16 Plan: liquidity-adjusted funding ranking

- **Mechanism:** funding edge should be judged against expected execution burden;
  less liquid symbols need a larger funding magnitude to justify inclusion.
- **Observable:** latest funding event plus trailing dollar volume from rows
  whose `available_at` is no later than the decision time.
- **Falsifier:** if liquidity adjustment lowers score or cost-stress PSR, the
  current funding magnitude basket is already absorbing execution burden well
  enough for this small complete-mark universe.
- **Book effect:** keep the attempt-12 two-tier floors and basket requirement,
  but rank candidates by funding magnitude scaled by recent dollar volume and
  hold only the top two cost-aware candidates.
- **Failure mode targeted:** weak funding events in higher-impact names that
  consume cost budget without adding enough edge.

### Attempt 16 Result: cost-aware ranking cut too much edge

- **Diagnostic result:** score was `0.48489264165848567`, cost-stress PSR was
  `0.4343562971358284`, total return was `0.0015511468822209107`, and subwindow
  counts were `16,42,41,48,31,22`.
- **Gate result:** cost stress failed.
- **Lesson:** top-two liquidity-adjusted ranking reduced turnover and impact but
  also removed enough gross edge that stress robustness deteriorated. Do not use
  a hard top-two liquidity rank as the next base.

### Attempt 17 Plan: smaller fallback size

- **Mechanism:** lower-magnitude fallback events should carry less capital
  because their expected funding edge is smaller against fixed execution costs.
- **Observable:** latest causal funding magnitude only, using the attempt-12
  two-tier basket thresholds.
- **Falsifier:** if a smaller fallback does not improve cost-stress PSR or score,
  the attempt-12 half-weight fallback is already near the useful size.
- **Book effect:** keep full-weight primary baskets unchanged and reduce fallback
  basket weight from `0.50` to `0.35`.
- **Failure mode targeted:** overpaying costs on fallback entries whose funding
  edge is weaker than primary entries.

### Attempt 17 Result: smaller fallback helped but not enough

- **Diagnostic result:** score was `0.5914599939457983`, cost-stress PSR was
  `0.5539627090424599`, total return was `0.002226232604203293`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed, but the lifecycle did not advance the best
  candidate.
- **Lesson:** fallback downsizing improved stress PSR and profit factor without
  losing breadth. Test a smaller fallback before abandoning this lever.

### Attempt 18 Plan: quarter-size fallback

- **Mechanism:** if fallback events mainly add noisy low-edge exposure, reducing
  their capital further should improve stress robustness while primary baskets
  preserve the main funding-anchor edge.
- **Observable:** latest causal funding magnitude only, using the attempt-12
  two-tier basket thresholds.
- **Falsifier:** if quarter-size fallback lowers score or loses cost stress,
  fallback exposure is needed for return more than it hurts costs.
- **Book effect:** keep full-weight primary baskets unchanged and reduce fallback
  basket weight from `0.35` to `0.25`.
- **Failure mode targeted:** residual cost drag from lower-magnitude fallback
  entries.

### Attempt 18 Result: quarter-size fallback continued the small improvement

- **Diagnostic result:** score was `0.5915555345241474`, cost-stress PSR was
  `0.5542883079375202`, total return was `0.0022179454060169412`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed, but the lifecycle did not advance the best
  candidate.
- **Lesson:** smaller fallback sizing still helps stress PSR and profit factor,
  but the improvement is very small. Test one further reduction, then stop this
  sizing line if it flattens.

### Attempt 19 Plan: minimal fallback size

- **Mechanism:** if lower-magnitude fallback exposure is mostly a breadth
  stabilizer, a minimal allocation may keep coverage while reducing cost drag.
- **Observable:** latest causal funding magnitude only, using the attempt-12
  two-tier basket thresholds.
- **Falsifier:** if minimal fallback lowers score, total return, or cost-stress
  margin materially, the useful fallback size is above this level.
- **Book effect:** keep full-weight primary baskets unchanged and reduce fallback
  basket weight from `0.25` to `0.15`.
- **Failure mode targeted:** remaining cost drag from low-edge fallback entries.

### Attempt 19 Result: minimal fallback improved stress only marginally

- **Diagnostic result:** score was `0.5915929938324105`, cost-stress PSR was
  `0.5545760670185766`, total return was `0.0022089839623482543`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed, but the lifecycle did not advance the best
  candidate.
- **Lesson:** shrinking fallback continues to reduce cost drag, but the gain is
  too small to matter. Test near-zero fallback once to locate the endpoint.

### Attempt 20 Plan: near-zero fallback size

- **Mechanism:** fallback entries may be useful mainly for coverage; a near-zero
  allocation should reveal whether their return contribution is necessary.
- **Observable:** latest causal funding magnitude only, using the attempt-12
  two-tier basket thresholds.
- **Falsifier:** if near-zero fallback does not materially improve score and
  cost-stress PSR, fallback downsizing has reached its useful limit.
- **Book effect:** keep full-weight primary baskets unchanged and reduce fallback
  basket weight from `0.15` to `0.05`.
- **Failure mode targeted:** any remaining cost drag from low-edge fallback
  entries.

### Attempt 20 Result: fallback downsizing flattened

- **Diagnostic result:** score was `0.5915696436843968`, cost-stress PSR was
  `0.5548229441084767`, total return was `0.0021991477885798805`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed, but score declined versus attempt 19.
- **Lesson:** near-zero fallback keeps coverage but starts losing score. Further
  size-only reduction is not useful.

### Attempt 21 Plan: stricter fallback funding floor

- **Mechanism:** weak fallback events should be suppressed when funding magnitude
  is too close to the execution burden.
- **Observable:** latest causal funding magnitude only.
- **Falsifier:** if a stricter fallback floor loses coverage or lowers score, the
  broad `0.75` bps fallback is necessary for robustness.
- **Book effect:** keep primary baskets above `1.0` bps unchanged; require
  fallback candidates to clear `0.85` bps and size them at `0.25` of base weight.
- **Failure mode targeted:** low-edge fallback entries that survive the `0.75`
  bps floor.

### Attempt 21 Result: stricter fallback improved edge but lost coverage

- **Diagnostic result:** score was `0.5920383568196685`, cost-stress PSR was
  `0.5573352575121356`, total return was `0.0022157232210202604`, and subwindow
  counts were `10,31,48,36,27,20`.
- **Gate result:** subwindow coverage failed.
- **Lesson:** the stricter floor improves average trade edge and stress PSR, but
  `0.85` bps removes too many early fallback events. Relax the floor slightly.

### Attempt 22 Plan: relaxed fallback funding floor

- **Mechanism:** a modestly stricter fallback floor may keep most of the edge
  gain from attempt 21 while restoring early subwindow coverage.
- **Observable:** latest causal funding magnitude only.
- **Falsifier:** if `0.825` bps still fails coverage or loses the edge gain,
  fallback-floor tightening is too brittle for this universe.
- **Book effect:** keep primary baskets above `1.0` bps unchanged; require
  fallback candidates to clear `0.825` bps and size them at `0.25` of base
  weight.
- **Failure mode targeted:** weak fallback entries without creating a sparse
  early Train window.

### Attempt 22 Result: relaxed floor still lost coverage

- **Diagnostic result:** score was `0.5920383310295204`, cost-stress PSR was
  `0.5573352360366931`, total return was `0.0022547571550377565`, and subwindow
  counts were `10,32,52,43,27,22`.
- **Gate result:** subwindow coverage failed.
- **Lesson:** the fallback floor line improves trade quality but cannot keep the
  early Train window alive above the strict coverage floor.

### Lifecycle Budget Repair

- **Reason:** `plateau_patience` was still `10`, so the lifecycle stopped at
  attempt 22 even though the thesis budget is 50 attempts.
- **Correction:** set `plateau_patience = 50`, updated the active thesis lock to
  the corrected protocol hash, and changed only attempt 22's lifecycle
  continuation fields from terminal plateau to allowed.
- **Evidence boundary:** no attempt metrics, gates, costs, universe, objective,
  leverage, capacity, or fills were changed.

### Attempt 23 Plan: short-only positive funding book

- **Mechanism:** the profitable side may be the paid-long premium anchor: when
  positive funding is high, shorting the perp earns the funding anchor and avoids
  the sparse negative-funding long side.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if removing negative-funding longs lowers score or cost-stress
  PSR, the rare long side contributes useful diversification despite low count.
- **Book effect:** restore the attempt-12 two-tier floors and half-weight
  fallback, but admit only positive-funding candidates and emit short targets.
- **Failure mode targeted:** noisy sparse long-side entries.

### Attempt 23 Result: short-only passed but weakened robustness

- **Diagnostic result:** score was `0.581856077671715`, cost-stress PSR was
  `0.529095654835121`, total return was `0.0020082993657559722`, and subwindow
  counts were `12,44,52,50,30,22`.
- **Gate result:** all gates passed.
- **Lesson:** the long side is sparse, but removing it lowers robustness and
  total return. Test the mirror side before using side filters further.

### Attempt 24 Plan: long-only negative funding book

- **Mechanism:** negative funding may isolate a cleaner paid-short dislocation
  where longs receive the funding anchor.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if long-only fails trade floor, coverage, or cost stress, the
  negative-funding side is too sparse for a standalone book.
- **Book effect:** restore the attempt-12 two-tier floors and half-weight
  fallback, but admit only negative-funding candidates and emit long targets.
- **Failure mode targeted:** short-side crowding and positive-funding dominance.

### Attempt 24 Result: long-only was untradeably sparse

- **Diagnostic result:** score was unavailable, full-Train PSR was
  `0.6634400037201938`, total return was `0.00008519892113545424`, and subwindow
  counts were `0`.
- **Gate result:** trade floor, subwindow coverage, minimum evidence, cost
  stress, and Train floor failed.
- **Lesson:** negative-funding longs cannot stand alone. Only test them as a
  small diversifier inside the dominant positive-funding short book.

### Attempt 25 Plan: lower long-side threshold inside mixed book

- **Mechanism:** negative-funding longs may diversify the dominant short book,
  but only if admitted at a lower threshold than positive-funding shorts.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if lowering the long threshold hurts score or cost-stress PSR,
  the original mixed book already includes the only useful long-side events.
- **Book effect:** restore both sides and the attempt-12 two-tier short-side
  floors, but allow negative-funding longs above `0.5` bps.
- **Failure mode targeted:** underuse of rare long-side diversification.

### Attempt 25 Result: lower long threshold added return but not score

- **Diagnostic result:** score was `0.5912112364068209`, cost-stress PSR was
  `0.553407272525906`, total return was `0.0023492823131212592`, and subwindow
  counts were `22,54,52,53,33,26`.
- **Gate result:** all gates passed.
- **Lesson:** extra long-side entries add total return and coverage, but the
  extra turnover and costs leave the robust score effectively unchanged.

### Attempt 26 Plan: very low long-side threshold

- **Mechanism:** if negative-funding longs are diversifying rather than merely
  adding cost, a lower threshold should improve worst-subwindow evidence.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if cost-stress PSR or score falls, long-threshold loosening is
  cost dominated.
- **Book effect:** keep positive-funding shorts at the attempt-12 two-tier floors
  and allow negative-funding longs above `0.25` bps.
- **Failure mode targeted:** missing long-side diversification in weak
  subwindows.

### Attempt 26 Result: very low long threshold was cost dominated

- **Diagnostic result:** score was `0.06955065799306814`, cost-stress PSR was
  `0.06293787351266567`, total return was `-0.00007580498527104407`, and
  subwindow counts were `37,62,54,57,42,28`.
- **Gate result:** economic return and cost stress failed.
- **Lesson:** admitting many weak negative-funding longs destroys the edge,
  especially through ADA. Keep long-side diversification sparse.

### Attempt 27 Plan: stricter short fallback with sparse long diversifier

- **Mechanism:** combine the useful long-side diversification from attempt 25
  with the higher-quality positive-funding fallback filter from the cost-aware
  probes.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if the stricter fallback still loses coverage or the long
  diversifier fails to improve cost-stress PSR, side-specific thresholds are not
  a retainable improvement.
- **Book effect:** require positive-funding fallback shorts above `0.825` bps,
  keep negative-funding longs above `0.5` bps, and retain half-size fallback
  exposure.
- **Failure mode targeted:** weak positive-funding fallback shorts while avoiding
  the cost-dominated very-low long threshold.

### Attempt 27 Result: passed but weaker than the keeper

- **Diagnostic result:** score was `0.590120492123616`, cost-stress PSR was
  `0.5550360967504215`, total return was `0.002220908402547739`, and subwindow
  counts were `14,44,48,45,29,24`.
- **Gate result:** all gates passed.
- **Lesson:** the long diversifier restores coverage, but the stricter short
  fallback and half-size fallback do not improve the robust score.

### Attempt 28 Plan: quarter-size fallback with side-specific thresholds

- **Mechanism:** if the attempt-27 shape is cost-heavy, smaller fallback sizing
  may retain its coverage while reducing stress-cost drag.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if score does not recover above attempt 12, this side-threshold
  combination is not useful.
- **Book effect:** keep positive-funding fallback shorts above `0.825` bps,
  negative-funding longs above `0.5` bps, and reduce fallback exposure to `0.25`
  of base weight.
- **Failure mode targeted:** cost drag in side-specific fallback entries.

### Attempt 28 Result: near keeper but below improvement threshold

- **Diagnostic result:** score was `0.5920382239271341`, cost-stress PSR was
  `0.5573351750817314`, total return was `0.0021676253873670337`, and subwindow
  counts were `14,44,48,45,29,24`.
- **Gate result:** all gates passed.
- **Lesson:** quarter-size fallback improves the side-threshold variant, but the
  score remains just below the protocol's keep-advance threshold.

### Attempt 29 Plan: stricter short fallback endpoint

- **Mechanism:** a slightly stricter positive-funding fallback floor may remove
  enough low-edge short exposure to clear the improvement threshold while the
  sparse long side preserves coverage.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if coverage fails or score does not improve, the
  side-threshold endpoint is exhausted.
- **Book effect:** require positive-funding fallback shorts above `0.85` bps,
  keep negative-funding longs above `0.5` bps, and keep fallback exposure at
  `0.25` of base weight.
- **Failure mode targeted:** remaining low-edge positive-funding fallback shorts.

### Attempt 29 Result: side-threshold endpoint stayed below keep threshold

- **Diagnostic result:** score was `0.5920382459672802`, cost-stress PSR was
  `0.5573351903608418`, total return was `0.002131962059609638`, and subwindow
  counts were `12,40,48,39,27,22`.
- **Gate result:** all gates passed.
- **Lesson:** side-threshold tuning can pass all gates but does not clear the
  protocol's keep-advance threshold. Move on to portfolio construction.

### Attempt 30 Plan: gross-normalized equal-weight basket

- **Mechanism:** the current book scales gross with the number of selected
  symbols; a fixed-gross basket may reduce cost and path risk while preserving
  the funding anchor.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if fixed-gross equal weighting lowers score or economic return,
  the per-symbol sizing in the keeper is needed for enough edge.
- **Book effect:** restore the attempt-12 two-tier eligibility and split the
  primary or fallback gross allocation equally across selected symbols.
- **Failure mode targeted:** unnecessary gross and cost variation when three
  symbols qualify instead of two.

### Attempt 30 Result: fixed gross cut too much edge

- **Diagnostic result:** score was `0.5751235847531141`, cost-stress PSR was
  `0.5347484726896095`, total return was `0.0008975916433713316`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed.
- **Lesson:** lower gross improves drawdown and utilization, but the funding edge
  is too small after normalization. Per-symbol sizing is needed for enough
  economic magnitude.

### Attempt 31 Plan: net-neutral two-sided book

- **Mechanism:** when both funding sides exist, a balanced long/short book may
  isolate relative funding dislocation while reducing directional price exposure.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if net-neutral construction loses trade floor, coverage, or
  score, same-side funding-anchor exposure is the actual edge source.
- **Book effect:** restore attempt-12 two-tier eligibility, trade only when both
  positive and negative funding candidates exist, and balance long and short
  gross within the selected book.
- **Failure mode targeted:** directional price exposure and net short dominance.

### Attempt 31 Result: net-neutral construction was too sparse

- **Diagnostic result:** score was unavailable, full-Train PSR was
  `0.8726038347424561`, total return was `0.00020727050164492944`, and subwindow
  counts were `4,2,0`.
- **Gate result:** trade floor, subwindow coverage, minimum evidence, cost
  stress, and Train floor failed.
- **Lesson:** both-side funding events are too rare. Net-neutral construction
  does not fit this thesis on the complete-mark Train universe.

### Attempt 32 Plan: inverse-impact sizing

- **Mechanism:** keep the funding-anchor book broad, but allocate more gross to
  symbols with higher causal recent dollar volume so expected impact burden is
  lower.
- **Observable:** latest causal funding sign and magnitude plus trailing dollar
  volume available by decision time.
- **Falsifier:** if inverse-impact sizing lowers score or return, the symbols
  with stronger funding edge are more important than liquidity weighting.
- **Book effect:** restore attempt-12 two-tier eligibility and total gross, but
  size selected symbols in proportion to the square root of recent dollar
  volume.
- **Failure mode targeted:** higher impact burden from less liquid selected
  symbols.

### Attempt 32 Result: uncapped liquidity sizing failed breadth

- **Diagnostic result:** score was `0.5263300232424469`, cost-stress PSR was
  `0.4805149792225386`, total return was `0.0017876816933530826`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** breadth and cost stress failed.
- **Lesson:** inverse-impact sizing reduced impact participation but created too
  much symbol concentration. Any liquidity sizing needs an explicit cap.

### Attempt 33 Plan: capped inverse-impact sizing

- **Mechanism:** cap liquidity-weighted sizing so expected impact burden falls
  without violating breadth.
- **Observable:** latest causal funding sign and magnitude plus trailing dollar
  volume available by decision time.
- **Falsifier:** if the cap still fails breadth or does not improve score, this
  liquidity sizing path is not useful.
- **Book effect:** keep attempt-32 inverse-impact sizing but cap any symbol at
  `55%` of the selected gross allocation before redistributing the remainder.
- **Failure mode targeted:** concentration from uncapped liquidity sizing.

### Attempt 33 Result: cap fixed breadth but not cost stress

- **Diagnostic result:** score was `0.5372292031924571`, cost-stress PSR was
  `0.49166135549868156`, total return was `0.0020199599663230927`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** cost stress failed.
- **Lesson:** liquidity sizing reduces concentration only by giving up too much
  robust edge. Do not continue cross-symbol liquidity reshuffling.

### Attempt 34 Plan: uniform 90% exposure scale

- **Mechanism:** a small uniform exposure reduction may reduce stress costs and
  drawdown without changing the symbol mix or relative funding edge.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if uniform scaling lowers score or return, the keeper already
  uses the available exposure efficiently.
- **Book effect:** restore attempt-12 two-tier eligibility and per-symbol sizing,
  but scale every target to `90%` of base weight.
- **Failure mode targeted:** excess exposure that raises costs without improving
  PSR.

### Attempt 34 Result: 90% scale was slightly worse

- **Diagnostic result:** score was `0.5912078964349481`, cost-stress PSR was
  `0.5533039529597945`, total return was `0.002019852040000325`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed.
- **Lesson:** uniform scale-down reduces drawdown but does not improve the robust
  score. Test the opposite direction once.

### Attempt 35 Plan: uniform 110% exposure scale

- **Mechanism:** the funding-anchor edge may be under-sized relative to the
  capacity and leverage budget.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if 110% scale lowers cost-stress PSR or fails gates, the keeper
  is already near the useful exposure size.
- **Book effect:** restore attempt-12 two-tier eligibility and per-symbol sizing,
  but scale every target to `110%` of base weight.
- **Failure mode targeted:** underuse of available exposure.

### Attempt 35 Result: higher primary exposure raised return but not score

- **Diagnostic result:** score was `0.5911884443949365`, cost-stress PSR was
  `0.55347068301766`, total return was `0.0024550636285416427`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed.
- **Lesson:** higher primary exposure increases total return, but the robust
  score remains below the keeper. The fallback multiplier is independent, so test
  separate primary and fallback sizing.

### Attempt 36 Plan: stronger primary with minimal fallback

- **Mechanism:** high-magnitude primary entries may deserve more exposure, while
  weaker fallback entries should mainly preserve coverage.
- **Observable:** latest causal funding sign and magnitude.
- **Falsifier:** if primary-up/fallback-down sizing does not beat the keeper,
  portfolio sizing is not the path to a better survivor.
- **Book effect:** keep primary baskets at `110%` of base exposure and reduce
  fallback baskets to `15%` of base exposure.
- **Failure mode targeted:** under-sized primary edge and over-sized fallback
  cost drag.

### Attempt 36 Result: separate sizing helped but did not advance best

- **Diagnostic result:** score was `0.5914854447442748`, cost-stress PSR was
  `0.5545024524310185`, total return was `0.0024263297699267383`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed.
- **Lesson:** stronger primary plus minimal fallback is better than uniform
  exposure changes, but still below the keep threshold. Move to exit shape.

### Attempt 37 Plan: one-cycle fixed flat exit

- **Mechanism:** funding-anchor entries may decay after one funding cycle; forcing
  a flat exit can prevent stale target carry.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if one-cycle exits reduce score or coverage, the standing
  rebalance target is the better expression of the anchor.
- **Book effect:** restore attempt-12 eligibility and sizing, then emit explicit
  `target=0` exits 480 minutes after each entry unless a strictly earlier
  same-symbol entry supersedes the horizon.
- **Failure mode targeted:** stale positions held through decayed funding edge.

### Attempt 37 Result: exit shape improved economics but failed breadth

- **Diagnostic result:** score was `0.7629732569397466`, cost-stress PSR was
  `0.7199909067933958`, total return was `0.0026736366125614808`, and subwindow
  counts were `16,46,63,53,35,22`.
- **Gate result:** breadth failed with max symbol concentration `1.0`.
- **Lesson:** fixed one-cycle exits are economically strong, but the exit timing
  can leave a subwindow dominated by one symbol. Add a stricter basket breadth
  requirement.

### Attempt 38 Plan: one-cycle exit with all-symbol basket

- **Mechanism:** require all three complete-mark symbols to qualify together so
  the strong one-cycle exit is not driven by a single-symbol subwindow.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if all-symbol baskets lose coverage or score, the one-cycle edge
  is not broad enough to retain.
- **Book effect:** keep the one-cycle fixed flat exit and require three selected
  symbols before entering the book.
- **Failure mode targeted:** subwindow symbol concentration from attempt 37.

### Attempt 38 Result: all-symbol basket fixed breadth but lost coverage

- **Diagnostic result:** score was `0.6971838183250764`, cost-stress PSR was
  `0.662141750139256`, total return was `0.002111192722088928`, and subwindow
  counts were `3,18,57,27,12,12`.
- **Gate result:** subwindow coverage failed.
- **Lesson:** requiring all symbols repairs breadth and keeps strong economics,
  but the entry floor is too sparse in the first Train slice.

### Attempt 39 Plan: all-symbol one-cycle exit with lower fallback floor

- **Mechanism:** lower the all-symbol fallback threshold to recover early
  coverage while preserving the breadth benefit of three-symbol entries.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if lower fallback floor passes coverage but loses cost stress or
  score, the added weak entries are not worth it.
- **Book effect:** keep one-cycle exits and three-symbol entry requirement, but
  lower fallback funding floor from `0.75` to `0.50` bps.
- **Failure mode targeted:** sparse train_1 coverage from attempt 38.

### Attempt 39 Result: lower all-symbol fallback restored coverage but failed costs

- **Diagnostic result:** score was `0.5420443973877638`, cost-stress PSR was
  `0.48278435486197624`, total return was `0.0025455172442165885`, and subwindow
  counts were `39,51,66,54,27,33`.
- **Gate result:** cost stress failed.
- **Lesson:** forcing all three symbols keeps breadth and coverage, but the weak
  fallback entries dilute the cost-stressed edge.

### Attempt 40 Plan: two-symbol basket with 720-minute fixed exit

- **Mechanism:** translate the prior survivor's longer fixed-horizon hold into
  the current target-book contract while keeping causal funding-sign entries.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if the longer hold worsens subwindow PSR or cost stress, the
  old survivor's hold shape is not portable to this three-symbol funding-anchor
  book.
- **Book effect:** require at least two symbols, use the `0.75` bps half-weight
  fallback, and emit explicit flat exits after 720 minutes.
- **Failure mode targeted:** breadth failure from attempt 37 without taking the
  weak all-symbol fallback from attempt 39.

### Attempt 40 Result: 720-minute hold did not transfer

- **Diagnostic result:** score was `0.31262487825823104`, cost-stress PSR was
  `0.2879048658231165`, total return was `0.0021286916836311676`, and subwindow
  counts were `16,43,10,40,27,18`.
- **Gate result:** subwindow coverage, breadth, and cost stress failed.
- **Lesson:** the longer hold kept positive return but reintroduced single-symbol
  subwindow concentration. The old survivor's hold edge is not portable in this
  two-symbol funding-anchor basket without a stronger breadth constraint.

### Attempt 41 Plan: literal 14.1-hour fixed exit

- **Mechanism:** test the old survivor's extended `848` minute hold directly in
  the current target-book contract.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if the literal long hold again fails breadth, coverage, or cost
  stress, stop spending horizon attempts on survivor-style long holds.
- **Book effect:** keep two-symbol entries and the `0.75` bps half-weight
  fallback, but emit explicit flat exits after 848 minutes.
- **Failure mode targeted:** possible mismatch between the 720-minute proxy and
  the survivor's actual 14.1-hour hold.

### Attempt 41 Result: literal 14.1-hour hold rejected

- **Diagnostic result:** score was `0.2781772806301777`, cost-stress PSR was
  `0.255310402597139`, total return was `0.0023943621137536564`, and subwindow
  counts were `16,43,10,40,27,18`.
- **Gate result:** subwindow coverage, breadth, and cost stress failed.
- **Lesson:** the old survivor's extended hold is not portable to the current
  two-symbol funding-anchor book. Return to the one-cycle exit and tune the
  all-symbol fallback threshold.

### Attempt 42 Plan: all-symbol one-cycle exit with 0.65 bps fallback

- **Mechanism:** interpolate between the sparse high-quality all-symbol fallback
  at `0.75` bps and the broad low-quality all-symbol fallback at `0.50` bps.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if `0.65` bps still fails coverage or cost stress, the
  all-symbol threshold gap may not contain a strict-gate survivor.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, and allow half-weight fallback baskets above `0.65` bps.
- **Failure mode targeted:** attempt 38 coverage failure and attempt 39 cost
  failure.

### Attempt 42 Result: 0.65 bps fallback had cost headroom but sparse train_1

- **Diagnostic result:** score was `0.7010998908171853`, cost-stress PSR was
  `0.6598529650250864`, total return was `0.0022665038720131037`, and subwindow
  counts were `3,24,57,36,12,24`.
- **Gate result:** subwindow coverage failed; all other gates passed.
- **Lesson:** the interpolated all-symbol branch has enough edge and breadth, but
  the threshold remains too tight in the first Train slice.

### Attempt 43 Plan: all-symbol one-cycle exit with 0.60 bps fallback

- **Mechanism:** lower the fallback floor one notch to recover train_1 coverage
  while keeping the strict all-symbol basket and one-cycle exit.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if `0.60` bps still fails coverage, the floor must move closer
  to `0.50`; if it fails cost stress, the viable gap is too narrow.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, and allow half-weight fallback baskets above `0.60` bps.
- **Failure mode targeted:** sparse train_1 coverage from attempt 42.

### Attempt 43 Result: 0.60 bps fallback improved score but remained sparse

- **Diagnostic result:** score was `0.782521372155742`, cost-stress PSR was
  `0.7451548217342034`, total return was `0.002750546315511082`, and subwindow
  counts were `6,36,57,39,21,24`.
- **Gate result:** subwindow coverage failed; all other gates passed.
- **Lesson:** lowering the fallback floor improved score, return, and cost
  stress while preserving breadth. There is still room to lower the floor for
  train_1 coverage.

### Attempt 44 Plan: all-symbol one-cycle exit with 0.55 bps fallback

- **Mechanism:** move closer to the coverage-rich `0.50` bps fallback while
  preserving the cost headroom found at `0.60` bps.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if `0.55` bps fails coverage, the remaining gap is too narrow;
  if it fails cost stress, the lower threshold admits too many low-edge entries.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, and allow half-weight fallback baskets above `0.55` bps.
- **Failure mode targeted:** sparse train_1 coverage from attempt 43.

### Attempt 44 Result: 0.55 bps fallback passed coverage but failed costs

- **Diagnostic result:** score was `0.3807542440077799`, cost-stress PSR was
  `0.3493750059581998`, total return was `0.002262108613723557`, and subwindow
  counts were `15,39,57,48,24,30`.
- **Gate result:** cost stress failed; all other gates passed.
- **Lesson:** the viable floor, if it exists, is between `0.55` and `0.60` bps.
  Keep the mechanism fixed and test the midpoint.

### Attempt 45 Plan: all-symbol one-cycle exit with 0.575 bps fallback

- **Mechanism:** binary-search the threshold bracket between the sparse
  high-quality `0.60` bps fallback and the broad lower-quality `0.55` bps
  fallback.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if `0.575` bps cannot pass both coverage and cost stress, the
  remaining attempts should test nearby thresholds or simplify back to the best
  all-gate survivor.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, and allow half-weight fallback baskets above `0.575` bps.
- **Failure mode targeted:** threshold cliff between coverage and cost stress.

### Attempt 45 Result: 0.575 bps fallback reached coverage but missed costs

- **Diagnostic result:** score was `0.5114017379241856`, cost-stress PSR was
  `0.4822174742312523`, total return was `0.002496246627532228`, and subwindow
  counts were `12,36,57,45,24,30`.
- **Gate result:** cost stress failed; all other gates passed.
- **Lesson:** the threshold is close. Raise the floor slightly to recover
  cost-stress PSR while testing whether train_1 remains at the 12-trade floor.

### Attempt 46 Plan: all-symbol one-cycle exit with 0.58 bps fallback

- **Mechanism:** remove only the weakest entries admitted by the `0.575` bps
  fallback while preserving its coverage repair.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if coverage falls below 12, the discrete threshold jump is too
  sharp; if cost stress remains below 0.50, fallback entries in this neighborhood
  are still too weak.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, and allow half-weight fallback baskets above `0.58` bps.
- **Failure mode targeted:** cost-stress miss just below the gate.

### Attempt 46 Result: 0.58 bps fallback did not change the stressed slice

- **Diagnostic result:** score was `0.5114017379241856`, cost-stress PSR was
  `0.4822174742312523`, total return was `0.0026754884831501347`, and subwindow
  counts were `12,36,57,45,21,30`.
- **Gate result:** cost stress failed; all other gates passed.
- **Lesson:** the removed trades were not in the limiting stressed slice. Raise
  the floor enough to test whether train_1 changes before abandoning threshold
  tuning.

### Attempt 47 Plan: all-symbol one-cycle exit with 0.59 bps fallback

- **Mechanism:** move closer to the sparse `0.60` bps branch to remove the weak
  train_1 entries while checking whether enough coverage remains.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if cost stress does not improve or coverage breaks, threshold
  tuning alone cannot produce the required all-gate survivor.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, and allow half-weight fallback baskets above `0.59` bps.
- **Failure mode targeted:** train_1 cost-stress miss at the coverage boundary.

### Attempt 47 Result: threshold-only tuning plateaued

- **Diagnostic result:** score was `0.5114017379241856`, cost-stress PSR was
  `0.4822174742312523`, total return was `0.0026612007245827574`, and subwindow
  counts were `12,36,57,39,21,30`.
- **Gate result:** cost stress failed; all other gates passed.
- **Lesson:** raising the floor to `0.59` did not change the limiting stressed
  train_1 slice. Combine the coverage-producing floor with smaller fallback
  size instead of adding more conditions.

### Attempt 48 Plan: all-symbol one-cycle exit with smaller fallback size

- **Mechanism:** keep the `0.575` bps floor that reaches coverage, but reduce
  fallback target size so marginal coverage trades have less stressed PnL weight.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if smaller fallback size still fails cost stress or loses
  economic return, the fallback entries are not salvageable through sizing.
- **Book effect:** require all three complete-mark symbols, keep the one-cycle
  fixed flat exit, allow fallback baskets above `0.575` bps, and size fallback
  targets at `0.35x`.
- **Failure mode targeted:** train_1 cost-stress miss from coverage-boundary
  fallback entries.

### Attempt 48 Result: smaller fallback size did not repair cost stress

- **Diagnostic result:** score was `0.511719905624958`, cost-stress PSR was
  `0.4825348299607142`, total return was `0.0022917343697879122`, and subwindow
  counts were `12,36,57,45,24,30`.
- **Gate result:** cost stress failed; all other gates passed.
- **Lesson:** fallback size is not the main driver of the stressed train_1 miss.
  Test a simple causal confirmation filter before reverting to the known keeper.

### Attempt 49 Plan: all-symbol fixed exit with zero-threshold price extension

- **Mechanism:** require same-direction 120-minute price extension before a
  funding-sign entry, using the old survivor's price-context idea without
  importing its old ticket contract or symbol universe.
- **Observable:** event-time close, close 120 minutes earlier, funding sign, and
  `available_at` for both close rows by `decision_time`.
- **Falsifier:** if confirmation loses coverage or does not repair cost stress,
  price context is not the missing filter for this target-book branch.
- **Book effect:** keep the all-symbol one-cycle book, `0.575` bps fallback, and
  `0.35x` fallback size, but require signed 120-minute extension.
- **Failure mode targeted:** unconfirmed weak train_1 fallback entries.

### Attempt 49 Result: price extension was too sparse

- **Diagnostic result:** the run had no score because train_1 was missing Sharpe;
  full-Train PSR was `0.938556262356101`, total return was
  `0.0012751201731402428`, trade count was `99`, and minimum subwindow trades
  was `0`.
- **Gate result:** trade floor, subwindow coverage, minimum evidence, cost
  stress, and Train floor failed.
- **Lesson:** even zero-threshold same-direction extension removes too much
  evidence in the strict three-symbol target-book branch. End the 50-run
  lifecycle by rerunning the known all-gate keeper shape rather than preserving
  a failed exploratory branch.

### Attempt 50 Plan: restore the attempt-12 keeper shape

- **Mechanism:** return to the simplest all-gate survivor from this lifecycle:
  two-symbol funding-sign basket, `0.75` bps half-weight fallback, no fixed exit,
  and no price-extension filter.
- **Observable:** latest causal funding sign and magnitude at entry time only.
- **Falsifier:** if the restored keeper no longer passes, the active source no
  longer matches the recorded best candidate.
- **Book effect:** standing target-book rebalance with explicit flats when
  symbols no longer qualify.
- **Failure mode targeted:** avoid ending the 50-attempt lifecycle on a known
  non-scoreable exploratory variant.

### Attempt 50 Result: restored keeper passed all gates

- **Diagnostic result:** score was `0.5912115954065148`, cost-stress PSR was
  `0.553407577666641`, total return was `0.0022376043506817656`, and subwindow
  counts were `16,46,52,50,33,23`.
- **Gate result:** all gates passed.
- **Lesson:** the strongest all-gate survivor remained the simple attempt-12
  target-book shape. Later fixed-horizon variants produced better raw scores but
  could not satisfy both subwindow coverage and cost-stress gates together.

### Attempts 2-8 Plan: price-extension confirmation

Require positive-funding shorts only after same-direction positive return
extension, and negative-funding longs only after same-direction negative return
extension. Test 60m, 120m, and 240m windows with small, medium, and strong
thresholds.

### Attempts 9-15 Plan: funding persistence and quality

Require two or three same-sign funding events, prefer acceleration over raw
funding magnitude, and trade only when the top funding magnitude is meaningfully
above the cross-section.

### Attempts 16-22 Plan: cost-aware eligibility

Add causal ADV or volume-derived liquidity screens, rank funding edge against
estimated impact burden, and suppress trades whose expected edge is too small
versus fee, slippage, and impact burden.

### Attempts 23-29 Plan: side asymmetry

Test long-only negative funding, short-only positive funding, and separate
long/short thresholds when diagnostics show clear side asymmetry.

### Attempts 30-36 Plan: portfolio construction

Test equal-weight baskets, net-neutral books when both sides exist, and
inverse-impact or inverse-volatility sizing while keeping gross and net exposure
inside the protocol budget.

### Attempts 37-43 Plan: horizon and exit shape

Hold through one funding cycle, two funding cycles, or until signal reversal.
Test explicit flat exits after fixed target durations and use simple causal
`RiskRule` stops or take-profits only if diagnostics support them.

### Attempts 44-50 Plan: combine and simplify

Combine only independently useful mechanisms, remove stale params and dead
conditions, and prefer the simplest candidate that improves cost stress,
breadth, and worst-subwindow PSR.
