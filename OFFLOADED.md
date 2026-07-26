# Offloaded — crypto_perp_tsmom_majors

**This thesis is archived. The bench files below are the offloaded survivor, not active research.**

| | |
| --- | --- |
| offloaded | 2026-07-26 |
| destination | `~/Personal/researched_strategies/crypto_perp_tsmom_majors/` |
| runnable bundle | `~/Personal/quant_strategies/candidates/crypto_perp_tsmom_majors/` |
| verdict | Train survivor |
| frozen survivor | `attempt-0040`, score 1.0468 (two-sided) |
| second candidate | `attempt-0033`, score 1.0371 (long-only) — **the choice is open** |
| lifecycle | 50 attempts, `continuation: terminal`, `stop_reason: max_iterations` |
| retained downstream | 28 attempts across survivors / gated / near-misses / anti-patterns |

The destination package is authoritative for the thesis, the evidence, and the reseed case. It was
validated against `results.tsv`: every retained attempt ID reconciles, every copied snapshot is
byte-identical to its frozen source, and the root `strategy.py` / `experiment.toml` /
`protocol.train.toml` match the survivor's snapshot.

## Two candidates — do not resolve this by reading the survivor row

They differ in one lever (side logic) and earn the same annualized return by different routes:
long-only earns Sharpe ~1.30 while invested but is at risk ~78% of the window, two-sided earns ~1.08
across all of it. **Carry long-only if the volatility target will ever be raised** (it reaches ~0.30
vol against two-sided's ~0.23, because turnover sets capacity headroom); **carry two-sided if the book
stays at 0.15** and evidence count matters more. Full reasoning in the destination's `README.md` and
`reseed_log.md`.

## Next step is downstream, not a reseed

The recommendation at stop is **OOS both candidates, do not reseed first.** `target_volatility` is the
only material axis left, but it is a leverage dial that yields no new information, and leveraging an
unvalidated edge doubles the cost of being wrong. If further Train work is wanted, the universe axis is
the defensible one. See the destination's `reseed_log.md` Consolidated Reseed Case.

Note the available holdout is short: data ends 2026-04-13 against a Train end of 2025-12-31, roughly
3.5 months, yielding ~4 closed trades for long-only and ~21 for two-sided.

## Bench state

`strategy.py` and `experiment.toml` still hold the survivor's configuration — they were **not** reset,
because no next thesis has been chosen and the offload contract forbids inventing a template. Starting
a new thesis means running `new-thesis-setup`, which owns the reset, the protocol proposal, and the new
lock. **Remove this file once a new baseline exists.**
