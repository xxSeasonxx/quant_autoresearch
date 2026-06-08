## 1. Experiment Bounds Contract

- [x] 1.1 Add `ParamBound` and `ExperimentConfig` data structures for `[params]` and `[bounds.*]`.
- [x] 1.2 Implement `load_experiment()` that validates numeric params against inclusive bounds.
- [x] 1.3 Make missing param bounds and orphan bounds fail with clear errors.
- [x] 1.4 Route `climb_once()` and quick-run materialization through validated experiment params.
- [x] 1.5 Keep or retire `load_params()` as a compatibility wrapper with tests updated accordingly.

## 2. Rationale Component Contract

- [x] 2.1 Implement deterministic parsing of `### Component: <name>` headings under `## Signal Components`.
- [x] 2.2 Reject missing component declarations and duplicate normalized component names before quick-run materialization.
- [x] 2.3 Route ordinary loop component accounting through parsed rationale components instead of the CLI/default tuple.
- [x] 2.4 Keep `evaluate_gates()` simple; pass it validated params and parsed components.

## 3. Tests

- [x] 3.1 Add protocol/experiment tests for in-bounds, below-bound, above-bound, missing-bound, and orphan-bound cases.
- [x] 3.2 Add rationale parser tests for declared components, duplicate components, missing components, and unrelated headings.
- [x] 3.3 Add loop tests proving out-of-bound params and missing/duplicate components fail before `run_config`.
- [x] 3.4 Add gate/loop tests proving complexity count uses rationale-derived components and validated params.

## 4. Docs And Review Status

- [x] 4.1 Update `program.md` minimally: open thesis-guided exploration inside existing bounds, rationale component headings are accounting.
- [x] 4.2 Update `README.md` to describe validated experiment params and rationale-derived component accounting.
- [x] 4.3 Mark `docs/simplified-autoresearch-loop-design.md` as historical/superseded context and point to active docs/specs.
- [x] 4.4 Update `docs/reviews/foundation-review-20260607.md` action map statuses for addressed P1 items after implementation.

## 5. Verification

- [x] 5.1 Run focused tests for protocol/experiment loading, rationale parsing, gates, and loop rejection paths.
- [x] 5.2 Run `conda run -n quant python -m pytest -q`.
- [x] 5.3 Run `conda run -n quant python -m ruff check .`.
- [x] 5.4 Run `conda run -n quant python -m mypy .` and document any remaining residual failures. Mypy still fails on existing untyped upstream/strategy/test-protocol boundaries.
- [x] 5.5 Run `conda run -n quant python -m loop status`.
