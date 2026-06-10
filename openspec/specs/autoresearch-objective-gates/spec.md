## Purpose

Define the Train robustness objective and binary gates used to decide whether an attempt can update the best Train survivor.
## Requirements
### Requirement: Objectives are selected by read-only protocol
The loop SHALL choose the Train robustness objective from protocol config. The agent SHALL NOT choose, change, or retry objective kinds during a thesis run.

#### Scenario: objective kind comes from protocol
- **WHEN** the protocol specifies `objective.kind`
- **THEN** the loop uses that objective implementation for all iterations in the thesis

### Requirement: Plateau improvement is mathematically defined
For completed iteration `t`, let `s_t` be its score and `b_t` be the best kept feasible score before `t`. The iteration SHALL count as an improvement only if all gates pass and `s_t > b_t + max(eps, rho * max(1, abs(b_t)))`, where `eps` and `rho` come from protocol config.

#### Scenario: tiny score movement is not improvement
- **WHEN** an iteration improves by less than both configured absolute and relative thresholds
- **THEN** it is counted as non-improving

#### Scenario: gated improvement counts
- **WHEN** an iteration passes all gates and beats the threshold
- **THEN** it resets plateau patience and becomes the new best score

### Requirement: Gates are binary and separate from the objective
The loop SHALL compute admissibility checks as binary gates. Gates SHALL NOT be blended into the objective score.

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

### Requirement: Portfolio foundation PSR objective scores full Train and weakest subwindow
The objective layer SHALL support `objective.kind = "portfolio_psr_subwindow"`. For this kind, the loop SHALL compute PSR from upstream portfolio-foundation `realistic_costs` metrics for the full Train window and every configured subwindow, then set the run score to `min(full_train_psr, min(subwindow_psr))`.

#### Scenario: full Train PSR is binding
- **WHEN** the full Train PSR is lower than every subwindow PSR
- **THEN** the objective score equals the full Train PSR

#### Scenario: weakest subwindow PSR is binding
- **WHEN** one Train subwindow has the lowest PSR
- **THEN** the objective score equals that subwindow PSR
- **AND** the objective exposes that subwindow id as the worst subwindow id

#### Scenario: foundation score inputs are unavailable
- **WHEN** any required full Train or subwindow Sharpe input is missing, non-finite, or has non-positive Sharpe standard error
- **THEN** the objective score is unavailable
- **AND** the failure detail identifies the missing or invalid foundation input

### Requirement: PSR uses protocol-owned hurdle
The portfolio foundation objective SHALL compute `PSR = NormalCDF((sharpe - psr_hurdle_sharpe) / sharpe_standard_error)`, where `psr_hurdle_sharpe` comes from protocol config and is fixed for the thesis lifecycle.

#### Scenario: hurdle affects PSR
- **WHEN** two protocol configs use different `psr_hurdle_sharpe` values against the same foundation metric record
- **THEN** the computed PSR values reflect those different hurdles

### Requirement: Foundation-backed gates are binary and separate from score
For portfolio-foundation scoring, the loop SHALL compute binary gates for trade floor, subwindow closed-trade coverage, return/effective-sample evidence, cost-stress PSR, foundation symbol concentration, max drawdown, economic total return, complexity cap, and Train score floor. These gates SHALL NOT be blended into the objective score.

#### Scenario: weak cost stress fails gate
- **WHEN** the `cost_stress` foundation scenario score is below the protocol-owned floor
- **THEN** the cost-stress gate fails
- **AND** the base objective score is not changed by the failed gate

#### Scenario: weak path risk fails gate
- **WHEN** the base foundation full Train max drawdown breaches the protocol-owned absolute drawdown cap
- **THEN** the path-risk gate fails
- **AND** the candidate is not keepable

#### Scenario: economic return floor fails gate
- **WHEN** the base foundation full Train total return is below the protocol-owned minimum
- **THEN** the economic-return gate fails
- **AND** the candidate is not keepable

### Requirement: Trade diagnostics remain diagnostic
Completed trade economics SHALL remain available for basic diagnostics such as win rate, profit factor, average trade net, and cost return sum, but trade-bag statistics SHALL NOT be used to compute the portfolio-foundation objective or foundation-backed gates.

#### Scenario: trade metrics do not override foundation score
- **WHEN** trade diagnostics are present but portfolio-foundation score inputs are unavailable
- **THEN** the loop does not compute a fallback score from trade returns
