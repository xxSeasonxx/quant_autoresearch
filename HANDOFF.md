# Objective

Run one immutable Train lifecycle against the $100,000 primary mandate only
after real execution feasibility is priced from a lawfully accessible venue.

# Current state

- The repository has no active lifecycle and zero attempts.
- `protocol.toml` fixes `[account].initial_notional = 100000.0`, uses the current
  `average_bar_impact` capacity contract, and deliberately sets
  `[execution_model] mode = "unpriced"`.
- `python -m loop status` is readable and reports `continuation: blocked` plus
  the execution-setup blocker.
- `baseline` and `climb` fail before creating a thesis lock, ledger row, quick
  config, or artifact while execution is unpriced.
- Priced onboarding requires venue, terms as-of date, authoritative source, and
  exact per-symbol minimum-order and fixed-order-cost terms.
- The harness accepts portfolio-foundation v4 and sizing-report v2 only. Run
  cards and `results.tsv` report `target_reached`,
  `max_feasible_book_scale`, `minimum_order_notional_ratio`, and
  `fixed_cost_share`; retired evidence and ledger shapes fail closed.
- The $1 million rerun remains a non-gating diagnostic and is distinct from the
  $100,000 scored mandate.
- The full suite passes: 119 tests. Ruff and mypy pass.

# Next steps with success checks

1. Season selects a venue the account may lawfully access and supplies current
   terms provenance.
   - Success: every configured symbol has sourced minimum-order and fixed-cost
     terms from the same dated snapshot.
2. Run onboarding and review its recommendation without starting Train.
   - Success: the recommended execution model is `minimum_notional`, coverage is
     exact, and the approved protocol hash matches `protocol.toml`.
3. Run the first baseline only after approval.
   - Success: attempt 0001 creates the first lock, ledger row, run card, and v4
     foundation evidence; the execution fields reconcile with upstream evidence.

# Open questions/risks

- The eligible execution venue and live terms are intentionally unresolved.
- Lot sizes, quantity steps, price ticks, contract multipliers, multi-numeraire
  conversion, and historical venue-rule changes remain upstream limitations.
- `min_cost_stress_return_retention = 0.50` still needs an operator-owned
  calibration study under the chosen venue terms.
- `HISTORY.md` contains an unrelated, preserved `n_eff` chronology update.

# Key references

- `program.md`
- `protocol.toml`
- `docs/score_research.md`
- `UPSTREAM_LIMITATIONS_TODO.md`
- `docs/HARNESS_CONSTRAINT_REVIEW.md`
- `onboarding.py`
- `loop.py`
