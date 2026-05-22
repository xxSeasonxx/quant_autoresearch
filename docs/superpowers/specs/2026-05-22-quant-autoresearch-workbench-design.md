# Quant Autoresearch Workbench Design

## Decision

Adopt the core `karpathy/autoresearch` loop pattern for quant strategy
research by making `quant_autoresearch` a local scratch workbench for one
active strategy candidate at a time.

The workbench will use a fixed harness, a narrow edit scope, a guarded scalar
score, and an attempt ledger. It will delegate actual strategy execution to
`quant_strategies.runner.run_config` instead of owning a separate market-data or
evaluation engine.

## Context

Upstream autoresearch is valuable because it keeps the research loop small:
a human-authored `program.md`, a fixed harness, one editable experiment file,
one comparable metric, and keep/discard behavior over git commits.

The quant version has different domain risks. A strategy can appear to improve
because of tiny samples, fill assumptions, missing data, timing leakage, or
overfitting one window. The workbench must still optimize one number, but the
agent must inspect the evidence like a quant researcher before choosing the
next change.

`quant_strategies` already owns the canonical strategy shape and runner:
strategy modules are pure files exposing `generate_signals(bars, params)`,
configured experiments run through TOML, and generated artifacts come from
`quant_strategies.runner`.

## Goals

- Run bounded autonomous research sessions for one active strategy candidate.
- Keep the active strategy as a local scratch `strategy.py`.
- Let the loop edit only `strategy.py` and `experiment.toml`.
- Use a direct TOML config instead of a YAML wrapper.
- Optimize one guarded scalar score while requiring evidence review.
- Log every attempt and preserve runner-managed artifacts.
- Attribute failures to strategy, config, `quant_strategies`, `quant_data`, or
  environment before deciding the next action.
- Keep the exact attempt count out of `program.md`; the deterministic harness
  enforces budget.

## Non-Goals

- Do not edit `quant_strategies/untested` or `quant_strategies/tested` during
  the loop.
- Do not design paper trading, production readiness, or any downstream
  lifecycle outside this research workbench.
- Do not create strategy registries, discovery systems, generated prompts, or
  multi-strategy batch research.
- Do not duplicate the `quant_strategies.runner` data loading, fill, evidence,
  or artifact logic.
- Do not hide the evaluated strategy in an agent skill.

## Architecture

```text
quant_strategies/
  untested/            source strategy library, not edited by this loop
  tested/              outside this design
  src/quant_strategies/runner/
                       canonical execution and artifact path

quant_autoresearch/
  program.md           human-authored research protocol
  strategy.py          active scratch strategy, editable by loop
  experiment.toml      active deterministic run/search config, editable by loop
  runner.py            fixed harness, not edited by loop
  scoring.py           fixed guarded-score builder, not edited by loop
  results.tsv          untracked attempt ledger
  results/             untracked per-attempt artifacts
```

The session starts by copying or adapting one strategy candidate into local
`strategy.py`. From that point on, the loop works only against the scratch file.
The original source strategy remains unchanged.

An agent skill may document the workflow later, but it must not replace
`strategy.py` as the evaluated artifact. Real files keep diffs, runner
snapshots, manifests, scores, and git resets auditable.

## Program Protocol

`program.md` is the operating instruction for the LLM. It should describe how
to think and what evidence to inspect, not how many attempts to run.

It should require the agent to:

- Act like a quant researcher, not just a metric optimizer.
- Read `program.md`, `strategy.py`, `experiment.toml`, latest artifacts, and
  `results.tsv` before choosing the next change.
- Inspect hypothesis, causal timing, falsifier, score movement, failed gates,
  trade count, costs, fill assumptions, data quality, and overfit risk.
- Edit only `strategy.py` and `experiment.toml`.
- Continue until the deterministic harness reports the session budget is
  exhausted or a hard blocker occurs.

The exact attempt count belongs in `experiment.toml` or a CLI override such as
`python runner.py --max-attempts 24`. The runner records budget state in
deterministic artifacts such as `results.tsv` and optional `session_state.json`.

## Strategy Compatibility

`strategy.py` must be a drop-in scratch copy of a normal `quant_strategies`
strategy file. The concrete model is
`/Users/Season_Yang/Personal/quant_strategies/untested/crypto_perp_funding_crowding_reversal.py`.

