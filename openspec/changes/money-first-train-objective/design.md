## Context

Upstream `quant_strategies` now owns book scale (risk-budget sizing). The strategy
emits a base target shape; the foundation normalizes it, applies `[risk_budget]`,
and scores one netted-book NAV path. The consumer (`quant_autoresearch`) therefore
controls only *shape*, and its job is to score that shape on deployable money.

The live score (`objective.py`) is `min_w PSR_w`, a scale-invariant ratio that
cannot see money. The foundation already serializes everything the money score
needs; the consumer just doesn't read it:

- Per window (`ReturnStatistics.payload`): `mean_return`, `return_volatility`,
  `effective_sample_size`, `sharpe`, `sharpe_standard_error`.
- Run-level (`PortfolioSizingReport.payload`, sibling to `scenarios` in
  `matrix_payload()`): `annualization_periods_per_year` (`P`), `book_scale`,
  `deployed_volatility`, `max_feasible_volatility`, `capacity_bound`.

`loop.py:_foundation_metric` keeps only `sharpe`/`sharpe_se`/`n_eff`;
`_foundation_from_result` reads `scenarios` and discards `sizing_report`.

## Goals / Non-Goals

**Goals:**
- Make the score money-denominated, gateable, and overfit-braked, while reusing the
  exact per-window evidence the loop already consumes.
- Acceptance gate carries the multiple-testing correction; ranking uses a light haircut.
- Hard cutover to the new contract with regenerated fixtures and a current `program.md`.

**Non-Goals:**
- Operator-mandate elicitation and `mandate→config` derivation (separate change).
- The return-blind `[universe] rule` resolver (separate change).
- The mandate-capacity verdict gate (its thresholds derive from the mandate).
- Making the loop *hunt* for more money — that comes from scale/capacity/breadth,
  not the scalar swap. This change only makes the score *measure* money correctly.

## Decisions

### D1 — Score: weakest-window return LCB, direct SE, no proxy
`score = min over windows of [ R_w − k_rank · SE_w ]`, windows = full Train + each
subwindow, on the `realistic_costs` scenario.
- `R_w = mean_return_w · P` (arithmetic annualization).
- `SE_w = return_volatility_w · P / √(effective_sample_size_w)` (textbook `σ/√n`,
  scaled by the same `P`, so units stay consistent with `R_w`).
- `k_rank = 1`, a code constant (ranking haircut).
- `P` is a single run-level integer applied to every window and both scenarios.

Why LCB over raw return or a ratio: at a fixed vol target, raw worst-window return
ranks almost identically to Sharpe, and a raw-return score drops the uncertainty
penalty — the worst thing to drop in a best-of-many in-sample search. The LCB keeps
money as the unit *and* folds the penalty back in. It factors as
`(uncertainty-deflated Sharpe) × (deployed volatility)`. Alternatives rejected:
raw deployed return as the score (kept only as `worst_window_annualized_return`
and per-window run-card diagnostics); any ratio (drops the deployed-vol/money
lever); `sharpe_se × vol` SE proxy (mixes per-period Sharpe SE with annualized
vol, understates SE by ≈√P).

Cross-check used as a test oracle: `SE_w = R_w / t_w` with
`t_w = sharpe_w / sharpe_se_w = Φ⁻¹(PSR_w)`, so `LCB_w = R_w · (1 − k/t_w)`. This
ties the new score to the t-stat the PSR machinery already computes.

### D2 — Deflated money floor replaces two gates
Replace `min_total_return ≥ 0` (economic-return) and `train_score_floor` with one gate:
`min over windows of [ R_w − k_accept · SE_w ] ≥ min_annualized_return`.
- `min_annualized_return = 0.10`.
- `k_accept` is an explicit protocol field `gates.score_haircut_se`, set literally
  (≈ `√(2 ln N_attempts)` ≈ `2.8` at N=50), **not** auto-derived from
  `max_iterations`, so changing the loop budget does not silently move the bar.
- Same `SE_w` as D1; only `k` differs. The drawdown gate now binds because exposure
  is deployment-scaled (kept as-is).

