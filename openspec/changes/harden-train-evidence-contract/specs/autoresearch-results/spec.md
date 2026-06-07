## MODIFIED Requirements

### Requirement: results.tsv has stable columns
`results.tsv` SHALL include stable columns for run id, commit, candidate/protocol/artifact provenance, iteration, score, gate flags, subwindow trade counts, trade count, breadth/concentration summary, cost-stress result, complexity count, status, best status, continuation state, stop reason, elapsed seconds, and note.

#### Scenario: header is initialized
- **WHEN** a thesis run starts without `results.tsv`
- **THEN** the loop creates it with the stable header row

#### Scenario: row identifies candidate snapshot
- **WHEN** an iteration appends a result row
- **THEN** the row includes hashes for the strategy, experiment params/config, protocol, rationale, and materialized quick-run config

#### Scenario: row identifies generated artifacts
- **WHEN** an iteration appends a result row
- **THEN** the row includes the generated artifact directory for that attempt

## ADDED Requirements

### Requirement: Result rows record attempt provenance
Each new `results.tsv` row SHALL identify the exact attempt snapshot it describes, including whether the worktree was dirty when the attempt ran.

#### Scenario: dirty worktree is visible
- **WHEN** an attempt runs while tracked source files have uncommitted changes
- **THEN** the result row records `worktree_dirty=true`

#### Scenario: clean worktree is visible
- **WHEN** an attempt runs with no tracked source changes
- **THEN** the result row records `worktree_dirty=false`

### Requirement: Result rows record lifecycle state
Each new `results.tsv` row SHALL record whether the attempt updated the best candidate and whether research may continue from the working snapshot.

#### Scenario: discard does not update best
- **WHEN** an attempt is discarded because it fails gates or does not improve enough
- **THEN** the result row records `best_status=unchanged`

#### Scenario: discard can allow continuation
- **WHEN** an attempt is discarded without leaving the workspace invalid and no terminal stop fires
- **THEN** the result row records that continuation is allowed

#### Scenario: keep updates best
- **WHEN** an attempt is kept as the new best candidate
- **THEN** the result row records `best_status=updated`

#### Scenario: terminal stop blocks continuation
- **WHEN** an attempt triggers a terminal stop condition
- **THEN** the result row records a terminal continuation state
