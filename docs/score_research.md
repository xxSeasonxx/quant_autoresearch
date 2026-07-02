# Train Score Rationale

Active rationale for the Train scoring contract. The executable contract lives in
`protocol.toml`, `objective.py`, `gates.py`, and `loop.py`. This note explains
what the score measures and how a new session should reason about it.

## Core Decision

The Train keep-rule score is the full-Train deflated lower confidence bound on
deployed annualized return:

```text
score = R_full - k_rank * SE_full
R_full = mean_return_full * P
SE_full = return_volatility_full * P / sqrt(n_eff_full)
k_rank = 1
```

`P` is the run-level `annualization_periods_per_year` emitted by the upstream
sizing report. The score uses the upstream `realistic_costs` portfolio-foundation
metrics for the full Train window. Each configured subwindow is measured the same
way and reported as a regime-stability diagnostic, but the score and the
significance gate bind on the full-Train window — the most-sampled, tightest-SE
instrument — not on the noisiest short subwindow.

The scored unit is the single netted-book NAV path. The per-trade tape is a
derived attribution view of that same book; inspect it for diagnostics, but do
not score a completed-trade return bag.

The score is a Train development filter, not deployability evidence. A kept
candidate is only a candidate for Season's downstream OOS, paper, and small-live
review.

## Why This Score

- **Money magnitude:** annualized return moves when the deployed book scale moves;
  scale-invariant ratios do not.
- **Full-Train window:** the score binds on the full Train window (most samples,
  tightest SE); per-subwindow returns are reported as a regime-stability diagnostic,
  not scored, so the noisiest short slice cannot dominate the score.
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
- **minimum evidence:** return samples and effective sample size, on the full
  Train window and each subwindow (the sound per-window sufficiency knob);
- **path risk:** full-Train max drawdown;
- **breadth:** upstream economic concentration (largest single symbol's share of
  realized PnL);
- **significance:** `R_full - k_accept * SE_full >= 0` — the deflated full-Train
  return is positive (the edge is statistically real after the best-of-N
  deflation). Materiality is not gated; deployed money lives in the run score;
- **cost stress retention:** cost-stress full-Train annualized return retains the
  configured fraction of realistic full-Train annualized return when realistic
  return is positive;
- **causality:** upstream evidence must be score-admissible;
- **complexity:** declared signal components and bounded params.

Per-subwindow trade counts and per-slice returns (with a below-zero count) are
reported diagnostics, not gates: per-window sample sufficiency is owned by
**minimum evidence**, and the binding in-sample robustness gate is the full-Train
deflated **significance** gate. Per-slice return sign on contiguous, autocorrelated
calendar slices is not gated — regime independence is the firewalled OOS stage's
job.

`k_accept` is `gates.score_haircut_se`, the operator-owned acceptance haircut for
the best-of-N Train search. It is separate from `k_rank`.

Micro causality is a bounded score-admissibility check. It can allow Train
scoring while still not being retention, paper-trade, or deployability proof.

## Results And Run Cards

`results.tsv` is the compact loop ledger. It records:

- score parts: `score`, `deflated_return_lcb`, `full_train_annualized_return`,
  `cost_stress_return_retention`;
- sizing: `book_scale`, `deployed_volatility`, `max_feasible_volatility`,
  `capacity_bound`;
- diagnostics: `full_train_psr`, `worst_subwindow_psr`, `trade_count`,
  `min_subwindow_trades`, `total_return`, `max_drawdown`,
  `max_symbol_concentration`, `win_rate`, `profit_factor`, `avg_trade_net`,
  `cost_return_sum`;
- loop state: gate flags, derived `failure_class` (one of `edge | no_edge |
  breadth_bound | evidence_thin | causality | <other gate> | error states`),
  complexity count, failure reason, best status, continuation,
  stop reason, elapsed seconds, artifact directory, and note.

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
