# quant_autoresearch

This is an experiment to have the LLM do quant strategy research.

## Setup

To set up a new strategy candidate, work with the user to:

1. **Understand the candidate**: read `strategy.py` and identify the strategy
   hypothesis before changing anything. Fine-tune and improve the strategy, but
   do not drift away from the overarching strategy hypothesis. Keep the file
   shaped like a normal `quant_strategies` strategy module. Review the strategy
   to ensure it is implemented correctly.
2. **Use the current worktree**: this workbench is intentionally run on the
   current branch unless the human explicitly asks for a new branch.
3. **Read the in-scope files**: The repo is small. Read these files for full
   context:
   - `README.md` — repository context.
   - `program.md` — these instructions.
   - `strategy.py` — the scratch strategy you modify.
   - `experiment.toml` — the experiment configuration you modify.
   - latest `results/` artifacts, if present.
   - `results.tsv`, if present.
4. **Check data and harness readiness**: the runner delegates execution to
   `quant_strategies` and may depend on `quant_data`. If either upstream system
   is missing data or fails independently of the strategy, document the
   limitation instead of mutating the strategy to hide it.
5. **Confirm and go**: confirm setup looks good.

Once setup is clear, kick off the experimentation.

## Experimentation

Each experiment evaluates one scratch strategy under the windows configured in
`experiment.toml`. You launch one deterministic attempt simply as:

```bash
conda run -n quant python runner.py --description "short attempt description"
```

Choose windows from a quant research perspective. You may change
`active_window_id`, edit configured `[[windows]]`, or run a configured
`--window-id` when there is a research reason: regime, sample quality,
holdout/stress check, or a falsifier. Do not cherry-pick windows just to rescue
the last score.

**What you CAN do:**

- Modify `strategy.py`.
- Modify `experiment.toml`.
- Add a package when the strategy genuinely needs it, but record the dependency
  in the project configuration before using it so the run is reproducible.
  Treat dependency changes as setup changes, not ordinary loop edits.

Editable during a research loop:

- `strategy.py`
- `experiment.toml`

Read-only during a research loop:

- `program.md`
- `runner.py`
- `scoring.py`
- `experiment_config.py`
- `README.md`
- `tests/`
- `results/`
- `results.tsv`

**What you CANNOT do:**

- Modify the evaluation harness: `runner.py`, `scoring.py`, or
  `experiment_config.py`.
- Modify generated artifacts in `results/` or `results.tsv`.
- Install an unrecorded package or rely on an ad hoc local environment.
- Add runner calls, file writes, subprocesses, network calls, or
  autonomous loops inside `strategy.py`.
- Set `decision_lag_minutes` to zero; decisions must be emitted after the
  as-of bar can be observed.

**The goal is simple: get the highest guarded score.** The score is the guarded
`net_return` produced by the harness, and it is valid only when the trade count
passes the configured sample gate. Higher is better.

Think like a quant researcher. The score is loop feedback only, not market
evidence. Loop feedback only. Do not blindly chase the last number. Use the
score to compare attempts, then use causal timing, trade count, costs, data
quality, fill assumptions, and overfit risk to decide what to try next.

**Simplicity criterion**: All else being equal, simpler is better. A small score
improvement that adds ugly complexity is not worth it. Conversely, removing
something and getting equal or better results is a great outcome. When
evaluating whether to keep a change, weigh the complexity cost against the
improvement magnitude.

**The first run**: Your very first run should always establish the baseline, so
run the current `strategy.py` and `experiment.toml` as is.

## Output format

Once the runner finishes it prints a JSON summary like this:

```json
{
  "attempt": 1,
  "decision": "keep",
  "remaining_attempts": 0,
  "result_dir": "results/attempt_0001_example",
  "score": 0.0123,
  "status": "active"
}
```

Use the printed `result_dir` to inspect the attempt artifacts:

```bash
cat results/session_state.json
cat results.tsv
cat results/<attempt>/score.json
cat results/<attempt>/summary.json
cat results/<attempt>/evidence.json
```

## Logging results

The runner appends results to `results.tsv` automatically. Do not hand-edit this
file during the research loop.

The ledger records attempt identity, evaluated window, score/trade feedback,
status, and the short description. The exact schema is owned by the runner.

## Evidence review

Before changing the strategy after any run, inspect the latest artifacts and
write down the research reason for the next attempt:

- hypothesis and economic rationale
- causal timing and `as_of_time` assumptions
- falsifier
- guarded score movement
- raw net return, gross return, costs, and failed gates
- trade count and sample quality
- fill assumptions and data quality
- overfit risk and whether the change adds unjustified complexity

If an attempt fails, attribute the root source before changing anything:

- `strategy_error`
- `config_error`
- `quant_strategies_error`
- `quant_data_error`
- `environment_error`

If the error is not from `strategy.py`, document the limitation instead of
mutating the strategy to work around it. Capture useful feedback for
`quant_strategies` or `quant_data` when those upstream systems are the source.

## The experiment loop

The experiment runs in the current worktree.

LOOP UNTIL THE HARNESS SAYS THE SESSION IS EXHAUSTED:

1. Look at the git state: the current branch and commit we're on.
2. Review the latest `results/` artifacts and `results.tsv`.
3. Tune `strategy.py` or `experiment.toml` with one focused experimental idea.
4. git commit the focused research change.
5. Run the experiment:
   `conda run -n quant python runner.py --description "short attempt description"`.
6. Read the JSON summary, `score.json`, `summary.json`, and `evidence.json`.
7. The runner records the results in `results.tsv`; leave it untracked by git.
8. If the runner reports `keep`, advance from that commit.
9. If the runner reports `discard`, restore `strategy.py` and
   `experiment.toml` to the previous kept commit before designing the next
   change. Keep generated results as the research record.

The idea is that you are an autonomous quant researcher trying things out. If
they work, keep. If they don't, discard. You are advancing the strategy only
when the guarded evidence improves or when an equal result is materially
simpler.

**Crashes**: If a run crashes because of a typo, missing import, malformed
config, or other local issue, fix it if it is clearly from `strategy.py` or
`experiment.toml`. If the idea itself is fundamentally broken, log and move on.
If the failure is from `quant_strategies`, `quant_data`, or the environment,
document the limitation and do not contort the strategy around the upstream
failure.

**NEVER EARLY STOP**: Once the experiment loop has begun, do not pause to ask
the human whether you should continue while the harness still reports remaining
session capacity. Do not ask "should I keep going?" or "is this a good stopping
point?". If you run out of ideas, think harder: re-read the in-scope files,
study the latest artifacts, combine previous near-misses, simplify accidental
complexity, or try a more radical but causal quant hypothesis. The loop runs
until the harness says the session is exhausted or the human interrupts you.
