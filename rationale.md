# Rationale

## Thesis

Crowded crypto-perpetual positioning mean-reverts. Persistent same-sign realized
funding pressure identifies the paying side, and an idiosyncratic price extension
in the same direction identifies a crowded move. The book fades that move and
exits at a fixed intraday horizon.

The mechanism is two-sided: negative funding plus a downside extension marks a
crowded short to fade long; positive funding plus an upside extension marks a
crowded long to fade short. Side restrictions are strategy variants, not changes
to the invariant thesis.

## Observable

- Dataset: `crypto_perp_1min_with_funding`.
- Fields: `close`, `volume`, `available_at`, `funding_timestamp`, `funding_rate`,
  and `has_funding_event`.
- Signal: the sign and persistence of the latest realized funding settlements,
  paired with a completed-close extension versus the current cross-section.
- Causality: a row is usable only when `available_at <= decision_time`. Entry and
  exit ramps are fixed minute schedules created when the signal is observed; they
  do not inspect future rows to choose decision timestamps.

## Universe

The protocol freezes 14 return-blind eligible crypto-perp names:
`ADA-PERP`, `AVAX-PERP`, `BNB-PERP`, `BTC-PERP`, `DOGE-PERP`, `DOT-PERP`,
`ETH-PERP`, `LINK-PERP`, `NEAR-PERP`, `PEPE-PERP`, `SOL-PERP`, `SUI-PERP`,
`UNI-PERP`, and `XRP-PERP`.

Eligibility requires derived-funding readiness, full-window coverage, and enough
median daily dollar volume for the frozen capacity model. The strategy changes
active breadth through ranking, `top_n`, and thresholds; it does not prune the
protocol universe from realized returns.

## Signal Components

### Component: Funding crowding

Sum the latest `funding_lookback_events` realized settlements and require
same-sign persistence. Negative pressure supports a long reversal candidate;
positive pressure supports a short reversal candidate.

### Component: Idiosyncratic price extension

Measure the completed-close return over `return_lookback_minutes` against the
cross-section median. The current candidate uses raw basis-point dislocation and
a recent-return guard.

### Component: Capacity-aware conviction allocation

`capacity_dislocation` weights selected names by idiosyncratic dislocation and
causal signal-bar dollar volume. This preserves allocation as strategy-owned shape
while favoring signals the upstream capacity model can size.

## Baseline Configuration

The next baseline starts from the current `experiment.toml`:

- five-event funding memory with three-event same-sign persistence;
- 120-minute price extension, median cross-section reference, and a 2.5 bps raw
  idiosyncratic threshold;
- long candidates enabled and short candidates disabled for the first test;
- top-five selection with at least five cross-sectional candidates;
- dislocation power 4 and liquidity power 2;
- 240-minute cadence, 720-minute hold, 30-minute entry ramp, and 60-minute exit
  ramp.

The run score is realistic-cost full-window total return. The fixed 2-SE
`train_strength` hurdle is a development gate, not statistical proof or a
best-of-N correction. Causality evidence is bounded to 12 micro probes and 30
seconds by the frozen protocol; a timeout is an evidence outcome, not thesis
evidence.

## Falsifier

The thesis fails if causal Train evidence cannot clear the configured gates, if
full-window return collapses after realistic costs or capacity impact, if
cost-stress retention fails, or if returns depend on one symbol or one time slice.
The current long-only restriction must earn positive economic return before the
short side is reconsidered.

## Assumptions

- Funding fields are realized settlement events, not forecasts.
- A bar close and volume are used only after their `available_at` time.
- Target magnitude is relative allocation shape; upstream risk-budget sizing owns
  deployed scale.
- The frozen universe was selected without using realized Train returns.

## First Failure Mode To Watch

Whether the long-only baseline on the 14-name universe clears `train_strength`
while producing positive realistic-cost full-window total return. If it fails,
inspect per-symbol economics, cost-stress retention, duty cycle, effective symbol
count, and the weakest subwindow before choosing one thesis-driven edit.

## Lever Enumeration

- Baseline pending under the current score, schema, strategy schedule, universe,
  and causality budget.
