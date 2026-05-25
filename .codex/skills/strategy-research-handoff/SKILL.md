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
2. Run the ranker with the completed campaign directory and an explicit output
   path; do not choose families manually:
   ```bash
   conda run -n quant python tools/research_handoff_rank.py <campaign_dir> --output <handoff_ranking.json>
   ```
3. Inspect `handoff_ranking.json` for exactly three selected families.
4. After the ranker/package toolchain is implemented, run the package tool with
   the campaign, target repo, strategy id, and ranking file:
   ```bash
   conda run -n quant python tools/research_handoff_package.py --campaign <campaign_dir> --target-repo <quant_strategies_repo> --strategy-id <strategy_id> --ranking <handoff_ranking.json>
   ```
5. In `quant_strategies`, run config load/import checks for retained variants.
6. Update `researched/{strategy_id}/notes/llm_research_summary.md` if useful;
   cite ranking JSON, configs, and evidence files as the source of truth.
7. Only after package verification, reset these `quant_autoresearch` bench files
   to the neutral placeholder state:
   - `strategy.py`
   - `experiment.toml`
   - `tests/test_strategy_contract.py`

   Preserve generic docs, skills, tools, and `UPSTREAM_LIMITATIONS_TODO.md`
   unless adding or retaining a real upstream limitation discovered during the
   research.
8. Never describe the strategy as market validated. It is researched and ready
   for a separate validation process.
