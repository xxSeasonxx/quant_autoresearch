# autoresearch program

This file tells a new agent how to run one Train-only quant strategy research
loop in this repository. The agent edits the strategy surface, runs the fixed
local Train harness, records every attempt in `results.tsv`, learns from
diagnostics and trade samples, and continues until a configured stop rule fires
or Season interrupts.

Trading research needs strict evidence discipline because leakage, fills, costs,
and OOS contamination can easily create false edges.

## North Star

Your job is to push for the strongest real, tradeable economic return this Train
thesis can support under the fixed protocol. The run score is the deployed
annualized return, uncertainty-haircut: the full-Train deflated lower bound on the
book's annualized return at its upstream-sized book, subject to robustness and
practicality gates. A Train survivor is a candidate for Season's downstream OOS,
paper, and small-live review, not proof of deployability. Think like a skeptical
quant: every change must be causal, feasible, auditable, and explainable from the
target book, diagnostics, and sampled trades. The score and gates are evidence
filters, not the thing to game. Never improve a number by hiding leverage,
capacity, cost, fill, data, or OOS problems.

When a feasibility constraint caps deployed scale, relieving it is itself an alpha
move: idle notional earns nothing, so reshaping the book to deploy more of the
edge feasibly can lift return more than sharpening the raw signal.

Run one bounded Train thesis from baseline to configured stop: find or falsify the
simplest causal candidate that survives the Train gates and is worth Season's
downstream OOS, paper, and small-live review.

Every edit should serve the active thesis: express it more cleanly, test it more
directly, learn why it fails, or kill it quickly when the evidence says it is
weak.

## Setup

If this is a new thesis or reseed, invoke the `new-thesis-setup` skill
(`/new-thesis-setup`) before running the first baseline. That skill owns mandate
intake, protocol recommendation, Season approval, lifecycle reset, and
first-baseline preflight.

Setup also declares the bounded search space: set `experiment.toml` `[bounds.*]`
to the ranges the thesis needs tested, not pinned to the baseline point. Bounds
pinned at `min == max` leave the loop nothing to search.

After the first baseline starts the lifecycle, treat `protocol.toml` as frozen.
Ordinary Train iteration uses only:

- `program.md` for this operating contract;
- `protocol.toml` for frozen Train data, costs, fills, objective, gates, and stop rules;
- `experiment.toml` for bounded params;
- `strategy.py` for editable target-book logic;
- `rationale.md` for thesis, components, variants, and lessons;
- recent `results.tsv`;
- the latest run card and diagnostics.

During ordinary Train iteration, do not browse the rest of this repo. Use the
in-scope files, recent `results.tsv`, and latest diagnostics. Browse elsewhere
only to debug a run failure, check an explicitly in-scope contract, or follow a
direct request from Season.

If protocol-owned assumptions need to change, record the reseed case in
`rationale.md` and keep iterating the current lifecycle — do not halt mid-run to
wait for approval. The reseed is Season's call at a stop-rule boundary, not a
mid-run pause; the loop stays productive until a stop rule fires or Season
interrupts.

## Experimentation

Each experiment is one Train quick run through `climb`. The strategy edit should
be one thesis-linked change or one bold thesis-guided variant. Do not run a
manual sweep when the next structural lesson is unclear.

### Fixed Evidence Boundary

The loop uses Train-only quick runs. Train robustness is a development filter,
not proof of an edge.

Do not run `evaluate`. Do not import evaluation APIs. Do not read or create OOS
windows from this loop. Do not let downstream OOS, paper, or live results feed
back into this same Train thesis.

The hard boundary is evidence integrity:

- no lookahead;
- no same-bar fill fantasy;
- no hidden data, cost, fill, or engine limitation;
- no hidden symbol cherry-picking;
- no OOS feedback;
- no gate repair that cannot be explained from portfolio diagnostics and sampled trades;
- no complexity that exists only because the Train window liked it.

### Editable Surface

Ordinary loop edits are:

- `strategy.py`: the editable target-book surface via `generate_decisions(bars,
  params)`. It returns a complete portfolio of standing, signed weight-of-NAV
  `TargetDecision`s per instrument (`0` = flat/close), idempotent (re-emitting the
  current target trades nothing, and same-symbol targets net), with optional
  declared price-path `RiskRule` exits. Data/time exits are explicit `target=0`
  decisions or new targets, not an implicit ticket duration. Keep it pure and
  causal: a row is usable only when its `available_at` is on or before the
  emitted `decision_time`;
  `timestamp` is bar/event time, not proof that the row was tradable knowledge.
  Keep `as_of_time <= decision_time` and declare observations for data the
  decision depends on.
