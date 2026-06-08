## Purpose

Define the Train robustness objective and binary gates used to decide whether an attempt can update the best Train survivor.
## Requirements
### Requirement: Objectives are selected by read-only protocol
The loop SHALL choose the Train robustness objective from protocol config. The agent SHALL NOT choose, change, or retry objective kinds during a thesis run.

#### Scenario: objective kind comes from protocol
- **WHEN** the protocol specifies `objective.kind`
- **THEN** the loop uses that objective implementation for all iterations in the thesis

### Requirement: worst_subwindow scores configured Train slices
The default `worst_subwindow` objective SHALL split Train into `K` configured contiguous subwindows and score the minimum after-cost trade-unit robustness value across those subwindows. The objective SHALL expose subwindow scores and subwindow trade counts so gates can distinguish poor evidence from missing evidence. A candidate with no valid subwindow score SHALL be infeasible.

#### Scenario: worst subwindow is binding
- **WHEN** one Train subwindow has a lower after-cost score than the others
- **THEN** the objective score equals that lowest subwindow score

#### Scenario: K comes from protocol
- **WHEN** the protocol sets `objective.subwindows`
- **THEN** the objective uses that value as `K`

#### Scenario: subwindow trade counts are exposed
- **WHEN** the objective scores a candidate across `K` subwindows
- **THEN** the objective exposes exactly `K` subwindow trade counts aligned with the subwindow scores

### Requirement: Plateau improvement is mathematically defined
For completed iteration `t`, let `s_t` be its score and `b_t` be the best kept feasible score before `t`. The iteration SHALL count as an improvement only if all gates pass and `s_t > b_t + max(eps, rho * max(1, abs(b_t)))`, where `eps` and `rho` come from protocol config.

#### Scenario: tiny score movement is not improvement
- **WHEN** an iteration improves by less than both configured absolute and relative thresholds
- **THEN** it is counted as non-improving

#### Scenario: gated improvement counts
- **WHEN** an iteration passes all gates and beats the threshold
- **THEN** it resets plateau patience and becomes the new best score

### Requirement: Gates are binary and separate from the objective
The loop SHALL compute trade floor, subwindow coverage, net-return contribution concentration, cost stress, complexity cap, and Train score floor as binary gates. Gates SHALL NOT be blended into the objective score.

#### Scenario: failed gate prevents keep
- **WHEN** a candidate improves the objective score but fails any gate
- **THEN** it is not keepable and counts as non-improving after a feasible baseline exists

#### Scenario: subwindow coverage is a binary gate
- **WHEN** any Train subwindow has fewer completed trades than the protocol-owned subwindow trade floor
- **THEN** the subwindow coverage gate fails

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

### Requirement: Missing subwindow evidence is not robustness
The Train gate set SHALL reject candidates that lack the protocol-required minimum trade evidence in any configured objective subwindow.

#### Scenario: clustered trades fail coverage
- **WHEN** a candidate satisfies the aggregate trade floor but all trades are clustered in fewer than `K` configured subwindows
- **THEN** the candidate fails the subwindow coverage gate

#### Scenario: covered subwindows can pass coverage
- **WHEN** every configured objective subwindow has at least the protocol-owned minimum subwindow trade count
- **THEN** the subwindow coverage gate passes if no other gate condition fails

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

### Requirement: Breadth gate names net-return contribution concentration explicitly
The breadth gate SHALL identify the current concentration metric as net-return contribution concentration when exposing gate details, result fields, and documentation.

#### Scenario: Result label is unambiguous
- **WHEN** a run emits or documents the concentration metric
- **THEN** the metric is labeled `net_return_contribution_concentration`
- **AND** no new breadth, exposure, or trade-count metric is introduced