Required module shape:

```python
"""Strategy rationale docstring."""

from __future__ import annotations


def generate_signals(bars, params) -> list[dict[str, object]]:
    ...
```

Compatibility rules:

- Keep the same rationale-docstring style as `quant_strategies` strategies.
- Keep the strategy pure: no data loading, runner calls, artifact writes,
  subprocesses, network calls, or autonomous loops.
- Treat `bars` as row dictionaries from the configured
  `quant_strategies.runner` data kind.
- Return signal dictionaries with `symbol`, `decision_time`, `side`, `weight`,
  `hold_bars`, and optional `as_of_time`.
- Make `experiment.toml` point active runs at local `strategy.py`.
- Use `source_strategy_path` as metadata only.

If Season pastes a strategy from `quant_strategies/untested/*.py` into
`quant_autoresearch/strategy.py` and `experiment.toml` requests the matching
data kind and fields, it should run without wrappers.

## Experiment Config

`experiment.toml` is the deterministic control plane. It contains both the
runner inputs and the research-session controls.

Expected shape:

```toml
strategy_id = "crypto_perp_funding_crowding_reversal"
strategy_path = "strategy.py"
source_strategy_path = "/Users/Season_Yang/Personal/quant_strategies/untested/crypto_perp_funding_crowding_reversal.py"
# Example session budget. The runner/config owns this value, not program.md.
max_attempts = 24

[[windows]]
id = "primary"
start = "2024-01-01"
end = "2024-01-31"

[[windows]]
id = "holdout"
start = "2024-02-01"
end = "2024-02-29"

[data]
kind = "crypto_perp_funding"
symbols = ["BTC-PERP", "ETH-PERP"]
strict = true

[params]
weight = 0.25
hold_bars = 480

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 0.0
slippage_bps_per_side = 0.0

[scoring]
metric = "net_return"
min_score_trades = 20

[output]
results_dir = "results"
mode = "validate"
```

The loop may allocate attempts dynamically across configured windows. It should
not hard-code an `8 * 3` schedule. Kept candidates must eventually be tested
against required windows before being treated as best-so-far for the session.

## Attempt Loop

Each session runs on a dedicated branch such as `autoresearch/<tag>`.

Setup:

1. Pick a run tag.
2. Create a fresh branch.
3. Populate `strategy.py` from the selected candidate.
4. Configure `experiment.toml`.
5. Run and log a baseline attempt before any strategy edit.

For each attempt:

1. Read git state, `program.md`, `strategy.py`, `experiment.toml`, latest
   artifacts, and `results.tsv`.
2. Choose one focused improvement to the signal rule, timing, filter,
   parameter, risk sizing, or window allocation.
3. Edit only `strategy.py` and/or `experiment.toml`.
4. Commit the attempted change.
5. Run one attempt through `runner.py`.
6. Write `score.json` and append one row to `results.tsv`.
7. If guarded score improves, keep the commit.
8. If score is missing, worse, or equal without meaningful simplification, reset
   to the previous kept commit after logging artifacts.
9. Continue until the deterministic attempt budget is exhausted.

No early stop:

- Bad scores do not stop the session.
- Validation failures do not stop the session.
- Insufficient sample does not stop the session.
- The session stops early only for missing data, repeated crash from the same
  root cause, invalid fixed harness configuration, user interruption, or a
  required change outside `strategy.py` and `experiment.toml`.

## Scoring

The workbench optimizes one guarded scalar.

```text
raw_metric = validation_report.screening_result.net_return
score = raw_metric only when trade_count >= min_score_trades
score = null otherwise
```

`score.json` includes:

```json
{
  "status": "scored",
  "score": 0.0123,
  "metric": "net_return",
  "raw_net_return": 0.0123,
  "gross_return": 0.018,
  "cost_return": 0.0057,
  "trade_count": 42,
  "min_score_trades": 20,
  "window_id": "primary",
  "passed_validation": true,
  "failed_gates": [],
  "failure_source": null,
  "complexity_note": "small parameter change",
  "notes": "Loop feedback only. Not market evidence."
}
```

Status values:

- `scored`: evidence exists and guarded score is numeric.
- `insufficient_sample`: evidence exists but trade count is below the scoring
  guard.
