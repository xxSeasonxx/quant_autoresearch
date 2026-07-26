# Reseed Log

Append-only reseed evidence for the active thesis lifecycle. The thesis and Lever
Enumeration live in `rationale.md`; this file holds only dated reseed evidence and,
at stop, the consolidated reseed case. `program.md` (Stop) owns the full contract:
when to write, when to read, and that this is never itself a reason to stop.

## Running Log

One dated line per attempt that materially strengthens or weakens the reseed case,
recording why. Skip attempts that add nothing.

- 2026-07-25 (attempt-0002, `signal_band` 0.05) — First of the two candidate in-protocol
  capacity-relief levers falsified on clean evidence: the no-trade band raised `book_scale`
  only 0.097 → 0.103 while cutting trades 215 → 83, so `train_strength` fell below the gate
  (LCB −0.0085 vs +0.0074). Mildly **strengthens** the case that the capacity pin is a
  protocol-envelope constraint rather than something the strategy can trade its way out of:
  turnover reduction buys per-trade quality, not deployable scale. Also invalidates the
  inherited matched-control read for every turnover-reducing lever — the contaminant's damage
  scales with entries, so cutting turnover cut the contaminant, not the constraint. One
  candidate remains (`position_smoothing`, which raised turnover and so cannot be explained
  that way); the envelope case is not established until it is tested clean.
- 2026-07-25 (attempt-0003, `position_smoothing` 5) — **Decisively weakens the envelope reseed
  case: the capacity pin is relievable from inside the protocol.** Across-day smoothing took
  `capacity_bound` true → false, deploying the full 0.15 vol target (0.14999, max feasible
  0.180) with `book_scale` 0.097 → 0.328 and score 0.281 → 0.802. No notional cut, universe
  change, or ADV-ceiling concession was needed — only lower turnover per capacity window. The
  inherited recommendation to run this edge at ~$450k is therefore **wrong in kind, not just
  contaminated**: idle capital was never the constraint, the largest single flip was. What
  smoothing costs is evidence, not scale: 23 closed trades against a floor of 36, one trade in
  the thinnest subwindow, and drawdown −0.053 → −0.156. The live research question becomes the
  scale-versus-evidence frontier inside the current protocol, which is an in-loop question, so
  no reseed axis is currently earned.
- 2026-07-25 (attempts-0004/0005, `position_smoothing` 2 and 3) — Quantifies how far in-protocol
  relief actually goes, which is the number any envelope decision needs: at smoothing 3 the book
  deploys **0.128 of the 0.15 vol target** (85%) with all nine gates passing, against 0.067 (45%)
  at the inherited survivor. Both are still `capacity_bound`, so the last ~15% needs either more
  smoothing (which breaks the trade floor) or participation relief that does not spend
  round-trips. The edge is unchanged throughout — t 2.19 / 2.19 / 2.11 across smoothing 1/2/3 —
  so this is pure deployment, not a better signal. **Further weakens the envelope case:** a
  notional cut was proposed to fix a 45% deployment that in-loop turnover shaping lifts to 85%
  at $1M. Any residual envelope argument now has to justify itself on the last 15%, not on the
  original gap.
- 2026-07-25 (attempt-0006, `execution_bars` 10 on smoothing 3) — **The capacity envelope reseed
  case is dead, and a different, genuinely earned axis replaces it.** Within-day TWAP released the
  participation cap without spending a single round-trip (trades 52 → 52): `capacity_bound` true →
  **false**, deployed vol **0.15000** (the full target), `max_feasible_volatility` **0.484** —
  3.2× headroom. All nine gates pass at score 0.850, LCB +0.0081. So none of the inherited
  envelope axes is needed: not a smaller notional, not a deeper universe, not a higher ADV
  ceiling. Turnover shaping at $1M deploys the entire risk budget with capacity to spare.
  **New axis, and it is the one the inherited case explicitly ruled out:** with capacity no
  longer binding, the sole limit on deployment is the operator-frozen `target_volatility = 0.15`.
  The inherited claim that raising it "does nothing" was true only while capacity bound below it.
  Drawdown is now the real ceiling — −0.146 at 0.15 deployed vol implies the 0.25 drawdown gate
  binds near 0.25 vol, so the reachable range is roughly 0.15 → 0.22-0.25. This is Season's
  risk-appetite decision, not a research question: t is unchanged at ~2.11 throughout, so a higher
  vol target buys proportionally more return **and** proportionally more drawdown on the same
  edge. Nothing about the signal improves.
- 2026-07-25 (attempt-0010, `skip_days` 0 isolated) — **The capacity constraint was inverting the
  survivor ranking, which is why the inherited lifecycle mis-ranked its own candidates.** Dropping
  the gap raises t in both lifecycles (2.42 vs 2.19 inherited, 2.40 vs 2.21 here), yet inherited
  *scores* ranked gap 3 above gap 0 because gap 3's lower turnover bought more capacity while the
  book was pinned. A binding capacity cap therefore rewards the cheaper-to-deploy configuration
  over the better edge, and any survivor chosen under a binding cap is suspect for that reason
  alone. Once relieved, the higher-t configuration also earns the higher return. This is a
  **general lesson for the score contract**, not a fact about this thesis: score ranking is only
  trustworthy when `capacity_bound` is false.

