## ADDED Requirements

### Requirement: Terminal handoff snapshots the best Train survivor
When a terminal stop condition fires after at least one kept candidate exists, the loop SHALL produce a terminal manifest whose Train survivor snapshot contains the source, params, protocol, rationale, and quick-run config from the best kept attempt, not from the current workspace unless the current workspace is that same best attempt.

#### Scenario: Plateau after discard preserves prior best survivor
- **WHEN** a prior attempt was kept and a later discarded attempt triggers plateau
- **THEN** the terminal manifest identifies the prior kept attempt as the best survivor
- **AND** the best survivor snapshot hashes match the prior kept attempt hashes

#### Scenario: Train failure has no survivor snapshot
- **WHEN** a thesis reaches a terminal stop without any kept candidate
- **THEN** the terminal manifest records Train failure
- **AND** the manifest does not expose a best survivor snapshot

### Requirement: Active thesis identity blocks ordinary drift
After the first attempt in a thesis lifecycle, the loop SHALL reject ordinary continuation when the provided mechanism or falsifier no longer matches the active thesis lock.

#### Scenario: Matching thesis continues
- **WHEN** a later climb uses the same normalized mechanism and falsifier as the active thesis lock
- **THEN** the loop may continue if no other stop or repair condition blocks it

#### Scenario: Changed thesis is rejected
- **WHEN** a later climb uses a different mechanism or falsifier from the active thesis lock
- **THEN** the loop rejects the attempt before quick-run materialization
- **AND** the rejection explains that a new thesis lifecycle is required
