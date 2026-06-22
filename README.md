# quant_autoresearch

`quant_autoresearch` is a small autonomous research workbench for developing one quant strategy thesis at a time.

The shape is intentionally close to Karpathy's `autoresearch`: a short `program.md`, one narrow editable strategy surface, fixed read-only run configuration, and an append-only `results.tsv`. The trading-specific difference is that the loop never tunes against OOS. It only develops on Train and hands survivors to Season for downstream OOS, paper, and small-live review.

This is not a trading system, investment advice, or proof of deployability.

For a new plain-language strategy idea, invoke the `new-thesis-setup` skill
(`/new-thesis-setup`). It owns mandate collection, protocol proposal, approval,
lifecycle reset, and first baseline preflight.

Root files may hold either the neutral scaffold or an active local thesis. Use
`python -m loop status` as the lifecycle-state source; do not infer state from
checkout comments or strategy names alone.

## Active Documents

| Path | Role |
| --- | --- |
| `new-thesis-setup` skill | New-thesis setup workflow (`/new-thesis-setup`); the filled brief lives under `.autoresearch/protocol_briefs/`. |
| `program.md` | Agent operating contract for one active Train loop. |
| `docs/score_research.md` | Train money-score rationale and scoring boundaries. |
| `docs/adr/0001-curated-few-research-regime.md` | Research-regime decision. |
| `docs/templates/oos-drift-review.md` | Downstream one-look OOS drift review template. |
| `HISTORY.md` | Development chronology and migration rationale. |

## Editable Surface

The agent may edit:

- `strategy.py`
- `experiment.toml` `[params]`, within the existing `[bounds.*]`
- `rationale.md` when variants are tried or signal components change

The agent does not edit during an active thesis loop:

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

Those live in `protocol.toml` and are chosen through the `new-thesis-setup` skill
before a thesis starts. A new-thesis setup can use explicit `symbols` or a
`.autoresearch/universe/` resolver artifact; `propose-protocol` maps the approved
symbol list into the recommendation table but does not edit `protocol.toml`.

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

9. Append one compact row to `results.tsv`; source provenance is preserved in the
   attempt snapshot under the row's `artifact_dir`.
10. Stop on plateau, max iterations, complexity cap, or baseline failure.

A Train survivor is only a handoff for Season. OOS, paper, and small-live review are outside this loop. Use `docs/templates/oos-drift-review.md` for a one-look downstream OOS comparison, and `docs/adr/0001-curated-few-research-regime.md` for the current research-regime decision.

`results.tsv` records a compact, human-scannable metric set per attempt:
deployed-return LCB score, worst-window id and annualized return, deflated money
floor, full-Train annualized return, cost-stress return retention, sizing,
diagnostic PSR fields, gate flags, foundation closed-trade count, minimum
subwindow trades, total return, max drawdown, max symbol concentration, win rate,
profit factor, average trade net, cost return sum, complexity count, typed failure
reason, artifact directory, and lifecycle state. Source provenance is preserved
in the per-attempt snapshot; richer vectors, gate details, foundation warnings,
and causality evidence live in the per-attempt `run_card.json` under the generated
artifact directory. Only `keep` updates the best Train survivor; ordinary
discarded variants may still remain useful working bases for thesis-guided
follow-up edits. The complexity gate counts validated bounded params and signal
components declared in `rationale.md` under `### Component:` headings.

## Commands

```bash
conda run -n quant python -m pytest
conda run -n quant python -m loop resolve-universe --data-kind crypto_perp_funding --dataset crypto_perp_1min_with_funding --start 2025-03-01 --end 2025-12-31 --exclude MATIC-PERP --out .autoresearch/universe/latest.json
conda run -n quant python -m loop propose-protocol --brief .autoresearch/protocol_briefs/latest.md --out .autoresearch/protocol_proposals/latest.json
conda run -n quant python -m loop baseline --mechanism "<why it should work>" --falsifier "<what kills it>" --approved-proposal .autoresearch/protocol_proposals/latest.json
conda run -n quant python -m loop status
conda run -n quant python -m loop climb --mechanism "<why it should work>" --falsifier "<what kills it>"
conda run -n quant python -m loop reset --confirm RESET-LIFECYCLE
```

The `resolve-universe` command writes a return-blind eligibility artifact from
catalog/readiness metadata only. The `propose-protocol` command writes proposal
artifacts only; it does not edit `protocol.toml`. The `baseline` command
validates an approved proposal before the first attempt, then uses the normal
climb path. The `climb` command runs the current candidate once and logs the
attempt. The `reset` command archives generated lifecycle state only:
`results.tsv`, `.autoresearch/thesis_lock.json`, and `.autoresearch/quick/`.
It does not edit `strategy.py`, `protocol.toml`, `experiment.toml`, or
`rationale.md`. The autonomous editing loop is driven by the agent contract in
`program.md`.

The configured local environment can reach `quant_data` for real quick-run smoke checks, but data freshness and runtime still depend on the selected dataset/window. Generated run artifacts live under `results/` and are not source.

## Upstream Boundary

`quant_autoresearch` consumes `quant_strategies` through public APIs only. Strategy execution uses `quant_strategies.runner.run_config`; private engine modules are not part of this contract.

There is one model of money: the single netted-book NAV path is the scored object, read from the quick-run portfolio foundation (compact full-Train and subwindow portfolio-return metrics for the Train score and gates). The per-trade economics tape is a derived attribution view of that same book, used for diagnostics only. Survivor-grade NAV/path traces still belong downstream, outside this Train loop.
