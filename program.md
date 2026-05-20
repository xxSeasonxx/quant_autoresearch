# quant_autoresearch

## Objective

Find plausible quant strategy candidates in the fixed harness. A run is evidence
for one window, not proof of market edge.

## Files

Read `program.md`, `AGENTS.md`, `README.md`, `experiment.yml`, `strategy.py`,
and the latest `results/` attempt.

During research loops, edit only: `strategy.py`, `experiment.yml`.

Do not edit: `runner.py`, `prepare.py`, `README.md`, `AGENTS.md`, `program.md`,
`tests/`, or `results/`.

Harness improvements happen outside research loops.

## Experiment

One loop = one strategy/window attempt.

Pick one causal hypothesis or focused revision. Use `experiment.yml` for active
parameters and the active window.

Run:

```bash
conda run -n quant python runner.py --max-attempts 1
```

Window ladder: primary -> alternate earlier/later -> holdout/stress. Run one
window per loop. Passing one window is not robustness.

## Results

Inspect the latest attempt artifacts: `notes.md`, `screen_summary.json`,
`validate_summary.json`, and `evidence.json` if present.

Report: hypothesis, active window, `keep`/`discard`/`crash`, what passed or
failed, and next window or idea.

`keep` means worth carrying forward, not market evidence. `discard` means failed
or too complex for the result. `crash` means no usable artifacts.

## Rules

Use causal signals only.
Keep the strategy simple and falsifiable.
Account for costs, timing, and holding period.
Do not overfit tiny or synthetic samples.
Do not claim market evidence or paper-trading readiness.
Do not add registries, discovery, generated prompts, or batch runners.
