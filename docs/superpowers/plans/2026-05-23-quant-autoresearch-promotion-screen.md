# Quant Autoresearch Promotion Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add compact promotion screening so every scored explore can be checked against recent windows, cost stress, and one rotating regime probe before it becomes best-so-far.

**Architecture:** Reuse the existing single-window runner, candidate scoring, attribution, artifact policy, ledger migration, and session state patterns. Add a small `[promotion]` config and a focused `promotion.py` module for pure promotion decisions; keep orchestration in `runner.py` and reuse the just-run explore result instead of running the primary window twice.

**Tech Stack:** Python 3.12 standard library (`dataclasses`, `csv`, `json`, `math`, `pathlib`, `tomllib`), existing `quant_strategies.runner.run_config`, `pytest`.

---

## Scope Reduction Accepted

The original plan was complete but too heavy for the workbench. The reduced plan keeps the agreed promotion behavior while cutting avoidable churn:

- Reuse the primary explore `WindowAttemptResult` inside the promotion recent core.
- Keep `promotion.py` pure and small; no new service layer.
- Keep promotion artifacts compact and grouped, but do not redesign all existing candidate artifacts.
- Create repo-local `AGENTS.md`, but skip README edits.
- Add targeted `program.md` wording only; do not rewrite the protocol.

## What Already Exists

- `run_single_window_attempt()` already materializes per-window configs, delegates to `quant_strategies`, scores, applies artifact policy, and writes metadata.
- `build_candidate_score()` already computes recent mean, median, worst score, dispersion, low-trade penalties, and symbol concentration.
- `build_trade_attribution()` already summarizes trade evidence by window, symbol, side, month, and hour.
- `append_ledger()` already migrates old result ledgers and writes candidate-level fields.
- `SessionState` already persists attempt budget and best confirmed candidate state.
- `program.md` already contains the quant researcher behavior contract.

## Not In Scope

- Full validation, walk-forward research, drawdown, capacity, leverage, or portfolio analytics.
- UI/dashboard work.
- Changing `quant_strategies` or `quant_data`.
- Replacing current confirmation commands; explicit `--confirm` remains available for compatibility.
- Rewriting `program.md`; only targeted promotion language is added.
- README updates; `AGENTS.md` carries the project target requested for agents.

## Target Flow

```text
runner.py --explore
  |
  +-- run primary window once
  |
  +-- if not scored
  |     `-- finish normal explore, no promotion spend
  |
  `-- if scored and promotion enabled
        |
        +-- recent core
        |     +-- reuse primary explore result when window ids match
        |     `-- run remaining configured recent windows
        |
        +-- run cost stress on primary window
        +-- run one rotating probe window
        +-- write promotion_score.json + summary + attribution
        +-- update best_promoted_* if promoted
        `-- append one promotion ledger row
```

---

### Task 1: Parse Promotion Config

**Files:**
- Modify: `experiment_config.py`
- Modify: `tests/test_experiment_config.py`

- [ ] **Step 1: Add failing promotion config tests**

Append to `tests/test_experiment_config.py`:

```python
def test_load_experiment_config_defaults_promotion_disabled(tmp_path: Path):
    config = load_experiment_config(write_config(tmp_path))

    assert config.promotion.enabled is False
    assert config.promotion.screen_on_scored_explore is False
    assert config.promotion.recent_window_ids == ()
    assert config.promotion.rotating_probe_window_ids == ()
    assert config.promotion.deep_probe_floor == 0.0
    assert config.promotion.near_equal_score_tolerance == 0.0
    assert config.promotion.cost_stress_id == "cost_stress"
    assert config.promotion.cost_fee_bps_per_side == 0.0
    assert config.promotion.cost_slippage_bps_per_side == 0.0
    assert config.promotion.cost_stress_min_ratio == 0.0


def test_load_experiment_config_parses_promotion_section(tmp_path: Path):
    config_text = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""

    config = load_experiment_config(write_config(tmp_path, config_text))

    assert config.promotion.enabled is True
    assert config.promotion.screen_on_scored_explore is True
    assert config.promotion.recent_window_ids == ("primary", "holdout")
    assert config.promotion.rotating_probe_window_ids == ("holdout",)
    assert config.promotion.deep_probe_floor == pytest.approx(-0.001)
    assert config.promotion.near_equal_score_tolerance == pytest.approx(0.0001)
    assert config.promotion.cost_stress_id == "realistic_costs"
    assert config.promotion.cost_fee_bps_per_side == pytest.approx(0.5)
    assert config.promotion.cost_slippage_bps_per_side == pytest.approx(0.5)
    assert config.promotion.cost_stress_min_ratio == pytest.approx(0.5)


def test_load_experiment_config_rejects_unknown_promotion_window(tmp_path: Path):
    bad = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "missing"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""

    with pytest.raises(ConfigError, match="promotion.recent_window_ids"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_promotion_recent_without_primary_window(tmp_path: Path):
    bad = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""

    with pytest.raises(ConfigError, match="research.primary_window_id"):
        load_experiment_config(write_config(tmp_path, bad))


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_load_experiment_config_rejects_invalid_cost_stress_ratio(tmp_path: Path, ratio: float):
    bad = VALID_TOML + f"""

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = {ratio}
"""

    with pytest.raises(ConfigError, match="cost_stress_min_ratio"):
        load_experiment_config(write_config(tmp_path, bad))


def test_load_experiment_config_rejects_enabled_zero_cost_promotion(tmp_path: Path):
    bad = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.0
cost_slippage_bps_per_side = 0.0
cost_stress_min_ratio = 0.5
"""

    with pytest.raises(ConfigError, match="nonzero fee or slippage"):
        load_experiment_config(write_config(tmp_path, bad))
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py -q
```

Expected: fails because `ExperimentConfig` has no `promotion` field.

- [ ] **Step 3: Add `PromotionConfig`**

In `experiment_config.py`, add after `ConfirmationScoringConfig`:

```python
@dataclass(frozen=True)
class PromotionConfig:
    enabled: bool
    screen_on_scored_explore: bool
    recent_window_ids: tuple[str, ...]
    rotating_probe_window_ids: tuple[str, ...]
    deep_probe_floor: float
    near_equal_score_tolerance: float
    cost_stress_id: str
    cost_fee_bps_per_side: float
    cost_slippage_bps_per_side: float
    cost_stress_min_ratio: float
```

Add to `ExperimentConfig` after `confirmation_scoring`:

```python
    promotion: PromotionConfig
```

- [ ] **Step 4: Add parser**

In `load_experiment_config`, after confirmation scoring is parsed:

```python
    promotion = _parse_promotion(raw, window_ids, primary_window_id=research.primary_window_id)
```

