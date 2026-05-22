# Quant Autoresearch Research Process Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recent-window confirmation, balanced candidate scoring, compact trade attribution, and artifact retention controls so the autoresearch loop rewards robust quant research instead of one-window optimization.

**Architecture:** Extend `experiment_config.py` with research, confirmation-scoring, and artifact policy config objects. Add focused scoring/attribution/artifact helpers, then update `runner.py` so explore/diagnostic runs remain single-window while confirmation runs execute a configured recent-window bundle and update best confirmed state only from aggregate candidate scores. Keep `program.md` concise and explicit; keep execution-engine upgrades out of this repository.

**Tech Stack:** Python 3.12 standard library (`dataclasses`, `statistics`, `concurrent.futures`, `csv`, `json`, `pathlib`, `argparse`, `shutil`), existing `quant_strategies.runner.run_config`, `pytest`.

---

## File Structure

Create or modify these files:

- Modify `experiment_config.py`
  - Own parsing and validation for `[research]`, `[confirmation_scoring]`, and `[artifacts]`.
  - Keep runner-TOML materialization focused on per-window `quant_strategies` input.
- Modify `scoring.py`
  - Keep existing per-window `build_score`.
  - Add candidate-level scoring models/functions.
  - Add trade-attribution helpers derived from existing `evidence.json` trades.
- Create `artifact_policy.py`
  - Own compact/debug artifact retention after each runner window completes.
  - Keep file deletion/compression separate from scoring and runner orchestration.
- Modify `runner.py`
  - Add CLI modes `--explore`, `--confirm`, and `--artifact-profile`.
  - Add run-kind semantics: `explore`, `confirm`, `diagnostic`.
  - Add bounded parallel confirmation orchestration.
  - Add candidate-level artifact writing and session state updates.
  - Extend ledger schema while preserving old rows.
- Modify `program.md`
  - Add explicit rules: one-window result is exploration only; confirmation controls best-so-far; trade evidence must justify changes.
  - Do not include exact weights, worker counts, or attempt counts.
- Modify `experiment.toml`
  - Add default `[research]`, `[confirmation_scoring]`, and `[artifacts]` sections.
- Modify `tests/test_experiment_config.py`
  - Config parsing and validation coverage.
- Modify `tests/test_scoring.py`
  - Candidate score and trade attribution tests.
- Create `tests/test_artifact_policy.py`
  - Compact/debug artifact retention tests.
- Modify `tests/test_runner.py`
  - Explore/confirm/diagnostic mode, parallel confirmation, session state, ledger, and failure handling tests.
- Modify `tests/test_program_contract.py`
  - Protocol wording tests for confirmation and trade evidence.

Do not modify `quant_strategies`; engine/fill/drawdown upgrades belong there.

---

### Task 1: Parse Research, Confirmation Scoring, And Artifact Config

**Files:**
- Modify: `experiment_config.py`
- Modify: `tests/test_experiment_config.py`

- [ ] **Step 1: Write failing config parsing tests**

Append these tests to `tests/test_experiment_config.py`:

```python
def test_load_experiment_config_parses_research_confirmation_and_artifacts(tmp_path: Path):
    config_text = VALID_TOML + """

[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 4
confirm_on_explore_keep = true

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 200
low_trade_penalty = 0.001
min_symbol_count = 4
symbol_concentration_penalty = 0.00025

[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
"""

    config = load_experiment_config(write_config(tmp_path, config_text))

    assert config.research.mode == "explore"
    assert config.research.primary_window_id == "primary"
    assert config.research.confirmation_window_ids == ("primary", "holdout")
    assert config.research.parallel_workers == 4
    assert config.research.confirm_on_explore_keep is True
    assert config.confirmation_scoring.primary_metric == "net_return_per_day"
    assert config.confirmation_scoring.dispersion_weight == 0.5
    assert config.confirmation_scoring.weak_window_floor == 0.0
    assert config.confirmation_scoring.weak_window_penalty == 0.001
    assert config.confirmation_scoring.min_trades_per_window == 200
    assert config.confirmation_scoring.low_trade_penalty == 0.001
    assert config.confirmation_scoring.min_symbol_count == 4
    assert config.confirmation_scoring.symbol_concentration_penalty == 0.00025
    assert config.artifacts.profile == "research"
    assert config.artifacts.keep_input_rows_csv is False
    assert config.artifacts.keep_input_rows_jsonl is False
    assert config.artifacts.keep_signals is True
    assert config.artifacts.large_artifact_max_mb == 100
```

Append validation tests:

```python
@pytest.mark.parametrize("mode", ["fast", "confirm-all", ""])
def test_load_experiment_config_rejects_invalid_research_mode(tmp_path: Path, mode: str):
    bad = VALID_TOML + f"""

[research]
mode = "{mode}"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 4
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="research.mode"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_unknown_confirmation_window(tmp_path: Path):
    bad = VALID_TOML + """

[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "missing"]
parallel_workers = 4
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="confirmation_window_ids"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_invalid_parallel_workers(tmp_path: Path):
    bad = VALID_TOML + """

[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 0
confirm_on_explore_keep = true
"""

    with pytest.raises(ConfigError, match="parallel_workers"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_invalid_artifact_profile(tmp_path: Path):
    bad = VALID_TOML + """

[artifacts]
profile = "everything"
"""

    with pytest.raises(ConfigError, match="artifacts.profile"):
        load_experiment_config(write_config(tmp_path, bad))
```

- [ ] **Step 2: Run the config tests and verify they fail**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py -q
```

Expected: fail because `ExperimentConfig` does not expose `research`, `confirmation_scoring`, or `artifacts`.

- [ ] **Step 3: Add config dataclasses**

In `experiment_config.py`, add these dataclasses after `ScoringConfig`:

```python
@dataclass(frozen=True)
class ResearchConfig:
    mode: str
    primary_window_id: str
    confirmation_window_ids: tuple[str, ...]
    parallel_workers: int
    confirm_on_explore_keep: bool


@dataclass(frozen=True)
class ConfirmationScoringConfig:
    primary_metric: str
    dispersion_weight: float
    weak_window_floor: float
    weak_window_penalty: float
    min_trades_per_window: int
    low_trade_penalty: float
    min_symbol_count: int
    symbol_concentration_penalty: float


@dataclass(frozen=True)
class ArtifactConfig:
    profile: str
    keep_strategy_snapshot: bool
    keep_config: bool
    keep_summary: bool
    keep_evidence: bool
    keep_signals: bool
    keep_engine_request: bool
    keep_input_rows_csv: bool
    keep_input_rows_jsonl: bool
    compress_large_artifacts: bool
    large_artifact_max_mb: int
```

Extend `ExperimentConfig`:

```python
    research: ResearchConfig
    confirmation_scoring: ConfirmationScoringConfig
    artifacts: ArtifactConfig
