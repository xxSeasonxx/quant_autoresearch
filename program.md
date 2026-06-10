# autoresearch program

This file tells a new agent how to run one Train-only quant strategy research
loop in this repository. The agent edits the strategy surface, runs the fixed
local Train harness, records every attempt in `results.tsv`, learns from
diagnostics and trade samples, and continues until a configured stop rule fires
or Season interrupts.

Trading research needs strict evidence discipline because leakage, fills, costs,
and OOS contamination can easily create false edges.

## Run Objective

For this run, act as a skeptical quant researcher first and a benchmark optimizer
never. This is the most important instruction in the loop.

Run one bounded Train thesis from baseline to configured stop. The objective is
to find or falsify the simplest causal strategy candidate that survives the
configured Train gates and is worth Season's downstream OOS, paper, and
small-live review.

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
4. Write the working thesis in `rationale.md`: mechanism, observable, falsifier,
   assumptions, and first failure mode to watch.
5. Verify the configured Train data is available through `quant_data` /
   `quant_strategies`.
6. Initialize `results.tsv` with only the header row if it does not exist.
7. Confirm setup, then begin the loop.

During ordinary Train iteration, do not browse the rest of this repo. Use the
in-scope files, recent `results.tsv`, and latest diagnostics. Browse elsewhere
only to debug a run failure, check an explicitly in-scope contract, or follow a
direct request from Season.

## Fixed Evidence Boundary

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
- no gate repair that cannot be explained from trades;
- no complexity that exists only because the Train window liked it.

## Editable Surface

Ordinary loop edits are:

- `strategy.py`: causal signal logic via `generate_decisions(rows, params)`.
- `experiment.toml`: bounded `[params]` within existing bounds.
- `rationale.md`: thesis, components, diagnostics, failure modes, and lessons.

`protocol.toml` owns the current Train window, data kind, costs, fills,
objective, gates, and stop rules. Do not change dates, costs, fills, objective,
gate thresholds, plateau patience, max iterations, subwindows, or improvement
thresholds from strategy code. If those assumptions need to change, Season
changes the protocol before the thesis starts or explicitly approves the change.

Universe changes are allowed when they are the cleanest quant research move, but
they must be explicit: update `protocol.toml`, record the reason in
`rationale.md`, and interpret later results as evidence about the
strategy-universe combination. Do not hide a universe change as ordinary signal
logic. Symbol-specific normalization, ranking, scaling, and side treatment are
valid when they express the thesis and are visible in `rationale.md`.

Generated artifacts under `.autoresearch/` and `results/` are evidence, not
source. Use the latest diagnostics to choose the next Train edit, but do not
treat generated snapshots or terminal manifests as active design documents.

## Quant Research Standard

Before each structural edit after the baseline, state:

- mechanism: why this should make money;
- observable: what data expresses it at decision time;
- falsifier: what result would kill it;
- failure mode targeted: no edge, too sparse, too costly, side asymmetry, symbol
  concentration, time/regime dependence, exit mismatch, implementation limit, or
  data limit.

Use the score to compare attempts, but use diagnostics and trade tape to decide
what to try next. Inspect actual trades before structural edits: at least a
small sample of winners and losers from the latest relevant attempt when the
artifact provides them. Explain what happened at entry, what happened by exit,
and how costs/fills affected the result. If you cannot explain the trades, do
not edit.

Allowed bold moves include changing signal construction, entry cadence, hold
horizon, exits, risk shape, side logic, symbol treatment, and simplification
when diagnostics and trade tape justify it. If the better research move is
blocked by upstream data, fill, cost, public API, or engine capability, update
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

## Experiment Loop

Loop for the current thesis until a configured stop rule fires or Season
interrupts:

1. Read `protocol.toml`, `experiment.toml`, `strategy.py`, `rationale.md`, and
   recent `results.tsv`.
2. Establish or inspect the feasible baseline.
3. Inspect diagnostics and sampled trades from the latest relevant attempt.
4. Make one thesis-linked edit or one bold thesis-guided variant.
5. Run the Train quick run through `climb` or the focused local helper.
6. Parse score, gate flags, portfolio-foundation metrics, basic economics,
   exits, and trade samples. Use the per-attempt `run_card.json` for detailed
   score parts, gate outcomes, foundation warnings, and micro causality evidence.
7. Append exactly one tab-separated row to `results.tsv`. Use the existing
   header; do not invent a second ledger during ordinary iteration.
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
- the improvement cannot be explained from sampled trades;
- more than 30 attempts have run on one Train window without a new structural
  lesson.

This is not a stop rule. It is a research sanity check. Inspect trades and
choose one path: simplify, make a larger structural move, freeze the survivor,
switch thesis, or continue with a written trade-tape justification. Do not keep
polishing the same boundary without new evidence.

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