- `validation_failed`: runner completed but validation gates failed.
- `runner_failed`: config, import, data load, readiness, request build, or
  engine failure.
- `crash`: no usable artifacts were produced.

`validation_failed` can still carry a numeric guarded score when evidence exists
and `trade_count >= min_score_trades`. The status prevents confusing that loop
feedback with a validation pass.

Keep/discard rule:

- `keep`: score improves over the best kept score, or equal score with
  materially simpler strategy.
- `discard`: score is worse, missing, under-sampled, or comes from unjustified
  complexity.
- `crash`: attempt fails before usable evidence, with one obvious self-fix
  allowed.

The score is loop feedback. It is not market evidence.

## Evidence Review

After every attempt, `program.md` should force a cross-perspective review:

- Quant researcher: Is the signal causal, economically plausible, and
  falsifiable?
- Backtest skeptic: Is this a sample-size, cost, fill, timing, or data-quality
  artifact?
- Software reviewer: Did the strategy stay pure and scoped?
- Optimizer: Did the guarded score improve, and is the improvement worth the
  complexity?
- Portfolio/risk lens: Did return improve through many trades and windows, or
  through one concentrated artifact?

The next change should come from this review, not from blindly chasing the last
score.

## Failure Attribution

Every failed attempt must attribute the failure before deciding the next action.

Failure sources:

- `strategy_error`: caused by `strategy.py` logic, emitted signals, parameter
  assumptions, or field usage.
- `config_error`: caused by `experiment.toml` paths, windows, fill model,
  costs, scoring guard, or invalid runner config.
- `quant_strategies_error`: caused by runner/evaluator behavior, artifact
  contract, fill logic, readiness handling, or strategy compatibility gaps.
- `quant_data_error`: caused by missing data, loader/API limitations, strict
  window failures, source joins, stale materialization, or unavailable fields.
- `environment_error`: caused by conda, package, import, or runtime environment
  issues.

If the error is not from `strategy.py`, the loop should document the limitation
rather than mutate the strategy to work around it. Attempt artifacts should
include a short limitation note, and the session report should list upstream
feedback for `quant_strategies` or `quant_data` when relevant.

## File Contracts

`program.md`:

- Human-authored research protocol.
- No exact attempt count.
- Names the editable files and evidence-review behavior.

`strategy.py`:

- Active scratch strategy.
- Pure `generate_signals(bars, params)` module.
- Compatible with normal `quant_strategies` strategy files.

`experiment.toml`:

- Active deterministic config.
- Contains strategy path, source metadata, budget, windows, data config, params,
  fill/cost model, scoring guard, and output settings.

`runner.py`:

- Fixed harness.
- Reads `experiment.toml`.
- Materializes window-specific runner TOML for each attempt.
- Calls `quant_strategies.runner.run_config`.
- Delegates guarded scoring to `scoring.py`.

`scoring.py`:

- Fixed score builder.
- Reads `summary.json` and `evidence.json`.
- Writes `score.json`.
- Returns status for keep/discard logging.

`results.tsv`:

```text
attempt	commit	window_id	score	raw_net_return	trade_count	status	description
```

It is untracked and append-only within a session.

`results/<attempt>/`:

- Runner-managed artifacts.
- `score.json`.
- Attempt metadata and limitation notes when relevant.

## Research Boundary

The workbench is only for iterative research on one active scratch strategy.

It never claims readiness for `tested/`, production, or paper trading. Session
output is a research packet: best kept `strategy.py`, `experiment.toml`,
`results.tsv`, score history, artifacts, and upstream limitation notes. Any
later movement into another repo or workflow is outside this design.

## Verification

Implementation should verify:

- `program.md` does not expose a hard-coded attempt count.
- The only loop-editable files are `strategy.py` and `experiment.toml`.
- `results.tsv`, `results/`, and generated per-attempt configs are ignored.
- Config parsing accepts the planned `experiment.toml` shape.
- Scoring computes guarded score from runner evidence.
- Insufficient samples produce `score = null`.
- Runner attempts write `score.json` and append `results.tsv`.
- Keep/reset behavior preserves improved commits and discards non-improving
  commits after logging artifacts.
- A smoke attempt runs with a scratch strategy compatible with
  `crypto_perp_funding_crowding_reversal.py`.
