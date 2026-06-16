# Harness Objective Redesign — Implementation Roadmap

**Status:** active plan. Read this first; it is self-contained.
**Date:** 2026-06-16.
Full rationale, rejected alternatives, and the diagnosis trail live in
`docs/harness-objective-redesign.md` (to be folded into `HISTORY.md`). You do not
need that file to execute this roadmap.

## Why this work exists

The Train loop optimizes the wrong number. The live score is worst-window PSR
(`min(full_train_psr, min subwindow_psr)`, `objective.py`). PSR is built on
`sharpe = mean/std`, which is **scale-invariant**: scale every position by `k` and
mean and std both scale by `k`, so the score does not change. The score literally
cannot tell a 0.2%-return book from a 20%-return book of the same shape.

Result: 50 attempts converged on a survivor that makes **~0.27%/yr** while deploying
**~1% of its budget** (≈99% in cash), with 5–10× capacity headroom unused. The edge
is real (good Sharpe, all symbols profitable); the **scale is nothing**, and the
score never asked for scale. Evidence: scaling a survivor +10% raised return but
moved the score −0.00002.

We are switching the loop to optimize **deployable money, robustly** — so a Train
survivor means "ready to paper-trade," not "consistent but uninvested."

## Operating principle (the decision rule for every choice below)

Be practical: **make real money, robustly.** Three requirements that must hold
*jointly* — a candidate failing any one is not a survivor, however well it scores on
the others:

1. **Make money, uncertainty-adjusted.** The objective is realized economic return
   at the deployed book size, haircut for the statistical uncertainty of its own
   estimate. A scale-invariant ratio (Sharpe, PSR, Calmar) is wrong *as the
   objective* — it cannot see money. Statistical significance is not a separate side
   constraint; it is internalized as the uncertainty haircut inside the money score.
   If the score does not move when deployed return moves, the score is wrong.
2. **Don't overfit.** A survivor must generalize beyond this Train window. Enforce
   robustness in the score's shape (weakest subwindow + uncertainty haircut + cost
   stress), a deflated acceptance bar for the best-of-many search, a return-blind
   frozen universe with no symbol cherry-picking, and hard simplicity caps. On a tie,
   keep the simpler candidate.
3. **Stay practical.** Price costs, slippage, capacity, and position size exactly as
   live trading will, so a passing survivor is deployable to paper then live as is.
   Surface real ceilings (capacity, universe breadth); never hide a limit to make a
   number look better.

## Already done — do not re-do (upstream `quant_strategies`, shipped)

The scale fix landed upstream; the consumer just has to use it.

- The strategy emits a **base target shape**, not a deployable weight. The foundation
  normalizes the shape and applies a required `[risk_budget]`, and owns global scale.
  A strategy can no longer search economic size.
- `[risk_budget]` is required: Train quick-run uses `mode="calibrate_vol"` +
  `target_volatility`; downstream uses `mode="fixed_scale"` + the recorded
  `book_scale`. Capacity-bound calibration sizes to the feasible frontier and is
  **recorded** (`capacity_bound`), not failed.
- The foundation emits, **per window (full Train + each subwindow)**, a
  `ReturnStatistics` with `mean_return`, `return_volatility`, `effective_sample_size`,
  `sharpe`, `sharpe_standard_error`; and a `PortfolioSizingReport` carrying
  `annualization_periods_per_year` (P), `book_scale`, deployed &
  `max_feasible_volatility`, `capacity_bound`. **No upstream change is needed for the
  score** — every input already exists.

## The target score contract (state it once; implement to this)

```text
# Ranking score the loop maximizes:
score   = min over windows of [ annualized_return_w - k_rank * SE_w ]
k_rank  = 1

# Acceptance gate (where multiple-testing correction lives):
min over windows of [ annualized_return_w - k_accept * SE_w ] >= min_annualized_return
k_accept ≈ sqrt(2 * ln N_attempts)        # ≈ 2.8 at a 50-attempt budget; an explicit protocol field

# Standard error — same for both, direct from per-window foundation fields:
SE_w               = return_volatility_w * P / sqrt(effective_sample_size_w)
annualized_return_w = mean_return_w * P
```

- Fields are **per-period**; `P = annualization_periods_per_year`. `SE_w` is the
  textbook `σ/√n` (with `n_eff` discounting lag-1 autocorrelation). **Do not** use a
  `sharpe_se × vol` proxy — it mixes frequencies and understates `SE_w` by ≈√P.
- Cross-check identity: `SE_w = annualized_return_w / t_w` with
  `t_w = sharpe_w/sharpe_se_w = Φ⁻¹(PSR_w)` — the exact t-stat the current PSR score
  uses. So this migration reuses machinery the loop already has.
- Calmar / Sharpe / PSR demote to diagnostics or tie-breakers; the SE haircut now
  carries the robustness role inside the primary score.

## Action items (ordered; each has a "Done when")

### Phase A — Money-first score + gates (load-bearing; build first)