- `experiment.toml`: the bounded `[params]` and their `[bounds.*]` search ranges.
  You own this search space: set each bound to the range the thesis needs tested,
  and widen or tighten it as the mechanism demands. The bounds are a research
  tool, not a frozen wall.
- `rationale.md`: thesis, components, diagnostics, failure modes, and lessons.

`protocol.toml` owns the current Train window, data kind, costs, fills, capacity
model, leverage budget, objective, gates, and stop rules. Do not change dates,
costs, fills, capacity, leverage budget, objective, gate thresholds, plateau
patience, max iterations, subwindows, or improvement thresholds from strategy
code. If those assumptions need to change, Season changes the protocol before the
thesis starts or explicitly approves the change.

The thesis identity frozen for the lifecycle is the mechanism, the falsifier, and
the `protocol.toml` evaluation (data, costs, fills, capacity, leverage budget,
objective, gates, stop rules). That identity is what makes attempts comparable.
The `experiment.toml` search space is not part of it: bounds and params are yours
to set and revise mid-run. Multiple-testing honesty comes from the hard attempt
cap and the per-attempt score deflation, which price best-of-N regardless of how
wide the search space is — so widening or tightening a bound is an ordinary loop
edit, not a reseed.

Build within the operator-frozen leverage budget and capacity model; intended
exposure beyond the budget fails closed upstream (see Target Book Rules).

The universe is two things, owned by two parties. The frozen **universe** is the
eligible population the mechanism may trade — protocol-owned, selected
return-blind, and fixed for the lifecycle. The **active book** is how many of
those names the signal actually holds — strategy-owned, varying every attempt
through ranking, `top_n`, and selection thresholds. Converging on the right
breadth means reducing the *book*, never the *universe*: start from the full
frozen universe and let the signal hold fewer names where the edge is strongest.
That reduction is honest because the signal drives it — return-blind and causal —
not which names earned. The breadth you land on is an output of the mechanism and
regime; read it as evidence, not a count to optimize toward.

A universe change is not an ordinary loop edit: symbols are protocol-owned and
frozen for the active lifecycle. Do not change the universe while continuing to
count the same run. If a different universe looks like the cleanest move, record
the reseed case in `rationale.md`; Season can approve a new lifecycle, and the new
universe must itself be chosen return-blind on eligibility — never by dropping the
names that lost money. Never reach a new universe through hidden signal logic:
thresholds tuned until only the historically winning names ever trade is exactly
that. Symbol-specific normalization, ranking, scaling, side treatment, and causal
eligibility rules remain valid when they express the thesis and are visible in
`rationale.md`.

Generated artifacts under `.autoresearch/` and `results/` are evidence, not
source. Use the latest diagnostics to choose the next Train edit, but do not
treat generated snapshots or terminal manifests as active design documents.

### Target Book Rules

A target book is a standing portfolio, not a stream of trade tickets.

- `target` is signed weight of NAV: positive long, negative short, `0` flat.
- A target stands until a later same-symbol decision changes it.
- Re-emitting the same target trades nothing; same-symbol targets net.
- Gross exposure is `sum(abs(target))`; net exposure is `abs(sum(target))`.
- The strategy owns relative allocation shape, side logic, rebalance cadence,
  data/time exits, and declared price-path `RiskRule`s.
- The operator and upstream own book scale (risk-budget sizing), gross/net exposure
  ceilings, capacity, costs, fills, universe, objective, gates, and stop rules.
- Gross or net exposure over the frozen budget is fail-closed and non-scoreable,
  never clamped.
- Optimize shape, not magnitude: upstream sizes the book, so a global magnitude
  knob is washed out and is not a degree of freedom to search. The score rewards
  the deployed money the *shape* earns at the upstream-sized book; improve the
  edge's shape, breadth, and robustness, not a scale multiplier. Leverage is
  magnitude too: it scales return and risk together without changing the edge, so
  levering up flatters the money score without improving the alpha — it is not a
  knob you turn. If a different leverage budget is genuinely right, that is a
  reseed case for Season, not a mid-run change.
- If capacity, financing, or execution cannot be priced by the engine, record the
  limitation instead of hiding it in strategy code.

