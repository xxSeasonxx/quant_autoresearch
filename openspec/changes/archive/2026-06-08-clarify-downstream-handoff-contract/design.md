## Context

The Train loop now has stronger evidence contracts, but the human handoff is still split between console output, generated manifests, and informal downstream review. This creates two risks:

- the agent or Season may need to open `results.tsv` manually to see the evidence needed for the next edit;
- OOS comparison may happen informally, making it harder to preserve the one-look downstream discipline.

The root fix is a clearer handoff boundary, not OOS automation.

```text
Train loop
  produces attempt rows + terminal manifest
  prints complete latest attempt summary
        |
        v
Season downstream review
  fills OOS drift template once
  records curated-few regime decision
        |
        v
paper -> small live -> scale
```

## Goals / Non-Goals

**Goals:**

- Make `climb` output sufficiently complete for the next edit and human inspection without opening `results.tsv`.
- Provide a downstream one-look OOS drift template for Season to use after a frozen Train survivor exists.
- Record the curated-few thesis-driven regime and the trigger for heavier multiple-testing controls.
- Keep the Train loop from importing, reading, or writing downstream OOS artifacts.

**Non-Goals:**

- Do not implement OOS evaluation.
- Do not add a new `oos`, `evaluate`, `screen`, or `graduate` command.
- Do not read downstream templates from `loop.py`.
- Do not implement paper/live infrastructure.
- Do not add DSR/PBO/CSCV or multiple-testing statistics.
- Do not solve mypy/type-boundary cleanup.

## Decisions

### Decision 1: `climb` prints the result-row summary

Keep CLI output simple and parseable by printing one `key: value` line per result-row field, matching `ResultRow.as_record()`. This is already close to the current implementation shape and does not create a new display schema.

Alternatives considered:

- **Pretty report format.** Easier to read, harder for agents to parse reliably.
- **JSON output only.** Useful later, but not needed for current local workflow.

### Decision 2: Downstream OOS drift is a template, not code

Add a Markdown template under `docs/templates/oos-drift-review.md`. It should be explicitly human-owned and filled once per frozen Train survivor. It should record Train evidence, OOS evidence, deltas, and final human decision, while stating that results must not feed back into the same candidate.

Alternatives considered:

- **Automate OOS drift from `loop.py`.** Violates the Train-only wall.
- **Do nothing.** Leaves Season's stated OOS drift concern informal.

### Decision 3: Curated-few is an ADR

Add `docs/adr/0001-curated-few-research-regime.md` to capture the regime choice and escalation trigger. This keeps the decision durable without expanding `program.md`.

Escalation triggers should include automated-many generation, many independent OOS looks, or using historical validation as a deployment verdict.

## Risks / Trade-offs

- **Templates can be ignored** -> Keep them small and link from README/program only where helpful.
- **ADR can become stale** -> State the trigger conditions rather than trying to forecast all future research modes.
- **CLI output can become too verbose** -> Use existing row fields and avoid explanatory prose in command output.
- **OOS template can tempt iteration** -> Include explicit "one look; no same-candidate tuning" language.

## Migration Plan

1. Confirm `climb` output already prints all row fields; add or adjust tests if needed.
2. Add OOS drift review template under `docs/templates/`.
3. Add curated-few ADR under `docs/adr/`.
4. Add docs pointers without expanding the one-page `program.md` too much.
5. Mark foundation review items 6, 7, 10, and 11 addressed if implemented.
