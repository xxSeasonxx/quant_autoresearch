# Strategy Research Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan task-by-task. Keep commits green: write failing tests locally when useful, but commit tests and implementation together only after targeted verification passes.

**Goal:** Build and run a repeatable closeout process that packages a completed `quant_autoresearch` strategy campaign into `quant_strategies/researched/`, then resets the workbench so the next strategy starts without bias from the previous one.

**Architecture:** Add deterministic Python tools in `quant_autoresearch/tools/`: one ranker that selects exactly three logic families and up to five variants per family, and one packager that copies the selected package into `quant_strategies/researched/`. Add a local skill that orchestrates those tools; update `quant_strategies` docs/tests for the new lifecycle; run the process for `crypto_perp_funding_crowding_reversal`; reset `quant_autoresearch`.

**Tech Stack:** Python 3.12 standard library (`argparse`, `dataclasses`, `hashlib`, `json`, `pathlib`, `shutil`, `statistics`, `tomllib`), pytest, existing `quant_strategies.runner.config.load_config`.

**Non-Goals:**
- Do not create the separate validation process in this pass.
- Do not call researched candidates market validated.
- Do not move anything to `tested/`.
- Do not leave strategy-specific logic in `quant_autoresearch` after the handoff reset.

---

## Data Flow

```text
quant_autoresearch/results/<campaign>/
  session_state.json
  */attempt_metadata.json
  */score.json
  promotion_*/promotion_summary.json
  promotion_*/promotion_score.json
              |
              v
tools/research_handoff_rank.py
  - infer campaign baseline params
  - classify logic families deterministically
  - score variants with penalties
  - select exactly 3 families, up to 5 variants each
              |
              v
handoff_ranking.json
              |
              v
tools/research_handoff_package.py
              |
              v
quant_strategies/researched/<strategy_id>/
  selection/
  families/family_01_primary_*/variants/rank_*/
  notes/
  manifest.json
              |
              v
verify package configs and target-repo tests
              |
              v
reset quant_autoresearch to awaiting_next_candidate
```

---

## Reviewed Decisions Locked Into This Plan

- Execute phased: ranker, packager, lifecycle docs, current handoff, bench reset.
- Select exactly three logic families. Keep up to five concrete variants inside each family.
- Treat a logic family as a logic change, not a parameter sweep.
- Infer baseline params from campaign artifacts. Do not hard-code strategy-specific baseline values in the ranker.
- Use deterministic scoring; the skill or LLM must not decide rankings.
- Require clean tracked state before changing either repo, except known handoff files and the current bench config.
- Ignore untracked local tool directories such as `.codex/`, `.codegraph/`, `.cursor/`, `.claude/`, and `openspec/` unless a task explicitly creates a tracked file inside them.
- Keep commits green. Do not commit intentionally failing tests.
- Add `tools/__init__.py`.
- Add full ranker edge coverage: fewer than three families, NaN penalty, top-five cap, promotion matching, and cost-stress penalty.
- Add full package safety coverage: destination collision, source snapshot choice, missing optional evidence, config rewrite, manifest hashes, and `load_config` acceptance.
- Reset `experiment.toml` with the exact neutral TOML in Task 8.
- Do not add a validation-process TODO in this pass.

---

## File Structure

Create or modify these files in `quant_autoresearch`:

- Create `tools/__init__.py`.
- Create `tools/research_handoff_rank.py`.
- Create `tools/research_handoff_package.py`.
- Create `tests/test_research_handoff_rank.py`.
- Create `tests/test_research_handoff_package.py`.
- Create `.codex/skills/strategy-research-handoff/SKILL.md`.
- Modify `program.md`.
- Modify `strategy.py`, `experiment.toml`, and `tests/test_strategy_contract.py` only in the final reset task after the researched package verifies.
- Modify `UPSTREAM_LIMITATIONS_TODO.md` only to record upstream limitations surfaced by this campaign and handoff. Do not add validation-process TODOs.

Create or modify these files in `/Users/Season_Yang/Personal/quant_strategies`:

- Create `researched/.gitkeep` if no package exists yet.
- Modify `README.md`.
- Modify `AGENTS.md` carefully; preserve existing user edits.
- Modify `tests/test_strategy_docstrings.py`.
- Create `researched/crypto_perp_funding_crowding_reversal/` through the packager.

Do not edit generated `results/` by hand. Tools may read them and copy selected evidence into `quant_strategies/researched/`.

---

## Task 0: Preflight

**Files:** none.

