## Purpose

Define the operating contract that keeps the autonomous agent focused on one Train-only thesis run with a narrow editable surface and no in-loop OOS evaluation.

## Requirements

### Requirement: program.md mirrors the reference autoresearch structure
The project SHALL provide a concise `program.md` whose top-level structure follows the reference autoresearch contract: setup, experimentation, output format, logging results, and the experiment loop. The content SHALL be adapted to quant usage: Train-only quick runs, pure strategy functions, bounded params, configured stop rules, and no in-loop OOS evaluation.

#### Scenario: program sections are present
- **WHEN** `program.md` is read
- **THEN** it contains sections for setup, experimentation, output format, logging results, and the experiment loop

#### Scenario: quant-specific differences are explicit
- **WHEN** an agent reads the experiment loop section
- **THEN** it is told that OOS/evaluate is outside auto-research, the loop stops on configured rules, and the editable surface is limited

### Requirement: The agent-editable surface is narrow
The agent contract SHALL state that the agent may edit only `strategy.py` and bounded strategy params for the active thesis. Symbols, Train window, objective choice, gates, costs, fills, loop constants, and downstream OOS configuration SHALL be read-only to the agent.

#### Scenario: editable files are explicit
- **WHEN** `program.md` describes what the agent may edit
- **THEN** it names only `strategy.py` and bounded params as editable

#### Scenario: dangerous knobs are read-only
- **WHEN** `program.md` describes fixed configuration
- **THEN** symbols, time windows, costs/fills, objective, gates, and loop constants are read-only

### Requirement: Signal-component rationale is required
The agent contract SHALL require a rationale entry when a signal component is added or materially changed. The entry SHALL include the mechanism, observable, and falsifier. A component without a matching rationale entry SHALL NOT be considered keepable.

#### Scenario: changed component needs rationale
- **WHEN** an iteration adds a new signal component
- **THEN** the agent is required to add or update a rationale entry before keeping the iteration

### Requirement: The contract forbids in-loop evaluate
The agent contract SHALL forbid running `quant-strategies evaluate`, importing evaluation APIs, or reading OOS windows during the auto-research loop. OOS screening SHALL be documented as a separate downstream handoff after a frozen Train survivor exists.

#### Scenario: evaluate is not an agent command
- **WHEN** the agent command list is inspected
- **THEN** it includes no `evaluate`, `screen`, `graduate`, or `lockbox` command