When feasibility is the binding constraint — capacity, participation, or
deployable scale — treat it as part of the alpha problem, not a wall to route
around. The strategy-owned moves that relieve it are real research: spread
turnover across bars so no single decision minute pins participation, hold longer
and rebalance less so the same edge deploys more notional per unit of impact,
concentrate where the signal is strongest rather than diluting breadth, and
reshape allocation to fit the capacity profile. This reshaping is the work of the
loop, not a reason to pause it: keep iterating until a configured stop rule fires,
and never stop on your own to declare the envelope binding. Exhaust these moves
honestly; only a wall that survives genuine reshaping — shown by decomposing the
failure into edge quality (net bps/trade, profit factor), which capacity cap
binds, and realized-versus-target scale — is evidence about the envelope, written
into the reseed case only at stop.

### Quant Research Standard

Before each structural edit after the baseline, state:

- mechanism: why this should make money;
- observable: what data expresses it at decision time;
- falsifier: what result would kill it;
- book effect: expected change to gross, net, turnover, concentration, capacity,
  and exits;
- failure mode targeted: no edge, too sparse, too costly, side asymmetry, symbol
  concentration, time/regime dependence, exit mismatch, implementation limit, or
  data limit.

Use the score to compare attempts, but use diagnostics and trade tape to decide
what to try next. Inspect actual trades before structural edits when the artifact
provides them. If no trade sample exists, use the typed failure reason,
foundation warnings, and gate details instead. If the available evidence cannot
explain the result, do not edit.

Allowed bold moves include changing signal construction, allocation, target
weights, entry and rebalance cadence, target duration, explicit exit timing,
declared risk shape, side logic, symbol treatment, and simplification when
diagnostics and trade tape justify it. If the better research move is blocked by
upstream data, fill, cost, public API, or engine capability, update
`UPSTREAM_LIMITATIONS_TODO.md` instead of approximating it silently in strategy
code.

After any material strategy-logic change, do a quick causality review before
trusting the next result: check timestamp ordering, available fields, fill
assumptions, state updates, and hidden reads from artifacts, results, or
diagnostics.

A parameter sweep that tests a real edge hypothesis is legitimate research: sweep
a bound when it better expresses the mechanism, aligns the signal with a plausible
market horizon, fixes a diagnosed failure, or relieves a feasibility constraint.
What is not research is aimless boundary-polishing — nudging a bound only to
flatter the in-sample score with no mechanism behind the move. More attempts
should mean more distinct research, not more polishing.

Each attempt after the baseline must test a mechanistically distinct lever — new
signal construction, allocation shape, side logic, exit structure, or causal
eligibility rule — with its own mechanism and falsifier; re-parameterizing a lever
already run is not distinct. Maintain a **Lever Enumeration** in `rationale.md`:
every distinct lever the thesis affords, each marked run/not-run with its result.
Exhaustion is a property of this enumeration, not of the iteration counter: the run
may not conclude while a plausible distinct lever is un-run and no stop rule has
fired, and it ends at whichever comes first — the enumeration genuinely closed
(every distinct lever has a result and no new distinct hypothesis can be articulated
with a real mechanism) or the `max_iterations` cap. Running out of distinct
hypotheses before the cap is the honest signal of near-exhaustion; manufacturing
threshold-nudges to fill the cap is the dishonesty this forbids.

Simplicity wins ties. A small score improvement with ugly symbol/time exceptions
is probably overfit. Removing code, params, or conditions while keeping equal or
better evidence is a strong result. Prefer killing a weak thesis over adding
filters until the sample flatters it, but do not confuse caution with passivity:
bold variants are good when they test the mechanism.

## Output Format

Run one ordinary Train attempt with `climb`:

```bash
conda run -n quant python -m loop climb \
  --mechanism "<why it should work>" \
  --falsifier "<what kills it>"
```

`climb` runs one candidate, writes the artifact directory and `run_card.json`,
appends one row to `results.tsv`, and prints the latest result fields as
parseable key/value lines. Read the printed summary and the attempt's
`run_card.json`.

`--mechanism` and `--falsifier` carry the frozen thesis identity, not the
per-attempt idea: pass the same text verbatim on every attempt. The harness
matches them against the thesis lock and refuses a changed identity. Put the
per-attempt hypothesis — why this specific edit should make money and what would
kill it — in `rationale.md`.

## Logging Results

Do not append `results.tsv` yourself during ordinary iteration. Confirm that
`climb` appended one tab-separated row, then read that row. Use `results.tsv` for
scan state and the per-attempt `run_card.json` for score parts, gate outcomes,
foundation warnings, causality evidence, primary failure mode, and sampled
trades.

## Experiment Loop

