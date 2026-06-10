## ADDED Requirements

### Requirement: Portfolio-foundation iterations consume public foundation evidence
When the protocol selects `portfolio_psr_subwindow`, each successful quick-run iteration SHALL compute score and foundation-backed gates from public `RunResult.foundation` payloads and SHALL NOT import private `quant_strategies` modules.

#### Scenario: foundation evidence drives score
- **WHEN** `run_config` succeeds and returns portfolio foundation evidence
- **THEN** the loop computes the objective score from `result.foundation`
- **AND** appends a result row using the portfolio-foundation score

#### Scenario: missing foundation evidence fails attempt
- **WHEN** `run_config` succeeds but returns no portfolio foundation evidence for `portfolio_psr_subwindow`
- **THEN** the iteration records a crash or repair-required attempt with a clear missing-foundation message

### Requirement: Micro causality evidence is surfaced for Train iteration
For Train iteration, the loop SHALL allow the protocol to request `micro` causality replay and SHALL surface causality status in the generated run card.

#### Scenario: micro causality is passed through
- **WHEN** the protocol sets `output.causality_check = "micro"`
- **THEN** the materialized quick-run config passed to `run_config` contains `causality_check = "micro"`

#### Scenario: causality status appears in run card
- **WHEN** `run_config` returns causality evidence
- **THEN** the generated run card records causality mode, verification status, replay warning, timeout status, and selected probe count when available

### Requirement: Portfolio-foundation keep rule preserves existing lifecycle semantics
For `portfolio_psr_subwindow`, the loop SHALL use the existing keep rule shape: only all-gates-pass attempts whose score exceeds the previous best by `max(eps, rho * max(1, abs(best)))` update the best Train survivor.

#### Scenario: gated PSR improvement is kept
- **WHEN** an iteration has a portfolio-foundation PSR score, passes all gates, and improves beyond the configured threshold
- **THEN** the loop logs status `keep`
- **AND** records `best_status=updated`

#### Scenario: failed foundation gate prevents keep
- **WHEN** an iteration has an improved PSR score but fails any foundation-backed gate
- **THEN** the loop logs status `discard`
- **AND** records `best_status=unchanged`
