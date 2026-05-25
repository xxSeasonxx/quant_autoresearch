# Upstream Limitations TODO

This file is only for research ideas that are worth testing but are blocked by
upstream data, engine, or harness capabilities. Do not use it for ordinary
strategy parameters, failed attempts, or generated run results.

Each note should include:

- the strategy idea or hypothesis
- the missing upstream capability
- why the current harness cannot test it faithfully
- the validation it would unlock

## Open Items

### Stop-loss and take-profit exits

- Idea: test stop-loss, take-profit, and possibly trailing-stop exits for
  crowding-reversal trades.
- Missing capability: the upstream engine currently exits from `hold_bars`
  only, so it cannot scan post-entry bars for stop or take-profit triggers.
- Current limitation: approximating stop/take-profit behavior inside
  `strategy.py` would not change engine fills and could create misleading
  research evidence.
- Unlocks: compare the current best conditional time exit against real
  threshold-based exits with explicit `exit_reason` attribution.
