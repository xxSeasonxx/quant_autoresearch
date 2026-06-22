# Train Score Rationale

Active rationale for the Train scoring contract. The executable contract lives in
`protocol.toml`, `objective.py`, `gates.py`, and `loop.py`. This note explains
what the score measures and how a new session should reason about it.

## Core Decision

The Train keep-rule score is the weakest-window lower confidence bound on
deployed annualized return:

```text
score = min_w(R_w - k_rank * SE_w)
R_w = mean_return_w * P
SE_w = return_volatility_w * P / sqrt(n_eff_w)
k_rank = 1
```

`P` is the run-level `annualization_periods_per_year` emitted by the upstream
sizing report. The score uses the upstream `realistic_costs` portfolio-foundation
metrics for the full Train window and each configured subwindow.

The scored unit is the single netted-book NAV path. The per-trade tape is a
derived attribution view of that same book; inspect it for diagnostics, but do
not score a completed-trade return bag.

The score is a Train development filter, not deployability evidence. A kept
candidate is only a candidate for Season's downstream OOS, paper, and small-live
review.

## Why This Score

- **Money magnitude:** annualized return moves when the deployed book scale moves;
  scale-invariant ratios do not.
- **Weakest window:** a candidate must work across the Train path, not only in one
  favorable slice.
- **Uncertainty haircut:** each window pays for its own return uncertainty through
  upstream `return_volatility` and `effective_sample_size`.
- **Upstream accounting:** costs, fills, capacity, sizing, compounding, idle time,
  and overlapping positions stay in the runner-owned NAV path.

PSR, Sharpe, Calmar, win rate, profit factor, and sampled trades are diagnostics
only. They are not the score and are not money gates unless a protocol-owned gate
explicitly says so.

## Score Inputs

Each `realistic_costs` scoring window must provide:

- `mean_return`;
- `return_volatility`;
- `effective_sample_size`;
- `return_sample_count`;
- `closed_trade_count`;
- `max_drawdown`;
- `max_symbol_concentration`.

Missing or non-finite `mean_return`, `return_volatility`, or
`effective_sample_size` makes that window non-scoreable. Non-positive
`effective_sample_size` or zero variance also makes it non-scoreable. A
non-scoreable window yields no finite run score; it is not assigned a punitive
number.

Structural safety fields still fail closed when malformed. Counts must be
nonnegative integers, drawdown must be zero or negative, and concentration must
be in `[0, 1]`.

## Gates

The score ranks only candidates that pass all gates. Gates are binary viability
checks and do not alter the score.

The active gate set covers:

- **trade floor:** full-Train upstream `closed_trade_count`;
- **subwindow coverage:** each subwindow's upstream `closed_trade_count`;
- **minimum evidence:** return samples and effective sample size;
- **path risk:** full-Train max drawdown;
- **breadth:** upstream max symbol concentration;
- **money floor:** `min_w(R_w - k_accept * SE_w) >= min_annualized_return`;
- **cost stress retention:** cost-stress full-Train annualized return retains the
  configured fraction of realistic full-Train annualized return when realistic
  return is positive;
- **causality:** upstream evidence must be score-admissible;
- **complexity:** declared signal components and bounded params.

`k_accept` is `gates.score_haircut_se`, the operator-owned acceptance haircut for
the best-of-N Train search. It is separate from `k_rank`.

Micro causality is a bounded score-admissibility check. It can allow Train
scoring while still not being retention, paper-trade, or deployability proof.

## Results And Run Cards

`results.tsv` is the compact loop ledger. It records:

- score parts: `score`, `worst_window_id`, `deflated_money_floor`,
  `full_train_annualized_return`, `worst_window_annualized_return`,
  `cost_stress_return_retention`;
- sizing: `book_scale`, `deployed_volatility`, `max_feasible_volatility`,
  `capacity_bound`;
- diagnostics: `full_train_psr`, `worst_subwindow_psr`, `trade_count`,
  `min_subwindow_trades`, `total_return`, `max_drawdown`,
  `max_symbol_concentration`, `win_rate`, `profit_factor`, `avg_trade_net`,
  `cost_return_sum`;
- loop state: gate flags, complexity count, failure reason, best status,
  continuation, stop reason, elapsed seconds, artifact directory, and note.

Source provenance is owned by the per-attempt snapshot under `artifact_dir`, not
by inline TSV columns. The per-attempt `run_card.json` owns detailed gate
outcomes, window vectors, foundation scenario payloads, sizing, causality
evidence, and primary failure mode.

Before a structural strategy edit, inspect the latest row and run card. The score
says whether the candidate is keepable; the diagnostics should explain what to
change or whether to kill the thesis.

## Boundaries

`quant_strategies` owns portfolio construction and path statistics:

- target-book execution and NAV path semantics;
- costs, fills, funding, and execution accounting;
- book sizing and capacity envelopes;
- return moments, effective sample size, drawdown, total return, closed-trade
  count, and symbol concentration;
- realistic-cost and cost-stress scenario generation;
- causality evidence production.

`quant_autoresearch` owns loop policy:

- score calculation from upstream foundation fields;
- gate thresholds;
- keep, discard, and stop decisions;
- compact result logging and run-card emission.

Do not rebuild upstream-owned metrics from trade bags in this repo. If an
upstream metric is missing, ambiguous, non-finite, or mathematically suspect,
record the run as unavailable and fix the owning contract.
