## ADDED Requirements

### Requirement: Default objective scores the weakest-window deployed-return lower bound
The objective layer SHALL support `objective.kind = "return_lcb_subwindow"` as the default Train objective. For this kind, over windows = full Train plus every configured subwindow on the upstream `realistic_costs` scenario, the run score SHALL be `min over windows of [ R_w - k_rank * SE_w ]`, where `R_w = mean_return_w * P`, `SE_w = return_volatility_w * P / sqrt(effective_sample_size_w)`, `k_rank = 1`, and `P` is the run-level `annualization_periods_per_year` read from the sizing report and applied to every window. The score SHALL move when deployed return moves; a scale-invariant ratio SHALL NOT be the default objective.

#### Scenario: score equals the weakest-window lower bound
- **WHEN** one window has the lowest `R_w - SE_w` among full Train and all subwindows
- **THEN** the objective score equals that window's `R_w - SE_w`
- **AND** the objective exposes that window id as the worst window id

#### Scenario: scaling deployed return moves the score
- **WHEN** the same shape is scored at a larger deployed annualized return
- **THEN** the objective score increases
- **AND** an equal-shape book at a smaller deployed return scores lower

#### Scenario: SE comes directly from per-window fields
- **WHEN** the loop computes `SE_w`
- **THEN** it uses `return_volatility_w * P / sqrt(effective_sample_size_w)` from per-window foundation fields
- **AND** it does NOT approximate the SE as `sharpe_standard_error * volatility`

#### Scenario: unscoreable window makes the run non-scoreable
- **WHEN** any full Train or subwindow has missing `mean_return` or `return_volatility`, non-finite values, `effective_sample_size_w <= 0`, or `return_volatility_w == 0`
- **THEN** the objective score is unavailable
- **AND** the run is non-scoreable rather than assigned a finite score

#### Scenario: raw return remains an undeflated diagnostic
- **WHEN** `return_subwindow` is computed
- **THEN** it reports the weakest-window point-estimate deployed return with no uncertainty haircut
- **AND** it is a diagnostic only, never the default score

#### Scenario: unknown objective kind is rejected
- **WHEN** `objective.kind` is not a supported value
- **THEN** objective evaluation fails with a clear error

## MODIFIED Requirements

### Requirement: Foundation-backed gates are binary and separate from score
For portfolio-foundation scoring, the loop SHALL compute binary gates for trade floor, subwindow closed-trade coverage, return/effective-sample evidence, the deflated money floor, cost-stress return retention, foundation symbol concentration, max drawdown, causality verification, and complexity cap. These gates SHALL NOT be blended into the objective score.

The deflated money floor SHALL require `min over windows of [ R_w - k_accept * SE_w ] >= min_annualized_return`, using the same per-window `R_w` and `SE_w` as the objective score and the protocol-owned acceptance haircut `k_accept`. The cost-stress return-retention gate SHALL require `R_full(cost_stress) / R_full(realistic) >= min_cost_stress_return_retention`, evaluated only when `R_full(realistic) > 0`; when `R_full(realistic) <= 0` the retention gate is non-binding because the money floor is the binding economic kill. The causality gate SHALL fail when the upstream causality verification did not verify.

#### Scenario: deflated money floor fails despite positive point estimate
- **WHEN** the weakest-window point-estimate return is positive but its deflated lower bound `R_w - k_accept * SE_w` is below `min_annualized_return`
- **THEN** the money floor gate fails
- **AND** the base objective score is not changed by the failed gate

#### Scenario: weak cost-stress retention fails gate
- **WHEN** `R_full(realistic) > 0` and the cost-stress full-Train return retains less than `min_cost_stress_return_retention` of the realistic full-Train return
- **THEN** the cost-stress retention gate fails

#### Scenario: unverified causality fails gate
- **WHEN** the upstream causality verification reports not verified
- **THEN** the causality gate fails
- **AND** the candidate is not a survivor

#### Scenario: weak path risk fails gate
- **WHEN** the base foundation full Train max drawdown breaches the protocol-owned absolute drawdown cap
- **THEN** the path-risk gate fails
- **AND** the candidate is not keepable

## REMOVED Requirements

### Requirement: Portfolio foundation PSR objective scores full Train and weakest subwindow
**Reason**: PSR is built on `sharpe = mean/std`, which is scale-invariant and cannot see deployed money; it converged the loop on a survivor that returned ~0.27%/yr while deploying ~1% of budget.
**Migration**: Use `objective.kind = "return_lcb_subwindow"` (weakest-window deployed-return lower bound). PSR is retained only as a diagnostic, never as the score.

### Requirement: PSR uses protocol-owned hurdle
**Reason**: The PSR hurdle parameterized the scale-invariant score that is no longer the objective.
**Migration**: PSR is diagnostic-only; `objective.psr_hurdle_sharpe` parameterizes the diagnostic PSR, not the run score. The money floor (`min_annualized_return`, `k_accept`) is the economic acceptance bar.
