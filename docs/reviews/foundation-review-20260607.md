# Foundation Review: quant_autoresearch

Date: 2026-06-07
Reviewer: Codex, with onboarding, architecture, senior engineering, adversarial, and senior quant research lenses
Target: `/Users/Season_Yang/Personal/quant_autoresearch`

## Executive Verdict

`quant_autoresearch` is directionally the right project shape for Season's objective: a small, thesis-driven, Train-only autoresearch loop inspired by `karpathy/autoresearch`, with a deliberately narrow LLM-editable surface and OOS kept outside the loop. It is not yet a trustworthy foundation for producing handoff-ready Train survivors because several guardrails are still procedural rather than executable: stop/freeze/revert state, parameter bounds, evidence provenance, component/rationale accounting, and per-subwindow evidence quality.

The answer to the main product question is: **yes, the project is simple enough in concept, but it is not yet strict enough in contracts.** Do not add automated OOS feedback into the loop. Add a downstream one-look OOS drift artifact owned by Season, and first make the Train loop's own claims mechanically true.

## Review Objective

I understand the project objective as: `/Users/Season_Yang/Personal/quant_autoresearch` should serve Season as PM/research owner, plus downstream OOS/paper/small-live review, by enabling an LLM-driven Train-only autoresearch loop that makes simple, causal strategy changes, records evidence, and produces either a frozen Train survivor or a clear Train failure. A solid foundation should keep the LLM focused on strategy development, make overfit/stale/invalid evidence hard to mistake for real profitability, and support a research process that resembles disciplined quant research without wiring automated OOS into the loop unless that boundary is explicitly re-decided. It should prevent protocol drift, hidden data/fill/cost assumption changes, stale docs, false claims of deployability, and complexity that turns the system into a framework instead of a thesis-testing loop, while respecting the repo's current non-goals around protocol-owned assumptions and human-gated downstream validation.

I reviewed the repo against that project objective, using foundation, architecture, senior software engineering, adversarial, senior quant research, and quant math/code lenses, accounting for concerns about OOS drift measurement, whether the setup matches real quant research, whether the project is simple enough to find profitable strategies, whether the LLM is focused on strategy development, and whether docs are stale.

### Clarified Scope

- **In scope**: current repo shape, Train loop contract, protocol/params boundary, strategy surface, objective/gates, results logging, docs, tests, upstream `karpathy/autoresearch` comparison, and senior quant research process fit.
- **Out of scope**: implementing fixes, running live/OOS evaluation, changing thesis protocol values, auditing all of `quant_strategies`, or deciding deployability of any strategy.
- **Assumption**: the current dirty working tree is the review target.
- **Artifact**: this durable review doc at `docs/reviews/foundation-review-20260607.md`.

## Scope And Evidence Inspected

- **Core source**: `loop.py`, `protocol.py`, `objective.py`, `gates.py`, `results_log.py`, `strategy.py`.
- **Config and contracts**: `pyproject.toml`, `protocol.toml`, `experiment.toml`, `AGENTS.md`, `.gitignore`.
- **Tests**: `tests/test_loop.py`, `tests/test_protocol.py`, `tests/test_objective_gates.py`, `tests/test_program_contract.py`, `tests/test_public_contract.py`, `tests/test_results_log.py`, `tests/test_strategy_contract.py`.
- **Docs treated as claims**: `README.md`, `program.md`, `rationale.md`, `UPSTREAM_LIMITATIONS_TODO.md`, `docs/simplified-autoresearch-loop-design.md`, `openspec/specs/*`.
- **Upstream inspiration**: cloned `karpathy/autoresearch` at `228791fb499a`; inspected its README, `program.md`, `prepare.py`, `train.py`.
- **External quant practice basis**: Federal Reserve/OCC SR 11-7 on model risk governance, CFA Institute Backtesting & Simulation, Bailey et al. on Probability of Backtest Overfitting, Bailey/de Prado on Deflated Sharpe Ratio, and Harvey/Liu/Zhu on multiple testing in expected returns.
- **Not inspected deeply**: full `quant_strategies` validation/OOS internals, real local market data freshness, generated artifacts from a real Train run, paper/live infrastructure.

## Upstream Karpathy Comparison

