# Quant Autoresearch Cheap Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ordinary research iterations fast again by disabling automatic full promotion, adding an explicit `--promote` command, and documenting the primary-plus-fixed-guard loop.

**Architecture:** Keep the existing promotion implementation. `--explore` remains the cheap idea-discovery command. `--promote` runs the primary window once and reuses `run_promotion_screen()` plus `_finish_promotion_attempt()` for the full promotion path.

**Tech Stack:** Python 3.12 standard library, existing `runner.py`, `experiment_config.py`, `promotion.py`, `pytest`, markdown docs.

---

## File Structure

- `runner.py`: add explicit `--promote` CLI mode and route it through existing promotion code.
- `experiment.toml`: set `promotion.screen_on_scored_explore = false` for the active research configuration.
- `program.md`: simplify the LLM-facing research instructions around explore, fixed guard, and deliberate promotion.
- `AGENTS.md`: keep project target consistent with cheap guard plus deliberate promotion.
- `tests/test_runner.py`: cover `--promote`, disabled auto promotion, and CLI ambiguity.
- `tests/test_program_contract.py`: update the contract from “every scored explore promotes” to “cheap guard, deliberate promotion.”
- `tests/test_agents_contract.py`: keep repo-local agent target wording current.

No new module is needed. Do not add a separate “fast screen” scoring framework.

## What Already Exists

- `runner.py --window-id`: already runs one configured diagnostic window; reuse it for the fixed guard.
- `run_promotion_screen()`: already runs recent windows, cost stress, and rotating probe; reuse it for `--promote`.
- `_finish_promotion_attempt()`: already updates promotion state, artifacts, stdout, and `results.tsv`; reuse it unchanged.
- `promotion.screen_on_scored_explore`: already controls automatic full promotion; flip the active config default instead of adding a new setting.
- `tests/test_runner.py` promotion tests: already cover legacy auto-promotion behavior; extend them rather than creating a new test module.

## NOT In Scope

- New guard scoring framework: the guard is a manual diagnostic command, not another optimizer target.
- New runner subcommands beyond `--promote`: `--window-id validation_2025_h1` already covers the fixed guard.
- Full validation suite: promoted candidates still move to downstream comprehensive validation.
- Parallel orchestration: the immediate goal is faster ordinary iterations, not more automation.
- Rewriting confirmation mode: keep existing `--confirm` behavior unless a later cleanup removes it deliberately.

## Control Flow

```text
runner.py --explore
  |
  v
primary: locked_recent_2026
  |
  +-- weak or unscored -> inspect evidence, revise idea
  |
  v
runner.py --window-id validation_2025_h1
  |
  +-- contradicts primary -> reject or diagnose with quant rationale
  |
  v
runner.py --promote
  |
  +-- promotion disabled -> fail before running windows
  +-- primary unscored -> finish one attempt, no promotion artifacts
  `-- primary scored -> reuse existing full promotion screen
```

## Test Coverage Map

```text
CODE PATHS                                            USER FLOWS
[+] runner.py CLI mode selection                      [+] Fast research loop
  ├── [★★★ TESTED] --explore primary only               ├── [★★★ TESTED] explore does not auto-promote when disabled
  ├── [★★★ TESTED] --window-id remains diagnostic       ├── [★★★ TESTED] fixed guard uses existing --window-id flow
  ├── [★★★ TESTED] --promote excludes --window-id       └── [★★★ TESTED] serious candidate escalates through --promote
  └── [★★★ TESTED] --confirm legacy path unchanged

[+] runner.py --promote control flow                  [+] Failure and cheap-exit behavior
  ├── [★★★ TESTED] promotion disabled exits before run  ├── [★★★ TESTED] no results.tsv on disabled --promote
  ├── [★★★ TESTED] primary unscored stays one-window    ├── [★★★ TESTED] no promotion artifacts for unscored primary
  └── [★★★ TESTED] primary scored runs promotion screen └── [★★★ TESTED] legacy auto-promotion still works when enabled

