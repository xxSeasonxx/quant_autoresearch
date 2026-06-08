# Causality Policy Design

Date: 2026-06-08

## Purpose

Restore usable Train-loop iteration for large minute-bar panels without weakening
the research evidence contract. The fix must address the root cause, not add a
local bypass around `quant_strategies.runner.run_config`.

## Context

`quant_autoresearch` runs each attempt through the public
`quant_strategies.runner.run_config` API. The active crypto perpetual funding
protocol uses a two-year, five-symbol, minute-bar Train panel with sparse
four-hour decision cadence. The upstream runner currently performs strict
hidden-lookahead replay on every public quick run by deriving row-grid
boundaries from every symbol timestamp, so the replay probe count scales with
minute rows instead of emitted decisions.

A one-week timing probe showed normal data load plus one full strategy
generation completing in about six seconds, producing 50,400 rows and 38
decisions. The same window derives 10,080 strict replay boundaries. This points
to strict replay, not ordinary strategy generation, as the dominant runtime
source for large windows.

There is also a separate strategy-level causality defect: the current strategy's
`require_exit_horizon` filter checks future sample availability before emitting
a decision. That is not a market observable. With only that parameter disabled
in memory, emitted replay passed for the one-week profile. A runner policy
change alone would make iteration faster but would not make this candidate
causal.

## Design

### Strategy Boundary

Strategy code must emit decisions using only observations available at or before
the decision's `as_of_time`. Sample-tail feasibility, such as whether enough
future bars exist to complete a hold horizon, must not suppress decisions inside
`generate_decisions`.

The immediate strategy fix is to remove future-horizon filtering from signal
generation. Exit feasibility should be handled by runner data readiness,
evaluation semantics, or clear evaluation failure/skip behavior after decisions
are emitted.

### Runner Causality Policy

`quant_strategies.runner.run_config` should expose causality policy through the
public run config instead of hard-coding strict replay. The initial public shape
should be small:

```toml
[output]
causality_check = "emitted"
strict_probe_limit = 10000
```

Supported modes:

- `off`: no replay check; only acceptable for explicit profiling or debugging,
  and artifacts must mark causality as unverified.
- `emitted`: verify deterministic full replay and emitted-decision replay.
  This is the default Train iteration mode for large sparse strategies.
- `strict`: verify deterministic full replay, emitted-decision replay, and
  strict no-emission replay. If `strict_probe_limit` is set and the grid exceeds
  it, strict evidence is capped or incomplete rather than silently treated as
  passed.

The runner result and artifacts must distinguish the evidence dimensions:

- deterministic replay verified
- emitted replay verified
- strict suppression replay verified
- strict replay skipped, capped, failed, or incomplete

Quick-run assessment can complete under emitted replay, but promotion or final
survivor language must not imply strict suppression evidence unless strict replay
actually completed.

### Autoresearch Boundary

`quant_autoresearch` should continue using the public `run_config` API. It
should materialize the configured causality policy into generated quick-run TOML
instead of importing private runner internals or monkeypatching replay.

Train iteration should default to `causality_check = "emitted"` once upstream
supports it. Final survivor handoff should either run a strict audit or clearly
mark strict suppression replay as unverified in the handoff artifacts.

### Evidence Semantics

Train-loop evidence is allowed to be usable for iteration when emitted replay
passes and strict suppression replay is skipped or capped, provided artifacts
say that plainly. This is development evidence only. It is not OOS, paper,
small-live, or deployment evidence.

Strict replay remains valuable as a dedicated audit because it can catch
strategies that peek forward to suppress losing trades. It is not required on
every inner-loop Train attempt when its cost makes iteration unusable.

## Testing

Focused verification should cover:

- Strategy emitted replay passes after removing future-horizon suppression from
  signal generation.
- Runner config accepts `off`, `emitted`, and `strict`, and rejects invalid modes.
- `run_config` forwards the selected mode into `check_hidden_lookahead`.
- Artifacts expose deterministic, emitted, and strict evidence flags separately.
- Emitted Train runs can complete without strict replay verification.
- Strict survivor/audit runs still fail on suppression-lookahead strategies.
- Capped strict replay records incomplete strict evidence instead of a false pass.

## Non-Goals

- Do not replace `run_config` in `quant_autoresearch`.
- Do not import private `quant_strategies` engine or execution internals from the
  Train loop.
- Do not use smaller Train windows as the root fix, though smaller smoke windows
  remain useful for debugging.
- Do not treat emitted-only Train evidence as promotion or deployment evidence.
