## Context

`objective.py` currently scores completed trade net returns by subwindow. The upstream quick-run surface now exposes `RunResult.foundation`, a compact portfolio-foundation object with `realistic_costs` and `cost_stress` scenarios, `full_train` metrics, and per-subwindow metrics. Those records include the inputs needed for downstream PSR scoring: Sharpe, Sharpe standard error, effective sample count, sample count, skew, kurtosis, total return, drawdown, closed trades, and symbol concentration.

The active local loop logs one TSV row per attempt. That row is both human feedback and loop control state, so it should stay compact and stable. Richer evidence belongs in generated artifacts under the attempt directory.

## Goals / Non-Goals

**Goals:**
- Make the live Train score `min(full_train_psr, min_k subwindow_psr_k)` from upstream portfolio-foundation metrics.
- Use `micro` causality replay in the materialized quick-run config.
- Keep `results.tsv` useful but short: control fields, basic economic diagnostics, and the few portfolio-foundation metrics needed to explain gates.
- Emit a generated run card with detailed score parts, gate outcomes, warnings, and failure-mode context for the next edit.
- Fail clearly when foundation evidence is missing or when a non-empty legacy result ledger would mix incomparable schemas.

**Non-Goals:**
- Do not compute NAV, period returns, drawdown, effective sample size, or concentration from trade bags in `quant_autoresearch`.
- Do not add DSR, attempt count, PBO, parameter-neighborhood, or leave-one-symbol audits to the live score.
- Do not run OOS evaluation or downstream validation inside the Train loop.
- Do not make `results.tsv` a full research dashboard.

## Decisions

1. **Add a new objective kind: `portfolio_psr_subwindow`.**
   - Rationale: Existing `worst_subwindow` rows are on a different score scale and should remain understandable. A new kind makes protocol migration explicit.
   - Alternative rejected: silently change `worst_subwindow`; this would make old rows and docs misleading.

2. **Represent foundation metrics with small local dataclasses.**
   - Rationale: The loop should extract public `RunPortfolioFoundation` payloads into typed local inputs, then score/gate those. This keeps Pydantic or upstream private types out of the local boundary.
   - Alternative rejected: pass raw nested dicts through objective/gates; this makes tests and failure messages brittle.

3. **Compute PSR locally from upstream Sharpe and Sharpe SE only.**
   - Formula: `NormalDist().cdf((sharpe - hurdle) / sharpe_standard_error)`.
   - If Sharpe or SE is missing, non-finite, or SE is non-positive, the objective score is unavailable and the attempt crashes/records the failure.
   - Rationale: `quant_autoresearch` owns only lightweight scoring policy; upstream owns the portfolio path and statistics.

4. **Use upstream `cost_stress` scenario for the cost-stress gate.**
   - Rationale: Manual trade-bag cost stress duplicates execution semantics and can diverge from upstream. The cost-stress PSR should use the same foundation path semantics as the base score.

5. **Keep `results.tsv` compact with a curated metric set.**
   - Keep provenance/lifecycle fields.
   - Score/control metrics: `score`, `full_train_psr`, `worst_subwindow_psr`, `worst_subwindow_id`, `cost_stress_psr`, `gate_flags`.
   - Basic diagnostics: `total_return`, `max_drawdown`, foundation `trade_count`, `win_rate`, `profit_factor`, `avg_trade_net`, `cost_return_sum`.
   - Breadth/complexity: `max_symbol_concentration`, `complexity_count`.
   - Detailed vectors and warnings go to `run_card.json`.

6. **Treat result schema migration as a thesis-lifecycle boundary.**
   - If an existing `results.tsv` has only a header, it can be rewritten to the new header on first append.
   - If it has rows with a legacy header, reading/appending fails with a clear error requiring a new thesis lifecycle.

7. **Make `micro` an accepted causality policy.**
   - Rationale: Upstream explicitly documents `micro` as the Train/autoresearch iteration annotation. The loop should pass it through rather than forcing `off` or `focused`.

## Risks / Trade-offs

- **PSR score scale changes from trade-unit ratios to probability.** → Require new objective kind, updated docs, and new result schema.
- **Upstream foundation can be disabled or unavailable.** → Make foundation output protocol-owned and fail clearly if the result lacks foundation for the new objective.
- **More gate thresholds can feel like a dashboard.** → Keep thresholds protocol-owned and log only the binding compact metrics in `results.tsv`; preserve details in `run_card.json`.
- **Existing header-only `results.tsv` uses the old schema.** → Allow header-only replacement, but block mixed non-empty ledgers.

## Migration Plan

1. Add protocol fields and default active config for portfolio foundation, PSR hurdle, and foundation-backed gate thresholds.
2. Add scoring/gating code and tests using synthetic foundation payloads.
3. Update result-row schema, run-card writing, and header migration behavior.
4. Update README/program/spec docs to describe portfolio-foundation scoring and micro replay.
5. Run focused tests, then archive the OpenSpec change into living specs.
