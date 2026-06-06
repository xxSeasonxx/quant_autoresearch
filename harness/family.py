"""Family Identifier — a computed fingerprint of the signal STRUCTURE (FR-E4).

The budget is keyed to a *family*, and family is the AC-2 linchpin: relabeling a free-text
thesis or tweaking a `[params]` value must NOT mint a fresh family (and so cannot mint fresh
budget). The only honest way to make "family" unforgeable is to compute it from the thing the
agent cannot relabel away — the **signal-construction code itself** — with everything an agent
could trivially permute normalized out.

What is fingerprinted:

- The strategy module's ``generate_decisions`` function plus every module-level function it
  transitively calls (the signal-construction closure). Helpers the entry point does not reach
  are irrelevant to the structure and are excluded, so dead code cannot perturb the id.

What is normalized OUT (so it cannot change the id):

- **Numeric and string literal VALUES** — every ``Constant`` is replaced by a type tag
  (``<num>``/``<str>``/``<const>``). A threshold of ``0.012`` vs ``0.015``, ``MIN_VOTES=4`` vs
  ``5``, or a renamed metadata string are the *same* structure. (This is what makes a param-only
  or literal-only change collapse to one family.)
- **Docstrings** — the leading string expression of every function body is dropped, so rewriting
  the prose thesis in a docstring cannot change the id.
- **Local variable / argument names** — alpha-renamed to positional placeholders
  (``v0``, ``v1`` …) within each function, so ``lookback`` → ``window`` is the same structure.
- **Cosmetic ordering** — keyword arguments and the set of fingerprinted functions are sorted
  deterministically, so reordering kwargs or function definitions does not change the id.

What is PRESERVED (so a genuinely different signal is a NEW family):

- Control-flow shape (the kinds and nesting of statements/expressions), operators (``>`` vs
  ``<``, ``+`` vs ``-``), the *names of attributes/methods/functions called* (``_rsi`` vs
  ``_macd_histogram``), comparison/boolean structure, and the call graph. Change the logic and
  the structure hash changes.

Pure: ``ast`` + ``hashlib`` over source text. Deterministic, no clock, no ``quant_strategies``
import. The harness computes this from the strategy file the Experiment references; the agent
never supplies it.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

# The signal entry point every strategy module exposes (the foundation's pure contract).
ENTRY_POINT = "generate_decisions"

# Algorithm version: bump if the normalization rules below change so old ids are not silently
# treated as comparable to new ones (it is part of the hashed payload).
_FINGERPRINT_VERSION = "family-v1"


class FamilyError(ValueError):
    """Raised when a strategy source has no fingerprintable signal structure."""


def compute_family_id(source: str, *, entry_point: str = ENTRY_POINT) -> str:
    """Compute the deterministic family fingerprint of a strategy module's source.

    Parses ``source``, isolates ``entry_point`` and the module-level functions it transitively
    calls, normalizes out literal values / docstrings / local names / kwarg order, and hashes
    the canonical structure. Raises ``FamilyError`` if ``entry_point`` is absent.
    """
    tree = ast.parse(source)
    functions = _module_functions(tree)
    if entry_point not in functions:
        raise FamilyError(
            f"strategy source defines no {entry_point!r} — cannot fingerprint signal structure"
        )

    reachable = _reachable_functions(entry_point, functions)
    # Canonicalize each reachable function independently, then join in a stable order so the
    # order functions happen to be defined in the file does not change the id.
    parts = [_canonical_function(name, functions[name]) for name in sorted(reachable)]
    payload = _FINGERPRINT_VERSION + "\n" + "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_family_id_from_path(path: str | Path, *, entry_point: str = ENTRY_POINT) -> str:
    """Compute the family id from a strategy file on disk (UTF-8)."""
    p = Path(path)
    if not p.is_file():
        raise FamilyError(f"strategy file not found: {p}")
    return compute_family_id(p.read_text(encoding="utf-8"), entry_point=entry_point)


# --------------------------------------------------------------------------- #
# Call-graph extraction (the signal-construction closure).
# --------------------------------------------------------------------------- #


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """All module-level ``def`` (and ``async def``) by name. Nested defs travel with their
    enclosing function body, so only the top-level definitions are roots of the call graph."""
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node  # type: ignore[assignment]
    return out


def _called_names(fn: ast.AST) -> set[str]:
    """Bare-name calls inside ``fn`` (``foo(...)`` → ``foo``).

    Only direct-name calls reference *module-level* functions; attribute/method calls
    (``x.foo()``) are part of the structure (the method name is preserved in the canonical
    form) but are not module functions to recurse into.
    """
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def _reachable_functions(
    entry: str, functions: dict[str, ast.FunctionDef]
) -> set[str]:
    """The transitive closure of module-level functions called from ``entry`` (inclusive).

    BFS over direct-name calls; only names that are themselves module-level functions are
    followed (calls into the engine / stdlib are not module functions and stop the walk, but
    their call *site* is still captured in the canonical structure).
    """
    seen: set[str] = set()
    frontier = [entry]
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        for called in _called_names(functions[name]):
            if called in functions and called not in seen:
                frontier.append(called)
    return seen


# --------------------------------------------------------------------------- #
# Structural normalization (what makes relabeling / param-tweaks collapse).
# --------------------------------------------------------------------------- #


class _StructureNormalizer(ast.NodeTransformer):
    """Rewrite one function's AST into a value-free, name-free structural skeleton.

    - Constants → a type tag (``<num>`` / ``<str>`` / ``<bytes>`` / ``<const>``). VALUE erased.
    - Docstring (leading bare-string statement of any body) → dropped.
    - Local names (params, assigned/used identifiers) → positional placeholders ``vN``, assigned
      deterministically by first textual appearance, so consistent renames collapse.
    - Attribute access (``x.attr``) keeps ``attr`` (the called method/field IS structure) but the
      receiver is normalized like any other name.

    Free (module-global) names — other helper functions, imported engine symbols — are NOT
    renamed: ``_rsi`` vs ``_macd_histogram`` is a real structural difference and is preserved.
    """

    def __init__(self, fn: ast.FunctionDef) -> None:
        # Placeholders are assigned in order of FIRST TEXTUAL APPEARANCE, not by the original
        # names' alphabetical order — otherwise renaming `lookback`→`window` would reshuffle the
        # sort and remap *other* locals (e.g. `m`), breaking rename-invariance. Appearance order
        # depends only on structure, so a consistent rename leaves every placeholder fixed.
        self._local_names = _collect_local_names(fn)
        self._rename: dict[str, str] = {}
        for node in ast.walk(fn):
            name = _bound_name(node)
            if name is not None and name in self._local_names and name not in self._rename:
                self._rename[name] = f"v{len(self._rename)}"

    # -- value erasure --
    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802
        value = node.value
        if isinstance(value, bool):
            tag = "<bool>"  # bool before int (bool is an int subclass)
        elif isinstance(value, (int, float, complex)):
            tag = "<num>"
        elif isinstance(value, str):
            tag = "<str>"
        elif isinstance(value, bytes):
            tag = "<bytes>"
        else:
            tag = "<const>"  # None, Ellipsis, …
        return ast.copy_location(ast.Constant(value=tag), node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:  # noqa: N802
        """Collapse an f-string to a single ``<str>`` tag.

        An f-string's literal text segments and ``{...}`` interpolations are formatting, not
        signal logic. Without this, padding a metadata/log f-string (``f"signal {n}"`` →
        ``f"signal {n} extra"``) changes the segment structure and would mint a new family — a
        cheap relabel vector. Treating any f-string as one opaque string tag closes it: you
        cannot hide signal structure in a formatted message and have it count.
        """
        return ast.copy_location(ast.Constant(value="<str>"), node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:  # noqa: N802
        """Normalize an annotated assignment to a plain assignment (annotation erased).

        ``x: int = 1`` and ``x = 1`` are the same signal structure; a type annotation is style an
        agent can toggle freely. We rewrite the annotated form to the unannotated ``Assign`` shape
        so the two collapse to one family. A bare annotation with no value (``x: int``) becomes a
        ``Pass`` (it binds nothing and runs nothing) so it cannot perturb the structure either.
        """
        self.generic_visit(node)
        if node.value is None:
            return ast.copy_location(ast.Pass(), node)
        return ast.copy_location(
            ast.Assign(targets=[node.target], value=node.value, type_comment=None), node
        )

    # -- local-name erasure --
    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
        new_id = self._rename.get(node.id, node.id)
        return ast.copy_location(ast.Name(id=new_id, ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: N802
        new_arg = self._rename.get(node.arg, node.arg)
        # Drop annotations: a type annotation is not signal structure and an agent could
        # restyle it freely. (Annotations also often carry literals normalized elsewhere.)
        return ast.copy_location(ast.arg(arg=new_arg, annotation=None), node)

    # -- docstring + cosmetic ordering --
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: N802
        self.generic_visit(node)
        node.body = _strip_docstring(node.body)
        node.decorator_list = sorted(node.decorator_list, key=ast.dump)
        node.returns = None
        node.name = "fn"  # the def's own name is the call-graph key, not part of its body shape
        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        self.generic_visit(node)
        # Keyword-argument order is cosmetic: a(x=1, y=2) ≡ a(y=2, x=1). Sort by (key, dump).
        node.keywords = sorted(node.keywords, key=lambda k: (k.arg or "", ast.dump(k)))
        return node


def _bound_name(node: ast.AST) -> str | None:
    """If ``node`` introduces a local name (a Store ``Name``, an ``arg``, or a nested def/class),
    return that name; else None. Used to assign placeholders in structural-walk order."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return node.id
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return None