- [ ] **A1. Capture the SE inputs.** `loop.py:_foundation_metric` and `objective.py
  FoundationMetric` keep `sharpe`/`sharpe_se`/`effective_sample_size` but drop
  `mean_return` and `return_volatility`; add both. Read `P` from the
  `PortfolioSizingReport` payload. *Done when* a quick-run `run_card` surfaces
  `mean_return`, `return_volatility`, and `P` per window.
- [ ] **A2. Implement `return_lcb_subwindow`.** Default objective per the contract
  above. Keep `return_subwindow` (undeflated) as a diagnostic only; reject unknown
  kinds; an unscoreable window → non-scoreable run. *Done when* unit tests confirm:
  score = weakest-window LCB at `k_rank=1`; scaling deployed return moves the score.
- [ ] **A3. Money gates.** Replace `min_total_return ≥ 0` and `train_score_floor`
  with one deflated money floor (`k_accept`, contract above) as an explicit protocol
  field (`gates.score_haircut_se`, not auto-derived from `max_iterations`). Replace
  PSR-only cost stress with money-aware cost-stress (`min_cost_stress_annualized_return`
  and/or `min_cost_stress_return_retention`). Add a mandate-capacity verdict gate and
  make causality-verify a hard gate (a `verified:false` replay is not a survivor).
  Make `min_effective_sample_size` / `min_trades_per_subwindow` strict enough that a
  thin slice cannot drive the score on noise. *Done when* gate tests cover each.
- [ ] **A4. Wire `protocol.toml`.** `[objective].kind = return_lcb_subwindow`
  (protocol-owned); add `min_annualized_return`, `k_accept`, and money-aware
  cost/capacity gate fields. *Done when* an end-to-end `climb` run scores and gates
  under the new contract.

### Phase B — Operator mandate (freeze intent before search)

- [ ] **B1. `[mandate]` fields + derivation.** Add `[mandate]` to `protocol.toml`
  (capital, risk appetite → target_volatility, drawdown stop, return hurdle,
  deployment intent, hard limits). Deterministically derive `[risk_budget]`,
  `max_abs_drawdown`, `min_annualized_return`, `k_accept`, and the universe threshold.
  *Done when* a mandate→config wiring test shows the derivation is deterministic.
- [ ] **B2. (polish) Elicitation + doc split.** `new-strategy.md` owns the plain-
  language operator brief, mandate translation, protocol fit, and lifecycle reset;
  `program.md` trims to the active Train runbook. Lower priority — does **not** block
  Phase A; mandate fields can be set directly in `protocol.toml`.

### Phase C — Universe as a return-blind rule

- [ ] **C1. `[universe] rule` resolver.** Replace the hand-picked 3-symbol list with
  an objective filter (data kind, min ADV/liquidity, data-readiness, complete marks,
  capacity support, eligibility, operator exclusions). Resolve at run start; freeze
  and record the rule + resolved list. *Done when* resolution is deterministic, a
  threshold change moves the list, and the resolver never reads realized return /
  PnL / Sharpe / Calmar / win rate.

### Phase D — Surface, ledger, cutover

- [ ] **D1. Prune surface.** Remove the dead `experiment.toml` params and the global
  `weight` knob. *Done when* the complexity gate is meaningful and the strategy still
  runs.
- [ ] **D2. Ledger.** Record config (`objective.kind`, risk-budget mode +
  `target_volatility`, universe rule + resolved list) plus the `PortfolioSizingReport`
  and the money/diagnostic metrics in the run card + `results_log.py`.
- [ ] **D3. Hard cutover + docs.** Regenerate artifacts/fixtures against the new
  contract (no compatibility mode). Update the `program.md` North Star to "deployed
  annualized return, uncertainty-haircut, subject to robustness and practicality
  gates," and move the durable rationale to `HISTORY.md`.

## Expected first outcome — do not "fix" it

On the current 3-symbol universe the funding sleeve will almost certainly **fail**
the deflated money floor: its weakest subwindow sits ~0.23 SE above zero
(PSR 0.59 → `Φ⁻¹(0.59) ≈ 0.23`), so any real `k_accept` drives the floor negative.
That is the score working — the correct verdict is *reseed with more breadth and/or
leverage*, not a deployable survivor. A run that ends with no survivor here is
success, not a bug. Do not weaken the score to make this sleeve pass.

## Open risks / deferred

- **Cross-attempt effective-N.** `k_accept = √(2 ln N_attempts)` treats the attempts
  as independent trials. Honest clustering of correlated attempts (true effective-N)
  would shrink N; deferred. The current heuristic is conservative-ish but not exact.
- **Leverage vs vol-target precedence.** Confirm the clamp order is leverage budget →
  capacity frontier (recorded as `capacity_bound`) → only a strategy's raw intended
  shape over budget fails closed. Verify it is written in the foundation's owning doc.
- **Causality replay timeout.** The survivor card showed `verified:false` from a
  micro-replay timeout. Raise the replay budget or shrink the probe; an unverified
  causal book is not deployable money (enforced by the A3 gate).
