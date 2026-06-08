## ADDED Requirements

### Requirement: Breadth gate names net-return contribution concentration explicitly
The breadth gate SHALL identify the current concentration metric as net-return contribution concentration when exposing gate details, result fields, and documentation.

#### Scenario: Result label is unambiguous
- **WHEN** a run emits or documents the concentration metric
- **THEN** the metric is labeled `net_return_contribution_concentration`
- **AND** no new breadth, exposure, or trade-count metric is introduced