Karpathy's repo is intentionally tiny: `prepare.py` is fixed data/eval infrastructure, `train.py` is the single agent-editable surface, `program.md` is the agent operating contract, and `results.tsv` is the experiment memory. The loop optimizes one fixed metric, `val_bpb`, under a fixed 5-minute time budget.

This repo preserves the useful part: short program, narrow editable surface, fixed harness assumptions, one run log. The trading-specific divergence is necessary: a backtest score is not equivalent to LLM validation loss, so the loop must stop, must avoid OOS feedback, and must treat Train robustness as a filter only.

The current implementation follows the template at the file-boundary level:

```text
karpathy/autoresearch           quant_autoresearch
----------------------          ------------------------------
program.md                      program.md
train.py editable               strategy.py + bounded params editable
prepare.py fixed                protocol.toml fixed
val_bpb metric                  Train trade-unit robustness score
results.tsv                     results.tsv
loop forever                    bounded loop by stop rules
validation in loop              OOS outside loop
```

The main gap is not that this repo departed from Karpathy. The main gap is that its own bounded-loop contract is not fully executable yet.

## Intended Foundation Model

From first principles, this project needs a **curated-few quant research funnel**, not a mining platform.

```text
Season seeds thesis
    |
    v
Protocol frozen before run
    |  owns symbols, Train window, costs, fills, objective, gates, stop rules
    v
LLM edits only strategy.py + bounded params + rationale
    |
    v
Train quick run via public quant_strategies.runner.run_config
    |
    v
Trade-unit evidence -> objective score + gates -> results.tsv
    |
    +-- discard/revert -> next thesis-guided variant
    |
    +-- keep -> best Train survivor candidate
    |
    v
Stop rule fires -> freeze handoff or Train death
    |
    v
Season one-look OOS drift review -> paper -> small live -> scale
```

### Project Ontology

| Concept / boundary | Responsibility | Required invariant | Current-code fit |
|---|---|---|---|
| Thesis | Mechanism and falsifier for one run | One thesis at a time; no hidden mechanism drift | Mostly in docs, weak in executable state |
| Protocol | Operator-owned run assumptions | Not agent-editable mid-run; no OOS surface | Strong in config and materialization |
| Strategy surface | Express signal logic | Causal, simple, no protocol overrides | Good baseline, but can still condition on timestamp regimes |
| Experiment params | Bounded numeric dials | Bounds are enforced before a run | Weak: bounds declared but ignored by loader |
| Objective | One Train robustness score | Selected a priori by protocol; not proof of edge | Partly good; empty subwindows are dangerous |
| Gates | Binary feasibility filters | Separate from score; reject weak evidence | Good shape; missing per-subwindow evidence gate |
| Results log | Append-only attempt evidence | One row per attempt, tied to exact candidate snapshot | Too little provenance |
| Handoff | Frozen Train survivor or failure | Cannot be confused with promotion | Documented, not implemented |
| OOS gate | Downstream one-look validation | Human-gated, no loop feedback | Correctly out of loop; missing drift artifact |

## What Already Exists And Should Be Reused

| Existing code/flow | What it does | Reuse / concern |
|---|---|---|
| `program.md` | Clear LLM operating contract with Train-only/OOS boundary | Preserve; tighten wording around score semantics |
| `protocol.toml` | Operator-owned data, fills, costs, objective, gates, stop settings | Preserve; make protocol snapshot part of evidence |
| `protocol.py` | Loads protocol and materializes public quick-run TOML | Preserve public API boundary; add experiment bounds validation nearby |
| `loop.py` | One-shot status/climb entry and run logging | Refactor into explicit state/stop/handoff contract |
| `objective.py` | Trade-unit worst-subwindow score and stop helpers | Keep simple, but fix empty-subwindow semantics |
| `gates.py` | Binary feasibility gates | Preserve gate-vs-score separation; add evidence coverage gate |
| `results_log.py` | Stable append/read/status helpers | Preserve TSV simplicity; extend provenance columns deliberately |
| `strategy.py` | Simple causal momentum baseline using `available_at` | Preserve as example, but do not over-credit it as evidence |
| Tests | Focused contract tests | Good base; add tests for the missing lifecycle/provenance cases |

## Architecture And Boundary Review

