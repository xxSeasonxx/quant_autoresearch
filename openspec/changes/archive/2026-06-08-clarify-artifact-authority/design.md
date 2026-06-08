## Context

The P0 identity work made generated Train artifacts more trustworthy. That also increases the number of artifacts a future LLM might notice: thesis locks, snapshots, terminal manifests, OOS templates, archived OpenSpec changes, reviews, and historical design docs.

The root issue is not missing data. It is authority confusion: agents need to know which artifacts drive active Train research and which artifacts exist for audit, handoff, or Season downstream review.

## Goals / Non-Goals

**Goals:**

- Define a simple artifact authority map in active docs.
- Keep the active LLM research loop focused on a small input set.
- Preserve downstream OOS as Season-owned and out of loop.
- Record the deferred P1 hardening queue without adding runtime behavior.

**Non-Goals:**

- No source code behavior changes.
- No new generated artifact types.
- No automated OOS/evaluation integration.
- No result ledger, database, or evidence-quality expansion.
- No redesign of `results.tsv`, terminal manifests, snapshots, or OpenSpec.

## Decisions

### Decision 1: Put the authority map in active docs

`program.md` is the agent operating contract; `README.md` is the human/agent orientation map. Both should contain the artifact authority hierarchy. Review docs and historical design docs should not be the primary place future agents learn what to read.

### Decision 2: Keep categories operational, not exhaustive

Use four categories:

- active loop inputs;
- generated audit/handoff artifacts;
- Season downstream-only artifacts;
- historical/non-contract context.

This tells the agent what to do without creating a comprehensive artifact taxonomy.

### Decision 3: Backlog the next P1 code hardening separately

The next code hardening is protocol validation plus minimal result-row semantic validation. This change records that queue, but does not implement it, to avoid bundling docs authority with code behavior.

## Risks / Trade-offs

- Too much doc text can become another artifact burden -> mitigation: keep the authority map short and action-oriented.
- Agents may still inspect generated artifacts when debugging -> mitigation: allow latest quick-run diagnostics during Train iteration, but mark terminal/OOS/review artifacts as non-loop inputs.
- Deferred P1 items may be forgotten -> mitigation: add a small backlog note with explicit scope and avoids.