```

- [ ] **Step 4: Add parser helpers**

In `experiment_config.py`, add these helpers before `_required_table`:

```python
def _parse_research(raw: dict[str, Any], window_ids: set[str], selected_window_id: str) -> ResearchConfig:
    table = raw.get("research")
    if table is None:
        return ResearchConfig(
            mode="explore",
            primary_window_id=selected_window_id,
            confirmation_window_ids=(selected_window_id,),
            parallel_workers=1,
            confirm_on_explore_keep=False,
        )
    if not isinstance(table, dict):
        raise ConfigError("research must be a table")

    mode = _required_str(table, "mode", table="research")
    if mode not in {"explore", "confirm"}:
        raise ConfigError("research.mode must be explore or confirm")

    primary_window_id = _required_str(table, "primary_window_id", table="research")
    if primary_window_id not in window_ids:
        raise ConfigError(f"research.primary_window_id does not match a configured window: {primary_window_id}")

    raw_confirmation_ids = table.get("confirmation_window_ids")
    if not isinstance(raw_confirmation_ids, list) or not raw_confirmation_ids:
        raise ConfigError("research.confirmation_window_ids must be a non-empty list")
    confirmation_window_ids = tuple(_list_item_str(raw_confirmation_ids, "research.confirmation_window_ids"))
    unknown = [window_id for window_id in confirmation_window_ids if window_id not in window_ids]
    if unknown:
        raise ConfigError(f"research.confirmation_window_ids contains unknown windows: {unknown}")

    parallel_workers = _required_positive_int(table, "parallel_workers", table="research")
    if parallel_workers > len(confirmation_window_ids):
        parallel_workers = len(confirmation_window_ids)
    confirm_on_explore_keep = _required_bool(table, "confirm_on_explore_keep", table="research")

    return ResearchConfig(
        mode=mode,
        primary_window_id=primary_window_id,
        confirmation_window_ids=confirmation_window_ids,
        parallel_workers=parallel_workers,
        confirm_on_explore_keep=confirm_on_explore_keep,
    )


def _parse_confirmation_scoring(raw: dict[str, Any]) -> ConfirmationScoringConfig:
    table = raw.get("confirmation_scoring")
    if table is None:
        return ConfirmationScoringConfig(
            primary_metric="net_return_per_day",
            dispersion_weight=0.5,
            weak_window_floor=0.0,
            weak_window_penalty=0.001,
            min_trades_per_window=200,
            low_trade_penalty=0.001,
            min_symbol_count=4,
            symbol_concentration_penalty=0.00025,
        )
    if not isinstance(table, dict):
        raise ConfigError("confirmation_scoring must be a table")

    primary_metric = _required_str(table, "primary_metric", table="confirmation_scoring")
    if primary_metric != "net_return_per_day":
        raise ConfigError("confirmation_scoring.primary_metric must be net_return_per_day")

    return ConfirmationScoringConfig(
        primary_metric=primary_metric,
        dispersion_weight=_required_non_negative_float(table, "dispersion_weight", table="confirmation_scoring"),
        weak_window_floor=float(_required_number(table, "weak_window_floor", table="confirmation_scoring")),
        weak_window_penalty=_required_non_negative_float(table, "weak_window_penalty", table="confirmation_scoring"),
        min_trades_per_window=_required_positive_int(table, "min_trades_per_window", table="confirmation_scoring"),
        low_trade_penalty=_required_non_negative_float(table, "low_trade_penalty", table="confirmation_scoring"),
        min_symbol_count=_required_positive_int(table, "min_symbol_count", table="confirmation_scoring"),
        symbol_concentration_penalty=_required_non_negative_float(
            table,
            "symbol_concentration_penalty",
            table="confirmation_scoring",
        ),
    )


def _parse_artifacts(raw: dict[str, Any]) -> ArtifactConfig:
    table = raw.get("artifacts")
    if table is None:
        return ArtifactConfig(
            profile="research",
            keep_strategy_snapshot=True,
            keep_config=True,
            keep_summary=True,
            keep_evidence=True,
            keep_signals=True,
            keep_engine_request=False,
            keep_input_rows_csv=False,
            keep_input_rows_jsonl=False,
            compress_large_artifacts=False,
            large_artifact_max_mb=100,
        )
    if not isinstance(table, dict):
        raise ConfigError("artifacts must be a table")

    profile = _required_str(table, "profile", table="artifacts")
    if profile not in {"research", "debug"}:
        raise ConfigError("artifacts.profile must be research or debug")

    return ArtifactConfig(
        profile=profile,
        keep_strategy_snapshot=_required_bool(table, "keep_strategy_snapshot", table="artifacts"),
        keep_config=_required_bool(table, "keep_config", table="artifacts"),
        keep_summary=_required_bool(table, "keep_summary", table="artifacts"),
        keep_evidence=_required_bool(table, "keep_evidence", table="artifacts"),
        keep_signals=_required_bool(table, "keep_signals", table="artifacts"),
        keep_engine_request=_required_bool(table, "keep_engine_request", table="artifacts"),
        keep_input_rows_csv=_required_bool(table, "keep_input_rows_csv", table="artifacts"),
        keep_input_rows_jsonl=_required_bool(table, "keep_input_rows_jsonl", table="artifacts"),
        compress_large_artifacts=_required_bool(table, "compress_large_artifacts", table="artifacts"),
        large_artifact_max_mb=_required_positive_int(table, "large_artifact_max_mb", table="artifacts"),
    )
```

Add scalar helpers:

```python
def _required_bool(raw: dict[str, Any], key: str, *, table: str | None = None) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"missing required boolean field: {_field_name(key, table)}")
    return value


def _required_non_negative_float(raw: dict[str, Any], key: str, *, table: str | None = None) -> float:
    value = _required_number(raw, key, table=table)
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise ConfigError(f"{_field_name(key, table)} must be finite and non-negative")
    return parsed


def _list_item_str(values: list[Any], field_name: str) -> list[str]:
    parsed: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or value == "":
            raise ConfigError(f"{field_name}[{index}] must be a non-empty string")
        parsed.append(value)
    return parsed
```

- [ ] **Step 5: Wire parsers into `load_experiment_config`**

In `load_experiment_config`, after `window_ids` is built and `active_window_id` is validated, add:

```python
    selected_window_id = active_window_id or windows[0].id
    research = _parse_research(raw, window_ids, selected_window_id)
    confirmation_scoring = _parse_confirmation_scoring(raw)
    artifacts = _parse_artifacts(raw)
```

In the `ExperimentConfig(...)` return, include:

```python
        research=research,
        confirmation_scoring=confirmation_scoring,
        artifacts=artifacts,
```

- [ ] **Step 6: Run config tests**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add experiment_config.py tests/test_experiment_config.py
git commit -m "Parse research process config"
```

---

### Task 2: Add Candidate Scoring

**Files:**
- Modify: `scoring.py`
- Modify: `tests/test_scoring.py`

- [ ] **Step 1: Write failing candidate scoring tests**

Append to `tests/test_scoring.py`:

