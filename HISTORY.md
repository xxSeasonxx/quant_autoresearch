# History

Development chronology and migration rationale. Active contracts live in the
owning docs (`program.md`, `protocol.toml`, `docs/score_research.md`, and the module
docstrings); this file is history only.

## Semantic lifecycle identity and derived stop state

The thesis lock moved from a raw `protocol.toml` byte hash to a canonical semantic
identity that excludes only the three operator-owned stop rules. Continuation and
stop reason were removed from `results.tsv`; the harness now derives them from
immutable attempts and authorized stop rules. Stopped lifecycles can be reopened
only through a monotonic, Season-confirmed extension recorded in an append-only
event chain.

This was an intentional breaking cutover while no lifecycle was active. Old lock
and ledger schemas require reset and are not translated.

## Full-window total-return score and Train-strength naming

The harness now ranks gate-passing candidates by realistic-cost full-window
`total_return`. The ranking-only one-SE haircut was removed so candidates with
different duty cycles are compared by economic return earned over the fixed Train
window. The ledger's duplicate `total_return` column was removed; `score` is its
single representation.

The unchanged full-Train at-risk strength calculation was renamed from
`significance` to `train_strength`:
`at_risk_annualized_return - train_strength_haircut_se *
at_risk_annualized_standard_error >= 0`, with a fixed 2-SE hurdle. The names no
longer imply statistical proof, deflation, or a best-of-N correction. This was a
hard schema cutover after archiving the existing lifecycle; old protocols and
ledgers are not translated.

## Validity-only significance gate (money-to-score)

The money-first redesign (below) added an acceptance gate `deflated_full_train_return >=
min_annualized_return` (0.10). That gate fused two questions — is the edge statistically
real (validity), and does it deploy enough money (materiality) — into one number:
`money_floor = return * (1 - k/t)`, with a cliff at `t = k`. A real, cost-robust, causal
edge (Sharpe ~3.8) failed it not for edge quality but because low duty cycle (~33% of the
calendar at-risk) and capacity limits suppressed the full-Train t-stat to ~2, collapsing the
money term. A gate whose failures track "intermittent / capacity-limited" rather than "real
vs overfit" is not a useful discovery filter upstream of OOS, and its verdict was routinely
overridden.

Repurposed to a **validity-only** gate, renamed `significance`:

- **Gate** → `significance`: `R_full - k_accept * SE_full >= 0` — the edge was treated as
  statistically real after the best-of-N deflation (equivalently the full-Train t-stat clearing
  `k_accept`). The `k_accept` (`gates.score_haircut_se`) deflation — the multiple-testing
  correction — was retained, so overfit protection was unchanged; only the materiality threshold
  was dropped.
- **Money → score.** Materiality (how much money) lived entirely in the run score
  (`R - k_rank * SE`, the deployed-return LCB the loop then ranked on) and was the operator's
  judgment, not a hard floor. `min_annualized_return` (0.10) was removed from config, parser,
  brief, and proposal payload (no orphan config).
- **`capacity_bound` stopped being a `failure_class`:** a significant but capacity-throttled
  edge then passed (`failure_class = edge`); its low deployed scale showed in the score and the
  `capacity_bound` diagnostic column. A `significance` failure meant the edge was not
  distinguishable from best-of-N noise (`no_edge`).
- The `deflated_money_floor` results column was renamed `deflated_return_lcb` (same deflated
  return value, non-gating).

This reversed the recommendation to keep `money_floor` and 0.10 unchanged — a
deliberate operator decision, not a rescue: the change
does not pass the strategy that prompted it (its deflated LCB is ~0, borderline on validity
too). The score already carried money (`k_rank`, `_K_RANK = 1.0`), so no score change was
needed, and no upstream `quant_strategies` change — the gate and deflation are consumer-side.

## Money-first Train objective

The Train loop previously maximized worst-window PSR
(`min(full_train_psr, min subwindow_psr)`), a score built on `sharpe = mean/std`.
That ratio is scale-invariant: scaling every position by `k` leaves it unchanged,
so it could not tell a 0.2%/yr book from a 20%/yr book of the same shape. Fifty
attempts converged on a survivor that returned ~0.27%/yr while deploying ~1% of
its budget, with 5–10× capacity headroom unused — the edge was real but the scale
was nothing, and the score never asked for scale.

Upstream `quant_strategies` took ownership of book scale (risk-budget sizing), so
the loop controls only shape. The objective was switched to measure deployable
money:

- **Score** → `return_lcb_subwindow`: `min over windows of (R_w - k_rank * SE_w)`,
  with `R_w = mean_return_w * P`, `SE_w = return_volatility_w * P / sqrt(n_eff_w)`,
  `k_rank = 1`, and `P` the run-level `annualization_periods_per_year` from the
  upstream sizing report. The SE inputs were already serialized by the foundation;
  the consumer simply began reading them — no upstream change.
- **Acceptance** → a deflated money floor `min over windows of (R_w - k_accept*SE_w)
  >= min_annualized_return` replaced the toothless `min_total_return >= 0` and the
  redundant `train_score_floor`. `k_accept` (`gates.score_haircut_se`) is an
  explicit best-of-N correction (~`sqrt(2 ln N)`), not derived from
  `max_iterations`, so changing the loop budget cannot silently move the bar.