Pass it into the dataclass constructor:

```python
        promotion=promotion,
```

Add before `_parse_artifacts`:

```python
def _parse_promotion(
    raw: dict[str, Any],
    window_ids: set[str],
    *,
    primary_window_id: str,
) -> PromotionConfig:
    table = raw.get("promotion")
    if table is None:
        return PromotionConfig(
            enabled=False,
            screen_on_scored_explore=False,
            recent_window_ids=(),
            rotating_probe_window_ids=(),
            deep_probe_floor=0.0,
            near_equal_score_tolerance=0.0,
            cost_stress_id="cost_stress",
            cost_fee_bps_per_side=0.0,
            cost_slippage_bps_per_side=0.0,
            cost_stress_min_ratio=0.0,
        )
    if not isinstance(table, dict):
        raise ConfigError("promotion must be a table")

    recent_window_ids = tuple(
        _list_item_str(
            _required_list(table, "recent_window_ids", table="promotion"),
            "promotion.recent_window_ids",
        )
    )
    rotating_probe_window_ids = tuple(
        _list_item_str(
            _required_list(table, "rotating_probe_window_ids", table="promotion"),
            "promotion.rotating_probe_window_ids",
        )
    )
    _reject_unknown_window_ids(recent_window_ids, window_ids, "promotion.recent_window_ids")
    _reject_unknown_window_ids(rotating_probe_window_ids, window_ids, "promotion.rotating_probe_window_ids")

    enabled = _required_bool(table, "enabled", table="promotion")
    screen_on_scored_explore = _required_bool(table, "screen_on_scored_explore", table="promotion")
    cost_fee_bps_per_side = _required_non_negative_float(table, "cost_fee_bps_per_side", table="promotion")
    cost_slippage_bps_per_side = _required_non_negative_float(table, "cost_slippage_bps_per_side", table="promotion")
    cost_stress_min_ratio = _required_non_negative_float(table, "cost_stress_min_ratio", table="promotion")
    if cost_stress_min_ratio > 1.0:
        raise ConfigError("promotion.cost_stress_min_ratio must be between 0 and 1 inclusive")
    if enabled and screen_on_scored_explore and not recent_window_ids:
        raise ConfigError("promotion.recent_window_ids must be non-empty when enabled")
    if enabled and screen_on_scored_explore and not rotating_probe_window_ids:
        raise ConfigError("promotion.rotating_probe_window_ids must be non-empty when enabled")
    if enabled and screen_on_scored_explore and primary_window_id not in recent_window_ids:
        raise ConfigError("promotion.recent_window_ids must include research.primary_window_id")
    if enabled and screen_on_scored_explore and cost_fee_bps_per_side == 0.0 and cost_slippage_bps_per_side == 0.0:
        raise ConfigError("promotion cost stress must use nonzero fee or slippage")

    return PromotionConfig(
        enabled=enabled,
        screen_on_scored_explore=screen_on_scored_explore,
        recent_window_ids=recent_window_ids,
        rotating_probe_window_ids=rotating_probe_window_ids,
        deep_probe_floor=float(_required_number(table, "deep_probe_floor", table="promotion")),
        near_equal_score_tolerance=_required_non_negative_float(table, "near_equal_score_tolerance", table="promotion"),
        cost_stress_id=_required_str(table, "cost_stress_id", table="promotion"),
        cost_fee_bps_per_side=cost_fee_bps_per_side,
        cost_slippage_bps_per_side=cost_slippage_bps_per_side,
        cost_stress_min_ratio=cost_stress_min_ratio,
    )
```

Add near `_list_item_str`:

```python
def _required_list(raw: dict[str, Any], key: str, *, table: str | None = None) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ConfigError(f"missing required list field: {_field_name(key, table)}")
    return value


def _reject_unknown_window_ids(values: tuple[str, ...], window_ids: set[str], field_name: str) -> None:
    unknown = [window_id for window_id in values if window_id not in window_ids]
    if unknown:
        raise ConfigError(f"{field_name} contains unknown windows: {unknown}")
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py -q
```

Expected: pass.

Commit:

```bash
git add experiment_config.py tests/test_experiment_config.py
git commit -m "Add promotion config parsing"
```

---

### Task 2: Add Pure Promotion Decisions

**Files:**
- Create: `promotion.py`
- Create: `tests/test_promotion.py`

- [ ] **Step 1: Add failing tests**

Create `tests/test_promotion.py`:

```python
from __future__ import annotations

from dataclasses import replace

import pytest

from experiment_config import ConfirmationScoringConfig, PromotionConfig
from promotion import (
    build_cost_stress_config,
    build_promotion_score,
    decision_for_promotion,
    scored_for_promotion,
    select_rotating_probe_window_id,
)
from runner import SessionState


def confirmation_config() -> ConfirmationScoringConfig:
    return ConfirmationScoringConfig(
        primary_metric="net_return_per_day",
        dispersion_weight=0.0,
        weak_window_floor=0.0,
        weak_window_penalty=0.0,
        min_trades_per_window=2,
        low_trade_penalty=0.0,
        min_symbol_count=1,
        symbol_concentration_penalty=0.0,
    )


def promotion_config() -> PromotionConfig:
    return PromotionConfig(
        enabled=True,
        screen_on_scored_explore=True,
        recent_window_ids=("primary", "holdout"),
        rotating_probe_window_ids=("stress_a", "stress_b"),
        deep_probe_floor=-0.001,
        near_equal_score_tolerance=0.0001,
        cost_stress_id="realistic_costs",
        cost_fee_bps_per_side=0.5,
        cost_slippage_bps_per_side=0.5,
        cost_stress_min_ratio=0.5,
    )


def window_score(window_id: str, score: float | None, *, status: str = "scored") -> dict[str, object]:
    return {
        "window_id": window_id,
        "score": score,
        "raw_net_return": score * 120 if score is not None else None,
        "trade_count": 3,
        "symbol_count": 2,
        "status": status,
        "failed_gates": [],
        "failure_source": None,
    }


def state(**overrides: object) -> SessionState:
    base = SessionState(
        max_attempts=3,
        attempts_used=0,
        best_score=None,
        best_commit=None,
        status="active",
        best_primary_window_score=None,
        best_confirmed_candidate_score=None,
        best_confirmed_commit=None,
        best_promoted_score=None,
        best_promoted_commit=None,
        rotating_probe_index=0,
        last_promotion_decision=None,
    )
    return replace(base, **overrides)


def test_scored_for_promotion_accepts_only_scored_numeric_scores():
    assert scored_for_promotion(window_score("primary", 0.01)) is True
    assert scored_for_promotion(window_score("primary", None, status="insufficient_sample")) is False
    assert scored_for_promotion(window_score("primary", 0.01, status="validation_failed")) is False


def test_select_rotating_probe_window_id_uses_session_index_modulo_probe_count():
    assert select_rotating_probe_window_id(promotion_config(), state(rotating_probe_index=0)) == "stress_a"
    assert select_rotating_probe_window_id(promotion_config(), state(rotating_probe_index=1)) == "stress_b"
    assert select_rotating_probe_window_id(promotion_config(), state(rotating_probe_index=2)) == "stress_a"


def test_build_cost_stress_config_overrides_only_cost_model(tmp_path):
    from experiment_config import load_experiment_config
    from tests.test_experiment_config import VALID_TOML, write_config

    text = VALID_TOML + """

[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = ["primary", "holdout"]
rotating_probe_window_ids = ["holdout"]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
"""
    config = load_experiment_config(write_config(tmp_path, text))

    stressed = build_cost_stress_config(config)

    assert stressed.cost_model["fee_bps_per_side"] == 0.5
    assert stressed.cost_model["slippage_bps_per_side"] == 0.5
    assert config.cost_model["fee_bps_per_side"] == 1.0
    assert config.cost_model["slippage_bps_per_side"] == 2.0
    assert stressed.strategy_id == config.strategy_id


def test_build_promotion_score_records_recent_cost_and_probe_evidence():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is True
    assert payload["promotion_score"] == pytest.approx(0.0019)
    assert payload["recent_mean_score"] == pytest.approx(0.0019)
    assert payload["cost_stress_ratio"] == pytest.approx(0.0012 / 0.0019)
    assert payload["rotating_probe_window_id"] == "stress_a"
    assert payload["failed_reasons"] == []


def test_build_promotion_score_rejects_cost_stress_edge_destruction():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0002),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is False
    assert "cost_stress_ratio_below_minimum" in payload["failed_reasons"]


def test_build_promotion_score_rejects_deep_negative_probe():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", -0.0020),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert payload["eligible_for_promotion"] is False
    assert "rotating_probe_below_floor" in payload["failed_reasons"]


def test_decision_for_promotion_respects_best_score_and_simplification_tolerance():
    payload = build_promotion_score(
        recent_window_scores=[window_score("primary", 0.0020), window_score("holdout", 0.0018)],
        cost_stress_score=window_score("primary", 0.0012),
        rotating_probe_score=window_score("stress_a", 0.0001),
        confirmation_config=confirmation_config(),
        promotion_config=promotion_config(),
        commit="abc1234",
        description="candidate",
        rotating_probe_window_id="stress_a",
    )

    assert decision_for_promotion(payload, state=state(), simplification=False) == "promote"
    current = state(best_promoted_score=payload["promotion_score"] + 0.00005)
    assert decision_for_promotion(payload, state=current, simplification=False) == "reject"
    assert decision_for_promotion(payload, state=current, simplification=True) == "promote"
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
conda run -n quant pytest tests/test_promotion.py -q
```

Expected: fails because `promotion.py` and `SessionState` promotion fields do not exist.

- [ ] **Step 3: Create `promotion.py`**

Create `promotion.py`:

```python
from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

from experiment_config import ConfirmationScoringConfig, ExperimentConfig, PromotionConfig
from scoring import build_candidate_score


def scored_for_promotion(score: dict[str, Any]) -> bool:
    return score.get("status") == "scored" and _as_float_or_none(score.get("score")) is not None


def select_rotating_probe_window_id(config: PromotionConfig, state: Any) -> str:
    if not config.rotating_probe_window_ids:
        raise ValueError("promotion rotating probe windows are empty")
    index = int(getattr(state, "rotating_probe_index", 0))
    return config.rotating_probe_window_ids[index % len(config.rotating_probe_window_ids)]


def build_cost_stress_config(config: ExperimentConfig) -> ExperimentConfig:
    return replace(
        config,
        cost_model={
            **config.cost_model,
            "fee_bps_per_side": config.promotion.cost_fee_bps_per_side,
            "slippage_bps_per_side": config.promotion.cost_slippage_bps_per_side,
        },
    )


def build_promotion_score(
    *,
    recent_window_scores: list[dict[str, Any]],
    cost_stress_score: dict[str, Any],
    rotating_probe_score: dict[str, Any],
    confirmation_config: ConfirmationScoringConfig,
    promotion_config: PromotionConfig,
    commit: str | None,
    description: str,
    rotating_probe_window_id: str,
) -> dict[str, Any]:
    recent_score = build_candidate_score(
        window_scores=recent_window_scores,
        config=confirmation_config,
        commit=commit,
        description=description,
    )
    promotion_score = _as_float_or_none(recent_score.get("candidate_score"))
    recent_mean_score = _as_float_or_none(recent_score.get("recent_mean_score"))
    cost_value = _as_float_or_none(cost_stress_score.get("score"))
    probe_value = _as_float_or_none(rotating_probe_score.get("score"))
    failed_reasons: list[str] = []

    if recent_score.get("status") != "scored" or promotion_score is None:
        failed_reasons.append("recent_core_failed")
    if _failed_recent_core(recent_window_scores):
        failed_reasons.append("recent_core_weak_window")

    cost_stress_ratio = _cost_stress_ratio(cost_value, recent_mean_score)
    if cost_value is None:
        failed_reasons.append("cost_stress_failed")
    elif cost_stress_ratio is None:
        failed_reasons.append("cost_stress_ratio_unavailable")
    elif cost_stress_ratio < promotion_config.cost_stress_min_ratio:
        failed_reasons.append("cost_stress_ratio_below_minimum")

    if probe_value is None:
        failed_reasons.append("rotating_probe_failed")
    elif probe_value <= promotion_config.deep_probe_floor:
        failed_reasons.append("rotating_probe_below_floor")

    return {
        "status": "scored" if promotion_score is not None else "promotion_failed",
        "promotion_score": promotion_score,
        "metric": "promotion_recent_net_return_per_day",
        "commit": commit,
        "description": _single_line(description),
        "eligible_for_promotion": not failed_reasons,
        "failed_reasons": failed_reasons,
        "recent_candidate_score": recent_score,
        "recent_mean_score": recent_score.get("recent_mean_score"),
        "recent_median_score": recent_score.get("recent_median_score"),
        "worst_recent_score": recent_score.get("worst_recent_score"),
        "score_dispersion": recent_score.get("score_dispersion"),
        "near_equal_score_tolerance": promotion_config.near_equal_score_tolerance,
        "cost_stress_id": promotion_config.cost_stress_id,
        "cost_stress_score": cost_value,
        "cost_stress_ratio": cost_stress_ratio,
        "rotating_probe_window_id": rotating_probe_window_id,
        "rotating_probe_score": probe_value,
        "recent_window_scores": recent_window_scores,
        "cost_stress_window_score": cost_stress_score,
        "rotating_probe_window_score": rotating_probe_score,
        "notes": "Promotion screening only. Not final validation.",
    }


def decision_for_promotion(
    promotion_score: dict[str, Any],
    *,
    state: Any,
    simplification: bool,
) -> str:
    if promotion_score.get("eligible_for_promotion") is not True:
        return "reject"
    value = _as_float_or_none(promotion_score.get("promotion_score"))
    if value is None:
        return "reject"
    current = _as_float_or_none(getattr(state, "best_promoted_score", None))
    if current is None or value > current:
        return "promote"
    tolerance = _as_float_or_none(promotion_score.get("near_equal_score_tolerance")) or 0.0
    if simplification and value >= current - tolerance:
        return "promote"
    return "reject"


def _failed_recent_core(window_scores: list[dict[str, Any]]) -> bool:
    for score in window_scores:
        value = _as_float_or_none(score.get("score"))
        if score.get("status") != "scored" or value is None or value <= 0.0:
            return True
    return False


def _cost_stress_ratio(cost_value: float | None, recent_mean_score: float | None) -> float | None:
    if cost_value is None or recent_mean_score is None or recent_mean_score <= 0.0:
        return None
    return cost_value / recent_mean_score


def _as_float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _single_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")
```

