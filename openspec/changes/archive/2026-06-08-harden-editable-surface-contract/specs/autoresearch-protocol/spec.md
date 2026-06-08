## MODIFIED Requirements

### Requirement: Protocol materializes public quick-run configs
The protocol layer SHALL materialize `quant_strategies` quick-run TOML configs using the public runner schema: strategy path/id, `[data]`, validated `[params]`, `[fill_model]`, `[cost_model]`, and `[output]`. It SHALL call only public `quant_strategies.runner.run_config`.

#### Scenario: quick-run config contains required sections
- **WHEN** the loop materializes a quick-run config
- **THEN** the config contains the public runner sections needed by `run_config`

#### Scenario: no internal engine import is needed
- **WHEN** protocol and loop modules are imported
- **THEN** they do not import `quant_strategies.engine` or private `quant_strategies` modules

#### Scenario: quick-run params are bounded
- **WHEN** the loop materializes a quick-run config from `experiment.toml`
- **THEN** the `[params]` block contains only params validated against declared `[bounds.*]`

## ADDED Requirements

### Requirement: Experiment params are validated against bounds
The experiment loader SHALL validate `experiment.toml` `[params]` against `[bounds.<param>]` before params are passed to the quick-run config.

#### Scenario: param within bounds loads
- **WHEN** a param has a numeric value inside its declared inclusive min and max bounds
- **THEN** the experiment loader accepts the param

#### Scenario: param below bounds fails
- **WHEN** a param value is below its declared min bound
- **THEN** the experiment loader rejects the experiment before quick-run materialization

#### Scenario: param above bounds fails
- **WHEN** a param value is above its declared max bound
- **THEN** the experiment loader rejects the experiment before quick-run materialization

#### Scenario: missing param bound fails
- **WHEN** `[params]` contains a key without a corresponding `[bounds.<param>]` table
- **THEN** the experiment loader rejects the experiment before quick-run materialization

#### Scenario: orphan bound fails
- **WHEN** `[bounds.<param>]` exists for a key that is absent from `[params]`
- **THEN** the experiment loader rejects the experiment before quick-run materialization
