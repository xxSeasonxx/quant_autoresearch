# Quant Autoresearch Research Process Upgrade Design

## Objective

Improve the autoresearch loop so it behaves more like a disciplined quant
research process while preserving the simple local workbench shape.

The workbench should still let an LLM make judgment calls, form hypotheses, and
iterate quickly. The harness should make poor research behavior unprofitable:
one-window overfitting, cherry-picked symbol pruning, unexamined parameter
changes, and oversized artifacts should no longer be the easiest path to a
better score.

## Current Problem

`program.md` already tells the agent to think like a quant researcher, inspect
evidence, avoid metric chasing, and use 120-180 day windows. The current runner
and scoring mechanics do not fully enforce that behavior.

The most important gap is that the session best is still chosen by a single
window score. In the recent session, a 2024 H1 candidate became the best
because it scored strongly on that window, even though later recent-window
checks showed materially weaker robustness. That mismatch creates an incentive
to optimize one favorable window instead of finding a candidate that generalizes
across recent market regimes.

Artifact size is also a practical blocker. A single 180-day run can write about
1 GB or more of input-row debug files. Multi-window confirmation would multiply
that cost unless the research runner has a compact artifact policy.

## Scope

This design upgrades `quant_autoresearch` only.

In scope:

- Research protocol wording in `program.md`.
- Multi-window orchestration in `runner.py`.
- Candidate-level confirmation scoring in `scoring.py`.
- Configuration additions in `experiment.toml`.
- Compact trade attribution artifacts generated from existing evidence.
- Artifact-retention policy for research runs.
- Tests for orchestration, scoring, artifact cleanup, and protocol guarantees.

Out of scope:

- Better fills, slippage, drawdown, margin, leverage, and equity-curve engine
  internals. Those belong in `quant_strategies`.
- Production trading, deployment, paper trading, or portfolio operations.
- A UI or dashboard.
- Strategy-library lifecycle outside this scratch workbench.

## Chosen Approach

Use a candidate lifecycle with recent-window confirmation.

The loop has two main modes:

- Explore cheaply on one primary recent window.
- Confirm promising candidates across a configured recent window bundle.

Only confirmed candidates can become best-so-far. Manual single-window runs can
still be used for diagnostics, but they should not replace the best confirmed
candidate.

This preserves LLM judgment and iteration speed while making one-window luck
and one-symbol cherry-picking less useful.

## Window Policy

Keep 180 calendar days as the standard full evaluation unit. It is long enough
to include many crypto funding cycles and enough trades, while still being
short enough to preserve regime specificity.

Do not require every window to be exactly 180 days. The config should allow
90-180 day recent confirmation windows when there is a research reason, such as
checking a very recent deployment-like slice. Scores should normalize by window
days so different valid lengths can be compared.

Recommended usage:

- Exploration: one 120-180 day recent primary window.
- Confirmation: three to five recent windows, each 90-180 days.
- Stress/reference: older 2022-2024 windows, diagnostic unless explicitly
  included in the confirmation bundle.

Recent windows should dominate candidate selection. Older windows should reveal
regime dependence and failure modes, not override recent deployability by
default.

## Symbol Universe Policy

The workbench may test fewer or more symbols when there is a market-structure
or trade-evidence reason. Profitability is allowed to improve through universe
selection, but symbol changes should be evaluated across the recent confirmation
bundle.

The score should not ban narrow universes. It should apply a small concentration
penalty below the configured `min_symbol_count` so a narrower universe must
earn its way through better recent-window performance.

## Machine-Aware Parallelism

The local machine is suitable for bounded parallel confirmation:

- MacBook Pro with Apple M3 Max.
- 16 CPU cores, including 12 performance cores.
- 128 GB RAM.
- Approximately 346 GB free disk at review time.

Default confirmation parallelism should be conservative:

```text
parallel_workers = 4
```

Four workers should use the machine well while leaving headroom for Python
memory use and avoiding excessive disk contention from runner artifacts. The
config may allow a higher value, but `4` should be the default.

## Configuration

Add research lifecycle configuration to `experiment.toml`:

```toml
[research]
mode = "explore"
primary_window_id = "locked_recent_2026"
confirmation_window_ids = [
  "validation_2025_h1",
  "validation_2025_h2",
  "locked_recent_2026",
]
parallel_workers = 4
confirm_on_explore_keep = true
```

Add balanced confirmation scoring configuration:

```toml
[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 200
low_trade_penalty = 0.001
min_symbol_count = 4
symbol_concentration_penalty = 0.00025
```

Add artifact policy configuration:

```toml
[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
```

`program.md` should not include the exact weights or worker count. It should
describe the rules and defer mechanics to the config.

## Runner Interface

Support these CLI modes:

```bash
python runner.py --explore --description "idea"
python runner.py --confirm --description "candidate confirmation"
python runner.py --window-id validation_2025_h2 --description "manual check"
```

Behavior:

- `--explore`: run one primary recent window. Log as exploration evidence.
- `--confirm`: run the configured confirmation windows, preferably in parallel,
  then write a candidate-level score and update best confirmed candidate.
- `--window-id`: run a single diagnostic window. Log evidence, but do not update
  best confirmed candidate unless the run is also part of confirmation.
- No explicit mode: use `research.mode` from `experiment.toml`.

Explore runs may trigger confirmation automatically when
`confirm_on_explore_keep = true`. The exact trigger should be simple: if the
explore score is valid and improves over the current primary-window reference
stored in session state, run confirmation before updating best confirmed state.
The primary-window reference is separate from `best_confirmed_candidate_score`.

## Candidate Artifacts

Confirmation should write a candidate-level result directory:

```text
results/<candidate_id>/
  candidate_score.json
  candidate_summary.json
  trade_attribution.json
  windows/
    <window_id>/
      score.json
      summary.json
      evidence.json
      signals.csv
      config.toml
      strategy_snapshot.py
```

The exact candidate directory name may reuse the timestamp and strategy id
pattern already produced by `quant_strategies`, as long as confirmation windows
are grouped under one candidate-level directory.

`results.tsv` should add columns for candidate-level evidence:

```text
run_kind
candidate_score
recent_mean_score
worst_recent_score
passed_window_count
failed_window_count
```

Allowed `run_kind` values:

```text
explore
confirm
diagnostic
```

## Candidate Scoring

Candidate scoring should be balanced, simple, and inspectable.

For each confirmed candidate, compute:

```text
recent_mean_score
recent_median_score
worst_recent_score
score_dispersion
total_trade_count
min_window_trade_count
symbol_count
passed_windows
failed_windows
candidate_score
decision
```

Use `net_return_per_day` as the primary input metric because configured windows
may differ in length.

Score formula:

```text
candidate_score =
    recent_mean_score
  - dispersion_penalty
  - weak_window_penalty
  - low_trade_penalty
  - symbol_concentration_penalty
```

Definitions:

- `recent_mean_score`: mean `net_return_per_day` across confirmation windows.
- `dispersion_penalty`: standard deviation of recent scores multiplied by
  `dispersion_weight`.
- `weak_window_penalty`: applied for each recent window at or below
  `weak_window_floor`.
- `low_trade_penalty`: applied for each window below `min_trades_per_window`.
- `symbol_concentration_penalty`: applied when symbol count is below
  `min_symbol_count`.

Do not add drawdown to this project until `quant_strategies` exposes a reliable
portfolio equity curve. The score may include drawdown later by consuming a
proper upstream metric.

Keep rule:

```text
keep if candidate_score > best_confirmed_candidate_score
```

Single-window explore and diagnostic scores should not overwrite
`best_confirmed_candidate_score`.

## Trade Evidence Attribution

The workbench should make trade evidence easy to inspect before the next
strategy change. Generate `trade_attribution.json` from the trades already
available in `evidence.json`.

Attribution groups:

```text
by_window
by_symbol
by_side
by_decision_hour
by_month
by_symbol_side
by_window_side
by_window_hour
```

Each group row should include:

```text
trade_count
gross_return
funding_return
cost_return
net_return
average_net_per_trade
score_contribution
```

The goal is not to make the LLM obey a mechanical checklist. The goal is to
make causal reasoning cheap:

