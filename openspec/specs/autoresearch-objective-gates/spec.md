## Purpose

Define the Train robustness objective and binary gates used to decide whether an attempt can update the best Train survivor.
## Requirements
### Requirement: Objectives are selected by read-only protocol
The loop SHALL choose the Train robustness objective from protocol config. The agent SHALL NOT choose, change, or retry objective kinds during a thesis run.

#### Scenario: objective kind comes from protocol
- **WHEN** the protocol specifies `objective.kind`
- **THEN** the loop uses that objective implementation for all iterations in the thesis

### Requirement: Plateau improvement is mathematically defined
For completed iteration `t`, let `s_t` be its score and `b_t` be the best kept feasible score before `t`. The iteration SHALL count as an improvement only if all gates pass and `s_t > b_t + max(eps, rho * max(1, abs(b_t)))`, where `eps` and `rho` come from protocol config.

#### Scenario: tiny score movement is not improvement
- **WHEN** an iteration improves by less than both configured absolute and relative thresholds
- **THEN** it is counted as non-improving

#### Scenario: gated improvement counts
- **WHEN** an iteration passes all gates and beats the threshold
- **THEN** it resets plateau patience and becomes the new best score

### Requirement: Gates are binary and separate from the objective
The loop SHALL compute admissibility checks as binary gates. Gates SHALL NOT be blended into the objective score.

#### Scenario: failed gate prevents keep
- **WHEN** a candidate improves the objective score but fails any gate
- **THEN** it is not keepable and counts as non-improving after a feasible baseline exists

#### Scenario: subwindow coverage is a binary gate
- **WHEN** any Train subwindow has fewer completed trades than the protocol-owned subwindow trade floor
- **THEN** the subwindow coverage gate fails

### Requirement: Complexity cap limits declared components and params
The complexity gate SHALL fail when the candidate exceeds the configured maximum rationale-declared signal components or validated bounded params. Signal components SHALL be derived from `rationale.md` component headings for ordinary loop execution.

#### Scenario: complexity cap fails
- **WHEN** a candidate has more rationale-declared components or validated bounded params than allowed
- **THEN** the complexity gate fails

#### Scenario: component count comes from rationale
- **WHEN** ordinary loop execution evaluates gates
- **THEN** the component count used by the complexity gate comes from `rationale.md` `### Component:` headings

#### Scenario: missing component declarations fail before run
- **WHEN** `rationale.md` has no declared signal components for an ordinary thesis run
- **THEN** the loop rejects the attempt before quick-run materialization

### Requirement: Missing subwindow evidence is not robustness
The Train gate set SHALL reject candidates that lack the protocol-required minimum trade evidence in any configured objective subwindow.

#### Scenario: clustered trades fail coverage
- **WHEN** a candidate satisfies the aggregate trade floor but all trades are clustered in fewer than `K` configured subwindows
- **THEN** the candidate fails the subwindow coverage gate

#### Scenario: covered subwindows can pass coverage
- **WHEN** every configured objective subwindow has at least the protocol-owned minimum subwindow trade count
- **THEN** the subwindow coverage gate passes if no other gate condition fails

### Requirement: Rationale component declarations are parsed deterministically
The loop SHALL parse signal component declarations from `rationale.md` using only `### Component: <name>` headings under the `## Signal Components` section.

#### Scenario: declared components are returned
- **WHEN** `rationale.md` contains multiple `### Component: <name>` headings under `## Signal Components`
- **THEN** the parser returns those component names in document order

#### Scenario: duplicate components fail
- **WHEN** `rationale.md` declares duplicate component names after normalization
- **THEN** the parser rejects the rationale before quick-run materialization

#### Scenario: unrelated headings are ignored
- **WHEN** `rationale.md` contains `### Variant:` or other headings outside `## Signal Components`
- **THEN** those headings are not counted as signal components

### Requirement: Foundation-backed gates are binary and separate from score
For portfolio-foundation scoring, the loop SHALL compute binary gates for trade floor, subwindow closed-trade coverage, return/effective-sample evidence, the deflated money floor, cost-stress return retention, foundation symbol concentration, max drawdown, causality admissibility, and complexity cap. These gates SHALL NOT be blended into the objective score.

The deflated money floor SHALL require `min over windows of [ R_w - k_accept * SE_w ] >= min_annualized_return`, using the same per-window `R_w` and `SE_w` as the objective score and the protocol-owned acceptance haircut `k_accept`. The cost-stress return-retention gate SHALL require `R_full(cost_stress) / R_full(realistic) >= min_cost_stress_return_retention`, evaluated only when `R_full(realistic) > 0`; when `R_full(realistic) <= 0` the retention gate is non-binding because the money floor is the binding economic kill. The causality gate SHALL fail when upstream causality evidence is not score-admissible. Micro causality can be score-admissible without being retention-verified.

#### Scenario: deflated money floor fails despite positive point estimate
- **WHEN** the weakest-window point-estimate return is positive but its deflated lower bound `R_w - k_accept * SE_w` is below `min_annualized_return`
- **THEN** the money floor gate fails
- **AND** the base objective score is not changed by the failed gate

#### Scenario: weak cost-stress retention fails gate
- **WHEN** `R_full(realistic) > 0` and the cost-stress full-Train return retains less than `min_cost_stress_return_retention` of the realistic full-Train return
- **THEN** the cost-stress retention gate fails

#### Scenario: non-admissible causality fails gate
- **WHEN** the upstream causality evidence reports not score-admissible
- **THEN** the causality gate fails
- **AND** the candidate is not a survivor

#### Scenario: weak path risk fails gate
- **WHEN** the base foundation full Train max drawdown breaches the protocol-owned absolute drawdown cap
- **THEN** the path-risk gate fails
- **AND** the candidate is not keepable

### Requirement: Trade diagnostics remain diagnostic
Completed trade economics SHALL remain available for basic diagnostics such as win rate, profit factor, average trade net, and cost return sum, but trade-bag statistics SHALL NOT be used to compute the portfolio-foundation objective or foundation-backed gates.

#### Scenario: trade metrics do not override foundation score
- **WHEN** trade diagnostics are present but portfolio-foundation score inputs are unavailable
- **THEN** the loop does not compute a fallback score from trade returns

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

#### Scenario: raw deployed returns remain diagnostics
- **WHEN** an iteration records score parts
- **THEN** the result row reports `worst_window_annualized_return` for the LCB-binding `worst_window_id`
- **AND** the run card reports every window's annualized return and standard error
- **AND** raw deployed returns are diagnostics only, never the default score

#### Scenario: unknown objective kind is rejected
- **WHEN** `objective.kind` is not a supported value
- **THEN** objective evaluation fails with a clear error
