# Foundation Review: quant_autoresearch

Date: 2026-06-08
Reviewer: Codex, with independent onboarding, architecture, senior engineering, adversarial, and quant math/code lenses
Target: `/Users/Season_Yang/Personal/quant_autoresearch`

## Executive Verdict

`quant_autoresearch` is now the right small shape for the stated objective, but it is not yet a fully trustworthy foundation for downstream review.

The repo correctly follows the useful part of `karpathy/autoresearch`: a short agent contract, a narrow editable file surface, fixed operator-owned assumptions, and an append-only experiment log. The trading-specific changes are also directionally correct: Train-only iteration, robustness/gate filtering instead of raw-return chasing, bounded stopping, and OOS kept outside the loop.

The remaining foundation risk is not "needs more quant machinery." It is identity and evidence integrity. A terminal Train survivor can currently snapshot the current workspace rather than the best kept attempt, and the active thesis/protocol lifecycle is not locked even though protocol hashes are recorded. Those two issues can make downstream OOS/paper review inspect stale or mismatched evidence. Fix those before trusting any frozen Train survivor.

On the product questions:

- One OOS comparison belongs in the research process, but downstream of a frozen Train survivor, not inside the LLM Train loop.
- The setup matches a personal curated-few quant process, not institutional model validation or automated-many mining.
- The project is simple enough; the needed fixes are boundary contracts, not a framework rewrite.
- The current two-year BTC/ETH Train window is a plausible default, not a universal truth. It needs a protocol rationale per thesis.
- The LLM should not freely choose symbols to maximize score inside a thesis. Universe changes should be explicit protocol variants owned by Season.

Impact calibration:

- P0 items are correctness boundaries. They should block trusting a frozen Train survivor.
- P1 items are hardening boundaries. They reduce silent evidence drift but should be implemented as small validators or manifest fields.
- P2/P3 items are process clarity and semantics. They should not become new research machinery.
- Do not turn any recommendation here into automated OOS tuning, a candidate-family ledger, a database, or a framework unless the curated-few ADR escalation triggers occur.

Status note after follow-up changes:

- P0 identity items are addressed by `harden-run-identity-and-survivor-handoff`.
- P1 protocol/result boundary validation is addressed by `validate-protocol-and-results-boundaries`.
- P1 OOS binding and quick-run evidence flags remain deferred to avoid adding artifacts or active-loop cognitive load before real runs show the need.

## Scope And Evidence Inspected

Objective lock:

`quant_autoresearch` should serve Season as PM/research owner, plus downstream OOS/paper/small-live reviewers, by enabling an LLM-driven Train-only autoresearch loop that makes simple causal strategy changes, records evidence, and produces either a frozen Train survivor or a clear Train failure across one human-seeded thesis lifecycle. A solid foundation should make disciplined, auditable thesis testing easy and prevent protocol drift, hidden data/fill/cost assumption changes, stale or invalid evidence, false deployability claims, overfit Train results mistaken for profitability, and framework-like complexity, while respecting non-goals around protocol-owned assumptions and human-gated downstream validation.

Inspected evidence:

- Repo instructions and active operating docs: `AGENTS.md`, `README.md`, `program.md`, `protocol.toml`, `experiment.toml`, `rationale.md`.
- Core source: `loop.py`, `protocol.py`, `objective.py`, `gates.py`, `results_log.py`, `strategy.py`.
- Tests/specs: `tests/`, `openspec/specs/`.
- Supporting docs: `docs/simplified-autoresearch-loop-design.md`, `docs/adr/0001-curated-few-research-regime.md`, `docs/templates/oos-drift-review.md`, prior `docs/reviews/foundation-review-20260607.md`.
- Named upstream context: `/Users/Season_Yang/Personal/quant_strategies/docs/consumer/README.md`, `reference.md`, and `usage-guide.md`.
- Reference inspiration: upstream `karpathy/autoresearch` README, `program.md`, and `train.py` were fetched directly; `prepare.py` raw fetch hit a rate limit, but the upstream README describes its role.

