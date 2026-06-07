## Why

The current Train loop has the right narrow shape, but the core attempt evidence is not yet a single explicit contract: empty Train subwindows can count as acceptable robustness, result rows do not identify the exact candidate/protocol/artifact snapshot, and stop/freeze/revert lifecycle state is partly left to the agent's memory.

This change hardens the root Train evidence contract so an LLM can keep iterating on strategy development without mistaking stale, sparse, or procedurally interpreted evidence for a valid Train survivor.

## What Changes

- Introduce an explicit attempt contract tying candidate identity, protocol identity, run artifact identity, Train evidence validity, and lifecycle decision into one append-only result row.
- Add protocol-owned subwindow coverage requirements so `worst_subwindow` cannot treat missing time slices as acceptable robustness evidence.
- Make loop lifecycle decisions explicit: only kept attempts update the best handoff candidate, discarded attempts may remain the working base for further thesis-guided exploration, terminal stops refuse further runs, and generated Train handoff/failure manifests summarize the result.
- Extend result logging with provenance fields: run id, artifact directory, dirty-worktree flag, and hashes for the strategy, params/experiment, protocol, rationale, and materialized quick-run config.
- Keep OOS/evaluate outside auto-research. This change does not add downstream OOS drift scoring to the loop.
- Avoid layered sidecar fixes: no separate provenance log, no warning-only subwindow monitor, no after-the-fact stop-rule checker.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `autoresearch-objective-gates`: add protocol-owned subwindow coverage as a binary Train gate and clarify that missing subwindow evidence is not robustness.
- `autoresearch-results`: extend `results.tsv` to identify the exact candidate/protocol/artifact snapshot for each attempt.
- `autoresearch-train-loop`: make lifecycle stop/handoff decisions an executable part of the loop contract.
- `autoresearch-protocol`: add protocol-owned subwindow coverage configuration while preserving the Train-only/OOS-free protocol boundary.

## Impact

- Affected source: `objective.py`, `gates.py`, `protocol.py`, `results_log.py`, `loop.py`.
- Affected configs: `protocol.toml`.
- Affected docs/tests: `program.md`, `README.md`, relevant OpenSpec specs, loop/gate/results/protocol tests.
- Generated artifacts remain under `.autoresearch/`, `results/`, and `results.tsv`.
- No new runtime dependency is expected.
