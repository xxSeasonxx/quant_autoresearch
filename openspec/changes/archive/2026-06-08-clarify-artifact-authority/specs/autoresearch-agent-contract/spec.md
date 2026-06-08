## ADDED Requirements

### Requirement: Agent contract defines artifact authority
The agent contract SHALL distinguish active-loop inputs from generated audit/handoff artifacts, Season downstream-only artifacts, and historical or non-contract context.

#### Scenario: Active loop inputs are bounded
- **WHEN** an agent reads `program.md` for an active Train research run
- **THEN** it is told to use the active operating files, recent `results.tsv`, and the latest quick-run artifact directory recorded in `results.tsv` as the active loop inputs

#### Scenario: Generated handoff artifacts are not routine loop inputs
- **WHEN** an agent reads `program.md` for an active Train research run
- **THEN** it is told that thesis locks, snapshots, and terminal manifests are generated audit or handoff artifacts rather than routine inputs for choosing Train edits

#### Scenario: Historical context is not operating contract
- **WHEN** an agent reads active docs
- **THEN** it is told not to browse the rest of the repo during ordinary Train iteration unless debugging a failure, checking an explicitly in-scope contract, or Season asks
