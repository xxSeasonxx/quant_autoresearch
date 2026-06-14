# Rationale

Working thesis log for the active run: the crypto-perp funding-crowding reversal
survivor, brought in from downstream research to re-baseline on the bench.

## Working Thesis

- **Mechanism:** recent same-direction perpetual funding pressure plus price
  extension marks crowded positioning that mean-reverts over the configured
  holding window. Repeated same-symbol signals are state updates, not independent
  tickets, so new same-symbol entries are suppressed until the active window exits.
- **Observable:** per-symbol close, funding rate and funding timestamp, the
  funding-event flag, and each row's `available_at`.
- **Falsifier:** if same-symbol state suppression removes the edge or leaves too
  few trades for the sample gate, the result was an overlapping-ticket artifact,
  not a tradable rebalance rule.
- **First failure mode to watch:** single-symbol concentration and sparse
  subwindow coverage — the downstream run showed foundation concentration near 1.0
  and a thin weakest subwindow.

## Signal Components

### Component: funding_pressure

Summed recent same-direction funding over the last `funding_lookback_events`,
with a stronger threshold required during market-wide selloff regimes.

### Component: return_extension

Price extension over `return_lookback_minutes` (idiosyncratic vs the cross-section
mean) that triggers the mean-reversion entry.

### Component: crowding_state

Stateful same-symbol suppression and per-symbol hold horizons that treat repeated
signals as rebalances of a standing target rather than new tickets.
