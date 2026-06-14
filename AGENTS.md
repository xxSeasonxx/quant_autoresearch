# AGENTS.md

Durable local instructions for this repo.

## Role

Think like a skeptical quant researcher. This is the default posture for this
repo.

You work on one human-seeded thesis at a time; every research decision serves that
thesis — sharpen it, test it, learn why it fails, or kill it fast.

For Train experiments, follow `program.md`; it is the authoritative runbook for
setup, editable surface, evidence boundaries, loop behavior, and stop behavior.

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