- [ ] Check tracked status in both repos before edits:

```bash
git status --short
git -C /Users/Season_Yang/Personal/quant_strategies status --short
```

- [ ] Fail and ask Season if either repo has tracked modifications outside known handoff paths:
  - `quant_autoresearch`: current `experiment.toml`, plan files, and files named in this plan.
  - `quant_strategies`: `AGENTS.md`, docs/tests named in this plan, and generated `researched/` package.

- [ ] Ignore untracked local tool/cache directories unless this plan explicitly tracks a file inside them.

- [ ] Verify the current campaign is complete:

```bash
conda run -n quant python - <<'PY'
import json
from pathlib import Path

state = json.loads(Path("results/broad_strategy_100/session_state.json").read_text())
assert state["remaining_attempts"] == 0
assert state["status"] == "exhausted"
print(state["attempts_used"], state["best_promoted_score"])
PY
```

---

## Task 1: Deterministic Ranker

**Files:**
- Create `tools/__init__.py`.
- Create `tools/research_handoff_rank.py`.
- Create `tests/test_research_handoff_rank.py`.

- [ ] Implement `build_handoff_ranking(campaign_dir: str | Path) -> dict[str, Any]` and a CLI:

```bash
conda run -n quant python tools/research_handoff_rank.py results/broad_strategy_100 --output /tmp/handoff_ranking.json
```

- [ ] Public output shape:

```python
{
    "method_version": "research_handoff_rank_v1",
    "generated_at": "...",
    "campaign_dir": "...",
    "baseline_params": {...},
    "selected_families": [...],
    "variants": [...],
}
```

- [ ] Load root-level scored attempt directories by reading `attempt_metadata.json`, sibling `score.json`, generated config TOML, and `[params]`.
- [ ] Skip `promotion_*` directories while loading attempts.
- [ ] Group attempts into concrete variants by SHA-256 of canonical JSON containing params plus strategy source SHA.
- [ ] Compute strategy source SHA by preferring the scored run's `strategy_snapshot.py` when present; otherwise use current `strategy.py`; otherwise `"missing"`.
- [ ] Attach promotions by matching `promotion_*/promotion_summary.json` to selected attempt ids. Store promotion score, promotion dir, promotion summary, and optional cost-stress score from any referenced score artifact.
- [ ] Infer campaign baseline params from observed variants:
  - Use only keys present in the campaign configs.
  - For each param key, choose the modal canonical value across variants.
  - Break ties by selecting the value from the earliest attempt that has the tied value.
  - Expose the inferred baseline in output.
  - Family classification may compare only keys present in the inferred baseline.

- [ ] Classify logic families with fixed priority:
  - `trailing_exit`: positive `trailing_stop_bps`.
  - `price_threshold_exit`: positive `take_profit_bps` or `stop_loss_bps`.
  - `directional_subset`: either side include flag is false.
  - `entry_filter`: hard filter keys differ from inferred baseline: `min_abs_funding_bps`, `min_abs_return_bps`, `min_same_sign_funding_events`, `min_latest_abs_funding_bps`, `min_idiosyncratic_return_bps`, `min_long_idiosyncratic_return_bps`, `min_tail_count`, `balance_sides`.
  - `lookback_or_cadence`: `funding_lookback_events`, `return_lookback_minutes`, or `decision_interval_minutes` differ.
  - `selection_or_breadth`: `top_n` or `selection_score` differ.
  - `time_only_exit`: otherwise.

- [ ] Score each variant:
  - `base_score = promotion_score` when present, otherwise mean of finite recent-window scores.
  - `recent_window_score_stdev = statistics.pstdev(finite recent scores)` when at least two finite scores exist, else `0.0`.
  - Penalize NaN/non-finite scores.
  - Penalize low trade count.
  - Penalize missing recent windows.
  - Penalize worse cost-stress evidence when available.
  - `blended_score = base_score - 0.50 * recent_window_score_stdev - sum(penalties)`.

- [ ] Sort variants deterministically by blended score descending, promotion score descending, lower stdev, higher trade count, family priority, then variant id.
- [ ] Select exactly three families by each family's best variant; raise `ValueError("expected at least three logic families")` when fewer than three families exist.
- [ ] Keep up to five variants per selected family.

- [ ] Test coverage must include:
  - exactly three family selection,
  - fewer than three families raises,
  - NaN/non-finite score penalty,
  - low-trade penalty,
  - top-five cap within a family,
  - promotion matching by attempt,
  - optional cost-stress penalty,
  - inferred baseline comparison rather than hard-coded baseline values.

