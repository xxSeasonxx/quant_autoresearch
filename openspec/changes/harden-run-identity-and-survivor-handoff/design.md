## Context

`quant_autoresearch` is intentionally a small Train-only loop. It already records per-attempt hashes in `results.tsv`, but two identity boundaries remain procedural:

- terminal manifests select the best kept row but snapshot current workspace files;
- continuation compares current attempts against all prior rows without a run/thesis/protocol lock.

Both defects can contaminate downstream OOS/paper review even when the Train loop itself is otherwise simple and bounded.

## Goals / Non-Goals

**Goals:**

- Make a terminal Train survivor snapshot match the best kept attempt that produced the recorded Train evidence.
- Prevent one active `results.tsv` lifecycle from mixing protocols, bounds, or thesis identity.
- Preserve the current LLM research workflow and append-only TSV model.
- Keep generated state under `.autoresearch/` and `results/`.

**Non-Goals:**

- No automated OOS/evaluation wiring.
- No database, ledger, candidate-family tracking, DSR/PBO, or broader validation framework.
- No general result-log audit system beyond the checks needed for these P0 boundaries.
- No change to `quant_strategies` public API usage.

## Decisions

### Decision 1: Snapshot candidate-defining files for each attempt

Each attempt writes a generated source snapshot under its attempt artifact directory, containing:

- `strategy.py`
- `experiment.toml`
- `protocol.toml`
- `rationale.md`
- `quick_config.toml`

This makes the handoff source independent of whatever the workspace looks like when a stop rule fires.

Alternative considered: reset the workspace to the best kept commit before writing the terminal manifest. Rejected because it is more invasive, depends on git state, and conflicts with the current design where discarded working variants may remain useful bases.

### Decision 2: Terminal manifests distinguish terminal attempt and best survivor

Terminal manifests keep the terminal attempt record, but add explicit snapshot references:

- terminal attempt snapshot;
- best survivor snapshot when a kept candidate exists;
- no best survivor snapshot for Train failure.

The survivor snapshot must be copied from the best kept attempt's generated artifact, not from the current workspace.

Alternative considered: only copy `best_quick_config`. Rejected because downstream review needs the strategy, params, protocol, and rationale that produced the best evidence.

### Decision 3: Use a small generated thesis lock

The first ordinary `climb` for a thesis creates `.autoresearch/thesis_lock.json` with:

- normalized mechanism and falsifier;
- current protocol hash;
- current experiment bounds hash;
- results path;
- created run metadata.

Later attempts must match the lock. Changing the thesis, protocol, or bounds means Season is starting a new thesis lifecycle and should rotate generated state/results intentionally.

Alternative considered: add columns to every `results.tsv` row for lock identity. Rejected for this change because existing rows already contain protocol/experiment hashes, and a small generated lock is enough to block drift without widening the TSV.

### Decision 4: Hash bounds separately from param values

The agent may change `[params]` during a thesis but may not change existing `[bounds.*]`. The lock therefore records a stable bounds hash derived only from the bounds block, not the full `experiment.toml`.

Alternative considered: freeze the full experiment hash. Rejected because it would block valid param changes.

## Risks / Trade-offs

- Generated lock can become stale after intentional reseed -> mitigation: fail with a clear message telling Season to start a new thesis/run state.
- Snapshotting files on every attempt duplicates small text files -> mitigation: acceptable for a tiny repo and much simpler than reconstructing from git.
- Mechanism/falsifier matching may be annoying if CLI text changes slightly -> mitigation: normalize whitespace and print the locked values in the error/status path.
- Bounds hashing requires parsing `experiment.toml` -> mitigation: reuse the existing experiment loader and hash only normalized bounds data.