- [ ] **Step 4: Commit after Task 3**

Do not commit until Task 3 adds `SessionState` fields and the new tests pass.

---

### Task 3: Extend State And Ledger

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Add focused state and ledger tests**

Append to `tests/test_runner.py`:

```python
def test_session_state_tracks_promotion_fields(tmp_path: Path):
    state = runner_module.SessionState(
        max_attempts=3,
        attempts_used=0,
        best_score=0.01,
        best_commit="old",
        status="active",
        best_primary_window_score=0.0015,
        best_confirmed_candidate_score=0.002,
        best_confirmed_commit="confirmed_old",
        best_promoted_score=0.003,
        best_promoted_commit="promoted_old",
        rotating_probe_index=2,
        last_promotion_decision="promote",
    )

    payload_path = tmp_path / "session_state.json"
    runner_module.save_session_state(payload_path, state)
    loaded = runner_module.load_session_state(
        payload_path,
        config=None,
        max_attempts_override=None,
        fallback_max_attempts=3,
    )

    assert loaded.best_promoted_score == 0.003
    assert loaded.best_promoted_commit == "promoted_old"
    assert loaded.rotating_probe_index == 2
    assert loaded.last_promotion_decision == "promote"


def test_load_session_state_defaults_missing_promotion_fields(tmp_path: Path):
    payload_path = tmp_path / "session_state.json"
    payload_path.write_text(
        json.dumps(
            {
                "attempts_used": 0,
                "best_commit": None,
                "best_score": None,
                "best_primary_window_score": None,
                "best_confirmed_candidate_score": None,
                "best_confirmed_commit": None,
                "last_decision": None,
                "max_attempts": 3,
                "remaining_attempts": 3,
                "status": "active",
            }
        )
        + "\n"
    )

    loaded = runner_module.load_session_state(
        payload_path,
        config=None,
        max_attempts_override=None,
        fallback_max_attempts=3,
    )

    assert loaded.best_promoted_score is None
    assert loaded.best_promoted_commit is None
    assert loaded.rotating_probe_index == 0
    assert loaded.last_promotion_decision is None


def test_append_ledger_writes_promotion_columns(tmp_path: Path):
    score = {"score": 0.001, "raw_net_return": 0.12, "trade_count": 250}
    promotion_score = {
        "promotion_decision": "promote",
        "promotion_score": 0.0008,
        "recent_mean_score": 0.0012,
        "worst_recent_score": 0.0004,
        "score_dispersion": 0.0001,
        "cost_stress_score": 0.0007,
        "cost_stress_ratio": 0.58,
        "rotating_probe_window_id": "stress_2022_ftx",
        "rotating_probe_score": -0.0002,
        "promoted_commit": "abc1234",
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
        status="promote",
        description="promotion",
        run_kind="promotion",
        promotion_score=promotion_score,
    )

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert rows[0]["promotion_decision"] == "promote"
    assert rows[0]["promotion_score"] == "0.0008"
    assert rows[0]["cost_stress_ratio"] == "0.58"
    assert rows[0]["rotating_probe_window_id"] == "stress_2022_ftx"
    assert rows[0]["promoted_commit"] == "abc1234"
```

- [ ] **Step 2: Update `SessionState`**

In `runner.py`, add default fields:

```python
    best_promoted_score: float | None = None
    best_promoted_commit: str | None = None
    rotating_probe_index: int = 0
    last_promotion_decision: str | None = None
```

Update `load_session_state()`, `save_session_state()`, `update_state()`, and `update_state_for_candidate()` to preserve these fields. Use this pattern when loading old sessions:

```python
        best_promoted_score=_optional_float(payload.get("best_promoted_score")),
        best_promoted_commit=_optional_str(payload.get("best_promoted_commit")),
        rotating_probe_index=_optional_int(payload.get("rotating_probe_index")) or 0,
        last_promotion_decision=_optional_str(payload.get("last_promotion_decision")),
```

When returning a new `SessionState` from `update_state()` or
`update_state_for_candidate()`, explicitly carry these four promotion fields
forward from the previous state. Otherwise a normal explore or explicit
confirmation after promotion would silently erase promotion history.

- [ ] **Step 3: Add promotion state updater**

Add after `update_state_for_candidate()`:

```python
def update_state_for_promotion(
    state: SessionState,
    *,
    promotion_score: dict[str, Any],
    commit: str | None,
    decision: str,
) -> SessionState:
    attempts_used = state.attempts_used + 1
    best_promoted_score = state.best_promoted_score
    best_promoted_commit = state.best_promoted_commit
    value = _numeric_score(promotion_score.get("promotion_score"))
    if decision == "promote" and value is not None:
        best_promoted_score = value
        best_promoted_commit = commit
    return SessionState(
        max_attempts=state.max_attempts,
        attempts_used=attempts_used,
        best_score=state.best_score,
        best_commit=state.best_commit,
        best_primary_window_score=state.best_primary_window_score,
        best_confirmed_candidate_score=state.best_confirmed_candidate_score,
        best_confirmed_commit=state.best_confirmed_commit,
        best_promoted_score=best_promoted_score,
        best_promoted_commit=best_promoted_commit,
        rotating_probe_index=state.rotating_probe_index + 1,
        last_promotion_decision=decision,
        status="exhausted" if attempts_used >= state.max_attempts else "active",
        last_decision=decision,
    )
```