- [ ] Run targeted verification before committing:

```bash
conda run -n quant pytest tests/test_research_handoff_rank.py -q
conda run -n quant python tools/research_handoff_rank.py results/broad_strategy_100 --output /tmp/broad_strategy_handoff_ranking.json
```

- [ ] Commit green:

```bash
git add tools/__init__.py tools/research_handoff_rank.py tests/test_research_handoff_rank.py
git commit -m "feat: add deterministic research handoff ranker"
```

---

## Task 2: Researched Package Builder

**Files:**
- Create `tools/research_handoff_package.py`.
- Create `tests/test_research_handoff_package.py`.

- [ ] Implement:

```python
def build_researched_package(
    *,
    campaign_dir: str | Path,
    target_repo: str | Path,
    strategy_id: str,
    ranking_path: str | Path | None = None,
    source_strategy_path: str | Path = "strategy.py",
    replace: bool = False,
) -> Path:
    ...
```

- [ ] CLI options:
  - `--campaign`
  - `--target-repo`
  - `--strategy-id`
  - `--ranking`
  - `--source-strategy`
  - `--replace`

- [ ] Load `ranking_path` if passed; otherwise call `build_handoff_ranking(campaign_dir)`.
- [ ] Destination is `target_repo/researched/{strategy_id}`. If it already exists, fail with `FileExistsError` unless `replace=True` or CLI `--replace` is used.
- [ ] Write `selection/handoff_ranking.json` and `selection/scoring_method.md`.
- [ ] For each selected family, create:

```text
families/family_01_primary_{logic_family_id}/
families/family_02_secondary_{logic_family_id}/
families/family_03_exploratory_{logic_family_id}/
```

- [ ] For each retained variant, create `variants/rank_XX/strategy.py`, `config.toml`, and `evidence/`.
- [ ] Copy source strategy snapshot into each variant. Prefer the selected variant's per-run `strategy_snapshot.py` when present; otherwise use `source_strategy_path`.
- [ ] Rewrite config TOML from the selected `generated_config`:
  - top-level `strategy_path = "researched/{strategy_id}/families/{family_dir}/variants/rank_XX/strategy.py"`;
  - `[output].results_dir = "results/researched/{strategy_id}/{family_dir}/rank_XX"`.
- [ ] Preserve other config fields while rewriting.
- [ ] Copy minimal evidence:
  - promotion score and summary when present,
  - root scored `score.json` files for retained windows,
  - `trade_attribution.json` for `rank_01` in each family when present,
  - tolerate missing optional evidence without failing.
- [ ] Write `manifest.json` with source repo path, target repo path, campaign path, generated timestamp, ranking method version, selected family ids, variant ids, code SHA-256, config SHA-256, and copied evidence file list.
- [ ] Write deterministic `README.md`, `HANDOFF.md`, `notes/llm_research_summary.md`, and `notes/upstream_limitations.md`.
- [ ] The generated LLM summary scaffold must state that it is an initial machine-written scaffold and that source JSON/config/evidence files are authoritative.

- [ ] Test coverage must include:
  - package layout for three families,
  - config rewrite assertions for strategy path and results dir,
  - destination collision behavior,
  - source snapshot preference over current source strategy,
  - missing optional evidence does not fail,
  - manifest hashes match actual files,
  - generated configs are accepted by `quant_strategies.runner.config.load_config`.

- [ ] Run targeted verification before committing:

```bash
conda run -n quant pytest tests/test_research_handoff_package.py -q
```

- [ ] Commit green:

```bash
git add tools/research_handoff_package.py tests/test_research_handoff_package.py
git commit -m "feat: add researched package builder"
```

---

## Task 3: Local Handoff Skill And Program Guidance

**Files:**
- Create `.codex/skills/strategy-research-handoff/SKILL.md`.
- Modify `program.md`.
- Modify `UPSTREAM_LIMITATIONS_TODO.md` only if needed for upstream limitations surfaced by this workflow.

- [ ] Create the local skill:

```markdown
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
```

- [ ] Add a short `program.md` closeout section:

```markdown
## Strategy Closeout

When a campaign is complete and Season wants the bench prepared for the next
strategy, use the `strategy-research-handoff` skill. The closeout process must
rank variants with deterministic tooling, write the researched package into
`quant_strategies/researched/`, verify the package, and only then reset this
bench to a neutral placeholder state.
```

- [ ] Run:

