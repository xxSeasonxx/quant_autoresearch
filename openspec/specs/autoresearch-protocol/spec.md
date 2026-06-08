## Purpose

Define the operator-owned protocol fields that freeze Train data, execution assumptions, objectives, gates, and loop constants for a thesis run.
## Requirements
### Requirement: Protocol owns Train data and execution assumptions
The protocol SHALL define the fixed Train data configuration, symbols, cost model, fill model, objective choice, gate thresholds, subwindow evidence coverage threshold, and loop settings. These values SHALL be loaded from read-only operator config and SHALL NOT be overridden by strategy params.

#### Scenario: params cannot override protocol fields
- **WHEN** params contain keys that resemble data, cost, fill, objective, gate, subwindow coverage, or loop fields
- **THEN** materialized quick-run configs use protocol values for those fields and put params only under strategy params

### Requirement: Loop constants are configurable and frozen per thesis
The protocol SHALL expose `M`, `N`, `K`, `eps`, and `rho` as named configuration values before a thesis starts. `M` SHALL control plateau patience, `N` SHALL control maximum iterations, `K` SHALL control Train objective subwindows, `eps` SHALL control minimum absolute improvement, and `rho` SHALL control minimum relative improvement. These values SHALL remain fixed during the thesis run.

#### Scenario: loop constants load from config
- **WHEN** a protocol file defines loop and objective constants
- **THEN** the loop uses those configured values instead of hard-coded defaults

#### Scenario: agent params cannot change loop constants
- **WHEN** strategy params contain `M`, `N`, `K`, `eps`, or `rho`
- **THEN** the loop constants still come from protocol config

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

### Requirement: Protocol excludes OOS windows from auto-research
The auto-research protocol SHALL expose only Train data to the loop. OOS windows and downstream evaluation config SHALL NOT be readable by the loop.

#### Scenario: loop config has no OOS window
- **WHEN** the auto-research protocol is loaded
- **THEN** the loop receives Train configuration only and no OOS/evaluate configuration

### Requirement: Protocol owns subwindow coverage
The protocol SHALL expose the minimum completed trade count required per configured objective subwindow as an operator-owned gate setting.

#### Scenario: subwindow coverage loads from config
- **WHEN** a protocol file defines `gates.min_trades_per_subwindow`
- **THEN** the gate configuration uses that value for subwindow coverage checks

#### Scenario: agent params cannot change subwindow coverage
- **WHEN** strategy params contain `min_trades_per_subwindow` or similar coverage keys
- **THEN** the loop still uses the protocol-owned subwindow coverage value

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

### Requirement: Active thesis lock freezes protocol and bounds
The first ordinary thesis attempt SHALL create a generated active thesis lock that records the current protocol hash and the current experiment bounds hash. Later attempts in the same thesis lifecycle SHALL reject protocol or bounds drift before quick-run materialization.

#### Scenario: Protocol hash drift is rejected
- **WHEN** prior thesis state exists and the current protocol hash differs from the active thesis lock
- **THEN** the loop rejects the attempt before quick-run materialization
- **AND** the rejection explains that Season must start a new thesis lifecycle for protocol changes

#### Scenario: Bounds hash drift is rejected
- **WHEN** prior thesis state exists and the current experiment bounds hash differs from the active thesis lock
- **THEN** the loop rejects the attempt before quick-run materialization
- **AND** ordinary param value changes within unchanged bounds remain allowed

#### Scenario: Missing lock is created on first attempt
- **WHEN** no active thesis lock exists and no prior result rows exist
- **THEN** the loop creates an active thesis lock from the current thesis text, protocol hash, bounds hash, and results path before running the first attempt

### Requirement: Protocol loading rejects invalid values
The protocol loader SHALL reject invalid protocol field types and ranges before quick-run config materialization.

#### Scenario: Invalid numeric protocol values fail
- **WHEN** a protocol file contains non-finite, boolean, negative, or zero values for fields whose contract requires finite positive or nonnegative numeric values
- **THEN** loading the protocol fails with a clear `ValueError`

#### Scenario: Invalid gate concentration fails
- **WHEN** `gates.max_symbol_concentration` is outside the inclusive range `[0, 1]`
- **THEN** loading the protocol fails with a clear `ValueError`

#### Scenario: Empty symbol universe fails
- **WHEN** `data.symbols` is empty
- **THEN** loading the protocol fails with a clear `ValueError`

#### Scenario: Invalid boolean protocol values fail
- **WHEN** a protocol boolean field is not a TOML boolean
- **THEN** loading the protocol fails with a clear `ValueError`

### Requirement: Default protocol documents symbol and window rationale
The active default protocol SHALL document why the default symbol universe, Train window, and subwindow count were selected for the current thesis-development setup.

#### Scenario: Protocol rationale is near owned values
- **WHEN** `protocol.toml` is read
- **THEN** symbol, Train window, and subwindow rationale is available near the corresponding protocol-owned values

