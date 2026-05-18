# Loop Feedback Score Design

## Decision

Add a fixed scratchpad score artifact:

```text
score.json
```

The score lives in `quant_autoresearch`, not `quant_engine`, because it is loop
feedback for the active research workbench. It is not evidence, validation, or
promotion.

## Purpose

The loop needs one simple scalar so an LLM can compare attempts without
inventing its own objective from raw JSON.

The score must stay boring and sample-aware:

```text
raw_net_return = screen_summary.net_return
score = raw_net_return only when trade_count >= min_score_trades
```

No Sharpe, no composite score, no ranking model, and no configurable score
formula in this version. `min_score_trades` is a guardrail, not a formula.

## Boundaries

- `quant_engine` remains unchanged.
- `strategy.py` remains signal generation only.
- `experiment.yml` owns the fixed evaluation window and the minimum sample
  threshold:
  - `start`
  - `end`
  - `min_score_trades`
- `scoring.py` is fixed harness code.
- The LLM may read `score.json`, but during normal loops it may still edit only
  `strategy.py` and `experiment.yml`.

## Status Semantics

Every attempt writes `score.json`.

Statuses:

```text
build_error
  strategy, prepare, or request building failed before screen summary existed

screen_failed
  quant-engine screen could not evaluate the request

validation_failed
  quant-engine validate ran, but validate_summary.passed was false

insufficient_sample
  quant-engine produced a screen summary, but trade_count is below
  min_score_trades for the fixed evaluation window

validated
  quant-engine validate passed all gates
```

Score values:

```text
build_error         score = null
screen_failed       score = null
insufficient_sample score = null
validation_failed   score = raw_net_return
validated           score = raw_net_return
```

Failed validation still gets a numeric score because it is useful loop feedback.
The status and `passed_validation` fields prevent confusing it with success.
Insufficient sample overrides validation status for scoring, but preserves the
validation fields in `score.json`.

## Artifact Shape

Example validated attempt:

```json
{
  "status": "validated",
  "score": 0.028811764705882353,
  "metric": "net_return",
  "raw_net_return": 0.028811764705882353,
  "passed_validation": true,
  "trade_count": 42,
  "min_score_trades": 20,
  "window_start": "2024-01-01",
  "window_end": "2024-12-31",
  "failed_gates": [],
  "notes": "Loop feedback only. Not evidence or promotion."
}
```

Example failed validation:

```json
{
  "status": "validation_failed",
  "score": -0.002,
  "metric": "net_return",
  "raw_net_return": -0.002,
  "passed_validation": false,
  "trade_count": 27,
  "min_score_trades": 20,
  "window_start": "2024-01-01",
  "window_end": "2024-12-31",
  "failed_gates": ["positive_net"],
  "notes": "Loop feedback only. Not evidence or promotion."
}
```

Example insufficient sample:

```json
{
  "status": "insufficient_sample",
  "score": null,
  "metric": "net_return",
  "raw_net_return": 0.12,
  "passed_validation": true,
  "trade_count": 1,
  "min_score_trades": 20,
  "window_start": "2024-01-01",
  "window_end": "2024-12-31",
  "failed_gates": [],
  "notes": "Loop feedback only. Not evidence or promotion."
}
```

Example screen failure:

```json
{
  "status": "screen_failed",
  "score": null,
  "metric": "net_return",
  "raw_net_return": null,
  "passed_validation": false,
  "trade_count": null,
  "min_score_trades": 20,
  "window_start": "2024-01-01",
  "window_end": "2024-12-31",
  "failed_gates": [],
  "notes": "Loop feedback only. Not evidence or promotion."
}
```

## Implementation Shape

Add one fixed harness file:

```text
scoring.py
```

`scoring.py` should expose one function:

```python
def build_score(
    *,
    status: str,
    experiment: dict[str, object],
    screen_summary: dict[str, object] | None,
    validate_summary: dict[str, object] | None,
) -> dict[str, object]:
    ...
```

`runner.py` writes `score.json` after each attempt reaches a terminal status.

## Testing

Add focused tests for:

- validated attempt writes score from `screen_summary.net_return`
- validation-failed attempt writes score from `screen_summary.net_return` when
  `trade_count >= min_score_trades`
- attempt below `min_score_trades` writes `status = insufficient_sample` and
  `score = null`
- screen-failed attempt writes `score = null`
- request-build error writes `score = null`
- `score.json` includes `window_start`, `window_end`, and `min_score_trades`
- score artifact always includes the warning note
