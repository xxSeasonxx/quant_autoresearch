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
    assert "symbols are special" in text
    assert "fixed symbol universe" in text
    assert "protocol/universe variant" in text


def test_program_states_objective_and_autonomy_boundary():
    text = _normalized()
    assert "senior quant researcher" in text
    assert "profitable in the real world" in text
    assert "the harness guides the experiment" in text
    assert "the goal is simple" in text
    assert "best gated train survivor" in text
    assert "do not pause once the loop has begun" in text
    assert "protocol stop rule fires" in text


def test_program_requires_rationale_foundation_and_variant_refresh():
    text = _normalized()
    assert "set the working thesis in `rationale.md`" in text
    assert "thesis-guided variants" in text
    assert "refresh `rationale.md`" in text
    assert "bold thesis-guided variant" in text
    assert "update `upstream_limitations_todo.md`" in text


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


def test_program_defines_artifact_authority_for_active_loop():
    text = _normalized()
    assert "artifact authority" in text
    assert "active loop inputs" in text
    assert "latest quick-run artifact directory recorded in `results.tsv`" in text
    assert "generated audit and handoff artifacts" in text
    assert "season downstream-only artifacts" in text
    assert "historical or non-contract context" in text
    assert "terminal manifests" in text
    assert "not routine inputs for choosing train edits" in text
    assert "do not browse the rest of the repo during ordinary train iteration" in text
    assert "oos drift reviews" in text
    assert "must not be used during train iteration" in text