Independent lens process:

- Onboarding lens checked whether a competent engineer can understand entry points, data flow, and workflow from source.
- Architecture lens checked bounded contexts, dependency direction, contracts, and right-sizedness.
- Senior engineering lens checked tests, CLI ergonomics, result parsing, type boundaries, and operability.
- Adversarial lens checked how a capable LLM could drift, rationalize, or contaminate evidence.
- Quant math/code lens checked timing, fills, costs, PnL labels, validation semantics, and artifact identity.

Not inspected deeply:

- `quant_strategies` internals beyond consumer docs.
- Real `quant_data` freshness or coverage.
- A real market-data-backed `climb` run.
- OOS, paper, or small-live behavior.

## Intended Foundation Model

The minimal foundation is a curated-few quant research loop:

```text
Season seeds one thesis
  mechanism + falsifier + protocol rationale
        |
        v
Protocol lock
  symbols, Train window, costs, fills, objective, gates, stop rules
        |
        v
LLM edits only strategy.py + bounded params + rationale.md
        |
        v
Public quick run through quant_strategies.runner.run_config
        |
        v
Train trade-unit evidence -> objective score + binary gates
        |
        +--> discard/crash: log exactly once, keep best unchanged
        |
        +--> keep: record exact kept candidate identity
        |
        v
Terminal stop: plateau | max iterations | complexity | baseline failure
        |
        v
Frozen Train survivor or explicit Train failure
        |
        v
Season-owned one-look OOS drift review -> paper -> small live
```

The system needs hard contracts at exactly three places:

- Before the loop: the thesis/protocol/bounds identity must be locked.
- During the loop: every attempt row must tie score, gates, source, params, protocol, and artifacts together.
- After the loop: the terminal handoff must point to the exact best kept candidate, not the latest workspace state.

Everything else should stay small and boring.

## Project Ontology: Concepts, Contracts, Boundaries, Invariants


| Concept           | Owner                         | Contract                                                              | Invariant                                                                          |
| ----------------- | ----------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Thesis            | Season                        | One mechanism and falsifier for a run                                 | Results from one thesis must not mix with another                                  |
| Protocol          | Season/operator               | Train data, symbols, costs, fills, objective, gates, loop constants   | Frozen once attempts begin                                                         |
| Experiment params | LLM within bounds             | Numeric params under `[params]`                                       | Bounds are operator-owned for the thesis                                           |
| Strategy          | LLM                           | Pure `generate_decisions(rows, params)` plus strict `validate_params` | No data loading, private engine access, OOS, clocks, RNG, or hidden protocol knobs |
| Rationale         | LLM + Season review           | Component declarations, mechanism, observable, falsifier, variants    | Component count and explanation remain auditable                                   |
| Quick-run result  | `quant_strategies` public API | `RunResult.succeeded`, economics, evidence, artifacts                 | Operational warnings are not strategy evidence                                     |
| Objective         | `objective.py`                | One configured Train trade-unit robustness score                      | Score is a filter, not proof of edge                                               |
| Gates             | `gates.py`                    | Binary feasibility checks                                             | Failed gates prevent keep                                                          |
| Result row        | `results_log.py`              | One append-only TSV row per attempted iteration                       | Rows must identify the exact candidate and protocol snapshot                       |
| Terminal manifest | `loop.py`                     | Frozen Train survivor or Train failure                                | Survivor snapshot must match the best kept attempt                                 |
| OOS review        | Season                        | One-look downstream artifact                                          | Must not feed back into same-candidate tuning                                      |


The most important invalid states to prevent:

- A Train survivor manifest contains code that did not produce the best Train score.
- A later attempt uses changed protocol assumptions while comparing against earlier scores.
- A stale or hand-edited `results.tsv` row changes best/stop decisions silently.
- A Train robustness score is read as deployability or OOS evidence.
- The LLM turns symbols, dates, sessions, or cost assumptions into hidden strategy parameters.

## What Already Exists And Should Be Reused


