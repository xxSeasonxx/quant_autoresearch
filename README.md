# quant_autoresearch

`quant_autoresearch` is a small autonomous research workbench for developing one quant strategy thesis at a time.

The shape is intentionally close to Karpathy's `autoresearch`: a short `program.md`, one narrow editable strategy surface, fixed read-only run configuration, and an append-only `results.tsv`. The trading-specific difference is that the loop never tunes against OOS. It only develops on Train and hands survivors to Season for downstream OOS, paper, and small-live review.

This is not a trading system, investment advice, or proof of deployability.

## Repository Map

| Path | Role |
| --- | --- |
| `program.md` | One-page agent operating contract. |
| `strategy.py` | Agent-editable target book: standing weight-of-NAV `TargetDecision`s. |
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
- capacity model
- leverage budget
- objective kind
- gate thresholds
- `plateau_patience`, `max_iterations`, `subwindows`, `min_abs_improvement`, or `min_rel_improvement`

Those live in `protocol.toml` and are chosen before a thesis starts.

## Artifact Authority

During an active thesis loop, the agent's active loop inputs are:

- `program.md`, `protocol.toml`, `experiment.toml`, `strategy.py`, and `rationale.md`
- recent `results.tsv`
- the latest quick-run artifact directory recorded in `results.tsv`, especially diagnostics needed to choose the next Train edit

Generated audit and handoff artifacts are evidence records, not source. Thesis locks, source snapshots, and terminal manifests preserve what happened and what should be handed to Season after a stop rule fires; they are not routine inputs for choosing Train edits.

Season downstream-only artifacts include OOS drift reviews, OOS evaluation artifacts, paper-test notes, and small-live notes. They must not feed back into the same Train loop.

Do not browse the rest of the repo during ordinary Train iteration unless debugging a failure, checking an explicitly in-scope contract, or Season asks.

## Loop

For one thesis:

1. Set the working thesis in `rationale.md`.
2. Establish a feasible baseline.
3. Modify `strategy.py` or bounded params.
4. Run a Train quick run through public `quant_strategies.runner.run_config`.
5. Review diagnostic output and update `rationale.md`.
6. Score the configured Train portfolio-foundation robustness objective.
7. Apply binary gates, including evidence coverage, cost stress, path risk, breadth, economic magnitude, aggregate trade floor, and subwindow coverage.
8. Let the loop decide keep/discard with the implemented keep rule:

   ```text
   all_gates_pass AND score > best + max(eps, rho * max(1, abs(best)))
   ```

9. Append one provenance-bearing row to `results.tsv`.
10. Stop on plateau, max iterations, complexity cap, or baseline failure.

A Train survivor is only a handoff for Season. OOS, paper, and small-live review are outside this loop. Use `docs/templates/oos-drift-review.md` for a one-look downstream OOS comparison, and `docs/adr/0001-curated-few-research-regime.md` for the current research-regime decision.

`results.tsv` records a compact, human-scannable metric set per attempt: objective score, full-Train PSR, worst-subwindow PSR/id, cost-stress PSR, gate flags, foundation closed-trade count, minimum subwindow trades, total return, max drawdown, max symbol concentration, gross/net utilization, ADV/bar participation, win rate, profit factor, average trade net, cost return sum, complexity count, a typed failure reason for non-scoreable runs, the artifact directory, and lifecycle state. Source provenance is preserved in the per-attempt snapshot; richer vectors, gate details, foundation warnings, and causality evidence live in the per-attempt `run_card.json` under the generated artifact directory. Only `keep` updates the best Train survivor; ordinary discarded variants may still remain useful working bases for thesis-guided follow-up edits. The complexity gate counts validated bounded params and signal components declared in `rationale.md` under `### Component:` headings.

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

There is one model of money: the single netted-book NAV path is the scored object, read from the quick-run portfolio foundation (compact full-Train and subwindow portfolio-return metrics for the Train score and gates). The per-trade economics tape is a derived attribution view of that same book, used for diagnostics only. Survivor-grade NAV/path traces still belong downstream, outside this Train loop.
