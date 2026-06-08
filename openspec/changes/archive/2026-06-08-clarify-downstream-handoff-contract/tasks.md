## 1. CLI Handoff Output

- [x] 1.1 Verify `climb` prints every `ResultRow.as_record()` field as `key: value`.
- [x] 1.2 Add or update CLI tests for full result-row output.
- [x] 1.3 Keep output parseable and avoid adding narrative prose to the command output.

## 2. Downstream Review Artifacts

- [x] 2.1 Add `docs/templates/oos-drift-review.md` for one-look downstream OOS drift review.
- [x] 2.2 Include frozen candidate identity, Train evidence, OOS evidence, drift comparison, and human decision fields in the template.
- [x] 2.3 Make the template explicitly state that OOS results must not tune the same candidate.
- [x] 2.4 Add `docs/adr/0001-curated-few-research-regime.md` with current regime and escalation triggers.

## 3. Documentation Links And Review Status

- [x] 3.1 Add minimal README/program pointers to downstream handoff artifacts without expanding the agent loop contract.
- [x] 3.2 Update the foundation review action map: mark item 6 addressed if verified, and mark items 7, 10, and 11 addressed after implementation.
- [x] 3.3 Ensure docs do not imply OOS is read or run by auto-research.

## 4. Verification

- [x] 4.1 Run focused tests for CLI output and docs contracts.
- [x] 4.2 Run `conda run -n quant python -m pytest -q`.
- [x] 4.3 Run `conda run -n quant python -m ruff check .`.
- [x] 4.4 Run `openspec validate clarify-downstream-handoff-contract --strict`.
- [x] 4.5 Run `conda run -n quant python -m loop status`.
