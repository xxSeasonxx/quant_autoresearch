## ADDED Requirements

### Requirement: Downstream artifacts stay outside active Train iteration
The downstream handoff contract SHALL state that OOS drift reviews, OOS artifacts, paper notes, and small-live notes are Season downstream-only artifacts and SHALL NOT be used as active-loop inputs for tuning the same Train candidate.

#### Scenario: OOS review is downstream-only
- **WHEN** an agent reads active docs or the OOS drift template
- **THEN** it is told that OOS review is for Season after a frozen Train survivor exists
- **AND** the auto-research loop must not read or optimize against OOS review artifacts