| Existing boundary                              | Assessment                                                                               | Preserve / use                                     |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `program.md`                                   | Clear, compact agent contract modeled after the reference project                        | Preserve as the primary LLM-facing contract        |
| `protocol.toml`                                | Correctly owns symbols, Train window, costs, fills, objective, gates, and loop constants | Preserve; add executable lock semantics            |
| `protocol.py`                                  | Clean materialization of public quick-run config                                         | Preserve public `run_config` dependency            |
| `strategy.py`                                  | Simple single-file causal baseline using `available_at` and public decision models       | Preserve as a baseline example                     |
| `objective.py` + `gates.py`                    | Small score/gate separation and subwindow coverage                                       | Preserve; clarify some labels                      |
| `results_log.py`                               | Simple append/read/status TSV helpers                                                    | Preserve; add semantic validation                  |
| `docs/templates/oos-drift-review.md`           | Right downstream concept: one-look comparison outside the loop                           | Preserve; bind it to frozen manifests              |
| `docs/adr/0001-curated-few-research-regime.md` | Correctly chooses curated-few over automated-many                                        | Preserve as the constraint against framework creep |
| Tests                                          | Focused and currently cover many prior gaps                                              | Extend around identity/lifecycle edge cases        |


## Architecture And Boundary Review

### Finding 1: Terminal handoff can snapshot the wrong candidate

- Severity: Critical
- Action class: Refactor
- Evidence: `loop.py:310-327`, `loop.py:314-318`, `loop.py:324-328`, `program.md:131-139`, `README.md:68`.
- What is wrong: `_write_terminal_manifest()` selects `best = _best_row(rows)`, but copies the current workspace `strategy.py`, `experiment.toml`, `protocol.toml`, and `rationale.md` into the terminal `snapshot/`. If the loop keeps a good candidate, then later leaves a discarded variant in the workspace and stops on plateau, the manifest can say `train_survivor` while snapshotting the discarded variant.
- First-principles reason it matters: Downstream OOS review consumes the frozen survivor. If the survivor artifact is not the exact candidate that earned the Train score, every later OOS/paper decision is contaminated.
- Root cause: Terminal attempt identity and best survivor identity are conflated in one manifest.
- Recommendation: Persist exact source snapshots for every attempt or at least every `keep`, then build terminal survivor handoff from the best kept attempt snapshot. Separate `terminal_attempt_snapshot` from `best_survivor_snapshot`. Freeze a copy of `results.tsv` into the terminal artifact.
- Tradeoff and scope: Adds a small artifact contract, not a new research framework.
- Verification needed: Add a test where attempt 1 is `keep`, attempt 2 is `discard`, plateau fires, and terminal snapshot hashes equal attempt 1 hashes rather than current workspace hashes.

### Finding 2: Active thesis/protocol identity is not executable

- Severity: Critical
- Action class: Add
- Evidence: `program.md:11-13`, `program.md:41-51`, `loop.py:714-733`, `loop.py:142-149`, `results_log.py:41-74`, `openspec/specs/autoresearch-protocol/spec.md:12-21`.
- What is wrong: Result rows record `protocol_sha256`, but continuation logic does not require the current protocol, bounds, or thesis identity to match the active run. `climb_once()` reads all prior rows, computes best score across all kept rows, and continues even if the protocol or thesis was reseeded in place.
- First-principles reason it matters: Scores are only comparable under the same protocol. Changing symbols, windows, costs, fills, objective, gates, or bounds creates a different experiment.
- Root cause: The repo has attempt provenance, but no thesis/run lifecycle identity.
- Recommendation: Add an active thesis lock with run tag, mechanism/falsifier hash, genesis protocol hash, initial experiment bounds hash, and results path. Once `results.tsv` has rows, reject protocol or bounds drift unless Season explicitly starts a new thesis/run log.
- Tradeoff and scope: One small lock/manifest is enough. Avoid a database or research ledger.
- Verification needed: Tests that changing `protocol.toml`, `[bounds.*]`, or mechanism/falsifier mid-run blocks continuation while a fresh run tag starts cleanly.

