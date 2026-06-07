# Signal Rationale

## Component: baseline momentum

- Mechanism: short-horizon return persistence can continue after the latest available bar.
- Observable: close-to-close return over `lookback_bars`.
- Falsifier: after-cost Train robustness fails to clear the configured trade floor and gate thresholds before parameter tuning.
