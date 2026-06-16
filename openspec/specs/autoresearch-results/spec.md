## Purpose

Define the append-only `results.tsv` evidence log and status summary used by the Train loop.
## Requirements
### Requirement: results.tsv is the append-only loop log
The loop SHALL maintain a tab-separated `results.tsv` for the active thesis. It SHALL append one row per attempted iteration and SHALL NOT rewrite prior rows during normal operation.

#### Scenario: row appended for every attempt
- **WHEN** an iteration completes, fails, crashes, or is reverted
- **THEN** exactly one row is appended to `results.tsv`

### Requirement: results.tsv has stable columns
`results.tsv` SHALL include stable columns for run id, iteration, score, money-score parts (deflated money floor, full-Train annualized return, LCB-binding worst-window id and annualized return), sizing-report fields (book scale, deployed and max-feasible volatility, capacity-bound flag), gate flags, foundation full-Train closed-trade count, minimum subwindow trades, basic economics, compact portfolio-foundation diagnostics including diagnostic PSR, complexity count, status, best status, continuation state, stop reason, elapsed seconds, artifact directory, and note. Source provenance SHALL be preserved by the per-attempt snapshot under `artifact_dir`, not by inline provenance columns. The `climb` command SHALL print the latest appended row using these same fields in a parseable `key: value` format.

#### Scenario: header is initialized
- **WHEN** a thesis run starts without `results.tsv`
- **THEN** the loop creates it with the stable header row

#### Scenario: empty legacy header is replaced
- **WHEN** `results.tsv` contains only a header row from a previous schema
- **THEN** the next append replaces it with the current stable header before writing the first result row

#### Scenario: non-empty legacy ledger is rejected
- **WHEN** `results.tsv` contains rows from a previous schema
- **THEN** reading or appending results fails with a clear error requiring a new thesis lifecycle

#### Scenario: row identifies candidate snapshot
- **WHEN** an iteration appends a result row
- **THEN** the row includes the generated artifact directory for that attempt
- **AND** that artifact directory contains a snapshot of the strategy, experiment params/config, protocol, rationale, and materialized quick-run config

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

### Requirement: Result rows validate field semantics
The result log reader SHALL reject malformed result rows before returning `ResultRow` objects to loop state derivation.

#### Scenario: Invalid lifecycle enum fails
- **WHEN** a result row contains an unsupported `status`, `best_status`, or `continuation` value
- **THEN** reading results fails with a clear `ValueError`

#### Scenario: Invalid boolean text fails
- **WHEN** a result row boolean field is not exactly `true` or `false`
- **THEN** reading results fails with a clear `ValueError`

#### Scenario: Invalid hash text fails
- **WHEN** a result row hash field is neither a 64-character lowercase hexadecimal hash nor the explicit `missing` marker
- **THEN** reading results fails with a clear `ValueError`

### Requirement: Result chains validate attempt order
The result log reader SHALL reject result chains with duplicate run ids, duplicate iterations, non-contiguous iterations, or terminal continuation before the final row.

#### Scenario: Duplicate or non-contiguous attempts fail
- **WHEN** a `results.tsv` file has duplicate run ids, duplicate iterations, or skips an iteration number
- **THEN** reading results fails with a clear `ValueError`

#### Scenario: Terminal row before final row fails
- **WHEN** a row with `continuation=terminal` is followed by another result row
- **THEN** reading results fails with a clear `ValueError`

### Requirement: results.tsv reports a compact metric set
Each successful portfolio-foundation result row SHALL report no more than the compact metric set needed for loop control and human scanability: `score`, `worst_window_id`, `deflated_money_floor`, `full_train_annualized_return`, `worst_window_annualized_return`, `cost_stress_return_retention`, `book_scale`, `deployed_volatility`, `max_feasible_volatility`, `capacity_bound`, `trade_count`, `min_subwindow_trades`, `total_return`, `max_drawdown`, `win_rate`, `profit_factor`, `avg_trade_net`, `cost_return_sum`, `max_symbol_concentration`, `complexity_count`, and the diagnostic `full_train_psr` and `worst_subwindow_psr`. `trade_count` SHALL be the upstream foundation full-Train `closed_trade_count` used by the trade-floor gate, not the number of sampled diagnostic trades. PSR columns SHALL be diagnostics only and SHALL NOT be the score or a gate value.

#### Scenario: money score parts are present
- **WHEN** an iteration appends a successful result row
- **THEN** the row includes `score`, `deflated_money_floor`, and `worst_window_annualized_return`

#### Scenario: sizing-report fields are present
- **WHEN** an iteration appends a successful result row
- **THEN** the row includes `book_scale`, `deployed_volatility`, `max_feasible_volatility`, and `capacity_bound`

#### Scenario: basic economic diagnostics are present
- **WHEN** an iteration appends a successful result row
- **THEN** the row includes total return, win rate, profit factor, average trade net, and cost return sum when available

#### Scenario: detailed vectors are not stored in TSV
- **WHEN** an iteration computes per-subwindow values or foundation warnings
- **THEN** those detailed vectors and warnings are omitted from `results.tsv`
- **AND** they are written to the generated run card

### Requirement: Each attempt writes a run card artifact
Each attempted iteration SHALL write a generated `run_card.json` under the attempt artifact directory. The run card SHALL include money-score parts and per-window deployed-return statistics, the upstream `PortfolioSizingReport` fields, foundation scenario summaries used for scoring and gates, all gate outcomes with values and thresholds, relevant foundation warnings, and the primary failure mode when derivable.

#### Scenario: run card path is stable
- **WHEN** an attempt has artifact directory `results/autoresearch/attempt-0001`
- **THEN** its generated run card is written at `results/autoresearch/attempt-0001/run_card.json`

#### Scenario: run card includes sizing report
- **WHEN** an iteration scores a feasible book
- **THEN** the run card includes the `PortfolioSizingReport` fields used for sizing and the capacity-bound flag

#### Scenario: run card includes gate details
- **WHEN** an iteration evaluates gates
- **THEN** the run card includes each gate name, pass/fail result, value, threshold, and detail text