### Finding 3: The repo is right-sized as a small modular monolith

- Severity: Preserve
- Action class: Preserve
- Evidence: `README.md:9-23`, `protocol.py:200-234`, `loop.py:152-155`, `tests/test_public_contract.py:45-53`, `docs/adr/0001-curated-few-research-regime.md:15-35`.
- What is right: The project is a few modules, one CLI entry, one public upstream dependency, and no database/service layer.
- First-principles reason it matters: The objective is one human-seeded thesis at a time. A heavier framework would increase the surface the LLM can misunderstand and would push the repo back toward the retired evaluator.
- Preservation constraint: Keep this shape unless the ADR escalation triggers occur: automated-many candidate generation, repeated OOS selection, strategy-family tracking too large for manual audit, or historical validation being treated as deployment evidence.

## Engineering, Testability, And Operability Review

### Finding 4: Protocol math fields are coerced without range validation

- Severity: High
- Action class: Add
- Current status: Addressed by `validate-protocol-and-results-boundaries`.
- Evidence: `protocol.py:109-149`.
- What is wrong: `load_protocol()` casts lags, costs, loop constants, subwindow count, and gate thresholds with `int()`, `float()`, and `bool()` but does not validate valid ranges. Invalid values such as negative costs, zero subwindows, invalid concentration bounds, negative trade floors, or same-bar close fills can enter the run contract.
- First-principles reason it matters: Protocol fields are the trusted assumptions. If invalid assumptions load successfully, the protocol wall becomes a source of false evidence.
- Root cause: Protocol parsing lacks the strict numeric/type boundary that `load_experiment()` already has.
- Recommendation: Add explicit protocol validators: finite nonnegative costs, `entry_lag_bars >= 1` for close-derived bar fills unless deliberately allowed by a separate protocol decision, `exit_lag_bars >= 0`, `subwindows >= 1`, count floors >= 0, `0 <= max_symbol_concentration <= 1`, positive iteration limits, and nonnegative improvement thresholds.
- Tradeoff and scope: Small validation code plus tests; no architecture change.
- Verification needed: Bad-protocol tests fail before quick-run materialization.

### Finding 5: Result rows parse shape but not lifecycle semantics

- Severity: High
- Action class: Add
- Current status: Addressed by `validate-protocol-and-results-boundaries`.
- Evidence: `results_log.py:123-159`, `results_log.py:178-183`, `loop.py:733-736`.
- What is wrong: `read_results()` validates missing columns but accepts arbitrary `status`, `best_status`, and `continuation` strings, treats any boolean text other than `"true"` as false, and does not validate contiguous iterations, duplicate run IDs, terminal rows only at the end, hash shape, or artifact existence.
- First-principles reason it matters: `results.tsv` is not just reporting; it drives best-score and stop-state decisions. A stale or edited row can become control flow.
- Root cause: The result log has a schema but no chain validator.
- Recommendation: Add a lightweight result-chain validator before deriving run state. Validate enums, booleans, monotonic iterations, unique run IDs, terminal row position, required hashes, and consistency between `status`, `best_status`, `gates_passed`, and `score`.
- Tradeoff and scope: Slightly stricter on hand-edited logs, which is good for evidence integrity.
- Verification needed: Tests for malformed booleans/enums, duplicate iterations, terminal-not-last, and mixed protocol hashes.

### Finding 6: Quick-run evidence quality is not surfaced in autoresearch evidence

- Severity: Medium
- Action class: Add
- Evidence: `loop.py:445-496`, `results_log.py:41-74`, upstream consumer contract in `quant_strategies/docs/consumer/reference.md:232-236` and `usage-guide.md:240-267`.
- What is wrong: The loop checks `result.succeeded` and reads trade economics, but the autoresearch row/manifest does not persist compact evidence quality fields such as row-contract status, causality verification, data availability status, warnings, assessment status, or upstream result directory.
- First-principles reason it matters: Operational evidence quality must stay distinguishable from strategy performance. A downstream reviewer should see whether a score came from clean causal replay and valid data contracts.
- Root cause: The integration only consumes the economics needed for scoring, not the evidence metadata needed for audit.
- Recommendation: Add a compact `evidence_flags` or manifest subsection from public `RunResult` fields: causality verified, row contract status, data availability status, warning count/messages, assessment status, and upstream `result_dir`.
- Tradeoff and scope: Keep `results.tsv` compact; detailed metadata can live in terminal manifest or generated attempt manifest.
- Verification needed: Mock result with warnings/evidence and assert row or manifest preserves them.

