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

## Worked example — a thesis this loop researched end-to-end

**Crypto Perp Funding-Crowding Reversal.** One human-seeded thesis — crowded crypto-perp
positioning mean-reverts — developed over 45 autonomous iterations under a frozen protocol,
each attempt kept or killed by the evidence gates below. The survivor:

> **Train-only research evidence — not OOS, paper, live, or deployability evidence.** These
> metrics are in-sample by construction.

| Metric | Value |
|---|---:|
| Full-window total return (net) | **+20.1%** |
| Profit factor | 1.98 |
| Win rate | 56.9% (170 / 129) |
| Max drawdown | −5.6% |
| Trades | 299 (avg +6.7 bps net) |
| Subwindow robustness | 6 / 6 positive |
| Evidence gates | **9 / 9 pass** |

Window 2025-03-01 → 2025-12-31, 8 crypto-perp majors, 1-minute bars, net of fees + slippage +
market impact. The edge is a single interpretable change from the baseline — a conviction
filter — that improved every metric at once, the signature of a real effect rather than an
overfit.

### The research journey

45 iterations ran; most ideas were **falsified** — and that is the signal. The arc:

| # | Idea tried | Return | Verdict |
|---|---|---:|---|
| 0001 | Baseline — long-only fade of crowded shorts, 720m hold | 0.181 | ✅ kept |
| 0002 | Add the short side | −0.003 | ❌ loses; can't reach the vol target |
| 0003 | Shorter hold (360m) | 0.066 | ❌ clips the slow bounce |
| 0004 | Longer hold (1080m) | 0.085 | ❌ gives the bounce back |
| 0005 | Trailing stop | 0.010 | ❌ fires on the overshoot a fade must hold |
| 0007 | Faster cadence (120m) | 0.035 | ❌ earlier, weaker entries dilute the signal |
| 0009 | Recency-weighted funding | 0.047 | ❌ the crowd reads best equal-weighted |
| 0016 | Funding-magnitude filter | 0.085 | ❌ wrong lever; crushes breadth |
| 0025 | Reversion-completion exit | 0.068 | ❌ exits before the absolute price peak |
| 0035 | Dislocation conviction ≥ 4 bps | 0.195 | ▫️ the search warms up |
| **0014** | **Dislocation conviction ≥ 5 bps** | **0.201** | 🏆 **survivor** |
| 0017 | Dislocation conviction ≥ 6 bps | 0.188 | ▫️ past the peak |
| 0018 | Concentrate to top-3 names | 0.199 | ▫️ near-best |

The one durable win is a smooth local maximum, not a razor edge — min-dislocation
2.5 → 0.181, 4 → 0.195, **5 → 0.201**, 6 → 0.188, 8 → 0.187.

### The keep/kill gates every survivor must clear

`trade_floor` (≥ 120 trades) · `minimum_evidence` (≥ 100 samples, ≥ 50 per subwindow) ·
`path_risk` (max drawdown ≤ 25%) · `train_strength` (`return − 2·SE ≥ 0`) ·
`cost_stress_retention` (≥ 50% of the edge survives a cost stress test) · `breadth` +
`effective_symbol_count` (edge not carried by one name) · `causality` (no decision uses data
before it was knowable) · `complexity_cap` (≤ 3 components, ≤ 50 params). A result is *kept*
only if it beats the incumbent **and** clears every gate. The authoritative contract is
`docs/score_research.md`.

## Active Documents

| Path | Role |
| --- | --- |
| `new-thesis-setup` skill | New-thesis setup workflow (`/new-thesis-setup`); the filled brief lives under `.autoresearch/protocol_briefs/`. |
| `program.md` | Agent operating contract for one active Train loop. |
| `docs/score_research.md` | Train score, gate, result-ledger, and run-card contract. |
| `docs/adr/0001-curated-few-research-regime.md` | Research-regime decision. |
| `docs/templates/oos-drift-review.md` | Downstream one-look OOS drift review template. |
| `HISTORY.md` | Development chronology and migration rationale. |

On any conflict between documents, `program.md` and `protocol.toml` govern — except
the score, gate, and result-ledger contract, which `docs/score_research.md` owns.

## Editable Surface

The agent may edit:

- `strategy.py`
- `experiment.toml` `[params]` and their `[bounds.*]` ranges — the agent owns the
  search space and may widen or tighten a bound as the mechanism demands (an
  ordinary loop edit, not a reseed)
- `rationale.md` when variants are tried or signal components change
- `reseed_log.md` — append-only reseed evidence; write during the loop, read at stop

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

- `program.md`, `protocol.toml`, `docs/score_research.md`, `experiment.toml`, `strategy.py`, and `rationale.md`
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
6. Apply the Train score and gates defined in `docs/score_research.md`.
7. Let the loop decide keep/discard with the implemented improvement rule.

8. Confirm `climb` appended exactly one row to `results.tsv`; do not write it
   yourself. Source provenance is preserved in the attempt snapshot under the row's
   `artifact_dir`.
9. Stop when a configured rule fires; `program.md` (Stop) owns the authoritative
   stop taxonomy.

A Train survivor is only a handoff for Season. OOS, paper, and small-live review are outside this loop. Use `docs/templates/oos-drift-review.md` for a one-look downstream OOS comparison, and `docs/adr/0001-curated-few-research-regime.md` for the current research-regime decision.

`results.tsv` records one compact, human-scannable row per attempt. The exact
ledger and run-card fields are defined in
`docs/score_research.md#results-and-run-cards`. Source provenance is preserved in
the per-attempt snapshot. Only `keep` updates the best Train survivor; ordinary
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
conda run -n quant python -m loop climb
conda run -n quant python -m loop reset --confirm RESET-LIFECYCLE
```

The `resolve-universe` command writes a return-blind eligibility artifact from
catalog/readiness metadata only. The `propose-protocol` command writes proposal
artifacts only; it does not edit `protocol.toml`. The `baseline` command
validates an approved proposal before the first attempt, then uses the normal
climb path. The `climb` command runs the current candidate once and logs the
attempt; the frozen thesis identity is sourced from the lock, so `climb` no longer
requires `--mechanism`/`--falsifier` (they stay optional, for an explicit re-check
against the lock). The `reset` command archives generated lifecycle state only:
`results.tsv`, `.autoresearch/thesis_lock.json`, `.autoresearch/quick/`, and the
`results/autoresearch/` attempt-artifact tree.
It does not edit `strategy.py`, `protocol.toml`, `experiment.toml`,
`rationale.md`, or `reseed_log.md`. The autonomous editing loop is driven by the agent contract in
`program.md`.

The configured local environment can reach `quant_data` for real quick-run smoke checks, but data freshness and runtime still depend on the selected dataset/window. Generated run artifacts live under `results/` and are not source.

## Upstream Boundary

`quant_autoresearch` consumes `quant_strategies` through public APIs only. Strategy execution uses `quant_strategies.runner.run_config`; private engine modules are not part of this contract.

There is one model of money: the single netted-book NAV path is the scored object, read from the quick-run portfolio foundation (compact full-Train and subwindow portfolio-return metrics for the Train score and gates). The per-trade economics tape is a derived attribution view of that same book, used for diagnostics only. Survivor-grade NAV/path traces still belong downstream, outside this Train loop.
