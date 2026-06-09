---
name: quant-strategy-offload
description: Use when offloading a completed quant_autoresearch thesis into a downstream strategy repository, either a Train survivor for evaluation or a failed/abandoned thesis for archive and cleanup. Covers using the quant_strategies/researched destination, curating evidence, writing survivor README or failed-thesis verdict, and cleaning the research bench afterward.
---

# Quant Strategy Offload

## Purpose

Move a completed `quant_autoresearch` Train thesis out of the research bench and into a downstream strategy project. The output is a curated, auditable strategy package, not a dump of every generated artifact.

There are two modes:

- **Survivor offload:** a Train survivor exists and Season wants a package for downstream OOS/paper/small-live evaluation.
- **Failed-thesis offload:** no Train survivor exists, or Season explicitly calls the thesis failed/paused and wants the useful lessons preserved before cleaning the bench.

Default destination for completed Train theses:

```text
~/Personal/quant_strategies/researched/<strategy-slug>/
```

Use `~/Personal/quant_strategies/researched/` for both Train survivors and failed/paused Train theses. The README verdict distinguishes `Train survivor` from `Failed on Train`.

Use `~/Personal/quant_strategies/candidates/` only for manually seeded, unresearched, or pre-autoresearch strategy candidates unless Season explicitly chooses otherwise.

## Preconditions

Before offloading:

- `results.tsv` exists and is the canonical active ledger.
- The loop has stopped or Season explicitly asks to offload a current survivor.
- The active `strategy.py` matches the frozen best survivor snapshot, or any mismatch is intentional and documented.
- Do not run OOS/evaluation inside `quant_autoresearch`; the offload package is for downstream review or archive only.

For failed-thesis offload:

- `results.tsv` should show no `keep` row, or Season explicitly says the thesis is failed/paused.
- Do not manufacture a survivor or promote the best discard row.
- The current `strategy.py` may represent the last failed variant rather than a canonical candidate; choose and document the exact final code state being archived.
- The package is for memory and cleanup, not downstream evaluation, unless Season later reopens the idea as a fresh thesis.

Recommended checks:

```bash
conda run -n quant python -m loop status
conda run -n quant python -m py_compile strategy.py
diff -u strategy.py results/autoresearch/<best-attempt>/snapshot/strategy.py
```

For failed-thesis offload, replace `<best-attempt>` with the selected archived code attempt, or skip the diff if the current working file is intentionally the archived state and that is documented.

## Destination Layout

For survivor offload, use this layout unless the destination repo has an established convention:

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

For failed-thesis offload, use a smaller layout:

```text
~/Personal/quant_strategies/researched/<strategy-slug>/
  README.md
  rationale.md
  strategy.py
  experiment.toml
  protocol.train.toml
  results.tsv
  failed_cases/
    attempt-XXXX-<short-label>/
      strategy.py
      experiment.toml
      protocol.toml
      quick_config.toml
      diagnostics.json
      summary.json
  diagnostics/
```

Do not create an `evaluation/` plan for failed-thesis offloads unless Season explicitly asks to reopen the thesis.

## Candidate Retention Policy

For survivor offload, retain at least 20 experiments when available. Select for structural diversity and diagnostic value, not just top score.

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

For failed-thesis offload, keep the package deliberately small: usually 3-7 failed cases.

Retain:

- **Best near-miss:** highest score or most economically plausible discard, even if gates failed.
- **Terminal/final case:** the attempt that stopped the loop or the last meaningful paused attempt.
- **Turning-point diagnostic:** the case that revealed the likely failure cause, such as wrong entry timing, unstable pair family, bad exit design, or insufficient trade coverage.
- **Anti-pattern representatives:** one or two attempts that clearly show what not to repeat.
- **Optional implementation failure:** only if a crash/engine issue taught a durable engineering lesson.

Do not retain a broad sweep. Drop repeated threshold, cadence, and near-duplicate rows unless they support the verdict.

Every retained failed case needs a verdict line:

```text
attempt-XXXX: <idea tested> -> <why it failed> -> <what not to repeat or what could be reopened>
```

## What To Copy

For each retained survivor/offload attempt, copy:

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

For failed-thesis offload, copy only selected failed cases plus the canonical ledger. Prefer attempt snapshots over mutable working files. If the final working files differ from the selected case, copy them as the current archived code and state why in `README.md`.

## README Requirements

For survivor offload, the destination `README.md` must answer:

- What is the thesis?
- What exact attempt is the current Train survivor?
- What files are authoritative?
- What Train data window, symbols, fills, costs, objective, and gates were used?
- What candidates were retained and why?
- What retention policy was used, including that candidates were selected for structural diversity and diagnostic value rather than only performance rank?
- What failed ideas should not be repeated?
- What is the downstream evaluation plan?
- What must not be inferred from Train evidence?

For failed-thesis offload, the destination `README.md` must answer:

