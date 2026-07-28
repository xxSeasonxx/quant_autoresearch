# autoresearch program

This file tells a new agent how to run one Train-only quant strategy research
loop in this repository. You edit a bounded strategy surface, run the fixed local
Train harness, record every attempt in `results.tsv`, learn from diagnostics and
sampled trades, and continue until a configured stop rule fires or Season
interrupts.

Strict evidence discipline is the point of the harness: leakage, fills, costs, and
OOS contamination create false edges, so the loop is built to make a real edge hard
to fake.

## North Star

Push for the strongest real, tradeable economic return this thesis can support
under the fixed protocol. The harness ranks attempts and filters keepers under the
score and gates defined in `docs/score_research.md`; think like a skeptical quant,
so every change is causal, feasible, auditable, and explainable from the target
book, diagnostics, and sampled trades.

The score and gates are evidence filters, not a target to game. Never improve a
number by hiding leverage, capacity, cost, fill, data, or OOS problems — that is
the one thing the whole harness exists to prevent.

When a feasibility constraint caps deployed scale, relieving it is itself an alpha
move: idle notional earns nothing, so reshaping the book to deploy more of the edge
feasibly can lift return more than sharpening the raw signal.

Run one bounded thesis from baseline to a configured stop: find or falsify the
simplest causal candidate worth Season's downstream OOS, paper, and small-live
review. Every edit should serve that thesis — express it more cleanly, test it more
directly, learn why it fails, or kill it quickly when the evidence says it is weak.

## Setup

If this is a new thesis or reseed, invoke the `new-thesis-setup` skill
(`/new-thesis-setup`) before the first baseline; it owns mandate intake, protocol
recommendation, Season approval, lifecycle reset, and first-baseline preflight.
Setup also declares the bounded search space: set `experiment.toml` `[bounds.*]` to
the ranges the thesis needs tested, not pinned at `min == max`.

Before baseline, select a venue the account may lawfully access and snapshot its
current per-symbol minimum-order and fixed-order-cost terms with an authoritative
source and as-of date. Until then `[execution_model] mode = "unpriced"` is the
correct protocol state: `status` reports the setup blocker and `climb` creates no
lock, ledger row, quick config, or artifact.

After the first baseline starts the lifecycle, treat the research protocol as frozen.
Only Season may increase `max_iterations`, `plateau_patience`, or
`baseline_grace_iterations` after a configured stop, using the extension procedure
in Stop. Every other protocol field remains frozen.
Ordinary iteration reads only:

- `program.md` — this operating contract;
- `protocol.toml` — frozen account scale, execution terms, Train data, costs,
  fills, capacity, leverage budget, objective, gates, and stop rules;
- `docs/score_research.md` — the frozen score, gate, and result-ledger field semantics (a frozen contract to follow, not repo browsing);
- `experiment.toml` — bounded params and their search ranges;
- `strategy.py` — editable target-book logic;
- `rationale.md` — thesis, components, variants, and lessons;
- recent `results.tsv`, and the latest run card and diagnostics.

Do not browse the rest of the repo during ordinary iteration; go elsewhere only to
debug a run failure, check an explicitly in-scope contract, or follow a direct
request from Season.

If a protocol-owned assumption needs to change, record the reseed rationale in the
Reseed Log (`reseed_log.md`) and keep iterating the current lifecycle. A reseed is
Season's call at a stop-rule boundary, not a mid-run pause. (`reseed_log.md` is
written during the loop but read only at stop, and is not a per-iteration input;
Stop owns the full contract.)

## Experimentation

Each experiment is one Train quick run through `climb`, carrying one thesis-linked
change or one bold thesis-guided variant. Do not run a manual sweep when the next
structural lesson is unclear.

### Fixed Evidence Boundary

The loop uses Train-only quick runs; Train robustness is a development filter, not
proof of an edge. Do not run `evaluate`, import evaluation APIs, read or create OOS
windows, or let downstream OOS, paper, or live results feed back into this thesis.

The hard boundary is evidence integrity:

- no lookahead;
- no same-bar fill fantasy;
- no hidden data, cost, fill, or engine limitation;
- no hidden symbol cherry-picking;
- no OOS feedback;
- no gate repair that cannot be explained from portfolio diagnostics and sampled trades;
- no complexity that exists only because the Train window liked it.