- [ ] **Step 4: Extend ledger fields**

Add a current-header alias before redefining `LEDGER_HEADER`:

```python
CANDIDATE_LEDGER_HEADER = [
    *SYMBOL_LEDGER_HEADER,
    "run_kind",
    "candidate_score",
    "recent_mean_score",
    "worst_recent_score",
    "passed_window_count",
    "failed_window_count",
]
```

Then set:

```python
LEDGER_HEADER = [
    *CANDIDATE_LEDGER_HEADER,
    "promotion_decision",
    "promotion_score",
    "score_dispersion",
    "cost_stress_score",
    "cost_stress_ratio",
    "rotating_probe_window_id",
    "rotating_probe_score",
    "promoted_commit",
]
```

Update `_ensure_ledger_schema()` to accept `CANDIDATE_LEDGER_HEADER` as an old schema. Add optional `promotion_score` to `append_ledger()` and write these row fields:

```python
                "promotion_decision": _promotion_field(promotion_score, "promotion_decision"),
                "promotion_score": _promotion_field(promotion_score, "promotion_score"),
                "score_dispersion": _promotion_field(promotion_score, "score_dispersion"),
                "cost_stress_score": _promotion_field(promotion_score, "cost_stress_score"),
                "cost_stress_ratio": _promotion_field(promotion_score, "cost_stress_ratio"),
                "rotating_probe_window_id": _promotion_field(promotion_score, "rotating_probe_window_id"),
                "rotating_probe_score": _promotion_field(promotion_score, "rotating_probe_score"),
                "promoted_commit": _promotion_field(promotion_score, "promoted_commit"),
```

Add:

```python
def _promotion_field(promotion_score: dict[str, Any] | None, key: str) -> str:
    if promotion_score is None:
        return ""
    value = promotion_score.get(key)
    return "" if value is None else str(value)
```

- [ ] **Step 5: Verify and commit Tasks 2-3**

Run:

```bash
conda run -n quant pytest tests/test_promotion.py tests/test_runner.py::test_session_state_tracks_promotion_fields tests/test_runner.py::test_load_session_state_defaults_missing_promotion_fields tests/test_runner.py::test_append_ledger_writes_promotion_columns -q
```

Expected: pass.

Commit:

```bash
git add promotion.py runner.py tests/test_promotion.py tests/test_runner.py
git commit -m "Add promotion decisions state and ledger"
```

---

### Task 4: Run Promotion After Scored Explore

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Add test helper**

Add after `write_experiment()` in `tests/test_runner.py`:

```python
def append_promotion_config(root: Path) -> None:
    with (root / "experiment.toml").open("a") as handle:
        handle.write(
            """
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
enabled = true
screen_on_scored_explore = true
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

- [ ] **Step 2: Add orchestration tests**

Append to `tests/test_runner.py`:

```python
def test_scored_explore_runs_promotion_without_rerunning_primary(tmp_path: Path, monkeypatch, capsys):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path)
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

    assert main(["--explore", "--description", "promotion screen"]) == 0

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


def test_non_scored_explore_does_not_run_promotion(tmp_path: Path, monkeypatch):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")
    monkeypatch.setattr(
        runner_module,
        "run_config",
        fake_success_run(tmp_path / "results", net_return=0.20, trade_count=1),
    )

    assert main(["--explore", "--description", "too few trades"]) == 0

    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert state["best_promoted_score"] is None
    assert state["rotating_probe_index"] == 0
    assert rows[0]["run_kind"] == "explore"
    assert rows[0]["promotion_score"] == ""
    assert not list((tmp_path / "results").glob("promotion_*"))


def test_promotion_rejects_cost_stress_failure(tmp_path: Path, monkeypatch, capsys):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        parsed = tomllib.loads(config_path.read_text())
        output_dir = Path(parsed["output"]["results_dir"])
        net = 0.01 if parsed["cost_model"]["fee_bps_per_side"] == 0.5 else 0.18
        return fake_success_run(output_dir, net_return=net, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--description", "weak costs"]) == 0

    output = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "results" / "session_state.json").read_text())
    assert output["decision"] == "reject"
    assert state["best_promoted_score"] is None
    promotion_score = json.loads((Path(output["result_dir"]) / "promotion_score.json").read_text())
    assert "cost_stress_ratio_below_minimum" in promotion_score["failed_reasons"]


def test_promotion_window_exception_records_rejection_instead_of_aborting(tmp_path: Path, monkeypatch, capsys):
    write_experiment(tmp_path, max_attempts=1)
    append_promotion_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner_module, "current_commit", lambda: "abc1234")

    def _run_config(config_path: Path, *, repo_root: Path):
        parsed = tomllib.loads(config_path.read_text())
        output_dir = Path(parsed["output"]["results_dir"])
        is_holdout_recent = (
            parsed["data"]["start"] == "2024-05-01"
            and parsed["cost_model"]["fee_bps_per_side"] == 0.0
        )
        if is_holdout_recent:
            raise RuntimeError("data unavailable")
        return fake_success_run(output_dir, net_return=0.18, trade_count=3)(config_path, repo_root=repo_root)

    monkeypatch.setattr(runner_module, "run_config", _run_config)

    assert main(["--explore", "--description", "subwindow crash"]) == 0

    output = json.loads(capsys.readouterr().out)
    promotion_score = json.loads((Path(output["result_dir"]) / "promotion_score.json").read_text())
    assert output["decision"] == "reject"
    assert "recent_core_failed" in promotion_score["failed_reasons"]
    assert (Path(output["result_dir"]) / "windows" / "holdout").exists()
