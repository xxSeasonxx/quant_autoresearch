## Context

The core Train loop has been hardened. The remaining selected cleanup work is about contract clarity: terms should say exactly what they mean, historical docs should not look actionable, and active OpenSpec files should be trackable without force-add.

## Goals / Non-Goals

**Goals:**

- Make the current concentration metric's meaning explicit.
- Add concise current-protocol rationale for Season-owned symbol/window choices.
- Reduce stale-document and OpenSpec tracking confusion.
- Update review status so cleanup items are no longer ambiguous.

**Non-Goals:**

- No new gates, objectives, or metrics.
- No exposure, notional, or trade-count breadth metrics.
- No OOS process change.
- No rationale parser strictness.
- No `next_action` CLI behavior.
- No broad OpenSpec reorganization.

## Decisions

### Decision 1: Rename, do not add, concentration semantics

The current metric is useful but ambiguous. Rename the field to `net_return_contribution_concentration` and keep the calculation unchanged.

### Decision 2: Keep protocol rationale as comments

Current symbol/window rationale should live near the protocol values. Do not add thesis-lock fields or new validation for rationale text.

### Decision 3: Track active OpenSpec surfaces without unignoring local archives wholesale

`.gitignore` should allow active `openspec/config.yaml`, `openspec/specs/**`, and current/future `openspec/changes/**` to be tracked. Local old archive leftovers can remain untracked unless explicitly force-added.

### Decision 4: Quarantine historical design text, not rewrite it into active design

The historical design doc can retain background, but its stale implementation sketch should be clearly labeled as non-contract. Avoid rewriting old planning history into new specs.

## Risks / Trade-offs

- Renaming `results.tsv` columns can break old generated rows -> acceptable because generated rows are disposable; no migration.
- Long metric name is verbose -> accepted for semantic clarity.
- Unignoring OpenSpec may surface old local archive directories -> mitigate by keeping already-untracked old archive leftovers ignored or explicitly not staging them.
