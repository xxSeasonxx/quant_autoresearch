# Harness TODO

Live backlog for loop and harness design gaps found while running Train. Use this file
only for changes to this repo's own harness (`loop.py`, `protocol.py`, `gates.py`,
`objective.py`, `onboarding.py`, `results_log.py`) and its operator ergonomics. Upstream
data and engine limits belong in `UPSTREAM_LIMITATIONS_TODO.md`; development chronology
belongs in `HISTORY.md`.

Each item states the problem, why it matters, and what a fix would look like.

## Open Items

### The attempt-start param delta anchors only on the score-best row

- **Problem:** `param_delta_vs_best` compares the working params against the frozen best-by-score
  survivor. When research is deliberately maintaining a second candidate — a configuration that
  loses on the objective but wins on evidence quality, drawdown, or trade count — every attempt
  exploring that candidate's neighbourhood reports an extra delta by construction. The signal that
  means "you left a lever on by accident" becomes indistinguishable from "you are mapping the other
  candidate".
- **Why it matters:** the delta line exists to make unintended parameter carry-over visible, and it
  earns its keep (it caught a real substring-edit accident within one attempt). Diluting it with
  expected multi-delta rows trains the reader to skim it, which is exactly how the failure it
  guards against went unnoticed for 18 attempts before.
- **What a fix looks like:** let the attempt name its intended base — an optional
  `--base <run_id>` on `climb` that anchors the delta on that row instead of the score-best one,
  defaulting to current behaviour. The printed line then reads as "one intended lever" for
  second-candidate work, and any additional delta is a genuine warning again. Recording the
  declared base in the ledger row would also make the comparison the attempt intended explicit
  rather than inferred.

### No supported way to extend a stopped lifecycle's iteration budget

- **Problem:** raising `max_iterations` to continue an active thesis is blocked by two
  independent guards, and the only way through is to hand-edit generated state.
  `_ensure_active_thesis_lock` refuses when `protocol_sha256` no longer matches
  `.autoresearch/thesis_lock.json` ("active thesis protocol changed"), and
  `_ensure_can_attempt` refuses when the last ledger row reads `continuation = terminal`.
  So extending a budget currently requires editing the thesis lock's `protocol_sha256`
  **and** rewriting the last row's `continuation` / `stop_reason` in `results.tsv` — the
  canonical ledger the harness otherwise treats as append-only and operator-forbidden.
- **Why it matters:** the guards exist to stop research assumptions drifting mid-lifecycle,
  which is right. But `max_iterations` is a **stop rule, not a research assumption**: it does
  not change the window, costs, fills, capacity model, leverage budget, objective, or gates,
  so it cannot make attempts less comparable. Conflating the two forces the operator to either
  fight the harness by editing generated state, or reset the lifecycle and lose one continuous
  ledger — splitting one research narrative across archives and restarting the attempt
  numbering, which is exactly what the ledger exists to prevent. The current workaround also
  teaches the operator to hand-edit `results.tsv`, which is a far worse habit than the problem
  it solves.
- **What a fix looks like:** a first-class `extend` path — e.g.
  `python -m loop extend --max-iterations N --confirm` — that (a) permits changes confined to
  `[loop]` stop-rule fields while still refusing any change to data, costs, fills, capacity,
  leverage, objective, or gates; (b) rebinds `protocol_sha256` in the lock as part of that
  operation; (c) recomputes the trailing row's derived `continuation` / `stop_reason` through
  `_stop_reason_after_attempt` under the new budget rather than leaving the operator to edit
  them; and (d) records the extension so the ledger shows the budget changed and when.
  Partition `protocol.toml` for the lock's purposes into research-identity fields (frozen for
  the lifecycle) and stop-rule fields (extendable under an explicit, recorded operation).
- **Distinguish from a reseed:** changing the universe, notional, leverage budget, risk budget,
  objective, or any gate stays a reseed and must still require a new lifecycle. Only the
  iteration budget and its dependent patience/grace fields belong in `extend`.
- **Interim workaround, and why it is unsafe to leave as the answer:** edit the lock's
  `protocol_sha256` to the new protocol hash and recompute the trailing row's two derived stop
  fields by hand. Derived fields are legitimate to recompute — they are budget-dependent
  functions, not measurements — but doing it manually puts an operator's editor inside the
  canonical evidence file with no record that it happened.
