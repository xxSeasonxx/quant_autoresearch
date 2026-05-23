# Quant Autoresearch Promotion Screen Design

## Objective

Improve `quant_autoresearch` as a fast quant candidate research workbench while
keeping the simplicity of the original `autoresearch` idea: one scratch
strategy, a small fixed harness, compact artifacts, and clear loop feedback.

This repo is not the final validation framework. Its target is to iterate on
candidate strategies quickly, run a compact promotion screen for candidates
that produce valid evidence, and send only promoted candidates to a separate,
more comprehensive validation process.

## Context

The current process already has useful guardrails:

- `strategy.py` and `experiment.toml` are the editable research surface.
- `runner.py`, `scoring.py`, and `experiment_config.py` form a fixed harness.
- Single-window exploration is separated from multi-window confirmation.
- Candidate scoring uses recent-window evidence, dispersion penalties, sample
  gates, and symbol-concentration penalties.
- Artifacts record enough detail to inspect trade attribution and failures.

The main remaining weakness is incentive alignment. The current auto-confirm
path triggers from primary-window improvement, which can still make the primary
recent window the optimizer target. A candidate that is slightly worse on the
primary window but more robust across costs, recent windows, or a known weak
regime may be missed.

## Chosen Approach

Use a compact promotion screen after every scored explore.

```text
explore
  |
  +-- invalid / crash / insufficient trades
  |     `-- discard or fix the local issue
  |
  `-- scored attempt
        `-- promotion screen
              +-- fixed recent core
              +-- realistic cost stress
              +-- rotating regime probe
              `-- promoted / not promoted
```

The key rule is that a scored explore can enter promotion screening even when
its primary-window score is worse than the best current primary-window score.
Promotion is based on compact robustness, not on winning one window.

Terminology should stay explicit:

- `explore`: fast single-window idea feedback.
- `promotion screen`: compact robustness filter inside this workbench.
- `promoted candidate`: strong enough to export to comprehensive validation.
- `validated strategy`: out of scope for this repo.

## Non-Goals

- Do not turn this repo into the comprehensive validation stack.
- Do not run every possible validation test inside each research attempt.
- Do not add a dashboard or broad workflow UI.
- Do not redesign `quant_strategies`, fill models, data loaders, drawdown
  accounting, margin, leverage, capacity, or portfolio construction here.
- Do not rewrite `program.md` wholesale; keep its current working protocol and
  update it only where promotion terminology changes agent behavior.

## Promotion Bundle

The promotion screen should be compact and repeatable.

```text
promotion screen
  +-- fixed recent core
  |     +-- validation_2025_h1
  |     +-- validation_2025_h2
  |     `-- locked_recent_2026
  |
  +-- realistic cost stress
  |     `-- same candidate under configured nonzero fee/slippage
  |
  `-- rotating regime probe
        `-- one older or known-weak window per attempt
```

The fixed recent core gives comparability across candidates. The cost stress
prevents zero-cost artifacts from being promoted as robust candidates. The
rotating regime probe reveals overfit and regime fragility without making old
regimes dominate the workbench objective.

The rotating probe should advance deterministically through configured probe
windows stored in session state. This keeps the loop reproducible and prevents
the agent from repeatedly optimizing against the same diagnostic slice.

## Promotion Decision

Promotion status should be simple, inspectable, and conservative:

- Promote if the recent core improves the best promoted candidate score.
- Promote an equal or near-equal candidate only when it is materially simpler.
- Reject if any recent core window fails validation gates or is materially weak.
- Reject if the cost stress destroys the edge beyond a configured tolerance.
- Flag a weak rotating probe as regime risk; reject only if the probe is deeply
  negative or violates a configured hard floor.
- Never call a promoted candidate validated. Promotion means ready for
  comprehensive validation.

The candidate score should remain mostly recent-window strength. Robustness
checks should act as gates and penalties rather than a large opaque composite
metric.

## Configuration

Add a focused `[promotion]` section to `experiment.toml` rather than expanding
the existing `[research]` section until it becomes ambiguous.

```toml
[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = [
  "validation_2025_h1",
  "validation_2025_h2",
  "locked_recent_2026",
]
rotating_probe_window_ids = [
  "stress_2022_deleveraging",
  "stress_2022_ftx",
  "recovery_2023_h1",
  "research_2024_h1",
  "research_2024_h2",
]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
```

The implementation plan should choose concrete defaults before coding. The
illustrative values above encode the intended scale and behavior:

