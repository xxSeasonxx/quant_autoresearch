## Why

The current agent-editable surface is conceptually narrow, but two important parts are still procedural: `experiment.toml` declares bounds that the backend does not enforce, and `rationale.md` declares signal components that the complexity gate does not derive. This weakens the root contract that lets the LLM explore freely while the backend keeps the search bounded, auditable, and simple.

This change makes the editable surface real without adding restrictive strategy logic inspection or extra process layers.

## What Changes

- Introduce an explicit experiment contract: `[params]` are the values passed to `run_config`, `[bounds.*]` are the admissible operator-defined ranges, and params must validate against bounds before quick-run materialization.
- Derive declared signal components from `rationale.md` instead of trusting the caller-provided default component list.
- Feed rationale-derived component counts into the existing complexity cap gate.
- Keep the agent free to try thesis-guided strategy variants; the backend only enforces declared bounds, component accounting, and evidence language.
- Mark the simplified design discussion as historical/currently superseded where it no longer represents live behavior.
- Normalize active wording so the score is described as trade-unit robustness, not Sharpe or deployability evidence.
- Avoid layered fixes: no AST component detector, no separate component registry file, no sidecar bounds file, no new runtime manifest.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `autoresearch-agent-contract`: clarify that the agent may explore freely inside bounded params and strategy logic, but must keep `rationale.md` current for materially changed signal components; mark active vs historical docs clearly.
- `autoresearch-protocol`: require experiment params to be loaded with bounds and validated before quick-run configs are materialized.
- `autoresearch-objective-gates`: require the complexity cap to use validated params and rationale-derived signal components rather than caller-trusted component defaults.

## Impact

- Affected source: `protocol.py`, `gates.py`, `loop.py`, and possibly a small rationale parsing helper if that keeps responsibilities clearer.
- Affected configs/docs: `experiment.toml`, `rationale.md`, `program.md`, `README.md`, `docs/simplified-autoresearch-loop-design.md`.
- Affected tests: protocol/experiment loading, loop complexity behavior, objective/gates, program contract, and possibly mypy boundary cleanup if the typed experiment contract resolves local errors.
- No new dependency is expected.