### Finding A1: Stop/freeze/revert is documented but not executable

- **Severity**: High
- **Action class**: Refactor
- **Evidence**: `program.md:110-138`, `loop.py:309-337`, `loop.py:281-282`, `objective.py:190-200`, `openspec/specs/autoresearch-train-loop/spec.md:21-48`
- **What is wrong**: Docs/specs describe an autonomous loop that reverts non-kept candidates, stops on plateau/max/baseline/complexity, and freezes a handoff. The executable CLI runs one candidate and exits; normal result rows always record blank `stop_reason`.
- **Why it matters**: The core product is a bounded autonomous research loop. If stop state lives in the LLM's memory, the system can overrun, stop opportunistically, fail to revert discarded code, or claim a survivor that was never frozen.
- **Root cause**: lifecycle boundary missing from source.
- **Recommendation**: Add a small `RunState` / `StopDecision` boundary that reads `results.tsv` and protocol before each iteration, decides whether another attempt is allowed, records terminal stop reasons, and writes a frozen handoff manifest when appropriate. This does not require a large daemon.
- **Tradeoff**: Slightly more code in `loop.py` or a new `state.py`, but it makes the repo's most important claim executable.

### Finding A2: Protocol wall is strong, but evidence identity is weak

- **Severity**: High
- **Action class**: Add
- **Evidence**: `loop.py:38-47`, `results_log.py:8-52`, `.gitignore:5-8`, `loop.py:155-162`
- **What is wrong**: `results.tsv` records only short `HEAD`, metrics, status, and note. It does not record dirty status, `strategy.py` hash, `experiment.toml` hash, `protocol.toml` hash, quick-config hash, artifact path, or thesis/run id.
- **Why it matters**: The result row is the research memory. If it cannot identify the exact candidate/protocol snapshot, stale rows can influence keep/discard decisions or downstream OOS review.
- **Root cause**: artifact/provenance contract is incomplete.
- **Recommendation**: Add cheap provenance columns: `run_id`, `artifact_dir`, `worktree_dirty`, `strategy_sha256`, `params_sha256`, `protocol_sha256`, `quick_config_sha256`, and `rationale_sha256`.
- **Tradeoff**: Wider TSV, but still simple and inspectable.

### Finding A3: The CLI bypasses the component/rationale complexity guard

- **Severity**: High
- **Action class**: Add
- **Evidence**: `program.md:35-39`, `gates.py:66-97`, `loop.py:316`, `loop.py:349-351`, `rationale.md:9-18`
- **What is wrong**: Complexity is counted from a `components` argument, but the CLI accepts no component metadata and defaults to `("baseline",)`.
- **Why it matters**: Structural search is the dangerous overfit vector in this domain. If the LLM can add filters in `strategy.py` while the gate still counts one component, the simplicity guard is mostly procedural.
- **Root cause**: rationale/component metadata is not a first-class runtime input.
- **Recommendation**: Either parse component headings from `rationale.md` and pass that count into gates, or add explicit `--component` CLI input and require it to match `rationale.md`. Parsing headings is simpler and aligns with the current docs.
- **Tradeoff**: Parsing Markdown is a little brittle, but better than trusting a hidden default.

### Finding A4: The active architecture is right-sized as a modular monolith

- **Severity**: Preserve
- **Action class**: Preserve
- **Evidence**: `README.md:9-23`, `protocol.py:64-122`, `loop.py:50-53`, `tests/test_public_contract.py:45-53`
- **What is right**: The repo is small, local, Python-only, and integrates with `quant_strategies` through `runner.run_config`, not private engine modules.
- **Why it matters**: This is the right shape for a personal LLM-driven workbench. More services, databases, research ledgers, or heavy statistical orchestration would push the project back toward the retired overbuilt harness.
- **Preservation constraint**: Keep this as a small modular monolith unless the workflow changes to automated-many candidate mining.

## Engineering, Testability, And Operability Review

### Finding E1: Declared parameter bounds are not enforced