```

- [ ] **Step 3: Import promotion helpers**

In `runner.py`:

```python
from promotion import (
    build_cost_stress_config,
    build_promotion_score,
    decision_for_promotion,
    scored_for_promotion,
    select_rotating_probe_window_id,
)
```

- [ ] **Step 4: Add promotion orchestration**

Add after `run_confirmation_attempt()`:

```python
def run_promotion_screen(
    *,
    config: ExperimentConfig,
    state: SessionState,
    attempt: int,
    results_dir: Path,
    description: str,
    commit: str | None,
    simplification: bool,
    artifact_profile: str | None,
    explore_result: WindowAttemptResult,
) -> tuple[Path, dict[str, Any], list[WindowAttemptResult]]:
    promotion_dir = results_dir / f"promotion_{attempt:04d}_{config.strategy_id}"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    def _run(
        *,
        target_config: ExperimentConfig,
        window_id: str,
        result_dir: Path,
        stage: str,
    ) -> WindowAttemptResult:
        try:
            return run_single_window_attempt(
                config=target_config,
                attempt=attempt,
                window_id=window_id,
                results_dir=result_dir,
                description=description,
                commit=commit,
                simplification=simplification,
                artifact_profile=artifact_profile,
            )
        except Exception as exc:
            return failed_window_attempt_result(
                config=target_config,
                attempt=attempt,
                window_id=window_id,
                result_dir=result_dir / f"attempt_{attempt:04d}_{window_id}_failed",
                description=description,
                commit=commit,
                message=f"{stage} failed: {exc}",
            )

    recent_results: list[WindowAttemptResult] = []
    for window_id in config.promotion.recent_window_ids:
        if window_id == explore_result.window_id:
            recent_results.append(explore_result)
            continue
        recent_results.append(
            _run(
                target_config=config,
                window_id=window_id,
                result_dir=promotion_dir / "windows" / window_id,
                stage="promotion recent window",
            )
        )

    cost_config = build_cost_stress_config(config)
    cost_result = _run(
        target_config=cost_config,
        window_id=config.research.primary_window_id,
        result_dir=promotion_dir / "cost_stress" / config.promotion.cost_stress_id,
        stage="promotion cost stress",
    )

    probe_window_id = select_rotating_probe_window_id(config.promotion, state)
    probe_result = _run(
        target_config=config,
        window_id=probe_window_id,
        result_dir=promotion_dir / "rotating_probe" / probe_window_id,
        stage="promotion rotating probe",
    )

    promotion_score = build_promotion_score(
        recent_window_scores=[result.score for result in recent_results],
        cost_stress_score=cost_result.score,
        rotating_probe_score=probe_result.score,
        confirmation_config=config.confirmation_scoring,
        promotion_config=config.promotion,
        commit=commit,
        description=description,
        rotating_probe_window_id=probe_window_id,
    )
    write_score(promotion_dir / "promotion_score.json", promotion_score)
    (promotion_dir / "promotion_summary.json").write_text(
        json.dumps(
            {
                "attempt": attempt,
                "commit": commit,
                "description": description,
                "promotion_score": promotion_score["promotion_score"],
                "eligible_for_promotion": promotion_score["eligible_for_promotion"],
                "failed_reasons": promotion_score["failed_reasons"],
                "recent_window_ids": list(config.promotion.recent_window_ids),
                "source_result_dirs": {result.window_id: str(result.result_dir) for result in recent_results},
                "cost_stress_result_dir": str(cost_result.result_dir),
                "cost_stress_id": config.promotion.cost_stress_id,
                "rotating_probe_window_id": probe_window_id,
                "rotating_probe_result_dir": str(probe_result.result_dir),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    evidence_by_window = {result.window_id: result.evidence for result in recent_results}
    evidence_by_window[f"cost_stress:{config.promotion.cost_stress_id}"] = cost_result.evidence
    evidence_by_window[f"rotating_probe:{probe_window_id}"] = probe_result.evidence
    (promotion_dir / "trade_attribution.json").write_text(
        json.dumps(build_trade_attribution(evidence_by_window), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return promotion_dir, promotion_score, recent_results
```

Add `_finish_promotion_attempt()` after `_finish_confirmation_attempt()`:

```python
def _finish_promotion_attempt(
    *,
    state_path: Path,
    state: SessionState,
    promotion_dir: Path,
    promotion_score: dict[str, Any],
    recent_results: list[WindowAttemptResult],
    attempt: int,
    commit: str | None,
    description: str,
    ignored_max_attempts_override: int | None,
    simplification: bool,
    primary_window_id: str,
) -> int:
    decision = decision_for_promotion(promotion_score, state=state, simplification=simplification)
    next_score = {
        **promotion_score,
        "promotion_decision": decision,
        "promoted_commit": commit if decision == "promote" else None,
    }
    write_score(promotion_dir / "promotion_score.json", next_score)
    next_state = update_state_for_promotion(
        state,
        promotion_score=promotion_score,
        commit=commit,
        decision=decision,
    )
    save_session_state(state_path, next_state)
    primary_result = _primary_window_result(recent_results, primary_window_id=primary_window_id)
    append_ledger(
        ROOT / "results.tsv",
        attempt=attempt,
        commit=commit,
        window_id=primary_result.window_id,
        window_start=_optional_str(primary_result.run_metadata["window_start"]),
        window_end=_optional_str(primary_result.run_metadata["window_end"]),
        window_days=_optional_int(primary_result.run_metadata["window_days"]),
        symbol_count=_optional_int(primary_result.run_metadata["symbol_count"]),
        score=primary_result.score,
        status=decision,
        description=description,
        run_kind="promotion",
        promotion_score=next_score,
    )
    print(
        json.dumps(
            {
                "attempt": attempt,
                "decision": decision,
                "ignored_max_attempts_override": ignored_max_attempts_override,
                "max_attempts": next_state.max_attempts,
                "promotion_score": promotion_score["promotion_score"],
                "remaining_attempts": next_state.remaining_attempts,
                "result_dir": str(promotion_dir),
                "run_kind": "promotion",
                "status": next_state.status,
            },
            sort_keys=True,
        )
    )
    return 0
```

- [ ] **Step 5: Wire `main()`**

After `window_result = run_single_window_attempt(...)`, add this before the legacy auto-confirm branch:

```python
    if (
        run_kind == "explore"
        and config.promotion.enabled
        and config.promotion.screen_on_scored_explore
        and scored_for_promotion(window_result.score)
    ):
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

- [ ] **Step 6: Verify and commit**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_scored_explore_runs_promotion_without_rerunning_primary tests/test_runner.py::test_non_scored_explore_does_not_run_promotion tests/test_runner.py::test_promotion_rejects_cost_stress_failure tests/test_runner.py::test_promotion_window_exception_records_rejection_instead_of_aborting -q
conda run -n quant pytest tests/test_runner.py -q
```

Expected: pass.

Commit:

```bash
git add runner.py tests/test_runner.py
git commit -m "Run promotion screen after scored explores"
```

---

### Task 5: Enable Promotion In Current Config

**Files:**
- Modify: `experiment.toml`

- [ ] **Step 1: Add `[promotion]`**

Add after `[confirmation_scoring]`:

```toml
[promotion]
enabled = true
screen_on_scored_explore = true
recent_window_ids = [
  "validation_2025_h1",
  "validation_2025_h2",
  "locked_recent_2026",
]
rotating_probe_window_ids = [
  "stress_2022_deleveraging",
  "stress_2022_ftx",
  "recovery_2023_h1",
  "research_2024_h1",
  "research_2024_h2",
]
deep_probe_floor = -0.001
near_equal_score_tolerance = 0.0001
cost_stress_id = "realistic_costs"
cost_fee_bps_per_side = 0.5
cost_slippage_bps_per_side = 0.5
cost_stress_min_ratio = 0.5
```

- [ ] **Step 2: Verify config**

Run:

```bash
conda run -n quant python - <<'PY'
from experiment_config import load_experiment_config
config = load_experiment_config("experiment.toml")
assert config.promotion.enabled is True
assert config.promotion.recent_window_ids == (
    "validation_2025_h1",
    "validation_2025_h2",
    "locked_recent_2026",
)
assert config.promotion.cost_fee_bps_per_side == 0.5
print("promotion config ok")
PY
```

Expected:

```text
promotion config ok
```

Commit:

```bash
git add experiment.toml
git commit -m "Enable promotion screening config"
```

---

### Task 6: Document Project Target And Promotion Protocol

**Files:**
- Create: `AGENTS.md`
- Modify: `program.md`
- Create: `tests/test_agents_contract.py`
- Modify: `tests/test_program_contract.py`

- [ ] **Step 1: Add docs tests**

Create `tests/test_agents_contract.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def test_agents_documents_project_target_and_protocol_entry_points():
    text = AGENTS.read_text()

    required = [
        "fast quant candidate research workbench",
        "not the final validation framework",
        "compact promotion screening",
        "comprehensive validation",
        "program.md",
        "README.md",
    ]
    for phrase in required:
        assert phrase in text
```

Append to `tests/test_program_contract.py`:

```python
def test_program_documents_promotion_screen_without_replacing_protocol():
    text = PROGRAM.read_text()
    normalized = " ".join(text.split())

    required = [
        "Promotion screening",
        "compact robustness filter",
        "not final validation",
        "Every scored explore enters promotion screening",
        "does not beat the primary window",
        "Do not chase one-window wins",
        "comprehensive validation",
    ]
    for phrase in required:
        assert phrase in normalized

    assert "Editable during a research loop:" in text
    assert "Evidence review" in text
    assert "The experiment loop" in text
```

- [ ] **Step 2: Create `AGENTS.md`**

Create:

```markdown
# AGENTS.md

## Project Target

This repo is a fast quant candidate research workbench. It is not the final
validation framework.

The goal is to iterate on one scratch strategy, run compact promotion
screening, and send only promoted candidates to comprehensive validation.

## Research Protocol

- Read `program.md` before running the research loop.
- Use `README.md` for repository file contracts and runner entry points.
- Treat `strategy.py` and `experiment.toml` as the ordinary editable research
  surface.
- Treat `runner.py`, `scoring.py`, `experiment_config.py`, tests, generated
  results, and ledgers as harness or evidence unless the user explicitly asks
  for harness changes.

## Quant Research Posture

- Promotion screening is loop feedback, not market evidence.
- Prefer simple robust candidates over complex fragile ones.
- Do not chase one-window wins.
- Do not call a promoted candidate validated; comprehensive validation is a
  separate downstream process.
```

- [ ] **Step 3: Add targeted `program.md` wording**

Keep the existing structure. Make only these targeted edits:

1. Replace the current goal lead:

```markdown
**The goal is simple: get the highest confirmed candidate score.**
```

with:

```markdown
**The goal is simple: find promoted candidates for comprehensive validation.**
```

2. Add after the first paragraph in `## Candidate confirmation`:

```markdown
## Promotion screening

Promotion screening is a compact robustness filter, not final validation. Every
scored explore enters promotion screening when promotion is enabled, even if it
does not beat the primary window. This prevents the primary recent window from
becoming the only optimizer target.

Do not chase one-window wins. Prefer simple robust candidates over complex
fragile candidates. A promoted candidate is ready for comprehensive validation;
it is not validated market evidence.
```

3. In the experiment-loop step that mentions confirmation, add:

```markdown
When promotion is enabled, a scored explore should auto-run promotion screening;
treat the promotion decision as the best-so-far gate for this workbench.
```

- [ ] **Step 4: Verify and commit**

Run:

```bash
conda run -n quant pytest tests/test_agents_contract.py tests/test_program_contract.py -q
```

Expected: pass.

Commit:

```bash
git add AGENTS.md program.md tests/test_agents_contract.py tests/test_program_contract.py
git commit -m "Document promotion screening research target"
```

---

### Task 7: Final Verification

**Files:**
- No planned edits unless verification exposes a defect.

- [ ] **Step 1: Run full test suite**

```bash
conda run -n quant pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run config sanity check**

```bash
conda run -n quant python - <<'PY'
from experiment_config import load_experiment_config
config = load_experiment_config("experiment.toml")
print({
    "promotion_enabled": config.promotion.enabled,
    "recent_windows": config.promotion.recent_window_ids,
    "rotating_probes": config.promotion.rotating_probe_window_ids,
    "cost_fee_bps_per_side": config.promotion.cost_fee_bps_per_side,
    "cost_slippage_bps_per_side": config.promotion.cost_slippage_bps_per_side,
})
PY
```

Expected:

```text
{'promotion_enabled': True, 'recent_windows': ('validation_2025_h1', 'validation_2025_h2', 'locked_recent_2026'), 'rotating_probes': ('stress_2022_deleveraging', 'stress_2022_ftx', 'recovery_2023_h1', 'research_2024_h1', 'research_2024_h2'), 'cost_fee_bps_per_side': 0.5, 'cost_slippage_bps_per_side': 0.5}
```

- [ ] **Step 3: Inspect git state**

```bash
git status --short
```

Expected: only pre-existing unrelated untracked files remain, or a clean tree.

---

## Self-Review Notes

Spec coverage:

- Every scored explore can enter promotion: Task 4.
- Primary-window rerun avoided: Task 4 test.
- Recent core, cost stress, rotating probe: Tasks 2 and 4.
- Deterministic rotating probe state: Tasks 2 and 3.
- Promotion ledger and artifacts: Tasks 3 and 4.
- Repo-local `AGENTS.md`: Task 6.
- Minimal `program.md` update: Task 6.
- Backward compatibility: Tasks 1, 3, and 4 keep defaults and legacy confirmation behavior.

Implementation boundaries:

- `promotion.py` owns pure decision logic.
- `runner.py` owns orchestration and persistence.
- `experiment_config.py` owns parsing and validation.
- Existing candidate scoring and attribution are reused.

---

## GSTACK REVIEW REPORT

Status: `DONE_WITH_CONCERNS`, with concerns patched into the plan.

### Step 0: Scope Challenge

Scope reduction accepted. The plan now stays on the existing harness instead of
building a parallel promotion system:

- Reuses `run_single_window_attempt()`, `build_candidate_score()`,
  `build_trade_attribution()`, `append_ledger()`, and `SessionState`.
- Adds one small config dataclass and one pure helper module.
- Keeps orchestration in `runner.py`.
- Defers full validation, UI, portfolio analytics, and upstream
  `quant_strategies` changes.

Layer assessment:

- [Layer 1] Existing runner/scoring/ledger patterns are reused.
- [Layer 3] The only new logic is quant-specific promotion decision math.
- Distribution check: no new binary, package, container, or external artifact is
  introduced.

### Architecture Review

Issues found and patched:

- `[P1] (confidence: 9/10) Task 1 / Task 4 - promotion recent core must include research.primary_window_id.`
  `_finish_promotion_attempt()` needs the primary recent result for the ledger.
  The plan now adds a config test and parser validation requiring
  `promotion.recent_window_ids` to include `research.primary_window_id`.
- `[P1] (confidence: 9/10) Task 4 - promotion sub-window exceptions would abort the research loop.`
  Confirmation already converts per-window crashes into failed evidence. The
  plan now mirrors that behavior in `run_promotion_screen()` via a local `_run()`
  wrapper around recent, cost-stress, and rotating-probe windows.
- `[P2] (confidence: 8/10) Task 4 - reused primary artifacts need traceability from promotion artifacts.`
  The plan now records `source_result_dirs`, `cost_stress_result_dir`, and
  `rotating_probe_result_dir` in `promotion_summary.json`.

No security or auth architecture applies. This is a local CLI workbench with
filesystem artifacts.

### Code Quality Review

Issues found and patched:

- `[P2] (confidence: 8/10) Task 3 - normal explore/confirm updates could erase promotion state.`
  The plan now explicitly says `update_state()` and
  `update_state_for_candidate()` must carry promotion fields forward.

No further module split recommended. A service layer, artifact registry, or new
workflow engine would be over-engineering for this project target.

### Test Review

Test framework: `pytest`, detected from `pyproject.toml`.

```text
CODE PATHS                                                     USER FLOWS
[+] experiment_config.py                                      [+] Config loading
  +-- [PLAN TEST] default promotion disabled                    +-- [PLAN TEST] old config still works
  +-- [PLAN TEST] enabled promotion parses                      +-- [PLAN TEST] bad window names rejected
  +-- [PLAN TEST] invalid cost ratio rejected                   +-- [PLAN TEST] missing primary in recent rejected
  +-- [PLAN TEST] zero-cost enabled promotion rejected

[+] promotion.py                                               [+] Promotion decision
  +-- [PLAN TEST] scored_for_promotion accepts scored only       +-- [PLAN TEST] weak cost stress rejects
  +-- [PLAN TEST] rotating probe index modulo list length        +-- [PLAN TEST] deep negative probe rejects
  +-- [PLAN TEST] cost stress config overrides costs only        +-- [PLAN TEST] simplification tolerance respected
  +-- [PLAN TEST] recent/cost/probe payload fields recorded

[+] runner.py                                                  [+] Explore loop
  +-- [PLAN TEST] scored explore enters promotion                +-- [PLAN TEST] primary is not rerun
  +-- [PLAN TEST] non-scored explore skips promotion             +-- [PLAN TEST] promotion row written to ledger
  +-- [PLAN TEST] cost-stress rejection path                     +-- [PLAN TEST] promotion state persisted
  +-- [PLAN TEST] sub-window exception becomes evidence          +-- [PLAN TEST] old session state loads
  +-- [PLAN TEST] old ledger schema migrates

[+] docs                                                       [+] Agent protocol
  +-- [PLAN TEST] AGENTS.md states project target                +-- [PLAN TEST] program.md keeps existing sections
  +-- [PLAN TEST] program.md states promotion is not validation
```

Planned coverage: 24/24 meaningful paths have explicit tests in the plan.
Quality mix: behavior and edge-path tests, no E2E needed because this is a CLI
runner and pure helper surface. Prompt/LLM changes: `program.md` changes are
covered by contract tests, not evals.

Test plan artifact written:
`~/.gstack/projects/quant_autoresearch/Season_Yang-main-eng-review-test-plan-20260523-131046.md`

### Performance Review

No performance issue requiring a plan change.

- Promotion adds bounded extra runs only after a scored explore, which matches
  the intended fast-funnel posture.
- Promotion stays sequential. That is acceptable here because it keeps disk IO
  and artifact generation predictable.
- Prior learning applied: `artifact_cleanup_peak_io`. Artifact cleanup reduces
  retained disk use, but peak disk IO still exists until `quant_strategies`
  supports pre-write suppression. This plan does not expand that scope.

### Failure Modes

```text
Failure mode                                      Test planned?  Handling planned?  User-visible result
Unknown promotion window id                       yes            yes                ConfigError
Primary window omitted from recent core            yes            yes                ConfigError
Non-scored explore                                 yes            yes                normal explore ledger row
Recent promotion sub-window raises                 yes            yes                reject with failed_reasons
Cost stress destroys edge                          yes            yes                reject with failed_reasons
Rotating probe below floor                         yes            yes                reject with failed_reasons
Old session state lacks promotion fields           yes            yes                defaults loaded
Old ledger lacks promotion columns                 yes            yes                schema migration
program.md accidentally rewritten                  yes            yes                contract test failure
```

Critical silent gaps: 0.

### Parallelization

Sequential implementation, no parallelization opportunity worth taking. The
plan mostly touches `runner.py`, `experiment_config.py`, and shared tests. Split
worktrees would create merge conflicts without reducing meaningful risk.

### TODOs.md Updates

No `TODOS.md` exists and no deferred item needs a TODO. Full downstream
validation remains explicitly out of scope in this plan, not a forgotten task.

### Completion Summary

- Step 0: Scope Challenge - scope reduced per recommendation.
- Architecture Review: 3 issues found, all patched in the plan.
- Code Quality Review: 1 issue found, patched in the plan.
- Test Review: diagram produced, 3 gaps identified and patched.
- Performance Review: 0 issues found.
- NOT in scope: written.
- What already exists: written.
- TODOS.md updates: 0 items proposed.
- Failure modes: 0 critical gaps flagged.
- Outside voice: skipped.
- Parallelization: 1 sequential lane, 0 parallel lanes.
- Lake Score: 4/4 recommendations chose complete-but-small handling.
- Unresolved decisions: 0.
