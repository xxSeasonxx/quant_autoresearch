# Handoff — crypto_perp_tsmom_majors

## Objective

Find or falsify one causal, deployable crypto-perp trend edge worth Season's downstream OOS, paper,
and small-live review — and never let a number look better than its evidence. The thesis is per-name
time-series momentum on the three deepest crypto perpetuals, and the research question is no longer
whether the edge exists but how much of it can be honestly deployed and which form of it to carry
forward. Everything on this bench is Train-only evidence; promotion decisions belong downstream.

## Current state

**Lifecycle stopped: 50 attempts, `continuation: terminal`, `stop_reason: max_iterations`.**
Survivor is **attempt-0040** at score **1.0468**. `experiment.toml` matches that attempt's snapshot
byte-for-byte. `strategy.py` differs from the snapshot in exactly one executable line — `max(0.0, …)`
became `abs(…)` in the conviction weight metric — which is unreachable under the survivor's
`inverse_vol` weighting, so the survivor is bit-reproducible from the current tree.

**Two candidates survive, differing in one lever (side logic), and the choice is Season's.**
Everything else is identical: 30d formation, no gap, daily rebalance, `inverse_vol` on a 60d
volatility estimator, no regime gate, no exits, `position_smoothing` 2, `execution_bars` 20.

| | attempt-0033 long-only | attempt-0040 two-sided (survivor) |
| --- | --- | --- |
| score (objective) | 1.0371 | **1.0468** |
| compound annualized, 4.83y | 15.87% | 15.99% |
| full-window Sharpe | 1.06 | 1.07 |
| annualized rate while at risk | **19.43%** (~78% duty) | 16.20% (~100% duty) |
| `train_strength` t / LCB | **2.533 / +0.0409** | 2.346 / +0.0239 |
| full-train PSR | **0.9942** | 0.9905 |
| closed trades | 66 (~14/yr) | **345** (~72/yr) |
| profit factor | **4.96** | 1.92 |
| cost drag / stress retention | **0.027 / 0.978** | 0.052 / 0.959 |
| max drawdown | −0.119 | −0.120 |
| `max_feasible_volatility` | **0.338** | 0.233 |
| horizon robustness | 25 **and** 30 pass | 30 only; 35 fails |
| gates | 9/9 | 9/9 |

**The two candidates deliver the same annualized return by different routes**, which is the exact form
of the trade-off. Long-only earns a Sharpe of ~1.30 while invested but is at risk only ~78% of the
window; two-sided earns ~1.08 across essentially all of it. So the 0.94% score gap is noise on top of
two genuinely different books, not a ranking. Two-sided's real purchase is evidence: 5× the closed
trades and return spread far more evenly across names and regimes. **Do not resolve the choice by
reading the survivor row.**

**Expected out-of-sample, stated honestly.** In-sample Sharpe ~1.06 with t 2.35-2.53 across 50
attempts, and `train_strength` is explicitly not a multiple-testing correction. The expected maximum
of 50 independent null draws is ≈2.10, so the survivor's t sits about half a standard deviation above
what search alone would produce; the attempts are far from independent (one a-priori mechanism,
~8-12 effective distinct tries) which improves that materially, but nothing in the ledger has priced
the search. A defensible expectation after search deflation and normal in-sample decay is Sharpe
**0.4-0.7**, i.e. **6-11% annualized**, with real probability of near zero.

**Three conclusions that change how any further work on this thesis must be read:**

1. **This book is paid for duty cycle.** Seven levers that reduced time at risk all lost (slower
   clock −16.5%, faster exit −27%, regime gate −51%, take-profit −77%, trailing stop −85%, hysteresis
   band −10.4%, heavier smoothing −11.9%), and the one lever that raised it took the score lead. Four
   of those rows improved per-trade economics *and* cost drag while losing badly on total return, so
   **cost is not the binding constraint and turnover reduction is not a productive direction.**
2. **The exit family is closed.** Four devices, four distinct falsifications. Holding until the
   formation horizon turns beats every alternative the surface affords. No price-path barrier improves
   drawdown per unit of deployed volatility, which removes a hoped-for cushion from the vol-target
   axis.
3. **Single-lever verdicts are conditional on their base.** Six of the lever verdicts in this thesis
   flipped when the base moved, including side logic. Treat every single-lever verdict in
   `rationale.md` as conditional unless it is marked as having transferred.

**In-protocol shape is exhausted.** The survivor's neighbourhood is mapped closed on every axis the
surface affords. The last thirteen attempts produced no keep.

**Nothing is committed.** All work is in the working tree: `loop.py`, `strategy.py`, `experiment.toml`,
`protocol.toml`, `rationale.md`, `reseed_log.md`, `tests/test_portfolio_foundation_scoring.py`,
`UPSTREAM_LIMITATIONS_TODO.md`, and untracked `HARNESS_TODO.md`.

## Next steps

Steps 1-2 are the recommended path in order. Step 3 is the only defensible further Train work and is
**not** the next move. Steps 4-5 are independent.

1. **Take both candidates downstream to OOS — do not reseed first.** They are one flag apart, so
   testing both costs nothing extra, and the long-only row needs the comparison because its sample is
   thinner. *Success check:* both evaluated on the same held-out window, with the long-only result
   explicitly weighted by its trade count.
   **Know the window is thin before relying on it.** Data ends 2026-04-13 against a Train end of
   2025-12-31 — about 3.5 months, and currently ~104 days stale. At ~14 trades/year long-only yields
   roughly **4 closed trades** there; two-sided yields ~21. If the holdout stays this short, forward
   paper-tracking will be more informative than the OOS window itself.