- **Severity**: High
- **Action class**: Add
- **Evidence**: `experiment.toml:7-20`, `protocol.py:125-127`, `protocol.py:144-148`, `strategy.py:55-82`
- **What is wrong**: `experiment.toml` declares `[bounds.*]`, but `load_params()` returns only `[params]`. `strategy.validate_params()` has separate hardcoded checks and allows values outside declared bounds, e.g. `weight <= 1.0` while the experiment bound is `0.50`.
- **Why it matters**: Bounded params are part of the overfit guard. If bounds are advisory, the editable surface is wider than advertised.
- **Root cause**: experiment config has no typed contract.
- **Recommendation**: Add `ExperimentConfig(params, bounds)` with validation before materializing quick-run config. Keep strategy-level validation for semantic constraints, but make experiment bounds operator-owned.
- **Verification**: tests for out-of-bound params failing before `run_config`.

### Finding E2: Missing economics can be mislabeled as a valid no-trade strategy

- **Severity**: Medium
- **Action class**: Refactor
- **Evidence**: `loop.py:56-72`, `loop.py:188-204`
- **What is wrong**: `_trades_from_result()` returns `()` when `result.economics is None`. A successful upstream result with missing economics would look like zero trades rather than an integration contract failure.
- **Why it matters**: Operational failures should not be strategy evidence.
- **Root cause**: upstream result contract is too loose at the boundary.
- **Recommendation**: Treat `succeeded=True` with `economics is None` as `crash`; allow `economics.trades == ()` as valid no-trade evidence.
- **Verification**: unit test with `succeeded=True, economics=None`.

### Finding E3: CLI output is thinner than the documented run summary

- **Severity**: Medium
- **Action class**: Add
- **Evidence**: `program.md:53-74`, `loop.py:357-360`, `results_log.py:31-52`
- **What is wrong**: `climb` prints only status and score; the operating contract says the agent should review gates, trade count, concentration, cost stress, returns, complexity, and elapsed time.
- **Why it matters**: The LLM's next edit depends on diagnostics. Hiding diagnostics in TSV/artifacts increases the chance of leaderboard behavior.
- **Recommendation**: Print the same fields appended to `results.tsv`, plus artifact path once added.
- **Tradeoff**: More console output, but still bounded and parseable.

### Finding E4: Type checking currently fails at boundaries

- **Severity**: Medium
- **Action class**: Refactor
- **Evidence**: `mypy` reported 12 errors in `results_log.py`, `strategy.py`, `loop.py`, and `tests/test_protocol.py`.
- **What is wrong**: `object`-typed params, untyped upstream imports, and optional max handling are loose enough that mypy cannot validate the boundaries.
- **Why it matters**: This project relies on small explicit contracts. Type failures at boundary code are not cosmetic.
- **Recommendation**: Do not type-polish broadly yet. After bounds/provenance/state are designed, tighten `ExperimentConfig`, `ResultRow`, and strategy param types.
- **Verification**: `conda run -n quant python -m mypy .`.

## Domain-Specific Lens: Senior Quant Research

### Finding Q1: Empty Train subwindows can pass as robustness evidence

- **Severity**: Critical
- **Action class**: Add
- **Evidence**: `objective.py:43-52`, `objective.py:100-128`, `protocol.toml:115-122`, `gates.py:83-103`, `tests/test_objective_gates.py:63-74`
- **What is wrong**: `_score_returns([])` returns `0.0`. With `train_score_floor = 0.0` and `min_cost_stress_score = 0.0`, a strategy can cluster trades in one part of Train while idle subwindows score at the floor rather than failing as missing evidence.
- **Domain risk**: A time filter can hide weak regimes and still produce a "robust" survivor. This is temporal cherry-picking by another name.
- **Recommendation**: Add `min_trades_per_subwindow` or make empty subwindows infeasible for `worst_subwindow`. Prefer a configurable per-subwindow trade floor because it distinguishes true no-trade evidence from sparse but acceptable markets.
- **Tradeoff**: Some slow strategies may die on Train. That is acceptable unless the protocol explicitly supports slow strategies with a different objective.

### Finding Q2: Timestamp-based regime cherry-picking remains possible inside `strategy.py`

