# autoresearch-downstream-handoff Specification

## Purpose
TBD - created by archiving change clarify-downstream-handoff-contract. Update Purpose after archive.
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
- **THEN** it includes fields for score, trade count, concentration, cost-stress, and drawdown/return drift when available

### Requirement: Curated-few regime is recorded
The project SHALL record an ADR that chooses the curated-few thesis-driven research regime and defines when heavier automated-many controls are required.

#### Scenario: ADR states current regime
- **WHEN** the ADR is read
- **THEN** it states that current auto-research is one human-seeded thesis at a time with downstream OOS, paper, and small-live review

#### Scenario: ADR states escalation triggers
- **WHEN** the ADR is read
- **THEN** it lists triggers for heavier controls such as automated-many candidate generation, repeated OOS selection, or using historical validation as deployment evidence

