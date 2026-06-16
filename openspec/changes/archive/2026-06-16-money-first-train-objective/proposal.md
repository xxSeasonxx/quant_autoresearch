## Why

The Train loop maximizes worst-window PSR, a score built on `sharpe = mean/std`,
which is scale-invariant: scaling every position by `k` leaves the score unchanged,
so it cannot distinguish a 0.2%/yr book from a 20%/yr book of the same shape. The
loop converged on a survivor making ~0.27%/yr while deploying ~1% of its budget,
with 5–10× capacity headroom unused. Upstream now owns book scale (risk-budget
sizing shipped), so the loop controls only shape — but the score still ignores
deployed money. This change switches the loop to optimize deployable money,
uncertainty-haircut, so a Train survivor is a candidate for Season's downstream
OOS, paper, and small-live review.

## What Changes

- **BREAKING** Default objective becomes `return_lcb_subwindow`: the run score is the
  weakest-window lower bound on deployed annualized return,
  `min_w [ R_w − k_rank·SE_w ]` with `R_w = mean_return_w·P`,
  `SE_w = return_volatility_w·P/√n_eff_w`, `k_rank = 1`. PSR/Sharpe/Calmar demote to
  diagnostics. `portfolio_psr_subwindow` scoring is removed as the default contract.
- Capture the SE inputs the foundation already emits: read per-window `mean_return`
  and `return_volatility`, and read run-level `P = annualization_periods_per_year`
  from the sizing report (consumer-side only; no upstream change).
- **BREAKING** Replace the toothless `min_total_return ≥ 0` and the now-redundant
  `train_score_floor` with one deflated money floor:
  `min_w [ R_w − k_accept·SE_w ] ≥ min_annualized_return`, where
  `k_accept ≈ √(2 ln N_attempts)` is an explicit protocol field (the multiple-testing
  correction for the best-of-N search).
- Replace PSR-only cost stress with a money-aware full-train return-retention gate
  (`min_cost_stress_return_retention`).
- Make causality admissibility a hard gate and pass the micro replay budget that
  the selected `causality_check = "micro"` mode actually consumes. Micro replay
  is a Train score-admissibility check, not retention or deployability proof.
- Make `min_effective_sample_size` / `min_trades_per_subwindow` strict enough that a
  thin slice cannot drive the SE-haircut score on noise; treat a zero-variance or
  unscoreable window as non-scoreable.
- Remove the dead strategy `weight` knob and prune dead `experiment.toml` params so
  the complexity gate is meaningful (scale-search is already owned upstream).
- Record the new money/diagnostic metrics and the `PortfolioSizingReport` fields in
  the run card and `results.tsv`.

## Capabilities

### New Capabilities
<!-- none: this change modifies existing contracts only -->

### Modified Capabilities
- `autoresearch-objective-gates`: default objective becomes the money-denominated
  weakest-window return LCB; the economic-return gate becomes a deflated money floor;
  cost-stress becomes money-aware return retention; causality admissibility becomes a hard gate;
  sample-size gates become load-bearing for the score; PSR/Sharpe/Calmar become
  diagnostics.
- `autoresearch-protocol`: `objective.kind = return_lcb_subwindow`; add
  `min_annualized_return`, `gates.score_haircut_se` (`k_accept`),
  `min_cost_stress_return_retention`, and a larger micro causality replay budget; remove
  `min_total_return`, `train_score_floor`, `min_cost_stress_psr`.
- `autoresearch-results`: ledger records money score, deflated floor, deployed
  annualized return per window, return retention, sizing-report fields
  (`book_scale`, deployed/`max_feasible_volatility`, `capacity_bound`); PSR retained
  only as a diagnostic column.

## Impact

- Code: `objective.py` (new `return_lcb_subwindow` scorer, `FoundationMetric` +
  `mean_return`/`return_volatility`), `loop.py` (`_foundation_metric` reads the new
  fields, `_foundation_from_result` reads `sizing_report.annualization_periods_per_year`,
  result-row money columns), `gates.py` (money floor, retention gate, causality gate,
  stricter sample-size), `protocol.toml` (field set above), `strategy.py` +
  `experiment.toml` (drop `weight`, prune dead params), `results_log.py` (columns),
  `program.md` North Star.
- Fixtures/artifacts: regenerated against the new contract; hard cutover, no
  compatibility mode.
- Expected first outcome: the current 3-symbol funding sleeve fails the deflated
  money floor (its weakest subwindow sits ~0.23 SE above zero). That is the score
  working — the correct verdict is *reseed with more breadth/leverage*, not a
  deployable survivor. Do not weaken the score to make it pass.
- Out of scope (separate changes): operator-mandate elicitation and the
  mandate→config derivation; the return-blind `[universe] rule` resolver; the
  mandate-capacity verdict gate (its thresholds derive from the mandate).
