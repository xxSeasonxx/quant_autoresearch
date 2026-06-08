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
The protocol layer SHALL materialize `quant_strategies` quick-run TOML configs using the public runner schema: strategy path/id, `[data]`, `[params]`, `[fill_model]`, `[cost_model]`, and `[output]`. It SHALL call only public `quant_strategies.runner.run_config`.

#### Scenario: quick-run config contains required sections
- **WHEN** the loop materializes a quick-run config
- **THEN** the config contains the public runner sections needed by `run_config`

#### Scenario: no internal engine import is needed
- **WHEN** protocol and loop modules are imported
- **THEN** they do not import `quant_strategies.engine` or private `quant_strategies` modules

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

