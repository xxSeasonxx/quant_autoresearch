## 1. Objective And Gate Evidence

- [x] 1.1 Extend objective results to expose subwindow trade counts aligned with subwindow scores.
- [x] 1.2 Add `min_trades_per_subwindow` to protocol/gate configuration loading.
- [x] 1.3 Add `subwindow_coverage` as a binary gate in `evaluate_gates`.
- [x] 1.4 Add tests proving aggregate trade floor can pass while clustered trades fail subwindow coverage.
- [x] 1.5 Update score wording in docs/tests from Sharpe-like language to trade-unit robustness where applicable.

## 2. Attempt Provenance

- [x] 2.1 Define the candidate snapshot fields used for attempt identity: run id, artifact dir, dirty flag, and source/config hashes.
- [x] 2.2 Add deterministic hash helpers for `strategy.py`, `experiment.toml`, `protocol.toml`, `rationale.md`, and materialized quick-run config.
- [x] 2.3 Extend `ResultRow` header, serialization, and parsing with provenance fields and subwindow trade counts.
- [x] 2.4 Add tests that appended rows include artifact path, dirty flag, hashes, and subwindow trade counts.
- [x] 2.5 Decide and implement legacy `results.tsv` behavior: clear error or explicit legacy-row handling.

## 3. Lifecycle State

- [x] 3.1 Add a state derivation boundary that reads protocol, current candidate snapshot, and prior result rows.
- [x] 3.2 Compute best kept attempt, working snapshot identity, non-improving count since best, terminal stop reason, best status, and continuation state.
- [x] 3.3 Refuse new climb attempts when terminal stop is already recorded.
- [x] 3.4 Allow ordinary discarded attempts to continue from the working snapshot while leaving the best kept attempt unchanged.
- [x] 3.5 Refuse new climb attempts only when continuation is terminal or the workspace is marked invalid/repair-required.

## 4. Terminal Manifests

- [x] 4.1 Choose the generated manifest location for Train survivor/failure records.
- [x] 4.2 Write a Train survivor manifest at terminal stop when a kept candidate clears all Train gates.
- [x] 4.3 Write a Train failure manifest at terminal stop when no valid survivor exists.
- [x] 4.4 Include not-deployability-evidence language and attempt provenance in terminal manifests.
- [x] 4.5 Add tests for plateau, max-iteration, and baseline-failure terminal manifest behavior.

## 5. CLI And Documentation

- [x] 5.1 Update `climb` output to show the full result-row summary, including gates, counts, provenance, best status, continuation state, and stop reason.
- [x] 5.2 Update `status` output to show terminal stop state, best kept attempt, and whether continuation is currently allowed.
- [x] 5.3 Update `program.md` and `README.md` to describe the hardened attempt contract without adding OOS feedback to the loop.
- [x] 5.4 Update `docs/reviews/foundation-review-20260607.md` action map statuses for addressed P0 items after implementation.

## 6. Verification

- [x] 6.1 Run focused tests for objective/gates, protocol loading, results logging, and loop lifecycle.
- [x] 6.2 Run `conda run -n quant python -m pytest -q`.
- [x] 6.3 Run `conda run -n quant python -m ruff check .`.
- [x] 6.4 Run `conda run -n quant python -m mypy .` or document remaining type-boundary gaps if outside this change. Mypy still fails on existing untyped upstream/strategy/test-protocol boundaries.
- [x] 6.5 Run `conda run -n quant python -m loop status` to verify CLI status remains usable.
