## Context

The prior P0 changes made candidate identity and thesis locks explicit. The remaining P1 root-boundary risks are simpler:

- `protocol.toml` is trusted but is parsed through direct casts;
- `results.tsv` is used for state but row values are parsed loosely.

Both boundaries can be hardened locally without changing the research loop.

## Goals / Non-Goals

**Goals:**

- Fail fast on invalid protocol values before a quick run is materialized.
- Fail fast on malformed result rows before best/stop state is derived.
- Keep validators small and local to existing modules.
- Keep the LLM research workflow unchanged.

**Non-Goals:**

- No Pydantic or schema framework migration.
- No OOS artifact changes.
- No quick-run evidence flag expansion.
- No artifact existence audit or repair tool.
- No ledger/database.
- No `next_action` changes.

## Decisions

### Decision 1: Validate protocol in `protocol.py`

Protocol loading already centralizes config parsing, so validation should happen there. This keeps invalid assumptions from reaching quick-run config materialization.

The validators should cover concrete invariants: real booleans, finite numbers, non-empty symbol universe, positive loop counts, nonnegative costs/thresholds, valid concentration bounds, and supported objective/fill shapes already implied by current code.

### Decision 2: Validate result rows in `results_log.py`

`read_results()` is the boundary where TSV text becomes loop state. Row-level validation should happen in `_parse_row()`, and sequence-level validation should happen once per `read_results()` call.

The chain validator should be intentionally small: unique/contiguous iterations and run ids, terminal continuation only on the final row, and enum/boolean/hash semantics.

### Decision 3: Do not validate generated artifact existence

Generated artifacts may be moved, cleaned, or regenerated. This change only protects active loop state from malformed rows. Artifact existence belongs to a separate audit/handoff check if needed later.

## Risks / Trade-offs

- Stricter parsers may reject hand-edited rows that previously loaded -> mitigation: reject with clear errors rather than silently deriving state from malformed evidence.
- Some future protocols may want same-bar fills or negative costs for special simulations -> mitigation: those should be explicit future protocol changes, not accepted silently now.
- More validation code can grow into a framework -> mitigation: keep helpers local and only validate fields that already drive loop behavior.
