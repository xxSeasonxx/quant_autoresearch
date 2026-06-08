# OOS Drift Review

Use this template only after a frozen Train survivor exists. This is a one-look downstream review owned by Season. It is not an active-loop input. The OOS result MUST NOT be used to tune the same candidate's strategy, params, protocol, or rationale.

## Candidate Identity

| Field | Value |
|---|---|
| Run ID |  |
| Train artifact path |  |
| Strategy SHA-256 |  |
| Experiment SHA-256 |  |
| Protocol SHA-256 |  |
| Rationale SHA-256 |  |
| Review date |  |
| Reviewer | Season |

## Train Evidence

| Field | Value |
|---|---|
| Train score |  |
| Gates |  |
| Subwindow trade counts |  |
| Trade count |  |
| Net-return contribution concentration |  |
| Cost-stress score |  |
| Net return sum |  |
| Average trade net |  |
| Profit factor |  |
| Stop reason |  |

## OOS Evidence

| Field | Value |
|---|---|
| OOS command / artifact path |  |
| OOS window |  |
| OOS score |  |
| Gates |  |
| Trade count |  |
| Net-return contribution concentration |  |
| Cost-stress score |  |
| Return / drawdown summary |  |
| Execution or data caveats |  |

## Drift

| Comparison | Value |
|---|---|
| Score delta / ratio |  |
| Trade-count drift |  |
| Net-return contribution concentration drift |  |
| Cost-stress drift |  |
| Return / drawdown drift |  |
| New failure mode observed |  |

## Decision

Decision: `discard | reseed thesis | paper test | small-live candidate`

Reason:

## Guardrail

This OOS result is a scarce downstream screen. It is not an optimization target. If it fails, do not tune this same candidate against the OOS window; discard, reseed, or start a distinct thesis.