### Editable Surface

The ordinary strategy-development surface is three files:

- `strategy.py` — the target-book surface via `generate_decisions(bars, params)`.
  It returns a complete portfolio of standing, signed weight-of-NAV
  `TargetDecision`s per instrument (`0` = flat/close), idempotent (re-emitting the
  current target trades nothing, and same-symbol targets net), with optional
  declared price-path `RiskRule` exits. Data/time exits are explicit `target=0`
  decisions or new targets, not an implicit ticket duration. Keep it pure and
  causal: a row is usable only when its `available_at` is on or before the emitted
  `decision_time` (`timestamp` is bar/event time, not proof the row was tradable
  knowledge); keep `as_of_time <= decision_time` and declare observations for the
  data the decision depends on.
- `experiment.toml` — the bounded `[params]` and their `[bounds.*]` ranges. You own
  this search space: set each bound to the range the thesis needs and widen or
  tighten it as the mechanism demands. The bounds are a research tool, not a frozen
  wall.
- `rationale.md` — thesis, components, diagnostics, failure modes, and lessons.

Two more files are append-only evidence records, not a per-iteration dev surface —
write to them only as warranted: `reseed_log.md` (reseed evidence; write during the
loop, read at stop — see Stop) and `UPSTREAM_LIMITATIONS_TODO.md` (a limitation the
engine cannot price, per the evidence boundary).

`protocol.toml` owns the account notional, venue execution terms, Train window,
data kind, costs, fills, capacity model, leverage budget, objective, gates, and
stop rules; do not change any of those from strategy code. The thesis identity
frozen for the lifecycle is the mechanism, the falsifier, and the `protocol.toml`
evaluation — that is what makes attempts comparable.

State the mechanism and falsifier as the **invariant economic hypothesis** — the
causal edge and what would disprove it — at the widest level that still keeps
attempts comparable. Do not embed an editable lever (side logic, hold or exit
horizon, cadence, allocation shape, weighting, selection thresholds) in the
identity: naming one accidentally freezes it, forcing a reseed to change what should
be an ordinary edit. Restricting a lever (e.g. trading one side) is always an
in-loop edit, while widening one embedded in the identity is a reseed — so freeze
the widest defensible mechanism and let the loop restrict from there.

The **universe** and the **active book** are different things. The universe is the
protocol-frozen, return-blind population of eligible names; changing it is a reseed,
never a loop edit, and any new universe is itself chosen return-blind on
eligibility, never by dropping names that lost money. The active book is how many of
those names the signal holds — strategy-owned, varied every attempt through ranking,
`top_n`, and selection thresholds. Narrow breadth by reducing the *book* through the
signal, never by naming names or by thresholds reverse-engineered to keep only past
winners. Never compare Train scores across different universes: that is unpriced
multiple testing, and universe generalization is resolved only downstream, OOS. The
breadth you land on is evidence to read, not a number to optimize.

Generated artifacts under `.autoresearch/` and `results/` are evidence, not source:
use the latest diagnostics to choose the next edit, but do not treat generated
snapshots or terminal manifests as design documents.

### Target Book Rules

A target book is a standing portfolio, not a stream of trade tickets.

- `target` is signed weight of NAV: positive long, negative short, `0` flat; a target stands until a later same-symbol decision changes it; re-emitting the same target trades nothing.
- Gross exposure is `sum(abs(target))`; net exposure is `abs(sum(target))`.
- The strategy owns relative allocation shape, side logic, rebalance cadence,
  data/time exits, and declared price-path `RiskRule`s. The operator and upstream
  own the real account scale, venue execution terms, book scale (risk-budget
  sizing), gross/net ceilings, capacity, costs, fills, universe, objective, gates,
  and stop rules.
- Gross or net exposure over the frozen budget fails closed and is non-scoreable, never clamped.
- Every final entry, trim, reversal, close, and `RiskRule` exit must satisfy the
  configured minimum order notional. Unpriced execution or a below-minimum order
  fails closed; orders are never skipped, rounded, accumulated, or clamped.