Prompt/docs contract: [★★★ TESTED] program.md names fast guard, deliberate --promote, and not-final-validation posture.
```

## Failure Modes

- Disabled `--promote` accidentally runs a primary window: covered by `test_explicit_promote_requires_promotion_enabled_before_running`; user sees argparse exit code 2 and no artifacts.
- Unscored primary result starts full promotion anyway: covered by `test_explicit_promote_with_unscored_primary_does_not_run_promotion`; user gets one normal attempt result and no promotion artifacts.
- Ordinary `--explore` keeps running full promotion: covered by `test_scored_explore_with_auto_promotion_disabled_stays_single_window`; iteration stays cheap.
- Legacy configs relying on auto-promotion break: covered by existing `test_scored_explore_runs_promotion_without_rerunning_primary`; compatibility remains.
- `program.md` grows into a heavy validation manual: controlled by compact wording contract in `test_program_documents_cheap_guard_and_deliberate_promotion`.

## Worktree Parallelization

Sequential implementation, no parallelization opportunity. The runner and docs changes are small, and both touch shared test contracts, so parallel worktrees would add merge overhead without reducing meaningful risk.

## Task 1: Add Failing Runner Tests

**Files:**
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Make the promotion config test helper configurable**

Replace the whole `append_promotion_config` function in `tests/test_runner.py` with:

```python
def append_promotion_config(
    root: Path,
    *,
    promotion_enabled: bool = True,
    screen_on_scored_explore: bool = True,
) -> None:
    enabled_flag = "true" if promotion_enabled else "false"
    screen_flag = "true" if screen_on_scored_explore else "false"
    with (root / "experiment.toml").open("a") as handle:
        handle.write(
            f"""
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 1
confirm_on_explore_keep = false

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.0
weak_window_floor = 0.0
weak_window_penalty = 0.0
min_trades_per_window = 2
low_trade_penalty = 0.0
min_symbol_count = 1
symbol_concentration_penalty = 0.0

[promotion]
enabled = {enabled_flag}
screen_on_scored_explore = {screen_flag}
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""
        )
```

- [ ] **Step 2: Add a test that disabled auto promotion keeps explore cheap**

Append this test near the existing promotion tests:

```python
def test_scored_explore_with_auto_promotion_disabled_stays_single_window(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path, screen_on_scored_explore=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    generated_configs: list[str] = []

    def _run_config(config_path: Path, *, repo_root: Path):
        generated_configs.append(config_path.read_text())
        output_dir = Path(tomllib.loads(config_path.read_text())["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=0.18, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--description", "cheap explore"]) == 0

    output = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))

    assert len(generated_configs) == 1
    assert output["run_kind"] == "explore"
    assert rows[0]["run_kind"] == "explore"
    assert rows[0]["promotion_score"] == ""
    assert state["best_promoted_score"] is None
    assert state["rotating_probe_index"] == 0
    assert not list((tmp_path / "results").glob("promotion_*"))
```

- [ ] **Step 3: Add a test that explicit `--promote` runs full promotion**

Append this test after the disabled-auto test:

```python
def test_explicit_promote_runs_full_promotion_when_auto_promotion_is_disabled(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path, screen_on_scored_explore=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    generated_starts: list[str] = []

    def _run_config(config_path: Path, *, repo_root: Path):
        parsed = tomllib.loads(config_path.read_text())
        output_dir = Path(parsed["output"]["results_dir"])
        start = parsed["data"]["start"]
        fee = parsed["cost_model"]["fee_bps_per_side"]
        generated_starts.append(f"{start}|fee={fee}")
        if fee == 0.5:
            net = 0.12
        elif start == "2024-01-01":
            net = 0.18
        else:
            net = 0.16
        return fake_success_run(output_dir, net_return=net, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--promote", "--description", "deliberate promotion"]) == 0

    output = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))

    assert generated_starts.count("2024-01-01|fee=0.0") == 1
    assert output["run_kind"] == "promotion"
    assert output["decision"] == "promote"
    assert state["best_promoted_score"] == pytest.approx(output["promotion_score"])
    assert state["rotating_probe_index"] == 1
    assert rows[0]["run_kind"] == "promotion"
    assert rows[0]["promotion_decision"] == "promote"
    promotion_score = json.loads((Path(output["result_dir"]) / "promotion_score.json").read_text())
    promotion_summary = json.loads((Path(output["result_dir"]) / "promotion_summary.json").read_text())
    assert promotion_score["promotion_decision"] == "promote"
    assert promotion_score["promoted_commit"] == "abc1234"
    assert promotion_summary["source_result_dirs"]["primary"]
```

- [ ] **Step 4: Add a test that disabled promotion fails before running**

Append this test after the explicit-promote test:

```python
def test_explicit_promote_requires_promotion_enabled_before_running(
    tmp_path: Path,
    monkeypatch,
):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(
        tmp_path,
        promotion_enabled=False,
        screen_on_scored_explore=False,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)

    def _run_config(config_path: Path, *, repo_root: Path):
        raise AssertionError("disabled --promote must fail before running a window")

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    with pytest.raises(SystemExit) as exc:
        main(["--promote", "--description", "disabled promotion"])

    assert exc.value.code == 2
    assert not (tmp_path / "results.tsv").exists()
    assert not list((tmp_path / "results").glob("promotion_*"))
```

- [ ] **Step 5: Add a test that unscored promote stays single-window**

Append this test after the disabled-promotion test:

```python
def test_explicit_promote_with_unscored_primary_does_not_run_promotion(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path, screen_on_scored_explore=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    generated_configs: list[str] = []

    def _run_config(config_path: Path, *, repo_root: Path):
        generated_configs.append(config_path.read_text())
        output_dir = Path(tomllib.loads(config_path.read_text())["output"]["results_dir"])
        return fake_success_run(output_dir, net_return=0.18, trade_count=1)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--promote", "--description", "unscored promotion"]) == 0

    output = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))

    assert len(generated_configs) == 1
    assert output["run_kind"] == "promote"
    assert output["decision"] == "discard"
    assert output["score"] is None
    assert rows[0]["run_kind"] == "promote"
    assert rows[0]["promotion_score"] == ""
    assert state["best_promoted_score"] is None
    assert state["rotating_probe_index"] == 0
    assert not list((tmp_path / "results").glob("promotion_*"))
```

- [ ] **Step 6: Update the CLI ambiguity test**

In the `test_main_rejects_window_id_combined_with_research_modes` parameter list, add:

```python
["--promote", "--window-id", "holdout", "--description", "ambiguous"],
```

The list should become:

```python
[
    ["--confirm", "--window-id", "holdout", "--description", "ambiguous"],
    ["--explore", "--window-id", "holdout", "--description", "ambiguous"],
    ["--promote", "--window-id", "holdout", "--description", "ambiguous"],
]
```

- [ ] **Step 7: Run the focused failing tests**

Run:

```bash
conda run -n quant pytest \
  tests/test_runner.py::test_scored_explore_with_auto_promotion_disabled_stays_single_window \
  tests/test_runner.py::test_explicit_promote_runs_full_promotion_when_auto_promotion_is_disabled \
  tests/test_runner.py::test_explicit_promote_requires_promotion_enabled_before_running \
  tests/test_runner.py::test_explicit_promote_with_unscored_primary_does_not_run_promotion \
  tests/test_runner.py::test_main_rejects_window_id_combined_with_research_modes \
  -q
```

Expected:

- disabled-auto test may pass already if helper is correct,
- explicit `--promote` fails because the parser does not know `--promote`,
- disabled-promotion preflight fails until `--promote` exits before running,
- unscored-promote fails until `--promote` short-circuits to a single attempt when the primary score is not promotion-eligible,
- ambiguity test fails until `--promote` is part of the mutually exclusive group.

Do not change implementation before seeing the failure.

## Task 2: Implement Explicit `--promote`

**Files:**
- Modify: `runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Add `--promote` to the mutually exclusive mode group**

In `main`, update the parser mode group from:

```python
mode_group.add_argument("--window-id", default=None)
mode_group.add_argument("--explore", action="store_true")
mode_group.add_argument("--confirm", action="store_true")
```

to:

```python
mode_group.add_argument("--window-id", default=None)
mode_group.add_argument("--explore", action="store_true")
mode_group.add_argument("--confirm", action="store_true")
mode_group.add_argument("--promote", action="store_true")
```

- [ ] **Step 2: Add promote mode detection**

Update `_run_kind` from:

```python
def _run_kind(args: argparse.Namespace, config: ExperimentConfig) -> str:
    if args.confirm:
        return "confirm"
    if args.explore:
        return "explore"
    if args.window_id is not None:
        return "diagnostic"
    return config.research.mode
```

to:

```python
def _run_kind(args: argparse.Namespace, config: ExperimentConfig) -> str:
    if args.confirm:
        return "confirm"
    if args.promote:
        return "promote"
    if args.explore:
        return "explore"
    if args.window_id is not None:
        return "diagnostic"
    return config.research.mode
```

- [ ] **Step 3: Select the primary research window for promote**

Update `_selected_single_window` from:

```python
def _selected_single_window(args: argparse.Namespace, config: ExperimentConfig, run_kind: str) -> str:
    if args.window_id is not None:
        return args.window_id
    if run_kind == "explore":
        return config.research.primary_window_id
    return config.selected_window_id
```

to:

```python
def _selected_single_window(args: argparse.Namespace, config: ExperimentConfig, run_kind: str) -> str:
    if args.window_id is not None:
        return args.window_id
    if run_kind in {"explore", "promote"}:
        return config.research.primary_window_id
    return config.selected_window_id
```

- [ ] **Step 4: Fail fast when explicit promote is disabled**

In `main`, after `run_kind = _run_kind(args, config)` and before the `if run_kind == "confirm":` block, add:

```python
    if run_kind == "promote" and not config.promotion.enabled:
        parser.error("--promote requires promotion.enabled = true")
```

- [ ] **Step 5: Route explicit promote through the existing promotion path**

In `main`, after the assignment beginning `window_result = run_single_window_attempt(` and before the existing auto-promotion block, add this block:

```python
    if run_kind == "promote":
        if not scored_for_promotion(window_result.score):
            return _finish_attempt(
                state_path=state_path,
                state=state,
                score=window_result.score,
                attempt=attempt,
                commit=commit,
                window_id=window_id,
                run_metadata=window_result.run_metadata,
                result_dir=window_result.result_dir,
                description=args.description,
                simplification=args.simplification,
                ignored_max_attempts_override=ignored_max_attempts_override,
                run_kind=run_kind,
            )
        promotion_dir, promotion_score, recent_results = run_promotion_screen(
            config=config,
            state=state,
            attempt=attempt,
            results_dir=results_dir,
            description=args.description,
            commit=commit,
            simplification=args.simplification,
            artifact_profile=args.artifact_profile,
            explore_result=window_result,
        )
        return _finish_promotion_attempt(
            state_path=state_path,
            state=state,
            promotion_dir=promotion_dir,
            promotion_score=promotion_score,
            recent_results=recent_results,
            attempt=attempt,
            commit=commit,
            description=args.description,
            ignored_max_attempts_override=ignored_max_attempts_override,
            simplification=args.simplification,
            primary_window_id=config.research.primary_window_id,
        )
```

Keep the existing automatic promotion block below this. It still supports old configs where `screen_on_scored_explore = true`.

- [ ] **Step 6: Run the focused runner tests**

Run:

```bash
conda run -n quant pytest \
  tests/test_runner.py::test_scored_explore_with_auto_promotion_disabled_stays_single_window \
  tests/test_runner.py::test_explicit_promote_runs_full_promotion_when_auto_promotion_is_disabled \
  tests/test_runner.py::test_explicit_promote_requires_promotion_enabled_before_running \
  tests/test_runner.py::test_explicit_promote_with_unscored_primary_does_not_run_promotion \
  tests/test_runner.py::test_scored_explore_runs_promotion_without_rerunning_primary \
  tests/test_runner.py::test_non_scored_explore_does_not_run_promotion \
  tests/test_runner.py::test_main_rejects_window_id_combined_with_research_modes \
  -q
```

Expected: all pass.

- [ ] **Step 7: Commit runner behavior**

Run:

```bash
git add runner.py tests/test_runner.py
git commit -m "Add explicit promotion runner mode"
```

## Task 3: Update Active Config Defaults

**Files:**
- Modify: `experiment.toml`

- [ ] **Step 1: Disable automatic full promotion in active config**

Change:

```toml
[promotion]
enabled = true
screen_on_scored_explore = true
```

to:

```toml
[promotion]
enabled = true
screen_on_scored_explore = false
```

Do not remove the rest of the `[promotion]` section. It is still used by `runner.py --promote`.

- [ ] **Step 2: Verify config parses**

Run:

```bash
conda run -n quant python - <<'PY'
from experiment_config import load_experiment_config
config = load_experiment_config("experiment.toml")
assert config.promotion.enabled is True
assert config.promotion.screen_on_scored_explore is False
assert config.promotion.recent_window_ids
assert config.promotion.rotating_probe_window_ids
print("promotion explicit-only config ok")
PY
```

Expected output:

```text
promotion explicit-only config ok
```

- [ ] **Step 3: Commit config default**

Run:

```bash
git add experiment.toml
git commit -m "Disable automatic full promotion"
```

## Task 4: Update Program And Agent Instructions

**Files:**
- Modify: `program.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_program_contract.py`
- Modify: `tests/test_agents_contract.py`

- [ ] **Step 1: Update the program contract test for cheap guard wording**

Replace `test_program_documents_promotion_screen_without_replacing_protocol` in `tests/test_program_contract.py` with:

```python
def test_program_documents_cheap_guard_and_deliberate_promotion():
    text = PROGRAM.read_text()
    normalized = " ".join(text.split())

    required = [
        "Fast guard",
        "`locked_recent_2026`",
        "`validation_2025_h1`",
        "Do not run full promotion after every idea",
        "`runner.py --promote`",
        "guard is a sanity check",
        "not a second optimizer target",
        "Promotion screening remains a compact robustness filter",
        "not final validation",
        "comprehensive validation",
    ]
    for phrase in required:
        assert phrase in normalized

    banned = [
        "Every scored explore enters promotion screening",
    ]
    for phrase in banned:
        assert phrase not in normalized

    assert "Editable during a research loop:" in text
    assert "Evidence review" in text
    assert "The experiment loop" in text
```

- [ ] **Step 2: Update the agent contract test**

In `tests/test_agents_contract.py`, change the `required` list from:

```python
required = [
    "fast quant candidate research workbench",
    "not the final validation framework",
    "compact promotion screening",
    "comprehensive validation",
    "program.md",
    "README.md",
]
```

to:

```python
required = [
    "fast quant candidate research workbench",
    "not the final validation framework",
    "cheap guard screen",
    "deliberate promotion screening",
    "comprehensive validation",
    "program.md",
    "README.md",
]
```

- [ ] **Step 3: Run docs contract tests to verify they fail**

Run:

```bash
conda run -n quant pytest tests/test_program_contract.py tests/test_agents_contract.py -q
```

Expected: fail because `program.md` and `AGENTS.md` still use the old promotion wording.

- [ ] **Step 4: Update `program.md` promotion section with compact wording**

Replace the current `## Promotion screening` section with:

```markdown
## Fast guard

Use a cheap guard before spending time on full promotion:

1. Primary explore window: `locked_recent_2026`.
2. Fixed guard diagnostic: `validation_2025_h1`.

Commands:

```bash
conda run -n quant python runner.py --explore --description "short attempt description"
conda run -n quant python runner.py --window-id validation_2025_h1 --description "fixed guard: short attempt description"
```

The guard is a sanity check, not a second optimizer target. If the primary
improves but the guard weakens materially, reject the idea unless there is a
clear quant reason to diagnose it.

Do not run full promotion after every idea. Use it only for serious candidates:

```bash
conda run -n quant python runner.py --promote --description "promote candidate: short description"
```

Promotion screening remains a compact robustness filter, not final validation.
A promoted candidate is ready for comprehensive validation; it is not validated
market evidence.
```

- [ ] **Step 5: Update the experiment-loop command block in `program.md`**

In the experiment loop step that currently says:

```markdown
5. Run the experiment:
   `conda run -n quant python runner.py --explore --description "short attempt description"`.
   When promotion is enabled, a scored explore should auto-run promotion
   screening; treat the promotion decision as the best-so-far gate for this
   workbench.
   If exploration does not auto-confirm but the trade evidence justifies a
   candidate check, run
   `conda run -n quant python runner.py --confirm --description "candidate confirmation"`.
```

replace it with:

```markdown
5. Run the cheap screen:
   `conda run -n quant python runner.py --explore --description "short attempt description"`.
   If the primary result is plausible, run the fixed guard:
   `conda run -n quant python runner.py --window-id validation_2025_h1 --description "fixed guard: short attempt description"`.
   If both support a serious candidate with a clear quant rationale, run:
   `conda run -n quant python runner.py --promote --description "promote candidate: short description"`.
   Do not run full promotion after every idea.
```

- [ ] **Step 6: Update `AGENTS.md` target wording**

Change:

```markdown
The goal is to iterate on one scratch strategy, run compact promotion screening,
and send only promoted candidates to comprehensive validation.
```

to:

```markdown
The goal is to iterate on one scratch strategy with a cheap guard screen, run
deliberate promotion screening only for serious candidates, and send only
promoted candidates to comprehensive validation.
```

Change:

```markdown
- Promotion screening is loop feedback, not market evidence.
```

to:

```markdown
- The cheap guard screen and deliberate promotion screening are loop feedback,
  not market evidence.
```

- [ ] **Step 7: Run docs contract tests**

Run:

```bash
conda run -n quant pytest tests/test_program_contract.py tests/test_agents_contract.py -q
```

Expected: pass.

- [ ] **Step 8: Commit docs**

Run:

```bash
git add program.md AGENTS.md tests/test_program_contract.py tests/test_agents_contract.py
git commit -m "Document cheap guard research protocol"
```

## Task 5: Full Verification

**Files:**
- No code edits.

- [ ] **Step 1: Run focused tests for changed behavior**

Run:

```bash
conda run -n quant pytest \
  tests/test_runner.py::test_scored_explore_with_auto_promotion_disabled_stays_single_window \
  tests/test_runner.py::test_explicit_promote_runs_full_promotion_when_auto_promotion_is_disabled \
  tests/test_runner.py::test_explicit_promote_requires_promotion_enabled_before_running \
  tests/test_runner.py::test_explicit_promote_with_unscored_primary_does_not_run_promotion \
  tests/test_runner.py::test_scored_explore_runs_promotion_without_rerunning_primary \
  tests/test_runner.py::test_main_rejects_window_id_combined_with_research_modes \
  tests/test_program_contract.py \
  tests/test_agents_contract.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Run the related module tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py tests/test_experiment_config.py tests/test_promotion.py -q
```

Expected: all pass.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git diff --stat HEAD~3..HEAD
git status --short
```

Expected:

- commits are limited to runner/tests, config, and docs/contracts,
- no generated `results/` or `results.tsv` changes are staged,
- only pre-existing untracked local/tooling paths remain.

- [ ] **Step 4: Report outcome**

Report:

- `--explore` no longer auto-runs full promotion in the active config,
- `--promote` runs the existing promotion screen explicitly,
- `program.md` now tells the LLM to use `locked_recent_2026` plus `validation_2025_h1` before promotion,
- tests run and any residual risk.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | not run | No CEO review required for this small harness/process change |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | not run | Outside voice skipped; review stayed plan-local |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 4 | clear | 4 issues, 0 critical gaps; scope reduced to compact docs, fail-fast CLI, and full branch coverage |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | not applicable | No UI changes |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | not run | CLI behavior reviewed inside Eng Review |

- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED - ready to implement.
