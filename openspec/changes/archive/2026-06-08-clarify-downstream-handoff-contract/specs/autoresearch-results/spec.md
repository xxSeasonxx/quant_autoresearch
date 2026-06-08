## MODIFIED Requirements

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
