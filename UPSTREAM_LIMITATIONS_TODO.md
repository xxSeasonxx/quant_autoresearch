# Upstream Limitations TODO

Use this file only for promising research or loop capabilities blocked by upstream
data, engine, or public API limits. Do not use it for ordinary strategy params,
failed attempts, or generated run results.

Each note should include:

- the idea or workflow it would unlock
- the missing upstream capability
- why the current loop cannot test it faithfully
- the validation it would unlock

## Open Items

### Volume in strategy bars, for volume-aware execution under an ADV cap

- **Unlocks:** participation-aware execution (VWAP-style, or any schedule that leans on
  high-volume minutes), which is the only honest way to relieve an ADV participation cap
  without slowing the signal. Without it, a capacity-bound book can only spread turnover
  blindly over time, which trades execution lag for participation relief and degrades any
  fast signal.
- **Missing upstream capability:** strategies appear to receive no traded volume on the bars
  they read, so a decision cannot condition size or timing on the liquidity actually
  available in that minute — while the capacity model scores the book against a 25% ADV cap
  measured on that same volume.
- **Why the loop cannot test it faithfully:** the strategy is scored against a participation
  constraint it cannot observe. Every capacity-relief lever available in-loop
  (`execution_bars`, `position_smoothing`, `signal_band`) is volume-blind, so a pinned ADV
  read cannot be distinguished from one a volume-aware schedule would relieve, and Train's
  capacity verdict is pessimistic by an unknown margin.
- **Validation it would unlock:** an honest deployable-scale ceiling, and therefore whether a
  capacity-bound edge needs a protocol-envelope change (notional, universe depth, ADV
  ceiling) or just better execution.
- **Verify first:** confirm against the `quant_data` and `quant_strategies` consumer docs
  which volume fields actually reach a strategy's bars and observation rows. This item is
  recorded from prior-lifecycle notes and has not been re-checked against those contracts; if
  volume is in fact available, the item is moot and the relief lever should simply be built.

### Autocorrelation-robust effective sample size for the Train-strength gate

- **Unlocks:** a Train-strength gate (`R - 2*SE >= 0`) whose standard error is
  honest for multi-hour, overlapping-hold strategies, so the one in-loop robustness
  gate cannot pass a materially weaker edge.
- **Missing upstream capability:** `effective_sample_size` is a lag-1
  autocorrelation adjustment capped to `[1, sample_count]`. For a book holding
  ~720-minute positions on a ~240-minute cadence, at-risk per-minute returns are
  positively autocorrelated across hundreds of lags, so a lag-1 adjustment leaves
  `n_eff` near `sample_count`, understating SE and overstating the t-stat. A
  block or Newey-West effective sample size, or a strength statistic anchored to
  independent closed trades, is needed.
- **Why the loop cannot test it faithfully:** SE is derived from upstream per-minute
  return moments and `effective_sample_size`; the harness cannot reconstruct an
  autocorrelation-robust `n_eff` from the emitted scalars, and dividing a per-minute
  mean by a closed-trade count is not statistically clean.
- **Validation it would unlock:** trustworthy in-sample strength screening before an
  edge is committed to downstream OOS.
- **Verify first:** measure the realized multi-lag autocorrelation of the at-risk NAV
  return series on a representative run; if autocorrelation is immaterial, this item
  is moot.
