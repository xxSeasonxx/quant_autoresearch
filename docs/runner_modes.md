# Runner Modes And Windows

This file explains what `runner.py` does for each mode and which windows each
mode uses from `experiment.toml`.

## Short Version

Use this mental model:

```text
explore   = run one primary window
promote   = run primary window, then a robustness screen if primary scores
confirm   = run a configured bundle of windows and combine them
window-id = run exactly one requested window
```

For the ordinary research loop, start with `--explore`. Use `--promote` only
for serious candidates. Use `--confirm` or `--window-id` when you deliberately
want extra diagnostics.

## Important Terms

`experiment.toml` defines named windows:

```toml
[[windows]]
id = "some_window_id"
start = "2025-01-01"
end = "2025-06-29"
```

Window names such as `validation_2025_h1` are just IDs. They are not a separate
runner mode.

The runner then chooses windows from these config fields:

```toml
[research]
primary_window_id = "..."
confirmation_window_ids = [...]

[promotion]
recent_window_ids = [...]
rotating_probe_window_ids = [...]
```

## Explore

Command:

```bash
conda run -n quant python runner.py --explore --description "short description"
```

Uses:

```text
research.primary_window_id
```

Decision tree:

```text
run primary_window_id
  |
  v
write score.json / summary.json / evidence.json
  |
  v
record one ledger row with run_kind = explore
```

Explore is the cheap first screen. It answers:

```text
Does this idea work at all on the primary research window?
```

## Promote

Command:

```bash
conda run -n quant python runner.py --promote --description "short description"
```

Required config:

```toml
[promotion]
enabled = true
```

First uses:

```text
research.primary_window_id
```

If the primary result is not scorable, promotion stops there:

```text
run primary_window_id
  |
  +-- primary not scored
        -> no promotion screen
        -> record one ledger row with run_kind = promote
```

If the primary result is scorable, promotion runs the full promotion screen:

```text
run primary_window_id
  |
  +-- primary scored
        |
        v
        run promotion.recent_window_ids
        run primary_window_id again with promotion cost-stress costs
        run one rotating probe from promotion.rotating_probe_window_ids
        |
        v
        write promotion_score.json / promotion_summary.json / trade_attribution.json
        record one ledger row with run_kind = promotion
```

Promotion uses these window groups:

```text
1. research.primary_window_id
2. promotion.recent_window_ids
3. research.primary_window_id again with stressed costs
4. one window from promotion.rotating_probe_window_ids
```

If `primary_window_id` is also listed in `promotion.recent_window_ids`, the
promotion screen reuses the already-run primary result instead of rerunning that
same recent window.

Promotion answers:

```text
Is this candidate strong enough to preserve for the next review step?
```

## Confirm

Command:

```bash
conda run -n quant python runner.py --confirm --description "short description"
```

Uses:

```text
research.confirmation_window_ids
```

Decision tree:

```text
run every window in confirmation_window_ids
  |
  v
combine window scores into candidate_score.json
write candidate_summary.json / trade_attribution.json
  |
  v
record one ledger row with run_kind = confirm
```

Confirm answers:

```text
Does this candidate hold up across the configured confirmation bundle?
```

This is optional in the simple loop. It is useful when you want a multi-window
diagnostic without running the full promotion screen.

## Window Diagnostic

Command:

```bash
conda run -n quant python runner.py --window-id WINDOW_ID --description "short description"
```

Uses:

```text
the exact WINDOW_ID passed on the command line
```

Decision tree:

```text
run WINDOW_ID
  |
  v
write score.json / summary.json / evidence.json
  |
  v
record one ledger row with run_kind = diagnostic
```

Window diagnostic answers:

```text
What happens on this one specific configured window?
```

## Which Mode Should I Use?

Use `--explore` when testing a normal idea.

Use `--promote` when an explored candidate looks serious enough for a more
expensive robustness screen.

Use `--confirm` when you want a multi-window bundle check but not the full
promotion screen.

Use `--window-id WINDOW_ID` when you want to inspect one specific regime or
holdout window.

## Current Placeholder State

After the bench is reset, `experiment.toml` is intentionally neutral. It uses a
placeholder strategy and placeholder window. Before a real campaign, replace the
placeholder strategy, params, symbols, and windows with the actual candidate
setup.
