# Quant Autoresearch Upstream Contract And Selected 15 Design

## Purpose

Update `quant_autoresearch` after the upstream `quant_strategies` runner and strategy contracts changed. The workbench should consume the new contracts directly, migrate the selected strategy variants, and clean `results/` so it contains only the curated legacy 15 and the future rerun 15.

This is a contract migration and cleanup, not a strategy research iteration.

## Scope

- Update the local runner boundary to match upstream `quant_strategies.runner.run_config`.
- Remove active legacy contract handling from `quant_autoresearch`.
- Select the top 3 logic families and top 5 variants per family from existing evidence.
- Migrate the selected 15 strategy variants to the new decision contract.
- Rebuild `results.tsv` so it describes only the selected legacy 15 and future new 15.
- Hard-delete old `results/` children after the preservation package verifies.
- Update `program.md` only where necessary to describe the current contracts and loop language.

## Upstream Contract Changes

The upstream public execution entry point remains:

```text
quant_strategies.runner.run_config(config_path, *, repo_root=None)
```

The contracts around it changed:

- Strategies must expose `generate_decisions(rows, params) -> list[StrategyDecision]`.
- `StrategyDecision` requires timezone-aware `decision_time` and `as_of_time`.
- Decisions use typed `InstrumentRef`, `PositionTarget`, `ExitPolicy`, optional `ObservationRef`, and JSON-compatible metadata.
- Runner TOML uses `[output].artifact_profile = "full" | "summary"`.
- Evidence v2 reports returns under `screening_result.smoke_score.sum_weighted_trade_*`.
- Full artifacts may include `decision_records.jsonl`, `signals.csv`, `engine_request.json`, `strategy_input_rows.csv`, and `strategy_input_rows.jsonl`.

## Architecture

`quant_autoresearch` remains the research-loop orchestrator. It owns `program.md`, attempt budgets, promotion logic, ranking, selection manifests, and cleanup policy. It does not reimplement execution or mutate upstream `quant_strategies`.

The runner boundary will be updated narrowly:

- Materialized runner configs will match the upstream config schema directly.
- Local artifact retention policy may keep `research` and `debug` names, but those names must translate before runner TOML is written. They must not leak into upstream configs.
- Scoring will read only evidence v2 smoke score fields in the active path.
- Trade attribution will require full evidence with trades.
- Failure classification will recognize upstream stages including `param_validation`, `decision_generation`, `request_build`, and `engine_evaluation`.

## Components

### `scoring.py`

Read active score fields from:

```text
screening_result.smoke_score.sum_weighted_trade_net_return
screening_result.smoke_score.sum_weighted_trade_gross_return
screening_result.smoke_score.sum_weighted_trade_funding_return
screening_result.smoke_score.sum_weighted_trade_cost_return
```

If v2 smoke score fields are missing, score construction should return a non-scored evidence failure with an explicit message. It must not silently return zero or read old fields. Historical old-field fallback should be removed from the active scoring path.

Trade attribution should read v2 `screening_result.trades`. If trades are absent because a summary artifact profile was used, attribution should report that full artifacts are required.

### `experiment_config.py`

Keep the workbench-level artifact policy if needed, but materialized upstream TOML must emit:

```toml
[output]
artifact_profile = "full"
```

The research loop should default to `full` because scoring and attribution need evidence and trades.

### `artifact_policy.py`

Update artifact handling for current upstream filenames:

```text
decision_records.jsonl
artifact_profile_summary.json
strategy_input_rows.csv
strategy_input_rows.jsonl
engine_request.json
signals.csv
evidence.json
summary.json
config.toml
strategy_snapshot.py
data_manifest.json
run_manifest.json
notes.md
```

Remove expectations for artifacts that no longer exist upstream.

### Migrated Strategies

Each selected variant will expose:

```text
validate_params(params) -> mapping
generate_decisions(rows, params) -> list[StrategyDecision]
```

The public `generate_signals` dict contract should be removed. If the implementation still benefits from internal candidate dictionaries, keep those helpers private.

Each emitted decision should include:

- `InstrumentRef(kind="crypto_perp", symbol=...)`
- `PositionTarget(direction="long" | "short", sizing_kind="target_weight", size=weight)`
- `ExitPolicy(max_hold_bars=...)`
- `decision_time` and `as_of_time` as timezone-aware datetimes
- JSON-safe metadata for funding pressure, return extension, family, and state mode
- `ObservationRef` lineage for each emitted symbol's as-of close row and the funding observations used in the funding-pressure calculation

## Selection Flow

Use the existing ranking logic as the starting point, but select from all relevant result evidence under `results/`, including researched packages and stateful campaigns. The selected output is written to:

```text
results/selected_15/
```

The selected package will contain:

```text
results/selected_15/selection_manifest.json
results/selected_15/<family>/rank_##/strategy.py
results/selected_15/<family>/rank_##/config.toml
results/selected_15/<family>/rank_##/source_summary.json
```

`selection_manifest.json` records:

- selection timestamp
- selection method version
- source campaign/result paths
- family and rank
- old scores, raw returns, trade counts, and promotion score if available
- params used for the migrated config
- source strategy hash

## Rerun Flow

New run artifacts go only under:

```text
results/new_15/
```

The first implementation pass only prepares the selected 15 and runner compatibility. The rerun itself can be started after the user reviews the package.

## Cleanup Flow

After selection and migration verify successfully:

1. Ensure `results/selected_15/selection_manifest.json` exists.
2. Ensure exactly 15 selected variant directories exist.
3. Ensure each selected variant has `strategy.py`, `config.toml`, and `source_summary.json`.
4. Ensure every migrated strategy imports cleanly under `conda run -n quant`.
5. Ensure every migrated config validates through upstream `quant_strategies.runner.config.load_config`.
6. Ensure `results/new_15/` exists.
7. Rebuild `results.tsv`.
8. Hard-delete every direct child under `results/` except `selected_15` and `new_15`.

No deletion is allowed outside `results/`.

## Ledger Contract

`results.tsv` will be rebuilt. It should contain only:

- selected legacy 15 rows, with `run_kind = selected_legacy` and `status = selected`
- future new rerun rows under `results/new_15`

Old campaign attempt rows should be removed because their artifact directories will be deleted.

Selected legacy rows should use explicit values instead of faking active runner attempts:

- `result_dir = results/selected_15/<family>/rank_##`
- score/raw/trade fields copied from selection evidence where available
- new-run-only fields blank when not applicable

## Program Documentation

Update `program.md` only for necessary contract language:

- strategies emit `StrategyDecision`
- upstream evidence v2 smoke-score fields define loop scoring
- full artifact profile is required for attribution
- `results/selected_15` and `results/new_15` are the only preserved result roots after cleanup

Do not rewrite the research philosophy or experiment loop beyond those contract changes.

## Error Handling

If any selected strategy cannot be migrated cleanly, stop before deleting old results. Report the failing variant, source path, and contract violation.

If upstream config validation fails, stop before deleting old results. Report the config path and validation error.

If `results.tsv` rebuild cannot map a selected variant to evidence, stop before deletion unless the missing value can be represented explicitly as blank/null in a selected legacy row.

## Tests

Focused tests should cover:

- materialized runner TOML emits upstream `output.artifact_profile`
- old `research/debug` artifact names do not appear in upstream config
- `build_score` reads v2 `smoke_score.sum_weighted_trade_*`
- missing v2 smoke-score fields fail clearly
- trade attribution reads v2 trades
- artifact policy handles current upstream artifact filenames
- selection manifest schema and exactly 15 variants
- cleanup preserves only `selected_15` and `new_15`
- rebuilt `results.tsv` contains only selected legacy and new rerun rows

Verification commands:

```bash
conda run -n quant pytest tests/test_experiment_config.py tests/test_scoring.py tests/test_artifact_policy.py
```

Add targeted migration tests if the implementation introduces a new migration module.

## Non-Goals

- Do not mutate upstream `quant_strategies`.
- Do not rerun the 15 variants during this migration step unless Season explicitly starts the rerun.
- Do not optimize parameters while migrating.
- Do not preserve old run directories after the selected package verifies.