### Finding 7: Console/entrypoint ergonomics are mostly enough but still agent-dependent

- Severity: Medium
- Action class: Add
- Evidence: `README.md:76-80`, `program.md:115-145`, `loop.py:758-779`.
- What is wrong: `climb` runs one attempt and exits, while `program.md` tells the LLM to continue until stop. This can work because the LLM is the loop driver, but it leaves a gap where an agent can summarize a `continuation=allowed` row as done.
- First-principles reason it matters: The value-producing workflow is a terminal survivor or Train failure, not a single attempt.
- Recommendation: Keep `climb` as one-attempt primitive, but make `status` and `climb` output include a clear `next_action` such as `continue`, `repair`, `terminal_review`, or `start_new_thesis`.
- Tradeoff and scope: Avoid an autonomous daemon; improve the existing primitive.
- Verification needed: CLI tests for `next_action` under allowed, repair-required, and terminal states.

## Domain-Specific Lens Findings

### Finding 8: OOS drift review is conceptually right but not bound tightly enough to the frozen survivor

- Severity: High
- Action class: Add
- Evidence: `docs/templates/oos-drift-review.md:1-66`, `program.md:51`, `program.md:139`, `tests/test_public_contract.py:45-53`.
- What is wrong: The repo correctly keeps OOS out of the auto loop and provides a downstream OOS drift template. The template is still manual and blank. It is not mechanically tied to a frozen terminal manifest, and there is no explicit "look consumed" record.
- First-principles reason it matters: OOS is scarce. If the candidate identity or look count is ambiguous, the OOS gate becomes another tunable feedback channel.
- Recommendation: Keep one OOS comparison in the research process, but make it consume a terminal manifest path/hash. Record Train score/gates, OOS score/gates, score ratio/delta, trade-count drift, concentration drift, cost-stress drift, drawdown/return drift, and final human decision. Add a `look_consumed_at` field. The auto loop must never read this artifact.
- Tradeoff and scope: Human-owned artifact only. This is not an OOS subsystem and must not add automated OOS calls to `loop.py`.
- Research-process impact: Low if kept as a template field and manifest reference; high and harmful if implemented as automatic evaluation feedback.
- Verification needed: Tests/docs assert OOS template references terminal manifest identity and auto loop does not read/write it.

### Finding 9: Symbol expansion should be protocol design, not LLM score search

- Severity: High
- Action class: Add
- Evidence: `protocol.toml:38-52`, `program.md:47-51`, `program.md:109-113`, `gates.py:49-56`.
- What is wrong: The current design lets the LLM propose a different fixed universe, but free symbol choice to maximize profit would create direct sample selection. Current gates only check net-return contribution concentration, not broad universe coverage or per-symbol exposure/trade coverage.
- First-principles reason it matters: In trading, choosing symbols after seeing performance is one of the strongest overfit vectors. More symbols can improve robustness only if the universe is fixed for a reason before the run.
- Recommendation: Add a protocol-rationale section for symbol universe selection: liquidity, tradability, data readiness, thesis relevance, and exclusion criteria. If Season wants larger universes, start a new protocol variant and add breadth gates appropriate to that universe, such as per-symbol trade/activity floors or a `symbol x subwindow` objective.
- Tradeoff and scope: More symbols can help find robust edges, but allowing the LLM to churn symbols for score should remain out of scope.
- Verification needed: New-run checklist requires a universe rationale; result/handoff artifacts record fixed symbols and universe rationale hash.

