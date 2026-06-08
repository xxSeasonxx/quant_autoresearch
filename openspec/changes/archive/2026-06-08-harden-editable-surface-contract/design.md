## Context

The P0 evidence contract made each attempt identifiable and harder to misread. The next foundation risk is one level closer to the LLM-editable surface:

```text
strategy.py       free-form signal expression
experiment.toml   params + declared bounds
rationale.md      thesis + declared signal components
```

The repo already tells the agent to stay within bounded params and update rationale when signal components change, but the backend still trusts procedure in two places:

- `load_params()` reads only `[params]` and ignores `[bounds.*]`.
- `climb_once()` defaults `components=("baseline",)` instead of deriving components from `rationale.md`.

The root fix is to make the editable surface itself a small contract, not to add inspection layers around strategy code.

```text
EditableSurface =
  ExperimentContract(params + bounds)
  + RationaleContract(thesis + components)
  + EvidenceLanguageContract(current docs say what the code means)
```

## Goals / Non-Goals

**Goals:**

- Validate all ordinary strategy params against operator-visible bounds before a quick-run config is materialized.
- Derive signal component count from `rationale.md`, so the complexity gate reflects the agent-maintained thesis record instead of a caller default.
- Keep the agent's strategy exploration open: thesis-guided variants are allowed, but params and component accounting are explicit.
- Mark stale implementation discussion as historical so active instructions stay short and current.
- Keep score wording honest: trade-unit robustness, not Sharpe or deployability evidence.

**Non-Goals:**

- Do not inspect `strategy.py` AST to infer components.
- Do not add a component registry file.
- Do not create a second params/bounds file.
- Do not add a new runtime manifest.
- Do not implement P2 OOS drift templates or curated-few ADRs here.
- Do not solve all mypy issues unless the typed experiment boundary naturally removes them.

## Decisions

### Decision 1: `experiment.toml` becomes the experiment contract

Add a focused loader, likely `load_experiment(path) -> ExperimentConfig`, with:

- `params: dict[str, int | float]`
- `bounds: dict[str, ParamBound]`
- validation that every param has a matching bound,
- validation that every bound corresponds to a param,
- validation that param values are numeric and inside inclusive `[min, max]`.

Keep `load_params()` only as a compatibility wrapper around `load_experiment().params`, or retire it if all callers migrate cleanly.

Alternatives considered:

- **Rely on `strategy.validate_params()`.** Too late and editable by the agent; bounds are supposed to be an external accounting contract.
- **Move bounds into `protocol.toml`.** Stronger ownership, but it spreads one strategy's dials into the protocol and makes ordinary agent param edits less ergonomic.
- **Use Pydantic.** Reasonable, but unnecessary for this tiny TOML shape.

### Decision 2: Rationale components are parsed from Markdown headings

Derive components from headings under `## Signal Components`:

```markdown
### Component: baseline momentum
```

This is intentionally simple. The parser should not infer strategy structure; it only counts what the agent declared in the thesis record. If no components are declared for an ordinary run, the run should fail before quick-run materialization with a clear message.

Alternatives considered:

- **CLI `--component` arguments.** Still caller-trusted and easy to forget.
- **AST inspection of `strategy.py`.** Too heavy and brittle; would punish legitimate creative exploration.
- **Separate component registry file.** Another active artifact for the agent to maintain; not needed while `rationale.md` already carries thesis context.

### Decision 3: Complexity gate consumes derived accounting

The complexity cap should continue to live in `gates.py`, but ordinary loop execution should supply:

- params from `ExperimentConfig.params`,
- components from `components_from_rationale(rationale.md)`.

`evaluate_gates()` stays simple; the root change is who owns the data passed into it.

### Decision 4: Documentation cleanup is active/historical separation, not rewrite

`README.md`, `program.md`, `protocol.toml`, and OpenSpec specs are active guidance. `docs/simplified-autoresearch-loop-design.md` is historical design context and should say so at the top. Do not rewrite it into a second live source of truth.

## Risks / Trade-offs

- **Bounds can become annoying during exploration** -> The agent can still edit `[params]` freely inside bounds; changing bounds is an operator/protocol-seed decision before a thesis run.
- **Markdown parsing can be brittle** -> Keep the accepted syntax narrow and documented. This is deliberate accounting, not natural-language understanding.
- **Agent may under-declare components** -> This remains a human-gated review risk. Mechanical parsing makes omissions visible; it does not prove the declaration matches code.
- **Future non-numeric params may need schema work** -> Current contract covers bounded numeric params only. Add a new schema only when a real strategy needs categorical params.
- **Historical doc may still be read by agents** -> Put the historical/superseded warning at the top and point to active docs/specs.

## Migration Plan

1. Add `ExperimentConfig` / `ParamBound` and validation tests.
2. Route `climb_once()` and quick-run materialization through validated experiment params.
3. Add rationale component parser and tests for ordinary headings, missing components, and unrelated headings.
4. Route ordinary loop component accounting through parsed rationale components.
5. Update active docs with minimal wording: free exploration inside bounds, component headings are accounting, design doc is historical.
6. Mark P1 action-map rows addressed after implementation.

## Open Questions

- Should bounds be required for every param immediately, or should missing bounds fail only for keys modified by the agent? Recommendation: require bounds for every param in `[params]` to keep the contract simple.
- Should duplicate component names be rejected? Recommendation: reject duplicates after normalizing whitespace/case.
