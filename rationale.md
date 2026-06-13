# Rationale

Working thesis log for the active run. It currently holds the neutral template,
not a researched thesis. When Season seeds a real thesis, replace the Working
Thesis and Signal Components below so they match `strategy.py`.

## Working Thesis

- **Mechanism:** none claimed. The template holds a long weight-of-NAV target
  while price trends up and flattens otherwise, only to exercise the target-book
  contract end to end.
- **Observable:** per-symbol close and its `available_at`, compared across
  `lookback_bars`.
- **Falsifier:** as a neutral placeholder it should show no durable edge; a real
  thesis replaces it before any tuning.
- **First failure mode to watch:** sparse or one-regime evidence, since a plain
  trend rule rarely clears the subwindow PSR floor.

## Signal Components

### Component: trend_direction

Long while the latest available close exceeds the close `lookback_bars` bars
earlier; flat otherwise. Targets are standing and emitted only on change.
