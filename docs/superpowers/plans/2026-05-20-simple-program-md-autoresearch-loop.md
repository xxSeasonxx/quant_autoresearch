# Simple Program.md Autoresearch Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a short root-level `program.md` that tells Codex/Claude-style agents how to run one quant autoresearch attempt.

**Architecture:** This is a static instruction-file change. `program.md` becomes the human-authored research loop brief; `AGENTS.md` remains the stricter repository contract and still controls editable files during research loops.

**Tech Stack:** Markdown, existing Python runner command, existing `conda run -n quant` environment.

---

## File Structure

- Create: `program.md`
  - Responsibility: standing operating note for one autonomous quant research loop.
- Do not modify: `runner.py`, `prepare.py`, `README.md`, `AGENTS.md`, `tests/`, `results/`
  - Reason: harness changes are outside this feature and outside autonomous research loops.
- Do not stage unrelated existing changes in `strategy.py` or `experiment.yml`
  - Reason: those files are already dirty and are not part of this plan.

## What Already Exists

- `AGENTS.md` already defines the hard editable-file boundary: research loops may edit only `strategy.py` and `experiment.yml`.
- `README.md` already documents the fixed harness shape and run command.
- `runner.py` already snapshots strategy/config through `quant_strategies.runner.run_config` and writes attempt artifacts.
- `docs/superpowers/specs/2026-05-20-simple-program-md-autoresearch-loop-design.md` defines the approved `program.md` content constraints.

## NOT In Scope

- Runner changes: harness improvements happen outside the research loop.
- Generated `next_prompt.md`: useful later, not needed for the simple v1.
- Attempt journal: extra mutable state would weaken the two-file research boundary.
- Strategy registry or discovery: explicitly against repo rules.
- Batch multi-window runner: v1 uses one window per loop.
- Automated tests for wording: manual verification is enough for a static instruction file.

## Data Flow

```text
agent reads program.md
        |
        v
edits strategy.py + experiment.yml only
        |
        v
conda run -n quant python runner.py --max-attempts 1
        |
        v
results/<attempt>/ artifacts
        |
        v
agent reports keep / discard / crash
```

## Task 1: Add The Operating Brief

**Files:**
- Create: `program.md`
- Verify: `program.md`

- [ ] **Step 1: Create `program.md`**

Create `program.md` with exactly this content:

````markdown
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

Inspect the latest attempt artifacts: `notes.md`, `summary.json`,
`run_manifest.json`, `data_manifest.json`, and `evidence.json` if present.

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
````

- [ ] **Step 2: Verify the file exists**

Run:

```bash
test -f program.md && echo "program.md exists"
```

Expected:

```text
program.md exists
```

- [ ] **Step 3: Verify the edit boundary is explicit**

Run:

```bash
rg -n "edit only: `strategy.py`, `experiment.yml`|Do not edit: `runner.py`" program.md
```

Expected: the command prints lines for both the editable files and the read-only harness files.

- [ ] **Step 4: Verify the one-attempt command is present**

Run:

```bash
rg -n "conda run -n quant python runner.py --max-attempts 1" program.md
```

Expected: the command prints the one-attempt runner command.

- [ ] **Step 5: Verify market-evidence limits are explicit**

Run:

```bash
rg -n "not proof of market edge|not market evidence|Do not claim market evidence or paper-trading readiness" program.md
```

Expected: the command prints all market-evidence guardrails.

- [ ] **Step 6: Verify the file stays compact**

Run:

```bash
lines=$(wc -l < program.md | tr -d ' ')
test "$lines" -lt 80 && echo "program.md is compact: $lines lines"
```

Expected: output like:

```text
program.md is compact: 54 lines
```

- [ ] **Step 7: Check markdown whitespace**

Run:

```bash
git diff --check -- program.md
```

Expected: no output.

- [ ] **Step 8: Review the final diff**

Run:

```bash
git diff -- program.md
```

Expected: diff shows only the new `program.md` file.

- [ ] **Step 9: Commit only `program.md`**

Run:

```bash
git add program.md
git commit -m "Add simple autoresearch program"
```

Expected: commit succeeds and does not include the pre-existing `strategy.py` or `experiment.yml` changes.
