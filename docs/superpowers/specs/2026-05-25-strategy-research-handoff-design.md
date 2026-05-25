# Strategy Research Handoff Design

## Purpose

Create a repeatable closeout process for a finished `quant_autoresearch`
strategy campaign. The process transfers reproducible research candidates into
`quant_strategies/researched/`, preserves enough artifacts to rerun and audit
the result, then resets this workbench for the next strategy without keeping
strategy-specific bias.

This process does not market-validate a strategy. It promotes a bench-researched
candidate into a separate validation queue.

## Lifecycle

`quant_strategies` should use three lifecycle folders:

```text
untested/     raw or actively forming strategy ideas
researched/   bench-promoted candidates frozen for separate validation
tested/       strategies that passed the future validation process
```

The handoff process writes only to `researched/`. Moving a strategy to `tested/`
belongs to the separate validation process.

## Researched Package

Each completed strategy gets a self-contained package:

```text
researched/<strategy_id>/
  README.md
  HANDOFF.md
  manifest.json

  selection/
    handoff_ranking.json
    scoring_method.md

  families/
    family_01_primary_<slug>/
      README.md
      variants/
        rank_01/
          strategy.py
          config.toml
          evidence/
        ...
    family_02_secondary_<slug>/
    family_03_exploratory_<slug>/

  notes/
    llm_research_summary.md
    upstream_limitations.md
```

Every retained concrete variant is self-contained: it has its own frozen
`strategy.py`, frozen runnable `config.toml`, and evidence subset. If variants
share identical strategy code, the same snapshot is still copied into each
variant folder; `manifest.json` records matching code hashes.

Configs must point at their local frozen strategy file, for example:

```toml
strategy_path = "researched/<strategy_id>/families/family_01_primary_<slug>/variants/rank_01/strategy.py"
```

## Retention Rules

The process keeps exactly three distinct logic families. A logic family is a
research idea, not a numeric parameter tweak.

Examples:

- Same logic: `long_hold_bars = 720` vs `960`.
- Same logic: `take_profit_bps = 300` vs `500`.
- Different logic: time-only exits vs fixed take-profit/stop-loss exits.
- Different logic: funding plus return tail entry vs idiosyncratic-return
  filtered entry.
- Different logic: both-side strategy vs short-only or long-only decomposition.

For each selected family, keep up to five concrete variants. If fewer than five
exist, keep what exists and record the reason. Weak families are still retained
when they rank in the top three, but they must be labelled clearly as primary,
secondary, exploratory, fragile, or negative-control evidence.

Do not copy all generated artifacts by default. Keep enough to reproduce and
audit:

- frozen strategy code,
- frozen config,
- promotion score/summary,
- relevant window scores,
- trade attribution for the best variant in each family,
- session state,
- deterministic ranking output,
- LLM summary and upstream limitations notes.

Large artifacts such as full signals files are optional and should be retained
only when they are required for auditability and cannot be reproduced cheaply
from the frozen config and source data.

## Deterministic Ranking

The skill must not decide rankings. A deterministic ranker computes family and
variant selections from artifacts.

Proposed tool:

```text
tools/research_handoff_rank.py
```

Inputs:

- `results/<campaign>/session_state.json`
- root-level scored attempt artifacts:
  `results/<campaign>/*/attempt_metadata.json` and
  `results/<campaign>/*/score.json`
- `results/<campaign>/promotion_*/promotion_summary.json`
- `results/<campaign>/promotion_*/promotion_score.json`
- `results/<campaign>/.generated/*.toml`
- optional promotion window `score.json` files
- optional `trade_attribution.json`

Output:

```text
handoff_ranking.json
```

The output contains all concrete variants, deterministic `logic_family_id`,
blended score, selected three families, retained variants per family, and
machine-readable penalties/reasons.

Root-level scored attempt artifacts are required because the top three logic
families may not all have been promoted. Promotion artifacts enrich a variant
when present, but they are not the only source for family selection.

The scoring method is versioned and written to
`selection/scoring_method.md`. Initial method version: `research_handoff_rank_v1`.

Initial formula:

