## 1. Capture SE inputs from the foundation (A1)

- [x] 1.1 Add `mean_return` and `return_volatility` fields to `FoundationMetric` in `objective.py`; keep `sharpe`/`sharpe_standard_error`/`effective_sample_size`.
- [x] 1.2 Read `mean_return` and `return_volatility` per window in `loop.py:_foundation_metric`; extend `_validate_foundation_metric` (volatility ≥ 0).
- [x] 1.3 Read run-level `P = sizing_report.annualization_periods_per_year` in `loop.py:_foundation_from_result` and thread it onto `FoundationEvidence`/`FoundationScenario` so scoring can read it.
- [x] 1.4 Verify: a quick-run `run_card` surfaces `mean_return`, `return_volatility`, and `P` per window (smoke assertion against a captured payload).

## 2. Money-first score (A2)

- [x] 2.1 Implement `return_lcb_subwindow` in `objective.py`: `score = min_w [ R_w - k_rank*SE_w ]`, `R_w = mean_return_w*P`, `SE_w = return_volatility_w*P/sqrt(n_eff_w)`, `k_rank = 1`; expose worst-window id and per-window `R_w`.
- [x] 2.2 Record raw deployed-return diagnostics as `worst_window_annualized_return` and per-window run-card vectors; keep PSR/Sharpe/Calmar as diagnostics; reject unknown `objective.kind`.
- [x] 2.3 Handle non-scoreable windows: missing/non-finite `mean_return`/`return_volatility`, `n_eff ≤ 0`, or `return_volatility == 0` → `score=None`, non-scoreable run.
- [x] 2.4 Unit tests (`tests/test_portfolio_foundation_scoring.py`): score = weakest-window LCB at `k_rank=1`; scaling deployed return moves the score; cross-check `LCB_w = R_w·(1 − k/t_w)` with `t_w = Φ⁻¹(PSR_w)`; SE is direct (not the `sharpe_se×vol` proxy); zero-variance/unscoreable window → non-scoreable.

## 3. Money-aware gates (A3)

- [x] 3.1 Add deflated money floor gate in `gates.py`: `min_w [ R_w - k_accept*SE_w ] >= min_annualized_return`; replace `economic_return` (`min_total_return`) and remove `train_floor`.
- [x] 3.2 Add cost-stress return-retention gate: `R_full(cost_stress)/R_full(realistic) >= min_cost_stress_return_retention`, evaluated only when `R_full(realistic) > 0`; remove the `cost_stress` PSR gate.
- [x] 3.3 Add causality hard gate: fail when upstream causality evidence is not score-admissible.
- [x] 3.4 Tighten sample-size gates so a thin slice cannot drive the SE-haircut score; confirm `min_effective_sample_size`/`min_trades_per_subwindow` bind in tests.
- [x] 3.5 Gate tests: money floor fails with positive point estimate but deflated LCB below hurdle; retention fails / is non-binding when `R_full(realistic) ≤ 0`; non-admissible causality fails; gate failure does not change the score.

## 4. Protocol wiring (A4)

- [x] 4.1 `protocol.toml`: set `[objective].kind = "return_lcb_subwindow"`; add `gates.min_annualized_return = 0.10`, `gates.score_haircut_se` (`k_accept` ≈ 2.8), `gates.min_cost_stress_return_retention = 0.5`; remove `min_total_return`, `train_score_floor`, `min_cost_stress_psr`.
- [x] 4.2 Pass the micro causality replay budget in `[output]` (`micro_probe_limit`, `micro_timeout_seconds`) and gate on upstream `causality_admissible`, not retention verification. Keep Train iteration on `causality_check = "micro"`; do not require strict/focused replay for scoring.
- [x] 4.3 Update `protocol.py` loader + `GateConfig`/`ObjectiveConfig`: validate new fields (finite, ranges), drop removed fields, document `sqrt(2 ln N)` guidance near `score_haircut_se`.
- [x] 4.4 Verify: an end-to-end `climb` run scores and gates under the new contract; PSR remains computed as a diagnostic only. (Verified via fake-runner `run_iteration` integration tests; a real `climb` is 8.2.)

## 5. Prune strategy surface (D1)

- [x] 5.1 Remove the global `weight` knob from `strategy.py` and its bounds/entry in `experiment.toml`; confirm deployed weights are unchanged by any residual magnitude (scale-search-is-dead invariant test).
- [x] 5.2 Prune dead `experiment.toml` params the strategy does not read; confirm the complexity gate is now meaningful and the strategy still runs.

## 6. Ledger (D2)

- [x] 6.1 Update `results_log.py` columns to the new compact metric set (money score parts, sizing-report fields, return retention; PSR demoted to diagnostic columns); update the stable header.
- [x] 6.2 Update the run-card writer to record money-score parts, per-window deployed-return stats, and the `PortfolioSizingReport` fields.
- [x] 6.3 Update `climb` row printing to mirror the new fields; result-row reader validation covers the new columns.

## 7. Cutover + docs (D3)

- [x] 7.1 Regenerate test fixtures / golden artifacts against the new contract; no compatibility mode (hard cutover).
- [x] 7.2 Update `program.md` North Star to "deployed annualized return, uncertainty-haircut, subject to robustness and practicality gates"; remove magnitude-blind / "size is not alpha" framing.
- [x] 7.3 Update the owning docs (`objective.py`/`gates.py` module docstrings) to the money-first contract; move durable rationale to `HISTORY.md`.

## 8. End-to-end verification

- [x] 8.1 Run `pytest tests/` green.
- [x] 8.2 Run a real `climb` on the 3-symbol universe; confirm the expected outcome — the sleeve fails the deflated money floor (no survivor) — and the verdict reads as *reseed with more breadth/leverage*. Do not weaken the score to make it pass. **Confirmed (attempt-0001, 166s):** `discard`, `primary_failure_mode=money_floor`; deflated money floor `-0.51` vs `0.10` hurdle and score `-0.15` while diagnostic `full_train_psr=0.95`; `capacity_bound=true`, `deployed_volatility=0.026 == max_feasible_volatility`, `book_scale=0.06`. The money score correctly kills an under-deployed book the PSR score would have kept.
