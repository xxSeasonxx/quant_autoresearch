## ADDED Requirements

### Requirement: Protocol owns quick-run foundation output controls
The protocol SHALL expose operator-owned quick-run foundation output settings and materialize them into public `quant_strategies.runner.run_config` output config. Foundation subwindow count SHALL match the configured objective subwindow count for portfolio-foundation scoring.

#### Scenario: foundation output is materialized
- **WHEN** the protocol enables portfolio foundation output
- **THEN** the materialized quick-run config includes `foundation_enabled = true`
- **AND** `foundation_subwindows` equals `objective.subwindows`

#### Scenario: foundation subwindow mismatch is rejected
- **WHEN** a protocol would materialize a foundation subwindow count different from the objective subwindow count
- **THEN** protocol loading rejects the configuration before quick-run materialization

### Requirement: Protocol supports micro causality policy
The protocol loader SHALL accept `output.causality_check = "micro"` and pass it through to the materialized quick-run config.

#### Scenario: micro causality loads
- **WHEN** the protocol sets `output.causality_check = "micro"`
- **THEN** protocol loading succeeds
- **AND** the quick-run output config preserves `causality_check = "micro"`

### Requirement: Protocol owns PSR scoring parameters
The protocol SHALL expose `objective.psr_hurdle_sharpe` for portfolio-foundation PSR scoring. This value SHALL be finite and SHALL remain fixed for the thesis lifecycle through the existing active thesis protocol hash.

#### Scenario: PSR hurdle loads from protocol
- **WHEN** the protocol defines `objective.psr_hurdle_sharpe`
- **THEN** the objective config exposes that value to scoring

### Requirement: Protocol owns foundation-backed gate thresholds
The protocol SHALL expose finite operator-owned thresholds for minimum return sample count, minimum effective sample count, minimum cost-stress PSR, maximum absolute drawdown, minimum total return, maximum symbol concentration, trade floors, and complexity caps.

#### Scenario: foundation gate thresholds load
- **WHEN** a protocol file defines the foundation-backed gate thresholds
- **THEN** the gate configuration exposes those thresholds to gate evaluation

#### Scenario: invalid foundation gate threshold fails
- **WHEN** a foundation-backed gate threshold is non-finite or outside its valid range
- **THEN** protocol loading rejects the config before quick-run materialization