### Finding 10: The current two-year Train window is a reasonable default, not a validated constant

- Severity: Medium
- Action class: Add
- Evidence: `protocol.toml:17-23`, `protocol.toml:51-52`, `protocol.toml:102-106`.
- What is wrong: The active protocol uses 2024-01-01 to 2025-12-31, six subwindows, and comments reserving 2026+ for downstream OOS while local data ends near 2026-04-13. That is plausible for BTC/ETH minute-bar thesis development, but the repo does not record why two years is right for a particular thesis.
- First-principles reason it matters: The Train window defines the market regimes the LLM can fit. Too short is noisy; too long can mix regimes irrelevant to the thesis; changing it after seeing results is protocol drift.
- Recommendation: Keep the two-year default, but require protocol rationale before the run: horizon, expected regime dependence, data readiness, OOS reservation, and why `K=6` is adequate. If the thesis is slow-moving or regime-specific, Season should reseed with a different Train window before any attempts begin.
- Tradeoff and scope: Documentation/lock field only; do not let the LLM tune dates inside the loop.
- Research-process impact: Low. This should be a short rationale in the thesis/protocol lock, not a statistical window-selection process.
- Verification needed: Protocol-lock artifact includes `window_rationale` or a link to rationale text.

### Finding 11: Concentration/breadth labels are economically ambiguous

- Severity: Medium
- Action class: Refactor
- Evidence: `gates.py:49-56`, `protocol.toml:116-118`, `results_log.py:24-30`.
- What is wrong: `symbol_concentration()` measures each symbol's share of absolute realized net trade returns. That can be useful, but labels like `concentration` and `breadth` can be misread as trade-count, exposure, or notional breadth.
- First-principles reason it matters: Downstream reviewers need exact metric semantics. A strategy can have balanced realized net contribution but concentrated exposure, or broad trade count but concentrated PnL.
- Recommendation: Rename the current metric to `net_return_contribution_concentration`, or add separate `trade_count_concentration` and `exposure_concentration` if the upstream quick-run economics expose enough information.
- Tradeoff and scope: Rename is safest now; richer breadth metrics can wait for upstream economics support.
- Research-process impact: Very low. This is a label/semantics fix unless upstream already exposes clean exposure data.
- Verification needed: Tests and OOS template use the unambiguous label.

### Finding 12: Time/symbol filters remain procedural complexity risk

- Severity: Medium
- Action class: Add
- Evidence: `strategy.py:130-178`, `loop.py:53-82`, `openspec/specs/autoresearch-agent-contract/spec.md:31-40`, `docs/simplified-autoresearch-loop-design.md:154-157`.
- What is wrong: The strategy receives `symbol`, `timestamp`, and `available_at`, so the LLM can encode symbol-specific or calendar/session filters. Some filters are legitimate market logic, but component accounting currently counts headings rather than requiring complete mechanism/observable/falsifier fields per component.
- First-principles reason it matters: Structural filters are often disguised sample selection.
- Recommendation: Validate minimal rationale completeness for each `### Component:` heading. Require any symbol, session, calendar, or time-of-day filter to be its own declared component with a prior rationale.
- Tradeoff and scope: Still procedural; do not build brittle strategy-code inspection unless abuse becomes common.
- Research-process impact: Low if implemented as three required fields per component; high if implemented as AST policing of strategy logic.
- Verification needed: Rationale parser rejects component headings without mechanism, observable, and falsifier fields.

## Unknown Unknowns And Assumption Risks


| Risk                                                                 | Why it matters                                        | De-risking action                                                           |
| -------------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------------- |
| `quant_data` readiness differs from protocol comments                | Data gaps can become run failures or biased samples   | Add a pre-run data readiness check recorded in thesis lock                  |
| Quick-run trade-unit score ignores NAV path and overlapping exposure | Train score may miss drawdown/capital-path risk       | Keep score label honest; use OOS evaluation for portfolio/NAV/path evidence |
| OOS process remains manual                                           | Manual one-look discipline can be violated informally | Bind OOS review to terminal manifest and record look consumed               |
| Larger symbol universes increase multiple-testing pressure           | More names give the LLM more ways to select noise     | Fix universe a priori and add breadth/cell coverage gates before expanding  |
| Current active docs/specs can drift                                  | LLMs may follow stale instructions                    | Collapse or clearly retire stale design sections                            |


