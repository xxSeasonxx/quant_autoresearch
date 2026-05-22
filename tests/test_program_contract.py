from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "program.md"


def test_program_names_exactly_strategy_and_experiment_toml_as_loop_editable_files():
    text = PROGRAM.read_text()

    assert "Editable during a research loop:" in text
    editable_section = text.split("Editable during a research loop:", 1)[1].split(
        "Read-only during a research loop:", 1
    )[0]
    editable_lines = [
        line.strip() for line in editable_section.splitlines() if line.strip()
    ]
    assert editable_lines == ["- `strategy.py`", "- `experiment.toml`"]


def test_program_does_not_expose_attempt_count_or_max_attempts():
    text = PROGRAM.read_text().lower()

    banned_fragments = (
        "attempt_count",
        "max_attempts",
        "24 attempts",
        "attempt budget",
        "run 24",
    )
    assert all(fragment not in text for fragment in banned_fragments)


def test_program_requires_quant_research_review_not_metric_chasing():
    text = PROGRAM.read_text()

    required = [
        "Think like a quant researcher",
        "Evidence review",
        "causal timing",
        "trade count",
        "costs",
        "data quality",
        "overfit",
        "Loop feedback only",
    ]
    for phrase in required:
        assert phrase in text


def test_program_allows_quant_judgment_window_changes_without_cherry_picking():
    text = PROGRAM.read_text()

    required = [
        "Choose windows from a quant research perspective",
        "`active_window_id`",
        "`--window-id`",
        "regime",
        "sample quality",
        "holdout/stress check",
        "falsifier",
        "Do not cherry-pick windows",
    ]
    for phrase in required:
        assert phrase in text


def test_program_allows_quant_perspective_symbol_changes_without_cherry_picking():
    text = PROGRAM.read_text()

    required = [
        "Choose symbols from a quant research perspective",
        "symbol universe",
        "liquidity",
        "data coverage",
        "market structure",
        "representative breadth",
        "falsifier",
        "Do not cherry-pick",
        "symbols just to rescue",
    ]
    for phrase in required:
        assert phrase in text


def test_program_documents_upstream_limitation_reporting():
    text = PROGRAM.read_text()

    assert "quant_strategies" in text
    assert "quant_data" in text
    assert "document the limitation" in text
