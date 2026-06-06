"""Family Identifier — the signal-STRUCTURE fingerprint (FR-E4); the AC-2 unit linchpin.

These tests pin the normalization contract: anything an agent could trivially permute to
"split" one signal into two (literal values, the prose thesis, local names, kwarg order, dead
code) maps to the SAME family; a genuinely different signal structure maps to a NEW family.
The campaign-level AC-2 assertion (no relabeling raises the global cap) lives in
``test_selection_budget.py``; here we prove the mechanism it relies on.
"""

from __future__ import annotations

import textwrap

import pytest

from harness.family import FamilyError, compute_family_id, compute_family_id_from_path

# A minimal but representative signal: a literal threshold, a docstring, a helper call.
_BASE = '''
def _signal(x, lookback, threshold):
    """Long when momentum exceeds the threshold."""
    m = x[-1] / x[-lookback] - 1.0
    if m > threshold:
        return "long"
    return None


def generate_decisions(bars, params):
    """The agent's prose thesis lives here and can be rewritten freely."""
    lookback = params["lookback"]
    threshold = 0.012
    out = []
    for series in bars:
        side = _signal(series, lookback, threshold)
        if side is not None:
            out.append(side)
    return out
'''


def test_literal_value_change_is_the_same_family():
    """A hardcoded numeric literal differing (0.012 → 0.015) is a PARAM-equivalent change:
    same signal structure ⇒ same family. This is the core of AC-2 (a tweak can't split)."""
    a = compute_family_id(_BASE)
    b = compute_family_id(_BASE.replace("0.012", "0.015"))
    assert a == b


def test_docstring_rethesis_is_the_same_family():
    """Rewriting the free-text thesis (a docstring) does not change the structure ⇒ same id.
    Relabeling the thesis cannot mint a new family (FR-E4)."""
    rethesised = _BASE.replace(
        "The agent's prose thesis lives here and can be rewritten freely.",
        "A COMPLETELY DIFFERENT STORY about mean reversion and regime filters.",
    )
    assert compute_family_id(_BASE) == compute_family_id(rethesised)


def test_local_variable_rename_is_the_same_family():
    """Alpha-renaming local variables/params (lookback → window) is cosmetic ⇒ same id."""
    renamed = _BASE.replace("lookback", "window").replace("threshold", "thr")
    assert compute_family_id(_BASE) == compute_family_id(renamed)


def test_kwarg_reordering_is_the_same_family():
    src1 = textwrap.dedent(
        '''
        def helper(a, b, c):
            return a + b + c

        def generate_decisions(bars, params):
            return helper(a=1, b=2, c=3)
        '''
    )
    src2 = textwrap.dedent(
        '''
        def helper(a, b, c):
            return a + b + c

        def generate_decisions(bars, params):
            return helper(c=3, a=1, b=2)
        '''
    )
    assert compute_family_id(src1) == compute_family_id(src2)


def test_whitespace_and_comment_change_is_the_same_family():
    noisy = _BASE.replace("    out = []", "\n    # a fresh comment\n    out = []")
    assert compute_family_id(_BASE) == compute_family_id(noisy)


def test_dead_unreached_helper_does_not_change_family():
    """A helper ``generate_decisions`` does not call is not part of the signal closure ⇒
    adding/removing it cannot perturb the id."""
    with_dead = _BASE + textwrap.dedent(
        '''
        def _never_called(z):
            return z * 2 + 7
        '''
    )
    assert compute_family_id(_BASE) == compute_family_id(with_dead)


def test_changing_an_operator_is_a_new_family():
    """``>`` → ``<`` flips the signal logic: a genuinely different structure ⇒ new family."""
    flipped = _BASE.replace("if m > threshold:", "if m < threshold:")
    assert compute_family_id(_BASE) != compute_family_id(flipped)


def test_calling_a_different_helper_is_a_new_family():
    """Swapping which helper the signal calls is a structural change ⇒ new family."""
    variant = _BASE.replace("_signal(series", "_other_signal(series").replace(
        "def _signal(", "def _other_signal("
    )
    # Same *shape* but a different call-graph key — the called name is preserved as structure.
    assert compute_family_id(_BASE) != compute_family_id(variant)


def test_adding_a_real_statement_to_the_signal_is_a_new_family():
    extended = _BASE.replace(
        "        if side is not None:\n            out.append(side)",
        "        if side is not None:\n            side = side.upper()\n            out.append(side)",
    )
    assert compute_family_id(_BASE) != compute_family_id(extended)


def test_changing_a_called_helper_body_is_a_new_family():
    """A structural change *inside* a reached helper changes the family (the closure is hashed,
    not just the entry point)."""
    changed_helper = _BASE.replace(
        "    m = x[-1] / x[-lookback] - 1.0",
        "    m = x[-1] / x[-lookback] - 1.0\n    m = abs(m)",
    )
    assert compute_family_id(_BASE) != compute_family_id(changed_helper)


def test_missing_entry_point_raises():
    with pytest.raises(FamilyError):
        compute_family_id("def not_the_entry(a):\n    return a\n")


def test_real_strategy_param_only_change_is_the_same_family(tmp_path):
    """End-to-end on the real strategy.py: it is fingerprinted from source, and since params
    live in the Experiment (never the source), every param set is the SAME family. We also
    confirm a literal edit to the source is the same family, while a logic edit differs."""
    import strategy  # the repo's agent-editable strategy module

    src = __import__("inspect").getsource(strategy)
    base_id = compute_family_id(src)

    # A REAL literal-only edit to the source: change a hardcoded default-param value
    # (0.08 → 0.09 for BASE_POSITION_PCT). Params live in the Experiment, not the source, so a
    # numeric-literal change is structure-invariant ⇒ same family. (Asserted independently of
    # ``test_literal_value_change_is_the_same_family``, which pins the same rule on a fixture.)
    literal_edit = src.replace('"BASE_POSITION_PCT": 0.08', '"BASE_POSITION_PCT": 0.09', 1)
    assert literal_edit != src  # the edit actually changed the source (no vacuous .replace)
    # Flip a real comparison operator deep in the signal — must be a NEW family.
    logic_edit = src.replace("if rsi > 50.0:", "if rsi < 50.0:", 1)
    assert logic_edit != src

    assert compute_family_id(literal_edit) == base_id
    assert compute_family_id(logic_edit) != base_id

    # From a path round-trips identically.
    p = tmp_path / "strategy_copy.py"
    p.write_text(src, encoding="utf-8")
    assert compute_family_id_from_path(p) == base_id
