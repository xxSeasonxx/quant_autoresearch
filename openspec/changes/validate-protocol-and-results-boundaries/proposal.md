## Why

Protocol values and result rows are control inputs for the Train loop, but they currently rely on loose casts and shape-only parsing. Invalid protocol assumptions or malformed `results.tsv` rows can become false evidence or control flow.

This change hardens those two input boundaries without adding new artifact surfaces, OOS wiring, ledgers, or workflow steps for the LLM researcher.

## What Changes

- Add explicit type/range validation to `load_protocol()`.
- Add semantic validation for parsed result rows.
- Add minimal result-chain validation for duplicate/non-contiguous attempts and terminal rows.
- Remove `docs/backlog.md` and record this P1 scope in `docs/reviews/foundation-review-20260608.md` instead.
- Do not add quick-run evidence flags, OOS binding, `next_action`, databases, or broad artifact validation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `autoresearch-protocol`: protocol loading rejects invalid types and ranges before quick-run materialization.
- `autoresearch-results`: result parsing rejects malformed rows and invalid attempt chains before loop state is derived.

## Impact

- Affected source: `protocol.py`, `results_log.py`.
- Affected tests: focused protocol and result-log contract tests.
- Affected docs: remove `docs/backlog.md`; update `docs/reviews/foundation-review-20260608.md`.
- No new runtime dependencies.
- No new generated artifacts.
- No changes to the active LLM research workflow.
