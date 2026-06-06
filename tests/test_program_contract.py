"""program.md contract — the FINAL one-page agent loop (the headline deliverable).

Asserts program.md names the EXACT CLI commands the harness exposes, the editable/read-only
split, and the new-world loop — and does NOT contain the SUPERSEDED language (the hill-climb
"keep if the score rose", the per-family budget, or the retired `--explore`/`--promote`/
`net_return` shell). The rigor lives in the harness; the contract stays short and explicit.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "program.md"


def _text() -> str:
    return PROGRAM.read_text()


def _normalized() -> str:
    return " ".join(_text().split())


def test_program_names_the_exact_cli_commands():
    """The three agent commands, named exactly as built (conda run -n quant python -m harness.cli)."""
    norm = _normalized()
    assert "conda run -n quant python -m harness.cli status" in norm
    assert 'conda run -n quant python -m harness.cli run --desc "<thesis>"' in norm
    assert "conda run -n quant python -m harness.cli evaluate --desc" in norm


def test_program_states_the_editable_and_read_only_split():
    norm = _normalized()
    # Editable: strategy.py + experiment.toml [params].
    assert "`strategy.py`" in norm
    assert "`experiment.toml`" in norm
    assert "EDITABLE" in norm
    # Read-only: the Protocol, the harness package, the ledger.
    assert "READ-ONLY" in norm
    assert "`protocol.toml`" in norm
    assert "`harness/` package" in norm
    assert "ledger" in norm


def test_program_keeps_the_new_world_loop_semantics():
    # Concept presence is case-insensitive (program.md uppercases some terms for emphasis).
    norm = _normalized().lower()
    required = [
        "falsifiable, causal hypothesis",
        "robust plateau",
        "escalation gate",  # the harness-enforced gate
        "logs the bet",
        "swing big",
        "quota",
        "global to the campaign",  # the budget is global, not per-family
        "satisfice on train",
        "never early stop",
        "never run the lockbox",
    ]
    for phrase in required:
        assert phrase in norm, f"missing required phrase: {phrase!r}"


def test_program_does_not_contain_superseded_hill_climb_language():
    """The hill-climb 'keep if the score rose' is GONE (FR-D3)."""
    norm = _normalized().lower()
    banned = [
        "keep if the score rose",
        "keep if the score rises",
        "keep it only if the score rose",
        "best-so-far",
        "if promotion reports",
        "decision\": \"keep\"",
    ]
    for phrase in banned:
        assert phrase not in norm, f"superseded hill-climb language present: {phrase!r}"


def test_program_does_not_contain_per_family_budget_language():
    """The budget is GLOBAL; the 'fresh family gets its own budget' line is GONE."""
    norm = _normalized().lower()
    banned = [
        "fresh family gets its own budget",
        "its own budget",
        "per-family budget",
        "reset per family",  # only the negation "not reset per family" is allowed (checked below)
    ]
    for phrase in banned:
        # Allow the explicit negation that the budget is NOT reset per family.
        if phrase == "reset per family" and "not reset per family" in norm:
            continue
        assert phrase not in norm, f"superseded per-family-budget language present: {phrase!r}"


def test_program_does_not_reference_retired_runner_shell():
    """No `--explore` / `--promote` / `net_return` / runner.py / results.tsv (retired in P1-P5)."""
    norm = _normalized().lower()
    banned = [
        "--explore",
        "--promote",
        "--confirm",
        "net_return",
        "runner.py",
        "results.tsv",
        "scoring.py",
        "promotion screening",
        "max_attempts",
        "remaining_attempts",
    ]
    for phrase in banned:
        assert phrase not in norm, f"retired legacy reference present: {phrase!r}"