## Overbuilt, Underbuilt, And Right-Sized Areas

Overbuilt:

- Keeping active OpenSpec specs, archived OpenSpec changes, a historical design doc, and active operating docs in a tiny repo creates multiple instruction surfaces.
- Reintroducing DSR/PBO/family-ledger machinery now would be premature for one human-seeded thesis at a time.

Underbuilt:

- Best kept candidate identity in terminal handoff.
- Thesis/protocol/bounds lock.
- Protocol range validation.
- Result-chain semantic validation.
- OOS one-look artifact binding to terminal manifest.
- Universe/window rationale capture.

Right-sized:

- Python-only small modules.
- Public `quant_strategies.runner.run_config` integration.
- No in-loop OOS/evaluation import.
- Append-only TSV rather than a database.
- Trade-unit Train robustness as a filter, not a deployability claim.
- Curated-few ADR with escalation triggers.

## Missing Docs, PRD, ADR, Or Decision Records

- Addressed active-thesis/protocol-lock decision: run identity, protocol hash, bounds hash, and result path are now generated lock state.
- Addressed terminal handoff contract: terminal manifests distinguish terminal attempt snapshots from best survivor snapshots.
- Missing OOS look-consumption record tied to terminal manifest.
- Addressed protocol rationale fields for Train window and symbol universe.
- Addressed downstream handoff spec placeholder purpose.
- Addressed active OpenSpec tracking hygiene for current/future OpenSpec files.
- Addressed historical design doc warning around stale implementation sketches such as cache plumbing, `git revert`, and `params.toml` wording.

## ASCII Architecture And Lifecycle Diagrams

Current source boundary:

```text
program.md / AGENTS.md
        |
        v
loop.py CLI
  |-- load_protocol(protocol.toml) ----> protocol.py ----> quick TOML
  |-- load_params(experiment.toml) ----> bounds validation
  |-- components_from_rationale() ----> rationale.md headings
  |
  v
quant_strategies.runner.run_config(...)
        |
        v
RunResult.economics.trades
        |
        +--> objective.py: trade-unit Train score
        +--> gates.py: binary gates
        |
        v
results_log.py -> results.tsv
        |
        v
terminal_manifest.json when stop fires
```

Needed identity boundary:

```text
thesis.lock
  run_tag
  mechanism_hash
  falsifier_hash
  protocol_sha256_at_start
  bounds_sha256_at_start
        |
        v
every attempt row must match lock
        |
        v
every keep writes exact keep snapshot
        |
        v
terminal survivor references best keep snapshot
        |
        v
OOS review consumes terminal survivor id once
```

## Prioritized Recommendations / Action Map


