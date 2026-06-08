## 1. Regression Tests

- [x] 1.1 Add protocol tests for invalid numeric ranges, invalid concentration, empty symbols, and invalid booleans.
- [x] 1.2 Add result-row tests for invalid lifecycle enums, invalid booleans, invalid hashes, duplicate/non-contiguous attempts, and terminal-not-last rows.

## 2. Protocol Boundary

- [x] 2.1 Add small local validators in `protocol.py` for strict booleans, numeric types, and numeric ranges.
- [x] 2.2 Apply validators in `load_protocol()` without changing the public dataclass shape or quick-run config shape.

## 3. Results Boundary

- [x] 3.1 Add semantic row parsing helpers in `results_log.py`.
- [x] 3.2 Add minimal result-chain validation in `read_results()`.

## 4. Docs Cleanup

- [x] 4.1 Remove `docs/backlog.md`.
- [x] 4.2 Update `docs/reviews/foundation-review-20260608.md` so the deferred P1 note lives there instead of in a separate backlog doc.

## 5. Verification

- [x] 5.1 Run focused protocol and result-log tests.
- [x] 5.2 Run full pytest, mypy, ruff, and OpenSpec validation.
