# quant_autoresearch

This is an experiment to have an LLM do quant research inside a fixed harness.

## Setup

Read the in-scope files before each research attempt:

- `program.md` - this loop brief
- `AGENTS.md` - hard repository rules
- `README.md` - harness shape and run command
- `experiment.yml` - active parameters and window
- `strategy.py` - the strategy under test
- latest `results/` attempt, if present

Check `git status --short` and note any dirty files before editing. Existing
dirty files may belong to the user; do not overwrite or revert them.

## Experimentation

One loop means one strategy/window attempt.

What you can edit during a research loop:

- `strategy.py`
- `experiment.yml`

What you cannot edit during a research loop:

- `runner.py`
- `prepare.py`
- `README.md`
- `AGENTS.md`
- `program.md`
- `tests/`
- `results/`

Harness improvements happen outside research loops.

The goal is simple: find plausible causal strategy candidates that pass the
fixed harness for the active window. A run is not proof of market edge.

Use simple, falsifiable ideas. Account for timing, costs, holding period, and
the active window. Do not add registries, discovery, generated prompts, batch
runners, new dependencies, or paper-trading approval.

## Running

Run exactly one attempt:

```bash
conda run -n quant python runner.py --max-attempts 1
```

Then inspect the latest attempt under `results/`:

- `notes.md`
- `screen_summary.json`
- `validate_summary.json`
- `evidence.json`, if present

Key fields are `passed`, `failed_gates`, `trade_count`, `gross_return`,
`net_return`, and `cost_return`.

## Logging

At the end of each loop, keep one compact result row for the final response:

```text
window status net_return trade_count failed_gates description
```

Use these statuses:

- `keep` - worth carrying to the next window or next loop
- `discard` - failed, overfit, or too complex for the result
- `crash` - did not produce usable artifacts

`keep` does not mean market evidence. It only means the candidate is worth
testing again.

## Loop

1. Look at git state and the latest result.
2. Pick one causal hypothesis or one focused revision.
3. Edit only `strategy.py` and `experiment.yml`.
4. Run the one-attempt command.
5. Read the attempt artifacts.
6. Report the result row and a short explanation.
7. Decide the next loop.

Continue looping until Season stops you, the harness needs changes outside the
editable files, or the next useful action is unclear.

Window ladder: primary -> alternate earlier/later -> holdout/stress.
Run one window per loop. Passing one window is not robustness.

If the run crashes because of a simple mistake, fix your own mistake and rerun
once. If it still crashes, report `crash` and stop.

If the result is `keep`, continue with the next window in the ladder. If all
windows keep, report the candidate as worth deeper review, not as proven alpha.
If the result is `discard`, continue with a new simple hypothesis.

Do not claim market evidence, robustness, or paper-trading readiness from the
current synthetic harness.
