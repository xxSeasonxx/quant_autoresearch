## ADDED Requirements

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
