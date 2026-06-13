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
The agent contract SHALL state that the agent may edit only `strategy.py`, bounded strategy params under `experiment.toml` `[params]`, and `rationale.md` for the active thesis. Symbols, Train window, objective choice, gates, costs, fills, loop constants, and downstream OOS configuration SHALL be read-only to the agent.

#### Scenario: editable files are explicit
- **WHEN** `program.md` describes what the agent may edit
- **THEN** it names only `strategy.py`, bounded params under `experiment.toml` `[params]`, and `rationale.md` as editable

#### Scenario: dangerous knobs are read-only
- **WHEN** `program.md` describes fixed configuration
- **THEN** symbols, time windows, costs/fills, objective, gates, and loop constants are read-only

#### Scenario: bounds are part of the editable surface
- **WHEN** the agent reads the editable params instructions
- **THEN** it is told that ordinary parameter edits must remain within the existing `[bounds.*]` ranges unless Season reseeds the thesis

### Requirement: Signal-component rationale is required
The agent contract SHALL require a `rationale.md` entry when a signal component is added or materially changed. The entry SHALL include the mechanism, observable, and falsifier. Signal components SHALL be declared using `### Component: <name>` headings under `## Signal Components`, and those declarations SHALL be the source of truth for component-count accounting.

#### Scenario: changed component needs rationale
- **WHEN** an iteration adds a new signal component
- **THEN** the agent is required to add or update a rationale entry before keeping the iteration

#### Scenario: component headings are accounting
- **WHEN** the agent adds or materially changes a signal component
- **THEN** `rationale.md` includes a `### Component: <name>` heading for that component under `## Signal Components`

### Requirement: The contract forbids in-loop evaluate
The agent contract SHALL forbid running `quant-strategies evaluate`, importing evaluation APIs, or reading OOS windows during the auto-research loop. OOS screening SHALL be documented as a separate downstream handoff after a frozen Train survivor exists.

#### Scenario: evaluate is not an agent command
- **WHEN** the agent command list is inspected
- **THEN** it includes no `evaluate`, `screen`, `graduate`, or `lockbox` command

### Requirement: Local type checking passes
The project SHALL keep local `mypy .` checks passing, with untyped upstream imports handled by explicit narrow configuration rather than broad ignores.

#### Scenario: mypy passes locally
- **WHEN** `conda run -n quant python -m mypy .` is run in the repo
- **THEN** it exits successfully

#### Scenario: upstream ignore is narrow
- **WHEN** mypy configuration is inspected
- **THEN** missing-import ignores are scoped to `quant_strategies.*`

### Requirement: Agent contract defines artifact authority
The agent contract SHALL distinguish active-loop inputs from generated audit/handoff artifacts and Season downstream-only artifacts.

#### Scenario: Active loop inputs are bounded
- **WHEN** an agent reads `program.md` for an active Train research run
- **THEN** it is told to use the active operating files, recent `results.tsv`, and the latest quick-run artifact directory recorded in `results.tsv` as the active loop inputs

#### Scenario: Generated handoff artifacts are not routine loop inputs
- **WHEN** an agent reads `program.md` for an active Train research run
- **THEN** it is told that thesis locks, snapshots, and terminal manifests are generated audit or handoff artifacts rather than routine inputs for choosing Train edits

#### Scenario: Rest of repo is not a routine loop input
- **WHEN** an agent reads active docs
- **THEN** it is told not to browse the rest of the repo during ordinary Train iteration unless debugging a failure, checking an explicitly in-scope contract, or Season asks