```bash
conda run -n quant pytest tests/test_program_contract.py -q
```

- [ ] Commit green:

```bash
git add .codex/skills/strategy-research-handoff/SKILL.md program.md UPSTREAM_LIMITATIONS_TODO.md
git commit -m "docs: add strategy research handoff skill"
```

If `UPSTREAM_LIMITATIONS_TODO.md` is unchanged, do not stage it.

---

## Task 4: `quant_strategies` Lifecycle Docs And Tests

**Files in `/Users/Season_Yang/Personal/quant_strategies`:**
- Modify `README.md`.
- Modify `AGENTS.md`; preserve existing user edits.
- Modify `tests/test_strategy_docstrings.py`.
- Create `researched/.gitkeep` if no package exists yet.

- [ ] Update README lifecycle language to include:

```text
untested/    raw or actively forming strategy ideas
researched/  bench-researched candidates frozen for separate validation
tested/      strategies that passed the separate validation process
```

- [ ] Add README paragraph:

```markdown
`researched/` stores self-contained handoff packages from `quant_autoresearch`.
Each package keeps frozen strategy code, runnable configs, deterministic
selection output, and compact evidence. A researched strategy is ready for the
separate validation process; it is not market validated and should not be moved
to `tested/` until that validation process passes.
```

- [ ] Add AGENTS lifecycle instructions:

```markdown
- Keep `researched/` for frozen bench-promoted packages from
  `quant_autoresearch`. Do not treat `researched/` as market validated.
- Move from `researched/` to `tested/` only through the separate validation
  process Season approves.
```

- [ ] Extend `tests/test_strategy_docstrings.py` so docstring and purity checks include nested researched variants:

```python
def researched_strategy_files() -> list[Path]:
    return sorted(Path("researched").glob("*/families/*/variants/*/strategy.py"))


def all_strategy_files_for_contract() -> list[Path]:
    return strategy_files() + researched_strategy_files()
```

- [ ] Keep flat-layout tests limited to `tested/` and `untested/`.
- [ ] Run:

```bash
cd /Users/Season_Yang/Personal/quant_strategies
conda run -n quant pytest tests/test_strategy_docstrings.py tests/test_runner_config.py -q
```

- [ ] Commit green in `quant_strategies`:

```bash
git add README.md AGENTS.md tests/test_strategy_docstrings.py researched/.gitkeep
git commit -m "docs: add researched strategy lifecycle"
```

If the package already exists, include only lifecycle docs/tests here and commit the package separately.

---

## Task 5: Package Current Strategy Into `quant_strategies`

**Reads:**
- `results/broad_strategy_100/`
- current `strategy.py`

**Writes:**
- `/Users/Season_Yang/Personal/quant_strategies/researched/crypto_perp_funding_crowding_reversal/`

- [ ] Generate deterministic ranking:

```bash
conda run -n quant python tools/research_handoff_rank.py \
  results/broad_strategy_100 \
  --output /tmp/crypto_perp_funding_crowding_reversal_handoff_ranking.json
```

- [ ] Confirm:
  - output JSON exists,
  - `selected_families` length is exactly `3`,
  - family 1 is expected to be `time_only_exit` unless deterministic scoring says otherwise.

- [ ] Build researched package:

```bash
conda run -n quant python tools/research_handoff_package.py \
  --campaign results/broad_strategy_100 \
  --target-repo /Users/Season_Yang/Personal/quant_strategies \
  --strategy-id crypto_perp_funding_crowding_reversal \
  --ranking /tmp/crypto_perp_funding_crowding_reversal_handoff_ranking.json
```

- [ ] Update package LLM summary at:

```text
/Users/Season_Yang/Personal/quant_strategies/researched/crypto_perp_funding_crowding_reversal/notes/llm_research_summary.md
```

Include:
- best candidate score `0.016278311526520668`,
- prior best `0.015707175388822794`,
- best logic: funding/return crowding reversal with time-only exits,
- threshold exits generally underperformed,
- family 2/3 labels if weak or exploratory,
- caveat: researched package only, not market validation.

- [ ] Verify retained configs load:

```bash
cd /Users/Season_Yang/Personal/quant_strategies
conda run -n quant python - <<'PY'
from pathlib import Path
from quant_strategies.runner.config import load_config

repo = Path.cwd()
configs = sorted(repo.glob("researched/crypto_perp_funding_crowding_reversal/families/*/variants/*/config.toml"))
assert configs, "no researched configs found"
for path in configs:
    load_config(path, repo_root=repo)
print(f"loaded {len(configs)} researched configs")
PY
```

