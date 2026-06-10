## MODIFIED Requirements

### Requirement: results.tsv has stable columns
`results.tsv` SHALL include stable columns for run id, commit, candidate/protocol/artifact provenance, iteration, score, PSR score parts, gate flags, foundation full-Train closed-trade count, minimum subwindow trades, basic economics, compact portfolio-foundation diagnostics, complexity count, status, best status, continuation state, stop reason, elapsed seconds, and note. The `climb` command SHALL print the latest appended row using these same fields in a parseable `key: value` format.

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
- **THEN** the row includes hashes for the strategy, experiment params/config, protocol, rationale, and materialized quick-run config

#### Scenario: row identifies generated artifacts
- **WHEN** an iteration appends a result row
- **THEN** the row includes the generated artifact directory for that attempt

#### Scenario: climb output mirrors result row
- **WHEN** `climb` completes an attempt and appends a result row
- **THEN** command output includes each result-row field as a parseable `key: value` line

## ADDED Requirements

### Requirement: results.tsv reports a compact metric set
Each successful portfolio-foundation result row SHALL report no more than the compact metric set needed for loop control and human scanability: `score`, `full_train_psr`, `worst_subwindow_psr`, `worst_subwindow_id`, `cost_stress_psr`, `trade_count`, `min_subwindow_trades`, `total_return`, `max_drawdown`, `win_rate`, `profit_factor`, `avg_trade_net`, `cost_return_sum`, `max_symbol_concentration`, and `complexity_count`. `trade_count` SHALL be the upstream foundation full-Train `closed_trade_count` used by the trade-floor gate, not the number of sampled diagnostic trades.

#### Scenario: basic economic diagnostics are present
- **WHEN** an iteration appends a successful result row
- **THEN** the row includes total return, win rate, profit factor, average trade net, and cost return sum when available

#### Scenario: detailed vectors are not stored in TSV
- **WHEN** an iteration computes per-subwindow PSR values or foundation warnings
- **THEN** those detailed vectors and warnings are omitted from `results.tsv`
- **AND** they are written to the generated run card

### Requirement: Each attempt writes a run card artifact
Each attempted iteration SHALL write a generated `run_card.json` under the attempt artifact directory. The run card SHALL include score parts, foundation scenario summaries used for scoring and gates, all gate outcomes with values and thresholds, relevant foundation warnings, and the primary failure mode when derivable.

#### Scenario: run card path is stable
- **WHEN** an attempt has artifact directory `results/autoresearch/attempt-0001`
- **THEN** its generated run card is written at `results/autoresearch/attempt-0001/run_card.json`

#### Scenario: run card includes gate details
- **WHEN** an iteration evaluates gates
- **THEN** the run card includes each gate name, pass/fail result, value, threshold, and detail text
