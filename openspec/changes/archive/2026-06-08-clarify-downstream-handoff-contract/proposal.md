## Why

The Train loop now produces stronger attempt evidence, but the handoff from automated Train research to Season's downstream review is still under-specified. Season needs a clearer operator-facing path that improves review ergonomics without letting OOS become loop feedback.

This change clarifies the downstream handoff contract: the CLI should surface complete attempt evidence, and downstream OOS/regime decisions should live in explicit human-owned artifacts outside auto-research.

## What Changes

- Make `climb` output the complete latest attempt summary in a parseable form, not only status and score.
- Add a downstream one-look OOS drift review template that compares a frozen Train survivor to one OOS evaluation without feeding results back into the same candidate.
- Add an ADR documenting the curated-few thesis-driven regime and the trigger for heavier automated-many controls.
- Mark the foundation review's already-addressed missing-economics item as addressed.
- Keep OOS/evaluate outside `loop.py`; do not add new OOS commands or automated OOS scoring.
- Avoid scope creep: no paper/live implementation, no OOS runner integration, no DSR/PBO implementation, no new database or service.

## Capabilities

### New Capabilities

- `autoresearch-downstream-handoff`: Defines downstream human-owned artifacts for OOS drift review and curated-few regime decisions after a frozen Train survivor exists.

### Modified Capabilities

- `autoresearch-results`: Require CLI climb output to expose the same control fields as the appended result row so the agent and Season can inspect evidence without manually opening `results.tsv`.
- `autoresearch-train-loop`: Clarify that terminal Train survivor handoff points to downstream human review artifacts, not automated OOS feedback.

## Impact

- Affected source: likely `loop.py` CLI output formatting only.
- Affected docs/artifacts: new `docs/templates/oos-drift-review.md`, new ADR under `docs/adr/`, `README.md` / `program.md` wording if needed, foundation review action map statuses.
- Affected specs: new downstream handoff spec plus result/train-loop deltas.
- No new runtime dependencies.
