## ADDED Requirements

### Requirement: Protocol owns the money-first objective and acceptance haircut
The protocol SHALL set `objective.kind = "return_lcb_subwindow"` as the operator-owned default objective and SHALL expose the acceptance haircut `gates.score_haircut_se` (`k_accept`) as an explicit finite field. `k_accept` SHALL NOT be auto-derived from `max_iterations`; the `sqrt(2 * ln N_attempts)` guidance is documented near the field. These values SHALL remain fixed for the thesis lifecycle through the active thesis protocol hash.

#### Scenario: objective kind loads from protocol
- **WHEN** the protocol sets `objective.kind = "return_lcb_subwindow"`
- **THEN** the objective config exposes that kind to scoring for all iterations

#### Scenario: acceptance haircut is explicit, not derived
- **WHEN** the protocol defines `gates.score_haircut_se`
- **THEN** the gate configuration uses that value for the deflated money floor
- **AND** changing `max_iterations` does not change `k_accept`

## MODIFIED Requirements

### Requirement: Protocol owns foundation-backed gate thresholds
The protocol SHALL expose finite operator-owned thresholds for minimum return sample count, minimum effective sample count, minimum annualized return (the deflated money floor), the acceptance haircut `score_haircut_se`, minimum cost-stress return retention, maximum absolute drawdown, maximum symbol concentration, trade floors, and complexity caps.

#### Scenario: foundation gate thresholds load
- **WHEN** a protocol file defines the foundation-backed gate thresholds
- **THEN** the gate configuration exposes those thresholds to gate evaluation

#### Scenario: invalid foundation gate threshold fails
- **WHEN** a foundation-backed gate threshold is non-finite or outside its valid range
- **THEN** protocol loading rejects the config before quick-run materialization

### Requirement: Protocol owns diagnostic PSR parameters
The protocol SHALL expose `objective.psr_hurdle_sharpe` to parameterize the diagnostic PSR computation. PSR is a diagnostic only and SHALL NOT be the run score or a gate. This value SHALL be finite and SHALL remain fixed for the thesis lifecycle through the active thesis protocol hash.

#### Scenario: PSR hurdle parameterizes the diagnostic
- **WHEN** the protocol defines `objective.psr_hurdle_sharpe`
- **THEN** the diagnostic PSR uses that hurdle
- **AND** the run score and gates do not depend on it

### Requirement: Protocol supports micro causality policy
The protocol loader SHALL accept `output.causality_check = "micro"` and pass it through to the materialized quick-run config. The protocol SHALL expose the operator-owned causality replay budget (`output.focused_timeout_seconds`, `output.focused_probe_limit`) and materialize it, so a legitimate run can verify causality within budget given that causality verification is a hard gate.

#### Scenario: micro causality loads
- **WHEN** the protocol sets `output.causality_check = "micro"`
- **THEN** protocol loading succeeds
- **AND** the quick-run output config preserves `causality_check = "micro"`

#### Scenario: replay budget is materialized
- **WHEN** the protocol defines `output.focused_timeout_seconds` and `output.focused_probe_limit`
- **THEN** the materialized quick-run config carries those replay-budget values
