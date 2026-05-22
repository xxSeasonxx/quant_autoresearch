# quant_autoresearch

Local scratch workbench for one quant strategy candidate at a time.

The research loop edits only:

```text
strategy.py
experiment.toml
```

The planned fixed harness for this workbench is:

```text
program.md
runner.py
scoring.py
experiment_config.py
```

Task 1 establishes the scaffold and protocol; later implementation tasks add
the runnable harness files that are not present yet in a fresh Task 1 checkout.

Strategy execution is delegated to `quant_strategies.runner.run_config`.
Generated attempt artifacts live under ignored `results/`, and the append-only
attempt ledger is ignored as `results.tsv`.

## Run One Attempt

Once the runner harness is present, run one attempt with:

```bash
conda run -n quant python runner.py --description "baseline"
```

The first run initializes deterministic session state from `experiment.toml`.
Subsequent runs consume one attempt each until the harness reports that the
session budget is exhausted. The exact attempt count is config/CLI state, not
LLM instruction text in `program.md`.
