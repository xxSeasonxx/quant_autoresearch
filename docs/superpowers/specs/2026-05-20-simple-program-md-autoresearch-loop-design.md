# Simple Program.md Autoresearch Loop Design

## Decision

Add a short `program.md` as the standing instruction file for autonomous quant
research loops.

The file should read like an operating note, not a framework. It should tell a
Codex/Claude-style agent the goal, the files, the command, the result artifacts,
and the keep/discard rules.

## Purpose

This project already has the fixed harness shape:

```text
strategy.py + experiment.yml -> runner.py -> quant_engine -> results/
```

The missing piece is the research-loop brief. Without it, an agent has no
project-local instruction for how to run one quant research attempt and report
the result.

`program.md` is not a generated prompt, strategy registry, or harness
orchestrator. It is a human-authored standing brief for the LLM.

## Scope

Add one root-level file:

```text
program.md
```

During an autonomous research loop, the agent may still edit only:

```text
strategy.py
experiment.yml
```

Harness files remain read-only during research:

```text
runner.py
prepare.py
README.md
AGENTS.md
program.md
tests/
```

Harness improvements happen outside the autonomous research loop.

## Program.md Shape

The file should stay compact and use only these sections:

```text
# quant_autoresearch

## Objective
## Files
## Experiment
## Results
## Rules
```

## Behavior Contract

One research loop means exactly one strategy/window attempt.

The agent should:

1. Read `program.md`, `AGENTS.md`, `README.md`, `experiment.yml`,
   `strategy.py`, and the latest result artifacts if present.
2. Form one causal quant hypothesis or one focused revision.
3. Edit only `strategy.py` and `experiment.yml`.
4. Run:

```bash
conda run -n quant python runner.py --max-attempts 1
```

5. Inspect the latest attempt artifacts:

```text
notes.md
screen_summary.json
validate_summary.json
evidence.json
```

6. Stop and report the hypothesis, active window, result, keep/discard
   decision, and next suggested window or idea.

## Window Protocol

`experiment.yml` carries the active window for the current loop.

The research process should test robustness sequentially across windows:

1. Primary window.
2. Alternate earlier or later window.
3. Holdout or stress window.

Only one window is run per loop. A strategy passing one window is not enough to
claim robustness.

## Quant Discipline

`program.md` should keep the LLM focused on quant research:

- Use causal signals only.
- Prefer simple hypotheses with explicit falsifiers.
- Account for transaction costs and holding period.
- Avoid overfitting one tiny or synthetic sample.
- Treat current synthetic-data results as harness evidence, not market evidence.
- Do not claim paper-trading readiness.

## Keep Or Discard

The result report should use simple labels:

```text
keep
discard
crash
```

`keep` means the attempt is worth carrying into the next window or next loop.
It does not mean the strategy has market evidence.

`discard` means the idea did not survive the current run or is too complex for
the result.

`crash` means the attempt did not produce usable artifacts.

## Non-Goals

Do not add these in this design:

- generated `next_prompt.md`
- attempt journal
- strategy registry
- strategy discovery
- autonomous mutation of harness files
- multi-window batch runner
- paper-trading approval flow

These can be designed later if the fixed harness needs them.

## Verification

Implementation should manually verify:

- `program.md` exists at the repo root.
- `program.md` names only `strategy.py` and `experiment.yml` as editable during
  research loops.
- `program.md` includes the one-attempt command.
- `program.md` states that `runner.py` and other harness files are read-only
  during research loops.
- `program.md` states that synthetic-data results are not market evidence.
- `program.md` fits on one screen in normal terminal output.
