## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Active docs are distinguishable from historical design context
The agent contract SHALL make the active operating sources distinguishable from historical discussion documents.

#### Scenario: historical design doc is labeled
- **WHEN** the simplified loop design discussion is read
- **THEN** it identifies itself as historical or superseded context and points to active operating docs or specs
