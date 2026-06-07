# Rationale

## Working Thesis

- Mechanism: short-horizon return persistence can continue after the latest available bar.
- Observable: close-to-close return over `lookback_bars`.
- Falsifier: after-cost Train robustness fails to clear the configured trade floor and gate thresholds before parameter tuning.
- Assumptions to watch:
  - decisions use only available rows
  - costs and fills come from the protocol

## Signal Components

### Component: baseline momentum

- Mechanism: recent close-to-close strength expresses the working thesis.
- Observable: close return over `lookback_bars`.
- Falsifier: the component produces too few trades or fails after-cost robustness gates.

## Variants Tried

Record each run here after reviewing diagnostics.

### Variant: baseline

- Changed: initial simple momentum expression.
- Thesis connection: uses the same return-persistence mechanism and close-to-close observable.
- Diagnostic motivation: establish baseline behavior.
- Next falsifier: fails trade floor, concentration, cost-stress, or worst-subwindow Train robustness.
