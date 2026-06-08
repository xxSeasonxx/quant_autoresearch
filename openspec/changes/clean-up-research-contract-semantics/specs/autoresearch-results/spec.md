## ADDED Requirements

### Requirement: Results use explicit concentration field name
The result log SHALL use `net_return_contribution_concentration` for the current symbol concentration value, preserving the existing calculation and avoiding ambiguous `concentration` labels.

#### Scenario: Result header names net-return contribution concentration
- **WHEN** a result row is written
- **THEN** the header includes `net_return_contribution_concentration`
- **AND** the header does not include the ambiguous `concentration` field
