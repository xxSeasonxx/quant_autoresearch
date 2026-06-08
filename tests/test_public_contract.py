from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_retired_harness_concepts_are_absent_from_public_docs():
    text = "\n".join(
        [
            _read("README.md").lower(),
            _read("AGENTS.md").lower(),
            _read("program.md").lower(),
        ]
    )
    banned = [
        "selection-look budget",
        "selection budget",
        "trial ledger",
        "family fingerprint",
        "escalation gate",
        "graduation audit",
        "lockbox",
        "python -m harness.cli evaluate",
    ]
    for phrase in banned:
        assert phrase not in text


def test_retired_harness_package_is_not_importable():
    assert not (ROOT / "harness").exists()
    try:
        importlib.import_module("harness")
    except ModuleNotFoundError:
        return
    raise AssertionError("retired harness package is still importable")


def test_loop_module_does_not_import_private_quant_strategies_modules():
    source = "\n".join(
        (ROOT / name).read_text()
        for name in ["protocol.py", "loop.py"]
        if (ROOT / name).exists()
    )
    assert "quant_strategies.engine" not in source
    assert "quant_strategies._" not in source
    assert "run_evaluation" not in source


def test_historical_design_doc_is_explicitly_non_contract():
    text = _read("docs/simplified-autoresearch-loop-design.md").lower()

    assert "historical design / decision record" in text
    assert "not the live implementation contract" in text
    assert "historical implementation sketch" in text
    assert "do not implement from this section" in text


def test_active_openspec_files_are_trackable_without_force_add():
    ignore = (ROOT / ".gitignore").read_text()

    assert "\n/openspec/\n" not in ignore
    assert "/openspec/changes/archive/2026-06-06-*/" in ignore
    assert "/openspec/changes/archive/2026-06-07-*/" in ignore