```python
from experiment_config import ConfirmationScoringConfig
from scoring import build_candidate_score


def confirmation_config() -> ConfirmationScoringConfig:
    return ConfirmationScoringConfig(
        primary_metric="net_return_per_day",
        dispersion_weight=0.5,
        weak_window_floor=0.0,
        weak_window_penalty=0.001,
        min_trades_per_window=200,
        low_trade_penalty=0.001,
        min_symbol_count=4,
        symbol_concentration_penalty=0.00025,
    )


def window_score(
    window_id: str,
    score: float | None,
    *,
    raw_net_return: float | None = None,
    trade_count: int | None = 250,
    symbol_count: int | None = 5,
    status: str = "scored",
) -> dict[str, object]:
    return {
        "window_id": window_id,
        "window_start": "2025-01-01",
        "window_end": "2025-06-29",
        "window_days": 180,
        "score": score,
        "raw_net_return": raw_net_return if raw_net_return is not None else (score * 180 if score is not None else None),
        "trade_count": trade_count,
        "symbol_count": symbol_count,
        "status": status,
        "failed_gates": [],
        "failure_source": None,
    }


def test_build_candidate_score_rewards_recent_mean_and_records_components():
    payload = build_candidate_score(
        window_scores=[
            window_score("validation_2025_h1", 0.0010),
            window_score("validation_2025_h2", 0.0020),
            window_score("locked_recent_2026", 0.0030),
        ],
        config=confirmation_config(),
        commit="abc1234",
        description="candidate",
    )

    assert payload["status"] == "scored"
    assert payload["commit"] == "abc1234"
    assert payload["description"] == "candidate"
    assert payload["recent_mean_score"] == pytest.approx(0.0020)
    assert payload["recent_median_score"] == pytest.approx(0.0020)
    assert payload["worst_recent_score"] == pytest.approx(0.0010)
    assert payload["total_trade_count"] == 750
    assert payload["min_window_trade_count"] == 250
    assert payload["symbol_count"] == 5
    assert payload["passed_windows"] == ["validation_2025_h1", "validation_2025_h2", "locked_recent_2026"]
    assert payload["failed_windows"] == []
    assert payload["candidate_score"] < payload["recent_mean_score"]
    assert payload["penalties"]["dispersion"] > 0.0
    assert payload["penalties"]["weak_windows"] == 0.0
    assert payload["penalties"]["low_trades"] == 0.0
    assert payload["penalties"]["symbol_concentration"] == 0.0


def test_build_candidate_score_penalizes_weak_low_trade_and_narrow_universe():
    payload = build_candidate_score(
        window_scores=[
            window_score("validation_2025_h1", 0.0010, trade_count=250, symbol_count=3),
            window_score("validation_2025_h2", -0.0005, trade_count=100, symbol_count=3),
            window_score("locked_recent_2026", 0.0020, trade_count=250, symbol_count=3),
        ],
        config=confirmation_config(),
        commit="abc1234",
        description="candidate",
    )

    assert payload["status"] == "scored"
    assert payload["failed_windows"] == ["validation_2025_h2"]
    assert payload["min_window_trade_count"] == 100
    assert payload["symbol_count"] == 3
    assert payload["penalties"]["weak_windows"] == pytest.approx(0.001)
    assert payload["penalties"]["low_trades"] == pytest.approx(0.001)
    assert payload["penalties"]["symbol_concentration"] == pytest.approx(0.00025)


def test_build_candidate_score_invalidates_missing_numeric_window_score():
    payload = build_candidate_score(
        window_scores=[
            window_score("validation_2025_h1", 0.0010),
            window_score("validation_2025_h2", None, status="runner_failed"),
            window_score("locked_recent_2026", 0.0020),
        ],
        config=confirmation_config(),
        commit="abc1234",
        description="candidate",
    )

    assert payload["status"] == "confirmation_failed"
    assert payload["candidate_score"] is None
    assert payload["failed_windows"] == ["validation_2025_h2"]
```

- [ ] **Step 2: Run scoring tests and verify they fail**

Run:

```bash
conda run -n quant pytest tests/test_scoring.py -q
```

Expected: fail because `build_candidate_score` does not exist.

- [ ] **Step 3: Implement candidate scoring**

In `scoring.py`, import:

```python
import statistics
from experiment_config import ConfirmationScoringConfig
```

Add:

```python
def build_candidate_score(
    *,
    window_scores: list[dict[str, Any]],
    config: ConfirmationScoringConfig,
    commit: str | None,
    description: str,
) -> dict[str, Any]:
    numeric_scores: list[float] = []
    failed_windows: list[str] = []
    passed_windows: list[str] = []
    trade_counts: list[int] = []
    symbol_counts: list[int] = []

    for score in window_scores:
        window_id = _as_str_or_none(score.get("window_id")) or ""
        value = _as_float_or_none(score.get("score"))
        trade_count = _as_int_or_none(score.get("trade_count"))
        symbol_count = _as_int_or_none(score.get("symbol_count"))
        if trade_count is not None:
            trade_counts.append(trade_count)
        if symbol_count is not None:
            symbol_counts.append(symbol_count)
        if value is None:
            failed_windows.append(window_id)
            continue
        numeric_scores.append(value)
        if value <= config.weak_window_floor:
            failed_windows.append(window_id)
        else:
            passed_windows.append(window_id)

    if len(numeric_scores) != len(window_scores):
        return _candidate_payload(
            status="confirmation_failed",
            candidate_score=None,
            window_scores=window_scores,
            commit=commit,
            description=description,
            recent_mean_score=None,
            recent_median_score=None,
            worst_recent_score=None,
            score_dispersion=None,
            total_trade_count=sum(trade_counts),
            min_window_trade_count=min(trade_counts) if trade_counts else None,
            symbol_count=min(symbol_counts) if symbol_counts else None,
            passed_windows=passed_windows,
            failed_windows=failed_windows,
            penalties={
                "dispersion": None,
                "weak_windows": None,
                "low_trades": None,
                "symbol_concentration": None,
            },
        )

    recent_mean_score = statistics.fmean(numeric_scores)
    recent_median_score = statistics.median(numeric_scores)
    worst_recent_score = min(numeric_scores)
    score_dispersion = statistics.pstdev(numeric_scores) if len(numeric_scores) > 1 else 0.0
    min_window_trade_count = min(trade_counts) if trade_counts else None
    symbol_count = min(symbol_counts) if symbol_counts else None

    weak_window_count = sum(1 for value in numeric_scores if value <= config.weak_window_floor)
    low_trade_count = sum(1 for value in trade_counts if value < config.min_trades_per_window)
    symbol_concentration = (
        config.symbol_concentration_penalty
        if symbol_count is not None and symbol_count < config.min_symbol_count
        else 0.0
    )
    penalties = {
        "dispersion": score_dispersion * config.dispersion_weight,
        "weak_windows": weak_window_count * config.weak_window_penalty,
        "low_trades": low_trade_count * config.low_trade_penalty,
        "symbol_concentration": symbol_concentration,
    }
    candidate_score = recent_mean_score - sum(penalties.values())

    return _candidate_payload(
        status="scored",
        candidate_score=candidate_score,
        window_scores=window_scores,
        commit=commit,
        description=description,
        recent_mean_score=recent_mean_score,
        recent_median_score=recent_median_score,
        worst_recent_score=worst_recent_score,
        score_dispersion=score_dispersion,
        total_trade_count=sum(trade_counts),
        min_window_trade_count=min_window_trade_count,
        symbol_count=symbol_count,
        passed_windows=passed_windows,
        failed_windows=failed_windows,
        penalties=penalties,
    )
```

Add helper:

```python
def _candidate_payload(
    *,
    status: str,
    candidate_score: float | None,
    window_scores: list[dict[str, Any]],
    commit: str | None,
    description: str,
    recent_mean_score: float | None,
    recent_median_score: float | None,
    worst_recent_score: float | None,
    score_dispersion: float | None,
    total_trade_count: int,
    min_window_trade_count: int | None,
    symbol_count: int | None,
    passed_windows: list[str],
    failed_windows: list[str],
    penalties: dict[str, float | None],
) -> dict[str, Any]:
    return {
        "status": status,
        "candidate_score": candidate_score,
        "metric": "balanced_recent_net_return_per_day",
        "commit": commit,
        "description": _single_line(description),
        "recent_mean_score": recent_mean_score,
        "recent_median_score": recent_median_score,
        "worst_recent_score": worst_recent_score,
        "score_dispersion": score_dispersion,
        "total_trade_count": total_trade_count,
        "min_window_trade_count": min_window_trade_count,
        "symbol_count": symbol_count,
        "passed_windows": passed_windows,
        "failed_windows": failed_windows,
        "penalties": penalties,
        "window_scores": window_scores,
        "notes": NOTES,
    }


def _single_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")
```

- [ ] **Step 4: Run scoring tests**

Run:

```bash
conda run -n quant pytest tests/test_scoring.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add scoring.py tests/test_scoring.py
git commit -m "Add candidate confirmation scoring"
```

---

### Task 3: Add Trade Attribution

**Files:**
- Modify: `scoring.py`
- Modify: `tests/test_scoring.py`

- [ ] **Step 1: Write failing trade attribution tests**

Append to `tests/test_scoring.py`:

```python
from scoring import build_trade_attribution


def trade(symbol: str, side: str, decision_time: str, net: float, gross: float, funding: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "side": side,
        "decision_time": decision_time,
        "exit_time": decision_time,
        "gross_return": gross,
        "funding_return": funding,
        "cost_return": 0.0,
        "net_return": net,
    }


def test_build_trade_attribution_groups_trade_evidence():
    evidence_by_window = {
        "validation_2025_h1": {
            "validation_report": {
                "screening_result": {
                    "trades": [
                        trade("ETH-PERP", "short", "2025-01-02T08:01:00Z", 0.01, 0.009, 0.001),
                        trade("ETH-PERP", "long", "2025-01-02T12:01:00Z", -0.02, -0.019, -0.001),
                    ]
                }
            }
        },
        "locked_recent_2026": {
            "validation_report": {
                "screening_result": {
                    "trades": [
                        trade("ADA-PERP", "short", "2026-01-02T08:01:00Z", 0.03, 0.029, 0.001),
                    ]
                }
            }
        },
    }

    attribution = build_trade_attribution(evidence_by_window)

    assert attribution["total_trade_count"] == 3
    assert attribution["by_window"]["validation_2025_h1"]["trade_count"] == 2
    assert attribution["by_window"]["validation_2025_h1"]["net_return"] == pytest.approx(-0.01)
    assert attribution["by_symbol"]["ETH-PERP"]["trade_count"] == 2
    assert attribution["by_side"]["short"]["net_return"] == pytest.approx(0.04)
    assert attribution["by_decision_hour"]["08"]["trade_count"] == 2
    assert attribution["by_month"]["2025-01"]["net_return"] == pytest.approx(-0.01)
    assert attribution["by_symbol_side"]["ETH-PERP|long"]["net_return"] == pytest.approx(-0.02)
    assert attribution["by_window_side"]["locked_recent_2026|short"]["net_return"] == pytest.approx(0.03)
    assert attribution["by_window_hour"]["validation_2025_h1|12"]["net_return"] == pytest.approx(-0.02)
```

