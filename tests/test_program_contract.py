from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "program.md"


def _normalized() -> str:
    return " ".join(PROGRAM.read_text().split()).lower()


def test_program_mirrors_reference_autoresearch_sections():
    text = _normalized()
    for section in [
        "## setup",
        "## experimentation",
        "## output format",
        "## logging results",
        "## the experiment loop",
    ]:
        assert section in text


def test_program_states_thin_editable_surface_and_read_only_protocol():
    text = _normalized()
    assert "editable" in text
    assert "`strategy.py`" in text
    assert "bounded params" in text
    assert "read-only" in text
    assert "`protocol.toml`" in text
    assert "symbols" in text
    assert "cost" in text
    assert "fill" in text
    assert "loop constants" in text


def test_program_forbids_in_loop_evaluate_and_old_harness_commands():
    text = _normalized()
    assert "no `evaluate`" in text or "do not run `evaluate`" in text
    for phrase in [
        "python -m harness.cli",
        "selection",
        "lockbox",
        "graduation",
        "--promote",
        "--explore",
    ]:
        assert phrase not in text


def test_program_documents_results_tsv_and_plateau_stop():
    text = _normalized()
    assert "results.tsv" in text
    assert "plateau" in text
    assert "max_iterations" in text
    assert "plateau_patience" in text
