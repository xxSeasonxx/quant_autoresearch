# Quant Autoresearch Cheap Guard Design

## Goal

Simplify the research loop so it stays fast enough for candidate discovery while
still protecting against obvious one-window overfit.

The workbench should no longer run the full promotion screen after every scored
explore. Instead, ordinary research should use a cheap, explicit two-window
screen:

```text
primary explore window + one fixed guard window
```

Full promotion remains available, but it should be reserved for serious
candidates that pass the cheap screen and have a clear quant rationale.

## Problem

The current promotion screen does useful work, but it is too expensive for every
iteration. A normal `runner.py --explore` can run:

- the primary recent window
- the other recent windows
- a cost-stressed primary window
- one rotating probe window

That makes each idea feel like a mini-validation suite. It reduces obvious
overfit, but it slows research and encourages fewer, heavier attempts. This
conflicts with the project target: fast iteration on candidate strategies that
will later go through comprehensive validation.

## Design Principles

- Keep the mental model simple enough for an LLM researcher to follow.
- Do not add a new framework, service layer, or validation taxonomy.
- Prefer explicit instructions in `program.md` over hidden automation.
- Keep full promotion as a deliberate escalation, not the default path.
- Preserve one independent guard during fast iteration.

## Selected Approach

Use the existing runner and promotion machinery, but change the default research
behavior:

```text
Fast research loop
  1. Run primary explore on locked_recent_2026.
  2. If the primary result is scored and plausible, run validation_2025_h1 as a
     fixed guard diagnostic.
  3. Keep iterating only from ideas that make sense on both windows.
  4. Run full promotion only for candidates worth spending time on.
```

The fixed guard should be `validation_2025_h1`.

Reasons:

- It is recent but does not overlap with `locked_recent_2026`.
- It caught failures during attempts 101-128.
- It keeps attempt-to-attempt comparisons stable.
- It avoids repeatedly optimizing against the known weak older regime
  `research_2024_h2`.

## Flow

```text
runner.py --explore
  |
  v
primary window: locked_recent_2026
  |
  +-- if not scored or obviously weak:
  |     reject/revert idea; do not spend promotion budget
  |
  v
runner.py --window-id validation_2025_h1
  |
  +-- if guard contradicts the primary result:
  |     reject/revert idea unless there is a strong quant reason to diagnose
  |
  v
candidate is eligible for full promotion consideration
  |
  v
runner.py --promote
  |
  +-- recent bundle
  +-- cost stress
  `-- rotating older probe
```

## Program Instructions

`program.md` should make the loop explicit:

- `--explore` is for fast idea discovery.
- Fast research uses a fixed guard window after a plausible primary result.
- The fixed guard is `validation_2025_h1`.
- Do not run full promotion after every small idea.
- Run full promotion only when the primary and guard results both support the
  candidate and the change has a clear quant rationale.
- Use `runner.py --promote` for the deliberate full promotion screen.
- Treat the guard as a sanity check, not a second optimizer target.
- Full promotion is still not final validation.

This language should replace any implication that every scored explore must
enter full promotion screening.

## Runner And Config Shape

Prefer the smallest implementation that supports the instruction above:

- Disable automatic full promotion on every scored explore in the active
  experiment config.
- Keep the existing `[promotion]` section for full promotion behavior.
- Add a simple explicit `--promote` runner mode. It must reuse the existing
  promotion screen implementation rather than adding a separate validation path.
- Add no new scoring framework; keep using existing `score.json`, `results.tsv`,
  and promotion artifacts.

The implementation should avoid introducing terms like "tier 1", "tier 2",
"pre-promotion", or "fast promotion" unless the code truly needs them. The user
workflow should remain:

```text
explore -> fixed guard -> --promote serious candidates
```

## Decision Rules

For the fast loop, an idea is worth continuing only when:

- the primary score is scored and directionally competitive,
- the fixed guard is positive or at least not meaningfully worse for a clear
  quant reason,
- trade count remains adequate,
- the change is coherent with the strategy hypothesis,
- complexity added is justified by evidence.

If a change wins only on `locked_recent_2026` and weakens
`validation_2025_h1`, reject it or run a targeted diagnostic before continuing.

## Non-Goals

- Do not add comprehensive validation metrics.
- Do not redesign `quant_strategies` or `quant_data`.
- Do not create a dashboard.
- Do not add parallel multi-run orchestration.
- Do not turn the guard into a parameter tuning target.
- Do not remove full promotion; make it deliberate.

## Testing

Use focused tests around the control-flow change:

- config can disable automatic promotion screening,
- ordinary explore no longer triggers full promotion when auto promotion is off,
- explicit `--promote` still runs the existing full promotion screen,
- `program.md` gives unambiguous instructions for the fast loop.

End-to-end verification should include one cheap explore plus fixed guard run,
not a full 50-attempt research session.

## Expected Outcome

Iteration time should drop substantially because most ideas run one or two
windows instead of the full promotion bundle. The process should still reject
obvious one-window overfit, while preserving full promotion for candidates that
deserve more expensive checks.
