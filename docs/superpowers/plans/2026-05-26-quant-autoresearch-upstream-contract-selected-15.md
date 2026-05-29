# Quant Autoresearch Upstream Contract Selected 15 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `quant_autoresearch` to the current upstream `quant_strategies` runner and decision contracts, preserve the selected legacy 15, prepare `results/new_15/`, rebuild `results.tsv`, and remove every old result directory after verification.

**Architecture:** Keep `quant_autoresearch` as the research-loop orchestrator and delegate execution to upstream `quant_strategies.runner.run_config`. Update only the local contract boundary, scoring/artifact interpretation, selected-15 packaging, ledger schema, and the strategy template needed by selected variants. Make result deletion a guarded final step that can run only after selected package, imports, upstream config validation, and ledger checks pass.

**Tech Stack:** Python 3, `pytest`, stdlib `tomllib`/`csv`/`json`/`shutil`, upstream `quant_strategies` decision models and runner config loader, `conda run -n quant`.

---

## Files And Responsibilities

- `experiment_config.py`: keep workbench artifact profile names, but materialize upstream runner TOML with `[output].artifact_profile = "full"`.
- `scoring.py`: read active return fields from evidence v2 `screening_result.smoke_score.sum_weighted_trade_*`; classify current upstream stages.
- `artifact_policy.py`: retain/remove current upstream artifact filenames.
- `strategy.py`: remove public legacy signal contract; expose `validate_params` and `generate_decisions` with typed `StrategyDecision` and `ObservationRef` lineage.
- `runner.py`: keep using upstream `run_config`; add `result_dir` to ledger rows so selected legacy and future new rows can be traced after old run directories are deleted.
- `tools/research_handoff_rank.py`: keep existing campaign ranking behavior; the migration tool imports `build_handoff_ranking` without changing this file.
- `tools/selected_15_migration.py`: create selected-15 package, rebuild ledger, verify package, and hard-delete old direct `results/` children behind guards.
- `tests/test_experiment_config.py`: assert upstream TOML artifact profile mapping.
- `tests/test_scoring.py`: assert evidence v2 scoring, v2 trade attribution, and new stage classification.
- `tests/test_artifact_policy.py`: assert current upstream artifact filename retention/removal.
- `tests/test_strategy_contract.py`: assert strategy public API and typed decision lineage.
- `tests/test_runner.py`: assert ledger includes `result_dir`.
- `tests/test_selected_15_migration.py`: assert deterministic selection, package shape, ledger rebuild, and cleanup guard.
- `program.md`: update only contract/result-root language.
- `results/selected_15/`: generated selected legacy package.
- `results/new_15/`: empty destination for the next rerun.
- `results.tsv`: rebuilt ledger containing only selected legacy rows now and future new rerun rows later.

## Task 1: Materialize Upstream Artifact Profile

**Files:**
- Modify: `tests/test_experiment_config.py`
- Modify: `experiment_config.py`

- [ ] **Step 1: Add failing assertions for upstream artifact profile**

In `tests/test_experiment_config.py`, extend `test_materialize_runner_toml_uses_selected_window_dates` after the existing output assertions:

```python
    assert parsed["output"]["artifact_profile"] == "full"
    assert 'artifact_profile = "full"' in text
    assert 'artifact_profile = "research"' not in text
    assert 'artifact_profile = "debug"' not in text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py::test_materialize_runner_toml_uses_selected_window_dates -q
```

Expected: FAIL because `parsed["output"]` has no `artifact_profile`.

- [ ] **Step 3: Write the minimal implementation**

In `experiment_config.py`, update `materialize_runner_toml` immediately after the results directory is assigned:

```python
    output = dict(config.output)
    output["results_dir"] = str(results_dir)
    output["artifact_profile"] = "full"
```

Do not add `research` or `debug` to upstream TOML. Those remain local artifact retention names only.

- [ ] **Step 4: Verify the focused test passes**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py::test_materialize_runner_toml_uses_selected_window_dates -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add experiment_config.py tests/test_experiment_config.py
git commit -m "fix: emit upstream full artifact profile"
```

## Task 2: Read Evidence V2 Smoke Scores Only

**Files:**
- Modify: `tests/test_scoring.py`
- Modify: `scoring.py`

- [ ] **Step 1: Replace the test evidence helper with evidence v2 shape**

In `tests/test_scoring.py`, replace the `evidence(...)` helper with:

```python
def evidence(
    *,
    net_return: float = 0.03,
    gross_return: float = 0.04,
    funding_return: float = 0.002,
    cost_return: float = 0.01,
    trade_count: int = 25,
    passed: bool = True,
) -> dict[str, object]:
    screening_result = {
        "trade_count": trade_count,
        "smoke_score": {
            "sum_weighted_trade_net_return": net_return,
            "sum_weighted_trade_gross_return": gross_return,
            "sum_weighted_trade_funding_return": funding_return,
            "sum_weighted_trade_cost_return": cost_return,
        },
    }
    return {
        "schema_version": "quant_strategies.engine.evidence/v2",
        "mode": "validate",
        "strategy_id": "demo_strategy",
        "screening_result": screening_result,
        "validation_report": {
            "mode": "validate",
            "passed": passed,
            "gates": [
                {"name": "valid_inputs", "passed": True, "detail": "screening completed"},
                {"name": "positive_net", "passed": passed, "detail": f"net_return={net_return}"},
            ],
            "screening_result": screening_result,
        },
    }
```

- [ ] **Step 2: Add explicit assertions for funding return and missing smoke score**

In `test_build_score_returns_guarded_score_when_trade_count_is_sufficient`, add:

```python
    assert score["gross_return"] == 0.04
    assert score["funding_return"] == 0.002
    assert score["cost_return"] == 0.01
    assert score["failure_message"] is None
```

Replace `test_build_score_returns_runner_failed_when_net_return_is_missing_with_enough_trades` with:

```python
def test_build_score_returns_runner_failed_when_v2_smoke_score_is_missing_with_enough_trades():
    malformed_evidence = evidence(trade_count=25)
    del malformed_evidence["validation_report"]["screening_result"]["smoke_score"]
    del malformed_evidence["screening_result"]["smoke_score"]

    score = build_score(
        summary={"stage": "completed", "assessment_status": "smoke_passed"},
        evidence=malformed_evidence,
        min_score_trades=20,
        window_id="primary",
        failure_source=None,
    )

    assert score["status"] == "runner_failed"
    assert score["score"] is None
    assert score["raw_net_return"] is None
    assert score["funding_return"] is None
    assert score["trade_count"] == 25
    assert score["failure_source"] == "quant_strategies_error"
    assert "smoke_score.sum_weighted_trade_net_return" in score["failure_message"]