def _collect_local_names(fn: ast.FunctionDef) -> set[str]:
    """Every name bound anywhere in ``fn``'s tree: all args (including nested-function args),
    any ``Name`` in a Store context, and nested def/class names. These are alpha-renamed;
    everything else (module globals, imported symbols, called helpers) is left intact as
    structure. The set must agree with the ``_bound_name`` walk in ``_StructureNormalizer``
    (which assigns placeholders in structural-walk order) — collect uniformly over the WHOLE
    tree so a nested-function arg is renamed too and rename-invariance holds across closures.
    The function's own name is excluded (it is the call-graph key, not part of its body)."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if node is fn:
            continue
        bound = _bound_name(node)
        if bound is not None:
            names.add(bound)
    return names


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop a leading bare-string-literal statement (the docstring) from a body.

    After ``_StructureNormalizer`` runs, a docstring is an ``Expr(Constant('<str>'))``; we detect
    it pre-normalization too (a real string) so the rule holds regardless of visit order.
    """
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        val = body[0].value.value
        if isinstance(val, str) or val == "<str>":
            return body[1:]
    return body


def _canonical_function(name: str, fn: ast.FunctionDef) -> str:
    """The canonical, value-free structural string for one function.

    ``name`` (the call-graph key) is prefixed so swapping two functions' bodies is a different
    structure; the body itself is the normalized, value-erased dump.
    """
    # Work on a deep copy so the source tree is never mutated across calls.
    clone = _StructureNormalizer(fn).visit(_deepcopy_ast(fn))
    ast.fix_missing_locations(clone)
    # ``include_attributes=False`` strips line/col so whitespace/formatting changes don't matter.
    return f"def {name}:\n" + ast.dump(clone, include_attributes=False)


def _deepcopy_ast(node: ast.AST) -> ast.AST:
    """Deep-copy an AST node (so normalization never mutates the parsed source tree)."""
    import copy

    return copy.deepcopy(node)