- 2026-07-25 (attempts-0011 to 0016, lever re-test under relieved capacity) — **No envelope axis is
  implicated by the lever map.** Seven levers rejected while the book was capacity-bound were
  re-tested: three flipped from gate-failure to gate-pass (`lookback` 30, two-sided `sign`, `equal`
  weighting) and four were confirmed (`top_n` 1, `conviction`, `ma_cross`, `blend`). **None beat the
  survivor and no ranking changed.** The distortion inflated pass/fail labels broadly but inverted
  rank order in only one place, already corrected. Concentration levers additionally *cause* the cap
  to re-bind rather than being penalised by it, so no universe or participation change would rescue
  them. Nothing here supports a universe, notional, or ADV reseed.
- 2026-07-25 (attempts-0023/0029, interaction search) — **The remaining gains came from lever
  interactions inside the protocol, not from the envelope.** Formation horizon 30 wins only at wider
  execution ramping (+29% at 30d against +0.34% at 25d), and the volatility estimator wants 60 only
  at the longer horizon (+3.3%). Score rose 0.977 → **1.036** and t 2.40 → **2.511** from three
  interacting in-loop changes. This *further* weakens any envelope case: the protocol still had
  unexploited shape available when the budget ran out.

- 2026-07-26 (attempts-0034 to 0037, exit-structure block) — **Constrains the one earned reseed
  axis: the drawdown ceiling on `target_volatility` cannot be relieved from inside the protocol.**
  The vol-target case rests on drawdown being the binding limit, so how far that axis reaches
  depends on whether drawdown per unit of deployed volatility can be improved. Four exit devices
  were tested clean and none does it. The fixed stop is the decisive one: it left drawdown unchanged
  (−0.1192 → −0.1197) while costing 5.1% of return, because this book's path risk is a correlated
  cross-sectional move under a global volatility target, not an accumulation of per-name losses from
  entry — a per-name entry-relative barrier cannot reach it. The trailing barrier appears to halve
  drawdown but only by failing to deploy: per unit of deployed volatility it is **worse** (1.06 vs
  the survivor's 0.79). **So the reachable vol range stays as estimated from the raw path risk of
  the edge, roughly 0.15 → 0.30, and no exit lever buys extra headroom to spend.** Any vol-target
  reseed must therefore price drawdown at the survivor's own ratio and test one intermediate level
  before a large step. This neither strengthens nor weakens the case for the axis; it removes a
  hoped-for cushion, and it closes the question rather than leaving it open.
- 2026-07-26 (attempts-0040/0044, two-sided side logic) — **The reseed axis now depends on which
  candidate is carried, and the score-leading one is the worse base for it.** Two-sided side logic
  took the score lead (1.0468 vs 1.0371) by being invested at all times, but it runs 5× the turnover,
  and turnover sets capacity headroom. `max_feasible_volatility` is **0.233** for two-sided against
  **0.338** for long-only, while both carry the same drawdown (−0.12). Since the vol-target axis is
  limited by whichever of drawdown or capacity binds first, the long-only book reaches roughly
  **0.30** volatility (drawdown binds near 0.32, capacity at 0.338) and the two-sided book only about
  **0.23** (capacity binds first). Ramping cannot fix it: widening within-day spreading to 30 bars
  *lowered* headroom to 0.179, which locates the binding constraint at the daily ADV cap rather than
  the per-bar cap, where within-day spreading has no purchase.
  **Consequence for the decision.** A vol-target reseed is worth roughly proportional return, so
  long-only at ~0.30 vol beats two-sided at ~0.23 vol by more than two-sided's 0.94% score lead at
  the frozen target. **If Season takes the vol-target axis, carry the long-only candidate; if the
  book stays at 0.15, the two-sided candidate scores higher.** That is a real fork rather than a
  ranking, it is decided by capacity rather than by edge, and it must not be resolved silently by
  reading the survivor row.

## Consolidated Reseed Case

Written at the `max_iterations` stop (50 attempts, 2026-07-26).

**Recommendation: do not reseed next. Take both candidates downstream first.** No protocol-envelope
constraint binds this thesis except the frozen `target_volatility`, capacity is solved inside the
protocol, and drawdown cannot be improved by any available exit lever — but the vol-target axis is a
leverage dial that yields no new information, so it is the wrong thing to spend a lifecycle on while
the edge is unvalidated. If further Train work is wanted, the universe axis is the defensible one.

1. **Nothing forces an envelope change: no notional, leverage, ADV, or universe reseed is *needed* to
   relieve capacity, and this is settled rather than unexplored.** Turnover shaping deploys the full
   0.15 volatility target at the unchanged $1M notional. Every attempt to implicate the envelope failed
   on its own terms: concentration levers (`top_n` 1, `conviction`) *cause* the participation cap to
   re-bind by construction, so no envelope change rescues them; equal weighting re-binds it by pushing
   the thinnest name through its ADV limit while `inverse_vol` keeps it inside; and the levers rejected
   under a binding cap were re-tested clean without a single ranking change. **This is a statement
   about capacity only.** A universe widening is still worth doing for breadth, pervasiveness, and
   scale — see item 9 — but it would be chosen for those reasons, never because the capacity evidence
   demands it.
2. **The earned axis remains `target_volatility`, and its ceiling is now measured rather than hoped
   for.** Four exit devices were tested clean and none improves drawdown per unit of deployed
   volatility. The fixed stop is decisive: drawdown unchanged (−0.1192 → −0.1197) for 5.1% of return,
   because this book's path risk is a correlated cross-sectional move under a global volatility
   target, not an accumulation of per-name losses from entry. **So there is no cushion to spend, and a
   vol-target reseed must price drawdown at the survivor's own ratio.**
3. **The candidate choice sets how far the axis reaches, and the score-leading candidate reaches
   less.** Both candidates carry the same drawdown (−0.12), so the limit is whichever of drawdown or
   capacity binds first. Long-only holds `max_feasible_volatility` **0.338** and reaches roughly
   **0.30** vol (drawdown binds near 0.32). Two-sided holds **0.233** and reaches about **0.23**
   (capacity binds first, and widening within-day ramping *lowered* headroom to 0.179, locating the
   binding constraint at the daily ADV cap where within-day spreading has no purchase).
4. **Therefore: if the vol-target axis is taken, carry long-only.** A proportional-return axis to
   ~0.30 vol dominates two-sided's 0.94% score lead at the frozen target by a wide margin. If the book
   stays at 0.15, two-sided scores higher and carries 5× the evidence. **The fork is decided by
   capacity, not by edge, and both directions are defensible** — it is Season's risk-appetite and
   evidence-appetite call.
5. **What a vol-target reseed does not buy, stated plainly.** t is ~2.35-2.53 regardless of the
   target, so a higher one buys proportionally more return **and** proportionally more drawdown on the
   same edge. It is not an edge improvement and must never be presented as one. Treat the ceiling as a
   linear extrapolation from a single deployed level, test one intermediate level before any large
   step, and re-measure capacity at that level rather than assuming it scales.
6. **In-protocol shape is now genuinely exhausted, which was not true at the previous stop.** The
   survivor's neighbourhood is mapped closed on every axis the surface affords — horizon (four points
   per candidate), estimator (interior peak at both bases), smoothing, ramping, gap, all three
   weightings, all three breadth modes, both side logics, the regime gate, the hysteresis band,
   rebalance cadence, and all four exit devices. Twenty attempts produced two keeps worth +1.05%
   combined, and the last thirteen produced none. A further continuation at this protocol is no longer
   the cheaper option.

