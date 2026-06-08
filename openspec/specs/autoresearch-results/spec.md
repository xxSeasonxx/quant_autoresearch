## Purpose

Define the append-only `results.tsv` evidence log and status summary used by the Train loop.
## Requirements
### Requirement: results.tsv is the append-only loop log
The loop SHALL maintain a tab-separated `results.tsv` for the active thesis. It SHALL append one row per attempted iteration and SHALL NOT rewrite prior rows during normal operation.

#### Scenario: row appended for every attempt
- **WHEN** an iteration completes, fails, crashes, or is reverted
- **THEN** exactly one row is appended to `results.tsv`

### Requirement: results.tsv has stable columns
`results.tsv` SHALL include stable columns for run id, commit, candidate/protocol/artifact provenance, iteration, score, gate flags, subwindow trade counts, trade count, breadth/concentration summary, cost-stress result, complexity count, status, best status, continuation state, stop reason, elapsed seconds, and note. The `climb` command SHALL print the latest appended row using these same fields in a parseable `key: value` format.

#### Scenario: header is initialized
- **WHEN** a thesis run starts without `results.tsv`
- **THEN** the loop creates it with the stable header row

#### Scenario: row identifies candidate snapshot
- **WHEN** an iteration appends a result row
- **THEN** the row includes hashes for the strategy, experiment params/config, protocol, rationale, and materialized quick-run config

#### Scenario: row identifies generated artifacts
- **WHEN** an iteration appends a result row
- **THEN** the row includes the generated artifact directory for that attempt

#### Scenario: climb output mirrors result row
- **WHEN** `climb` completes an attempt and appends a result row
- **THEN** command output includes each result-row field as a parseable `key: value` line

### Requirement: status summarizes current thesis state
The status command SHALL read `results.tsv` and current protocol state to report best kept score, last attempts, stop state, configured `M`, `N`, `K`, and remaining attempts before max-iterations. It SHALL NOT report Selection budget, graduation state, or Lockbox state.

#### Scenario: status excludes retired harness concepts
- **WHEN** status output is generated
- **THEN** it contains no Selection budget, family id, ledger, graduation, or Lockbox fields

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

