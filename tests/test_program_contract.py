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


def test_program_rejects_blind_parameter_sweeps():
    text = PROGRAM.read_text()
    normalized = " ".join(text.split())

    required = [
        "Do not default to a parameter sweep",
        "improve the strategy hypothesis",
        "signal construction",
        "risk filter",
        "timing logic",
        "Parameter changes are valid only when",
        "better expresses that quant idea",
        "do not tune numbers just because",
        "the quant reason the new value should improve the",
        "strategy rather than merely fitting the last run",
    ]
    for phrase in required:
        assert phrase in normalized


def test_program_allows_quant_judgment_window_changes_without_cherry_picking():
    text = PROGRAM.read_text()

    required = [
        "Choose windows from a quant research perspective",
        "120 to 180 calendar days",
        "`active_window_id`",
        "`--window-id`",
        "regime",
        "sample quality",
        "holdout/stress check",
        "recent out-of-sample evidence",
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


def test_program_requires_confirmed_candidate_protocol():
    text = PROGRAM.read_text()
    normalized = " ".join(text.split())

    required = [
        "Candidate confirmation",
        "A one-window result is exploration evidence only",
        "`runner.py --confirm` remains available",
        "manual recent-window bundle diagnostic",
        "default fast loop escalates serious candidates",
        "`runner.py --promote`",
        "Recent windows dominate the score",
        "Do not prune symbols or windows because of one isolated result",
        "trade evidence changed your belief",
        "what causal hypothesis follows",
        "what result would falsify it",
    ]
    for phrase in required:
        assert phrase in normalized


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


def test_program_loop_uses_promotion_artifacts_and_decisions():
    text = PROGRAM.read_text()
    normalized = " ".join(text.split())

    required = [
        "`promotion_score.json`",
        "`promotion_summary.json`",
        "If promotion reports `promote`, advance",
        "If promotion reports `reject`",
        "previous promoted or baseline commit",
        "run_kind",
        "promotion",
    ]
    for phrase in required:
        assert phrase in normalized

    banned = [
        "For confirmation, inspect `candidate_score.json`",
        "If a confirmed candidate reports `keep`",
        "If a confirmed candidate reports `discard`",
        "confirmed candidate works",
    ]
    for phrase in banned:
        assert phrase not in normalized
