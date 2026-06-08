## ADDED Requirements

### Requirement: Protocol loading rejects invalid values
The protocol loader SHALL reject invalid protocol field types and ranges before quick-run config materialization.

#### Scenario: Invalid numeric protocol values fail
- **WHEN** a protocol file contains non-finite, boolean, negative, or zero values for fields whose contract requires finite positive or nonnegative numeric values
- **THEN** loading the protocol fails with a clear `ValueError`

#### Scenario: Invalid gate concentration fails
- **WHEN** `gates.max_symbol_concentration` is outside the inclusive range `[0, 1]`
- **THEN** loading the protocol fails with a clear `ValueError`

#### Scenario: Empty symbol universe fails
- **WHEN** `data.symbols` is empty
- **THEN** loading the protocol fails with a clear `ValueError`

#### Scenario: Invalid boolean protocol values fail
- **WHEN** a protocol boolean field is not a TOML boolean
- **THEN** loading the protocol fails with a clear `ValueError`
