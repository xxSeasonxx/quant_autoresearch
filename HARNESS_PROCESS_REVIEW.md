# Harness & Process Review — 2026-06-23

Process review of the autoresearch harness and `program.md` as a quant-research
instrument, based on this session's run (attempts 0001–0008). Focus is the
**experiment process** — how the harness and contract shape research — **not the
strategy**.

Lens: the tight propose → run → measure → learn loop in karpathy/autoresearch
(reference only) — fast feedback, *gradient* signal over pass/fail, agent
autonomy, minimal ceremony. Goal here is a handful of surgical fixes, not a
refactor. The framework is sound; the issues below are contained.

**Status (2026-06-24):** items 1–4 implemented and code-reviewed, then refined from
first principles. Current state: objective deflates the full-Train window with
`k_accept = 2.0`; the `subwindow_consistency` gate is **tolerance-based** — at most
`max_subwindows_below_floor` subwindows (default 1) may fall below
`min_subwindow_return` (default 0.0), so one unlucky short window no longer kills a
consistent edge; the run card carries per-window `t_stat` only (the misleading
per-subwindow `money_floor_gap` was dropped — the full-Train gap remains at
`score_parts.deflated_money_floor`); feasibility pre-check at setup;
`program.md`/skill clarifications. Item 5 (surface-vs-grind guidance) **considered
and rejected** — a fuzzy "fully-evidenced" early-stop exception would erode the
anti-quitting discipline for a minor, already-mitigated gain. Full test suite green.

## What happened (process-relevant facts)

- **Started blocked.** The thesis lock froze `bounds_sha256` and setup pinned
  every bound at `min == max`, so no param could move — only `strategy.py` was
  editable, contradicting `program.md`'s bounds-ownership language. Fixed by
  dropping `bounds_sha256` from the lock: the attempt-count deflation already
  prices best-of-N, so search-space width is irrelevant to score honesty.
- **Real edge, but every attempt was `discard`.** Eight attempts isolated a
  genuine, clean, cost-robust edge (capitulation longs: profit factor 1.7–1.9,
  all six subwindows positive, full-train PSR 0.98).
- **Root cause of "no survivor": the `money_floor` objective.** It deflates the
  *worst* of six ~1.7-month subwindows by `k = 2.8` SE and requires ≥ +10%
  annualized. That demands a per-window return **t-stat > 2.8** — an annualized
  Sharpe of roughly 8+ in the weakest slice (more for the sparse windows).
  Observed worst-window t-stats were 0.72–1.59. Near-unclearable for any real
  strategy; the dense baseline failed it too.

## What works (keep)

- **Rich diagnostics** (`by_direction`, `by_symbol`, `economic_slices`,
  `sample_trades`, per-window R/SE) — enabled precise, fast diagnosis. Real
  strength.
- **Frozen-protocol + attempt-count deflation** — a sound evidence model once the
  redundant bounds-freeze was removed.
- **Clean editable surface** (`strategy.py` + `experiment.toml`) and the
  `rationale.md` attempt-log discipline.
- **Causal micro-replay** — genuine leakage protection.

## Process friction, ranked, with fixes

### 1. The objective can make good research look like failure — HIGH value, contained
The deflated worst-of-6-subwindow floor with `k = 2.8` is so strict that no
realistic edge clears it, so the loop can never *reward* a real find. This is the
central process failure: with no achievable target, 50 attempts of honest research
can only register as `discard`. It also double-counts conservatism — worst-window
*selection* and a 2.8-SE *haircut* on a short window.

**Fix (recommended):** deflate the **full-train** window for the money floor
(`full_train_ann − k·SE_full ≥ threshold`) and make subwindow robustness a
**separate** gate — e.g. every subwindow's annualized return > 0 (or > a small
floor), with no per-window haircut. Full-train carries ~6× the effective sample,
so its t-stat is ~2.4× higher and a genuinely good edge can clear it, while
cross-window consistency is still enforced.

*Alternatives:* fewer/longer subwindows (3 × ~3.3 mo); or a gentler acceptance
haircut. Both less clean than deflating full-train.

**Effort:** contained. `objective.py` already computes both full-train and
per-window R/SE; switch the floor input to full-train and add a subwindow-
positivity gate.

### 2. No feasibility pre-check — HIGH value, cheap
Nothing verified, before spending the 50-attempt budget, that the money_floor was
achievable in principle. The ~Sharpe-8 requirement was plain arithmetic at setup.

**Fix:** in `new-thesis-setup`, compute and display the edge needed to clear each
gate given `(subwindows, k, P, trade floors)` — e.g. "worst-window floor needs
annualized Sharpe ≈ X and ≈ Y independent trades/window." Flag implausible
calibrations before the run. A few formulas in the proposal step.

### 3. The binding math was opaque — MED value, cheap
Understanding *why* a clean edge failed required reverse-engineering `objective.py`
(the `n_eff`/autocorrelation → t-stat collapse). The run card reported score and
gate pass/fail, but not the **gap**.

**Fix:** add to the run card, per window: the return t-stat, and a "gate gap" —
the Sharpe or trade-count delta needed to clear the money_floor. Turns pass/fail
into *gradient* feedback (the karpathy spirit) and lets the agent target the
binding quantity directly. Reports values already computed.

### 4. Small contract / CLI frictions — LOW value, trivial
- `climb`'s `--mechanism/--falsifier` are the **frozen thesis identity** (matched
  verbatim against the lock every attempt), not a per-attempt hypothesis. The
  first climb failed ("active thesis identity changed") because the per-attempt
  hypothesis was passed. **Fix:** state this in `program.md` (per-attempt
  hypothesis → `rationale.md`; identity flags → verbatim), or have `climb` read
  them from the lock so they need not be re-passed.
- **Setup must declare a real search space.** This session's setup pinned every
  bound at `min == max`. `new-thesis-setup` should set bounds to the ranges the
  thesis needs tested, not pin to the baseline point.

### 5. When to surface a protocol-blocker vs. grind to stop — MED value, doc-only
`program.md` says "don't pause, run to a stop rule," but a fully-evidenced
envelope-binding conclusion was reached at attempt 8, and surfacing it (the only
productive next step is a protocol change Season owns) beat grinding ~42 polishing
attempts. The doc's "don't pause / exhaust reshaping" pulled against "surface the
wall."

**Fix:** `program.md` should distinguish (a) *timid pausing* — forbidden — from
(b) a *fully-evidenced protocol-level blocker* where the only productive next step
is Season's decision — surface it with the evidence, without burning the rest of
the budget. Empowers agent judgment while keeping the bias toward autonomous
iteration.

## Known constraint — not fixing now
Iteration latency ~5 min/attempt (micro causal replay dominates); 50 attempts is
hours of wall-clock and must run sequentially. Parallel climbs or sampled replay
would tighten the loop but are infrastructure work. Flag and defer.

## Explicitly NOT recommended
No rewrite of the lock / lifecycle / gate framework. The model is sound. The fixes
above are one objective-calibration change, two reporting additions, and two doc
clarifications.

## Suggested order
1. Recalibrate the objective (#1) — Season has agreed it is too restrictive.
2. Doc clarifications (#4, #5) in `program.md` — trivial, no code.
3. Feasibility pre-check (#2) and gate-gap reporting (#3) — cheap adds that make
   the loop fail-fast and gradient-driven.
