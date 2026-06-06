"""Session shell — the never-early-stop loop lifecycle (FR-A1).

The thin, clean parts of the legacy ``runner.py`` session shell, ported deliberately and
shorn of everything coupled to the retired ``net_return/day`` scoring / promotion model. What
survives the port:

- **git commit provenance** — the short HEAD hash for ledger/observability (``current_commit``);
- **a session marker** — a small JSON file (``.autoresearch_session.json``) recording the active
  campaign's ledger + book + protocol-hash so a resumed process picks up the same campaign;
- **never-early-stop status** — the session ends only when the *harness* says so (the global
  budget is spent — a quota, FR-E5) or a *human* interrupts. **There is no attempt countdown.**

What is deliberately NOT ported (it encoded the diagnosed anti-patterns, retirement map §6):
the ``max_attempts`` budget, ``best_score`` / hill-climb ``decision_for_score``, the
``results.tsv`` writer, the promotion/confirmation orchestration, and the explore/promote modes.
Budget is the Selection-look quota (``harness.budget``), not an attempt counter; "keep if the
score rose" is GONE (FR-D3); the ledger (``harness.ledger``) is the system of record.

Pure of ``quant_strategies``: this is process/git/JSON plumbing only. The status is derived from
the injected ``BudgetManager`` (a quota), so the agent is never handed a countdown (FR-E5).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from harness.budget import BudgetManager

# The session marker filename (repurposed from the legacy results-dir pointer): it now records
# the active campaign's paths so a resumed process attaches to the same ledger/book.
SESSION_MARKER_NAME = ".autoresearch_session.json"


def current_commit(repo_root: str | Path) -> str | None:
    """The short HEAD commit hash for provenance, or None if git is unavailable.

    Ported verbatim-in-spirit from the legacy runner: a 5s-timeout ``git rev-parse``. Failure
    (no git, detached, timeout) degrades to None rather than crashing the session.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


@dataclass(frozen=True)
class SessionStatus:
    """The never-early-stop session status — a QUOTA state, never a countdown (FR-E5).

    ``active`` while the harness can still issue Selection looks; ``budget_spent`` once the
    global budget is exhausted (the harness stops issuing looks — graduate the best or retire).
    ``looks_remaining`` is surfaced for observability (NFR-5) but is a quota, NOT a per-call
    countdown the agent should pause on: the loop runs until the harness ends it or a human
    interrupts (the agent never asks "should I keep going?").
    """

    state: str  # "active" | "budget_spent"
    looks_remaining: int
    looks_charged: int
    cap: int

    @property
    def ended(self) -> bool:
        """True iff the harness has ended the session (budget spent). The ONLY harness-side
        stop condition; otherwise the session is open until a human interrupts."""
        return self.state == "budget_spent"


def session_status(budget: BudgetManager) -> SessionStatus:
    """Derive the session status from the global Selection-look budget (a quota, FR-E5).

    The session is ``active`` while the budget can still reserve a look, and ``budget_spent``
    once it cannot. This is the single never-early-stop signal: the harness ends the session by
    spending the budget, not by counting attempts.
    """
    status = budget.status()
    return SessionStatus(
        state="active" if not status.spent else "budget_spent",
        looks_remaining=status.remaining,
        looks_charged=status.charged,
        cap=status.cap,
    )


# --------------------------------------------------------------------------- #
# The session marker (resume the same campaign across processes).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionMarker:
    """Pointer to the active campaign's durable state (so a resumed process attaches to it).

    ``ideas_since_new_family`` is the **swing-big cadence counter** (FR-A4): the number of IDEAS
    the agent has explored — every ``run`` and ``evaluate`` is an idea — since the last
    ``evaluate`` that LOGGED a structurally-new family. It lives here (not in the ledger) because
    a free Train ``run`` is an idea too: the cadence must count the agent circling one family on
    Train, which the ledger (logged looks only) cannot see. Every logged look is already a new
    family (the escalation new-thesis condition), so a ledger-only counter would be permanently
    zero and swing-big would never bite — counting ideas here is what makes it a real, independent
    cadence. Reset to 0 on a new-family logged bet; incremented on every idea otherwise.
    """

    ledger_path: str
    book_path: str
    protocol_hash: str
    ideas_since_new_family: int = 0


def advance_idea(marker: SessionMarker, *, logged_new_family: bool) -> SessionMarker:
    """Advance the swing-big cadence counter for one idea (a ``run`` or ``evaluate``).

    A logged NEW-family bet RESETS the counter to 0 (the agent just swung); any other idea (a
    Train ``run``, a routed ``evaluate``, or a logged bet of an already-counted family) increments
    it. The harness's escalation gate then requires a new family once the counter reaches ``M``.
    """
    if logged_new_family:
        return _with_count(marker, 0)
    return _with_count(marker, marker.ideas_since_new_family + 1)


def _with_count(marker: SessionMarker, count: int) -> SessionMarker:
    return SessionMarker(
        ledger_path=marker.ledger_path,
        book_path=marker.book_path,
        protocol_hash=marker.protocol_hash,
        ideas_since_new_family=count,
    )


def write_session_marker(repo_root: str | Path, marker: SessionMarker) -> Path:
    """Write the session marker atomically (temp-file + ``os.replace``, fail-safe NFR-6).

    A crash mid-write never leaves a torn marker — the file is the old or the new state. The
    marker is a convenience for resuming a campaign; the ledger/book remain the system of record.
    """
    path = Path(repo_root) / SESSION_MARKER_NAME
    payload = {
        "ledger_path": marker.ledger_path,
        "book_path": marker.book_path,
        "protocol_hash": marker.protocol_hash,
        "ideas_since_new_family": int(marker.ideas_since_new_family),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def read_session_marker(repo_root: str | Path) -> SessionMarker | None:
    """Read the active campaign's session marker, or None if absent/malformed."""
    path = Path(repo_root) / SESSION_MARKER_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return SessionMarker(
            ledger_path=str(payload["ledger_path"]),
            book_path=str(payload["book_path"]),
            protocol_hash=str(payload["protocol_hash"]),
            ideas_since_new_family=int(payload.get("ideas_since_new_family", 0)),
        )
    except KeyError:
        return None