```

In `test_classify_failure_source_maps_runner_stages_and_messages`, add:

```python
    assert classify_failure_source("param_validation", "param validation failed") == "strategy_error"
    assert classify_failure_source("decision_generation", "decision generation failed") == "strategy_error"
```

- [ ] **Step 3: Update trade attribution tests to use top-level v2 screening results**

In `test_build_trade_attribution_groups_trade_evidence`, shape each evidence packet like:

```python
        "validation_2025_h1": {
            "schema_version": "quant_strategies.engine.evidence/v2",
            "screening_result": {
                "trades": [
                    trade("ETH-PERP", "short", "2025-01-02T08:01:00Z", 0.01, 0.009, 0.001),
                    trade("ETH-PERP", "long", "2025-01-02T12:01:00Z", -0.02, -0.019, -0.001),
                ]
            },
        },
```

Do the same for the `locked_recent_2026` evidence entry.

- [ ] **Step 4: Run the focused failing scoring tests**

Run:

```bash
conda run -n quant pytest tests/test_scoring.py -q
```

Expected: FAIL on missing `funding_return`, old field extraction, and stage classification.

- [ ] **Step 5: Implement evidence v2 extraction**

In `scoring.py`, add these helpers above `build_score`:

```python
SMOKE_SCORE_FIELDS = {
    "raw_net_return": "sum_weighted_trade_net_return",
    "gross_return": "sum_weighted_trade_gross_return",
    "funding_return": "sum_weighted_trade_funding_return",
    "cost_return": "sum_weighted_trade_cost_return",
}


def _screening_result_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    validation_report = evidence.get("validation_report")
    if isinstance(validation_report, dict):
        screening_result = validation_report.get("screening_result")
        if isinstance(screening_result, dict):
            return screening_result
    screening_result = evidence.get("screening_result")
    return screening_result if isinstance(screening_result, dict) else {}


def _v2_returns_from_screening_result(
    screening_result: dict[str, Any],
) -> tuple[float | None, float | None, float | None, float | None, str | None]:
    smoke_score = screening_result.get("smoke_score")
    if not isinstance(smoke_score, dict):
        return None, None, None, None, "missing screening_result.smoke_score.sum_weighted_trade_net_return"
    values: dict[str, float | None] = {}
    for payload_key, field_name in SMOKE_SCORE_FIELDS.items():
        values[payload_key] = _as_float_or_none(smoke_score.get(field_name))
        if values[payload_key] is None:
            return (
                None,
                None,
                None,
                None,
                f"missing screening_result.smoke_score.{field_name}",
            )
    return (
        values["raw_net_return"],
        values["gross_return"],
        values["funding_return"],
        values["cost_return"],
        None,
    )
```

- [ ] **Step 6: Wire v2 extraction into `build_score`**

In `build_score`, replace the current validation-report/screening-result extraction block with:

```python
    validation_report = evidence.get("validation_report")
    if not isinstance(validation_report, dict):
        validation_report = {}

    screening_result = _screening_result_from_evidence(evidence)
    trade_count = _as_int_or_none(screening_result.get("trade_count"))
    raw_net_return, gross_return, funding_return, cost_return, smoke_score_error = _v2_returns_from_screening_result(
        screening_result
    )
    passed_validation = validation_report.get("passed") is True
    failed_gates = _failed_gate_names(validation_report.get("gates"))

    failure_message = None
    if smoke_score_error is not None:
        status = "runner_failed"
        score = None
        failure_source = failure_source or "quant_strategies_error"
        failure_message = smoke_score_error
    elif trade_count is None or trade_count < min_score_trades:
        status = "insufficient_sample"
        score = None
    elif not passed_validation:
        status = "validation_failed"
        score = _window_normalized_score(raw_net_return, window_days)
    else:
        status = "scored"
        score = _window_normalized_score(raw_net_return, window_days)
```

Keep the no-evidence branch intact except pass `funding_return=None` and `failure_message=None` to `_payload`.

- [ ] **Step 7: Add `funding_return` and `failure_message` to `_payload`**

Change the `_payload` signature and returned dict:

```python
    funding_return: float | None,
    failure_message: str | None,
```

Return:

```python
        "funding_return": funding_return,
        "failure_message": failure_message,
```

Update every `_payload(...)` call to pass both fields.

- [ ] **Step 8: Update stage classification**

In `classify_failure_source`, change the strategy-stage set to:

```python
    if normalized_stage in {"strategy_import", "signal_generation", "decision_generation", "param_validation", "request_build"}:
        return "strategy_error"
```

- [ ] **Step 9: Update `_trades_from_evidence` to use the same v2 screening helper**

Replace `_trades_from_evidence` with:

```python
def _trades_from_evidence(evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    if evidence is None:
        return []
    screening_result = _screening_result_from_evidence(evidence)
    trades = screening_result.get("trades")
    if not isinstance(trades, list):
        return []
    return [trade for trade in trades if isinstance(trade, dict)]
```

- [ ] **Step 10: Verify scoring tests pass**

Run:

```bash
conda run -n quant pytest tests/test_scoring.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add scoring.py tests/test_scoring.py
git commit -m "fix: score upstream evidence v2 smoke results"
```

## Task 3: Refresh Artifact Policy For Current Upstream Files

**Files:**
- Modify: `tests/test_artifact_policy.py`
- Modify: `artifact_policy.py`

- [ ] **Step 1: Extend artifact fixture with current upstream filenames**

In `tests/test_artifact_policy.py`, update `write_artifacts` to write:

```python
    for name in (
        "config.toml",
        "summary.json",
        "evidence.json",
        "signals.csv",
        "decision_records.jsonl",
        "strategy_snapshot.py",
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
        "artifact_profile_summary.json",
        "data_manifest.json",
        "run_manifest.json",
        "notes.md",
    ):
        (result_dir / name).write_text(name + "\n")
```

- [ ] **Step 2: Update expected research-profile removals**

In `test_apply_artifact_policy_removes_large_debug_inputs_for_research_profile`, keep the expected removals as:

```python
    assert sorted(removed) == [
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ]
```

Add existence assertions:

```python
    assert (result_dir / "decision_records.jsonl").exists()
    assert (result_dir / "artifact_profile_summary.json").exists()
    assert (result_dir / "data_manifest.json").exists()
    assert (result_dir / "run_manifest.json").exists()
    assert (result_dir / "notes.md").exists()
```

- [ ] **Step 3: Update core keep flag test expected removals**

In `test_apply_artifact_policy_honors_core_keep_flags_for_research_profile`, use:

```python
    assert sorted(removed) == [
        "artifact_profile_summary.json",
        "config.toml",
        "data_manifest.json",
        "decision_records.jsonl",
        "engine_request.json",
        "evidence.json",
        "notes.md",
        "run_manifest.json",
        "signals.csv",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
        "strategy_snapshot.py",
        "summary.json",
    ]
```

- [ ] **Step 4: Run the focused failing artifact tests**

Run:

```bash
conda run -n quant pytest tests/test_artifact_policy.py -q
```

Expected: FAIL because the new filenames are not governed by `_ARTIFACTS`.

- [ ] **Step 5: Update artifact filename map**

In `artifact_policy.py`, replace `_ARTIFACTS` with:

```python
_ARTIFACTS = {
    "strategy_snapshot.py": "keep_strategy_snapshot",
    "config.toml": "keep_config",
    "summary.json": "keep_summary",
    "artifact_profile_summary.json": "keep_summary",
    "data_manifest.json": "keep_summary",
    "run_manifest.json": "keep_summary",
    "notes.md": "keep_summary",
    "evidence.json": "keep_evidence",
    "signals.csv": "keep_signals",
    "decision_records.jsonl": "keep_signals",
    "engine_request.json": "keep_engine_request",
    "strategy_input_rows.csv": "keep_input_rows_csv",
    "strategy_input_rows.jsonl": "keep_input_rows_jsonl",
}
```

- [ ] **Step 6: Verify artifact tests pass**

Run:

```bash
conda run -n quant pytest tests/test_artifact_policy.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add artifact_policy.py tests/test_artifact_policy.py
git commit -m "fix: retain current upstream artifacts"
```

## Task 4: Convert Strategy Template To Decision-Only Public Contract

**Files:**
- Create: `tests/test_strategy_contract.py`
- Modify: `strategy.py`

- [ ] **Step 1: Add strategy contract tests**

Create `tests/test_strategy_contract.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import strategy
from quant_strategies.decisions import ObservationRef, StrategyDecision


def _row(symbol: str, timestamp: datetime, funding_rate: float, has_event: bool = False) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "available_at": timestamp,
        "close": 100.0 + (timestamp.minute / 100.0),
        "funding_timestamp": timestamp if has_event else None,
        "funding_rate": funding_rate,
        "has_funding_event": has_event,
    }


