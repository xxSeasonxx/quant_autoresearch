## MODIFIED Requirements

### Requirement: Complexity cap limits declared components and params
The complexity gate SHALL fail when the candidate exceeds the configured maximum rationale-declared signal components or validated bounded params. Signal components SHALL be derived from `rationale.md` component headings for ordinary loop execution.

#### Scenario: complexity cap fails
- **WHEN** a candidate has more rationale-declared components or validated bounded params than allowed
- **THEN** the complexity gate fails

#### Scenario: component count comes from rationale
- **WHEN** ordinary loop execution evaluates gates
- **THEN** the component count used by the complexity gate comes from `rationale.md` `### Component:` headings

#### Scenario: missing component declarations fail before run
- **WHEN** `rationale.md` has no declared signal components for an ordinary thesis run
- **THEN** the loop rejects the attempt before quick-run materialization

## ADDED Requirements

### Requirement: Rationale component declarations are parsed deterministically
The loop SHALL parse signal component declarations from `rationale.md` using only `### Component: <name>` headings under the `## Signal Components` section.

#### Scenario: declared components are returned
- **WHEN** `rationale.md` contains multiple `### Component: <name>` headings under `## Signal Components`
- **THEN** the parser returns those component names in document order

#### Scenario: duplicate components fail
- **WHEN** `rationale.md` declares duplicate component names after normalization
- **THEN** the parser rejects the rationale before quick-run materialization

#### Scenario: unrelated headings are ignored
- **WHEN** `rationale.md` contains `### Variant:` or other headings outside `## Signal Components`
- **THEN** those headings are not counted as signal components
