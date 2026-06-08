## Why

`mypy .` still fails after the evidence and editable-surface contract work, so the type checker is not yet a useful local gate. The remaining failures are local boundary issues plus untyped `quant_strategies` imports.

This change makes `mypy .` pass locally without expanding architecture or changing strategy behavior.

## What Changes

- Add narrow mypy configuration for untyped `quant_strategies.*` imports only.
- Tighten local strategy param typing in `strategy.py`.
- Fix local `tests/test_protocol.py` object-indexing type issues.
- Mark the foundation-review P3 type-boundary item addressed after verification.
- Do not modify `quant_strategies`, add vendored stubs, or broaden ignores.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `autoresearch-agent-contract`: local project checks include a passing mypy gate, with untyped upstream imports handled explicitly.

## Impact

- Affected files: `pyproject.toml`, `strategy.py`, `tests/test_protocol.py`, and `docs/reviews/foundation-review-20260607.md`.
- No runtime behavior change is intended.
