## 1. Protocol And Config

- [x] 1.1 Add protocol dataclass fields and validation for portfolio foundation output, PSR hurdle, foundation-backed gate thresholds, and `micro` causality.
- [x] 1.2 Materialize foundation output settings into quick-run config and update `protocol.toml` for the new objective/gates.

## 2. Objective And Gates

- [x] 2.1 Add typed local foundation metric/scenario inputs and PSR scoring for `portfolio_psr_subwindow`.
- [x] 2.2 Replace foundation-mode cost stress and gates with upstream foundation scenario metrics while preserving trade diagnostics for reporting.

## 3. Results And Artifacts

- [x] 3.1 Update `ResultRow` schema, parsing, and header migration for the compact portfolio-foundation metric set.
- [x] 3.2 Write per-attempt `run_card.json` with score parts, gate details, foundation warnings, and causality evidence.

## 4. Loop Integration

- [x] 4.1 Extract foundation and economics from `RunResult`, compute objective/gates, append compact result rows, and fail clearly when required foundation evidence is unavailable.
- [x] 4.2 Preserve keep/discard/stop semantics for portfolio-foundation scoring.

## 5. Verification And Docs

- [x] 5.1 Add focused tests for protocol loading/materialization, PSR scoring/gates, result schema/header behavior, and loop integration with synthetic run results.
- [x] 5.2 Update README/program docs for portfolio-foundation scoring, compact TSV metrics, run cards, and micro causality.
- [x] 5.3 Run the focused test suite and mark the OpenSpec tasks complete.