- What was the thesis?
- What is the verdict? Use direct language such as `Failed on Train: no survivor`.
- Why did it fail? Give the top 3-5 causal reasons, not just scores.
- Which 3-7 failed cases were retained and why?
- What should not be repeated?
- What might be worth reopening as a fresh thesis, if anything?
- What exact data window, symbols, fills, costs, objective, and gates were used?
- What source files and result ledger are authoritative?
- What cleanup was performed in `quant_autoresearch`?

Required disclaimer:

```text
This package is Train-only research evidence. It is not OOS, paper, live, or deployability evidence.
```

For failed-thesis packages, add:

```text
This package records a failed Train thesis. It is not a candidate for OOS, paper, live, or deployment review unless Season explicitly reopens it as a new thesis.
```

## Evaluation Boundary

Keep the handoff one-way:

- Downstream evaluation may compare top candidates.
- Do not feed OOS results back into this same Train thesis.
- If OOS fails, archive or start a fresh thesis from the learned principles.
- Do not patch the same candidate after seeing OOS.

For failed-thesis offload, no downstream evaluation is expected. If the idea later looks worth revisiting, start a new thesis with a new protocol/ledger instead of continuing the failed Train loop.

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

For survivor offload:

1. Identify best survivor and top structural candidates from `results.tsv`.
2. Build a retention list with at least 20 experiments if available.
3. Create destination under `~/Personal/quant_strategies/researched/<strategy-slug>/`.
4. Copy authoritative snapshots and diagnostics for retained attempts.
5. Write a curated `rationale.md`: preserve current thesis, durable decisions, candidate taxonomy, residual risks, and links to retained evidence; collapse noisy turn-by-turn history.
6. Write `README.md` using the requirements above.
7. Validate copied files exist and hashes or attempt IDs match `results.tsv`.
8. Clean the source `quant_autoresearch` bench if Season approves.
9. Do not run downstream evaluation unless Season explicitly asks.

For failed-thesis offload:

1. Confirm there is no Train survivor, or that Season explicitly wants a failed/paused thesis offloaded.
2. Write the verdict first: one sentence for what failed and why it matters.
3. Select 3-7 failed cases: best near-miss, terminal/final case, turning-point diagnostic, and one or two anti-patterns.
4. Create destination under `~/Personal/quant_strategies/researched/<strategy-slug>/`.
5. Copy selected snapshots and diagnostics only; do not copy the full generated tree.
6. Copy canonical `results.tsv`, current or curated `rationale.md`, and terminal manifest if present.
7. Write `README.md` with the failed-thesis requirements above.
8. Validate copied files exist and selected attempt IDs match `results.tsv`.
9. Clean the source `quant_autoresearch` bench if Season approves, using the same cleanup policy below.
10. Do not run downstream evaluation.

## Source Bench Cleanup

After a successful offload, ask Season before destructive cleanup. The cleanup goal is to make `quant_autoresearch` ready for a new thesis while preserving the downstream handoff and enough local provenance to know what moved.

Default cleanup policy:

- Keep `program.md`, `protocol.toml`, project code, and tests unless Season explicitly asks to reset protocol state.
- Reset `strategy.py` only to a known repo template, a Season-provided next thesis, or an existing neutral baseline. If no such template exists, do not invent one; leave the offloaded strategy in place with a clear archived/offloaded warning.
- Reset `experiment.toml` only to a known repo template, a Season-provided next thesis, or a confirmed blank-bench config. If no such template exists, do not invent one.
- Rewrite `rationale.md` into a compact handoff note, not the full history:
  - destination path;
  - offloaded survivor attempt ID or failed-thesis verdict;
  - hash/date of offload;
  - “this thesis is archived/offloaded” warning;
  - next-thesis placeholder.
- Move or delete `results.tsv` only after the destination copy is validated.
- Remove generated result artifacts under `results/autoresearch/` only after the retained attempts and diagnostics are copied.
- Remove generated quick-run configs under `.autoresearch/quick/` only after retained `quick_config.toml` files are copied.
- Remove temporary root-level duplicate ledgers such as `results_continuation.tsv`, `results_plateau_*.tsv`, and `results_max_iterations_*.tsv`.
- Preserve `.autoresearch/thesis_lock.json` only if continuing the same thesis; otherwise archive or remove it so the next run can create a new lock.

Recommended cleanup sequence:

1. Verify downstream package has `README.md`, `rationale.md`, canonical `results.tsv`, selected strategy snapshot, retained cases/candidates, diagnostics, and protocol/experiment snapshots.
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

Never delete the only copy of a survivor, failed-case evidence, retained diagnostics, or canonical results. If the downstream copy cannot be validated, stop cleanup and report the gap.

## Destination Choice Guidance

Use `quant_strategies/researched` for completed `quant_autoresearch` Train theses, whether the verdict is a Train survivor or failed on Train.

Use `quant_strategies/candidates` for manually seeded, unresearched, or pre-autoresearch executable strategy candidates.

Use a generic `strategies` repository only for prose-only ideas, non-executable playbooks, or strategy notes without quant evaluation artifacts.
