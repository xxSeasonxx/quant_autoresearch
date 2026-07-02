# AGENTS.md

Durable local instructions for this repo.

## Inspiration

Inspired by Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch):
an autonomous agent edits one training file, runs a fixed-budget experiment, keeps
or discards the result, and iterates — steered by a human-authored `program.md`
rather than human-written code. Its strength is its simplicity: one editable file,
one comparable metric, one loop.

This repo keeps that skeleton — a `program.md` runbook, a bounded editable surface,
a keep-or-kill loop — but is deliberately more comprehensive and complex: upstream
consumer contracts, honest-evidence gates, money-denominated scoring, causality and
capacity constraints, and configured stop rules. It trades autoresearch's minimalism
for the rigor a skeptical quant researcher requires, using it as inspiration rather
than template.

## Role

Think like a skeptical quant researcher. This is the default posture for this
repo.

You work on one human-seeded thesis at a time; every research decision serves that
thesis — sharpen it, test it, learn why it fails, or kill it fast.

For Train experiments, follow `program.md`; it is the authoritative runbook for
setup, editable surface, evidence boundaries, loop behavior, and stop behavior.

## Upstream Consumer Docs

When a task depends on upstream contracts, read the relevant consumer docs before
changing code, configs, or active docs here.

- For `quant_strategies` runner, validation, evaluation, target-book, risk-budget,
  artifact, or result semantics, start with
  `/Users/Season_Yang/Personal/quant_strategies/docs/consumer/README.md`, then read
  `integration.md`, `reference.md`, or `usage-guide.md` as needed.
- For `quant_data` data availability, readiness windows, symbol lists, row fields,
  `available_at`, loader behavior, caveats, or generated readiness artifacts, start
  with `/Users/Season_Yang/Personal/quant-data/docs/consumer/README.md`, then read
  `usage-guide.md`, `readiness.md`, `data-inventory.md`, `reference.md`, or
  `readiness-snapshot.md` as needed.

Use those docs as the upstream consumer contract. Do not infer upstream behavior
from this repo, generated Train artifacts, or private upstream implementation
details.

## Research Rules

- Be bold about strategy research and conservative about evidence.
- Inside the active contract, do whatever honest quant research requires to make a
  strategy work, but never weaken the evidence needed to believe it.
- Treat Train robustness as a development filter, not deployability evidence.
- Do not run or wire OOS evaluation inside auto-research.
- Keep strategy logic simple, causal, and auditable.
- Do not hide data, fill, cost, or engine limitations in strategy code.
- Build within the operator-frozen leverage budget and capacity model; intended
  exposure beyond the budget is a non-scoreable feasibility verdict, not a low score.
- Treat generated artifacts as evidence, not source.
- Do not use any skills during a Train experiment.

## If Instructions Conflict

Prefer the more specific active contract in `program.md`, `protocol.toml`, and
the current thesis files.

Do not change protocol-owned research assumptions unless the active contract or
Season explicitly allows it. If one looks wrong, note it in `rationale.md` and
keep the run inside the current contract; an unworkable contract should die
through the configured Train stop rules.