- [ ] **Step 2: Run scoring tests and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_scoring.py::test_build_trade_attribution_groups_trade_evidence -q
```

Expected: fail because `build_trade_attribution` does not exist.

- [ ] **Step 3: Implement attribution helpers**

In `scoring.py`, add:

```python
def build_trade_attribution(evidence_by_window: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    groups: dict[str, dict[str, dict[str, float | int]]] = {
        "by_window": {},
        "by_symbol": {},
        "by_side": {},
        "by_decision_hour": {},
        "by_month": {},
        "by_symbol_side": {},
        "by_window_side": {},
        "by_window_hour": {},
    }
    total_trade_count = 0

    for window_id, evidence in evidence_by_window.items():
        for trade in _trades_from_evidence(evidence):
            total_trade_count += 1
            symbol = str(trade.get("symbol", ""))
            side = str(trade.get("side", ""))
            decision_time = str(trade.get("decision_time", ""))
            hour = _iso_hour(decision_time)
            month = _iso_month(decision_time)

            keys = {
                "by_window": window_id,
                "by_symbol": symbol,
                "by_side": side,
                "by_decision_hour": hour,
                "by_month": month,
                "by_symbol_side": f"{symbol}|{side}",
                "by_window_side": f"{window_id}|{side}",
                "by_window_hour": f"{window_id}|{hour}",
            }
            for group_name, group_key in keys.items():
                _add_trade_to_group(groups[group_name], group_key, trade)

    return {
        "total_trade_count": total_trade_count,
        **groups,
    }


def _trades_from_evidence(evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    if evidence is None:
        return []
    validation_report = evidence.get("validation_report")
    if not isinstance(validation_report, dict):
        return []
    screening_result = validation_report.get("screening_result")
    if not isinstance(screening_result, dict):
        return []
    trades = screening_result.get("trades")
    if not isinstance(trades, list):
        return []
    return [trade for trade in trades if isinstance(trade, dict)]


def _add_trade_to_group(group: dict[str, dict[str, float | int]], key: str, trade: dict[str, Any]) -> None:
    row = group.setdefault(
        key,
        {
            "trade_count": 0,
            "gross_return": 0.0,
            "funding_return": 0.0,
            "cost_return": 0.0,
            "net_return": 0.0,
            "average_net_per_trade": 0.0,
            "score_contribution": 0.0,
        },
    )
    row["trade_count"] = int(row["trade_count"]) + 1
    row["gross_return"] = float(row["gross_return"]) + _trade_float(trade.get("gross_return"))
    row["funding_return"] = float(row["funding_return"]) + _trade_float(trade.get("funding_return"))
    row["cost_return"] = float(row["cost_return"]) + _trade_float(trade.get("cost_return"))
    row["net_return"] = float(row["net_return"]) + _trade_float(trade.get("net_return"))
    row["average_net_per_trade"] = float(row["net_return"]) / int(row["trade_count"])
    row["score_contribution"] = float(row["net_return"])


def _trade_float(value: object) -> float:
    parsed = _as_float_or_none(value)
    return 0.0 if parsed is None else parsed


def _iso_hour(value: str) -> str:
    return value[11:13] if len(value) >= 13 else ""


def _iso_month(value: str) -> str:
    return value[:7] if len(value) >= 7 else ""
```

- [ ] **Step 4: Run scoring tests**

Run:

```bash
conda run -n quant pytest tests/test_scoring.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add scoring.py tests/test_scoring.py
git commit -m "Add trade evidence attribution"
```

---

### Task 4: Add Artifact Policy Module

**Files:**
- Create: `artifact_policy.py`
- Create: `tests/test_artifact_policy.py`

- [ ] **Step 1: Write failing artifact policy tests**

Create `tests/test_artifact_policy.py`:

```python
from __future__ import annotations

from pathlib import Path

from artifact_policy import apply_artifact_policy
from experiment_config import ArtifactConfig


def research_policy() -> ArtifactConfig:
    return ArtifactConfig(
        profile="research",
        keep_strategy_snapshot=True,
        keep_config=True,
        keep_summary=True,
        keep_evidence=True,
        keep_signals=True,
        keep_engine_request=False,
        keep_input_rows_csv=False,
        keep_input_rows_jsonl=False,
        compress_large_artifacts=False,
        large_artifact_max_mb=100,
    )


def debug_policy() -> ArtifactConfig:
    return ArtifactConfig(
        profile="debug",
        keep_strategy_snapshot=True,
        keep_config=True,
        keep_summary=True,
        keep_evidence=True,
        keep_signals=True,
        keep_engine_request=True,
        keep_input_rows_csv=True,
        keep_input_rows_jsonl=True,
        compress_large_artifacts=False,
        large_artifact_max_mb=100,
    )


def write_artifacts(result_dir: Path) -> None:
    result_dir.mkdir()
    for name in (
        "config.toml",
        "summary.json",
        "evidence.json",
        "signals.csv",
        "strategy_snapshot.py",
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ):
        (result_dir / name).write_text(name + "\n")


def test_apply_artifact_policy_removes_large_debug_inputs_for_research_profile(tmp_path: Path):
    result_dir = tmp_path / "attempt"
    write_artifacts(result_dir)

    removed = apply_artifact_policy(result_dir, research_policy())

    assert sorted(removed) == [
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ]
    assert (result_dir / "config.toml").exists()
    assert (result_dir / "summary.json").exists()
    assert (result_dir / "evidence.json").exists()
    assert (result_dir / "signals.csv").exists()
    assert (result_dir / "strategy_snapshot.py").exists()
    assert not (result_dir / "engine_request.json").exists()
    assert not (result_dir / "strategy_input_rows.csv").exists()
    assert not (result_dir / "strategy_input_rows.jsonl").exists()


def test_apply_artifact_policy_keeps_debug_profile_artifacts(tmp_path: Path):
    result_dir = tmp_path / "attempt"
    write_artifacts(result_dir)

    removed = apply_artifact_policy(result_dir, debug_policy())

    assert removed == []
    assert (result_dir / "engine_request.json").exists()
    assert (result_dir / "strategy_input_rows.csv").exists()
    assert (result_dir / "strategy_input_rows.jsonl").exists()
```

- [ ] **Step 2: Run artifact tests and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_artifact_policy.py -q
```

Expected: fail because `artifact_policy.py` does not exist.

- [ ] **Step 3: Implement artifact policy**

Create `artifact_policy.py`:

```python
from __future__ import annotations

from pathlib import Path

from experiment_config import ArtifactConfig


_OPTIONAL_ARTIFACTS = {
    "engine_request.json": "keep_engine_request",
    "strategy_input_rows.csv": "keep_input_rows_csv",
    "strategy_input_rows.jsonl": "keep_input_rows_jsonl",
}


def apply_artifact_policy(result_dir: Path, config: ArtifactConfig) -> list[str]:
    removed: list[str] = []
    if config.profile == "debug":
        return removed

    for filename, flag_name in _OPTIONAL_ARTIFACTS.items():
        keep = bool(getattr(config, flag_name))
        path = result_dir / filename
        if keep or not path.exists():
            continue
        path.unlink()
        removed.append(filename)

    return removed
```

- [ ] **Step 4: Run artifact tests**

Run:

```bash
conda run -n quant pytest tests/test_artifact_policy.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add artifact_policy.py tests/test_artifact_policy.py
git commit -m "Add research artifact retention policy"
```

---

### Task 5: Extend Program Protocol And Default Config

**Files:**
- Modify: `program.md`
- Modify: `experiment.toml`
- Modify: `tests/test_program_contract.py`
- Modify: `tests/test_experiment_config.py`

- [ ] **Step 1: Write failing program contract test**

Append to `tests/test_program_contract.py`:

```python
def test_program_requires_confirmation_before_best_so_far_and_trade_evidence():
    text = PROGRAM.read_text()

    required = [
        "A one-window result is exploration evidence only",
        "Only confirmed candidates can become best-so-far",
        "Confirmation means running the configured recent window bundle",
        "Recent windows dominate the score",
        "Do not prune symbols or windows because of one isolated result",
        "what trade evidence changed your belief",
        "what causal hypothesis follows",
        "what result would falsify it",
    ]
    for phrase in required:
        assert phrase in text
```

- [ ] **Step 2: Run program contract test and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_program_contract.py::test_program_requires_confirmation_before_best_so_far_and_trade_evidence -q
```

Expected: fail until `program.md` is updated.

- [ ] **Step 3: Add protocol wording to `program.md`**

In `program.md`, replace the single-window keep language in "The experiment loop" with explicit confirmation language:

```markdown
## Candidate confirmation

A one-window result is exploration evidence only. Only confirmed candidates can
become best-so-far.

Confirmation means running the configured recent window bundle. Recent windows
dominate the score. Older windows are diagnostic or stress evidence unless
`experiment.toml` says otherwise.

Do not prune symbols or windows because of one isolated result. If a candidate
improves one window but weakens the recent bundle, discard it.

Before changing `strategy.py` or `experiment.toml`, explain what trade evidence
changed your belief, what causal hypothesis follows, what focused change tests
it, and what result would falsify it.
```

Keep the editable/read-only file lists unchanged.

- [ ] **Step 4: Add default config sections to `experiment.toml`**

Append to `experiment.toml` after `[scoring]`:

```toml
[research]
mode = "explore"
primary_window_id = "locked_recent_2026"
confirmation_window_ids = [
  "validation_2025_h1",
  "validation_2025_h2",
  "locked_recent_2026",
]
parallel_workers = 4
confirm_on_explore_keep = true

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 200
low_trade_penalty = 0.001
min_symbol_count = 4
symbol_concentration_penalty = 0.00025

[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
```

- [ ] **Step 5: Run protocol and config tests**

Run:

```bash
conda run -n quant pytest tests/test_program_contract.py tests/test_experiment_config.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add program.md experiment.toml tests/test_program_contract.py tests/test_experiment_config.py
git commit -m "Document confirmed candidate research protocol"
```

---

### Task 6: Extend Session State And Ledger For Candidate Runs

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write failing session-state and ledger tests**

Append to `tests/test_runner.py`:

```python
def test_session_state_tracks_best_confirmed_candidate(tmp_path: Path):
    state = runner_module.SessionState(
        max_attempts=3,
        attempts_used=0,
        best_score=0.01,
        best_commit="old",
        status="active",
        best_confirmed_candidate_score=0.002,
        best_confirmed_commit="confirmed_old",
    )

    payload_path = tmp_path / "session_state.json"
    runner_module.save_session_state(payload_path, state)
    loaded = runner_module.load_session_state(
        payload_path,
        config=None,
        max_attempts_override=None,
        fallback_max_attempts=3,
    )

    assert loaded.best_score == 0.01
    assert loaded.best_commit == "old"
    assert loaded.best_confirmed_candidate_score == 0.002
    assert loaded.best_confirmed_commit == "confirmed_old"


def test_append_ledger_writes_candidate_columns(tmp_path: Path):
    score = {
        "score": 0.001,
        "raw_net_return": 0.12,
        "trade_count": 250,
    }
    candidate_score = {
        "candidate_score": 0.0008,
        "recent_mean_score": 0.0012,
        "worst_recent_score": 0.0004,
        "passed_windows": ["validation_2025_h1", "locked_recent_2026"],
        "failed_windows": ["validation_2025_h2"],
    }

    runner_module.append_ledger(
        tmp_path / "results.tsv",
        attempt=1,
        commit="abc1234",
        window_id="locked_recent_2026",
        window_start="2025-10-16",
        window_end="2026-04-13",
        window_days=180,
        symbol_count=4,
        score=score,
        status="discard",
        description="confirm",
        run_kind="confirm",
        candidate_score=candidate_score,
    )

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["run_kind"] == "confirm"
    assert rows[0]["candidate_score"] == "0.0008"
    assert rows[0]["recent_mean_score"] == "0.0012"
    assert rows[0]["worst_recent_score"] == "0.0004"
    assert rows[0]["passed_window_count"] == "2"
    assert rows[0]["failed_window_count"] == "1"
```

- [ ] **Step 2: Run runner tests and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_session_state_tracks_best_confirmed_candidate tests/test_runner.py::test_append_ledger_writes_candidate_columns -q
```

Expected: fail because the dataclass and ledger do not yet have these fields.

- [ ] **Step 3: Extend `SessionState`**

In `runner.py`, add fields:

```python
    best_confirmed_candidate_score: float | None = None
    best_confirmed_commit: str | None = None
```

Update `load_session_state` creation and loading:

```python
            best_confirmed_candidate_score=None,
            best_confirmed_commit=None,
```

and:

```python
        best_confirmed_candidate_score=_optional_float(payload.get("best_confirmed_candidate_score")),
        best_confirmed_commit=_optional_str(payload.get("best_confirmed_commit")),
```

Update `save_session_state` payload:

```python
        "best_confirmed_candidate_score": state.best_confirmed_candidate_score,
        "best_confirmed_commit": state.best_confirmed_commit,
```

- [ ] **Step 4: Extend ledger header and append API**

In `runner.py`, add to `LEDGER_HEADER`:

```python
    "run_kind",
    "candidate_score",
    "recent_mean_score",
    "worst_recent_score",
    "passed_window_count",
    "failed_window_count",
```

Add parameters to `append_ledger`:

```python
    run_kind: str = "explore",
    candidate_score: dict[str, Any] | None = None,
```

In the written row, add:

```python
                "run_kind": run_kind,
                "candidate_score": _candidate_field(candidate_score, "candidate_score"),
                "recent_mean_score": _candidate_field(candidate_score, "recent_mean_score"),
                "worst_recent_score": _candidate_field(candidate_score, "worst_recent_score"),
                "passed_window_count": _candidate_count(candidate_score, "passed_windows"),
                "failed_window_count": _candidate_count(candidate_score, "failed_windows"),
```

Add helpers:

```python
def _candidate_field(candidate_score: dict[str, Any] | None, key: str) -> str:
    if candidate_score is None:
        return ""
    value = candidate_score.get(key)
    return "" if value is None else str(value)


def _candidate_count(candidate_score: dict[str, Any] | None, key: str) -> str:
    if candidate_score is None:
        return ""
    value = candidate_score.get(key)
    if not isinstance(value, list):
        return ""
    return str(len(value))
```

Update `_ensure_ledger_schema` so `OLD_LEDGER_HEADER` and `WINDOW_LEDGER_HEADER` migrate to the new header by filling missing fields with empty strings.

- [ ] **Step 5: Run runner tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 6**

```bash
git add runner.py tests/test_runner.py
git commit -m "Track confirmed candidate state"
```

---

### Task 7: Refactor Runner To Single-Window Helper

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Add helper-level test for single-window execution**

Append to `tests/test_runner.py`:

```python
def test_run_single_window_attempt_returns_score_and_artifacts(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path)
    config = runner_module.load_experiment_config(tmp_path / "experiment.toml")
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        runner_module,
        "run_config",
        fake_success_run(tmp_path / "results", net_return=0.05),
    )

    result = runner_module.run_single_window_attempt(
        config=config,
        attempt=1,
        window_id="primary",
        results_dir=tmp_path / "results",
        description="helper run",
        commit="abc1234",
        simplification=False,
        artifact_profile=None,
    )

    assert result.window_id == "primary"
    assert result.score["score"] == pytest.approx(0.05 / 120)
    assert result.evidence is not None
    assert (result.result_dir / "score.json").exists()
    assert (result.result_dir / "attempt_metadata.json").exists()
```

- [ ] **Step 2: Run helper test and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_run_single_window_attempt_returns_score_and_artifacts -q
```

Expected: fail because `run_single_window_attempt` does not exist.

- [ ] **Step 3: Add result dataclass and helper**

In `runner.py`, add:

```python
@dataclass(frozen=True)
class WindowAttemptResult:
    window_id: str
    result_dir: Path
    score: dict[str, Any]
    summary: dict[str, Any] | None
    evidence: dict[str, Any] | None
    run_metadata: dict[str, str | int | None]
    failure_source: str | None
```

Add helper by moving the single-window body from `main` into a function:

```python
def run_single_window_attempt(
    *,
    config: ExperimentConfig,
    attempt: int,
    window_id: str,
    results_dir: Path,
    description: str,
    commit: str | None,
    simplification: bool,
    artifact_profile: str | None,
) -> WindowAttemptResult:
    run_metadata = _run_metadata(config, window_id)
    generated_config = results_dir / ".generated" / f"attempt_{attempt:04d}_{window_id}.toml"
    materialize_runner_toml(config, generated_config, window_id=window_id, results_dir=results_dir)
    result = run_config(generated_config, repo_root=ROOT)
    result_dir = result.result_dir
    if result_dir is None:
        result_dir = results_dir / f"attempt_{attempt:04d}_{window_id}_config_failed"
        result_dir.mkdir(parents=True, exist_ok=True)
    summary, evidence = _load_artifacts(result_dir, result_message=getattr(result, "message", None))
    if result.result_dir is None:
        summary = {"stage": "config", "message": getattr(result, "message", None)}
    failure_source = _failure_source(summary, evidence, getattr(result, "message", None))
    score = build_score(
        summary=summary,
        evidence=evidence,
        min_score_trades=config.scoring.min_score_trades,
        window_id=window_id,
        failure_source=failure_source,
        complexity_note="simplification" if simplification else "",
        **run_metadata,
    )
    write_score(result_dir / "score.json", score)
    write_attempt_metadata(
        result_dir / "attempt_metadata.json",
        attempt=attempt,
        commit=commit,
        window_id=window_id,
        description=description,
        generated_config=generated_config,
        failure_source=failure_source,
        **run_metadata,
    )
    return WindowAttemptResult(
        window_id=window_id,
        result_dir=result_dir,
        score=score,
        summary=summary,
        evidence=evidence,
        run_metadata=run_metadata,
        failure_source=failure_source,
    )
```

The `artifact_profile` parameter is accepted here and used in Task 9.

- [ ] **Step 4: Update `main` to use the helper**

Replace the duplicated single-window execution block in `main` with:

```python
    window_result = run_single_window_attempt(
        config=config,
        attempt=attempt,
        window_id=window_id,
        results_dir=results_dir,
        description=args.description,
        commit=commit,
        simplification=args.simplification,
        artifact_profile=args.artifact_profile,
    )
```

Pass `window_result.score`, `window_result.result_dir`, and `window_result.run_metadata` into `_finish_attempt`.

- [ ] **Step 5: Run runner tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 7**

```bash
git add runner.py tests/test_runner.py
git commit -m "Refactor runner window execution"
```

---

### Task 8: Add Explore, Diagnostic, And Confirm CLI Modes

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write failing CLI mode tests**

Append to `tests/test_runner.py`:

```python
def test_window_id_run_is_diagnostic_and_does_not_update_best_confirmed(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=2)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--window-id", "holdout", "--description", "manual"]) == 0

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert state["best_confirmed_candidate_score"] is None
    assert rows[0]["run_kind"] == "diagnostic"


def test_explore_run_uses_primary_research_window(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=2)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "holdout"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 2
confirm_on_explore_keep = false
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(runner_module, "run_config", fake_success_run(tmp_path / "results", net_return=0.05))

    assert main(["--explore", "--description", "explore"]) == 0

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["window_id"] == "holdout"
    assert rows[0]["run_kind"] == "explore"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_window_id_run_is_diagnostic_and_does_not_update_best_confirmed tests/test_runner.py::test_explore_run_uses_primary_research_window -q
```

Expected: fail because CLI flags and run kinds do not exist.

- [ ] **Step 3: Add CLI flags**

In `runner.py`, update parser:

```python
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--explore", action="store_true")
    mode_group.add_argument("--confirm", action="store_true")
    parser.add_argument("--artifact-profile", choices=("research", "debug"), default=None)
```

Add:

```python
def _run_kind(args: argparse.Namespace, config: ExperimentConfig) -> str:
    if args.confirm:
        return "confirm"
    if args.explore:
        return "explore"
    if args.window_id is not None:
        return "diagnostic"
    return config.research.mode


def _selected_single_window(args: argparse.Namespace, config: ExperimentConfig, run_kind: str) -> str:
    if args.window_id is not None:
        return args.window_id
    if run_kind == "explore":
        return config.research.primary_window_id
    return config.selected_window_id
```

- [ ] **Step 4: Wire run kind into single-window path**

In `main`, compute:

```python
    run_kind = _run_kind(args, config)
```

If `run_kind != "confirm"`, use:

```python
    window_id = _selected_single_window(args, config, run_kind)
```

Pass `run_kind=run_kind` into `_finish_attempt`, then into `append_ledger`.

- [ ] **Step 5: Run runner tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 8**

```bash
git add runner.py tests/test_runner.py
git commit -m "Add research runner modes"
```

---

### Task 9: Implement Confirmation Bundle Orchestration

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write failing confirmation orchestration test**

Append to `tests/test_runner.py`:

```python
def test_confirm_runs_all_confirmation_windows_and_writes_candidate_score(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[research]
mode = "explore"
primary_window_id = "primary"
confirmation_window_ids = ["primary", "holdout"]
parallel_workers = 2
confirm_on_explore_keep = true

[confirmation_scoring]
primary_metric = "net_return_per_day"
dispersion_weight = 0.5
weak_window_floor = 0.0
weak_window_penalty = 0.001
min_trades_per_window = 2
low_trade_penalty = 0.001
min_symbol_count = 1
symbol_concentration_penalty = 0.00025

[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        text = config_path.read_text()
        net = 0.12 if 'start = "2024-01-01"' in text else 0.24
        return fake_success_run(tmp_path / "results", net_return=net, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--confirm", "--description", "confirm candidate"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["run_kind"] == "confirm"
    assert output["candidate_score"] is not None
    candidate_dir = Path(output["result_dir"])
    assert (candidate_dir / "candidate_score.json").exists()
    assert (candidate_dir / "candidate_summary.json").exists()
    assert (candidate_dir / "trade_attribution.json").exists()

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert state["best_confirmed_candidate_score"] == pytest.approx(output["candidate_score"])
    assert state["best_confirmed_commit"] == "abc1234"

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["run_kind"] == "confirm"
    assert rows[0]["candidate_score"] != ""
    assert rows[0]["passed_window_count"] == "2"
```

- [ ] **Step 2: Run confirmation test and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_confirm_runs_all_confirmation_windows_and_writes_candidate_score -q
```

Expected: fail because confirmation orchestration does not exist.

- [ ] **Step 3: Add confirmation helpers**

In `runner.py`, import:

```python
from concurrent.futures import ThreadPoolExecutor
from scoring import build_candidate_score, build_trade_attribution
```

Add:

```python
def run_confirmation_attempt(
    *,
    config: ExperimentConfig,
    attempt: int,
    results_dir: Path,
    description: str,
    commit: str | None,
    simplification: bool,
    artifact_profile: str | None,
) -> tuple[Path, dict[str, Any], list[WindowAttemptResult]]:
    candidate_dir = results_dir / f"candidate_{attempt:04d}_{config.strategy_id}"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    def _run(window_id: str) -> WindowAttemptResult:
        window_results_dir = candidate_dir / "windows" / window_id
        return run_single_window_attempt(
            config=config,
            attempt=attempt,
            window_id=window_id,
            results_dir=window_results_dir,
            description=description,
            commit=commit,
            simplification=simplification,
            artifact_profile=artifact_profile,
        )

    workers = max(1, min(config.research.parallel_workers, len(config.research.confirmation_window_ids)))
    if workers == 1:
        window_results = [_run(window_id) for window_id in config.research.confirmation_window_ids]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            window_results = list(executor.map(_run, config.research.confirmation_window_ids))

    candidate_score = build_candidate_score(
        window_scores=[result.score for result in window_results],
        config=config.confirmation_scoring,
        commit=commit,
        description=description,
    )
    write_score(candidate_dir / "candidate_score.json", candidate_score)
    (candidate_dir / "candidate_summary.json").write_text(
        json.dumps(
            {
                "attempt": attempt,
                "commit": commit,
                "description": description,
                "window_ids": list(config.research.confirmation_window_ids),
                "candidate_score": candidate_score["candidate_score"],
                "status": candidate_score["status"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    attribution = build_trade_attribution({result.window_id: result.evidence for result in window_results})
    (candidate_dir / "trade_attribution.json").write_text(
        json.dumps(attribution, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate_dir, candidate_score, window_results
```

- [ ] **Step 4: Add confirmation finish path**

Add:

```python
def decision_for_candidate_score(candidate_score: dict[str, Any], *, state: SessionState) -> str:
    value = _numeric_score(candidate_score.get("candidate_score"))
    if value is None:
        return "discard"
    if state.best_confirmed_candidate_score is None:
        return "keep"
    return "keep" if value > state.best_confirmed_candidate_score else "discard"
```

Add:

```python
def update_state_for_candidate(
    state: SessionState,
    *,
    candidate_score: dict[str, Any],
    commit: str | None,
    decision: str,
) -> SessionState:
    attempts_used = state.attempts_used + 1
    best_confirmed_candidate_score = state.best_confirmed_candidate_score
    best_confirmed_commit = state.best_confirmed_commit
    value = _numeric_score(candidate_score.get("candidate_score"))
    if decision == "keep" and value is not None:
        best_confirmed_candidate_score = value
        best_confirmed_commit = commit
    return SessionState(
        max_attempts=state.max_attempts,
        attempts_used=attempts_used,
        best_score=state.best_score,
        best_commit=state.best_commit,
        status="exhausted" if attempts_used >= state.max_attempts else "active",
        last_decision=decision,
        best_confirmed_candidate_score=best_confirmed_candidate_score,
        best_confirmed_commit=best_confirmed_commit,
    )
```

In `main`, if `run_kind == "confirm"`, call `run_confirmation_attempt`, update state with `update_state_for_candidate`, append ledger with `run_kind="confirm"` and `candidate_score=candidate_score`, print JSON containing:

```python
{
    "attempt": attempt,
    "decision": decision,
    "run_kind": "confirm",
    "candidate_score": candidate_score["candidate_score"],
    "remaining_attempts": next_state.remaining_attempts,
    "result_dir": str(candidate_dir),
    "status": next_state.status,
}
```

- [ ] **Step 5: Run confirmation tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_confirm_runs_all_confirmation_windows_and_writes_candidate_score -q
```

Expected: pass.

- [ ] **Step 6: Run all runner tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 9**

```bash
git add runner.py tests/test_runner.py
git commit -m "Run confirmed candidates across windows"
```

---

### Task 10: Apply Artifact Policy During Runs

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Add runner-level artifact cleanup test**

Append to `tests/test_runner.py`:

```python
def test_runner_applies_research_artifact_policy(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=1)
    with (tmp_path / "experiment.toml").open("a") as handle:
        handle.write(
            """
[artifacts]
profile = "research"
keep_strategy_snapshot = true
keep_config = true
keep_summary = true
keep_evidence = true
keep_signals = true
keep_engine_request = false
keep_input_rows_csv = false
keep_input_rows_jsonl = false
compress_large_artifacts = false
large_artifact_max_mb = 100
"""
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        result = fake_success_run(tmp_path / "results", net_return=0.05)(config_path, repo_root=repo_root)
        assert result.result_dir is not None
        (result.result_dir / "strategy_input_rows.csv").write_text("big csv\n")
        (result.result_dir / "strategy_input_rows.jsonl").write_text("big jsonl\n")
        (result.result_dir / "engine_request.json").write_text("{}\n")
        return result

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--description", "compact artifacts"]) == 0

    attempt_dir = tmp_path / "results" / "attempt_0_05"
    assert not (attempt_dir / "strategy_input_rows.csv").exists()
    assert not (attempt_dir / "strategy_input_rows.jsonl").exists()
    assert not (attempt_dir / "engine_request.json").exists()
    metadata = json.loads((attempt_dir / "attempt_metadata.json").read_text())
    assert metadata["removed_artifacts"] == [
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_runner_applies_research_artifact_policy -q
```

Expected: fail because the runner does not call artifact policy.

- [ ] **Step 3: Wire artifact policy into `run_single_window_attempt`**

In `runner.py`, import:

```python
from artifact_policy import apply_artifact_policy
```

After writing `score.json` but before `write_attempt_metadata`, add:

```python
    artifact_config = config.artifacts
    if artifact_profile is not None and artifact_profile != artifact_config.profile:
        artifact_config = _artifact_config_with_profile(artifact_config, artifact_profile)
    removed_artifacts = apply_artifact_policy(result_dir, artifact_config)
```

Add helper:

```python
def _artifact_config_with_profile(config: Any, profile: str) -> Any:
    if profile == "debug":
        return type(config)(
            profile="debug",
            keep_strategy_snapshot=True,
            keep_config=True,
            keep_summary=True,
            keep_evidence=True,
            keep_signals=True,
            keep_engine_request=True,
            keep_input_rows_csv=True,
            keep_input_rows_jsonl=True,
            compress_large_artifacts=config.compress_large_artifacts,
            large_artifact_max_mb=config.large_artifact_max_mb,
        )
    return config
```

Extend `write_attempt_metadata` signature:

```python
    removed_artifacts: list[str] | None = None,
```

Add to metadata payload:

```python
        "removed_artifacts": removed_artifacts or [],
```

Pass `removed_artifacts=removed_artifacts` from `run_single_window_attempt`.

- [ ] **Step 4: Run artifact and runner tests**

Run:

```bash
conda run -n quant pytest tests/test_artifact_policy.py tests/test_runner.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 10**

```bash
git add runner.py tests/test_runner.py
git commit -m "Apply compact artifact policy"
```

---

### Task 11: Documentation And Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README run instructions**

In `README.md`, add:

```markdown
## Research Modes

Explore one recent primary window:

```bash
conda run -n quant python runner.py --explore --description "idea"
```

Confirm a candidate across the configured recent window bundle:

```bash
conda run -n quant python runner.py --confirm --description "candidate confirmation"
```

Run one diagnostic window without updating the best confirmed candidate:

```bash
conda run -n quant python runner.py --window-id validation_2025_h2 --description "diagnostic"
```

Confirmed candidates are scored by `candidate_score.json`; single-window scores
are exploration or diagnostic evidence.
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
conda run -n quant pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Inspect git diff**

Run:

```bash
git diff --stat
git diff -- program.md experiment.toml README.md
```

Expected: only intended files changed. Confirm `program.md` stays concise and does not expose exact attempt count.

- [ ] **Step 4: Commit Task 11**

```bash
git add README.md
git commit -m "Document research lifecycle modes"
```

---

## Final Verification

After all tasks are complete, run:

```bash
conda run -n quant pytest -q
```

Expected:

```text
all tests pass
```

Then run a lightweight mocked confirmation through tests rather than a live multi-window backtest:

```bash
conda run -n quant pytest tests/test_runner.py::test_confirm_runs_all_confirmation_windows_and_writes_candidate_score -q
```

Expected:

```text
1 passed
```

Do not run a live `--confirm` against real data as part of implementation verification unless Season explicitly asks; real confirmation writes large artifacts and consumes session capacity.

---

## Self-Review Checklist

- Spec coverage:
  - Multi-window confirmation: Tasks 8 and 9.
  - Balanced candidate scoring: Task 2.
  - Trade attribution: Task 3.
  - Artifact policy: Tasks 4 and 10.
  - Explicit `program.md` language: Task 5.
  - Config additions: Task 1 and Task 5.
  - Ledger/session migration: Task 6.
  - Documentation: Task 11.
- Type consistency:
  - `ResearchConfig`, `ConfirmationScoringConfig`, and `ArtifactConfig` are defined in Task 1 and reused by later tasks.
  - `WindowAttemptResult` is defined in Task 7 and reused by confirmation in Task 9.
  - `candidate_score` consistently means the aggregate JSON payload; its scalar value is `candidate_score["candidate_score"]`.
- Scope:
  - No task modifies `quant_strategies`.
  - No task adds fill, slippage, drawdown, margin, leverage, or equity-curve internals.