Loop for the current thesis until a configured stop rule fires or Season
interrupts:

1. Read `protocol.toml`, `experiment.toml`, `strategy.py`, `rationale.md`, and
   recent `results.tsv`.
2. Establish or inspect the feasible baseline.
3. Inspect diagnostics, failure reasons, and sampled trades from the latest
   relevant attempt.
4. Make one thesis-linked edit or one bold thesis-guided variant.
5. Run the Train quick run through `climb`.
6. Parse score, gate flags, portfolio-foundation metrics, basic economics, exits,
   failure reasons, and trade samples.
7. Confirm `climb` appended exactly one tab-separated row to `results.tsv` and read
   it; do not append a row yourself or start a second ledger during ordinary
   iteration.
8. Refresh `rationale.md` with what changed, why, the failure mode targeted, the
   diagnostic result, and the next falsifier.
9. Let the loop decide keep/discard/crash. Only all-gates-pass attempts that
   improve by the protocol keep rule advance the best Train survivor.

Do not pause once the loop has begun. After setup confirmation, do not ask
whether to continue, whether this is a good stopping point, or whether to try one
more edit. Continue until a protocol stop rule fires or Season interrupts. This
workflow is meant to run while Season is away from the keyboard.

The only decisions reserved for Season are protocol- and harness-level: changing
`protocol.toml` (data, costs, fills, capacity, leverage/notional budget, objective,
gates, stop rules) or the universe — i.e. a reseed. Present those as a reseed case
in `rationale.md` reached at a stop-rule boundary, not by pausing mid-run.
Everything else inside the loop and its in-scope files — reshaping the book,
widening or tightening bounds, simplifying, killing a weak variant, and choosing
the next edit — is yours to run without asking. Do not offer decision menus for
work that is already inside this contract; take the obvious next step and surface
only a genuine fork.

`discard` and `crash` never become final candidates, but a discarded working
variant may remain the base for the next edit when it is still simple, causal,
and connected to the thesis.

## When The Loop Looks Overfit

Pause ordinary edit/run iteration and inspect the evidence more carefully when:

- three consecutive edits target the same gate;
- a fix depends on one symbol, one subwindow, or one time boundary;
- the candidate needs named-symbol exceptions to survive;
- the next idea is only "move the threshold a little";
- the improvement cannot be explained from sampled trades or failure details;
- more than 30 attempts have run on one Train window without a new structural
  lesson.

This is a research sanity check, not a stop. Inspect trades and choose one path
that **continues the loop**: simplify, make a larger structural move inside the
current thesis, or continue with a written trade-tape justification. Recording an
updated reseed hypothesis in the Reseed Log is expected here — but it is a note,
never a reason to stop iterating. Freezing the survivor and concluding the run
happen only when a configured stop rule fires (see Stop). Do not change thesis or
protocol mid-run unless Season explicitly reseeds the run.

A 50 or 100 attempt run should still have shape: baseline and sanity repairs
first, bold structural variants next, simplification and diagnosed repairs after
that, then exit/risk-shape variants. This is a bias, not a cage; keep going when
new structural lessons are still appearing.

## Stop

Stop when one configured rule fires: plateau after a feasible baseline,
max iterations, complexity cap exhaustion, or no feasible baseline within the
baseline grace window.

Do not conclude — freeze a survivor, declare thesis death, or finalize a reseed
case — before a configured stop rule fires. While the harness reports
`continuation: allowed` with an empty `stop_reason`, the run is not done: a judgment
that "research has converged" or "the envelope binds" is not a stop rule, and is
exactly the premature-closure the loop must resist. A reseed story often looks
complete long before the search is; keep generating mechanistically distinct
falsifications until a stop rule fires, then read the accumulated Reseed Log.

At stop, report the frozen Train survivor or say the thesis died on Train.
A Train survivor is not a promotion signal; it is only a candidate for downstream
OOS, paper, and small-live review.

A reseed recommendation is a third honest outcome, reached through the stop rules,
never instead of them. Maintain a **Reseed Log** in `rationale.md`: a living,
append-only section with one dated line per attempt recording whether that result
strengthens or weakens the reseed case, and why. It accretes the reseed argument as
evidence builds and is **never itself a reason to stop** — it is read only after a
stop rule has fired. When the loop stops and the accumulated log shows the binding
constraint is the protocol envelope itself — universe, notional, leverage budget,
capacity, or a gate — not the edge, consolidate it into a concrete, evidence-backed
reseed case. It does not change the protocol or the run; Season decides whether to
reseed.
