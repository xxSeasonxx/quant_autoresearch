# quant_autoresearch

Local scratch workbench for one quant strategy candidate at a time.

The research loop edits only:

```text
strategy.py
experiment.toml
```

The fixed harness for this workbench is:

```text
program.md
runner.py
scoring.py
experiment_config.py
```

Strategy execution is delegated to `quant_strategies.runner.run_config`.
Generated attempt artifacts live under ignored `results/`, and the append-only
attempt ledger is ignored as `results.tsv`. The ledger is runner-owned and
includes the evaluated window id, start, end, day count, and symbol count for
each attempt.

Configured research windows are 120 to 180 calendar days. The runner records
raw net return, but the guarded comparison score is normalized by window days
when window metadata is available.

Runner file contracts:

```text
results.tsv
results/session_state.json
results/<attempt>/score.json
results/<attempt>/attempt_metadata.json
```

## Run One Attempt

Run one attempt with:

```bash
conda run -n quant python runner.py --description "baseline"
```

The first run initializes deterministic session state from `experiment.toml`.
Subsequent runs consume one attempt each until the harness reports that the
session budget is exhausted. The exact attempt count is config/CLI state, not
LLM instruction text in `program.md`.

## Research Modes

Explore one recent primary window:

```bash
conda run -n quant python runner.py --explore --description "idea"
```

Confirm a candidate across the configured recent window bundle:

```bash
conda run -n quant python runner.py --confirm --description "candidate confirmation"
```

Run one diagnostic window without updating the best confirmed candidate:

```bash
conda run -n quant python runner.py --window-id validation_2025_h2 --description "diagnostic"
```

Confirmed candidates are scored by `candidate_score.json`; single-window scores
are exploration or diagnostic evidence.
