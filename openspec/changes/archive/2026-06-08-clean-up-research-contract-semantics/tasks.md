## 1. Contract Tests

- [x] 1.1 Add/update tests for the explicit concentration field name in result rows and docs.
- [x] 1.2 Add/update tests for protocol symbol/window/subwindow rationale comments.
- [x] 1.3 Add/update tests for historical design non-contract wording and downstream handoff spec purpose.

## 2. Concentration Semantics

- [x] 2.1 Rename result field `concentration` to `net_return_contribution_concentration`.
- [x] 2.2 Preserve the existing concentration calculation and gate behavior.
- [x] 2.3 Update README, program, OOS template, result-log tests, and loop tests for the explicit label.

## 3. Documentation Hygiene

- [x] 3.1 Add concise protocol rationale comments for symbols, Train window, and `K=6`.
- [x] 3.2 Strengthen historical design document non-contract language around stale implementation sketches.
- [x] 3.3 Replace downstream handoff spec placeholder purpose.
- [x] 3.4 Update `docs/reviews/foundation-review-20260608.md` statuses for addressed cleanup items.

## 4. OpenSpec Tracking Hygiene

- [x] 4.1 Adjust `.gitignore` so active OpenSpec specs/config/changes can be tracked without force-add while local agent state remains ignored.
- [x] 4.2 Verify old untracked archive leftovers are not accidentally staged.

## 5. Verification

- [x] 5.1 Run focused tests for docs/results contract changes.
- [x] 5.2 Run full pytest, mypy, ruff, and OpenSpec validation.