- Side evidence supports asymmetric long/short hypotheses.
- Hour evidence supports session or cadence hypotheses.
- Symbol evidence supports universe rules, but only when repeated across
  windows.
- Window evidence supports regime hypotheses, not date hard-coding.
- Gross/funding disagreement separates price-reversal edge from carry.
- Low trade count lowers confidence even when return is high.

## Artifact Policy

Normal research runs should not keep full input rows.

Keep by default:

- `score.json`
- `candidate_score.json`
- `candidate_summary.json`
- `trade_attribution.json`
- `summary.json`
- `evidence.json`
- `signals.csv`
- `config.toml`
- `strategy_snapshot.py`
- manifests

Drop by default:

- `strategy_input_rows.csv`
- `strategy_input_rows.jsonl`
- `engine_request.json`, unless needed for debugging

Debug runs may keep full artifacts explicitly:

```bash
python runner.py --confirm --artifact-profile debug
```

Research runs should default to compact artifacts:

```bash
python runner.py --confirm --artifact-profile research
```

If `quant_strategies` supports suppressing large artifacts before writing, use
that. If it does not, `quant_autoresearch` may delete or compress large debug
artifacts after each window run. The deeper optimization belongs upstream in
`quant_strategies`.

## `program.md` Language

`program.md` should stay explicit and concise. It should include these rules in
plain language:

```text
A one-window result is exploration evidence only.
Only confirmed candidates can become best-so-far.
Confirmation means running the configured recent window bundle.
Recent windows dominate the score.
Older windows are diagnostic or stress evidence unless the config says
otherwise.
Do not prune symbols or windows because of one isolated result.
If a candidate improves one window but weakens the recent bundle, discard it.
Before changing strategy.py or experiment.toml, explain what trade evidence
changed your belief, what causal hypothesis follows, what focused change tests
it, and what result would falsify it.
```

It should also preserve this existing principle:

```text
Think like a quant researcher. Do not change parameters just because a score
moved. Use trade evidence to explain why the strategy works or fails. Every
change must map to a causal hypothesis from attribution by window, symbol,
side, decision time, gross return, funding return, costs, and trade count.
```

## Error Handling

If one confirmation window fails:

- Write that window's failure score.
- Include it in `candidate_score.json`.
- Penalize or invalidate the candidate depending on failure source.

Recommended behavior:

- `strategy_error` or `config_error`: candidate confirmation fails.
- `quant_data_error`, `quant_strategies_error`, or `environment_error`: record
  as blocked evidence and do not mutate the strategy to hide it.
- Missing `evidence.json`: window score is invalid and included in failed
  windows.

Parallel workers should isolate window output directories so one failed window
does not corrupt other window artifacts.

## Testing

Add focused tests for:

- Parsing new `[research]`, `[confirmation_scoring]`, and `[artifacts]` config
  sections.
- `--explore`, `--confirm`, and `--window-id` run-kind behavior.
- Confirmation runs creating per-window artifacts and aggregate candidate
  artifacts.
- Candidate score formula, including dispersion, weak-window, low-trade, and
  symbol-count penalties.
- Explore and diagnostic runs not overwriting best confirmed state.
- Artifact policy removing or retaining large files as configured.
- `trade_attribution.json` grouping and totals.
- `program.md` contract: one-window evidence is not best-so-far, confirmation
  controls keep/discard, and trade evidence is required before changes.

## Migration

Existing `results.tsv` rows may remain readable as historical attempt rows.
New rows should include the new candidate-level fields. The ledger migration
can fill missing new columns with empty values for old rows.

Existing single-window `score.json` files remain valid. New confirmation
artifacts add candidate-level files without changing the meaning of existing
per-window score files.

## Success Criteria

The upgrade is successful when:

- A strong one-window candidate cannot become best-so-far without confirmation.
- Confirmation can run multiple recent windows with bounded parallelism.
- Candidate decisions are based on a balanced recent-window aggregate score.
- The LLM has compact trade attribution for causal reasoning before changes.
- Normal runs no longer write or retain multi-GB debug input-row artifacts.
- `program.md` remains short enough to act as operating protocol, not a second
  implementation spec.
