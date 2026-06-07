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

- **Public preloaded-row quick-run API for cached Train loops.**
  - *Idea / what it unlocks:* load a Train window once, keep normalized rows in memory, and run many strategy variants without reloading data every iteration.
  - *Missing upstream capability:* `quant_strategies.runner.run_config` accepts a config path and loads rows internally. It does not expose a public parameter for preloaded normalized rows.
  - *Why the current loop cannot test it faithfully today:* importing engine internals would create a private execution contract. The clean loop therefore uses public quick-run configs, which may reload data per attempt.
  - *Validation it would unlock:* Karpathy-style high-throughput Train iteration while preserving the public `quant_strategies` strategy contract and causal replay behavior.
