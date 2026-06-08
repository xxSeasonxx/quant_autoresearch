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
| `rationale.md` | Working thesis, signal components, and variant log. |
| `loop.py` | Thin status and climb entry point. |
| `protocol.py` | Protocol loading and public quick-run config materialization. |
| `objective.py` | Train robustness objectives and plateau math. |
| `gates.py` | Binary Train gates. |
| `results_log.py` | Append-only `results.tsv` helpers. |
| `tests/` | Focused tests for the thin loop contract. |

## Editable Surface

The agent may edit:

- `strategy.py`
- `experiment.toml` `[params]`, within the existing `[bounds.*]`
- `rationale.md` when variants are tried or signal components change

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

1. Set the working thesis in `rationale.md`.
2. Establish a feasible baseline.
3. Modify `strategy.py` or bounded params.
4. Run a Train quick run through public `quant_strategies.runner.run_config`.
5. Review diagnostic output and update `rationale.md`.
6. Score the configured Train trade-unit robustness objective.
7. Apply binary gates, including aggregate trade floor and subwindow coverage.
8. Let the loop decide keep/discard with the implemented keep rule:

   ```text
   all_gates_pass AND score > best + max(eps, rho * max(1, abs(best)))
   ```

9. Append one provenance-bearing row to `results.tsv`.
10. Stop on plateau, max iterations, complexity cap, or baseline failure.

A Train survivor is only a handoff for Season. OOS, paper, and small-live review are outside this loop. Use `docs/templates/oos-drift-review.md` for a one-look downstream OOS comparison, and `docs/adr/0001-curated-few-research-regime.md` for the current research-regime decision.

`results.tsv` records both control metrics and intuitive diagnostics: attempt provenance, objective score, gate flags, subwindow trade counts, trade count, concentration, cost stress, net return sum, average trade net, win rate, profit factor, gross return sum, cost return sum, and lifecycle state. Only `keep` updates the best Train survivor; ordinary discarded variants may still remain useful working bases for thesis-guided follow-up edits. The complexity gate counts validated bounded params and signal components declared in `rationale.md` under `### Component:` headings.

## Commands

```bash
conda run -n quant python -m pytest
conda run -n quant python -m loop status
conda run -n quant python -m loop climb --mechanism "<why it should work>" --falsifier "<what kills it>"
```

The `climb` command runs the current candidate once and logs the attempt. The autonomous editing loop is driven by the agent contract in `program.md`.

The configured local environment can reach `quant_data` for real quick-run smoke checks, but data freshness and runtime still depend on the selected dataset/window. Generated run artifacts live under `results/` and are not source.

## Upstream Boundary

`quant_autoresearch` consumes `quant_strategies` through public APIs only. Strategy execution uses `quant_strategies.runner.run_config`; private engine modules are not part of this contract.

Quick-run economics expose trade-unit after-cost samples, not NAV or period-return series. That is enough for the v1 Train filter, but not enough for final validation.
