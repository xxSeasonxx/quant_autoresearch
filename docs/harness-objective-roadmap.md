# Harness Process Roadmap

Active roadmap for process improvements around thesis setup, protocol ownership,
evidence flow, and lifecycle hygiene. This is not a strategy-improvement plan.
Strategy variants belong in `rationale.md` during a thesis run.

## Current Baseline

The money-first Train objective is the current scoring contract:

- `objective.kind = "return_lcb_subwindow"`;
- score = weakest-window deployed annualized return lower bound;
- PSR, Sharpe, Calmar, win rate, and trade-bag stats are diagnostics only;
- the deflated money floor, cost-stress return retention, path risk, breadth,
  sample/trade coverage, causality admissibility, and complexity are binary gates;
- upstream risk-budget sizing owns book scale through `[risk_budget]`;
- strategy code owns target-book shape, not a global weight knob;
- `results.tsv` is compact, and each attempt's `run_card.json` owns detailed
  vectors, gates, sizing, causality evidence, and failure mode;
- Train micro causality is a bounded score-admissibility check, not retention,
  paper-trade, or deployability proof.
- New-thesis onboarding is owned by the root `new-strategy.md` guide and the
  deterministic `propose-protocol` / `baseline` CLI boundary. The proposal CLI
  writes review artifacts only; baseline requires an approved proposal hash and
  refuses to run when active lifecycle state already exists.
- The optional `resolve-universe` CLI resolves a pre-baseline, return-blind
  symbol list from `quant_data.catalog` and `quant_data.readiness` metadata. The
  resolver writes `.autoresearch/universe/` artifacts and never edits
  `protocol.toml` or inspects Train results.

## Open Work

### Universe Provenance In Lifecycle Artifacts

Attach the approved universe artifact identity to lifecycle state after Season
approves a resolver-backed protocol. The protocol still owns the actual Train
symbol list; the resolver artifact explains how that list was chosen before any
Train result existed.

The thesis lock and attempt artifacts should record the resolved list, rule
config, data snapshot identity, resolver hash, and exclusions.

Done when:

- resolver-backed lifecycles preserve universe artifact identity;
- stale or mismatching universe provenance fails closed;
- terminal manifests include the approved universe source;
- a universe change requires a fresh lifecycle.

### Lifecycle Reseed Flow

Make reseeding explicit when protocol-owned assumptions change. A reseed should
archive or preserve prior generated evidence, clear active lifecycle state, create
a fresh thesis lock, and start a new results ledger. It must not mutate an active
run into a new universe or protocol while preserving the old attempt chain.

Done when:

- a documented reseed command or checklist exists;
- stale `results.tsv` and `.autoresearch/thesis_lock.json` states fail closed;
- the new lifecycle records the approved protocol, bounds, thesis, universe, and
  mandate hashes;
- the handoff tells Season whether the prior lifecycle died by money floor,
  capacity, data, causality, complexity, plateau, or max iterations.

### Setup Documentation Coverage

Keep new-thesis setup, loop operation, scoring, roadmap, and history in their
owning documents: `new-strategy.md`, `program.md`, `docs/score_research.md`,
this roadmap, and `HISTORY.md`.

Done when:

- a new session can start a thesis without reading chat history;
- each durable rule has one owning active document;
- active docs contain no completed task timelines or stale review dispositions;
- README points to the correct owner for setup, scoring, loop operation, and
  roadmap state.

### Process Handoff

When a run stops, emit or document a compact handoff that separates Train verdict
from downstream evidence. It should name the terminal condition, best kept attempt
if any, primary failure mode, score/gate summary, artifact paths, and the next
allowed process move: continue current thesis, reseed, kill thesis, or hand off
to Season for downstream review.

Done when:

- terminal artifacts distinguish terminal attempt and best survivor;
- no handoff language claims Train evidence is paper/live deployability proof;
- downstream OOS, paper, and small-live notes are outside the Train ledger and
  cannot feed back into the same thesis lifecycle.

## Guardrails

- Do not switch Train iteration to strict or focused causality replay; keep micro
  replay bounded for score admissibility and leave stronger retention proof to
  downstream review.
- Do not lower the money floor, acceptance haircut, cost-stress gate, or evidence
  gates to make the current 3-symbol sleeve pass.
- Do not add strategy alpha work to this roadmap; use it only for harness process,
  protocol, lifecycle, and documentation improvements.
- Do not create compatibility modes for old PSR-scored ledgers. Start a new
  lifecycle when the schema or protocol changes.
