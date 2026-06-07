## MODIFIED Requirements

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

### Requirement: Gates are binary and separate from the objective
The loop SHALL compute trade floor, subwindow coverage, breadth/concentration, cost stress, complexity cap, and Train score floor as binary gates. Gates SHALL NOT be blended into the objective score.

#### Scenario: failed gate prevents keep
- **WHEN** a candidate improves the objective score but fails any gate
- **THEN** it is not keepable and counts as non-improving after a feasible baseline exists

#### Scenario: subwindow coverage is a binary gate
- **WHEN** any Train subwindow has fewer completed trades than the protocol-owned subwindow trade floor
- **THEN** the subwindow coverage gate fails

## ADDED Requirements

### Requirement: Missing subwindow evidence is not robustness
The Train gate set SHALL reject candidates that lack the protocol-required minimum trade evidence in any configured objective subwindow.

#### Scenario: clustered trades fail coverage
- **WHEN** a candidate satisfies the aggregate trade floor but all trades are clustered in fewer than `K` configured subwindows
- **THEN** the candidate fails the subwindow coverage gate

#### Scenario: covered subwindows can pass coverage
- **WHEN** every configured objective subwindow has at least the protocol-owned minimum subwindow trade count
- **THEN** the subwindow coverage gate passes if no other gate condition fails
