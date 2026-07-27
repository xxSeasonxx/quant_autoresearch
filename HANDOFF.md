# Objective

Keep Train attempts comparable and immutable while allowing Season to extend a
configured stop budget without editing generated evidence. Research identity must
remain frozen; lifecycle state must be derived from attempts and explicitly
authorized stop rules.

## Current state

- The compatibility-breaking lifecycle cutover is implemented and documented.
- `results.tsv` no longer stores continuation or stop reason. Thesis locks use
  semantic protocol identity, and extensions use
  `.autoresearch/lifecycle_events.jsonl`.
- The repo has no active lifecycle: `python -m loop status` reports zero attempts
  and `continuation: allowed`.
- The full suite passes: `116 passed`. Mypy passes for all 12 source files.
- The ignored local setup and offload skills include
  `.autoresearch/lifecycle_events.jsonl` in baseline preflight, provenance
  retention, and bench cleanup.
- `UPSTREAM_LIMITATIONS_TODO.md` and `docs/capacity-model-study-guide.md` contain
  pre-existing work outside this implementation.

## Next steps

1. Review and commit the intended harness, test, and documentation files.
   Success: the commit excludes unrelated upstream/capacity-study edits.
2. Before the next baseline, run `new-thesis-setup`.
   Success: the approved protocol retains micro causality replay and the baseline
   run card reports admissible causality evidence.
3. Treat the remaining calibration and capacity items in
   `docs/HARNESS_CONSTRAINT_REVIEW.md` as separate operator studies.
   Success: no threshold or engine constant changes without its own evidence and
   approval.

## Open questions / risks

- `extend` intentionally requires Season to edit the three stop fields before
  recording authorization; the autonomous Train agent must not invoke it.
- The event log is append-only by contract and validates its sequence and stop-rule
  chain; it is not a cryptographic tamper-proof store.
- A real stopped lifecycle has not yet exercised `extend`; temporary-workspace tests
  cover baseline, repeated extension, rejection, and audit behavior.

## Key references

- `program.md` — active Train and extension contract.
- `docs/score_research.md` — ledger and run-card semantics.
- `docs/HARNESS_CONSTRAINT_REVIEW.md` — evidence and remaining studies.
- Verification: `conda run -n quant python -m pytest -q`,
  `conda run -n quant python -m mypy .`,
  `conda run -n quant python -m loop status`.
