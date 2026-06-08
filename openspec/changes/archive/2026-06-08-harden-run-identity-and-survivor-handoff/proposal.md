## Why

The Train loop now records per-attempt provenance, but the terminal handoff and continuation rules can still mix identities: a terminal survivor can snapshot the current workspace instead of the best kept attempt, and a continuing run can compare scores across changed protocol/thesis/bounds assumptions.

This change fixes those two P0 evidence-integrity defects without adding broader research governance, automated OOS, or a candidate ledger.

## What Changes

- Add exact per-attempt source snapshots for the files that define a candidate: strategy, experiment, protocol, rationale, and materialized quick-run config.
- Change terminal manifests so they distinguish the terminal attempt from the best kept Train survivor, and so survivor snapshots come from the best kept attempt rather than the current workspace.
- Add a small active thesis lock that records run identity and immutable setup hashes once a thesis starts.
- Reject ordinary continuation when the current thesis identity, protocol, or experiment bounds drift from the active thesis lock.
- Keep the LLM-facing workflow unchanged: agents still edit `strategy.py`, bounded `[params]`, and `rationale.md`; no OOS or downstream evaluation is added to the loop.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `autoresearch-train-loop`: terminal handoff must snapshot the best kept survivor accurately, and ordinary continuation must be blocked when active thesis identity drifts.
- `autoresearch-results`: result artifacts must preserve per-attempt source snapshots and enough lock identity to connect attempts to one thesis lifecycle.
- `autoresearch-protocol`: protocol and experiment bounds must be frozen for the active thesis once attempts begin.

## Impact

- Affected source: `loop.py`, `results_log.py` if a row field is needed, and focused tests under `tests/`.
- Affected generated artifacts: `.autoresearch/` thesis lock and per-attempt snapshots under generated attempt artifact directories.
- No new runtime dependencies.
- No changes to `quant_strategies` public API usage.
- No automated OOS/evaluation wiring.
