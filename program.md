# autoresearch program

This file is the one-page operating contract for an autonomous quant research run. Its shape intentionally mirrors the reference `autoresearch` repo: setup, experimentation, output format, logging, and loop. The content is trading-specific.

## Setup

To start a new thesis run, work with Season to:

1. Agree on a run tag and a thesis: one mechanism sentence plus one falsifier.
2. Start from a clean branch or a clearly named working branch for this run.
3. Read the in-scope files:
   - `README.md` for the project map.
   - `program.md` for this operating contract.
   - `protocol.toml` for fixed Train data, objective, gates, costs, fills, and loop constants.
   - `experiment.toml` for bounded params.
   - `strategy.py` for the editable signal logic.
4. Verify the configured Train data is available through `quant_data` / `quant_strategies`.
5. Initialize `results.tsv` with only the header row if it does not exist.
6. Confirm setup, then begin.

## Experimentation

The loop uses Train-only quick runs. It is a development filter, not proof of an edge.

**What you can edit:**

- `strategy.py`: pure signal logic via `generate_decisions(rows, params)`.
- `experiment.toml` bounded params under `[params]`.
- `rationale.md`: required when a signal component is added or materially changed.

**What is read-only:**

- `protocol.toml`: symbols, Train window, data kind, costs, fills, objective, gates, and loop constants.
- OOS and forward testing surfaces. They are downstream and human-gated.
- Generated artifacts under `.autoresearch/` and `results/`.

Do not change symbols, hours, dates, costs, fills, objective kind, gate thresholds, `plateau_patience`, `max_iterations`, `subwindows`, `min_abs_improvement`, or `min_rel_improvement` from strategy params. If these need to change, Season changes the protocol before the thesis starts.

Do not run `evaluate` inside auto-research. Do not import evaluation APIs. Do not read or create OOS windows from this loop.

## Output Format

A quick run is summarized by:

```text
score: <objective score or blank>
gates: <gate=pass/fail,...>
trade_count: <integer>
concentration: <0..1 or blank>
cost_stress: <number or blank>
complexity_count: <integer>
status: keep | discard | crash
elapsed_seconds: <float>
```

`score` is the configured Train robustness objective. Gates are binary and separate from the score.

## Logging Results

Append every attempted iteration to `results.tsv`. It is tab-separated, not comma-separated.

```text
commit	iteration	score	gates_passed	gate_flags	trade_count	concentration	cost_stress	complexity_count	status	stop_reason	elapsed_seconds	note
```

Use `status=keep` only when the candidate passes all gates and improves beyond the configured plateau threshold. Use `discard` for a valid but non-keepable attempt. Use `crash` for failed runs or invalid candidates.

## The Experiment Loop

Loop for the current thesis until a configured stop rule fires:

1. Read `protocol.toml`, `experiment.toml`, `strategy.py`, `rationale.md`, and recent `results.tsv`.
2. Establish or inspect the feasible baseline.
3. Make one simple change to express the thesis better.
4. If the change adds or materially changes a signal component, update `rationale.md` with mechanism, observable, and falsifier.
5. Run the Train quick run through the local `climb` command or an equivalent focused test helper.
6. Parse the objective score and gate flags.
7. Keep only if:
   ```text
   all_gates_pass AND score > best + max(eps, rho * max(1, abs(best)))
   ```
   where `eps = min_abs_improvement` and `rho = min_rel_improvement`.
8. Otherwise revert to the prior best kept candidate.
9. Append exactly one `results.tsv` row.
10. Stop when one fires:
    - `plateau_patience` consecutive completed non-improving attempts after a feasible baseline.
    - `max_iterations` completed attempts.
    - complexity cap exhausted.
    - no feasible baseline within `baseline_grace_iterations`.

At stop, hand Season the frozen Train survivor or say the thesis died on Train. A Train survivor is not a promotion signal; it is only a candidate for downstream OOS, paper, and small-live review.
