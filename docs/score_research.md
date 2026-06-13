# Train Score Rationale

Active rationale for the Train loop. The executable contract lives in
`protocol.toml`, `objective.py`, `gates.py`, `loop.py`, and the OpenSpec specs.
This note explains why the score exists, what it measures, and how a new session
should reason about it.

## Core Decision

The Train keep-rule score is:

```text
score = min(
  PSR(full_train_portfolio_returns),
  min_k PSR(portfolio_returns_in_train_subwindow_k)
)
```

where:

```text
PSR = NormalCDF((sharpe - psr_hurdle_sharpe) / sharpe_standard_error)
```

The loop computes this from upstream quick-run portfolio-foundation metrics. The
scored unit is the single netted-book NAV path: there is one model of money, so
the loop does not compute Sharpe from completed trade bags and does not
reconstruct NAV, drawdown, concentration, or effective sample size locally. The
per-trade tape is a derived attribution view of that same book; inspect it for
alpha attribution, but score the NAV path.

The score is a Train development filter, not deployability evidence. A kept
candidate is only a candidate for downstream human OOS, paper, and small-live
review.

A quick run can also come back infeasible: `result.succeeded` is `False`,
`failure_stage = "feasibility"`, and `result.feasibility` carries a typed `reason`
(for example `capacity_unpriced`, `leverage_budget_breach`, `zero_cost`,
`insufficient_samples`) plus observed exposure. That is no score, not a low score.
The loop records the reason in the attempt note and run card; respond to it (price
capacity, reduce intended gross, configure costs) rather than treat it as a weak
score to climb past.

## Why This Score

The score is built from the upstream netted-book NAV path, the one authoritative
accounting of the run:

- **Full Train evidence** checks whether the candidate has credible evidence
  over the whole Train path.
- **Weakest subwindow evidence** prevents one regime, one burst of trades, or
  one lucky period from carrying the aggregate.
- **PSR** puts the score on a probability scale and adjusts for Sharpe
  uncertainty through the upstream Sharpe standard error.
- **Portfolio returns** make the evidence about capital over time: overlapping
  positions, idle time, compounding, exposure, and drawdowns are already in the
  NAV path, not approximated from isolated trade outcomes.

The `min(...)` shape is intentionally conservative. It does not reward a strong
full-window result if one Train regime is weak, and it does not reward one
excellent subwindow if the full path lacks evidence.

## Why This Fits Autoresearch

This repo runs one human-seeded thesis at a time. The agent is supposed to make
structural, thesis-linked strategy changes, not run an unconstrained parameter
sweep. The score should therefore judge the current candidate's economics, not
the research process that produced it.

That is why attempt count, DSR, PBO, effective trial count, and search-pressure
metrics are not in the live score. They are useful process monitors, but folding
them into the candidate score would mix two different questions:

```text
candidate quality:  does this strategy version show robust Train evidence?
process quality:    is the search becoming overfit or exhausted?
```

The first question drives `keep` / `discard`. The second question drives pause,
simplify, restart, or kill-the-thesis decisions.

The live score also stays deliberately small. A large robust-utility formula
with many terms would create a larger optimized surface for the agent to game.
Extra robustness views are better used as gates, diagnostics, or finalist
audits until they are protocol-owned and consistently emitted.

## How The Loop Uses It

Each quick run emits portfolio-foundation metrics under two upstream scenarios:

- `realistic_costs`: the base scenario used for the live score;
- `cost_stress`: the harsher-cost scenario used by the cost-stress gate.

For `realistic_costs`, the loop reads:

- one `full_train` metric record;
- `K` subwindow metric records, where `K = objective.subwindows`.

Each scoring record must provide finite upstream-owned values for:

- `return_sample_count`;
- `effective_sample_size`;
- `sharpe`;
- `sharpe_standard_error`;
- `total_return`;
- `max_drawdown`;
- `closed_trade_count`;
- `max_symbol_concentration`.

The loop then computes:

```text
full_train_psr = PSR(realistic_costs.full_train)
subwindow_psrs = [PSR(realistic_costs.subwindow_k) for k in 1..K]
worst_subwindow_psr = min(subwindow_psrs)
score = min(full_train_psr, worst_subwindow_psr)
```

`worst_subwindow_id` always identifies the weakest subwindow, even when the full
Train PSR is the binding score.

`closed_trade_count` counts netted-book round trips, and the return statistics are
computed over at-risk bars under a minimum-sample gate. A subwindow below the
minimum is non-scoreable: it yields no PSR, so the run is non-scoreable rather
than assigned a finite Sharpe. The foundation summary also exposes a per-scenario
feasibility payload and live gross/net utilization series for diagnostics.

