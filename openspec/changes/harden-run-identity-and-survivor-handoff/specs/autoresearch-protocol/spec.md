## ADDED Requirements

### Requirement: Active thesis lock freezes protocol and bounds
The first ordinary thesis attempt SHALL create a generated active thesis lock that records the current protocol hash and the current experiment bounds hash. Later attempts in the same thesis lifecycle SHALL reject protocol or bounds drift before quick-run materialization.

#### Scenario: Protocol hash drift is rejected
- **WHEN** prior thesis state exists and the current protocol hash differs from the active thesis lock
- **THEN** the loop rejects the attempt before quick-run materialization
- **AND** the rejection explains that Season must start a new thesis lifecycle for protocol changes

#### Scenario: Bounds hash drift is rejected
- **WHEN** prior thesis state exists and the current experiment bounds hash differs from the active thesis lock
- **THEN** the loop rejects the attempt before quick-run materialization
- **AND** ordinary param value changes within unchanged bounds remain allowed

#### Scenario: Missing lock is created on first attempt
- **WHEN** no active thesis lock exists and no prior result rows exist
- **THEN** the loop creates an active thesis lock from the current thesis text, protocol hash, bounds hash, and results path before running the first attempt