- **Severity**: High
- **Action class**: Add
- **Evidence**: `program.md:47-51`, `strategy.py:98-157`, `objective.py:55-80`, `gates.py:71-103`
- **What is wrong**: Docs forbid changing dates/hours, but the editable strategy receives timestamps and can condition on calendar/time regimes. This is sometimes legitimate market logic, but it is also an easy overfit path.
- **Domain risk**: In trading, structural filters are often disguised sample selection.
- **Recommendation**: Do not ban time features globally. Require any calendar/time/session filter to be declared as a signal component with an a priori rationale, and add gate support for per-subwindow activity so time filters cannot simply avoid weak periods.
- **Tradeoff**: Legitimate session effects remain allowed, but more auditable.

### Finding Q3: The current score is trade-unit robustness, not Sharpe or deployability

- **Severity**: High
- **Action class**: Retire
- **Evidence**: `objective.py:43-52`, `README.md:86`, `docs/simplified-autoresearch-loop-design.md:168-170`
- **What is wrong**: The implemented score is mean/std of completed trade net returns by subwindow. The design doc calls `worst_subwindow` "min after-cost Sharpe," but the README correctly says quick-run economics expose trade-unit samples, not NAV or period-return series.
- **Domain risk**: Sharpe language can cause downstream overconfidence.
- **Recommendation**: Rename and document as "trade-unit robustness score" until the runner exposes portfolio NAV or period returns. Downstream OOS can use richer metrics if `quant_strategies evaluate` provides them.
- **Tradeoff**: Less impressive metric language, more honest artifact semantics.

### Finding Q4: OOS drift should exist, but not as loop feedback

- **Severity**: High
- **Action class**: Add
- **Evidence**: `program.md:51`, `README.md:5-7`, `docs/simplified-autoresearch-loop-design.md:245-269`
- **What is wrong**: The OOS boundary is right, but the downstream handoff artifact is not defined in the current repo.
- **Domain risk**: Without a formal one-look OOS record, Season may still compare Train/OOS informally and lose auditability.
- **Recommendation**: Add a separate downstream `oos-review.md` or `oos_drift.tsv` template, outside the auto loop, with frozen candidate ID/hash, Train score/gates, OOS score/gates, score delta/ratio, trade-count drift, concentration drift, cost-stress drift, drawdown/return drift if available, and final human decision. The auto loop must not read this artifact.
- **Tradeoff**: Adds a human-owned artifact, not an automated feedback channel.

### Finding Q5: The process matches personal curated-few research, not institutional research

- **Severity**: Medium
- **Action class**: Preserve
- **Evidence**: `README.md:3-7`, `program.md:29-33`, `protocol.toml:1-14`, `quant_strategies/RESEARCH_DIRECTION.md` inspected as a related direction record
- **What is right**: For a personal trader, the correct goal is a clean funnel from Train to OOS to paper to small live, not a publishable historical proof.
- **Domain risk**: If the project later becomes automated-many mining, current light machinery is insufficient.
- **Recommendation**: Add an ADR that explicitly chooses "curated-few thesis-driven research" as the operating regime. State the trigger for heavier statistics: many independent candidates, automated strategy generation, or using historical evidence as a deployment verdict.

## Quant Research Practice Comparison

Institutional quant research practice generally expects a clear model purpose, documented theory, data quality controls, independent validation/effective challenge, outcome analysis, ongoing monitoring, and governance proportional to model materiality. SR 11-7 is bank model-risk guidance, not a personal trading rulebook, but its principles map cleanly: state purpose, validate inputs/processing/outputs, document limitations, and monitor after use.

Investment backtesting practice also expects a hypothesis, explicit rules, realistic portfolio construction/rebalancing assumptions, performance/risk metrics, sensitivity/scenario analysis, and attention to survivorship/lookahead bias. The CFA framing is useful here because it treats backtesting as approximating an investment process, not proving future profit.

Academic quant research adds a warning: repeated search inflates performance. PBO/CSCV and DSR exist because backtest optimization and multiple trials can convert noise into selected "alpha." Harvey/Liu/Zhu make the same point in factor research: as the factor zoo grows, ordinary significance thresholds become too lenient.

For this repo, the right translation is:

- **Keep light**: one thesis, one frozen protocol, one Train objective, one results log.
- **Be stricter at boundaries**: provenance, bounds, stop state, per-subwindow evidence.
- **Do not add OOS into the loop**: one-look OOS belongs downstream and human-gated.
- **Do not import DSR/PBO now** unless the regime shifts from curated-few to automated-many.
- **Do require paper and small live** before any claim of real profitability.

