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

- **Separate Train decision/scoring window from execution exit coverage.**
  - *Idea / what it unlocks:* run sparse strategies on an exact Train decision window while still allowing the engine to resolve exits that occur after the decision window ends.
  - *Missing upstream capability:* `quant_strategies.runner.run_config` has one data window that currently acts as the load window, strategy input window, engine execution window, and evidence window. It does not expose an execution buffer such as `load_end = score_end + max_hold_bars`, nor a distinct decision/scoring window that filters eligible entries while preserving later bars for exits.
  - *Why the current loop cannot test it faithfully today:* the researched funding-crowding strategy previously used `require_exit_horizon = true`, which checked future row availability in strategy code before emitting. The active Train baseline disables that non-causal gate so emitted replay can pass. The remaining limitation is that near-window-end trades can still be rejected by the engine with errors such as `exit fill is outside available bars`; that horizon rule belongs in runner/engine window handling, not in signal generation.
  - *Validation it would unlock:* a causal baseline where strategy decisions are generated from as-of-visible rows, entries are scored only inside the Train decision window, exits are resolved from a declared post-window buffer, and diagnostics clearly distinguish decision-window trades from buffer-only exit data.

- **Causality policy controls for Train quick runs and dedicated audits.**
  - *Idea / what it unlocks:* use emitted-decision replay for fast Train iteration, and reserve strict no-emission replay for survivor audits or smaller explicit probes.
  - *Missing upstream capability:* partially addressed upstream by adding `output.causality_check` and `strict_probe_limit`, plus boundary-scoped replay payload checks. Remaining upstream work is to make the recommended Train/audit split durable in docs and runner semantics, and to ensure strict replay stays bounded and clearly marked incomplete when capped.
  - *Why the current loop cannot test it faithfully today:* unbounded strict row-grid replay is too expensive for large minute panels. Emitted replay is now fast enough, but it still cannot pass strategies that encode future exit-horizon checks in signal logic; that residual issue is the execution-window boundary above, not alpha logic.
  - *Validation it would unlock:* quick-run evidence that can honestly say `causality_check = "emitted"` during Train iteration, while strict replay evidence can later say passed, capped, skipped, or incomplete without blocking ordinary baseline learning.
