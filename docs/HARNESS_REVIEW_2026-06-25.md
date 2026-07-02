# Harness & Universe Review — 2026-06-25

A first-principles assessment of the autoresearch harness and `program.md` as a
quant-research instrument: does it both keep evidence honest *and* let a real
profitable edge survive? Plus a first-principles rule for choosing the symbol
universe. Focus is the **process and harness**, not any one strategy. Companion
docs: `HARNESS_PROCESS_REVIEW.md` (earlier process notes) and `HISTORY.md`.

Claims below cite source `file:line` so a fresh session can verify them directly,
including the upstream `quant_strategies` definitions the local `gates.py` consumes.

---

## The governing principle

This is a **Train-only discovery harness that sits upstream of a dedicated OOS /
paper / small-live gauntlet** (`program.md` North Star and Stop sections: a Train
survivor "is not a promotion signal; it is only a candidate for downstream OOS,
paper, and small-live review"; OOS is firewalled out of the loop).

Two consequences drive every recommendation here:

1. **A Train check is one of two kinds, and they have opposite tuning.**
  - **Measurement-validity guards** ensure the *number is real*: no lookahead, no
   same-bar fill, realistic costs/fills, capacity pricing, deflation for
   best-of-N. These must stay strict — a measurement error (e.g. a leak) is not
   "a fluke OOS will catch"; it corrupts OOS too. This is the hard part of
   trading research and the harness does it well.
  - **Fragility judgments** ask *is this real number robust / general?* For a
  discovery filter with a real OOS stage downstream, these should optimize
  **recall, not precision**: a false positive is cheap (the OOS gauntlet,
  designed for exactly this, catches it next stage), while a false negative is
  **expensive and irreversible** — a real edge killed at Train never reaches the
  stage that could validate it.
2. **Generalization is tested by *new regimes*, which live in OOS — not by slicing
  one in-sample window.** Any robustness construct built from a single contiguous
   Train window cannot manufacture regime independence; the sound in-sample
   instrument is uncertainty-pricing (deflation), and true generalization is
   deferred to OOS where the harness already tests it.

The single most useful structural improvement is therefore to **stop collapsing
distinct outcomes into one undifferentiated FAIL** and to keep only the checks that
either guard measurement validity or price in-sample uncertainty — demoting the
rest to reported diagnostics.

---

## Part 1 — What to preserve, what to fix

### Preserve (the earned core)

- **Measurement-validity guards:** `available_at` gating, micro-causality replay,
realistic costs (5/1 bps), fill lag, adv_impact capacity, 2× cost-stress, the OOS
firewall, per-attempt score deflation. These make the backtest number trustworthy.
- **The money-denominated full-Train objective with deflation:** score at
`k_rank=1`, accept floor at `k_accept=2.0`, binding on the **full-Train** window
(`objective.py:287-291`). This is the one statistically-sound, frequency-neutral,
archetype-neutral robustness instrument in the harness — an honest SE haircut on
the in-sample mean using effective sample size. It should remain the *only*
in-window robustness gate.
- **The target-book abstraction** (standing signed weights, upstream sizing,
"leverage/magnitude washed out"): refuses paper-Sharpe and leverage games.

### Fix 1 — `breadth` measures the wrong thing (correctness bug, upstream)

The gated value is the upstream `foundation_scenario.full_train.max_symbol_concentration`
(`gates.py:117-121`; the local trade-bag `symbol_concentration` at `gates.py:84` is
only a fallback). Upstream computes it per marked bar as
`max(|signed_notional_sym|) / gross_notional`, accumulated as a `max()` over all
bars (`quant_strategies/core/portfolio_foundation.py:2690, 2504, 2526`). That is the
**peak instantaneous single-symbol share of gross** — it reads 1.0 whenever the book
holds one name for even one bar, which a sparse, event-driven, or single-name book
does structurally, *regardless of how diversified the PnL is*.

That is not the risk a breadth gate should police. The real risk is **economic
dependence on one symbol**. Measure that instead: single-symbol share of
PnL / risk, or leave-one-symbol-out Sharpe stability. A genuinely diversified
multi-name book scores well below the threshold; a legitimate single-name thesis
trivially passes. **This one fix also dissolves the harness's archetype bias with no
declaration system** — see Part 2.

*Recommended:* redefine the concentration metric to economic concentration in
upstream `portfolio_foundation.py`; the local harness keeps consuming the field.

### Fix 2 — the micro-causality probe over-kills (upstream limitation)

The probe rejects strategies that use **no future data**. A causal intra-symbol
entry-ramp (each step's `as_of` = the signal bar) crashes with
`hidden_lookahead_suppression_detected` (recorded in `UPSTREAM_LIMITATIONS_TODO.md`).
`program.md`'s Target Book Rules explicitly tell the agent to "spread turnover across
bars" to relieve capacity, and the probe then rejects the canonical way to do it —
the harness blocks its own stated alpha lever. Generalizes to any thesis whose
capacity relief is multi-decision-per-signal.

*Recommended:* relax the upstream micro-causality probe so multi-decision-per-signal
patterns with non-future `as_of` are admissible.

### Fix 3 — `subwindow_coverage` should be removed as a hard gate

It hard-fails unless **every** one of 6 subwindows has ≥12 closed trades
(`gates.py:139-155`). The subwindows are **contiguous, equal-calendar-duration**
slices (`portfolio_foundation.py:2584`) — equal clock time, not equal trade count —
so any sparse, seasonal, or regime-clustered edge leaves some slices near-empty *by
construction*.

The gate welds together two jobs:

- A legitimate one — per-window sample sufficiency — which is **already fully owned
by `minimum_evidence*`* (`min_return_sample_count`, `min_effective_sample_size`
enforced on the full window *and* each subwindow, `gates.py:157-178`).
- An illegitimate one — a **uniform-turnover-across-calendar-time mandate**. There is
no statistical reason a real edge must place ≥12 round-trips in each calendar
sixth; that is a turnover-shape requirement masquerading as evidence sufficiency,
and it walls off the entire low-frequency / seasonal archetype.

*Recommended:* **remove the hard gate.** If anything is missing, raise
`minimum_evidence`'s per-window sample floor — the sound knob. Keep the per-subwindow
trade counts as a printed diagnostic.

### Fix 4 — single-window robustness (`subwindow_consistency`) should be demoted to a diagnostic

This gate fails a candidate if more than `max_subwindows_below_floor=1` of 6 slices
fall below `min_subwindow_return=0.0` (`gates.py:196-205`) — i.e. it demands ≥5 of 6
**contiguous, autocorrelated, single-regime** calendar slices be individually
positive. It is meant to catch "the edge only worked in one sub-period," a real
failure mode — but contiguous in-window slices cannot detect it:

- Six adjacent slices of one window share one macro regime and are serially
correlated; "5 of 6 positive" mostly reflects whether the *single* window was
favorable, not regime-independence. It is closer to one observation cut six ways.
- It mostly re-measures short-window noise and uneven trade timing, and it
**double-counts** with full-Train deflation (the statistically correct in-sample
haircut) — while adding a *bias* against time-clustered-but-real edges.
- True out-of-regime testing requires a *different* regime, which by the contract's
own design lives in OOS and is firewalled. The construct is structurally incapable
of delivering the generalization signal it claims.

By the governing principle, this is precision spent against a fragility mode the OOS
stage catches far better — at the cost of irreversible false negatives.

*Recommended:* **demote to a reported confidence diagnostic; gate nothing on it.**
Surface `subwindows_below_floor` and the per-slice returns on the run card so they
can be eyeballed. The full-Train deflated `money_floor` remains the binding
in-sample robustness gate; OOS remains the generalization test.

### Fix 5 — make failure legible (`failure_class`)

Today ~10 gates collapse into one FAIL; distinguishing "no edge" from "real edge,
wrong envelope" requires reading diagnostics. Add **one derived `failure_class`
string** to the run card (`no_edge | capacity_bound | breadth_bound | coverage_thin | robustness_thin | edge`) computed from already-present fields (`gate_flags`,
`capacity_bound`, `deployed_volatility`, `max_feasible_volatility`, the deflated
floor and its t-stat). This captures most of the "make failure a first-class output"
value at trivial cost and forks no gate logic.

### `money_floor` is a deliberate choice, not a defect — keep it

> **SUPERSEDED 2026-07-02.** Reversed by an operator decision: `money_floor` was
> repurposed into a validity-only `significance` gate (deflated full-Train return ≥ 0),
> `min_annualized_return` (0.10) was removed, and money materiality moved entirely to
> the run score. The reasoning below held when the binding failure was capacity/scale;
> once capacity relief shipped, the binding failure became statistical significance, and
> the fused validity+materiality floor false-killed a real edge for reasons orthogonal to
> edge quality. See `HISTORY.md`. The rest of this section is retained as a point-in-time
> record.

`money_floor` requires the deflated full-Train annualized return ≥
`min_annualized_return = 0.10` (`gates.py:185-192`, `protocol.toml`). A real,
significant edge whose deployable vol is capacity-throttled (e.g. ~1.6% vs a 15%
target under adv_impact / $1M / leverage-1.0) can fail this on **scale**, not edge
quality. That is intended: the North Star is "strongest real *tradeable economic
return* … deployed annualized return," and it deliberately treats capacity relief as
alpha work. The threshold encodes an *operator* requirement that an edge be
deployable at scale — a separate axis from "is the edge real."

So **keep `money_floor` and the 0.10 threshold as-is.** Do **not** split it into a
separate edge-quality gate plus a capacity gate: that adds machinery, and the
capacity verdict already exists on every row (`capacity_bound`,
`deployed_volatility`, `max_feasible_volatility`). The only gap is legibility, which
`failure_class` (Fix 5) closes — surface *why* it failed (edge vs scale), don't
re-litigate the threshold.

### Explicitly NOT recommended (avoid the ceremony)

- **Archetype-conditional gate calibration / a thesis "type" declaration that forks
gate behavior.** This is config-sprawl that fights the lean loop. The corrected
breadth metric (Fix 1) removes the archetype bias *without* a declaration system,
and demoting the subwindow gates (Fixes 3–4) removes the rest. No per-type fork is
needed.
- **Splitting `money_floor` into two gates** (see above).
- **Block-bootstrap or purged/embargoed CV inside Train.** Block bootstrap on one
contiguous window still draws one regime — added machinery for marginal gain over
deflation. Purged CV *is* OOS-style evaluation; building it into Train breaches the
explicit OOS firewall. Let full-Train deflation price in-sample uncertainty and let
the existing OOS stage carry generalization.

---

## Part 2 — Choosing the universe, from first principles

**The universe is not a starting choice or a tuning knob — it is part of the thesis,
and the mechanism determines it.** The right question is never "how many symbols
should I start with"; it is "what is the minimum set of instruments on which *this
mechanism* can exist and be falsified?" — answerable from the mechanism alone, before
any backtest.

### The deciding property: the signal's cross-sectional dimension

- **A. Cross-sectional / relative mechanisms** — the signal *is* a comparison across
instruments (relative value, cross-sectional momentum/reversal, dispersion, pairs,
"fade the most-crowded name *vs peers*"). These **do not exist at N = 1**; breadth
is constitutive of the signal. **Start with the full eligible cross-section**,
sized for statistical power (rule of thumb: enough names that a typical decision
has ~10–20 simultaneous candidates, so no 1–2 names dominate). "Start with one and
expand" is incoherent — you would test the edge where it cannot appear and kill it
for the wrong reason.
- **B. Time-series / single-instrument mechanisms** — the signal is fully defined by
*one* instrument's own history (a price/vol/carry/calendar effect on itself). These
work at N = 1; more symbols is just running independent copies of the same edge —
**diversification and capacity, a separate and later question** from "does the edge
exist." **Start with one clean, representative instrument**, prove the edge, then
expand.

**This settles the sequencing question:** "start specific" is right for time-series
edges and wrong for cross-sectional ones, and you can tell which from the mechanism
sentence. Contains "vs peers / relative / rank / most-X among / cross-section" → type
A → start wide. Fully specified for one instrument's own history → type B → start
narrow.

### Why start narrow when you can (type B)

The single-symbol test is the cleanest falsifier: inspect every trade, and remove the
confounds aggregation introduces (survivorship, heterogeneous liquidity,
universe-construction bias). Aggregation has two evidence hazards — it can
*manufacture* an apparent edge (a few names carry it, breadth hides the fragility)
and can *bury* a real one (a strong single-name edge diluted by noise names).
Discover where the signal is unambiguous; expand only to test that it generalizes.

### Sequencing: discovery → robustness → scale

- *Discovery*: the smallest setting where the edge can exist and be cleanly falsified
(N = 1 for type B; minimum-power-N for type A).
- *Robustness*: expand to confirm the edge is not a fluke of the discovery set.
- *Scale*: expand to the full deployable universe for capacity.

The mistake is letting **infrastructure or convenience pick the universe** — seeding
"what we have" because it is there, or starting tiny for a thesis whose signal needs
breadth. Both are "the universe chose itself."

### Choosing members and size

- Define the *population* the mechanism targets; your data is a *sample* of it, not
its definition.
- Select members **return-blind**: eligibility only (liquidity, data quality, the
mechanism's economic preconditions) — never which names backtested well. Freeze for
the lifecycle.
- Set size by mechanism type (full cross-section for A; one-then-expand for B), not by
optimizing a "number of symbols" knob. For a time-series edge, "start with one"
means *one chosen a priori by theory* and treated as a
necessary-but-not-sufficient falsifier you must replicate on a held-out handful —
not "scan symbols and keep the one that worked" (cherry-picking at N = 1).

### Tie-back to Part 1

A valid single-name time-series thesis is permanently blocked by the current breadth
metric (always 1.0) — the harness is not archetype-neutral. The cure is **the
corrected breadth metric (Fix 1) plus demoting the subwindow gates (Fixes 3–4)**,
which make the gates frequency- and archetype-neutral *without* a declaration or
per-type calibration system. The universe question and the harness critique are the
same finding from two sides; the fix is one corrected metric and two demotions, not
new machinery.

---

## Recommended fixes — prioritized


| #   | Change                                                                                           | Kind           | Where                                               |
| --- | ------------------------------------------------------------------------------------------------ | -------------- | --------------------------------------------------- |
| 1   | Redefine concentration → economic concentration (PnL/risk share or leave-one-out)                | correctness    | upstream `quant_strategies/portfolio_foundation.py` |
| 2   | Relax micro-causality probe for non-future multi-decision-per-signal patterns                    | correctness    | upstream `quant_strategies`                         |
| 3   | Remove `subwindow_coverage` hard gate; rely on `minimum_evidence`; keep counts as diagnostic     | simplification | local `gates.py` / `protocol.toml`                  |
| 4   | Demote `subwindow_consistency` / single-window robustness to a reported diagnostic; gate nothing | simplification | local `gates.py` / `protocol.toml`                  |
| 5   | Add derived `failure_class` string to the run card                                               | legibility     | local `loop.py` / run card                          |


Leave alone: the full-Train deflated money LCB score, the `money_floor` 0.10
threshold, deflation, `minimum_evidence`, the anti-fakery guards, and the OOS
firewall. Do not build archetype-conditional gates, split `money_floor`, or add
block-bootstrap / purged-CV into Train.

Net effect: removes one gate, demotes another to a print statement, fixes one
metric and one probe, adds one derived string — eliminating the archetype bias and
the largest false-negative sources while losing no measurement discipline, because
the sound pieces (full-Train deflation, `minimum_evidence`, OOS) already exist.