- Optimize shape, not magnitude: upstream sizes the book, so a global magnitude knob is washed out. Leverage is magnitude too — it scales return and risk together without improving the edge, so it is not a knob you turn; a different leverage budget is a reseed case for Season, not a mid-run change.
- If capacity, financing, or execution cannot be priced by the engine, record the limitation in `UPSTREAM_LIMITATIONS_TODO.md` instead of hiding it in strategy code.

When feasibility is the binding constraint — capacity, participation, or deployable
scale — treat it as part of the alpha problem. The strategy-owned moves that relieve
it are real research: spread turnover across bars so no single decision minute pins
participation, hold longer and rebalance less so the same edge deploys more notional
per unit of impact, concentrate where the signal is strongest, and reshape
allocation to fit the capacity profile. Keep iterating through these moves; only a
wall that survives genuine reshaping — shown by decomposing the failure into edge
quality (net bps/trade, profit factor), which capacity cap binds, and
realized-versus-target scale — is evidence about the envelope, written into the
reseed case at stop.

### Quant Research Standard

Do whatever honest quant research the thesis needs: change signal construction,
allocation, target weights, entry and rebalance cadence, target duration, exit
timing, declared risk shape, side logic, symbol treatment, and simplification —
whenever diagnostics and the trade tape justify it. If the better move is blocked by
upstream data, fill, cost, public API, or engine capability, record it in
`UPSTREAM_LIMITATIONS_TODO.md` rather than approximating it silently in strategy
code.

Each attempt after the baseline should test a mechanistically distinct lever — new
signal construction, allocation shape, side logic, exit structure, or causal
eligibility rule. Record, in one `rationale.md` entry, its mechanism (why it should
make money), observable (what data expresses it at decision time), falsifier (what
result would kill it), expected book effect (gross, net, turnover, concentration,
capacity, exits), and the failure mode it targets. A bound sweep is distinct when it
carries a real mechanism — it better expresses the edge, aligns the signal with a
plausible market horizon, fixes a diagnosed failure, or relieves a feasibility
constraint; re-parameterizing an already-run lever with no new mechanism is
polishing and does not count.

Use the score to compare attempts and the diagnostics and trade tape to decide what
to try next; inspect actual trades before a structural edit when the artifact
provides them. If you cannot explain the last result from the available evidence,
make your next step gathering the missing diagnostic — the trade tape, typed failure
reason, foundation warnings, or gate detail — not a blind edit and not stopping.
After any material strategy-logic change, do a quick causality review before
trusting the result: timestamp ordering, available fields, fill assumptions, state
updates, and hidden reads from artifacts.

Maintain a **Lever Enumeration** in `rationale.md`: every distinct lever the thesis
affords, each marked run/not-run with its result. Use it to choose what to try next
— when no distinct lever remains, the next move is a larger structural variant or a
genuinely new mechanism, never stopping and never a threshold-nudge to look busy.
The enumeration decides what to try, never whether to stop; only the harness ends
the run (see Stop).

Simplicity wins ties. A small score gain bought with ugly symbol or time exceptions
is probably overfit; removing code, params, or conditions while keeping equal or
better evidence is a strong result. Prefer killing a weak thesis over adding filters
until the sample flatters it — but bold structural variants that test the mechanism
are exactly what the loop is for.

## Output Format

Run one ordinary Train attempt with `climb`:

```bash
conda run -n quant python -m loop climb
```

`climb` runs one candidate, writes the artifact directory and `run_card.json`,
appends one row to `results.tsv`, and prints the latest result fields as parseable
key/value lines. Read the printed summary and the attempt's `run_card.json`.

The thesis identity is frozen at baseline and stored in the thesis lock, so ordinary
`climb` attempts do not re-pass it: omit `--mechanism`/`--falsifier` and the harness
sources the identity from the lock. Passing both is still accepted and checked against
the lock, which refuses a changed identity — but never re-type it just to satisfy the
command, since a paraphrase that clears the whitespace check would hard-stop the run.
Put the per-attempt hypothesis in `rationale.md`.

## Experiment Loop

Loop for the current thesis until a configured stop rule fires or Season interrupts:

1. Read `protocol.toml`, `experiment.toml`, `strategy.py`, `rationale.md`, and recent `results.tsv`.
2. Establish or inspect the feasible baseline.
3. Inspect diagnostics, failure reasons, and sampled trades from the latest relevant attempt.
4. Make one thesis-linked edit or one bold thesis-guided variant.
5. Run the Train quick run through `climb`.
6. Parse the score, gate flags, portfolio-foundation metrics, basic economics, exits, failure reasons, and trade samples (fields defined in `docs/score_research.md`).
7. Confirm `climb` appended exactly one row to `results.tsv`, then read it — do not write the ledger yourself. Source provenance is preserved in the per-attempt snapshot.
8. Refresh `rationale.md` with what changed, why, the failure mode targeted, the diagnostic result, and the next falsifier; when a result materially moves the reseed case, append one dated line to `reseed_log.md`.
9. Let the loop decide keep/discard/crash; only all-gates-pass attempts that beat the protocol keep rule advance the best survivor.

Do not pause once the loop has begun: do not ask whether to continue, whether this
is a good stopping point, or whether to try one more edit. Everything inside this
contract — reshaping the book, widening or tightening bounds, simplifying, killing a
weak variant, choosing the next edit — is yours to run without asking. The only
decisions reserved for Season are protocol- and universe-level (a reseed), presented
as a reseed case in `reseed_log.md` at a stop-rule boundary. Surface only a genuine
fork; otherwise take the obvious next step.

`discard` and `crash` never become final candidates, but a discarded working variant
may remain the base for the next edit when it is still simple, causal, and connected
to the thesis.

## When The Loop Looks Overfit

Slow down and inspect the evidence more carefully when: three consecutive edits
target the same gate; a fix depends on one symbol, one subwindow, or one time
boundary; the candidate needs named-symbol exceptions; the next idea is only "move
the threshold a little"; the improvement cannot be explained from sampled trades or
failure detail; or more than 30 attempts have run without a new structural lesson.

This is a research sanity check, not a stop. Inspect trades and pick one path that
continues the loop: simplify, make a larger structural move inside the thesis, or
continue with a written trade-tape justification. A 50- or 100-attempt run should
still have shape — baseline and sanity repairs first, bold structural variants next,
simplification and diagnosed repairs after, then exit and risk-shape variants — but
keep going while new structural lessons are appearing.

## Stop

**Continue rule — the only authority on whether the run is over.** Run
`conda run -n quant python -m loop status` or read the latest `climb` summary. While
it shows `continuation: allowed` and an empty `stop_reason`, begin another attempt.
`results.tsv` contains immutable attempt evidence; continuation and stop reason are
derived from that evidence and the authorized stop rules. Your own judgment that
research has converged, that the envelope binds, or that you are out of distinct
levers is **not** a stop and must not end the run.

Stop only when a configured rule fires: the iteration budget (`max_iterations`)
reached, complexity-cap exhaustion, no feasible baseline within the grace window,
or — when the protocol sets `plateau_patience` below the budget — a post-baseline
plateau. At stop, report the frozen Train survivor, or say the thesis died on Train.
A Train survivor is not a promotion signal — it is only a candidate for Season's
downstream OOS, paper, and small-live review.

Only Season may extend a stopped lifecycle. Season increases one or more of
`max_iterations`, `plateau_patience`, and `baseline_grace_iterations` in
`protocol.toml`, then records the authorization with:

```bash
conda run -n quant python -m loop extend --confirm EXTEND-LIFECYCLE
```

The values may only increase and must reopen the configured stop. The command
rejects every research-identity change and appends an immutable event to
`.autoresearch/lifecycle_events.jsonl`; it never edits `results.tsv`. An agent may
resume `climb` after Season performs this operation, but must never run `extend`
itself.

A reseed recommendation is a third honest outcome, reached through the stop rules,
never instead of them. Maintain a **Reseed Log** in `reseed_log.md` — a file you
write during the loop but do not read or act on until a stop rule fires: one dated
line per attempt that materially strengthens or weakens the reseed case, recording
why. It is never itself a reason to stop. After a stop rule has fired, read it; if
the accumulated log shows the binding constraint is the protocol envelope —
universe, notional, leverage budget, capacity, or a gate — not the edge, consolidate
it into a concrete, evidence-backed reseed case in that file's `## Consolidated
Reseed Case` section. Season decides whether to reseed.
