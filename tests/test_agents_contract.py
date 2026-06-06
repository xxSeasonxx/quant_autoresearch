"""AGENTS.md contract — the durable agent role/mindset/boundaries for the new world.

Asserts AGENTS.md describes the immutable-harness + thin-agent-loop split, the hypothesis-only
editable surface, the three commands, the harness-enforced judgment, and never touching the
Protocol / ledger / Lockbox — and does NOT carry the retired promotion-screen vocabulary.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def test_agents_describes_the_new_world_role_and_boundaries():
    text = AGENTS.read_text()
    required = [
        "immutable harness",
        "thin agent loop",
        "structurally impossible to graduate",
        "not** the final validation framework",
        "hypothesis-only",
        "`strategy.py`",
        "`experiment.toml`",
        "`protocol.toml`",
        "`harness/` package",
        "escalation gate",
        "swing-big",
        "Never run the Lockbox",
        "Never early stop",
        "UPSTREAM_LIMITATIONS_TODO.md",
    ]
    for phrase in required:
        assert phrase in text, f"missing required phrase: {phrase!r}"


def test_agents_does_not_carry_retired_promotion_vocabulary():
    text = AGENTS.read_text().lower()
    banned = [
        "--explore",
        "--promote",
        "runner.py",
        "scoring.py",
        "net_return",
        "results.tsv",
        "cheap guard screen",
        "rotating probe",
        "keep if the score rose",
    ]
    for phrase in banned:
        assert phrase not in text, f"retired vocabulary present: {phrase!r}"
