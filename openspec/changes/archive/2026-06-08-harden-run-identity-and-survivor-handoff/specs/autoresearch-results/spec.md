## ADDED Requirements

### Requirement: Attempts preserve source snapshots
Each attempted iteration SHALL write a generated source snapshot for the exact candidate evaluated by that attempt, including strategy, experiment, protocol, rationale, and materialized quick-run config.

#### Scenario: Attempt snapshot is written before quick run
- **WHEN** an attempt materializes its quick-run config
- **THEN** the loop writes source snapshot files under the generated artifact directory for that attempt

#### Scenario: Result row hashes match attempt snapshot
- **WHEN** an attempt appends a result row
- **THEN** the source files in that attempt's generated snapshot hash to the same values recorded in the result row

### Requirement: Terminal manifest references terminal and survivor snapshots separately
Terminal manifests SHALL distinguish the terminal attempt snapshot from the best survivor snapshot so downstream review can tell which candidate stopped the run and which candidate is the Train survivor.

#### Scenario: Survivor and terminal attempt differ
- **WHEN** the terminal attempt is not the best kept attempt
- **THEN** the terminal manifest includes separate paths for the terminal attempt snapshot and the best survivor snapshot

#### Scenario: Survivor and terminal attempt are same
- **WHEN** the terminal attempt is also the best kept attempt
- **THEN** the terminal manifest may point both terminal and survivor snapshot references to the same generated snapshot
