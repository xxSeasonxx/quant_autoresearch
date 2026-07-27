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
