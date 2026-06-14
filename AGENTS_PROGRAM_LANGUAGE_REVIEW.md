# AGENTS.md / program.md Language Review

Review date: 2026-06-14

Implementation status: accepted by Season and applied to `AGENTS.md` /
`program.md` in the same worktree before commit.

Scope: current working-tree `AGENTS.md` and `program.md`, with context from
Karpathy's `autoresearch` repo, this repo's `README.md`, `protocol.toml`,
`docs/score_research.md`, and the upstream `quant_strategies` target-book
contract.

Line references below describe the pre-implementation files reviewed on
2026-06-14.

External references:

- https://github.com/karpathy/autoresearch
- https://raw.githubusercontent.com/karpathy/autoresearch/master/program.md

## Executive Recommendation

Do not do a large rewrite. The current docs have the right core: one
human-seeded thesis, Train-only iteration, narrow editable surface, target-book
semantics, fail-closed feasibility, no OOS feedback, and stop rules.

The main risk is prompt load. Upstream `autoresearch` works because the agent's
operating contract is very small: setup, editable surface, one metric, one log,
one loop. This project needs more constraints, but `program.md` should make the
agent remember one hierarchy:

```text
Push for the strongest real, tradeable economic return the active Train thesis can support.
Do it through causal target-book edits.
Let the fixed Train protocol decide feasibility, gates, score, keep/discard, and stop.
Never improve a number by weakening evidence.
```

Most refinements should tighten wording and section shape, not add new rules.

## Source-Grounded Baseline

- Upstream `autoresearch` keeps `program.md` as the human-edited research-org
  contract: one editable file, a fixed run budget, a single metric, an append-only
  result log, and a keep/discard loop.
- This repo correctly adapts that shape to quant research: the editable file is a
  pure strategy target book, the run budget is a Train quick run, the score comes
  from the netted-book NAV path, and OOS is outside the loop.
- Upstream `quant_strategies` defines the target book as standing signed
  weight-of-NAV `TargetDecision`s, scored through one causal netted NAV book; an
  envelope breach is fail-closed and non-scoreable, never clamped.

## What Is Already Strong

### `AGENTS.md`

- Lines 7-14 are strong: they set the skeptical quant role and delegate Train
  mechanics to `program.md`.
- Lines 18-28 are concise and mostly MECE for repo-level rules.
- Lines 25-26 correctly make leverage/capacity infeasibility a verdict, not a
  weak score.
- Line 28 is valuable for Train runs: skills are another prompt layer and should
  stay out of autonomous experiments.

### `program.md`

- Lines 14-20 have the right north star: skeptical quant first, not score-gamer.
- Lines 22-28 correctly bind every edit to the active thesis.
- Lines 58-75 correctly isolate Train evidence from downstream/OOS evidence.
- Lines 77-113 correctly fence the editable surface and generated artifacts.
- Lines 115-142 correctly introduce target-book risk design.
- Lines 144-185 correctly force mechanism, observable, falsifier, book effect,
  trade-tape inspection, and simplicity.
- Lines 187-217 correctly state one climb attempt, one logged row, and keep only
  when gates pass and score improves.
- Lines 241-249 correctly stop on configured rules and avoid promotion language.

## High-Leverage Refinements

### 1. Restore Upstream Section Shape

Current issue: `program.md` has the right content, but the top-level shape has
drifted from the upstream contract and from
`openspec/specs/autoresearch-agent-contract/spec.md`, which expects setup,
experimentation, output format, logging results, and experiment loop sections.

Recommendation: keep the substance, but reorganize top-level headings into this
shape:

```text
# autoresearch program

## North Star
## Setup
## Experimentation
### Fixed Evidence Boundary
### Editable Surface
### Target Book Rules
### Quant Research Standard
## Output Format
## Logging Results
## Experiment Loop
## When The Loop Looks Overfit
## Stop
```