## Unknown Unknowns And Assumption Risks

| Assumption | Why it may be wrong | How to de-risk |
|---|---|---|
| `quant_strategies.runner.run_config` economics are stable enough for scoring | Upstream schema may change or omit economics on some success paths | Add boundary tests around missing economics and artifact path |
| Trade-unit return samples are adequate for Train filtering | They ignore NAV path, exposure, drawdown, overlapping exposure, and capital usage | Label as trade-unit robustness; use richer downstream OOS metrics |
| Two-year BTC/ETH Train default is representative enough for thesis development | Crypto regimes shift and two symbols are narrow | Let Season choose protocol per thesis; use OOS/paper/live as real filters |
| Component declaration via rationale can control structural search | An LLM can under-declare or rationalize after seeing lift | Parse/check rationale and add human review at handoff |
| Fixed protocol prevents sample selection | Strategy can still condition on timestamps | Add per-subwindow trade floor and require time filters as components |

## Overbuilt / Underbuilt / Right-Sized Areas

- **Overbuilt**: keeping active OpenSpec specs plus a stale design doc after implementation creates more instruction surfaces than this small project needs.
- **Underbuilt**: lifecycle state, handoff manifest, provenance, params bounds, component accounting, and subwindow evidence coverage.
- **Right-sized**: no database, no service boundary, no automated OOS inside the loop, no heavy DSR/PBO machinery for curated-few research, public `run_config` dependency only.

## Missing Docs, PRD, ADR, Or Decision Records

- **Missing ADR**: "OOS stays outside auto-research; downstream gets one-look drift artifact."
- **Missing ADR**: "Curated-few thesis-driven regime; heavier multiple-testing machinery only if automated-many."
- **Missing handoff template**: frozen Train survivor manifest with explicit "not deployability evidence" language.
- **Missing downstream OOS drift template**: human-owned one-look artifact.
- **Stale doc**: `docs/simplified-autoresearch-loop-design.md:3-4` says "Not yet implemented."
- **Stale or stronger-than-code specs**: `openspec/specs/autoresearch-train-loop/spec.md` requires reversion, stop reasons, and frozen handoff that current code does not implement.

## Action Map

| No. | Status | Priority | Action class | Finding / recommendation | Rationale | Verify |
|---:|---|---|---|---|---|---|
| 1 | Addressed | P0 | Add | Add per-subwindow evidence coverage: `min_trades_per_subwindow` or infeasible empty subwindows. | Prevent temporal cherry-picking and false robustness. | Unit test clustered trades fail coverage gate. |
| 2 | Addressed | P0 | Refactor | Add explicit `RunState` / `StopDecision` / handoff lifecycle boundary. | Make plateau, max-iterations, baseline failure, reversion, and stop reasons executable. | Tests for plateau, max iterations, baseline grace, stop reasons, and handoff manifest. |
| 3 | Addressed | P0 | Add | Extend `results.tsv` with provenance columns and artifact path. | Prevent stale/dirty evidence from influencing decisions. | Test dirty worktree and hash columns are recorded. |
| 4 | Addressed | P1 | Add | Parse and enforce `[bounds]` from `experiment.toml`. | Make bounded params real rather than advisory. | Out-of-bound params fail before run. |
| 5 | Addressed | P1 | Add | Make component/rationale accounting first-class in the CLI or derive it from `rationale.md`. | Stop complexity gate from being bypassed by default. | CLI/rationale count test affects complexity gate. |
| 6 | Addressed | P2 | Refactor | Treat `succeeded=True` with missing economics as crash. | Keep operational failures out of strategy evidence. | Unit test with missing economics on a successful runner result. |
| 7 | Addressed | P2 | Add | Print full quick-run summary from `climb`. | Keep LLM focused on diagnostics, not just score. | CLI output includes the same control fields as `results.tsv`. |
| 8 | Addressed | P1 | Retire | Rename/document current score as trade-unit robustness, not Sharpe. | Avoid misleading downstream interpretation. | Docs no longer claim "Sharpe" for the trade-unit score. |
| 9 | Addressed | P1 | Retire | Mark `docs/simplified-autoresearch-loop-design.md` historical or collapse into current decisions/open risks. | Remove stale implementation guidance. | Docs no longer claim the implemented loop is "not yet implemented." |
| 10 | Addressed | P2 | Add | Add downstream one-look OOS drift artifact template outside the loop. | Answer Season's OOS drift concern without contaminating Train optimization. | Template exists and auto loop does not read it. |
| 11 | Addressed | P2 | Add | Add ADR for curated-few regime and trigger for heavier multiple-testing controls. | Keep the project simple for now and explicit about when that stops being valid. | ADR states curated-few assumptions and automated-many escalation trigger. |
| 12 | Addressed | P3 | Refactor | Tighten type boundaries after items 2-5 settle. | mypy failures are mostly boundary ambiguity symptoms. | `mypy .` passes or has documented ignores for untyped upstream imports. |

