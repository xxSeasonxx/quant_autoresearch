## Why

The Train loop can now consume upstream quick-run portfolio-foundation metrics instead of scoring a bag of completed trade returns. This lets the keep rule use the `score_research.md` recommendation while keeping the run log compact enough for iteration.

## What Changes

- Add a portfolio-foundation PSR objective that computes `min(full_train_psr, min_k subwindow_psr_k)` from `RunResult.foundation`.
- Enable quick-run portfolio foundation output from protocol config and use `causality_check = "micro"` for Train iteration.
- Replace manual trade-bag cost stress with upstream `cost_stress` foundation scenario scoring.
- Extend gates to use foundation evidence for minimum return observations, effective samples, cost-stress PSR, drawdown, economic return, and symbol concentration while retaining trade floor and complexity gates.
- Keep `results.tsv` compact: provenance and lifecycle fields plus score, gate flags, foundation closed-trade count, basic economics, and a small set of portfolio-foundation metrics.
- Add a generated per-attempt run-card artifact for richer score parts, gate outcomes, warnings, and failure-mode detail.
- **BREAKING**: New `results.tsv` rows use the portfolio-foundation scoring schema and are not comparable with old trade-unit rows. A non-empty legacy ledger must start a new thesis lifecycle.

## Capabilities

### New Capabilities

### Modified Capabilities
- `autoresearch-objective-gates`: Add portfolio-foundation PSR scoring and foundation-backed gates.
- `autoresearch-protocol`: Add protocol-owned foundation output controls, PSR hurdle, gate thresholds, and micro causality support.
- `autoresearch-results`: Update the compact result-row schema and add a generated run-card artifact contract.
- `autoresearch-train-loop`: Require each successful iteration to score/gate from `RunResult.foundation` while preserving Train-only boundaries.

## Impact

- Affected code: `protocol.py`, `objective.py`, `gates.py`, `loop.py`, `results_log.py`, tests, and operating docs.
- Affected config: `protocol.toml` gains foundation/scoring/gate fields and `causality_check = "micro"`.
- Affected generated artifacts: `results.tsv` schema changes; each attempt writes a compact run card under its generated artifact directory.
- Dependency boundary remains unchanged: `quant_autoresearch` consumes only public `quant_strategies.runner.run_config` result fields.
