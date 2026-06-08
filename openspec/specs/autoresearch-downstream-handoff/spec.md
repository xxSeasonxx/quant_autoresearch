# autoresearch-downstream-handoff Specification

## Purpose
Define the human-owned downstream handoff after a frozen Train survivor exists, including one-look OOS drift review, paper-test review, and small-live review boundaries.
## Requirements
### Requirement: OOS drift review is downstream and human-owned
The project SHALL provide a downstream OOS drift review template for Season to use after a frozen Train survivor exists. The auto-research loop SHALL NOT read, write, or optimize against this template.

#### Scenario: OOS template exists outside loop
- **WHEN** the repository docs are inspected
- **THEN** an OOS drift review template exists outside generated loop artifacts and outside the auto-research runtime path

#### Scenario: OOS template forbids same-candidate tuning
- **WHEN** the OOS drift review template is read
- **THEN** it states that the OOS result is a one-look downstream review and MUST NOT be used to tune the same candidate

### Requirement: OOS drift template records Train and OOS comparison fields
The downstream OOS drift review template SHALL include fields for frozen candidate identity, Train evidence, OOS evidence, drift comparison, and final human decision.

#### Scenario: template captures candidate identity
- **WHEN** the OOS drift review template is read
- **THEN** it includes fields for run id, artifact path, strategy hash, experiment hash, protocol hash, and rationale hash

#### Scenario: template captures drift comparison
- **WHEN** the OOS drift review template is read
- **THEN** it includes fields for score, trade count, net-return contribution concentration, cost-stress, and drawdown/return drift when available

### Requirement: Curated-few regime is recorded
The project SHALL record an ADR that chooses the curated-few thesis-driven research regime and defines when heavier automated-many controls are required.

#### Scenario: ADR states current regime
- **WHEN** the ADR is read
- **THEN** it states that current auto-research is one human-seeded thesis at a time with downstream OOS, paper, and small-live review

#### Scenario: ADR states escalation triggers
- **WHEN** the ADR is read
- **THEN** it lists triggers for heavier controls such as automated-many candidate generation, repeated OOS selection, or using historical validation as deployment evidence

### Requirement: Downstream artifacts stay outside active Train iteration
The downstream handoff contract SHALL state that OOS drift reviews, OOS artifacts, paper notes, and small-live notes are Season downstream-only artifacts and SHALL NOT be used as active-loop inputs for tuning the same Train candidate.

#### Scenario: OOS review is downstream-only
- **WHEN** an agent reads active docs or the OOS drift template
- **THEN** it is told that OOS review is for Season after a frozen Train survivor exists
- **AND** the auto-research loop must not read or optimize against OOS review artifacts

### Requirement: Downstream handoff spec has concrete purpose
The downstream handoff spec SHALL state its actual purpose and SHALL NOT retain placeholder purpose text.

#### Scenario: Purpose is concrete
- **WHEN** `openspec/specs/autoresearch-downstream-handoff/spec.md` is read
- **THEN** its Purpose section explains downstream OOS, paper, and small-live handoff responsibilities
- **AND** it contains no placeholder purpose text
