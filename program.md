# quant_autoresearch

This file is the operating protocol for autonomous quant strategy research in
this repository.

## Objective

Think like a quant researcher. Improve the active scratch strategy under the
configured windows using causal, falsifiable changes. Optimize the guarded
score, but treat the score as loop feedback only, not market evidence.
Loop feedback only.

## Files

Read before every attempt:

- `program.md`
- `strategy.py`
- `experiment.toml`
- latest `results/` artifacts
- `results.tsv`, if present

Editable during a research loop:

- `strategy.py`
- `experiment.toml`

Read-only during a research loop:

- `program.md`
- `runner.py`
- `scoring.py`
- `experiment_config.py`
- `README.md`
- `tests/`
- `results/`
- `results.tsv`

## Evidence review

Before changing the strategy, inspect the latest artifacts and write down the
research reason for the next attempt:

- hypothesis and economic rationale
- causal timing and `as_of_time` assumptions
- falsifier
- guarded score movement
- raw net return, gross return, costs, and failed gates
- trade count and sample quality
- fill assumptions and data quality
- overfit risk and whether the change adds unjustified complexity

Do not blindly chase the last score. Use the score to compare attempts, then use
quant judgment to choose the next focused change.

## Running

Run one deterministic attempt:

```bash
conda run -n quant python runner.py --description "short attempt description"
```

The harness reports whether the session is active or exhausted. Continue making
focused research attempts while the harness reports remaining session capacity.

## Failure Attribution

If an attempt fails, attribute the root source before changing anything:

- `strategy_error`
- `config_error`
- `quant_strategies_error`
- `quant_data_error`
- `environment_error`

If the error is not from `strategy.py`, document the limitation instead of
mutating the strategy to work around it. Capture useful feedback for
`quant_strategies` or `quant_data` when those upstream systems are the source.

## Rules

- Keep `strategy.py` shaped like a normal `quant_strategies` strategy module.
- Keep strategy code pure: no data loading, runner calls, file writes,
  subprocesses, network calls, or autonomous loops.
- Edit only `strategy.py` and `experiment.toml` during research attempts.
- One attempt should test one focused change.
- A validation pass or high score is not proof of edge.