- [ ] Run top variant per selected family:

```bash
cd /Users/Season_Yang/Personal/quant_strategies
conda run -n quant quant-strategies run --repo-root "$PWD" researched/crypto_perp_funding_crowding_reversal/families/<family_dir>/variants/rank_01/config.toml
```

- [ ] Run target repo focused tests:

```bash
cd /Users/Season_Yang/Personal/quant_strategies
conda run -n quant pytest tests/test_strategy_docstrings.py tests/test_runner_config.py tests/test_crypto_perp_funding_crowding_reversal.py -q
```

- [ ] Commit green in `quant_strategies`:

```bash
git add researched/crypto_perp_funding_crowding_reversal
git commit -m "research: add crypto perp funding crowding handoff"
```

Do not add ignored generated `results/`.

---

## Task 6: Reset `quant_autoresearch` Bench

**Files in `quant_autoresearch`:**
- Modify `strategy.py`.
- Modify `experiment.toml`.
- Modify `tests/test_strategy_contract.py`.
- Modify `UPSTREAM_LIMITATIONS_TODO.md` only if the completed campaign left unresolved upstream limitations.

- [ ] Replace `strategy.py` with:

```python
"""Strategy: awaiting_next_candidate

This workbench has been reset after the prior researched strategy was handed
off to `quant_strategies/researched/`.

The next research cycle should replace this module with one scratch strategy
candidate and update `experiment.toml` accordingly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


__all__ = ["generate_signals"]


def generate_signals(bars: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> list[dict[str, object]]:
    return []
```

- [ ] Replace `experiment.toml` with exactly:

```toml
strategy_id = "awaiting_next_candidate"
strategy_path = "strategy.py"
source_strategy_path = "/Users/Season_Yang/Personal/quant_strategies/untested/awaiting_next_candidate.py"
max_attempts = 100
active_window_id = "placeholder_120d"

[[windows]]
id = "placeholder_120d"
start = "2024-01-01"
end = "2024-04-29"

[data]
kind = "bars"
dataset = "equity_1min"
symbols = ["SPY"]
strict = true

[params]
weight = 1.0
hold_bars = 1

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 0.0
slippage_bps_per_side = 0.0

[scoring]
metric = "net_return"
min_score_trades = 1

[output]
results_dir = "results/next_strategy"
mode = "validate"
```

- [ ] Replace `tests/test_strategy_contract.py` with:

```python
from __future__ import annotations

from strategy import generate_signals


def test_placeholder_strategy_returns_no_signals():
    assert generate_signals([], {}) == []
```

- [ ] Run:

```bash
conda run -n quant pytest tests/test_strategy_contract.py tests/test_experiment_config.py tests/test_program_contract.py -q
```

- [ ] Commit green in `quant_autoresearch`:

```bash
git add strategy.py experiment.toml tests/test_strategy_contract.py
git commit -m "chore: reset research bench for next strategy"
```

---

## Task 7: Final Verification And Status

**Files:** no new files expected.

- [ ] Verify `quant_autoresearch`:

```bash
cd /Users/Season_Yang/Personal/quant_autoresearch
conda run -n quant pytest -q
git status --short
```

- [ ] Verify `quant_strategies`:

```bash
cd /Users/Season_Yang/Personal/quant_strategies
conda run -n quant pytest -q
git status --short
```

- [ ] Final report must include:
  - `quant_autoresearch` commits made,
  - `quant_strategies` commits made,
  - researched package path,
  - selected three logic families,
  - retained concrete variants per family,
  - verification commands and results,
  - local ignored/untracked tool or results directories left in place.

---

## GSTACK REVIEW REPORT

**Decision Summary:** Accepted the engineering review changes. The plan now executes in phases, commits only green work, infers baseline params from campaign artifacts, checks tracked dirty state before edits, and adds deterministic ranker/package edge coverage before the current strategy is handed off.

**Chosen Tradeoffs:**
- Exactly three logic families keeps the artifact easy to audit and forces deterministic comparison across logic classes.
- Weak families are still retained when they are among the top three deterministic families, but the package summary must label them accurately.
- Validation-process design is intentionally excluded from this pass to keep `researched/` distinct from future `tested/` promotion.

**Implementation Gate:** Do not reset `quant_autoresearch` until the `quant_strategies/researched/crypto_perp_funding_crowding_reversal/` package exists and retained configs load successfully.
