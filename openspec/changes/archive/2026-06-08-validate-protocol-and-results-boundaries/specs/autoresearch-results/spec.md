## ADDED Requirements

### Requirement: Result rows validate field semantics
The result log reader SHALL reject malformed result rows before returning `ResultRow` objects to loop state derivation.

#### Scenario: Invalid lifecycle enum fails
- **WHEN** a result row contains an unsupported `status`, `best_status`, or `continuation` value
- **THEN** reading results fails with a clear `ValueError`

#### Scenario: Invalid boolean text fails
- **WHEN** a result row boolean field is not exactly `true` or `false`
- **THEN** reading results fails with a clear `ValueError`

#### Scenario: Invalid hash text fails
- **WHEN** a result row hash field is neither a 64-character lowercase hexadecimal hash nor the explicit `missing` marker
- **THEN** reading results fails with a clear `ValueError`

### Requirement: Result chains validate attempt order
The result log reader SHALL reject result chains with duplicate run ids, duplicate iterations, non-contiguous iterations, or terminal continuation before the final row.

#### Scenario: Duplicate or non-contiguous attempts fail
- **WHEN** a `results.tsv` file has duplicate run ids, duplicate iterations, or skips an iteration number
- **THEN** reading results fails with a clear `ValueError`

#### Scenario: Terminal row before final row fails
- **WHEN** a row with `continuation=terminal` is followed by another result row
- **THEN** reading results fails with a clear `ValueError`
