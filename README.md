# quant_autoresearch

Local scratch workbench for one quant strategy candidate at a time.

The research loop edits only:

```text
strategy.py
experiment.toml
```

The fixed harness files are:

```text
program.md
runner.py
scoring.py
experiment_config.py
```

Strategy execution is delegated to `quant_strategies.runner.run_config`.
Generated attempt artifacts live under ignored `results/`, and the append-only
attempt ledger is ignored as `results.tsv`.

## Run One Attempt

```bash
conda run -n quant python runner.py --description "baseline"
```

The first run initializes deterministic session state from `experiment.toml`.
Subsequent runs consume one attempt each until the harness reports that the
session budget is exhausted. The exact attempt count is config/CLI state, not
LLM instruction text in `program.md`.