- **Cost stress** → a money-aware return-retention gate replaced the PSR cost-stress
  gate.
- **Causality** -> promoted to a hard score-admissibility gate. Micro replay uses
  its own bounded probe and timeout budget and is not retention, paper-trade, or
  deployability proof.
- **Diagnostics** → PSR/Sharpe/Calmar retained as diagnostics only; the strategy
  `weight` knob and the dead `experiment.toml` params were removed (scale search is
  owned upstream), making the complexity gate meaningful.

### Consumer `[risk_budget]` wiring

Applying the change surfaced a gap the proposal had assumed away: upstream had
already made `[risk_budget]` a required run-config block (the operator-frozen
sizing mandate that converts target-book shape to executable book size), but the
consumer never emitted one. The old bench sized the book through the strategy
`weight` knob; removing that knob left the book unsized, so the consumer now emits
an operator-frozen `[risk_budget]` block (`protocol.toml` → `protocol.py` →
`build_quick_run_config`). The active mandate is `mode = "calibrate_vol"`,
`annualization_periods_per_year = 525600` (24/7 crypto-perp minute cadence),
`target_volatility = 0.15`. `P` flows back from the sizing report into the money
score, closing the loop. The broader operator-mandate elicitation and
`mandate→config` derivation remain a separate change.

Hard cutover: no dual-scoring mode; old PSR-scored run dirs and the prior
`results.tsv` schema were not migrated. The first `climb` under the new contract
was expected to end with no survivor on the 3-symbol funding sleeve — its weakest
subwindow sits ~0.23 SE above zero, so any real `k_accept` drives the floor
negative. That is the score working; the correct verdict is *reseed with more
breadth/leverage*, not weaken the score.

This section is the durable diagnosis trail, rejected-alternative summary, and
migration rationale for the money-first objective cutover.

## Universe resolver v1

New-thesis setup gained a small return-blind universe resolver before the first
Train result exists. The resolver reads catalog symbol constants and readiness
metadata from `quant_data`, applies explicit exclusions, validates dataset and
derived-symbol windows, sorts the eligible symbols, and writes a hashed artifact
under `.autoresearch/universe/`.

`propose-protocol` can now read that artifact through `universe_artifact` in the
setup brief. It maps the resolved symbols into the recommended protocol table and
records the resolver hash in the proposal. The resolver does not edit
`protocol.toml`, run Train, or inspect PnL, returns, score diagnostics, prior
attempts, `results.tsv`, run cards, or generated Train artifacts.

## Lifecycle 1–2 — 2025 10-month window (2025-03-01 → 2025-12-31)

The thesis first ran on a 0.83-year Train window. Two budget-only reseeds occurred
(no evidence gate changed): `max_iterations` 30→40, then the full fixed-budget stop
config (`max_iterations = baseline_grace_iterations = plateau_patience = 40`, after
discovering `baseline_grace_iterations=10` would force-stop at attempt 10). The
40-budget lifecycle ran 30 climb attempts; full results/run-cards are archived under
`.autoresearch/lifecycle_archive/`.

**What was found.** Baseline (30d vol_scaled, daily, two-sided) was negative
(t = −0.24) and capacity-strangled. A real edge was then built and characterized:

- **Best config:** two-sided per-instrument sign-TSMOM, 30d formation, daily,
  `take_profit=0.20`, `ma_gate_days=45`, `top_n=8`, TWAP `ramp_bars=30`.
  Full-window **t = 1.60 (Sharpe ≈ 1.75)**, 4–5/6 subwindows positive, both legs
  profitable, all gates pass except `train_strength`.
- **Mechanism:** crypto majors show short-horizon *reversal of extremes* —
  (1) equal-weight `sign` beats vol-scaling (vol_scaled is anti-predictive: it loads
  the strong movers that revert); (2) `take_profit=0.20` monetizes the reversal
  (this one lever lifted t from ~0 to 1.14); (3) a 45d MA-gate filters unconfirmed
  entries; (4) a balanced two-sided book halves return variance. Robust — every
  lever sits on a smooth plateau, not a razor spike.
- **Why no keeper:** `train_strength` is full-window t≥2 (Sharpe ≈ 2.19) and is
  scale-invariant. Per-instrument momentum topped at Sharpe ~1.75 across the entire
  lever space (signal form, three formation measures, all exit types+levels,
  selection, horizon, side, cadence, capacity), so it never cleared the bar. The
  0.83-year window made the hurdle (`2/√years`) implausibly high; separately, the
  13-name universe ADV capped deployable vol at ~7% of target (~1.6% return on $1M).
  Both binding constraints were protocol-level, not the edge.

This directly motivated the reseed to a 4-year window (below): the same edge clears
a `2/√4 ≈ 1.0` hurdle, and the longer window is the honest regime-robustness test.
`strategy.py` carries the levers discovered here (`signal` incl. `ma_trend`,
`skip_days`, `stop_loss_pct`, `take_profit_pct`, `trailing_pct`, `top_n`,
`stagger_minutes`, `ramp_bars`); the best config above is the prior-to-beat.