def rows() -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    payload: list[dict[str, object]] = []
    for minute in range(0, 241):
        timestamp = start + timedelta(minutes=minute)
        payload.append(_row("BTC-PERP", timestamp, 0.0004, minute in {0, 120, 240}))
        payload.append(_row("ETH-PERP", timestamp, -0.0004, minute in {0, 120, 240}))
        payload.append(_row("ADA-PERP", timestamp, 0.0001, minute in {0, 120, 240}))
        payload.append(_row("LINK-PERP", timestamp, -0.0001, minute in {0, 120, 240}))
    return payload


def params() -> dict[str, object]:
    return {
        "funding_lookback_events": 2,
        "return_lookback_minutes": 120,
        "decision_interval_minutes": 120,
        "decision_lag_minutes": 1,
        "session_start_hour": 0,
        "session_end_hour": 24,
        "top_n": 1,
        "min_cross_section": 4,
        "min_abs_funding_bps": 1.0,
        "min_abs_return_bps": 0.0,
        "include_positive_funding_shorts": True,
        "include_negative_funding_longs": True,
        "min_same_sign_funding_events": 1,
        "min_tail_count": 1,
        "selection_score": "funding",
        "require_exit_horizon": False,
        "weight": 0.2,
        "hold_bars": 120,
        "short_hold_bars": 120,
        "long_hold_bars": 120,
        "state_mode": "suppress_until_exit",
    }


def test_strategy_exports_decision_contract_only():
    assert callable(strategy.generate_decisions)
    assert callable(strategy.validate_params)
    assert "generate_signals" not in strategy.__all__


def test_validate_params_returns_mapping_copy():
    source = params()
    validated = strategy.validate_params(source)

    assert validated == source
    assert validated is not source


def test_generate_decisions_returns_typed_decisions_with_observations():
    decisions = strategy.generate_decisions(rows(), params())

    assert decisions
    assert all(isinstance(decision, StrategyDecision) for decision in decisions)
    first = decisions[0]
    assert first.instrument.kind == "crypto_perp"
    assert first.target.sizing_kind == "target_weight"
    assert first.target.size == 0.2
    assert first.decision_time.tzinfo is not None
    assert first.as_of_time.tzinfo is not None
    assert first.as_of_time <= first.decision_time
    assert first.exit_policy.max_hold_bars == 120
    assert first.metadata["signal_family"] == "crypto_perp_funding_crowding_reversal_stateful_rebalance"
    assert first.metadata["state_mode"] == "suppress_until_exit"
    assert all(isinstance(item, ObservationRef) for item in first.observations)
    assert {item.field for item in first.observations} >= {"close", "funding_rate"}
```

- [ ] **Step 2: Run the focused failing strategy tests**

Run:

```bash
conda run -n quant pytest tests/test_strategy_contract.py -q
```

Expected: FAIL because `generate_signals` is still public and decisions do not include observations.

- [ ] **Step 3: Update imports and public exports**

In `strategy.py`, change the decision import and `__all__`:

```python
from quant_strategies.decisions import ExitPolicy, InstrumentRef, ObservationRef, PositionTarget, StrategyDecision

__all__ = ["validate_params", "generate_decisions"]
```

- [ ] **Step 4: Add a public parameter validator**

Add this function before the signal payload generator:

```python
def validate_params(params: Mapping[str, object]) -> dict[str, object]:
    validated = dict(params)
    _validate_scalar_params(validated)
    return validated
