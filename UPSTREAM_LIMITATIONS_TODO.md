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