| No. | Status | Priority | Action class | Recommendation                                                                                                                | Research-process impact                                        | Right-sized fix / avoid                                                                 |
| --- | ------ | -------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 1   | Addressed | P0       | Refactor     | Make terminal survivor snapshots come from the best kept attempt, and freeze `results.tsv` into the terminal artifact.        | High positive impact; prevents wrong OOS handoff.              | Persist/copy kept snapshots. Avoid broader artifact store.                              |
| 2   | Addressed | P0       | Add          | Add active thesis/protocol/bounds lock with run tag and mechanism/falsifier identity; reject drift unless starting a new run. | High positive impact; prevents mixed experiments.              | One lock file. Avoid database/ledger.                                                   |
| 3   | Addressed | P1       | Add          | Add explicit protocol type/range validators.                                                                                  | Medium positive impact; catches bad assumptions early.         | Small validators. Avoid schema framework unless needed.                                 |
| 4   | Addressed | P1       | Add          | Add result-chain validation before deriving best/stop state.                                                                  | Medium positive impact; protects control flow from stale rows. | Validate enums, booleans, iterations, hashes. Avoid full audit ledger.                  |
| 5   | Deferred | P1       | Add          | Bind downstream OOS drift review to terminal manifest identity and record one-look consumption.                               | Low workflow cost, high audit value.                           | Template fields only. Avoid automated OOS loop.                                         |
| 6   | Deferred | P1       | Add          | Record compact quick-run evidence quality from public `RunResult`.                                                            | Medium audit value; small workflow cost.                       | Store compact flags/warnings only after real runs show need. Avoid scraping artifacts or duplicating upstream reports. |
| 7   | Addressed | P2       | Add          | Add protocol rationale for Train window and symbol universe.                                                                  | Low workflow cost; improves Season review.                     | Short rationale fields. Avoid automated window/symbol optimization.                     |
| 8   | Addressed | P2       | Refactor     | Rename `concentration` to `net_return_contribution_concentration` or add explicit breadth metrics.                            | Very low process impact.                                       | Rename now. Avoid richer metrics unless upstream exposes clean data.                    |
| 9   | Open   | P2       | Add          | Require mechanism/observable/falsifier text for each rationale component, with explicit time/symbol-filter declarations.      | Low if textual; high if over-policed.                          | Validate fields. Avoid AST strategy inspection.                                         |
| 10  | Open   | P2       | Add          | Add `next_action` to status/climb output.                                                                                     | Low; reduces agent ambiguity.                                  | One derived field. Avoid autonomous daemon.                                             |
| 11  | Addressed | P3       | Simplify     | Collapse or quarantine stale historical design details.                                                                       | Low; onboarding hygiene.                                       | Mark/archive stale sections. Avoid rewriting history docs into new specs.               |
| 12  | Addressed | P3       | Refactor     | Unignore active `openspec/specs/**` or move active specs under `docs/specs/`.                                                 | Low; repo hygiene.                                             | One `.gitignore` or path change. Avoid reorganizing OpenSpec wholesale.                 |
| 13  | Addressed | P3       | Add          | Replace downstream handoff spec `TBD` purpose.                                                                                | Very low; wording only.                                        | One sentence. Avoid expanding scope.                                                    |


## Preservation Constraints / Right-Sized Boundaries

- Preserve the Train-only auto loop. Do not import or call `quant_strategies.evaluation` from `loop.py`.
- Preserve human-owned one-look OOS review. The answer is not zero OOS; it is OOS outside the loop.
- Preserve public `quant_strategies.runner.run_config` as the only execution dependency.
- Preserve one thesis at a time and avoid automated-many research governance until the ADR triggers appear.
- Preserve the narrow editable surface: `strategy.py`, bounded `[params]`, and `rationale.md`.
- Preserve append-only TSV simplicity. Add validation and identity, not a database.
- Preserve the score wording as Train trade-unit robustness, not Sharpe, NAV, alpha, or deployability.

## NOT In Scope

- Running OOS evaluation inside auto-research.
- Deciding whether any current strategy is paper-ready or live-ready.
- Changing the current protocol symbols, dates, costs, fills, objective, gates, or loop constants.
- Auditing all of `quant_strategies` or `quant_data` internals.
- Adding DSR/PBO/CPCV/family-ledger machinery for the current curated-few regime.
- Building an autonomous service, scheduler, database, dashboard, or multi-agent mining platform.

## Verification Performed And Residual Risk

Commands run by lens agents and/or this review pass reported:

- `conda run -n quant python -m pytest`: 54 passed.
- `conda run -n quant python -m mypy .`: passed.
- `conda run -n quant python -m ruff check .`: passed.
- `conda run -n quant python -m loop status`: worked and reported no active attempts in one lens.

This review did not run a real `climb` against market data because that would create generated attempt artifacts and depend on current data readiness. It did not inspect upstream internals. The working tree was already dirty in `protocol.toml` and `docs/reviews/foundation-review-20260607.md`; this review artifact was written as a new file to avoid overwriting those changes.
