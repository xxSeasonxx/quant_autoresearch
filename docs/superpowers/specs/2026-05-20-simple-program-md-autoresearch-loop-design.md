# Simple Program.md Autoresearch Loop Design

## Decision

Add a short `program.md` as the standing instruction file for autonomous quant
research loops.

The file should be direct and operational. It should tell a Codex/Claude-style
agent what to read, what it may edit, how to run one attempt, how to interpret
the artifacts, and when to stop.

## Purpose

This project already has the fixed harness shape:

```text
strategy.py + experiment.yml -> runner.py -> quant_engine -> results/
```

The missing piece is the research-loop brief. Without it, an agent has no
project-local instruction for how to turn one result into the next quant
research attempt.

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

## Program.md Content

The file should stay compact and use these sections:

```text
# quant_autoresearch

## Objective
## Read First
## Editable Files
## Fixed Harness
## One-Attempt Loop
## Window Protocol
## Research Rules
## Result Review
## Stop And Report
## Forbidden Actions
```

## Behavior Contract

One research loop means exactly one strategy/window attempt.

The agent should:

1. Read `program.md`, `AGENTS.md`, `README.md`, `experiment.yml`,
   `strategy.py`, and recent result artifacts if present.
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

6. Stop and report the hypothesis, active window, result, failure mode, and
   next suggested window or idea.

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

## Testing

Implementation should verify:

- `program.md` exists at the repo root.
- `program.md` names only `strategy.py` and `experiment.yml` as editable during
  research loops.
- `program.md` includes the one-attempt command.
- `program.md` states that `runner.py` and other harness files are read-only
  during research loops.
- `program.md` states that synthetic-data results are not market evidence.

