## Why

The remaining open cleanup items are mostly semantic and documentation hygiene: current protocol defaults need a concise rationale, the concentration metric name is ambiguous, historical docs still look too actionable, active OpenSpec tracking requires force-add, and one downstream spec still has a placeholder purpose.

This change cleans those surfaces without adding new research workflow steps, new gates, new OOS behavior, or stricter rationale parsing.

## What Changes

- Add concise comments in `protocol.toml` explaining the current symbol universe, Train window, and `K=6` subwindow default.
- Rename the current `concentration` result field to `net_return_contribution_concentration` everywhere it is emitted and documented.
- Strengthen historical-design documentation so stale implementation sketches are visibly non-contract.
- Adjust `.gitignore` so active OpenSpec config/specs and future changes can be tracked without force-add, while generated/local agent state remains ignored.
- Replace the downstream handoff spec placeholder purpose.
- Update `docs/reviews/foundation-review-20260608.md` statuses for addressed cleanup items.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `autoresearch-agent-contract`: clarify that historical design context is non-contract and should not guide implementation over active docs/specs.
- `autoresearch-objective-gates`: clarify the current breadth/concentration gate semantics as net-return contribution concentration.
- `autoresearch-results`: rename the emitted result field from `concentration` to `net_return_contribution_concentration`.
- `autoresearch-protocol`: clarify the rationale for the current default symbol universe and Train window.
- `autoresearch-downstream-handoff`: replace placeholder purpose text with the real downstream handoff purpose.

## Impact

- Affected source: `gates.py`, `loop.py`, `results_log.py`.
- Affected docs/specs/tests: `README.md`, `program.md`, `protocol.toml`, `docs/templates/oos-drift-review.md`, `docs/simplified-autoresearch-loop-design.md`, `.gitignore`, OpenSpec specs, and focused tests.
- Existing generated `results.tsv` files with the old `concentration` column are not migrated; generated results are disposable evidence.
- No new metrics, no OOS automation, no rationale parser enforcement, no new artifacts, and no change to the active research loop.