- Recent core dominates promotion.
- Cost stress must be nonzero and visible.
- Rotating probes are diagnostic with a hard floor.
- Simpler candidates may be promoted when score is effectively tied.

## Runner Flow

`runner.py --explore` should keep its fast first step, then run promotion only
when the explore result is scored.

```text
runner.py --explore
  +-- run primary window
  +-- build per-window score
  +-- if not scored: finish as rejected explore
  `-- if scored: run promotion screen
        +-- run recent core windows
        +-- run cost stress
        +-- choose next rotating probe from session state
        +-- build promotion_score.json
        +-- update best_promoted_* only if promoted
        `-- append one ledger row with promotion fields
```

Manual diagnostic runs should remain possible through `--window-id`. Explicit
confirmation or promotion commands may exist if useful, but the default research
loop should not require the agent to decide whether a valid scored explore
deserves a robustness check.

## Artifacts

Promotion should write grouped candidate artifacts:

```text
results/promotion_<attempt>_<strategy_id>/
  promotion_score.json
  promotion_summary.json
  trade_attribution.json
  windows/
    <window_id>/
      <attempt_artifacts>
  cost_stress/
    <stress_id>/
      <attempt_artifacts>
  rotating_probe/
    <window_id>/
      <attempt_artifacts>
```

The artifact policy should remain compact by default. Research runs should keep
strategy snapshots, configs, summaries, evidence, and signals, while omitting
large debug input-row artifacts unless a debug profile is requested.

## Session State

Session state should track only the fields needed to preserve deterministic
research behavior:

```text
best_promoted_score
best_promoted_commit
rotating_probe_index
last_promotion_decision
```

Existing best-score fields may remain for compatibility, but the workbench
should present promoted-candidate state as the meaningful best-so-far result.

## Ledger

`results.tsv` should keep its append-only role and add promotion-facing fields:

```text
promotion_decision
promotion_score
recent_mean_score
worst_recent_score
score_dispersion
cost_stress_score
cost_stress_ratio
rotating_probe_window_id
rotating_probe_score
promoted_commit
```

The ledger should stay easy to scan. It should record enough to understand why a
candidate was promoted or rejected without requiring immediate artifact digging.

## Program Protocol

`program.md` should remain a simple quant-research operating guide. It should
not become a full scoring specification or duplicate every config option.

Targeted wording changes should say:

- This workbench is for fast candidate generation.
- Promotion screening is a compact robustness filter, not final validation.
- Every scored explore enters promotion screening when promotion is enabled.
- A candidate can deserve promotion screening even when it does not beat the
  primary window.
- Do not chase one-window wins.
- Prefer simple robust candidates over complex fragile ones.
- Send promoted candidates to comprehensive validation before treating them as
  deployable evidence.

The current `program.md` structure should otherwise be preserved.

## Repo Guidance

Create a repo-local `AGENTS.md` because this repo currently lacks one. It should
document the target of the project, not replace `program.md`.

The repo-local `AGENTS.md` should state:

```text
This repo is a fast quant candidate research workbench.
It is not the final validation framework.
The goal is to iterate on one scratch strategy, run compact promotion
screening, and send only promoted candidates to comprehensive validation.
```

It should also point agents to `program.md` for the research-loop protocol and
to `README.md` for the file-contract summary.

## Error Handling

Error handling should stay conservative:

- If explore fails because of `strategy.py` or `experiment.toml`, fix only the
  focused local issue.
- If explore fails because of data, environment, or the upstream runner, record
  the limitation instead of contorting the strategy.
- If a promotion window fails due to data, environment, or harness issues, mark
  promotion inconclusive unless enough valid windows remain by configured rule.
- If cost stress or rotating probe failure is caused by the candidate, reject or
  flag according to gate severity.

## Testing

Focused tests should cover:

- Config parsing and validation for `[promotion]`.
- Scored explore auto-runs the promotion screen.
- Non-scored explore does not spend the promotion bundle.
- Primary-window underperformance can still promote when the bundle is strong.
- Rotating probe advances deterministically through session state.
- Cost stress affects promotion decisions.
- Promotion artifacts are grouped and compact.
- `results.tsv` records promotion fields.
- `AGENTS.md` and `program.md` contain the expected project-purpose language.

## Migration

Implementation should preserve existing result artifacts and ledger rows. New
session-state fields should default cleanly when absent, so old research
sessions remain readable.

Existing confirmation concepts may be retained internally if that reduces code
churn, but user-facing terminology should move toward promotion screening.
