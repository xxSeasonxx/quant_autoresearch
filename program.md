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
annualized return, uncertainty-haircut: the weakest-window lower bound on the
book's annualized return at its upstream-sized book, subject to robustness and
practicality gates. A Train survivor is a candidate for Season's downstream OOS,
paper, and small-live review, not proof of deployability. Think like a skeptical
quant: every change must be causal, feasible, auditable, and explainable from the
target book, diagnostics, and sampled trades. The score and gates are evidence
filters, not the thing to game. Never improve a number by hiding leverage,
capacity, cost, fill, data, or OOS problems.

Run one bounded Train thesis from baseline to configured stop: find or falsify the
simplest causal candidate that survives the Train gates and is worth Season's
downstream OOS, paper, and small-live review.

Every edit should serve the active thesis: express it more cleanly, test it more
directly, learn why it fails, or kill it quickly when the evidence says it is
weak.

## Setup

To start a new thesis run, work with Season to:

1. Agree on a run tag and thesis: one mechanism sentence, one observable, and
   one falsifier.
2. Start from a clean branch or a clearly named working branch for this run.
3. Read the in-scope files:
   - `README.md` for the project map.
   - `program.md` for this operating contract.
   - `protocol.toml` for Train data, costs, fills, objective, gates, and stop rules.
   - `experiment.toml` for bounded params.
   - `strategy.py` for editable signal logic.
   - `rationale.md` for thesis and variant notes.
   - `/Users/Season_Yang/Personal/quant-data/docs/consumer/` for data readiness
     and data-boundary context. Do not browse outside that folder unless Season asks.
4. Complete the New Thesis Protocol Fit pass below before the first attempt.
5. Write the working thesis in `rationale.md`: mechanism, observable, falsifier,
   assumptions, and first failure mode to watch.
6. Verify the configured Train data is available through `quant_data` /
   `quant_strategies`.
7. Initialize the active lifecycle state: for a fresh thesis, `results.tsv` is
   header-only and `.autoresearch/thesis_lock.json` does not carry an old thesis.
   Archive prior generated evidence first if it needs to be preserved.
8. Confirm setup, then begin the loop.

### New Thesis Protocol Fit

Before the first attempt of a new thesis, check whether the frozen Train
contract fits the mechanism. This is setup, not optimization against Train
results.

The agent may propose protocol changes only before the active lifecycle starts:

- data kind, dataset, and symbol universe, based on data readiness, finite mark
  coverage, liquidity/capacity support, and whether the mechanism applies;
- objective and subwindow shape, when the thesis horizon makes the default
  evidence shape inappropriate;
- gate thresholds that define the minimum evidence needed for the stated claim
  to be worth downstream review, not thresholds selected to fit expected
  candidate behavior;
- bounded `experiment.toml` params and bounds that expose only
  mechanism-relevant degrees of freedom.

For each proposed value, state why it follows from the mechanism, observable, and
falsifier. Season must approve protocol changes before the loop starts.

A symbol universe may change later only through a reseed, not as an ordinary
loop edit. Record the reason in `rationale.md`, update `protocol.toml`, reset the
thesis lifecycle, and start a new run. Within an active loop, the strategy may
change symbol treatment, allocation, ranking, scaling, side logic, or causal
eligibility rules when they express the thesis and remain visible in
`rationale.md`.

During ordinary Train iteration, do not browse the rest of this repo. Use the
in-scope files, recent `results.tsv`, and latest diagnostics. Browse elsewhere
only to debug a run failure, check an explicitly in-scope contract, or follow a
direct request from Season.

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
- `experiment.toml`: bounded `[params]` within existing bounds.
- `rationale.md`: thesis, components, diagnostics, failure modes, and lessons.

`protocol.toml` owns the current Train window, data kind, costs, fills, capacity
model, leverage budget, objective, gates, and stop rules. Do not change dates,
costs, fills, capacity, leverage budget, objective, gate thresholds, plateau
patience, max iterations, subwindows, or improvement thresholds from strategy
code. If those assumptions need to change, Season changes the protocol before the
thesis starts or explicitly approves the change.

Build within the operator-frozen leverage budget and capacity model; intended
exposure beyond the budget fails closed upstream (see Target Book Rules).

A universe change is not an ordinary loop edit: symbols are protocol-owned and
frozen for the active lifecycle. Do not change the universe while continuing to
count the same run. If a different universe looks like the cleanest move, record
the reseed case in `rationale.md`; Season can approve a new lifecycle. Never
reach a new universe through hidden signal logic. Symbol-specific normalization,
ranking, scaling, side treatment, and causal eligibility rules remain valid when
they express the thesis and are visible in `rationale.md`.

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
  edge's shape, breadth, and robustness, not a scale multiplier.
- If capacity, financing, or execution cannot be priced by the engine, record the
  limitation instead of hiding it in strategy code.

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

Do not default to parameter sweeps. A parameter change is valid only when it
better expresses the mechanism, aligns the signal with a plausible market
horizon, or fixes a diagnosed failure. More attempts should mean more distinct
research, not more boundary polishing.

Simplicity wins ties. A small score improvement with ugly symbol/time exceptions
is probably overfit. Removing code, params, or conditions while keeping equal or
better evidence is a strong result. Prefer killing a weak thesis over adding
filters until the sample flatters it, but do not confuse caution with passivity:
bold variants are good when they test the mechanism.

## Output Format

Run one attempt with:

```bash
conda run -n quant python -m loop climb \
  --mechanism "<why it should work>" \
  --falsifier "<what kills it>"
```

`climb` runs exactly one candidate, writes the artifact directory and
`run_card.json`, appends exactly one row to `results.tsv`, and prints the latest
result fields as parseable key/value lines. Read the printed summary and the
attempt's `run_card.json`.

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

This is not a stop rule. It is a research sanity check. Inspect trades and choose
one path: simplify, make a larger structural move inside the current thesis,
freeze the survivor, write a new-thesis recommendation in `rationale.md`, or
continue with a written trade-tape justification. Do not change thesis or
protocol mid-run unless Season explicitly reseeds the run.

A 50 or 100 attempt run should still have shape: baseline and sanity repairs
first, bold structural variants next, simplification and diagnosed repairs after
that, then exit/risk-shape variants. This is a bias, not a cage; keep going when
new structural lessons are still appearing.

## Stop

Stop when one configured rule fires: plateau after a feasible baseline,
max iterations, complexity cap exhaustion, or no feasible baseline within the
baseline grace window.

At stop, report the frozen Train survivor or say the thesis died on Train.
A Train survivor is not a promotion signal; it is only a candidate for downstream
OOS, paper, and small-live review.
