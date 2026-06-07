## Context

The foundation review identified three P0 risks that share one root cause: an attempted strategy run is not modeled as a complete evidence contract. Today, score/gates, result row identity, and lifecycle decision are split across code paths and agent procedure:

- `objective.py` produces scalar subwindow scores but not enough evidence coverage semantics.
- `gates.py` checks aggregate trade count, breadth, cost stress, complexity, and Train score, but not subwindow evidence coverage.
- `results_log.py` records metrics but not exact candidate/protocol/artifact identity.
- `loop.py` runs one candidate and logs it, but stop/revert/handoff state is not executable enough to prevent ambiguous continuation.

The change should fix the root contract, not add layered monitors. The conceptual unit is:

```text
Attempt =
  CandidateSnapshot
  + TrainEvidence
  + AttemptDecision
```

```text
CandidateSnapshot
  strategy_sha256
  experiment_sha256
  protocol_sha256
  rationale_sha256
  quick_config_sha256
  worktree_dirty
  artifact_dir

TrainEvidence
  score
  subwindow_scores
  subwindow_trade_counts
  gates

AttemptDecision
  keep | discard | crash
  best_status
  continuation
  stop_reason
```

## Goals / Non-Goals

**Goals:**

- Make missing subwindow evidence fail as a Train gate instead of passing as a zero score.
- Make every `results.tsv` row identify the exact candidate/protocol/artifact snapshot it describes.
- Make lifecycle state explicit enough that the agent can explore from discarded-but-informative working variants while the backend prevents any non-kept candidate from becoming the best or handoff candidate.
- Keep the loop small and local: one TSV row per attempt, generated artifacts under existing generated directories, public `quant_strategies.runner.run_config` only.

**Non-Goals:**

- Do not add OOS/evaluate into auto-research.
- Do not add DSR/PBO/CSCV or broader multiple-testing machinery.
- Do not implement paper/live infrastructure.
- Do not add a separate provenance log, stop-rule monitor, or warning-only subwindow checker.
- Do not perform implicit destructive git operations as the default discard behavior.

## Decisions

### Decision 1: Model subwindow evidence as a gate, not a score patch

Add protocol-owned `min_trades_per_subwindow` under `[gates]`. `score_worst_subwindow` should expose subwindow trade counts alongside scores, and `evaluate_gates` should add a binary `subwindow_coverage` outcome.

Alternatives considered:

- **Treat empty subwindows as infeasible inside the objective.** Simple, but too rigid for future slow strategies and hides the threshold in objective semantics.
- **Add warnings only.** Too weak; warnings are another layer and can be ignored by the LLM.

### Decision 2: Extend the result row as the attempt identity source

Add provenance fields directly to `results.tsv` rather than creating a sidecar log:

- `run_id`
- `artifact_dir`
- `worktree_dirty`
- `strategy_sha256`
- `experiment_sha256`
- `protocol_sha256`
- `rationale_sha256`
- `quick_config_sha256`
- `subwindow_trade_counts`
- `best_status`
- `continuation`

This preserves the repo's append-only TSV shape while making rows self-identifying.

Alternatives considered:

- **Separate manifest per row only.** Useful for artifacts, but the TSV would still be unsafe to scan alone.
- **Require a git commit per attempt.** Stronger but too heavy for local LLM iteration and does not capture generated config/artifact identity.

### Decision 3: Separate working exploration from best-selection state

Introduce a small state layer, likely in `loop.py` or a focused `state.py`, that derives:

- current best kept attempt,
- non-improving attempts since best,
- whether a terminal stop reason has already occurred,
- whether the current attempt updated the best candidate,
- whether continuation is allowed, blocked by terminal state, or blocked by an invalid workspace that needs repair.

For ordinary `discard`, the default behavior should be research-friendly: `best_status=unchanged` and `continuation=allowed`. The working snapshot may remain on the discarded variant if the agent has a thesis-guided reason to refine it. The backend guarantee is narrower and stronger: only `keep` updates `best_snapshot`, and only `best_snapshot` can become a Train survivor handoff.

For `crash`, continuation depends on whether the workspace is still valid. A simple first version may record `continuation=repair_required` when the run crashes before evidence is trustworthy.

Alternatives considered:

- **Automatic `git reset` on discard.** Too surprising and destructive for a shared dirty worktree.
- **Require restore after every discard.** Too restrictive; it collapses research into greedy hill-climbing and prevents useful failed variants from becoming the starting point for the next idea.
- **Leave best/working distinction only in prose.** Current root problem remains because non-kept evidence can be interpreted too loosely.

### Decision 4: Generated handoff/failure manifests summarize terminal state

When a terminal stop condition fires, write a generated manifest under `.autoresearch/handoffs/<run_id>/` or `results/autoresearch/<run_id>/handoff.json` with:

- terminal status: `train_survivor` or `train_failure`,
- stop reason,
- best kept attempt identity,
- protocol/strategy/experiment/rationale hashes,
- path to `results.tsv`,
- explicit note that this is not OOS, paper, or live evidence.

The manifest is generated evidence, not source.

## Risks / Trade-offs

- **Wider `results.tsv` is less compact** -> Keep fields stable and TSV-readable; do not add nested JSON except compact fields such as comma-separated subwindow counts.
- **Subwindow trade floors may reject legitimate slow strategies** -> Make the threshold protocol-owned per thesis; default for current crypto-perp quick loop can be strict enough to prevent idle slices.
- **Open-ended continuation can drift into score chasing** -> Non-improving attempts still count toward plateau and terminal stop rules; only kept attempts update best or handoff state.
- **Hashing dirty files does not make dirty work safe** -> The dirty flag plus hashes make the evidence honest, not automatically acceptable.
- **Backward compatibility with old `results.tsv` rows** -> Prefer migration-tolerant readers that can report legacy rows as missing provenance, but new rows must use the hardened header.

## Migration Plan

1. Add the new protocol field with a conservative default in `protocol.toml`.
2. Extend objective/gate data models and tests for subwindow trade counts and coverage.
3. Extend `ResultRow` schema and parsing. Decide whether legacy rows are rejected or marked as missing provenance; for this local repo, rejecting legacy rows with a clear error is acceptable if no active `results.tsv` exists.
4. Add attempt snapshot/provenance helpers.
5. Add lifecycle state derivation for best status, continuation state, and terminal refusal.
6. Add terminal manifest writing.
7. Update README/program wording to reflect the hardened attempt contract.

Rollback is straightforward before generated evidence exists: revert the code/spec change. After generated `results.tsv` rows exist, rollback requires discarding or archiving those generated rows because the schema differs.

## Open Questions

- What default `min_trades_per_subwindow` should `protocol.toml` use for the current 2-year BTC/ETH protocol? A simple starting point is `ceil(min_trades / subwindows / 2)`, but the operator may prefer an explicit value.
- Should the handoff manifest live under `.autoresearch/handoffs/` or under `results/autoresearch/<run_id>/`?
- What exact crash cases should use `continuation=repair_required` instead of `continuation=allowed`?