### Sequencing — why the material axis is not the next one

7. **`target_volatility` is material but adds no information, so it must not be the next lifecycle.**
   Raising the target scales return and drawdown together on an unchanged t. That is a risk-appetite
   dial, answerable in a single attempt or downstream with better information, and spending a
   multi-attempt lifecycle on it buys nothing a skeptic would credit. It also has the wrong risk
   ordering: **leveraging an unvalidated edge doubles the cost of being wrong.** Take the axis only
   after the edge has survived out-of-sample, and then with long-only, which reaches ~0.30 vol against
   two-sided's ~0.23.
8. **Extending the Train window backward is ruled out on the data.** `crypto_perp_1min` coverage starts
   2020-03-01 against a Train start of 2021-03-03, so at most ~1 extra year exists — roughly 9% off the
   standard error. That year is the COVID crash plus the opening of the mega-bull, which would make a
   trend book look better for reasons unrelated to edge quality. Wrong kind of data to add; do not
   re-investigate.
9. **The universe axis is the one defensible reseed, and it is now newly viable.** Three names give
   roughly **one** effective bet, since BTC/ETH/SOL co-move despite an effective-symbol-count of
   2.7-3.0; capacity caps the book near $1M; and worst-subwindow PSR of 0.375-0.408 means the edge is
   not reliably present in every regime. Widening to a broad return-blind eligibility rule over the 25
   eligible perps attacks all three at once, and requiring a per-name effect to replicate across a wide
   cross-section is a **harder** test rather than a flattering one. The capacity wall that ended the
   earlier 13-name attempt was a volume-blind participation problem, and this lifecycle established
   that turnover shaping relieves participation without spending round-trips — knowledge that attempt
   did not have. Two constraints on how it is read: Train scores are **not comparable across
   universes**, so this produces a new test and never an improvement over 1.0468; and the wider
   universe must be resolved from eligibility metadata alone, never from which names backtested well.

**Recommended order: OOS both candidates → decide which to carry → universe reseed only if more Train
work is wanted → `target_volatility` last, and only after validation.** Season decides whether to
reseed and along which axis.
