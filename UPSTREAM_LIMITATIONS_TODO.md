# Upstream Limitations TODO

This file is only for research ideas that are worth testing but are blocked by
upstream data, engine, or harness capabilities. Do not use it for ordinary
strategy parameters, failed attempts, or generated run results.

Each note should include:

- the strategy idea or hypothesis
- the missing upstream capability
- why the current harness cannot test it faithfully
- the validation it would unlock

## Open Items

### FX triangular residual reversion: scalable executable quote evaluation

- **Strategy idea / hypothesis:** Broad one-minute FX triangular residual
  reversion should be tested on executable quote data across multiple USD-leg
  triangles, using residual closes only after they are observable and quote
  fills only after quotes are available.
- **Missing upstream capability:** `quant_strategies` needs an indexed
  evaluation path for large intraday universes, especially direct
  `(symbol, decision_time) -> bar_index` lookup instead of per-signal linear
  bar scans, and it should skip or pre-index funding scans for non-funding data
  such as FX. The runner also needs artifact controls that avoid writing
  multi-gigabyte `strategy_input_rows` / `engine_request` dumps before an
  expensive screen completes.
- **Why the current harness cannot test it faithfully:** The
  `forex_with_quotes` data path itself is correct for this strategy: quote
  fills call `load_fx_bars_with_quotes(..., require_quotes=True)` and the
  attempted 180-day primary window loaded 2,519,882 quote-qualified rows across
  14 FX pairs with full `available_at`, `quote_ingested_at`, and
  `joined_refreshed_at` coverage. However, the same run generated 46,136
  signals and then entered a CPU-bound engine loop. Sampling showed Python
  datetime comparisons inside the engine's linear decision-time lookup, while
  the aborted attempt also wrote a 679M `engine_request.json`, 694M input CSV,
  and 1.4G input JSONL. This makes the intended broad FX candidate too slow for
  the 100-attempt autoresearch loop unless the strategy is artificially
  narrowed or over-filtered to fit the harness.
- **Causal timing limitation:** `quant_data` exposes FX quote `available_at`
  and documents that quotes are available at `timestamp + 1 minute`, but the
  current evaluation engine indexes fills by bar `timestamp`. The workbench can
  approximate causality with `decision_lag_minutes = 1`, but exact
  quote-availability enforcement should live in the engine or runner contract.
- **Validation it would unlock:** Full-width residual-reversion screening over
  the outside-view FX triangle set, realistic quote fills, promotion cost
  stress, and guard-window comparison without reducing the universe or signal
  count merely to avoid evaluation runtime.
