## Why

The repo now has active operating docs, generated Train evidence, downstream OOS templates, reviews, and archived OpenSpec changes. Without an explicit authority map, an LLM researcher can over-read audit or downstream artifacts and blur the Train-only research loop.

This change clarifies which artifacts are active-loop inputs, which are generated handoff/audit evidence, which are Season downstream-only, and which are historical/non-contract, without adding new runtime behavior.

## What Changes

- Add an artifact authority section to `README.md` and `program.md`.
- Make clear that active LLM research should read only the small operating set plus recent `results.tsv` and latest quick-run diagnostics.
- Mark terminal manifests, snapshots, and thesis locks as generated audit/handoff evidence, not active-loop research inputs.
- Mark OOS drift review artifacts as Season downstream-only and not part of Train iteration.
- Add a small backlog note for deferred P1 hardening: protocol validation and minimal result-row semantic validation.
- Add focused docs tests so future edits preserve the artifact authority boundary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `autoresearch-agent-contract`: clarify active-loop inputs and explicitly exclude audit, downstream, historical, and archived artifacts from routine agent reading during Train research.
- `autoresearch-downstream-handoff`: clarify that OOS drift review and terminal handoff artifacts are downstream/audit artifacts, not active-loop inputs.

## Impact

- Affected docs: `README.md`, `program.md`, and a small backlog note.
- Affected tests: focused docs contract tests.
- No source behavior changes.
- No new generated artifact types.
- No automated OOS/evaluation wiring.
