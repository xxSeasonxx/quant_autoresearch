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
