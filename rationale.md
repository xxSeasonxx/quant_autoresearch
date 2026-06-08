# Rationale

## Working Thesis

- Mechanism: crowded perpetual positioning reflected by persistent same-direction funding and recent price extension mean-reverts after the funding pressure is observable.
- Observable: completed funding events plus completed close-to-close return extension on the fixed five-symbol crypto perp funding panel.
- Falsifier: stateful same-symbol suppression leaves too few trades, excessive symbol concentration, negative cost-stressed robustness, or a non-positive worst-subwindow Train score.
- Assumptions to watch:
  - funding timestamps are observable no later than the strategy as-of time
  - decisions use completed prior closes and protocol-controlled next-bar fills
  - the five-symbol universe is explicit protocol state, so evidence is about the strategy-universe combination
  - costs and fills come from `protocol.toml`, not from the researched source config

## Signal Components

### Component: funding pressure

- Mechanism: repeated positive or negative funding marks one-sided perp positioning.
- Observable: summed recent funding rates and same-sign funding event count.
- Falsifier: funding pressure does not survive after-cost subwindow robustness.

### Component: return extension

- Mechanism: same-direction price extension identifies crowded entries likely to reverse.
- Observable: completed close-to-close return over `return_lookback_minutes`, including idiosyncratic return filters.
- Falsifier: extension filters produce too few trades or concentrate returns in one symbol.

### Component: stateful rebalance suppression

- Mechanism: repeated same-symbol signals before the prior target exits are state updates, not independent trade tickets.
- Observable: symbol-level active window suppression through the configured hold horizon.
- Falsifier: suppressing overlapping same-symbol targets kills trade count or Train robustness.

## Variants Tried

### Variant: rank-01 baseline

- Changed: replaced the toy momentum baseline with the researched `crypto_perp_funding_crowding_reversal_stateful_rebalance` rank-01 strategy, switched the protocol data kind to the five-symbol crypto perp funding panel, and raised the param cap to 50.
- Thesis connection: uses the researched funding-crowding reversal mechanism with explicit stateful rebalance suppression.
- Diagnostic motivation: establish the local Train baseline under this workbench's costs, fills, gates, and 2024-2025 Train window.
- Next falsifier: fails trade floor, subwindow coverage, breadth, cost-stress, complexity, or non-positive worst-subwindow Train robustness.

### Variant: emitted-replay Train baseline

- Changed: set `require_exit_horizon = false` so strategy generation no longer
  suppresses signals based on future row availability. Train quick runs use the
  protocol-owned `causality_check = "emitted"` policy.
- Thesis connection: keeps the same funding-crowding and stateful suppression
  mechanism while removing sample-tail feasibility from signal logic.
- Diagnostic motivation: emitted replay failed when the strategy checked future
  exit coverage before emitting decisions; that was workflow plumbing, not alpha.
- Next falsifier: emitted replay passes but the engine rejects late-window exits,
  or the no-horizon candidate fails the configured Train gates.