The keep rule is unchanged:

```text
all_gates_pass
and score > best + max(min_abs_improvement,
                       min_rel_improvement * max(1, abs(best)))
```

Because PSR is a probability, `min_abs_improvement = 0.001` means a 0.1
percentage-point improvement in evidence probability.

## Gates

The score ranks only candidates that pass all gates. Gates are not optimized and
are not blended into the score.

The active gate set covers:

- **trade floor**: full-Train upstream `closed_trade_count`;
- **subwindow coverage**: each subwindow's upstream `closed_trade_count`;
- **minimum evidence**: return samples and effective sample size;
- **cost stress**: PSR under the upstream `cost_stress` scenario;
- **breadth**: upstream max symbol concentration;
- **path risk**: full-Train max drawdown;
- **economic magnitude**: full-Train total return;
- **complexity**: declared signal components and bounded params;
- **Train score floor**: minimum acceptable base PSR score.

Gate values must be finite and semantically valid. Drawdown is expected to be
zero or negative. Concentration must be in `[0, 1]`. Counts must be nonnegative
integers. Missing or malformed foundation evidence is a run failure, not a weak
score to patch around.

## Diagnostics

`results.tsv` stays compact because it is both a human scan surface and loop
state. It reports:

- score parts: `score`, `full_train_psr`, `worst_subwindow_psr`,
  `worst_subwindow_id`, `cost_stress_psr`;
- gate summary: `gates_passed`, `gate_flags`;
- evidence basics: foundation `trade_count`, `min_subwindow_trades`,
  `total_return`, `max_drawdown`, `max_symbol_concentration`;
- trade-tape diagnostics when available: `win_rate`, `profit_factor`,
  `avg_trade_net`, `cost_return_sum`;
- lifecycle fields: status, best status, continuation, stop reason, elapsed
  seconds, provenance hashes.

Detailed vectors and warnings go to the per-attempt `run_card.json`, not the
TSV. The run card carries subwindow PSRs, full gate outcomes, foundation
scenario summaries, causality evidence, warnings, and a primary failure mode.

Before a structural strategy edit, the agent should inspect the latest run card
and sampled trades. The score says whether the candidate is keepable; the
diagnostics should explain what to change or whether to kill the thesis.

## Boundaries

`quant_strategies` owns portfolio construction and path statistics:

- portfolio/NAV return path semantics;
- costs, fills, funding, and execution accounting;
- Sharpe, Sharpe standard error, effective sample size, skew, and kurtosis;
- drawdown, total return, closed-trade counts, and symbol concentration;
- realistic-cost and cost-stress scenario generation.

`quant_autoresearch` owns loop policy:

- protocol-owned PSR hurdle;
- PSR calculation from upstream Sharpe and Sharpe SE;
- `min(full_train_psr, min_subwindow_psr)` score;
- gate thresholds;
- keep/discard/stop decisions;
- compact result logging and run-card emission.

Do not rebuild upstream-owned metrics from trade bags in this repo. If an
upstream metric is missing, ambiguous, non-finite, or mathematically suspect,
mark the run unavailable and fix the upstream contract.

## What Stays Out Of The Live Score

Do not add these to the keep-rule score without a new protocol-owned change:

- literal attempt count;
- effective independent trial count;
- DSR;
- PBO / CSCV;
- Minimum Backtest Length;
- parameter-neighborhood audits;
- leave-one-symbol audits;
- drawdown ratios;
- win rate or profit factor;
- aggregate net return alone.

These can be diagnostics, search monitors, or finalist audits. They are not the
candidate score.

## Interpreting Failures

Use failures to choose structural research moves:

- **Low full-Train PSR**: the mechanism lacks reliable full-path evidence.
  Change the mechanism or kill the thesis.
- **Low worst-subwindow PSR**: the idea is regime-dependent. Inspect the weak
  window before tuning anything.
- **Sparse evidence**: the trigger is too rare or concentrated. Broaden only if
  the thesis justifies it.
- **Weak cost stress**: the edge is too small or turnover-heavy. Change horizon,
  selectivity, or execution burden; do not hide it in the score.
- **Breadth failure**: the result is carried by a narrow source. Narrow the
  claim or reject the general thesis.
- **Path-risk failure**: losses are unacceptable on the Train path. Inspect
  exits and risk shape; do not mask drawdown with another ratio.
- **Complexity failure**: the candidate is no longer a simple auditable thesis.
  Simplify or stop.

The right next action should be structural: change the mechanism, simplify,
narrow the claim, fix risk/exits, or kill. It should not be "nudge a threshold."
