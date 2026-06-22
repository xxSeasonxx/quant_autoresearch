# Rationale

## Thesis

Realized same-sign funding pressure and same-direction price extension can mark
crowded crypto perpetual positioning. The strategy trades the reversal after the
signal bar is observable and exits with explicit fixed-horizon flat targets.

## Observable

- Data: `crypto_perp_1min_with_funding`.
- Fields: `close`, `available_at`, `funding_timestamp`, `funding_rate`, and
  `has_funding_event`.
- Signal: the sum of the latest realized funding events, same-sign funding-event
  persistence, and price extension versus a completed prior close.
- Cross-section: rank candidates by combined funding pressure and idiosyncratic
  return extension versus the current five-symbol universe.

## Signal Components

### Component: Funding pressure
Same-sign realized funding summed over the last `funding_lookback_events`
settlements, gated by `min_same_sign_funding_events` persistence and
`min_abs_funding_bps` / `min_latest_abs_funding_bps` magnitude. Crowded carry pays
one side; the book takes the other.

### Component: Idiosyncratic price extension
Signal-close return versus a completed prior close (`return_lookback_minutes`),
measured against the cross-section mean (`min_idiosyncratic_return_bps`), with a
recent-return guard (`max_recent_same_direction_return_bps`) against
still-accelerating moves. Same-direction extension marks the crowded move to
reverse.

## Falsifier

The thesis should die if micro-causal Train runs cannot produce enough closed
trades across subwindows, if returns collapse after costs and capacity impact, or
if the edge depends on one symbol or one time slice.

## Assumptions

- Funding fields are realized settlement events, not forecasts.
- A bar's close is used only after `available_at`.
- `BTC-PERP`, `ETH-PERP`, `DOGE-PERP`, `ADA-PERP`, and `LINK-PERP` are the
  explicit setup universe for this reseed.
- Target magnitude is shape-only: each active symbol receives an equal slice of
  gross book shape, and upstream risk-budget sizing owns deployed scale.

## Editable Params

- Funding pressure: `funding_lookback_events`, `min_abs_funding_bps`,
  `min_same_sign_funding_events`, `min_latest_abs_funding_bps`.
- Price extension: `return_lookback_minutes`, `min_abs_return_bps`,
  `recent_return_lookback_minutes`, `max_recent_same_direction_return_bps`,
  `min_idiosyncratic_return_bps`.
- Rebalance and horizon: `decision_interval_minutes`, `decision_lag_minutes`,
  `top_n`, `long_hold_minutes`, and `short_hold_minutes`.

## First Failure Mode To Watch

The likely first failure is the deflated money floor, not breadth. At 15% target
volatility with gross capped at 1.0, a five-name crypto-perp book is leverage-
bound, so realized volatility runs below target and the worst-subwindow
annualized-return lower bound (2.8-SE deflated) must clear 10% on a small
deployed scale. Expect the baseline to fail the return gate before the
trade-count gates. If it instead fails on sparse trades or subwindow breadth,
inspect trade timing before changing thresholds. A micro-causality timeout is a
compute limit, not thesis evidence.

## Baseline Diagnostic

The first feasible baseline is a `discard`: causality, trade-floor, subwindow
coverage, evidence, path-risk, and complexity gates pass; money_floor,
cost_stress_retention, and breadth fail. 1307 closed trades, 172+ per subwindow.

Three findings drive the result:

- Sub-cost edge: net per trade ≈ 0.03 bps, profit factor ≈ 1.05, full-train
  annualized return ≈ 0.8%. Under the 2x cost stress the edge turns negative
  (retention -0.62). The funding-crowding reversal, as expressed, barely clears
  realized costs.
- Capacity binds on per-bar participation, not ADV: max bar participation ≈ 0.50
  (at the cap) while ADV participation ≈ 0.12 (well under 0.25). Bursty rebalance
  into single decision-cadence minutes pins deployable size, so the book deploys
  ≈ 3.2% of notional at ≈ 0.94% realized volatility versus the 15% target.
- With feasible volatility capped near 0.94%, the deployed annualized return is
  bounded far below the 10% money floor for any signal shape: clearing it would
  require an implausible Sharpe. The money floor is structurally unreachable
  under the frozen capacity model at this notional, universe, and cadence.

Breadth fails because selection often collapses to one eligible name
(concentration 1.0), so the equal-slice book is not actually diversified.