Why: this keeps the extra quant guardrails while preserving the simple execution
grammar that makes upstream `autoresearch` reliable for agents.

### 2. Make The North Star Even Simpler

Current lines 14-20 are good, but dense. The agent should internalize the
objective in one pass.

Suggested replacement for lines 14-20:

```markdown
Your job is to push for the strongest real, tradeable economic return this Train
thesis can support under the fixed protocol. Think like a skeptical quant: every
change must be causal, feasible, auditable, and explainable from the target book,
diagnostics, and sampled trades. The score and gates are evidence filters, not
the thing to game. Never improve a number by hiding leverage, capacity, cost,
fill, data, or OOS problems.
```

Why: this preserves the user's core principle: enable the LLM to think like a
quant and maximize feasible strategy return. It also keeps score/gates in the
right role: selection machinery, not the researcher's identity.

### 3. Clarify Causal Availability Wording

Current lines 81-87 say to gate on `available_at`, never `timestamp`. The intent
is correct, but the wording is too compressed for target-book strategy code,
where `TargetDecision` has `as_of_time` and `decision_time`, and observation
availability is enforced against `available_at <= decision_time`.

Suggested replacement for the causality sentence in lines 81-87:

```markdown
Keep it pure and causal: a row is usable only when its `available_at` is on or
before the emitted `decision_time`; `timestamp` is bar/event time, not proof that
the row was tradable knowledge. Keep `as_of_time <= decision_time` and declare
observations for data the decision depends on.
```

Why: this is closer to the upstream target-book contract and reduces the chance
that an agent writes timestamp-only logic while believing it satisfied the rule.

### 4. Tighten Target-Book Rules

Current lines 115-142 are useful but long. They risk becoming a mini textbook
inside the primary agent prompt. Keep the section, but make it a short contract.

Suggested rewrite shape:

```markdown
## Target Book Rules

A target book is a standing portfolio, not a stream of trade tickets.

- `target` is signed weight of NAV: positive long, negative short, `0` flat.
- A target stands until a later same-symbol decision changes it.
- Re-emitting the same target trades nothing; same-symbol targets net.
- The strategy owns allocation, sizing, side logic, rebalance cadence, data/time
  exits, and declared price-path `RiskRule`s.
- The operator owns gross/net exposure ceilings, capacity, costs, fills, universe,
  objective, gates, and stop rules.
- Gross or net exposure over the frozen budget is fail-closed and non-scoreable,
  never clamped.
- Size is not alpha. Use size to express conviction and capacity; do not use it
  to manufacture evidence.
- If capacity, financing, or execution cannot be priced by the engine, record the
  limitation instead of hiding it in strategy code.
```

Why: the agent gets the complete target-book mental model without having to parse
gross/net examples, financing edge cases, and utilization diagnostics in the hot
loop. Those details can stay in `README.md`, `protocol.toml`, and
`docs/score_research.md`.

### 5. Soften "Scale != Edge"

Current lines 130-131 say larger size does not move the PSR score. That is a good
anti-gaming instinct, but it is too absolute because size can affect total
return, drawdown, impact, capacity, and gates, and nonlinear frictions can affect
portfolio-return shape.

Suggested replacement:

```markdown
- **Size is not alpha:** larger targets can change total return, drawdown, costs,
  capacity utilization, and gates, but they do not create an edge. Size only what
  the mechanism and capacity envelope justify.
```

Why: this keeps the anti-gaming rule while staying financially precise.

### 6. Add Explicit Output / Logging Sections

Current `program.md` puts output/logging rules inside the loop. That works, but
upstream has separate "Output format" and "Logging results" sections. This is
important because agents often recover from crashes or context compaction by
looking for those headings.

Recommended additions:

```markdown
## Output Format

Use `conda run -n quant python -m loop climb --mechanism "<why it should work>" --falsifier "<what kills it>"`.
`climb` runs exactly one candidate and appends exactly one row to `results.tsv`.
Read the printed key/value summary and the attempt's `run_card.json`.

## Logging Results

Do not append `results.tsv` yourself during ordinary iteration. Confirm that
`climb` appended one tab-separated row, then read that row. Use `results.tsv` for
scan state and the per-attempt `run_card.json` for score parts, gates,
foundation warnings, causality evidence, and sampled trades.
```

Why: this mirrors upstream's agent-friendly recovery points while preserving the
local harness authority.

### 7. Remove Or Reword "Switch Thesis" During Overfit Checks

Current lines 231-233 allow "switch thesis" inside the overfit sanity check. That
conflicts with the rest of the contract: one active thesis, frozen protocol, and
Season-owned reseeding.

Suggested replacement for the choice sentence:

```markdown
This is not a stop rule. Inspect trades and choose one path: simplify, make a
larger structural move inside the current thesis, freeze the survivor, write a
new-thesis recommendation in `rationale.md`, or continue with a trade-tape
justification. Do not change thesis or protocol mid-run unless Season explicitly
reseeds the run.
```

Why: the agent can still think boldly, but cannot silently mutate the research
question after seeing Train results.

### 8. Replace "Hold Horizon" Vocabulary

Current lines 164-166 list "hold horizon" as an allowed bold move. In a
target-book contract, data/time exits are explicit `target=0` or new target
decisions, not ticket holds.

Suggested edit:

```markdown
Allowed bold moves include changing signal construction, allocation, target
weights, entry and rebalance cadence, target duration, explicit exit timing,
declared risk shape, side logic, symbol treatment, and simplification when
diagnostics and trade tape justify it.
```

Why: small language change, but it keeps the agent thinking in standing-book
terms instead of reverting to trade-ticket semantics.

### 9. Add A No-Trade / No-Sample Exception To Trade-Tape Inspection

Current lines 157-162 end with "If you cannot explain the trades, do not edit."
That is good for normal scored attempts, but infeasible/no-trade attempts may not
have sampled trades.

Suggested refinement:

```markdown
Inspect actual trades before structural edits when the artifact provides them.
If no trade sample exists, use the typed failure reason, foundation warnings, and
gate details instead. If the available evidence cannot explain the result, do not
edit.
```

Why: this preserves evidence discipline without blocking on artifacts that cannot
exist for non-scoreable runs.

### 10. Split The Final `AGENTS.md` Conflict Rule

Current `AGENTS.md` line 32 is correct but too long for a global-ish local rule.

Suggested replacement:

```markdown
Prefer the more specific active contract in `program.md`, `protocol.toml`, and
the current thesis files.

Do not change protocol-owned research assumptions unless the active contract or
Season explicitly allows it. If one looks wrong, note it in `rationale.md` and
keep the run inside the current contract; an unworkable contract should die
through the configured Train stop rules.
```

Why: same rule, easier to follow during autonomous loops.

## What Not To Change

- Do not make `program.md` a general quant research manual. The agent should read
  enough to run, not enough to learn the whole platform.
- Do not move scoring math into the role section. Keep score details in
  `docs/score_research.md`; `program.md` should say how to use score, not teach
  all score internals.
- Do not weaken the OOS boundary. This is one of the most important protections
  against false edges.
- Do not make capacity/leverage a tunable strategy concern. Strategy can reduce
  intended exposure; it cannot change the envelope.
- Do not add more examples unless they replace prose. Examples help only if they
  shorten the prompt path.

## Suggested Implementation Order

1. Re-section `program.md` to restore upstream-compatible headings.
2. Replace the north-star paragraph.
3. Replace the target-book / causality wording.
4. Add explicit Output Format and Logging Results sections.
5. Reword the overfit "switch thesis" sentence.
6. Split the final `AGENTS.md` conflict rule.

This should be a refinement pass, not a rewrite. Target net change should be
small: fewer repeated concepts, clearer headings, and sharper high-stakes words.
