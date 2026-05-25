---
name: strategy-research-handoff
description: Package a completed quant_autoresearch campaign into quant_strategies/researched and reset the bench after verification.
---

# Strategy Research Handoff

Use this when Season asks to remove a completed strategy from the research bench,
transfer reproducible artifacts to `quant_strategies`, or prepare the bench for
the next strategy.

## Required Inputs

- Completed campaign directory, usually a concrete path such as `results/broad_strategy_100`.
- Target `quant_strategies` repo path.
- Strategy id.
- Current `strategy.py` and `experiment.toml`.

## Workflow

1. Confirm the campaign has `session_state.json` with `remaining_attempts = 0`
   or ask Season before packaging an unfinished campaign.
2. Run `tools/research_handoff_rank.py`; do not choose families manually.
3. Inspect `handoff_ranking.json` for exactly three selected families.
4. Run `tools/research_handoff_package.py`.
5. In `quant_strategies`, run config load/import checks for retained variants.
6. Update `researched/{strategy_id}/notes/llm_research_summary.md` if useful;
   cite ranking JSON, configs, and evidence files as the source of truth.
7. Only after package verification, reset `quant_autoresearch` to the neutral
   placeholder state.
8. Never describe the strategy as market validated. It is researched and ready
   for a separate validation process.
