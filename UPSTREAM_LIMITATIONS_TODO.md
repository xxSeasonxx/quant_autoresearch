# Upstream Limitations TODO

Use this file only for promising research or loop capabilities blocked by upstream
data, engine, or public API limits. Do not use it for ordinary strategy params,
failed attempts, or generated run results.

## Open Items

### Discrete instrument increments

- **Unlocks:** executable sizing for venues whose instruments require quantity
  steps, lot sizes, price ticks, or contract multipliers.
- **Missing upstream capability:** canonical instrument metadata and account-
  numeraire conversion for physical order quantity and price increments.
- **Why the loop cannot test it faithfully:** minimum order notional and fixed
  order cost are priced, but a notional that passes those checks may still be
  unrepresentable as a lawful venue quantity or price.
- **Validation it would unlock:** exact order construction after the current
  notional-level feasibility screen.

Do not approximate these increments from remembered venue rules. Add them only
after a lawfully accessible venue exposes reliable, current instrument metadata.
