# quant_autoresearch

`quant_autoresearch` is an autonomous quant research harness. An LLM agent proposes one strategy
hypothesis at a time and develops it; an **immutable evaluator** decides — mechanically — whether
the result is a real, out-of-sample, risk-adjusted edge worth graduating.

A backtest score is a *biased* estimator of future performance, and the bias *grows with the
number of trials*. An agent that "optimizes one number, keep/discard, loop" therefore converges on
the most overfit strategy. This repo's answer is to put the rigor in a harness the agent cannot
edit, and keep the agent's contract a one-page loop:

- **Rigor in the harness** — the `harness/` package enforces the data wall, the Robust Edge Score,
  every gate, the trial budget, the stability check, the escalation gate, and the graduation audit.
- **Simplicity in the contract** — the agent edits only `strategy.py` and `experiment.toml`
  `[params]`, and runs three commands. See `program.md`.

This is **not** a production trading system, investment advice, or a final validation framework.
Graduation is a screen, not a production sign-off.

## The two halves

| Half | What it is | Editable by the agent? |
| --- | --- | --- |
| **The harness** (`harness/`) | The immutable evaluator: Protocol/Experiment wall, RES objective, data tiers + walk-forward, trial ledger + global budget + family fingerprint, escalation gate + stability, graduation audit + power-aware Lockbox, the CLI and session shell. | No — read-only, content-hashed, fails closed on drift. |
| **The candidate** (`strategy.py`, `experiment.toml`) | One scratch strategy + its params (+ an optional bounded symbol set). | Yes — this is the whole editable surface. |

## The data wall

Every candidate is developed, selected, and confirmed on three disjoint partitions fixed in the
Protocol and never editable by the agent:

- **Train** — optimize freely and fast; the agent sees full diagnostics. FREE, unlimited.
- **Selection** — a forward-only walk-forward; the agent sees only the summary Robust Edge Score.
  Each look costs ONE from a small, global, data-derived budget.
- **Lockbox** — a one-shot, human-gated, write-once-per-dataset confirmation. The agent never
  touches it.

## The verdict ladder

`feedback → graduate → lockbox → human promotion`. The loop only ever *graduates* a candidate up
the ladder; "promotion" is the human step above the Lockbox. The Lockbox verdict is **trichotomous**:

- **confirmed** — a real edge at the stated confidence;
- **rejected** — a powered look that came back flat or negative;
- **insufficient-evidence** — the data cannot support a verdict (the harness never lowers the bar
  to manufacture one).

## The loop

The agent runs three commands (all under `conda run -n quant`):

```bash
conda run -n quant python -m harness.cli status
conda run -n quant python -m harness.cli run --desc "<thesis>"
conda run -n quant python -m harness.cli evaluate --desc "<thesis> | falsifier: <what kills it>"
```

`run` is the free Train sandbox; `evaluate` is the gated, budgeted Selection look — the harness
applies the escalation gate (valid · alive · in-sample positive · a structurally NEW thesis ·
not single-symbol-carried · not a knife-edge) and the budget, and only then logs the bet. There
is no hill-climb: each `evaluate` is a recorded bet, never a "keep if the score rose" step. See
`program.md` for the full one-page contract.

## Repository map

- `strategy.py` — the active scratch strategy candidate (a simple time-series momentum example).
- `experiment.toml` — the agent-editable hypothesis surface: `strategy_path` + `[params]` (+ optional `symbols`).
- `protocol.toml` — the harness-owned, read-only judgment config (costs, tiers, objective, gates, budget, stability, Lockbox).
- `harness/` — the immutable evaluator (see `docs/harness-architecture.md`).
- `program.md` — the one-page agent loop.
- `AGENTS.md` — the durable agent role and boundaries.
- `docs/` — the methodology, PRD, and the diagnosed-overfit case study that motivated the rebuild.
- `tests/` — harness + contract tests (each names the acceptance criterion it covers).

## The diagnosed campaign (why this exists)

An earlier version of this bench optimized an in-sample, leverage-inflated, zero-cost,
single-regime number with an unlimited trial budget. Over ~100 attempts it produced a textbook
overfit — an ADA-only, short-only, six-excluded-clock-hours bet with sizing cranked to 0.20,
dressed up as a diversified basket. That number rose; the edge was not real. Replaying that
campaign through this harness yields *infeasible / rejected / insufficient-evidence* — never a
graduation (the headline acceptance test, AC-1). The full diagnosis lives in
`docs/auto-research-methodology.md`; the historical `results.tsv`-based showcase is retired (the
append-only trial ledger is now the system of record).

## Running locally

This repo delegates execution to `quant_strategies` and expects local market-data access via
`quant_data`. A fresh public clone is useful for reading the workflow and the harness, but it will
not run unless your environment can resolve the `quant-strategies` dependency and its data
requirements.

```bash
conda run -n quant python -m pytest        # the harness + contract test suite
```

## Before a live campaign (known limitations)

The harness logic is fully verified in-process — the test suite covers AC-1..AC-10
deterministically against a fake foundation gateway and synthetic return series. A few things
must still be checked before pointing it at live capital:

- **Live data is required for real verdicts.** Real end-to-end paths (a real foundation fold, the
  live factor-panel build, bit-for-bit metric reproduction from a real `quant_data` snapshot) are
  exercised only by data-gated smoke tests, which *skip* without database access. Run them against
  a live `quant_data` before trusting a real campaign.
- **Configure the correct, aligned benchmark for the factor panel.** Residual-alpha scoring
  neutralizes market/funding beta against an operator-supplied benchmark. The harness fails closed
  unless each required factor column is a legitimate, well-conditioned, correctly time-aligned
  return series — but it cannot verify the benchmark is *semantically* the right factor. Supply the
  real market/funding benchmark for the asset (e.g. BTC-PERP for alts); a wrong-but-valid benchmark
  would silently fail to neutralize.
- **Audit FWER has a small near-unit-root residual.** The Romano-Wolf graduation audit controls
  the false-graduation rate at the configured level across realistic serial correlation; at extreme
  persistence (AR1 ≈ 0.8) the finite-sample rate sits modestly above nominal (~0.077 vs 0.05) and
  shrinks with sample size. Documented in `harness/audit.py`.
- **`profile` and `lockbox` are operator-invoked.** The agent CLI wires `status`/`run`/`evaluate`
  plus the admin `graduate`; asset profiling and the human-gated, one-shot Lockbox confirmation are
  invoked programmatically by the operator (Lockbox is human-gated by design).
- **Single supplied factor panel.** The panel is the operator's benchmark (market + funding-carry);
  auto-derived multi-factor panels are out of scope.

## Caveats

- These are research-bench results, not live trading claims.
- Graduation is a screening step, not comprehensive validation.
- Cost, fill, data availability, and sample quality assumptions matter, and live in the Protocol.
