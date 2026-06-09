---
name: quant-strategy-offload
description: Use when offloading a Train survivor from quant_autoresearch into a downstream strategy repository for evaluation, including choosing the quant_strategies/researched destination, curating at least 20 structurally distinct experiments, moving rationale and evidence, pruning bad candidates, writing a README for OOS/paper evaluation, and cleaning the research bench afterward.
---

# Quant Strategy Offload

## Purpose

Move a completed `quant_autoresearch` Train thesis out of the research bench and into a downstream strategy project for evaluation. The output is a curated, auditable strategy package, not a dump of every generated artifact.

Default destination:

```text
~/Personal/quant_strategies/researched/<strategy-slug>/
```

Use `~/Personal/quant_strategies/researched/` rather than a generic `strategies/` directory unless Season explicitly chooses otherwise.

## Preconditions

Before offloading:

- `results.tsv` exists and is the canonical active ledger.
- The loop has stopped or Season explicitly asks to offload a current survivor.
- The active `strategy.py` matches the frozen best survivor snapshot, or any mismatch is intentional and documented.
- Do not run OOS/evaluation inside `quant_autoresearch`; this package is for downstream evaluation.

Recommended checks:

```bash
conda run -n quant python -m loop status
conda run -n quant python -m py_compile strategy.py
diff -u strategy.py results/autoresearch/<best-attempt>/snapshot/strategy.py
```

## Destination Layout

Use this layout unless the destination repo has an established convention:

```text
~/Personal/quant_strategies/researched/<strategy-slug>/
  README.md
  rationale.md
  strategy.py
  experiment.toml
  protocol.train.toml
  results.tsv
  candidates/
    survivors/
    near_misses/
    anti_patterns/
  diagnostics/
  evaluation/
    README.md
```

Keep source files and evidence tied to exact attempts. Prefer copying frozen snapshots from `results/autoresearch/attempt-XXXX/snapshot/` over copying mutable working files, except for the final curated `rationale.md`.

## Candidate Retention Policy

Retain at least 20 experiments when available. Select for structural diversity and diagnostic value, not just top score.

Candidate buckets:

- **Survivors:** `status=keep` or the final selected handoff candidate.
- **Gated candidates:** all gates pass but the row did not update the best survivor.
- **Near misses:** failed exactly one gate or narrowly missed keep threshold, with high score or clear diagnostic value.
- **Anti-patterns:** one or two representative failures for ideas Season should not repeat.
- **Bad candidates to drop:** dominated variants, mechanical parameter churn, duplicate/equivalent rows, failed runs without a new lesson, and candidates that are neither survivors, near-misses, nor anti-pattern representatives.

Prefer distinct thesis expressions. The retained set should preserve candidates that represent genuinely different research theses or structural mechanisms, not only the same thesis with small parameter sweeps. A candidate earns retention when it changes what market behavior is being tested or how the thesis is expressed:

- Side thesis: two-sided, long-only, short coverage, coverage sleeve.
- Effective universe: all symbols, non-BTC, high-purity subsets.
- Signal definition: base funding pressure, strong funding threshold, funding acceleration, symbol-specific filters.
- Timing thesis: cadence, session timing, symbol-specific timing.
- Exit thesis: time exit horizon, per-symbol hold, TP/SL/trailing stop.
- State thesis: repeated tranches, suppression, tranche caps.

Avoid keeping many rows that differ only by tiny boundary tuning unless they mark an important boundary around a survivor.

For this repository’s crypto perp funding thesis, a good target is 20-25 retained experiments, including:

- Final best survivor.
- Earlier structural survivors.
- High-score one-gate misses.
- Representative failures for shorts, take-profit, stop-loss, trailing stop, hard acceleration, and tranche caps.

## What To Copy

For each retained attempt, copy:

- `snapshot/strategy.py`
- `snapshot/experiment.toml`
- `snapshot/protocol.toml`
- `snapshot/quick_config.toml`
- `diagnostics.json`
- `summary.json`
- optionally `notes.md`, `data_manifest.json`, and `run_manifest.json`

Also copy:

- canonical `results.tsv`
- final or curated `rationale.md`
- terminal manifest if present

Do not copy the entire `results/autoresearch/` tree unless Season explicitly asks. It is too noisy for downstream evaluation.

## README Requirements

The destination `README.md` must answer:

- What is the thesis?
- What exact attempt is the current Train survivor?
- What files are authoritative?
- What Train data window, symbols, fills, costs, objective, and gates were used?
- What candidates were retained and why?
- What retention policy was used, including that candidates were selected for structural diversity and diagnostic value rather than only performance rank?
- What failed ideas should not be repeated?
- What is the downstream evaluation plan?
- What must not be inferred from Train evidence?

Required disclaimer:

```text
This package is Train-only research evidence. It is not OOS, paper, live, or deployability evidence.
```

## Evaluation Boundary

Keep the handoff one-way:

- Downstream evaluation may compare top candidates.
- Do not feed OOS results back into this same Train thesis.
- If OOS fails, archive or start a fresh thesis from the learned principles.
- Do not patch the same candidate after seeing OOS.

## Bad-Candidate Pruning

Use this definition:

```text
Bad = not a survivor, not a near-miss, and not uniquely informative.
```

Drop:

- repeated parameter/cadence variants dominated by later attempts;
- candidates failing multiple gates with no new lesson;
- attempts that only prove the same anti-pattern already represented elsewhere;
- crash rows once the repair is understood.

Keep a small anti-pattern set so future research avoids rediscovering the same failures.

## Offload Steps

1. Identify best survivor and top structural candidates from `results.tsv`.
2. Build a retention list with at least 20 experiments if available.
3. Create destination under `~/Personal/quant_strategies/researched/<strategy-slug>/`.
4. Copy authoritative snapshots and diagnostics for retained attempts.
5. Write a curated `rationale.md`: preserve current thesis, durable decisions, candidate taxonomy, residual risks, and links to retained evidence; collapse noisy turn-by-turn history.
6. Write `README.md` using the requirements above.
7. Validate copied files exist and hashes or attempt IDs match `results.tsv`.
8. Clean the source `quant_autoresearch` bench if Season approves.
9. Do not run downstream evaluation unless Season explicitly asks.

## Source Bench Cleanup

After a successful offload, ask Season before destructive cleanup. The cleanup goal is to make `quant_autoresearch` ready for a new thesis while preserving the downstream handoff and enough local provenance to know what moved.

Default cleanup policy:

- Keep `program.md`, `protocol.toml`, project code, and tests unless Season explicitly asks to reset protocol state.
- Reset `strategy.py` only to a known repo template, a Season-provided next thesis, or an existing neutral baseline. If no such template exists, do not invent one; leave the offloaded survivor in place with a clear archived/offloaded warning.
- Reset `experiment.toml` only to a known repo template, a Season-provided next thesis, or a confirmed blank-bench config. If no such template exists, do not invent one.
- Rewrite `rationale.md` into a compact handoff note, not the full history:
  - destination path;
  - offloaded survivor attempt ID;
  - hash/date of offload;
  - “this thesis is archived/offloaded” warning;
  - next-thesis placeholder.
- Move or delete `results.tsv` only after the destination copy is validated.
- Remove generated result artifacts under `results/autoresearch/` only after the retained attempts and diagnostics are copied.
- Remove generated quick-run configs under `.autoresearch/quick/` only after retained `quick_config.toml` files are copied.
- Remove temporary root-level duplicate ledgers such as `results_continuation.tsv`, `results_plateau_*.tsv`, and `results_max_iterations_*.tsv`.
- Preserve `.autoresearch/thesis_lock.json` only if continuing the same thesis; otherwise archive or remove it so the next run can create a new lock.

Recommended cleanup sequence:

1. Verify downstream package has `README.md`, `rationale.md`, canonical `results.tsv`, final survivor snapshot, retained candidates, diagnostics, and protocol/experiment snapshots.
2. Write `OFFLOADED.md` or a compact top section in `rationale.md` pointing to the downstream destination.
3. Delete or archive generated artifacts not retained downstream.
4. Reset active editable surfaces only after Season confirms the next intended state:
   - `strategy.py`
   - `experiment.toml`
   - `rationale.md`
   - `results.tsv`
   - `.autoresearch/thesis_lock.json`
   - `.autoresearch/quick/`
5. Run lightweight validation:
   ```bash
   git status --short
   find results -mindepth 1 -maxdepth 2 -type d | sort | head
   test -f results.tsv && tail -n 3 results.tsv || true
   ```

Never delete the only copy of a survivor, retained diagnostics, or canonical results. If the downstream copy cannot be validated, stop cleanup and report the gap.

## Destination Choice Guidance

Use `quant_strategies/researched` when the package includes executable strategy code, provenance, and evaluation plans.

Use a generic `strategies` repository only for prose-only ideas, non-executable playbooks, or strategy notes without quant evaluation artifacts.