2. **Then decide which candidate to carry, with the reason recorded.** The rule the evidence supports:
   **long-only if `target_volatility` will ever be raised** (it reaches ~0.30 vol against two-sided's
   ~0.23, because turnover sets capacity headroom), **two-sided if the book stays at 0.15** and
   evidence count matters more. *Success check:* the choice and its reason are recorded, and the
   rejected candidate stays in the package rather than being dropped.
3. **If further Train work is wanted, reseed on the universe — not on `target_volatility`.** Full
   reasoning and the axes ruled out are in `reseed_log.md`'s Consolidated Reseed Case; in short, the
   vol-target axis is a leverage dial that yields no new information, while widening from 3 names to a
   broad return-blind eligibility rule over the 25 eligible perps attacks the three real weaknesses at
   once (≈1 effective bet, the $1M capacity ceiling, weak regime pervasiveness). Use
   `new-thesis-setup`; scores will not be comparable across universes, so treat it as a harder test of
   the same mechanism rather than an improvement. *Success check:* a return-blind
   `universe_artifact` resolved from eligibility metadata alone, an approved protocol, and a baseline
   that reproduces the per-name mechanism on the wider cross-section.
4. **Offload the thesis** (independent of the above, and needed before any reseed replaces the bench).
   The approved design for a reseed-continuation mode in
   `.claude/skills/quant-strategy-offload/SKILL.md` is **designed but not implemented** — see Open
   questions. *Success check:* package exists under `~/Personal/researched_strategies/<slug>/` with
   README, curated rationale, `reseed_log.md`, ledger, and retained attempt snapshots; both candidates
   present with the comparison table intact; every copied attempt ID reconciles against `results.tsv`.
5. **Implement `loop extend`** and **commit the work.** Spec in `HARNESS_TODO.md`. *Success checks:*
   budget extension works without hand-editing `thesis_lock.json` or `results.tsv`, with a test
   covering refusal of non-stop-rule protocol changes; and `git status --short` clean apart from
   intentional artifacts.

**Do not** continue iterating at this protocol. Twenty attempts returned two marginal keeps worth
+1.05% combined and the last thirteen returned none; the axes are mapped closed.

## Open questions / risks

- **Budget extension requires hand-editing generated state.** The thesis lock pins `protocol_sha256`
  over all of `protocol.toml` and `_ensure_can_attempt` refuses a `terminal` trailing row, so
  extending a *stop rule* needs the lock rebound and the trailing row's derived `continuation` /
  `stop_reason` recomputed. Done twice this lifecycle (derived fields only, recomputed via
  `_stop_reason_after_attempt`; no measured field touched). `HARNESS_TODO.md` item 1 exists to remove
  this hazard.
- **The offload skill's approved design is unimplemented.** Four decisions were approved: an
  orthogonal reseed-continuation section (not a third mode); a single contract-bound `OFFLOADED.md`
  removed once a new baseline exists; side-by-side package lineage for reseed chains; and matching
  edits at the `new-thesis-setup` end so it consumes and removes the handoff doc. `reseed_log.md` is
  also absent from both destination layouts, which would silently discard the consolidated reseed
  case.
- **Both keeps in the last twenty attempts are marginal.** The breadth tilt cleared the improvement
  floor by 0.00025 and is statistically indistinguishable from the linear mode; treat the survivor's
  `gross_mode` as a coin-flip, not a finding. It is also **inert** under two-sided side logic.
- **The survivor is knife-edge on the formation horizon.** Two-sided passes only at 30d, with a gate
  failure at 35d. A five-day drift in the true horizon breaks it, and drift is what an OOS window
  delivers. Long-only has a genuine two-point plateau inside the a-priori 25-30d range.
- **`tests/test_strategy_causality.py` fails against the working tree** and passes at `HEAD`. It
  hard-codes the committed thesis's param names, so it breaks on every thesis switch. Pre-existing and
  out of scope — do not "fix" it by weakening the test.
- **Volume is not available to strategies** (recorded in `UPSTREAM_LIMITATIONS_TODO.md`, flagged
  verify-first). It bounds how honest any participation-aware execution claim can be; verify against
  the upstream consumer docs before relying on it either way.
- **Drawdown and capacity ceilings are both single-point extrapolations.** Path dependence may make
  drawdown worse, and capacity was measured at 0.15 deployed volatility only.

## Key references

- `program.md` — the authoritative Train runbook. Read it before iterating; do not paraphrase it.
- `rationale.md` — thesis, Lever Enumeration, per-attempt log for all 50 attempts, the two-candidate
  comparison, and the base-dependence caveat.
- `reseed_log.md` — dated reseed evidence and the single Consolidated Reseed Case written at this stop.
- `HARNESS_TODO.md` — two open harness gaps: no `loop extend` path, and the attempt-start param delta
  anchoring only on the score-best row.
- `docs/score_research.md` — frozen score, gate, and ledger field semantics.
- `results.tsv` + `results/autoresearch/attempt-XXXX/snapshot/` — canonical ledger and per-attempt
  frozen sources.
- `.autoresearch/lifecycle_archive/20260725T151658926612Z/` — the contaminated 30-attempt predecessor.
- `.autoresearch/lifecycle_archive/20260725T210357327232Z/` — the 10-attempt clean confirmation run,
  plus `aborted_restart/` holding a mistaken lifecycle reset's leftovers and a stale `OFFLOADED.md`
  from an earlier thesis.
- Upstream consumer contracts: `~/Personal/quant_strategies/docs/consumer/README.md` and
  `~/Personal/quant-data/docs/consumer/README.md`. Use these rather than inferring upstream behaviour
  from this repo.

```bash
conda run -n quant python -m loop status
conda run -n quant python -m pytest tests/ -q
```