## Preservation Constraints

- Keep OOS/evaluate outside the auto loop.
- Keep `protocol.toml` operator-owned and frozen per thesis.
- Keep strategy development narrow: `strategy.py`, bounded params, and `rationale.md`.
- Keep `quant_strategies` integration through public `runner.run_config`.
- Keep `results.tsv` as simple tab-separated local evidence, but make it more identifying.
- Keep the repo as a modular monolith.

## Direct Answers To Season's Questions

### Is this simple enough to identify profitable strategies?

It is simple enough to identify **candidate strategies worth downstream review**, not profitable strategies by itself. That distinction matters. The project can be a good feeder into OOS/paper/small-live if the Train evidence is honest. It cannot prove real market profit from Train robustness.

### Should we add OOS into the loop?

No. Keep OOS outside the loop. Add a downstream one-look OOS drift artifact after a frozen Train survivor exists. The artifact should compare Train and OOS but must not feed back into strategy edits for the same candidate.

### Is this the right setup compared with real quant research?

For institutional research, it is too light: no independent validation team, no formal governance, no complete multiple-testing accounting, no production monitoring. For Season's personal curated-few process, it is the right direction if the missing boundary contracts are fixed and the funnel explicitly continues to OOS, paper, and small live.

### Are docs stale?

Yes. `docs/simplified-autoresearch-loop-design.md` is now historical, not current. Active OpenSpec train-loop specs also demand capabilities not implemented in source. The fix is not more docs; it is collapsing active docs into current contracts, decisions, open risks, and links to this review.

## NOT In Scope

- Automated OOS inside `loop.py`.
- Paper/live trading infrastructure.
- DSR/PBO/CSCV implementation for the current curated-few regime.
- Full `quant_strategies` architecture review.
- Changing the current thesis protocol values during this review.

## Verification Summary

- **Verified locally**:
  - `conda run -n quant python -m pytest -q` -> 29 passed.
  - `conda run -n quant python -m loop status` -> reports 0 attempts, 80 remaining iterations, 6 subwindows.
  - `conda run -n quant python -m ruff check .` -> passed.
  - CodeGraph index present: 16 indexed files, 230 nodes.
- **Known failure**:
  - `conda run -n quant python -m mypy .` -> 12 errors, mostly untyped upstream imports and loose `object` boundaries.
- **Not verified**:
  - Real Train quick-run against local market data.
  - Real OOS evaluation.
  - Paper/live execution.
  - Full upstream `quant_strategies` validation internals.
- **Residual risk**:
  - Even after the P0 fixes, Train survivors remain in-sample filters. Real profitability depends on downstream OOS, paper, small live, execution costs, sizing, and regime survival.

## Source Notes

- Karpathy `autoresearch` inspected locally at commit `228791fb499a`.
- Federal Reserve/OCC SR 11-7: model risk management guidance emphasizing clear model purpose, sound development, validation, governance, and ongoing monitoring.
- CFA Institute Backtesting & Simulation: backtesting as approximation of an investment process, with attention to hypothesis/rules, risk-return metrics, scenario/sensitivity analysis, lookahead/survivorship bias, structural breaks, and fat tails.
- Bailey, Borwein, Lopez de Prado, and Zhu: Probability of Backtest Overfitting and CSCV.
- Bailey and Lopez de Prado: Deflated Sharpe Ratio for selection bias, multiple testing, and non-normality.
- Harvey, Liu, and Zhu: multiple testing in expected returns and higher hurdles for newly discovered factors.
