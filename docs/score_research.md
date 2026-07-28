# Train Score Contract

This document owns the Train score semantics. The executable contract lives in
`protocol.toml`, `objective.py`, `gates.py`, and `loop.py`.

## Score

The keep-rule score is realistic-cost total return over the full Train window:

```text
score = realistic_costs.full_train.total_return
```

The score uses the upstream-sized, netted-book NAV path. It includes compounding,
idle time, overlapping positions, fills, fees, slippage, funding, capacity impact,
and realized duty cycle. A missing or non-finite full-window `total_return` makes
the attempt non-scoreable.

The ranking score is a raw point estimate — no standard-error or variance haircut is
applied to it. Robustness is enforced by the gate battery, not by deflating the
ranking, so a low-duty-cycle or capacity-relieving book is compared on the economic
return it earns over the fixed Train window rather than penalized for its higher
return variance.

Only candidates that pass every gate can become a keeper. Among those candidates,
the existing improvement rule applies:

```text
score > best_score + max(min_abs_improvement,
                         min_rel_improvement * max(1, abs(best_score)))
```

With `min_abs_improvement = 0.001`, a candidate must add more than 10 basis points
of full-window return before it replaces the survivor or resets plateau patience.

Subwindows are required diagnostics and minimum-evidence inputs. They do not enter
the ranking score.

## Train Strength

The full-Train at-risk return strength gate is:

```text
train_strength_lcb =
    full_train_at_risk_annualized_return
    - train_strength_haircut_se
      * full_train_at_risk_annualized_standard_error

pass when train_strength_lcb >= 0
```

The protocol fixes `train_strength_haircut_se = 2.0`. This is a Train development
hurdle, not statistical proof or a best-of-N correction. The hard attempt cap
bounds search effort separately.

For each window:

```text
at_risk_annualized_return = mean_return * annualization_periods_per_year
at_risk_annualized_standard_error =
    return_volatility * annualization_periods_per_year
    / sqrt(effective_sample_size)
```

The full-Train pair drives `train_strength`. Subwindow pairs are reported for
diagnosis only. Missing or non-finite moments, non-positive effective sample size,
or zero variance make an attempt non-scoreable because the required strength
diagnostics cannot be computed.

## Gates

Gates are binary viability checks. They do not alter the score:

- `trade_floor`: full-Train upstream closed-trade count;
- `minimum_evidence`: return samples and effective sample size for full Train and
  every subwindow;
- `path_risk`: full-Train maximum drawdown;
- `train_strength`: the fixed full-Train at-risk return hurdle above;
- `cost_stress_retention`: cost-stress full-Train at-risk annualized return retains
  the configured fraction of the realistic-cost value when the latter is positive;
- `breadth`: upstream economic symbol concentration;
- `causality`: upstream evidence is score-admissible;
- `complexity_cap`: declared signal components and bounded parameters.

Per-subwindow trade counts and at-risk return signs remain diagnostics. Minimum
evidence owns per-window sample sufficiency; regime independence belongs to the
firewalled downstream OOS stage.

## Diagnostics

PSR, Sharpe, Calmar, win rate, profit factor, sampled trades, book scale, deployed
volatility, target reachability, the sizing frontier, execution costs, capacity
tails, and subwindow returns explain results. They do not
replace the score or gate contract.

The per-trade tape is attribution derived from the same netted-book path. Do not
score a completed-trade return bag.

## Results And Run Cards

`results.tsv` records:

- score and strength: `score`, `train_strength_lcb`,
  `full_train_at_risk_annualized_return`, `cost_stress_return_retention`;
- sizing: `book_scale`, `deployed_volatility`, `max_feasible_volatility`,
  `target_reached`, and `max_feasible_book_scale`;
- execution: `minimum_order_notional_ratio` and `fixed_cost_share`;
- diagnostics: `full_train_psr`, `worst_subwindow_psr`, `trade_count`,
  `min_subwindow_trades`, `max_drawdown`, `max_symbol_concentration`,
  `effective_symbol_count`, `win_rate`, `profit_factor`, `avg_trade_net`, and
  `cost_return_sum`;
- attempt state: gate flags, `failure_class`, complexity count, failure reason,
  keep status, elapsed seconds, artifact directory, and note.

`score` is the ledger's single representation of full-window total return.
A nonempty `results.tsv` must use the exact current header. A header mismatch
fails closed and requires a new thesis lifecycle; an empty file initializes with
the current header on first append.

Continuation and stop reason are not attempt measurements and are not stored in
the ledger. `loop status` and the `climb` summary derive them from the immutable
rows and the currently authorized stop rules. Operator extensions are recorded in
`.autoresearch/lifecycle_events.jsonl`.

Each `run_card.json` adds:

- `full_window_total_return`;
- `train_strength_lcb`;
- `train_strength_required_annualized_sharpe`, computed from the realized full-Train
  effective sample size as `train_strength_haircut_se * sqrt(P / n_eff)`;
- `full_train_at_risk_annualized_return`;
- per-window `at_risk_annualized_return` and
  `at_risk_annualized_standard_error`;
- `cost_stress_full_window_total_return`;
- `cost_stress_full_train_at_risk_annualized_return`;
- full gate outcomes, foundation scenarios, sizing, causality, warnings, PSR
  diagnostics, and the primary failure class.

Foundation scenarios preserve the upstream MECE evidence sections:

- `execution`: event count, turnover, smallest real order, minimum-order ratio,
  proportional/fixed/impact/total costs, and fixed-cost share;
- `capacity`: participation and utilization tails, threshold exposure, peak
  event, headroom, and crossover.

A `train_strength` failure maps to `failure_class = edge_unproven`. Gate
precedence remains causality, Train strength, breadth, minimum evidence, then the
first remaining failed gate. A hard leverage-, execution-, or capacity-budget
breach is a distinct
economic verdict, not a harness error: it maps to `failure_class = infeasible`. A
harness exception maps to `run_error`, or to `foundation_unavailable` or
`score_unavailable` when it is raised while parsing or scoring the foundation. The
ledger row and run card carry the same class for an attempt.

## Ownership Boundary

`quant_strategies` owns target-book execution, the netted NAV path, costs, fills,
funding, capacity, sizing, return moments, effective sample size, total return,
drawdown, trade counts, symbol concentration, stress scenarios, and causality
evidence.

`quant_autoresearch` owns score selection, gate thresholds, keep/discard/stop
policy, compact result logging, and run-card emission. Missing or suspect upstream
metrics fail closed; this repository does not reconstruct them from trade bags.

A Train survivor is only a candidate for Season's downstream OOS, paper, and
small-live review. The score is not deployability evidence.
