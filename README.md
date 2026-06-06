# quant_autoresearch

`quant_autoresearch` is a small research workbench for improving one quant
strategy candidate at a time.

The repo is intentionally narrow: an agent or researcher edits only the active
strategy and its experiment config, while the runner keeps the evaluation loop,
attempt ledger, promotion gates, and generated artifacts separate.

This is not a production trading system, investment advice, or a final
validation framework. It is a fast bench for finding candidates worth promoting
to deeper validation.

## What It Shows

The current public example is a crypto perpetual futures strategy candidate:
`crypto_perp_autoresearch_ensemble`.

The strategy started as a broad technical-vote ensemble and was iterated through
guarded screens. The important point is not that one backtest number improved;
it is that the workbench rejected tempting one-window gains and only promoted
candidates that survived a compact robustness screen.

> Note (rebuild P3): `results.tsv` is retired as the system-of-record — the
> append-only Trial Ledger (`harness/ledger.py`) is now canonical. The
> historical narrative below predates the rebuild and is reconciled in P5's
> doc rewrite.

Raw generated result directories are intentionally ignored, while the public
`results.tsv` ledger records the attempt history. The latest campaign showed
this progression:

| Stage | Change | Primary score/day | Guard evidence | Promotion score | Outcome |
| --- | --- | ---: | --- | ---: | --- |
| Baseline | Imported ensemble after contract fix | `-0.000021` | 628 trades | n/a | Baseline kept for comparison |
| First serious filter | Short-only technical vote filter | `0.000120` | H1 `0.000105` | `-0.000998` | Rejected by promotion |
| First promoted subset | Short-only ADA/XRP/AVAX/LINK | `0.000137` | H1 `0.000198` | `0.000080` | Promoted |
| Concentrated trio | Short-only ADA/XRP/AVAX | `0.000162` | H1 `0.000156` | `0.000098` | Promoted |
| Timing filter | Exclude weak decision hours `01/02/03/04/14` | `0.000279` | H1 `0.000210`, H2 `0.000206` | `0.000224` | Promoted |
| Sizing variant | Same signal, `base_position_pct = 0.20` | `0.000698` | H1 `0.000526`, H2 `0.000515` | `0.000561` | Promoted |
| Current promoted candidate | ADA-heavy weights plus excluded hour `20` | `0.001092` | H1 `0.000662`, H2 `0.000843` | `0.000905` | Promoted |
| Rejected high primary | Higher volatility threshold weight | `0.001169` | H1 `0.000631` | `0.000851` | Rejected despite higher primary |

Scores are runner-owned research metrics. The primary score is normalized by
window days when window metadata is available. Promotion score additionally
penalizes dispersion, failed sample gates, weak windows, symbol concentration,
and cost-stress fragility according to `experiment.toml`.

## How The Loop Works

The ordinary editable surface is small:

```text
strategy.py
experiment.toml
```

The harness is deliberately treated as stable during strategy research:

```text
program.md
runner.py
scoring.py
experiment_config.py
promotion.py
artifact_policy.py
```

The loop is:

1. Establish a baseline on the configured primary window.
2. Make one focused strategy or experiment change.
3. Run a cheap explore screen.
4. Run one or more guard diagnostics only when the result is plausible.
5. Promote only serious candidates through the compact robustness screen.
6. Send promoted candidates to a separate comprehensive validation process.

The loop is designed to prevent common autoresearch failure modes:

- overfitting one recent window
- treating parameter sweeps as new strategy logic
- hiding upstream data or engine limitations inside `strategy.py`
- confusing a promoted candidate with final validation

## Current Strategy

`strategy.py` exposes the decision-strategy contract expected by the local
runner:

```python
generate_decisions(rows, params)
validate_params(params)
```

The active candidate uses completed hourly crypto perpetual bars and emits
target-weight decisions when a group of technical votes agrees. The current
config focuses on an ADA/XRP/AVAX universe with short-only entries, timing
filters, ATR-based risk exits, and explicit promotion screens across recent and
diagnostic windows.

The strategy code includes the market rationale, required observables,
assumptions, and falsifier. If an idea needs upstream engine or data support,
it belongs in `UPSTREAM_LIMITATIONS_TODO.md` rather than being approximated in a
misleading way inside the strategy.

## Running Locally

This repo delegates execution to `quant_strategies.runner.run_config` and
expects local market data access. A fresh public clone is useful for reading the
workflow and strategy, but it will not run unless your environment can resolve
the `quant-strategies` dependency and its data requirements.

With the local stack available:

```bash
conda run -n quant python runner.py --explore --description "baseline"
```

Run one guarded diagnostic window without updating the best candidate:

```bash
conda run -n quant python runner.py --window-id validation_2025_h1 --description "guard: idea"
```

Promote a serious candidate:

```bash
conda run -n quant python runner.py --promote --description "promote candidate: idea"
```

The public ledger is committed for auditability:

```text
results.tsv
```

Raw generated artifacts stay out of git:

```text
results/session_state.json
results/<attempt>/score.json
results/<attempt>/summary.json
results/<attempt>/evidence.json
results/<attempt>/promotion_score.json
```

## Repository Map

- `strategy.py` - active scratch strategy candidate
- `experiment.toml` - windows, universe, params, scoring, promotion, artifacts
- `runner.py` - attempt orchestration and ledger writing
- `promotion.py` - promotion screen logic
- `scoring.py` - score normalization and sample gates
- `experiment_config.py` - config parsing and validation
- `program.md` - durable research-loop instructions for agents
- `tests/` - harness and contract tests

## Caveats

- These are research-bench results, not live trading claims.
- Promotion is a screening step, not comprehensive validation.
- Cost, fill, data availability, and sample quality assumptions matter.
- The current candidate is intentionally simple enough to audit; extra
  complexity needs to pay for itself with stronger guarded evidence.