### D3 — Cost stress becomes money-aware return retention (full train)
`retention = R_full^cost_stress / R_full^realistic` (full-train arithmetic annualized
returns). Gate: `retention ≥ min_cost_stress_return_retention` (default `0.5`).
Positivity guard: the gate is evaluated only when `R_full^realistic > 0`; when it is
≤ 0 the candidate is economically dead and the D2 money floor is the binding kill, so
the retention ratio (sign-ambiguous) is treated as non-binding. Removes
`min_cost_stress_psr` and the PSR cost-stress scorer's gating role.

### D4 — Causality admissibility is a hard gate, coupled to the micro budget
A run whose upstream evidence is not `causality_admissible` is not a survivor. The
selected replay mode is `causality_check = "micro"`, so the protocol passes
`micro_probe_limit` and `micro_timeout_seconds` through to the quick-run config.
Micro replay can be admissible for Train scoring while still not being retention,
paper-trade, or deployability proof.

### D5 — Sample-size gates are load-bearing for the score
Because the SE haircut lets the thinnest subwindow drive the score, set
`min_effective_sample_size` and `min_trades_per_subwindow` strict enough that a
sparse slice cannot dominate through sampling noise. A window with
`return_volatility_w = 0`, `effective_sample_size_w ≤ 0`, or missing
`mean_return`/`return_volatility` yields no LCB → the run is non-scoreable
(`score = None`), mirroring today's missing-PSR semantics. No free-pass for a
zero-variance window.

### D6 — Diagnostics, surface, ledger
- PSR (and optionally Sharpe/Calmar) are still computed and emitted as diagnostics;
  they are neither the score nor a gate. Unknown `objective.kind` is rejected.
- Remove the strategy global `weight` knob and prune dead `experiment.toml` params;
  scale-search is owned upstream, so the complexity gate becomes meaningful.
- Record in run card + `results.tsv`: money score, the deflated floor value, per-window
  `R_w`, return retention, and sizing-report fields (`book_scale`, deployed &
  `max_feasible_volatility`, `capacity_bound`). Keep PSR as a diagnostic column.

## Risks / Trade-offs

- [The current sleeve fails the floor] → Expected and correct. The weakest subwindow
  sits ~0.23 SE above zero, so any real `k_accept` drives the floor negative. The
  verdict is *reseed with more breadth/leverage*, not a deployable survivor. **Do not
  weaken the score to make it pass.**
- [`k_accept` treats attempts as independent] → `√(2 ln N)` ignores attempt
  correlation (true effective-N is smaller); conservative-ish, not exact. Accepted for
  this change; honest clustering is deferred.
- [Arithmetic vs geometric annualization] → `R_w = mean·P` is arithmetic, chosen for
  exact linear consistency with `SE_w`. Over long windows this diverges from compounded
  return; acceptable because the score is a robustness-deflated comparator, not a NAV
  projection, and the foundation reports compounded `total_return` separately.
- [Micro replay budget slows iteration] → Quick-run wall-clock rises with the probe
  budget. Mitigation: stay on `causality_check = "micro"` and avoid strict/focused
  replay modes during Train iteration.
- [Hard cutover invalidates old artifacts] → No compatibility mode. Regenerate
  fixtures and artifacts; old PSR-scored run dirs are not migrated.

## Migration Plan

1. Land score + gates + protocol fields + ledger columns together.
2. Regenerate test fixtures and any golden artifacts against the new contract.
3. Update `program.md` North Star to "deployed annualized return, uncertainty-haircut,
   subject to robustness and practicality gates."
4. First real `climb` run is expected to end with no survivor on the 3-symbol universe.
5. Rollback = revert the change set; there is no dual-scoring mode.

## Open Questions

- `min_cost_stress_return_retention` default is `0.5`; confirm or tune once a
  legitimate book exists to measure against.
- `micro_probe_limit` and `micro_timeout_seconds` may need further tuning if the
  runner reports `causality_admissible = false`; strict/focused replay is not part
  of the Train iteration contract.