```

Add `_validate_scalar_params` below `_require_fields`:

```python
def _validate_scalar_params(params: Mapping[str, object]) -> None:
    _positive_int(params.get("funding_lookback_events", 3), "funding_lookback_events")
    _positive_int(params.get("return_lookback_minutes", 240), "return_lookback_minutes")
    _positive_int(params.get("decision_interval_minutes", 480), "decision_interval_minutes")
    _positive_int(params.get("decision_lag_minutes", 1), "decision_lag_minutes")
    _positive_int(params.get("top_n", 1), "top_n")
    _positive_int(params.get("min_cross_section", 4), "min_cross_section")
    _non_negative_float(params.get("min_abs_funding_bps", 1.0), "min_abs_funding_bps")
    _non_negative_float(params.get("min_abs_return_bps", 25.0), "min_abs_return_bps")
    _non_negative_float(params.get("max_short_return_extension_bps", 0.0), "max_short_return_extension_bps")
    _bool_param(params.get("include_positive_funding_shorts", True), "include_positive_funding_shorts")
    _bool_param(params.get("include_negative_funding_longs", True), "include_negative_funding_longs")
    _non_negative_int(params.get("min_same_sign_funding_events", 0), "min_same_sign_funding_events")
    _non_negative_float(params.get("min_latest_abs_funding_bps", 0.0), "min_latest_abs_funding_bps")
    _non_negative_int(params.get("volatility_lookback_minutes", 0), "volatility_lookback_minutes")
    _non_negative_float(params.get("min_abs_return_z", 0.0), "min_abs_return_z")
    _non_negative_int(params.get("recent_return_lookback_minutes", 0), "recent_return_lookback_minutes")
    _non_negative_float(
        params.get("max_recent_same_direction_return_bps", 0.0),
        "max_recent_same_direction_return_bps",
    )
    _non_negative_float(params.get("min_idiosyncratic_return_bps", 0.0), "min_idiosyncratic_return_bps")
    _non_negative_float(
        params.get("min_short_idiosyncratic_return_bps", params.get("min_idiosyncratic_return_bps", 0.0)),
        "min_short_idiosyncratic_return_bps",
    )
    _non_negative_float(
        params.get("min_long_idiosyncratic_return_bps", params.get("min_idiosyncratic_return_bps", 0.0)),
        "min_long_idiosyncratic_return_bps",
    )
    _non_negative_int(params.get("symbol_cooldown_minutes", 0), "symbol_cooldown_minutes")
    _positive_int(params.get("min_tail_count", 1), "min_tail_count")
    _bool_param(params.get("balance_sides", False), "balance_sides")
    selection_score = str(params.get("selection_score", "funding"))
    if selection_score not in {"funding", "return", "product"}:
        raise ValueError("selection_score must be one of: funding, return, product")
    _bool_param(params.get("require_exit_horizon", False), "require_exit_horizon")
    weight = float(params.get("weight", 1.0))
    if not math.isfinite(weight) or weight <= 0.0:
        raise ValueError("weight must be finite and positive")
    hold_bars = _positive_int(params.get("hold_bars", params.get("hold_minutes", 480)), "hold_bars")
    _positive_int(params.get("short_hold_bars", hold_bars), "short_hold_bars")
    _positive_int(params.get("long_hold_bars", hold_bars), "long_hold_bars")
    _non_negative_float(params.get("high_extension_short_return_bps", 0.0), "high_extension_short_return_bps")
    _positive_int(
        params.get("high_extension_short_hold_bars", params.get("short_hold_bars", hold_bars)),
        "high_extension_short_hold_bars",
    )
    state_mode = str(params.get("state_mode", "suppress_until_exit"))
    if state_mode not in {"off", "suppress_until_exit"}:
        raise ValueError("state_mode must be one of: off, suppress_until_exit")
    _non_negative_int(params.get("overlap_exit_buffer_bars", 2), "overlap_exit_buffer_bars")
    _exit_controls(params)