```text
blended_score =
  promotion_or_recent_score
  - 0.50 * recent_window_score_stdev
  - low_trade_penalty
  - failed_gate_penalty
  - nan_penalty
  - cost_stress_penalty
  - complexity_penalty
```

The exact penalty constants must be encoded in the ranker and copied into the
ranking output. Ranking ties use deterministic tie-breaks: higher promotion
score, lower score dispersion, higher trade count, simpler logic family, then
lexicographic variant id.

Initial penalty constants:

```text
low_trade_penalty = 0.001 when any retained recent window has fewer than 200 trades
failed_gate_penalty = 0.005 when a promotion summary reports failed reasons
nan_penalty = 0.010 when any required score is missing, NaN, or non-finite
cost_stress_penalty = max(0, promotion_score * 0.50 - cost_stress_score) when cost stress exists
complexity_penalty = 0.00025 per added mechanism beyond the base family
```

Added mechanisms include fixed take-profit, fixed stop-loss, trailing stop,
direction-only restriction, hard entry filter, balance-side restriction,
alternate selection score, and altered lookback/cadence. Constants are
intentionally small relative to the promotion score so penalties break ties and
discourage fragile complexity without drowning out evidence.

Logic family assignment is rule-based with fixed priority. Initial family ids:

```text
time_only_exit
price_threshold_exit
trailing_exit
entry_filter
directional_subset
lookback_or_cadence
selection_or_breadth
other
```

The LLM can summarize and challenge the categorization, but cannot silently
rewrite selected families or variants. Any manual override must be recorded in
`manifest.json` with a reason.

## Skill Workflow

Create a project-local skill named `strategy-research-handoff`.

The skill orchestrates:

1. Identify the latest completed campaign or accept an explicit campaign path.
2. Run the deterministic ranker.
3. Review the ranking output for obvious artifact gaps.
4. Create `quant_strategies/researched/<strategy_id>/`.
5. Copy the selected family and variant packages.
6. Write `README.md`, `HANDOFF.md`, `manifest.json`, and notes.
7. Verify retained configs in `quant_strategies`.
8. Only after successful verification, reset `quant_autoresearch` to a neutral
   next-strategy state.

The skill should be conservative. It may ask for confirmation before deleting
or cleaning ignored artifacts. It must not infer market validation.

## Bench Reset

After transfer verification, reset this workbench so the next strategy is not
biased by the completed one.

The reset should remove or neutralize strategy-specific state:

- scratch `strategy.py`,
- scratch `experiment.toml`,
- strategy-specific `tests/test_strategy_contract.py`,
- active results directory reference,
- local generated results if Season approves cleanup,
- any strategy-specific notes that belong in `quant_strategies/researched/`.

The reset should preserve generic process documentation, runner harness files,
tests, and upstream limitation guidance.

## Verification

Minimum verification before declaring handoff complete:

- Ranker output exists and selects exactly three logic families.
- Each selected family has up to five retained variants.
- Each retained variant has `strategy.py`, `config.toml`, and evidence files.
- `manifest.json` records source repo path, source commit, campaign path,
  code hashes, config hashes, ranking method version, and generated timestamp.
- `quant_strategies` can import each retained strategy file.
- Every retained config passes a config load/import check in `quant_strategies`.
- The top variant in each selected family runs through `quant-strategies run`
  unless Season explicitly approves skipping expensive reruns.
- No cleanup occurs before the researched package is verified.

## Neutral Bench State

After handoff, `quant_autoresearch` should keep neutral placeholders rather than
delete required files:

- `strategy.py` becomes a minimal strategy module with the required
  `generate_signals(bars, params)` function returning an empty list and a
  docstring saying the bench is awaiting the next candidate.
- `experiment.toml` becomes a minimal runnable skeleton using a placeholder
  `strategy_id`, `strategy_path = "strategy.py"`, neutral parameters, and a new
  `results_dir` such as `results/next_strategy`.
- `tests/test_strategy_contract.py` becomes a neutral contract test that checks
  the placeholder strategy exports `generate_signals` and returns no signals.
- `UPSTREAM_LIMITATIONS_TODO.md` remains generic and empty unless unresolved
  upstream issues were discovered during the completed campaign.
