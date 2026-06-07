# quant_autoresearch

`quant_autoresearch` is a small autonomous research workbench for developing one quant strategy thesis at a time.

The shape is intentionally close to Karpathy's `autoresearch`: a short `program.md`, one narrow editable strategy surface, fixed read-only run configuration, and an append-only `results.tsv`. The trading-specific difference is that the loop never tunes against OOS. It only develops on Train and hands survivors to Season for downstream OOS, paper, and small-live review.

This is not a trading system, investment advice, or proof of deployability.

## Repository Map

| Path | Role |
| --- | --- |
| `program.md` | One-page agent operating contract. |
| `strategy.py` | Agent-editable pure signal logic. |
| `experiment.toml` | Agent-editable bounded strategy params. |
| `protocol.toml` | Operator-owned Train data, objective, gates, costs, fills, and loop constants. |
| `rationale.md` | Mechanism / observable / falsifier entries for signal components. |
| `loop.py` | Thin status and climb entry point. |
| `protocol.py` | Protocol loading and public quick-run config materialization. |
| `objective.py` | Train robustness objectives and plateau math. |
| `gates.py` | Binary Train gates. |
| `results_log.py` | Append-only `results.tsv` helpers. |
| `tests/` | Focused tests for the thin loop contract. |

## Editable Surface

The agent may edit:

- `strategy.py`
- `experiment.toml` `[params]`
- `rationale.md` when signal components change

The agent does not edit:

- symbols
- Train start/end
- data kind
- cost model
- fill model
- objective kind
- gate thresholds
- `plateau_patience`, `max_iterations`, `subwindows`, `min_abs_improvement`, or `min_rel_improvement`

Those live in `protocol.toml` and are chosen before a thesis starts.

## Loop

For one thesis:

1. Establish a feasible baseline.
2. Modify `strategy.py` or bounded params.
3. Run a Train quick run through public `quant_strategies.runner.run_config`.
4. Score the configured Train robustness objective.
5. Apply binary gates.
6. Keep only if all gates pass and the score improves beyond:

   ```text
   best + max(eps, rho * max(1, abs(best)))
   ```

7. Append one row to `results.tsv`.
8. Stop on plateau, max iterations, complexity cap, or baseline failure.

A Train survivor is only a handoff for Season. OOS, paper, and small-live review are outside this loop.

## Commands

```bash
conda run -n quant python -m pytest
conda run -n quant python -m loop status
conda run -n quant python -m loop climb --mechanism "<why it should work>" --falsifier "<what kills it>"
```

The `climb` command runs the current candidate once and logs the attempt. The autonomous editing loop is driven by the agent contract in `program.md`.

## Upstream Boundary

`quant_autoresearch` consumes `quant_strategies` through public APIs only. Strategy execution uses `quant_strategies.runner.run_config`; private engine modules are not part of this contract.

Quick-run economics expose trade-unit after-cost samples, not NAV or period-return series. That is enough for the v1 Train filter, but not enough for final validation.
