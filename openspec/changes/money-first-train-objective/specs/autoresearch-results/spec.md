## MODIFIED Requirements

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
