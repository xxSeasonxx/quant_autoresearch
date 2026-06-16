# History

Development chronology and migration rationale. Active contracts live in the
owning docs (`program.md`, `protocol.toml`, and the module docstrings); this file
is history only.

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
- **Causality** → promoted to a hard gate, shipped with a raised replay budget so a
  legitimate run verifies within budget rather than failing on a timeout.
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

Full diagnosis trail, rejected alternatives, and the staged roadmap:
`docs/harness-objective-redesign.md` and `docs/harness-objective-roadmap.md`.
