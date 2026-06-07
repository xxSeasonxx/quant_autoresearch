## MODIFIED Requirements

### Requirement: Protocol owns Train data and execution assumptions
The protocol SHALL define the fixed Train data configuration, symbols, cost model, fill model, objective choice, gate thresholds, subwindow evidence coverage threshold, and loop settings. These values SHALL be loaded from read-only operator config and SHALL NOT be overridden by strategy params.

#### Scenario: params cannot override protocol fields
- **WHEN** params contain keys that resemble data, cost, fill, objective, gate, subwindow coverage, or loop fields
- **THEN** materialized quick-run configs use protocol values for those fields and put params only under strategy params

## ADDED Requirements

### Requirement: Protocol owns subwindow coverage
The protocol SHALL expose the minimum completed trade count required per configured objective subwindow as an operator-owned gate setting.

#### Scenario: subwindow coverage loads from config
- **WHEN** a protocol file defines `gates.min_trades_per_subwindow`
- **THEN** the gate configuration uses that value for subwindow coverage checks

#### Scenario: agent params cannot change subwindow coverage
- **WHEN** strategy params contain `min_trades_per_subwindow` or similar coverage keys
- **THEN** the loop still uses the protocol-owned subwindow coverage value