```

- [ ] **Step 5: Rename the legacy signal generator to a private helper**

Rename:

```python
def generate_signals(bars: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> list[dict[str, object]]:
```

to:

```python
def _generate_signal_payloads(bars: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> list[dict[str, object]]:
```

At the top of that helper, after the empty-bars check and field check, call:

```python
    _validate_scalar_params(params)
```

Update `generate_decisions` to iterate over `_generate_signal_payloads(bars, params)`.

- [ ] **Step 6: Add observation lineage to candidates and signals**

In `_decision_candidates`, add observation fields when appending a candidate:

```python
        observed_time = decision_time - timedelta(minutes=1)
        base_time = decision_time - timedelta(minutes=return_lookback_minutes)
```

Use these keys in the candidate payload:

```python
                "observation_refs": (
                    ObservationRef(symbol=symbol, timestamp=observed_time, field="close", source="quant_data"),
                    ObservationRef(symbol=symbol, timestamp=base_time, field="close", source="quant_data"),
                    *funding_stats["observation_refs"],
                ),
```

Change `_funding_pressure_stats` so each recent funding event creates an observation:

```python
    observation_refs = tuple(
        ObservationRef(symbol=symbol, timestamp=row_timestamp, field="funding_rate", source="quant_data")
        for _, (row_timestamp, _) in recent
    )
```

Because `_funding_pressure_stats` currently receives only `_SymbolRows`, first add a `symbol: str` parameter and pass it from `_decision_candidates`:

```python
        funding_stats = _funding_pressure_stats(symbol, rows, decision_time, funding_lookback_events)
```

Return the observation refs:

```python
        "observation_refs": observation_refs,
```

In `_signal`, include:

```python
        "observations": tuple(candidate.get("observation_refs", ())),
```

- [ ] **Step 7: Pass observations into `StrategyDecision`**

In `generate_decisions`, add:

```python
                observations=tuple(signal.get("observations", ())),
```

inside `StrategyDecision(...)`.

- [ ] **Step 8: Verify strategy contract tests pass**

Run:

```bash
conda run -n quant pytest tests/test_strategy_contract.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add strategy.py tests/test_strategy_contract.py
git commit -m "refactor: expose decision-only strategy contract"
```

## Task 5: Add Result Directory To Ledger Schema

**Files:**
- Modify: `runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Add failing ledger tests for result directory**

In `tests/test_runner.py`, update both direct `append_ledger(...)` calls in `test_append_ledger_writes_candidate_columns` and `test_append_ledger_writes_promotion_columns` to pass:

```python
        result_dir=Path("results/example"),
```

Add assertions after reading rows:

```python
    assert rows[0]["result_dir"] == "results/example"
```

- [ ] **Step 2: Run focused failing ledger tests**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_append_ledger_writes_candidate_columns tests/test_runner.py::test_append_ledger_writes_promotion_columns -q
```

Expected: FAIL because `append_ledger` does not accept `result_dir`.

- [ ] **Step 3: Add `result_dir` to ledger headers**

In `runner.py`, add `"result_dir"` to `SYMBOL_LEDGER_HEADER` immediately after `"window_id"`:

```python
    "window_id",
    "result_dir",
    "window_start",
```

This preserves automatic migration from old headers because `_ensure_ledger_schema` already writes missing fields as blanks.

- [ ] **Step 4: Add `result_dir` to `append_ledger`**

Change the function signature:

```python
    result_dir: Path | str,
```

Add this writer field:

```python
                "result_dir": str(result_dir),
```

- [ ] **Step 5: Pass result directories at call sites**

In `_finish_attempt`, add to `append_ledger(...)`:

```python
        result_dir=result_dir,
```

In `_finish_confirmation_attempt`, add:

```python
        result_dir=candidate_dir,
```

In `_finish_promotion_attempt`, add:

```python
        result_dir=promotion_dir,
```

- [ ] **Step 6: Verify focused ledger tests pass**

Run:

```bash
conda run -n quant pytest tests/test_runner.py::test_append_ledger_writes_candidate_columns tests/test_runner.py::test_append_ledger_writes_promotion_columns -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add runner.py tests/test_runner.py
git commit -m "chore: record result directories in ledger"
```

## Task 6: Build Selected 15 Migration Tool

**Files:**
- Create: `tools/selected_15_migration.py`
- Create: `tests/test_selected_15_migration.py`

- [ ] **Step 1: Add pure selection tests**

Create `tests/test_selected_15_migration.py` with these imports and helpers:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import tomllib

from tools.selected_15_migration import (
    cleanup_results_root,
    rebuild_results_ledger,
    select_top_variants_from_rankings,
    verify_selected_package,
    write_selected_package,
)


def variant(family: str, rank: int, score: float) -> dict[str, object]:
    return {
        "variant_id": f"{family}-{rank}",
        "family": family,
        "params": {"weight": 0.2, "hold_bars": 120 + rank},
        "strategy_source_sha": f"sha-{family}-{rank}",
        "attempt_ids": [rank],
        "attempt_dirs": [f"results/campaign/{family}/{rank}"],
        "recent_window_scores": [
            {
                "window_id": "locked_recent_2026",
                "score": score,
                "status": "scored",
                "trade_count": 200 + rank,
                "result_dir": f"results/campaign/{family}/{rank}",
            }
        ],
        "evidence_result_dirs": [f"results/campaign/{family}/{rank}"],
        "missing_recent_windows": [],
        "base_score": score,
        "promotion_score": score,
        "recent_window_score_stdev": 0.0,
        "trade_count": 200 + rank,
        "min_trade_count": 200 + rank,
        "required_min_trades": 80,
        "penalties": {},
        "blended_score": score,
        "promotion_dir": None,
        "promotion_summary": None,
        "cost_stress_score": score,
    }
```

Add:

```python
def test_select_top_variants_from_rankings_picks_three_families_and_five_each():
    ranking = {
        "method_version": "test",
        "generated_at": "2026-05-26T00:00:00+00:00",
        "campaign_dir": "results/campaign",
        "variants": [
            *(variant("time_only_exit", rank, 0.010 - rank / 1000) for rank in range(1, 7)),
            *(variant("entry_filter", rank, 0.009 - rank / 1000) for rank in range(1, 7)),
            *(variant("selection_or_breadth", rank, 0.008 - rank / 1000) for rank in range(1, 7)),
            *(variant("lookback_or_cadence", rank, 0.001 - rank / 1000) for rank in range(1, 7)),
        ],
    }

    selected = select_top_variants_from_rankings([ranking])

    assert len(selected) == 15
    assert [item["family"] for item in selected[:5]] == ["time_only_exit"] * 5
    assert [item["family"] for item in selected[5:10]] == ["entry_filter"] * 5
    assert [item["family"] for item in selected[10:15]] == ["selection_or_breadth"] * 5
    assert [item["rank"] for item in selected[:5]] == [1, 2, 3, 4, 5]
```

- [ ] **Step 2: Add package, ledger, verification, and cleanup tests**

Add:

```python
def test_write_selected_package_rebuilds_ledger_and_cleanup_is_guarded(tmp_path: Path):
    results_root = tmp_path / "results"
    results_root.mkdir()
    (results_root / "old_campaign").mkdir()
    (results_root / "research_briefs").mkdir()
    strategy_template = tmp_path / "strategy.py"
    strategy_template.write_text(
        "from quant_strategies.decisions import ExitPolicy, InstrumentRef, PositionTarget, StrategyDecision\n"
        "def validate_params(params):\n"
        "    return dict(params)\n"
        "def generate_decisions(rows, params):\n"
        "    return []\n"
    )
    experiment_config = {
        "strategy_id": "demo_strategy",
        "data": {
            "kind": "crypto_perp_funding",
            "symbols": ["BTC-PERP", "ETH-PERP"],
            "strict": True,
        },
        "fill_model": {"price": "close", "entry_lag_bars": 1, "exit_lag_bars": 1},
        "cost_model": {"fee_bps_per_side": 0.0, "slippage_bps_per_side": 0.0},
        "output": {"mode": "validate"},
        "windows": [{"id": "locked_recent_2026", "start": "2025-10-16", "end": "2026-04-13"}],
    }
    selected = [
        {**variant("time_only_exit", rank, 0.010 - rank / 1000), "rank": rank, "source_ranking": "test"}
        for rank in range(1, 6)
    ] + [
        {**variant("entry_filter", rank, 0.009 - rank / 1000), "rank": rank, "source_ranking": "test"}
        for rank in range(1, 6)
    ] + [
        {**variant("selection_or_breadth", rank, 0.008 - rank / 1000), "rank": rank, "source_ranking": "test"}
        for rank in range(1, 6)
    ]

    manifest = write_selected_package(
        results_root=results_root,
        selected=selected,
        strategy_template=strategy_template,
        experiment_config=experiment_config,
        selection_method_version="selected_15_v1",
    )
    verify_selected_package(results_root / "selected_15")
    rebuild_results_ledger(results_root=results_root, manifest=manifest, ledger_path=tmp_path / "results.tsv")
    cleanup_results_root(results_root)

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert len(rows) == 15
    assert {row["run_kind"] for row in rows} == {"selected_legacy"}
    assert {row["status"] for row in rows} == {"selected"}
    assert all(row["result_dir"].startswith(str(results_root / "selected_15")) for row in rows)
    assert sorted(path.name for path in results_root.iterdir()) == ["new_15", "selected_15"]
    config_path = results_root / "selected_15" / "time_only_exit" / "rank_01" / "config.toml"
    parsed = tomllib.loads(config_path.read_text())
    assert parsed["output"]["artifact_profile"] == "full"
    assert parsed["output"]["results_dir"].endswith("results/new_15/time_only_exit/rank_01")
```

Add:

```python
def test_verify_selected_package_rejects_wrong_variant_count(tmp_path: Path):
    selected_root = tmp_path / "selected_15"
    selected_root.mkdir()
    (selected_root / "selection_manifest.json").write_text(json.dumps({"variants": []}) + "\n")

    with pytest.raises(ValueError, match="exactly 15"):
        verify_selected_package(selected_root)
```

- [ ] **Step 3: Run failing migration tests**

Run:

```bash
conda run -n quant pytest tests/test_selected_15_migration.py -q
```

Expected: FAIL because `tools/selected_15_migration.py` does not exist.

- [ ] **Step 4: Implement selection and TOML writing helpers**

Create `tools/selected_15_migration.py` with:

```python
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quant_strategies.decisions.strategy_loader import load_decision_strategy
from quant_strategies.runner.config import load_config

from runner import LEDGER_HEADER
from tools.research_handoff_rank import build_handoff_ranking


METHOD_VERSION = "selected_15_migration_v1"
PRESERVED_RESULTS = {"selected_15", "new_15"}


def select_top_variants_from_rankings(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for ranking_index, ranking in enumerate(rankings):
        source = str(ranking.get("campaign_dir") or ranking.get("source_path") or f"ranking_{ranking_index}")
        for raw_variant in ranking.get("variants", []):
            if not isinstance(raw_variant, dict):
                continue
            variant_id = str(raw_variant["variant_id"])
            candidate = {**raw_variant, "source_ranking": source}
            existing = candidates.get(variant_id)
            if existing is None or _variant_sort_key(candidate) < _variant_sort_key(existing):
                candidates[variant_id] = candidate

    by_family: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates.values():
        by_family.setdefault(str(candidate["family"]), []).append(candidate)
    if len(by_family) < 3:
        raise ValueError("selection requires at least three families")

    for family_variants in by_family.values():
        family_variants.sort(key=_variant_sort_key)
    selected_families = sorted(by_family, key=lambda family: _variant_sort_key(by_family[family][0]))[:3]

    selected: list[dict[str, Any]] = []
    for family in selected_families:
        family_variants = by_family[family][:5]
        if len(family_variants) != 5:
            raise ValueError(f"family {family} has {len(family_variants)} variants; expected 5")
        for rank, variant in enumerate(family_variants, start=1):
            selected.append({**variant, "family": family, "rank": rank})
    if len(selected) != 15:
        raise ValueError(f"selected {len(selected)} variants; expected 15")
    return selected


def _variant_sort_key(variant: dict[str, Any]) -> tuple[float, float, float, int, str]:
    blended = _float_or_default(variant.get("blended_score"), -1.0e18)
    promotion = _float_or_default(variant.get("promotion_score"), -1.0e18)
    stdev = _float_or_default(variant.get("recent_window_score_stdev"), 1.0e18)
    trades = _int_or_default(variant.get("trade_count"), 0)
    return (-blended, -promotion, stdev, -trades, str(variant.get("variant_id", "")))


def _float_or_default(value: object, default: float) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else default


def _int_or_default(value: object, default: int) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else default
```

- [ ] **Step 5: Implement package writing and config materialization**

Add:

```python
def write_selected_package(
    *,
    results_root: Path,
    selected: list[dict[str, Any]],
    strategy_template: Path,
    experiment_config: dict[str, Any],
    selection_method_version: str = METHOD_VERSION,
) -> dict[str, Any]:
    selected_root = results_root / "selected_15"
    new_root = results_root / "new_15"
    if selected_root.exists():
        shutil.rmtree(selected_root)
    selected_root.mkdir(parents=True)
    new_root.mkdir(parents=True, exist_ok=True)

    variants: list[dict[str, Any]] = []
    for item in selected:
        family = str(item["family"])
        rank = int(item["rank"])
        variant_dir = selected_root / family / f"rank_{rank:02d}"
        variant_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(strategy_template, variant_dir / "strategy.py")
        _write_runner_config(
            variant_dir / "config.toml",
            strategy_id=str(experiment_config["strategy_id"]),
            strategy_path=variant_dir / "strategy.py",
            params=dict(item["params"]),
            experiment_config=experiment_config,
            results_dir=new_root / family / f"rank_{rank:02d}",
        )
        source_summary = _source_summary(item, strategy_template)
        _write_json(variant_dir / "source_summary.json", source_summary)
        variants.append(
            {
                "family": family,
                "rank": rank,
                "variant_id": str(item["variant_id"]),
                "result_dir": str(variant_dir),
                "config_path": str(variant_dir / "config.toml"),
                "strategy_path": str(variant_dir / "strategy.py"),
                "source_summary_path": str(variant_dir / "source_summary.json"),
                "source_ranking": str(item.get("source_ranking", "")),
                "attempt_ids": item.get("attempt_ids", []),
                "attempt_dirs": item.get("attempt_dirs", []),
                "evidence_result_dirs": item.get("evidence_result_dirs", []),
                "recent_window_scores": item.get("recent_window_scores", []),
                "params": item["params"],
                "score": item.get("blended_score"),
                "raw_net_return": item.get("base_score"),
                "promotion_score": item.get("promotion_score"),
                "trade_count": item.get("trade_count"),
                "min_trade_count": item.get("min_trade_count"),
                "strategy_source_sha": item.get("strategy_source_sha"),
            }
        )

    manifest = {
        "selection_method_version": selection_method_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "variant_count": len(variants),
        "variants": variants,
    }
    _write_json(selected_root / "selection_manifest.json", manifest)
    return manifest


def _write_runner_config(
    path: Path,
    *,
    strategy_id: str,
    strategy_path: Path,
    params: dict[str, Any],
    experiment_config: dict[str, Any],
    results_dir: Path,
) -> None:
    window = _primary_window(experiment_config)
    data = dict(experiment_config["data"])
    data["start"] = window["start"]
    data["end"] = window["end"]
    output = {"results_dir": str(results_dir), "mode": experiment_config["output"]["mode"], "artifact_profile": "full"}
    sections = [
        _format_key_value("strategy_path", str(strategy_path)),
        _format_key_value("strategy_id", strategy_id),
        "",
        _format_table("data", data),
        "",
        _format_table("params", params),
        "",
        _format_table("fill_model", dict(experiment_config["fill_model"])),
        "",
        _format_table("cost_model", dict(experiment_config["cost_model"])),
        "",
        _format_table("output", output),
    ]
    path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
```

- [ ] **Step 6: Implement verification, ledger rebuild, and cleanup**

Add:

```python
def verify_selected_package(selected_root: Path, *, repo_root: Path | None = None) -> None:
    manifest_path = selected_root / "selection_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"missing selection manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variants = manifest.get("variants")
    if not isinstance(variants, list) or len(variants) != 15:
        raise ValueError("selection manifest must contain exactly 15 variants")
    variant_dirs = sorted(path for path in selected_root.glob("*/rank_*") if path.is_dir())
    if len(variant_dirs) != 15:
        raise ValueError(f"selected package must contain exactly 15 variant directories; found {len(variant_dirs)}")
    seen: set[tuple[str, int]] = set()
    root = (repo_root or selected_root.parents[1]).resolve()
    for variant in variants:
        family = str(variant["family"])
        rank = int(variant["rank"])
        key = (family, rank)
        if key in seen:
            raise ValueError(f"duplicate selected variant: {family} rank {rank}")
        seen.add(key)
        variant_dir = selected_root / family / f"rank_{rank:02d}"
        for filename in ("strategy.py", "config.toml", "source_summary.json"):
            if not (variant_dir / filename).exists():
                raise ValueError(f"missing {filename}: {variant_dir}")
        load_decision_strategy(variant_dir / "strategy.py", repo_root=root)
        load_config(variant_dir / "config.toml", repo_root=root)


def rebuild_results_ledger(*, results_root: Path, manifest: dict[str, Any], ledger_path: Path) -> None:
    rows = [_selected_legacy_row(results_root, variant) for variant in manifest["variants"]]
    ledger_path.write_text("", encoding="utf-8")
    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_HEADER, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _selected_legacy_row(results_root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    row = {field: "" for field in LEDGER_HEADER}
    row.update(
        {
            "attempt": int(variant["rank"]),
            "window_id": "selected_legacy",
            "result_dir": str(results_root / "selected_15" / str(variant["family"]) / f"rank_{int(variant['rank']):02d}"),
            "score": "" if variant.get("score") is None else variant["score"],
            "raw_net_return": "" if variant.get("raw_net_return") is None else variant["raw_net_return"],
            "trade_count": "" if variant.get("trade_count") is None else variant["trade_count"],
            "status": "selected",
            "description": f"selected legacy {variant['family']} rank {int(variant['rank']):02d}",
            "run_kind": "selected_legacy",
            "promotion_score": "" if variant.get("promotion_score") is None else variant["promotion_score"],
        }
    )
    return row


def cleanup_results_root(results_root: Path) -> list[Path]:
    selected_root = results_root / "selected_15"
    verify_selected_package(selected_root, repo_root=results_root.parent)
    (results_root / "new_15").mkdir(exist_ok=True)
    removed: list[Path] = []
    for child in sorted(results_root.iterdir()):
        if child.name in PRESERVED_RESULTS:
            continue
        if child.parent.resolve() != results_root.resolve():
            raise ValueError(f"refusing to delete outside results root: {child}")
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed.append(child)
    return removed
```

- [ ] **Step 7: Add formatting and JSON helpers**

Add:

```python
def _primary_window(experiment_config: dict[str, Any]) -> dict[str, Any]:
    active_window_id = experiment_config.get("active_window_id") or experiment_config.get("research", {}).get("primary_window_id")
    windows = experiment_config.get("windows", [])
    for window in windows:
        if window.get("id") == active_window_id:
            return dict(window)
    if windows:
        return dict(windows[0])
    raise ValueError("experiment config has no windows")


def _source_summary(item: dict[str, Any], strategy_template: Path) -> dict[str, Any]:
    return {
        "variant_id": item["variant_id"],
        "family": item["family"],
        "rank": item["rank"],
        "source_ranking": item.get("source_ranking", ""),
        "attempt_ids": item.get("attempt_ids", []),
        "attempt_dirs": item.get("attempt_dirs", []),
        "evidence_result_dirs": item.get("evidence_result_dirs", []),
        "recent_window_scores": item.get("recent_window_scores", []),
        "strategy_source_sha": item.get("strategy_source_sha"),
        "migrated_strategy_template_sha256": _file_sha256(strategy_template),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_table(name: str, values: dict[str, Any]) -> str:
    lines = [f"[{name}]"]
    for key, value in values.items():
        lines.append(_format_key_value(str(key), value))
    return "\n".join(lines)


def _format_key_value(key: str, value: Any) -> str:
    return f"{key} = {_format_toml_value(value)}"


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    return json.dumps(str(value))
```

- [ ] **Step 8: Add discovery and CLI**

Add:

```python
def discover_rankings(results_root: Path) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    for child in sorted(results_root.iterdir()):
        if child.name in PRESERVED_RESULTS:
            continue
        if child.is_dir() and any(path.name == "score.json" for path in child.glob("*/score.json")):
            rankings.append(build_handoff_ranking(child))
    for ranking_path in sorted(results_root.glob("researched/**/selection/handoff_ranking.json")):
        ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
        ranking["source_path"] = str(ranking_path)
        rankings.append(ranking)
    if not rankings:
        raise ValueError(f"no rankings discovered under {results_root}")
    return rankings


def load_experiment_config_dict(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--experiment-config", default="experiment.toml")
    parser.add_argument("--strategy-template", default="strategy.py")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)

    results_root = Path(args.results_root)
    if args.verify_only:
        verify_selected_package(results_root / "selected_15", repo_root=results_root.parent)
        return 0

    rankings = discover_rankings(results_root)
    selected = select_top_variants_from_rankings(rankings)
    if not args.write:
        print(json.dumps({"selected": selected}, indent=2, sort_keys=True))
        return 0

    manifest = write_selected_package(
        results_root=results_root,
        selected=selected,
        strategy_template=Path(args.strategy_template),
        experiment_config=load_experiment_config_dict(Path(args.experiment_config)),
    )
    verify_selected_package(results_root / "selected_15", repo_root=results_root.parent)
    rebuild_results_ledger(results_root=results_root, manifest=manifest, ledger_path=results_root.parent / "results.tsv")
    if args.cleanup:
        cleanup_results_root(results_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Verify migration tests pass**

Run:

```bash
conda run -n quant pytest tests/test_selected_15_migration.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add tools/selected_15_migration.py tests/test_selected_15_migration.py
git commit -m "feat: package selected 15 migration"
```

## Task 7: Update Program Contract Language

**Files:**
- Modify: `program.md`

- [ ] **Step 1: Update setup strategy contract text**

In the setup section, replace:

```markdown
Keep the file shaped like a normal `quant_strategies` strategy module.
```

with:

```markdown
Keep the file shaped like a current `quant_strategies` decision strategy module:
it exposes `generate_decisions(rows, params)` returning typed
`StrategyDecision` objects, with optional `validate_params(params)`.
```

- [ ] **Step 2: Update output artifact language**

In the output format section, replace the explore artifact list with:

```bash
RESULT_DIR=results/new_15/time_only_exit/rank_01
cat "$RESULT_DIR"/score.json
cat "$RESULT_DIR"/summary.json
cat "$RESULT_DIR"/evidence.json
cat "$RESULT_DIR"/decision_records.jsonl
```

Add this sentence immediately below:

```markdown
Scoring reads upstream evidence v2 smoke-score fields under
`screening_result.smoke_score.sum_weighted_trade_*`; trade attribution requires
the upstream `full` artifact profile so evidence includes trades.
```

- [ ] **Step 3: Update result-root language**

In the logging section, add:

```markdown
After the selected-15 migration, preserved result roots are
`results/selected_15/` for the curated legacy package and `results/new_15/`
for the next rerun package. Old campaign attempt directories are not part of
the active research record after cleanup.
```

- [ ] **Step 4: Verify the exact new contract text exists**

Run:

```bash
rg "StrategyDecision|sum_weighted_trade|results/selected_15|results/new_15" program.md
```

Expected: all four terms appear.

- [ ] **Step 5: Commit**

```bash
git add program.md
git commit -m "docs: update research loop contract language"
```

## Task 8: Run Integrated Verification Before Touching Results

**Files:**
- No new edits unless a previous task failed.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py tests/test_scoring.py tests/test_artifact_policy.py tests/test_strategy_contract.py tests/test_selected_15_migration.py tests/test_runner.py -q
```

Expected: PASS.

- [ ] **Step 2: Dry-run selected-15 selection**

Run:

```bash
conda run -n quant python tools/selected_15_migration.py --results-root results
```

Expected: prints JSON with exactly 15 selected items across exactly 3 families. No files are written.

- [ ] **Step 3: Inspect selected families and make a stop/go note**

Run:

```bash
conda run -n quant python tools/selected_15_migration.py --results-root results > /tmp/quant_autoresearch_selected_15_dry_run.json
```

Then run:

```bash
conda run -n quant python -m json.tool /tmp/quant_autoresearch_selected_15_dry_run.json | rg '"family"|"variant_id"|"blended_score"|"promotion_score"'
```

Expected: selected variants match the approved top-three family logic: `time_only_exit`, `entry_filter`, and `selection_or_breadth`, unless the deterministic combined evidence ranking shows a different top-three set. If the family set differs, stop and report the selected family set before writing.

- [ ] **Step 4: Confirm verification-only fixes are already committed**

If no fixes were needed, continue. If fixes were needed, return to the task that introduced the fix and run that task's exact `git add ...` and `git commit ...` command before continuing. Do not create a catch-all verification commit here.

Run:

```bash
git status --short
```

Expected: no uncommitted source changes from Tasks 1-7 except generated ignored result artifacts.

## Task 9: Write Selected 15, Rebuild Ledger, And Hard-Delete Old Results

**Files:**
- Generate: `results/selected_15/`
- Generate: `results/new_15/`
- Rewrite: `results.tsv`
- Delete: every direct child under `results/` except `selected_15` and `new_15`

- [ ] **Step 1: Write selected package and cleanup through the guarded tool**

Run:

```bash
conda run -n quant python tools/selected_15_migration.py --results-root results --experiment-config experiment.toml --strategy-template strategy.py --write --cleanup
```

Expected:
- `results/selected_15/selection_manifest.json` exists.
- `results/new_15/` exists.
- `results.tsv` is rewritten.
- Old direct children such as `results/stateful_rebalance_50`, `results/stateful_rebalance_bold_100`, `results/researched`, `results/research_briefs`, and `results/validation_feedback` are deleted.

- [ ] **Step 2: Verify selected package after deletion**

Run:

```bash
conda run -n quant python tools/selected_15_migration.py --results-root results --verify-only
```

Expected: exit code 0.

- [ ] **Step 3: Verify only two result roots remain**

Run:

```bash
find results -mindepth 1 -maxdepth 1 -print | sort
```

Expected exactly:

```text
results/new_15
results/selected_15
```

- [ ] **Step 4: Verify selected legacy ledger rows**

Run:

```bash
conda run -n quant python - <<'PY'
import csv
from pathlib import Path

rows = list(csv.DictReader(Path("results.tsv").read_text().splitlines(), delimiter="\t"))
assert len(rows) == 15, len(rows)
assert {row["run_kind"] for row in rows} == {"selected_legacy"}
assert {row["status"] for row in rows} == {"selected"}
assert all(row["result_dir"].startswith("results/selected_15/") or "/results/selected_15/" in row["result_dir"] for row in rows)
print("results.tsv selected legacy rows:", len(rows))
PY
```

Expected: prints `results.tsv selected legacy rows: 15`.

- [ ] **Step 5: Verify every selected config loads through upstream**

Run:

```bash
conda run -n quant python - <<'PY'
from pathlib import Path
from quant_strategies.runner.config import load_config

root = Path.cwd()
configs = sorted(Path("results/selected_15").glob("*/rank_*/config.toml"))
assert len(configs) == 15, len(configs)
for config in configs:
    loaded = load_config(config, repo_root=root)
    assert loaded.output.artifact_profile == "full"
print("validated selected configs:", len(configs))
PY
```

Expected: prints `validated selected configs: 15`.

- [ ] **Step 6: Verify every selected strategy imports through upstream loader**

Run:

```bash
conda run -n quant python - <<'PY'
from pathlib import Path
from quant_strategies.decisions.strategy_loader import load_decision_strategy

root = Path.cwd()
strategies = sorted(Path("results/selected_15").glob("*/rank_*/strategy.py"))
assert len(strategies) == 15, len(strategies)
for strategy_path in strategies:
    loaded = load_decision_strategy(strategy_path, repo_root=root)
    assert callable(loaded)
print("validated selected strategies:", len(strategies))
PY
```

Expected: prints `validated selected strategies: 15`.

- [ ] **Step 7: Commit source changes, not ignored results**

Run:

```bash
git status --short
```

Expected: source/doc/test/tool changes are tracked or ready to commit; generated `results/` and `results.tsv` may remain ignored. Commit source changes if any remain uncommitted:

```bash
git add experiment_config.py scoring.py artifact_policy.py strategy.py runner.py program.md tools/selected_15_migration.py tests/test_experiment_config.py tests/test_scoring.py tests/test_artifact_policy.py tests/test_strategy_contract.py tests/test_selected_15_migration.py tests/test_runner.py
git commit -m "chore: migrate autoresearch to upstream decision contracts"
```

If all source changes were committed in earlier tasks, skip the commit.

## Task 10: Final Verification Report

**Files:**
- No edits.

- [ ] **Step 1: Capture final verification commands**

Run:

```bash
conda run -n quant pytest tests/test_experiment_config.py tests/test_scoring.py tests/test_artifact_policy.py tests/test_strategy_contract.py tests/test_selected_15_migration.py tests/test_runner.py -q
```

Expected: PASS.

Run:

```bash
find results -mindepth 1 -maxdepth 1 -print | sort
```

Expected exactly:

```text
results/new_15
results/selected_15
```

Run:

```bash
conda run -n quant python - <<'PY'
import csv
import json
from pathlib import Path

manifest = json.loads(Path("results/selected_15/selection_manifest.json").read_text())
rows = list(csv.DictReader(Path("results.tsv").read_text().splitlines(), delimiter="\t"))
print("selected variants:", manifest["variant_count"])
print("ledger rows:", len(rows))
print("ledger run kinds:", sorted({row["run_kind"] for row in rows}))
PY
```

Expected:

```text
selected variants: 15
ledger rows: 15
ledger run kinds: ['selected_legacy']
```

- [ ] **Step 2: Report remaining risk**

Final report must state:
- Tests run and pass/fail status.
- Whether `results/` contains only `selected_15` and `new_15`.
- Whether `results.tsv` contains exactly 15 `selected_legacy` rows.
- That no rerun of the 15 was started.
- Any selection-family difference from the dry-run expectation.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | not run | Not required for this harness refactor |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | not run | Outside voice skipped for quick review |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 4 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | not applicable | No UI scope |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | not run | Not required for local research harness |

- **UNRESOLVED:** 0 unresolved decisions. Season chose local execution/results, full artifacts, and refactoring existing handoff code.
- **VERDICT:** ENG REVIEW FOUND REQUIRED PLAN CHANGES — revise before implementation.
